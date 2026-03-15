"""Tests for the CostTracker."""

from __future__ import annotations

import threading
from datetime import datetime, timezone, timedelta

from agent_company_ai.core.cost_tracker import CostTracker, UsageRecord


class TestRecording:
    """Test basic recording and totals."""

    def test_record_returns_usage_record(self, cost_tracker: CostTracker):
        rec = cost_tracker.record("alice", "gpt-4o", 1000, 500)
        assert isinstance(rec, UsageRecord)
        assert rec.agent == "alice"
        assert rec.model == "gpt-4o"

    def test_total_cost_accumulates(self, cost_tracker: CostTracker):
        cost_tracker.record("alice", "gpt-4o", 1000, 500)
        cost_tracker.record("bob", "gpt-4o", 2000, 1000)
        assert cost_tracker.total_cost > 0
        assert cost_tracker.call_count == 2

    def test_total_tokens(self, cost_tracker: CostTracker):
        cost_tracker.record("alice", "gpt-4o", 1000, 500)
        assert cost_tracker.total_input_tokens == 1000
        assert cost_tracker.total_output_tokens == 500
        assert cost_tracker.total_tokens == 1500

    def test_unknown_model_zero_cost(self, cost_tracker: CostTracker):
        rec = cost_tracker.record("alice", "unknown-model-xyz", 1000, 500)
        assert rec.cost_usd == 0.0


class TestEstimation:
    """Test cost estimation."""

    def test_known_model(self, cost_tracker: CostTracker):
        cost = cost_tracker.estimate_cost("gpt-4o", 1_000_000, 0)
        assert cost == 2.50  # $2.50 per 1M input tokens

    def test_prefix_matching(self, cost_tracker: CostTracker):
        cost = cost_tracker.estimate_cost("gpt-4o-2024-11-20", 1_000_000, 0)
        assert cost == 2.50

    def test_unknown_model(self, cost_tracker: CostTracker):
        cost = cost_tracker.estimate_cost("no-such-model", 1000, 500)
        assert cost == 0.0

    def test_custom_pricing(self, cost_tracker: CostTracker):
        cost_tracker.set_pricing("my-model", 1.0, 2.0)
        cost = cost_tracker.estimate_cost("my-model", 1_000_000, 1_000_000)
        assert cost == 3.0  # $1 input + $2 output


class TestCostLast24h:
    """Test the 24-hour rolling window."""

    def test_all_recent(self, cost_tracker: CostTracker):
        cost_tracker.record("alice", "gpt-4o", 1_000_000, 0)
        assert cost_tracker.cost_last_24h() == 2.50

    def test_excludes_old_records(self, cost_tracker: CostTracker):
        # Add a record and manually backdate it
        rec = cost_tracker.record("alice", "gpt-4o", 1_000_000, 0)
        rec.timestamp = datetime.now(timezone.utc) - timedelta(hours=25)
        assert cost_tracker.cost_last_24h() == 0.0

    def test_empty_tracker(self, cost_tracker: CostTracker):
        assert cost_tracker.cost_last_24h() == 0.0


class TestSummary:
    """Test summary output."""

    def test_summary_structure(self, cost_tracker: CostTracker):
        cost_tracker.record("alice", "gpt-4o", 1000, 500)
        summary = cost_tracker.summary()
        assert "total_cost_usd" in summary
        assert "by_agent" in summary
        assert "by_model" in summary
        assert "alice" in summary["by_agent"]


class TestThreadSafety:
    """Test that concurrent recording doesn't crash."""

    def test_concurrent_recording(self, cost_tracker: CostTracker):
        errors = []

        def record_many():
            try:
                for _ in range(100):
                    cost_tracker.record("agent", "gpt-4o", 100, 50)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert cost_tracker.call_count == 400
