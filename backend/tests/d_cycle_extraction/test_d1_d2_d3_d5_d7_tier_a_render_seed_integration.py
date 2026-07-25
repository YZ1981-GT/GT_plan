"""Wave 4 / Task 4.2 —— D1/D2/D3/D5/D7 render Tier A 公式驱动 TB 核对行 transient seed 集成测试.

spec: .kiro/specs/d-cycle-tier-a-writeback-detail-seed/
      (Requirements 3.1–3.7, 5.1 / Property 6, 7, 10, 11, 13)

把 Task 4.1 D6 的主机制（`resolve_effective` 有效 Tier A 公式 → `evaluate_wp_formula_expression`
求值 → **transient seed** TB 核对行进 `responses_snapshot`，不落库）经共享助手
`d_cycle_extraction.tier_a_seed.seed_tier_a_reconciliation` 铺到 D1/D2/D3/D5/D7（各单标量）。

参数化覆盖五个单标量循环，逐条断言（对齐 D6 test 范式，mock 调用方模块的
`resolve_effective`/`evaluate_wp_formula_expression`）：
  * **Property 10（灰度关闭零回归）**：主开关关（默认）→ 不 seed 该循环 TB 核对行锚点。
  * **主机制 + 写对字段（Property 6 / R3.7）**：主开关开 + 无既有值 → seed 写入 remark 字段。
  * **默认预设 seed 值（Property 7）**：默认预设求值 = TB 审定核对标量（含 project_context.tb_amount
    的循环 D1/D5/D7 额外断言口径一致）。
  * **手工优先（Property 6 / R3.2）**：持久层已有非空 remark → 不覆盖。
  * **disabled 跳过（R3.3）**：source=disabled → 不 seed。
  * **fail-open（Property 11 / R3.4）**：resolver 异常 / evaluator 异常 / eval_errors / year 缺失
    → 不 seed，render 不阻断。
  * **Property 13（transient 不落库）**：seed 只进 payload，无 checklist_responses INSERT/UPDATE。
  * **编辑即生效**：用户 custom 公式（读时收敛覆盖预设）求值结果 seed 生效。
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.routers.wp_render_strategies import _d1_notes_receivable as d1
from app.routers.wp_render_strategies import _d2_accounts_receivable as d2
from app.routers.wp_render_strategies import _d3_prepaid_accounts as d3
from app.routers.wp_render_strategies import _d5_receivables_financing as d5
from app.routers.wp_render_strategies import _d7_contract_liabilities as d7
from app.services.d_cycle_extraction.presets import (
    SOURCE_CUSTOM,
    SOURCE_DISABLED,
    SOURCE_PRESET,
)

# (module, wp_code, anchor, expression, has_project_tb_amount)
_CYCLES = [
    (d1, "D1", "D1-adj-tb-amount", "TB('1121','期末余额')", True),
    (d2, "D2", "D2-adj-tb-amount", "TB('1122','期末余额')", False),
    (d3, "D3", "D3-adj-trial-balance-amount", "TB('2203','期末余额')", False),
    (d5, "D5", "D5-1-tb-amount", "TB('1124','期末余额')", True),
    (d7, "D7", "D7-1-adj-aging-trial-balance-currentAudited", "TB('2205','期末余额')", True),
]

_TB_VALUE = "98765.43"


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fake async DB —— 按 SQL 文本路由，覆盖各循环 render 的自有查询
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
    def __init__(self, *, checklist_rows=None):
        self.checklist_rows = checklist_rows or []
        self.executed_sql: list[str] = []

    async def execute(self, stmt, params=None):
        s = str(stmt).lower()
        self.executed_sql.append(s)
        if "tb_balance" in s and "trial_balance" not in s:
            return _FakeResult(rows=[])  # Tier B（本循环不触发）
        if "checklist_responses" in s:
            return _FakeResult(rows=self.checklist_rows)
        if "related_party_registry" in s:
            return _FakeResult(rows=[SimpleNamespace(name="关联方甲")])
        if "trial_balance" in s:
            # 覆盖 D1(unadjusted/audited) / D5(amount) / D7(amt) 各自 fetchone 列
            return _FakeResult(
                one=SimpleNamespace(
                    unadjusted=float(_TB_VALUE),
                    audited=float(_TB_VALUE),
                    amount=float(_TB_VALUE),
                    amt=float(_TB_VALUE),
                )
            )
        if "from projects" in s or "projects where" in s:
            return _FakeResult(
                one=SimpleNamespace(
                    client_name="测试客户",
                    audit_year=2025,
                    business_category="general",
                    applicable_standards="listed",
                )
            )
        return _FakeResult()

    async def rollback(self):
        return None


def _checklist_row(item_id, *, conclusion="", remark=""):
    return SimpleNamespace(item_id=item_id, conclusion=conclusion, remark=remark)


def _ctx(db, *, year=2025):
    return SimpleNamespace(
        db=db,
        wp_id=uuid4(),
        project_id=uuid4(),
        year=year,
        business_category="general",
        classification=SimpleNamespace(sheet_name="审定表"),
    )


def _binding(anchor, expression, *, source=SOURCE_PRESET, wp_code="D2"):
    return {
        "wp_code": wp_code,
        "sheet_name": f"{wp_code}-1",
        "anchor": anchor,
        "expression": expression,
        "formula_type": "auto_calc",
        "description": "",
        "source": source,
        "tier": "A",
    }


def _mock_resolver(monkeypatch, module, bindings):
    async def _fake_resolve(db, wp_id, wp_code, project_id):
        return list(bindings)

    monkeypatch.setattr(module, "resolve_effective", _fake_resolve)


def _mock_evaluator(monkeypatch, module, *, value=Decimal(_TB_VALUE), errs=None, raises=False):
    async def _fake_eval(db, *, project_id, year, expression, **kw):
        if raises:
            raise RuntimeError("evaluator boom")
        return value, list(errs or [])

    monkeypatch.setattr(module, "evaluate_wp_formula_expression", _fake_eval)


def _enable(monkeypatch, module):
    monkeypatch.setattr(module.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", True)


def _disable(monkeypatch, module):
    monkeypatch.setattr(module.settings, "D_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED", False)


# ---------------------------------------------------------------------------
# Property 10: 灰度关闭零回归
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_flag_off_no_tier_a_seed(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """主开关关（默认）→ 即便 resolver 会返回绑定，也不 seed TB 核对行锚点。"""
    _disable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, value=Decimal("111111"))
    result = _run(module.render(_ctx(_FakeSession())))
    assert anchor not in result["responses_snapshot"]


# ---------------------------------------------------------------------------
# 主机制 + 写对字段（Property 6 / R3.7）+ 默认等价（Property 7）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_flag_on_seeds_remark_field(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """主开关开 + 无既有值 → seed 写入 remark 字段（决策2 / R3.7），值 = 默认预设求值标量。"""
    _enable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, value=Decimal(_TB_VALUE))
    result = _run(module.render(_ctx(_FakeSession())))
    snap = result["responses_snapshot"]
    assert anchor in snap, f"{wp_code} 主开关开应 seed TB 核对行 {anchor}"
    assert snap[anchor]["remark"] == _TB_VALUE, "seed 写入 remark 字段"
    assert snap[anchor].get("conclusion", "") == "", "另一字段 conclusion 保持空"
    # Property 7：含 project_context.tb_amount 的循环，seed 与其口径一致
    if has_tb:
        assert float(snap[anchor]["remark"]) == result["project_context"]["tb_amount"]


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_edited_custom_formula_takes_effect(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """编辑即生效：用户 custom 公式（读时收敛覆盖预设）→ seed 按新公式求值结果。"""
    _enable(monkeypatch, module)
    _mock_resolver(
        monkeypatch,
        module,
        [_binding(anchor, "TB('x','年初余额')", source=SOURCE_CUSTOM, wp_code=wp_code)],
    )
    _mock_evaluator(monkeypatch, module, value=Decimal("42000"))
    result = _run(module.render(_ctx(_FakeSession())))
    assert result["responses_snapshot"][anchor]["remark"] == "42000"


# ---------------------------------------------------------------------------
# 手工优先（Property 6 / R3.2）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_manual_priority_not_overwritten(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """持久层已有非空 remark → 手工优先，不覆盖（Property 6 / R3.2）。"""
    _enable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, value=Decimal(_TB_VALUE))
    checklist = [_checklist_row(anchor, remark="500000")]
    result = _run(module.render(_ctx(_FakeSession(checklist_rows=checklist))))
    assert result["responses_snapshot"][anchor]["remark"] == "500000"


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_empty_persisted_value_gets_seeded(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """持久层锚点存在但 remark 空 → 视为未填，仍 seed（保留既有 conclusion）。"""
    _enable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, value=Decimal(_TB_VALUE))
    checklist = [_checklist_row(anchor, conclusion="核对说明", remark="")]
    result = _run(module.render(_ctx(_FakeSession(checklist_rows=checklist))))
    snap = result["responses_snapshot"][anchor]
    assert snap["remark"] == _TB_VALUE
    assert snap["conclusion"] == "核对说明", "只填空 remark，保留既有 conclusion"


# ---------------------------------------------------------------------------
# disabled 跳过（R3.3）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_disabled_binding_not_seeded(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """source=disabled 的绑定 → 不 seed 该锚点（R3.3）。"""
    _enable(monkeypatch, module)
    _mock_resolver(
        monkeypatch, module, [_binding(anchor, expr, source=SOURCE_DISABLED, wp_code=wp_code)]
    )
    _mock_evaluator(monkeypatch, module, value=Decimal(_TB_VALUE))
    result = _run(module.render(_ctx(_FakeSession())))
    assert anchor not in result["responses_snapshot"]


# ---------------------------------------------------------------------------
# fail-open（Property 11 / R3.4）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_failopen_resolver_error(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """resolver 异常 → fail-open（不 seed，不阻断 render）。"""
    _enable(monkeypatch, module)

    async def _boom(*a, **kw):
        raise RuntimeError("resolve boom")

    monkeypatch.setattr(module, "resolve_effective", _boom)
    _mock_evaluator(monkeypatch, module, value=Decimal(_TB_VALUE))
    result = _run(module.render(_ctx(_FakeSession())))
    assert anchor not in result["responses_snapshot"]
    assert "project_context" in result  # render 正常返回


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_failopen_evaluator_error(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """evaluator 异常 → 该锚点不 seed（fail-open）。"""
    _enable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, raises=True)
    result = _run(module.render(_ctx(_FakeSession())))
    assert anchor not in result["responses_snapshot"]


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_failopen_eval_errors_not_seeded(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """求值返回 eval_errors（悬空引用等）→ 不 seed（不静默落错误/0，R3.4）。"""
    _enable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, value=Decimal("0"), errs=["dangling ref"])
    result = _run(module.render(_ctx(_FakeSession())))
    assert anchor not in result["responses_snapshot"]


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_failopen_year_none(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """year 缺失 → 该锚点不 seed（fail-open，沿用 project_context 回退）。"""
    _enable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, value=Decimal(_TB_VALUE))
    result = _run(module.render(_ctx(_FakeSession(), year=None)))
    assert anchor not in result["responses_snapshot"]


# ---------------------------------------------------------------------------
# Property 13: seed 全程 transient 不落库
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module,wp_code,anchor,expr,has_tb", _CYCLES)
def test_seed_is_transient_no_db_write(monkeypatch, module, wp_code, anchor, expr, has_tb):
    """Tier A seed 只进返回 responses_snapshot，不发生任何 checklist_responses 写库。"""
    _enable(monkeypatch, module)
    _mock_resolver(monkeypatch, module, [_binding(anchor, expr, wp_code=wp_code)])
    _mock_evaluator(monkeypatch, module, value=Decimal(_TB_VALUE))
    db = _FakeSession()
    result = _run(module.render(_ctx(db)))
    assert result["responses_snapshot"][anchor]["remark"] == _TB_VALUE
    joined = " ".join(db.executed_sql)
    assert "insert into" not in joined and "update " not in joined, (
        f"{wp_code} Tier A transient seed 不得写 checklist_responses/DB（Property 13）"
    )
