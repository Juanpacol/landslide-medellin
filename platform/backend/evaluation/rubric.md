# DAGRD Expert-Agreement Rubric — Template

**Status: template, not conducted.** No rows below are filled with real judgments — this
document is ready to run the moment two or more DAGRD domain experts are available; see
`docs/research/paper.md` §5.6 and §6 for why it wasn't conducted in this research cycle
(no access to human judges in this session).

## Purpose

Rule coverage and explanation faithfulness (`docs/research/paper.md` §5.2, §5.4) measure
properties of the *system*. This rubric measures whether the system's conclusions match what a
domain expert would independently conclude from the same evidence — the closest thing to a
validity check available without a real landslide-event dataset (`docs/research/audit-2026-07.md`
§8).

## Method

1. Select 20 cases: real `(commune_id, date)` pairs with enough data coverage that at least one
   `domain/rules/catalog.py` rule was evaluable (`RuleTrace.not_evaluable` excludes it) — a case
   where every rule is "not evaluable" gives an expert nothing to react to. Draw from
   `evaluation/primary_metrics.py::rule_coverage()`'s output to find them systematically, not by
   hand-picking favorable cases.
2. For each case, show two independent DAGRD-affiliated experts:
   - The territory's raw evidence (rain, seismic, terrain, prior events) — NOT the system's
     verdict or derivation, to avoid anchoring.
   - Ask: "What risk category (bajo/medio/alto/critico) would you assign?"
3. Record both experts' independent judgments in the table below, plus the system's own verdict
   for comparison (not agreement — the system is not a third rater, it's what's being validated).
4. Compute Cohen's κ between the two experts with `evaluation/expert_agreement.py::cohens_kappa()`
   — this measures inter-rater reliability of the rubric itself, a precondition for the
   expert-vs-system comparison meaning anything. Low expert-expert κ means the cases are
   ambiguous even for humans, and expert-vs-system agreement shouldn't be over-interpreted.
5. Separately, compute agreement between each expert's judgment and the system's verdict level
   (also via `cohens_kappa()`, treating the system as a third column) — this is the number that
   answers "does the system's conclusion match expert judgment", reported alongside, not
   conflated with, expert-expert reliability from step 4.

## Case table (fill after data collection)

| # | commune_id | date | Expert A | Expert B | System verdict | Notes |
|---|---|---|---|---|---|---|
| 1 | | | | | | |
| 2 | | | | | | |
| ... | | | | | | |
| 20 | | | | | | |

## Computing κ once filled

```python
from evaluation.expert_agreement import cohens_kappa

expert_a = [...]  # 20 category strings, in case order
expert_b = [...]
system   = [...]

expert_reliability = cohens_kappa(expert_a, expert_b)
system_vs_a = cohens_kappa(system, expert_a)
system_vs_b = cohens_kappa(system, expert_b)
```

## Honesty note

An unfilled rubric is not a negative result — it's an open item. Do not fill this table with
placeholder or synthetic values to make the paper look more complete; `docs/research/paper.md`
§5.6 already states plainly that this was not conducted, and that remains true until real
DAGRD-affiliated experts fill it in.
