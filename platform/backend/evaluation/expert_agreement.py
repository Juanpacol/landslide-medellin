"""Statistics for the DAGRD expert-agreement rubric (specs/007-experimental-eval/spec.md task:
"expert agreement (20-case DAGRD rubric, Cohen's κ)"). Pure statistics, no I/O — the rubric
itself (`evaluation/rubric.md`) is a template for human judges; this module is ready to score
their responses the moment they exist, but does not simulate or fabricate judgments.

Two independent methodologies, both scored here:
  - Absolute categorical judgment (bajo/medio/alto/critico per case) -> `cohens_kappa()`.
  - Relative ranking of a case set by risk (rank 1 = highest) -> `kendalls_tau()`. A ranking
    judgment is easier for a human expert to give reliably than a category boundary call ("is
    this a 6 or a 7 out of 10 landslide risk"), and doesn't require the expert to share TEYVA's
    exact category thresholds (`domain/risk_rules.py`) to be useful evidence.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

CATEGORIES: tuple[str, ...] = ("bajo", "medio", "alto", "critico")


@dataclass(frozen=True)
class AgreementReport:
    n_cases: int
    observed_agreement: float
    expected_agreement: float
    kappa: float

    @property
    def interpretation(self) -> str:
        """Landis & Koch (1977) benchmark bands — standard reference for κ, not a
        TEYVA-specific threshold."""
        k = self.kappa
        if k < 0:
            return "poor"
        if k < 0.20:
            return "slight"
        if k < 0.40:
            return "fair"
        if k < 0.60:
            return "moderate"
        if k < 0.80:
            return "substantial"
        return "almost perfect"


def cohens_kappa(judge_a: list[str], judge_b: list[str]) -> AgreementReport:
    """Cohen's κ between two raters' category judgments over the same N cases.

    κ = (p_o - p_e) / (1 - p_e), where p_o is observed agreement and p_e is the
    agreement expected by chance given each rater's marginal category distribution.
    """
    if len(judge_a) != len(judge_b):
        raise ValueError(f"judges must rate the same cases: {len(judge_a)} != {len(judge_b)}")
    n = len(judge_a)
    if n == 0:
        return AgreementReport(n_cases=0, observed_agreement=0.0, expected_agreement=0.0, kappa=0.0)

    observed = sum(1 for a, b in zip(judge_a, judge_b, strict=True) if a == b) / n

    counts_a = Counter(judge_a)
    counts_b = Counter(judge_b)
    categories = set(counts_a) | set(counts_b)
    expected = sum((counts_a.get(c, 0) / n) * (counts_b.get(c, 0) / n) for c in categories)

    kappa = (observed - expected) / (1 - expected) if expected != 1.0 else 1.0

    return AgreementReport(
        n_cases=n,
        observed_agreement=round(observed, 4),
        expected_agreement=round(expected, 4),
        kappa=round(kappa, 4),
    )


@dataclass(frozen=True)
class RankCorrelationReport:
    n_cases: int
    n_concordant: int
    n_discordant: int
    tau: float

    @property
    def interpretation(self) -> str:
        """Same Landis & Koch (1977) bands `AgreementReport` uses — τ and κ aren't the same
        statistic, but both range roughly [-1, 1] with 0 meaning chance-level agreement, so
        reusing the band language keeps the two reports easy to read side by side."""
        t = self.tau
        if t < 0:
            return "poor"
        if t < 0.20:
            return "slight"
        if t < 0.40:
            return "fair"
        if t < 0.60:
            return "moderate"
        if t < 0.80:
            return "substantial"
        return "almost perfect"


def kendalls_tau(ranking_a: list[float], ranking_b: list[float]) -> RankCorrelationReport:
    """Kendall's tau-b between two rankings of the SAME N cases, in the same case order (i.e.
    `ranking_a[i]` and `ranking_b[i]` are two raters' rank/score for case i — not two lists of
    case identifiers in rank order).

    Tau-b (not tau-a): handles tied ranks, which a human expert ranking-by-risk will produce
    routinely ("these two cases feel equally risky to me").

    τ_b = (n_concordant - n_discordant) / sqrt((n0 - n1) * (n0 - n2))
    where n0 = n(n-1)/2, n1/n2 correct for ties in each ranking.
    """
    if len(ranking_a) != len(ranking_b):
        raise ValueError(
            f"rankings must cover the same cases: {len(ranking_a)} != {len(ranking_b)}"
        )
    n = len(ranking_a)
    if n < 2:
        return RankCorrelationReport(n_cases=n, n_concordant=0, n_discordant=0, tau=0.0)

    concordant = 0
    discordant = 0
    ties_a = 0  # pairs tied in ranking_a (n1), regardless of ranking_b
    ties_b = 0  # pairs tied in ranking_b (n2), regardless of ranking_a
    for i in range(n):
        for j in range(i + 1, n):
            da = ranking_a[i] - ranking_a[j]
            db = ranking_b[i] - ranking_b[j]
            if da == 0:
                ties_a += 1
            if db == 0:
                ties_b += 1
            if da == 0 or db == 0:
                continue  # excluded from concordant/discordant, per tau-b convention
            if (da > 0) == (db > 0):
                concordant += 1
            else:
                discordant += 1

    n0 = n * (n - 1) / 2
    n1 = ties_a
    n2 = ties_b
    denom = ((n0 - n1) * (n0 - n2)) ** 0.5
    tau = (concordant - discordant) / denom if denom > 0 else 0.0

    return RankCorrelationReport(
        n_cases=n,
        n_concordant=concordant,
        n_discordant=discordant,
        tau=round(tau, 4),
    )
