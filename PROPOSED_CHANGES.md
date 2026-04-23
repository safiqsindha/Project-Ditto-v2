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

~~Analysis 3 could not be run.~~ **Run completed 2026-04-23.** See SUPPLEMENTARY.md
§3 for full results. Key qualitative findings below are proposed for the
Discussion section based on §3.

---

## Proposed addition to §5.2 (the SWE-TA anomaly mechanism)

Currently §5.2 of WRITEUP.md attributes the SWE-TA reversal to "SWE TA
distribution is highly concentrated (file_B = 33% of TA constraints)... shuffled
chains inherit this prior". SUPPLEMENTARY §3.7 provides the case-level evidence
for this claim. Suggested extension:

> The qualitative error analysis (Supplementary §3.7) confirms the proposed
> mechanism at the case level. In all four sampled SWE-Sonnet shuffled-match
> ToolAvailability cases, three out of four had GT `file_b` and the model
> produced its default `use file_B` response. In the seven sampled SWE-Sonnet
> real-fail TA cases, GT was varied (`file_a`, `file_g`, `test_suite`) and the
> model's `file_B`/`error_class_B` defaults missed. The negative gap is a real
> artefact of how the model's default-guess prior interacts with the marginal
> versus conditional ToolAvailability distributions in SWE; it is not statistical
> noise. A scoring metric that conditioned on local context rather than
> marginal-distribution match would likely reverse the sign — left for
> follow-up work.

---

## Proposed addition to §5.3 (Sonnet compression — qualitative confirmation)

Currently §5.3 frames Sonnet's lower L1 gap as the "smarter-models compress the
gap" effect. Supplementary §3.6 confirms this qualitatively:

> Supplementary §3.6 finds that Sonnet shows stronger response mode-collapse
> than Haiku: in TB-Sonnet real-match cases, `use file_a` appears in 12/20
> responses; in TB-Haiku real-match cases the same prefix appears only 3/20
> with phase transitions and error resolutions making up the rest. Sonnet
> defaults more aggressively to a single high-prior action (`use file_A` in
> TB; `resolve_error_class_B` in SWE). This default fires on both real and
> shuffled chains alike, lifting the shuffled rate and compressing the gap.
> Haiku's more varied response distribution loses on "easy" cases but is more
> discriminating between conditions.

---

## Proposed addition to §5 (new subsection: failure-mode characterisation)

> **§5.x Source-conditioned response priors.** The error analysis (Supplementary
> §3.4–3.5) finds that when the model cannot predict the next constraint
> (typically because the cutoff is a `ResourceBudget(context_window)`), it
> falls back to a source-conditioned default: `switch to <phase>` on TB,
> `resolve_error_class_B` on SWE. The fallback is symmetric across real and
> shuffled within a source — the model fails the same way on the same vacuous-
> cutoff cases. This supports the actionable-L1 refinement (§5.1): vacuous
> cutoffs do not differentiate the conditions and are correctly excluded by
> the refinement.

---

## What the error analysis does NOT support

- It does not propose any change to the headline numbers in §4 of WRITEUP.md.
- It does not propose changing the pre-registered scoring metric. The
  marginal-vs-conditional metric question (§3.7) is flagged as follow-up work,
  not a v2 amendment.
- It does not weaken the actionable-L1 refinement — if anything, the
  source-conditioned fallback pattern (§3.4–3.5) strengthens the argument that
  vacuous cutoffs were correctly identified as non-differentiating.
