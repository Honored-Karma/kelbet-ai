from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModerationProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ProviderModerationResult:
    flagged: bool
    categories: tuple[str, ...]
    provider: str
    model: str
    request_id: str | None = None


class ModerationProvider(Protocol):
    async def moderate_text(self, text: str) -> ProviderModerationResult: ...
