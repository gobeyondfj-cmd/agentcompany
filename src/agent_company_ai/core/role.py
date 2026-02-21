"""Role definitions and preset role loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


ROLES_DIR = Path(__file__).parent.parent / "roles"


@dataclass
class Role:
    name: str
    title: str
    description: str
    system_prompt: str
    default_tools: list[str] = field(default_factory=list)
    can_delegate_to: list[str] = field(default_factory=list)
    reports_to: str = "owner"

    def build_system_prompt(self, company_name: str, team_members: list[str]) -> str:
        prompt = self.system_prompt.format(
            title=self.title,
            company_name=company_name,
            team_members=", ".join(team_members) if team_members else "None yet",
            delegates=", ".join(self.can_delegate_to) if self.can_delegate_to else "None",
        )
        return prompt


def load_role(role_name: str) -> Role:
    """Load a role from the preset YAML files."""
    role_file = ROLES_DIR / f"{role_name}.yaml"
    if not role_file.exists():
        raise ValueError(f"Unknown role: {role_name}. Available: {list_available_roles()}")

    with open(role_file) as f:
        data = yaml.safe_load(f)

    return Role(
        name=data["name"],
        title=data["title"],
        description=data["description"],
        system_prompt=data["system_prompt"],
        default_tools=data.get("default_tools", []),
        can_delegate_to=data.get("can_delegate_to", []),
        reports_to=data.get("reports_to", "owner"),
    )


def list_available_roles() -> list[str]:
    """List all available preset role names."""
    return [f.stem for f in ROLES_DIR.glob("*.yaml")]


def create_custom_role(
    name: str,
    title: str,
    description: str,
    system_prompt: str,
    tools: list[str] | None = None,
    can_delegate_to: list[str] | None = None,
    reports_to: str = "ceo",
) -> Role:
    """Create a custom role without a YAML file."""
    return Role(
        name=name,
        title=title,
        description=description,
        system_prompt=system_prompt,
        default_tools=tools or [],
        can_delegate_to=can_delegate_to or [],
        reports_to=reports_to,
    )
