import asyncio
import aiohttp
import pytest

from app.voicevox import VoiceVox, VoiceVoxError


def test_random_speaker_id_uses_all_loaded_styles(monkeypatch):
    voicevox = VoiceVox()
    voicevox.speaker_dict.update(
        {
            "speaker one": {"style one": 3, "style two": 4},
            "speaker two": {"style three": 107},
        }
    )
    choices = []

    def choose(values):
        choices.append(values)
        return values[-1]

    monkeypatch.setattr("app.voicevox.random.choice", choose)

    assert voicevox.get_random_speaker_id() == 107
    assert choices == [[3, 4, 107]]


def test_random_speaker_id_requires_loaded_speakers():
    with pytest.raises(VoiceVoxError, match="No VOICEVOX speakers"):
        VoiceVox().get_random_speaker_id()


def test_random_speaker_id_avoids_the_previous_selection(monkeypatch):
    voicevox = VoiceVox()
    voicevox.speaker_dict.update(
        {
            "speaker one": {"style one": 3},
            "speaker two": {"style two": 107},
        }
    )
    choices = iter((3, 107))
    candidate_lists = []

    def choose(values):
        candidate_lists.append(values)
        return next(choices)

    monkeypatch.setattr("app.voicevox.random.choice", choose)

    assert voicevox.get_random_speaker_id() == 3
    assert voicevox.get_random_speaker_id() == 107
    assert candidate_lists == [[3, 107], [107]]


def test_text_to_sound_applies_speed_scale_to_audio_query():
    async def scenario():
        captured = {}

        class TestVoiceVox(VoiceVox):
            async def get_query(self, text, speaker):
                return {"text": text, "speaker": speaker, "speedScale": 1.0}

            async def get_synthesis(self, query, speaker):
                captured["query"] = query
                captured["speaker"] = speaker
                return b"RIFF"

        voicevox = TestVoiceVox()

        assert await voicevox.text_to_sound("hello", 3, 1.25) == b"RIFF"
        assert captured == {
            "query": {"text": "hello", "speaker": 3, "speedScale": 1.25},
            "speaker": 3,
        }

    asyncio.run(scenario())


def test_voicevox_wraps_transport_errors():
    async def scenario():
        class Session:
            closed = False

            def request(self, *_args, **_kwargs):
                raise aiohttp.ClientError("engine unavailable")

        voicevox = VoiceVox(session=Session())

        with pytest.raises(VoiceVoxError, match="request failed"):
            await voicevox.get_query("hello", 3)

    asyncio.run(scenario())


def test_voicevox_rejects_invalid_json_response():
    async def scenario():
        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def json(self):
                raise ValueError("invalid response")

        class Session:
            closed = False

            def request(self, *_args, **_kwargs):
                return Response()

        voicevox = VoiceVox(session=Session())

        with pytest.raises(VoiceVoxError, match="invalid JSON"):
            await voicevox.get_query("hello", 3)

    asyncio.run(scenario())


def test_voicevox_includes_http_failure_details():
    async def scenario():
        class Response:
            status = 503

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def text(self):
                return "engine unavailable"

        class Session:
            closed = False

            def request(self, *_args, **_kwargs):
                return Response()

        voicevox = VoiceVox(session=Session())

        with pytest.raises(VoiceVoxError, match="HTTP 503.*engine unavailable"):
            await voicevox.get_query("hello", 3)

    asyncio.run(scenario())
