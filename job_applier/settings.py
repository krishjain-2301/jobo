"""Profile (data/profile.json) and secrets (.env or session only)."""

import json
import os
from pathlib import Path

from dotenv import load_dotenv, set_key

from .storage import DATA_DIR

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
PROFILE_PATH = DATA_DIR / "profile.json"

SECRET_KEYS = [
    "GMAIL_ADDRESS",
    "GMAIL_APP_PASSWORD",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_COMPAT_API_KEY",
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "JOOBLE_API_KEY",
    "JSEARCH_API_KEY",
]

DEFAULT_PROFILE = {
    "name": "",
    "email": "",
    "phone": "",
    "linkedin": "",
    "target_role": "",
    "pitch": "",
    "resume_path": "",
    "provider": "Claude (Anthropic)",
    "model": "claude-opus-5-5",
    "base_url": "",
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "daily_limit": 40,
    "delay_min": 45,
    "delay_max": 120,
    "subject_template": "",
    "body_template": "",
    # Discover filters: a job counts as relevant when one of these appears in its title or description
    "keywords": "",
    "min_match": 40,
    "fresher_only": True,
}

load_dotenv(ENV_PATH)


def secret(key: str) -> str:
    return os.environ.get(key, "")


def set_secret(key: str, value: str, remember: bool) -> None:
    os.environ[key] = value
    if remember:
        ENV_PATH.touch(exist_ok=True)
        set_key(str(ENV_PATH), key, value)


def load_profile() -> dict:
    profile = dict(DEFAULT_PROFILE)
    if PROFILE_PATH.exists():
        profile.update(json.loads(PROFILE_PATH.read_text(encoding="utf-8")))
    return profile


def save_profile(profile: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
