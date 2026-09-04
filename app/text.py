import ipaddress
import re
from collections import defaultdict
from collections.abc import Iterable

_URL_PATTERN = re.compile(
    r"(?<![\w@])(?:https?://|ftp://|www\.)[^\s<>(){}]+"
    r"|(?<![\w@./:-])"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}(?::\d+)?(?:[/?#][^\s<>(){}]*)?\.?"
    r"(?![\w.-])",
    re.IGNORECASE,
)
_IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
_IPV4_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9.])(?:{_IPV4_OCTET}\.){{3}}{_IPV4_OCTET}(?![A-Za-z0-9.])"
)
_IPV6_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*(?![A-Za-z0-9])"
)
_W_PATTERN = re.compile(r"[wWｗＷ]{4,}")
_URL_TRAILING_PUNCTUATION = ".,!?;:)]}，。！？；：、）】》」』"

_ATTACHMENT_TYPES = (
    ("application", "添付アプリケーション"),
    ("audio", "添付音声"),
    ("image", "添付画像"),
    ("message", "添付メッセージ"),
    ("multipart", "添付マルチパート"),
    ("text", "添付テキスト"),
    ("video", "添付動画"),
)


def normalize_text(text: str) -> str | None:
    """Apply the bot's message filtering and normalization rules."""
    if text.startswith(("m!", "/")):
        return None

    normalized = _URL_PATTERN.sub(_replace_url, text)
    normalized = _IPV6_PATTERN.sub(_replace_ipv6, normalized)
    normalized = _IPV4_PATTERN.sub(_replace_ipv4, normalized)

    normalized = _W_PATTERN.sub(_replace_w, normalized)
    if len(normalized) > 300:
        normalized = normalized[:300] + "以下省略。"
    return normalized


def _replace_url(match: re.Match[str]) -> str:
    value = match.group(0)
    trimmed = value.rstrip(_URL_TRAILING_PUNCTUATION)
    trailing = value[len(trimmed):]
    return f"ウェブサイトリンク{trailing or '。'}"


def _replacement_ending(match: re.Match[str]) -> str:
    if match.end() < len(match.string):
        next_character = match.string[match.end()]
        if next_character in _URL_TRAILING_PUNCTUATION:
            return ""
    return "。"


def _replace_ipv4(match: re.Match[str]) -> str:
    return f"IPアドレス{_replacement_ending(match)}"


def _replace_w(match: re.Match[str]) -> str:
    return f"わらわら{_replacement_ending(match)}"


def _replace_ipv6(match: re.Match[str]) -> str:
    value = match.group(0)
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return value
    return f"IPアドレス{_replacement_ending(match)}"


def attachment_category(content_type: str | None) -> str:
    value = (content_type or "").lower()
    for prefix, category in _ATTACHMENT_TYPES:
        if prefix in value:
            return f"{category}。"
    return "うんこなう。"


def attachment_announcements(attachments: Iterable[object]) -> list[str]:
    """Return one announcement for each attachment category in input order."""
    counts: dict[str, int] = defaultdict(int)
    for attachment in attachments:
        content_type = getattr(attachment, "content_type", None)
        counts[attachment_category(content_type)] += 1

    announcements: list[str] = []
    for category, count in counts.items():
        label = category.removesuffix("。")
        if not label.startswith("添付"):
            label = f"添付{label}"
        suffix = str(count) if count > 1 else ""
        announcements.append(f"{label}{suffix}。")
    return announcements
