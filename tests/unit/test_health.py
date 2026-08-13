"""The /health endpoint is the container healthcheck and the deploy smoke test."""

from fastapi.testclient import TestClient

from recimin import __version__


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_docs_are_disabled(client: TestClient) -> None:
    """No interactive docs on a household app exposed to the internet."""
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
