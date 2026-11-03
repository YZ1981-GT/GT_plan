"""ProcedureInstance 规范化身份的写入边界与 ORM/迁移契约守卫。"""
from __future__ import annotations

import ast
from pathlib import Path

import sqlalchemy as sa

from app.models.procedure_models import ProcedureInstance
from app.services.procedure_identity import (
    normalize_cycle,
    normalize_procedure_code,
    normalize_procedure_identity,
    normalize_wp_code,
)

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def test_identity_normalization_and_validation():
    identity = normalize_procedure_identity(" d ", " custom-1 ", " d2-1 ")
    assert (identity.audit_cycle, identity.procedure_code, identity.wp_code) == ("D", "CUSTOM-1", "D2-1")
    assert normalize_wp_code(None, fallback=" x-1 ") == "X-1"
    for fn, value in ((normalize_cycle, " "), (normalize_procedure_code, "")):
        try:
            fn(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{fn.__name__} 未拒绝空身份")


def _contains_call(function: ast.AST, name: str) -> bool:
    return any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name
               for node in ast.walk(function))


def test_all_production_procedure_instance_writers_use_identity_normalizer():
    found: list[tuple[str, str]] = []
    for path in APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for function in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            constructors = [n for n in ast.walk(function) if isinstance(n, ast.Call)
                            and isinstance(n.func, ast.Name) and n.func.id == "ProcedureInstance"]
            if constructors:
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                found.append((rel, function.name))
                assert _contains_call(function, "normalize_procedure_identity"), (
                    f"{rel}:{function.name} 构造 ProcedureInstance 却没走唯一规范化边界"
                )
    assert sorted(found) == [
        ("app/services/procedure_catalog.py", "ensure_supplement_rows"),
        ("app/services/procedure_service.py", "add_custom"),
        ("app/services/procedure_service.py", "init_from_templates"),
    ]


def test_orm_declares_canonical_checks_and_active_expression_unique_index():
    table = ProcedureInstance.__table__
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert set(checks) >= {
        "ck_procedure_instances_audit_cycle_canonical",
        "ck_procedure_instances_code_canonical",
        "ck_procedure_instances_wp_code_canonical",
    }
    index = next(i for i in table.indexes if i.name == "uq_procedure_instances_active_identity_norm")
    assert index.unique is True
    assert str(index.dialect_options["postgresql"]["where"]) == "is_deleted = false"
    expressions = [str(expr).lower() for expr in index.expressions]
    assert "project_id" in expressions[0]
    assert "upper" in expressions[1] and "trim" in expressions[1]
    assert "upper" in expressions[2] and "trim" in expressions[2]


def test_exact_read_boundaries_normalize_external_identity_inputs():
    cases = {
        "app/services/procedure_service.py": {
            "get_procedures": "normalize_cycle",
            "init_from_templates": "normalize_cycle",
            "add_custom": "normalize_procedure_identity",
        },
        "app/services/procedure_trim_service.py": {
            "is_scope_trimmed": "normalize_wp_code",
            "_resolve_scope": "normalize_wp_code",
            "reject_suggestions": "normalize_wp_code",
        },
        "app/services/wp_visibility/procedure_wp_resolver.py": {
            "_from_procedure_code": "normalize_procedure_code",
        },
        "app/services/wp_visibility/delegation_transaction.py": {
            "_lock_projection_instances": "normalize_wp_code",
        },
    }
    for rel, functions in cases.items():
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8-sig"), filename=rel)
        defs = {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for function, normalizer in functions.items():
            assert function in defs, f"{rel} 缺函数 {function}"
            assert _contains_call(defs[function], normalizer), f"{rel}:{function} 未调用 {normalizer}"
