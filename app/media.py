"""Optional media understanding. Both hooks degrade gracefully (return None).

NOTE: these two functions call external services and are NOT covered by the
automated tests (they need your credentials). Test with real devices/voices
before relying on them. Every image-derived number is echoed back to the
patient for confirmation before it is stored.
"""
from __future__ import annotations

import base64
import json
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("rafiq.media")


def transcribe(audio: bytes, mime: str = "audio/ogg") -> str | None:
    """Voice note → text via any OpenAI-compatible /audio/transcriptions endpoint.

    Configure RAFIQ_STT_ENDPOINT (e.g. https://api.openai.com/v1/audio/transcriptions),
    RAFIQ_STT_KEY, RAFIQ_STT_MODEL. Dialect accuracy varies a lot between vendors:
    benchmark on your own dialect recordings. Returns None if not configured.
    """
    s = settings()
    if not s.stt_endpoint:
        return None
    try:
        r = httpx.post(
            s.stt_endpoint,
            headers={"Authorization": f"Bearer {s.stt_key}"} if s.stt_key else {},
            data={"model": s.stt_model, "language": "ar"},
            files={"file": ("voice.ogg", audio, mime)},
            timeout=60,
        )
        r.raise_for_status()
        return (r.json().get("text") or "").strip() or None
    except Exception as exc:  # noqa: BLE001
        log.error("STT failed: %s", exc)
        return None


_PROMPT = (
    "This is a photo of a medical device display (blood glucose meter or blood pressure monitor). "
    "Read ONLY digits that are clearly visible. Do not guess. Reply with JSON only, no prose: "
    '{"type":"glucose"|"bp"|"unknown","glucose":number|null,"unit":"mg/dL"|"mmol/L"|null,'
    '"systolic":number|null,"diastolic":number|null,"confident":true|false}'
)


def read_meter(image: bytes, mime: str = "image/jpeg") -> dict | None:
    """Glucometer / BP-cuff photo → {'type','glucose','unit','systolic','diastolic'} via Claude vision."""
    s = settings()
    if not s.anthropic_key:
        return None
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": s.anthropic_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": s.anthropic_model,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(image).decode()}},
                    {"type": "text", "text": _PROMPT},
                ]}],
            },
            timeout=45,
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json()["content"] if b.get("type") == "text")
        data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
        if not data.get("confident") or data.get("type") == "unknown":
            return None
        return data
    except Exception as exc:  # noqa: BLE001
        log.error("meter read failed: %s", exc)
        return None
