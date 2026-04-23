# Verification Report: `src/scorer_corrected.py`

**Date:** 2026-04-23  
**Auditor:** Independent verification (Claude Sonnet 4.6)  
**Scope:** Computational correctness of `src/scorer_corrected.py` relative to its claims  
**Artifacts read:** `src/scorer.py`, `src/scorer_corrected.py`, `results/scored_corrected.json`, `results/scored.json`, raw results in `results/raw/tb/`, chain files in `chains/real/tb/` and `chains/shuffled/tb/`  
**Primary concern:** haiku::tb and sonnet::tb actionable gap both reported as 0.115 (up from 0.066 in original); identical to 4 decimal places across models.

---

## Check 1: McNemar Denominator

### What was checked

Whether `gap` in `mcnemar_test()` is computed across **all** pairs or only across **discordant** pairs. The conventional match-rate difference must use all pairs as the denominator, not just b+c.

### Relevant code (`src/scorer_corrected.py`, lines 104–115)

```python
real_rate = sum(real_matches) / n      # n = total pairs, not just discordant
shuf_rate = sum(shuffled_matches) / n
return {
    ...
    "real_rate": round(real_rate, 4),
    "shuffled_rate": round(shuf_rate, 4),
    "gap": round(real_rate - shuf_rate, 4),
    ...
}
```

where `n = len(real_matches)` (line 85), set at the top of `mcnemar_test()` as the full pair count.

### Numerical verification

For haiku::tb actionable (`results/scored_corrected.json`, lines 201–213):

| Cell | Value |
|------|-------|
| n\_pairs | 774 |
| n11 (both match) | 9 |
| b (real match, shuf no-match) | 114 |
| c (shuf match, real no-match) | 25 |
| n00 (neither) | 626 |

```
gap = (n11 + b)/n - (n11 + c)/n = (9+114)/774 - (9+25)/774
    = 123/774 - 34/774
    = 89/774
    = 0.114987...
    → rounds to 0.1150
```

The discordant-pairs-only formula would give:
```
(b - c) / (b + c) = 89 / 139 = 0.6403   ≠   0.115
```

These are unambiguously different. The reported gap **is** the match-rate difference across all pairs.

### Verdict: **NO BUG FOUND**

The gap is correctly computed as `real_rate − shuffled_rate` over all `n_pairs`, not as `(b−c)/(b+c)`.

---

## Check 2: Identical Gaps Across Models

### What was checked

Whether `haiku::tb` and `sonnet::tb` both reporting gap = 0.115 reflects shared state between model iterations, or is a genuine (if surprising) coincidence in the data.

### Values from `results/scored_corrected.json`

| Cell | real\_rate | shuffled\_rate | gap | b | c | b−c |
|------|-----------|---------------|-----|---|---|-----|
| haiku::tb actionable | 0.1589 | 0.0439 | **0.115** | 114 | 25 | **89** |
| sonnet::tb actionable | 0.186 | 0.0711 | **0.115** | 117 | 28 | **89** |

Both models have `b − c = 89` from **different** contingency tables (haiku: 139 total discordant; sonnet: 145 total discordant). The raw match rates differ substantially (haiku real = 15.9% vs sonnet = 18.6%; haiku shuffled = 4.4% vs sonnet = 7.1%). The identical gap is entirely explained by the arithmetic: `89/774 = 0.114987`, which rounds identically to 0.1150 for both.

### Model-iteration code (`src/scorer_corrected.py`, lines 402–435)

```python
for p in pairs:
    model = p.model          # "haiku" or "sonnet" — distinct per pair
    src = p.source
    ...
    for bkt in [
        per_model[model],                              # keyed by model string
        per_model_per_source[(model, src)],            # keyed by (model, source) tuple
        ...
    ]:
        bkt["real_l1"].append(p.real_l1)
        bkt["shuf_l1"].append(p.shuffled_l1)
    
    if p.real_l1_actionable:
        for bkt in [per_model[model], per_model_per_source[(model, src)], ...]:
            bkt["real_l1_act"].append(p.real_l1)
            bkt["shuf_l1_act"].append(p.shuffled_l1)
```

