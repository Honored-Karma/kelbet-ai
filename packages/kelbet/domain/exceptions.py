class KelbetError(Exception):
    """Base domain error."""


class InsufficientCreditsError(KelbetError):
    """Raised when wallet balance is too low for a debit."""


class UserNotFoundError(KelbetError):
    """Raised when a user cannot be found."""


class UserBlockedError(KelbetError):
    """Raised when a blocked user attempts a new paid operation."""


class AdminAuthorizationError(KelbetError):
    """Raised when the current session lacks an operator role or permission."""


class AdminActionConflictError(KelbetError):
    """Raised when an operator action ID is replayed with a different payload."""


class ModerationRejectedError(KelbetError):
    """Raised after a durable moderation decision blocks a request."""

    def __init__(self, *, language: str, reason_codes: tuple[str, ...]) -> None:
        super().__init__("Moderation policy rejected the request")
        self.language = language
        self.reason_codes = reason_codes


class ModerationRateLimitError(ModerationRejectedError):
    """Raised when the moderation-layer request budget is exceeded."""


class ConsentRequiredError(KelbetError):
    """Raised when a photo operation lacks the current rights confirmation."""

    def __init__(self, *, language: str, required_version: str) -> None:
        super().__init__("Photo rights consent is required")
        self.language = language
        self.required_version = required_version


class ModerationDecisionNotFoundError(KelbetError):
    """Raised when an operator moderation decision does not exist."""


class GenerationTemplateNotFoundError(KelbetError):
    """Raised when a generation template is unknown, disabled, or unavailable."""


class GenerationTemplateValidationError(KelbetError):
    """Raised when template/model/input compatibility validation fails."""


class WalletNotFoundError(KelbetError):
    """Raised when a wallet cannot be found."""


class ConcurrentModificationError(KelbetError):
    """Raised when optimistic locking fails after retries."""


class ChatProviderError(KelbetError):
    """Raised when the chat provider fails or times out."""


class ChatMessageTooLongError(KelbetError):
    """Raised when user input exceeds the configured length limit."""


class IdempotencyConflictError(KelbetError):
    """Raised when an idempotency key is reused for a different request."""


class ReservationNotFoundError(KelbetError):
    """Raised when a credit reservation cannot be found."""


class InvalidReservationStateError(KelbetError):
    """Raised when a reservation transition is not allowed."""


class AuthError(KelbetError):
    """Base authentication error."""


class InvalidInitDataError(AuthError):
    """Raised when Telegram initData fails validation."""


class ExpiredInitDataError(AuthError):
    """Raised when initData auth_date is outside the allowed window."""


class ReplayInitDataError(AuthError):
    """Raised when the same initData is reused (replay)."""


class InvalidSessionError(AuthError):
    """Raised when the bearer session is missing, expired, or revoked."""


class CatalogModelNotFoundError(KelbetError):
    """Raised when a catalog model slug is unknown or hidden."""


class ModelUnavailableError(KelbetError):
    """Raised when a model is disabled, deprecated, or flag-gated."""


class InvalidQuoteParamsError(KelbetError):
    """Raised when quote params violate catalog capabilities."""


class QuoteNotFoundError(KelbetError):
    """Raised when a quote_id is unknown or expired."""


class UploadValidationError(KelbetError):
    """Raised when upload content-type, size, or magic bytes are invalid."""


class AssetNotFoundError(KelbetError):
    """Raised when an asset is missing or not owned by the caller."""


class StorageError(KelbetError):
    """Raised when object storage operations fail."""


class GenerationNotFoundError(KelbetError):
    """Raised when a generation job is missing or not owned."""


class InvalidGenerationTransitionError(KelbetError):
    """Raised when a generation status transition is illegal."""


class GenerationConflictError(KelbetError):
    """Raised for cancel/create conflicts (e.g. already terminal)."""


class RateLimitExceededError(KelbetError):
    """Raised when an API rate limit is exceeded."""


class ActiveGenerationLimitError(KelbetError):
    """Raised when the user has too many active generations."""


class WebhookVerificationError(KelbetError):
    """Raised when a provider webhook is missing or fails authenticity checks."""


class PaymentUnavailableError(KelbetError):
    """Raised when the payment feature is not safe to expose."""


class PaymentProductNotFoundError(KelbetError):
    """Raised when a payment product is missing or disabled."""


class PaymentOrderNotFoundError(KelbetError):
    """Raised when a payment order cannot be found."""


class PaymentValidationError(KelbetError):
    """Raised when payment amount, currency, owner, or state does not match."""


class PaymentRefundNotFoundError(KelbetError):
    """Raised when a Stars refund request cannot be found."""


class PaymentRefundConflictError(KelbetError):
    """Raised when a Stars refund request conflicts with durable state."""


class PaymentRefundUnavailableError(KelbetError):
    """Raised when the independent Stars refund gate is closed."""
