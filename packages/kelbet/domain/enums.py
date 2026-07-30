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
    AI_CHAT = "ai_chat"
    PROMPT_ASSISTANT = "prompt_assistant"
    GENERATION_CAPTURE = "generation_capture"
    GENERATION_REFUND = "generation_refund"
    ADMIN_ADJUST = "admin_adjust"
    PLAN_GRANT = "plan_grant"
    PAYMENT_PURCHASE = "payment_purchase"
    PAYMENT_REFUND = "payment_refund"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    DISPUTED = "disputed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentReceiptStatus(StrEnum):
    PROCESSED = "processed"
    REJECTED = "rejected"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class ReservationStatus(StrEnum):
    HELD = "held"
    CAPTURED = "captured"
    RELEASED = "released"
    EXPIRED = "expired"


class Modality(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    IMAGE_EDIT = "image_edit"
    VIDEO = "video"
    UPSCALE = "upscale"


class AssetRole(StrEnum):
    INPUT = "input"
    MASK = "mask"
    OUTPUT = "output"
    THUMB = "thumb"


class AssetStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    REJECTED = "rejected"
    DELETED = "deleted"


class RetentionClass(StrEnum):
    TEMP_INPUT = "temp_input"
    PERMANENT_OUTPUT = "permanent_output"


class GenerationStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    SUBMITTING = "submitting"
    RUNNING = "running"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    DEAD_LETTER = "dead_letter"


class AttemptStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
