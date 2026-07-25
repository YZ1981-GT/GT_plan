"""Wave 3 / Task 4.3 —— D6 Tier A 预设落地 + 面板展示验证.

spec: .kiro/specs/d-cycle-four-table-extraction-formulas/
      (Requirements 3.1, 3.4 / Property 5, 8, 11)

Task 4.3 交付：`d_cycle_extraction_presets.json` D6 加入唯一一条可表达为单条公式的
简单总额提取 `D6-1-tb-amount` → `TB('1402','期末余额')`（对照 Wave0 anchor registry），
并在公式管理面板（`GET /api/workpapers/{wp_id}/formulas` 的 `extraction.tierA`）展示。

本测试**读真实预设文件**（不 monkeypatch `load_presets`），断言：
  1. 预设条目双门通过：`is_known_anchor("D6", anchor)` 为真 + `find_unsupported_formula_functions`
     无命中（仅 TB/SUM_TB/WP）。
  2. `resolve_effective(db, wp_id, "D6", project_id)` 无用户覆盖时返回该预设，source=preset。
  3. 用户同锚点覆盖 → source=custom（读时收敛，Property 5）。
  4. GET 端点（flag ON，wp_code=D6）在 `extraction.tierA` 中surface该预设。
  5. D2 无 Tier A 预设（Task 4.3 仅 D6）。

全部用 fake async session（不触发 conftest 的真实 SQLite create_all，规避已知
`working_paper` 表缺失问题）；直接调用 router 协程，绕过 FastAPI Depends。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.config import settings
from app.routers import wp_formula as router_mod
from app.services.d_cycle_extraction import presets as presets_mod
from app.services.d_cycle_extraction.anchor_registry import is_known_anchor
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_PRESET,
    load_presets,
    resolve_effective,
)
from app.services.wp_formula_eval_service import find_unsupported_formula_functions

_D6_ANCHOR = "D6-1-tb-amount"
_D6_EXPRESSION = "TB('1402','期末余额')"


def _run(coro):
    return asyncio.run(coro)


def _reset_presets_cache(monkeypatch):
    """强制预设库按 mtime 重读真实文件（清除可能被其它测试污染的缓存）。"""
    monkeypatch.setattr(presets_mod, "_cached_mtime", None, raising=False)


# ---------------------------------------------------------------------------
# Fake async session（复用端点测试同款路由）
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
    def __init__(self, *, wp, wp_code, user_formulas=None):
        self.wp = wp
        self.wp_code = wp_code
        self.user_formulas = user_formulas or []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        if "from wp_index" in s:
            return _FakeResult(scalar=self.wp_code)
        if "from wp_formula" in s:
            return _FakeResult(rows=self.user_formulas)
        if "from working_paper" in s:
            if "is_deleted" in s:
                return _FakeResult(scalar=self.wp)
            return _FakeResult(scalar=self.wp.project_id)
        return _FakeResult()

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


def _wp_formula(target_cell, *, expression, sheet_name="D6-1", wp=None):
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


# ---------------------------------------------------------------------------
# 1. 预设条目双门通过（合法锚点 + 受支持函数）
# ---------------------------------------------------------------------------


def test_d6_preset_entry_passes_both_gates(monkeypatch):
    """D6 预设 `D6-1-tb-amount` / `TB('1402','期末余额')` 通过锚点合法性 + 受支持函数双门。"""
    _reset_presets_cache(monkeypatch)
    presets = load_presets("D6")
    assert len(presets) == 1, "Task 4.3：D6 应有且仅有 1 条 Tier A 预设（诚实，唯一清晰候选）"
    entry = presets[0]
    assert entry["anchor"] == _D6_ANCHOR
    assert entry["expression"] == _D6_EXPRESSION

    # 门 1：锚点必 ∈ D6 已知锚点集（Property 8 / R6.2）
    assert is_known_anchor("D6", entry["anchor"]) is True

    # 门 2：表达式仅含受支持函数（TB/SUM_TB/WP），无 AUX/PREV/LEDGER/COUNT_LEDGER
    assert find_unsupported_formula_functions(entry["expression"]) == []


# ---------------------------------------------------------------------------
# 2. resolve_effective 无用户覆盖 → 返回预设 source=preset
# ---------------------------------------------------------------------------


def test_resolve_effective_returns_preset_when_no_user_override(monkeypatch):
    """无用户 wp_formula 时，resolve_effective("D6") 返回该 Tier A 预设，source=preset。"""
    _reset_presets_cache(monkeypatch)
    db = _FakeSession(wp=_wp(), wp_code="D6", user_formulas=[])
    result = _run(resolve_effective(db, uuid4(), "D6", uuid4()))

    assert len(result) == 1
    binding = result[0]
    assert binding["anchor"] == _D6_ANCHOR
    assert binding["expression"] == _D6_EXPRESSION
    assert binding["sheet_name"] == "D6-1"
    assert binding["source"] == SOURCE_PRESET
    assert binding["tier"] == "A"


def test_resolve_effective_user_override_becomes_custom(monkeypatch):
    """用户同锚点公式覆盖预设 → source=custom（读时收敛 Property 5）。"""
    _reset_presets_cache(monkeypatch)
    wp = _wp()
    user = _wp_formula(_D6_ANCHOR, expression="TB('1402','期初余额')", wp=wp)
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[user])
    result = _run(resolve_effective(db, wp.id, "D6", wp.project_id))

    assert len(result) == 1
    assert result[0]["source"] == SOURCE_CUSTOM
    assert result[0]["expression"] == "TB('1402','期初余额')"


# ---------------------------------------------------------------------------
# 3. GET 端点（flag ON）surface 预设到 extraction.tierA
# ---------------------------------------------------------------------------


def test_get_endpoint_surfaces_d6_preset_in_tier_a(monkeypatch):
    """flag ON + wp_code=D6：GET /formulas 的 extraction.tierA 含 D6-1-tb-amount（source=preset）。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)
    wp = _wp()
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" in resp
    ext = resp["extraction"]
    assert ext["wp_code"] == "D6"
    assert ext["enabled"] is True

    tier_a = {b["anchor"]: b for b in ext["tierA"]}
    assert _D6_ANCHOR in tier_a, "面板 D6 应展示 Tier A 预设 D6-1-tb-amount"
    binding = tier_a[_D6_ANCHOR]
    assert binding["expression"] == _D6_EXPRESSION
    assert binding["source"] == SOURCE_PRESET
    assert binding["tier"] == "A"
    # R5.6：GET 不逐条重求值
    assert binding["value"] is None


