"""Phase 3 task 3.3 — shared analyzer/messages.py builders."""

from pathlib import Path

from assetcache.core.analyzer.messages import (
    BATCH_AUDIO_PROMPT,
    BATCH_IMAGE_PROMPT,
    build_audio_chat_messages,
    build_image_chat_messages,
)


def test_build_image_chat_messages_includes_image_b64(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    messages = build_image_chat_messages(abs_path=img, prompt="describe")
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].content == "describe"
    assert len(messages[0].images_b64) == 1
    # base64 of b"\x89PNG\r\n\x1a\nfake"
    import base64
    expected = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
    assert messages[0].images_b64[0] == expected


def test_build_audio_chat_messages_includes_audio_b64(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFFfake")
    messages = build_audio_chat_messages(abs_path=wav, prompt="describe sound")
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].content == "describe sound"
    assert len(messages[0].audio_b64) == 1
    b64, mime = messages[0].audio_b64[0]
    assert mime == "audio/wav"
    import base64
    expected = base64.b64encode(b"RIFFfake").decode("ascii")
    assert b64 == expected


def test_build_audio_chat_messages_mime_by_extension(tmp_path):
    """mp3 / ogg 등 다른 확장자 mime type 분기."""
    mp3 = tmp_path / "a.mp3"
    mp3.write_bytes(b"fake")
    messages = build_audio_chat_messages(abs_path=mp3, prompt="x")
    _, mime = messages[0].audio_b64[0]
    assert mime == "audio/mpeg"


def test_build_audio_chat_messages_unknown_extension_fallback(tmp_path):
    """알 수 없는 확장자는 application/octet-stream 으로 폴백."""
    xz = tmp_path / "a.xyz"
    xz.write_bytes(b"data")
    messages = build_audio_chat_messages(abs_path=xz, prompt="x")
    _, mime = messages[0].audio_b64[0]
    assert mime == "application/octet-stream"


def test_batch_prompts_are_strings():
    """BATCH_IMAGE_PROMPT / BATCH_AUDIO_PROMPT 가 비어있지 않은 문자열."""
    assert isinstance(BATCH_IMAGE_PROMPT, str) and BATCH_IMAGE_PROMPT
    assert isinstance(BATCH_AUDIO_PROMPT, str) and BATCH_AUDIO_PROMPT
