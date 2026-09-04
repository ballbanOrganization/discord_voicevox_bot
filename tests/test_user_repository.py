import json

from app.user_repository import UserRepository


def test_user_json_round_trip_and_schema(tmp_path):
    path = tmp_path / "data" / "user_data.json"
    repository = UserRepository(path)
    user = repository.get_user(42)
    user.sound = 8
    user.entry_audio = "入室"
    user.exit_audio = "退室"
    repository.save_user(user)

    with path.open(encoding="utf-8") as data_file:
        saved = json.load(data_file)

    assert saved == {
        "42": {
            "user_id": 42,
            "sound": 8,
            "entry_audio": "入室",
            "exit_audio": "退室",
        }
    }

    loaded = UserRepository(path).get_user(42)
    assert loaded.user_id == 42
    assert loaded.sound == 8
    assert loaded.entry_audio == "入室"
    assert loaded.exit_audio == "退室"


def test_save_replaces_existing_file_atomically(tmp_path):
    path = tmp_path / "user_data.json"
    repository = UserRepository(path)
    repository.get_user(1).sound = 5
    repository.save_user_data()

    repository.get_user(2).sound = 6
    repository.save_user_data()

    assert path.is_file()
    assert not list(tmp_path.glob("*.tmp"))
