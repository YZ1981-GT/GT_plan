"""Wave 5 / Task 6 —— D4/D5/D7 render 四表库接入（宁缺勿造）+ Tier A 预设集成测试.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 1.1, 1.2, 2.3, 3.1, 3.4, 7.1, 7.2, 7.4 / Property 8, 9, 11)

三循环 KEY BOUNDARY（宁缺勿造 R3.4）：
  * D4 营业收入（6001/6051，收入类 occurrence）：D4-1 审定表主营/其他明细行**按产品/项目**，
    由 D4-2/D4-3 明细（序时账 6001 贷方按产品×月归集）SUMIF 派生。TB 6001/6051 只有科目
    总额、无产品维度 → render **不返回 adjudication_prefill**。Tier A = D4-1-adj-tb-6001 /
    D4-1-adj-tb-6051（TB('6001','审定数') / TB('6051','审定数')，收入 audited_amount 存审定发生额）。
  * D5 应收款项融资（1124/balance）：D5-1 审定表两固定分类行（应收票据/应收账款），由 D5-2
    按类别 SUMIF 派生。TB 1124 无类别拆分 → render **不返回 adjudication_prefill**。
    Tier A = D5-1-tb-amount（TB('1124','期末余额')）。
  * D7 合同负债（2205/balance，双区块同 D3）：D7-1 审定表按性质/账龄，由 D7-2 SUMIF 派生。
    TB 2205 无性质/账龄维度 → render **不返回 adjudication_prefill**。
    Tier A = D7-1-adj-aging-trial-balance-currentAudited（TB('2205','期末余额')）。
  * 因此三循环 render 输出在开关开/关时**逐字节等价**（Property 9 天然成立，零回归）。

全部 fake async session（不触发 conftest 真实 SQLite create_all）；直接调 render / router 协程。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import settings
from app.routers import wp_formula as router_mod
from app.routers.wp_render_strategies import _d4_operating_revenue as d4
from app.routers.wp_render_strategies import _d5_receivables_financing as d5
from app.routers.wp_render_strategies import _d7_contract_liabilities as d7
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_PRESET,
    load_presets,
    resolve_effective,
    tier_b_provenance,
)
from app.services.wp_formula_eval_service import find_unsupported_formula_functions

# 各循环 render characterization 基线顶层键
_D4_BASELINE_KEYS = {"sections", "visible_groups", "project_context", "responses_snapshot"}
_D5_BASELINE_KEYS = {
    "sections",
    "adjudication_config",
    "detail_columns",
    "fv_columns",
    "project_context",
    "disclosure_visibility",
    "responses_snapshot",
}
_D7_BASELINE_KEYS = {
    "sections",
    "adjudication_config",
    "project_context",
    "disclosure_visibility",
    "responses_snapshot",
}

# 每循环 (module, baseline_keys, sheet_name, 分类行前缀集)
_CYCLES = {
    "D4": (d4, _D4_BASELINE_KEYS, "营业收入审定表D4-1", ("D4-1-adj-rows",)),
    "D5": (d5, _D5_BASELINE_KEYS, "应收款项融资审定表D5-1", ("D5-1-adj-notes-receivable-", "D5-1-adj-accounts-receivable-")),
    "D7": (d7, _D7_BASELINE_KEYS, "合同负债审定表D7-1", ("D7-1-adj-nature-", "D7-1-adj-aging-")),
}


def _run(coro):
    return asyncio.run(coro)


def _reset_presets_cache(monkeypatch):
    monkeypatch.setattr(presets_mod, "_cached_mtime", None, raising=False)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由（checklist / projects / trial_balance / related_party）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows=None, one=None):
        self._rows = rows or []
        self._one = one

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one


class _FakeSession:
    def __init__(self, *, checklist_rows=None, project_row=None):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "from projects" in s or "projects where" in s:
            return _FakeResult(one=self.project_row)
        if "trial_balance" in s:
            # D5 fetchone().amount / D7 fetchone().amt —— 返回 0（无数据，不影响 prefill 决策）
            return _FakeResult(one=SimpleNamespace(amount=0, amt=0))
        if "related_party_registry" in s:
            return _FakeResult(rows=[])
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id: str, conclusion: str = "", remark: str = ""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _ctx(db, sheet_name):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name=sheet_name),
    )


def _session(*, checklist_rows=None):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
            applicable_standards="listed",
        ),
    )


def _enable_flag(monkeypatch, mod):
    monkeypatch.setattr(mod.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable_flag(monkeypatch, mod):
    monkeypatch.setattr(mod.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


# ---------------------------------------------------------------------------
# Property 9: 灰度零回归 + 宁缺勿造（开关开/关 render 逐字节等价，无 prefill）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wp_code", ["D4", "D5", "D7"])
def test_flag_off_baseline_keys_no_prefill(monkeypatch, wp_code):
    """开关关闭（默认）→ 顶层键 == 基线，无 adjudication_prefill。"""
    mod, baseline, sheet_name, _ = _CYCLES[wp_code]
    _disable_flag(monkeypatch, mod)
    result = _run(mod.render(_ctx(_session(), sheet_name)))
    assert set(result.keys()) == baseline
    assert "adjudication_prefill" not in result


@pytest.mark.parametrize("wp_code", ["D4", "D5", "D7"])
def test_flag_on_still_no_prefill_ningquewuzao(monkeypatch, wp_code):
    """开关开启 → **仍不返回** adjudication_prefill（宁缺勿造 R3.4，分类/明细行 SUMIF 不可从 TB 拆分）。"""
    mod, baseline, sheet_name, _ = _CYCLES[wp_code]
    _enable_flag(monkeypatch, mod)
    result = _run(mod.render(_ctx(_session(), sheet_name)))
    assert "adjudication_prefill" not in result
    assert set(result.keys()) == baseline


@pytest.mark.parametrize("wp_code", ["D4", "D5", "D7"])
def test_flag_on_off_byte_equivalent(monkeypatch, wp_code):
    """开关开/关 render 输出逐字节等价（不新增任何键，Property 9 天然成立）。"""
    mod, _baseline, sheet_name, _ = _CYCLES[wp_code]
    checklist = [
        _checklist_row(f"{wp_code}-1-adj-note", remark="123456"),
        _checklist_row(f"{wp_code}-2-rows", remark='[{"itemName":"甲"}]'),
    ]
    _disable_flag(monkeypatch, mod)
    off = _run(mod.render(_ctx(_session(checklist_rows=list(checklist)), sheet_name)))
    _enable_flag(monkeypatch, mod)
    on = _run(mod.render(_ctx(_session(checklist_rows=list(checklist)), sheet_name)))
    assert off == on
    assert "adjudication_prefill" not in on


@pytest.mark.parametrize("wp_code", ["D4", "D5", "D7"])
def test_no_fabricated_classification_rows(monkeypatch, wp_code):
    """render 不新增任何审定表分类/明细行未审键到 responses_snapshot（宁缺勿造）。"""
    mod, _baseline, sheet_name, prefixes = _CYCLES[wp_code]
    _enable_flag(monkeypatch, mod)
    result = _run(mod.render(_ctx(_session(), sheet_name)))
    snapshot = result["responses_snapshot"]
    fabricated = [k for k in snapshot if any(k.startswith(p) for p in prefixes)]
    assert fabricated == [], f"{wp_code} 宁缺勿造：不得臆造审定表分类/明细行未审数"


# ---------------------------------------------------------------------------
# D4：两 Tier A 标量（6001 主营 / 6051 其他，收入 audited_amount = 审定发生额）
# ---------------------------------------------------------------------------


def test_d4_presets_two_scalars_pass_gates(monkeypatch):
    """D4 预设 = 2 条（6001/6051），均通过锚点合法性 + 受支持函数双门。"""
    _reset_presets_cache(monkeypatch)
    presets = load_presets("D4")
    assert len(presets) == 2, "Task 6.1：D4 应有 2 条 Tier A 预设（6001 主营 + 6051 其他）"
    by_anchor = {p["anchor"]: p for p in presets}
    assert by_anchor["D4-1-adj-tb-6001"]["expression"] == "TB('6001','审定数')"
    assert by_anchor["D4-1-adj-tb-6051"]["expression"] == "TB('6051','审定数')"
    for p in presets:
        assert is_known_anchor("D4", p["anchor"]) is True
        assert find_unsupported_formula_functions(p["expression"]) == []


def test_d4_resolve_effective_returns_two_presets(monkeypatch):
    """无用户覆盖 → resolve_effective("D4") 返回 2 条预设，source=preset。"""
    _reset_presets_cache(monkeypatch)
    db = _FormulaFakeSession(wp=_wp(), wp_code="D4", user_formulas=[])
    result = _run(resolve_effective(db, uuid4(), "D4", uuid4()))
    assert len(result) == 2
    for b in result:
        assert b["source"] == SOURCE_PRESET
        assert b["tier"] == "A"
        assert b["sheet_name"] == "D4-1"


def test_d4_get_endpoint_surfaces_both_tier_a(monkeypatch):
    """flag ON + wp_code=D4：GET /formulas 的 extraction.tierA 含两个 6001/6051 标量。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D4", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    ext = resp["extraction"]
    assert ext["wp_code"] == "D4"
    assert ext["enabled"] is True
    tier_a = {b["anchor"]: b for b in ext["tierA"]}
    assert "D4-1-adj-tb-6001" in tier_a
    assert "D4-1-adj-tb-6051" in tier_a
    assert tier_a["D4-1-adj-tb-6001"]["value"] is None  # R5.6：GET 不逐条重求值


