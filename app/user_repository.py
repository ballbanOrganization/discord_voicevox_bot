import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import Any


class User:
    def __init__(
        self,
        user_id: int,
        sound: int = 3,
        entry_audio: str = "",
        exit_audio: str = "",
    ):
        self.user_id = int(user_id)
        self.sound = int(sound)
        self.entry_audio = entry_audio
        self.exit_audio = exit_audio

    def set_entry_audio(self, text: str) -> None:
        self.entry_audio = text

    def set_exit_audio(self, text: str) -> None:
        self.exit_audio = text

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "sound": self.sound,
            "entry_audio": self.entry_audio,
            "exit_audio": self.exit_audio,
        }


class UserRepository:
    """Persist user settings using the existing JSON schema."""

    def __init__(
        self,
        file_path: str | os.PathLike[str] = "data/user_data.json",
    ):
        self.file_path = os.fspath(file_path)
        self.user_data_dic: dict[int, User] = {}
        self._lock = RLock()
        self.load_user_data()

    def load_user_data(self) -> None:
        path = Path(self.file_path)
        if not path.is_file():
            with self._lock:
                self.user_data_dic = {}
            return

        with path.open("r", encoding="utf-8") as data_file:
            data = json.load(data_file)
        if not isinstance(data, dict):
            raise ValueError("User data must be a JSON object.")

        loaded: dict[int, User] = {}
        for key, value in data.items():
            if not isinstance(value, dict):
                raise ValueError("Each user entry must be a JSON object.")
            loaded[int(key)] = User(**value)
        with self._lock:
            self.user_data_dic = loaded

    def save_user_data(self) -> None:
        path = Path(self.file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = {
                str(user_id): user.to_dict()
                for user_id, user in self.user_data_dic.items()
            }

            temporary_path: str | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    newline="\n",
                    dir=path.parent,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary:
                    temporary_path = temporary.name
                    json.dump(data, temporary, ensure_ascii=False, indent=4)
                    temporary.write("\n")
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_path, path)
                temporary_path = None
            finally:
                if temporary_path is not None:
                    try:
                        os.unlink(temporary_path)
                    except FileNotFoundError:
                        pass

    def get_user(self, user_id: int) -> User:
        normalized_id = int(user_id)
        with self._lock:
            user = self.user_data_dic.get(normalized_id)
            if user is None:
                user = User(normalized_id)
                self.user_data_dic[normalized_id] = user
            return user

    def save_user(self, user: User) -> None:
        with self._lock:
            self.user_data_dic[user.user_id] = user
        self.save_user_data()


UserData = UserRepository
