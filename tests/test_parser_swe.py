"""
Tests for src/parser_swe.py — SWE-bench trajectory parser.

All tests use synthetic trajectory data so they run without any real dataset.
"""

from __future__ import annotations

import pytest
from src.parser_swe import (
    parse_swe_trajectory,
    filter_trajectory,
    _classify_swe_command,
    _extract_swe_outcome,
)
from src.parser_tb import TrajectoryEvent, TrajectoryLog


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_step(action: str, observation: str = "", thought: str = "") -> dict:
    return {"action": action, "observation": observation, "thought": thought, "state": "$"}


def _make_format_a(
    instance_id: str = "django__django-12345",
    model: str = "gpt-4-turbo",
    steps: list[dict] | None = None,
    exit_status: str = "submitted",
) -> dict:
    """Build a Format A (action/observation) SWE-agent trajectory dict."""
    if steps is None:
        steps = []
    return {
        "instance_id": instance_id,
        "model_name_or_path": model,
        "traj": steps,
        "info": {"exit_status": exit_status},
    }


def _make_format_b(
    instance_id: str = "astropy__astropy-9999",
    model: str = "claude-sonnet-4-6",
    messages: list[dict] | None = None,
    exit_status: str = "submitted",
) -> dict:
    """Build a Format B (chat messages) SWE-agent trajectory dict."""
    if messages is None:
        messages = []
    return {
        "instance_id": instance_id,
        "model_name_or_path": model,
        "messages": messages,
        "info": {"exit_status": exit_status},
    }


def _tb_tool_call(call_id: str, cmd: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": "bash", "arguments": {"cmd": cmd}},
    }


def _tb_assistant_msg(cmd: str, call_id: str = "c0") -> dict:
    return {
        "role": "assistant",
        "content": "Running command.",
        "tool_calls": [_tb_tool_call(call_id, cmd)],
    }


