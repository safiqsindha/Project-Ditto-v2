"""
Human debugging session parser (Session 4).

Parses public human debugging session data into canonical TrajectoryLog /
TrajectoryEvent objects.

Human session sources (priority order per spec §4):
  1. Public live-coding stream logs with timestamp-aligned terminal/IDE actions
  2. Stack Overflow debugging-walkthrough answer threads (sequential steps)
  3. GitHub issue threads with step-by-step debugging in comments

The parser is more lenient about event granularity than parser_tb / parser_swe
because human descriptions are less structured than agent trajectories.

Uses the same TrajectoryEvent type vocabulary as parser_tb — critical for
T-code uniformity.

Implemented in Session 4.
"""

from __future__ import annotations

from src.parser_tb import TrajectoryEvent, TrajectoryLog


def parse_human_session(raw: dict) -> TrajectoryLog:
    """
    Parse a raw human debugging session record into a TrajectoryLog.

    Parameters
    ----------
    raw : dict with session metadata and a sequence of human-described actions

    Returns
    -------
    TrajectoryLog with typed TrajectoryEvent objects.
    """
    raise NotImplementedError("parse_human_session not yet implemented (Session 4)")


def filter_trajectory(log: TrajectoryLog, min_events: int = 5) -> bool:
    """Return True if the human trajectory meets minimum inclusion criteria.

    Minimum is lower (5) than agent sources because human session data is
    inherently less structured.
    """
    return len(log.events) >= min_events
