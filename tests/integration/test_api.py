"""Integration tests for all FastAPI routes.

Uses TestClient (synchronous) — no real DB, no real data.
Tests that all routes return expected status codes and basic structure.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from webapp.main import create_app


@pytest.fixture
def client(tmp_path):  # type: ignore[no-untyped-def]
    """FastAPI test client with fresh DB."""
    import os
    import config.settings as _settings_mod

    _settings_mod._settings = None  # reset singleton so new env vars take effect
    os.environ["DB_PATH"] = str(tmp_path / "test.db")
    os.environ["DATA_DIR"] = str(tmp_path / "raw")
    os.environ["AUTOSTART_RUNNER"] = "false"
    app = create_app()
    with TestClient(app) as c:
        yield c
    _settings_mod._settings = None  # cleanup


def test_dashboard_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "quant-v2" in response.text.lower()


def test_pipeline_page(client: TestClient) -> None:
    response = client.get("/pipeline")
    assert response.status_code == 200


def test_lab_page(client: TestClient) -> None:
    response = client.get("/lab")
    assert response.status_code == 200


def test_strategies_page(client: TestClient) -> None:
    response = client.get("/strategies")
    assert response.status_code == 200


def test_portfolio_page(client: TestClient) -> None:
    response = client.get("/portfolio")
    assert response.status_code == 200


def test_settings_page(client: TestClient) -> None:
    response = client.get("/settings")
    assert response.status_code == 200


def test_automation_status(client: TestClient) -> None:
    response = client.get("/api/automation/status")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert data["running"] is False


def test_start_stop_automation(client: TestClient) -> None:
    response = client.post("/api/automation/start")
    assert response.status_code == 200
    response = client.post("/api/automation/stop")
    assert response.status_code == 200


def test_list_strategies_api(client: TestClient) -> None:
    response = client.get("/api/strategies")
    assert response.status_code == 200
    data = response.json()
    assert "strategies" in data
    assert "ema_rsi" in data["strategies"]


def test_list_experiments_api(client: TestClient) -> None:
    response = client.get("/api/experiments")
    assert response.status_code == 200
    data = response.json()
    assert "experiments" in data


def test_seed_via_form_data(client: TestClient) -> None:
    """Seed endpoint accepts form-encoded data (HTMX sends this, not JSON)."""
    response = client.post(
        "/api/seed",
        data={"strategy": "ema_rsi", "tickers": ["MNQ"], "timeframes": ["15m"], "priority": "0"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "seeded" in data


def test_fwd_ready_page(client: TestClient) -> None:
    response = client.get("/fwd-ready")
    assert response.status_code == 200
    assert "FWD_READY" in response.text


def test_approve_not_found(client: TestClient) -> None:
    response = client.post("/api/experiments/99999/approve")
    assert response.status_code == 404


def test_approve_wrong_gate(client: TestClient) -> None:
    """Cannot approve an experiment that isn't at FWD_READY gate."""
    # First seed an experiment (at SCREEN gate)
    client.post(
        "/api/seed",
        data={"strategy": "ema_rsi", "tickers": ["MNQ"], "timeframes": ["15m"]},
    )
    response = client.post("/api/experiments/1/approve")
    assert response.status_code == 400
