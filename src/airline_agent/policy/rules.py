"""Pure policy functions (can_cancel, refund_amount, change_fee, ...).

No database access and no I/O: data in, decision out.
"""

MAX_FAILED_AUTH_ATTEMPTS = 3


def auth_locked(failed_attempts: int) -> bool:
    """Whether identity verification is locked and the user must go to a human agent."""
    return failed_attempts >= MAX_FAILED_AUTH_ATTEMPTS
