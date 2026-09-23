"""Pydantic models for the airline's mock data: users, reservations and flights.

Money is stored as whole US dollars. Datetimes are timezone-aware UTC.
"""

from datetime import date
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base model that rejects unknown fields, so typos in seed data fail loudly."""

    model_config = ConfigDict(extra="forbid")


class Cabin(StrEnum):
    BASIC_ECONOMY = "basic_economy"
    ECONOMY = "economy"
    BUSINESS = "business"


class MembershipTier(StrEnum):
    REGULAR = "regular"
    SILVER = "silver"
    GOLD = "gold"


class PaymentKind(StrEnum):
    CREDIT_CARD = "credit_card"
    GIFT_CARD = "gift_card"
    TRAVEL_CERTIFICATE = "travel_certificate"


class FlightStatus(StrEnum):
    SCHEDULED = "scheduled"
    LANDED = "landed"
    CANCELLED = "cancelled"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class PaymentMethod(StrictModel):
    id: str
    kind: PaymentKind
    description: str = Field(description="Human-readable label, e.g. 'Visa ending 4242'.")
    balance: int | None = Field(
        default=None, description="Remaining balance for gift cards and certificates."
    )


class User(StrictModel):
    user_id: str
    first_name: str
    last_name: str
    email: str
    membership: MembershipTier
    payment_methods: list[PaymentMethod]


class Flight(StrictModel):
    """One scheduled operation of a flight number on a specific date."""

    flight_number: str
    date: date
    origin: str
    destination: str
    departure: AwareDatetime
    arrival: AwareDatetime
    status: FlightStatus
    prices: dict[Cabin, int] = Field(description="Price per passenger by cabin.")
    seats_available: dict[Cabin, int]


class Passenger(StrictModel):
    first_name: str
    last_name: str
    date_of_birth: date


class FlightSegment(StrictModel):
    """A flight on a reservation, with the per-passenger price that was paid."""

    flight_number: str
    date: date
    price: int


class Payment(StrictModel):
    payment_method_id: str
    amount: int


class Reservation(StrictModel):
    reservation_id: str
    user_id: str
    origin: str
    destination: str
    cabin: Cabin
    flights: list[FlightSegment]
    passengers: list[Passenger]
    checked_bags: int
    travel_insurance: bool
    status: ReservationStatus
    created_at: AwareDatetime
    payments: list[Payment]
