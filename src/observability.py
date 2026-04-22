"""
Asymmetric observability filter for trajectory constraint chains (spec §3.3).

In v1 the opponent's units were hidden until revealed via switch events.
The v2 analog: code regions (files, modules, error types) the agent hasn't
read yet are hidden until referenced by a read/execution event.

The abstraction: InformationState constraints should only reference entities
that have been observable_added in a prior InformationState event.  Before
that, the entity is referenced only by role (e.g. "an external dependency").

Asymmetric reveal timing is applied the same way as v1 — entities are hidden
until their first InformationState.observable_added event, then fully visible.
"""

from __future__ import annotations

import re

from src.translation import (
    Constraint,
    CoordinationDependency,
    InformationState,
    OptimizationCriterion,
    ResourceBudget,
    SubGoalTransition,
    ToolAvailability,
)


def bucket_resource(amount: float) -> float:
    """Bucket 0.0–1.0 resource amount to {0.0, 0.25, 0.5, 0.75, 1.0}."""
    if amount <= 0:
        return 0.0
    if amount <= 0.25:
        return 0.25
    if amount <= 0.5:
        return 0.5
    if amount <= 0.75:
        return 0.75
    return 1.0


def _find_reveal_indices(constraints: list[Constraint]) -> dict[str, int]:
    """
    Return a mapping from entity label to the index of its first
    InformationState revelation in the constraint list.
    """
    first_reveal: dict[str, int] = {}
    for i, c in enumerate(constraints):
        if isinstance(c, InformationState):
            for entity in c.observable_added:
                if entity not in first_reveal:
                    first_reveal[entity] = i
    return first_reveal


def _find_pre_reveal_ta_indices(
    constraints: list[Constraint],
    first_reveal: dict[str, int],
) -> set[int]:
    """
    Identify ToolAvailability constraints that appear before the corresponding
    entity has been revealed via InformationState.

    Pattern (analogous to v1's opponent switch-in suppression):
      ..., TA(entity available), ..., InformationState(observable_added=[entity])
    Any TA for entity before its first reveal index is suppressed.
    """
    suppress_indices: set[int] = set()

    for i, c in enumerate(constraints):
        if not isinstance(c, ToolAvailability):
            continue
        entity = c.tool
        if entity in first_reveal and i < first_reveal[entity]:
            suppress_indices.add(i)

    return suppress_indices


def apply_asymmetric_observability_with_indices(
    constraints: list[Constraint],
    perspective: str = "agent",
) -> tuple[list[Constraint], list[int]]:
    """Same as apply_asymmetric_observability but also returns kept original indices."""
    first_reveal = _find_reveal_indices(constraints)
    suppress_ta_indices = _find_pre_reveal_ta_indices(constraints, first_reveal)

    result: list[Constraint] = []
    kept_indices: list[int] = []

    for i, c in enumerate(constraints):
        kept_c: Constraint | None

        if isinstance(c, InformationState):
            kept_c = c
        elif isinstance(c, ToolAvailability):
            kept_c = None if i in suppress_ta_indices else c
        elif isinstance(c, ResourceBudget):
            resource = c.resource
            m = re.search(r"(file_[A-Z](?:_OVERFLOW_\d+)?)", resource)
            entity_label = m.group(1) if m else None
            if entity_label and entity_label in first_reveal and i < first_reveal[entity_label]:
                kept_c = None  # suppress pre-reveal resource reference
            else:
                kept_c = c
        else:
            kept_c = c

        if kept_c is not None:
            result.append(kept_c)
            kept_indices.append(i)

    return result, kept_indices


def apply_asymmetric_observability(
    constraints: list[Constraint],
    perspective: str = "agent",
) -> list[Constraint]:
    """
    Filter/modify constraints to reflect partial information.

    Rules:
    - InformationState: always keep (it IS the reveal event)
    - ToolAvailability: suppress if the referenced entity has not yet been
      revealed via InformationState
    - ResourceBudget referencing an unrevealed file/error entity: suppress
    - All other constraint types: keep as-is
    """
    result, _ = apply_asymmetric_observability_with_indices(constraints, perspective)
    return result
