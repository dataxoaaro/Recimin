"""Request dependencies: database handles and the two authentication modes.

Session cookie is the norm. Bearer tokens are accepted on exactly one route,
POST /api/import, because the iOS Shortcut cannot perform a cookie login and an
installed PWA's cookie jar is separate from Safari's.
"""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from recimin.api import auth
from recimin.config import Settings
from recimin.db.models import User
from recimin.db.repositories import users as users_repo

UNAUTHORISED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_settings_dep(request: Request) -> Settings:
    """The settings attached to the app at startup."""
    return request.app.state.settings  # type: ignore[no-any-return]


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """A per-request connection from the app's factory."""
    conn = request.app.state.db_factory()
    try:
        yield conn
    finally:
        conn.close()


DbDep = Annotated[sqlite3.Connection, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def client_ip(request: Request) -> str:
    """Best-known client address.

    Behind Cloudflare, CF-Connecting-IP is the only trustworthy source; the
    socket address is the tunnel. Falling back to the socket keeps local
    development working.

    The header is spoofable by anything that can reach the origin port
    directly, which is why compose binds it to 127.0.0.1 — and why the
    per-email login limit, not this per-IP one, is the defence that matters.
    """
    forwarded = request.headers.get("CF-Connecting-IP")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "unknown"


def require_session(request: Request, conn: DbDep, settings: SettingsDep) -> User:
    """Resolve the session cookie to a user, or 401."""
    token = request.cookies.get(auth.COOKIE_NAME)
    if not token:
        raise UNAUTHORISED
    user_id = auth.read_session(token, settings.jwt_secret)
    if user_id is None:
        raise UNAUTHORISED
    user = users_repo.get(conn, user_id)
    if user is None:
        # A valid signature for a deleted account. Stateless sessions cannot be
        # revoked, so this check is what actually ends access.
        raise UNAUTHORISED
    return user


def require_session_or_token(request: Request, conn: DbDep, settings: SettingsDep) -> User:
    """Accept either a session cookie or a device bearer token.

    Used only by POST /api/import.
    """
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        plaintext = header.removeprefix("Bearer ").strip()
        if not plaintext:
            raise UNAUTHORISED
        record = users_repo.get_active_token(conn, auth.hash_device_token(plaintext))
        if record is None:
            raise UNAUTHORISED
        user = users_repo.get(conn, record.user_id)
        if user is None:
            raise UNAUTHORISED
        users_repo.touch_token(conn, record.id)
        return user

    return require_session(request, conn, settings)


CurrentUser = Annotated[User, Depends(require_session)]
ImportCaller = Annotated[User, Depends(require_session_or_token)]
