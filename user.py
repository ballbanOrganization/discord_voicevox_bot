import os.path
import pandas as pd


class User:
    def __init__(self, user_id: int):
        self.id: int = user_id
        self.sound: int = 3


class UserData:
    def __init__(self):
        self.file_path: str = 'data/user_data.pickle'
        self.user_data_dic: dict = dict()
        self.load_user_data()

    def load_user_data(self):
        if not os.path.isfile(self.file_path):
            pd.to_pickle(dict(), self.file_path)
        self.user_data_dic = pd.read_pickle(self.file_path)

    def save_user_data(self):
        pd.to_pickle(self.user_data_dic, self.file_path)

    def get_user(self, user_id: int) -> User:
        if user_id not in self.user_data_dic:
            self.user_data_dic[user_id] = User(user_id)
        return self.user_data_dic[user_id]

    def save_user(self, user: User):
        self.user_data_dic[user.id] = user
        self.save_user_data()
