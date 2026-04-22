"""
Tests for src/translation.py — T-code implementation.

Verifies that each event type produces the correct Constraint types, that
chains from synthetic trajectories satisfy the filter invariants, and that
serialisation round-trips work correctly.
"""

from __future__ import annotations

import pytest
from src.parser_tb import TrajectoryEvent
from src.translation import (
    translate_event,
    translate_trajectory,
    constraint_to_dict,
    constraint_from_dict,
    TranslationContext,
    ResourceBudget,
    ToolAvailability,
    SubGoalTransition,
    InformationState,
    CoordinationDependency,
    OptimizationCriterion,
    Constraint,
)
from src.filter import is_valid_chain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evt(type_: str, step: int, **args) -> TrajectoryEvent:
    return TrajectoryEvent(type=type_, step=step, args=args, raw={})


def _bash(step: int, cmd: str = "ls") -> TrajectoryEvent:
    return _evt("bash_call", step, command=cmd)


def _file_read(step: int, path: str = "main.py") -> TrajectoryEvent:
    return _evt("file_read", step, command=f"cat {path}", path=path)


def _file_edit(step: int, path: str = "main.py") -> TrajectoryEvent:
    return _evt("file_edit", step, command="edit", path=path, operation="modify")


def _test_pass(step: int) -> TrajectoryEvent:
    return _evt("test_run", step, command="pytest", framework="pytest", outcome="pass")


def _test_fail(step: int) -> TrajectoryEvent:
    return _evt("test_run", step, command="pytest", framework="pytest", outcome="fail")


def _error(step: int, error_type: str = "TypeError") -> TrajectoryEvent:
    return _evt("error_reveal", step, error_type=error_type, message=f"{error_type}: bad")


def _context_update(step: int, used: int = 50_000, max_: int = 200_000) -> TrajectoryEvent:
    return _evt("context_update", step, tokens_used=used, tokens_max=max_)


def _task_trans(step: int, from_p: str = "exploration", to_p: str = "hypothesis") -> TrajectoryEvent:
    return _evt("task_transition", step, from_phase=from_p, to_phase=to_p, reason="new sub-task")


def _ctx() -> TranslationContext:
    return TranslationContext()


# Build a minimal valid trajectory (satisfies all filter invariants)
def _make_valid_events(n_bash: int = 12, n_reads: int = 5) -> list[TrajectoryEvent]:
    events = []
    step = 0
    # Enough bash_calls for ≥10 ResourceBudget
    for i in range(n_bash):
        events.append(_bash(step, f"cmd_{i}"))
        step += 1
    # File reads
    for i in range(n_reads):
        events.append(_file_read(step, f"file_{i}.py"))
        step += 1
    # First file_edit → SubGoalTransition #1
    events.append(_file_edit(step)); step += 1
    # Test fail → SubGoalTransition #2 + ToolAvailability(unavailable)
    events.append(_test_fail(step)); step += 1
    # A few more to pad length
    for _ in range(4):
        events.append(_bash(step, "make build")); step += 1
    return events


# ---------------------------------------------------------------------------
# TestEventTranslation
# ---------------------------------------------------------------------------

