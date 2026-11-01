"""S10 交付闭合守卫：防止实现被后续整文件覆盖后清单仍假绿。"""
from __future__ import annotations

import ast
from pathlib import Path

from app.models.audit_log_models import AuditChainHead

_BACKEND = Path(__file__).resolve().parents[2]
_APP = _BACKEND / "app"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _function(path: Path, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in _tree(path).body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{path} 缺少函数 {name}")


def _calls(node: ast.AST) -> set[str]:
    result: set[str] = set()
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Name):
            result.add(child.func.id)
        elif isinstance(child.func, ast.Attribute):
            result.add(child.func.attr)
    return result


def test_chain_head_orm_contract_exists() -> None:
    table = AuditChainHead.__table__
    assert table.name == "audit_chain_head"
    assert set(table.columns.keys()) == {
        "chain_key", "tail_entry_id", "tail_hash", "entry_count", "updated_at"
    }
    assert table.primary_key.columns.keys() == ["chain_key"]


def test_helper_and_worker_use_single_chain_kernel() -> None:
    helper = _function(_APP / "services" / "audit_log_helper.py", "append_audit_log")
    worker = _function(_APP / "workers" / "audit_log_writer_worker.py", "_write_batch")
    assert "append_entry" in _calls(helper)
    assert "AuditLogEntry" not in _calls(helper)
    assert "write_batch" in _calls(worker)
    assert "AuditLogEntry" not in _calls(worker)


def test_worker_quarantine_and_health_are_live() -> None:
    worker_path = _APP / "workers" / "audit_log_writer_worker.py"
    health_path = _APP / "api" / "health.py"
    assert "_replay_quarantine" in {
        node.name for node in _tree(worker_path).body
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
    }
    health_query = _function(health_path, "_query_audit_chain_health")
    assert "quarantine_count" in _calls(health_query)
    health_check = _function(health_path, "health_check")
    assert any(
        isinstance(node, ast.Constant) and node.value == "quarantined_entries"
        for node in ast.walk(health_check)
    )


def test_verify_chain_router_is_registered_in_production() -> None:
    tree = _tree(_APP / "router_registry" / "system.py")
    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.routers.audit_logs"
        and any(alias.name == "router" and alias.asname == "audit_logs_router" for alias in node.names)
        for node in ast.walk(tree)
    )
    mounted = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "include_router" or not node.args:
            continue
        first = node.args[0]
        prefix = next((kw.value for kw in node.keywords if kw.arg == "prefix"), None)
        if (
            isinstance(first, ast.Name)
            and first.id == "audit_logs_router"
            and isinstance(prefix, ast.Constant)
            and prefix.value == "/api"
        ):
            mounted = True
            break
    assert imported and mounted


def test_verify_chain_tests_are_not_hidden_by_xfail() -> None:
    source = (_BACKEND / "tests" / "test_audit_log_enhanced.py").read_text(
        encoding="utf-8"
    )
    assert "verify-chain endpoint not registered" not in source
