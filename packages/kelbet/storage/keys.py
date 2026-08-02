"""Safe object key helpers — never trust client-supplied paths."""

from __future__ import annotations

from uuid import UUID, uuid4

from kelbet.storage.validation import extension_for_mime


def build_input_object_key(*, user_id: UUID, asset_id: UUID, content_type: str) -> str:
    ext = extension_for_mime(content_type)
    return f"inputs/{user_id}/{asset_id}/{uuid4().hex}.{ext}"


def build_output_object_key(*, user_id: UUID, asset_id: UUID, content_type: str) -> str:
    ext = extension_for_mime(content_type)
    return f"outputs/{user_id}/{asset_id}/{uuid4().hex}.{ext}"


def build_workflow_step_object_key(
    *, user_id: UUID, generation_id: UUID, step_index: int
) -> str:
    """Stable key makes completion replay/crash recovery idempotent."""
    return f"workflows/{user_id}/{generation_id}/step-{step_index:02d}.mp4"
