from airline_agent.agent.session import Session

ARGS = {"reservation_id": "ZQ4K2P"}


def proposed(tool_name: str = "cancel_reservation") -> Session:
    session = Session()
    session.begin_user_turn()
    session.propose(tool_name, ARGS)
    return session


def test_starts_unauthenticated() -> None:
    session = Session()
    assert session.user_id is None
    assert session.failed_auth_attempts == 0


def test_authenticate_and_failed_attempts() -> None:
    session = Session()
    session.record_failed_auth()
    session.authenticate("ava_chen_1042")
    assert session.user_id == "ava_chen_1042"
    assert session.failed_auth_attempts == 1


def test_confirmation_not_available_in_same_turn() -> None:
    assert not proposed().consume_confirmation("cancel_reservation", ARGS)


def test_confirmation_available_in_next_turn() -> None:
    session = proposed()
    session.begin_user_turn()
    assert session.consume_confirmation("cancel_reservation", ARGS)


def test_confirmation_can_be_used_once() -> None:
    session = proposed()
    session.begin_user_turn()
    assert session.consume_confirmation("cancel_reservation", ARGS)
    assert not session.consume_confirmation("cancel_reservation", ARGS)


def test_confirmation_requires_identical_args() -> None:
    session = proposed()
    session.begin_user_turn()
    assert not session.consume_confirmation("cancel_reservation", {"reservation_id": "M8TRW3"})


def test_confirmation_requires_same_tool() -> None:
    session = proposed()
    session.begin_user_turn()
    assert not session.consume_confirmation("update_reservation", ARGS)


def test_arg_order_does_not_matter() -> None:
    session = Session()
    session.propose("book", {"a": 1, "b": 2})
    session.begin_user_turn()
    assert session.consume_confirmation("book", {"b": 2, "a": 1})


def test_proposal_expires_after_one_user_turn() -> None:
    session = proposed()
    session.begin_user_turn()  # user changed the subject instead of confirming
    session.begin_user_turn()
    assert not session.consume_confirmation("cancel_reservation", ARGS)


def test_several_proposals_in_one_turn_can_all_be_confirmed() -> None:
    session = proposed("cancel_reservation")
    session.propose("add_checked_bag", ARGS)
    session.begin_user_turn()
    assert session.consume_confirmation("cancel_reservation", ARGS)
    assert session.consume_confirmation("add_checked_bag", ARGS)
