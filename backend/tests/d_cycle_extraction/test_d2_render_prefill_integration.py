"""Wave 4 / Task 5.1 —— D2 render 四表库接入（宁缺勿造）+ Tier A 预设集成测试.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 1.1, 2.3, 3.4, 7.1, 7.2 / Property 8, 9, 11)

D2 的 KEY BOUNDARY（宁缺勿造 R3.4）：
  * D2-1 审定表按**信用风险组合方式**固定三分类行（单项计提/账龄组合/客户类型组合），
    而 trial_balance/tb_balance 的 1122 应收账款**只有科目总额、无信用风险组合维度**
    → 无法把 TB 干净映射到分类行 → D2 render **不返回 adjudication_prefill**（不臆造）。
  * 因此 D2 render 输出在开关开/关时**逐字节等价**（Property 9 天然成立，零回归）。
  * 唯一可从四表库干净取的是 `D2-adj-tb-amount`（1122 总额）——已由前端
    `useD2FormData.loadAll` seed，且注册为 Tier A **可编辑**公式 `TB('1122','期末余额')`。
  * D2-2 明细四表库归集（`importFromAuxBalance` / `importPostPaymentFromLedger`）为前端
    既有一键取数，本 render 不介入、不冲突（手工优先精度）。

覆盖：
  * Property 9（灰度零回归）：开关关/开 D2 render 顶层键与彼此逐字节等价，均无
    `adjudication_prefill`、无新增 `D2-adj-*` 分类键。
  * 宁缺勿造：即便 responses_snapshot 已含 D2-adj-tb-amount / D2-detail-rows（既有 seed /
    aux 导入），render 原样透传、不覆盖、不新增分类行未审（手工优先精度共存）。
  * Tier A：D2 预设 `D2-adj-tb-amount → TB('1122','期末余额')` 通过双门（合法锚点 +
    受支持函数）+ GET /formulas 的 `extraction.tierA` surface（source=preset）。
  * Tier B 只读溯源：`tier_b_provenance("D2")` 诚实登记 D2-2 归集 + 声明 D2-1 分类不填。

全部 fake async session（不触发 conftest 真实 SQLite create_all）；直接调 render / router
协程。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.routers import wp_formula as router_mod
from app.routers.wp_render_strategies import _d2_accounts_receivable as d2
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

_D2_ANCHOR = "D2-adj-tb-amount"
_D2_EXPRESSION = "TB('1122','期末余额')"

# D2 render characterization 基线顶层键
_BASELINE_KEYS = {"sheet_name", "project_context", "responses_snapshot"}


def _run(coro):
    return asyncio.run(coro)


def _reset_presets_cache(monkeypatch):
    monkeypatch.setattr(presets_mod, "_cached_mtime", None, raising=False)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由（D2 render：checklist / projects / related_party）
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
    def __init__(self, *, checklist_rows=None, project_row=None, rp_rows=None):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.rp_rows = rp_rows or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _FakeResult(rows=self.rp_rows)
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
        classification=SimpleNamespace(sheet_name="应收账款审定表D2-1"),
    )


def _session(*, checklist_rows=None):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
        ),
        rp_rows=[SimpleNamespace(name="关联方甲")],
    )


def _enable_flag(monkeypatch):
    monkeypatch.setattr(d2.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable_flag(monkeypatch):
    monkeypatch.setattr(d2.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


# ---------------------------------------------------------------------------
# Property 9: 灰度零回归 + 宁缺勿造（开关开/关 D2 render 逐字节等价，无 prefill）
# ---------------------------------------------------------------------------


def test_flag_off_baseline_keys_no_prefill(monkeypatch):
    """开关关闭（默认）→ 顶层键 == 基线，无 adjudication_prefill。"""
    _disable_flag(monkeypatch)
    result = _run(d2.render(_ctx(_session())))
    assert set(result.keys()) == _BASELINE_KEYS
    assert "adjudication_prefill" not in result


def test_flag_on_still_no_prefill_ningquewuzao(monkeypatch):
    """开关开启 → D2 **仍不返回** adjudication_prefill（宁缺勿造 R3.4，分类行不可从 TB 拆分）。"""
    _enable_flag(monkeypatch)
    result = _run(d2.render(_ctx(_session())))
    assert "adjudication_prefill" not in result
    assert set(result.keys()) == _BASELINE_KEYS


def test_flag_on_off_byte_equivalent(monkeypatch):
    """开关开/关 D2 render 输出逐字节等价（D2 不新增任何键，Property 9 天然成立）。"""
    checklist = [
        _checklist_row("D2-adj-individual-current-unadjusted", remark="123456"),
        _checklist_row("D2-detail-rows", remark='[{"customerName":"甲"}]'),
    ]
    _disable_flag(monkeypatch)
    off = _run(d2.render(_ctx(_session(checklist_rows=list(checklist)))))
    _enable_flag(monkeypatch)
    on = _run(d2.render(_ctx(_session(checklist_rows=list(checklist)))))
    assert off == on
    assert "adjudication_prefill" not in on


# ---------------------------------------------------------------------------
# 宁缺勿造：不臆造分类行未审；与既有 D2-adj-tb-amount / D2-detail-rows 共存不冲突
# ---------------------------------------------------------------------------


def test_no_fabricated_classification_rows(monkeypatch):
    """D2 render 不新增任何 D2-adj-{individual|aging|customer-type}-* 分类未审键。"""
    _enable_flag(monkeypatch)
    result = _run(d2.render(_ctx(_session())))
    snapshot = result["responses_snapshot"]
    fabricated = [
        k
        for k in snapshot
        if k.startswith("D2-adj-individual-")
        or k.startswith("D2-adj-aging-")
        or k.startswith("D2-adj-customer-type-")
    ]
    assert fabricated == [], "宁缺勿造：不得臆造审定表分类行未审数"


def test_coexist_with_existing_tb_amount_and_detail_seed(monkeypatch):
    """既有 D2-adj-tb-amount（前端 seed）+ D2-detail-rows（aux 导入）原样透传，render 不覆盖。

    手工优先精度：render 只读快照回传，不重写 tb-amount / 明细行。
    """
    _enable_flag(monkeypatch)
    checklist = [
        _checklist_row("D2-adj-tb-amount", remark="9182572.99"),
        _checklist_row("D2-detail-rows", remark='[{"customerName":"甲","priorUnadjusted":100}]'),
    ]
    result = _run(d2.render(_ctx(_session(checklist_rows=checklist))))
    snap = result["responses_snapshot"]
    assert snap["D2-adj-tb-amount"]["remark"] == "9182572.99"
    assert snap["D2-detail-rows"]["remark"] == '[{"customerName":"甲","priorUnadjusted":100}]'


# ---------------------------------------------------------------------------
# Tier A：D2 预设双门 + GET extraction.tierA surface
# ---------------------------------------------------------------------------


def test_d2_preset_passes_both_gates(monkeypatch):
    """D2 预设 D2-adj-tb-amount / TB('1122','期末余额') 通过锚点合法性 + 受支持函数双门。"""
    _reset_presets_cache(monkeypatch)
    presets = load_presets("D2")
    assert len(presets) == 1
    entry = presets[0]
    assert entry["anchor"] == _D2_ANCHOR
    assert entry["expression"] == _D2_EXPRESSION
    assert is_known_anchor("D2", entry["anchor"]) is True
    assert find_unsupported_formula_functions(entry["expression"]) == []


def test_resolve_effective_returns_d2_preset(monkeypatch):
    """无用户覆盖 → resolve_effective("D2") 返回该预设，source=preset。"""
    _reset_presets_cache(monkeypatch)
    db = _FormulaFakeSession(wp=_wp(), wp_code="D2", user_formulas=[])
    result = _run(resolve_effective(db, uuid4(), "D2", uuid4()))
    assert len(result) == 1
    b = result[0]
    assert b["anchor"] == _D2_ANCHOR
    assert b["expression"] == _D2_EXPRESSION
    assert b["sheet_name"] == "D2-1"
    assert b["source"] == SOURCE_PRESET
    assert b["tier"] == "A"


def test_resolve_effective_user_override_becomes_custom(monkeypatch):
    """用户同锚点覆盖 → source=custom（读时收敛 Property 5）。"""
    _reset_presets_cache(monkeypatch)
    wp = _wp()
    user = _wp_formula(_D2_ANCHOR, expression="TB('1122','期初余额')", wp=wp)
    db = _FormulaFakeSession(wp=wp, wp_code="D2", user_formulas=[user])
    result = _run(resolve_effective(db, wp.id, "D2", wp.project_id))
    assert len(result) == 1
    assert result[0]["source"] == SOURCE_CUSTOM
    assert result[0]["expression"] == "TB('1122','期初余额')"


def test_get_endpoint_surfaces_d2_preset_in_tier_a(monkeypatch):
    """flag ON + wp_code=D2：GET /formulas 的 extraction.tierA 含 D2-adj-tb-amount。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D2", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" in resp
    ext = resp["extraction"]
    assert ext["wp_code"] == "D2"
    assert ext["enabled"] is True

    tier_a = {b["anchor"]: b for b in ext["tierA"]}
    assert _D2_ANCHOR in tier_a
    binding = tier_a[_D2_ANCHOR]
    assert binding["expression"] == _D2_EXPRESSION
    assert binding["source"] == SOURCE_PRESET
    assert binding["tier"] == "A"
    assert binding["value"] is None  # R5.6：GET 不逐条重求值


