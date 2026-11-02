"""Server-Sent Events endpoints: /api/events (staff, scoped to their patients) and /api/me/events (a patient's own record)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from . import auth, live
from .db import DB

router = APIRouter(tags=["live"])
HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def _response(request: Request, user: dict, make_fp, once: bool) -> StreamingResponse:
    key = user["username"]
    if not live.acquire(key):
        raise HTTPException(429, "Too many live connections open for this account.")

    def signed_in() -> bool:
        return auth.user_from_request(request) is not None

    async def gen():
        try:
            async for chunk in live.stream(request, make_fp, signed_in, once):
                yield chunk
        finally:
            live.release(key)

    return StreamingResponse(gen(), media_type="text/event-stream", headers=HEADERS)


@router.get("/api/events")
def staff_events(request: Request, once: bool = False, user: dict = Depends(auth.staff)):
    db: DB = request.app.state.db
    return _response(request, user, lambda: live.staff_fingerprint(db, user), once)


@router.get("/api/me/events")
def patient_events(request: Request, once: bool = False, user: dict = Depends(auth.patient_only)):
    db: DB = request.app.state.db
    return _response(request, user, lambda: live.patient_fingerprint(db, user["patient_id"]), once)
