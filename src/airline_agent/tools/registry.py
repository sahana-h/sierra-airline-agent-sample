"""Discovers tools, publishes their schemas and dispatches calls by name.

This is the only interface the agent loop uses to reach tools. It guarantees
that a call never raises: every problem comes back as a failed `ToolResult`.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import ValidationError

import airline_agent.tools as tools_package
from airline_agent.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

# Modules in the tools package that define the machinery rather than tools.
_INFRASTRUCTURE_MODULES = {"base", "registry"}


class Registry:
    """A fixed set of tools, looked up by name."""

    def __init__(self, tools: Iterable[Tool[Any]]) -> None:
        self._tools: dict[str, Tool[Any]] = {}
        for t in tools:
            if t.name in self._tools:
                raise ValueError(f"Duplicate tool name: {t.name!r}")
            self._tools[t.name] = t

    @classmethod
    def discover(cls) -> Registry:
        """Build a registry from every `@tool` defined in the tools package."""
        found: list[Tool[Any]] = []
        for module_info in pkgutil.iter_modules(tools_package.__path__):
            if module_info.name in _INFRASTRUCTURE_MODULES:
                continue
            module = importlib.import_module(f"{tools_package.__name__}.{module_info.name}")
            found.extend(value for value in vars(module).values() if isinstance(value, Tool))
        return cls(found)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self) -> list[dict[str, Any]]:
        """Tool definitions to send to the model."""
        return [t.schema() for t in self._tools.values()]

    def call(self, name: str, args: Mapping[str, Any], ctx: ToolContext) -> ToolResult:
        """Validate `args`, enforce confirmation for writes, and run the tool."""
        selected = self._tools.get(name)
        if selected is None:
            available = ", ".join(self._tools)
            return ToolResult.failure(f"Unknown tool {name!r}. Available tools: {available}.")

        try:
            parsed = selected.input_model.model_validate(args)
        except ValidationError as exc:
            return ToolResult.failure(
                f"Invalid arguments for {name}: {_describe(exc)}. Fix them and try again."
            )

        if selected.mutates and not ctx.session.is_confirmed(name, parsed.model_dump(mode="json")):
            return ToolResult.failure(
                "This action changes the booking and needs the user's explicit confirmation. "
                "Tell the user exactly what will change and what it costs, wait for a clear "
                "yes, then call the tool again with the same arguments."
            )

        try:
            return selected(parsed, ctx)
        except Exception:
            # Tools should return failures themselves; this is the last line of defense.
            logger.exception("Tool %s raised", name)
            return ToolResult.failure(
                f"{name} failed because of an internal error. Tell the user it could not "
                "be completed and offer to transfer them to a human agent."
            )


def _describe(exc: ValidationError) -> str:
    """Summarize validation errors as 'field: problem' pairs the model can fix."""
    problems = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "input"
        problems.append(f"{location}: {error['msg']}")
    return "; ".join(problems)
