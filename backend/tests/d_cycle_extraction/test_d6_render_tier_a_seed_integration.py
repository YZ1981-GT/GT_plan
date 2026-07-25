"""Wave 3 / Task 4.1 —— D6 render 用 Tier A 公式 transient seed TB 核对行集成测试.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 3.1-3.7, 5.1 / Property 6, 7, 10, 11, 13)

**P0-1 主机制**：D6 render（主灰度开关开）用 `resolve_effective` 的有效 Tier A 公式
逐条 `evaluate_wp_formula_expression` 求值，**transient seed** TB 核对行锚点
`D6-1-tb-amount` 进 `responses_snapshot`（写 remark 字段，不落库），使"编辑公式即生效"。

覆盖：
  * **Property 10（灰度关闭零回归）**：主开关关（默认）→ responses_snapshot 无 D6-1-tb-amount
    seed，顶层键与 characterization 基线一致。
  * **主机制 + 写对字段（Property 6 / R3.7）**：主开关开 + 默认预设 → seed
    responses_snapshot["D6-1-tb-amount"]["remark"]。
  * **Property 7（默认预设等价 tb_amount）**：默认预设 `TB('1402','期末余额')` 求值
    = project_context.tb_amount 口径。
  * **编辑即生效**：用户 custom 公式（`TB('1402','年初余额')`）→ seed 按新公式取数（期初余额）。
  * **手工优先（Property 6 / R3.2）**：D6-1-tb-amount 持久层已有非空 remark → 不覆盖。
  * **disabled 跳过（R3.3）**：user 禁用绑定 → 不 seed。
  * **fail-open（Property 11 / R3.4）**：year 缺失 / resolve_effective 异常 / 求值有 eval_errors
    → 不 seed，静默沿用 tb_amount，render 不阻断。
  * **Property 13（transient 不落库）**：seed 只进 render payload，无 checklist_responses INSERT/UPDATE。

fake async session 按 SQL 文本路由；`get_active_filter`（eval + prefill）经 monkeypatch 隔离。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.routers.wp_render_strategies import _d6_contract_assets as d6
from app.services import wp_formula_eval_service as eval_mod
from app.services.d_cycle_extraction import prefill as prefill_mod
from app.services.d_cycle_extraction import presets as presets_mod

_ANCHOR = "D6-1-tb-amount"
_BASELINE_KEYS = {
    "sections",
    "adjudication_config",
    "ecl_config",
    "project_context",
    "disclosure_visibility",
    "responses_snapshot",
}


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由（D6 render 原查询 + resolve_effective + _resolve_tb）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, *, rows=None, one=None, scalar=None, scalar_rows=None):
        self._rows = rows or []
        self._one = one
        self._scalar = scalar
        self._scalar_rows = scalar_rows or []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._one

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalar_rows))


class _FakeSession:
    def __init__(
        self,
        *,
        checklist_rows=None,
        project_row=None,
        tb_agg_row=None,
        rp_rows=None,
        user_formulas=None,
        tb_resolve_row=None,
    ):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_agg_row = tb_agg_row
        self.rp_rows = rp_rows or []
        self.user_formulas = user_formulas or []
        self.tb_resolve_row = tb_resolve_row
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt)
        self.executed_sql.append(s)
        sl = s.lower()
        if "from wp_formula" in sl:
            return _FakeResult(scalar_rows=self.user_formulas)
        if "trial_balance" in sl:
            # D6 render 聚合（COALESCE(SUM(ABS(...）→ fetchone；_resolve_tb ORM select → scalar
            if "coalesce" in sl or "sum(abs" in sl:
                return _FakeResult(one=self.tb_agg_row)
            return _FakeResult(scalar=self.tb_resolve_row)
        if "tb_balance" in sl:  # prefill 叶子查询（本测试给空 → 无 adjudication_prefill）
            return _FakeResult(rows=[])
        if "checklist_responses" in sl:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in sl:
            return _FakeResult(rows=self.rp_rows)
        if "from projects" in sl or "projects where" in sl:
            return _FakeResult(one=self.project_row)
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id, *, conclusion="", remark=""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _user_formula(target_cell, *, expression, category=None, sheet_name="D6-1"):
    return SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        wp_id=uuid4(),
        sheet_name=sheet_name,
        target_cell=target_cell,
        expression=expression,
        category=category,
        description="",
        formula_type="auto_calc",
        refs=None,
        issue_description=None,
        hint_text=None,
        last_computed_at=None,
        created_by=None,
        created_at=None,
        updated_at=None,
    )


def _ctx(db, *, year=2025):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=year,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产审定表D6-1"),
    )


def _session(*, checklist_rows=None, user_formulas=None, tb_audited="98765.43",
             tb_opening="12345.67"):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
            applicable_standards="listed",
        ),
        tb_agg_row=SimpleNamespace(amount=98765.43),
        rp_rows=[SimpleNamespace(name="关联方甲", relation_type="subsidiary")],
        user_formulas=user_formulas or [],
        tb_resolve_row=SimpleNamespace(
            audited_amount=Decimal(tb_audited),
            opening_balance=Decimal(tb_opening),
            unadjusted_amount=Decimal("0"),
            rje_adjustment=Decimal("0"),
            aje_adjustment=Decimal("0"),
        ),
    )


def _enable(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


def _patch_filters(monkeypatch):
    import sqlalchemy as sa

    async def _fake(db, table, project_id, year, **kw):
        return sa.true()

    monkeypatch.setattr(eval_mod, "get_active_filter", _fake)
    monkeypatch.setattr(prefill_mod, "get_active_filter", _fake)


def _reset_presets(monkeypatch):
    monkeypatch.setattr(presets_mod, "_cached_mtime", None, raising=False)


# ---------------------------------------------------------------------------
# Property 10: 灰度关闭零回归
# ---------------------------------------------------------------------------


def test_flag_off_no_tier_a_seed(monkeypatch):
    """主开关关（默认）→ responses_snapshot 无 D6-1-tb-amount seed，顶层键同基线。"""
    _disable(monkeypatch)
    _reset_presets(monkeypatch)
    result = _run(d6.render(_ctx(_session())))
    assert set(result.keys()) == _BASELINE_KEYS
    assert _ANCHOR not in result["responses_snapshot"]


# ---------------------------------------------------------------------------
# 主机制 + 写对字段（Property 6 / R3.7）+ 默认等价（Property 7）
# ---------------------------------------------------------------------------


def test_flag_on_seeds_tb_amount_to_remark(monkeypatch):
    """主开关开 + 默认预设 → seed responses_snapshot['D6-1-tb-amount']['remark']（写对字段）。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    result = _run(d6.render(_ctx(_session())))
    snap = result["responses_snapshot"]
    assert _ANCHOR in snap, "主开关开应 seed D6-1-tb-amount 核对行"
    assert snap[_ANCHOR]["remark"] == "98765.43", "seed 写入 remark 字段（决策2 / R3.7）"
    # additive：既有顶层键保留
    assert _BASELINE_KEYS.issubset(set(result.keys()))


