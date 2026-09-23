"""Tools for looking up and changing reservations."""

from pydantic import BaseModel, Field, field_validator

from airline_agent.tools.base import ToolContext, ToolResult, tool


class GetReservationInput(BaseModel):
    reservation_id: str = Field(
        description="The six-character reservation code, for example 'ZQ4K2P'."
    )

    @field_validator("reservation_id")
    @classmethod
    def _normalize(cls, value: str) -> str:
        # Users often read codes out in lowercase or with stray spaces.
        return value.strip().upper()


@tool(
    name="get_reservation",
    description=(
        "Look up one of the authenticated user's reservations by its code: flights, cabin, "
        "passengers, checked bags, travel insurance, payments and status. Use this before "
        "discussing or changing a booking. Do not use it to search for flights or to look up "
        "reservations that belong to someone else."
    ),
    input_model=GetReservationInput,
    mutates=False,
)
def get_reservation(args: GetReservationInput, ctx: ToolContext) -> ToolResult:
    """Return the reservation if it belongs to the authenticated user."""
    reservation = ctx.db.get_reservation(args.reservation_id)
    # Same message for "missing" and "someone else's" so we don't reveal which codes exist.
    if reservation is None or reservation.user_id != ctx.user_id:
        return ToolResult.failure(
            f"No reservation {args.reservation_id} was found for this user. "
            "Ask the user to double-check the code."
        )

    return ToolResult.success(reservation.model_dump(mode="json"))
