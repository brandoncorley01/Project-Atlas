"""Regression: sports Search must not UnboundLocalError on _read_cache."""

from __future__ import annotations

import ast
from pathlib import Path


def _fetch_fn_node() -> ast.AsyncFunctionDef:
    path = Path(__file__).resolve().parents[1] / "app" / "services" / "fanduel_catalog.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "fetch_verified_markets_for_search":
            return node
    raise AssertionError("fetch_verified_markets_for_search not found")


def test_no_local_read_cache_import_in_search():
    """A local `from ... import _read_cache` shadows the module binding and breaks Search."""
    fn = _fetch_fn_node()
    shadowed: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name in {"_read_cache", "_write_cache", "_merge_cached_events"}:
                    shadowed.append(alias.name)
    assert shadowed == [], f"Local odds_api imports shadow module bindings: {shadowed}"


def test_module_imports_odds_cache_helpers():
    path = Path(__file__).resolve().parents[1] / "app" / "services" / "fanduel_catalog.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("odds_api"):
            imported.update(alias.name for alias in node.names)
    assert "_read_cache" in imported
    assert "_write_cache" in imported
    assert "_merge_cached_events" in imported
