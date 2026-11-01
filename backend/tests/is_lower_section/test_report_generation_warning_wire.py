"""S9 陈旧试算表 warning 的 API 回传契约（ADR-ISL-05）。"""
from __future__ import annotations

import ast
from pathlib import Path

from app.routers.reports import _generation_warnings

ROUTER = Path(__file__).resolve().parents[2] / "app" / "routers" / "reports.py"


def _results(warnings):
    return {
        "income_statement": [],
        "coverage_stats": {
            "by_type": {
                "income_statement": {"warnings": warnings},
            },
        },
    }


def test_extracts_only_stale_trial_balance_warning():
    result = _generation_warnings(_results([
        {"type": "formula_warning", "row_code": "IS-001", "message": "逐行提示"},
        {"type": "stale_trial_balance", "message": "试算表口径陈旧"},
        {"type": "dangling_row_ref", "message": "行引用悬空"},
    ]))
    assert result == [{"type": "stale_trial_balance", "message": "试算表口径陈旧"}]


def test_deduplicates_and_ignores_malformed_warning_entries():
    assert _generation_warnings(_results([
        {"type": "stale_trial_balance", "message": "  提示甲  "},
        {"type": "stale_trial_balance", "message": "提示甲"},
        {"type": "stale_trial_balance", "message": ""},
        None,
        "bad",
    ])) == [{"type": "stale_trial_balance", "message": "提示甲"}]


def test_missing_or_malformed_coverage_returns_empty():
    for value in ({}, {"coverage_stats": None}, {"coverage_stats": []},
                  {"coverage_stats": {"by_type": None}},
                  {"coverage_stats": {"by_type": {"income_statement": []}}}):
        assert _generation_warnings(value) == []


def test_generate_endpoint_returns_extracted_warnings():
    """AST 钉住生成端点的回执确实调用提取器；只测 helper 会漏掉「路由丢字段」的真实缺陷。"""
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    functions = {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    endpoint = functions["generate_reports"]
    returns = [node for node in ast.walk(endpoint) if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)]
    response = next(node.value for node in returns
                    if any(isinstance(key, ast.Constant) and key.value == "message" for key in node.value.keys))
    values = {key.value: value for key, value in zip(response.keys, response.values)
              if isinstance(key, ast.Constant) and isinstance(key.value, str)}
    warning_call = values.get("warnings")
    assert isinstance(warning_call, ast.Call), "生成端点没有返回 warnings 调用"
    assert isinstance(warning_call.func, ast.Name) and warning_call.func.id == "_generation_warnings"
    assert len(warning_call.args) == 1 and isinstance(warning_call.args[0], ast.Name)
    assert warning_call.args[0].id == "results", "warning 不是从本次引擎结果提取"
