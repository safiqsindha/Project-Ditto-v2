# Project Ditto v2 — Pre-Registration Specification

**Specification v1.1** · Pre-registration draft · Supersedes v1.0  
Full PDF: `SPEC.pdf` (immutable — do not edit)

> **This document is frozen.**  
> Thresholds, methodology, and analysis plan are committed here before T-code
> implementation begins.  Any methodology change after Gate 1 invalidates the
> pre-registration and requires a new dated spec.

---

## Hypothesis (precisely scoped)

The constraint-chain abstraction developed in Project Ditto (six constraint types:
`ResourceBudget`, `ToolAvailability`, `SubGoalTransition`, `InformationState`,
`CoordinationDependency`, `OptimizationCriterion`) captures **generalizable structure in
sequential decision-making**.  When applied to programming-task agent trajectories across
two structurally distinct benchmarks (Terminal-Bench 2.0 and SWE-bench Verified) via a
domain-specific translation function **T-code**, it will produce the same real-vs-shuffled
detectability effect that Ditto observed on Pokémon telemetry.

The experiment is a **replication-and-generality test**, not a cross-domain transfer test.

---

## What this experiment is NOT

- Not a test of whether game telemetry helps programming reasoning
- Not a test of whether models trained on one domain transfer to another
- No Pokémon-derived data enters this evaluation
- Does not measure programming capability
- Does not justify a production application

---

## Pre-registered Success Criteria

| Criterion | Threshold | Tier implication |
|-----------|-----------|-----------------|
| Layer 1 gap (top-3 match rate, real − shuffled) | ≥ 0.05 | Primary hypothesis threshold |
| Layer 1 significance | p < 0.05 (two-sample proportion test) | Primary hypothesis threshold |
| Layer 2 gap (legality × optimality composite) | ≥ 0.04 | Secondary confirmation |
| Layer 2 direction | Consistent with Layer 1 | Secondary confirmation |
| Strong-positive (single model) | Layer 1 gap ≥ 0.08 ∧ p < 0.01 | Publishable strong result |
| At least one model clears primary | On at least one data source | Minimum for publishable result |

**Outcome tiers** (identical to v1): `strong_positive`, `moderate_positive`, `weak_mixed`, `null`, `reversed`

---

## Models and Evaluation Parameters

| Parameter | Value |
|-----------|-------|
| Models | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`), Claude Sonnet 4.6 (`claude-sonnet-4-6`) |
| Primary config | Temperature 0.0, seed 42 |
| Variance study | T=0.5, seeds 1337 and 7919 |
| Max tokens | 50 |
| Cutoff K | `len(constraints) // 2` |
| Prompt version | v2.0-code |
| API | Anthropic Messages Batches (50% cost reduction) |
| Action normalization | Full normalization (case, punctuation, whitespace, word order) |

---

## Data Sources (ordered — committed now, will not change)

1. **Primary:** Terminal-Bench 2.0 (~500 trajectories)
2. **Secondary:** SWE-bench Verified (~500 trajectories)
3. **Validation:** Human debugging sessions (~100 trajectories)

All three sources' results will be reported regardless of direction.

---

## Chain Construction Parameters

- **Length:** 20–40 constraints per chain
- **Diversity:** ≥ 2 `SubGoalTransition`, ≥ 1 `ToolAvailability(unavailable)`, ≥ 10 `ResourceBudget`
- **Timestamps:** non-decreasing, no consecutive duplicates
- **Shuffling:** seeded permutation with sorted timestamp reassignment (seeds 42, 1337, 7919)
- **Targets:** 500 real + 1500 shuffled per primary/secondary source; ≥ 30 real + ≥ 90 shuffled for human

---

## Gating Decisions

| Gate | Criterion | Failure response |
|------|-----------|-----------------|
| Gate 1 (end Week 1) | ≥ 400 usable Terminal-Bench trajectories | Stop, find alternative sources |
| Gate 2 (end Week 2) | ≥ 400 usable SWE-bench trajectories; aggregation rules validated | Stop, find alternative sources |
| Gate 3 (end Week 4) | T-code passes leakage checks on 20 rendered chains per source (40 total) | Fix T-code before freeze |
| Gate 4 (end Week 5) | ≥ 90% non-max-backoff coverage per source | Expand reference corpus |
| Gate 5 (mid Week 6) | Dry-run produces parseable responses and non-zero Layer 1 match rates | Debug format alignment |

---

## Methodology Hardening (lessons from v1)

- **Scorer-in-separate-session:** scoring code reads from `results/blinded/` only, no chain source access
- **Reference distribution size:** target ≥ 90% non-max-backoff coverage (vs v1's 80%)
- **Vocabulary leakage:** default programming vocab list ships with renderer, cannot be bypassed
- **Multi-seed and multi-temperature from the start:** full seed × temperature matrix pre-registered before any scoring

---

## Pre-registered Supplementary Analyses (spec §5.1)

1. Effect-size comparison to v1 (Ditto v1 Sonnet gap = 0.20, Haiku gap = 0.059)
2. Primary-vs-secondary dataset consistency (if effects diverge >2×, investigate trajectory features)
3. Agent-trajectory vs human-trajectory consistency (direction confirmation only for human set)

---

## What it would establish if it clears thresholds

> "The constraint-chain abstraction (six specific types) captures causal structure in
> sequential decision-making across at least two structurally different domains.  The
> abstraction is not Pokémon-specific; it generalizes to programming-task trajectories."

If both programming sources clear: the claim strengthens to generality across programming
domains with different trajectory structures (tightly-discretized vs longer-horizon).

---

*Pre-registration v1.1 — committed 2026-04-22. Ditto v1 result (published 2026-04-21)
is prior work establishing the methodology; v2 independently tests its generality.*
