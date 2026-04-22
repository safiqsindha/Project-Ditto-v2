"""
Human-AI collaborative session parser (Session 4).

Parses SpecStory Markdown session files committed to public GitHub repositories
into canonical TrajectoryLog / TrajectoryEvent objects.

SpecStory (https://specstory.com) auto-saves AI conversations from Cursor,
VS Code + Copilot, Claude Code, Codex CLI, Gemini CLI, and other AI coding tools
to `.specstory/history/` inside the developer's repository.  Developers commit
these files as part of their normal workflow, making them publicly accessible.

File naming convention: `YYYY-MM-DD_session-<hash>.md`

Markdown format:
    ## User
    [developer message with optional code blocks and error output]

    ## Assistant
    [AI response with code blocks, tool call descriptions, file references]

    ## Agent
    [tool execution output — some tools emit this as a distinct role]

These are human-AI COLLABORATIVE sessions, not solo human debugging.  The human
drives intent and makes decisions; the AI generates code in response.  The event
vocabulary maps collaborative turns to the same types used by the agent parsers
so that T-code (Session 6) can process all three sources uniformly.

Turn → event mapping (see _classify_user_turn / _classify_assistant_turn):
  User turn with error/traceback  → error_reveal
  User turn with code block       → file_read   (reviewing pasted code)
  User turn with new request      → task_transition
  Assistant turn with code block  → file_edit   (agent applies generated code)
  Assistant turn with command     → bash_call
  Assistant turn mentioning test  → test_run
  Every turn (implicit)           → context_update tracked via turn count
"""

from __future__ import annotations

import re
from typing import Any

from src.parser_tb import TrajectoryEvent, TrajectoryLog


# ---------------------------------------------------------------------------
# Secret / PII detection (used by acquire_human.py; kept here for testability)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'sk-ant-[a-zA-Z0-9\-_]{20,}'),       "anthropic_api_key"),
    (re.compile(r'sk-[a-zA-Z0-9]{32,}'),               "openai_api_key"),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'),               "github_pat"),
    (re.compile(r'ghs_[a-zA-Z0-9]{36}'),               "github_token"),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{22,}'),      "github_fine_grained_pat"),
    (re.compile(r'AKIA[A-Z0-9]{16}'),                  "aws_access_key"),
    (re.compile(r'Bearer\s+[a-zA-Z0-9._\-]{30,}'),     "bearer_token"),
    (re.compile(
        r'(?:password|passwd|secret|token)\s*[=:]\s*["\']?[^\s"\'<]{8,}',
        re.IGNORECASE,
    ),                                                  "credential_assignment"),
    (re.compile(
        r'(?:api[_\-]?key|apikey)\s*[=:]\s*["\']?[a-zA-Z0-9\-_]{20,}',
        re.IGNORECASE,
    ),                                                  "api_key_assignment"),
]

_EMAIL_RE = re.compile(
    r'\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b'
)


def detect_secrets(content: str) -> list[str]:
    """Return list of detected secret type names (empty means clean)."""
    return [name for pattern, name in _SECRET_PATTERNS if pattern.search(content)]


def redact_emails(content: str) -> str:
    """Replace email addresses with <redacted-email>."""
    return _EMAIL_RE.sub("<redacted-email>", content)


# ---------------------------------------------------------------------------
# Turn-splitting regex
# ---------------------------------------------------------------------------

