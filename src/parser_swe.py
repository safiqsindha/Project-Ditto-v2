"""
SWE-bench Verified trajectory parser (Session 3).

Parses raw SWE-agent / mini-SWE-agent trajectory format into canonical
TrajectoryLog / TrajectoryEvent objects for downstream T-code translation.

Uses the same TrajectoryEvent type vocabulary as parser_tb — critical for
T-code uniformity across sources (spec §3.4).

Supported raw formats
---------------------
Format A — SWE-agent action/observation steps (most common):
    {
      "instance_id": "owner__repo-number",
      "model_name_or_path": "gpt-4-...",
      "traj": [
        {"action": "bash cmd", "observation": "output",
         "thought": "...", "response": "...", "state": "..."},
        ...
      ],
      "info": {"exit_status": "submitted"|"early_exit", ...}
    }

Format B — Chat-style messages (newer SWE-agent / mini-SWE-agent):
    {
      "instance_id": "...",
      "model_name_or_path": "...",
      "messages": [
        {"role": "user"|"assistant"|"tool", "content": "...",
         "tool_calls": [...]}
      ],
      "info": {"exit_status": "...", ...}
    }

SWE-bench-specific idiosyncrasies handled:
  - File-read bursts (reading 10+ files to understand a codebase)
  - Long error stacks (message truncated to first 300 chars)
  - Git diff / apply events treated as file_edit
  - Longer-horizon trajectories (100+ events before aggregation)
"""

from __future__ import annotations

import re
from typing import Any

from src.parser_tb import (
    TrajectoryEvent,
    TrajectoryLog,
    _classify_command,
    _detect_test_framework,
    _ERROR_RE,
    _extract_error_class,
    _extract_file_path,
    _extract_test_outcome,
    _count_tests,
)


# ---------------------------------------------------------------------------
# SWE-bench-specific command patterns
# ---------------------------------------------------------------------------

_GIT_PATCH_RE = re.compile(r"^\s*git\s+(diff|apply|am|patch)\b", re.IGNORECASE)
_EDITOR_CMD_RE = re.compile(
    r"^\s*(edit|open|create|insert|replace|delete_lines?)\b", re.IGNORECASE
)

_PASS_STATUS = frozenset({"submitted", "exit_cost", "exit_format"})
_FAIL_STATUS = frozenset({"early_exit", "exit_context", "autosubmission_failed"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _classify_swe_command(cmd: str) -> str:
    """Classify a command string, with SWE-bench-specific overrides."""
    if _GIT_PATCH_RE.match(cmd):
        return "file_edit"
    if _EDITOR_CMD_RE.match(cmd):
        return "file_edit"
    return _classify_command(cmd)


def _extract_swe_outcome(info: dict) -> str:
    """Determine pass/fail from SWE-agent info dict."""
    status = str(info.get("exit_status", "")).lower()
    if status in _PASS_STATUS:
        return "pass"
    if status in _FAIL_STATUS:
        return "fail"
    if info.get("submission") or info.get("model_patch"):
        return "pass"
    return "fail"


# ---------------------------------------------------------------------------
# Format A parser: action/observation step list
# ---------------------------------------------------------------------------

def _parse_action_obs_steps(steps: list[dict]) -> list[TrajectoryEvent]:
    """Parse SWE-agent-style action/observation step list into TrajectoryEvents."""
    events: list[TrajectoryEvent] = []
    step = 0

    for entry in steps:
        action = str(entry.get("action", "")).strip()
        observation = str(entry.get("observation", "")).strip()

        if not action:
            continue

        evt_type = _classify_swe_command(action)

        if evt_type == "test_run":
            evt = TrajectoryEvent(
                type="test_run",
                step=step,
                args={
                    "command": action,
                    "framework": _detect_test_framework(action),
                    "outcome": _extract_test_outcome(observation),
                    "tests_run": _count_tests(observation),
                },
                raw=entry,
            )
        elif evt_type == "file_read":
            evt = TrajectoryEvent(
                type="file_read",
                step=step,
                args={"command": action, "path": _extract_file_path(action)},
                raw=entry,
            )
        elif evt_type == "file_edit":
            evt = TrajectoryEvent(
                type="file_edit",
                step=step,
                args={
                    "command": action,
                    "path": _extract_file_path(action),
                    "operation": "modify",
                },
                raw=entry,
            )
        else:
            evt = TrajectoryEvent(
                type="bash_call",
                step=step,
                args={"command": action},
                raw=entry,
            )

        events.append(evt)
        step += 1

        if observation and _ERROR_RE.search(observation):
            events.append(TrajectoryEvent(
                type="error_reveal",
                step=step,
                args={
                    "error_type": _extract_error_class(observation),
                    "message": observation[:300],
                },
                raw={"observation": observation[:300]},
            ))
            step += 1

    return events


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_swe_trajectory(raw: dict) -> TrajectoryLog:
    """
    Parse a raw SWE-agent trajectory dict into a TrajectoryLog.

    Supports both Format A (action/observation steps) and Format B
    (chat-style messages).

    Parameters
    ----------
    raw : dict
        One SWE-agent trajectory record.  Required: ``instance_id`` and
        either ``traj`` (Format A) or ``messages`` (Format B).

    Returns
    -------
    TrajectoryLog with ``source="swe"``

    Raises
    ------
    ValueError
        If neither ``traj`` nor ``messages`` is found in ``raw``.
    """
    task_id = str(
        raw.get("instance_id")
        or raw.get("id")
        or raw.get("task_id")
        or "unknown"
    )
    model = str(
        raw.get("model_name_or_path")
        or raw.get("model")
        or "unknown"
    )
    agent = raw.get("agent", "swe-agent")
    info = raw.get("info") or {}
    outcome = _extract_swe_outcome(info)

    if "traj" in raw and isinstance(raw["traj"], list):
        events = _parse_action_obs_steps(raw["traj"])
    elif "trajectory" in raw and isinstance(raw["trajectory"], list):
        steps = raw["trajectory"]
        if steps and isinstance(steps[0], dict) and "action" in steps[0]:
            events = _parse_action_obs_steps(steps)
        else:
            from src.parser_tb import _parse_messages as _tb_parse_messages
            events = _tb_parse_messages(steps)
    elif "messages" in raw and isinstance(raw["messages"], list):
        from src.parser_tb import _parse_messages as _tb_parse_messages
        events = _tb_parse_messages(raw["messages"])
    else:
        raise ValueError(
            f"Cannot find trajectory data in SWE sample {task_id!r}. "
            "Expected 'traj', 'trajectory', or 'messages' key."
        )

    # Append context_update if token stats are available
    model_stats = info.get("model_stats") or {}
    tokens_sent = model_stats.get("tokens_sent", 0) or 0
    tokens_received = model_stats.get("tokens_received", 0) or 0
    total_tokens = int(tokens_sent) + int(tokens_received)
    if total_tokens:
        events.append(TrajectoryEvent(
            type="context_update",
            step=len(events),
            args={"tokens_used": total_tokens, "tokens_max": 200_000},
            raw=model_stats,
        ))

    return TrajectoryLog(
        task_id=task_id,
        model=model,
        agent=agent,
        outcome=outcome,
        events=events,
        source="swe",
    )


def filter_trajectory(log: TrajectoryLog, min_events: int = 15) -> bool:
    """Return True if the SWE-bench trajectory meets inclusion criteria."""
    if len(log.events) < min_events:
        return False
    if log.outcome not in ("pass", "fail"):
        return False
    return True
