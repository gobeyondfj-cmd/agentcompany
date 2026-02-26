"""In-process async message bus for agent-to-agent communication."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Awaitable


logger = logging.getLogger("agent_company_ai.message_bus")


@dataclass
class BusMessage:
    from_agent: str | None  # None = from human owner
    to_agent: str | None  # None = broadcast
    content: str
    topic: str = "general"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Callback = Callable[[BusMessage], Awaitable[None]]


class MessageBus:
    """Async pub/sub message bus for inter-agent communication."""

    def __init__(self):
        self._subscribers: dict[str, list[Callback]] = {}  # topic -> callbacks
        self._agent_inboxes: dict[str, asyncio.Queue[BusMessage]] = {}
        self._history: list[BusMessage] = []
        self._lock = asyncio.Lock()
        self._on_message: Callback | None = None  # global listener for logging

    def set_global_listener(self, callback: Callback) -> None:
        self._on_message = callback

    def subscribe(self, topic: str, callback: Callback) -> None:
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(callback)

    def register_agent(self, agent_name: str) -> asyncio.Queue[BusMessage]:
        queue: asyncio.Queue[BusMessage] = asyncio.Queue()
        self._agent_inboxes[agent_name] = queue
        return queue

    def unregister_agent(self, agent_name: str) -> None:
        self._agent_inboxes.pop(agent_name, None)

    async def publish(self, message: BusMessage) -> None:
        async with self._lock:
            self._history.append(message)

        # Notify global listener
        if self._on_message:
            try:
                await self._on_message(message)
            except Exception as e:
                logger.error(f"Global message listener error: {e}")

        # Deliver to specific agent inbox
        if message.to_agent and message.to_agent in self._agent_inboxes:
            await self._agent_inboxes[message.to_agent].put(message)

        # Broadcast to all if no specific target
        if message.to_agent is None:
            for name, queue in self._agent_inboxes.items():
                if name != message.from_agent:
                    await queue.put(message)

        # Notify topic subscribers
        if message.topic in self._subscribers:
            for callback in self._subscribers[message.topic]:
                try:
                    await callback(message)
                except Exception as e:
                    logger.error(f"Subscriber callback error on topic '{message.topic}': {e}")

    async def send(
        self,
        from_agent: str | None,
        to_agent: str | None,
        content: str,
        topic: str = "general",
    ) -> None:
        msg = BusMessage(
            from_agent=from_agent,
            to_agent=to_agent,
            content=content,
            topic=topic,
        )
        await self.publish(msg)

    def get_history(self, limit: int = 50, topic: str | None = None) -> list[BusMessage]:
        # Return a copy to avoid mutation during iteration
        messages = list(self._history)
        if topic:
            messages = [m for m in messages if m.topic == topic]
        return messages[-limit:]
