# Airline Support Agent

A customer-service agent for a fictional airline. It helps customers with reservations, changes, cancellations, baggage and refunds by calling tools against a mock database, and it follows written business policy that is **enforced in code**, not only described in the prompt.

The orchestration loop is written by hand on top of the Anthropic SDK. It uses no agent framework.

> **Status:** scaffold. The tool contract, registry, data layer and one read-only tool (`get_reservation`) are built and tested. The agent loop, the CLI, the policy rules and the other tools come next.

## Quickstart

Requires Python 3.11+ and `make`.

```bash
make install   # create .venv and install dependencies
make test      # unit tests: fast, no network
make lint      # ruff + mypy --strict
make run       # terminal chat (placeholder for now)
```

`make run` and `make eval` call the Claude API and will need `ANTHROPIC_API_KEY` in your environment once the loop exists. If your default `python3` is older than 3.11, use `make install PYTHON=python3.12`.

## Architecture

```
cli.py ──► agent/loop.py ──► tools/registry.py ──► tools/*.py ──► policy/rules.py
                │                                       │
           agent/llm.py                            data/db.py
       (only file importing SDK)
```

| Layer | Responsibility |
|---|---|
| `cli.py` | Terminal input/output. Nothing else. |
| `agent/loop.py` | Model → tool calls → model, until the model replies to the user. Knows nothing about specific tools. |
| `agent/llm.py` | Thin wrapper around the SDK, so the model provider sits behind one seam. |
| `tools/registry.py` | Discovers tools, publishes their schemas, validates arguments, blocks unconfirmed writes, and never raises. |
| `tools/*.py` | Thin tools: validate input, ask policy, read or write the DB, return a `ToolResult`. |
| `policy/rules.py` | Pure functions for business rules. No I/O, so they are trivial to test. |
| `data/db.py` | In-memory database. The only way to reach data. |

## Design decisions

- **Policy is enforced in code.** The prompt tells the model what the policy is. The tools make sure it's followed. If the model asks for something the policy forbids, the tool refuses and says why.
- **Writes require confirmation, enforced by the registry.** A tool marked `mutates=True` only runs if the session has recorded the user's explicit yes for *that exact call*. The check compares the validated arguments, so the model can't get approval for one change and then carry out a different one.
- **Tools never raise to the loop.** Every failure comes back as `ToolResult(ok=False, error=...)` worded so the model can recover or explain. The registry also catches unexpected exceptions as a last line of defense.
- **Authorization is checked in tools too.** Tools look up the authenticated user from the session. A reservation belonging to someone else is reported as "not found", so the tool doesn't reveal which codes exist.
- **Time is injected.** `ToolContext.now` means rules like "free cancellation within 24 hours" can be tested with a fixed clock.
- **The DB hands out copies.** Getters return deep copies, so a tool can't change data by accident. Writes will go through explicit `Database` methods.
- **Domain model.** The domain loosely follows the τ-bench airline setting: cabins, membership tiers, passengers and mixed payment methods. The seed data is small and hand-written so that each record exercises a policy edge case (basic economy, a gold member, a flight that has already flown, a cancelled booking, a split payment).

## Adding a tool

No changes to the loop or the registry are needed. Here is `get_reservation` in full:

```python
class GetReservationInput(BaseModel):
    reservation_id: str = Field(description="The six-character reservation code, for example 'ZQ4K2P'.")


@tool(
    name="get_reservation",
    description="Look up one of the authenticated user's reservations by its code ... "
                "Do not use it to search for flights ...",
    input_model=GetReservationInput,  # the JSON schema is generated from this
    mutates=False,                     # True → the registry requires user confirmation
)
def get_reservation(args: GetReservationInput, ctx: ToolContext) -> ToolResult:
    ...
    return ToolResult.success(reservation.model_dump(mode="json"))
```

Checklist:

1. Define the input model and the `@tool` function in a module under `src/airline_agent/tools/`. The registry picks it up automatically.
2. Put any new business rule in `policy/rules.py` as a pure function.
3. Add unit tests for the rule and for the tool, covering success and every failure path.
4. Add or update an eval scenario in `tests/evals/`.
5. If the policy text changed, update `prompts/system.md`.

## Testing

- `make test`: unit tests for the registry, the tools and the database. They run offline against `seed.json` with a fixed clock (`2026-09-25T12:00Z`).
- `make eval` *(coming)*: scripted conversations against the real model. A scenario passes only if the **final database state** matches what's expected and no forbidden change happened.

## Project layout

```
src/airline_agent/
├── cli.py
├── agent/     loop.py, llm.py, prompts.py, session.py
├── tools/     base.py, registry.py, reservations.py, flights.py, baggage.py, refunds.py
├── policy/    rules.py
└── data/      models.py, db.py, seed.json
prompts/system.md
tests/unit/, tests/evals/
```
