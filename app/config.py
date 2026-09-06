import math
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICEVOX_URL = "http://127.0.0.1:50021/"


def _read_env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a number.") from error
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be finite and greater than zero.")
    return value


def _read_env_path(name: str, default: Path) -> Path:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    if not raw_value.strip():
        raise RuntimeError(f"{name} must not be empty.")
    return Path(raw_value.strip())


@dataclass(frozen=True)
class Settings:
    discord_token: str = ""
    data_path: Path = Path("data/user_data.json")
    audio_path: Path = Path("audio")
    voicevox_url: str = DEFAULT_VOICEVOX_URL
    voicevox_timeout: float = 10.0
    queue_idle_timeout: float = 300.0
    cleanup_interval: float = 60.0

    @classmethod
    def from_env(cls, *, require_token: bool = True) -> "Settings":
        token = os.environ.get("discord_token", "").strip()
        if require_token and not token:
            raise RuntimeError("The discord_token environment variable is required.")

        defaults = cls()
        voicevox_url = os.environ.get("VOICEVOX_URL", DEFAULT_VOICEVOX_URL).strip()
        if not voicevox_url:
            raise RuntimeError("VOICEVOX_URL must not be empty.")

        return cls(
            discord_token=token,
            data_path=_read_env_path("DATA_PATH", defaults.data_path),
            audio_path=_read_env_path("AUDIO_PATH", defaults.audio_path),
            voicevox_url=voicevox_url,
            voicevox_timeout=_read_env_float(
                "VOICEVOX_TIMEOUT",
                defaults.voicevox_timeout,
            ),
            queue_idle_timeout=_read_env_float(
                "QUEUE_IDLE_TIMEOUT",
                defaults.queue_idle_timeout,
            ),
            cleanup_interval=_read_env_float(
                "CLEANUP_INTERVAL",
                defaults.cleanup_interval,
            ),
        )
