"""Configuration system for AgentCompany.

Loads company config from `.agentcompany/config.yaml`, supports environment
variable expansion, and provides access to preset role definitions shipped
with the package.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Environment-variable expansion helper
# ---------------------------------------------------------------------------

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(value: str) -> str:
    """Replace ``${VAR_NAME}`` placeholders with their environment values.

    If the variable is not set the placeholder is left as-is so that
    validation can catch it later.
    """

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return _ENV_VAR_RE.sub(_replace, value)


def _expand_env_recursive(obj: object) -> object:
    """Walk an arbitrary nested structure and expand env vars in strings."""
    if isinstance(obj, str):
        return _expand_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _expand_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_recursive(item) for item in obj]
    return obj


# ---------------------------------------------------------------------------
# Pydantic v2 models
# ---------------------------------------------------------------------------


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider (Anthropic, OpenAI, etc.)."""

    api_key: str = ""
    model: str = ""
    base_url: Optional[str] = None  # For OpenAI-compatible endpoints
    max_tokens: int = 4096


class LLMConfig(BaseModel):
    """Top-level LLM configuration that can hold multiple providers."""

    default_provider: str = "anthropic"
    anthropic: Optional[LLMProviderConfig] = None
    openai: Optional[LLMProviderConfig] = None


class AgentConfig(BaseModel):
    """Configuration for a single agent in the company."""

    name: str
    role: str
    provider: Optional[str] = None  # Override LLMConfig.default_provider
    model: Optional[str] = None  # Override the provider's default model


class DashboardConfig(BaseModel):
    """Web dashboard settings."""

    port: int = 8420
    host: str = "127.0.0.1"


class AutonomousConfig(BaseModel):
    """Limits and budgets for autonomous (goal-driven) mode."""

    max_cycles: int = 5             # CEO review-and-replan cycles
    max_waves_per_cycle: int = 10   # delegation waves within one cycle
    max_agent_iterations: int = 15  # tool-call loops per agent per task
    max_total_tasks: int = 50       # hard cap on total tasks created
    max_time_seconds: int = 3600    # 1 hour wall-clock timeout (0 = unlimited)
    max_cost_usd: float = 0.0      # spending cap (0 = unlimited, requires usage tracking)


class CompanyConfig(BaseModel):
    """Root configuration object representing the entire company."""

    name: str = "My AI Company"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agents: list[AgentConfig] = Field(default_factory=list)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    autonomous: AutonomousConfig = Field(default_factory=AutonomousConfig)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_ROLES_DIR = Path(__file__).resolve().parent / "roles"


def get_company_dir(base: Path | None = None) -> Path:
    """Return the ``.agentcompany/`` directory, creating it if needed.

    Parameters
    ----------
    base:
        The parent directory that contains (or will contain) the
        ``.agentcompany/`` folder.  Defaults to the current working
        directory.
    """
    if base is None:
        base = Path.cwd()
    company_dir = base / ".agentcompany"
    company_dir.mkdir(parents=True, exist_ok=True)
    return company_dir


def load_config(path: Path) -> CompanyConfig:
    """Load and validate a company configuration from a YAML file.

    Environment variable placeholders (``${VAR}``) are expanded before
    validation.
    """
    raw_text = path.read_text(encoding="utf-8")
    raw_data = yaml.safe_load(raw_text) or {}
    expanded = _expand_env_recursive(raw_data)
    return CompanyConfig.model_validate(expanded)


def save_config(config: CompanyConfig, path: Path) -> None:
    """Serialize a :class:`CompanyConfig` to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="python", exclude_none=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, default_flow_style=False, sort_keys=False)


def load_role(role_name: str) -> dict:
    """Load a preset role definition by name.

    Parameters
    ----------
    role_name:
        The stem name of the role file (e.g. ``"ceo"``, ``"developer"``).

    Returns
    -------
    dict
        The parsed YAML contents of the role file.

    Raises
    ------
    FileNotFoundError
        If no matching role YAML exists in the package ``roles/`` directory.
    """
    role_path = _ROLES_DIR / f"{role_name}.yaml"
    if not role_path.exists():
        raise FileNotFoundError(
            f"No preset role named '{role_name}'. "
            f"Available roles: {list_available_roles()}"
        )
    with open(role_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_available_roles() -> list[str]:
    """Return the names of all preset roles shipped with the package."""
    if not _ROLES_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in _ROLES_DIR.glob("*.yaml") if p.is_file()
    )
