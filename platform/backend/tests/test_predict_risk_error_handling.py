"""Tests de application/predict_risk.py::_classify_predict_exception y
_predict_one_commune. Sin BD real: predict_risk() se monkeypatchea.

Antes predict_risk() se llamaba sin ningún try/except dentro del loop de
21 comunas — una excepción sin capturar abortaba TODO el batch (el commit
ocurre una sola vez al final). Este test reproduce exactamente ese caso.
"""

from __future__ import annotations

import pytest

from application.predict_risk import (
    _PREDICTION_FALLBACK,
    _classify_predict_exception,
    _predict_one_commune,
)
from errors.error_handler import BusinessError, TransientError


class TestClassifyPredictException:
    def test_io_es_transitorio(self) -> None:
        assert isinstance(_classify_predict_exception(OSError("disco lleno")), TransientError)
        assert isinstance(_classify_predict_exception(TimeoutError("timeout")), TransientError)
        assert isinstance(_classify_predict_exception(ConnectionError("db caída")), TransientError)

    def test_resto_es_business(self) -> None:
        assert isinstance(_classify_predict_exception(KeyError("feature faltante")), BusinessError)
        assert isinstance(_classify_predict_exception(ValueError("dato corrupto")), BusinessError)


class TestPredictOneCommune:
    pytestmark = pytest.mark.asyncio

    async def test_una_comuna_fallida_no_aborta_el_batch(self, monkeypatch) -> None:
        # Reproduce el bug real: antes esto habría propagado la excepción y
        # tumbado el loop completo de run_predictions para las 21 comunas.
        import ml.predict

        async def _boom(cid, db):
            raise KeyError("features faltantes para esta comuna")

        monkeypatch.setattr(ml.predict, "predict_risk", _boom)

        result = await _predict_one_commune("99", db=None)

        assert result == _PREDICTION_FALLBACK

    async def test_comuna_exitosa_devuelve_su_resultado(self, monkeypatch) -> None:
        import ml.predict

        expected = {"risk_score": 0.42, "risk_level": "medio", "confidence": 0.8, "features_used": {}}

        async def _ok(cid, db):
            return expected

        monkeypatch.setattr(ml.predict, "predict_risk", _ok)

        result = await _predict_one_commune("1", db=None)

        assert result == expected

    async def test_fallo_transitorio_reintenta(self, monkeypatch) -> None:
        import ml.predict

        calls = 0

        async def _flaky(cid, db):
            nonlocal calls
            calls += 1
            if calls < 2:
                raise ConnectionError("caída temporal")
            return {"risk_score": 0.1, "risk_level": "bajo", "confidence": 0.5, "features_used": {}}

        monkeypatch.setattr(ml.predict, "predict_risk", _flaky)

        result = await _predict_one_commune("1", db=None)

        # retries=2 en _predict_one_commune: 2 intentos totales, no 2 extra.
        assert calls == 2
        assert result["risk_level"] == "bajo"
        assert result != _PREDICTION_FALLBACK
