from enum import StrEnum


class Language(StrEnum):
    RU = "ru"
    KK = "kk"


class Plan(StrEnum):
    FREE = "free"
    START = "start"
    PRO = "pro"
    STUDIO = "studio"
    BUSINESS = "business"


class SubscriptionStatus(StrEnum):
    """Lifecycle of one Telegram Stars subscription.

    Telegram owns the billing clock, so these states record what Telegram has told us
    rather than a schedule of our own. PENDING: an invoice link was issued, no charge has
    arrived. CANCELLED: renewal is switched off but the paid period is still running —
    access continues to `current_period_end`, which is what Telegram guarantees. Cancelling
    is therefore never an immediate revocation. PAYMENT_FAILED: Telegram could not collect
    a renewal; the period still ends when it was always going to end, so this is a signal
    to the user, not a cut-off.
    """

    PENDING = "pending"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    PAYMENT_FAILED = "payment_failed"
    EXPIRED = "expired"


class OperatorRole(StrEnum):
    SUPPORT = "support"
    ADMIN = "admin"


class ModerationMode(StrEnum):
    OFF = "off"
    REPORT = "report"
    BLOCK = "block"


class ModerationOutcome(StrEnum):
    ALLOW = "allow"
    REPORT = "report"
    BLOCK = "block"


class ModerationReviewStatus(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"


class TemplateKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


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
    REFERRAL_REWARD = "referral_reward"


class ReferralRewardStatus(StrEnum):
    PENDING = "pending"
    ELIGIBLE = "eligible"
    CREDITED = "credited"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"


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


class PaymentRefundStatus(StrEnum):
    REQUESTED = "requested"
    PROCESSING = "processing"
    REFUNDED = "refunded"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class PaymentReconciliationIssueStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
    NEEDS_REVIEW = "needs_review"


class StarTransactionDirection(StrEnum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


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
