"""
Pruebas de integración de los endpoints principales de la API REST.

Requieren el backend corriendo en http://localhost:8000.
Ejecutar con: pytest tests/integration/ -v --tb=short
"""
import pytest
import httpx


BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def client():
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


class TestHealthEndpoints:
    def test_health_ok(self, client):
        """El health check debe retornar status ok."""
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") == "ok"


class TestRiskEndpoints:
    def test_get_comunas_returns_geojson(self, client):
        """GET /api/risk/comunas debe retornar un GeoJSON válido con 21 features."""
        r = client.get("/api/risk/comunas")
        assert r.status_code == 200
        body = r.json()
        assert body.get("type") == "FeatureCollection"
        assert len(body.get("features", [])) == 21

    def test_get_commune_detail(self, client):
        """GET /api/risk/comuna/13/detalle debe retornar datos de San Javier."""
        r = client.get("/api/risk/comuna/13/detalle")
        assert r.status_code == 200
        body = r.json()
        assert body.get("commune_id") == "13"
        assert "risk_score" in body
        assert "risk_category" in body
        assert body["risk_category"] in {"bajo", "medio", "alto", "critico"}

    def test_invalid_commune_returns_404(self, client):
        """Una comuna inexistente debe retornar 404."""
        r = client.get("/api/risk/comuna/99/detalle")
        assert r.status_code in {404, 422}


class TestChatEndpoint:
    def test_chat_returns_response(self, client):
        """POST /api/chat debe retornar una respuesta de texto."""
        r = client.post(
            "/api/chat",
            json={"message": "¿Cuáles son las comunas con mayor riesgo?", "session_id": "test-integration"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "response" in body or "message" in body or "content" in body


class TestScraperEndpoints:
    def test_scraper_status(self, client):
        """GET /api/scraper/status debe retornar el estado de las fuentes."""
        r = client.get("/api/scraper/status")
        assert r.status_code == 200
