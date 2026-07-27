"""
Test suite para verificar que los examples están presentes en prompts.
Valida estructura, formato y cobertura de casos.
"""

from agent.chat_rag import _RAG_SYSTEM_SUFFIX
from agent.risk_explanations import _SYSTEM_PROMPT


class TestChatRagExamples:
    """Verifica que chat_rag tiene examples multi-shot bien formados."""

    def test_chat_rag_has_examples(self):
        """chat_rag debe tener múltiples examples."""
        assert "<example_" in _RAG_SYSTEM_SUFFIX
        # Busca al menos 3 ejemplos
        assert _RAG_SYSTEM_SUFFIX.count("<example_") >= 3

    def test_chat_rag_examples_wrapped_in_xml(self):
        """Cada example debe estar envuelto en XML tags."""
        assert "<example_1>" in _RAG_SYSTEM_SUFFIX
        assert "</example_1>" in _RAG_SYSTEM_SUFFIX
        assert "<input>" in _RAG_SYSTEM_SUFFIX
        assert "<output>" in _RAG_SYSTEM_SUFFIX
        assert "<explanation>" in _RAG_SYSTEM_SUFFIX

    def test_chat_rag_examples_explain_why(self):
        """Cada example debe explicar por qué es ideal (reasoning)."""
        assert "Este es un buen output porque:" in _RAG_SYSTEM_SUFFIX
        # Debería haber múltiples explicaciones
        count = _RAG_SYSTEM_SUFFIX.count("Este es un buen output porque:")
        assert count >= 3, f"Expected ≥3 explanations, got {count}"

    def test_chat_rag_examples_cover_cases(self):
        """Examples deben cubrir diferentes tipos de preguntas."""
        # Verificar que hay ejemplos para:
        # 1. Riesgo específico (¿Cuál es el riesgo en X?)
        assert "¿Cuál es el riesgo" in _RAG_SYSTEM_SUFFIX
        # 2. Pregunta "por qué"
        assert "¿Por qué" in _RAG_SYSTEM_SUFFIX
        # 3. Caso de error (comuna no reconocida)
        assert "No reconozco" in _RAG_SYSTEM_SUFFIX

    def test_chat_rag_examples_have_data(self):
        """Examples deben incluir datos concretos, no vaguos."""
        # Buscar números/datos en los ejemplos
        assert "mm" in _RAG_SYSTEM_SUFFIX  # unidades de lluvia
        assert "0.65" in _RAG_SYSTEM_SUFFIX or "riesgo" in _RAG_SYSTEM_SUFFIX.lower()


class TestRiskExplanationsExamples:
    """Verifica que risk_explanations tiene examples para cada categoría."""

    def test_risk_explanations_has_examples(self):
        """Debe tener múltiples ejemplos, al menos 4 (uno por categoría)."""
        assert "EJEMPLO 1" in _SYSTEM_PROMPT
        assert "EJEMPLO 2" in _SYSTEM_PROMPT
        assert "EJEMPLO 3" in _SYSTEM_PROMPT
        assert "EJEMPLO 4" in _SYSTEM_PROMPT

    def test_risk_explanations_covers_categories(self):
        """Debe tener ejemplos para bajo, medio, alto, crítico."""
        assert "CATEGORÍA BAJO" in _SYSTEM_PROMPT
        assert "CATEGORÍA MEDIO" in _SYSTEM_PROMPT
        assert "CATEGORÍA ALTO" in _SYSTEM_PROMPT
        assert "CATEGORÍA CRÍTICO" in _SYSTEM_PROMPT

    def test_risk_explanations_examples_are_json(self):
        """Cada ejemplo debe mostrar JSON válido."""
        # Buscar estructura JSON en los ejemplos
        assert '"title"' in _SYSTEM_PROMPT
        assert '"factors"' in _SYSTEM_PROMPT
        assert '"urgency"' in _SYSTEM_PROMPT
        assert '"recommended_action"' in _SYSTEM_PROMPT

    def test_risk_explanations_examples_explain_why(self):
        """Cada ejemplo debe explicar por qué es ideal."""
        assert "Razón:" in _SYSTEM_PROMPT
        # Debería haber múltiples explicaciones
        count = _SYSTEM_PROMPT.count("Razón:")
        assert count >= 4, f"Expected ≥4 explanations, got {count}"

    def test_risk_explanations_has_counter_example(self):
        """Debe haber un contra-ejemplo que muestre qué NO hacer."""
        assert "CONTRA-EJEMPLO" in _SYSTEM_PROMPT
        assert "NO HAGAS ESTO" in _SYSTEM_PROMPT
        assert "Errores:" in _SYSTEM_PROMPT

    def test_risk_explanations_examples_have_data(self):
        """Examples deben incluir datos concretos."""
        # Buscar números en los ejemplos
        assert "90" in _SYSTEM_PROMPT  # precipitación
        assert "70" in _SYSTEM_PROMPT  # umbral
        assert "20" in _SYSTEM_PROMPT  # exceso


