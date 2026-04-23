"""
Supplementary Analysis 4: Cross-cell interaction analysis.

Tests four structural hypotheses from the discussion:
  (a) Entity entropy: SWE has higher average action-distribution entropy than TB
  (b) Distribution concentration: top-3 label coverage per source
  (c) Carrier-type shift: which constraint type carries L1 signal differs by source
  (d) Sonnet compression: model×condition interaction differs significantly from Haiku

Data sources (no new evaluations):
  - data/reference_tb.pkl, data/reference_swe.pkl
  - results/scored.json

Writes supplementary/interaction_results.json.
"""

from __future__ import annotations

import json
import math
import pickle
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

SCORED = Path("results/scored.json")
REF_TB = Path("data/reference_tb.pkl")
REF_SWE = Path("data/reference_swe.pkl")
OUT = Path("supplementary/interaction_results.json")


# ── helpers ──────────────────────────────────────────────────────────────────

def shannon_entropy(counts: dict) -> float:
    """Shannon entropy (nats) of a count distribution."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            h -= p * math.log(p)
    return h


def top3_coverage(counts: dict) -> float:
    """Fraction of total mass in top-3 most frequent labels."""
    if not counts:
        return 0.0
    total = sum(counts.values())
    if total == 0:
        return 0.0
    top3 = sorted(counts.values(), reverse=True)[:3]
    return sum(top3) / total


# ── (a) Entity entropy ────────────────────────────────────────────────────────

def compute_entropy_stats(ref_pkl: dict) -> dict:
    """Average Shannon entropy over all level-0 state signatures."""
    counts_list = ref_pkl["counts"]
    if not counts_list:
        return {}
    level0 = counts_list[0]  # most specific (no backoff)
    entropies = [shannon_entropy(dict(action_counts)) for action_counts in level0.values()]
    return {
        "n_state_signatures": len(entropies),
        "mean_entropy_nats": round(float(np.mean(entropies)), 4),
        "median_entropy_nats": round(float(np.median(entropies)), 4),
        "std_entropy_nats": round(float(np.std(entropies)), 4),
        "min_entropy_nats": round(float(np.min(entropies)), 4),
        "max_entropy_nats": round(float(np.max(entropies)), 4),
    }


def hypothesis_a(tb_ref: dict, swe_ref: dict) -> dict:
    tb_stats = compute_entropy_stats(tb_ref)
    swe_stats = compute_entropy_stats(swe_ref)

    # One-sided Mann-Whitney U: is SWE entropy > TB entropy?
    tb_l0 = tb_ref["counts"][0]
    swe_l0 = swe_ref["counts"][0]
    tb_ents = [shannon_entropy(dict(v)) for v in tb_l0.values()]
    swe_ents = [shannon_entropy(dict(v)) for v in swe_l0.values()]
    u_stat, p_two = stats.mannwhitneyu(swe_ents, tb_ents, alternative="two-sided")
    _, p_one = stats.mannwhitneyu(swe_ents, tb_ents, alternative="greater")

    confirmed = swe_stats["mean_entropy_nats"] > tb_stats["mean_entropy_nats"]

    return {
        "tb": tb_stats,
        "swe": swe_stats,
        "mann_whitney_u": round(float(u_stat), 2),
        "p_two_sided": round(float(p_two), 6),
        "p_one_sided_swe_greater": round(float(p_one), 6),
        "hypothesis_confirmed": confirmed,
        "interpretation": (
            "SWE has higher mean entropy than TB — action space is less predictable "
            "at each state, consistent with SWE showing lower Layer 1 gap."
            if confirmed else
            "SWE does NOT have higher entropy than TB — entropy hypothesis not supported."
        ),
    }


# ── (b) Distribution concentration ───────────────────────────────────────────

def concentration_for_tool_availability(ref_pkl: dict) -> dict:
    """Top-3 coverage for ToolAvailability-related state signatures (level 0)."""
    level0 = ref_pkl["counts"][0]
    coverages = []
    for sig, action_counts in level0.items():
        # ToolAvailability states tend to appear in phases with 'tool' entities
        # Proxy: check if any top label contains 'test_suite' or 'command'
        top_labels = sorted(action_counts, key=action_counts.get, reverse=True)[:1]
        if any("test" in str(lbl) or "command" in str(lbl) for lbl in top_labels):
            coverages.append(top3_coverage(dict(action_counts)))
    if not coverages:
        # Fall back to all signatures
        coverages = [top3_coverage(dict(v)) for v in level0.values()]

    return {
        "n_signatures_used": len(coverages),
        "mean_top3_coverage": round(float(np.mean(coverages)), 4),
        "median_top3_coverage": round(float(np.median(coverages)), 4),
    }


def hypothesis_b(tb_ref: dict, swe_ref: dict) -> dict:
    tb_conc = concentration_for_tool_availability(tb_ref)
    swe_conc = concentration_for_tool_availability(swe_ref)

    # Overall top-3 coverage across all signatures
    tb_all = [top3_coverage(dict(v)) for v in tb_ref["counts"][0].values()]
    swe_all = [top3_coverage(dict(v)) for v in swe_ref["counts"][0].values()]
    _, p = stats.mannwhitneyu(swe_all, tb_all, alternative="two-sided")

    return {
        "tb_all_sigs": {
            "mean_top3_coverage": round(float(np.mean(tb_all)), 4),
            "median_top3_coverage": round(float(np.median(tb_all)), 4),
            "n": len(tb_all),
        },
        "swe_all_sigs": {
            "mean_top3_coverage": round(float(np.mean(swe_all)), 4),
            "median_top3_coverage": round(float(np.median(swe_all)), 4),
            "n": len(swe_all),
        },
        "mann_whitney_p_two_sided": round(float(p), 6),
        "hypothesis_confirmed": float(np.mean(swe_all)) > float(np.mean(tb_all)),
        "interpretation": (
            "SWE has higher top-3 concentration — a few labels dominate. "
            "This is consistent with SWE having lower diversity in agent actions."
            if float(np.mean(swe_all)) > float(np.mean(tb_all)) else
            "SWE does NOT have higher top-3 concentration than TB."
        ),
    }


# ── (c) Carrier-type shift ────────────────────────────────────────────────────

def hypothesis_c(scored: dict) -> dict:
    """
    Test whether the signal-carrying constraint type differs between TB and SWE.
    Uses haiku results (better-powered source for Layer 1).
    Fisher's exact on 2×2: source (TB/SWE) × carrier match (InformationState/Other).
    """
    gt = scored["layer1_by_gt_constraint_type"]
    CT_LABELS = [
        "ResourceBudget", "ToolAvailability", "InformationState",
        "SubGoalTransition", "CoordinationDependency",
    ]

    # Find which type shows the largest positive gap in each source
    source_gaps: dict[str, dict[str, float]] = {}
    for source in ["tb", "swe"]:
        source_gaps[source] = {}
        for ct in CT_LABELS:
            key = f"haiku::{source}::{ct}"
            cell = gt.get(key, {})
            if "error" not in cell and cell.get("n_real", 0) >= 10:
                source_gaps[source][ct] = cell.get("gap", 0.0)

    tb_carrier = max(source_gaps["tb"], key=source_gaps["tb"].get, default=None)
    swe_carrier = max(source_gaps["swe"], key=source_gaps["swe"].get, default=None)

    # Fisher's exact: contingency on whether InformationState is the carrier
    # 2×2: source (TB/SWE) × InformationState_match_rate > other_types
    tb_is = source_gaps["tb"].get("InformationState", 0)
    swe_is = source_gaps["swe"].get("InformationState", 0)

    # For formal test: use haiku n_real from InformationState vs pooled other types
    def _get(src, ct):
        key = f"haiku::{src}::{ct}"
        c = gt.get(key, {})
        return c.get("n_real", 0), c.get("n_shuffled", 0), c.get("real_rate", 0), c.get("shuffled_rate", 0)

    # 2×2 contingency: IS vs non-IS hits in TB and SWE
    tb_is_n, _, tb_is_rr, _ = _get("tb", "InformationState")
    swe_is_n, _, swe_is_rr, _ = _get("swe", "InformationState")
    tb_is_hits = round(tb_is_rr * tb_is_n)
    swe_is_hits = round(swe_is_rr * swe_is_n)
    tb_non_is_hits = sum(
        round(source_gaps["tb"].get(ct, 0) * _get("tb", ct)[0])
        for ct in CT_LABELS if ct != "InformationState"
        if source_gaps["tb"].get(ct, 0) > 0
    )
    swe_non_is_hits = sum(
        round(source_gaps["swe"].get(ct, 0) * _get("swe", ct)[0])
        for ct in CT_LABELS if ct != "InformationState"
        if source_gaps["swe"].get(ct, 0) > 0
    )

    contingency = [[tb_is_hits, swe_is_hits], [tb_non_is_hits, swe_non_is_hits]]
    try:
        odds_ratio, p_fisher = stats.fisher_exact(contingency)
    except Exception:
        odds_ratio, p_fisher = float("nan"), float("nan")

    carrier_differs = tb_carrier != swe_carrier

    return {
        "tb_gaps_by_type": {ct: round(g, 4) for ct, g in source_gaps["tb"].items()},
        "swe_gaps_by_type": {ct: round(g, 4) for ct, g in source_gaps["swe"].items()},
        "tb_dominant_carrier": tb_carrier,
        "swe_dominant_carrier": swe_carrier,
        "carrier_type_differs": carrier_differs,
        "fisher_exact_IS_vs_other": {
            "contingency_2x2": contingency,
            "odds_ratio": round(float(odds_ratio), 4),
            "p_value": round(float(p_fisher), 4),
        },
        "interpretation": (
            f"Dominant signal carrier differs: TB={tb_carrier}, SWE={swe_carrier}. "
            f"Fisher's exact p={p_fisher:.4f}."
            if carrier_differs else
            f"Same dominant carrier in both sources: {tb_carrier}. "
            f"Fisher's exact p={p_fisher:.4f}."
        ),
    }


# ── (d) Sonnet compression ────────────────────────────────────────────────────

def hypothesis_d(scored: dict) -> dict:
    """
    Test whether Sonnet's gap compression is statistically different from Haiku's.
    Uses 4 cells of aggregate stats + individual binary vectors from per_subset.

    Primary test: z-test on whether (haiku_gap - sonnet_gap) is consistent across
    sources and significantly different from zero.
    """
    cells = scored["per_model_per_source"]

    def gap_and_se(cell_name, layer="layer1"):
        c = cells[cell_name][layer]
        n1, n2 = c["n_real"], c["n_shuffled"]
        p1, p2 = c["real_rate"], c["shuffled_rate"]
        gap = c["gap"]
        p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
        se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
        return gap, se

    # Interaction statistic: (haiku_gap_tb - sonnet_gap_tb) and (haiku_gap_swe - sonnet_gap_swe)
    interactions = {}
    for source in ["tb", "swe"]:
        haiku_gap, haiku_se = gap_and_se(f"haiku::{source}")
        sonnet_gap, sonnet_se = gap_and_se(f"sonnet::{source}")
        diff = haiku_gap - sonnet_gap
        se_diff = math.sqrt(haiku_se**2 + sonnet_se**2)
        z = diff / se_diff if se_diff > 0 else 0.0
        p = 2 * (1 - stats.norm.cdf(abs(z)))
        interactions[source] = {
            "haiku_gap": round(haiku_gap, 4),
            "sonnet_gap": round(sonnet_gap, 4),
            "gap_difference": round(diff, 4),
            "z_stat": round(z, 4),
            "p_value": round(p, 4),
            "significant": bool(p < 0.05),
        }

    # Pooled interaction: meta-analysis across sources
    diffs = [interactions[s]["gap_difference"] for s in ["tb", "swe"]]
    ses = [math.sqrt(
        gap_and_se(f"haiku::{s}")[1]**2 + gap_and_se(f"sonnet::{s}")[1]**2
    ) for s in ["tb", "swe"]]
    weights = [1 / se**2 for se in ses]
    pooled_diff = sum(w * d for w, d in zip(weights, diffs)) / sum(weights)
    pooled_se = math.sqrt(1 / sum(weights))
    z_pooled = pooled_diff / pooled_se
    p_pooled = 2 * (1 - stats.norm.cdf(abs(z_pooled)))

    # Layer 2 comparison
    l2_interactions = {}
    for source in ["tb", "swe"]:
        h2 = cells[f"haiku::{source}"]["layer2"]
        s2 = cells[f"sonnet::{source}"]["layer2"]
        l2_interactions[source] = {
            "haiku_gap": round(h2["gap"], 4),
            "sonnet_gap": round(s2["gap"], 4),
            "difference": round(h2["gap"] - s2["gap"], 4),
        }

    compression_consistent = all(
        interactions[s]["gap_difference"] > 0 for s in ["tb", "swe"]
    )
    compression_significant = p_pooled < 0.05

    return {
        "per_source_l1": interactions,
        "pooled_l1": {
            "pooled_gap_difference": round(pooled_diff, 4),
            "pooled_se": round(pooled_se, 4),
            "z_stat": round(z_pooled, 4),
            "p_value": round(p_pooled, 4),
            "significant": bool(compression_significant),
        },
        "per_source_l2": l2_interactions,
        "sonnet_compression_consistent": compression_consistent,
        "sonnet_compression_significant": compression_significant,
        "interpretation": (
            f"Haiku shows larger L1 gap than Sonnet in "
            f"{'both' if compression_consistent else 'some'} source(s). "
            f"Pooled gap-difference = {pooled_diff:.4f} "
            f"(z={z_pooled:.2f}, p={p_pooled:.4f}). "
            + ("Sonnet gap compression is statistically significant."
               if compression_significant else
               "Gap compression is present but not statistically significant "
               "(consistent with noise at current sample size).")
        ),
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    scored = json.loads(SCORED.read_text())
    with open(REF_TB, "rb") as f:
        tb_ref = pickle.load(f)
    with open(REF_SWE, "rb") as f:
        swe_ref = pickle.load(f)

    print("Running hypothesis tests...\n")

    a = hypothesis_a(tb_ref, swe_ref)
    b = hypothesis_b(tb_ref, swe_ref)
    c = hypothesis_c(scored)
    d = hypothesis_d(scored)

    results = {
        "hypothesis_a_entropy": a,
        "hypothesis_b_concentration": b,
        "hypothesis_c_carrier_type": c,
        "hypothesis_d_sonnet_compression": d,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)

    def _default(obj):
        if isinstance(obj, (np.bool_, np.integer)):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    OUT.write_text(json.dumps(results, indent=2, default=_default))

    print("(a) Entity entropy hypothesis:")
    print(f"    TB mean entropy: {a['tb']['mean_entropy_nats']} nats "
          f"(n={a['tb']['n_state_signatures']} sigs)")
    print(f"    SWE mean entropy: {a['swe']['mean_entropy_nats']} nats "
          f"(n={a['swe']['n_state_signatures']} sigs)")
    print(f"    Mann-Whitney p (two-sided): {a['p_two_sided']}")
    print(f"    Confirmed: {a['hypothesis_confirmed']}")
    print()

    print("(b) Concentration hypothesis:")
    print(f"    TB mean top-3 coverage: {b['tb_all_sigs']['mean_top3_coverage']}")
    print(f"    SWE mean top-3 coverage: {b['swe_all_sigs']['mean_top3_coverage']}")
    print(f"    Mann-Whitney p (two-sided): {b['mann_whitney_p_two_sided']}")
    print(f"    Confirmed: {b['hypothesis_confirmed']}")
    print()

    print("(c) Carrier-type shift hypothesis:")
    print(f"    TB dominant carrier: {c['tb_dominant_carrier']}")
    print(f"    SWE dominant carrier: {c['swe_dominant_carrier']}")
    print(f"    Carrier differs: {c['carrier_type_differs']}")
    print(f"    Fisher's exact p: {c['fisher_exact_IS_vs_other']['p_value']}")
    print()

    print("(d) Sonnet compression hypothesis:")
    for src in ["tb", "swe"]:
        di = d["per_source_l1"][src]
        print(f"    {src.upper()}: haiku_gap={di['haiku_gap']:.4f} "
              f"sonnet_gap={di['sonnet_gap']:.4f} diff={di['gap_difference']:.4f} "
              f"p={di['p_value']:.4f}")
    pd_ = d["pooled_l1"]
    print(f"    Pooled: diff={pd_['pooled_gap_difference']:.4f} "
          f"z={pd_['z_stat']:.2f} p={pd_['p_value']:.4f}")
    print(f"    Compression consistent: {d['sonnet_compression_consistent']}")
    print(f"    Compression significant: {d['sonnet_compression_significant']}")
    print()
    print(f"Output written to {OUT}")


if __name__ == "__main__":
    main()