# ---------------------------------------------------------------------------
# D5 / D7：单 Tier A 标量
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wp_code,anchor,expression,sheet",
    [
        ("D5", "D5-1-tb-amount", "TB('1124','期末余额')", "D5-1"),
        ("D7", "D7-1-adj-aging-trial-balance-currentAudited", "TB('2205','期末余额')", "D7-1"),
    ],
)
def test_single_scalar_preset_passes_gates(monkeypatch, wp_code, anchor, expression, sheet):
    """D5/D7 预设 = 1 条 TB 标量，通过锚点合法性 + 受支持函数双门。"""
    _reset_presets_cache(monkeypatch)
    presets = load_presets(wp_code)
    assert len(presets) == 1, f"{wp_code} 应有且仅有 1 条 Tier A 预设（TB 总额，宁缺勿造）"
    entry = presets[0]
    assert entry["anchor"] == anchor
    assert entry["expression"] == expression
    assert entry["sheet_name"] == sheet
    assert is_known_anchor(wp_code, anchor) is True
    assert find_unsupported_formula_functions(expression) == []


@pytest.mark.parametrize(
    "wp_code,anchor,expression",
    [
        ("D5", "D5-1-tb-amount", "TB('1124','期末余额')"),
        ("D7", "D7-1-adj-aging-trial-balance-currentAudited", "TB('2205','期末余额')"),
    ],
)
def test_single_scalar_resolve_effective(monkeypatch, wp_code, anchor, expression):
    """无用户覆盖 → resolve_effective 返回该预设 source=preset；用户同锚点覆盖 → custom。"""
    _reset_presets_cache(monkeypatch)
    db = _FormulaFakeSession(wp=_wp(), wp_code=wp_code, user_formulas=[])
    result = _run(resolve_effective(db, uuid4(), wp_code, uuid4()))
    assert len(result) == 1
    assert result[0]["anchor"] == anchor
    assert result[0]["expression"] == expression
    assert result[0]["source"] == SOURCE_PRESET

    # 用户覆盖
    _reset_presets_cache(monkeypatch)
    wp = _wp()
    user = _wp_formula(anchor, expression="TB('9999','期初余额')", wp=wp)
    db2 = _FormulaFakeSession(wp=wp, wp_code=wp_code, user_formulas=[user])
    result2 = _run(resolve_effective(db2, wp.id, wp_code, wp.project_id))
    assert len(result2) == 1
    assert result2[0]["source"] == SOURCE_CUSTOM
    assert result2[0]["expression"] == "TB('9999','期初余额')"


