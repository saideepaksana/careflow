import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "careflow"
INTAKE_FORBIDDEN = ("careflow.db", "careflow.mcp_servers", "careflow.knowledge", "careflow.memory")


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def modules_importing(prefix: str) -> set[str]:
    return {
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if any(name.split(".")[0] == prefix for name in imported_modules(path))
    }


def test_intake_has_no_data_or_tool_access() -> None:
    imports = imported_modules(SRC / "agents" / "intake.py")
    assert not [name for name in imports if name.startswith(INTAKE_FORBIDDEN)]


def test_database_driver_only_in_db_package() -> None:
    assert all(path.startswith("db/") for path in modules_importing("psycopg"))


def test_litellm_only_in_gateway() -> None:
    assert modules_importing("litellm") == {"llm/gateway.py"}


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=lambda path: path.name)
def test_no_print_in_library_code(path: Path) -> None:
    if path.name == "__main__.py" and path.parent.name == "evaluation":
        return
    calls = [
        node
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print"
    ]
    assert not calls
