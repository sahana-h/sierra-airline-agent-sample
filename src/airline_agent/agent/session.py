"""Conversation state: who the user is, and which writes they have confirmed.

Confirmation is two-step. When the model calls a write tool, the registry
records it with `propose`. That call can run only in the user's next turn,
only with identical arguments, and only once. So the model cannot propose and
act in the same turn, change the details after the user agreed, or reuse an
old approval. A proposal the user doesn't take up in their next turn expires.
"""

import json
from collections.abc import Mapping
from typing import Any


class Session:
    """State for one conversation with one customer."""

    def __init__(self) -> None:
        self._user_id: str | None = None
        self._failed_auth_attempts = 0
        self._turn = 0
        # (tool name, canonical args) -> the user turn in which it was proposed
        self._pending: dict[tuple[str, str], int] = {}

    @property
    def user_id(self) -> str | None:
        return self._user_id

    @property
    def failed_auth_attempts(self) -> int:
        return self._failed_auth_attempts

    def authenticate(self, user_id: str) -> None:
        self._user_id = user_id

    def record_failed_auth(self) -> None:
        self._failed_auth_attempts += 1

    def begin_user_turn(self) -> None:
        """Call when a new user message arrives. Expires proposals older than one turn."""
        self._turn += 1
        self._pending = {key: turn for key, turn in self._pending.items() if turn == self._turn - 1}

    def propose(self, tool_name: str, args: Mapping[str, Any]) -> None:
        self._pending[_key(tool_name, args)] = self._turn

    def consume_confirmation(self, tool_name: str, args: Mapping[str, Any]) -> bool:
        key = _key(tool_name, args)
        # A proposal from this same turn doesn't count: the user hasn't replied yet.
        if self._pending.get(key) != self._turn - 1:
            return False
        del self._pending[key]
        return True


def _key(tool_name: str, args: Mapping[str, Any]) -> tuple[str, str]:
    return tool_name, json.dumps(args, sort_keys=True)