class TestEventTranslation:
    def test_bash_call_produces_resource_budget(self):
        cs = translate_event(_bash(0, "pip install foo"), _ctx())
        assert any(isinstance(c, ResourceBudget) for c in cs)

    def test_bash_call_resource_budget_resource_is_context_window(self):
        cs = translate_event(_bash(0), _ctx())
        rb = next(c for c in cs if isinstance(c, ResourceBudget))
        assert rb.resource == "context_window"

    def test_file_read_produces_information_state(self):
        cs = translate_event(_file_read(0, "app.py"), _ctx())
        assert any(isinstance(c, InformationState) for c in cs)

    def test_file_read_adds_file_label(self):
        cs = translate_event(_file_read(0, "app.py"), _ctx())
        is_ = next(c for c in cs if isinstance(c, InformationState))
        assert len(is_.observable_added) == 1
        assert is_.observable_added[0].startswith("file_")

    def test_file_read_same_path_same_label(self):
        ctx = _ctx()
        cs1 = translate_event(_file_read(0, "app.py"), ctx)
        cs2 = translate_event(_file_read(1, "app.py"), ctx)
        label1 = next(c for c in cs1 if isinstance(c, InformationState)).observable_added[0]
        label2 = next(c for c in cs2 if isinstance(c, InformationState)).observable_added[0]
        assert label1 == label2

    def test_file_read_different_paths_different_labels(self):
        ctx = _ctx()
        cs1 = translate_event(_file_read(0, "a.py"), ctx)
        cs2 = translate_event(_file_read(1, "b.py"), ctx)
        label1 = next(c for c in cs1 if isinstance(c, InformationState)).observable_added[0]
        label2 = next(c for c in cs2 if isinstance(c, InformationState)).observable_added[0]
        assert label1 != label2

    def test_first_file_edit_produces_subgoal_transition(self):
        cs = translate_event(_file_edit(0), _ctx())
        assert any(isinstance(c, SubGoalTransition) for c in cs)

    def test_first_file_edit_transition_to_implementation(self):
        cs = translate_event(_file_edit(0), _ctx())
        sgt = next(c for c in cs if isinstance(c, SubGoalTransition))
        assert sgt.to_phase == "implementation"

    def test_subsequent_file_edit_produces_tool_availability(self):
        ctx = _ctx()
        translate_event(_file_edit(0, "a.py"), ctx)
        cs = translate_event(_file_edit(1, "b.py"), ctx)
        assert any(isinstance(c, ToolAvailability) for c in cs)

    def test_test_run_pass_produces_subgoal_to_validation(self):
        ctx = _ctx()
        translate_event(_file_edit(0), ctx)  # first edit → implementation
        cs = translate_event(_test_pass(1), ctx)
        sgts = [c for c in cs if isinstance(c, SubGoalTransition)]
        assert any(c.to_phase == "validation" for c in sgts)

    def test_test_run_pass_produces_optimization_criterion(self):
        cs = translate_event(_test_pass(0), _ctx())
        assert any(isinstance(c, OptimizationCriterion) for c in cs)

    def test_test_run_fail_produces_subgoal_to_debugging(self):
        ctx = _ctx()
        translate_event(_file_edit(0), ctx)
        cs = translate_event(_test_fail(1), ctx)
        sgts = [c for c in cs if isinstance(c, SubGoalTransition)]
        assert any(c.to_phase == "debugging" for c in sgts)

    def test_test_run_fail_produces_tool_availability_unavailable(self):
        ctx = _ctx()
        translate_event(_file_edit(0), ctx)
        cs = translate_event(_test_fail(1), ctx)
        ta = [c for c in cs if isinstance(c, ToolAvailability) and c.state == "unavailable"]
        assert len(ta) >= 1
        assert ta[0].tool == "test_suite"

    def test_test_run_fail_decrements_patience_budget(self):
        ctx = _ctx()
        initial = ctx.patience_budget
        translate_event(_test_fail(0), ctx)
        assert ctx.patience_budget < initial

    def test_error_reveal_produces_information_state_first(self):
        cs = translate_event(_error(0), _ctx())
        assert any(isinstance(c, InformationState) for c in cs)

    def test_error_reveal_alternates_with_coordination_dependency(self):
        ctx = _ctx()
        cs1 = translate_event(_error(0), ctx)
        cs2 = translate_event(_error(1), ctx)
        assert any(isinstance(c, InformationState) for c in cs1)
        assert any(isinstance(c, CoordinationDependency) for c in cs2)

    def test_context_update_produces_resource_budget(self):
        cs = translate_event(_context_update(0, 100_000, 200_000), _ctx())
        assert any(isinstance(c, ResourceBudget) for c in cs)

    def test_context_update_high_usage_produces_tool_unavailable(self):
        cs = translate_event(_context_update(0, 190_000, 200_000), _ctx())
        ta = [c for c in cs if isinstance(c, ToolAvailability) and c.state == "unavailable"]
        assert len(ta) == 1
        assert ta[0].tool == "context_window"

    def test_context_update_unavailable_only_emitted_once(self):
        ctx = _ctx()
        translate_event(_context_update(0, 190_000), ctx)
        cs = translate_event(_context_update(1, 195_000), ctx)
        ta = [c for c in cs if isinstance(c, ToolAvailability) and c.state == "unavailable"]
        assert len(ta) == 0

    def test_task_transition_produces_subgoal_transition(self):
        cs = translate_event(_task_trans(0, "exploration", "hypothesis"), _ctx())
        assert any(isinstance(c, SubGoalTransition) for c in cs)

    def test_unknown_event_type_returns_empty(self):
        cs = translate_event(_evt("totally_unknown", 0), _ctx())
        assert cs == []

    def test_timestamps_match_event_step(self):
        step = 42
        cs = translate_event(_bash(step), _ctx())
        assert all(c.timestamp == step for c in cs)


# ---------------------------------------------------------------------------
# TestTranslateTrajectory
# ---------------------------------------------------------------------------

