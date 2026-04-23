# Proposed Changes to RESULTS.md §5 Discussion

**For human review — do not apply directly.**

These proposals are based on the supplementary analyses (SUPPLEMENTARY.md, added
2026-04-23). They are exploratory findings and should only be incorporated into
RESULTS.md if the author agrees they accurately characterise the results.

No changes to §4 (headline numbers), SPEC.md, or scoring code are proposed.

---

## Proposed addition to §5.2 (Why TB outperforms SWE)

Current text (if any) should be extended with:

> Supplementary Analysis §4a–b provides a mechanistic account: TB's reference
> distributions have lower mean entropy (0.73 vs. 0.93 nats per state signature,
> Mann-Whitney p < 0.001) and higher top-3 label concentration (0.939 vs. 0.902,
> p < 0.001). In TB, at each chain state, a small number of entity labels account
> for most probability mass, making top-3 entity prediction tractable at this
> sample size. SWE's higher entropy means the correct entity is spread across a
> wider action space; a larger evaluation would be needed to detect the signal
> (estimated ~7,500 real evaluations for haiku::swe at 80% power).

---

## Proposed addition to §5.3 (Why Sonnet's gap is below Haiku's)

Current text (if any) should be extended with:

> Supplementary Analysis §4d finds the Sonnet compression to be directionally
> consistent (Haiku L1 gap > Sonnet L1 gap in both sources, pooled difference +0.006)
> but not statistically distinguishable from noise (z = 0.89, p = 0.37). The
> hypothesis cannot be confirmed or rejected at this sample size.
>
> Notably, Sonnet shows *larger* Layer 2 gaps than Haiku in both sources (TB: 0.088
> vs. 0.049; SWE: 0.068 vs. 0.067). This suggests that Sonnet produces more
> legally-valid responses (higher legality score) while Haiku more often produces
> the exact entity string the reference expects (higher top-k entity match). These
> may be two distinct response strategies rather than a capability gradient.

---

## Proposed addition to §5 (new subsection: Mechanism)

> **§5.x Constraint-type decomposition.** Post-hoc stratification by ground-truth
> constraint type at the cutoff (Supplementary §2) reveals that the Layer 1 signal
> is concentrated in InformationState cutoffs in both sources. At these positions,
> the model is asked to predict the entity label associated with a newly-revealed
> observable (e.g., `file_B`, `error_class_A`). InformationState shows significant
> positive gaps in both haiku::swe (gap = +0.109, p < 0.001) and haiku::tb (gap =
> +0.117, p = 0.075). ToolAvailability cutoffs show a notable source-direction
> reversal: positive in TB (haiku gap = +0.112, p = 0.001) but negative in SWE
> (sonnet gap = −0.027, p = 0.002). This reversal merits investigation in follow-up
> work — it may reflect differences in how tool states are represented in ATIF vs.
> SWE-agent trajectories.

---

## Note on error analysis (§3)

Analysis 3 (per-case qualitative error analysis) could not be run because
`results/raw/` was not committed to this repository. The findings in §5 that rely
on qualitative characterisation of failure modes are therefore unverified. Push
`results/raw/` and re-run `scripts/supplementary/03_error_analysis.py` to complete
this analysis.
