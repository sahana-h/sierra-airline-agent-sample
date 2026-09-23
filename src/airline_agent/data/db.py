"""In-memory database. The only module that holds or hands out airline data.

Getters return deep copies, so changing a returned model never changes the
database by accident. Writes will go through explicit methods on `Database`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import BaseModel

from airline_agent.data.models import Flight, Reservation, User

DEFAULT_SEED_PATH = Path(__file__).with_name("seed.json")


class DatabaseState(BaseModel):
    """The full contents of the database, as stored in JSON and compared in evals."""

    users: list[User]
    reservations: list[Reservation]
    flights: list[Flight]


class Database:
    """Indexed, in-memory store of users, reservations and flights."""

    def __init__(self, state: DatabaseState) -> None:
        self._users = {user.user_id: user for user in state.users}
        self._reservations = {res.reservation_id: res for res in state.reservations}
        self._flights = {(flight.flight_number, flight.date): flight for flight in state.flights}

    @classmethod
    def load(cls, path: Path = DEFAULT_SEED_PATH) -> Database:
        """Load a database from a JSON file (the bundled seed by default)."""
        return cls(DatabaseState.model_validate_json(path.read_text()))

    def get_user(self, user_id: str) -> User | None:
        user = self._users.get(user_id)
        return user.model_copy(deep=True) if user else None

    def get_reservation(self, reservation_id: str) -> Reservation | None:
        reservation = self._reservations.get(reservation_id)
        return reservation.model_copy(deep=True) if reservation else None

    def get_flight(self, flight_number: str, flight_date: date) -> Flight | None:
        flight = self._flights.get((flight_number, flight_date))
        return flight.model_copy(deep=True) if flight else None

    def snapshot(self) -> DatabaseState:
        """Return an independent copy of the current state."""
        state = DatabaseState(
            users=list(self._users.values()),
            reservations=list(self._reservations.values()),
            flights=list(self._flights.values()),
        )
        return state.model_copy(deep=True)

    def save(self, path: Path) -> None:
        """Write the current state to `path`. Refuses to overwrite the bundled seed."""
        if path.resolve() == DEFAULT_SEED_PATH.resolve():
            raise ValueError("Refusing to overwrite the seed data; save to another path.")
        path.write_text(self.snapshot().model_dump_json(indent=2))
