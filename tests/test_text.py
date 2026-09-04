from types import SimpleNamespace

from app.text import attachment_announcements, normalize_text


def test_normalize_text_filters_and_rewrites_content():
    assert normalize_text("m!ping") is None
    assert normalize_text("/help") is None
    assert normalize_text("visit https://example.com now") == "リンク省略"
    assert normalize_text("server at 192.168.0.1") == "IP省略"
    assert normalize_text("すごいｗｗｗｗ") == "すごいわらわら"


def test_normalize_text_caps_long_content():
    result = normalize_text("a" * 301)

    assert result == ("a" * 300) + "以下省略"


def test_attachment_announcements_group_categories_in_order():
    attachments = [
        SimpleNamespace(content_type="image/png"),
        SimpleNamespace(content_type="audio/mpeg"),
        SimpleNamespace(content_type="image/jpeg"),
        SimpleNamespace(content_type=None),
    ]

    assert attachment_announcements(attachments) == [
        "添付画像2",
        "添付音声",
        "添付うんこなう",
    ]
