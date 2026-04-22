"""
End-to-end pipeline integration tests (Session 7).

Validates the full chain: aggregate → translate → observability → filter → render → shuffle
using synthetic TrajectoryEvent sequences.  Also serves as Gate 3 validation for
synthetic data: 20+ rendered chains per source must pass the leakage check.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.aggregation import aggregate_events
from src.filter import is_valid_chain
from src.observability import apply_asymmetric_observability
from src.parser_tb import TrajectoryEvent
from src.renderer import render_chain, check_programming_leakage
from src.shuffler import shuffle_chain
from src.translation import (
    ResourceBudget,
    SubGoalTransition,
    ToolAvailability,
    constraint_from_dict,
    constraint_to_dict,
    translate_trajectory,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic event factories
# ---------------------------------------------------------------------------

def _evt(type_: str, step: int, **args) -> TrajectoryEvent:
    return TrajectoryEvent(type=type_, step=step, args=args, raw={})


def _bash(step: int, cmd: str = "ls") -> TrajectoryEvent:
    return _evt("bash_call", step, command=cmd)


def _file_read(step: int, path: str = "main.py") -> TrajectoryEvent:
    return _evt("file_read", step, command=f"cat {path}", path=path)


def _file_edit(step: int, path: str = "main.py") -> TrajectoryEvent:
    return _evt("file_edit", step, command="edit", path=path, operation="modify")


def _test_fail(step: int) -> TrajectoryEvent:
    return _evt("test_run", step, command="pytest", framework="pytest", outcome="fail")


def _test_pass(step: int) -> TrajectoryEvent:
    return _evt("test_run", step, command="pytest", framework="pytest", outcome="pass")


def _error(step: int, error_type: str = "TypeError") -> TrajectoryEvent:
    return _evt("error_reveal", step, error_type=error_type, message=f"{error_type}: bad")


def _task_trans(step: int, from_p: str = "exploration", to_p: str = "hypothesis") -> TrajectoryEvent:
    return _evt("task_transition", step, from_phase=from_p, to_phase=to_p, reason="sub-task")


def _make_valid_events(n_bash: int = 12, n_reads: int = 5, source: str = "tb") -> list[TrajectoryEvent]:
    """Build a minimal valid event sequence that satisfies filter invariants."""
    events = []
    step = 0
    for i in range(n_bash):
        events.append(_bash(step, f"cmd_{i}")); step += 1
    for i in range(n_reads):
        events.append(_file_read(step, f"file_{i}.py")); step += 1
    events.append(_file_edit(step)); step += 1    # SubGoalTransition #1
    events.append(_test_fail(step)); step += 1    # SubGoalTransition #2 + TA(unavailable)
    for _ in range(4):
        events.append(_bash(step, "make build")); step += 1
    return events


def _run_pipeline(events: list[TrajectoryEvent], source: str = "tb"):
    """Run the full pipeline on a list of events and return (constraints, active_pairs)."""
    agg_events, _ = aggregate_events(events, source)
    constraints, active_pairs = translate_trajectory(agg_events, source)
    from src.observability import apply_asymmetric_observability_with_indices
    constraints, kept_indices = apply_asymmetric_observability_with_indices(constraints)
    active_pairs = [active_pairs[i] for i in kept_indices]
    return constraints, active_pairs


def _make_chain_dict(constraints, active_pairs, chain_id: str = "test_chain_0") -> dict:
    return {
        "chain_id": chain_id,
        "match_id": chain_id,
        "source": "tb",
        "task_id": "task_0",
        "constraints": constraints,
        "active_pair_by_step": active_pairs,
        "rendered": render_chain(constraints),
        "action_at_step": None,
    }


# ---------------------------------------------------------------------------
# TestFullPipelineTB — Terminal-Bench source
# ---------------------------------------------------------------------------

class TestFullPipelineTB:
    def test_pipeline_produces_constraints(self):
        events = _make_valid_events(source="tb")
        cs, _ = _run_pipeline(events, "tb")
        assert len(cs) > 0

    def test_pipeline_passes_filter(self):
        events = _make_valid_events(source="tb")
        cs, _ = _run_pipeline(events, "tb")
        assert is_valid_chain(cs)

    def test_pipeline_render_no_leakage(self):
        events = _make_valid_events(source="tb")
        cs, _ = _run_pipeline(events, "tb")
        rendered = render_chain(cs, perspective="tb")
        leaked = check_programming_leakage(rendered)
        assert leaked == [], f"Leakage detected: {leaked}"

    def test_pipeline_active_pairs_match_constraints(self):
        events = _make_valid_events(source="tb")
        cs, aps = _run_pipeline(events, "tb")
        assert len(cs) == len(aps)

    def test_pipeline_active_pairs_are_string_tuples(self):
        events = _make_valid_events(source="tb")
        _, aps = _run_pipeline(events, "tb")
        for pair in aps:
            assert isinstance(pair, tuple)
            assert len(pair) == 2
            assert all(isinstance(s, str) for s in pair)

    def test_pipeline_chain_length_in_bounds(self):
        events = _make_valid_events(source="tb")
        cs, _ = _run_pipeline(events, "tb")
        assert 20 <= len(cs) <= 40, f"Chain length {len(cs)} out of bounds"


# ---------------------------------------------------------------------------
# TestFullPipelineSWE — SWE-bench source
# ---------------------------------------------------------------------------

class TestFullPipelineSWE:
    def _make_swe_events(self) -> list[TrajectoryEvent]:
        # SWE aggregation: burst-collapses ≥3 consecutive file_reads to 1 event,
        # and compresses retry loops.  Use 20 distinct bash_calls so that after
        # burst-collapse (5 reads → 1) the chain still has ≥20 constraints.
        events = []
        step = 0
        for i in range(20):
            events.append(_bash(step, f"cmd_{i}")); step += 1
        for i in range(5):
            events.append(_file_read(step, f"module_{i}.py")); step += 1
        events.append(_file_edit(step)); step += 1
        events.append(_test_fail(step)); step += 1
        return events

    def test_pipeline_passes_filter_swe(self):
        events = self._make_swe_events()
        cs, _ = _run_pipeline(events, "swe")
        assert is_valid_chain(cs)

    def test_pipeline_render_no_leakage_swe(self):
        events = self._make_swe_events()
        cs, _ = _run_pipeline(events, "swe")
        rendered = render_chain(cs, perspective="swe")
        leaked = check_programming_leakage(rendered)
        assert leaked == [], f"Leakage detected in SWE chain: {leaked}"


# ---------------------------------------------------------------------------
# TestFullPipelineHuman — Human-AI session source
# ---------------------------------------------------------------------------

class TestFullPipelineHuman:
    def _make_human_events(self) -> list[TrajectoryEvent]:
        events = []
        step = 0
        for i in range(12):
            events.append(_bash(step, f"action_{i}")); step += 1
        for i in range(5):
            events.append(_file_read(step, f"doc_{i}.py")); step += 1
        events.append(_file_edit(step)); step += 1
        events.append(_test_fail(step)); step += 1
        for _ in range(4):
            events.append(_task_trans(step, "exploration", "hypothesis")); step += 1
        return events

    def test_pipeline_passes_filter_human(self):
        events = self._make_human_events()
        cs, _ = _run_pipeline(events, "human")
        assert is_valid_chain(cs)

    def test_pipeline_render_no_leakage_human(self):
        events = self._make_human_events()
        cs, _ = _run_pipeline(events, "human")
        rendered = render_chain(cs, perspective="human")
        leaked = check_programming_leakage(rendered)
        assert leaked == [], f"Leakage detected in human chain: {leaked}"


# ---------------------------------------------------------------------------
# TestShuffler — shuffle_chain integration
# ---------------------------------------------------------------------------

class TestShuffler:
    def _make_chain_dict(self, source: str = "tb") -> dict:
        events = _make_valid_events(source=source)
        cs, aps = _run_pipeline(events, source)
        rendered = render_chain(cs, perspective=source)
        return {
            "chain_id": f"{source}_test_0",
            "match_id": f"{source}_test_0",
            "source": source,
            "task_id": "task_0",
            "constraints": cs,
            "active_pair_by_step": aps,
            "rendered": rendered,
            "action_at_step": None,
        }

    def test_shuffle_produces_different_ordering(self):
        chain = self._make_chain_dict()
        shuffled = shuffle_chain(chain, seed=42)
        orig_types = [type(c).__name__ for c in chain["constraints"]]
        shuf_types = [type(c).__name__ for c in shuffled["constraints"]]
        assert orig_types != shuf_types, "Expected different ordering after shuffle"

    def test_shuffle_preserves_type_counts(self):
        chain = self._make_chain_dict()
        shuffled = shuffle_chain(chain, seed=42)
        from collections import Counter
        orig = Counter(type(c).__name__ for c in chain["constraints"])
        shuf = Counter(type(c).__name__ for c in shuffled["constraints"])
        assert orig == shuf

    def test_shuffle_timestamps_nondecreasing(self):
        chain = self._make_chain_dict()
        shuffled = shuffle_chain(chain, seed=42)
        timestamps = [c.timestamp for c in shuffled["constraints"]]
        assert timestamps == sorted(timestamps)

    def test_shuffle_chain_id_suffix(self):
        chain = self._make_chain_dict()
        shuffled = shuffle_chain(chain, seed=1337)
        assert shuffled["chain_id"].endswith("_shuffled_1337")

    def test_shuffle_active_pairs_permuted(self):
        chain = self._make_chain_dict()
        shuffled = shuffle_chain(chain, seed=42)
        assert len(shuffled["active_pair_by_step"]) == len(chain["active_pair_by_step"])

    def test_different_seeds_produce_different_shuffles(self):
        chain = self._make_chain_dict()
        s1 = shuffle_chain(chain, seed=42)
        s2 = shuffle_chain(chain, seed=1337)
        types1 = [type(c).__name__ for c in s1["constraints"]]
        types2 = [type(c).__name__ for c in s2["constraints"]]
        assert types1 != types2


# ---------------------------------------------------------------------------
# TestSerialisation — chain round-trip through JSONL
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_constraint_to_dict_and_back(self):
        events = _make_valid_events()
        cs, _ = _run_pipeline(events)
        for c in cs:
            d = constraint_to_dict(c)
            c2 = constraint_from_dict(d)
            assert c == c2

    def test_chain_dict_json_serializable(self):
        events = _make_valid_events()
        cs, aps = _run_pipeline(events)
        rendered = render_chain(cs)
        chain = {
            "chain_id": "tb_test_0",
            "match_id": "tb_test_0",
            "source": "tb",
            "task_id": "test_task",
            "constraints": [constraint_to_dict(c) for c in cs],
            "active_pair_by_step": list(aps),
            "rendered": rendered,
            "action_at_step": None,
        }
        # Should not raise
        serialized = json.dumps(chain)
        recovered = json.loads(serialized)
        assert recovered["chain_id"] == "tb_test_0"
        assert len(recovered["constraints"]) == len(cs)

    def test_chain_round_trip_through_file(self):
        events = _make_valid_events()
        cs, aps = _run_pipeline(events)
        rendered = render_chain(cs)
        chain = {
            "chain_id": "tb_test_1",
            "match_id": "tb_test_1",
            "source": "tb",
            "task_id": "test_task",
            "constraints": [constraint_to_dict(c) for c in cs],
            "active_pair_by_step": list(aps),
            "rendered": rendered,
            "action_at_step": None,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps(chain) + "\n")
            tmp_path = fh.name

        with open(tmp_path, encoding="utf-8") as fh:
            recovered = json.loads(fh.read().strip())

        assert recovered["chain_id"] == "tb_test_1"
        cs_recovered = [constraint_from_dict(d) for d in recovered["constraints"]]
        assert len(cs_recovered) == len(cs)
        for orig, rec in zip(cs, cs_recovered):
            assert type(orig) == type(rec)
            assert orig == rec


# ---------------------------------------------------------------------------
# TestGate3Synthetic — Gate 3 leakage check on 20+ synthetic chains/source
# ---------------------------------------------------------------------------

class TestGate3Synthetic:
    """
    Gate 3 validation: 20 synthetic chains per source, all must pass render_chain
    without raising ValueError (no programming vocabulary leakage).
    """

    def _build_chains_for_source(self, source: str, n: int = 20) -> list[list]:
        # Use 20+ distinct bash_calls so that even after SWE burst-collapse
        # (≥3 consecutive file_reads → 1) the chain satisfies the ≥20 length filter.
        chains = []
        for idx in range(n):
            n_bash = 20 + (idx % 5)
            events = []
            step = 0
            for i in range(n_bash):
                events.append(_bash(step, f"task_{idx}_op_{i}")); step += 1
            for i in range(5):
                events.append(_file_read(step, f"src_{idx}_{i}.py")); step += 1
            events.append(_file_edit(step, f"mod_{idx}.py")); step += 1
            events.append(_test_fail(step)); step += 1
            chains.append(events)
        return chains

    def _check_no_leakage(self, source: str, chains_events: list[list]) -> list[str]:
        failures = []
        for idx, events in enumerate(chains_events):
            try:
                cs, _ = _run_pipeline(events, source)
                if not is_valid_chain(cs):
                    failures.append(f"{source}[{idx}]: filter_fail")
                    continue
                render_chain(cs, perspective=source)
            except ValueError as exc:
                failures.append(f"{source}[{idx}]: {exc}")
        return failures

    def test_20_tb_chains_pass_gate3(self):
        chains = self._build_chains_for_source("tb", n=20)
        failures = self._check_no_leakage("tb", chains)
        assert failures == [], f"Gate 3 failures (tb):\n" + "\n".join(failures)

    def test_20_swe_chains_pass_gate3(self):
        chains = self._build_chains_for_source("swe", n=20)
        failures = self._check_no_leakage("swe", chains)
        assert failures == [], f"Gate 3 failures (swe):\n" + "\n".join(failures)

    def test_20_human_chains_pass_gate3(self):
        chains = self._build_chains_for_source("human", n=20)
        failures = self._check_no_leakage("human", chains)
        assert failures == [], f"Gate 3 failures (human):\n" + "\n".join(failures)

    def test_40_tb_chains_pass_gate3(self):
        """Double the minimum to be confident."""
        chains = self._build_chains_for_source("tb", n=40)
        failures = self._check_no_leakage("tb", chains)
        assert failures == [], f"Gate 3 failures (40 tb chains):\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# TestBuildChainsModule — unit tests for build_chains.py helpers
# ---------------------------------------------------------------------------

class TestBuildChainsModule:
    def test_load_events_from_record(self):
        from scripts.build_chains import _load_events
        record = {
            "task_id": "t1",
            "events": [
                {"type": "bash_call", "step": 0, "args": {"command": "ls"}, "raw": {}},
                {"type": "file_read", "step": 1, "args": {"path": "a.py"}, "raw": {}},
            ],
        }
        events = _load_events(record)
        assert len(events) == 2
        assert events[0].type == "bash_call"
        assert events[1].type == "file_read"

    def test_load_events_empty(self):
        from scripts.build_chains import _load_events
        assert _load_events({}) == []
        assert _load_events({"events": []}) == []

    def test_process_trajectory_success(self, tmp_path):
        from scripts.build_chains import process_trajectory

        out_real = tmp_path / "real"
        out_shuffled = tmp_path / "shuffled"

        events = _make_valid_events()
        record = {
            "task_id": "task_proc_0",
            "events": [
                {"type": e.type, "step": e.step, "args": e.args, "raw": e.raw}
                for e in events
            ],
        }
        success, reason = process_trajectory(record, "tb", out_real, out_shuffled)
        assert success, f"Expected success, got reason={reason!r}"
        chain_files = list(out_real.glob("*.jsonl"))
        assert len(chain_files) == 1

    def test_process_trajectory_filter_fail(self, tmp_path):
        from scripts.build_chains import process_trajectory

        out_real = tmp_path / "real"
        out_shuffled = tmp_path / "shuffled"

        # Only 2 events — will fail filter (too short)
        record = {
            "task_id": "task_short",
            "events": [
                {"type": "bash_call", "step": 0, "args": {"command": "ls"}, "raw": {}},
                {"type": "bash_call", "step": 1, "args": {"command": "pwd"}, "raw": {}},
            ],
        }
        success, reason = process_trajectory(record, "tb", out_real, out_shuffled)
        assert not success
        assert reason == "filter_fail"

    def test_process_trajectory_no_events(self, tmp_path):
        from scripts.build_chains import process_trajectory

        out_real = tmp_path / "real"
        out_shuffled = tmp_path / "shuffled"
        record = {"task_id": "empty"}
        success, reason = process_trajectory(record, "tb", out_real, out_shuffled)
        assert not success
        assert reason == "no_events"

    def test_gate3_check_passes(self, tmp_path):
        from scripts.build_chains import gate3_check, _chain_to_dict, _save_chain

        out_real = tmp_path / "real"
        for idx in range(20):
            events = _make_valid_events()
            cs, aps = _run_pipeline(events)
            rendered = render_chain(cs)
            chain = _chain_to_dict(
                chain_id=f"tb_gate3_{idx}",
                source="tb",
                task_id=f"task_{idx}",
                constraints=cs,
                active_pairs=aps,
                rendered=rendered,
            )
            _save_chain(chain, out_real)

        assert gate3_check(out_real, min_chains=20)

    def test_gate3_check_fails_too_few(self, tmp_path):
        from scripts.build_chains import gate3_check, _chain_to_dict, _save_chain

        out_real = tmp_path / "real"
        # Only 5 chains when 20 are required
        for idx in range(5):
            events = _make_valid_events()
            cs, aps = _run_pipeline(events)
            rendered = render_chain(cs)
            chain = _chain_to_dict(
                chain_id=f"tb_few_{idx}",
                source="tb",
                task_id=f"task_{idx}",
                constraints=cs,
                active_pairs=aps,
                rendered=rendered,
            )
            _save_chain(chain, out_real)

        assert not gate3_check(out_real, min_chains=20)

    def test_iter_records_missing_file(self, tmp_path):
        from scripts.build_chains import _iter_records
        records = _iter_records(tmp_path)
        assert records == []

    def test_iter_records_valid_jsonl(self, tmp_path):
        from scripts.build_chains import _iter_records
        traj_file = tmp_path / "trajectories.jsonl"
        traj_file.write_text(
            json.dumps({"task_id": "a", "events": []}) + "\n" +
            json.dumps({"task_id": "b", "events": []}) + "\n"
        )
        records = _iter_records(tmp_path)
        assert len(records) == 2
        assert records[0]["task_id"] == "a"
