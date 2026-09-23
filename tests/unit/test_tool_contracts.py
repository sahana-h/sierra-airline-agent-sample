"""Contract tests that every discovered tool must pass. New tools are covered automatically."""

import json
import re
from collections.abc import Callable
from typing import Any

import pytest

from airline_agent.data.db import Database
from airline_agent.tools.base import ToolContext, ToolResult
from airline_agent.tools.registry import Registry

MakeCtx = Callable[..., ToolContext]

REGISTRY = Registry.discover()
SCHEMAS = {schema["name"]: schema for schema in REGISTRY.schemas()}
TOOL_NAMES = sorted(SCHEMAS)

MIN_DESCRIPTION_WORDS = 10

# Tools that run before sign-in. Adding one here is a security decision; review it as one.
PUBLIC_TOOLS = {"authenticate_user"}


def junk_inputs(name: str) -> list[dict[str, Any]]:
    """Inputs a confused model might send: extra keys, wrong types, empty and huge values."""
    fields = list(SCHEMAS[name]["input_schema"].get("properties", {}))
    return [
        {"unexpected_field": 1},
        {field: None for field in fields},
        {field: {"nested": [1, 2]} for field in fields},
        {field: "x" * 10_000 for field in fields},
    ]


def all_properties(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Top-level and nested-model properties, keyed by a readable path."""
    found = {f"{name}": prop for name, prop in schema.get("properties", {}).items()}
    for model_name, model in schema.get("$defs", {}).items():
        found.update(
            {f"{model_name}.{name}": prop for name, prop in model.get("properties", {}).items()}
        )
    return found


def test_tools_are_discovered() -> None:
    assert TOOL_NAMES, "Registry.discover() found no tools"


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_name_is_snake_case(name: str) -> None:
    assert re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_description_is_written_for_the_model(name: str) -> None:
    description = SCHEMAS[name]["description"]
    assert len(description.split()) >= MIN_DESCRIPTION_WORDS, (
        f"{name}: say what the tool does, when to use it and when not to"
    )


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_every_input_field_has_a_description(name: str) -> None:
    missing = [
        path
        for path, prop in all_properties(SCHEMAS[name]["input_schema"]).items()
        if not prop.get("description")
    ]
    assert not missing, f"{name}: add Field(description=...) to {missing}"


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_input_schema_is_a_serializable_object_schema(name: str) -> None:
    schema = SCHEMAS[name]["input_schema"]
    assert schema["type"] == "object"
    json.dumps(schema)


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_missing_required_fields_are_rejected(name: str, make_ctx: MakeCtx) -> None:
    if not SCHEMAS[name]["input_schema"].get("required"):
        pytest.skip("tool has no required fields")
    result = REGISTRY.call(name, {}, make_ctx(user_id="ava_chen_1042"))
    assert not result.ok
    assert result.error is not None
    assert "Invalid arguments" in result.error


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_only_public_tools_run_when_signed_out(name: str, make_ctx: MakeCtx) -> None:
    result = REGISTRY.call(name, {}, make_ctx())
    refused = result.error is not None and "not authenticated" in result.error
    assert refused == (name not in PUBLIC_TOOLS)


def test_public_tools_exist() -> None:
    assert set(TOOL_NAMES) >= PUBLIC_TOOLS


@pytest.mark.parametrize("signed_in_as", [None, "ava_chen_1042"])
@pytest.mark.parametrize("name", TOOL_NAMES)
def test_junk_input_never_raises_or_changes_the_db(
    name: str, signed_in_as: str | None, db: Database, make_ctx: MakeCtx
) -> None:
    before = db.snapshot()
    for args in junk_inputs(name):
        result = REGISTRY.call(name, args, make_ctx(user_id=signed_in_as))
        assert isinstance(result, ToolResult)
    assert db.snapshot() == before
