"""Web Push."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from recimin import push
from recimin.config import Settings
from recimin.db.repositories import users as users_repo

SUB = {
    "endpoint": "https://web.push.apple.com/abc123",
    "p256dh": "BPublicKey",
    "auth": "authsecret",
}


@pytest.fixture
def user_id(db: sqlite3.Connection) -> int:
    return users_repo.create(db, email="a@b.fi", password_hash="h", display_name="A")


def test_subscribing_twice_updates_rather_than_duplicates(
    db: sqlite3.Connection, user_id: int
) -> None:
    """A browser re-subscribing must not create a second row for one device."""
    push.subscribe(db, user_id=user_id, **SUB)
    push.subscribe(db, user_id=user_id, **{**SUB, "p256dh": "BRotatedKey"})

    rows = db.execute("SELECT * FROM push_subscriptions").fetchall()
    assert len(rows) == 1
    assert rows[0]["p256dh"] == "BRotatedKey"


def test_unsubscribe_removes_it(db: sqlite3.Connection, user_id: int) -> None:
    push.subscribe(db, user_id=user_id, **SUB)
    push.unsubscribe(db, SUB["endpoint"])
    assert db.execute("SELECT count(*) FROM push_subscriptions").fetchone()[0] == 0


def test_notify_is_a_no_op_without_vapid_keys(
    db: sqlite3.Connection, settings: Settings, user_id: int
) -> None:
    push.subscribe(db, user_id=user_id, **SUB)
    assert push.notify(db, settings, title="t", body="b") == 0


def test_a_dead_subscription_is_dropped(
    db: sqlite3.Connection, settings: Settings, user_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 410 means the PWA was deleted. Retrying it forever fills the table."""

    class Response:
        status_code = 410

    def gone(**kwargs: object) -> None:
        raise push.WebPushException("gone", response=Response())  # type: ignore[arg-type]

    monkeypatch.setattr(push, "webpush", gone)
    configured = settings.model_copy(
        update={"vapid_private_key": "k", "vapid_subject": "mailto:a@b.fi"}
    )
    push.subscribe(db, user_id=user_id, **SUB)

    assert push.notify(db, configured, title="t", body="b") == 0
    assert db.execute("SELECT count(*) FROM push_subscriptions").fetchone()[0] == 0


def test_a_transient_failure_keeps_the_subscription(
    db: sqlite3.Connection, settings: Settings, user_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        status_code = 503

    def unavailable(**kwargs: object) -> None:
        raise push.WebPushException("busy", response=Response())  # type: ignore[arg-type]

    monkeypatch.setattr(push, "webpush", unavailable)
    configured = settings.model_copy(
        update={"vapid_private_key": "k", "vapid_subject": "mailto:a@b.fi"}
    )
    push.subscribe(db, user_id=user_id, **SUB)

    assert push.notify(db, configured, title="t", body="b") == 0
    assert db.execute("SELECT count(*) FROM push_subscriptions").fetchone()[0] == 1


def test_subscribe_route_requires_a_session(client: TestClient) -> None:
    response = client.post(
        "/api/push/subscribe",
        json={"endpoint": SUB["endpoint"], "keys": {"p256dh": "x", "auth": "y"}},
    )
    assert response.status_code == 401


def test_subscribe_route_round_trip(auth_client: TestClient, db: sqlite3.Connection) -> None:
    response = auth_client.post(
        "/api/push/subscribe",
        json={"endpoint": SUB["endpoint"], "keys": {"p256dh": "x", "auth": "y"}},
    )
    assert response.status_code == 201
    assert db.execute("SELECT count(*) FROM push_subscriptions").fetchone()[0] == 1
