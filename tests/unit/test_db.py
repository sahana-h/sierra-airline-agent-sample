from datetime import date
from pathlib import Path

import pytest

from airline_agent.data.db import DEFAULT_SEED_PATH, Database
from airline_agent.data.models import Cabin, FlightStatus, ReservationStatus


def test_seed_loads_all_records(db: Database) -> None:
    state = db.snapshot()
    assert len(state.users) == 3
    assert len(state.reservations) == 5
    assert len(state.flights) == 6


def test_seed_references_are_consistent(db: Database) -> None:
    """Every reservation points at a real user, real flights and the user's own cards."""
    for reservation in db.snapshot().reservations:
        user = db.get_user(reservation.user_id)
        assert user is not None
        own_methods = {method.id for method in user.payment_methods}
        for payment in reservation.payments:
            assert payment.payment_method_id in own_methods
        for segment in reservation.flights:
            assert db.get_flight(segment.flight_number, segment.date) is not None


def test_lookups(db: Database) -> None:
    reservation = db.get_reservation("M8TRW3")
    assert reservation is not None
    assert reservation.cabin is Cabin.BASIC_ECONOMY
    assert reservation.status is ReservationStatus.ACTIVE

    flight = db.get_flight("FA305", date(2026, 9, 20))
    assert flight is not None
    assert flight.status is FlightStatus.LANDED


def test_missing_records_return_none(db: Database) -> None:
    assert db.get_user("nobody") is None
    assert db.get_reservation("NOPE00") is None
    assert db.get_flight("FA101", date(2030, 1, 1)) is None


def test_returned_models_are_copies(db: Database) -> None:
    reservation = db.get_reservation("ZQ4K2P")
    assert reservation is not None
    reservation.checked_bags = 99
    unchanged = db.get_reservation("ZQ4K2P")
    assert unchanged is not None
    assert unchanged.checked_bags == 2


def test_snapshot_is_independent(db: Database) -> None:
    before = db.snapshot()
    before.users[0].first_name = "Changed"
    assert db.snapshot() != before


def test_save_round_trips(db: Database, tmp_path: Path) -> None:
    path = tmp_path / "state.db.json"
    db.save(path)
    assert Database.load(path).snapshot() == db.snapshot()


def test_save_refuses_to_overwrite_seed(db: Database) -> None:
    with pytest.raises(ValueError, match="seed"):
        db.save(DEFAULT_SEED_PATH)
