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

## Session 8 Amendment — Pooled Analysis (2026-04-22)

**Supplementary pre-registration (Session 8 amendment):** Due to lower-than-expected
per-source chain counts (~5% pass rate for TB, ~18% for SWE with current trajectory
volumes), the primary hypothesis test will aggregate the real-vs-shuffled comparison
across all three sources (TB + SWE + human) to achieve adequate statistical power for
both Sonnet and Haiku effect sizes.  Per-source results are reported as secondary analyses.

This is not a methodology change — pooled analysis was always intended (see §5.1 below);
this amendment makes the pooling the **primary** test rather than secondary, effective
2026-04-22 before any chain-level scoring begins.

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

---

## Post-Acquisition Deviations (documented 2026-04-22)

Thresholds and primary methodology are unchanged. The following deviations from the
original data-source descriptions are documented here before evaluation begins.

### TB source expansion
Terminal-Bench 2.0 trajectories (ATIF format) yield a 4.8% chain acceptance rate due to
the constraint filter requiring ≥10 ResourceBudget constraints. To reach statistical power,
the "tb" source was expanded to include:
- `DCAgent/{GPT-5,GPT-5-nano,eval-SERA-*,eval-R2EGym-*}-terminal-bench-2.0` — same TB2.0
  tasks, different models (no methodology deviation)
- `mlfoundations-dev/code-contests-sandboxes-traces-terminus-2` — competitive-programming
  terminal-sandbox tasks in the same ATIF format. Constraint structure is identical
  (bash_call → ResourceBudget, file_edit → SubGoalTransition, test_run → validation).
  **Deviation**: tasks are competitive programming problems, not Terminal-Bench 2.0 tasks.
  Final TB chain count: 170 real chains from 4,258 combined trajectories.

### SWE scale-up
SWE source expanded from 500 to 5,000 trajectories (target 1,016 real chains).
Same nebius/SWE-agent-trajectories dataset, same methodology. No deviation.

### Human source dropped (Gate 2c FAIL — structural incompatibility)
Two full acquisition runs of SpecStory files from GitHub (12,828 candidates total) yielded
0 accepted sessions. Root cause: SpecStory human-AI chat sessions are too short and
conversational — 79% rejected as too_short (< 15 events). The T-code requires ≥10
ResourceBudget constraints (from bash_call events), which human chat turns do not produce.
This is a structural mismatch, not a filter calibration issue.

**Decision (2026-04-22):** Human source is dropped. Evaluation proceeds on TB + SWE only.
Human was the "Validation" source in the spec (not primary or secondary); the primary
hypothesis is unaffected. The pooled analysis (TB + SWE) is the primary test.

### Layer 1 scoring — fixed
`action_at_step` and `per_step_actions` are now populated in all chain files.
`action_at_step` = constraint type name at `cutoff_k`; `per_step_actions` = constraint
type at every step. Reference distributions rebuilt: TB 354 level-0 keys, SWE 3,485
level-0 keys. Gate 4 PASS: 100% non-max-backoff coverage on both sources. Gate 5 PASS:
live API dry-run produced parseable responses.

### Pooled analysis pre-registered
Given per-source chain counts (TB: 170, SWE: 1,016, human: TBD), Haiku's small effect
(d=0.059) requires pooled analysis across all sources. Pooled analysis was pre-planned
in SESSION_LOG.md before evaluation and is reported alongside per-source results.
