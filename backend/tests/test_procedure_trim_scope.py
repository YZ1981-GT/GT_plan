# -*- coding: utf-8 -*-
"""程序裁剪「科目有无数据」判定单测（spec procedure-trim-generation-delegation-chain 需求 1）。

覆盖：
- 科目口径：四表单一来源覆盖、H3 不再落到 1503/1504、映射表主条目只补规格缺失的底稿
- 逐项目定位：两种标准科目表写法（2006 版码 / 平台标准表码）都按名称定位；名称优先于同号码
- 有数据口径：期末 / 期初 / 本期发生 / 客户科目未映射；全零与科目表没有该科目 ⇒ 无数据；
  科目表不可用且无兜底码 ⇒ 无法判定
- 对外接口：试算表查询失败 fail-safe、返回结构
"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from app.services import procedure_trim_scope as pts
from app.services import trim_subject_scope as tss
from app.services.four_table.leaf_aggregation import LeafRow
from app.services.four_table.semantic_account_resolver import ChartRow, SemanticAccountSlot


def _std(code: str, name: str) -> ChartRow:
    return ChartRow(account_code=code, account_name=name, source="standard")


def _cli(code: str, name: str) -> ChartRow:
    return ChartRow(account_code=code, account_name=name, source="client")


def _eval(scope, *, client=(), standard=(), mapping=None, tb=(), occ=None, leaves=()):
    return tss.evaluate_scope(
        scope,
        client_rows=list(client),
        standard_rows=list(standard),
        mapping=dict(mapping or {}),
        tb_rows=list(tb),
        occurrence=dict(occ or {}),
        leaves=list(leaves),
    )


# ── 科目口径 ────────────────────────────────────────────────────────────────


def test_scopes_cover_four_table_specs_and_only_data_driven_cycles():
    scopes = tss.subject_scopes()
    for code in ("D2", "E1", "F2", "G6", "H3", "H8", "I2", "I6", "J1", "K1", "L1", "M4", "M9", "N3"):
        assert code in scopes, code
        assert scopes[code].source == tss.SCOPE_SOURCE_FOUR_TABLE, code
    assert all(code[:1] in tss.DATA_DRIVEN_CYCLES for code in scopes)


def test_h3_scope_is_investment_property_not_1503_1504():
    """回归：旧补充码表把 H3 写成 1503/1504（可供出售金融资产 / 债权投资）。"""
    h3 = tss.subject_scopes()["H3"]
    names = {n for s in h3.slots for n in s.names}
    codes = {c for s in h3.slots for c in s.fallback_standard_codes}
    assert any("投资性房地产" in n for n in names)
    assert "1521" in codes
    assert not ({"1503", "1504"} & codes)


def _code_string_constants(module) -> list[str]:
    """模块里**代码**用到的字符串常量（剔除模块 / 类 / 函数 docstring —— 文档提及旧文件名不算读取）。"""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings
    ]


def test_old_static_code_tables_are_not_read():
    """旧判定读两份静态码表；新判定只读四表规格与 wp_account_mapping.json（按 AST 判，不看注释）。"""
    for module in (tss, pts):
        consts = _code_string_constants(module)
        assert not any("procedure_trim_account_map" in c for c in consts), module.__name__
        assert not any("account_package_registry" in c for c in consts), module.__name__
    assert any("wp_account_mapping.json" in c for c in _code_string_constants(tss))


def test_mapping_primary_entries_outside_data_driven_cycles_are_ignored(tmp_path, monkeypatch):
    """映射表里 A/B/C/S 底稿的主条目不进科目口径（这些循环不按单科目余额裁剪）。

    现有映射表恰好没有这类主条目（去掉过滤的变异在真数据上等价），用临时文件钉住过滤本身。
    """
    path = tmp_path / "wp_account_mapping.json"
    path.write_text(json.dumps({"mappings": [
        {"wp_code": "A1", "is_primary": True, "account_name": "货币资金", "account_codes": ["1001"]},
        {"wp_code": "S3", "is_primary": True, "account_name": "其他", "account_codes": ["1"]},
        {"wp_code": "h9", "is_primary": True, "account_name": "某资产", "account_codes": ["1999"]},
        {"wp_code": "H10", "is_primary": False, "account_name": "非主条目"},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(tss, "_WP_MAPPING_PATH", path)
    assert set(tss._wp_mapping_primary_entries()) == {"H9"}


# ── 逐项目定位：两种科目表写法 ───────────────────────────────────────────────

H3 = tss.subject_scopes()["H3"]
M2 = tss.subject_scopes()["M2"]
L1 = tss.subject_scopes()["L1"]


def test_h3_with_balance_is_with_data_regression_anhui():
    """重药安徽：1521 审定 7,689,744.44 曾被判「无数据」自动裁剪。"""
    ev = _eval(
        H3,
        standard=[_std("1521", "投资性房地产"), _std("1525", "投资性房地产累计折旧")],
        tb=[tss.TbRow("1521", "投资性房地产", 7689744.44, 0), tss.TbRow("1525", "投资性房地产累计折旧", 3074163.37, 0)],
    )
    assert ev.state == tss.STATE_WITH_DATA
    assert ev.closing >= 7689744.44


def test_equity_located_by_name_in_both_chart_dialects():
    """实收资本：一类项目标准码 4001，一类映射进平台标准表 3001（4001 = 生产成本）。"""
    dialect_2006 = _eval(
        M2, standard=[_std("4001", "实收资本")], tb=[tss.TbRow("4001", "实收资本", 150000000, 150000000)]
    )
    assert dialect_2006.state == tss.STATE_WITH_DATA

    platform_chart = [_std("3001", "实收资本"), _std("4001", "生产成本")]
    paid_in_zero = _eval(
        M2, standard=platform_chart,
        tb=[tss.TbRow("3001", "实收资本", 0, 0), tss.TbRow("4001", "生产成本", 880000, 0)],
    )
    # 名称已定位到 3001 ⇒ 不因同号码 4001（生产成本）有余额而误判有数据
    assert paid_in_zero.state == tss.STATE_NO_DATA
    paid_in = _eval(M2, standard=platform_chart, tb=[tss.TbRow("3001", "实收资本", 5000000, 5000000)])
    assert paid_in.state == tss.STATE_WITH_DATA


def test_opening_balance_only_counts_as_data():
    """当年还清的借款：期初 7700 万、期末 0 ⇒ 有数据（旧判定只看期末，会裁掉）。"""
    ev = _eval(L1, standard=[_std("2001", "短期借款")], tb=[tss.TbRow("2001", "短期借款", 0, 77000000)])
    assert ev.state == tss.STATE_WITH_DATA
    assert ev.opening == 77000000


def test_period_activity_only_counts_as_data():
    ev = _eval(
        L1, standard=[_std("2001", "短期借款")],
        tb=[tss.TbRow("2001", "短期借款", 0, 0)], occ={"2001": (1000000.0, 1000000.0)},
    )
    assert ev.state == tss.STATE_WITH_DATA


def test_client_account_unmapped_still_counts_with_flag():
    """客户科目表有「投资性房地产」且余额表有数，但未映射进试算表 ⇒ 有数据并注明。"""
    ev = _eval(
        H3,
        client=[_cli("1521", "投资性房地产")],
        mapping={},
        tb=[],
        leaves=[LeafRow(account_code="1521.01", account_name="房屋", closing=100.0)],
    )
    assert ev.state == tss.STATE_WITH_DATA
    assert ev.client_unmapped is True


def test_multi_name_slot_unions_all_candidate_accounts():
    """存货槽候选名「存货 / 材料采购 / 原材料 / 库存商品」：材料采购为 0、库存商品有数 ⇒ 有数据。

    回归：四表定位「只取第一个命中的名字」会定位到材料采购，把重药安徽存货判成无数据。
    """
    f2 = tss.subject_scopes()["F2"]
    standard = [_std("1401", "材料采购"), _std("1403", "原材料"), _std("1406", "库存商品"), _std("1416", "存货跌价准备")]
    ev = _eval(
        f2, standard=standard,
        tb=[tss.TbRow("1401", "材料采购", 0, 0), tss.TbRow("1406", "库存商品", 159109974.32, 201669114.92)],
    )
    assert ev.state == tss.STATE_WITH_DATA
    located = {c for s in ev.slots for c in s.standard_codes}
    assert {"1401", "1406"} <= located


def test_located_but_all_zero_is_no_data():
    ev = _eval(H3, standard=[_std("1521", "投资性房地产")], tb=[tss.TbRow("1521", "投资性房地产", 0, 0)])
    assert ev.state == tss.STATE_NO_DATA


def test_account_absent_from_project_chart_is_no_data():
    ev = _eval(H3, standard=[_std("1601", "固定资产")], tb=[tss.TbRow("1601", "固定资产", 100, 100)])
    assert ev.state == tss.STATE_NO_DATA
    assert "没有" in ev.reason


def test_no_chart_and_no_fallback_is_unknown():
    scope = tss.SubjectScope("D9", (SemanticAccountSlot(key="gross", names=("某科目",)),), "test", "某科目")
    ev = _eval(scope, tb=[tss.TbRow("1001", "库存现金", 1, 1)])
    assert ev.state == tss.STATE_UNKNOWN


def test_no_chart_uses_bare_fallback_codes():
    scope = tss.SubjectScope(
        "D9", (SemanticAccountSlot(key="gross", names=("某科目",), fallback_standard_codes=("1122",)),), "test", "某科目"
    )
    ev = _eval(scope, tb=[tss.TbRow("112201", "应收账款-甲", 10, 0)])
    assert ev.state == tss.STATE_WITH_DATA


def test_client_to_standard_and_reverse_follow_mapping():
    mapping = {"1525": "1521", "1521": "1521", "1521.01": "1521", "4001.05": "4001"}
    assert tss.client_to_standard(["1521"], mapping) == ["1521"]
    assert set(tss.standard_to_client(["1521"], mapping)) == {"1521", "1525"}


# ── 对外接口 ────────────────────────────────────────────────────────────────


def test_resolve_failsafe_when_trial_balance_unavailable(monkeypatch):
    async def _boom(db, pid, year):
        raise tss.TrialBalanceUnavailable("db down")

    monkeypatch.setattr(pts, "evaluate_subjects", _boom)
    out = asyncio.run(pts.resolve_subject_data_availability(object(), uuid4(), 2025))
    assert out["tb_empty"] is True
    assert out["subject_no_data"] == [] and out["subject_with_data"] == []
    assert "error" in out


def test_resolve_shapes_states(monkeypatch):
    def _ev(code, state):
        return tss.SubjectEvidence(wp_code=code, state=state, reason="", scope_source="t")

    async def _fake(db, pid, year):
        return tss.SubjectAvailability(
            tb_empty=False,
            cycles_with_data=["H"],
            evidence={"H3": _ev("H3", "with_data"), "H4": _ev("H4", "no_data"), "J9": _ev("J9", "unknown")},
        )

    monkeypatch.setattr(pts, "evaluate_subjects", _fake)
    out = asyncio.run(pts.resolve_subject_data_availability(object(), uuid4(), 2025))
    assert out["subject_with_data"] == ["H3"]
    assert out["subject_no_data"] == ["H4"]
    assert out["subject_unknown"] == ["J9"]
    assert out["cycles_with_data"] == ["H"]
    assert set(out["evidence"]) == {"H3", "H4", "J9"}
