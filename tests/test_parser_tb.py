"""
Tests for src/parser_tb.py — Terminal-Bench trajectory parser.

All tests use synthetic trajectory data so they run without any real dataset.
"""

from __future__ import annotations

import pytest
from src.parser_tb import (
    parse_tb_trajectory,
    filter_trajectory,
    TrajectoryEvent,
    TrajectoryLog,
    _classify_command,
    _extract_outcome,
    _extract_test_outcome,
    _detect_test_framework,
    _extract_file_path,
    _extract_error_class,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_tool_call(call_id: str, name: str, cmd: str) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": {"cmd": cmd}},
    }


def _make_sample(
    task_id: str = "task_001",
    messages: list[dict] | None = None,
    scores: dict | None = None,
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Return a minimal inspect-ai sample dict."""
    if messages is None:
        messages = []
    if scores is None:
        scores = {"accuracy": {"value": 1.0}}
    return {
        "id": task_id,
        "messages": messages,
        "scores": scores,
        "output": {"model": model},
    }


def _make_assistant_msg(cmd: str, call_id: str = "c1") -> dict:
    return {
        "role": "assistant",
        "content": "I'll run a command.",
        "tool_calls": [_make_tool_call(call_id, "bash", cmd)],
    }


def _make_tool_msg(call_id: str, output: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": output}


def _make_conversation(*pairs: tuple[str, str]) -> list[dict]:
    """Build a message list from (command, output) pairs."""
    messages = [
        {"role": "system", "content": "You are a coding agent."},
        {"role": "user", "content": "Fix the bug."},
    ]
    for i, (cmd, output) in enumerate(pairs):
        cid = f"c{i}"
        messages.append(_make_assistant_msg(cmd, cid))
        messages.append(_make_tool_msg(cid, output))
    return messages


# ---------------------------------------------------------------------------
# TestBasicParsing
# ---------------------------------------------------------------------------

class TestBasicParsing:
    def test_returns_trajectory_log(self):
        raw = _make_sample(messages=_make_conversation(("ls -la", "file.py")))
        log = parse_tb_trajectory(raw)
        assert isinstance(log, TrajectoryLog)

    def test_task_id_extracted(self):
        raw = _make_sample(task_id="my_task_42")
        log = parse_tb_trajectory(raw)
        assert log.task_id == "my_task_42"

    def test_task_id_fallback_to_task_id_key(self):
        raw = {"task_id": "alt_task", "messages": [], "scores": {}}
        log = parse_tb_trajectory(raw)
        assert log.task_id == "alt_task"

    def test_model_extracted_from_output(self):
        raw = _make_sample(model="claude-haiku-4-5-20251001")
        log = parse_tb_trajectory(raw)
        assert log.model == "claude-haiku-4-5-20251001"

    def test_source_is_tb(self):
        raw = _make_sample()
        log = parse_tb_trajectory(raw)
        assert log.source == "tb"

    def test_empty_messages_produces_no_events(self):
        raw = _make_sample(messages=[])
        log = parse_tb_trajectory(raw)
        assert log.events == []

    def test_raises_value_error_on_non_list_messages(self):
        raw = {"id": "x", "messages": "not a list", "scores": {}}
        with pytest.raises(ValueError):
            parse_tb_trajectory(raw)


# ---------------------------------------------------------------------------
# TestOutcomeExtraction
# ---------------------------------------------------------------------------

class TestOutcomeExtraction:
    def test_pass_from_float_1(self):
        raw = _make_sample(scores={"accuracy": {"value": 1.0}})
        assert parse_tb_trajectory(raw).outcome == "pass"

    def test_pass_from_int_1(self):
        raw = _make_sample(scores={"verify": {"value": 1}})
        assert parse_tb_trajectory(raw).outcome == "pass"

    def test_pass_from_string_correct(self):
        raw = _make_sample(scores={"check": {"value": "correct"}})
        assert parse_tb_trajectory(raw).outcome == "pass"

    def test_fail_from_float_0(self):
        raw = _make_sample(scores={"accuracy": {"value": 0.0}})
        assert parse_tb_trajectory(raw).outcome == "fail"

    def test_fail_on_empty_scores(self):
        raw = _make_sample(scores={})
        assert parse_tb_trajectory(raw).outcome == "fail"

    def test_extract_outcome_pass_string(self):
        assert _extract_outcome({"x": {"value": "pass"}}) == "pass"

    def test_extract_outcome_true_string(self):
        assert _extract_outcome({"x": {"value": "true"}}) == "pass"


# ---------------------------------------------------------------------------
# TestEventExtraction
# ---------------------------------------------------------------------------

class TestEventExtraction:
    def test_bash_call_event(self):
        raw = _make_sample(
            messages=_make_conversation(("pip install requests", "Successfully installed"))
        )
        log = parse_tb_trajectory(raw)
        assert any(e.type == "bash_call" for e in log.events)

    def test_file_read_event_from_cat(self):
        raw = _make_sample(
            messages=_make_conversation(("cat src/main.py", "def main(): pass"))
        )
        log = parse_tb_trajectory(raw)
        assert any(e.type == "file_read" for e in log.events)

    def test_file_edit_event_from_redirect(self):
        raw = _make_sample(
            messages=_make_conversation(('echo "fix" > main.py', ""))
        )
        log = parse_tb_trajectory(raw)
        assert any(e.type == "file_edit" for e in log.events)

    def test_test_run_event_from_pytest(self):
        raw = _make_sample(
            messages=_make_conversation(("pytest tests/", "1 passed in 0.5s"))
        )
        log = parse_tb_trajectory(raw)
        assert any(e.type == "test_run" for e in log.events)

    def test_test_run_outcome_pass(self):
        raw = _make_sample(
            messages=_make_conversation(("pytest tests/", "3 passed in 1.2s"))
        )
        log = parse_tb_trajectory(raw)
        test_events = [e for e in log.events if e.type == "test_run"]
        assert len(test_events) == 1
        assert test_events[0].args["outcome"] == "pass"

    def test_test_run_outcome_fail(self):
        raw = _make_sample(
            messages=_make_conversation(("pytest tests/", "2 failed, 1 passed"))
        )
        log = parse_tb_trajectory(raw)
        test_events = [e for e in log.events if e.type == "test_run"]
        assert test_events[0].args["outcome"] == "fail"

    def test_error_reveal_from_traceback(self):
        error_output = "Traceback (most recent call last):\n  File 'x.py'\nValueError: bad"
        raw = _make_sample(
            messages=_make_conversation(("python x.py", error_output))
        )
        log = parse_tb_trajectory(raw)
        assert any(e.type == "error_reveal" for e in log.events)

    def test_error_reveal_captures_error_class(self):
        error_output = "Traceback (most recent call last):\nAttributeError: 'NoneType'"
        raw = _make_sample(
            messages=_make_conversation(("python x.py", error_output))
        )
        log = parse_tb_trajectory(raw)
        errs = [e for e in log.events if e.type == "error_reveal"]
        assert errs[0].args["error_type"] == "AttributeError"

    def test_no_error_reveal_on_clean_output(self):
        raw = _make_sample(
            messages=_make_conversation(("ls", "file.py\nsetup.py"))
        )
        log = parse_tb_trajectory(raw)
        assert not any(e.type == "error_reveal" for e in log.events)

    def test_step_numbers_are_nonnegative(self):
        raw = _make_sample(
            messages=_make_conversation(
                ("ls", "file.py"),
                ("cat file.py", "code"),
                ("pytest", "1 passed"),
            )
        )
        log = parse_tb_trajectory(raw)
        assert all(e.step >= 0 for e in log.events)

    def test_context_update_from_metadata(self):
        raw = _make_sample()
        raw["metadata"] = {"usage": {"input_tokens": 15000}}
        log = parse_tb_trajectory(raw)
        cu = [e for e in log.events if e.type == "context_update"]
        assert len(cu) == 1
        assert cu[0].args["tokens_used"] == 15000

    def test_test_run_framework_detected(self):
        raw = _make_sample(
            messages=_make_conversation(("pytest -v tests/unit/", "1 passed"))
        )
        log = parse_tb_trajectory(raw)
        tr = [e for e in log.events if e.type == "test_run"]
        assert tr[0].args["framework"] == "pytest"


# ---------------------------------------------------------------------------
# TestCommandClassification
# ---------------------------------------------------------------------------

class TestCommandClassification:
    @pytest.mark.parametrize("cmd,expected", [
        ("cat src/main.py", "file_read"),
        ("head -n 20 README.md", "file_read"),
        ("grep -r 'def foo' .", "file_read"),
        ("ls -la", "file_read"),
        ("pytest tests/", "test_run"),
        ("python -m pytest", "test_run"),
        ("python -m unittest discover", "test_run"),
        ('echo "content" > file.py', "file_edit"),
        ("sed -i 's/old/new/g' main.py", "file_edit"),
        ("pip install requests", "bash_call"),
        ("git status", "bash_call"),
        ("python setup.py install", "bash_call"),
    ])
    def test_classify(self, cmd, expected):
        assert _classify_command(cmd) == expected


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
            task_id="t", model="m", agent="a", outcome=outcome, events=events
        )

    def test_passes_with_enough_events(self):
        assert filter_trajectory(self._make_log(20)) is True

    def test_fails_with_too_few_events(self):
        assert filter_trajectory(self._make_log(5)) is False

    def test_fails_on_timeout_outcome(self):
        assert filter_trajectory(self._make_log(20, outcome="timeout")) is False

    def test_passes_on_fail_outcome(self):
        assert filter_trajectory(self._make_log(20, outcome="fail")) is True

    def test_custom_min_events(self):
        assert filter_trajectory(self._make_log(8), min_events=8) is True
        assert filter_trajectory(self._make_log(7), min_events=8) is False
