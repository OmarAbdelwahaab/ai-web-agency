from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _time(name: str, default: str) -> time:
    h, m = os.environ.get(name, default).split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class Settings:
    agency_name: str = field(default_factory=lambda: os.environ.get("AGENCY_NAME", "Your Agency"))
    callback_number: str = field(default_factory=lambda: os.environ.get("AGENCY_CALLBACK_NUMBER", ""))
    persona_name: str = field(default_factory=lambda: os.environ.get("AGENT_PERSONA_NAME", "Ava"))
    db_path: Path = field(default_factory=lambda: Path(os.environ.get("DB_PATH", "data/agency.db")))

    live_dialing_enabled: bool = field(default_factory=lambda: _bool("LIVE_DIALING_ENABLED"))
    legal_review_done: bool = field(default_factory=lambda: _bool("LEGAL_REVIEW_DONE"))
    record_calls: bool = field(default_factory=lambda: _bool("RECORD_CALLS"))
    max_attempts: int = field(default_factory=lambda: int(os.environ.get("MAX_ATTEMPTS_PER_LEAD", "2")))
    window_start: time = field(default_factory=lambda: _time("CALL_WINDOW_START", "08:00"))
    window_end: time = field(default_factory=lambda: _time("CALL_WINDOW_END", "21:00"))

    places_api_key: str = field(default_factory=lambda: os.environ.get("GOOGLE_PLACES_API_KEY", ""))
    overpass_url: str = field(default_factory=lambda: os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter"))
    search_api_key: str = field(default_factory=lambda: os.environ.get("SEARCH_API_KEY", ""))
    search_engine_id: str = field(default_factory=lambda: os.environ.get("SEARCH_ENGINE_ID", ""))

    llm_base_url: str = field(default_factory=lambda: os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"))
    llm_api_key: str = field(default_factory=lambda: os.environ.get("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile"))

    livekit_agent_name: str = field(default_factory=lambda: os.environ.get("LIVEKIT_AGENT_NAME", "agency-caller"))
    sip_trunk_id: str = field(default_factory=lambda: os.environ.get("SIP_OUTBOUND_TRUNK_ID", ""))
    stt_provider: str = field(default_factory=lambda: os.environ.get("STT_PROVIDER", "deepgram"))
    tts_provider: str = field(default_factory=lambda: os.environ.get("TTS_PROVIDER", "cartesia"))
    voice_llm_provider: str = field(default_factory=lambda: os.environ.get("VOICE_LLM_PROVIDER", "groq"))

    telegram_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))

    payment_provider: str = field(default_factory=lambda: os.environ.get("PAYMENT_PROVIDER", "manual"))
    deploy_enabled: bool = field(default_factory=lambda: _bool("DEPLOY_ENABLED"))
    qa_enabled: bool = field(default_factory=lambda: _bool("QA_ENABLED"))

    pricing_path: Path = field(default_factory=lambda: ROOT / "pricing.yaml")
    output_dir: Path = field(default_factory=lambda: ROOT / "output")


def get_settings() -> Settings:
    return Settings()