def test_get_endpoint_surfaces_d2_tier_b_provenance(monkeypatch):
    """flag ON + wp_code=D2：extraction.tierB 含 D2-2 归集溯源 + D2-1 宁缺勿造声明（只读）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D2", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    tier_b = resp["extraction"]["tierB"]
    anchors = {e["anchor"]: e for e in tier_b}
    assert "D2-detail-rows" in anchors
    assert anchors["D2-detail-rows"]["editable"] is False
    assert anchors["D2-detail-rows"]["tier"] == "B"
    # D2-1 分类不填的诚实声明
    assert any("individual" in a or "分类" in e.get("description", "") for a, e in anchors.items())


def test_flag_off_no_extraction_for_d2(monkeypatch):
    """flag OFF → 无 extraction（零回归 / R7.1）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    wp = _wp()
    db = _FormulaFakeSession(wp=wp, wp_code="D2", user_formulas=[])
    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    assert "extraction" not in resp


# ---------------------------------------------------------------------------
# Tier B 只读溯源（诚实登记 D2-2 归集 + D2-1 不填声明）
# ---------------------------------------------------------------------------


def test_tier_b_provenance_d2_honest(monkeypatch):
    """tier_b_provenance("D2") 登记 D2-2 归集来源 + D2-1 分类不填声明，全部只读。"""
    entries = tier_b_provenance("D2")
    assert len(entries) == 2
    for e in entries:
        assert e["editable"] is False
        assert e["source"] == "prefill"
        assert e["tier"] == "B"
        assert e["value"] is None
    anchors = {e["anchor"] for e in entries}
    assert "D2-detail-rows" in anchors
    # D2-1 分类行不填的诚实声明存在
    assert any("individual" in a for a in anchors)


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


def _wp_formula(target_cell, *, expression, sheet_name="D2-1", wp=None):
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
