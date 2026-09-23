#!/usr/bin/env python3
"""Check this repo against the architecture rules in CLAUDE.md.

Run from the repo root:  python .claude/skills/architecture-check/scripts/check_architecture.py

Prints one line per finding. Exits 1 if any ERROR was found; WARNINGs don't fail.
Uses only the standard library and static analysis (ast), so it never imports the app.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path.cwd()
PKG = ROOT / "src" / "airline_agent"
TOOL_INFRA = {"base.py", "registry.py", "__init__.py"}
# Modules that make a policy function impure (I/O, real clock, randomness, app state).
IMPURE_MODULES = {"os", "pathlib", "io", "json", "random", "time", "subprocess", "requests"}
APP_LAYERS_FORBIDDEN_IN_POLICY = ("airline_agent.data.db", "airline_agent.tools", "airline_agent.agent")


@dataclass
class Finding:
    level: str  # "ERROR" or "WARNING"
    path: Path
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.path.relative_to(ROOT)}:{self.line}: {self.message}"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def imported_modules(tree: ast.Module) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, node.lineno))
    return found


def is_real_clock_call(node: ast.AST) -> bool:
    """datetime.now(), datetime.utcnow(), date.today(), time.time()."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    return node.func.attr in {"now", "utcnow", "today", "time"} and isinstance(
        node.func.value, ast.Name
    ) and node.func.value.id in {"datetime", "date", "time"}


def tool_decorator(func: ast.FunctionDef) -> ast.Call | None:
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "tool":
            return dec
    return None


def check_sdk_isolation(files: list[Path]) -> list[Finding]:
    """Rule: the Anthropic SDK is imported only in agent/llm.py."""
    allowed = PKG / "agent" / "llm.py"
    return [
        Finding("ERROR", path, line, f"imports {module!r}; only agent/llm.py may use the SDK")
        for path in files
        if path != allowed
        for module, line in imported_modules(parse(path))
        if module.split(".")[0] == "anthropic"
    ]


def check_policy_purity() -> list[Finding]:
    """Rule: policy functions are pure - no DB, no session, no I/O, no real clock."""
    findings: list[Finding] = []
    for path in sorted((PKG / "policy").glob("*.py")):
        tree = parse(path)
        for module, line in imported_modules(tree):
            if module.startswith(APP_LAYERS_FORBIDDEN_IN_POLICY):
                findings.append(Finding("ERROR", path, line, f"policy imports {module!r}"))
            elif module.split(".")[0] in IMPURE_MODULES:
                findings.append(Finding("ERROR", path, line, f"policy imports I/O module {module!r}"))
        for node in ast.walk(tree):
            if is_real_clock_call(node):
                findings.append(Finding("ERROR", path, node.lineno, "policy reads the real clock; take `now` as a parameter"))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "print", "input"}:
                findings.append(Finding("ERROR", path, node.lineno, f"policy calls {node.func.id}()"))
    return findings


def check_tools() -> tuple[list[Finding], set[str]]:
    """Rules: tools declare `mutates`, don't raise, don't read the clock or raw data, don't reach into the DB."""
    findings: list[Finding] = []
    tool_names: set[str] = set()
    for path in sorted((PKG / "tools").glob("*.py")):
        if path.name in TOOL_INFRA:
            continue
        tree = parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                findings.append(Finding("ERROR", path, node.lineno, "tool opens a file; go through data/db.py"))
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.endswith("seed.json"):
                findings.append(Finding("ERROR", path, node.lineno, "tool references seed.json; go through data/db.py"))
            if is_real_clock_call(node):
                findings.append(Finding("ERROR", path, node.lineno, "tool reads the real clock; use ctx.now"))
            if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
                if isinstance(node.value, ast.Attribute) and node.value.attr == "db":
                    findings.append(Finding("ERROR", path, node.lineno, f"tool reaches into private DB state ({node.attr})"))
            if not isinstance(node, ast.FunctionDef):
                continue
            decorator = tool_decorator(node)
            if decorator is None:
                continue
            keywords = {kw.arg: kw.value for kw in decorator.keywords}
            if "mutates" not in keywords:
                findings.append(Finding("ERROR", path, node.lineno, f"@tool {node.name} doesn't declare mutates="))
            name = keywords.get("name")
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                tool_names.add(name.value)
            for inner in ast.walk(node):
                if isinstance(inner, ast.Raise):
                    findings.append(Finding("ERROR", path, inner.lineno, f"tool {node.name} raises; return ToolResult.failure(...)"))
    return findings, tool_names


def check_loop_is_generic(tool_names: set[str]) -> list[Finding]:
    """Rule: the loop knows nothing about specific tools."""
    loop = PKG / "agent" / "loop.py"
    if not loop.exists():
        return []
    findings: list[Finding] = []
    for node in ast.walk(parse(loop)):
        if isinstance(node, ast.Constant) and node.value in tool_names:
            findings.append(Finding("ERROR", loop, node.lineno, f"loop mentions tool {node.value!r}"))
    for module, line in imported_modules(parse(loop)):
        if module.startswith("airline_agent.tools.") and module.rsplit(".", 1)[-1] not in {"base", "registry"}:
            findings.append(Finding("ERROR", loop, line, f"loop imports tool module {module!r}"))
    return findings


def check_tests_changed() -> list[Finding]:
    """Rule: every change to src/ ships with tests. Best-effort, from git."""
    try:
        diff = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=True, cwd=ROOT,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    changed = [line[3:] for line in diff.splitlines()]
    src_changed = [p for p in changed if p.startswith("src/") and p.endswith(".py")]
    tests_changed = [p for p in changed if p.startswith("tests/")]
    if src_changed and not tests_changed:
        return [Finding("WARNING", ROOT / src_changed[0], 1, "src/ changed but no tests/ changed")]
    return []


def main() -> int:
    if not PKG.is_dir():
        print("Run this from the repo root (src/airline_agent not found).", file=sys.stderr)
        return 2
    files = sorted(PKG.rglob("*.py"))
    tool_findings, tool_names = check_tools()
    findings = [
        *check_sdk_isolation(files),
        *check_policy_purity(),
        *tool_findings,
        *check_loop_is_generic(tool_names),
        *check_tests_changed(),
    ]
    for finding in sorted(findings, key=lambda f: (f.path, f.line)):
        print(finding)
    errors = sum(f.level == "ERROR" for f in findings)
    print(f"\n{len(tool_names)} tools checked; {errors} error(s), {len(findings) - errors} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
