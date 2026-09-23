"""The tool contract: the `@tool` decorator, `Tool`, `ToolResult` and `ToolContext`."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, Protocol, Self, TypeVar

from pydantic import BaseModel, model_validator

from airline_agent.data.db import Database

InputT = TypeVar("InputT", bound=BaseModel)

_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class Session(Protocol):
    """What tools and the registry need from the conversation session."""

    @property
    def user_id(self) -> str | None:
        """The authenticated user's ID, or None before authentication."""
        ...

    def is_confirmed(self, tool_name: str, args: Mapping[str, Any]) -> bool:
        """Whether the user explicitly approved this exact call (validated, JSON-mode args)."""
        ...


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool may use besides its arguments."""

    db: Database
    session: Session
    now: datetime  # injected so time-based policy is deterministic in tests


class ToolResult(BaseModel):
    """The outcome of a tool call, sent back to the model as JSON."""

    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _error_iff_failed(self) -> Self:
        if self.ok == (self.error is not None):
            raise ValueError("A ToolResult has an error exactly when ok is False.")
        return self

    @classmethod
    def success(cls, data: dict[str, Any]) -> ToolResult:
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, error: str) -> ToolResult:
        """A failure with a message the model can act on and explain to the user."""
        return cls(ok=False, error=error)

    def to_content(self) -> str:
        return self.model_dump_json(exclude_none=True)


@dataclass(frozen=True)
class Tool(Generic[InputT]):
    """A callable the model can use, plus the metadata needed to describe it."""

    name: str
    description: str
    input_model: type[InputT]
    mutates: bool
    fn: Callable[[InputT, ToolContext], ToolResult]

    def __post_init__(self) -> None:
        if not _TOOL_NAME.match(self.name):
            raise ValueError(f"Tool name {self.name!r} must be snake_case, at most 64 chars.")

    def __call__(self, args: InputT, ctx: ToolContext) -> ToolResult:
        return self.fn(args, ctx)

    def schema(self) -> dict[str, Any]:
        """The tool definition in the shape the model API expects."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


def tool(
    *,
    name: str,
    description: str,
    input_model: type[InputT],
    mutates: bool,
) -> Callable[[Callable[[InputT, ToolContext], ToolResult]], Tool[InputT]]:
    """Turn a function into a `Tool` that the registry discovers automatically.

    `mutates` has no default on purpose: every tool author must decide whether
    the tool needs user confirmation.
    """

    def decorator(fn: Callable[[InputT, ToolContext], ToolResult]) -> Tool[InputT]:
        return Tool(
            name=name,
            description=description,
            input_model=input_model,
            mutates=mutates,
            fn=fn,
        )

    return decorator
