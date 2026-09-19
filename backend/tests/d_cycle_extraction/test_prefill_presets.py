"""Wave 0 / Task 1.3 —— Tier B prefill + Tier A presets 收敛单测.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/

覆盖：
  * **Property 1**：`build_d_adjudication_prefill` 只取叶子科目防双算（R1.4）。
  * **Property 4**：无子科目 → 空列表；查询异常 → 空列表（fail-open，R1.6/R4.4）。
  * **Property 5**：`resolve_effective` 读时收敛，每锚点唯一，禁用 > 用户 custom > 预设；
    预设未落库不丢失（R3.3/R5.4/R5.5）。
  * 顺带：occurrence 模式、跳零/无名、Property 8 复用（未知锚点丢弃）。

测试用 fake async session（不依赖真实 PG / SQLite）：
  * prefill：monkeypatch `get_active_filter` 隔离叶子/跳零逻辑，fake session 只回主 SELECT 行。
  * presets：monkeypatch `load_presets` 注入预设，fake session 回 WpFormula 列表。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import sqlalchemy as sa

from app.services.d_cycle_extraction import prefill as prefill_mod
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.prefill import (
    MODE_BALANCE,
    MODE_OCCURRENCE,
    build_d_adjudication_prefill,
)
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
    resolve_effective,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async session
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchall(self):
        return self._rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _FakeTbSession:
    """prefill 用：execute 恒回预置的 tb 汇总行（labels: code/name/opening/closing/debit/credit）。"""

    def __init__(self, rows=None, *, raise_on_execute=False):
        self._rows = rows or []
        self._raise = raise_on_execute

    async def execute(self, stmt, params=None):
        if self._raise:
            raise RuntimeError("boom")
        return _FakeResult(rows=self._rows)

    async def rollback(self):
        return None


class _FakeFormulaSession:
    """presets 用：execute 回预置 WpFormula 列表（供 scalars().all()）。"""

    def __init__(self, formulas=None, *, raise_on_execute=False):
        self._formulas = formulas or []
        self._raise = raise_on_execute

    async def execute(self, stmt, params=None):
        if self._raise:
            raise RuntimeError("boom")
        return _FakeResult(rows=self._formulas)


def _tb_row(code, name, *, opening=0.0, closing=0.0, debit=0.0, credit=0.0):
    return SimpleNamespace(
        code=code, name=name, opening=opening, closing=closing, debit=debit, credit=credit
    )


def _ctx(db):
    return SimpleNamespace(db=db, project_id=uuid4(), year=2025)


def _patch_active_filter(monkeypatch):
    async def _fake_filter(db, table, project_id, year, **kw):
        return sa.true()
    monkeypatch.setattr(prefill_mod, "get_active_filter", _fake_filter)


def _fake_formula(target_cell, *, expression="TB('1141','期末余额')",
                  sheet_name="D6-1", category=None, description="", formula_type="auto_calc"):
    return SimpleNamespace(
        target_cell=target_cell,
        expression=expression,
        sheet_name=sheet_name,
        category=category,
        description=description,
        formula_type=formula_type,
    )


# ---------------------------------------------------------------------------
# Property 1: 只取叶子防双算
# ---------------------------------------------------------------------------


def test_property1_leaf_only_excludes_rollup(monkeypatch):
    """中间级 1141.01 与其子 1141.01.01 同时存在时，只取叶子 1141.01.01（防双算）。"""
    _patch_active_filter(monkeypatch)
    rows = [
        _tb_row("1141.01", "合同资产-中间级", closing=1000.0, opening=800.0),
        _tb_row("1141.01.01", "合同资产-明细", closing=1000.0, opening=800.0),
    ]
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession(rows)), account_prefix="1141", mode=MODE_BALANCE
    ))
    assert len(result) == 1
    assert result[0]["code"] == "1141.01.01"
    # 合计不含 rollup 双计
    assert sum(r["closing_balance"] for r in result) == 1000.0


def test_property1_multiple_independent_leaves_all_kept(monkeypatch):
    """多个互不为前缀的叶子科目全部保留。"""
    _patch_active_filter(monkeypatch)
    rows = [
        _tb_row("1141.01", "甲", closing=100.0),
        _tb_row("1141.02", "乙", closing=200.0),
        _tb_row("1141.03", "丙", closing=300.0),
    ]
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession(rows)), account_prefix="1141", mode=MODE_BALANCE
    ))
    assert {r["code"] for r in result} == {"1141.01", "1141.02", "1141.03"}
    # 降序（按 abs(closing)）
    assert [r["code"] for r in result] == ["1141.03", "1141.02", "1141.01"]


def test_skip_zero_and_no_name(monkeypatch):
    """零余额与无名称子科目被跳过（R1.4）。"""
    _patch_active_filter(monkeypatch)
    rows = [
        _tb_row("1141.01", "有效", closing=500.0),
        _tb_row("1141.02", "零余额", closing=0.0, opening=0.0),
        _tb_row("1141.03", "", closing=999.0),  # 无名称
    ]
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession(rows)), account_prefix="1141", mode=MODE_BALANCE
    ))
    assert len(result) == 1
    assert result[0]["code"] == "1141.01"


def test_occurrence_mode_returns_debit_credit(monkeypatch):
    """occurrence 模式（D4 收入）返回 debit/credit 发生额字段。"""
    _patch_active_filter(monkeypatch)
    rows = [
        _tb_row("6001.01", "主营收入", debit=10.0, credit=5000.0),
        _tb_row("6001.02", "零发生", debit=0.0, credit=0.0),
    ]
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession(rows)), account_prefix="6001", mode=MODE_OCCURRENCE
    ))
    assert len(result) == 1
    assert result[0]["code"] == "6001.01"
    assert result[0]["debit_amount"] == 10.0
    assert result[0]["credit_amount"] == 5000.0
    assert "opening_balance" not in result[0]


def test_invalid_mode_returns_empty(monkeypatch):
    _patch_active_filter(monkeypatch)
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession([_tb_row("1141.01", "甲", closing=1.0)])),
        account_prefix="1141", mode="bogus",
    ))
    assert result == []


# ---------------------------------------------------------------------------
# Property 4: 无数据 → 空；查询异常 → 空（fail-open）
# ---------------------------------------------------------------------------


def test_property4_no_subaccounts_returns_empty(monkeypatch):
    _patch_active_filter(monkeypatch)
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession([])), account_prefix="1141", mode=MODE_BALANCE
    ))
    assert result == []


def test_property4_query_error_fails_open_empty(monkeypatch):
    _patch_active_filter(monkeypatch)
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession(raise_on_execute=True)),
        account_prefix="1141", mode=MODE_BALANCE,
    ))
    assert result == []


def test_empty_prefix_returns_empty(monkeypatch):
    _patch_active_filter(monkeypatch)
    result = _run(build_d_adjudication_prefill(
        _ctx(_FakeTbSession([])), account_prefix="", mode=MODE_BALANCE
    ))
    assert result == []


# ---------------------------------------------------------------------------
# Property 5: 读时收敛（禁用 > 用户 custom > 预设；预设未落库不丢失）
# ---------------------------------------------------------------------------


def _patch_presets(monkeypatch, wp_code, bindings):
    def _fake_load(code):
        return [dict(b) for b in bindings] if code == wp_code else []
    monkeypatch.setattr(presets_mod, "load_presets", _fake_load)


def _preset_binding(anchor, *, expression="TB('1141','期末余额')", sheet_name="D6-1"):
    return {
        "wp_code": "D6", "sheet_name": sheet_name, "anchor": anchor,
        "expression": expression, "formula_type": "auto_calc",
        "description": "预设", "source": SOURCE_PRESET, "tier": "A",
    }


def test_property5_preset_only_survives(monkeypatch):
    """无用户覆盖时预设仍出现（预设未落库不丢失），source=preset。"""
    # D6-1-tb-amount 是真实已知锚点
    _patch_presets(monkeypatch, "D6", [_preset_binding("D6-1-tb-amount")])
    result = _run(resolve_effective(_FakeFormulaSession([]), uuid4(), "D6", uuid4()))
    assert len(result) == 1
    assert result[0]["anchor"] == "D6-1-tb-amount"
    assert result[0]["source"] == SOURCE_PRESET


def test_property5_custom_overrides_preset(monkeypatch):
    """同锚点用户 custom 覆盖预设，source=custom，表达式为用户值。"""
    _patch_presets(monkeypatch, "D6", [_preset_binding("D6-1-tb-amount")])
    user = _fake_formula("D6-1-tb-amount", expression="SUM_TB('1141~1403','期末余额')")
    result = _run(resolve_effective(_FakeFormulaSession([user]), uuid4(), "D6", uuid4()))
    assert len(result) == 1
    assert result[0]["source"] == SOURCE_CUSTOM
    assert result[0]["expression"] == "SUM_TB('1141~1403','期末余额')"


def test_property5_disabled_marker_category(monkeypatch):
    """用户 category='__disabled__' → source=disabled（禁用优先）。"""
    _patch_presets(monkeypatch, "D6", [_preset_binding("D6-1-tb-amount")])
    user = _fake_formula("D6-1-tb-amount", category="__disabled__")
    result = _run(resolve_effective(_FakeFormulaSession([user]), uuid4(), "D6", uuid4()))
    assert len(result) == 1
    assert result[0]["source"] == SOURCE_DISABLED


def test_property5_disabled_marker_empty_expression(monkeypatch):
    """用户空表达式 → 视为禁用，source=disabled。"""
    _patch_presets(monkeypatch, "D6", [_preset_binding("D6-1-tb-amount")])
    user = _fake_formula("D6-1-tb-amount", expression="   ")
    result = _run(resolve_effective(_FakeFormulaSession([user]), uuid4(), "D6", uuid4()))
    assert len(result) == 1
    assert result[0]["source"] == SOURCE_DISABLED


def test_property5_each_anchor_unique(monkeypatch):
    """每锚点唯一：多个预设 + 用户，锚点集合不重复。"""
    _patch_presets(monkeypatch, "D6", [
        _preset_binding("D6-1-tb-amount"),
        _preset_binding("D6-1-note-conclusion", expression="TB('1141','期末余额')"),
    ])
    user = _fake_formula("D6-1-tb-amount", expression="TB('1141','期初余额')")
    result = _run(resolve_effective(_FakeFormulaSession([user]), uuid4(), "D6", uuid4()))
    anchors = [b["anchor"] for b in result]
    assert len(anchors) == len(set(anchors))  # 无重复
    assert set(anchors) == {"D6-1-tb-amount", "D6-1-note-conclusion"}
    # 被覆盖的锚点用用户值
    tb = next(b for b in result if b["anchor"] == "D6-1-tb-amount")
    assert tb["source"] == SOURCE_CUSTOM


# ---------------------------------------------------------------------------
# Property 8 复用: 未知锚点丢弃（不静默写空）
# ---------------------------------------------------------------------------


def test_property8_unknown_preset_anchor_dropped(monkeypatch):
    """预设含未知锚点 → 丢弃（不出现在结果）。"""
    _patch_presets(monkeypatch, "D6", [
        _preset_binding("D6-1-tb-amount"),         # 已知
        _preset_binding("D6-1-made-up-anchor"),    # 未知 → 丢弃
    ])
    result = _run(resolve_effective(_FakeFormulaSession([]), uuid4(), "D6", uuid4()))
    assert {b["anchor"] for b in result} == {"D6-1-tb-amount"}


def test_property8_unknown_user_anchor_dropped(monkeypatch):
    """用户公式含未知锚点 → 丢弃。"""
    _patch_presets(monkeypatch, "D6", [])
    user_known = _fake_formula("D6-1-tb-amount")
    user_unknown = _fake_formula("D6-1-bogus-field")
    result = _run(resolve_effective(
        _FakeFormulaSession([user_known, user_unknown]), uuid4(), "D6", uuid4()
    ))
    assert {b["anchor"] for b in result} == {"D6-1-tb-amount"}


def test_property5_user_read_error_falls_back_to_presets(monkeypatch):
    """读用户 wp_formula 异常 → 仅返回预设（fail-open，不崩）。"""
    _patch_presets(monkeypatch, "D6", [_preset_binding("D6-1-tb-amount")])
    result = _run(resolve_effective(
        _FakeFormulaSession(raise_on_execute=True), uuid4(), "D6", uuid4()
    ))
    assert {b["anchor"] for b in result} == {"D6-1-tb-amount"}


# ---------------------------------------------------------------------------
# load_presets: 最小/空 JSON 解析为 []
# ---------------------------------------------------------------------------


def test_load_presets_real_json_d6_tier_a(monkeypatch):
    """交付的 d_cycle_extraction_presets.json：D6 含单条 Tier A 预设；D2 含单条（Task 5.1）。

    读真实文件（非 monkeypatch），确认 D6 Tier A 预设 `D6-1-tb-amount` →
    `TB('1141','期末余额')`（Task 4.3）与 D2 Tier A 预设 `D2-adj-tb-amount` →
    `TB('1122','期末余额')`（Task 5.1，宁缺勿造：仅 1122 总额标量可编辑，分类行不注册）；
    未登记/空码仍解析为 []。
    """
    # 清除 mtime 缓存，确保读到最新文件内容（其它测试可能已 monkeypatch load_presets 之外
    # 触发过缓存；此处直接强制重载）。
    monkeypatch.setattr(presets_mod, "_cached_mtime", None, raising=False)
    from app.services.d_cycle_extraction.presets import load_presets

    d6 = load_presets("D6")
    assert len(d6) == 1
    entry = d6[0]
    assert entry["anchor"] == "D6-1-tb-amount"
    assert entry["expression"] == "TB('1141','期末余额')"
    assert entry["sheet_name"] == "D6-1"
    assert entry["formula_type"] == "auto_calc"
    assert entry["source"] == SOURCE_PRESET
    assert entry["tier"] == "A"

    d2 = load_presets("D2")
    assert len(d2) == 1
    d2_entry = d2[0]
    assert d2_entry["anchor"] == "D2-adj-tb-amount"
    # 净额口径（原值 1122 − 坏账准备 1231-02）：源模板 D2-1 比的是「三、应收账款净值」，
    # `report_config` BS-006 soe_standalone 公式同此。取原值会产生假差异（D1 同款已实测）。
    assert d2_entry["expression"] == "TB('1122','期末余额') - TB('1231-02','期末余额')"
    assert d2_entry["sheet_name"] == "D2-1"
    assert d2_entry["source"] == SOURCE_PRESET
    assert d2_entry["tier"] == "A"

    assert load_presets("D9") == []  # 未登记
    assert load_presets("") == []
