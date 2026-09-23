from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from airline_agent.agent.session import Session
from airline_agent.policy.rules import MAX_FAILED_AUTH_ATTEMPTS
from airline_agent.tools.auth import AuthenticateUserInput, authenticate_user
from airline_agent.tools.base import ToolContext, ToolResult
from airline_agent.tools.registry import Registry

MakeCtx = Callable[..., ToolContext]


def attempt(ctx: ToolContext, **kwargs: Any) -> ToolResult:
    return authenticate_user(AuthenticateUserInput(**kwargs), ctx)


def test_by_user_id(make_ctx: MakeCtx) -> None:
    ctx = make_ctx()
    result = attempt(ctx, first_name="Ava", last_name="Chen", user_id="ava_chen_1042")
    assert result.ok
    assert result.data == {
        "user_id": "ava_chen_1042",
        "first_name": "Ava",
        "last_name": "Chen",
        "membership": "gold",
    }
    assert ctx.session.user_id == "ava_chen_1042"


def test_by_reservation_code_ignoring_case_and_spaces(make_ctx: MakeCtx) -> None:
    ctx = make_ctx()
    result = attempt(ctx, first_name=" marcus", last_name="REED ", reservation_id="m8trw3")
    assert result.ok
    assert ctx.session.user_id == "marcus_reed_2210"


@pytest.mark.parametrize(
    "details",
    [
        {"first_name": "Eve", "last_name": "Chen", "user_id": "ava_chen_1042"},
        {"first_name": "Ava", "last_name": "Chen", "user_id": "nobody_0000"},
        {"first_name": "Ava", "last_name": "Chen", "reservation_id": "NOPE00"},
        # Real code, but it belongs to Marcus.
        {"first_name": "Ava", "last_name": "Chen", "reservation_id": "M8TRW3"},
    ],
)
def test_mismatch_fails_and_counts(make_ctx: MakeCtx, details: dict[str, str]) -> None:
    ctx = make_ctx()
    result = attempt(ctx, **details)
    assert not result.ok
    assert result.error is not None
    assert "Could not verify" in result.error
    assert ctx.session.user_id is None
    assert ctx.session.failed_auth_attempts == 1


def test_locks_after_max_failures_even_with_correct_details(make_ctx: MakeCtx) -> None:
    ctx = make_ctx()
    for _ in range(MAX_FAILED_AUTH_ATTEMPTS - 1):
        attempt(ctx, first_name="Eve", last_name="Chen", user_id="ava_chen_1042")

    last = attempt(ctx, first_name="Eve", last_name="Chen", user_id="ava_chen_1042")
    assert last.error is not None
    assert "human agent" in last.error

    correct = attempt(ctx, first_name="Ava", last_name="Chen", user_id="ava_chen_1042")
    assert correct.error is not None
    assert "human agent" in correct.error
    assert ctx.session.user_id is None


def test_cannot_switch_to_another_user(make_ctx: MakeCtx) -> None:
    ctx = make_ctx(user_id="ava_chen_1042")
    result = attempt(ctx, first_name="Marcus", last_name="Reed", user_id="marcus_reed_2210")
    assert not result.ok
    assert ctx.session.user_id == "ava_chen_1042"


def test_same_user_can_verify_again(make_ctx: MakeCtx) -> None:
    ctx = make_ctx(user_id="ava_chen_1042")
    assert attempt(ctx, first_name="Ava", last_name="Chen", reservation_id="ZQ4K2P").ok


@pytest.mark.parametrize(
    "identifiers",
    [{}, {"user_id": "ava_chen_1042", "reservation_id": "ZQ4K2P"}],
)
def test_requires_exactly_one_identifier(identifiers: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        AuthenticateUserInput(first_name="Ava", last_name="Chen", **identifiers)


def test_session_is_shared_with_registry(make_ctx: MakeCtx) -> None:
    """Signing in through the tool lets later tools see the user."""
    session = Session()
    ctx = make_ctx(session=session)
    registry = Registry.discover()
    registry.call(
        "authenticate_user",
        {"first_name": "Priya", "last_name": "Nair", "reservation_id": "P5XJ9D"},
        ctx,
    )
    assert registry.call("get_reservation", {"reservation_id": "P5XJ9D"}, ctx).ok
