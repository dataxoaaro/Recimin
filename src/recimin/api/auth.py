"""Password hashing, session tokens and device tokens.

Ported from Arboretium's hand-rolled module with two changes: Argon2id instead
of PBKDF2, since we are not on the Cloudflare Workers 100k-iteration ceiling,
and a device-token table the original lacks.

Deliberately NOT ported: Arboretium's admin routes, which are gated only on
"is there a session" and let any registered user mint a password-reset token for
any account. Recimin has no admin surface at all.
"""

import contextlib
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

COOKIE_NAME = "recimin_session"
SESSION_TTL = timedelta(days=30)
JWT_ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 10
TOKEN_BYTES = 32

_hasher = PasswordHasher()

# A precomputed hash of a throwaway password. Verifying against it on an unknown
# email keeps login timing flat, so the endpoint does not leak which addresses
# are registered.
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-login")


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


# InvalidHashError subclasses ValueError, not VerificationError, so it must be
# listed explicitly. Without it a corrupt or truncated stored hash raises out of
# the login endpoint as a 500 instead of failing the login.
_VERIFY_FAILURES = (VerifyMismatchError, VerificationError, InvalidHashError)


def verify_password(password_hash: str, password: str) -> bool:
    """Check a password against its hash. Any failure is False, never an exception."""
    try:
        return _hasher.verify(password_hash, password)
    except _VERIFY_FAILURES:
        return False


def dummy_verify() -> None:
    """Burn the same time as a real verification, for unknown-email logins."""
    with contextlib.suppress(*_VERIFY_FAILURES):
        _hasher.verify(_DUMMY_HASH, "wrong")


def needs_rehash(password_hash: str) -> bool:
    """Whether a stored hash was made with outdated parameters."""
    return _hasher.check_needs_rehash(password_hash)


def constant_time_equals(supplied: str, expected: str) -> bool:
    """Compare two secrets without leaking length or content through timing.

    The explicit length check first mirrors Arboretium, whose deploy notes warn
    that a trailing newline in the stored secret silently breaks login.
    """
    if len(supplied) != len(expected):
        return False
    return hmac.compare_digest(supplied, expected)


def issue_session(user_id: int, secret: str, *, now: datetime | None = None) -> str:
    """Mint a session JWT for a user."""
    issued = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(issued.timestamp()),
        "exp": int((issued + SESSION_TTL).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def read_session(token: str, secret: str) -> int | None:
    """Return the user id from a valid session token, or None.

    Any failure — expiry, bad signature, malformed payload, wrong algorithm —
    is a None rather than an exception. The caller's job is to send a 401, not
    to distinguish why.
    """
    try:
        payload: dict[str, Any] = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdigit():
        return None
    return int(subject)


def generate_device_token() -> tuple[str, str]:
    """Create a device token. Returns (plaintext, sha256).

    The plaintext is shown to the user exactly once and never stored.
    """
    plaintext = secrets.token_urlsafe(TOKEN_BYTES)
    return plaintext, hash_device_token(plaintext)


def hash_device_token(plaintext: str) -> str:
    """Hash a device token for storage and lookup.

    Plain sha256, not Argon2: these are 256 bits of entropy from a CSPRNG, not
    user-chosen passwords, so there is nothing for a slow hash to defend, and
    every import request would otherwise pay Argon2's cost.
    """
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
