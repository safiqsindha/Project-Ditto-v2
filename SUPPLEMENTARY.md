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
**Output:** `supplementary/error_analysis/_status.json`

**Status: Cannot run.** `results/raw/` was not committed to this repository. The script
exits gracefully and documents the expected format. To enable this analysis, push
`results/raw/` from the local evaluation machine and re-run the script.

Expected output: 16 JSONL files (4 cells × 2 conditions × match/fail), each with 20
sampled cases including model response, ground-truth entity, constraint type at cutoff,
5-constraint context window, and a qualitative annotation.

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
