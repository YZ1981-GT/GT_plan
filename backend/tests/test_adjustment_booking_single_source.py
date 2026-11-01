"""客户已入账排除判定的单一来源与路由接线守卫。"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AMOUNT = ROOT / "app/services/adjustment_amount_source.py"
TB = ROOT / "app/services/trial_balance_service.py"
SYSTEM = ROOT / "app/router_registry/system.py"


def _function(path: Path, name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == name)


def _called(function: ast.AST, name: str) -> bool:
    return any(
        isinstance(node, ast.Call)
        and ((isinstance(node.func, ast.Name) and node.func.id == name)
             or (isinstance(node.func, ast.Attribute) and node.func.attr == name))
        for node in ast.walk(function)
    )


def test_three_calculation_paths_call_one_treatment_predicate():
    targets = [
        _function(AMOUNT, "adj_net"),
        _function(AMOUNT, "adj_net_batch"),
        _function(TB, "recalc_adjustments"),
    ]
    assert all(_called(function, "effective_groups_clause") for function in targets)


def test_adj_readers_default_to_excluding_client_booked():
    for name in ("adj_net", "adj_net_batch"):
        function = _function(AMOUNT, name)
        defaults = {
            arg.arg: default
            for arg, default in zip(function.args.kwonlyargs, function.args.kw_defaults)
            if default is not None
        }
        value = defaults["exclude_client_booked"]
        assert isinstance(value, ast.Constant) and value.value is True


def test_scanner_distinguishes_good_and_missing_call():
    good = ast.parse("async def f():\n    q = q.where(await effective_groups_clause(db, A, project_id=p, year=y))\n")
    bad = ast.parse("async def f():\n    q = q.where(A.review_status == 'approved')\n")
    good_fn = next(node for node in ast.walk(good) if isinstance(node, ast.AsyncFunctionDef))
    bad_fn = next(node for node in ast.walk(bad) if isinstance(node, ast.AsyncFunctionDef))
    assert _called(good_fn, "effective_groups_clause")
    assert not _called(bad_fn, "effective_groups_clause")


def test_client_booking_router_is_explicitly_registered():
    tree = ast.parse(SYSTEM.read_text(encoding="utf-8-sig"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "adj_booking_router" in names
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.routers.adjustment_client_booking"
        for node in ast.walk(tree)
    )
