"""Forbidden-surface guard: the controller core stays local and offline.

CTRL-001 forbids GitHub mutations, Z.ai integration, external service
credentials, secrets, and a persistent controller database. This test
makes those prohibitions executable: it parses every module of the
``controller`` package (and the tests) with the ``ast`` module and fails
if any import references network, subprocess, or persistence machinery,
or if any non-stdlib dependency is introduced.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

from tests.util import REPO_ROOT

#: Modules whose import means network, process, or durable-state access.
_FORBIDDEN_IMPORT_ROOTS: frozenset[str] = frozenset(
    {
        # network / external services
        "socket",
        "http",
        "urllib",
        "requests",
        "ftplib",
        "smtplib",
        "xmlrpc",
        # process control
        "subprocess",
        # durable state (no controller database allowed)
        "sqlite3",
        "shelve",
        "pickle",
        "dbm",
    }
)

#: Words that indicate credentials/secrets leaking into source.
_FORBIDDEN_SOURCE_MARKERS: tuple[str, ...] = (
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "credential",
)


def _import_roots(tree: ast.Module) -> set[str]:
    """Collect top-level module roots imported anywhere in a module."""
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module is not None:
                roots.add(node.module.split(".")[0])
    return roots


def _package_sources() -> list[Path]:
    return sorted((REPO_ROOT / "controller").glob("*.py"))


def _test_sources() -> list[Path]:
    return sorted((REPO_ROOT / "tests").glob("*.py"))


class ForbiddenSurfaceTests(unittest.TestCase):
    def test_controller_package_imports_no_forbidden_modules(self) -> None:
        for path in _package_sources():
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                roots = _import_roots(tree)
                self.assertEqual(roots & _FORBIDDEN_IMPORT_ROOTS, set())

    def test_controller_package_uses_only_stdlib_and_itself(self) -> None:
        """No third-party runtime dependency is introduced by CTRL-001."""
        allowed = set(sys.stdlib_module_names) | {"controller"}
        for path in _package_sources():
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                roots = _import_roots(tree)
                self.assertEqual(roots - allowed, set())

    def test_tests_use_only_stdlib_and_the_controller_package(self) -> None:
        """The suite runs with zero external dependencies or services."""
        allowed = set(sys.stdlib_module_names) | {"controller", "tests"}
        for path in _test_sources():
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                roots = _import_roots(tree)
                self.assertEqual(roots - allowed, set())

    def test_no_credential_markers_in_controller_sources(self) -> None:
        for path in _package_sources():
            with self.subTest(module=path.name):
                source = path.read_text(encoding="utf-8").lower()
                for marker in _FORBIDDEN_SOURCE_MARKERS:
                    self.assertNotIn(marker, source)

    def test_no_network_calls_in_controller_sources(self) -> None:
        """No direct function calls to forbidden machinery either."""
        banned_names = {"urlopen", "socket", "create_connection", "Popen", "run", "check_output"}
        allowed = set(sys.stdlib_module_names) | {"controller"}
        for path in _package_sources():
            with self.subTest(module=path.name):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                        self.assertNotIn(node.func.id, banned_names)
                    if isinstance(node, ast.Attribute):
                        self.assertNotIn(node.attr, {"urlopen", "Popen", "system"})
                roots = _import_roots(tree)
                self.assertEqual(roots - allowed, set())


if __name__ == "__main__":
    unittest.main()
