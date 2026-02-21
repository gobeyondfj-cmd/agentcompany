"""Anthropic LLM provider using the ``anthropic`` SDK."""

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


class AnthropicProvider(BaseLLMProvider):
    """LLM provider backed by the Anthropic Messages API.

    Uses :class:`anthropic.AsyncAnthropic` for all network calls so that the
    provider can be used inside ``asyncio`` event loops without blocking.
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
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for the Anthropic provider. "
                "Install it with: pip install anthropic"
            ) from exc

        client_kwargs: dict = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self._client = anthropic.AsyncAnthropic(**client_kwargs)

    # ------------------------------------------------------------------
    # Format conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_system(messages: list[LLMMessage]) -> tuple[str | None, list[LLMMessage]]:
        """Separate the system prompt from the rest of the messages.

        Anthropic expects the system prompt as a top-level parameter, not
        embedded in the messages list.  If multiple system messages are
        present they are concatenated with newlines.
        """
        system_parts: list[str] = []
        non_system: list[LLMMessage] = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
            else:
                non_system.append(msg)
        system_text = "\n".join(system_parts) if system_parts else None
        return system_text, non_system

    @staticmethod
    def _convert_messages(messages: list[LLMMessage]) -> list[dict]:
        """Convert internal ``LLMMessage`` objects to Anthropic's format.

        Key mapping rules:
        - ``assistant`` messages with tool calls become content blocks of
          mixed ``text`` and ``tool_use`` types.
        - ``tool`` messages become ``user`` messages containing a
          ``tool_result`` content block.
        - Plain ``user`` / ``assistant`` messages are passed through.
        """
        converted: list[dict] = []
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                # Build content blocks: optional leading text + tool_use blocks
                content_blocks: list[dict] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    arguments = tc.get("arguments", tc.get("args", {}))
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except (json.JSONDecodeError, TypeError):
                            arguments = {}
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "input": arguments,
                        }
                    )
                converted.append({"role": "assistant", "content": content_blocks})

            elif msg.role == "tool":
                # Anthropic expects tool results as user messages
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id or "",
                                "content": msg.content,
                            }
                        ],
                    }
                )

            else:
                converted.append({"role": msg.role, "content": msg.content})

        return converted

    @staticmethod
    def _convert_tools(tools: list[ToolDefinition]) -> list[dict]:
        """Convert tool definitions to Anthropic's expected schema."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            }
            for tool in tools
        ]

    @staticmethod
    def _parse_response(response) -> LLMResponse:
        """Parse an Anthropic ``Message`` object into our unified format."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input if isinstance(block.input, dict) else {},
                    )
                )

        usage = None
        if response.usage:
            usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        return LLMResponse(
            content="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
            usage=usage,
            stop_reason=response.stop_reason,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> LLMResponse:
        """Send a completion request to the Anthropic Messages API."""
        system_text, non_system_messages = self._extract_system(messages)
        anthropic_messages = self._convert_messages(non_system_messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            response = await self._client.messages.create(**kwargs)
        except Exception as exc:
            logger.error("Anthropic API call failed: %s", exc)
            raise

        return self._parse_response(response)

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> AsyncIterator[str]:
        """Stream text deltas from the Anthropic Messages API."""
        system_text, non_system_messages = self._extract_system(messages)
        anthropic_messages = self._convert_messages(non_system_messages)

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": anthropic_messages,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            logger.error("Anthropic streaming call failed: %s", exc)
            raise
