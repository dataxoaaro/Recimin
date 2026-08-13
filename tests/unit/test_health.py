"""The /health endpoint is the container healthcheck and the deploy smoke test."""

from fastapi.testclient import TestClient

from recimin import __version__


def test_health_reports_version_and_queue_depth(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["queue"] == 0


def test_health_needs_no_authentication(client: TestClient) -> None:
    """Docker's healthcheck has no cookie."""
    assert client.get("/health").status_code == 200


def test_docs_are_disabled(client: TestClient) -> None:
    """No interactive docs on a household app exposed to the internet."""
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
