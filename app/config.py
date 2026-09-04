import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VOICEVOX_URL = "http://127.0.0.1:50021/"


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
        token = os.environ.get("discord_token", "")
        if require_token and not token:
            raise RuntimeError("The discord_token environment variable is required.")

        return cls(
            discord_token=token,
            voicevox_url=os.environ.get("VOICEVOX_URL", DEFAULT_VOICEVOX_URL),
        )
