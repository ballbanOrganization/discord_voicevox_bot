import asyncio
from types import SimpleNamespace

from app.audio_cache import AudioCache
from app.speech import SpeechService


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
