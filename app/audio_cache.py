import hashlib
import logging
import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from .speed import (
    DEFAULT_SPEED_SCALE,
    format_speed_scale,
    normalize_speed_scale,
)

logger = logging.getLogger(__name__)


class AudioCache:
    """Manage the compatible speaker-directory and expiring MD5 WAV cache."""

    def __init__(self, root: str | os.PathLike[str] = "audio"):
        self.root = Path(root)
        self.max_age = timedelta(days=30)

    @staticmethod
    def cache_key(text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def path_for(
        self,
        text: str,
        speaker_name: str,
        speed_scale: float = DEFAULT_SPEED_SCALE,
    ) -> Path:
        normalized_speed_scale = normalize_speed_scale(speed_scale)
        speed_suffix = (
            ""
            if normalized_speed_scale == DEFAULT_SPEED_SCALE
            else f"-speed-{format_speed_scale(normalized_speed_scale)}"
        )
        return self.root / speaker_name / f"{self.cache_key(text)}{speed_suffix}.wav"

    def is_fresh(self, path: str | os.PathLike[str]) -> bool:
        path = Path(path)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        if not path.is_file():
            return False
        return time.time() - stat.st_mtime < self.max_age.total_seconds()

    def cleanup_expired(self, now: float | None = None) -> int:
        """Delete expired WAV files and return the number removed."""
        cutoff = (time.time() if now is None else now) - self.max_age.total_seconds()
        removed = 0
        if not self.root.is_dir():
            return removed

        try:
            paths = self.root.rglob("*.wav")
            for path in paths:
                try:
                    if path.is_file() and path.stat().st_mtime < cutoff:
                        path.unlink()
                        removed += 1
                except FileNotFoundError:
                    continue
                except OSError:
                    logger.warning(
                        "Could not remove expired audio cache file: %s",
                        path,
                        exc_info=True,
                    )
        except OSError:
            logger.warning(
                "Could not enumerate audio cache files under %s.",
                self.root,
                exc_info=True,
            )
        return removed

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
