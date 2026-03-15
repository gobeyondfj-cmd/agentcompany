"""Shared fixtures for Agent Company AI tests."""

from __future__ import annotations

import pytest
from agent_company_ai.config import CompanyConfig, AutonomousConfig
from agent_company_ai.core.cost_tracker import CostTracker
from agent_company_ai.tools.registry import ToolRegistry, Tool


@pytest.fixture
def config():
    """Return a default CompanyConfig."""
    return CompanyConfig()


@pytest.fixture
def autonomous_config():
    """Return a default AutonomousConfig."""
    return AutonomousConfig()


@pytest.fixture
def cost_tracker():
    """Return a fresh CostTracker."""
    return CostTracker()


@pytest.fixture
def tool_registry():
    """Return an isolated ToolRegistry (not the global singleton)."""
    return ToolRegistry()
