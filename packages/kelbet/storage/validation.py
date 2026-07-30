"""Content-type and magic-byte validation for uploads."""

from __future__ import annotations

from kelbet.domain.exceptions import UploadValidationError

ALLOWED_IMAGE_MIME = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_OUTPUT_MIME = frozenset(
    {
        *ALLOWED_IMAGE_MIME,
        "text/plain",
        "text/plain; charset=utf-8",
        "video/mp4",
    }
)

# (mime, signatures) — signatures are prefixes; webp needs RIFF....WEBP
_JPEG = (b"\xff\xd8\xff",)
_PNG = (b"\x89PNG\r\n\x1a\n",)


def _normalize_mime(content_type: str) -> str:
    return content_type.strip().lower()


def extension_for_mime(content_type: str) -> str:
    mime = _normalize_mime(content_type)
    mapping = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "text/plain": "txt",
        "text/plain; charset=utf-8": "txt",
        "video/mp4": "mp4",
    }
    try:
        return mapping[mime]
    except KeyError as exc:
        raise UploadValidationError(f"Unsupported content type: {content_type}") from exc


def assert_allowed_content_type(content_type: str) -> str:
    normalized = content_type.strip().lower()
    if normalized not in ALLOWED_IMAGE_MIME:
        raise UploadValidationError(f"Unsupported content type: {content_type}")
    return normalized


def assert_size_within_limit(byte_size: int, *, max_bytes: int) -> None:
    if byte_size <= 0:
        raise UploadValidationError("byte_size must be positive")
    if byte_size > max_bytes:
        raise UploadValidationError(f"File exceeds max size of {max_bytes} bytes")


def looks_like_webp(header: bytes) -> bool:
    return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"


def validate_magic_bytes(content_type: str, header: bytes) -> None:
    mime = assert_allowed_content_type(content_type)
    if mime == "image/jpeg":
        if not any(header.startswith(sig) for sig in _JPEG):
            raise UploadValidationError("Magic bytes do not match image/jpeg")
        return
    if mime == "image/png":
        if not any(header.startswith(sig) for sig in _PNG):
            raise UploadValidationError("Magic bytes do not match image/png")
        return
    if mime == "image/webp":
        if not looks_like_webp(header):
            raise UploadValidationError("Magic bytes do not match image/webp")
        return
    raise UploadValidationError(f"Unsupported content type: {mime}")


def image_dimensions(content_type: str, data: bytes) -> tuple[int, int] | None:
    """Read image dimensions from a bounded prefix without decoding pixels."""
    mime = _normalize_mime(content_type)
    if mime == "image/png":
        if len(data) < 24 or not data.startswith(_PNG[0]):
            return None
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return (width, height) if width > 0 and height > 0 else None

    if mime == "image/jpeg":
        if len(data) < 4 or not data.startswith(_JPEG[0]):
            return None
        index = 2
        sof_markers = {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }
        while index + 4 <= len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            while index < len(data) and data[index] == 0xFF:
                index += 1
            if index >= len(data):
                return None
            marker = data[index]
            index += 1
            if marker in {0xD8, 0xD9}:
                continue
            if marker == 0xDA:
                return None
            if index + 2 > len(data):
                return None
            segment_len = int.from_bytes(data[index : index + 2], "big")
            if segment_len < 2 or index + segment_len > len(data):
                return None
            if marker in sof_markers and segment_len >= 7:
                height = int.from_bytes(data[index + 3 : index + 5], "big")
                width = int.from_bytes(data[index + 5 : index + 7], "big")
                return (width, height) if width > 0 and height > 0 else None
            index += segment_len
        return None

    if mime == "image/webp":
        if len(data) < 30 or not looks_like_webp(data):
            return None
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return (width, height)
        if chunk == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return (width, height)
        if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
            return (width, height) if width > 0 and height > 0 else None
    return None
