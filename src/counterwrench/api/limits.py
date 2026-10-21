"""A per-IP limit on the requests that spend model money (triage, re-triage, drafting), for
the public deployment. Off unless CW_RATE_LIMIT_PER_HOUR is set. In memory: one server, and a
restart resetting the counts is fine for a demo; the OpenRouter key's credit cap is the backstop.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse

WINDOW_S = 3600


def _spends_money(request: Request) -> bool:
    path = request.url.path
    return (
        request.method == "POST"
        and path.startswith("/api/intakes")
        and not path.endswith("/decline")
    )


def _client_ip(request: Request) -> str:
    # Behind Caddy, the client is the first address it forwards; directly, the socket's peer.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")


def install(app, per_hour: int | None = None) -> None:
    limit = per_hour if per_hour is not None else int(os.environ.get("CW_RATE_LIMIT_PER_HOUR", "0"))
    if limit <= 0:
        return
    hits: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if _spends_money(request):
            now, recent = time.monotonic(), hits[_client_ip(request)]
            while recent and now - recent[0] > WINDOW_S:
                recent.popleft()
            if len(recent) >= limit:
                retry = int(WINDOW_S - (now - recent[0])) + 1
                return JSONResponse(
                    {"detail": f"Rate limit: {limit} triage requests per hour. Try again later."},
                    status_code=429, headers={"Retry-After": str(retry)},
                )  # fmt: skip
            recent.append(now)
        return await call_next(request)
