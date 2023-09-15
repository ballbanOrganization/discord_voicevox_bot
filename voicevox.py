import requests
import json


class VoiceVox:
    def __init__(self):
        self.speaker = None
        self.speaker_dic = dict()
        self.text = None
        self.query = None
        self.sound = None
        self.url = 'http://127.0.0.1:50021/'

        self.get_speakers()

    def get_query(self):
        self.query = requests.post(f'{self.url}audio_query',
                                   params=(("text", self.text), ("speaker", self.speaker)))

    def get_synthesis(self):
        self.sound = requests.post(f'{self.url}synthesis', params={"speaker": self.speaker},
                                   data=json.dumps(self.query.json()))

    def text_to_sound(self, text: str, speaker: int = 3):
        self.text = text
        self.speaker = speaker
        self.get_query()
        self.get_synthesis()

        return self.sound.content

    def get_speakers(self):
        speakers = requests.get(f'{self.url}speakers').json()
        for speaker in speakers:
            # print(speaker['speaker_uuid'])
            for style in speaker['styles']:
                self.speaker_dic[style['id']] = style['name'] + speaker['name']

    def get_speaker_name(self, speaker_id):
        result = self.speaker_dic[speaker_id]
        return result
