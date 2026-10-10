"""Outbound channels. The engine only knows the tiny Channel interface, so SMS,
Telegram or a hospital gateway can be added without touching conversation logic."""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Protocol

import httpx

from .config import settings

log = logging.getLogger("rafiq.channels")


class Channel(Protocol):
    name: str

    def send(self, phone: str, text: str, template: str | None = None, params: list[str] | None = None) -> None: ...


class NullChannel:
    """Simulator / tests: nothing leaves the machine (messages are still logged in the DB)."""
    name = "simulator"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, phone, text, template=None, params=None) -> None:
        self.sent.append((phone, text))


class WhatsAppCloud:
    """Meta WhatsApp Business Cloud API.

    Business-initiated messages outside the 24h customer-service window MUST be
    pre-approved templates; the engine passes `template` for those cases.
    """
    name = "whatsapp"

    def __init__(self) -> None:
        s = settings()
        self.base = f"https://graph.facebook.com/{s.wa_api_version}"
        self.phone_id = s.wa_phone_id
        self.headers = {"Authorization": f"Bearer {s.wa_token}"}

    def send(self, phone, text, template=None, params=None) -> None:
        to = phone.lstrip("+")
        if template:
            payload = {
                "messaging_product": "whatsapp", "to": to, "type": "template",
                "template": {
                    "name": template, "language": {"code": "ar"},
                    "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in (params or [])]}],
                },
            }
        else:
            payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text, "preview_url": False}}
        try:
            r = httpx.post(f"{self.base}/{self.phone_id}/messages", json=payload, headers=self.headers, timeout=15)
            if r.status_code >= 400:
                log.error("WhatsApp send failed %s: %s", r.status_code, r.text[:300])
        except httpx.HTTPError as exc:  # never crash the engine on a network error
            log.error("WhatsApp send error: %s", exc)

    def download_media(self, media_id: str) -> tuple[bytes, str] | None:
        try:
            meta = httpx.get(f"{self.base}/{media_id}", headers=self.headers, timeout=15).json()
            r = httpx.get(meta["url"], headers=self.headers, timeout=30)
            r.raise_for_status()
            return r.content, meta.get("mime_type", "application/octet-stream")
        except Exception as exc:  # noqa: BLE001
            log.error("media download failed: %s", exc)
            return None


def verify_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """Validate Meta's X-Hub-Signature-256 header."""
    if not app_secret:
        return True  # dev mode; README tells operators to set WHATSAPP_APP_SECRET
    if not header or not header.startswith("sha256="):
        return False
    digest = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header.split("=", 1)[1])


def build_channel():
    return WhatsAppCloud() if settings().whatsapp_enabled else NullChannel()
