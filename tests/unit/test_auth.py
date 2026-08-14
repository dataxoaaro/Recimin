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

    for _ in range(3):
        assert ratelimit.check(db, "b", limit, now=base).allowed is True
        ratelimit.record_failure(db, "b", limit, now=base)

    assert ratelimit.check(db, "b", limit, now=base).allowed is False
    # Still locked out for the rest of the window.
    assert ratelimit.check(db, "b", limit, now=base + 30).allowed is False
    # Fresh window.
    assert ratelimit.check(db, "b", limit, now=base + 60).allowed is True


def test_stale_windows_are_purged_by_the_next_failure(db: sqlite3.Connection) -> None:
    """Failures are the table's only writes, so cleanup rides along on them —
    otherwise stale window rows accumulate for the life of the database."""
    ratelimit.ensure_table(db)
    limit = (3, 60)
    day = 24 * 60 * 60

    ratelimit.record_failure(db, "old", limit, now=0)
    ratelimit.record_failure(db, "fresh", limit, now=float(2 * day))

    buckets = {row["bucket"] for row in db.execute("SELECT bucket FROM rate_limits")}
    assert buckets == {"fresh"}


def test_rate_limit_buckets_are_independent(db: sqlite3.Connection) -> None:
    ratelimit.ensure_table(db)
    limit = (1, 60)
    ratelimit.record_failure(db, "a", limit, now=0)
    assert ratelimit.check(db, "a", limit, now=0).allowed is False
    assert ratelimit.check(db, "b", limit, now=0).allowed is True


def test_checking_never_charges_the_bucket(db: sqlite3.Connection) -> None:
    """The old limiter incremented on every attempt, so a legitimate user was
    locked out by their own successes and a rejected caller extended its own
    lockout by retrying."""
    ratelimit.ensure_table(db)
    limit = (2, 60)
    for _ in range(50):
        assert ratelimit.check(db, "b", limit, now=0).allowed is True


def test_retry_after_counts_down_to_the_window_boundary(db: sqlite3.Connection) -> None:
    """Fixed windows reset on the boundary, not an interval after the last try,
    so a wait quoted as the full window length would be a lie."""
    ratelimit.ensure_table(db)
    limit = (1, 900)
    base = 900_000.0  # a 900s boundary

    ratelimit.record_failure(db, "b", limit, now=base)
    assert ratelimit.check(db, "b", limit, now=base).retry_after_seconds == 900
    assert ratelimit.check(db, "b", limit, now=base + 600).retry_after_seconds == 300
    assert ratelimit.check(db, "b", limit, now=base + 899).retry_after_seconds == 1


def test_an_allowed_decision_quotes_no_wait(db: sqlite3.Connection) -> None:
    ratelimit.ensure_table(db)
    assert ratelimit.check(db, "b", (5, 60), now=0).retry_after_seconds == 0


def test_clearing_a_bucket_forgets_its_failures(db: sqlite3.Connection) -> None:
    ratelimit.ensure_table(db)
    limit = (1, 60)
    ratelimit.record_failure(db, "b", limit, now=0)
    assert ratelimit.check(db, "b", limit, now=0).allowed is False

    ratelimit.clear(db, "b")
    assert ratelimit.check(db, "b", limit, now=0).allowed is True


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (1, "1 second"),
        (45, "45 seconds"),
        (90, "90 seconds"),
        (91, "2 minutes"),
        (3600, "60 minutes"),
    ],
)
def test_wait_is_described_in_units_a_person_reads(seconds: int, expected: str) -> None:
    assert ratelimit.describe_wait(seconds) == expected


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


# ─── the limiter, through the routes ─────────────────────────────────────


def test_successful_registration_is_not_charged_to_the_limiter(client: TestClient) -> None:
    """REGISTER_PER_IP is 10/hour and a household shares one public IP.

    The old limiter incremented before validating anything, so ten legitimate
    actions — successes included — locked the household out for the rest of the
    hour.
    """
    assert _register(client).status_code == 201  # type: ignore[attr-defined]

    for index in range(12):
        response = _register(client, email=f"person{index}@example.fi")
        assert response.status_code != 429, (  # type: ignore[attr-defined]
            f"locked out after {index} successful registrations"
        )


def test_a_wrong_site_password_is_charged_and_eventually_locks_out(client: TestClient) -> None:
    limit, _ = ratelimit.REGISTER_PER_IP
    for _ in range(limit):
        assert _register(client, site_password="guess").status_code == 403  # type: ignore[attr-defined]

    blocked = _register(client, site_password="guess")
    assert blocked.status_code == 429  # type: ignore[attr-defined]


def test_a_lockout_says_when_to_come_back(client: TestClient) -> None:
    """'Try again later' is indistinguishable from a wrong password at the UI —
    which is exactly how it was misread in practice."""
    limit, _ = ratelimit.REGISTER_PER_IP
    for _ in range(limit):
        _register(client, site_password="guess")

    blocked = _register(client, site_password="guess")
    detail = blocked.json()["detail"]  # type: ignore[attr-defined]
    assert "Try again in" in detail
    assert "minute" in detail or "second" in detail

    retry_after = blocked.headers["Retry-After"]  # type: ignore[attr-defined]
    assert 0 < int(retry_after) <= ratelimit.REGISTER_PER_IP[1]


def test_a_correct_password_clears_earlier_login_failures(client: TestClient) -> None:
    """Proving you know the credential is the strongest evidence you are not
    the guesser the limiter exists to slow."""
    _register(client)
    client.post("/api/auth/logout")

    limit, _ = ratelimit.LOGIN_PER_EMAIL
    for _ in range(limit - 1):
        client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": "wrong-password"})

    good = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert good.status_code == 200

    # The near-exhausted bucket is gone, so a fresh run of failures is possible.
    client.post("/api/auth/logout")
    again = client.post("/api/auth/login", json={"email": TEST_EMAIL, "password": "wrong-password"})
    assert again.status_code == 401, "earlier failures were not cleared by the success"


def test_retrying_while_locked_out_does_not_extend_the_lockout(client: TestClient) -> None:
    limit, _ = ratelimit.REGISTER_PER_IP
    for _ in range(limit):
        _register(client, site_password="guess")

    first = _register(client, site_password="guess")
    for _ in range(20):
        _register(client, site_password="guess")
    last = _register(client, site_password="guess")

    assert int(last.headers["Retry-After"]) <= int(first.headers["Retry-After"])  # type: ignore[attr-defined]
