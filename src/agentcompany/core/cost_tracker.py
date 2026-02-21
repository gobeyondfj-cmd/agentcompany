"""Real-time LLM API cost tracking."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

# Pricing per 1M tokens (USD) - updated for common models.
# Users can extend this dict at runtime via CostTracker.set_pricing().
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-sonnet-4-5-20250929": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6":            {"input": 15.00, "output": 75.00},
    "claude-haiku-4-5-20251001":  {"input": 0.80, "output": 4.00},
    # OpenAI
    "gpt-4o":                     {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":                {"input": 0.15, "output": 0.60},
    "gpt-4-turbo":                {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo":              {"input": 0.50, "output": 1.50},
}


@dataclass
class UsageRecord:
    """A single LLM API call's usage."""
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CostTracker:
    """Thread-safe accumulator for LLM API costs.

    Tracks per-call usage records and maintains running totals for
    tokens and estimated USD cost.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._records: list[UsageRecord] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self._pricing = dict(DEFAULT_PRICING)

    def set_pricing(self, model: str, input_per_1m: float, output_per_1m: float) -> None:
        """Set or override pricing for a model."""
        with self._lock:
            self._pricing[model] = {"input": input_per_1m, "output": output_per_1m}

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost for a call. Returns 0 if model pricing is unknown."""
        pricing = self._pricing.get(model)
        if not pricing:
            # Try prefix matching (e.g. "gpt-4o-2024-..." matches "gpt-4o")
            for key, p in self._pricing.items():
                if model.startswith(key):
                    pricing = p
                    break
        if not pricing:
            return 0.0
        return (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

    def record(self, agent: str, model: str, input_tokens: int, output_tokens: int) -> UsageRecord:
        """Record a single LLM API call and return the usage record."""
        cost = self.estimate_cost(model, input_tokens, output_tokens)
        rec = UsageRecord(
            agent=agent,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        with self._lock:
            self._records.append(rec)
            self._total_input_tokens += input_tokens
            self._total_output_tokens += output_tokens
            self._total_cost_usd += cost
        return rec

    @property
    def total_cost(self) -> float:
        with self._lock:
            return self._total_cost_usd

    @property
    def total_input_tokens(self) -> int:
        with self._lock:
            return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        with self._lock:
            return self._total_output_tokens

    @property
    def total_tokens(self) -> int:
        with self._lock:
            return self._total_input_tokens + self._total_output_tokens

    @property
    def call_count(self) -> int:
        with self._lock:
            return len(self._records)

    def summary(self) -> dict:
        """Return a snapshot of cost data for API/dashboard."""
        with self._lock:
            by_agent: dict[str, float] = {}
            by_model: dict[str, float] = {}
            for r in self._records:
                by_agent[r.agent] = by_agent.get(r.agent, 0.0) + r.cost_usd
                by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd

            return {
                "total_cost_usd": round(self._total_cost_usd, 6),
                "total_input_tokens": self._total_input_tokens,
                "total_output_tokens": self._total_output_tokens,
                "total_tokens": self._total_input_tokens + self._total_output_tokens,
                "api_calls": len(self._records),
                "by_agent": {k: round(v, 6) for k, v in sorted(by_agent.items())},
                "by_model": {k: round(v, 6) for k, v in sorted(by_model.items())},
            }

    def recent(self, limit: int = 20) -> list[dict]:
        """Return the most recent usage records."""
        with self._lock:
            records = self._records[-limit:]
        return [
            {
                "agent": r.agent,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": round(r.cost_usd, 6),
                "timestamp": r.timestamp.isoformat(),
            }
            for r in reversed(records)
        ]