class TestTranslateTrajectory:
    def test_returns_tuple(self):
        result = translate_trajectory([], "tb")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_empty_events_returns_empty(self):
        cs, aps = translate_trajectory([], "tb")
        assert cs == []
        assert aps == []

    def test_active_pairs_length_matches_constraints(self):
        events = _make_valid_events()
        cs, aps = translate_trajectory(events, "tb")
        assert len(cs) == len(aps)

    def test_active_pairs_are_tuples_of_two_strings(self):
        events = [_bash(0), _file_read(1), _file_edit(2)]
        cs, aps = translate_trajectory(events, "tb")
        for pair in aps:
            assert isinstance(pair, tuple)
            assert len(pair) == 2
            assert all(isinstance(s, str) for s in pair)

    def test_source_stored_in_context(self):
        ctx = TranslationContext(source="swe")
        assert ctx.source == "swe"


# ---------------------------------------------------------------------------
# TestFilterInvariants
# ---------------------------------------------------------------------------

class TestFilterInvariants:
    """Verify that synthetic trajectories built by T-code pass the chain filter."""

    def test_valid_trajectory_passes_filter(self):
        events = _make_valid_events()
        cs, _ = translate_trajectory(events, "tb")
        assert is_valid_chain(cs), (
            f"Chain failed filter. "
            f"len={len(cs)}, "
            f"RB={sum(isinstance(c, ResourceBudget) for c in cs)}, "
            f"SGT={sum(isinstance(c, SubGoalTransition) for c in cs)}, "
            f"TA_unavail={sum(1 for c in cs if isinstance(c, ToolAvailability) and c.state == 'unavailable')}"
        )

    def test_has_at_least_10_resource_budgets(self):
        events = _make_valid_events(n_bash=12)
        cs, _ = translate_trajectory(events, "tb")
        assert sum(isinstance(c, ResourceBudget) for c in cs) >= 10

    def test_has_at_least_2_subgoal_transitions(self):
        events = _make_valid_events()
        cs, _ = translate_trajectory(events, "tb")
        assert sum(isinstance(c, SubGoalTransition) for c in cs) >= 2

    def test_has_at_least_1_tool_unavailable(self):
        events = _make_valid_events()
        cs, _ = translate_trajectory(events, "tb")
        assert sum(
            1 for c in cs
            if isinstance(c, ToolAvailability) and c.state == "unavailable"
        ) >= 1

    def test_timestamps_monotone_nondecreasing(self):
        events = _make_valid_events()
        cs, _ = translate_trajectory(events, "tb")
        timestamps = [c.timestamp for c in cs]
        assert timestamps == sorted(timestamps)

    def test_length_within_bounds_for_valid_trajectory(self):
        events = _make_valid_events()
        cs, _ = translate_trajectory(events, "tb")
        assert 20 <= len(cs) <= 40, f"Chain length {len(cs)} outside [20, 40]"


# ---------------------------------------------------------------------------
# TestSerialisation
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_resource_budget_round_trip(self):
        c = ResourceBudget(timestamp=5, resource="context_window",
                           amount=0.75, decay="monotone_decrease", recover_in=None)
        d = constraint_to_dict(c)
        assert d["type"] == "ResourceBudget"
        c2 = constraint_from_dict(d)
        assert c2 == c

    def test_tool_availability_round_trip(self):
        c = ToolAvailability(timestamp=3, tool="test_suite",
                             state="unavailable", recover_in=3)
        assert constraint_from_dict(constraint_to_dict(c)) == c

    def test_subgoal_transition_round_trip(self):
        c = SubGoalTransition(timestamp=7, from_phase="exploration",
                              to_phase="implementation", trigger="first_edit")
        assert constraint_from_dict(constraint_to_dict(c)) == c

    def test_information_state_round_trip(self):
        c = InformationState(timestamp=2, observable_added=["file_A"],
                             observable_removed=[], uncertainty=0.4)
        assert constraint_from_dict(constraint_to_dict(c)) == c

    def test_coordination_dependency_round_trip(self):
        c = CoordinationDependency(timestamp=9, role="affected_module_M1",
                                   dependency="error_class_A",
                                   expected_action="resolve_error_class_A")
        assert constraint_from_dict(constraint_to_dict(c)) == c

    def test_optimization_criterion_round_trip(self):
        c = OptimizationCriterion(timestamp=11, objective="correctness_primary",
                                  weight_shift="correctness_increase")
        assert constraint_from_dict(constraint_to_dict(c)) == c

    def test_all_types_have_type_key_in_dict(self):
        constraints = [
            ResourceBudget(0, "context_window", 0.9, "monotone_decrease", None),
            ToolAvailability(1, "test_suite", "unavailable", 3),
            SubGoalTransition(2, "exploration", "implementation", "first_edit"),
            InformationState(3, ["file_A"], [], 0.5),
            CoordinationDependency(4, "role_R1", "error_class_A", "fix_it"),
            OptimizationCriterion(5, "correctness_primary", "increase"),
        ]
        for c in constraints:
            d = constraint_to_dict(c)
            assert "type" in d
            assert d["type"] == type(c).__name__
