"""Runtime configuration (environment variables) and static lookup tables."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Settings:
    db_path: str
    database_url: str
    cookie_secure: bool
    admin_user: str
    admin_password: str
    session_hours: int
    wa_token: str
    wa_phone_id: str
    wa_verify_token: str
    wa_app_secret: str
    wa_api_version: str
    anthropic_key: str
    anthropic_model: str
    stt_endpoint: str
    stt_key: str
    stt_model: str
    scheduler_enabled: bool
    demo_seed: bool
    clinic_name: str

    @property
    def db_target(self) -> str:
        return self.database_url or self.db_path

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.wa_token and self.wa_phone_id)


def settings() -> Settings:
    e = os.environ.get
    return Settings(
        db_path=e("RAFIQ_DB", "rafiq.db"),
        database_url=e("DATABASE_URL", ""),
        cookie_secure=e("RAFIQ_COOKIE_SECURE", "0") == "1",
        admin_user=e("RAFIQ_ADMIN_USER", ""),
        admin_password=e("RAFIQ_ADMIN_PASSWORD", ""),
        session_hours=int(e("RAFIQ_SESSION_HOURS", "12")),
        wa_token=e("WHATSAPP_TOKEN", ""),
        wa_phone_id=e("WHATSAPP_PHONE_ID", ""),
        wa_verify_token=e("WHATSAPP_VERIFY_TOKEN", ""),
        wa_app_secret=e("WHATSAPP_APP_SECRET", ""),
        wa_api_version=e("WHATSAPP_API_VERSION", "v21.0"),
        anthropic_key=e("ANTHROPIC_API_KEY", ""),
        anthropic_model=e("RAFIQ_VISION_MODEL", "claude-sonnet-5-5"),
        stt_endpoint=e("RAFIQ_STT_ENDPOINT", ""),
        stt_key=e("RAFIQ_STT_KEY", ""),
        stt_model=e("RAFIQ_STT_MODEL", "whisper-1"),
        scheduler_enabled=e("RAFIQ_SCHEDULER", "1") == "1",
        demo_seed=e("RAFIQ_DEMO_SEED", "1") == "1",
        clinic_name=e("RAFIQ_CLINIC_NAME", "المركز الصحي"),
    )


def load_thresholds() -> dict:
    with open(BASE_DIR / "thresholds.json", encoding="utf-8") as f:
        return json.load(f)


# Emergency numbers by ISO country code. VERIFY every number with the local
# health authority before deployment; they are configuration, not clinical truth.
EMERGENCY_NUMBERS = {
    "JO": "911", "SA": "997", "AE": "998", "EG": "123", "KW": "112",
    "QA": "999", "LB": "140", "MA": "150", "TN": "190", "PS": "101",
    "OM": "9999", "BH": "999",
}

COUNTRY_TZ = {
    "JO": "Asia/Amman", "SA": "Asia/Riyadh", "AE": "Asia/Dubai", "EG": "Africa/Cairo",
    "KW": "Asia/Kuwait", "QA": "Asia/Qatar", "LB": "Asia/Beirut", "MA": "Africa/Casablanca",
    "TN": "Africa/Tunis", "PS": "Asia/Hebron", "OM": "Asia/Muscat", "BH": "Asia/Bahrain",
}


def emergency_number(country: str) -> str:
    return EMERGENCY_NUMBERS.get((country or "").upper(), "112")
