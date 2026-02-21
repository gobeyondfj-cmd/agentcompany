"""Tool registry - register and discover tools for agents."""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from agent_company_ai.llm.base import ToolDefinition


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any] | Callable[..., Awaitable[Any]]
    is_async: bool = False

    def to_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )

    async def execute(self, **kwargs) -> str:
        if self.is_async:
            result = await self.func(**kwargs)
        else:
            result = self.func(**kwargs)
        if isinstance(result, str):
            return result
        return json.dumps(result, default=str)


class ToolRegistry:
    """Global registry of available tools."""

    _instance: ToolRegistry | None = None
    _tools: dict[str, Tool]

    def __init__(self):
        self._tools = {}

    @classmethod
    def get(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_tools(self, names: list[str] | None = None) -> list[Tool]:
        if names is None:
            return list(self._tools.values())
        return [self._tools[n] for n in names if n in self._tools]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())


def _extract_parameters(func: Callable) -> dict:
    """Extract JSON Schema parameters from function type hints."""
    sig = inspect.signature(func)
    properties = {}
    required = []

    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue

        annotation = param.annotation
        json_type = type_map.get(annotation, "string")
        prop: dict[str, Any] = {"type": json_type}

        # Use docstring parsing would be overkill; keep descriptions in the decorator
        properties[name] = prop

        if param.default is inspect.Parameter.empty:
            required.append(name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def tool(name: str, description: str, parameters: dict[str, Any] | None = None):
    """Decorator to register a function as a tool.

    Usage:
        @tool("web_search", "Search the web for information")
        def web_search(query: str) -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        params = parameters if parameters is not None else _extract_parameters(func)
        t = Tool(
            name=name,
            description=description,
            parameters=params,
            func=func,
            is_async=inspect.iscoroutinefunction(func),
        )
        ToolRegistry.get().register(t)
        return func

    return decorator
