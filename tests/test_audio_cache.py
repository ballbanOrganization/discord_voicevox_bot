import hashlib
import os
import time
from datetime import timedelta

from app.audio_cache import AudioCache


def test_cache_key_and_path_match_legacy_layout(tmp_path):
    cache = AudioCache(tmp_path / "audio")
    text = "読み上げテスト"
    expected_key = hashlib.md5(text.encode("utf-8")).hexdigest()

    assert cache.cache_key(text) == expected_key
    assert cache.path_for(text, "ノーマルずんだもん") == (
        tmp_path / "audio" / "ノーマルずんだもん" / f"{expected_key}.wav"
    )


def test_cache_write_creates_parent_and_file(tmp_path):
    cache = AudioCache(tmp_path / "audio")
    path = cache.path_for("hello", "style speaker")

    cache.write(path, b"RIFF")

    assert path.read_bytes() == b"RIFF"


def test_cache_entry_expires_after_thirty_days(tmp_path):
    cache = AudioCache(tmp_path / "audio")
    path = cache.path_for("hello", "style speaker")
    cache.write(path, b"RIFF")

    assert cache.is_fresh(path)

    expired_at = time.time() - timedelta(days=31).total_seconds()
    os.utime(path, (expired_at, expired_at))

    assert not cache.is_fresh(path)
