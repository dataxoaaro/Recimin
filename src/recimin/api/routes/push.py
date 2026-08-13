"""Push subscription management."""

from fastapi import APIRouter, status
from pydantic import BaseModel

from recimin import push
from recimin.api.deps import CurrentUser, DbDep, SettingsDep

router = APIRouter(prefix="/push", tags=["push"])


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscribeRequest(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


@router.get("/key")
def public_key(_: CurrentUser, settings: SettingsDep) -> dict[str, str]:
    """The VAPID public key the browser needs to subscribe."""
    return {"key": settings.vapid_public_key}


@router.post("/subscribe", status_code=status.HTTP_201_CREATED)
def create_subscription(body: SubscribeRequest, user: CurrentUser, conn: DbDep) -> dict[str, int]:
    """Register this browser for notifications."""
    subscription_id = push.subscribe(
        conn,
        user_id=user.id,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
    )
    return {"id": subscription_id}


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
def remove_subscription(body: dict[str, str], _: CurrentUser, conn: DbDep) -> None:
    """Forget this browser."""
    push.unsubscribe(conn, body.get("endpoint", ""))
