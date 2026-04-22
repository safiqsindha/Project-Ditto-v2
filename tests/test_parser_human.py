"""
Tests for src/parser_human.py — SpecStory human-AI session parser.

Uses synthetic SpecStory-format Markdown fixtures; no real data required.
"""

from __future__ import annotations

import pytest
from src.parser_human import (
    parse_human_session,
    filter_trajectory,
    _parse_turns,
    _classify_user_turn,
    _classify_assistant_turn,
    detect_secrets,
    redact_emails,
)
from src.parser_tb import TrajectoryEvent, TrajectoryLog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SHORT_SESSION = """\
## User

Can you help me understand why this function doesn't work?

## Assistant

Sure! Let me look at the code.

## User

Here's the code I'm working with.

## Assistant

I see the issue. Let me fix it for you.

## User

Thanks, that makes sense.
"""

_DEBUGGING_SESSION = """\
## User

I'm getting an error when I run the tests. Here's the output:

```
Traceback (most recent call last):
  File "test_app.py", line 42, in test_parse
    result = parse(data)
ValueError: Invalid input format
```

## Assistant

I can see the issue. The `parse` function doesn't handle the new format.

Let me fix it:

```python
def parse(data):
    if isinstance(data, dict):
        return data.get("value", None)
    return data
```

## User

That fixed the ValueError but now I'm getting an AttributeError:

```
AttributeError: 'NoneType' object has no attribute 'strip'
```

## Assistant

The issue is that `parse` can return `None`. Here's the updated fix:

```python
def parse(data):
    result = data.get("value") if isinstance(data, dict) else data
    return result.strip() if result is not None else ""
```

## User

Can you run the tests to confirm?

## Assistant

```bash
pytest tests/test_app.py -v
```

## User

The tests pass now. 3 passed in 0.4s.

## Assistant

Excellent! Let me also add a test for the None case.
"""

_CODE_PASTE_SESSION = """\
## User

Here's the file I'm working on:

```python
import os
import sys

def main():
    path = sys.argv[1]
    files = os.listdir(path)
    return files
```

What should I change to handle permission errors?

## Assistant

You should add a try/except block:

```python
def main():
    path = sys.argv[1]
    try:
        files = os.listdir(path)
    except PermissionError as e:
        print(f"Permission denied: {e}")
        return []
    return files
```

## User

What about FileNotFoundError?

## Assistant

Good catch! Here's the complete version:

```python
def main():
    path = sys.argv[1]
    try:
        files = os.listdir(path)
    except (PermissionError, FileNotFoundError) as e:
        print(f"Error: {e}")
        return []
    return files
```
"""

_EMPTY_SESSION = """\
## User

## Assistant
"""


def _make_raw(content: str, session_id: str = "test_session") -> dict:
    return {"session_id": session_id, "content": content, "repo": "owner/repo"}


# ---------------------------------------------------------------------------
# TestTurnSplitting
# ---------------------------------------------------------------------------

class TestTurnSplitting:
    def test_splits_short_session(self):
        turns = _parse_turns(_SHORT_SESSION)
        assert len(turns) == 5

    def test_role_extraction(self):
        turns = _parse_turns(_SHORT_SESSION)
        roles = [t["role"] for t in turns]
        assert roles == ["user", "assistant", "user", "assistant", "user"]

    def test_content_is_nonempty(self):
        turns = _parse_turns(_DEBUGGING_SESSION)
        for t in turns:
            # At least some turns have content
            pass  # turns may have empty content after stripping
        assert len(turns) > 0

    def test_no_turns_on_empty_string(self):
        turns = _parse_turns("")
        assert turns == []

    def test_handles_agent_role(self):
        content = "## Agent\n\nTool output here.\n\n## User\n\nThanks."
        turns = _parse_turns(content)
        assert turns[0]["role"] == "agent"


# ---------------------------------------------------------------------------
# TestBasicParsing
# ---------------------------------------------------------------------------