def test_property7_default_preset_equiv_tb_amount(monkeypatch):
    """Property 7：默认预设 TB('1402','期末余额') 求值 = project_context.tb_amount 口径。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    result = _run(d6.render(_ctx(_session())))
    seed_val = result["responses_snapshot"][_ANCHOR]["remark"]
    tb_amount = result["project_context"]["tb_amount"]
    assert seed_val == str(tb_amount), "默认预设 seed 与 tb_amount 口径一致（默认行为不变）"


def test_edited_custom_formula_takes_effect(monkeypatch):
    """编辑即生效：用户 custom 公式 TB('1402','年初余额') → seed 按新公式取期初余额。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    user = [_user_formula(_ANCHOR, expression="TB('1402','年初余额')")]
    result = _run(d6.render(_ctx(_session(user_formulas=user))))
    # 年初余额 → opening_balance = 12345.67
    assert result["responses_snapshot"][_ANCHOR]["remark"] == "12345.67"


# ---------------------------------------------------------------------------
# 手工优先（Property 6 / R3.2）
# ---------------------------------------------------------------------------


def test_property6_manual_priority_not_overwritten(monkeypatch):
    """持久层已有非空 remark → 不覆盖（手工优先）。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    checklist = [_checklist_row(_ANCHOR, remark="500000")]
    result = _run(d6.render(_ctx(_session(checklist_rows=checklist))))
    assert result["responses_snapshot"][_ANCHOR]["remark"] == "500000", "手工值不被 seed 覆盖"


def test_empty_persisted_value_gets_seeded(monkeypatch):
    """持久层该锚点存在但 remark 空 → 视为未填，仍 seed（保留既有 conclusion）。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    checklist = [_checklist_row(_ANCHOR, conclusion="核对说明", remark="")]
    result = _run(d6.render(_ctx(_session(checklist_rows=checklist))))
    snap = result["responses_snapshot"][_ANCHOR]
    assert snap["remark"] == "98765.43"
    assert snap["conclusion"] == "核对说明", "保留既有 conclusion（只填空 remark）"


