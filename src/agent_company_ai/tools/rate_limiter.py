"""Shared rate limiter for external service tools.

Uses rolling time windows to prevent abuse of email, payment, and other
rate-limited integrations.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class RateBucket:
    """Tracks timestamps in a rolling window."""

    max_count: int
    window_seconds: float
    timestamps: list[float] = field(default_factory=list)

    def _prune(self) -> None:
        cutoff = time.monotonic() - self.window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    def check(self) -> bool:
        """Return True if another action is allowed."""
        self._prune()
        return len(self.timestamps) < self.max_count

    def record(self) -> None:
        """Record that an action was taken."""
        self.timestamps.append(time.monotonic())

    def remaining(self) -> int:
        """Return how many actions remain in the current window."""
        self._prune()
        return max(0, self.max_count - len(self.timestamps))


class RateLimiter:
    """Singleton rate limiter with named buckets."""

    _instance: RateLimiter | None = None

    def __init__(self) -> None:
        self._buckets: dict[str, RateBucket] = {}

    @classmethod
    def get(cls) -> RateLimiter:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def configure(self, key: str, max_count: int, window_seconds: float) -> None:
        """Configure a rate limit bucket."""
        self._buckets[key] = RateBucket(
            max_count=max_count, window_seconds=window_seconds
        )

    def check(self, key: str) -> bool:
        """Return True if the action is allowed under rate limits."""
        bucket = self._buckets.get(key)
        if bucket is None:
            return True  # No limit configured
        return bucket.check()

    def record(self, key: str) -> None:
        """Record that a rate-limited action was taken."""
        bucket = self._buckets.get(key)
        if bucket is not None:
            bucket.record()

    def remaining(self, key: str) -> int:
        """Return remaining actions for a bucket."""
        bucket = self._buckets.get(key)
        if bucket is None:
            return 999
        return bucket.remaining()

    def check_and_record(self, key: str) -> bool:
        """Check if allowed and record in one step. Returns True if allowed."""
        if not self.check(key):
            return False
        self.record(key)
        return True
