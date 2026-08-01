"""Deterministic, bounded text overlays for approved server-side templates."""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from kelbet.providers.base import GenerationOutput

_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_IMAGE_PIXELS = 40_000_000
_FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSans-Variable.ttf"


class TemplateCompositorError(RuntimeError):
    """Safe error raised when a controlled overlay cannot be produced."""


def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(_FONT_PATH), size=size)
    except OSError as exc:
        raise TemplateCompositorError("Bundled template font is unavailable") from exc


def _fit_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int,
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if current and width > max_width:
            lines.append(current)
            current = word
            if len(lines) == max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and words and " ".join(lines) != text:
        last = lines[-1]
        while last and draw.textbbox((0, 0), f"{last}…", font=font)[2] > max_width:
            last = last[:-1].rstrip()
        lines[-1] = f"{last}…" if last else "…"
    return lines


def _draw_text_block(
    canvas: Image.Image,
    values: dict[str, Any],
    *,
    variant: str,
) -> None:
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = max(24, width // 24)
    panel_top = int(height * 0.57)
    draw.rounded_rectangle(
        (margin, panel_top, width - margin, height - margin),
        radius=max(20, width // 32),
        fill=(12, 18, 28, 224) if variant == "product_card_v1" else (45, 25, 18, 218),
        outline=(255, 255, 255, 45),
        width=max(1, width // 360),
    )

    title_font = _font(max(26, width // 18))
    body_font = _font(max(18, width // 30))
    accent_font = _font(max(24, width // 22))
    x = margin * 2
    y = float(panel_top + margin)
    text_width = width - margin * 4
    line_gap = max(7, height // 100)

    headline = str(values.get("headline") or "")
    for line in _fit_lines(draw, headline, title_font, text_width, max_lines=2):
        draw.text((x, y), line, font=title_font, fill=(255, 255, 255, 255))
        y += draw.textbbox((0, 0), line, font=title_font)[3] + line_gap

    body = str(values.get("body") or "")
    if body:
        for line in _fit_lines(draw, body, body_font, text_width, max_lines=2):
            draw.text((x, y), line, font=body_font, fill=(224, 229, 236, 255))
            y += draw.textbbox((0, 0), line, font=body_font)[3] + line_gap

    if variant == "product_card_v1":
        accent = str(values.get("price") or "")
        footer = str(values.get("contact") or "")
    else:
        accent = str(values.get("date") or "")
        footer = str(values.get("contact") or "")
    footer_y = height - margin * 2 - max(24, width // 28)
    draw.text((x, footer_y), footer, font=body_font, fill=(224, 229, 236, 255))
    accent_width = draw.textbbox((0, 0), accent, font=accent_font)[2]
    draw.text(
        (width - margin * 2 - accent_width, footer_y),
        accent,
        font=accent_font,
        fill=(255, 207, 92, 255),
    )


def _compose_image(output: GenerationOutput, inputs: dict[str, Any]) -> GenerationOutput:
    if output.content_type not in _IMAGE_TYPES:
        raise TemplateCompositorError("Product-card template requires an image output")
    try:
        from io import BytesIO

        source = Image.open(BytesIO(output.data))
        if source.width * source.height > _MAX_IMAGE_PIXELS:
            raise TemplateCompositorError("Generated image is too large to compose safely")
        canvas = ImageOps.exif_transpose(source).convert("RGBA")
        _draw_text_block(canvas, inputs, variant="product_card_v1")
        rendered = BytesIO()
        canvas.save(rendered, format="PNG", optimize=True)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise TemplateCompositorError("Generated image could not be composed") from exc
    return GenerationOutput(
        content_type="image/png",
        data=rendered.getvalue(),
        meta={**output.meta, "compositor": "product_card_v1"},
    )


def _video_overlay(aspect_ratio: str, inputs: dict[str, Any]) -> Image.Image:
    size = (1280, 720) if aspect_ratio == "16:9" else (720, 1280)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    _draw_text_block(overlay, inputs, variant="toi_invite_v1")
    return overlay


def _compose_video(
    output: GenerationOutput,
    inputs: dict[str, Any],
    aspect_ratio: str,
) -> GenerationOutput:
    if output.content_type != "video/mp4":
        raise TemplateCompositorError("Invitation template requires an MP4 output")
    try:
        with tempfile.TemporaryDirectory(prefix="kelbet-template-") as temp_dir:
            directory = Path(temp_dir)
            source_path = directory / "source.mp4"
            overlay_path = directory / "overlay.png"
            result_path = directory / "result.mp4"
            source_path.write_bytes(output.data)
            _video_overlay(aspect_ratio, inputs).save(overlay_path, format="PNG")
            executable = imageio_ffmpeg.get_ffmpeg_exe()
            command = [
                executable,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source_path),
                "-loop",
                "1",
                "-i",
                str(overlay_path),
                "-filter_complex",
                (
                    "[1:v][0:v]scale2ref=w=main_w:h=main_h[overlay][base];"
                    "[base][overlay]overlay=0:0:shortest=1[video]"
                ),
                "-map",
                "[video]",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
                "-movflags",
                "+faststart",
                "-y",
                str(result_path),
            ]
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=120,
            )
            rendered = result_path.read_bytes()
            if not rendered:
                raise TemplateCompositorError("Invitation compositor produced an empty video")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise TemplateCompositorError("Generated video could not be composed") from exc
    return GenerationOutput(
        content_type="video/mp4",
        data=rendered,
        meta={**output.meta, "compositor": "toi_invite_v1"},
    )


class TemplateCompositor:
    async def compose(
        self,
        output: GenerationOutput,
        *,
        compositor: str,
        inputs: dict[str, Any],
        aspect_ratio: str,
    ) -> GenerationOutput:
        if compositor == "product_card_v1":
            return await asyncio.to_thread(_compose_image, output, inputs)
        if compositor == "toi_invite_v1":
            return await asyncio.to_thread(_compose_video, output, inputs, aspect_ratio)
        raise TemplateCompositorError("Unknown template compositor")
