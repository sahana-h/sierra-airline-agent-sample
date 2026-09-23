---
name: write-tests
description: Write unit tests for new or changed code in this airline-agent repo - tools, policy rules, the registry, session, DB, and (later) the agent loop and eval scenarios - using the project's fixtures and conventions and an airline-specific catalog of what to cover. Use this whenever code is added or changed, a bug is fixed (regression test first), the user asks for tests or coverage, or another skill (add-tool, add-policy-rule) reaches its testing step. Every feature in this repo ships with tests, so reach for this skill any time you touch src/.
---

# Write tests

In this repo a feature without tests is not done (CLAUDE.md). Tests are also the live-interview safety net: when a tool or rule is added under time pressure, the suite is what proves nothing else broke. Aim for tests that pin down *behavior the model and the user depend on*, not implementation details.

## Workflow

1. **List behaviors before writing code.** For the change at hand, write down each behavior as a sentence: "refuses to cancel a flight that already landed", "refund goes back to the original card". Each becomes one test. Include this list in the plan you show the user.
2. **Check the catalog.** Read `references/test-catalog.md` and pick every category that applies. It holds the airline-specific cases that are easy to forget (money conservation, boundaries, confirmation abuse, DB-unchanged-on-failure).
3. **Bug fix? Failing test first.** Write the test, run it, see it fail for the right reason, then fix.
4. **Write the tests** following the conventions below.
5. **Run `make test` and `make lint`** (tests are ruff-checked too) and report results honestly — failures included, with output.

## Where tests go

| Code | Test file |
|---|---|
| `policy/rules.py` | `tests/unit/test_rules.py` |
| a tool in `tools/<module>.py` | `tests/unit/test_<tool_name>.py` (one file per tool) |
| `tools/registry.py`, `tools/base.py` | `tests/unit/test_registry.py` |
| every registered tool, generically | `tests/unit/test_tool_contracts.py` (automatic — just keep it passing) |
| `agent/session.py` | `tests/unit/test_session.py` |
| `data/db.py`, `seed.json` | `tests/unit/test_db.py` |
| `agent/loop.py` | `tests/unit/test_loop.py`, with a fake scripted model — never the network |
| whole conversations against the real model | `tests/evals/` (run by `make eval`) |

## Fixtures and helpers (from `tests/conftest.py`)

- `db` — a fresh `Database` loaded from the seed for each test, so tests can write freely.
- `make_ctx(user_id=None, session=None)` — a `ToolContext` with the fixed clock. Pass `user_id` for a signed-in user; pass your own `Session()` when you need to drive turns (`session.begin_user_turn()`).
- `FIXED_NOW` = 2026-09-25 12:00 UTC. Seed dates are chosen relative to it (e.g. `M8TRW3` was booked 10h earlier; `B2LN6Y`'s flight landed 5 days earlier).
- Annotate the factory as `MakeCtx = Callable[..., ToolContext]` at the top of the test file.

Use real objects (real `Session`, real `Database`, real `Registry`). Fakes are only for things outside the process — the LLM. Seed records cover most edge cases; read `src/airline_agent/data/seed.json` before inventing data, and if you must add a record, keep the reference-integrity test in `test_db.py` passing.

## Conventions

- **Name tests after the behavior**: `test_refuses_to_cancel_landed_flight`, not `test_cancel_3`.
- **One behavior per test.** Small helpers (like `attempt(...)` in `test_authenticate_user.py`) keep them short.
- **Tables for rules**: `@pytest.mark.parametrize` with readable ids, covering each branch and each boundary.
- **Assert on the phrase that matters in error messages** (`"not authenticated" in result.error`), not the full string — messages get reworded; the key fact shouldn't.
- **Check `result.error is not None` before `in`** — mypy-style narrowing keeps tests readable and failures clear.
- **Prove "nothing changed"** with `before = db.snapshot()` … `assert db.snapshot() == before`. A write tool has many failure paths, so write one small helper in the test file (call the tool, assert it failed, assert the snapshot is unchanged, return the error) and keep each failure test to two lines.
- **Prove "only this changed"** by comparing snapshots with the target record excluded, or by asserting on the specific fields.
- **Write tools go through the registry** for at least one test, so the confirmation gate is exercised: call → expect "Nothing has been changed" → `session.begin_user_turn()` → call again → success.
- **No network, no sleeps, no real clock.** Unit tests must stay under a second in total.

## Minimum coverage by kind of change

- **Policy rule**: every branch, every boundary (at, just before, just after), every enum value that matters (cabin × tier tables).
- **Read tool**: success; not authenticated; missing record; another user's record (same message as missing); input normalization.
- **Write tool**: everything for a read tool, plus each policy refusal with its reason; DB unchanged on every failure; exact DB change on success; confirmation flow through the registry; changed arguments after proposal are refused; can't be applied twice.
- **Bug fix**: a regression test named after the bug's behavior, written before the fix.
