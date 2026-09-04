import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from typing import TypeGuard, cast


def _is_string_keyed_dict(value: object) -> TypeGuard[dict[str, object]]:
    if not isinstance(value, dict):
        return False
    items = cast(dict[object, object], value)
    return all(isinstance(key, str) for key in items)


def _read_int(
    record: dict[str, object],
    field_name: str,
    *,
    default: int | None = None,
) -> int:
    if field_name not in record:
        if default is None:
            raise TypeError(f"User field {field_name!r} is required.")
        return default

    value = record[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"User field {field_name!r} must be an integer.")
    return value


def _read_text(
    record: dict[str, object],
    field_name: str,
    *,
    default: str = "",
) -> str:
    if field_name not in record:
        return default

    value = record[field_name]
    if not isinstance(value, str):
        raise TypeError(f"User field {field_name!r} must be a string.")
    return value


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

    def to_dict(self) -> dict[str, int | str]:
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
        self.file_path = str(Path(file_path))
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
        if not _is_string_keyed_dict(data):
            raise TypeError("User data must be a JSON object.")

        loaded: dict[int, User] = {}
        for key, value in data.items():
            if not _is_string_keyed_dict(value):
                raise TypeError("Each user entry must be a JSON object.")

            try:
                user_id = int(key)
            except ValueError as error:
                raise ValueError(f"Invalid user ID key: {key!r}.") from error

            expected_fields = {"user_id", "sound", "entry_audio", "exit_audio"}
            unexpected_fields = set(value) - expected_fields
            if unexpected_fields:
                raise TypeError(
                    f"Unexpected user fields: {sorted(unexpected_fields)!r}."
                )

            record_user_id = _read_int(value, "user_id")
            if record_user_id != user_id:
                raise ValueError(
                    f"User ID key {user_id} does not match record value "
                    f"{record_user_id}."
                )
            if user_id in loaded:
                raise ValueError(f"Duplicate user ID: {user_id}.")

            loaded[user_id] = User(
                user_id=record_user_id,
                sound=_read_int(value, "sound", default=3),
                entry_audio=_read_text(value, "entry_audio"),
                exit_audio=_read_text(value, "exit_audio"),
            )
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
