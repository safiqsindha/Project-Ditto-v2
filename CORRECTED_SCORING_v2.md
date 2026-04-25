# Corrected Scoring Analysis — Version 2

**Date:** 2026-04-23  
**Status:** FOR CO-AUTHOR REVIEW — PRIMARY RESULTS (RESULTS.md) NOT YET UPDATED  
**Supersedes:** CORRECTED_SCORING.md for the recommendation on which scorer to adopt

---

## 1. Background: Three Scorer Versions

Three versions of the scorer exist. They are additive: no file has been modified.

| File | Tests | Actionable filter | Bonferroni |
|------|-------|------------------|-----------|
| `src/scorer.py` | z-test (L1), Welch's t (L2), **unpaired** | Each condition filtered independently by its own chain | No |
| `src/scorer_corrected.py` | McNemar (L1), paired t (L2), **paired** | REAL chain must be actionable only | Yes (×4) |
| `src/scorer_corrected_v2.py` | McNemar (L1), paired t (L2), **paired** | BOTH real AND shuffled must be actionable | Yes (×4) |

### Why a v2?

`scorer_corrected.py` fixed the statistical tests (unpaired → paired) but also changed the
actionable-subset filter rule: it included pairs where the real chain is actionable regardless
of whether the shuffled chain is. This inflated the haiku::tb gap from 0.066 to 0.115.

`VERIFICATION_REPORT.md` Check 3 documented the mechanism: 59.7% of the first correction's
774 "actionable" pairs had a non-actionable constraint at cutoff\_k for the shuffled chain.
These pairs have near-zero shuffled match rates (ResourceBudget: 1.1%, OptimizationCriterion:
0.0%, CoordinationDependency: 0.0%), artificially depressing the shuffled baseline and
inflating the gap.

`scorer_corrected_v2.py` implements the methodologically correct version:
**paired tests + original filter rule** (both real AND shuffled must be actionable).
This is an apples-to-apples comparison — both sides of each pair are measured on the same
type of constraint (actionable) at the cutoff position.

---

## 2. Investigation Note: Expected Gap vs Observed Gap for haiku::tb

The task specification expected the v2 haiku::tb actionable gap to be "approximately 0.066,
matching the original scorer's number." The observed value is **0.0801**.

**This is not a bug.** The discrepancy is documented in VERIFICATION_REPORT.md Check 3 which
explicitly reported the "both-actionable" paired subset:

> Also actionable (ToolAvail / InfoState / SubGoal) | **312 (40.3%)** | 0.0929 | **0.0801**

The reason the paired gap (0.0801) differs from the unpaired gap (0.066):

| Quantity | Original (unpaired) | v2 (paired, both-actionable) |
|---------|---------------------|------------------------------|
| n real | 258 independent results | 312 pairs (real side) |
| n shuffled | 549 independent results | 312 pairs (shuffled side) |
| real\_rate | 0.1589 | **0.1731** |
| shuffled\_rate | **0.0929** | **0.0929** |
| gap | 0.066 | **0.0801** |

The shuffled rate (0.0929) is identical — confirming the shuffled side is consistent.
The real rate differs (0.1589 vs 0.1731) because the 312 "both-actionable" pairs are a
**selected subset** of the 258 real evals (each appearing 1–3 times, paired with whichever
shuffled variants are also actionable). Real evals in chains where the shuffled variant is
also actionable happen to have a slightly higher match rate — a mild selection effect.

This is the expected behaviour of paired tests on a filtered subset. The 0.0801 is the
correct estimand for "paired, both-actionable." The 0.066 was the unpaired estimate and
cannot be reproduced by a paired analysis on the same filter.

---

## 3. Primary 4 Cells — Layer 1 Actionable (McNemar)

### 3a. Side-by-side: all three scorers

| Cell | **Original** | | | **First correction** | | | **Second correction (v2)** | | |
|------|---|---|---|---|---|---|---|---|---|
| | gap | p (uncorr) | n (real / shuffled) | gap | McNemar p | Bonf p (×4) | gap | McNemar p | Bonf p (×4) |
| haiku::tb | 0.066 | 0.0059 | 258 / 549 | 0.115 | <0.0001 | <0.0001 | **0.0801** | 0.0029 | **0.0116** |
| haiku::swe | 0.014 | 0.0879 | 1467 / 4776 | 0.024 | <0.0001 | <0.0001 | 0.0053 | 0.4360 | 1.0000 |
| sonnet::tb | 0.031 | 0.2649 | 258 / 549 | 0.115 | <0.0001 | <0.0001 | 0.0545 | 0.0611 | 0.2444 |
| sonnet::swe | 0.007 | 0.4539 | 1467 / 4776 | 0.026 | <0.0001 | <0.0001 | −0.0042 | 0.5949 | 1.0000 |

