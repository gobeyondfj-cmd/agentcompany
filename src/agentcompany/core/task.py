"""Task model and management for the agent company."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    description: str
    assignee: str | None = None
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 0
    parent_id: str | None = None
    subtasks: list[Task] = field(default_factory=list)
    result: str | None = None
    artifacts: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def create(
        cls,
        description: str,
        assignee: str | None = None,
        priority: int = 0,
        parent_id: str | None = None,
    ) -> Task:
        return cls(
            id=uuid.uuid4().hex[:12],
            description=description,
            assignee=assignee,
            status=TaskStatus.ASSIGNED if assignee else TaskStatus.PENDING,
            priority=priority,
            parent_id=parent_id,
        )

    def assign(self, agent_name: str) -> None:
        self.assignee = agent_name
        self.status = TaskStatus.ASSIGNED
        self.updated_at = datetime.now(timezone.utc)

    def start(self) -> None:
        self.status = TaskStatus.IN_PROGRESS
        self.updated_at = datetime.now(timezone.utc)

    def complete(self, result: str | None = None) -> None:
        self.status = TaskStatus.DONE
        self.result = result
        self.updated_at = datetime.now(timezone.utc)

    def fail(self, reason: str | None = None) -> None:
        self.status = TaskStatus.FAILED
        self.result = reason
        self.updated_at = datetime.now(timezone.utc)

    def add_subtask(self, description: str, assignee: str | None = None) -> Task:
        subtask = Task.create(
            description=description,
            assignee=assignee,
            parent_id=self.id,
        )
        self.subtasks.append(subtask)
        return subtask

    @property
    def is_terminal(self) -> bool:
        return self.status in (TaskStatus.DONE, TaskStatus.FAILED)

    @property
    def all_subtasks_done(self) -> bool:
        return all(st.is_terminal for st in self.subtasks) if self.subtasks else True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "assignee": self.assignee,
            "status": self.status.value,
            "priority": self.priority,
            "parent_id": self.parent_id,
            "result": self.result,
            "subtask_count": len(self.subtasks),
            "subtasks_done": sum(1 for st in self.subtasks if st.is_terminal),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class TaskBoard:
    """Manages all tasks for the company."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        self._tasks[task.id] = task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def remove(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)

    def list_all(self) -> list[Task]:
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def list_by_status(self, status: TaskStatus) -> list[Task]:
        return [t for t in self._tasks.values() if t.status == status]

    def list_by_assignee(self, agent_name: str) -> list[Task]:
        return [t for t in self._tasks.values() if t.assignee == agent_name]

    def pending_tasks(self) -> list[Task]:
        return self.list_by_status(TaskStatus.PENDING) + self.list_by_status(TaskStatus.ASSIGNED)

    def active_tasks(self) -> list[Task]:
        return self.list_by_status(TaskStatus.IN_PROGRESS)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in self._tasks.values():
            counts[task.status.value] = counts.get(task.status.value, 0) + 1
        return counts
