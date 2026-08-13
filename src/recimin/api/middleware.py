"""Origin allowlist for mutating requests.

`SameSite=Strict` on the session cookie is the primary CSRF defence; this is the
second layer, matching Arboretium's approach.

A missing Origin header is allowed on purpose. Non-browser callers — the iOS
Shortcut, curl, the deploy smoke test — send no Origin, and they authenticate
with a bearer token rather than an ambient cookie, so they are not the shape of
request CSRF describes.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def build_origin_guard(
    allowed_origin: str,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Create the middleware for a given allowed origin."""

    allowed = {allowed_origin.rstrip("/")}

    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in MUTATING_METHODS:
            origin = request.headers.get("Origin")
            if origin is not None:
                normalised = origin.rstrip("/")
                same_origin = normalised == str(request.base_url).rstrip("/")
                if normalised not in allowed and not same_origin:
                    return JSONResponse(
                        {"detail": "Origin not allowed"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )
        return await call_next(request)

    return guard
