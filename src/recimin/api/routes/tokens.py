"""Device token management.

A token is shown exactly once, at creation. Only its sha256 is stored, so a lost
token is replaced rather than recovered. Each phone gets its own so a lost
device is one DELETE rather than a household-wide rotation.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from recimin.api import auth
from recimin.api.deps import CurrentUser, DbDep
from recimin.api.schemas import TokenCreatedOut, TokenCreateRequest, TokenOut
from recimin.db.repositories import users as users_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.get("", response_model=list[TokenOut])
def list_tokens(user: CurrentUser, conn: DbDep) -> list[TokenOut]:
    """The caller's own tokens, live and revoked."""
    return [
        TokenOut(
            id=token.id,
            name=token.name,
            created_at=token.created_at,
            last_used_at=token.last_used_at,
            revoked_at=token.revoked_at,
        )
        for token in users_repo.tokens_for_user(conn, user.id)
    ]


@router.post("", response_model=TokenCreatedOut, status_code=status.HTTP_201_CREATED)
def create_token(body: TokenCreateRequest, user: CurrentUser, conn: DbDep) -> TokenCreatedOut:
    """Mint a device token. The plaintext is in this response and nowhere else."""
    plaintext, token_hash = auth.generate_device_token()
    token_id = users_repo.create_token(conn, user_id=user.id, name=body.name, token_hash=token_hash)
    created = next(t for t in users_repo.tokens_for_user(conn, user.id) if t.id == token_id)
    logger.info("device token created", extra={"user_id": user.id, "token_id": token_id})
    return TokenCreatedOut(
        id=created.id,
        name=created.name,
        created_at=created.created_at,
        last_used_at=None,
        revoked_at=None,
        token=plaintext,
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(token_id: int, user: CurrentUser, conn: DbDep) -> None:
    """Revoke one of the caller's own tokens.

    The ownership check is the whole point: without it this is Arboretium's
    admin-route bug in a different costume.
    """
    owned = {token.id for token in users_repo.tokens_for_user(conn, user.id)}
    if token_id not in owned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    if not users_repo.revoke_token(conn, token_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Token already revoked")
    logger.info("device token revoked", extra={"user_id": user.id, "token_id": token_id})