`per_model` is a `defaultdict(_new_bucket)` where each call to `_new_bucket()` creates a fresh dict of empty lists. Haiku pairs go to `per_model["haiku"]`; sonnet pairs go to `per_model["sonnet"]`. There is no shared mutable state between model buckets.

### Independent verification

Manual computation of haiku::tb and sonnet::tb actionable pairs from raw files, using `src.scorer.score_layer1` directly:

```
haiku: n=774, real_matches=123, shuf_matches=34, gap=0.1150
       b=114, c=25, n11=9, n00=626    ← exact match to scored_corrected.json
sonnet: n=774, real_matches=144, shuf_matches=55, gap=0.1150
        b=117, c=28, n11=27, n00=602  ← exact match to scored_corrected.json
```

Both are computed from model-distinct subsets of the data.

### Why both b−c = 89?

The 774 pairs are drawn from the **same 86 base TB chains** for both models (same base chains, same eval_seeds 42/1337/7919, same shuffle_seeds 42/1337/7919). Haiku and sonnet operate on the same chains but produce independent responses. The net real-favored discordance equalling 89 for both is a **numerical coincidence** in this particular TB dataset. It is implausible under a uniform random model but not mechanically impossible; the TB dataset is small (170 real chains, 86 with actionable cutoffs) and both models have similar overall accuracy levels on this task, making equal net discordance plausible.

### Verdict: **NO BUG FOUND**

No shared state between model iterations. Identical gaps are a data coincidence (both b−c = 89 over the same 774 pairs), not a code defect. The suspicious appearance is warranted and co-authors should note the small sample (n=774 for TB actionable).

---

## Check 3: Actionable Subset Filter

### What was checked

Whether the actionable filter is applied at the same point, to both conditions, and before/after pair alignment in both scorers — and whether any difference explains the gap inflation from 0.066 to 0.115.

### Original scorer (`src/scorer.py`, lines 366–445) — independent samples

```python
ACTIONABLE_TYPES = {"ToolAvailability", "InformationState", "SubGoalTransition"}
...
for r in results:
    ...
    gt_type = l1.get("constraint_type", "")
    is_actionable = gt_type in ACTIONABLE_TYPES
    
    if l1["top_k_match"] is not None:
        # always buckets for ALL cutoffs:
        per_model[model][f"{condition}_l1"].append(match)
        ...
        # actionable-only bucket, applied PER RESULT, PER CONDITION independently:
        if is_actionable:
            per_model[model][f"{condition}_l1_actionable"].append(match)
```

The `is_actionable` flag is computed from **the result's own chain's constraint type** (`condition` = "real" or "shuffled"). Real and shuffled are independent lists.

**Effect:** The real pool contains only real-chain results where the real chain's constraint at cutoff\_k is actionable. The shuffled pool contains only shuffled-chain results where the **shuffled chain's** constraint at cutoff\_k is actionable — which may differ from the real chain's.

### Corrected scorer (`src/scorer_corrected.py`, lines 422–435) — paired

```python
if p.real_l1_actionable:          # filter by REAL chain's constraint type only
    for bkt in [
        per_model[model],
        per_model_per_source[(model, src)],
        ...
    ]:
        bkt["real_l1_act"].append(p.real_l1)
        bkt["shuf_l1_act"].append(p.shuffled_l1)   # shuffled included regardless of its gt_type
```

The `real_l1_actionable` flag is from the **real chain's constraint type** only (`p.real_l1_actionable = real_entry["l1_is_actionable"]`, line 366). The paired shuffled result is included regardless of whether the shuffled chain's constraint at cutoff\_k is actionable.

### Quantitative impact

For haiku::tb, among the 774 corrected actionable pairs:

| Shuffled chain's constraint at cutoff\_k | n pairs | shuf\_rate | gap |
|------------------------------------------|---------|-----------|-----|
| Also actionable (ToolAvail / InfoState / SubGoal) | 312 (40.3%) | **0.0929** | 0.0801 |
| NOT actionable (ResourceBudget / Coord / Opt) | 462 (59.7%) | **0.0108** | 0.1385 |
| **All 774** | 774 | **0.0439** | **0.1150** |

