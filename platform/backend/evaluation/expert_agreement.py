"""Cohen's kappa for the DAGRD expert-agreement rubric (specs/007-experimental-eval/spec.md
task: "expert agreement (20-case DAGRD rubric, Cohen's κ)"). Pure statistics, no I/O — the rubric
itself (`evaluation/rubric.md`) is a template for human judges; this module is ready to score
their responses the moment they exist, but does not simulate or fabricate judgments.
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
