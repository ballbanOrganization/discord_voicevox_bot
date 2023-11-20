import os.path
import json


class User:
    def __init__(self, user_id: int, sound: int = 3, entry_audio: str = '', exit_audio: str = ''):
        self.user_id = user_id
        self.sound = sound
        self.entry_audio = entry_audio
        self.exit_audio = exit_audio

    def set_entry_audio(self, text: str):
        self.entry_audio = text

    def set_exit_audio(self, text: str):
        self.exit_audio = text


class UserData:
    def __init__(self):
        self.file_path: str = 'data/user_data.json'
        self.user_data_dic: dict = dict()
        self.load_user_data()

    def load_user_data(self):
        if not os.path.isfile(self.file_path):
            return
        with open(self.file_path, 'r') as f:
            data = json.load(f)
            self.user_data_dic = {k: User(**v) for k, v in data.items()}

    def save_user_data(self):
        data = {int(k): v.__dict__ for k, v in self.user_data_dic.items()}
        with open(self.file_path, "w") as f:
            json.dump(data, f, indent=4)

    def get_user(self, user_id: int) -> User:
        if user_id not in self.user_data_dic:
            self.user_data_dic[user_id] = User(user_id)
        return self.user_data_dic[user_id]

    def save_user(self, user: User):
        self.user_data_dic[user.user_id] = user
        self.save_user_data()

