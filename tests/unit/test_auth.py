"""Authentication primitives and the auth routes."""

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from recimin.api import auth, ratelimit
from tests.conftest import TEST_EMAIL, TEST_PASSWORD, TEST_SITE_PASSWORD

SECRET = "s" * 32

# ─── primitives ──────────────────────────────────────────────────────────


def test_password_round_trip() -> None:
    stored = auth.hash_password("correct-horse-battery")
    assert auth.verify_password(stored, "correct-horse-battery") is True
    assert auth.verify_password(stored, "wrong") is False


def test_hash_is_salted() -> None:
    assert auth.hash_password("same-password") != auth.hash_password("same-password")


def test_short_passwords_are_refused() -> None:
    with pytest.raises(ValueError, match="at least"):
        auth.hash_password("short")


def test_verify_tolerates_a_corrupt_stored_hash() -> None:
    """A garbage hash must be a failed login, not a 500."""
    assert auth.verify_password("not-a-hash", "anything") is False


def test_constant_time_equals() -> None:
    assert auth.constant_time_equals("abc", "abc") is True
    assert auth.constant_time_equals("abc", "abd") is False
    assert auth.constant_time_equals("abc", "abcd") is False
    # A trailing newline in the stored secret is the classic deploy footgun.
    assert auth.constant_time_equals("abc", "abc\n") is False


def test_session_round_trip() -> None:
    token = auth.issue_session(42, SECRET)
    assert auth.read_session(token, SECRET) == 42


def test_session_rejects_a_foreign_signature() -> None:
    token = auth.issue_session(42, SECRET)
    assert auth.read_session(token, "d" * 32) is None


def test_session_rejects_expiry() -> None:
    past = datetime.now(UTC) - auth.SESSION_TTL - timedelta(minutes=1)
    token = auth.issue_session(42, SECRET, now=past)
    assert auth.read_session(token, SECRET) is None


def test_session_rejects_garbage() -> None:
    for bad in ("", "x", "a.b.c", "not.a.jwt"):
        assert auth.read_session(bad, SECRET) is None


def test_device_tokens_are_unique_and_hashed() -> None:
    first, first_hash = auth.generate_device_token()
    second, _ = auth.generate_device_token()
    assert first != second
    assert first_hash == auth.hash_device_token(first)
    assert first not in first_hash


# ─── rate limiting ───────────────────────────────────────────────────────


def test_rate_limit_trips_then_recovers_next_window(db: sqlite3.Connection) -> None:
    ratelimit.ensure_table(db)
    limit = (3, 60)
    base = 1_000_020.0  # aligned to a 60s window boundary

    assert [ratelimit.check_and_increment(db, "b", limit, now=base) for _ in range(3)] == [
        True,
        True,
        True,
    ]
    assert ratelimit.check_and_increment(db, "b", limit, now=base) is False
    # Still locked out for the rest of the window.
    assert ratelimit.check_and_increment(db, "b", limit, now=base + 30) is False
    # Fresh window.
    assert ratelimit.check_and_increment(db, "b", limit, now=base + 60) is True


def test_rate_limit_buckets_are_independent(db: sqlite3.Connection) -> None:
    ratelimit.ensure_table(db)
    limit = (1, 60)
    assert ratelimit.check_and_increment(db, "a", limit, now=0) is True
    assert ratelimit.check_and_increment(db, "b", limit, now=0) is True


# ─── routes ──────────────────────────────────────────────────────────────


def _register(client: TestClient, **overrides: str) -> object:
    payload = {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "display_name": "Aaro",
        "site_password": TEST_SITE_PASSWORD,
        **overrides,
    }
    return client.post("/api/auth/register", json=payload)


def test_full_auth_flow(client: TestClient) -> None:
    assert _register(client).status_code == 201  # type: ignore[attr-defined]
    assert client.get("/api/auth/me").json()["email"] == TEST_EMAIL

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    login = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_registration_requires_the_site_password(client: TestClient) -> None:
    response = _register(client, site_password="guess")
    assert response.status_code == 403  # type: ignore[attr-defined]
    assert client.get("/api/auth/me").status_code == 401


def test_registration_rejects_a_duplicate_email(client: TestClient) -> None:
    _register(client)
    assert _register(client, display_name="Someone else").status_code == 409  # type: ignore[attr-defined]


def test_registration_rejects_a_weak_password(client: TestClient) -> None:
    assert _register(client, password="short").status_code == 422  # type: ignore[attr-defined]


def test_login_is_vague_about_why_it_failed(client: TestClient) -> None:
    """Unknown email and wrong password must be indistinguishable."""
    _register(client)
    client.post("/api/auth/logout")

    unknown = client.post(
        "/api/auth/login", json={"email": "nobody@example.fi", "password": TEST_PASSWORD}
    )
    wrong = client.post(
        "/api/auth/login", json={"email": TEST_EMAIL, "password": "wrong-password-x"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_login_rate_limit_trips(client: TestClient) -> None:
    _register(client)
    client.post("/api/auth/logout")

    codes = [
        client.post(
            "/api/auth/login", json={"email": TEST_EMAIL, "password": "wrong-password-x"}
        ).status_code
        for _ in range(ratelimit.LOGIN_PER_EMAIL[0] + 1)
    ]
    assert codes[-1] == 429
    # Even the correct password is refused once the bucket is exhausted.
    assert (
        client.post(
            "/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        ).status_code
        == 429
    )


def test_change_password_requires_the_current_one(auth_client: TestClient) -> None:
    bad = auth_client.post(
        "/api/auth/change-password",
        json={"current_password": "not-it-at-all", "new_password": "brand-new-password"},
    )
    assert bad.status_code == 401

    good = auth_client.post(
        "/api/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "brand-new-password"},
    )
    assert good.status_code == 204

    auth_client.post("/api/auth/logout")
    assert (
        auth_client.post(
            "/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        ).status_code
        == 401
    )
    assert (
        auth_client.post(
            "/api/auth/login", json={"email": TEST_EMAIL, "password": "brand-new-password"}
        ).status_code
        == 200
    )


def test_session_for_a_deleted_user_is_rejected(
    auth_client: TestClient, db: sqlite3.Connection
) -> None:
    """Sessions are stateless, so this check is what actually ends access."""
    assert auth_client.get("/api/auth/me").status_code == 200
    db.execute("DELETE FROM users")
    assert auth_client.get("/api/auth/me").status_code == 401


# ─── CSRF origin guard ───────────────────────────────────────────────────


def test_foreign_origin_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_same_origin_passes(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code != 403


def test_missing_origin_passes(client: TestClient) -> None:
    """The iOS Shortcut and curl send no Origin and use bearer auth, not cookies."""
    response = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert response.status_code != 403


def test_reads_are_never_origin_checked(client: TestClient) -> None:
    assert client.get("/health", headers={"Origin": "https://evil.example"}).status_code == 200
