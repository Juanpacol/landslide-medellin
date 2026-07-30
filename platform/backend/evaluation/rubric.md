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
system = [...]

expert_reliability = cohens_kappa(expert_a, expert_b)
system_vs_a = cohens_kappa(system, expert_a)
system_vs_b = cohens_kappa(system, expert_b)
```

## Alternative method: relative ranking

Absolute categorical judgment (above) asks an expert to place a case in one of four boxes —
which requires the expert to implicitly agree with `domain/risk_rules.py`'s exact thresholds
(0.35/0.65/0.90) to be scored as "correct" against them. A landslide-risk expert may be
confident that case A is riskier than case B without being confident whether either crosses a
specific numeric boundary. Relative ranking sidesteps that: it only asks for an ordering, which
is both easier to give reliably and doesn't smuggle in agreement with TEYVA's own category
cutoffs as a precondition for the comparison meaning anything.

1. Use the same 20-case selection as above (real cases with at least one evaluable rule).
2. Show each expert the same 20 cases' raw evidence (same anti-anchoring rule: no system verdict
   shown), and ask them to **rank all 20 from highest to lowest perceived risk** (ties allowed —
   "these feel equally risky" is a valid answer, not a forced tie-break).
3. Record each expert's rank (1 = highest risk) per case in the table below, plus the system's
   own resolved `score` (not category) for the same cases, used as its implicit ranking.
4. Compute agreement with `evaluation/expert_agreement.py::kendalls_tau()`:
   - Expert A vs. Expert B — reliability of the ranking task itself (precondition for step 5
     meaning anything, same logic as Cohen's κ in the categorical method).
   - Expert A vs. system score, Expert B vs. system score — does the system's *relative*
     ordering of cases match expert judgment, independent of whether its absolute category
     cutoffs are right.

### Ranking case table (fill after data collection)

| # | commune_id | date | Expert A rank | Expert B rank | System score |
|---|---|---|---|---|---|
| 1 | | | | | |
| 2 | | | | | |
| ... | | | | | |
| 20 | | | | | |

### Computing τ once filled

```python
from evaluation.expert_agreement import kendalls_tau

expert_a_ranks = [...]  # 20 ranks (ties allowed), in case order
expert_b_ranks = [...]
system_scores = [...]  # 20 raw hazard scores, same case order — not categories

ranking_reliability = kendalls_tau(expert_a_ranks, expert_b_ranks)
system_vs_a = kendalls_tau(system_scores, expert_a_ranks)
system_vs_b = kendalls_tau(system_scores, expert_b_ranks)
```

Both methodologies (categorical κ and ranking τ) can be run on the same 20 cases without
conflict — they measure different things and neither supersedes the other. Report whichever the
available experts' time allows; both together is strictly more evidence than either alone.

## Honesty note

An unfilled rubric is not a negative result — it's an open item. Do not fill this table with
placeholder or synthetic values to make the paper look more complete; `docs/research/paper.md`
§5.6 already states plainly that this was not conducted, and that remains true until real
DAGRD-affiliated experts fill it in.
