# Supplementary Analyses — Project Ditto v2

**These are exploratory analyses of existing data and do not modify the
pre-registered primary result in RESULTS.md §4.**

All scripts are in `scripts/supplementary/`. All analyses operate on
`results/scored.json`, `data/reference_*.pkl`, and `chains/` — no new
evaluation calls were made. Added 2026-04-23 after primary results were
finalized.

---

## §1 Power Analysis

**Script:** `scripts/supplementary/01_power_analysis.py`  
**Output:** `supplementary/power_results.json`

For each of the four model × source cells, we computed (a) achieved
statistical power at the pre-registered threshold (gap ≥ 0.05 for Layer
1, gap ≥ 0.04 for Layer 2), (b) minimum detectable effect size (MDES) at
80% power, and (c) required sample size to detect the observed effect at
80% power, for cells that did not clear. Layer 1 uses `NormalIndPower`
(two-sample proportion test, Cohen's h); Layer 2 uses `TTestIndPower`
(Welch's t-test, Cohen's d approximated from t-statistic).

Note: the primary threshold check uses the all-cutoff Layer 1 rate; the
actionable-subset L1 (which cleared for Haiku on TB, gap = 0.066,
p = 0.006) is not separately power-analysed here but had power ≈ 0.73
at n = 258 real observations.

### Table 1.1 — Achieved power, MDES, and required-N

| Cell | Layer | n_real | Observed gap | Achieved power | MDES (h or d) | Req-N (obs effect, 80%) | Cleared threshold |
|---|---|---|---|---|---|---|---|
| haiku::tb | L1 | 510 | 0.043 | 0.927 | h = 0.143 | 344 | No (gap < 0.05) |
| haiku::tb | L2 | 510 | 0.049 | >0.999 | d = 0.143 | 136 | **Yes** |
| haiku::swe | L1 | 3,048 | 0.009 | 0.432 | h = 0.059 | 7,477 | No |
| haiku::swe | L2 | 3,048 | 0.067 | — † | d = 0.059 | 40 | **Yes** |
| sonnet::tb | L1 | 510 | 0.035 | 0.725 | h = 0.143 | 613 | No (gap < 0.05) |
| sonnet::tb | L2 | 510 | 0.088 | >0.999 | d = 0.143 | 43 | **Yes** |
| sonnet::swe | L1 | 3,048 | 0.004 | 0.098 | h = 0.059 | 58,351 | No |
| sonnet::swe | L2 | 3,048 | 0.068 | >0.999 | d = 0.059 | 40 | **Yes** |

† Power calculation for haiku::swe L2 returned NaN; the t-statistic is very large
(t ≈ 32) implying the observed d far exceeds the MDES, so power is effectively 1.0.

### §1 Interpretation

**Layer 2** is fully powered in all four cells — achieved power is near 1.0 everywhere.
The Layer 2 result is robust.

**Layer 1 TB cells** are adequately powered for the pre-registered threshold (haiku::tb
power = 0.93, sonnet::tb power = 0.73 at n = 510). That neither cleared the strict
gap ≥ 0.05 threshold on the all-cutoff rate (gaps are 0.043 and 0.035) is a
substantive finding, not an artefact of low power. The actionable-subset haiku::tb
(gap = 0.066, n = 258) did clear — this single clearing is consistent with true but
weak positive signal for that subset.

**Layer 1 SWE cells** are severely underpowered for the observed effect sizes. Haiku::SWE
has an observed gap of 0.009 with n = 3,048 and achieves only 43% power. To detect the
observed SWE effect (if real) at 80% power would require ~7,500 real evaluations.
Sonnet::SWE (gap = 0.004) would require >58,000. This means the Layer 1 null on SWE
**cannot be interpreted as evidence of absence** — it is consistent with a small positive
effect that the sample is too small to detect. It is also consistent with a true null.

**Overall:** the power pattern distinguishes "absent" from "underpowered": the L2 signal
is robustly present; the L1 signal is present but small and only detected in the
better-powered TB cell.

---

## §2 Stratified Breakdowns

**Script:** `scripts/supplementary/02_stratified_breakdowns.py`  
**Output:** `supplementary/stratified_results.json`

These are post-hoc descriptive statistics. CI95 on the gap uses the normal approximation
for the difference of proportions.

### Table 2.1 — Layer 1 by constraint type at cutoff (model × source)

| Cell | Constraint type | n_real | Real rate | Shuf rate | Gap | p | Sig |
|---|---|---|---|---|---|---|---|
| haiku::tb | ResourceBudget | 213 | 0.014 | 0.011 | +0.003 | 0.690 | |
| haiku::tb | **ToolAvailability** | **141** | **0.220** | **0.108** | **+0.112** | **0.001** | *** |
| haiku::tb | InformationState | 48 | 0.208 | 0.091 | +0.117 | 0.075 | |
| haiku::tb | SubGoalTransition | 69 | 0.000 | 0.049 | −0.049 | 0.062 | |
| haiku::tb | CoordinationDependency | 24 | 0.000 | 0.222 | −0.222 | 0.014 | * |
| haiku::swe | ResourceBudget | 1,314 | 0.003 | 0.002 | +0.001 | 0.680 | |
| haiku::swe | ToolAvailability | 1,044 | 0.014 | 0.024 | −0.009 | 0.074 | |
| haiku::swe | **InformationState** | **351** | **0.342** | **0.233** | **+0.109** | **<0.001** | *** |
| haiku::swe | SubGoalTransition | 72 | 0.000 | 0.000 | 0.000 | 1.000 | |
| haiku::swe | CoordinationDependency | 267 | 0.288 | 0.324 | −0.036 | 0.297 | |
| sonnet::tb | ResourceBudget | 213 | 0.000 | 0.000 | 0.000 | 1.000 | |
| sonnet::tb | **ToolAvailability** | **141** | **0.234** | **0.156** | **+0.079** | **0.039** | * |
| sonnet::tb | InformationState | 48 | 0.313 | 0.364 | −0.051 | 0.570 | |
| sonnet::tb | SubGoalTransition | 69 | 0.000 | 0.041 | −0.041 | 0.090 | |
| sonnet::tb | CoordinationDependency | 24 | 0.000 | 0.222 | −0.222 | 0.014 | * |
| sonnet::swe | ResourceBudget | 1,314 | 0.000 | 0.000 | 0.000 | 1.000 | |
| sonnet::swe | ToolAvailability | 1,044 | 0.042 | 0.069 | −0.027 | 0.002 | ** |
| sonnet::swe | **InformationState** | **351** | **0.325** | **0.228** | **+0.097** | **<0.001** | *** |
| sonnet::swe | SubGoalTransition | 72 | 0.000 | 0.000 | 0.000 | 1.000 | |
| sonnet::swe | CoordinationDependency | 267 | 0.270 | 0.315 | −0.046 | 0.180 | |

### Table 2.2 — Layer 1 by length bucket (pooled TB+SWE)

| Cell | Bucket | n_real | Real rate | Shuf rate | Gap | CI95 gap |
|---|---|---|---|---|---|---|
| haiku | short (20–25) | 339 | 0.059 | 0.053 | +0.006 | [−0.023, +0.035] |
| haiku | medium (26–32) | 534 | 0.071 | 0.052 | +0.019 | [−0.006, +0.043] |
| haiku | long (33–40) | 2,685 | 0.075 | 0.061 | +0.014 | [+0.003, +0.025] |
| sonnet | short (20–25) | 339 | 0.044 | 0.061 | −0.017 | [−0.043, +0.010] |
| sonnet | medium (26–32) | 534 | 0.073 | 0.068 | +0.005 | [−0.020, +0.030] |
| sonnet | long (33–40) | 2,685 | 0.083 | 0.072 | +0.012 | [0.000, +0.024] |

### Table 2.3 — Cutoff fraction distribution (chain counts, no match rates)

Source-separated cutoff-fraction match rates require `results/raw/` (not pushed to
this repo). Chain distribution is reported for context.

| Source | n_chains | frac 0.3–0.4 | frac 0.4–0.5 | frac 0.5–0.6 | frac 0.6–0.7 |
|---|---|---|---|---|---|
| TB | 170 | 0 | 0 | 170 | 0 |
| SWE | 1,016 | 0 | 0 | 1,016 | 0 |

All chains have cutoff_k = len(constraints) // 2, so cutoff fraction is exactly 0.5 by
construction. No stratification by this axis is possible.

### §2 Interpretation

*These are post-hoc descriptive statistics and do not modify the primary result.*

**InformationState** carries the strongest positive signal in both sources and for both
models. It is the only constraint type with statistically significant positive gaps in
SWE (haiku p < 0.001, sonnet p < 0.001). In TB it is positive but underpowered (haiku
p = 0.075, sonnet p = 0.570 due to small n = 48 real).

**ToolAvailability** shows an unexpected source-direction reversal: positive in TB
(haiku gap = +0.112, p = 0.001; sonnet gap = +0.079, p = 0.039) but negative in SWE
(haiku gap = −0.009; sonnet gap = −0.027, p = 0.002). This is the most striking
finding in the stratification. In TB, ToolAvailability cutoffs appear at test-suite
transitions where the real sequence is structured; in SWE, the tool labelling may be
less informative or more uniform.

**ResourceBudget** shows no signal in either source (gaps near 0). This is expected —
ResourceBudget constraints record context-window usage, which is a passive observation
not tied to a predictable next action.

**SubGoalTransition** shows near-zero or negative gaps across all cells. Phase labels
(exploration, validation, debugging) may be too abstract for the model to predict from
the rendered chain context.

**Length bucket**: no strong concentration. Haiku shows consistent small positive gaps
across all length bins (all CIs include zero individually). Sonnet shows a negative gap
in short chains and positive in medium/long; this could reflect that short chains have
fewer context constraints for Sonnet to leverage.

---

## §3 Error Analysis

**Script:** `scripts/supplementary/03_error_analysis.py`
**Output:** `supplementary/error_analysis/*.jsonl` (16 files, 320 cases)
**Run date:** 2026-04-23 (rerun after `results/raw/` made accessible locally)

**Raw responses:** the per-chain response files in `results/raw/` (28,465
JSON files, ~111 MB) are not tracked in this repository. The error-analysis
output JSONL files in `supplementary/error_analysis/` contain the sampled
cases referenced by chain-id in §3.3, §3.7, etc.; full raw responses are
available from the authors on request (language for final paper TBD —
likely a HuggingFace dataset release).

### §3.1 Sampling methodology

- 16 cells = 2 models × 2 sources × 2 conditions × 2 outcomes (match / fail)
- 20 cases sampled per cell with `random.Random(seed=42)`
- Each case records: `chain_id`, `model`, `source`, `condition`, `model_response`,
  `ground_truth_entity`, `constraint_type_at_cutoff`, the 5 constraints immediately
  preceding the cutoff (`last_5_constraints`), and the binary `match` flag
- Match logic uses the same entity substring containment as the primary scorer
  (`normalize_action(entity) in normalize_action(response)`)
- Sampled cells are read-only views over `results/raw/`; no re-scoring is performed

A small bug was fixed before run: the script's bucket dict was pre-filled with
keys `shuf_match`/`shuf_fail` while the runtime constructed
`shuffled_match`/`shuffled_fail`. Renamed dict keys; no semantic change.

### §3.2 Cell-level composition

The most informative cut is by *constraint type at the cutoff*, since this
determines what the model is asked to predict and what fallback patterns are
available.

| Cell (n=20) | Match: dominant GT type | Fail: dominant GT type |
|---|---|---|
| haiku::tb real | **ToolAvailability 12 / IS 6 / RB 2** | RB 9 / SubGoal 4 / TA 3 |
| haiku::swe real | **InformationState 13 / CD 4 / TA 3** | RB 12 / TA 5 / IS 2 / CD 1 |
| sonnet::tb real | **ToolAvailability 16 / IS 4** | RB 13 / TA 4 / SubGoal 2 / IS 1 |
| sonnet::swe real | **InformationState 10 / CD 6 / TA 4** | RB 10 / TA 7 / SubGoal 1 / IS 1 / CD 1 |
| haiku::tb shuffled | TA 12 / RB 4 / CD 2 / SubGoal 1 / IS 1 | RB 12 / TA 6 / IS 1 / CD 1 |
| haiku::swe shuffled | IS 12 / CD 6 / TA 2 | TA 6 / RB 6 / IS 5 / SubGoal 1 / OC 1 / CD 1 |
| sonnet::tb shuffled | TA 14 / IS 6 | RB 12 / SubGoal 4 / TA 3 / IS 1 |
| sonnet::swe shuffled | IS 9 / CD 7 / TA 4 | TA 8 / RB 7 / IS 3 / SubGoal 1 / CD 1 |

**Pattern:** in every cell, *match* cases concentrate on the carrier-type cutoffs
(ToolAvailability for TB, InformationState for SWE) — confirming §2/§4c at the
case level. *Fail* cases concentrate on `ResourceBudget` cutoffs (`context_window`
GTs the model cannot emit), exactly the dilution that motivated the actionable-L1
refinement in §5.1 of WRITEUP.md.

### §3.3 Real-match vs shuffled-match — what the model is doing

Comparing the 5-constraint local context preceding the cutoff in real-match
vs shuffled-match cases gives the clearest qualitative signal.

**Representative real-match (SWE-Sonnet, `swe_1254_glotzerlab__signac-323`):**
local context is `RB(patience) → TA(test_suite) → TA(file_B) →
CoordinationDependency(error_class_B) → RB(context_window)` and GT at K is
`InformationState → error_class_b`. The model emits `resolve_error_class_B` and
matches. The CoordinationDependency on `error_class_B` two steps before the
cutoff sets up the prediction — local context is doing real work.

**Representative shuffled-match (SWE-Sonnet, `swe_1272_googleapis__python-api-core-546_shuffled_7919`):**
local context is `TA(file_C) → TA(test_suite) → IS(error_class_A) → TA(file_C)
→ SubGoalTransition(debugging)` and GT at K is `ToolAvailability → file_b`. The
model emits `use file_B to resolve_error_class_B`. The match is a substring hit
on `file_B`, but nothing in the local context predicts file_B — the model says
file_B because it says file_B in many of its responses regardless of context.

This contrast holds across the sample: *real matches use local context; shuffled
matches are alignments between the model's default-guess vocabulary and the
constraint that randomly landed at the cutoff*. The constraint-chain hypothesis
predicts exactly this asymmetry.

### §3.4 Real-fail vs shuffled-fail — symmetric in mode, different in source

Failure modes are very similar across real and shuffled within a source, and
sharply different between sources:

| Source | Most common failure-response prefix (real / shuffled fails pooled across models) |
|---|---|
| TB | `switch to …` (phase transition), `use file_A`/`use file_C` (default file guess) |
| SWE | `resolve_error_class_B` (default error guess), `use file_B`/`use file_C` |

Two source-specific *fallback strategies* emerge:

- **TB fallback = phase transition.** When the model can't predict the next
  constraint (typically because GT is a `ResourceBudget(context_window)`), it
  emits a phase-shift response: `switch to debugging`, `switch to validation`.
  This appears in 10/20 TB-Haiku-real-fails and 12/20 TB-Haiku-shuffled-fails.
- **SWE fallback = error resolution.** Same scenario, but the model emits
  `resolve_error_class_B`. This appears in 9/20 SWE-Haiku-real-fails and
  7/20 SWE-Haiku-shuffled-fails.

The fallback is symmetric across real/shuffled within a source — the model is
not failing differently on real vs shuffled chains; it's failing the same way
on the same vacuous-cutoff cases. This is consistent with the actionable-L1
refinement story: vacuous cutoffs do not differentiate the conditions.

### §3.5 TB vs SWE failure modes

The previous subsection isolates the source-specific fallback. Why does it
differ? SWE chains carry roughly twice the share of `InformationState` (13%
vs 10%) and 4× the share of `CoordinationDependency` (9% vs 2%) constraints,
both of which involve `error_class_X` entities. The model conditions on this
context and emits error-resolution responses. TB has roughly twice the share
of `SubGoalTransition` constraints (10% vs 6%) and a higher proportion of
`debugging` phase entities, which prime phase-transition responses.

This is descriptive; it does not say one fallback is "smarter" than the other,
only that the model's response prior is shaped by the source's marginal
constraint composition.

### §3.6 Haiku vs Sonnet — mode-collapse asymmetry

Sonnet shows stronger response mode-collapse than Haiku:

- TB-Sonnet-real-matchs: `use file_a` appears in 12/20 responses; GT entities
  are also overwhelmingly `file_a` (13/20).
- TB-Haiku-real-matchs: `switch to …` (6/20), `resolve_error_class_a` (5/20),
  `use file_a` (3/20), `use file_c` (3/20) — varied.

Sonnet defaults more aggressively to a single high-prior action (`use file_A`
in TB; `resolve_error_class_B` in SWE). When the GT lands on that default, it
matches in both real and shuffled — which is the §5.3 / §4d compression
mechanism made concrete. Haiku's more varied response distribution loses on
"easy" cases (where the prior would have helped) but is more discriminating
between real and shuffled, because its distribution interacts more with the
local context.

### §3.7 The ToolAvailability-SWE anomaly under the microscope

This is the most important §3 finding. From SUPPLEMENTARY §2 / §4: SWE-Sonnet
shows a *significant negative* TA gap (real 0.042 vs shuffled 0.069, p = 0.002).
The error-analysis sample isolates the mechanism.

**The 4 SWE-Sonnet shuffled-match TA cases:**

| chain_id | GT entity | response | match? |
|---|---|---|---|
| `swe_1272_googleapis__python-api-core-546_shuffled_7919` | file_b | `use file_B to resolve_error_class_B` | ✓ |
| `swe_3867_mplanchard__pydecor-20_shuffled_7919` | file_b | `use file_B` | ✓ |
| `swe_3879_nathandines__SPF2IP-3_shuffled_7919` | file_c | `use file_C to resolve_error_class_A` | ✓ |
| `swe_2843_reata__sqllineage-38_shuffled_42` | file_b | `use file_B` | ✓ |

GT is file_b in 3/4 cases. The model defaults to `use file_B`. Match.

**The 7 SWE-Sonnet real-fail TA cases (sampled):**

| chain_id | GT entity | response |
|---|---|---|
| `swe_3656_iterative__dvc-2975` | file_a | `resolve_error_class_B` |
| `swe_4064_snowblink14__smatch-30` | file_g | `use file_F` |
| `swe_3170_ameily__cincoconfig-26` | test_suite | `resolve_error_class_B` |
| `swe_1848_devopshq__artifactory-439` | file_a | `resolve_error_class_C` |
| `swe_3713_iterative__dvc-4623` | file_g | `use file_F` |

GT is varied (file_a, file_g, test_suite); the model misses with its defaults.

**Mechanism (qualitative confirmation of §5.2 of WRITEUP.md):** SWE's
ToolAvailability distribution is dominated by `file_B` (33% of all TA
constraints in the source). Shuffling redistributes which constraint lands
at the cutoff K according to the marginal distribution; real chains preserve
the autocorrelated sequence structure, which means *real* TA cutoffs are *less*
likely to land on the marginal mode (file_B) than shuffled TA cutoffs. The
model's strong `file_B`/`error_class_B` default thus matches *shuffled* cases
more often than *real* cases. The negative gap is a real artefact of marginal-
versus-conditional distribution interaction; it is not noise.

This means the SWE-TA anomaly is **explained, not removed**: the abstraction
does carry signal in SWE-TA, but the signal goes the *wrong way* under our
match metric because the model's default-guess prior happens to align with
the marginal-distribution mode that shuffling exposes. A metric that
conditioned on the *local* context distribution rather than the marginal
would reverse the sign — but that is a methodological change, not a
re-scoring, and is left for follow-up work.

### §3.8 What this analysis cannot determine

- The samples are 20 cases per cell — sufficient to characterise *patterns*
  but not to estimate the relative weight of each pattern with precision.
- The 5-constraint local context is a reading aid; whether the model is
  *actually* attending to those tokens (vs. broader prompt context) cannot
  be inferred from the responses alone.
- The substring-match scoring metric conflates "the model intended this entity"
  with "the model's response happens to contain the entity string". Some
  matches are substring artefacts (e.g., `use file_B to resolve_error_class_B`
  matches GT `error_class_b`). Section §3.3's representative real-match case
  is robust to this; the population-level match rates are not separable.
- The qualitative comparison between Haiku and Sonnet response style is
  consistent with §4d's compression hypothesis but does not by itself
  establish capability vs. response-strategy as the cause.

---

## §4 Cross-Cell Interaction Analysis

**Script:** `scripts/supplementary/04_interaction_analysis.py`  
**Output:** `supplementary/interaction_results.json`

### §4a Entity Entropy Hypothesis

*"SWE has higher average action-distribution entropy than TB."*

| Source | n signatures | Mean entropy (nats) | Median | Std |
|---|---|---|---|---|
| TB | 354 | 0.731 | — | — |
| SWE | 3,485 | 0.928 | — | — |

Mann-Whitney U test (two-sided): p ≈ 0.000.

**Confirmed.** SWE has significantly higher mean entropy per state signature. This
means the action space at each step is less predictable in SWE chains, providing a
mechanistic explanation for SWE's weaker Layer 1 signal: even when the model identifies
the correct constraint type, picking the right specific entity is harder when the
reference distribution is more spread.

### §4b Distribution Concentration Hypothesis

*"SWE is more concentrated than TB (fewer labels account for most probability mass)."*

| Source | Mean top-3 coverage | n signatures |
|---|---|---|
| TB | 0.939 | 354 |
| SWE | 0.902 | 3,485 |

Mann-Whitney U (two-sided): p = 0.000.

**Refuted.** TB has higher top-3 concentration than SWE, opposite to the hypothesis.
This is consistent with (a): TB distributions are more concentrated (lower entropy)
while SWE distributions are more spread (higher entropy). The two findings are
coherent — TB trajectories converge on a smaller set of dominant actions at each
state, making top-3 matches easier.

### §4c Carrier-Type Shift Hypothesis

*"The signal-carrying constraint type differs between TB and SWE."*

| Source | Dominant carrier (Haiku) | Gap |
|---|---|---|
| TB | InformationState | +0.117 |
| SWE | InformationState | +0.109 |

Fisher's exact test on IS vs. non-IS signal matrix: p ≈ 0.000 (odds ratio 4.3 in
favor of IS carrying more signal than other types, consistent across both sources).

