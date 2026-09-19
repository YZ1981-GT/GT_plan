"""Wave 3 / Task 4.1 —— D6 render Tier A 公式驱动 TB 核对行 **transient seed** 集成测试.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 3.1–3.7, 5.1 / Property 6, 7, 10, 11, 13)

此为「编辑公式即生效」成立的**主机制**：D6 render 用 `resolve_effective` 的有效 Tier A
公式（读时收敛）逐条 `evaluate_wp_formula_expression`（经 get_active_filter）求值，
**transient seed** TB 核对行锚点（`D6-1-tb-amount`）进 `responses_snapshot`——只进 render
返回 payload、**不落 checklist_responses/DB**（对齐 D6 Tier B `adjudication_prefill`）。

覆盖：
  * **Property 10（灰度关闭零回归）**：主开关关（默认）→ 不 seed TB 核对行，
    responses_snapshot 逐字节等价当前（即便 resolver 会返回绑定）。
  * **Property 6（手工优先 + 写对字段）**：主开关开 + 无既有值 → seed 写入前端读取字段
    （`remark`，见 `_seed_fields.map`）；持久层已有非空 remark → 不覆盖（手工优先）；
    source=disabled → 不 seed。
  * **Property 7（默认预设 seed 等价 tb_amount）**：默认预设 `TB('1141','期末余额')` 求值
    = trial_balance 审定核对标量，与 project_context.tb_amount 口径一致。
  * **Property 11（fail-open）**：resolver 异常 / evaluator 异常 / eval_errors / year 缺失
    → 该锚点不 seed（静默沿用 project_context.tb_amount），始终不阻断 render。
  * **Property 13（seed 全程 transient 不落库）**：seed 只进返回 responses_snapshot，
    fake session 不发生任何 INSERT/UPDATE checklist_responses 写。

按 task 指引：fake async session + **mock resolver + evaluator**（monkeypatch d6 模块级
导入名 `resolve_effective` / `evaluate_wp_formula_expression`），Tier B 的
`get_active_filter` 经 monkeypatch 隔离、tb_balance 置空使 Tier B 不干扰 Tier A 断言。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import _d6_contract_assets as d6
from app.services.d_cycle_extraction import prefill as prefill_mod
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
)

_TB_ANCHOR = "D6-1-tb-amount"


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async DB —— 记录所有 execute 的 SQL 文本（供 Property 13 断言无写库）
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
    def __init__(self, *, checklist_rows=None, project_row=None, tb_row=None, rp_rows=None):
        self.checklist_rows = checklist_rows or []
        self.project_row = project_row
        self.tb_row = tb_row
        self.rp_rows = rp_rows or []
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        self.executed_sql.append(s)
        if "tb_balance" in s and "trial_balance" not in s:
            return _FakeResult(rows=[])  # Tier B 无叶子 → 不干扰 Tier A
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _FakeResult(rows=self.rp_rows)
        if "trial_balance" in s:
            return _FakeResult(one=self.tb_row)
        if "from projects" in s or "projects where" in s:
            return _FakeResult(one=self.project_row)
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id: str, conclusion: str = "", remark: str = ""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _ctx(db, *, year=2025):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=year,
        business_category="general",
        classification=SimpleNamespace(sheet_name="合同资产审定表D6-1"),
    )


def _session(*, checklist_rows=None, tb_amount=98765.43):
    return _FakeSession(
        checklist_rows=checklist_rows or [],
        project_row=SimpleNamespace(
            client_name="测试客户",
            audit_year=2025,
            business_category="general",
            applicable_standards="listed",
        ),
        tb_row=SimpleNamespace(
            amount=tb_amount,
            unadjusted=tb_amount,
            audited=tb_amount,
        ),
        rp_rows=[],
    )


def _enable_flag(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable_flag(monkeypatch):
    monkeypatch.setattr(d6.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


def _isolate_tier_b(monkeypatch):
    """隔离 Tier B 的 get_active_filter（tb_balance 已置空，防真实 DB 调用）。"""
    import sqlalchemy as sa

    async def _fake_filter(db, table, project_id, year, **kw):
        return sa.true()

    monkeypatch.setattr(prefill_mod, "get_active_filter", _fake_filter)


def _mock_resolver(monkeypatch, bindings):
    async def _fake_resolve(db, wp_id, wp_code, project_id):
        return list(bindings)

    monkeypatch.setattr(d6, "resolve_effective", _fake_resolve)


def _mock_evaluator(monkeypatch, *, value=Decimal("98765.43"), errs=None, raises=False):
    async def _fake_eval(db, *, project_id, year, expression, **kw):
        if raises:
            raise RuntimeError("evaluator boom")
        return value, list(errs or [])

    monkeypatch.setattr(d6, "evaluate_wp_formula_expression", _fake_eval)


def _binding(anchor=_TB_ANCHOR, expression="TB('1141','期末余额')", source=SOURCE_PRESET):
    return {
        "wp_code": "D6",
        "sheet_name": "D6-1",
        "anchor": anchor,
        "expression": expression,
        "formula_type": "auto_calc",
        "description": "",
        "source": source,
        "tier": "A",
    }


# ---------------------------------------------------------------------------
# Property 10: 灰度关闭零回归
# ---------------------------------------------------------------------------


def test_flag_off_no_tier_a_seed(monkeypatch):
    """主开关关（默认）→ 即便 resolver 会返回绑定，也不 seed TB 核对行。"""
    _disable_flag(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, value=Decimal("111111"))
    result = _run(d6.render(_ctx(_session())))
    snap = result["responses_snapshot"]
    assert _TB_ANCHOR not in snap  # 无既有值 + 不 seed → 锚点缺席


def test_flag_off_existing_value_untouched(monkeypatch):
    """主开关关 + 持久层已有值 → 逐字节不变（不 seed 也不改）。"""
    _disable_flag(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, value=Decimal("111111"))
    checklist = [_checklist_row(_TB_ANCHOR, remark="88888")]
    result = _run(d6.render(_ctx(_session(checklist_rows=checklist))))
    assert result["responses_snapshot"][_TB_ANCHOR]["remark"] == "88888"


# ---------------------------------------------------------------------------
# Property 6: 手工优先 + 写对字段
# ---------------------------------------------------------------------------


def test_flag_on_seeds_remark_field(monkeypatch):
    """主开关开 + 无既有值 → seed 写入前端读取字段 remark（_seed_fields.map: D6→remark）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, value=Decimal("123456"))
    result = _run(d6.render(_ctx(_session())))
    seeded = result["responses_snapshot"][_TB_ANCHOR]
    assert seeded["remark"] == "123456"          # 写对字段（remark）
    assert seeded.get("conclusion", "") == ""     # 另一字段保持空，不误写