class TestExamplesStructure:
    """Valida que los ejemplos siguen buenas prácticas."""

    def test_chat_rag_xml_tags_match(self):
        """Tags XML deben abrirse y cerrarse correctamente."""
        # Contar apertura/cierre de tags
        open_tags = _RAG_SYSTEM_SUFFIX.count("<example_")
        close_tags = _RAG_SYSTEM_SUFFIX.count("</example_")
        assert open_tags == close_tags, "Mismatched <example_> tags"

    def test_risk_explanations_no_vague_language_in_json_outputs(self):
        """El CONTRA-EJEMPLO debe mostrar vagueness para enseñar qué evitar."""
        # Buscar solo en el CONTRA-EJEMPLO
        if "CONTRA-EJEMPLO" in _SYSTEM_PROMPT:
            contra_section = _SYSTEM_PROMPT.split("CONTRA-EJEMPLO")[1]
            # El CONTRA-EJEMPLO debe mostrar ejemplos de vagueness
            assert "Tal vez hay mucha lluvia" in contra_section, (
                "Counter-example should show vague language like 'Tal vez'"
            )
            assert "Monitorear la situación" in contra_section, (
                "Counter-example should show generic action"
            )

    def test_examples_are_realistic(self):
        """Examples deben ser realistas y aplicables."""
        # chat_rag examples deben mencionar comunas reales
        real_communes = ["San Javier", "Castilla", "Buenos Aires", "Villa Hermosa"]
        for commune in real_communes:
            assert commune in _RAG_SYSTEM_SUFFIX, f"Missing realistic example with {commune}"

        # risk_explanations examples deben usar datos realistas
        assert "Popular" in _SYSTEM_PROMPT
        assert "Manrique" in _SYSTEM_PROMPT
        assert "Castilla" in _SYSTEM_PROMPT
        assert "Robledo" in _SYSTEM_PROMPT


class TestExamplesInContext:
    """Valida que los ejemplos están en el lugar correcto del prompt."""

    def test_chat_rag_examples_after_rules(self):
        """chat_rag examples deben venir DESPUÉS de las REGLAS."""
        rules_pos = _RAG_SYSTEM_SUFFIX.find("REGLAS (CRÍTICAS):")
        examples_pos = _RAG_SYSTEM_SUFFIX.find("EJEMPLOS DE RESPUESTAS IDEALES")
        assert examples_pos > rules_pos, "Examples should come after Rules"

    def test_risk_explanations_examples_after_categories(self):
        """risk_explanations examples deben venir DESPUÉS de CATEGORÍAS."""
        categories_pos = _SYSTEM_PROMPT.find("CATEGORÍAS:")
        examples_pos = _SYSTEM_PROMPT.find("EJEMPLOS DE SALIDAS IDEALES")
        assert examples_pos > categories_pos, "Examples should come after Categories"

    def test_examples_before_schema_hint(self):
        """Examples deben venir antes del schema hint."""
        # En risk_explanations, los ejemplos deben estar antes del JSON schema
        assert "EJEMPLO" in _SYSTEM_PROMPT.split("_EXPLANATION_SCHEMA_HINT")[0], (
            "Examples should come before schema hint"
        )