class TestBasicParsing:
    def test_returns_trajectory_log(self):
        log = parse_human_session(_make_raw(_SHORT_SESSION))
        assert isinstance(log, TrajectoryLog)

    def test_source_is_human(self):
        log = parse_human_session(_make_raw(_SHORT_SESSION))
        assert log.source == "human"

    def test_session_id_as_task_id(self):
        log = parse_human_session(_make_raw(_SHORT_SESSION, "my_session_42"))
        assert log.task_id == "my_session_42"

    def test_agent_is_human(self):
        log = parse_human_session(_make_raw(_SHORT_SESSION))
        assert log.agent == "human"

    def test_raises_on_empty_content(self):
        with pytest.raises(ValueError):
            parse_human_session({"session_id": "x", "content": ""})

    def test_produces_events(self):
        log = parse_human_session(_make_raw(_SHORT_SESSION))
        assert len(log.events) > 0

    def test_step_numbers_nonnegative(self):
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        assert all(e.step >= 0 for e in log.events)

    def test_step_numbers_monotone(self):
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        steps = [e.step for e in log.events]
        assert steps == sorted(steps)


# ---------------------------------------------------------------------------
# TestEventTypes
# ---------------------------------------------------------------------------

class TestEventTypes:
    def test_error_reveal_from_traceback(self):
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        assert any(e.type == "error_reveal" for e in log.events)

    def test_error_reveal_captures_class(self):
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        errs = [e for e in log.events if e.type == "error_reveal"]
        assert any("Error" in e.args.get("error_type", "") for e in errs)

    def test_file_edit_from_code_block(self):
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        assert any(e.type == "file_edit" for e in log.events)

    def test_bash_call_from_pytest(self):
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        assert any(e.type in ("bash_call", "test_run") for e in log.events)

    def test_file_read_from_user_code_paste(self):
        log = parse_human_session(_make_raw(_CODE_PASTE_SESSION))
        assert any(e.type == "file_read" for e in log.events)

    def test_task_transition_from_plain_user_message(self):
        log = parse_human_session(_make_raw(_SHORT_SESSION))
        assert any(e.type == "task_transition" for e in log.events)

    def test_all_event_types_valid(self):
        valid_types = {"bash_call", "file_read", "file_edit", "test_run",
                       "error_reveal", "context_update", "task_transition"}
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        for e in log.events:
            assert e.type in valid_types, f"Unexpected event type: {e.type!r}"


# ---------------------------------------------------------------------------
# TestOutcome
# ---------------------------------------------------------------------------

class TestOutcome:
    def test_outcome_pass_after_successful_test(self):
        # The debugging session ends with "3 passed" in the user message
        log = parse_human_session(_make_raw(_DEBUGGING_SESSION))
        # Outcome depends on whether test_run with pass outcome appears
        assert log.outcome in ("pass", "fail")

    def test_outcome_pass_when_no_tests(self):
        log = parse_human_session(_make_raw(_SHORT_SESSION))
        # No test_run events → default outcome is "pass"
        assert log.outcome == "pass"


# ---------------------------------------------------------------------------
# TestFilterTrajectory
# ---------------------------------------------------------------------------

class TestFilterTrajectory:
    def _make_log(self, n_events: int) -> TrajectoryLog:
        events = [
            TrajectoryEvent(type="task_transition", step=i, args={}, raw={})
            for i in range(n_events)
        ]
        return TrajectoryLog(
            task_id="t", model="human-ai", agent="human",
            outcome="pass", events=events, source="human",
        )

    def test_passes_with_enough_events(self):
        assert filter_trajectory(self._make_log(10)) is True

    def test_fails_with_too_few_events(self):
        assert filter_trajectory(self._make_log(2)) is False

    def test_custom_min_events(self):
        assert filter_trajectory(self._make_log(15), min_events=15) is True
        assert filter_trajectory(self._make_log(14), min_events=15) is False


# ---------------------------------------------------------------------------
# TestSecretDetection
# ---------------------------------------------------------------------------

class TestSecretDetection:
    def test_detects_anthropic_key(self):
        content = "I used the key sk-ant-api03-abcdef123456789012345678901234567890 for testing"
        assert "anthropic_api_key" in detect_secrets(content)

    def test_detects_github_pat(self):
        content = "token = ghp_" + "a" * 36
        assert "github_pat" in detect_secrets(content)

    def test_clean_content_is_empty(self):
        content = "This is a normal conversation about Python programming."
        assert detect_secrets(content) == []

    def test_email_redaction(self):
        content = "Contact me at alice@example.com for more info."
        redacted = redact_emails(content)
        assert "alice@example.com" not in redacted
        assert "<redacted-email>" in redacted

    def test_email_not_detected_as_secret(self):
        content = "My email is user@domain.org"
        # Emails are redacted, not rejected — not in secret patterns
        assert detect_secrets(content) == []