Key observation: the 312 pairs where the shuffled chain is also actionable reproduce **exactly** the original scorer's shuffled\_rate of 0.0929. The remaining 462 pairs — where the shuffled chain has a non-actionable constraint at cutoff\_k — have a shuffled match rate of only 0.0108, because the model's response to the shuffled chain is unlikely to contain non-actionable entity labels (e.g., "memory\_limit" for ResourceBudget, coordination dependency labels).

**The gap inflation from 0.066 → 0.115 is entirely produced by including these 462 non-actionable shuffled pairs.** Their shuffled match rate is near-zero because:

- 438 of 462 non-actionable shuffled pairs have `ResourceBudget` at cutoff\_k, with a shuffled match rate of 0.0114
- 15 have `OptimizationCriterion`: shuffled match rate 0.0000
- 9 have `CoordinationDependency`: shuffled match rate 0.0000

Within these pairs, the real chain still has an actionable constraint (real\_rate ≈ 0.149), so the gap is ~0.138 — almost entirely artifact.

### Is this a bug?

This is a **methodological choice**, not a computational error. The corrected scorer's comment (lines 424–427) explicitly documents the decision:

```python
# Both real and shuffled must have the SAME constraint type at cutoff_k
# (same chain up to reordering means the same constraint IS at that step
# but the test should reflect whether "actionable cutoff" is true for REAL chain,
# since that's our designed-for case; we include pair if real cutoff is actionable)
if p.real_l1_actionable:
```

However, the **consequence** is that 59.7% of the 774 actionable pairs compare a real chain's actionable-constraint prediction against a shuffled chain's non-actionable-constraint prediction. This is not an apples-to-apples comparison. The "gap" in these pairs partly reflects the structural ease of predicting actionable vs non-actionable entities, not the model's ability to exploit real vs shuffled constraint ordering.

The original scorer's approach — filtering both conditions by their own chain's actionability — avoids this confound, at the cost of losing pairing guarantees.

### Verdict: **UNCLEAR — NEEDS HUMAN REVIEW**

No computational bug. The gap inflation is produced by an explicit, documented methodological choice: 59.7% of the corrected actionable pairs have non-actionable shuffled constraints with near-zero shuffled match rates. Whether this methodological choice is appropriate is a scientific question, not a code question. Co-authors should decide whether the "actionable" label should apply to both conditions in a pair before accepting the 0.115 figure as the primary estimand.

---

## Check 4: Manual Gap Computation

### What was checked

Manual replication of the haiku::tb actionable gap using scorer's own `score_layer1` function applied directly to raw result files and chain files.

### Method

All 170 real TB chain files and 510 shuffled TB chain files were loaded. For every combination of:
- base chain where real chain's constraint at cutoff\_k is actionable (86 chains)
- eval\_seed ∈ {42, 1337, 7919}
- shuffle\_seed ∈ {42, 1337, 7919}

a pair was formed and `src.scorer.score_layer1` was called for both real and shuffled results. Pairs with `None` top\_k\_match were excluded.

### Results

```
haiku::tb manual:
  n_pairs:       774          (corrected scorer: 774)
  real_matches:  123          (corrected scorer: n11+b = 9+114 = 123)
  shuf_matches:  34           (corrected scorer: n11+c = 9+25 = 34)
  real_rate:     0.1589       (corrected scorer: 0.1589)
  shuf_rate:     0.0439       (corrected scorer: 0.0439)
  gap:           0.1150       (corrected scorer: 0.115)
  n11=9, b=114, c=25, n00=626 (corrected scorer: identical)

sonnet::tb manual:
  n_pairs:       774          (corrected scorer: 774)
  real_matches:  144          (corrected scorer: n11+b = 27+117 = 144)
  shuf_matches:  55           (corrected scorer: n11+c = 27+28 = 55)
  real_rate:     0.1860       (corrected scorer: 0.186)
  shuf_rate:     0.0711       (corrected scorer: 0.0711)
  gap:           0.1150       (corrected scorer: 0.115)
  n11=27, b=117, c=28, n00=602 (corrected scorer: identical)
```

