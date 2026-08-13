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


def test_health_is_503_when_the_database_is_unreachable(settings, tmp_path) -> None:
    """Docker's healthcheck is `curl -fsS`, which only fails on >=400.

    Returning 200 with status:"degraded" means a container that cannot reach its
    database reports itself healthy — the exact failure a healthcheck exists to
    catch.
    """
    import sqlite3

    from fastapi.testclient import TestClient

    from recimin.api.main import create_app

    def broken() -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn  # no schema, so queue_depth raises

    with TestClient(create_app(settings, db_factory=broken, migrate=False)) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
