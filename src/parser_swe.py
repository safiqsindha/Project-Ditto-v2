"""
SWE-bench Verified trajectory parser (Session 3).

Parses raw SWE-agent / mini-SWE-agent trajectory format into canonical
TrajectoryLog / TrajectoryEvent objects for downstream T-code translation.

Uses the same TrajectoryEvent type vocabulary as parser_tb.py — critical for
T-code uniformity across sources (spec §3.4).

SWE-bench-specific idiosyncrasies handled:
  - File-read bursts (reading 10+ files to understand a codebase)
  - Long error stacks (truncated to first line by aggregation layer)
  - Git diff events
  - Longer-horizon trajectories (100+ events before aggregation)

Implemented in Session 3.
"""

from __future__ import annotations

from src.parser_tb import TrajectoryEvent, TrajectoryLog


def parse_swe_trajectory(raw: dict) -> TrajectoryLog:
    """
    Parse a raw SWE-agent trajectory dict into a TrajectoryLog.

    Parameters
    ----------
    raw : dict from SWE-agent / mini-SWE-agent trajectory JSON

    Returns
    -------
    TrajectoryLog with typed TrajectoryEvent objects using the same
    event type vocabulary as parser_tb.parse_tb_trajectory.

    Raises
    ------
    ValueError if the raw dict is missing required fields.
    """
    raise NotImplementedError("parse_swe_trajectory not yet implemented (Session 3)")


def filter_trajectory(log: TrajectoryLog, min_events: int = 15) -> bool:
    """Return True if the SWE-bench trajectory meets inclusion criteria."""
    if len(log.events) < min_events:
        return False
    if log.outcome not in ("pass", "fail"):
        return False
    return True