Every number in `results/scored_corrected.json` for these two cells exactly matches the independent manual computation, including all four cells of the contingency table.

### Does the manual gap match the original (0.066) or the corrected (0.115)?

The manual computation **matches the corrected scorer** (0.115), not the original. The manual computation uses the corrected scorer's filtering rule (real chain actionability only). When the manual computation is run with the original scorer's rule (both real AND shuffled must have actionable constraints), the result matches the original scorer:

```
original logic manual:
  n_real=258, n_shuffled=549
  real_rate=0.1589, shuffled_rate=0.0929, gap=0.0660
  (matches results/scored.json: gap=0.066 ✓)
```

The gap difference (0.066 vs 0.115) is fully accounted for by the filter rule, not by any computation error.

### Verdict: **NO BUG FOUND**

The corrected scorer's 0.115 figure is numerically exact. The original scorer's 0.066 figure is also numerically exact. The difference is methodological.

---

## Check 5: Pairing Correctness

### What was checked

Whether pairs in `scorer_corrected.py` correctly align one real and one shuffled result from the same base chain, eval\_seed, and model.

### Relevant code (`src/scorer_corrected.py`, lines 334–373)

```python
for base_cid in sorted(real_chain_ids):
    real_scored = scored_by_chain.get(base_cid, {})     # keyed by eval_key=(model, seed)
    shuf_cids = shuffled_by_base.get(base_cid, [])       # all shuffled variants of this chain

    real_eval_keys = set(real_scored.keys())

    for shuf_cid in shuf_cids:
        shuf_scored = scored_by_chain.get(shuf_cid, {})
        sh_seed = shuffle_seed_from_chain_id(shuf_cid)   # extracts integer after "_shuffled_"

        all_eval_keys = real_eval_keys | set(shuf_scored.keys())
        for ek in sorted(all_eval_keys):
            real_entry = real_scored.get(ek)
            shuf_entry = shuf_scored.get(ek)

            if real_entry is None:
                n_excluded_no_real += 1
                continue
            if shuf_entry is None:
                n_excluded_no_shuffled += 1
                continue

            pairs.append(Pair(
                base_cid=base_cid,
                model=ek[0],          # from eval_key — same for real and shuffled
                eval_seed=ek[1],      # from eval_key — same for real and shuffled
                shuffle_seed=sh_seed, # from shuffled chain_id suffix
                ...
            ))
```

`eval_key = (model, seed)` (line 237). The pairing loop iterates over all eval\_keys present in **either** real or shuffled; incomplete pairs (missing real or shuffled for a given eval\_key) are counted and excluded. The pair structure is:

```
(base_chain_id, model, eval_seed) × (shuffled_chain = base_chain_id + "_shuffled_" + shuffle_seed)
```

### Traced example

For `base_cid = "tb_0130_crack-7z-hash.hard"`:
- Real evaluations: 6 — haiku/42, haiku/1337, haiku/7919, sonnet/42, sonnet/1337, sonnet/7919
- Shuffled variants: `_shuffled_42`, `_shuffled_1337`, `_shuffled_7919`
- Each shuffled variant has 6 evaluations (same eval\_keys)
- Total pairs for this base chain: 3 shuffle\_seeds × 6 eval\_keys = 18 pairs

This is correct: each pair maps exactly one real eval to one shuffled eval sharing the same model and eval\_seed.

`scored_corrected.json` reports:
- `n_excluded_no_real_eval: 0`
- `n_excluded_no_shuffled_eval: 0`
- `n_base_chains_no_shuffled_variant: 0`

All pairs are complete. No exclusions.

### Verdict: **NO BUG FOUND**

Pairing is correct. Each pair has one real and one shuffled result from the same base\_chain\_id, same model, and same eval\_seed. Shuffle\_seed correctly distinguishes the three shuffled variants.

---

## Check 6: Sample Size Sanity

### What was checked

Whether the number of pairs is internally consistent with the experimental design.

### Counts

