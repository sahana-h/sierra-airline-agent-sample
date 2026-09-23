# Airline Support Agent

A customer-service agent for a fictional airline. It handles reservations, changes, cancellations, baggage, and refunds by calling tools against a mock database and following written business policy.

This is an interview take-home. It will be **extended live** by adding tools and policy rules, so extensibility and clarity matter more than feature count.

## Hard constraints

- **No agent frameworks** (no LangChain, LlamaIndex, CrewAI, etc.). The orchestration loop is written by hand.
- Use the Anthropic SDK directly, and only inside `agent/llm.py`.
- Runs on a laptop with one command: `make run`. No external services, no fragile setup.
- Python 3.11+, type hints everywhere, Pydantic for tool inputs and data models.

## Project layout

```
airline-agent/
├── CLAUDE.md
├── README.md              # how to run, design decisions, how to add a tool
├── Makefile               # run, test, eval, lint
├── pyproject.toml
├── src/airline_agent/
│   ├── cli.py             # terminal chat interface, nothing else
│   ├── agent/
│   │   ├── loop.py        # the orchestration loop (model -> tools -> model)
│   │   ├── llm.py         # thin wrapper around the SDK; the only file that imports it
│   │   ├── prompts.py     # system prompt and policy text, loaded from prompts/*.md
│   │   └── session.py     # conversation state, pending confirmations
│   ├── tools/
│   │   ├── base.py        # Tool dataclass, @tool decorator, ToolResult
│   │   ├── registry.py    # auto-discovers tools, builds schemas, dispatches by name
│   │   ├── reservations.py
│   │   ├── flights.py
│   │   ├── baggage.py
│   │   └── refunds.py
│   ├── policy/
│   │   └── rules.py       # pure functions: can_cancel, refund_amount, change_fee, ...
│   └── data/
│       ├── models.py      # Pydantic models: User, Reservation, Flight
│       ├── db.py          # in-memory DB with load/save/snapshot
│       └── seed.json      # mock users, reservations, flights
├── prompts/
│   └── system.md          # agent instructions + airline policy
└── tests/
    ├── unit/              # policy rules, tools, registry
    └── evals/             # scripted conversations, pass/fail on final DB state
```

Rule of thumb: **one concern per file.** If a change requires touching more than one layer, the layers are wrong.

## Architecture rules

1. **The loop knows nothing about specific tools.** `loop.py` only talks to the registry: `registry.schemas()` and `registry.call(name, args, session)`. Adding a tool must never require editing the loop.
2. **Tools are thin.** A tool validates input, calls policy functions, reads or writes the DB, and returns a `ToolResult`. Business logic lives in `policy/rules.py`, not in tools and not only in the prompt.
3. **Policy is enforced in code.** If policy forbids an action, the tool returns an error explaining why, even if the model asks for it. The prompt describes policy; the code guarantees it.
4. **Policy functions are pure.** They take data in and return a decision out, with no DB access and no I/O, so they are trivially unit-testable.
5. **Tools never raise to the loop.** They return `ToolResult(ok=False, error="...")` with a message the model can act on and explain to the user.
6. **All DB access goes through `data/db.py`.** No tool touches raw dicts.

## Tool contract

Every tool is a function decorated with `@tool` and lives in a module under `src/airline_agent/tools/`.

```python
@tool(
    name="add_checked_bag",
    description="Add a checked bag to an existing reservation. Fee depends on fare class and loyalty tier.",
    input_model=AddCheckedBagInput,   # Pydantic model; JSON schema is generated from it
    mutates=True,                     # write tools require explicit user confirmation
)
def add_checked_bag(args: AddCheckedBagInput, ctx: ToolContext) -> ToolResult:
    ...
```

- `name`: snake_case verb phrase. `description`: written for the model. Say when to use it and when not to.
- `input_model`: Pydantic model with field descriptions. This is the single source of truth for the schema.
- `mutates`: `False` for reads, `True` for writes. The registry refuses to run a mutating tool unless the session has a recorded user confirmation for that exact action.
- `requires_auth`: defaults to `True`; the registry refuses the call until the user is signed in, and the tool can read `ctx.user_id`. Set `False` only for tools that must work before sign-in (e.g. `authenticate_user`).
- Return `ToolResult(ok=True, data={...})` or `ToolResult(ok=False, error="...")`.

### Checklist for adding a tool

Use the `add-tool` skill (and `add-policy-rule` / `write-tests` for rules and tests); it walks through these steps.

1. Create or open a module in `tools/` and define the input model and function with `@tool`.
2. If there is a new business rule, add a pure function in `policy/rules.py`.
3. Add a unit test for the rule and one for the tool (success and each failure path).
4. Add or update one eval scenario in `tests/evals/`.
5. If the policy text changed, update `prompts/system.md`.

Do not edit `loop.py` or `registry.py` for any of this. If you feel like you have to, stop and fix the abstraction.

## Agent behavior

- Authenticate the user (name and reservation or user ID) before reading or changing anything.
- Confirm before every write: state exactly what will change and the cost, then wait for an explicit yes.
- Never invent policy, prices, or availability. Use tools or say you don't know.
- Refuse out-of-policy requests politely, explain why, and offer the closest allowed alternative.
- Hand off to a human when the request is outside the toolset or the user asks for one.
- Keep replies short and plain. Get the details right (amounts, dates, flight numbers).

## Testing

- `make test`: unit tests (fast, no network).
- `make eval`: runs scripted conversations against the real model. Each scenario defines user turns, and passes only if the **final DB state** matches the expected state (and forbidden mutations did not happen).
- Cover at least: happy path, out-of-policy request, missing info, tool error, user changes their mind before confirming, unauthenticated request.
- Every bug fix gets a regression test first.

## Code style

- Small functions, descriptive names, no dead code, no clever tricks.
- Docstrings on public functions; comments explain *why*, not *what*.
- Format with `ruff format`, lint with `ruff check`, type-check with `mypy --strict` on `src/`.
- Commit in small steps with clear messages.

## Working with Claude Code on this repo

### Plan first, then wait for approval (required)

1. Before creating, editing, or deleting any file, explain your plan to the user: what you will change, which files you will touch, and why.
2. **Stop and wait for explicit approval.** Do not edit code, run installs, or make changes until the user says to proceed.
3. If the user requests changes to the plan, revise it and ask again.
4. If the scope grows mid-implementation, stop and get approval for the new plan.

Reading files and running tests to understand the code do not need approval.

### Tests are part of every feature (required)

- Every new feature, tool, or policy rule ships with tests in the same change. A feature without tests is not done.
- Include the tests in your plan, and list which ones you will add.
- Every bug fix starts with a failing regression test.
- After any change, run `make test`, and run `make eval` if agent behavior changed. Report the results.

### General

- Read this file and `README.md` before making changes.
- Prefer the smallest change that fits the existing structure. Do not refactor unrelated code.
- Never add a dependency without asking. Never add an agent framework.