Notes on n\_pairs:
- Original: independent pools (n\_real ≠ n\_shuffled), no pair alignment
- First correction: n\_pairs = 774 (TB) / 4401 (SWE) — includes pairs where shuffled is non-actionable
- Second correction: n\_pairs = **312 (TB)** / **2850 (SWE)** — restricted to both-actionable pairs

### 3b. Pre-registered threshold: gap ≥ 0.05 AND Bonferroni p < 0.05

| Cell | Original | First correction | Second correction (v2) |
|------|----------|-----------------|------------------------|
| haiku::tb | ✓ MET (gap=0.066, p=0.006, no Bonf) | ✓ MET (gap=0.115, bonf\_p<0.0001) | ✓ **MET** (gap=0.0801, bonf\_p=0.0116) |
| haiku::swe | ✗ not met | ✗ not met (gap<0.05) | ✗ not met |
| sonnet::tb | ✗ not met (gap<0.05) | ✓ MET (gap=0.115, bonf\_p<0.0001) | ✗ not met (p=0.244) |
| sonnet::swe | ✗ not met | ✗ not met (gap<0.05) | ✗ not met |

**Pre-registered minimum publishable criterion** (any primary cell meets gap ≥ 0.05, Bonf p < 0.05):

| Version | Met? |
|---------|------|
| Original | Yes (haiku::tb) — no Bonferroni applied |
| First correction | Yes (haiku::tb and sonnet::tb) |
| **Second correction (v2)** | **Yes (haiku::tb only)** |

The minimum criterion is met under all three versions. The number of passing cells differs.

---

## 4. Layer 1 All Cutoffs

The all-cutoffs Layer 1 analysis is IDENTICAL between scorer\_corrected.py and
scorer\_corrected\_v2.py (the filter change only affects the actionable subset). It is
reproduced here for completeness.

| Cell | Original gap | Original z / p | Corrected gap | McNemar χ² / p | n\_pairs |
|------|-------------|---------------|--------------|----------------|---------|
| haiku::tb | 0.0425 | z=3.66, p=0.0002 | 0.0425 | χ²=22.63, p<0.0001 | 1530 |
| haiku::swe | 0.0093 | z=1.82, p=0.0692 | 0.0093 | χ²=7.97, p=0.0047 | 9144 |
| sonnet::tb | 0.0346 | z=2.69, p=0.0072 | 0.0346 | χ²=14.94, p=0.0001 | 1530 |
| sonnet::swe | 0.0035 | z=0.64, p=0.5197 | 0.0035 | χ²=0.96, p=0.3269 | 9144 |

No cell clears gap ≥ 0.05 in either analysis. haiku::swe changes from non-significant
(z-test, p=0.069) to significant (McNemar, p=0.005); the gap (0.0093) remains below threshold.

---

## 5. Layer 2 (Coupled Score) — Paired t-test

Layer 2 gaps are **identical** across all three scorer versions (same means, different tests).
The paired t-test is more powerful than Welch's (same data, better accounts for within-pair
correlation).

| Cell | Original gap | Original t / p | Paired t / p | n\_pairs |
|------|-------------|---------------|-------------|---------|
| haiku::tb | 0.0488 | t=5.45, p<0.001 | t=8.31, p<0.0001 | 1530 |
| haiku::swe | 0.0671 | t=24.87, p<0.001 | t=37.69, p<0.0001 | 9144 |
| sonnet::tb | 0.0884 | t=9.81, p<0.001 | t=17.02, p<0.0001 | 1530 |
| sonnet::swe | 0.0684 | t=24.81, p<0.001 | t=38.67, p<0.0001 | 9144 |

All four cells are significant at p < 0.0001 under all three scorers. Layer 2 conclusions
are unchanged.

---

## 6. Summary and Recommendation

### Which version should be adopted as primary?

**Recommendation: `scorer_corrected_v2.py` (second correction) should be the primary scorer.**

Reasoning:

1. **Paired tests are the right choice.** The data is inherently paired (each real chain has
   matched shuffled variants). McNemar and paired t-test are strictly more appropriate than
   the z-test and Welch's t-test used in the original scorer. Both corrected versions agree
   on this.

2. **The original filter rule is the right choice for the actionable metric.** The "actionable"
   subset is defined as cases where the prediction task requires guessing an actionable entity.
   For a fair comparison, both sides of the pair should be on the same footing: both real and
   shuffled chains should have an actionable constraint at cutoff\_k. The first correction
   broke this by including pairs where the shuffled chain has a non-actionable constraint
   (ResourceBudget, etc.), comparing a hard prediction problem on the real side against a
   trivially-different prediction on the shuffled side.

3. **`scorer_corrected.py` (first correction) produced an inflated estimand.** Its gap of
   0.115 for haiku::tb reflects that 59.7% of its "actionable" pairs had non-actionable
   shuffled constraints with near-zero match rates (VERIFICATION_REPORT Check 3). This is
   not a causal-structure detection comparison — it is partly artifact.

