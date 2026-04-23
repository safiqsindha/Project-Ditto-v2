# Corrected Scoring Analysis

**Date of methodological review:** 2026-04-23  
**Status:** FOR CO-AUTHOR REVIEW — Primary results (RESULTS.md) NOT YET UPDATED

This document reports corrected scoring for four methodological issues identified
in `src/scorer.py`. The original scorer and original `results/scored.json` are
unchanged. New artifacts are `src/scorer_corrected.py` and
`results/scored_corrected.json`.

---

## Issues Identified

### Issue 1 — Unpaired test for Layer 1 (binary outcome)

**Original:** Two-sample proportion test (z-test) comparing real match rates vs
shuffled match rates as independent samples.

**Problem:** The data is structurally paired. Each real chain has three
corresponding shuffled variants with the same base chain content. The real and
shuffled evaluations for the same (chain_id, eval_seed) are not independent;
they share the same sequence of constraints, just reordered. Two-sample tests
ignore this correlation and may over- or under-estimate significance depending
on the direction of within-pair correlation.

**Correction:** McNemar's test for paired binary outcomes (with continuity
correction). Continuity-corrected statistic: χ² = (|b − c| − 1)² / (b + c),
where b = discordant pairs real-match, c = discordant pairs shuffled-match.

---

### Issue 2 — Unpaired test for Layer 2 (continuous outcome)

**Original:** Welch's t-test treating real and shuffled score lists as
independent samples.

**Problem:** Same pairing structure as Issue 1. Welch's t-test ignores within-
pair correlation, making it less efficient than a paired test when correlation
is positive.

**Correction:** Paired t-test (scipy.stats.ttest_rel) on aligned
(real_score, shuffled_score) pairs.

---

### Issue 3 — No (chain_id, seed) alignment

**Original:** Real and shuffled evaluation lists were built in parallel but
without enforcing that each real evaluation had a corresponding shuffled
evaluation at the same (chain_id, eval_seed). A result file that failed for
one condition but not the other would introduce unmatched samples.

**Correction:** Before scoring, all raw results are indexed by
(base_chain_id, model, eval_seed). Pairs are formed only where both a real
evaluation and ≥1 shuffled evaluation succeeded for the same (chain_id,
eval_seed). Missing pairs are reported.

**Finding:** 0 pairs were excluded. All 28,464 result files were present and
paired correctly. No alignment issue was present in the actual data.

---

### Issue 4 — No multiple-comparisons correction

**Original:** p-values for all breakdown cells were tested individually at
α = 0.05 without accounting for the many parallel tests performed (per-model,
per-source, per-config, and interactions).

**Correction:** Bonferroni correction applied at two levels:
1. **Primary (4-cell) Bonferroni:** family = {haiku::tb, haiku::swe,
   sonnet::tb, sonnet::swe} using layer1_actionable as the primary metric.
   Corrected α = 0.05 / 4 = 0.0125. Corrected p-values = uncorrected × 4.
2. **Full breakdown Bonferroni:** family = all cells in per_model + 
   per_model_per_source + per_model_per_config + per_model_per_config_per_source
   (24 cells total). Reported in `results/scored_corrected.json` under
   `bonferroni_full_breakdown`. Not discussed in detail below (no cell passes
   full-breakdown correction at gap ≥ 0.05 threshold).

---

## Side-by-Side Comparison — Primary 4 Cells

### Layer 1 (all cutoffs) — Original z-test vs Corrected McNemar

Gaps are **identical** (same data, same means). Only the test statistic and
p-value change.

| Cell | Orig gap | Orig z | Orig p | Corr gap | Corr χ² | Corr p | Significance change? |
|------|----------|--------|--------|----------|---------|--------|----------------------|
| haiku::tb  | 0.0425 | 3.663  | 0.0002 | 0.0425 | 22.63 | <0.0001 | Stronger (both significant) |
| haiku::swe | 0.0093 | 1.817  | 0.0692 | 0.0093 |  7.97 |  0.0047 | **CHANGES: non-sig → sig** |
| sonnet::tb | 0.0346 | 2.689  | 0.0072 | 0.0346 | 14.94 | 0.0001  | Stronger (both significant) |
| sonnet::swe| 0.0035 | 0.644  | 0.5197 | 0.0035 |  0.96 |  0.3269 | No change (both non-sig) |

