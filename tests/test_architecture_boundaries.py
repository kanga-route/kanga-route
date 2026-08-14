"""Executable dependency rules that keep integrations out of the engine."""

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "kanga_route"


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_engine_cannot_import_adapters_or_product_clients():
    forbidden = (
        "kanga_route.adapters",
        "kanga_route.crm",
        "kanga_route.mail",
        "kanga_route.web",
    )
    for path in (PACKAGE_ROOT / "engine").glob("*.py"):
        violations = [name for name in _imports(path) if name.startswith(forbidden)]
        assert violations == [], f"{path.name} imports integration code: {violations}"


def test_engine_source_contains_no_product_names():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PACKAGE_ROOT / "engine").glob("*.py")
    ).casefold()
    for product in ("hubspot", "postfix", "gmail", "microsoft graph"):
        assert product not in source


def test_shared_orchestration_contains_no_product_names():
    source = (PACKAGE_ROOT / "application" / "batch.py").read_text(
        encoding="utf-8"
    ).casefold()
    for product in ("hubspot", "postfix", "gmail", "microsoft graph"):
        assert product not in source


def test_mail_advisory_cannot_import_the_live_engine():
    path = PACKAGE_ROOT / "application" / "mail_advisory.py"
    violations = [
        name for name in _imports(path) if name.startswith("kanga_route.engine")
    ]
    assert violations == []
