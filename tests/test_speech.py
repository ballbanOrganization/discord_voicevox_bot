import asyncio
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

            async def text_to_sound(self, text, speaker):
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

        paths = await asyncio.gather(
            service.audio_path("same", 1),
            service.audio_path("same", 2),
        )

        assert paths[0] == paths[1]
        assert calls == [("same", 3)]
        assert service._locks == {}

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

            async def text_to_sound(self, text, speaker):
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

        first_path = await service.audio_path("same", 1)
        second_path = await service.audio_path("same", 1)

        assert first_path != second_path
        assert random_calls == [3, 107]
        assert synthesis_calls == [("same", 3), ("same", 107)]

    asyncio.run(scenario())