def _tb_tool_msg(call_id: str, output: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": output}


def _many_steps(n: int = 20) -> list[dict]:
    """Generate n generic steps to satisfy min_events filter."""
    steps = []
    for i in range(n):
        steps.append(_make_step(f"ls dir_{i}", f"file_{i}.py"))
    return steps


# ---------------------------------------------------------------------------
# TestBasicParsing
# ---------------------------------------------------------------------------

class TestBasicParsing:
    def test_returns_trajectory_log(self):
        raw = _make_format_a(steps=_many_steps(5))
        log = parse_swe_trajectory(raw)
        assert isinstance(log, TrajectoryLog)

    def test_source_is_swe(self):
        raw = _make_format_a(steps=[])
        log = parse_swe_trajectory(raw)
        assert log.source == "swe"

    def test_instance_id_as_task_id(self):
        raw = _make_format_a(instance_id="sympy__sympy-42")
        log = parse_swe_trajectory(raw)
        assert log.task_id == "sympy__sympy-42"

    def test_model_name_extracted(self):
        raw = _make_format_a(model="claude-haiku-4-5-20251001")
        log = parse_swe_trajectory(raw)
        assert log.model == "claude-haiku-4-5-20251001"

    def test_raises_on_missing_trajectory_key(self):
        raw = {"instance_id": "x", "model_name_or_path": "m", "info": {}}
        with pytest.raises(ValueError):
            parse_swe_trajectory(raw)

    def test_format_b_chat_messages(self):
        messages = [
            {"role": "system", "content": "You are a coding agent."},
            {"role": "user", "content": "Fix this bug."},
            _tb_assistant_msg("ls -la", "c0"),
            _tb_tool_msg("c0", "file.py"),
        ]
        raw = _make_format_b(messages=messages)
        log = parse_swe_trajectory(raw)
        assert isinstance(log, TrajectoryLog)
        assert any(e.type in ("bash_call", "file_read") for e in log.events)

    def test_trajectory_key_also_accepted(self):
        raw = {
            "instance_id": "x",
            "model_name_or_path": "m",
            "trajectory": [_make_step("ls", "file.py")],
            "info": {"exit_status": "submitted"},
        }
        log = parse_swe_trajectory(raw)
        assert isinstance(log, TrajectoryLog)


# ---------------------------------------------------------------------------
# TestOutcomeExtraction
# ---------------------------------------------------------------------------

class TestOutcomeExtraction:
    @pytest.mark.parametrize("status,expected", [
        ("submitted", "pass"),
        ("exit_cost", "pass"),
        ("exit_format", "pass"),
        ("early_exit", "fail"),
        ("exit_context", "fail"),
        ("autosubmission_failed", "fail"),
        ("", "fail"),
    ])
    def test_outcome_from_exit_status(self, status, expected):
        result = _extract_swe_outcome({"exit_status": status})
        assert result == expected

    def test_pass_when_submission_present(self):
        result = _extract_swe_outcome({"exit_status": "", "submission": "diff content"})
        assert result == "pass"

    def test_fail_on_empty_info(self):
        assert _extract_swe_outcome({}) == "fail"

    def test_trajectory_outcome_pass(self):
        raw = _make_format_a(exit_status="submitted", steps=_many_steps(5))
        assert parse_swe_trajectory(raw).outcome == "pass"

    def test_trajectory_outcome_fail(self):
        raw = _make_format_a(exit_status="early_exit", steps=_many_steps(5))
        assert parse_swe_trajectory(raw).outcome == "fail"


# ---------------------------------------------------------------------------
# TestEventExtraction
# ---------------------------------------------------------------------------

class TestEventExtraction:
    def test_bash_call_from_git_status(self):
        raw = _make_format_a(steps=[_make_step("git status", "On branch main")])
        log = parse_swe_trajectory(raw)
        assert any(e.type == "bash_call" for e in log.events)

    def test_file_read_from_cat(self):
        raw = _make_format_a(steps=[_make_step("cat django/db/models.py", "class Model:")])
        log = parse_swe_trajectory(raw)
        assert any(e.type == "file_read" for e in log.events)

    def test_test_run_from_pytest(self):
        raw = _make_format_a(
            steps=[_make_step("pytest tests/", "5 passed in 2.1s")]
        )
        log = parse_swe_trajectory(raw)
        assert any(e.type == "test_run" for e in log.events)

    def test_test_run_outcome_filled_in(self):
        raw = _make_format_a(
            steps=[_make_step("pytest tests/", "3 failed, 2 passed")]
        )
        log = parse_swe_trajectory(raw)
        tr = [e for e in log.events if e.type == "test_run"]
        assert tr[0].args["outcome"] == "fail"

    def test_error_reveal_from_traceback_in_observation(self):
        obs = "Traceback (most recent call last):\nTypeError: unsupported operand"
        raw = _make_format_a(steps=[_make_step("python run.py", obs)])
        log = parse_swe_trajectory(raw)
        assert any(e.type == "error_reveal" for e in log.events)

    def test_git_diff_is_file_edit(self):
        raw = _make_format_a(steps=[_make_step("git diff HEAD", "--- a/file.py")])
        log = parse_swe_trajectory(raw)
        assert any(e.type == "file_edit" for e in log.events)

    def test_git_apply_is_file_edit(self):
        raw = _make_format_a(steps=[_make_step("git apply patch.diff", "")])
        log = parse_swe_trajectory(raw)
        assert any(e.type == "file_edit" for e in log.events)

    def test_context_update_from_model_stats(self):
        raw = _make_format_a(steps=[])
        raw["info"]["model_stats"] = {"tokens_sent": 20000, "tokens_received": 5000}
        log = parse_swe_trajectory(raw)
        cu = [e for e in log.events if e.type == "context_update"]
        assert len(cu) == 1
        assert cu[0].args["tokens_used"] == 25000

    def test_empty_traj_produces_no_action_events(self):
        raw = _make_format_a(steps=[])
        log = parse_swe_trajectory(raw)
        action_events = [e for e in log.events if e.type != "context_update"]
        assert action_events == []


# ---------------------------------------------------------------------------
# TestSWECommandClassification
# ---------------------------------------------------------------------------

class TestSWECommandClassification:
    @pytest.mark.parametrize("cmd,expected", [
        ("git diff HEAD", "file_edit"),
        ("git apply fix.patch", "file_edit"),
        ("edit 42:50 main.py", "file_edit"),
        ("create new_file.py", "file_edit"),
        ("cat README.md", "file_read"),
        ("pytest tests/", "test_run"),
        ("git status", "bash_call"),
        ("pip install -e .", "bash_call"),
    ])
    def test_classify(self, cmd, expected):
        assert _classify_swe_command(cmd) == expected


# ---------------------------------------------------------------------------
# TestFilterTrajectory
# ---------------------------------------------------------------------------

class TestFilterTrajectory:
    def _make_log(self, n_events: int, outcome: str = "pass") -> TrajectoryLog:
        events = [
            TrajectoryEvent(type="bash_call", step=i, args={}, raw={})
            for i in range(n_events)
        ]
        return TrajectoryLog(
            task_id="t", model="m", agent="swe-agent",
            outcome=outcome, events=events, source="swe",
        )

    def test_passes_with_enough_events(self):
        assert filter_trajectory(self._make_log(20)) is True

    def test_fails_with_too_few_events(self):
        assert filter_trajectory(self._make_log(10)) is False

    def test_fails_on_error_outcome(self):
        assert filter_trajectory(self._make_log(20, outcome="error")) is False

    def test_passes_on_fail_outcome(self):
        assert filter_trajectory(self._make_log(20, outcome="fail")) is True
