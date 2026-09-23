"""Tools for verifying the customer's identity."""

from typing import Self

from pydantic import BaseModel, Field, model_validator

from airline_agent.data.models import User
from airline_agent.policy.rules import auth_locked
from airline_agent.tools.base import ToolContext, ToolResult, tool

_HANDOFF = (
    "Identity verification is locked after too many failed attempts. Do not try again; "
    "tell the user and offer to transfer them to a human agent."
)


class AuthenticateUserInput(BaseModel):
    first_name: str = Field(description="The user's first name, as they gave it.")
    last_name: str = Field(description="The user's last name, as they gave it.")
    user_id: str | None = Field(
        default=None, description="The user's ID. Give this or reservation_id, not both."
    )
    reservation_id: str | None = Field(
        default=None,
        description="A six-character code of one of the user's reservations. "
        "Give this or user_id, not both.",
    )

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> Self:
        if (self.user_id is None) == (self.reservation_id is None):
            raise ValueError("Provide exactly one of user_id or reservation_id.")
        return self


@tool(
    name="authenticate_user",
    description=(
        "Verify the user's identity with their first and last name plus either their user ID "
        "or one of their reservation codes. Call this before any other tool. Ask the user for "
        "these details; never guess them."
    ),
    input_model=AuthenticateUserInput,
    mutates=False,  # changes the session, not the database
)
def authenticate_user(args: AuthenticateUserInput, ctx: ToolContext) -> ToolResult:
    """Sign the user in if their name matches the account found by ID or reservation."""
    session = ctx.session
    if auth_locked(session.failed_auth_attempts):
        return ToolResult.failure(_HANDOFF)

    user = _find_user(args, ctx)
    if user is None or not _names_match(args, user):
        session.record_failed_auth()
        if auth_locked(session.failed_auth_attempts):
            return ToolResult.failure(_HANDOFF)
        # Deliberately vague, so the tool can't be used to learn which details are right.
        return ToolResult.failure(
            "Could not verify the user's identity with those details. "
            "Ask them to double-check and try again."
        )

    if session.user_id is not None and session.user_id != user.user_id:
        return ToolResult.failure(
            "A different user is already verified in this conversation. One conversation "
            "serves one customer; offer to transfer them to a human agent."
        )

    session.authenticate(user.user_id)
    return ToolResult.success(
        {
            "user_id": user.user_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "membership": user.membership.value,
        }
    )


def _find_user(args: AuthenticateUserInput, ctx: ToolContext) -> User | None:
    if args.user_id is not None:
        return ctx.db.get_user(args.user_id.strip())
    assert args.reservation_id is not None  # guaranteed by the input model
    reservation = ctx.db.get_reservation(args.reservation_id.strip().upper())
    return ctx.db.get_user(reservation.user_id) if reservation else None


def _names_match(args: AuthenticateUserInput, user: User) -> bool:
    return (
        args.first_name.strip().casefold() == user.first_name.casefold()
        and args.last_name.strip().casefold() == user.last_name.casefold()
    )
