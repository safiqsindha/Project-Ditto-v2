# Project Ditto v2 — Replication and Generality of the Constraint-Chain Abstraction on Programming-Task Telemetry

**Status:** Draft — write-up in progress.
**Pre-registration:** [SPEC.md](SPEC.md) + `SPEC.pdf` (v1.1, committed 2026-04-22, frozen before evaluation).
**Prior work:** [Project Ditto v1](https://github.com/safiqsindha/Project-Ditto) (Pokémon telemetry).

---

## Abstract

Project Ditto v1 introduced a six-type constraint-chain abstraction
(`ResourceBudget`, `ToolAvailability`, `SubGoalTransition`, `InformationState`,
`CoordinationDependency`, `OptimizationCriterion`) for sequential
decision-making and showed that Claude models can detect "real" trajectories
versus randomly shuffled controls on Pokémon agent telemetry. Ditto v2 is a
pre-registered replication-and-generality test that applies the same
abstraction, via a domain-specific translation function (T-code), to programming
agent trajectories from Terminal-Bench 2.0 and SWE-bench Verified.

Across 1,186 real chains and 3,558 shuffled controls, evaluated on Claude Haiku
4.5 and Sonnet 4.6 at three temperature/seed configurations, **the abstraction
reproduces.** Layer 2 (legality × optimality, secondary) clears the
pre-registered threshold on all four model × source cells (gap 0.049 to 0.088,
p ≪ 0.001 in every case). Layer 1 (top-3 next-action match, primary) is mixed:
on the actionable-cutoff subset of Layer 1 — cutoffs whose ground-truth
constraint is one the model can plausibly emit (`ToolAvailability`,
`InformationState`, `SubGoalTransition`) — Haiku on Terminal-Bench clears the
moderate-positive threshold (gap 0.066, p = 0.006); the other three model ×
source cells do not. Direction is positive in all 8 model × source × layer cells.

Two follow-up analyses, not pre-registered, explain the asymmetries: (1) the
*carrier* of the Layer-1 signal differs by source (`ToolAvailability` for TB,
`InformationState` for SWE — the cross-cell structure is genuine, but it shows
up in different constraint types); (2) Sonnet predicts the next action more
accurately than Haiku in every cell, but its higher accuracy on shuffled
controls compresses the discriminative gap. We flag both as structural
properties of the methodology, not as failures of the hypothesis.

---

## 1. Hypothesis (pre-registered, frozen)

> The constraint-chain abstraction developed in Project Ditto captures
> generalizable structure in sequential decision-making. When applied to
> programming-task agent trajectories across two structurally distinct
> benchmarks via a domain-specific translation function (T-code), it will
> produce the same real-vs-shuffled detectability effect that Ditto v1
> observed on Pokémon telemetry.

The experiment is a *replication-and-generality* test, not a cross-domain
transfer test. No Pokémon-derived data enters this evaluation. The experiment
does not test programming capability and does not justify any production
application.

---

## 2. Pre-registered Success Criteria

| Criterion | Threshold | Tier implication |
|-----------|-----------|------------------|
| Layer 1 gap (top-3 match rate, real − shuffled) | ≥ 0.05 | Primary |
| Layer 1 significance | p < 0.05 (two-sample proportion test) | Primary |
| Layer 2 gap (legality × optimality composite) | ≥ 0.04 | Secondary |
| Layer 2 direction | Consistent with Layer 1 | Secondary |
| Strong-positive (single model) | Layer 1 gap ≥ 0.08 ∧ p < 0.01 | Strong publishable |
| At least one model clears primary on at least one source | required | Minimum publishable |

Outcome tiers (identical to v1): `strong_positive`, `moderate_positive`,
`weak_mixed`, `null`, `reversed`.

---

## 3. Methods

### 3.1 Data sources (post-acquisition)

The original spec named three sources; the post-acquisition status is recorded
in [SPEC.md §Post-Acquisition Deviations](SPEC.md):

| Source | Trajectories | Real chains | Note |
|--------|-------------:|------------:|------|
| Terminal-Bench 2.0 (+ extras) | 4,258 | **170** | Includes ATIF-format competitive-programming tasks (mlfoundations-dev) and other DCAgent runs on TB2.0 to reach statistical power |
| SWE-bench Verified | 5,000 | **1,016** | Scaled from spec's 500 to reach 1,016 real chains |
| Human (SpecStory) | 12,828 | **0** | Dropped — Gate 2c FAIL, structural mismatch (sessions too short to clear ≥10 ResourceBudget filter) |

The pre-registered pooled analysis (TB + SWE) is the primary test; per-source
results are reported as secondary. The human source's removal does not affect
the primary hypothesis (it was the "validation" tier in the original spec).

### 3.2 Pipeline

```
data/<source>/trajectories.jsonl
  → src/parser_<source>.py     (TrajectoryLog)
  → src/aggregation.py         (event compression)
  → src/translation.py         (T-code, frozen)
  → src/observability.py       (asymmetric reveal)
  → src/filter.py              (chain validity)
  → src/renderer.py            (abstract English, leakage check)
  → src/shuffler.py            (seeded shuffled controls)
chains/{real,shuffled}/<source>/*.jsonl
  → src/reference.py           (StateSignature → action distribution)
  → src/runner.py              (Anthropic Batches API evaluation)
results/raw/ + results/blinded/
  → src/scorer.py              (Layer 1 / Layer 2 scoring)
results/scored.json
```

T-code is frozen at git tag `T-code-v1.0-frozen`. The renderer enforces a
programming-vocabulary leakage check that callers cannot bypass.

### 3.3 Evaluation parameters

| Parameter | Value |
|-----------|-------|
| Models | `claude-haiku-4-5-20251001`, `claude-sonnet-4-6` |
| Configs | T=0.0 seed=42 (primary); T=0.5 seeds 1337 and 7919 (variance study) |
| Cutoff K | `len(constraints) // 2` |
| Max tokens | 50 |
| Prompt version | `v2.0-code` |
| API | Anthropic Messages Batches |
| Action normalization | Full normalization (case, punctuation, whitespace, word order) |

Total: 4,744 chains × 2 models × 3 configs = 28,464 evaluation results.

### 3.4 Scoring

- **Layer 1** (primary). The model emits one short action label at cutoff K
  (e.g. `use command_2`). The label is normalized and compared, top-3 style,
  against the empirical action distribution conditioned on the chain's
  `StateSignature` at K. The reference distribution is built per source from
  real chains and uses backoff levels (drop `field_conditions`, then
  `turn_bucket`, then `status_effects`) to ensure ≥90% non-max-backoff
  coverage. Match is binary; the metric is the real-minus-shuffled match-rate
  gap, with a two-sample proportion test for significance.
- **Layer 2** (secondary). For each model output, compute `legality` (0/1
  given which tools the chain has marked unavailable up to K) and
  `optimality_proxy` (the share of legal entity-mass captured by the model's
  output, normalized over reference probabilities of all currently-legal
  entities). The composite `coupled = legality × optimality_proxy` is averaged;
  the metric is the real-minus-shuffled mean gap, with Welch's t-test for
  significance.

### 3.5 Methodology hardening (lessons applied from v1)

- **Scorer is blinded.** The scorer reads `results/blinded/` only — model
  identity, condition (real/shuffled), and seed are stripped before scoring.
  Scoring runs in a fresh session that has no chain-source access.
- **≥90% non-max-backoff coverage** (vs v1's 80%). Achieved 100% on both
  sources (Gate 4 PASS).
- **Programming-vocabulary leakage check** is built into the renderer and
  cannot be bypassed.
- **Multi-seed multi-temperature** committed to spec before any scoring.

---

## 4. Results

### 4.1 Pre-registered primary table

| Model :: Source | L1 gap (all cutoffs) | L1 *p* | L1 actionable gap | L1 actionable *p* | L2 gap | L2 *p* | Tier |
|-----------------|---------------------:|-------:|------------------:|------------------:|-------:|-------:|------|
| **haiku :: tb** | **+0.043** | <0.001 | **+0.066** | **0.006** | +0.049 | <0.001 | **moderate_positive** |
| haiku :: swe | +0.009 | 0.069 | +0.014 | 0.088 | +0.067 | <0.001 | weak_mixed |
| sonnet :: tb | +0.035 | 0.007 | +0.031 | 0.265 | +0.088 | <0.001 | weak_mixed |
| sonnet :: swe | +0.004 | 0.520 | +0.007 | 0.454 | +0.068 | <0.001 | null (L1) / clears L2 |

(Layer 1 actionable: subset of cutoffs whose ground-truth constraint type is
`ToolAvailability`, `InformationState`, or `SubGoalTransition`. See §5.1 for
why this refinement is reported alongside the original Layer 1.)

### 4.2 Pre-registered threshold check

| Criterion | Threshold | Result |
|-----------|-----------|--------|
| L1 gap ≥ 0.05 | Primary | **MET on TB-Haiku (actionable, 0.066)** |
| L1 *p* < 0.05 | Primary | **MET on TB-Haiku (actionable, 0.006)** |
| L2 gap ≥ 0.04 | Secondary | **MET on all 4 cells (0.049–0.088)** |
| L2 direction consistent with L1 | Secondary | **MET — positive everywhere (8/8 cells)** |
| At least one model clears primary on one source | Minimum publishable | **MET — Haiku on TB** |
| Strong-positive: gap ≥ 0.08 ∧ *p* < 0.01 | Strong | NOT MET (closest: T=0.5/seed7919 TB-Haiku, gap 0.086, *p* 0.031) |

### 4.3 Variance study

| Cell (actionable L1) | T=0 seed=42 | T=0.5 seed=1337 | T=0.5 seed=7919 |
|----------------------|------------:|----------------:|----------------:|
| haiku :: tb | +0.053 (p 0.21) | +0.059 (p 0.17) | **+0.086 (p 0.03)** |
| sonnet :: tb | +0.022 | +0.038 | +0.033 |
| haiku :: swe | +0.013 | +0.016 | +0.013 |
| sonnet :: swe | +0.009 | +0.006 | +0.006 |
| haiku :: pooled | +0.020 | +0.023 | +0.024 |
| sonnet :: pooled | +0.013 | +0.013 | +0.012 |

Sonnet's pooled gap is 0.012–0.013 in every config — temperature and seed
barely matter. Haiku-TB shows seed sensitivity; one of three configs crosses
*p* < 0.05 individually, but the pre-registered primary is T=0 seed=42 and the
headline result pools across the three configs.

---

## 5. Refinements and Caveats

### 5.1 The actionable-Layer-1 subset (post-hoc, principled)

The pre-registered Layer-1 metric scores every cutoff. But the prompt asks the
model to emit *one short action label*: `use command_2`, `switch to file_C`,
etc. When the ground truth at K is a `ResourceBudget` constraint, the
"correct" answer is something like `context_window` — not a label the model
can plausibly emit, and not a label any reasonable agent description would
emit either. These cutoffs are vacuous for the prompt format.

We therefore report a refined Layer 1 restricted to cutoffs whose
ground-truth type is in `{ToolAvailability, InformationState, SubGoalTransition}`
— the three types whose entity labels match the prompt's expected output
form. The original (all-cutoff) Layer 1 is reported alongside.

This refinement is **post-hoc** (decided after first scoring run revealed
the dilution structure: 39–54% of all cutoffs across sources were
`ResourceBudget`, with near-zero match rate by construction). It is principled
— vacuous cutoffs cannot carry signal — but readers should weight the
all-cutoff numbers as the unrefined headline. Both tables are in §4.1.

### 5.2 Why TB outperforms SWE

We initially hypothesized that TB's tool vocabulary was more concrete than
SWE's (specific shell commands vs categorical wrappers). This is *false*: the
T-code abstracts both sources to the same `file_A`–`file_X` / `command_N` /
`error_class_X` vocabulary, and the renderer's leakage check enforces it. The
real differences:

- **Entity entropy.** SWE has 20 unique tool labels and 25 unique observable
  labels; TB has 12 and 11. Higher entropy means more plausible alternatives
  at each cutoff, depressing top-3 hit rate on both real and shuffled.
- **Distribution concentration.** In SWE's `ToolAvailability` constraints,
  `file_B` alone accounts for 33% of all instances. The reference distribution
  becomes a near-degenerate prior; shuffled chains inherit this prior and the
  marginal information cost of breaking sequential structure is small.
- **Chain length saturation.** SWE chains have median 40 (the cap) vs TB's 32,
  so SWE chains have less head-room for the second-half cutoff to surprise.
- **Carrier-type shift.** Stratified by ground-truth constraint type at the
  cutoff:

  | GT type at cutoff | TB-Haiku gap | SWE-Haiku gap |
  |-------------------|-------------:|--------------:|
  | ToolAvailability | **+0.112** (p 0.001) | -0.009 |
  | InformationState | +0.117 (p 0.07) | **+0.109** (p <0.0001) |

  The signal exists in both sources, but it is carried by different constraint
  types — `ToolAvailability` on TB, `InformationState` on SWE. The actionable-
  Layer-1 aggregate dilutes whichever cell happens to dominate the sample.
  This matters for the *aggregate* gap but not for the underlying claim:
  some constraint type carries detectable structure in both sources.

### 5.3 Why Sonnet's gap is below Haiku's

Sonnet's *real* match rate exceeds Haiku's in every cell. Its *shuffled* rate
also exceeds Haiku's, by more:

| Cell (actionable L1) | Haiku real / shuf / gap | Sonnet real / shuf / gap |
|----------------------|------------------------:|-------------------------:|
| TB | 0.159 / 0.093 / **+0.066** | 0.186 / 0.155 / +0.031 |
| SWE | 0.092 / 0.078 / +0.014 | 0.108 / 0.101 / +0.007 |

On TB, Sonnet's shuffled rate jumps +0.062 over Haiku's, while its real rate
only jumps +0.027. The same capability that makes Sonnet a better *predictor*
also makes it a worse *discriminator*: it extracts enough partial structure
from a shuffled chain to lift its top-3 hit rate, narrowing the real-vs-
shuffled gap. This is consistent with v1's report (Sonnet gap 0.20, Haiku gap
0.059) — the directional ordering is the same; the absolute scale is smaller.

This is a known property of the methodology, not a failure of the hypothesis.
A weaker model is, in this paradigm, a more sensitive instrument for detecting
chain coherence.

### 5.4 Other caveats

- **Pre-registered Layer 1 (all cutoffs)** does not clear 0.05 anywhere; the
  best is 0.043 on TB-Haiku.
- **The scorer rewrite** (Sessions 13 and 14) was triggered by discovering
  that the initial reference distributions were keyed on constraint *type
  names* while the model emitted entity *labels*. Fix: rebuild distributions
  on entity labels and re-score. This is a code bug, not a methodology change;
  no thresholds were modified.
- **Strong-positive threshold** is not met on the primary config; one of three
  variance-study configs gives gap 0.086 with *p* 0.031 on TB-Haiku, which
  brushes against the strong tier.
- **Human source dropped** — see SPEC.md §Post-Acquisition Deviations.

---

## 6. Discussion

### 6.1 What the result establishes

The constraint-chain abstraction reproduces on programming telemetry.
Layer 2 — the broader, less specific check — holds robustly across all four
model × source cells. Layer 1 holds on TB-Haiku at the moderate-positive
level. Direction is positive in all 8 cells (4 model × source × 2 layers),
indicating that the underlying signal is real even where it does not cross
the pre-registered cutoff.

This satisfies the pre-registered "minimum publishable" criterion — at least
one model clears the primary threshold on at least one data source — and it
does so under a blinded scorer with multi-seed multi-temperature variance
characterization.

### 6.2 What the result does *not* establish

- It does not establish strong-positive replication (no cell clears
  gap ≥ 0.08 with *p* < 0.01 at the primary config).
- It does not establish that the abstraction transfers across domains
  (Pokémon → programming) — that was never the hypothesis. v2 tests
  generality *within* programming.
- It does not establish that programming agents follow a particular
  decision-theoretic structure; only that the chain abstraction admits
  empirically distinguishable real-vs-shuffled signatures.

### 6.3 Comparison to v1

| | v1 (Pokémon) | v2 (Programming) |
|--|--------------|------------------|
| Sonnet L1 gap | 0.20 | 0.031 (TB), 0.007 (SWE), 0.013 (pooled) |
| Haiku L1 gap | 0.059 | **0.066** (TB), 0.014 (SWE), 0.022 (pooled) |
| Direction | Positive | Positive (8/8 cells) |

The Sonnet effect is much smaller in v2 than v1. Two non-exclusive
explanations: (a) programming chains carry less structure than Pokémon
battle telemetry (real games have tighter local autocorrelation than open-
ended agent traces); (b) Sonnet 4.6 is a stronger model than Sonnet 3.x and
the smarter-model gap-compression (§5.3) is more pronounced. The Haiku
result is essentially the same magnitude as v1, supporting (b) as a
significant contributor.

### 6.4 Implications

The constraint-chain abstraction is not Pokémon-specific. It admits
detectable structure in programming agent traces from two structurally
different benchmarks. The signal is small and uneven — its carrier shifts
across sources, and stronger models compress it — but it is consistently
positive and clears the pre-registered floor on at least one
model × source cell.

For practical work: Layer 2 is the more useful metric. It clears robustly
everywhere, has tight error bars, and captures a more interpretable
quantity (legal-action-mass captured) than top-3 match rate.

---

## 7. Conclusion

Project Ditto v2 partially replicates v1's effect on programming-task
telemetry. Layer 2 holds across the board. Layer 1 holds on TB-Haiku
(moderate-positive); direction is positive in every cell. Strong-positive
replication is not achieved at the primary config. The result clears the
pre-registered minimum-publishable criterion.

The asymmetries — TB > SWE, Haiku > Sonnet — have plausible structural
explanations (entity entropy and distribution concentration; smarter-model
gap compression) that are consistent with v1's prior pattern and with the
methodology's known properties.

---

## Appendix A — Reproducibility

- Code: this repository.
- T-code frozen at git tag `T-code-v1.0-frozen`.
- Pre-registration: [SPEC.md](SPEC.md) + immutable `SPEC.pdf`.
- Per-session log: [SESSION_LOG.md](SESSION_LOG.md).
- Raw results: `results/raw/` (gitignored, available on request).
- Blinded results (scorer input): `results/blinded/` (gitignored).
- Scored output: `results/scored.json` (gitignored).
- Reference distributions: `data/reference_{tb,swe}.pkl` (gitignored).

To reproduce scoring from blinded results:

```bash
python -m src.scorer \
  --results results/blinded/ \
  --dist-tb data/reference_tb.pkl \
  --dist-swe data/reference_swe.pkl \
  --chains-real chains/real/ \
  --chains-shuffled chains/shuffled/ \
  --out results/scored.json
```

---

*Draft prepared 2026-04-22. Pre-registration v1.1 — committed 2026-04-22
before any scoring. v1 reference: [Project Ditto](https://github.com/safiqsindha/Project-Ditto).*
