"""Unit tests for upload magic-byte validation."""

import pytest

from kelbet.domain.exceptions import UploadValidationError
from kelbet.storage.validation import (
    assert_allowed_content_type,
    assert_size_within_limit,
    image_dimensions,
    validate_magic_bytes,
)


def test_jpeg_png_webp_magic() -> None:
    validate_magic_bytes("image/jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 20)
    validate_magic_bytes("image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    validate_magic_bytes("image/webp", b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8)


def test_magic_mismatch_rejected() -> None:
    with pytest.raises(UploadValidationError):
        validate_magic_bytes("image/png", b"\xff\xd8\xff\xe0" + b"\x00" * 20)


def test_content_type_and_size_guards() -> None:
    assert assert_allowed_content_type("image/jpeg") == "image/jpeg"
    with pytest.raises(UploadValidationError):
        assert_allowed_content_type("application/pdf")
    with pytest.raises(UploadValidationError):
        assert_size_within_limit(0, max_bytes=100)
    with pytest.raises(UploadValidationError):
        assert_size_within_limit(200, max_bytes=100)


def test_image_dimensions_from_bounded_headers() -> None:
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + (1920).to_bytes(4, "big")
        + (1080).to_bytes(4, "big")
    )
    jpeg = (
        b"\xff\xd8"
        + b"\xff\xe0\x00\x04\x00\x00"
        + b"\xff\xc0\x00\x11\x08"
        + (720).to_bytes(2, "big")
        + (1280).to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    )
    webp = (
        b"RIFF"
        + b"\x00\x00\x00\x00"
        + b"WEBPVP8X"
        + b"\x0a\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + (639).to_bytes(3, "little")
        + (479).to_bytes(3, "little")
    )

    assert image_dimensions("image/png", png) == (1920, 1080)
    assert image_dimensions("image/jpeg", jpeg) == (1280, 720)
    assert image_dimensions("image/webp", webp) == (640, 480)
    assert image_dimensions("image/png", b"not-png") is None
