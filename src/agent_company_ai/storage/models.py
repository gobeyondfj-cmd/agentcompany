"""Pydantic models mapping to the Agent Company AI database tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    FIRED = "fired"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ArtifactType(str, Enum):
    TEXT = "text"
    CODE = "code"
    FILE = "file"
    DATA = "data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_id() -> str:
    """Generate a short hex ID (12 characters)."""
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Record models
# ---------------------------------------------------------------------------

class AgentRecord(BaseModel):
    """Maps to the ``agents`` table."""

    id: str = Field(default_factory=_new_id)
    name: str
    role: str
    provider: Optional[str] = None
    model: Optional[str] = None
    config_json: str = "{}"
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def new_id(cls) -> str:
        return _new_id()


class TaskRecord(BaseModel):
    """Maps to the ``tasks`` table."""

    id: str = Field(default_factory=_new_id)
    description: str
    assignee_id: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    parent_id: Optional[str] = None
    result: Optional[str] = None
    artifacts_json: str = "[]"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def new_id(cls) -> str:
        return _new_id()


class MessageRecord(BaseModel):
    """Maps to the ``messages`` table."""

    id: str = Field(default_factory=_new_id)
    from_agent: Optional[str] = None   # None == from human owner
    to_agent: Optional[str] = None     # None == broadcast
    content: str
    topic: Optional[str] = None
    metadata_json: str = "{}"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def new_id(cls) -> str:
        return _new_id()


class ConversationEntry(BaseModel):
    """Maps to the ``conversations`` table.

    The ``id`` is an auto-incrementing integer managed by SQLite, so it
    defaults to ``None`` for new records that haven't been inserted yet.
    """

    id: Optional[int] = None
    agent_id: str
    role: str          # 'system', 'user', 'assistant'
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def new_id(cls) -> str:
        """Not used for conversations (AUTOINCREMENT), provided for API consistency."""
        return _new_id()


class ArtifactRecord(BaseModel):
    """Maps to the ``artifacts`` table."""

    id: str = Field(default_factory=_new_id)
    task_id: Optional[str] = None
    agent_id: Optional[str] = None
    name: str
    content: Optional[str] = None
    artifact_type: ArtifactType = ArtifactType.TEXT
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def new_id(cls) -> str:
        return _new_id()


class GoalRecord(BaseModel):
    """Maps to the ``goals`` table."""

    id: str = Field(default_factory=_new_id)
    description: str
    status: GoalStatus = GoalStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @classmethod
    def new_id(cls) -> str:
        return _new_id()


# ---------------------------------------------------------------------------
# Wallet / Payment models
# ---------------------------------------------------------------------------

class PaymentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    FAILED = "failed"


class WalletRecord(BaseModel):
    """Maps to the ``wallets`` table."""

    id: str = Field(default_factory=_new_id)
    address: str
    keystore_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def new_id(cls) -> str:
        return _new_id()


class PaymentRecord(BaseModel):
    """Maps to the ``payment_queue`` table."""

    id: str = Field(default_factory=_new_id)
    to_address: str
    amount: str  # stored as string to preserve decimal precision
    token: str = "ETH"
    chain: str = "ethereum"
    reason: str = ""
    requested_by: Optional[str] = None
    status: PaymentStatus = PaymentStatus.PENDING
    tx_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    executed_at: Optional[datetime] = None

    @classmethod
    def new_id(cls) -> str:
        return _new_id()
