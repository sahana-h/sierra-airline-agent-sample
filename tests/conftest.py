"""Shared fixtures: a fresh seed database, a fake session and a fixed clock."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from airline_agent.data.db import Database
from airline_agent.tools.base import ToolContext

# A fixed "now" so time-based policy is deterministic. Matches the seed data.
FIXED_NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)

MakeCtx = Callable[..., ToolContext]


@dataclass
class FakeSession:
    """A session with a fixed user and a fixed list of confirmed (tool, args) calls."""

    user_id: str | None = None
    confirmed: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def is_confirmed(self, tool_name: str, args: Mapping[str, Any]) -> bool:
        return (tool_name, dict(args)) in self.confirmed


@pytest.fixture
def db() -> Database:
    return Database.load()


@pytest.fixture
def make_ctx(db: Database) -> MakeCtx:
    """Build a ToolContext for the given user and confirmations."""

    def build(
        user_id: str | None = None,
        confirmed: Sequence[tuple[str, dict[str, Any]]] = (),
    ) -> ToolContext:
        session = FakeSession(user_id=user_id, confirmed=list(confirmed))
        return ToolContext(db=db, session=session, now=FIXED_NOW)

    return build
