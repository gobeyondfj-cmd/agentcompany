"""Tests for the configuration system."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from agent_company_ai.config import (
    CompanyConfig,
    AutonomousConfig,
    slugify,
    load_config,
    save_config,
    list_available_roles,
    _expand_env_vars,
)


class TestDefaults:
    """Verify critical default values."""

    def test_max_cost_usd_default(self):
        cfg = AutonomousConfig()
        assert cfg.max_cost_usd == 10.0

    def test_daily_budget_usd_default(self):
        cfg = AutonomousConfig()
        assert cfg.daily_budget_usd == 20.0

    def test_max_cycles_default(self):
        cfg = AutonomousConfig()
        assert cfg.max_cycles == 5

    def test_max_agent_iterations_default(self):
        cfg = AutonomousConfig()
        assert cfg.max_agent_iterations == 25

    def test_company_name_default(self):
        cfg = CompanyConfig()
        assert cfg.name == "My AI Company"

    def test_default_provider(self):
        cfg = CompanyConfig()
        assert cfg.llm.default_provider == "anthropic"

    def test_wallet_disabled_by_default(self):
        cfg = CompanyConfig()
        assert cfg.wallet.enabled is False

    def test_profit_engine_disabled_by_default(self):
        cfg = CompanyConfig()
        assert cfg.profit_engine.enabled is False


class TestSlugify:
    """Test the slugify helper."""

    def test_basic(self):
        assert slugify("My Startup") == "my-startup"

    def test_empty_returns_default(self):
        assert slugify("") == "default"

    def test_special_characters(self):
        assert slugify("Hello World! @#$") == "hello-world"

    def test_already_slug(self):
        assert slugify("my-company") == "my-company"

    def test_numbers(self):
        assert slugify("Agent 42") == "agent-42"


class TestEnvExpansion:
    """Test environment variable expansion."""

    def test_expand_known_var(self):
        os.environ["_TEST_EXPAND"] = "hello"
        try:
            assert _expand_env_vars("${_TEST_EXPAND}") == "hello"
        finally:
            del os.environ["_TEST_EXPAND"]

    def test_unknown_var_left_as_is(self):
        result = _expand_env_vars("${_NONEXISTENT_VAR_XYZ}")
        assert result == "${_NONEXISTENT_VAR_XYZ}"

    def test_no_placeholders(self):
        assert _expand_env_vars("plain text") == "plain text"


class TestSaveLoad:
    """Test config round-trip."""

    def test_roundtrip(self):
        cfg = CompanyConfig(name="Test Co")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            save_config(cfg, path)
            loaded = load_config(path)
            assert loaded.name == "Test Co"
            assert loaded.autonomous.max_cost_usd == 10.0
            assert loaded.autonomous.daily_budget_usd == 20.0


class TestRoles:
    """Test role loading."""

    def test_roles_exist(self):
        roles = list_available_roles()
        assert len(roles) >= 9
        assert "ceo" in roles
        assert "developer" in roles
