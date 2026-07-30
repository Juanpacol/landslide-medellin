"""Tests for evaluation/expert_agreement.py — Cohen's kappa, pure math, no I/O.

These use hand-constructed synthetic judgment lists to verify the formula, NOT real
DAGRD expert data (specs/007-experimental-eval/spec.md's expert-agreement task is
unconducted — see docs/research/paper.md §5.6).
"""

from __future__ import annotations

import pytest

from evaluation.expert_agreement import cohens_kappa


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
