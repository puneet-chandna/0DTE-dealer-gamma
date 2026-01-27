"""0DTE GEX Backend - API Tests."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoints:
    """Test health and root endpoints."""

    def test_root_endpoint(self):
        """Root should return API info."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "0DTE GEX API"
        assert "version" in data

    def test_health_check(self):
        """Health check should return healthy status."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestGEXEndpoints:
    """Test GEX API endpoints."""

    def test_current_gex_returns_501(self):
        """Current GEX should return 501 until implemented."""
        response = client.get("/api/gex/current")

        # Should return 501 Not Implemented
        assert response.status_code == 501

    def test_regime_returns_501(self):
        """Regime endpoint should return 501 until implemented."""
        response = client.get("/api/gex/regime")

        assert response.status_code == 501
