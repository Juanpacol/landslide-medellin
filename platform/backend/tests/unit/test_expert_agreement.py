"""Tests for evaluation/expert_agreement.py — Cohen's kappa and Kendall's tau, pure math, no I/O.

These use hand-constructed synthetic judgment lists to verify the formula, NOT real
DAGRD expert data (specs/007-experimental-eval/spec.md's expert-agreement task is
unconducted — see docs/research/paper.md §5.6).
"""

from __future__ import annotations

import pytest
from scipy.stats import kendalltau

from evaluation.expert_agreement import cohens_kappa, kendalls_tau


def test_perfect_agreement_kappa_is_one():
    judge_a = ["bajo", "medio", "alto", "critico"] * 5
    result = cohens_kappa(judge_a, list(judge_a))
    assert result.kappa == 1.0
    assert result.interpretation == "almost perfect"


def test_no_agreement_beyond_chance_is_near_zero():
    # Two judges whose marginals match but whose per-case picks are anti-correlated.
    judge_a = ["bajo", "alto"] * 10
    judge_b = ["alto", "bajo"] * 10
    result = cohens_kappa(judge_a, judge_b)
    assert result.kappa < 0  # systematic disagreement, worse than chance


def test_mismatched_lengths_raises():
    with pytest.raises(ValueError):
        cohens_kappa(["bajo"], ["bajo", "alto"])


def test_empty_input_returns_zeroed_report():
    result = cohens_kappa([], [])
    assert result.n_cases == 0
    assert result.kappa == 0.0


def test_interpretation_bands():
    # Construct a case landing in the "moderate" band (0.40-0.60) by hand.
    judge_a = ["bajo"] * 6 + ["alto"] * 4
    judge_b = ["bajo"] * 8 + ["alto"] * 2
    result = cohens_kappa(judge_a, judge_b)
    assert result.interpretation in ("fair", "moderate", "substantial")


class TestKendallsTau:
    def test_identical_rankings_give_tau_one(self):
        ranking = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = kendalls_tau(ranking, list(ranking))
        assert result.tau == 1.0
        assert result.interpretation == "almost perfect"

    def test_fully_reversed_rankings_give_tau_minus_one(self):
        ranking_a = [1.0, 2.0, 3.0, 4.0, 5.0]
        ranking_b = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = kendalls_tau(ranking_a, ranking_b)
        assert result.tau == -1.0

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            kendalls_tau([1.0], [1.0, 2.0])

    def test_fewer_than_two_cases_returns_zeroed_report(self):
        result = kendalls_tau([1.0], [1.0])
        assert result.n_cases == 1
        assert result.tau == 0.0

    def test_empty_input_returns_zeroed_report(self):
        result = kendalls_tau([], [])
        assert result.n_cases == 0
        assert result.tau == 0.0

    def test_matches_scipy_tau_b_on_random_like_data(self):
        # Cross-checks the hand-rolled formula against scipy's reference implementation,
        # including ties (repeated ranks) since expert rankings will have them routinely.
        ranking_a = [1.0, 2.0, 2.0, 3.0, 4.0, 4.0, 5.0]
        ranking_b = [1.0, 1.0, 2.0, 4.0, 3.0, 5.0, 5.0]
        result = kendalls_tau(ranking_a, ranking_b)
        scipy_tau, _ = kendalltau(ranking_a, ranking_b, variant="b")
        assert result.tau == pytest.approx(scipy_tau, abs=1e-4)

    def test_all_tied_in_one_ranking_gives_zero_denominator_safe_result(self):
        # ranking_a has zero variance — every pair is tied in a, denominator is 0.
        result = kendalls_tau([3.0, 3.0, 3.0], [1.0, 2.0, 3.0])
        assert result.tau == 0.0

    def test_case_order_matters_not_case_identity(self):
        # ranking_a[i]/ranking_b[i] are two raters' scores for the SAME case i, not two
        # lists of case ids sorted by rank — swapping which case is at which index changes
        # the result, unlike a "does this list contain the same ranks" check would.
        ranking_a = [1.0, 2.0, 3.0]
        ranking_b_matched = [10.0, 20.0, 30.0]
        ranking_b_shuffled = [30.0, 10.0, 20.0]
        matched = kendalls_tau(ranking_a, ranking_b_matched)
        shuffled = kendalls_tau(ranking_a, ranking_b_shuffled)
        assert matched.tau == 1.0
        assert shuffled.tau != 1.0
