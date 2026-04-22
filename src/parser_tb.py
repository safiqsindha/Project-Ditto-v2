"""
Terminal-Bench trajectory parser (Session 2).

Parses raw Terminal-Bench 2.0 trajectory format (Harbor / inspect-ai eval log
samples) into canonical TrajectoryLog / TrajectoryEvent objects for downstream
T-code translation.

Expected raw format: one dict per trajectory sample from an inspect-ai eval log.
Fields used:
  id          (str)  — task identifier
  messages    (list) — chat message sequence (system/user/assistant/tool)
  scores      (dict) — scorer_name → {value: float|str}
  output      (dict) — model output, used to extract model name
  metadata    (dict) — optional, may contain token usage

Event types produced:
  bash_call       — a terminal command executed by the agent
  file_read       — agent read file content (cat / head / grep / etc.)
  file_edit       — agent modified, created, or deleted a file
  test_run        — agent ran a test suite (outcome: pass | fail)
  error_reveal    — error or stack trace appeared in command output
  context_update  — cumulative token count recorded
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Canonical event / trajectory types (shared across all parsers)
# ---------------------------------------------------------------------------

@dataclass
class TrajectoryEvent:
    """
    A single event in a parsed trajectory.

    Analogous to v1's BattleEvent.  Used by T-code and aggregation modules.
    """
    type: str               # one of the event types listed in the module docstring
    step: int               # 0-indexed step within the trajectory
    args: dict[str, Any]    # event-type-specific payload
    raw: dict               # original raw dict (for inspection / debugging)


@dataclass
class TrajectoryLog:
    """
    A parsed trajectory ready for T-code translation.

    Analogous to v1's BattleLog.
    """
    task_id: str
    model: str
    agent: str
    outcome: str                            # "pass" | "fail"
    events: list[TrajectoryEvent] = field(default_factory=list)
    source: str = "tb"


# ---------------------------------------------------------------------------
# Command classification regexes
# ---------------------------------------------------------------------------

_FILE_READ_RE = re.compile(
    r"^\s*(cat|head|tail|less|more|grep|find|ls|tree|wc|file|stat|diff)\b",
    re.IGNORECASE,
)

_FILE_EDIT_RE = re.compile(
    r"(>\s*\S+|\bsed\s+-i\b|\btee\s+\S|\btouch\s+\S|\bmv\s+\S|\bcp\s+\S"
    r"|\brm\s+\S|\bpatch\s+|\bwrite_file\b|\bcreate_file\b)",
    re.IGNORECASE,
)

_TEST_RUN_RE = re.compile(
    r"(pytest|python\s+-m\s+pytest|python\s+-m\s+unittest|nosetests"
    r"|npm\s+(run\s+)?test|yarn\s+test|make\s+test|go\s+test|cargo\s+test"
    r"|mvn\s+test|gradle\s+test|bundle\s+exec\s+rspec)",
    re.IGNORECASE,
)

_ERROR_RE = re.compile(
    r"(Traceback \(most recent call last\)"
    r"|^\s*\w+Error:"
    r"|^\s*\w+Exception:"
    r"|\bFAILED\b"
    r"|\bAssertionError\b"
    r"|\bSyntaxError\b"
    r"|\bTypeError\b"
    r"|\bValueError\b"
    r"|\bKeyError\b"
    r"|\bAttributeError\b"
    r"|\bImportError\b"
    r"|\bModuleNotFoundError\b"
    r"|\bRuntimeError\b"
    r"|\bIndexError\b"
    r"|\bNameError\b)",
    re.IGNORECASE | re.MULTILINE,
)

_ERROR_CLASS_RE = re.compile(r"\b(\w+(?:Error|Exception))\b")
_TEST_PASS_RE = re.compile(r"(\d+\s+passed|\bOK\b|\ball\s+tests?\s+pass)", re.IGNORECASE)
_TEST_FAIL_RE = re.compile(r"(\d+\s+failed|\bFAILED\b|\bERROR\b)", re.IGNORECASE)
_TEST_COUNT_RE = re.compile(r"(\d+)\s+(?:passed|failed|tests?)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_nested(d: dict, *keys: str, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
        if d is None:
            return default
    return d


def _extract_tool_args(tool_call: dict) -> dict[str, Any]:
    fn = tool_call.get("function", tool_call)
    args = fn.get("arguments") or fn.get("args") or {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (json.JSONDecodeError, ValueError):
            args = {"raw": args}
    return args if isinstance(args, dict) else {"raw": args}


def _extract_command(args: dict) -> str:
    for key in ("cmd", "command", "input", "bash_command", "code"):
        if key in args:
            return str(args[key]).strip()
    for v in args.values():
        if isinstance(v, str):
            return v.strip()
    return ""


def _classify_command(cmd: str) -> str:
    if _TEST_RUN_RE.search(cmd):
        return "test_run"
    if _FILE_EDIT_RE.search(cmd):
        return "file_edit"
    if _FILE_READ_RE.match(cmd):
        return "file_read"
    return "bash_call"


def _extract_file_path(cmd: str) -> str:
    parts = cmd.strip().split()
    for part in reversed(parts[1:]):
        if "/" in part or re.search(
            r"\.(py|js|ts|go|rs|java|c|cpp|h|sh|txt|json|yaml|yml|md|toml|cfg|ini)$",
            part,
        ):
            return part.lstrip("-")
    return parts[-1] if len(parts) > 1 else ""


def _detect_test_framework(cmd: str) -> str:
    cmd_lower = cmd.lower()
    if "pytest" in cmd_lower:
        return "pytest"
    if "unittest" in cmd_lower:
        return "unittest"
    if "jest" in cmd_lower or "npm" in cmd_lower or "yarn" in cmd_lower:
        return "jest"
    if "go test" in cmd_lower:
        return "go"
    if "cargo test" in cmd_lower:
        return "cargo"
    if "rspec" in cmd_lower:
        return "rspec"
    if "mvn" in cmd_lower or "gradle" in cmd_lower:
        return "junit"
    return "unknown"


def _extract_test_outcome(output: str) -> str:
    if _TEST_FAIL_RE.search(output):
        return "fail"
    if _TEST_PASS_RE.search(output):
        return "pass"
    return "fail"


def _count_tests(output: str) -> int | None:
    m = _TEST_COUNT_RE.search(output)
    return int(m.group(1)) if m else None


def _extract_error_class(content: str) -> str:
    m = _ERROR_CLASS_RE.search(content)
    return m.group(1) if m else "RuntimeError"


def _extract_outcome(scores: dict) -> str:
    if not scores:
        return "fail"
    for val in scores.values():
        if isinstance(val, dict):
            v = val.get("value", val.get("score", val.get("answer", 0)))
        else:
            v = val
        try:
            if float(v) >= 1.0:
                return "pass"
        except (TypeError, ValueError):
            if str(v).strip().lower() in ("correct", "pass", "true", "yes", "1", "c"):
                return "pass"
    return "fail"


def _content_as_str(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text", block.get("content", str(block))))
        return " ".join(parts)
    return str(content) if content is not None else ""


def _extract_usage(raw: dict) -> dict | None:
    for path in [
        ("metadata", "usage"),
        ("metadata", "token_usage"),
        ("output", "usage"),
        ("stats", "model_usage"),
    ]:
        v = _get_nested(raw, *path)
        if v and isinstance(v, dict):
            return v
    return None


# ---------------------------------------------------------------------------
# Message sequence parser
# ---------------------------------------------------------------------------

def _parse_messages(messages: list[dict]) -> list[TrajectoryEvent]:
    """Convert an inspect-ai message sequence to a list of TrajectoryEvents."""
    events: list[TrajectoryEvent] = []
    step = 0
    tool_call_event_idx: dict[str, int] = {}

    for msg in messages:
        role = msg.get("role", "")

        if role == "assistant":
            for tc in (msg.get("tool_calls") or []):
                call_id = tc.get("id", f"call_{step}")
                args = _extract_tool_args(tc)
                cmd = _extract_command(args)
                evt_type = _classify_command(cmd)

                if evt_type == "test_run":
                    evt = TrajectoryEvent(
                        type="test_run",
                        step=step,
                        args={
                            "command": cmd,
                            "framework": _detect_test_framework(cmd),
                            "outcome": None,
                            "tests_run": None,
                        },
                        raw=tc,
                    )
                elif evt_type == "file_read":
                    evt = TrajectoryEvent(
                        type="file_read",
                        step=step,
                        args={"command": cmd, "path": _extract_file_path(cmd)},
                        raw=tc,
                    )
                elif evt_type == "file_edit":
                    evt = TrajectoryEvent(
                        type="file_edit",
                        step=step,
                        args={
                            "command": cmd,
                            "path": _extract_file_path(cmd),
                            "operation": "modify",
                        },
                        raw=tc,
                    )
                else:
                    evt = TrajectoryEvent(
                        type="bash_call",
                        step=step,
                        args={"command": cmd},
                        raw=tc,
                    )

                tool_call_event_idx[call_id] = len(events)
                events.append(evt)
                step += 1

        elif role == "tool":
            call_id = msg.get("tool_call_id", "")
            output = _content_as_str(msg.get("content", ""))

            # Retroactively fill in test outcome
            if call_id in tool_call_event_idx:
                prior = events[tool_call_event_idx[call_id]]
                if prior.type == "test_run":
                    prior.args["outcome"] = _extract_test_outcome(output)
                    prior.args["tests_run"] = _count_tests(output)

            # Emit error_reveal if output contains error patterns
            if _ERROR_RE.search(output):
                events.append(TrajectoryEvent(
                    type="error_reveal",
                    step=step,
                    args={
                        "error_type": _extract_error_class(output),
                        "message": output[:300],
                    },
                    raw=msg,
                ))
                step += 1

    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_tb_trajectory(raw: dict) -> TrajectoryLog:
    """
    Parse a raw Terminal-Bench inspect-ai sample dict into a TrajectoryLog.

    Parameters
    ----------
    raw : dict
        One sample from an inspect-ai eval log.  Required: ``messages`` (list).
        Optional: ``id`` / ``task_id``, ``scores``, ``output``, ``metadata``.

    Returns
    -------
    TrajectoryLog

    Raises
    ------
    ValueError
        If ``messages`` is missing or not a list.
    """
    task_id = str(
        raw.get("id") or raw.get("task_id") or raw.get("sample_id") or "unknown"
    )

    messages = raw.get("messages", [])
    if not isinstance(messages, list):
        raise ValueError(
            f"'messages' must be a list, got {type(messages).__name__} "
            f"in sample {task_id!r}"
        )

    model = (
        _get_nested(raw, "output", "model")
        or raw.get("model")
        or _get_nested(raw, "eval", "model")
        or "unknown"
    )
    agent = raw.get("agent", "inspect-ai")
    outcome = _extract_outcome(raw.get("scores") or {})
    events = _parse_messages(messages)

    usage = _extract_usage(raw)
    if usage:
        total = int(
            usage.get("input_tokens")
            or usage.get("total_tokens")
            or usage.get("prompt_tokens")
            or 0
        )
        if total:
            events.append(TrajectoryEvent(
                type="context_update",
                step=len(events),
                args={"tokens_used": total, "tokens_max": 200_000},
                raw=usage,
            ))

    return TrajectoryLog(
        task_id=task_id,
        model=model,
        agent=agent,
        outcome=outcome,
        events=events,
        source="tb",
    )


def filter_trajectory(log: TrajectoryLog, min_events: int = 15) -> bool:
    """Return True if the trajectory meets inclusion criteria.

    Criteria (spec §3.4):
    - At least ``min_events`` events after parsing
    - Outcome is "pass" or "fail" (excludes timeouts, errors, early exits)
    """
    if len(log.events) < min_events:
        return False
    if log.outcome not in ("pass", "fail"):
        return False
    return True
