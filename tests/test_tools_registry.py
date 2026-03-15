"""Tests for the ToolRegistry."""

from __future__ import annotations

import asyncio
import json

import pytest
from agent_company_ai.tools.registry import ToolRegistry, Tool, tool, _extract_parameters


class TestToolRegistry:
    """Test ToolRegistry operations."""

    def test_register_and_get(self, tool_registry: ToolRegistry):
        t = Tool(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            func=lambda: "ok",
        )
        tool_registry.register(t)
        assert tool_registry.get_tool("test_tool") is t

    def test_get_nonexistent_returns_none(self, tool_registry: ToolRegistry):
        assert tool_registry.get_tool("nonexistent") is None

    def test_list_names(self, tool_registry: ToolRegistry):
        t = Tool(
            name="my_tool",
            description="desc",
            parameters={"type": "object", "properties": {}},
            func=lambda: "ok",
        )
        tool_registry.register(t)
        assert "my_tool" in tool_registry.list_names()

    def test_get_tools_filtered(self, tool_registry: ToolRegistry):
        for name in ["a", "b", "c"]:
            tool_registry.register(Tool(
                name=name,
                description=f"Tool {name}",
                parameters={"type": "object", "properties": {}},
                func=lambda: "ok",
            ))
        result = tool_registry.get_tools(["a", "c"])
        assert len(result) == 2
        assert {t.name for t in result} == {"a", "c"}

    def test_get_tools_none_returns_all(self, tool_registry: ToolRegistry):
        tool_registry.register(Tool(
            name="x",
            description="X",
            parameters={"type": "object", "properties": {}},
            func=lambda: "ok",
        ))
        assert len(tool_registry.get_tools(None)) >= 1


class TestToolExecution:
    """Test Tool.execute()."""

    def test_sync_execution(self):
        t = Tool(
            name="sync_tool",
            description="sync",
            parameters={"type": "object", "properties": {}},
            func=lambda: "hello",
            is_async=False,
        )
        result = asyncio.run(t.execute())
        assert result == "hello"

    def test_async_execution(self):
        async def async_fn():
            return "async hello"

        t = Tool(
            name="async_tool",
            description="async",
            parameters={"type": "object", "properties": {}},
            func=async_fn,
            is_async=True,
        )
        result = asyncio.run(t.execute())
        assert result == "async hello"

    def test_dict_result_json_serialized(self):
        t = Tool(
            name="dict_tool",
            description="dict",
            parameters={"type": "object", "properties": {}},
            func=lambda: {"key": "value"},
            is_async=False,
        )
        result = asyncio.run(t.execute())
        assert json.loads(result) == {"key": "value"}


class TestToolDefinition:
    """Test Tool.to_definition()."""

    def test_to_definition(self):
        t = Tool(
            name="my_tool",
            description="My description",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
            func=lambda q: q,
        )
        defn = t.to_definition()
        assert defn.name == "my_tool"
        assert defn.description == "My description"
        assert "q" in defn.parameters["properties"]


class TestParameterExtraction:
    """Test _extract_parameters."""

    def test_basic_types(self):
        # Annotations must be actual type objects (not strings from __future__.annotations)
        # for _extract_parameters to resolve them via the type_map.
        def fn(name, count, flag):
            return ""
        fn.__annotations__ = {"name": str, "count": int, "flag": bool, "return": str}

        params = _extract_parameters(fn)
        assert params["properties"]["name"]["type"] == "string"
        assert params["properties"]["count"]["type"] == "integer"
        assert params["properties"]["flag"]["type"] == "boolean"
        assert set(params["required"]) == {"name", "count", "flag"}

    def test_optional_parameters(self):
        def fn(name: str, limit: int = 10) -> str:
            return ""

        params = _extract_parameters(fn)
        assert "name" in params["required"]
        assert "limit" not in params.get("required", [])

    def test_self_excluded(self):
        def fn(self, query: str) -> str:
            return ""

        params = _extract_parameters(fn)
        assert "self" not in params["properties"]


class TestToolDecorator:
    """Test the @tool decorator registers with the global singleton."""

    def test_decorator_registers(self):
        @tool("_test_decorator_tool", "A test decorator tool")
        def _test_fn(query: str) -> str:
            return f"result: {query}"

        registry = ToolRegistry.get()
        t = registry.get_tool("_test_decorator_tool")
        assert t is not None
        assert t.description == "A test decorator tool"
