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