*Sample sizes (corrected): n_pairs per cell = n_shuffled in original (1530 for TB, 9144 for SWE).*

**Key observation:** haiku::swe changes from p = 0.069 (not significant) to
p = 0.005 (significant) under McNemar. McNemar is more powerful when the
positive within-pair correlation makes discordant pairs asymmetric in the
real-favoring direction. However, the gap (0.0093) remains below the
pre-registered gap ≥ 0.05 threshold, so this significance change does not
affect the primary publishable criterion.

With Bonferroni (×4) on "all cutoffs" Layer 1: haiku::tb bonf_p < 0.001 and
sonnet::tb bonf_p = 0.0004 remain significant; haiku::swe bonf_p = 0.019
becomes significant. None of these three cells clear gap ≥ 0.05, so none meet
the full pre-registered threshold.

---

### Layer 1 (actionable cutoffs only) — Original z-test vs Corrected McNemar

**⚠️ FLAG FOR CO-AUTHOR REVIEW — DRAMATIC ESTIMAND DIFFERENCE ⚠️**

The corrected paired test produces substantially larger gaps than the original
for this metric. This is NOT a bug; it reflects a fundamental difference in
what the two analyses measure. Co-authors must decide how to interpret this.

| Cell | Orig gap | Orig z | Orig p | Corr gap | Corr χ² | Corr p | Bonf p (×4) | Meets threshold? |
|------|----------|--------|--------|----------|---------|--------|-------------|------------------|
| haiku::tb  | 0.066 | 2.752 | 0.0059 | 0.115 | 55.71 | <0.0001 | <0.0001 | **YES** (gap≥0.05, bonf p<0.05) |
| haiku::swe | 0.014 | 1.706 | 0.0879 | 0.024 | 22.05 | <0.0001 | <0.0001 | No (gap<0.05) |
| sonnet::tb | 0.031 | 1.115 | 0.2649 | 0.115 | 53.41 | <0.0001 | <0.0001 | **YES** (gap≥0.05, bonf p<0.05) |
| sonnet::swe| 0.007 | 0.749 | 0.4539 | 0.026 | 20.01 | <0.0001 | <0.0001 | No (gap<0.05) |

*Original sample sizes: n_real=258/1467, n_shuffled=549/4776 (TB/SWE).*
*Corrected sample sizes: n_pairs=774/4401 (TB/SWE) — 258×3 shuffled variants for TB.*

**Why the gaps are larger in the corrected analysis:**

The original "actionable" Layer 1 compared two separately filtered lists:
- Real: evaluations where the **real chain's** constraint at cutoff_k is
  actionable (ToolAvailability, InformationState, or SubGoalTransition).
- Shuffled: evaluations where the **shuffled chain's** constraint at cutoff_k
  is actionable (a different filter — it only includes shuffled evaluations
  where shuffling happened to place an actionable constraint at position k).

The corrected paired test compares:
- Real: evaluations where the **real chain's** constraint at cutoff_k is
  actionable (same filter as original real side).
- Shuffled: for the **same (chain, eval_config)** pairs, the shuffled chain's
  outcome at position k — regardless of what constraint the shuffled chain has
  there.

Because shuffling randomizes constraint order, when the real chain has an
actionable constraint at k (e.g., ToolAvailability → "file_b"), the shuffled
chain at position k typically has a **non-actionable** constraint (e.g.,
ResourceBudget → "context_window"). The model cannot predict "context_window",
so the shuffled match rate at these positions is near zero.

The original "shuffled actionable" filtered this out — it only kept shuffled
evaluations where the shuffled chain happened to have an actionable constraint
at k. This created a higher shuffled baseline but also a selection bias (it
selected a non-representative subset of shuffled evaluations).

The corrected paired test uses a lower shuffled baseline (the true counterfactual:
if you took this exact chain and shuffled it, how well would the model do at
position k?). This larger gap (0.115 vs 0.066) is real signal, but the
interpretation differs from the original.

