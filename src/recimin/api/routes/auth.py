"""Registration, login and password management."""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status

from recimin.api import auth, ratelimit
from recimin.api.deps import CurrentUser, DbDep, SettingsDep, client_ip
from recimin.api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    UserOut,
)
from recimin.db.repositories import users as users_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Deliberately identical for unknown email and wrong password, so the endpoint
# does not confirm which addresses are registered.
_BAD_CREDENTIALS = "Incorrect email or password"


def _reject_if_limited(*decisions: ratelimit.Decision) -> None:
    """Raise 429 if any bucket is exhausted, naming when the caller may retry.

    Retry-After as well as prose: the header is what a client can act on, and
    the prose is what stops the user reading a lockout as a wrong password.
    """
    blocked = [d for d in decisions if not d.allowed]
    if not blocked:
        return

    wait = max(d.retry_after_seconds for d in blocked)
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many attempts. Try again in {ratelimit.describe_wait(wait)}.",
        headers={"Retry-After": str(wait)},
    )


def _set_session_cookie(response: Response, user_id: int, settings: SettingsDep) -> None:
    token = auth.issue_session(user_id, settings.jwt_secret)
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.allowed_origin.startswith("https://"),
        samesite="strict",
        path="/",
        max_age=int(auth.SESSION_TTL.total_seconds()),
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    conn: DbDep,
    settings: SettingsDep,
) -> UserOut:
    """Create an account. Gated by the shared site password."""
    ratelimit.ensure_table(conn)
    bucket = f"register:ip:{client_ip(request)}"
    _reject_if_limited(ratelimit.check(conn, bucket, ratelimit.REGISTER_PER_IP))

    if not auth.constant_time_equals(body.site_password, settings.site_password):
        ratelimit.record_failure(conn, bucket, ratelimit.REGISTER_PER_IP)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect site password")

    # Not charged to the limiter: reaching here means the site password was
    # right, so this is a household member retyping an address, not a guess.
    if users_repo.get_by_email(conn, body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered")

    user_id = users_repo.create(
        conn,
        email=body.email,
        password_hash=auth.hash_password(body.password),
        display_name=body.display_name,
    )
    ratelimit.clear(conn, bucket)
    _set_session_cookie(response, user_id, settings)
    logger.info("user registered", extra={"user_id": user_id})
    return UserOut(id=user_id, email=body.email, display_name=body.display_name)


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    conn: DbDep,
    settings: SettingsDep,
) -> UserOut:
    """Exchange credentials for a session cookie."""
    ratelimit.ensure_table(conn)
    ip_bucket = f"login:ip:{client_ip(request)}"
    email_bucket = f"login:email:{body.email.lower()}"
    _reject_if_limited(
        ratelimit.check(conn, ip_bucket, ratelimit.LOGIN_PER_IP),
        ratelimit.check(conn, email_bucket, ratelimit.LOGIN_PER_EMAIL),
    )

    def charge() -> None:
        ratelimit.record_failure(conn, ip_bucket, ratelimit.LOGIN_PER_IP)
        ratelimit.record_failure(conn, email_bucket, ratelimit.LOGIN_PER_EMAIL)

    user = users_repo.get_by_email(conn, body.email)
    if user is None:
        auth.dummy_verify()
        charge()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    if not auth.verify_password(user.password_hash, body.password):
        charge()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    if auth.needs_rehash(user.password_hash):
        users_repo.set_password_hash(conn, user.id, auth.hash_password(body.password))

    ratelimit.clear(conn, ip_bucket)
    ratelimit.clear(conn, email_bucket)
    _set_session_cookie(response, user.id, settings)
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Clear the session cookie."""
    response.delete_cookie(auth.COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    """The signed-in user."""
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, user: CurrentUser, conn: DbDep) -> None:
    """Replace the caller's own password. Never anyone else's."""
    if not auth.verify_password(user.password_hash, body.current_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    users_repo.set_password_hash(conn, user.id, auth.hash_password(body.new_password))
    logger.info("password changed", extra={"user_id": user.id})