| Quantity | Expected | Observed |
|---------|----------|---------|
| Real TB chains | — | 170 |
| Shuffled TB chains | 170 × 3 = 510 | 510 ✓ |
| Haiku real TB evaluations | 170 × 3 eval\_seeds = 510 | 510 ✓ |
| Haiku shuffled TB evaluations | 510 chains × 3 eval\_seeds = 1530 | 1530 ✓ |
| haiku::tb total pairs | 170 × 3 shuffle\_seeds × 3 eval\_seeds = 1530 | 1530 ✓ |
| haiku::tb actionable pairs | 86 chains × 9 = 774 | 774 ✓ |
| Total pairs (all models × sources) | 1186 × 3 × 6 = **21,348** | **21,348** ✓ |

The design is: each real chain (eval\_seed) is paired with each of its 3 shuffled variants (same eval\_seed). This means each real eval result contributes 3 pairs. In the actionable bucket, each real result (86 base chains × 3 eval\_seeds = 258 real evals) contributes 3 pairs = 774 pairs. The real\_rate in the paired analysis equals the unpaired real rate (258 results → 774 results but all replicated 3×, so rate is unchanged at 0.1589).

This 3× replication of real eval results in the paired structure is **by design**: one real eval is compared against three independent shuffled variants. It does not inflate the real\_rate but does increase McNemar test power by using all available shuffled variants.

### Verdict: **NO BUG FOUND**

All pair counts are internally consistent with the experimental design. The 3× replication of real evaluations is a known feature of the pairing strategy, not an error.

---

## Summary

### Overall assessment

`src/scorer_corrected.py` is **computing what it claims to compute**. The gap formula, pairing logic, and sample sizes are all correct. Every reported number for haiku::tb and sonnet::tb was independently verified to the last digit using raw data and the scorer's own scoring functions.

### No bugs found

All six checks produced either NO BUG FOUND or the methodological clarification below. There are no computational errors.

### Source of the 0.066 → 0.115 gap inflation

The inflation is entirely explained by **Check 3**: the corrected scorer's actionable filter uses the real chain's constraint type to select pairs, while including the paired shuffled result regardless of the shuffled chain's constraint type at cutoff\_k. 59.7% of the 774 haiku::tb actionable pairs have non-actionable constraints at cutoff\_k for the shuffled chain. These pairs contribute near-zero shuffled match rates (ResourceBudget: 1.1%, OptimizationCriterion: 0.0%, CoordinationDependency: 0.0%), driving the shuffled rate from 0.0929 (only shuffled-actionable, original approach) to 0.0439 (all paired, corrected approach). The real rate is unchanged at 0.1589.

This is documented as an intentional methodological choice in the corrected scorer (lines 423–427). Whether it is scientifically appropriate is a judgment call for co-authors, not a correctness issue.

### Source of the identical gaps

Both haiku::tb and sonnet::tb report gap = 0.115 = 89/774 because both happen to have exactly 89 net real-favored discordant pairs in the same 774-pair set. This is a numerical coincidence (haiku: b=114, c=25; sonnet: b=117, c=28). The coincidence is more plausible than it appears because the TB dataset is small (86 actionable base chains) and both models are operating at similar overall accuracy levels on this task.

### Recommendation for co-author review

1. **The 0.115 figure is numerically correct** and can be reported without qualification on that basis.

2. **Co-authors should decide whether the corrected actionable filter is appropriate.** If the intent is to compare "model performance on actionable-constraint prediction, real vs shuffled, holding constraint difficulty constant," then pairs where the shuffled chain has a non-actionable constraint should arguably be excluded (or both conditions should be required to be actionable). This would restore the 0.066–0.080 range and bring the estimand closer to the original scorer's intent.

3. **The identical gaps (both 0.115) are suspicious but not erroneous.** The small TB dataset (86 actionable chains) means coincidences of this kind are possible. The haiku and sonnet contingency tables are genuinely different. This should be disclosed in any write-up.

4. **The pre-registered threshold of gap ≥ 0.05 with p < 0.05 is met under both filter approaches** for haiku::tb (corrected gap = 0.115, original = 0.066; both > 0.05). The binary pass/fail conclusion is robust to the filter choice, even if the magnitude differs substantially.
