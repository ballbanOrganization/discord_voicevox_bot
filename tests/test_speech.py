import asyncio
import os
import time
from datetime import timedelta
from types import SimpleNamespace

from app.audio_cache import AudioCache
from app.speech import SpeechService
from app.voicevox import ALL_RANDOM_SPEAKER_ID


def test_speech_service_deduplicates_generation_and_releases_locks(tmp_path):
    async def scenario():
        calls = []

        class VoiceVox:
            def get_speaker_name(self, speaker_id):
                return "speaker"

            async def text_to_sound(self, text, speaker, speed_scale=1.0):
                await asyncio.sleep(0.001)
                calls.append((text, speaker))
                return b"RIFF"

        class Users:
            def get_user(self, user_id):
                return SimpleNamespace(sound=3)

        service = SpeechService(
            VoiceVox(),
            Users(),
            AudioCache(tmp_path / "audio"),
        )

        results = await asyncio.gather(
            service.synthesize("same", 1),
            service.synthesize("same", 2),
        )

        assert results[0].path == results[1].path
        assert calls == [("same", 3)]
        assert service._locks == {}

    asyncio.run(scenario())


def test_speech_service_uses_explicit_speaker_override(tmp_path):
    async def scenario():
        synthesis_calls = []

        class VoiceVox:
            def get_speaker_name(self, speaker_id):
                return f"speaker {speaker_id}"

            async def text_to_sound(self, text, speaker, speed_scale=1.0):
                synthesis_calls.append((text, speaker, speed_scale))
                return b"RIFF"

        class Users:
            def get_user(self, user_id):
                return SimpleNamespace(sound=107)

        service = SpeechService(
            VoiceVox(),
            Users(),
            AudioCache(tmp_path / "audio"),
        )

        result = await service.synthesize(
            "joined",
            1,
            speaker_id=3,
            speed_scale=1.2,
        )

        assert result.speaker_name == "speaker 3"
        assert synthesis_calls == [("joined", 3, 1.2)]

    asyncio.run(scenario())


def test_all_random_selects_a_speaker_for_each_request(tmp_path):
    async def scenario():
        selected_speakers = iter((3, 107))
        random_calls = []
        synthesis_calls = []

        class VoiceVox:
            def get_random_speaker_id(self):
                speaker_id = next(selected_speakers)
                random_calls.append(speaker_id)
                return speaker_id

            def get_speaker_name(self, speaker_id):
                return f"speaker {speaker_id}"

            async def text_to_sound(self, text, speaker, speed_scale=1.0):
                synthesis_calls.append((text, speaker))
                return b"RIFF"

        class Users:
            def get_user(self, user_id):
                return SimpleNamespace(sound=ALL_RANDOM_SPEAKER_ID)

        service = SpeechService(
            VoiceVox(),
            Users(),
            AudioCache(tmp_path / "audio"),
        )

        first_result = await service.synthesize("same", 1)
        second_result = await service.synthesize("same", 1)

        assert first_result.path != second_result.path
        assert first_result.speaker_name == "speaker 3"
        assert second_result.speaker_name == "speaker 107"
        assert random_calls == [3, 107]
        assert synthesis_calls == [("same", 3), ("same", 107)]

    asyncio.run(scenario())


def test_speech_service_regenerates_expired_cache(tmp_path):
    async def scenario():
        synthesis_calls = []

        class VoiceVox:
            def get_speaker_name(self, speaker_id):
                return f"speaker {speaker_id}"

            async def text_to_sound(self, text, speaker, speed_scale=1.0):
                synthesis_calls.append((text, speaker))
                return b"RIFF"

        class Users:
            def get_user(self, user_id):
                return SimpleNamespace(sound=3)

        service = SpeechService(
            VoiceVox(),
            Users(),
            AudioCache(tmp_path / "audio"),
        )

        result = await service.synthesize("same", 1)
        path = result.path
        expired_at = time.time() - timedelta(days=31).total_seconds()
        os.utime(path, (expired_at, expired_at))

        refreshed_result = await service.synthesize("same", 1)

        assert refreshed_result.path == path
        assert synthesis_calls == [("same", 3), ("same", 3)]

    asyncio.run(scenario())


def test_speech_service_separates_cache_and_synthesis_by_speed_scale(tmp_path):
    async def scenario():
        synthesis_calls = []

        class VoiceVox:
            def get_speaker_name(self, speaker_id):
                return f"speaker {speaker_id}"

            async def text_to_sound(self, text, speaker, speed_scale):
                synthesis_calls.append((text, speaker, speed_scale))
                return b"RIFF"

        class Users:
            def get_user(self, user_id):
                return SimpleNamespace(sound=3, speed_scale=1.25)

        service = SpeechService(
            VoiceVox(),
            Users(),
            AudioCache(tmp_path / "audio"),
        )

        result = await service.synthesize("same", 1)

        assert result.path.name == f"{AudioCache.cache_key('same')}-speed-1.25.wav"
        assert synthesis_calls == [("same", 3, 1.25)]

    asyncio.run(scenario())
