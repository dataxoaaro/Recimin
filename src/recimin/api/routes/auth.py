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
_TOO_MANY = "Too many attempts. Try again later."


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
    if not ratelimit.check_and_increment(
        conn, f"register:ip:{client_ip(request)}", ratelimit.REGISTER_PER_IP
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _TOO_MANY)

    if not auth.constant_time_equals(body.site_password, settings.site_password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Incorrect site password")

    if users_repo.get_by_email(conn, body.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered")

    user_id = users_repo.create(
        conn,
        email=body.email,
        password_hash=auth.hash_password(body.password),
        display_name=body.display_name,
    )
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
    ip_ok = ratelimit.check_and_increment(
        conn, f"login:ip:{client_ip(request)}", ratelimit.LOGIN_PER_IP
    )
    email_ok = ratelimit.check_and_increment(
        conn, f"login:email:{body.email.lower()}", ratelimit.LOGIN_PER_EMAIL
    )
    if not (ip_ok and email_ok):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, _TOO_MANY)

    user = users_repo.get_by_email(conn, body.email)
    if user is None:
        auth.dummy_verify()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    if not auth.verify_password(user.password_hash, body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, _BAD_CREDENTIALS)

    if auth.needs_rehash(user.password_hash):
        users_repo.set_password_hash(conn, user.id, auth.hash_password(body.password))

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
