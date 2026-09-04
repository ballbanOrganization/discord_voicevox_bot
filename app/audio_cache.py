import hashlib
import os
import tempfile
from pathlib import Path


class AudioCache:
    """Manage the compatible speaker-directory and MD5 WAV cache."""

    def __init__(self, root: str | os.PathLike[str] = "audio"):
        self.root = Path(root)

    @staticmethod
    def cache_key(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def path_for(self, text: str, speaker_name: str) -> Path:
        return self.root / speaker_name / f"{self.cache_key(text)}.wav"

    def write(self, path: str | os.PathLike[str], content: bytes) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = temporary.name
                temporary.write(content)
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
