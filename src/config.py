"""Carga de configuracion del asistente (settings.yaml + variables de entorno)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


class Settings:
    def __init__(self) -> None:
        cfg_path = ROOT / "config" / "settings.yaml"
        data: dict = {}
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}

        self.model = os.getenv("ASSISTANT_MODEL") or data.get("model", "qwen3:8b")
        self.temperature = float(data.get("temperature", 0.25))
        self.num_ctx = int(data.get("num_ctx", 6144))
        self.num_predict = int(data.get("num_predict", 400))
        self.keep_alive = data.get("keep_alive", "30m")
        self.history_limit = int(data.get("history_limit", 16))
        self.max_tool_iters = int(data.get("max_tool_iters", 6))

        self.assistant_name = data.get("assistant_name", "Jarvis")
        self.language = data.get("language", "es")
        self.week_start = str(data.get("week_start", "domingo")).strip().lower()

        memoria = data.get("memory", {}) or {}
        self.memory = {
            "enabled": bool(memoria.get("enabled", True)),
            "summary_after": max(10, int(memoria.get("summary_after", 30))),
            "history_limit": max(4, int(memoria.get("history_limit", self.history_limit))),
            "facts_limit": max(0, int(memoria.get("facts_limit", 20))),
            "keep_messages": max(50, int(memoria.get("keep_messages", 500))),
        }

        tools = data.get("tools", {}) or {}
        self.tools = {
            "mode": str(tools.get("mode", "auto")).strip().lower(),
            "fallback_full": bool(tools.get("fallback_full", True)),
        }

        db = data.get("database", "data/assistant.db")
        self.database = db if os.path.isabs(db) else str((ROOT / db).resolve())

        self.host = data.get("host", "127.0.0.1")
        self.port = int(data.get("port", 8000))

        voice = data.get("voice", {}) or {}
        self.voice = {
            "whisper_model": voice.get("whisper_model", "small"),
            "whisper_device": voice.get("whisper_device", "cpu"),
            "whisper_compute": voice.get("whisper_compute", "auto"),
            "tts_voice": voice.get("tts_voice", "es_ES-davefx-medium"),
            "wake_model": voice.get("wake_model", "hey_jarvis"),
            "wake_threshold": float(voice.get("wake_threshold", 0.5)),
            "input_device": voice.get("input_device", None),
            "silence_ms": int(voice.get("silence_ms", 900)),
            "max_record_seconds": int(voice.get("max_record_seconds", 12)),
            "sample_rate": int(voice.get("sample_rate", 16000)),
            "voices_dir": str(
                (ROOT / voice.get("voices_dir", "data/voices")).resolve()
            ),
        }

        avatar = data.get("avatar", {}) or {}
        models = avatar.get("models") or {
            "Haru": "avatar/public/models/Haru/haru_greeter_t03.model3.json"
        }
        models = {
            name: (p if os.path.isabs(p) else str((ROOT / p).resolve()))
            for name, p in models.items()
        }
        default_model = avatar.get("model", "Haru")
        self.avatar = {
            "model": default_model,
            "models": models,
            "model_path": models.get(default_model)
            or avatar.get("model_path")
            or next(iter(models.values()), None),
            "height": int(avatar.get("height", 350)),
            "half_duplex": bool(avatar.get("half_duplex", True)),
        }

        telegram = data.get("telegram", {}) or {}
        self.telegram = {
            "poll_timeout": int(telegram.get("poll_timeout", 25)),
        }

        sched = data.get("scheduler", {}) or {}
        self.scheduler = {
            "tick_s": max(1, int(sched.get("tick_s", 1))),
        }

        pomodoro = data.get("pomodoro", {}) or {}
        self.pomodoro = {
            "trabajo_min": int(pomodoro.get("trabajo_min", 25)),
            "descanso_min": int(pomodoro.get("descanso_min", 5)),
            "descanso_largo_min": int(pomodoro.get("descanso_largo_min", 15)),
            "ciclos": int(pomodoro.get("ciclos", 4)),
            "telegram": bool(pomodoro.get("telegram", True)),
            "avatar": bool(pomodoro.get("avatar", True)),
            "presintetizar": bool(pomodoro.get("presintetizar", True)),
        }

        google = data.get("google_calendar", {}) or {}
        cred = google.get("credentials_file", "data/google_credentials.json")
        token = google.get("token_file", "data/google_token.json")
        self.google_calendar = {
            "enabled": bool(google.get("enabled", False)),
            "calendar_id": os.getenv("GOOGLE_CALENDAR_ID")
            or google.get("calendar_id", "primary"),
            "credentials_file": cred
            if os.path.isabs(cred)
            else str((ROOT / cred).resolve()),
            "token_file": token
            if os.path.isabs(token)
            else str((ROOT / token).resolve()),
            "timezone": google.get("timezone") or None,
            "conflict_policy": google.get("conflict_policy", "last_write_wins"),
        }

        self.ollama_host = os.getenv("OLLAMA_HOST") or None

        # Telegram
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or None
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID") or None

        # Email (IMAP/SMTP)
        self.email_address = os.getenv("EMAIL_ADDRESS") or None
        self.email_password = os.getenv("EMAIL_PASSWORD") or None
        self.imap_host = os.getenv("IMAP_HOST") or None
        self.imap_port = int(os.getenv("IMAP_PORT", "993"))
        self.smtp_host = os.getenv("SMTP_HOST") or None
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))


settings = Settings()
