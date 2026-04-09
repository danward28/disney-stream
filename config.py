"""Centralized configuration for Disney Piano Stream."""

import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
CONFIG_JSON = PROJECT_DIR / "config.json"
ENV_FILE = PROJECT_DIR / ".env"


def _load_env():
    """Read .env file into os.environ (simple key=value parser)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def _load_json_config():
    """Load mutable runtime config from config.json."""
    if CONFIG_JSON.exists():
        try:
            return json.loads(CONFIG_JSON.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_json_config(data):
    """Persist mutable runtime config to config.json."""
    CONFIG_JSON.write_text(json.dumps(data, indent=2) + "\n")


# Load .env on import
_load_env()
_json_config = _load_json_config()


def get(key, default=None):
    """Get config value. Priority: config.json > env var > default."""
    if key in _json_config:
        return _json_config[key]
    return os.environ.get(key, default)


def set_runtime(key, value):
    """Set a runtime config value (persisted to config.json)."""
    _json_config[key] = value
    _save_json_config(_json_config)


def get_all():
    """Return all config as a dict for the settings page."""
    return {
        "ANTHROPIC_API_KEY": get("ANTHROPIC_API_KEY", ""),
        "YOUTUBE_STREAM_KEY": get("YOUTUBE_STREAM_KEY", ""),
        "SUNO_API_KEY": get("SUNO_API_KEY", ""),
        "FLASK_PORT": int(get("FLASK_PORT", 8080)),
    }
