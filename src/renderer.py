"""
Renderer: converts abstract Constraint objects into human-readable, domain-abstracted English.

NO programming-domain vocabulary is permitted in any output string.  The post-rendering
leakage check (check_programming_leakage) ships with a default vocabulary list and is
invoked automatically by render_chain().  The full vocabulary list is built in Session 7.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from src.translation import (
    Constraint,
    CoordinationDependency,
    InformationState,
    OptimizationCriterion,
    ResourceBudget,
    SubGoalTransition,
    ToolAvailability,
)


# ---------------------------------------------------------------------------
# Per-type renderers
# ---------------------------------------------------------------------------

def _render_resource_budget(c: ResourceBudget) -> str:
    pct = f"{c.amount * 100:.1f}%"
    parts = [f"ResourceBudget: {c.resource} at {pct}"]
    if c.decay != "none":
        parts.append(f"(decay={c.decay})")
    if c.recover_in is not None:
        parts.append(f"(recover_in={c.recover_in} steps)")
    return " ".join(parts)


def _render_tool_availability(c: ToolAvailability) -> str:
    state_str = c.state.upper()
    if c.state == "unavailable" and c.recover_in is None:
        return f"ToolAvailability: {c.tool} is now {state_str} (permanent)"
    elif c.state == "unavailable":
        return f"ToolAvailability: {c.tool} is now {state_str} (recover_in={c.recover_in})"
    else:
        return f"ToolAvailability: {c.tool} is now {state_str}"


def _render_subgoal_transition(c: SubGoalTransition) -> str:
    return (
        f"SubGoalTransition: phase shifted from '{c.from_phase}' to '{c.to_phase}'"
        f" (trigger={c.trigger})"
    )


def _render_information_state(c: InformationState) -> str:
    added = ", ".join(c.observable_added) if c.observable_added else "none"
    removed = ", ".join(c.observable_removed) if c.observable_removed else "none"
    return (
        f"InformationState: added=[{added}] removed=[{removed}]"
        f" uncertainty={c.uncertainty:.2f}"
    )


def _render_coordination_dependency(c: CoordinationDependency) -> str:
    return (
        f"CoordinationDependency: {c.role} depends on {c.dependency}"
        f" -> expected_action={c.expected_action}"
    )


def _render_optimization_criterion(c: OptimizationCriterion) -> str:
    return (
        f"OptimizationCriterion: objective={c.objective}"
        f" weight_shift={c.weight_shift}"
    )


_RENDERERS = {
    ResourceBudget:         _render_resource_budget,
    ToolAvailability:       _render_tool_availability,
    SubGoalTransition:      _render_subgoal_transition,
    InformationState:       _render_information_state,
    CoordinationDependency: _render_coordination_dependency,
    OptimizationCriterion:  _render_optimization_criterion,
}


def render_constraint(c: Constraint) -> str:
    """Render a single constraint as a one-line abstract English description."""
    renderer = _RENDERERS.get(type(c))
    if renderer is None:
        return f"UnknownConstraint: {c!r}"
    return renderer(c)


# ---------------------------------------------------------------------------
# Chain renderer
# ---------------------------------------------------------------------------

def render_chain(constraints: list[Constraint], perspective: str = "agent") -> str:
    """
    Render a list of constraints as numbered steps.

    Raises ValueError if programming-domain vocabulary is detected in the output.

    Parameters
    ----------
    constraints : ordered list of Constraint objects
    perspective : trajectory perspective label (included in header for traceability)

    Returns
    -------
    Multi-line string, one step per constraint.
    """
    if not constraints:
        return f"# Constraint chain (perspective={perspective})\n(no constraints)\n"

    lines: list[str] = [f"# Constraint chain (perspective={perspective})"]
    step = 1
    for c in constraints:
        turn = getattr(c, "timestamp", 0)
        body = render_constraint(c)
        lines.append(f"Step {step} (step={turn}):")
        lines.append(f"  {body}")
        step += 1

    rendered = "\n".join(lines) + "\n"

    leaked = check_programming_leakage(rendered)
    if leaked:
        raise ValueError(
            f"Programming vocabulary detected in rendered chain: {leaked}. "
            "Check translation.py for domain leakage."
        )

    return rendered


def render_trajectory_chain(constraints: list[Constraint], source: str = "tb") -> str:
    """Convenience wrapper for render_chain using source as the perspective label."""
    return render_chain(constraints, perspective=source)


# ---------------------------------------------------------------------------
# Leakage checker  (full vocabulary list built in Session 7)
# ---------------------------------------------------------------------------

# Default programming-domain vocabulary — expanded in Session 7.
# This seed list catches the most obvious leaks during early development.
_DEFAULT_PROGRAMMING_VOCAB: frozenset[str] = frozenset({
    # Python keywords
    "def", "class", "import", "return", "async", "await", "yield", "lambda",
    "raise", "except", "finally", "with", "pass", "global", "nonlocal",
    # Common packages (expanded in Session 7)
    "django", "flask", "numpy", "pandas", "scipy", "sklearn", "matplotlib",
    "torch", "tensorflow", "requests", "fastapi", "pydantic", "pytest",
    "sqlalchemy", "celery", "redis", "boto3", "aiohttp",
    # Common bash commands
    "grep", "find", "sed", "awk", "curl", "wget", "ssh", "docker",
    "git", "make", "pip", "npm", "yarn", "cargo", "rustc",
    # Python error types
    "TypeError", "ValueError", "KeyError", "AttributeError", "ImportError",
    "RuntimeError", "IndexError", "NameError", "OSError", "FileNotFoundError",
    "PermissionError", "TimeoutError", "StopIteration", "AssertionError",
    # File extensions that shouldn't appear literally
    # (checked as substrings only — whole-word matching applies)
})


def check_programming_leakage(
    rendered: str,
    vocab: set[str] | frozenset[str] | None = None,
) -> list[str]:
    """
    Return any programming-domain vocabulary found in the rendered output.

    A match is case-insensitive whole-word search so that partial substrings
    do not produce false positives.

    Parameters
    ----------
    rendered : string produced by render_chain()
    vocab    : set of terms to check for.  Defaults to _DEFAULT_PROGRAMMING_VOCAB.
               Cannot be bypassed — pass an empty set only in unit tests that
               explicitly test clean output.

    Returns
    -------
    List of leaking terms (empty list means no leakage).
    """
    if vocab is None:
        vocab = _DEFAULT_PROGRAMMING_VOCAB

    leaked: list[str] = []
    for term in vocab:
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, rendered, flags=re.IGNORECASE):
            leaked.append(term)
    return leaked
