from airline_agent.policy.rules import MAX_FAILED_AUTH_ATTEMPTS, auth_locked


def test_auth_not_locked_below_limit() -> None:
    assert not auth_locked(0)
    assert not auth_locked(MAX_FAILED_AUTH_ATTEMPTS - 1)


def test_auth_locked_at_limit() -> None:
    assert auth_locked(MAX_FAILED_AUTH_ATTEMPTS)
    assert auth_locked(MAX_FAILED_AUTH_ATTEMPTS + 1)
