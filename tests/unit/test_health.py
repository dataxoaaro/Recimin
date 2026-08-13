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


def test_api_docs_are_not_served(client: TestClient) -> None:
    """No Swagger and no schema on a household app exposed to the internet.

    /docs returns 200 because the SPA catch-all serves the shell for any unknown
    path — the assertion that matters is that it is not the Swagger UI.
    """
    assert "swagger-ui" not in client.get("/docs").text.lower()
    assert client.get("/openapi.json").status_code != 200 or (
        "openapi" not in client.get("/openapi.json").text[:200].lower()
    )
