"""Shared fixtures: a fresh seed database, a session and a fixed clock."""

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from airline_agent.agent.session import Session
from airline_agent.data.db import Database
from airline_agent.tools.base import ToolContext

# A fixed "now" so time-based policy is deterministic. Matches the seed data.
FIXED_NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)

MakeCtx = Callable[..., ToolContext]


@pytest.fixture
def db() -> Database:
    return Database.load()


@pytest.fixture
def make_ctx(db: Database) -> MakeCtx:
    """Build a ToolContext, optionally signed in as `user_id` or around a given session."""

    def build(user_id: str | None = None, session: Session | None = None) -> ToolContext:
        session = session or Session()
        if user_id is not None:
            session.authenticate(user_id)
        return ToolContext(db=db, session=session, now=FIXED_NOW)

    return build
