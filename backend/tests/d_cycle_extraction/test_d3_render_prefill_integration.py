"""Wave 4 / Task 5.2 —— D3 预收账款 render 四表库接入（宁缺勿造）+ Tier A 预设集成测试.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 1.1, 1.2, 2.3, 3.1, 3.4, 7.1, 7.2, 7.4 / Property 8, 9, 11)

D3 的 KEY BOUNDARY（宁缺勿造 R3.4）：
  * D3-1 审定表按**双区块固定分类**（一、按性质：固定资产/土地使用权/合同不成立对价/其他；
    二、按账龄段），未审数由 **D3-2 明细（`D3-det-rows`）经 cross-sheet 按性质/账龄 SUMIF
    聚合**填入（`useD3Adjudication` natureAggregation/agingByKey），**非从 tb_balance 叶子直接填**
    → trial_balance/tb_balance 的 2203 **只有科目总额、无「性质/账龄」组合维度** → 无法把 TB
    干净映射到分类行 → D3 render **不返回 adjudication_prefill**（不臆造）。
  * 因此 D3 render 输出在开关开/关时**逐字节等价**（Property 9 天然成立，零回归）。
  * 唯一可从四表库干净取的是 `D3-adj-trial-balance-amount`（2203 总额，TB↔账龄合计核对标量，
    同为 D3-2 明细核对标量）—— 注册为 Tier A **可编辑**公式 `TB('2203','期末余额')`。
  * D3-2 明细四表库归集（`importFromAuxBalance` → /d3/import-aux-balance）为前端既有一键取数，
    本 render 不介入、不冲突（手工优先精度）。

全部 fake async session（不触发 conftest 真实 SQLite create_all）；直接调 render / router 协程。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.routers import wp_formula as router_mod
from app.routers.wp_render_strategies import _d3_prepaid_accounts as d3
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

_D3_ANCHOR = "D3-adj-trial-balance-amount"
_D3_EXPRESSION = "TB('2203','期末余额')"

# D3 render characterization 基线顶层键
_BASELINE_KEYS = {
    "sections",
    "adjudication_config",
    "project_context",
    "disclosure_visibility",
    "responses_snapshot",
}


def _run(coro):
    return asyncio.run(coro)


def _reset_presets_cache(monkeypatch):
    monkeypatch.setattr(presets_mod, "_cached_mtime", None, raising=False)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由（D3 render：checklist / projects）
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
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id: str, conclusion: str = "", remark: str = ""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _ctx(db):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=2025,
        business_category="general",
        classification=SimpleNamespace(sheet_name="预收账款审定表D3-1"),
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


def _enable_flag(monkeypatch):
    monkeypatch.setattr(d3.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable_flag(monkeypatch):
    monkeypatch.setattr(d3.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


# ---------------------------------------------------------------------------
# Property 9: 灰度零回归 + 宁缺勿造（开关开/关 D3 render 逐字节等价，无 prefill）
# ---------------------------------------------------------------------------


def test_flag_off_baseline_keys_no_prefill(monkeypatch):
    """开关关闭（默认）→ 顶层键 == 基线，无 adjudication_prefill。"""
    _disable_flag(monkeypatch)
    result = _run(d3.render(_ctx(_session())))
    assert set(result.keys()) == _BASELINE_KEYS
    assert "adjudication_prefill" not in result


def test_flag_on_still_no_prefill_ningquewuzao(monkeypatch):
    """开关开启 → D3 **仍不返回** adjudication_prefill（宁缺勿造 R3.4，性质/账龄固定分类不可从 TB 拆分）。"""
    _enable_flag(monkeypatch)
    result = _run(d3.render(_ctx(_session())))
    assert "adjudication_prefill" not in result
    assert set(result.keys()) == _BASELINE_KEYS


def test_flag_on_off_byte_equivalent(monkeypatch):
    """开关开/关 D3 render 输出逐字节等价（D3 不新增任何键，Property 9 天然成立）。"""
    checklist = [
        _checklist_row("D3-adj-nature-other-currentUnadjusted", remark="123456"),
        _checklist_row("D3-det-rows", remark='[{"customerName":"甲"}]'),
    ]
    _disable_flag(monkeypatch)
    off = _run(d3.render(_ctx(_session(checklist_rows=list(checklist)))))
    _enable_flag(monkeypatch)
    on = _run(d3.render(_ctx(_session(checklist_rows=list(checklist)))))
    assert off == on
    assert "adjudication_prefill" not in on


# ---------------------------------------------------------------------------
# 宁缺勿造：不臆造分类行未审；与既有 D3-det-rows / D3-adj-trial-balance-amount 共存不冲突
# ---------------------------------------------------------------------------


def test_no_fabricated_classification_rows(monkeypatch):
    """D3 render 不新增任何 D3-adj-(nature|aging)-* 分类未审键到 responses_snapshot。"""
    _enable_flag(monkeypatch)
    result = _run(d3.render(_ctx(_session())))
    snapshot = result["responses_snapshot"]
    fabricated = [
        k
        for k in snapshot
        if k.startswith("D3-adj-nature-") or k.startswith("D3-adj-aging-")
    ]
    assert fabricated == [], "宁缺勿造：不得臆造审定表分类行未审数"


def test_coexist_with_existing_detail_and_tb_seed(monkeypatch):
    """既有 D3-det-rows（aux 导入）+ D3-adj-trial-balance-amount 原样透传，render 不覆盖。"""
    _enable_flag(monkeypatch)
    checklist = [
        _checklist_row("D3-adj-trial-balance-amount", remark="500000"),
        _checklist_row("D3-det-rows", remark='[{"customerName":"甲","priorUnadjusted":100}]'),
    ]
    result = _run(d3.render(_ctx(_session(checklist_rows=checklist))))
    snap = result["responses_snapshot"]
    assert snap["D3-adj-trial-balance-amount"]["remark"] == "500000"
    assert snap["D3-det-rows"]["remark"] == '[{"customerName":"甲","priorUnadjusted":100}]'


# ---------------------------------------------------------------------------
# Tier A：D3 预设双门 + GET extraction.tierA surface
# ---------------------------------------------------------------------------


def test_d3_preset_passes_both_gates(monkeypatch):
    """D3 预设 D3-adj-trial-balance-amount / TB('2203','期末余额') 通过锚点合法性 + 受支持函数双门。"""
    _reset_presets_cache(monkeypatch)
    presets = load_presets("D3")
    assert len(presets) == 1, "Task 5.2：D3 应有且仅有 1 条 Tier A 预设（2203 总额，宁缺勿造）"
    entry = presets[0]
    assert entry["anchor"] == _D3_ANCHOR
    assert entry["expression"] == _D3_EXPRESSION
    assert is_known_anchor("D3", entry["anchor"]) is True
    assert find_unsupported_formula_functions(entry["expression"]) == []


def test_resolve_effective_returns_d3_preset(monkeypatch):
    """无用户覆盖 → resolve_effective("D3") 返回该预设，source=preset。"""
    _reset_presets_cache(monkeypatch)
    db = _FormulaFakeSession(wp=_wp(), wp_code="D3", user_formulas=[])
    result = _run(resolve_effective(db, uuid4(), "D3", uuid4()))
    assert len(result) == 1
    b = result[0]
    assert b["anchor"] == _D3_ANCHOR
    assert b["expression"] == _D3_EXPRESSION
    assert b["sheet_name"] == "D3-1"
    assert b["source"] == SOURCE_PRESET
    assert b["tier"] == "A"


def test_resolve_effective_user_override_becomes_custom(monkeypatch):
    """用户同锚点覆盖 → source=custom（读时收敛 Property 5）。"""
    _reset_presets_cache(monkeypatch)
    wp = _wp()
    user = _wp_formula(_D3_ANCHOR, expression="TB('2203','期初余额')", wp=wp)
    db = _FormulaFakeSession(wp=wp, wp_code="D3", user_formulas=[user])
    result = _run(resolve_effective(db, wp.id, "D3", wp.project_id))
    assert len(result) == 1
    assert result[0]["source"] == SOURCE_CUSTOM
    assert result[0]["expression"] == "TB('2203','期初余额')"


def test_get_endpoint_surfaces_d3_preset_in_tier_a(monkeypatch):
    """flag ON + wp_code=D3：GET /formulas 的 extraction.tierA 含 D3-adj-trial-balance-amount。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D3", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" in resp
    ext = resp["extraction"]
    assert ext["wp_code"] == "D3"
    assert ext["enabled"] is True

    tier_a = {b["anchor"]: b for b in ext["tierA"]}
    assert _D3_ANCHOR in tier_a
    binding = tier_a[_D3_ANCHOR]
    assert binding["expression"] == _D3_EXPRESSION
    assert binding["source"] == SOURCE_PRESET
    assert binding["tier"] == "A"
    assert binding["value"] is None  # R5.6：GET 不逐条重求值


