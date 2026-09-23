from collections.abc import Callable

from airline_agent.tools.base import ToolContext
from airline_agent.tools.registry import Registry
from airline_agent.tools.reservations import GetReservationInput, get_reservation

MakeCtx = Callable[..., ToolContext]


def test_returns_reservation_for_owner(make_ctx: MakeCtx) -> None:
    result = get_reservation(
        GetReservationInput(reservation_id="ZQ4K2P"), make_ctx(user_id="ava_chen_1042")
    )
    assert result.ok
    assert result.data is not None
    assert result.data["reservation_id"] == "ZQ4K2P"
    assert result.data["cabin"] == "business"
    assert [f["flight_number"] for f in result.data["flights"]] == ["FA101", "FA102"]


def test_normalizes_reservation_code(make_ctx: MakeCtx) -> None:
    result = get_reservation(
        GetReservationInput(reservation_id="  zq4k2p "), make_ctx(user_id="ava_chen_1042")
    )
    assert result.ok


def test_refuses_when_not_authenticated(make_ctx: MakeCtx) -> None:
    result = Registry.discover().call("get_reservation", {"reservation_id": "ZQ4K2P"}, make_ctx())
    assert not result.ok
    assert result.error is not None
    assert "not authenticated" in result.error


def test_unknown_reservation(make_ctx: MakeCtx) -> None:
    result = get_reservation(
        GetReservationInput(reservation_id="NOPE00"), make_ctx(user_id="ava_chen_1042")
    )
    assert not result.ok
    assert result.error is not None
    assert "No reservation NOPE00" in result.error


def test_other_users_reservation_looks_not_found(make_ctx: MakeCtx) -> None:
    result = get_reservation(
        GetReservationInput(reservation_id="M8TRW3"), make_ctx(user_id="ava_chen_1042")
    )
    assert not result.ok
    assert result.error is not None
    assert "No reservation M8TRW3" in result.error


def test_end_to_end_through_registry(make_ctx: MakeCtx) -> None:
    result = Registry.discover().call(
        "get_reservation", {"reservation_id": "P5XJ9D"}, make_ctx(user_id="priya_nair_3318")
    )
    assert result.ok
    assert result.data is not None
    assert len(result.data["passengers"]) == 2
