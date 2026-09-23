---
name: add-tool
description: Add a new tool (a capability the airline agent can call) to this repo following the project's tool contract - input model, @tool function, policy wiring, DB access, tests, prompt and README updates. Use this whenever the user wants the agent to be able to do something new - "add a tool for X", "the agent should be able to change flights / add bags / upgrade / search flights / transfer to a human", "support refunds", or any new read or write action on reservations, users or flights - even if they don't say the word "tool".
---

# Add a tool

Tools are how the model acts on the world. In this repo they are deliberately thin: validate input, ask policy, read or write the DB, return a `ToolResult`. The loop and registry never change when a tool is added — that is the extensibility promise this project is judged on, so protect it.

## Before writing code

Read `CLAUDE.md` (tool contract + architecture rules), then the two reference tools, which show the house style:
- `src/airline_agent/tools/reservations.py` — `get_reservation` (read tool, ownership check)
- `src/airline_agent/tools/auth.py` — `authenticate_user` (session interaction, policy call, vague errors)

Then make three decisions and put them in the plan you show the user (CLAUDE.md requires plan-then-approval):

1. **Read or write?** Anything that changes the DB is `mutates=True`. The registry then enforces two-step confirmation automatically — the tool itself does nothing special for it. Signing in changes only the session, so it is not a write.
2. **Which business rules apply?** Every "is this allowed / how much does it cost" decision belongs in `policy/rules.py` as a pure function. If a rule doesn't exist yet, use the `add-policy-rule` skill for it first. A tool that contains `if cabin == ...` or a fee number is a sign the logic is in the wrong layer.
3. **Which module?** Group by domain: `reservations.py`, `flights.py`, `baggage.py`, `refunds.py`, `auth.py`. A new module is fine for a new domain; the registry discovers every module in `tools/` automatically.

If you find yourself needing to edit `agent/loop.py` or `tools/registry.py`, stop and tell the user — the abstraction is wrong and that is a design conversation, not a quiet edit.

## Writing the tool

```python
class AddCheckedBagsInput(BaseModel):
    reservation_id: str = Field(description="Six-character reservation code, e.g. 'ZQ4K2P'.")
    count: int = Field(ge=1, le=5, description="Number of bags to add.")
    payment_method_id: str = Field(description="ID of one of the user's saved payment methods.")


@tool(
    name="add_checked_bags",
    description=(
        "Add checked bags to one of the authenticated user's active reservations and charge "
        "the bag fee. Use only after telling the user the total fee. Do not use it to remove bags."
    ),
    input_model=AddCheckedBagsInput,
    mutates=True,
)
def add_checked_bags(args: AddCheckedBagsInput, ctx: ToolContext) -> ToolResult:
    """Add bags if policy allows, charging the fee to the chosen payment method."""
    ...
```

What good looks like, and why:

- **Name**: snake_case verb phrase (`change_flight`, not `flight_changer`). Enforced at import.
- **Description is written for the model**: say what it does, when to use it, and when *not* to. The model picks tools from descriptions alone, so a vague description causes wrong tool choice.
- **Every input field has a `Field(description=...)`** — it becomes the JSON schema the model reads. Use Pydantic constraints (`ge`, `le`, `Literal`, enums from `data/models.py`) so bad input fails validation before your code runs. Normalize user-typed codes (`.strip().upper()`) the way `GetReservationInput` does.
- **Sign-in is the registry's job**: tools require a signed-in user by default, and the registry refuses the call before your code runs. Read the user with `ctx.user_id` (a plain `str`). Only pass `requires_auth=False` for a tool that must work before sign-in, and add it to `PUBLIC_TOOLS` in `tests/unit/test_tool_contracts.py`. That's a security decision, so call it out in your plan.
- **Ownership is the tool's job**: if the record belongs to another user, return the *same* "not found" message as a missing record, so the tool can't be used to probe which codes exist. Once a second tool needs this same sign-in + ownership preamble, extract it into one shared helper (e.g. `tools/_common.py`) and have both tools use it. Copies of security checks drift apart, and the next tool written in a hurry will copy the weakest one.
- **Time comes from `ctx.now`**, never `datetime.now()`, so policy is deterministic in tests.
- **Never raise.** Return `ToolResult.failure("...")` with a message that tells the model what went wrong *and what to do next* (ask the user to re-check, offer an alternative, offer a human). The registry catches stray exceptions, but that's a last line of defense and gives the user a worse answer.
- **Return useful data on success** — the model has to explain the result, so include amounts, new totals, and IDs it will need for follow-ups.

## DB writes

`Database` getters return deep copies, so mutating a returned model does nothing. For a write, get the copy, change it, and persist it through an explicit method on `Database` (e.g. `save_reservation(reservation)`). If the method you need doesn't exist, add it to `data/db.py` with a test in `tests/unit/test_db.py` — that's the data layer's job, not the tool's. Tools never touch `seed.json` or raw dicts.

Do all policy checks *before* any write, so a failure leaves the DB exactly as it was.

## Tests, prompt, docs

1. **Tests** — use the `write-tests` skill. Minimum for a tool: success, every failure path, unauthenticated, another user's record, DB unchanged on each failure; for a write tool also the full confirmation flow through the registry. The contract tests in `tests/unit/test_tool_contracts.py` cover the new tool automatically — make sure they pass.
2. **Prompt** — if the tool introduces behavior the model must know (when to offer it, what to confirm), update `prompts/system.md`.
3. **README** — if the tool list or a design decision changed, update it. Keep the README truthful about what exists.
4. **Evals** — once `tests/evals/` has a harness, add or update one scenario.
5. **Verify** — run `make test` and `make lint`, then the `architecture-check` skill. Report results honestly, including failures.