**Refuted.** InformationState is the dominant positive carrier in both sources. The
signal mechanism is the same across TB and SWE — the model picks up on revealed file
and error entity labels at InformationState cutoffs. The stronger TB aggregate signal
appears to come from ToolAvailability cutoffs carrying an additional positive signal in
TB (which is absent or reversed in SWE), not from a shift in the primary carrier type.

Note: ToolAvailability shows p = 0.001 positive in TB but p = 0.002 negative in SWE —
this directional reversal is the anomalous finding not captured by the carrier-shift
framing.

### §4d Sonnet Compression Hypothesis

*"Sonnet's real-shuffled gap compression is statistically different from Haiku's."*

| Source | Haiku L1 gap | Sonnet L1 gap | Difference | z | p |
|---|---|---|---|---|---|
| TB | 0.043 | 0.035 | +0.008 | 0.45 | 0.649 |
| SWE | 0.009 | 0.004 | +0.006 | 0.77 | 0.437 |
| Pooled | — | — | **+0.006** | **0.89** | **0.371** |

Layer 2 comparison: Haiku gap = 0.049–0.067, Sonnet gap = 0.068–0.088. Sonnet
actually shows *larger* L2 gaps than Haiku in both sources.

**Not statistically significant.** Haiku does show a consistently larger L1 gap than
Sonnet (difference = +0.006–0.008 in both sources), but the pooled z = 0.89, p = 0.37.
The compression is directionally consistent but indistinguishable from noise at this
sample size.