# Matches SpecStory role headers: ## User, ## Assistant, ## Agent, ## Human, ## AI
_TURN_HEADER_RE = re.compile(
    r"^##\s+(User|Assistant|Agent|Human|AI|Copilot|System)\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Content-classification helpers
# ---------------------------------------------------------------------------

_ERROR_RE = re.compile(
    r"(Traceback \(most recent call last\)"
    r"|\b\w+Error:"
    r"|\b\w+Exception:"
    r"|\bFAILED\b"
    r"|\bAssertionError\b"
    r"|\bSyntaxError\b"
    r"|\bTypeError\b"
    r"|\bValueError\b"
    r"|\berror:\s)",
    re.IGNORECASE | re.MULTILINE,
)

_ERROR_CLASS_RE = re.compile(r"\b(\w+(?:Error|Exception))\b")

_CODE_BLOCK_RE = re.compile(r"```[\w]*\n(.*?)```", re.DOTALL)

_BASH_BLOCK_RE = re.compile(r"```(?:bash|sh|shell|zsh)\n(.*?)```", re.DOTALL)

_TEST_CMD_RE = re.compile(
    r"(pytest|python\s+-m\s+pytest|python\s+-m\s+unittest|npm\s+test|go\s+test|cargo\s+test)",
    re.IGNORECASE,
)

_FILE_REF_RE = re.compile(
    r"`([^`]+\.[a-zA-Z]{1,6})`|\"([^\"]+\.[a-zA-Z]{1,6})\"",
)

_TEST_PASS_RE = re.compile(r"(\d+\s+passed|\bOK\b|\bpassing\b|\bAll tests pass)", re.IGNORECASE)
_TEST_FAIL_RE = re.compile(r"(\d+\s+failed|\bFAILED\b|\bfailure)", re.IGNORECASE)


def _extract_error_class(content: str) -> str:
    m = _ERROR_CLASS_RE.search(content)
    return m.group(1) if m else "RuntimeError"


def _extract_file_from_code_ref(content: str) -> str:
    m = _FILE_REF_RE.search(content)
    if m:
        return m.group(1) or m.group(2) or ""
    return ""


def _extract_bash_command(content: str) -> str:
    """Extract the first bash command from content (from bash code blocks or inline)."""
    m = _BASH_BLOCK_RE.search(content)
    if m:
        return m.group(1).strip().split("\n")[0]
    # Fallback: look for backtick-fenced inline code that looks like a command
    m2 = re.search(r"`([a-z][a-z0-9\-_]+\s+[^`]{0,80})`", content)
    if m2:
        return m2.group(1)
    return ""


def _detect_test_framework(cmd: str) -> str:
    cmd_lower = cmd.lower()
    if "pytest" in cmd_lower:
        return "pytest"
    if "unittest" in cmd_lower:
        return "unittest"
    if "npm test" in cmd_lower or "jest" in cmd_lower:
        return "jest"
    if "go test" in cmd_lower:
        return "go"
    if "cargo test" in cmd_lower:
        return "cargo"
    return "unknown"


# ---------------------------------------------------------------------------
# Turn classifiers
# ---------------------------------------------------------------------------

def _classify_user_turn(content: str, step: int) -> TrajectoryEvent | None:
    """Classify a user turn into a TrajectoryEvent."""
    if not content.strip():
        return None

    # Error / traceback in user message → error_reveal
    if _ERROR_RE.search(content):
        return TrajectoryEvent(
            type="error_reveal",
            step=step,
            args={
                "error_type": _extract_error_class(content),
                "message": content[:300],
                "source": "user_paste",
            },
            raw={"role": "user", "content": content[:500]},
        )

    # Code block in user message → file_read (reviewing/sharing code)
    if _CODE_BLOCK_RE.search(content):
        file_ref = _extract_file_from_code_ref(content)
        return TrajectoryEvent(
            type="file_read",
            step=step,
            args={
                "command": "paste_code",
                "path": file_ref,
                "source": "user_paste",
            },
            raw={"role": "user", "content": content[:500]},
        )

    # Default: new direction / intent from the developer → task_transition
    # Truncate the content to a short summary
    summary = content.strip().split("\n")[0][:80]
    return TrajectoryEvent(
        type="task_transition",
        step=step,
        args={
            "from_phase": "unknown",
            "to_phase": "unknown",
            "reason": summary,
            "source": "user_request",
        },
        raw={"role": "user", "content": content[:500]},
    )


def _classify_assistant_turn(content: str, step: int) -> TrajectoryEvent | None:
    """Classify an assistant turn into a TrajectoryEvent."""
    if not content.strip():
        return None

    # Bash code block → check for test commands first
    bash_cmd = _extract_bash_command(content)
    if bash_cmd and _TEST_CMD_RE.search(bash_cmd):
        # Determine outcome from surrounding context (look for pass/fail in content)
        outcome = "fail"
        if _TEST_PASS_RE.search(content):
            outcome = "pass"
        elif _TEST_FAIL_RE.search(content):
            outcome = "fail"
        return TrajectoryEvent(
            type="test_run",
            step=step,
            args={
                "command": bash_cmd,
                "framework": _detect_test_framework(bash_cmd),
                "outcome": outcome,
                "tests_run": None,
                "source": "assistant_command",
            },
            raw={"role": "assistant", "content": content[:500]},
        )

    if bash_cmd:
        return TrajectoryEvent(
            type="bash_call",
            step=step,
            args={"command": bash_cmd, "source": "assistant_command"},
            raw={"role": "assistant", "content": content[:500]},
        )

    # Non-bash code block → file_edit (assistant generated code the developer applies)
    if _CODE_BLOCK_RE.search(content):
        file_ref = _extract_file_from_code_ref(content)
        return TrajectoryEvent(
            type="file_edit",
            step=step,
            args={
                "command": "apply_generated_code",
                "path": file_ref,
                "operation": "modify",
                "source": "assistant_codegen",
            },
            raw={"role": "assistant", "content": content[:500]},
        )

    # Plain text response — treat as bash_call (conceptual step)
    summary = content.strip().split("\n")[0][:80]
    return TrajectoryEvent(
        type="bash_call",
        step=step,
        args={"command": f"explain: {summary}", "source": "assistant_text"},
        raw={"role": "assistant", "content": content[:500]},
    )


# ---------------------------------------------------------------------------
# Turn splitter
# ---------------------------------------------------------------------------

def _parse_turns(content: str) -> list[dict[str, str]]:
    """Split SpecStory Markdown into a list of {role, content} dicts."""
    turns = []
    headers = list(_TURN_HEADER_RE.finditer(content))
    if not headers:
        return turns

    for i, match in enumerate(headers):
        role = match.group(1).lower()
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        turn_content = content[start:end].strip()
        turns.append({"role": role, "content": turn_content})

    return turns


def _determine_outcome(events: list[TrajectoryEvent]) -> str:
    """Determine overall session outcome from the last test run event, or 'pass' if none."""
    for evt in reversed(events):
        if evt.type == "test_run":
            return evt.args.get("outcome", "fail") or "fail"
    return "pass"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_human_session(raw: dict) -> TrajectoryLog:
    """
    Parse a SpecStory Markdown session file dict into a TrajectoryLog.

    Parameters
    ----------
    raw : dict with the following keys:
        session_id : str — filename stem (e.g. "2025-09-15_session-abc123")
        content    : str — full Markdown content of the SpecStory file
        repo       : str — "owner/repo" on GitHub (optional, for provenance)
        url        : str — GitHub file URL (optional)

    Returns
    -------
    TrajectoryLog with ``source="human"``

    Raises
    ------
    ValueError
        If ``content`` is missing or empty.
    """
    session_id = str(raw.get("session_id") or raw.get("id") or "unknown")
    content = raw.get("content", "")
    if not content:
        raise ValueError(f"Empty content in human session {session_id!r}")

    turns = _parse_turns(content)
    events: list[TrajectoryEvent] = []
    step = 0

    for turn in turns:
        role = turn["role"]
        if role in ("user", "human"):
            evt = _classify_user_turn(turn["content"], step)
        elif role in ("assistant", "ai", "copilot", "agent"):
            evt = _classify_assistant_turn(turn["content"], step)
        else:
            evt = None  # system turns ignored

        if evt is not None:
            events.append(evt)
            step += 1

    outcome = _determine_outcome(events)

    return TrajectoryLog(
        task_id=session_id,
        model="human-ai",
        agent="human",
        outcome=outcome,
        events=events,
        source="human",
    )


def filter_trajectory(log: TrajectoryLog, min_events: int = 5) -> bool:
    """Return True if the human-AI session meets minimum inclusion criteria.

    Minimum is lower (5) than agent sources because human dialog sessions
    are inherently higher-level than step-by-step agent trajectories.
    """
    return len(log.events) >= min_events
