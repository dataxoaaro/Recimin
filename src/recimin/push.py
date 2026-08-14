"""Web Push notifications.

Supported in installed PWAs on iOS since 16.4. Requires a Home Screen install,
a manifest with display: standalone, and permission granted from a user gesture.

This is what makes the 202-immediately pattern work: the Shortcut fires, gets
an acknowledgement in ~200ms while the user is still inside Instagram, and the
outcome arrives when it is actually known.
"""

import json
import logging
import sqlite3

from pywebpush import WebPushException, webpush

from recimin.config import Settings

logger = logging.getLogger(__name__)

TTL_SECONDS = 86_400

# Endpoints that are gone for good. A 404 or 410 means the subscription is
# dead — the user deleted the PWA or revoked permission — and retrying it
# forever is how a push table fills with corpses.
DEAD_STATUSES = frozenset({404, 410})


def subscribe(
    conn: sqlite3.Connection, *, user_id: int, endpoint: str, p256dh: str, auth: str
) -> int:
    """Store or refresh a browser's push subscription."""
    from recimin.db.clock import now

    conn.execute(
        "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at)"
        " VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth",
        (user_id, endpoint, p256dh, auth, now()),
    )
    row = conn.execute(
        "SELECT id FROM push_subscriptions WHERE endpoint = ?", (endpoint,)
    ).fetchone()
    return int(row["id"])


def unsubscribe(conn: sqlite3.Connection, endpoint: str) -> None:
    """Drop a subscription."""
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))


def notify(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    title: str,
    body: str,
    url: str = "/",
) -> int:
    """Send a notification to every live subscription. Returns how many landed.

    Every subscription, deliberately: an import's outcome is household news,
    not a per-user message.

    Never raises: a failed notification must not fail the import that triggered
    it. The recipe is already saved either way.
    """
    if not settings.vapid_private_key:
        logger.debug("push not configured")
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    delivered = 0

    for row in conn.execute("SELECT * FROM push_subscriptions").fetchall():
        try:
            webpush(
                subscription_info={
                    "endpoint": row["endpoint"],
                    "keys": {"p256dh": row["p256dh"], "auth": row["auth"]},
                },
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=TTL_SECONDS,
            )
            delivered += 1
        except WebPushException as error:
            status = getattr(error.response, "status_code", None)
            if status in DEAD_STATUSES:
                unsubscribe(conn, row["endpoint"])
                logger.info("dropped dead push subscription", extra={"status": status})
            else:
                logger.warning("push failed", extra={"status": status, "error": str(error)[:200]})

    return delivered
