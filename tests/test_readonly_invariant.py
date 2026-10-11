"""The read-only invariant: an AST sweep over every MCP package.

This test is the backstop of the golden rule. It does not trust reviewers to
notice a write operation; it scans the source tree and fails the build if any
MCP package contains something that could change a target system.

Whenever a new MCP server is added, it is covered automatically -- no wiring
needed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tracehub_mcp_common.guard import FORBIDDEN_PREFIXES

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_PACKAGES = sorted(REPO_ROOT.glob("packages/tracehub-mcp-*"))

#: Exact function names that are write verbs on their own.
FORBIDDEN_NAMES = frozenset({"post", "put", "patch", "delete", "apply", "exec"})

#: ReadOnlyHttpClient defines post() precisely so that it always raises.
#: It is the barrier itself, so it is the one place allowed to name the verb.
EXEMPT_FILES = frozenset({"http.py"})

#: Modules that hand out arbitrary command execution.
FORBIDDEN_IMPORTS = frozenset({"subprocess", "pty", "commands"})

#: Kubernetes escape hatches that bypass read-only RBAC.
FORBIDDEN_PATTERNS = (
    re.compile(r"\bconnect_(get|post)_namespaced_pod_(exec|attach|portforward)\b"),
    re.compile(r"\bport[-_]?forward\b", re.IGNORECASE),
    re.compile(r"\bos\.system\b"),
    re.compile(r"\bos\.popen\b"),
    re.compile(r"shell\s*=\s*True"),
    re.compile(r"\beval\s*\(", re.IGNORECASE),
)


def _python_files() -> list[Path]:
    files: list[Path] = []
    for package in MCP_PACKAGES:
        files.extend(path for path in package.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


PYTHON_FILES = _python_files()


def test_mcp_packages_exist() -> None:
    """Guards against the sweep silently passing because it found nothing."""
    assert MCP_PACKAGES, "packages/tracehub-mcp-* altinda hic paket bulunamadi"
    assert PYTHON_FILES, "MCP paketlerinde hic Python dosyasi bulunamadi"


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.name))
def test_no_state_changing_function_names(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        # Dunder hooks such as __post_init__ are Python plumbing, not tools.
        if node.name.startswith("__") and node.name.endswith("__"):
            continue
        name = node.name.casefold().lstrip("_")
        if name.startswith(FORBIDDEN_PREFIXES):
            offenders.append(f"{node.name} (satir {node.lineno}): yasakli onek")
        if name in FORBIDDEN_NAMES and path.name not in EXEMPT_FILES:
            offenders.append(f"{node.name} (satir {node.lineno}): yasakli isim")

    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} durum degistiren fonksiyon iceriyor:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.name))
def test_no_command_execution_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(
                f"import {alias.name} (satir {node.lineno})"
                for alias in node.names
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in FORBIDDEN_IMPORTS
        ):
            offenders.append(f"from {node.module} (satir {node.lineno})")

    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} komut calistirma modulu iceriyor:\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.name))
def test_no_forbidden_source_patterns(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    offenders = [
        f"{pattern.pattern} -> {match.group(0)!r}"
        for pattern in FORBIDDEN_PATTERNS
        for match in [pattern.search(source)]
        if match is not None and not _is_in_allowlist_declaration(source, match.start())
    ]

    assert not offenders, f"{path.relative_to(REPO_ROOT)} yasakli kalip iceriyor:\n" + "\n".join(
        offenders
    )


@pytest.mark.parametrize("path", PYTHON_FILES, ids=lambda p: str(p.name))
def test_no_print_calls(path: Path) -> None:
    """``print()`` on stdout corrupts the STDIO MCP protocol."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = [
        f"satir {node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]

    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} print() kullaniyor (STDIO protokolunu bozar): "
        + ", ".join(offenders)
    )


def _is_in_allowlist_declaration(source: str, position: int) -> bool:
    """Allow the forbidden words inside the guard's own denylist constants."""
    line_start = source.rfind("\n", 0, position) + 1
    line_end = source.find("\n", position)
    line = source[line_start : line_end if line_end != -1 else len(source)]
    stripped = line.strip()
    return stripped.startswith(("#", '"', "'", "r'", 'r"')) or stripped.endswith(",")