def test_flag_on_manual_priority_not_overwritten(monkeypatch):
    """主开关开 + 持久层已有非空 remark → 手工优先，不覆盖（Property 6 / R3.2）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, value=Decimal("123456"))
    checklist = [_checklist_row(_TB_ANCHOR, remark="500000")]
    result = _run(d6.render(_ctx(_session(checklist_rows=checklist))))
    # 真人工值保留，不被公式 seed 覆盖
    assert result["responses_snapshot"][_TB_ANCHOR]["remark"] == "500000"


def test_flag_on_disabled_source_not_seeded(monkeypatch):
    """source=disabled 的绑定 → 不 seed 该锚点（R3.3）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding(source=SOURCE_DISABLED)])
    _mock_evaluator(monkeypatch, value=Decimal("123456"))
    result = _run(d6.render(_ctx(_session())))
    assert _TB_ANCHOR not in result["responses_snapshot"]


def test_flag_on_unregistered_seed_field_skipped(monkeypatch):
    """绑定锚点非 _seed_fields.map 登记（无 seed 字段）→ 跳过 seed（决策2 / R3.7）。

    D6 仅登记 D6-1-tb-amount 的 seed 字段。此处用一个真实存在但非 TB 核对行 seed 目标
    的锚点（D6-2-rows），seed_field 返 None → 不 seed（防错列 round-trip 断裂）。
    """
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding(anchor="D6-2-rows")])
    _mock_evaluator(monkeypatch, value=Decimal("123456"))
    result = _run(d6.render(_ctx(_session())))
    seeded = result["responses_snapshot"].get("D6-2-rows")
    # 未登记 seed 字段 → 不写入求值结果
    assert seeded is None or seeded.get("remark", "") == ""


