from __future__ import annotations

import re
import unicodedata

from kelbet.moderation.base import ProviderModerationResult

_LEET_TRANSLATION = str.maketrans(
    {
        "0": "о",
        "1": "і",
        "3": "з",
        "4": "ч",
        "6": "б",
        "@": "а",
    }
)

_RULES: dict[str, tuple[str, ...]] = {
    "sexual_minors": (
        "детское порно",
        "голая несовершеннолетняя",
        "child porn",
        "кәмелетке толмаған порно",
    ),
    "self_harm_instructions": (
        "как покончить с собой",
        "инструкция суицида",
        "suicide instructions",
        "өзімді өлтіру жолы",
    ),
    "violent_wrongdoing": (
        "как сделать бомбу",
        "как убить человека",
        "build a bomb",
        "бомба жасау жолы",
        "адамды өлтіру жолы",
    ),
    "illicit_weapons": (
        "сделать оружие дома",
        "самодельное оружие инструкция",
        "homemade weapon instructions",
        "үйде қару жасау",
    ),
    "nonconsensual_intimate": (
        "дипфейк порно",
        "deepfake porn",
        "жалаңаш дипфейк",
    ),
}


def _normalized_forms(text: str) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFKC", text).casefold().translate(_LEET_TRANSLATION)
    spaced = re.sub(r"[^a-zа-яёәіңғүұқөһі0-9]+", " ", normalized)
    spaced = re.sub(r"\s+", " ", spaced).strip()
    compact = re.sub(r"[^a-zа-яёәіңғүұқөһі0-9]+", "", normalized)
    return spaced, compact


class RulesModerationProvider:
    """Conservative RU/KK/EN phrase baseline; not a semantic or image classifier."""

    async def moderate_text(self, text: str) -> ProviderModerationResult:
        spaced, compact = _normalized_forms(text)
        categories: list[str] = []
        for category, phrases in _RULES.items():
            if any(
                phrase in spaced or re.sub(r"\W+", "", phrase.casefold()) in compact
                for phrase in phrases
            ):
                categories.append(category)
        return ProviderModerationResult(
            flagged=bool(categories),
            categories=tuple(categories),
            provider="rules",
            model="ru-kk-baseline-v1",
        )
