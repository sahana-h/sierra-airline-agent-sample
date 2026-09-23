---
name: architecture-check
description: Check the airline-agent repo against the architecture rules in CLAUDE.md - SDK isolated to agent/llm.py, pure policy functions, thin tools that never raise and declare mutates, a loop that knows no tool names, all data access through data/db.py, tests shipped with every change. Run a bundled static-analysis script plus a short judgment checklist. Use this before committing, after adding a tool or policy rule, when reviewing a diff or PR, or whenever the user asks "does this follow the architecture / CLAUDE.md?" - and at the end of the add-tool and add-policy-rule workflows.
---

# Architecture check

The architecture is what makes this agent safe to extend live: each rule in CLAUDE.md exists so that adding a tool or rule can't quietly weaken policy enforcement. This skill checks the mechanical rules with a script and the judgment calls with a checklist.

## 1. Run the script

From the repo root:

```bash
.venv/bin/python .claude/skills/architecture-check/scripts/check_architecture.py
```

It uses static analysis only (never imports the app) and reports `ERROR`/`WARNING` lines with `file:line`. Exit code 1 means at least one error. It checks:

| Rule (CLAUDE.md) | What the script flags |
|---|---|
| SDK only in `agent/llm.py` | any `anthropic` import elsewhere |
| Policy is pure | `policy/` importing the DB, tools, agent, or I/O modules; calling `open`/`print`/`input`; reading the real clock |
| Tools are thin and never raise | `raise` inside a `@tool` function; `@tool` without `mutates=`; opening files or referencing `seed.json`; reading the real clock instead of `ctx.now`; touching private `ctx.db._...` state |
| Loop knows nothing about tools | `agent/loop.py` containing a tool name string or importing a tool module |
| Tests ship with features | `WARNING` when `src/` changed in the working tree but `tests/` didn't |

Treat every ERROR as something to fix, not explain away. If a finding is a genuine false positive, say so to the user with the reason — don't silently ignore it, and consider tightening the script.

## 2. Walk the judgment checklist

The script can't see these. Look at the changed code (`git diff` plus untracked files) and check each one that applies:

- **Business logic location**: does a tool contain a policy decision (cabin/tier conditions, fee numbers, time windows) that belongs in `policy/rules.py`?
- **Enforced, not just described**: is every rule in `prompts/system.md` that this change touches also checked in code?
- **Failure before write**: in write tools, do all checks run before the first DB write, so a failure leaves the DB unchanged?
- **Actionable errors**: does every `ToolResult.failure` message tell the model what to do next, without leaking internals or other users' data?
- **Authorization**: does every tool that reads or writes user data check `ctx.session.user_id` and ownership, with the same message for "missing" and "not yours"?
- **One concern per file**: did the change need edits across several layers? CLAUDE.md says that means the layers are wrong — flag it.
- **No edits to `loop.py`/`registry.py` for a new tool or rule.**
- **Docs truthful**: README and prompt describe what actually exists.

## 3. Report

Give the user a short summary: script result (errors/warnings with `file:line`), checklist items that failed with a one-line reason each, and what you recommend fixing. If everything passes, say so plainly.