# ---------------------------------------------------------------------------
# Tier B 只读溯源（诚实登记 X-2 归集 + X-1 分类不填声明）+ GET 端点透出
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wp_code", ["D4", "D5", "D7"])
def test_tier_b_provenance_honest(wp_code):
    """tier_b_provenance 登记 明细归集来源 + 审定表分类不填声明，全部只读。"""
    entries = tier_b_provenance(wp_code)
    assert len(entries) == 2
    for e in entries:
        assert e["editable"] is False
        assert e["source"] == "prefill"
        assert e["tier"] == "B"
        assert e["value"] is None
    anchors = {e["anchor"] for e in entries}
    # 明细归集条目
    assert any("-2-rows" in a or "-2-" in a for a in anchors)
    # 审定表分类不填声明条目
    assert any("adj" in a for a in anchors)


@pytest.mark.parametrize("wp_code", ["D4", "D5", "D7"])
def test_get_endpoint_surfaces_tier_b(monkeypatch, wp_code):
    """flag ON：extraction.tierB 含明细归集溯源（只读）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code=wp_code, user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    tier_b = resp["extraction"]["tierB"]
    assert len(tier_b) == 2
    for e in tier_b:
        assert e["editable"] is False
        assert e["tier"] == "B"


@pytest.mark.parametrize("wp_code", ["D4", "D5", "D7"])
def test_flag_off_no_extraction(monkeypatch, wp_code):
    """flag OFF → 无 extraction（零回归 / R7.1）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code=wp_code, user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    assert "extraction" not in resp


# ---------------------------------------------------------------------------
# Formula-endpoint fake session（复用 test_d3 同款）
# ---------------------------------------------------------------------------


class _FormulaFakeResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FormulaFakeSession:
    def __init__(self, *, wp, wp_code, user_formulas=None):
        self.wp = wp
        self.wp_code = wp_code
        self.user_formulas = user_formulas or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "from wp_index" in s:
            return _FormulaFakeResult(scalar=self.wp_code)
        if "from wp_formula" in s:
            return _FormulaFakeResult(rows=self.user_formulas)
        if "from working_paper" in s:
            if "is_deleted" in s:
                return _FormulaFakeResult(scalar=self.wp)
            return _FormulaFakeResult(scalar=self.wp.project_id)
        return _FormulaFakeResult()

    async def rollback(self):
        return None


def _wp():
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        wp_index_id=uuid4(),
        is_deleted=False,
        parsed_data={},
    )


def _wp_formula(target_cell, *, expression, sheet_name="D5-1", wp=None):
    return SimpleNamespace(
        id=uuid4(),
        project_id=(wp.project_id if wp else uuid4()),
        wp_id=(wp.id if wp else uuid4()),
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        category=None,
        description="用户覆盖",
        formula_type="auto_calc",
        refs=None,
        issue_description=None,
        hint_text=None,
        last_computed_at=None,
        created_by=None,
        created_at=None,
        updated_at=None,
    )


def _user():
    return SimpleNamespace(id=uuid4(), username="tester")