**Numerical check (haiku::tb actionable):**
- Original: real_rate=0.1589, shuffled_rate=0.0929, gap=0.066
- Corrected: real_rate=0.1589 (unchanged), shuffled_rate=0.0439, gap=0.115
- The real rate is identical; only the shuffled baseline changes.
- Shuffled rate drops from 0.093 (shuffled-actionable-only) to 0.044 (all
  shuffled at real-actionable positions). The ~0.044 rate when shuffled chains
  have a mix of actionable and non-actionable constraints at those positions is
  consistent with: ~40% of shuffled constraints being actionable × 0.093
  ≈ 0.037, plus some near-zero contribution from non-actionable → observed
  0.044.

**Flagged for co-author decision:**
1. The corrected paired estimand (real-actionable positions vs. shuffled
   counterfactual at same positions) is arguably more appropriate for testing
   the hypothesis: "does real constraint ordering help prediction at the
   positions where it should matter?"
2. The original estimand (real-actionable vs. shuffled-actionable) is less
   directly comparable because the shuffled baseline is a biased subsample.
3. A hybrid approach — using only pairs where BOTH real and shuffled chains
   have actionable constraints at k — would produce a fairer same-type
   comparison but would select a very small biased subset of pairs.
4. The corrected analysis STRENGTHENS the headline finding (both TB cells now
   clear gap≥0.05 even after Bonferroni), but this strengthening requires the
   interpretive caveat above.

---

### Layer 2 (coupled score) — Original Welch's t vs Corrected Paired t-test

Gaps are **identical** (same mean differences). The paired t-test is more
efficient, yielding larger t-statistics.

| Cell | Orig gap | Orig t | Orig p | Corr gap | Corr t | Corr p |
|------|----------|--------|--------|----------|--------|--------|
| haiku::tb  | 0.0488 |  5.451 | <0.001 | 0.0488 |  8.310 | <0.0001 |
| haiku::swe | 0.0671 | 24.874 | <0.001 | 0.0671 | 37.686 | <0.0001 |
| sonnet::tb | 0.0884 |  9.809 | <0.001 | 0.0884 | 17.015 | <0.0001 |
| sonnet::swe| 0.0684 | 24.807 | <0.001 | 0.0684 | 38.669 | <0.0001 |

All four cells remain significant at p < 0.0001 under both tests. No
significance status changes. The paired test is more powerful (higher t-stats)
due to positive within-pair correlation between real and shuffled Layer 2 scores.

---

## Pre-registered Primary Criterion

**Criterion:** At least one primary cell clears gap ≥ 0.05 (Layer 1 actionable)
AND p < 0.05, with Bonferroni correction across the 4 primary cells.

| | Original (no Bonferroni correction) | Corrected (with Bonferroni ×4) |
|-|--------------------------------------|-------------------------------|
| haiku::tb  | MET (gap=0.066, p=0.006) | MET (gap=0.115, bonf_p<0.0001) |
| sonnet::tb | NOT MET (gap=0.031, p=0.265) | **NOW MET** (gap=0.115, bonf_p<0.0001) |

**Conclusion:** The pre-registered minimum publishable criterion is **MET** under
corrected scoring with Bonferroni correction. This is the same conclusion as the
original (which also had haiku::tb meeting the threshold), but is now also met
by sonnet::tb, which was not significant in the original.

However, this conclusion carries the estimand caveat above. Co-authors must
decide whether the corrected paired test's "actionable" estimand is an
appropriate operationalization of the pre-registered metric, or whether the
"all cutoffs" metric should be used (which does NOT clear gap≥0.05 in either
the original or corrected analysis).

---

## Pair Alignment Report (Issue 3)

| Metric | Count |
|--------|-------|
| Total raw results loaded | 28,464 |
| Total aligned pairs built | 21,348 |
| Real chains found | 1,186 (170 TB + 1,016 SWE) |
| Pairs excluded: missing real eval | 0 |
| Pairs excluded: missing shuffled eval | 0 |
| Base chains with no shuffled variant | 0 |

**Expected pair count:** 1,186 chains × 3 eval configs × 3 shuffle seeds = 10,674
pairs per model × 2 models = 21,348 total. Observed: 21,348. ✓

