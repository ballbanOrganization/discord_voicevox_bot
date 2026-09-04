import asyncio
from dataclasses import dataclass
from pathlib import Path

from .audio_cache import AudioCache
from .user_repository import UserRepository
from .voicevox import ALL_RANDOM_SPEAKER_ID, VoiceVox


@dataclass
class _PathLock:
    lock: asyncio.Lock
    users: int = 0


class SpeechService:
    def __init__(
        self,
        voicevox: VoiceVox,
        users: UserRepository,
        cache: AudioCache,
    ):
        self.voicevox = voicevox
        self.users = users
        self.cache = cache
        self._locks: dict[Path, _PathLock] = {}

    async def audio_path(self, text: str, user_id: int) -> Path:
        user = self.users.get_user(user_id)
        speaker_id = user.sound
        if speaker_id == ALL_RANDOM_SPEAKER_ID:
            speaker_id = self.voicevox.get_random_speaker_id()
        speaker_name = self.voicevox.get_speaker_name(speaker_id)
        path = self.cache.path_for(text, speaker_name)
        if path.is_file():
            return path

        path_lock = self._locks.get(path)
        if path_lock is None:
            path_lock = _PathLock(asyncio.Lock())
            self._locks[path] = path_lock
        path_lock.users += 1
        try:
            async with path_lock.lock:
                if not path.is_file():
                    content = await self.voicevox.text_to_sound(text, speaker_id)
                    await asyncio.to_thread(self.cache.write, path, content)
        finally:
            path_lock.users -= 1
            if path_lock.users == 0 and self._locks.get(path) is path_lock:
                del self._locks[path]
        return path