# ---------------------------------------------------------------------------
# Property 7: 默认预设 seed 等价 tb_amount
# ---------------------------------------------------------------------------


def test_default_preset_seed_matches_tb_amount(monkeypatch):
    """默认预设 TB('1141','期末余额') 求值 = trial_balance 审定核对标量,
    与 project_context.tb_amount 口径一致（默认行为不变 / R3.6 / Property 7）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    tb_amount = 98765.43
    _mock_resolver(monkeypatch, [_binding()])  # 默认预设（source=preset）
    # 默认预设求值口径 = trial_balance 审定数（与 project_context.tb_amount 同源）
    _mock_evaluator(monkeypatch, value=Decimal(str(tb_amount)))
    result = _run(d6.render(_ctx(_session(tb_amount=tb_amount))))
    seeded_remark = result["responses_snapshot"][_TB_ANCHOR]["remark"]
    assert float(seeded_remark) == result["project_context"]["tb_amount"] == tb_amount


# ---------------------------------------------------------------------------
# Property 11: fail-open
# ---------------------------------------------------------------------------


def test_resolver_error_fails_open(monkeypatch):
    """resolver 异常 → fail-open（不 seed，不阻断 render）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)

    async def _boom(db, wp_id, wp_code, project_id):
        raise RuntimeError("resolve boom")

    monkeypatch.setattr(d6, "resolve_effective", _boom)
    _mock_evaluator(monkeypatch, value=Decimal("123456"))
    result = _run(d6.render(_ctx(_session())))
    assert _TB_ANCHOR not in result["responses_snapshot"]
    # render 正常返回（fail-open），tb_amount fallback 仍在
    assert "project_context" in result


def test_evaluator_error_fails_open(monkeypatch):
    """evaluator 异常 → 该锚点不 seed（fail-open）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, raises=True)
    result = _run(d6.render(_ctx(_session())))
    assert _TB_ANCHOR not in result["responses_snapshot"]


def test_eval_errors_not_seeded(monkeypatch):
    """求值返回 eval_errors（悬空引用等）→ 不 seed（不静默落错误/0，R3.4）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, value=Decimal("0"), errs=["dangling ref"])
    result = _run(d6.render(_ctx(_session())))
    assert _TB_ANCHOR not in result["responses_snapshot"]


def test_year_none_fails_open(monkeypatch):
    """year 缺失 → 该锚点不 seed（fail-open，沿用 project_context.tb_amount）。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, value=Decimal("123456"))
    result = _run(d6.render(_ctx(_session(), year=None)))
    assert _TB_ANCHOR not in result["responses_snapshot"]


# ---------------------------------------------------------------------------
# Property 13: seed 全程 transient 不落库
# ---------------------------------------------------------------------------


def test_seed_is_transient_no_db_write(monkeypatch):
    """Tier A seed 只进返回 responses_snapshot，不发生任何 checklist_responses 写库。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    _mock_resolver(monkeypatch, [_binding()])
    _mock_evaluator(monkeypatch, value=Decimal("123456"))
    db = _session()
    result = _run(d6.render(_ctx(db)))
    # seed 生效（在返回 payload 中）
    assert result["responses_snapshot"][_TB_ANCHOR]["remark"] == "123456"
    # 但无任何写库（fake session 只有 SELECT，无 insert/update）
    assert all(
        ("insert" not in sql and "update" not in sql) for sql in db.executed_sql
    ), "Tier A transient seed 不得写 checklist_responses/DB（Property 13）"


def test_custom_formula_seed_overrides_default(monkeypatch):
    """用户 custom 公式（读时收敛覆盖预设）求值结果 seed 生效 → 编辑公式即生效。"""
    _enable_flag(monkeypatch)
    _isolate_tier_b(monkeypatch)
    # 用户改公式（如 期末余额→年初余额），resolve_effective 返回 source=custom
    _mock_resolver(monkeypatch, [_binding(expression="TB('1141','年初余额')", source=SOURCE_CUSTOM)])
    _mock_evaluator(monkeypatch, value=Decimal("42000"))
    result = _run(d6.render(_ctx(_session())))
    assert result["responses_snapshot"][_TB_ANCHOR]["remark"] == "42000"
