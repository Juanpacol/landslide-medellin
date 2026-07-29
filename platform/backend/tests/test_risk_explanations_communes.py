"""Regression test: agent/risk_explanations.py used to keep its own `_IS_LADERA` dict keyed on
official codes ("50".."90"), so corregimientos looked up by canonical id ("17".."21") — how
every other part of the system addresses them, per domain/communes.py — always fell through to
`is_ladera=False`. All five corregimientos are hillside terrain.
"""

from __future__ import annotations

from agent.risk_explanations import _commune_is_ladera, _commune_name


def test_corregimientos_are_ladera_by_canonical_id():
    for cid in ("17", "18", "19", "20", "21"):
        assert _commune_is_ladera(cid) is True


def test_commune_name_matches_domain_communes():
    assert _commune_name("18") == "San Cristóbal"
    assert _commune_name("14") == "El Poblado"
