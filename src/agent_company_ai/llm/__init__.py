"""LLM provider abstraction layer for Agent Company AI.

Provides a unified interface for interacting with multiple LLM backends
(Anthropic, OpenAI, and any OpenAI-compatible endpoint) through a common
set of data structures and a routing layer.
"""

from agent_company_ai.llm.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    ToolCall,
    ToolDefinition,
)
from agent_company_ai.llm.router import LLMRouter

__all__ = [
    "BaseLLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMRouter",
    "ToolCall",
    "ToolDefinition",
]
