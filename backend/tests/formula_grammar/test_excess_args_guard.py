"""S1 ADR-FGR-02 守卫：存量公式定义无多余参数。

扫描静态数据源中的所有公式，确认没有超过 ARITY 上限的函数调用。
存量多余参数 = 0 是切换求值期上限检查的前提。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]  # 仓库根
DATA = ROOT / "backend" / "data"


# 与 formula_arity.ARITY 同口径
ARITY_MAX: dict[str, int | None] = {
    "TB": 2, "SUM_TB": 2, "PREV": 3, "AUX": 4, "NOTE": 3, "WP": 3, "ADJ": 2,
    "ROW": 1, "SUM_ROW": 2, "REPORT": 2,
    "ABS": 1, "ROUND": 2, "MAX": None, "MIN": None, "IF": 3,
    "LEDGER": 3, "LEDGER_DETAIL": 3, "TB_AUX": 3, "COUNT_LEDGER": 2, "PLACEHOLDER": 1,
}

FUNC_RE = re.compile(r"([A-Z_]+)\s*\(([^)]*)\)")


def _count_args(args_str: str) -> int:
    if not args_str.strip():
        return 0
    return args_str.count(",") + 1


def _scan(source_name: str, formulas: list[tuple[str, str]]) -> list[dict]:
    violations = []
    for fid, formula in formulas:
        if not formula or not isinstance(formula, str):
            continue
        for m in FUNC_RE.finditer(formula):
            name = m.group(1)
            max_args = ARITY_MAX.get(name)
            if max_args is None:
                continue
            argc = _count_args(m.group(2))
            if argc > max_args:
                violations.append({
                    "source": source_name,
                    "id": fid,
                    "function": name,
                    "actual": argc,
                    "max": max_args,
                })
    return violations


class TestNoExcessArgsInStaticData:
    """静态数据源无多余参数。"""

    def test_push_rules(self):
        path = DATA / "formula_push_rules.json"
        if not path.exists():
            pytest.skip("formula_push_rules.json 不存在")
        rules = json.loads(path.read_text(encoding="utf-8"))
        formulas = []
        if isinstance(rules, list):
            for r in rules:
                expr = r.get("formula") or r.get("expression") or ""
                formulas.append((str(r.get("rule_id", "?")), expr))
        elif isinstance(rules, dict):
            for k, v in rules.items():
                expr = v.get("formula", "") if isinstance(v, dict) else (v if isinstance(v, str) else "")
                formulas.append((k, expr))
        violations = _scan("formula_push_rules.json", formulas)
        assert violations == [], f"推送规则有多余参数: {violations}"

    def test_prefill_mapping(self):
        path = DATA / "prefill_formula_mapping.json"
        if not path.exists():
            pytest.skip("prefill_formula_mapping.json 不存在")
        mapping = json.loads(path.read_text(encoding="utf-8"))
        formulas = []
        if isinstance(mapping, dict):
            for code, entries in mapping.items():
                if isinstance(entries, dict):
                    for cell, expr in entries.items():
                        if isinstance(expr, str):
                            formulas.append((f"{code}/{cell}", expr))
                        elif isinstance(expr, dict):
                            formulas.append((f"{code}/{cell}", expr.get("formula", "")))
                elif isinstance(entries, list):
                    for e in entries:
                        if isinstance(e, dict):
                            formulas.append((f"{code}/{e.get('cell', '?')}", e.get("formula", "")))
        violations = _scan("prefill_formula_mapping.json", formulas)
        assert violations == [], f"预填映射有多余参数: {violations}"

    def test_cross_account_rules(self):
        path = DATA / "cross_account_rules.json"
        if not path.exists():
            pytest.skip("cross_account_rules.json 不存在")
        rules = json.loads(path.read_text(encoding="utf-8"))
        formulas = []
        if isinstance(rules, list):
            for r in rules:
                for field in ("left_formula", "right_formula", "formula"):
                    expr = r.get(field, "")
                    if expr:
                        formulas.append((str(r.get("rule_id", "?")), expr))
        violations = _scan("cross_account_rules.json", formulas)
        assert violations == [], f"校对规则有多余参数: {violations}"
