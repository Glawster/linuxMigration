"""ADR 011: core modules never import the GUI modules."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "pdfFiler"
CORE = ("cabinet", "dates", "filing", "learned", "naming", "rules", "suggest", "text")
GUI = {"pdfFiler.dialogs", "pdfFiler.preview", "pdfFiler.inbox"}


def test_coreModulesDoNotImportGui() -> None:
    for name in CORE:
        tree = ast.parse((PACKAGE / f"{name}.py").read_text())
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not imported & GUI, f"{name}.py imports {imported & GUI}"