No alignment issues were present in the actual data. All 28,464 evaluations
were properly paired. This confirms that Issue 3 was not causing any spurious
misalignment in the original results.

---

## Summary: What Changes Under Corrected Scoring

| Finding | Original | Corrected | Direction |
|---------|----------|-----------|-----------|
| Pair alignment issues | Not checked | 0 pairs excluded | No change to results |
| L1(all) gaps | Unchanged | Unchanged | No change |
| L1(all) p-values | Two-sample | McNemar (paired) | Most cells more significant |
| haiku::swe L1(all) significance | p=0.069 (NS) | p=0.005 (S) | **Changes to significant** (gap still <0.05) |
| sonnet (pooled) L1(all) | p=0.112 (NS) | p=0.015 (S) | **Changes to significant** |
| L1(act) gaps | 0.066/0.031 (TB) | 0.115/0.115 (TB) | **Dramatically larger** (see estimand note) |
| L1(act) significance | haiku::tb p=0.006 | all 4 cells p<0.0001 | All become significant |
| sonnet::tb meets threshold | NO (gap<0.05) | YES (gap=0.115) | **Changes to MET** (with estimand caveat) |
| L2 gaps | Unchanged | Unchanged | No change |
| L2 p-values | All p<0.0001 | All p<0.0001 | No change |
| Pre-reg min criterion (any cell: gap≥0.05, p<0.05 Bonf) | MET (haiku::tb) | MET (haiku::tb + sonnet::tb) | Strengthens |
| Strong-positive (gap≥0.08, p<0.01) | NOT MET | TB cells approach (gap=0.115, but estimand caveat) | Conditional on co-author decision |

**Are there findings that weaken under corrected scoring?** No. All changes are
in the direction of equal or stronger significance. The Bonferroni correction
is absorbed by the already-small p-values from McNemar. The "all cutoffs" L1
gaps are unchanged, and the Bonferroni correction on those doesn't flip any
previously-meeting cell (none met gap≥0.05 in the original).

---

## Items Requiring Co-Author Decision

1. **Actionable L1 estimand (HIGH PRIORITY):** The corrected paired test's
   "actionable" gaps (0.115 for TB) are significantly larger than the original's
   (0.066 for haiku::tb) due to the different shuffled baseline. Co-authors must
   decide:
   - Whether the corrected estimand (real-actionable positions vs. shuffled
     counterfactual at same positions) is the right primary metric.
   - Whether the original estimand (separately filtered real and shuffled
     actionable samples) is more appropriate despite being unpaired.
   - Whether the "all cutoffs" Layer 1 metric should be used instead, as it
     does not have this ambiguity (gaps are identical in both analyses).

2. **Additional significant cells (MEDIUM PRIORITY):** Under corrected scoring,
   haiku::swe L1(all) becomes significant (p=0.005) and sonnet (pooled) L1(all)
   becomes significant (p=0.015). Neither meets gap≥0.05, but both are now
   statistically significant effects. Whether these are worth reporting is a
   judgment call.

3. **Sonnet::TB now meets criterion (MEDIUM PRIORITY):** Under corrected
   actionable L1 with Bonferroni, sonnet::tb meets the pre-registered threshold
   (gap=0.115, bonf_p<0.0001). However, this depends on the estimand decision
   in item 1 above.

4. **RESULTS.md update:** PRIMARY RESULTS NOT YET UPDATED. The numbers in
   RESULTS.md remain the original scorer's output. Co-authors should review this
   document before deciding whether and how to update RESULTS.md.

---

## Artifacts

| File | Description |
|------|-------------|
| `src/scorer_corrected.py` | New corrected scorer (original `src/scorer.py` unchanged) |
| `results/scored_corrected.json` | Corrected scoring output with McNemar, paired t, Bonferroni |
| `CORRECTED_SCORING.md` | This document |

Corrected scorer command (for reproducibility):
```bash
python3.11 -m src.scorer_corrected \
  --results results/raw/ \
  --dist-tb data/reference_tb.pkl \
  --dist-swe data/reference_swe.pkl \
  --chains-real chains/real/ \
  --chains-shuffled chains/shuffled/ \
  --out results/scored_corrected.json
```
