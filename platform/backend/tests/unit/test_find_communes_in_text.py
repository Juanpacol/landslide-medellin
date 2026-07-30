"""Regresión del NameError de find_communes_in_text.

La función usaba `_ALIAS_TO_ID` desde agent/tools.py, donde ese nombre no
existía: el refactor "PR1 — domain layer" había movido el mapa de alias a
domain/communes.py. Resultado: NameError en CADA llamada, y se llama desde
agent/rag_tools.py (_resolve_commune_loose → report_incident) y desde
agent/chat.py en los dos flujos del chat clásico.

Ruff lo reportaba como F821 pero el lint del backend no era bloqueante en CI,
así que nunca falló nada visiblemente.
"""

from __future__ import annotations

from agent.tools import find_communes_in_text as from_agent
from domain.communes import find_communes_in_text


class TestNoLanzaNameError:
    def test_el_caso_que_estaba_roto(self) -> None:
        # Antes: NameError: name '_ALIAS_TO_ID' is not defined
        assert find_communes_in_text("riesgo en villatina y comuna 8") is not None

    def test_agent_tools_reexporta_la_misma_funcion(self) -> None:
        # agent/tools.py la re-exporta porque chat.py y rag_tools.py la importan de ahí.
        assert from_agent is find_communes_in_text


class TestResuelveAlias:
    def test_encuentra_por_nombre(self) -> None:
        assert "16" in find_communes_in_text("hay grietas en Belén")

    def test_encuentra_alias_extra(self) -> None:
        assert "11" in find_communes_in_text("qué pasa en laureles")

    def test_ignora_acentos_y_mayusculas(self) -> None:
        assert find_communes_in_text("BELÉN") == find_communes_in_text("belen")

    def test_varias_comunas_en_orden_de_aparicion(self) -> None:
        result = find_communes_in_text("primero belen y después laureles")
        assert result.index("16") < result.index("11")

    def test_sin_menciones_devuelve_vacio(self) -> None:
        assert find_communes_in_text("hola, cómo está el clima") == []

    def test_no_matchea_subcadenas(self) -> None:
        # El patrón usa lookarounds para no matchear alias dentro de otra palabra.
        assert find_communes_in_text("belenita") == []
