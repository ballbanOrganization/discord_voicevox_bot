import enum
from collections import defaultdict
import requests
import json


class VoiceVox:
    def __init__(self):
        self.speaker = None
        self.text = None
        self.query = None
        self.sound = None
        self.url = 'http://127.0.0.1:50021/'

        self.speaker_dict = defaultdict(dict)
        self.speaker_enum = None
        self.speaker_style_enum = None
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
        temp_speak_list = []
        temp_speak_style_dic = dict()
        speakers = requests.get(f'{self.url}speakers').json()
        for speaker in speakers:
            temp_speak_list.append(speaker['name'])
            for style in speaker['styles']:
                temp_speak_style_dic[speaker['name']] = {style['id']: style['name']}
                self.speaker_dict[speaker['name']][style['name']] = style['id']

    def get_speaker_name(self, speaker_id):
        for speaker_name, styles in self.speaker_dict.items():
            for style_name, v in styles.items():
                if v == speaker_id:
                    return style_name + speaker_name
        return '名称なし'

    @staticmethod
    def __create_enum(self, name: str, dic: dict):
        _k = _v = None

        class NewEnum(enum.Enum):
            nonlocal _k, _v
            for _k, _v in dic.items():
                locals()[_v] = _k

        NewEnum.__name__ = name
        return NewEnum
