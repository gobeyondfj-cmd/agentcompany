"""LLM provider abstraction layer for AgentCompany.

Provides a unified interface for interacting with multiple LLM backends
(Anthropic, OpenAI, and any OpenAI-compatible endpoint) through a common
set of data structures and a routing layer.
"""

from agentcompany.llm.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    ToolCall,
    ToolDefinition,
)
from agentcompany.llm.router import LLMRouter

__all__ = [
    "BaseLLMProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMRouter",
    "ToolCall",
    "ToolDefinition",
]