def test_get_endpoint_surfaces_d3_tier_b_provenance(monkeypatch):
    """flag ON + wp_code=D3：extraction.tierB 含 D3-2 归集溯源 + D3-1 宁缺勿造声明（只读）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D3", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    tier_b = resp["extraction"]["tierB"]
    anchors = {e["anchor"]: e for e in tier_b}
    assert "D3-det-rows" in anchors
    assert anchors["D3-det-rows"]["editable"] is False
    assert anchors["D3-det-rows"]["tier"] == "B"
    # D3-1 分类不填的诚实声明
    assert any("nature" in a or "aging" in a or "分类" in e.get("description", "") for a, e in anchors.items())


def test_flag_off_no_extraction_for_d3(monkeypatch):
    """flag OFF → 无 extraction（零回归 / R7.1）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D3", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    assert "extraction" not in resp


# ---------------------------------------------------------------------------
# Tier B 只读溯源（诚实登记 D3-2 归集 + D3-1 分类不填声明）
# ---------------------------------------------------------------------------


def test_tier_b_provenance_d3_honest():
    """tier_b_provenance("D3") 登记 D3-2 归集来源 + D3-1 分类不填声明，全部只读。"""
    entries = tier_b_provenance("D3")
    assert len(entries) == 2
    for e in entries:
        assert e["editable"] is False
        assert e["source"] == "prefill"
        assert e["tier"] == "B"
        assert e["value"] is None
    anchors = {e["anchor"] for e in entries}
    assert "D3-det-rows" in anchors
    assert any("nature" in a or "aging" in a for a in anchors)


# ---------------------------------------------------------------------------
# Formula-endpoint fake session（复用 test_d6_tier_a_preset 同款）
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


def _wp_formula(target_cell, *, expression, sheet_name="D3-1", wp=None):
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
