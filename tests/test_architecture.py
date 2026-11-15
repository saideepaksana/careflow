import ast
from pathlib import Path

import pytest

from careflow.agents.tools import TOOLS, ToolSpec
from careflow.memory.manager import SemanticKey
from careflow.safety.memory_guard import is_clinical

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


REPOSITORY_WRITES = (
    "book_appointment",
    "cancel_appointment",
    "reschedule_appointment",
    "create_coordinator_task",
)


def repository_calls(path: Path) -> set[str]:
    return {
        node.attr
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "repository"
    }


@pytest.mark.parametrize("spec", TOOLS.values(), ids=list(TOOLS))
def test_tool_args_never_take_patient_id(spec: ToolSpec) -> None:
    assert "patient_id" not in spec.args_model.model_fields


def test_repository_writes_only_called_from_tools() -> None:
    callers = {
        str(path.relative_to(SRC))
        for path in SRC.rglob("*.py")
        if path.parent.name != "db" and repository_calls(path) & set(REPOSITORY_WRITES)
    }
    assert callers == {"agents/tools.py"}


def test_fastembed_only_in_model_modules() -> None:
    assert modules_importing("fastembed") == {"memory/embeddings.py", "knowledge/rerank.py"}


def test_careplan_answerer_has_no_tools_or_database() -> None:
    imports = imported_modules(SRC / "agents" / "careplan.py")
    assert not [
        name for name in imports if name.startswith(("careflow.agents.tools", "careflow.db"))
    ]


@pytest.mark.parametrize("key", list(SemanticKey))
def test_semantic_keys_are_not_clinical(key: SemanticKey) -> None:
    assert not is_clinical(key.value.replace("_", " "))
