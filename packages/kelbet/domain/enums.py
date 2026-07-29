from enum import StrEnum


class Language(StrEnum):
    RU = "ru"
    KK = "kk"


class Plan(StrEnum):
    FREE = "free"


class TxType(StrEnum):
    CREDIT = "credit"
    DEBIT = "debit"


class TxReason(StrEnum):
    WELCOME_BONUS = "welcome_bonus"
