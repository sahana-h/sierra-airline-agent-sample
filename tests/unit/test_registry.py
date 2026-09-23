from collections.abc import Callable

import pytest
from pydantic import BaseModel, Field, ValidationError

from airline_agent.tools.base import Tool, ToolContext, ToolResult, tool
from airline_agent.tools.registry import Registry

MakeCtx = Callable[..., ToolContext]


class SeatInput(BaseModel):
    seat: str = Field(description="Seat code, e.g. '12A'.")


@tool(name="read_seat", description="Read a seat.", input_model=SeatInput, mutates=False)
def read_seat(args: SeatInput, ctx: ToolContext) -> ToolResult:
    return ToolResult.success({"seat": args.seat})


@tool(name="book_seat", description="Book a seat.", input_model=SeatInput, mutates=True)
def book_seat(args: SeatInput, ctx: ToolContext) -> ToolResult:
    return ToolResult.success({"booked": args.seat})


@tool(name="broken_tool", description="Always raises.", input_model=SeatInput, mutates=False)
def broken_tool(args: SeatInput, ctx: ToolContext) -> ToolResult:
    raise RuntimeError("boom")


@pytest.fixture
def registry() -> Registry:
    return Registry([read_seat, book_seat, broken_tool])


def test_discover_finds_tools_in_package() -> None:
    names = Registry.discover().names
    assert "get_reservation" in names
    assert "read_seat" not in names  # tools defined outside the package are not picked up


def test_schema_is_generated_from_input_model(registry: Registry) -> None:
    schema = next(s for s in registry.schemas() if s["name"] == "read_seat")
    assert schema["description"] == "Read a seat."
    assert schema["input_schema"]["required"] == ["seat"]
    assert schema["input_schema"]["properties"]["seat"]["description"] == "Seat code, e.g. '12A'."


def test_call_runs_tool_with_validated_args(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("read_seat", {"seat": "12A"}, make_ctx())
    assert result == ToolResult.success({"seat": "12A"})


def test_unknown_tool_returns_error(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("fly_plane", {}, make_ctx())
    assert not result.ok
    assert result.error is not None
    assert "Unknown tool 'fly_plane'" in result.error
    assert "read_seat" in result.error


def test_invalid_args_return_error(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("read_seat", {"seat": 12}, make_ctx())
    assert not result.ok
    assert result.error is not None
    assert "seat" in result.error


def test_tool_exception_becomes_error_result(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("broken_tool", {"seat": "1A"}, make_ctx())
    assert not result.ok
    assert result.error is not None
    assert "internal error" in result.error


def test_mutating_tool_refused_without_confirmation(registry: Registry, make_ctx: MakeCtx) -> None:
    result = registry.call("book_seat", {"seat": "12A"}, make_ctx())
    assert not result.ok
    assert result.error is not None
    assert "confirmation" in result.error


def test_mutating_tool_refused_when_confirmed_args_differ(
    registry: Registry, make_ctx: MakeCtx
) -> None:
    ctx = make_ctx(confirmed=[("book_seat", {"seat": "14C"})])
    assert not registry.call("book_seat", {"seat": "12A"}, ctx).ok


def test_mutating_tool_runs_with_matching_confirmation(
    registry: Registry, make_ctx: MakeCtx
) -> None:
    ctx = make_ctx(confirmed=[("book_seat", {"seat": "12A"})])
    assert registry.call("book_seat", {"seat": "12A"}, ctx) == ToolResult.success({"booked": "12A"})


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
