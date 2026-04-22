"""
Source-specific event aggregation rules (spec §3.4).

Reduces raw parsed events into a more compact sequence before T-code translation.
Aggregation rules are committed as part of T-code and frozen at the same tag
(T-code-v1.0-frozen) — see CLAUDE.md key invariants.

Three aggregation functions (all PURE — deterministic, no external state):

  aggregate_tb_events  — Terminal-Bench
    · Drop lone no-op commands (bare ls/pwd without downstream use)
    · Collapse consecutive identical bash_call commands into one
    · Collapse consecutive file_read on the same path into one

  aggregate_swe_events — SWE-bench
    · Collapse file-read bursts (≥3 consecutive file reads → single burst event)
    · Compress retry loops (same bash_call repeated N times → one with retry_count)
    · Truncate error_reveal message to first 120 chars

  aggregate_human_events — Human-AI sessions
    · Collapse consecutive identical task_transition events into one
    · Merge consecutive file_edit events on the same path
    · Pass all other events through unchanged (lenient — human turns already coarse)

Each function returns (aggregated_events, aggregation_log) where aggregation_log
is a list of human-readable strings describing each compression applied.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from src.parser_tb import TrajectoryEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _copy_event(evt: TrajectoryEvent, **overrides) -> TrajectoryEvent:
    """Return a new TrajectoryEvent identical to evt except for overrides."""
    d = dataclasses.asdict(evt)
    # dataclasses.asdict recursively converts — we want shallow copy of args
    result = TrajectoryEvent(
        type=overrides.get("type", evt.type),
        step=overrides.get("step", evt.step),
        args=overrides.get("args", dict(evt.args)),
        raw=overrides.get("raw", evt.raw),
    )
    return result


_NOOP_COMMANDS = frozenset({
    "ls", "ls -la", "ls -l", "ls -a", "ls -lh",
    "pwd", "whoami", "echo", "date", "hostname",
    "true", ":",
})


def _is_noop(evt: TrajectoryEvent) -> bool:
    """Return True if this is a trivial no-op bash call."""
    if evt.type != "bash_call":
        return False
    cmd = evt.args.get("command", "").strip()
    return cmd in _NOOP_COMMANDS


# ---------------------------------------------------------------------------
# Terminal-Bench aggregation
# ---------------------------------------------------------------------------

def aggregate_tb_events(
    events: list[TrajectoryEvent],
) -> tuple[list[TrajectoryEvent], list[str]]:
    """
    Aggregate Terminal-Bench trajectory events.

    Rules (applied in order):
    1. Drop lone no-op commands (bare ls / pwd / echo without follow-up)
    2. Collapse consecutive identical bash_call commands into one
    3. Collapse consecutive file_read on the same path into one

    Returns
    -------
    (aggregated_events, aggregation_log)
    """
    log: list[str] = []
    result: list[TrajectoryEvent] = []

    i = 0
    while i < len(events):
        evt = events[i]

        # Rule 1: skip lone no-ops (unless followed by file_read / file_edit)
        if _is_noop(evt):
            next_is_useful = (
                i + 1 < len(events)
                and events[i + 1].type in ("file_read", "file_edit", "bash_call")
                and not _is_noop(events[i + 1])
            )
            if not next_is_useful:
                log.append(f"[tb] step {evt.step}: dropped no-op '{evt.args.get('command', '')}'")
                i += 1
                continue

        # Rule 2: collapse consecutive identical bash_calls
        if evt.type == "bash_call" and result and result[-1].type == "bash_call":
            prev_cmd = result[-1].args.get("command", "").strip()
            curr_cmd = evt.args.get("command", "").strip()
            if prev_cmd == curr_cmd:
                log.append(f"[tb] step {evt.step}: collapsed duplicate bash_call '{curr_cmd}'")
                i += 1
                continue

        # Rule 3: collapse consecutive file_reads on the same path
        if evt.type == "file_read" and result and result[-1].type == "file_read":
            prev_path = result[-1].args.get("path", "")
            curr_path = evt.args.get("path", "")
            if prev_path and curr_path and prev_path == curr_path:
                log.append(f"[tb] step {evt.step}: collapsed duplicate file_read '{curr_path}'")
                i += 1
                continue

        result.append(evt)
        i += 1

    return result, log


# ---------------------------------------------------------------------------
# SWE-bench aggregation
# ---------------------------------------------------------------------------

_SWE_BURST_THRESHOLD = 3   # number of consecutive file_reads to trigger burst collapse


def aggregate_swe_events(
    events: list[TrajectoryEvent],
) -> tuple[list[TrajectoryEvent], list[str]]:
    """
    Aggregate SWE-bench trajectory events.

    Rules (applied in order):
    1. Collapse file-read bursts (≥3 consecutive file_read → single burst event)
    2. Compress retry loops (same bash_call repeated → one event with retry_count)
    3. Truncate error_reveal message to first 120 chars

    Returns
    -------
    (aggregated_events, aggregation_log)
    """
    log: list[str] = []
    result: list[TrajectoryEvent] = []

    i = 0
    while i < len(events):
        evt = events[i]

        # Rule 1: collapse file-read bursts
        if evt.type == "file_read":
            burst: list[TrajectoryEvent] = [evt]
            j = i + 1
            while j < len(events) and events[j].type == "file_read":
                burst.append(events[j])
                j += 1

            if len(burst) >= _SWE_BURST_THRESHOLD:
                paths = [e.args.get("path", "") for e in burst]
                collapsed_args = {
                    "command": "read_burst",
                    "path": paths[0],
                    "additional_paths": paths[1:],
                    "burst_size": len(burst),
                }
                collapsed = TrajectoryEvent(
                    type="file_read",
                    step=burst[0].step,
                    args=collapsed_args,
                    raw={"burst_size": len(burst)},
                )
                result.append(collapsed)
                log.append(
                    f"[swe] step {evt.step}: collapsed {len(burst)}-file read burst "
                    f"into one event"
                )
                i = j
                continue

        # Rule 2: compress retry loops
        if evt.type == "bash_call" and result and result[-1].type == "bash_call":
            prev_cmd = result[-1].args.get("command", "").strip()
            curr_cmd = evt.args.get("command", "").strip()
            if prev_cmd == curr_cmd:
                prev = result[-1]
                retry_count = prev.args.get("retry_count", 1) + 1
                updated_args = dict(prev.args)
                updated_args["retry_count"] = retry_count
                result[-1] = TrajectoryEvent(
                    type=prev.type, step=prev.step, args=updated_args, raw=prev.raw
                )
                log.append(
                    f"[swe] step {evt.step}: collapsed retry of '{curr_cmd}' "
                    f"(retry_count={retry_count})"
                )
                i += 1
                continue

        # Rule 3: truncate error messages
        if evt.type == "error_reveal":
            msg = evt.args.get("message", "")
            if len(msg) > 120:
                short_msg = msg[:120]
                new_args = dict(evt.args)
                new_args["message"] = short_msg
                evt = TrajectoryEvent(type=evt.type, step=evt.step, args=new_args, raw=evt.raw)
                log.append(f"[swe] step {evt.step}: truncated error_reveal message")

        result.append(evt)
        i += 1

    return result, log


# ---------------------------------------------------------------------------
# Human-AI session aggregation
# ---------------------------------------------------------------------------

def aggregate_human_events(
    events: list[TrajectoryEvent],
) -> tuple[list[TrajectoryEvent], list[str]]:
    """
    Aggregate human-AI collaborative session events.

    Rules (lenient — human turns already coarse):
    1. Collapse consecutive identical task_transition events into one
    2. Merge consecutive file_edit events on the same path into one
    3. All other events pass through unchanged

    Returns
    -------
    (aggregated_events, aggregation_log)
    """
    log: list[str] = []
    result: list[TrajectoryEvent] = []

    for evt in events:
        # Rule 1: collapse consecutive identical task_transitions
        if (evt.type == "task_transition"
                and result
                and result[-1].type == "task_transition"):
            prev_reason = result[-1].args.get("reason", "")
            curr_reason = evt.args.get("reason", "")
            if prev_reason == curr_reason:
                log.append(
                    f"[human] step {evt.step}: collapsed duplicate task_transition"
                )
                continue

        # Rule 2: merge consecutive file_edits on the same path
        if (evt.type == "file_edit"
                and result
                and result[-1].type == "file_edit"):
            prev_path = result[-1].args.get("path", "")
            curr_path = evt.args.get("path", "")
            if prev_path and curr_path and prev_path == curr_path:
                log.append(
                    f"[human] step {evt.step}: merged file_edit on same path '{curr_path}'"
                )
                continue

        result.append(evt)

    return result, log


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_AGGREGATORS = {
    "tb":    aggregate_tb_events,
    "swe":   aggregate_swe_events,
    "human": aggregate_human_events,
}


def aggregate_events(
    events: list[TrajectoryEvent],
    source: str,
) -> tuple[list[TrajectoryEvent], list[str]]:
    """Dispatch to the appropriate source-specific aggregation function."""
    fn = _AGGREGATORS.get(source)
    if fn is None:
        raise ValueError(
            f"Unknown source {source!r}. Choose from: {sorted(_AGGREGATORS)}"
        )
    return fn(events)
