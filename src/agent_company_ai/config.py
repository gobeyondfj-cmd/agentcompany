"""Configuration system for Agent Company AI.

Loads company config from `.agent-company-ai/config.yaml`, supports environment
variable expansion, and provides access to preset role definitions shipped
with the package.
"""

from __future__ import annotations

import os
import re
import shutil
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
    max_agent_iterations: int = 25  # tool-call loops per agent per task
    max_total_tasks: int = 50       # hard cap on total tasks created
    max_time_seconds: int = 3600    # 1 hour wall-clock timeout (0 = unlimited)
    max_cost_usd: float = 0.0      # spending cap (0 = unlimited, requires usage tracking)


class WalletConfig(BaseModel):
    """Blockchain wallet settings."""

    enabled: bool = False
    default_chain: str = "ethereum"


class ProfitEngineConfig(BaseModel):
    """Business DNA — defines how the company earns money and survives.

    When ``enabled`` is *True* and at least one field is non-empty, the
    formatted DNA string is injected into every agent's system prompt and
    into the CEO's autonomous goal loop.
    """

    enabled: bool = False
    mission: str = ""
    revenue_streams: str = ""
    target_customers: str = ""
    pricing_model: str = ""
    competitive_edge: str = ""
    key_metrics: str = ""
    cost_priorities: str = ""
    additional_context: str = ""

    def format_dna(self) -> str:
        """Format the business DNA into a prompt-ready string.

        Returns an empty string if the engine is disabled or every field is
        blank, so callers can simply check truthiness.
        """
        if not self.enabled:
            return ""

        sections: list[str] = []
        _fields = [
            ("Mission", self.mission),
            ("Revenue Streams", self.revenue_streams),
            ("Target Customers", self.target_customers),
            ("Pricing Model", self.pricing_model),
            ("Competitive Edge", self.competitive_edge),
            ("Key Metrics", self.key_metrics),
            ("Cost Priorities", self.cost_priorities),
            ("Additional Context", self.additional_context),
        ]
        for label, value in _fields:
            if value.strip():
                sections.append(f"- **{label}:** {value.strip()}")

        if not sections:
            return ""

        return (
            "\n\n--- COMPANY BUSINESS DNA (ProfitEngine) ---\n"
            "The following defines how this company earns money and what matters most. "
            "Factor this into every decision, recommendation, and deliverable.\n\n"
            + "\n".join(sections)
            + "\n--- END BUSINESS DNA ---"
        )


class RateLimitConfig(BaseModel):
    """Rate limits for external service integrations."""

    emails_per_hour: int = 20
    emails_per_day: int = 100
    payment_links_per_day: int = 10
    max_payment_amount_usd: float = 500.0
    tweets_per_day: int = 17          # Free tier is very restrictive
    deploys_per_day: int = 50
    gumroad_daily: int = 50
    invoices_daily: int = 50
    bookings_daily: int = 20


class EmailConfig(BaseModel):
    """Email sending configuration (Resend or SendGrid)."""

    enabled: bool = False
    provider: str = "resend"          # "resend" or "sendgrid"
    api_key: str = ""                 # ${RESEND_API_KEY} or ${SENDGRID_API_KEY}
    from_address: str = ""
    from_name: str = ""
    reply_to: str = ""


class StripeConfig(BaseModel):
    """Stripe payment integration configuration."""

    enabled: bool = False
    api_key: str = ""                 # ${STRIPE_SECRET_KEY}


class LandingPageConfig(BaseModel):
    """Landing page generator configuration."""

    enabled: bool = False
    serve_port: int = 8421
    output_dir: str = "landing_pages"


class TwitterConfig(BaseModel):
    """Twitter/X API configuration for publishing social posts."""

    enabled: bool = False
    api_key: str = ""              # ${TWITTER_API_KEY}
    api_secret: str = ""           # ${TWITTER_API_SECRET}
    access_token: str = ""         # ${TWITTER_ACCESS_TOKEN}
    access_token_secret: str = ""  # ${TWITTER_ACCESS_TOKEN_SECRET}


class VercelConfig(BaseModel):
    """Vercel deployment configuration for landing pages."""

    enabled: bool = False
    token: str = ""                # ${VERCEL_TOKEN}
    project_name: str = ""         # optional: sets subdomain prefix


class GumroadConfig(BaseModel):
    """Gumroad digital product sales configuration."""

    enabled: bool = False
    access_token: str = ""           # ${GUMROAD_ACCESS_TOKEN}


class InvoiceConfig(BaseModel):
    """Invoice generator configuration."""

    enabled: bool = False
    company_name: str = ""
    company_address: str = ""
    payment_instructions: str = ""
    currency: str = "USD"


class CalcomConfig(BaseModel):
    """Cal.com paid booking configuration."""

    enabled: bool = False
    api_key: str = ""                # ${CALCOM_API_KEY}
    default_duration: int = 30