4. **`scorer_corrected_v2.py` preserves the scientific intent.** The gap of 0.0801 for
   haiku::tb compares real-actionable predictions against shuffled-actionable predictions
   from the same (base chain, eval seed, shuffle seed) triplet. This is the correct
   apples-to-apples comparison.

### Filter rule: which is more correct scientifically?

**The v2 "both-actionable" filter is more correct** for the following reason:

The actionable Layer 1 metric asks: "when the model is prompted with a real (correctly ordered)
chain and the cutoff constraint is an actionable type, does the model predict the correct action
entity more often than when prompted with a shuffled chain?"

For this to be a valid comparison of causal-structure detection, the shuffled counterpart must
also have an actionable constraint at the cutoff position — otherwise, the comparison is:
- Real: can the model predict "use file\_B" given real ordering?
- Shuffled: can the model predict "context\_window" (non-actionable, ResoureBudget) given shuffled ordering?

The second question has a near-zero success rate by construction (the model's action-format
response rarely matches a ResourceBudget entity label). Including these comparisons inflates
the gap without measuring the intended effect.

**`scorer_corrected.py` should NOT be adopted as the primary scorer** because its 0.115 figure
(for both haiku::tb and sonnet::tb) is an inflated estimand, not the correct estimate of the
constraint-ordering effect.

### What changes under v2 vs original?

| Finding | Original | v2 (recommended) | Direction |
|---------|----------|-------------------|-----------|
| L1(act) gaps | 0.066 / 0.031 (TB) | 0.080 / 0.055 (TB) | Slightly larger (paired selection effect) |
| L1(act) TB p-values | 0.006 / 0.265 | 0.003 / 0.061 | haiku: stronger; sonnet: similar |
| haiku::tb meets threshold (Bonf) | Yes (no Bonf applied) | **Yes** (bonf\_p=0.012) | Criterion met |
| sonnet::tb meets threshold (Bonf) | No (gap<0.05) | **No** (gap=0.055, p=0.244) | Criterion not met |
| L2 gaps and significance | Unchanged | Unchanged | No change |
| Pre-reg min criterion met? | Yes (haiku::tb) | **Yes (haiku::tb)** | Same conclusion |

The headline conclusion is the same: the pre-registered minimum publishable criterion is met.
Under v2, it is met by haiku::tb (gap=0.0801, Bonferroni p=0.0116) with properly paired
tests and a valid actionable-subset comparison.

---

## 7. Items Requiring Co-Author Decision

1. **PRIMARY RESULTS NOT YET UPDATED.** RESULTS.md reflects the original scorer's output.
   Co-authors should review v2 numbers and decide whether to update RESULTS.md.

2. **Adopt v2 as primary scorer.** The recommendation above is that `scorer_corrected_v2.py`
   should replace `scorer.py` as the primary scorer. This requires updating RESULTS.md with
   the v2 numbers.

3. **Disclosure of methodological correction.** The paper should note that the original analysis
   used unpaired tests on paired data, and that the corrected analysis uses McNemar and paired
   t-test. The correction does not change the headline conclusion.

4. **sonnet::tb no longer meets the full threshold.** Under v2, sonnet::tb has gap=0.055 and
   Bonferroni p=0.244. The pre-registered minimum criterion (any cell meets) is still met by
   haiku::tb, but the two-cell result from the first correction was an artifact of the inflated
   filter. Co-authors should decide how to characterize the sonnet::tb finding (which shows
   gap>0.05 but is not significant after Bonferroni).

5. **haiku::swe and sonnet::swe actionable.** Under v2, neither SWE cell shows a significant
   actionable gap. This is a weaker result than the first correction suggested and is closer
   to the original's finding (both SWE cells were non-significant in the original too).

---

## 8. Artifacts

| File | Description | Status |
|------|-------------|--------|
| `src/scorer.py` | Original scorer (unpaired tests, original filter) | Unchanged |
| `src/scorer_corrected.py` | First correction (paired tests, real-only filter) | Unchanged — record only |
| `src/scorer_corrected_v2.py` | **Second correction (paired tests, both-actionable filter)** | **Recommended primary** |
| `results/scored.json` | Original scoring output | Unchanged |
| `results/scored_corrected.json` | First correction output | Unchanged — record only |
| `results/scored_corrected_v2.json` | **Second correction output** | **New** |
| `CORRECTED_SCORING.md` | First correction analysis | Unchanged — record only |
| `CORRECTED_SCORING_v2.md` | This document | New |

Command to reproduce:
```bash
python3.11 -m src.scorer_corrected_v2 \
  --results results/raw/ \
  --dist-tb data/reference_tb.pkl \
  --dist-swe data/reference_swe.pkl \
  --chains-real chains/real/ \
  --chains-shuffled chains/shuffled/ \
  --out results/scored_corrected_v2.json
```
