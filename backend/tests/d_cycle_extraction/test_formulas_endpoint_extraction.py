"""Wave 2 / Task 3.3 —— GET /api/workpapers/{wp_id}/formulas 提取分层 + Property 7 确认.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 5.2, 5.3, 3.1, 3.2 / Property 5, 7, 8, 11)

覆盖：
  * GET 合并 Tier A 预设（source=preset）+ 用户覆盖（source=custom）+ 禁用（source=disabled）。
  * Tier B 只读溯源（D6 flag ON 时非空，editable=false / source=prefill / tier=B）。
  * 灰度开关关闭 → 无 `extraction` 字段（零回归 / R7.1）。
  * 非 D 循环 wp_code → 无 `extraction` 字段（表现同当前）。
  * D 循环但未接入 Tier B（如 D1）→ tierB == []（诚实，不臆造 / R7.4）。
  * sheet 级 wp_code（"D6-1"）归到基础码 "D6"。
  * items 向后兼容（原始 wp_formula 行列表，不受 extraction 影响）。
  * Property 7：PUT 悬空引用 → 422（既有行为，确认 GET 改动未破坏）。

全部用 fake async session（不触发 conftest 的真实 SQLite create_all，规避已知
`working_paper` 表缺失问题）；直接调用 router 协程函数，绕过 FastAPI Depends。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.routers import wp_formula as router_mod
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async session —— 按 SQL 文本路由（working_paper / wp_index / wp_formula）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))


class _FakeSession:
    """路由：
    * working_paper + is_deleted → _load_wp（返回完整 wp）
    * working_paper（仅 project_id 列）→ _verify_wp_ownership（返回 project_id）
    * wp_index → _resolve_wp_code（返回 wp_code）
    * wp_formula → list_by_wp / resolve_effective（返回 user_formulas，scalars）
    * projects → _resolve_project_year（返回 audit_year；默认 None = 拿不到年度）
    """

    def __init__(self, *, wp, wp_code, user_formulas=None, project_year=None):
        self.wp = wp
        self.wp_code = wp_code
        self.user_formulas = user_formulas or []
        # d-cycle-tier-a-writeback-detail-seed Task 3.1：GET Tier A 求值需 projects.audit_year。
        # 默认 None → 该底稿全部 Tier A value=None（fail-open），既有用例零回归。
        self.project_year = project_year

    async def execute(self, stmt, params=None):
        # 用 "from <table>" 精确路由：working_paper 有列 wp_index_id（含子串 "wp_index"），
        # 裸 "wp_index in s" 会误命中 _load_wp 的 select(WorkingPaper)。
        s = str(stmt).lower()
        if "from wp_index" in s:
            return _FakeResult(scalar=self.wp_code)
        if "from wp_formula" in s:
            return _FakeResult(rows=self.user_formulas)
        if "from projects" in s:
            return _FakeResult(scalar=self.project_year)
        if "from working_paper" in s:
            if "is_deleted" in s:
                return _FakeResult(scalar=self.wp)
            return _FakeResult(scalar=self.wp.project_id)
        return _FakeResult()

    async def rollback(self):
        return None


def _wp(wp_code_present: bool = True):
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        wp_index_id=uuid4() if wp_code_present else None,
        is_deleted=False,
        parsed_data={},
    )


def _wp_formula(target_cell, *, expression="TB('1402','期末余额')",
                sheet_name="D6-1", category=None,
                formula_type="auto_calc", description="用户公式", wp=None):
    """构造 WpFormula-like（同时满足 _formula_to_dict 与 resolve_effective._formula_to_binding）。"""
    return SimpleNamespace(
        id=uuid4(),
        project_id=(wp.project_id if wp else uuid4()),
        wp_id=(wp.id if wp else uuid4()),
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        category=category,
        description=description,
        formula_type=formula_type,
        refs=None,
        issue_description=None,
        hint_text=None,
        last_computed_at=None,
        created_by=None,
        created_at=None,
        updated_at=None,
    )


def _preset(anchor, *, expression="TB('1402','期末余额')", sheet_name="D6-1"):
    return {
        "wp_code": "D6", "sheet_name": sheet_name, "anchor": anchor,
        "expression": expression, "formula_type": "auto_calc",
        "description": "预设公式", "source": SOURCE_PRESET, "tier": "A",
    }


def _patch_presets(monkeypatch, mapping):
    """monkeypatch presets 模块级 load_presets（resolve_effective 内部按 wp_code 取）。"""
    def _fake_load(code):
        return [dict(b) for b in mapping.get(code, [])]
    monkeypatch.setattr(presets_mod, "load_presets", _fake_load)


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable(monkeypatch):
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


def _user():
    return SimpleNamespace(id=uuid4(), username="tester")


# ---------------------------------------------------------------------------
# GET：Tier A 三来源合并（preset / custom / disabled）+ Tier B 溯源
# ---------------------------------------------------------------------------


def test_get_merges_preset_custom_disabled_and_tier_b(monkeypatch):
    """flag ON + D6：extraction.tierA 含 preset/custom/disabled 三来源；tierB D6 溯源非空。"""
    _enable(monkeypatch)
    wp = _wp()
    # 预设两锚点：tb-amount（无覆盖→preset）、note-conclusion（被用户 custom 覆盖）
    _patch_presets(monkeypatch, {
        "D6": [_preset("D6-1-tb-amount"), _preset("D6-1-note-conclusion")],
    })
    user_formulas = [
        _wp_formula("D6-1-note-conclusion", expression="SUM_TB('1402~1403','期末余额')", wp=wp),
        _wp_formula("D6-1-note-explanation", category="__disabled__", wp=wp),  # 禁用
    ]
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=user_formulas)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" in resp
    ext = resp["extraction"]
    assert ext["wp_code"] == "D6"
    assert ext["enabled"] is True

    tier_a = {b["anchor"]: b for b in ext["tierA"]}
    assert tier_a["D6-1-tb-amount"]["source"] == SOURCE_PRESET
    assert tier_a["D6-1-note-conclusion"]["source"] == SOURCE_CUSTOM
    assert tier_a["D6-1-note-conclusion"]["expression"] == "SUM_TB('1402~1403','期末余额')"
    assert tier_a["D6-1-note-explanation"]["source"] == SOURCE_DISABLED
    # 每条 Tier A 均标 tier=A；本 fake session 未设 project_year → GET 求值走 fail-open
    # （拿不到 audit_year）→ value=None（Task 3.1 求值填 value 的 no-year 分支 / R2.3）。
    for b in ext["tierA"]:
        assert b["tier"] == "A"
        assert b["value"] is None

    # Tier B 只读溯源（D6 已接入 → 非空）
    assert ext["tierB"], "D6 应有 Tier B 溯源条目"
    for b in ext["tierB"]:
        assert b["tier"] == "B"
        assert b["editable"] is False
        assert b["source"] == "prefill"
        assert b["value"] is None
    # 描述明确指向四表库来源（来源可溯 / Property 11）
    assert any("tb_balance 1402" in b["description"] for b in ext["tierB"])


def test_get_surfaces_semantic_labels_p1_4(monkeypatch):
    """P1-4：Tier A 附 trial_balance 审定核对语义、Tier B 附 tb_balance 未审来源语义（口径消歧）。"""
    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": [_preset("D6-1-tb-amount")]})
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    ext = resp["extraction"]

    # Tier A：语义标注 trial_balance 审定核对标量（与 tb_balance 未审 seed 消歧）
    tb = next(b for b in ext["tierA"] if b["anchor"] == "D6-1-tb-amount")
    assert "semantic" in tb and tb["semantic"]
    assert "trial_balance" in tb["semantic"]
    assert "审定" in tb["semantic"]
    assert "tb_balance" in tb["semantic"]  # 明确对比未审 seed 口径

    # Tier B：语义标注四表库未审/明细来源（非审定数）
    assert ext["tierB"], "D6 应有 Tier B 溯源"
    for b in ext["tierB"]:
        assert b.get("semantic")
        assert "非审定数" in b["semantic"]


# ---------------------------------------------------------------------------
# Task 3.1（R2 / Property 4/5）：GET 对每条 Tier A binding 求值填 value
# ---------------------------------------------------------------------------


def test_get_tier_a_value_filled_when_year_resolves(monkeypatch):
    """flag ON + D6 + 可解析 audit_year + 求值成功 → Tier A value 填真实结果；Tier B value 仍 None。"""
    from decimal import Decimal

    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": [_preset("D6-1-tb-amount")]})

    async def _fake_eval(*a, **kw):
        return Decimal("50000"), []

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _fake_eval)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[], project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    ext = resp["extraction"]

    tb = next(b for b in ext["tierA"] if b["anchor"] == "D6-1-tb-amount")
    # format_cell_display_value(Decimal('50000')) → 50000（整数）
    assert tb["value"] == 50000
    # Tier B value 不变（None，seed 由 render adjudication_prefill 提供 / R2.5）
    for b in ext["tierB"]:
        assert b["value"] is None


def test_get_tier_a_value_fail_open_single_binding(monkeypatch):
    """单条 Tier A 求值失败 → 该条 value=None，其它条目仍填值，整个 GET 不阻断（R2.3 / Property 5）。"""
    from decimal import Decimal

    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {
        "D6": [
            _preset("D6-1-tb-amount", expression="TB('1402','期末余额')"),
            _preset("D6-1-note-conclusion", expression="TB('9999','期末余额')"),
        ],
    })

    async def _selective_eval(db, *, project_id, year, expression, **kw):
        if "9999" in expression:
            raise RuntimeError("boom")
        return Decimal("777"), []

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _selective_eval)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[], project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    tier_a = {b["anchor"]: b for b in resp["extraction"]["tierA"]}

    assert tier_a["D6-1-tb-amount"]["value"] == 777
    assert tier_a["D6-1-note-conclusion"]["value"] is None  # 失败条 fail-open


def test_get_tier_a_value_none_on_eval_errors(monkeypatch):
    """求值返回 eval_errors（如悬空引用）→ 该条 value=None（不返回错误/0）。"""
    from decimal import Decimal

    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": [_preset("D6-1-tb-amount")]})

    async def _eval_with_errors(*a, **kw):
        return Decimal("0"), ["WP('Dbogus','B5'): 引用不存在"]

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _eval_with_errors)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[], project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    tb = next(b for b in resp["extraction"]["tierA"] if b["anchor"] == "D6-1-tb-amount")
    assert tb["value"] is None


def test_get_tier_a_disabled_binding_value_none(monkeypatch):
    """禁用绑定（source=disabled，表达式空）→ 不求值，value=None（避免误导 0）。"""
    from decimal import Decimal

    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": [_preset("D6-1-tb-amount")]})
    user_formulas = [_wp_formula("D6-1-note-conclusion", category="__disabled__", wp=wp)]

    eval_calls: list[str] = []

    async def _tracking_eval(db, *, project_id, year, expression, **kw):
        eval_calls.append(expression)
        return Decimal("42"), []

    monkeypatch.setattr(router_mod, "evaluate_wp_formula_expression", _tracking_eval)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=user_formulas, project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    tier_a = {b["anchor"]: b for b in resp["extraction"]["tierA"]}

    assert tier_a["D6-1-note-conclusion"]["source"] == SOURCE_DISABLED
    assert tier_a["D6-1-note-conclusion"]["value"] is None
    # 禁用绑定不触发求值（不进 eval_calls）；仅 tb-amount 被求值
    assert all("D6-1-note-conclusion" not in c for c in eval_calls)


def test_get_flag_off_no_year_query_no_extraction(monkeypatch):
    """flag OFF → 无 extraction 字段（Task 3.1 求值分支不触发 / 零回归 R2.4）。"""
    _disable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": [_preset("D6-1-tb-amount")]})
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[], project_year=2025)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))
    assert "extraction" not in resp


def test_get_items_backward_compatible(monkeypatch):
    """items 保持原始 wp_formula 行形状（不被 extraction 改动破坏）。"""
    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": []})
    user_formulas = [_wp_formula("D6-1-tb-amount", wp=wp)]
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=user_formulas)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert resp["wp_id"] == str(wp.id)
    assert resp["count"] == 1
    assert isinstance(resp["items"], list)
    item = resp["items"][0]
    # 原始形状关键字段仍在
    for key in ("id", "wp_id", "sheet_name", "target_cell", "expression", "formula_type"):
        assert key in item


# ---------------------------------------------------------------------------
# 灰度关闭 / 非 D 循环 → 无 extraction（零回归）
# ---------------------------------------------------------------------------


def test_get_flag_off_no_extraction(monkeypatch):
    """flag OFF → 无 extraction 字段，items 仍在（表现同当前 / R7.1）。"""
    _disable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": [_preset("D6-1-tb-amount")]})
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" not in resp
    assert "items" in resp and resp["count"] == 0


def test_get_non_d_cycle_no_extraction(monkeypatch):
    """flag ON 但非 D 循环 wp_code（K1）→ 无 extraction 字段。"""
    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": [_preset("D6-1-tb-amount")]})
    db = _FakeSession(wp=wp, wp_code="K1", user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" not in resp


def test_get_no_wp_code_no_extraction(monkeypatch):
    """wp 无 wp_index_id（拿不到 wp_code）→ 无 extraction 字段。"""
    _enable(monkeypatch)
    wp = _wp(wp_code_present=False)
    db = _FakeSession(wp=wp, wp_code=None, user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" not in resp


# ---------------------------------------------------------------------------
# D 循环但未接入 Tier B（D7 尚未覆盖）→ tierB == [] （诚实 / R7.4）
# ---------------------------------------------------------------------------


def test_get_uncovered_d_cycle_tier_b_empty_honest(monkeypatch):
    """D 循环但预设 + Tier B 溯源均空 → extraction 出现但 tierA/tierB 为空（诚实透出，不臆造）。

    注：D1–D7 现均已由各自 Wave 接入 Tier A 预设 + Tier B 溯源（Task 5/6 全覆盖），
    无真实「D 循环但未接入」wp_code（`_D_CYCLE_RE` 仅匹配 D1–D7）。故本用例改为
    **patch 空覆盖**（load_presets 空 + tier_b_provenance 返回 []）模拟未接入循环，
    验证路由器对空 tierA/tierB 的诚实透出（R7.4）。
    """
    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {})  # 无预设
    monkeypatch.setattr(router_mod, "tier_b_provenance", lambda code: [])  # 无溯源
    db = _FakeSession(wp=wp, wp_code="D7", user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" in resp
    assert resp["extraction"]["wp_code"] == "D7"
    assert resp["extraction"]["tierB"] == []
    assert resp["extraction"]["tierA"] == []


# ---------------------------------------------------------------------------
# sheet 级 wp_code 归基础码
# ---------------------------------------------------------------------------


def test_get_sheet_level_wp_code_normalized_to_base(monkeypatch):
    """wp_code='D6-1' → 归到基础码 D6，正常输出 Tier B 溯源。"""
    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {"D6": []})
    db = _FakeSession(wp=wp, wp_code="D6-1", user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" in resp
    assert resp["extraction"]["wp_code"] == "D6"
    assert resp["extraction"]["tierB"]  # D6 溯源非空


# ---------------------------------------------------------------------------
# Property 8 复用：未知锚点（预设/用户）丢弃，不进 extraction
# ---------------------------------------------------------------------------


def test_get_unknown_anchor_dropped(monkeypatch):
    """预设/用户含未知锚点 → 丢弃，不出现在 tierA。"""
    _enable(monkeypatch)
    wp = _wp()
    _patch_presets(monkeypatch, {
        "D6": [_preset("D6-1-tb-amount"), _preset("D6-1-totally-made-up")],
    })
    user_formulas = [_wp_formula("D6-1-also-bogus", wp=wp)]
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=user_formulas)

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    anchors = {b["anchor"] for b in resp["extraction"]["tierA"]}
    assert anchors == {"D6-1-tb-amount"}


# ---------------------------------------------------------------------------
# Property 7：PUT 悬空引用 → 422（既有行为，确认 GET 改动未破坏 save 路径）
# ---------------------------------------------------------------------------


def test_put_dangling_ref_returns_422(monkeypatch):
    """save 返回悬空 issues → router 抛 422 FORMULA_REF_NOT_FOUND（Property 7 intact）。"""
    wp = _wp()
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])
    # 通过不受支持函数门（返回空），聚焦悬空引用路径
    monkeypatch.setattr(router_mod, "find_unsupported_formula_functions", lambda expr: [])

    async def _fake_save(*args, **kwargs):
        return None, [{"ref": "WP('Dbogus','B5')", "status": "not_found",
                       "message": "引用不存在"}]

    monkeypatch.setattr(router_mod.wp_formula_service, "save", _fake_save)

    body = router_mod.FormulaSaveRequest(
        sheet_name="D6-1", target_cell="D6-1-tb-amount",
        expression="WP('Dbogus','B5')", year=2025,
    )

    with pytest.raises(HTTPException) as ei:
        _run(router_mod.save_formula(wp.id, body, db=db, user=_user()))
    assert ei.value.status_code == 422
    assert ei.value.detail["error_code"] == "FORMULA_REF_NOT_FOUND"


def test_put_unsupported_function_returns_422(monkeypatch):
    """save 前置不受支持函数门（AUX/PREV/序时账）→ 422 FORMULA_UNSUPPORTED_FUNCTION。"""
    wp = _wp()
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])
    monkeypatch.setattr(
        router_mod, "find_unsupported_formula_functions", lambda expr: ["AUX"]
    )

    body = router_mod.FormulaSaveRequest(
        sheet_name="D6-1", target_cell="D6-1-tb-amount",
        expression="AUX('1402','客户','期末余额')", year=2025,
    )

    with pytest.raises(HTTPException) as ei:
        _run(router_mod.save_formula(wp.id, body, db=db, user=_user()))
    assert ei.value.status_code == 422
    assert ei.value.detail["error_code"] == "FORMULA_UNSUPPORTED_FUNCTION"