class IntegrationsConfig(BaseModel):
    """External service integrations."""

    email: EmailConfig = Field(default_factory=EmailConfig)
    stripe: StripeConfig = Field(default_factory=StripeConfig)
    landing_page: LandingPageConfig = Field(default_factory=LandingPageConfig)
    twitter: TwitterConfig = Field(default_factory=TwitterConfig)
    vercel: VercelConfig = Field(default_factory=VercelConfig)
    gumroad: GumroadConfig = Field(default_factory=GumroadConfig)
    invoice: InvoiceConfig = Field(default_factory=InvoiceConfig)
    calcom: CalcomConfig = Field(default_factory=CalcomConfig)
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)


class CompanyConfig(BaseModel):
    """Root configuration object representing the entire company."""

    name: str = "My AI Company"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agents: list[AgentConfig] = Field(default_factory=list)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    autonomous: AutonomousConfig = Field(default_factory=AutonomousConfig)
    wallet: WalletConfig = Field(default_factory=WalletConfig)
    profit_engine: ProfitEngineConfig = Field(default_factory=ProfitEngineConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

_ROLES_DIR = Path(__file__).resolve().parent / "roles"


def slugify(name: str) -> str:
    """Convert a company name to a filesystem-safe slug.

    ``"My Startup"`` → ``"my-startup"``, ``""`` → ``"default"``.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "default"


def get_root_dir(base: Path | None = None) -> Path:
    """Return the ``.agent-company-ai/`` root directory (no auto-create).

    Parameters
    ----------
    base:
        Parent directory that contains (or will contain) the root folder.
        Defaults to the current working directory.
    """
    if base is None:
        base = Path.cwd()
    return base / ".agent-company-ai"


def get_company_dir(
    company: str = "default",
    base: Path | None = None,
    *,
    create: bool = True,
) -> Path:
    """Return the directory for a specific company, e.g. ``.agent-company-ai/<slug>/``.

    Parameters
    ----------
    company:
        Company slug (e.g. ``"default"``, ``"my-startup"``).
    base:
        Parent directory that contains (or will contain) the
        ``.agent-company-ai/`` folder.  Defaults to the current working
        directory.
    create:
        If *True* (default), create the directory tree if it doesn't exist.
        Pass *False* for read-only lookups.
    """
    root = get_root_dir(base)
    company_dir = root / slugify(company)
    if create:
        company_dir.mkdir(parents=True, exist_ok=True)
    return company_dir


def list_companies(base: Path | None = None) -> list[str]:
    """Return slugs of all companies (subdirs containing ``config.yaml``)."""
    root = get_root_dir(base)
    if not root.is_dir():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and (d / "config.yaml").exists()
    )


def maybe_migrate_legacy_layout(base: Path | None = None) -> bool:
    """Migrate a flat ``.agent-company-ai/`` layout into ``default/``.

    Old layout had ``config.yaml`` and ``company.db`` directly inside the
    root directory.  This moves them into a ``default/`` subdirectory.
    Idempotent — returns *True* if a migration actually happened.
    """
    root = get_root_dir(base)
    legacy_config = root / "config.yaml"
    if not legacy_config.exists():
        return False
    # Already migrated if default/ sub-dir exists with config
    default_dir = root / "default"
    if default_dir.exists() and (default_dir / "config.yaml").exists():
        return False
    default_dir.mkdir(parents=True, exist_ok=True)
    # Move config.yaml, company.db, and any WAL/SHM files
    for pattern in ("config.yaml", "company.db", "company.db-wal", "company.db-shm"):
        src = root / pattern
        if src.exists():
            shutil.move(str(src), str(default_dir / pattern))
    return True


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


# ---------------------------------------------------------------------------
# ProfitEngine template helpers
# ---------------------------------------------------------------------------

_PROFIT_ENGINE_TEMPLATES_DIR = Path(__file__).resolve().parent / "profit_engine_templates"


def load_profit_engine_template(name: str) -> dict:
    """Load a ProfitEngine preset template by name.

    Parameters
    ----------
    name:
        The stem name of the template file (e.g. ``"saas"``, ``"ecommerce"``).

    Returns
    -------
    dict
        The parsed YAML contents of the template file.

    Raises
    ------
    FileNotFoundError
        If no matching template YAML exists.
    """
    template_path = _PROFIT_ENGINE_TEMPLATES_DIR / f"{name}.yaml"
    if not template_path.exists():
        raise FileNotFoundError(
            f"No ProfitEngine template named '{name}'. "
            f"Available: {list_profit_engine_templates()}"
        )
    with open(template_path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def list_profit_engine_templates() -> list[str]:
    """Return the names of all ProfitEngine preset templates."""
    if not _PROFIT_ENGINE_TEMPLATES_DIR.is_dir():
        return []
    return sorted(
        p.stem for p in _PROFIT_ENGINE_TEMPLATES_DIR.glob("*.yaml") if p.is_file()
    )
