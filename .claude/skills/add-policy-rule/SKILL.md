---
name: add-policy-rule
description: Add or change an airline business rule in this repo - as a pure function in policy/rules.py, wired into the tools that must enforce it, reflected in prompts/system.md, with boundary tests. Use this whenever the user states or changes policy - fees, refunds, cancellation windows, change rules, baggage allowances, membership-tier perks, eligibility, limits, "basic economy can't be changed", "gold members get free bags", "free cancellation within 24 hours" - even if they phrase it as a product requirement rather than asking for a "rule".
---

# Add a policy rule

This project's central promise is **policy enforced in code**: the prompt describes the policy, the code guarantees it. A rule that lives only in `prompts/system.md` is a suggestion the model can be talked out of; a rule in `policy/rules.py` that a tool calls cannot. Every rule change therefore has three parts that must stay in sync — the function, the tools that call it, and the prompt text.

## 1. Pin down the rule

Before coding, restate the rule precisely in the plan you show the user, and ask about anything ambiguous. Rules are usually underspecified at the edges, and edges are where bugs and interview questions live:

- Boundaries: is "within 24 hours" `<` or `<=`? Measured from booking time or departure?
- Scope: which cabins, tiers, statuses (active/cancelled), flight states (scheduled/landed)?
- Interactions: does travel insurance override it? Does membership tier stack with cabin?
- Money: per passenger or per reservation? Which payment methods, and in what order, for refunds?

## 2. Write a pure function

In `src/airline_agent/policy/rules.py`:

- **Data in, decision out.** Take plain values or models (`Reservation`, `Cabin`, `MembershipTier`, `datetime`), return a `bool`, an amount, or a small result object. No DB, no session, no I/O, no `datetime.now()` — take `now` as a parameter. That purity is what makes rules trivially testable and reusable across tools.
- **Name it as a question or a quantity**: `can_cancel`, `refund_amount`, `change_fee`, `free_bag_allowance`.
- **Constants at module top** with names (`FREE_CANCELLATION_WINDOW = timedelta(hours=24)`, `MAX_FAILED_AUTH_ATTEMPTS = 3`), so the prompt-consistency test and humans can find them.
- **When a decision can be "no", return why.** A tool needs a reason to give the model ("basic economy fares can't be changed"). A small frozen dataclass like `Decision(allowed: bool, reason: str | None)` works well — add it once and reuse it.
- Money is whole dollars (`int`); datetimes are timezone-aware UTC.

## 3. Enforce it in every tool it applies to

Search `src/airline_agent/tools/` for every tool the rule affects and call the function there, *before* any DB write. Missing one tool is the classic way policy leaks — e.g. adding a change fee to `change_flight` but not to `change_cabin`. If a tool that needs the rule doesn't exist yet, note that in your summary; use the `add-tool` skill when building it.

## 4. Update the prompt

Describe the rule in `prompts/system.md` in plain language with the same numbers the code uses. The model needs it to set expectations and offer alternatives *before* hitting a tool error. If the prompt-consistency test exists, it will fail when the numbers drift — that's intended.

## 5. Tests and verification

Use the `write-tests` skill. For a rule that means a parametrized table covering each branch *and* each boundary (exactly at the limit, one unit either side), plus tool tests showing the tool refuses with the rule's reason and leaves the DB unchanged. Seed data has ready-made edge cases — check `src/airline_agent/data/seed.json` before inventing new records.

Run `make test`, `make lint` and the `architecture-check` skill, and report the results.