def test_get_endpoint_flag_off_no_preset_surfaced(monkeypatch):
    """flag OFF → 无 extraction（零回归 / R7.1），预设不 surface。"""
    _reset_presets_cache(monkeypatch)
    monkeypatch.setattr(settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)
    wp = _wp()
    db = _FakeSession(wp=wp, wp_code="D6", user_formulas=[])

    resp = _run(router_mod.list_formulas(wp.id, db=db, _user=_user()))

    assert "extraction" not in resp


# ---------------------------------------------------------------------------
# 4. D2 Tier A 预设（Task 5.1 追加：唯一清晰候选 D2-adj-tb-amount，宁缺勿造）
# ---------------------------------------------------------------------------


def test_d2_has_tb_amount_tier_a_preset(monkeypatch):
    """Task 5.1：D2 加入且仅加入 1 条 Tier A 预设 D2-adj-tb-amount → TB('1122','期末余额')。

    分类行（单项/账龄/客户类型）未审无法从 TB 拆分 → 宁缺勿造，不注册公式。
    唯一清晰可编辑候选是 1122 总额核对标量（对齐 D6-1-tb-amount 范式）。
    """
    _reset_presets_cache(monkeypatch)
    presets = load_presets("D2")
    assert len(presets) == 1, "Task 5.1：D2 应有且仅有 1 条 Tier A 预设（1122 总额，宁缺勿造）"
    entry = presets[0]
    assert entry["anchor"] == "D2-adj-tb-amount"
    assert entry["expression"] == "TB('1122','期末余额')"
    # 双门：锚点合法 + 表达式仅受支持函数
    assert is_known_anchor("D2", entry["anchor"]) is True
    assert find_unsupported_formula_functions(entry["expression"]) == []
