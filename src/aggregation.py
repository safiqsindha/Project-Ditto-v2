"""
Source-specific event aggregation rules (spec §3.4).

Reduces raw parsed events into chains of 20–40 constraints by applying
source-specific compression rules before T-code translation.  Rules are
committed as part of T-code and frozen at the same tag (T-code-v1.0-frozen).

Three aggregation functions:
  aggregate_tb_events  — Terminal-Bench: mostly pass-through, remove no-ops,
                         collapse consecutive identical bash calls.
  aggregate_swe_events — SWE-bench: collapse file-read bursts, truncate error
                         stacks to first line, compress retry loops.
  aggregate_human_events — Human sessions: lenient, events already high-granularity.

Each function is PURE (deterministic, no external state) and returns both the
aggregated event list and a log of what was aggregated for inspection.

Implemented in Session 5.
"""

from __future__ import annotations

from typing import Any

# Type alias for raw trajectory events (pre-T-code)
TrajectoryEvent = Any


def aggregate_tb_events(
    events: list[TrajectoryEvent],
) -> tuple[list[TrajectoryEvent], list[str]]:
    """
    Aggregate Terminal-Bench trajectory events.

    Rules:
    - Filter no-op commands (e.g. bare ls without follow-up use of output)
    - Collapse consecutive identical bash calls into one

    Returns
    -------
    (aggregated_events, aggregation_log)
    """
    raise NotImplementedError("aggregate_tb_events not yet implemented (Session 5)")


def aggregate_swe_events(
    events: list[TrajectoryEvent],
) -> tuple[list[TrajectoryEvent], list[str]]:
    """
    Aggregate SWE-bench trajectory events.

    Rules:
    - Collapse file-read bursts (N consecutive file reads → one InformationState
      with N observable_added entries)
    - Truncate error stacks to first-line only
    - Compress retry loops (same command repeated N times → one event with
      retry_count metadata)

    Returns
    -------
    (aggregated_events, aggregation_log)
    """
    raise NotImplementedError("aggregate_swe_events not yet implemented (Session 5)")


def aggregate_human_events(
    events: list[TrajectoryEvent],
) -> tuple[list[TrajectoryEvent], list[str]]:
    """
    Aggregate human debugging session events.

    Lenient rules — human event descriptions are already higher-granularity
    than agent trajectories.  Minimal compression applied.

    Returns
    -------
    (aggregated_events, aggregation_log)
    """
    raise NotImplementedError("aggregate_human_events not yet implemented (Session 5)")


# Dispatcher
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
        raise ValueError(f"Unknown source {source!r}. Choose from: {list(_AGGREGATORS)}")
    return fn(events)
