# Airline Support Agent

A customer-service agent for a fictional airline. It helps customers with reservations, changes, cancellations, baggage and refunds by calling tools against a mock database, and it follows written business policy that is **enforced in code**, not only described in the prompt.

The orchestration loop is written by hand on top of the Anthropic SDK. It uses no agent framework.

> **Status:** in progress. The tool contract, registry, data layer, session (sign-in and confirmations) and two tools (`authenticate_user`, `get_reservation`) are built and tested. The agent loop, the CLI, the remaining policy rules and the other tools come next.

## Quickstart

Requires Python 3.11+ and `make`.

```bash
make install   # create .venv and install dependencies
make test      # unit tests: fast, no network
make lint      # ruff + mypy --strict
make run       # terminal chat (placeholder for now)
```

Without make: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"`. The dependencies are listed in `pyproject.toml`.

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
- **Writes require confirmation, enforced in code.** See [Confirmation protocol](#confirmation-protocol).
- **Sign-in is required, enforced by the registry.** Every tool requires a signed-in user unless it explicitly opts out with `requires_auth=False` (today only `authenticate_user`). The default is "locked", so forgetting the flag can't open a tool up, and a contract test pins the list of tools that opt out. `authenticate_user` checks the user's name against their user ID or one of their reservation codes. Every mismatch gets the same vague error, and after 3 failed attempts the tool refuses and tells the model to hand off to a human. A conversation serves one customer, so switching to a different account is refused.
- **Tools never raise to the loop.** Every failure comes back as `ToolResult(ok=False, error=...)` worded so the model can recover or explain. The registry also catches unexpected exceptions as a last line of defense.
- **Ownership is checked in tools.** Only a tool knows what "belongs to this user" means for its data, so tools compare records against `ctx.user_id`. A reservation belonging to someone else is reported as "not found", so the tool doesn't reveal which codes exist.
- **Time is injected.** `ToolContext.now` means rules like "free cancellation within 24 hours" can be tested with a fixed clock.
- **The DB hands out copies.** Getters return deep copies, so a tool can't change data by accident. Writes will go through explicit `Database` methods.
- **Domain model.** The domain loosely follows the τ-bench airline setting: cabins, membership tiers, passengers and mixed payment methods. The seed data is small and hand-written so that each record exercises a policy edge case (basic economy, a gold member, a flight that has already flown, a cancelled booking, a split payment).

## Confirmation protocol

Any tool marked `mutates=True` goes through two steps, enforced by the registry and `agent/session.py`:

1. The model calls the write tool. The registry doesn't run it. It records the call as *pending* and tells the model to describe the change and its cost and ask the user.
2. The user replies. If they agree, the model makes the same call again. It runs only if:
   - it is the **first user turn after** the proposal,
   - the tool name and **validated arguments are identical**, and
   - the confirmation **hasn't been used** already.

So the model can't ask and act in the same turn, can't change the details after the user agreed, and can't reuse an old approval. If the user says no or changes the subject, the pending call expires on its own. Code guarantees the user was asked and had a chance to answer. Whether the answer meant "yes" is still the model's call.

We considered delaying the write ("cancelling in 30 seconds…") so the user could undo it. We didn't: on chat or voice the user may already be gone when it lands, and it adds background state. The right way to allow second thoughts is policy, such as a free-cancellation window.

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
    # requires_auth defaults to True → the registry refuses calls before sign-in
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

- `make test`: unit tests for the registry, session, policy rules, tools and database, plus contract tests that every tool passes automatically (descriptions, schema, sign-in, junk input). They run offline against `seed.json` with a fixed clock (`2026-09-25T12:00Z`).
- `make eval` *(coming)*: scripted conversations against the real model. A scenario passes only if the **final database state** matches what's expected and no forbidden change happened.

## Working with Claude Code

The repo ships project skills in `.claude/skills/` that encode the conventions above, so extensions stay consistent:

- **`add-tool`**: adds a tool end to end: input model, policy wiring, database access, tests, prompt and docs.
- **`add-policy-rule`**: adds a business rule as a pure function, enforces it in every affected tool, and keeps the prompt in sync.
- **`write-tests`**: the test conventions for each layer, plus a catalog of airline-specific cases (money, time boundaries, confirmation abuse).
- **`architecture-check`**: a static check of the CLAUDE.md rules plus a review checklist. Run it before committing.

## Project layout

```
src/airline_agent/
├── cli.py
├── agent/     loop.py, llm.py, prompts.py, session.py
├── tools/     base.py, registry.py, auth.py, reservations.py, flights.py, baggage.py, refunds.py
├── policy/    rules.py
└── data/      models.py, db.py, seed.json
prompts/system.md
tests/unit/, tests/evals/
```
