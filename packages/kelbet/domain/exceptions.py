class KelbetError(Exception):
    """Base domain error."""


class InsufficientCreditsError(KelbetError):
    """Raised when wallet balance is too low for a debit."""


class UserNotFoundError(KelbetError):
    """Raised when a user cannot be found."""


class WalletNotFoundError(KelbetError):
    """Raised when a wallet cannot be found."""


class ConcurrentModificationError(KelbetError):
    """Raised when optimistic locking fails after retries."""
