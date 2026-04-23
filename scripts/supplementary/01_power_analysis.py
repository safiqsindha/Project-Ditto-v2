"""
Supplementary Analysis 1: Power analysis on existing cells.

Reads results/scored.json (no new evaluations).
Computes achieved power, MDES, and required-N for underpowered cells.
Writes supplementary/power_results.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy import stats
from statsmodels.stats.power import NormalIndPower, TTestIndPower

SCORED = Path("results/scored.json")
OUT = Path("supplementary/power_results.json")
ALPHA = 0.05
TARGET_POWER = 0.80

# Pre-registered thresholds (SPEC.md)
L1_THRESHOLD = 0.05
L2_THRESHOLD = 0.04


def cohens_h(p1: float, p2: float) -> float:
    """Cohen's h effect size for two proportions."""
    return 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p2))


def cohens_d_from_tstat(t_stat: float, n1: int, n2: int) -> float:
    """Approximate Cohen's d from Welch's t-statistic and sample sizes."""
    return abs(t_stat) * math.sqrt(1 / n1 + 1 / n2)


def power_proportion(p1: float, p2: float, n1: int, n2: int) -> float:
    """Achieved power for a two-sample proportion test (z-test)."""
    h = abs(cohens_h(p1, p2))
    if h == 0:
        return alpha_only_power(ALPHA)
    ratio = n2 / n1
    try:
        pwr = NormalIndPower().solve_power(
            effect_size=h, nobs1=n1, ratio=ratio, alpha=ALPHA, alternative="two-sided"
        )
        return float(pwr)
    except Exception:
        return float("nan")


def alpha_only_power(alpha: float) -> float:
    return alpha


def mdes_proportion(n1: int, n2: int, power: float = TARGET_POWER) -> float:
    """Minimum detectable Cohen's h at given power and sample sizes."""
    ratio = n2 / n1
    try:
        h = NormalIndPower().solve_power(
            nobs1=n1, ratio=ratio, alpha=ALPHA, power=power, alternative="two-sided"
        )
        return float(h)
    except Exception:
        return float("nan")


def required_n_proportion(h: float, ratio: float = 1.0, power: float = TARGET_POWER) -> int:
    """Required n_real to detect effect size h at target power."""
    if h <= 0:
        return -1
    try:
        n = NormalIndPower().solve_power(
            effect_size=h, ratio=ratio, alpha=ALPHA, power=power, alternative="two-sided"
        )
        return int(math.ceil(n))
    except Exception:
        return -1


def power_ttest(d: float, n1: int, n2: int) -> float:
    """Achieved power for Welch's t-test given Cohen's d."""
    if d == 0:
        return alpha_only_power(ALPHA)
    ratio = n2 / n1
    try:
        pwr = TTestIndPower().solve_power(
            effect_size=d, nobs1=n1, ratio=ratio, alpha=ALPHA, alternative="two-sided"
        )
        return float(pwr)
    except Exception:
        return float("nan")


def mdes_ttest(n1: int, n2: int, power: float = TARGET_POWER) -> float:
    """Minimum detectable Cohen's d at given power."""
    ratio = n2 / n1
    try:
        d = TTestIndPower().solve_power(
            nobs1=n1, ratio=ratio, alpha=ALPHA, power=power, alternative="two-sided"
        )
        return float(d)
    except Exception:
        return float("nan")


def required_n_ttest(d: float, ratio: float = 1.0, power: float = TARGET_POWER) -> int:
    """Required n_real to detect Cohen's d at target power."""
    if d <= 0:
        return -1
    try:
        n = TTestIndPower().solve_power(
            effect_size=d, ratio=ratio, alpha=ALPHA, power=power, alternative="two-sided"
        )
        return int(math.ceil(n))
    except Exception:
        return -1


