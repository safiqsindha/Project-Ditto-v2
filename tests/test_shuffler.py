"""
Tests for src/shuffler.py.

All constraints are expressed as plain dicts (the format used by chain JSONL files)
rather than dataclass instances — the shuffler handles both formats.
"""

from __future__ import annotations

import pytest

from src.shuffler import shuffle_chain


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_chain(chain_id: str = "tb_00001", n: int = 5) -> dict:
    """Create a minimal chain dict with n dict-format constraints."""
    constraints = [
        {
            "type": "ToolAvailability",
            "timestamp": 1,
            "tool": "command_1",
            "state": "available",
            "recover_in": None,
        },
        {
            "type": "ResourceBudget",
            "timestamp": 1,
            "resource": "context_window",
            "amount": 1.0,
            "decay": "monotone_decrease",
            "recover_in": None,
        },
        {
            "type": "SubGoalTransition",
            "timestamp": 2,
            "from_phase": "initial",
            "to_phase": "exploration",
            "trigger": "task_start",
        },
        {
            "type": "InformationState",
            "timestamp": 2,
            "observable_added": ["file_A"],
            "observable_removed": [],
            "uncertainty": 0.5,
        },
        {
            "type": "ResourceBudget",
            "timestamp": 3,
            "resource": "patience_budget",
            "amount": 0.9,
            "decay": "monotone_decrease",
            "recover_in": None,
        },
    ]
    return {
        "chain_id": chain_id,
        "match_id": "task_001",
        "source": "tb",
        "constraints": constraints[:n],
        "rendered": "",
    }


def _make_large_chain(n: int = 12) -> dict:
    """Create a longer chain so seed differences are likely to produce different orders."""
    constraints = [
        {
            "type": "ResourceBudget",
            "timestamp": i + 1,
            "resource": f"context_window",
            "amount": round(1.0 - i * 0.05, 3),
            "decay": "monotone_decrease",
            "recover_in": None,
        }
        for i in range(n)
    ]
    return {
        "chain_id": "tb_large",
        "match_id": "task_large",
        "source": "tb",
        "constraints": constraints,
        "rendered": "",
    }


# ---------------------------------------------------------------------------
# Chain ID and metadata
# ---------------------------------------------------------------------------

class TestChainMetadata:

    def test_chain_id_updated_with_seed(self):
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        assert shuffled["chain_id"] == "tb_00001_shuffled_42"

    def test_chain_id_uses_given_seed(self):
        chain = _make_chain()
        s1 = shuffle_chain(chain, seed=1337)
        assert s1["chain_id"] == "tb_00001_shuffled_1337"

    def test_match_id_preserved(self):
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        assert shuffled["match_id"] == "task_001"

    def test_source_preserved(self):
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        assert shuffled.get("source") == "tb"

    def test_original_chain_id_unchanged(self):
        chain = _make_chain()
        original_id = chain["chain_id"]
        shuffle_chain(chain, seed=42)
        assert chain["chain_id"] == original_id


# ---------------------------------------------------------------------------
# Constraint count and content
# ---------------------------------------------------------------------------

class TestConstraintPreservation:

    def test_constraint_count_unchanged(self):
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        assert len(shuffled["constraints"]) == len(chain["constraints"])

    def test_all_constraint_types_preserved(self):
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        orig_types = sorted(c["type"] for c in chain["constraints"])
        shuf_types = sorted(c["type"] for c in shuffled["constraints"])
        assert orig_types == shuf_types

    def test_constraint_values_preserved(self):
        """All constraint dicts from original should appear in shuffled (modulo timestamp)."""
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        # Each shuffled constraint's non-timestamp fields should match one original
        orig_stripped = [
            {k: v for k, v in c.items() if k != "timestamp"}
            for c in chain["constraints"]
        ]
        shuf_stripped = [
            {k: v for k, v in c.items() if k != "timestamp"}
            for c in shuffled["constraints"]
        ]
        for s in shuf_stripped:
            assert s in orig_stripped

    def test_original_constraints_not_mutated(self):
        chain = _make_chain()
        orig_types = [c["type"] for c in chain["constraints"]]
        shuffle_chain(chain, seed=42)
        assert [c["type"] for c in chain["constraints"]] == orig_types


# ---------------------------------------------------------------------------
# Timestamp invariants
# ---------------------------------------------------------------------------

class TestTimestamps:

    def test_timestamps_monotonically_nondecreasing(self):
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        timestamps = [c["timestamp"] for c in shuffled["constraints"]]
        assert timestamps == sorted(timestamps)

    def test_timestamps_monotonic_across_seeds(self):
        chain = _make_chain()
        for seed in [42, 1337, 7919, 0, 99]:
            shuffled = shuffle_chain(chain, seed=seed)
            ts = [c["timestamp"] for c in shuffled["constraints"]]
            assert ts == sorted(ts), f"Non-monotonic timestamps for seed={seed}"

    def test_timestamp_set_unchanged(self):
        """The multiset of timestamps should be the same before and after shuffle."""
        chain = _make_chain()
        shuffled = shuffle_chain(chain, seed=42)
        orig_ts = sorted(c["timestamp"] for c in chain["constraints"])
        shuf_ts = sorted(c["timestamp"] for c in shuffled["constraints"])
        assert orig_ts == shuf_ts


# ---------------------------------------------------------------------------
# Determinism and diversity
# ---------------------------------------------------------------------------

class TestDeterminismAndDiversity:

    def test_same_seed_produces_same_order(self):
        chain = _make_large_chain()
        s1 = shuffle_chain(chain, seed=42)
        s2 = shuffle_chain(chain, seed=42)
        types1 = [c["type"] for c in s1["constraints"]]
        types2 = [c["type"] for c in s2["constraints"]]
        assert types1 == types2

    def test_different_seeds_produce_different_orders(self):
        """Two different seeds should almost certainly produce different permutations
        for a chain with 12 distinct-resource constraints."""
        chain = _make_large_chain(n=12)
        s1 = shuffle_chain(chain, seed=42)
        s2 = shuffle_chain(chain, seed=1337)
        amounts1 = [c["amount"] for c in s1["constraints"]]
        amounts2 = [c["amount"] for c in s2["constraints"]]
        # With 12 distinct amounts, P(same permutation) = 1/12! ≈ 0
        assert amounts1 != amounts2

    def test_shuffled_differs_from_original(self):
        """A large chain shuffled with any seed should differ from the original order."""
        chain = _make_large_chain(n=12)
        shuffled = shuffle_chain(chain, seed=42)
        orig_amounts = [c["amount"] for c in chain["constraints"]]
        shuf_amounts = [c["amount"] for c in shuffled["constraints"]]
        assert orig_amounts != shuf_amounts
