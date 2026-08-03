"""Which images a video model accepts, and which combinations Google will take.

Veo lets a request carry images in three mutually exclusive shapes, and the API
rejects the wrong combination with a 400 rather than degrading:

* ``first_frame`` — one image, the opening frame. Cannot be combined with
  reference images.
* ``first_last_frame`` — opening and closing frame; Veo generates the transition.
  Cannot be combined with reference images.
* ``reference_assets`` — up to three images of a subject to keep consistent
  across shots. Requires a prompt, and excludes the frame images entirely.

Source: https://ai.google.dev/gemini-api/docs/veo and the Vertex reference for
``VideoGenerationModelInstance``, which states the exclusions directly: "If
``image`` is provided, ``video`` and ``referenceImages`` cannot be used" and "If
``referenceImages`` are provided, ``prompt`` must also be provided, and
``image``, ``video``, and ``lastFrame`` cannot be used."

The point of validating here is that a rejected request is not free. Credits are
reserved before the provider is called, so an unsupported combination that only
fails at Google costs the user a wait and a refund cycle for a mistake we could
see at quote time. Every rule below is enforced before a price is quoted.

Modes are declared per catalog row rather than hardcoded, so a model that gains a
capability is a seed change. That matters for one restriction in particular:
reference images were 16:9-only when this was written, and Google said 9:16 was
coming, so the allowed aspect ratios live in the catalog and not in this file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kelbet.domain.exceptions import InvalidQuoteParamsError

#: Mode assumed when a request says nothing. Matches the behaviour that existed
#: before modes were introduced: an optional single opening frame.
DEFAULT_MODE = "first_frame"

FIRST_FRAME = "first_frame"
FIRST_LAST_FRAME = "first_last_frame"
REFERENCE_ASSETS = "reference_assets"

#: Ceiling from the Veo API: at most three ``asset`` reference images.
MAX_REFERENCE_ASSETS = 3


@dataclass(frozen=True, slots=True)
class VideoInputMode:
    """How many images a mode takes, and the aspect ratios it may run at."""

    name: str
    min_assets: int
    max_assets: int
    #: Empty means "whatever the model supports" — a mode only narrows this when
    #: the provider is stricter for that shape than for plain generation.
    aspect_ratios: tuple[str, ...] = ()

    def allows_aspect(self, aspect: str) -> bool:
        return not self.aspect_ratios or aspect in self.aspect_ratios


def _mode_from_raw(name: str, raw: dict[str, Any]) -> VideoInputMode:
    max_assets = int(raw.get("max_assets") or 0)
    if name == REFERENCE_ASSETS:
        # Declaring more than the API accepts would fail at Google with a 400
        # after the user had already paid, so clamp it at the source.
        max_assets = min(max_assets, MAX_REFERENCE_ASSETS)
    aspects = raw.get("aspect_ratios")
    return VideoInputMode(
        name=name,
        min_assets=int(raw.get("min_assets") or 0),
        max_assets=max_assets,
        aspect_ratios=tuple(str(value) for value in aspects) if aspects else (),
    )


def declared_modes(capabilities: dict[str, Any]) -> dict[str, VideoInputMode]:
    """Modes a catalog row declares, or just the default when it declares none."""

    block = capabilities.get("video_inputs")
    block = block if isinstance(block, dict) else {}
    raw_modes = block.get("modes")
    raw_modes = raw_modes if isinstance(raw_modes, dict) else {}
    if not raw_modes:
        max_assets = 1 if capabilities.get("supports_source_image", True) else 0
        return {DEFAULT_MODE: VideoInputMode(DEFAULT_MODE, 0, max_assets)}
    return {
        str(name): _mode_from_raw(str(name), raw if isinstance(raw, dict) else {})
        for name, raw in raw_modes.items()
    }


def resolve_mode(capabilities: dict[str, Any], requested: object) -> VideoInputMode:
    """The mode for this request, rejecting anything the model does not declare."""

    modes = declared_modes(capabilities)
    name = str(requested) if requested is not None else DEFAULT_MODE
    mode = modes.get(name)
    if mode is None:
        raise InvalidQuoteParamsError(
            f"Unsupported input_mode: {name}. This model accepts: {sorted(modes)}"
        )
    return mode


def narrow_aspect_ratios(
    allowed: list[str] | None,
    mode: VideoInputMode,
) -> list[str]:
    """Aspect ratios usable in this mode: the model's list, minus the mode's limits.

    Order is taken from the model so the default stays predictable, and the
    intersection is what makes an unsupported default impossible — picking the
    model's first ratio when the mode forbids it would quote a request that
    cannot run.
    """

    model_aspects = [str(value) for value in allowed or []]
    if not mode.aspect_ratios:
        return model_aspects
    return [aspect for aspect in model_aspects if aspect in mode.aspect_ratios]


def validate_asset_count(mode: VideoInputMode, count: int) -> None:
    """Check the image count against the mode before any credits are held."""

    if count < mode.min_assets:
        raise InvalidQuoteParamsError(
            f"Mode {mode.name} needs at least {mode.min_assets} image(s), got {count}"
        )
    if count > mode.max_assets:
        raise InvalidQuoteParamsError(
            f"Mode {mode.name} accepts at most {mode.max_assets} image(s), got {count}"
        )


def requires_prompt(mode: VideoInputMode) -> bool:
    """Reference images guide a prompt; they cannot stand in for one."""

    return mode.name == REFERENCE_ASSETS
