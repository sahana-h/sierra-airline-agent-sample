from collections.abc import Callable

import pytest
from pydantic import BaseModel, Field, ValidationError

from airline_agent.agent.session import Session
from airline_agent.tools.base import Tool, ToolContext, ToolResult, tool
from airline_agent.tools.registry import Registry

MakeCtx = Callable[..., ToolContext]

USER = "ava_chen_1042"


class SeatInput(BaseModel):
    seat: str = Field(description="Seat code, e.g. '12A'.")


@tool(name="read_seat", description="Read a seat.", input_model=SeatInput, mutates=False)
def read_seat(args: SeatInput, ctx: ToolContext) -> ToolResult:
    return ToolResult.success({"seat": args.seat})


@tool(name="book_seat", description="Book a seat.", input_model=SeatInput, mutates=True)
def book_seat(args: SeatInput, ctx: ToolContext) -> ToolResult:
    return ToolResult.success({"booked": args.seat})


@tool(
    name="public_seat_map",
    description="Show the seat map.",
    input_model=SeatInput,
    mutates=False,
    requires_auth=False,
)
def public_seat_map(args: SeatInput, ctx: ToolContext) -> ToolResult:
    return ToolResult.success({"map": args.seat})


@tool(name="broken_tool", description="Always raises.", input_model=SeatInput, mutates=False)
def broken_tool(args: SeatInput, ctx: ToolContext) -> ToolResult:
    raise RuntimeError("boom")


@pytest.fixture
def registry() -> Registry:
    return Registry([read_seat, book_seat, public_seat_map, broken_tool])


def signed_in_session() -> Session:
    session = Session()
    session.authenticate(USER)
    return session


def test_discover_finds_tools_in_package() -> None:
    names = Registry.discover().names
    assert {"authenticate_user", "get_reservation"} <= set(names)
    assert "read_seat" not in names  # tools defined outside the package are not picked up


def test_schema_is_generated_from_input_model(registry: Registry) -> None:
    schema = next(s for s in registry.schemas() if s["name"] == "read_seat")
    assert schema["description"] == "Read a seat."
    assert schema["input_schema"]["required"] == ["seat"]
    assert schema["input_schema"]["properties"]["seat"]["description"] == "Seat code, e.g. '12A'."


def test_call_runs_tool_with_validated_args(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("read_seat", {"seat": "12A"}, make_ctx(user_id=USER))
    assert result == ToolResult.success({"seat": "12A"})


def test_unknown_tool_returns_error(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("fly_plane", {}, make_ctx(user_id=USER))
    assert not result.ok
    assert result.error is not None
    assert "Unknown tool 'fly_plane'" in result.error
    assert "read_seat" in result.error


def test_invalid_args_return_error(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("read_seat", {"seat": 12}, make_ctx(user_id=USER))
    assert not result.ok
    assert result.error is not None
    assert "seat" in result.error


def test_tool_exception_becomes_error_result(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("broken_tool", {"seat": "1A"}, make_ctx(user_id=USER))
    assert not result.ok
    assert result.error is not None
    assert "internal error" in result.error


def test_tool_requiring_auth_is_refused_when_signed_out(
    registry: Registry, make_ctx: MakeCtx
) -> None:
    result = registry.call("read_seat", {"seat": "12A"}, make_ctx())
    assert not result.ok
    assert result.error is not None
    assert "not authenticated" in result.error


def test_tools_require_auth_by_default() -> None:
    assert read_seat.requires_auth


def test_opted_out_tool_runs_when_signed_out(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("public_seat_map", {"seat": "12A"}, make_ctx())
    assert result == ToolResult.success({"map": "12A"})


def test_signed_out_write_is_not_proposed(registry: Registry, make_ctx: MakeCtx) -> None:
    session = Session()
    registry.call("book_seat", {"seat": "12A"}, make_ctx(session=session))
    session.begin_user_turn()
    session.authenticate(USER)
    assert not session.consume_confirmation("book_seat", {"seat": "12A"})


def test_ctx_user_id_returns_signed_in_user(make_ctx: MakeCtx) -> None:
    assert make_ctx(user_id=USER).user_id == USER


def test_ctx_user_id_fails_loudly_when_signed_out(make_ctx: MakeCtx) -> None:
    with pytest.raises(RuntimeError, match="requires_auth"):
        _ = make_ctx().user_id


def test_mutating_tool_is_proposed_not_run(registry: Registry, make_ctx: MakeCtx) -> None:
    session = signed_in_session()
    result = registry.call("book_seat", {"seat": "12A"}, make_ctx(session=session))
    assert not result.ok
    assert result.error is not None
    assert "Nothing has been changed" in result.error
    session.begin_user_turn()
    assert session.consume_confirmation("book_seat", {"seat": "12A"})


def test_mutating_tool_refused_in_same_turn(registry: Registry, make_ctx: MakeCtx) -> None:
    ctx = make_ctx(session=signed_in_session())
    registry.call("book_seat", {"seat": "12A"}, ctx)
    assert not registry.call("book_seat", {"seat": "12A"}, ctx).ok


def test_mutating_tool_refused_when_args_change(registry: Registry, make_ctx: MakeCtx) -> None:
    session = signed_in_session()
    ctx = make_ctx(session=session)
    registry.call("book_seat", {"seat": "14C"}, ctx)
    session.begin_user_turn()
    assert not registry.call("book_seat", {"seat": "12A"}, ctx).ok


def test_mutating_tool_runs_after_user_turn(registry: Registry, make_ctx: MakeCtx) -> None:
    session = signed_in_session()
    ctx = make_ctx(session=session)
    registry.call("book_seat", {"seat": "12A"}, ctx)
    session.begin_user_turn()
    result = registry.call("book_seat", {"seat": "12A"}, ctx)
    assert result == ToolResult.success({"booked": "12A"})


def test_invalid_args_are_not_proposed(registry: Registry, make_ctx: MakeCtx) -> None:
    session = signed_in_session()
    registry.call("book_seat", {"seat": 12}, make_ctx(session=session))
    session.begin_user_turn()
    assert not session.consume_confirmation("book_seat", {"seat": 12})


def test_duplicate_tool_names_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        Registry([read_seat, read_seat])


def test_tool_name_must_be_snake_case() -> None:
    with pytest.raises(ValueError, match="snake_case"):
        Tool(name="ReadSeat", description="", input_model=SeatInput, mutates=False, fn=read_seat)


def test_tool_result_requires_error_exactly_when_failed() -> None:
    with pytest.raises(ValidationError):
        ToolResult(ok=False)
    with pytest.raises(ValidationError):
        ToolResult(ok=True, error="nope")