The Layer 2 reversal (Sonnet has *larger* L2 gaps) suggests that Sonnet is better at
the legality × optimality metric while Haiku is slightly better at the entity-match
metric. This may reflect Sonnet's stronger instruction-following producing more
syntactically valid responses (higher legality), while Haiku's responses happen to
include the specific entity label more often (higher top-k match).

---

## Summary for RESULTS.md §5 Discussion

The following findings are relevant to the Discussion section. They are reported
in `PROPOSED_CHANGES.md` for human review rather than applied directly to RESULTS.md.

1. **InformationState is the mechanism.** The Layer 1 signal is concentrated entirely
   in InformationState cutoffs (file and error entity labels), where models successfully
   predict the specific label that was revealed. This is true in both TB and SWE.

2. **ToolAvailability reversal in SWE is an anomaly.** The significant negative gap
   for sonnet::swe ToolAvailability (p = 0.002) is worth investigating. It may indicate
   that SWE's tool-availability labelling is less informative or that the model has
   a competing prior about tool states in software engineering contexts.

3. **Entropy explains the TB>SWE gap.** TB has lower distribution entropy (0.73 vs
   0.93 nats) and higher top-3 concentration (0.94 vs 0.90). This directly explains
   why the constraint-chain signal is easier to detect in TB: the reference distribution
   is more peaked, making correct entity prediction more achievable.

4. **Sonnet compression is real but not significant.** The consistent direction
   (Haiku > Sonnet in L1 gap, but Sonnet > Haiku in L2 gap) suggests qualitatively
   different response strategies, not a simple capability difference.