# ---------------------------------------------------------------------------
# disabled 跳过（R3.3）
# ---------------------------------------------------------------------------


def test_property_disabled_binding_not_seeded(monkeypatch):
    """user 禁用绑定（category=__disabled__）→ 不 seed 该锚点。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    user = [_user_formula(_ANCHOR, expression="", category="__disabled__")]
    result = _run(d6.render(_ctx(_session(user_formulas=user))))
    assert _ANCHOR not in result["responses_snapshot"], "disabled 绑定不 seed（R3.3）"


# ---------------------------------------------------------------------------
# fail-open（Property 11 / R3.4）
# ---------------------------------------------------------------------------


def test_failopen_year_missing_no_seed(monkeypatch):
    """year 缺失 → 不 seed（fail-open 沿用 tb_amount），render 正常返回。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    result = _run(d6.render(_ctx(_session(), year=None)))
    assert _ANCHOR not in result["responses_snapshot"]
    assert _BASELINE_KEYS.issubset(set(result.keys()))


def test_failopen_resolve_effective_raises(monkeypatch):
    """resolve_effective 异常 → fail-open（无 seed），render 不阻断。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)

    async def _boom(*a, **kw):
        raise RuntimeError("resolve boom")

    monkeypatch.setattr(d6, "resolve_effective", _boom)
    result = _run(d6.render(_ctx(_session())))
    assert _ANCHOR not in result["responses_snapshot"]
    assert set(result.keys()) == _BASELINE_KEYS


def test_failopen_eval_errors_no_seed(monkeypatch):
    """求值有 eval_errors（悬空引用等）→ 不 seed（不静默落错误/0，R3.4）。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)

    async def _eval_err(db, **kw):
        return Decimal("0"), ["TB('x'): 无法解析"]

    monkeypatch.setattr(d6, "evaluate_wp_formula_expression", _eval_err)
    result = _run(d6.render(_ctx(_session())))
    assert _ANCHOR not in result["responses_snapshot"], "有 eval_errors 不 seed"


# ---------------------------------------------------------------------------
# Property 13: transient 不落库
# ---------------------------------------------------------------------------


def test_property13_seed_transient_no_db_writeback(monkeypatch):
    """seed 只进 render payload；render 对 checklist_responses 只 SELECT，无 INSERT/UPDATE。"""
    _enable(monkeypatch)
    _reset_presets(monkeypatch)
    _patch_filters(monkeypatch)
    db = _session()
    result = _run(d6.render(_ctx(db)))
    assert result["responses_snapshot"][_ANCHOR]["remark"] == "98765.43"
    joined = " ".join(db.executed_sql).lower()
    assert "insert into" not in joined, "seed 不得 INSERT（transient 不落库 / Property 13）"
    assert "update " not in joined, "seed 不得 UPDATE（transient 不落库 / Property 13）"
