"""OpenAI LLM provider using the ``openai`` SDK."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from agent_company_ai.llm.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """LLM provider backed by the OpenAI Chat Completions API.

    Uses :class:`openai.AsyncOpenAI` for all network calls.  The ``base_url``
    parameter is forwarded to the client so this provider can target any
    OpenAI-compatible endpoint (e.g. local vLLM, Ollama, LiteLLM, etc.).
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        max_tokens: int = 4096,
    ):
        super().__init__(api_key=api_key, model=model, base_url=base_url, max_tokens=max_tokens)

        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for the OpenAI provider. "
                "Install it with: pip install openai"
            ) from exc

        client_kwargs: dict = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self._client = openai.AsyncOpenAI(**client_kwargs)

    # ------------------------------------------------------------------
    # Format conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_messages(messages: list[LLMMessage]) -> list[dict]:
        """Convert internal ``LLMMessage`` objects to OpenAI chat format.

        Mapping rules:
        - ``system`` / ``user`` / ``assistant`` messages are passed through
          with ``role`` and ``content``.
        - ``assistant`` messages carrying tool calls include a ``tool_calls``
          list with ``function`` sub-objects.
        - ``tool`` messages include ``tool_call_id`` so the API can match
          them to the originating call.
        """
        converted: list[dict] = []
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                openai_tool_calls: list[dict] = []
                for tc in msg.tool_calls:
                    arguments = tc.get("arguments", tc.get("args", {}))
                    if isinstance(arguments, dict):
                        arguments = json.dumps(arguments)
                    elif not isinstance(arguments, str):
                        arguments = json.dumps(arguments)
                    openai_tool_calls.append(
                        {
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("name", ""),
                                "arguments": arguments,
                            },
                        }
                    )
                entry: dict = {
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": openai_tool_calls,
                }
                converted.append(entry)

            elif msg.role == "tool":
                converted.append(
                    {
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": msg.tool_call_id or "",
                    }
                )

            else:
                converted.append({"role": msg.role, "content": msg.content})

        return converted

    @staticmethod
    def _convert_tools(tools: list[ToolDefinition]) -> list[dict]:
        """Convert tool definitions to OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        """Parse an OpenAI ``ChatCompletion`` into our unified format."""
        choice = response.choices[0]
        message = choice.message

        # Extract text content
        content = message.content or ""

        # Extract tool calls
        tool_calls: list[ToolCall] | None = None
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=arguments,
                    )
                )

        # Extract usage
        usage = None
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }

        # Map finish_reason to a normalised stop_reason
        stop_reason = choice.finish_reason

        return LLMResponse(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            stop_reason=stop_reason,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        """Send a completion request to the OpenAI Chat Completions API."""
        openai_messages = self._convert_messages(messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": openai_messages,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("OpenAI API call failed: %s", exc)
            raise

        return self._parse_response(response)

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[str]:
        """Stream text deltas from the OpenAI Chat Completions API."""
        openai_messages = self._convert_messages(messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": openai_messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as exc:
            logger.error("OpenAI streaming call failed: %s", exc)
            raise
