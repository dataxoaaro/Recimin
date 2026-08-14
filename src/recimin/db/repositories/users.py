"""Users and device tokens.

Password hashing lives in the api layer; this module stores whatever hash it is
given. Token values are never stored, only their sha256.
"""

import sqlite3

from recimin.db.clock import now
from recimin.db.models import ApiToken, User


def create(conn: sqlite3.Connection, *, email: str, password_hash: str, display_name: str) -> int:
    """Insert a user. Email uniqueness is case-insensitive at the index level."""
    cursor = conn.execute(
        "INSERT INTO users (email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
        (email.strip(), password_hash, display_name.strip(), now()),
    )
    return int(cursor.lastrowid or 0)


def get(conn: sqlite3.Connection, user_id: int) -> User | None:
    """Fetch one user, or None."""
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User.from_row(row) if row else None


def get_by_email(conn: sqlite3.Connection, email: str) -> User | None:
    """Case-insensitive lookup, matching the unique index."""
    row = conn.execute(
        "SELECT * FROM users WHERE lower(email) = lower(?)", (email.strip(),)
    ).fetchone()
    return User.from_row(row) if row else None


def set_password_hash(conn: sqlite3.Connection, user_id: int, password_hash: str) -> None:
    """Replace a user's stored hash."""
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def create_token(conn: sqlite3.Connection, *, user_id: int, name: str, token_hash: str) -> int:
    """Store a device token hash. The plaintext is shown once and never kept."""
    cursor = conn.execute(
        "INSERT INTO api_tokens (user_id, name, token_hash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, name.strip(), token_hash, now()),
    )
    return int(cursor.lastrowid or 0)


def get_token(conn: sqlite3.Connection, token_id: int, *, user_id: int) -> ApiToken | None:
    """One token by id, only if it belongs to this user."""
    row = conn.execute(
        "SELECT * FROM api_tokens WHERE id = ? AND user_id = ?", (token_id, user_id)
    ).fetchone()
    return ApiToken.from_row(row) if row else None


def get_active_token(conn: sqlite3.Connection, token_hash: str) -> ApiToken | None:
    """Look up a live token by hash. Revoked tokens are invisible."""
    row = conn.execute(
        "SELECT * FROM api_tokens WHERE token_hash = ? AND revoked_at IS NULL", (token_hash,)
    ).fetchone()
    return ApiToken.from_row(row) if row else None


def touch_token(conn: sqlite3.Connection, token_id: int) -> None:
    """Record that a token was just used."""
    conn.execute("UPDATE api_tokens SET last_used_at = ? WHERE id = ?", (now(), token_id))


def revoke_token(conn: sqlite3.Connection, token_id: int) -> bool:
    """Revoke a token. Returns whether it was live before the call."""
    cursor = conn.execute(
        "UPDATE api_tokens SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (now(), token_id),
    )
    return cursor.rowcount > 0


def tokens_for_user(conn: sqlite3.Connection, user_id: int) -> list[ApiToken]:
    """Every token for a user, live and revoked, newest first."""
    rows = conn.execute(
        "SELECT * FROM api_tokens WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()
    return [ApiToken.from_row(row) for row in rows]