def analyse_cell(cell_name: str, cell: dict) -> dict:
    result = {"cell": cell_name}

    # ── Layer 1 (proportion test) ──────────────────────────────────────────
    l1 = cell["layer1"]
    n1, n2 = l1["n_real"], l1["n_shuffled"]
    p1, p2 = l1["real_rate"], l1["shuffled_rate"]
    gap = l1["gap"]
    h_obs = cohens_h(p1, p2)
    h_threshold = cohens_h(p2 + L1_THRESHOLD, p2)  # h for gap = 0.05 at observed p2

    result["layer1"] = {
        "n_real": n1,
        "n_shuffled": n2,
        "observed_gap": gap,
        "cohens_h": round(h_obs, 4),
        "achieved_power": round(power_proportion(p1, p2, n1, n2), 4),
        "mdes_cohens_h_at_80pct": round(mdes_proportion(n1, n2), 4),
        "cleared_threshold": gap >= L1_THRESHOLD and l1["p_value"] < ALPHA,
        "required_n_for_observed_effect_80pct": (
            required_n_proportion(abs(h_obs), ratio=n2 / n1)
            if gap > 0 else -1
        ),
        "required_n_at_preregistered_threshold_80pct": (
            required_n_proportion(abs(h_threshold), ratio=n2 / n1)
        ),
    }

    # ── Layer 2 (Welch's t-test) ───────────────────────────────────────────
    l2 = cell["layer2"]
    # Back-calculate n from Layer 1 (same evaluations; L2 includes all, L1 excludes
    # un-scoreable cutoffs, so L2 n ≥ L1 n; use L1 n as conservative estimate)
    n1_l2 = n1
    n2_l2 = n2
    t_stat = l2["t_stat"]
    d_obs = cohens_d_from_tstat(t_stat, n1_l2, n2_l2)

    result["layer2"] = {
        "n_real_approx": n1_l2,
        "n_shuffled_approx": n2_l2,
        "observed_gap": l2["gap"],
        "cohens_d_approx": round(d_obs, 4),
        "achieved_power": round(power_ttest(d_obs, n1_l2, n2_l2), 4),
        "mdes_cohens_d_at_80pct": round(mdes_ttest(n1_l2, n2_l2), 4),
        "cleared_threshold": l2["gap"] >= L2_THRESHOLD and l2["p_value"] < ALPHA,
        "required_n_for_observed_effect_80pct": (
            required_n_ttest(d_obs, ratio=n2_l2 / n1_l2)
            if l2["gap"] > 0 else -1
        ),
    }

    return result


def main():
    scored = json.loads(SCORED.read_text())
    cells = scored["per_model_per_source"]

    results = []
    for cell_name in ["haiku::tb", "haiku::swe", "sonnet::tb", "sonnet::swe"]:
        results.append(analyse_cell(cell_name, cells[cell_name]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2))

    # Pretty-print summary
    print("=== Power Analysis Summary ===\n")
    print(f"{'Cell':<18} {'Layer':<6} {'n_real':>7} {'gap':>7} {'power':>7} "
          f"{'MDES(h/d)':>10} {'Req-N(obs)':>10} {'cleared':>8}")
    print("-" * 80)
    for r in results:
        for layer in ("layer1", "layer2"):
            d = r[layer]
            mdes_key = "mdes_cohens_h_at_80pct" if layer == "layer1" else "mdes_cohens_d_at_80pct"
            req_n_key = "required_n_for_observed_effect_80pct"
            n_real = d.get("n_real") or d.get("n_real_approx", 0)
            print(
                f"{r['cell']:<18} {layer:<6} {n_real:>7} "
                f"{d['observed_gap']:>7.4f} {d['achieved_power']:>7.3f} "
                f"{d[mdes_key]:>10.4f} {d[req_n_key]:>10} "
                f"{'YES' if d['cleared_threshold'] else 'NO':>8}"
            )
    print(f"\nOutput written to {OUT}")


if __name__ == "__main__":
    main()
