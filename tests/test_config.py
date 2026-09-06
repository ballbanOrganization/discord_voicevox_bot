from pathlib import Path

import pytest

from app.config import DEFAULT_VOICEVOX_URL, Settings


def test_settings_from_env_reads_supported_values(monkeypatch, tmp_path):
    data_path = tmp_path / "users.json"
    audio_path = tmp_path / "audio"
    monkeypatch.setenv("discord_token", "token")
    monkeypatch.setenv("VOICEVOX_URL", "http://voicevox:50021")
    monkeypatch.setenv("DATA_PATH", str(data_path))
    monkeypatch.setenv("AUDIO_PATH", str(audio_path))
    monkeypatch.setenv("VOICEVOX_TIMEOUT", "12.5")
    monkeypatch.setenv("QUEUE_IDLE_TIMEOUT", "45")
    monkeypatch.setenv("CLEANUP_INTERVAL", "7.5")

    settings = Settings.from_env()

    assert settings.discord_token == "token"
    assert settings.voicevox_url == "http://voicevox:50021"
    assert settings.data_path == data_path
    assert settings.audio_path == audio_path
    assert settings.voicevox_timeout == 12.5
    assert settings.queue_idle_timeout == 45.0
    assert settings.cleanup_interval == 7.5


def test_settings_from_env_uses_defaults_without_optional_values(monkeypatch):
    monkeypatch.setenv("discord_token", "token")
    for name in (
        "VOICEVOX_URL",
        "DATA_PATH",
        "AUDIO_PATH",
        "VOICEVOX_TIMEOUT",
        "QUEUE_IDLE_TIMEOUT",
        "CLEANUP_INTERVAL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env()

    assert settings.voicevox_url == DEFAULT_VOICEVOX_URL
    assert settings.data_path == Path("data/user_data.json")
    assert settings.audio_path == Path("audio")
    assert settings.voicevox_timeout == 10.0
    assert settings.queue_idle_timeout == 300.0
    assert settings.cleanup_interval == 60.0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VOICEVOX_TIMEOUT", "not-a-number"),
        ("QUEUE_IDLE_TIMEOUT", "0"),
        ("CLEANUP_INTERVAL", "inf"),
        ("VOICEVOX_TIMEOUT", "nan"),
        ("QUEUE_IDLE_TIMEOUT", "-1"),
    ],
)
def test_settings_from_env_rejects_invalid_positive_float(name, value, monkeypatch):
    monkeypatch.setenv("discord_token", "token")
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match=name):
        Settings.from_env()


def test_settings_from_env_strips_token_and_paths(monkeypatch, tmp_path):
    data_path = tmp_path / "users.json"
    audio_path = tmp_path / "audio"
    monkeypatch.setenv("discord_token", "  token  ")
    monkeypatch.setenv("DATA_PATH", f"  {data_path}  ")
    monkeypatch.setenv("AUDIO_PATH", f"  {audio_path}  ")

    settings = Settings.from_env()

    assert settings.discord_token == "token"
    assert settings.data_path == data_path
    assert settings.audio_path == audio_path


def test_settings_from_env_turns_whitespace_token_into_empty_optional_value(
    monkeypatch,
):
    monkeypatch.setenv("discord_token", "   ")

    settings = Settings.from_env(require_token=False)

    assert settings.discord_token == ""


def test_settings_from_env_requires_token(monkeypatch):
    monkeypatch.delenv("discord_token", raising=False)

    with pytest.raises(RuntimeError, match="discord_token"):
        Settings.from_env()
