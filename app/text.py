import re
from collections import defaultdict
from typing import Iterable


_URL_PATTERN = re.compile(
    r"(?:(?:https?|ftp)://|www\.)[^\s]+"
    r"|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:[/?#][^\s]*)?",
    re.IGNORECASE,
)
_IP_PATTERN = re.compile(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)")
_W_PATTERN = re.compile(r"[wWｗＷ]{4,}")

_ATTACHMENT_TYPES = (
    ("application", "アプリケーション"),
    ("audio", "音声"),
    ("image", "画像"),
    ("message", "メッセージ"),
    ("multipart", "マルチ"),
    ("text", "テキスト"),
    ("video", "動画"),
)


def normalize_text(text: str) -> str | None:
    """Apply the bot's message filtering and normalization rules."""
    if text.startswith(("m!", "/")):
        return None

    normalized = text
    if _URL_PATTERN.search(normalized):
        normalized = "リンク省略"
    if _IP_PATTERN.search(normalized):
        normalized = "IP省略"

    normalized = _W_PATTERN.sub("わらわら", normalized)
    if len(normalized) > 300:
        normalized = normalized[:300] + "以下省略"
    return normalized


def attachment_category(content_type: str | None) -> str:
    value = (content_type or "").lower()
    for prefix, category in _ATTACHMENT_TYPES:
        if prefix in value:
            return category
    return "うんこなう"


def attachment_announcements(attachments: Iterable[object]) -> list[str]:
    """Return one announcement for each attachment category in input order."""
    counts: dict[str, int] = defaultdict(int)
    for attachment in attachments:
        content_type = getattr(attachment, "content_type", None)
        counts[attachment_category(content_type)] += 1

    announcements: list[str] = []
    for category, count in counts.items():
        suffix = str(count) if count > 1 else ""
        announcements.append(f"添付{category}{suffix}")
    return announcements
