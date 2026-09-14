"""单元测试：审定表回写契约（Task 7.1 / Req 13）。

覆盖：
- auto_calc 审定表公式执行 → 回写 trial_balance.audited_amount（仅 audited，不动 unadjusted）
- 记 last_computed_at（Req 13.3）
- 悬空引用拒写 → 返回 Issue_List，不回写（Req 13.4）
- fail-open（ACNR 不可用）不视为悬空，照常回写（Req 11.3）
- 非 auto_calc 类型拒绝回写
- 科目缺失 → Issue，不改值
- 批量回写发生变更后触发 ACNR 失效链（复用 acnr.events.invalidate，Req 13.5）
- 仅 flush 不 commit（工程铁律）

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.services.formula_engine import FormulaContext
from app.services.formula_management import adjudication_writeback as awb
from app.services.formula_management.adjudication_writeback import (
    AdjudicationWritebackService,
)
from app.services.formula_management.engine import FormulaRecord, ResolveRefResult

PROJECT_ID = uuid4()
YEAR = 2025


class FakeTBRow:
    """模拟 TrialBalance ORM 行（含 unadjusted / audited）。"""

    def __init__(self, code: str, unadj: float = 1000.0, audited: float | None = None):
        self.standard_account_code = code
        self.unadjusted_amount = Decimal(str(unadj))
        self.audited_amount = Decimal(str(audited)) if audited is not None else None
        self.is_deleted = False


def _mock_db_with_rows(rows: list[FakeTBRow] | None = None):
    """构造 mock AsyncSession：execute → result.scalars().all() 返回 rows。"""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows or []
    result.scalars.return_value = scalars
    db.execute = AsyncMock(return_value=result)
    return db


def _auto_calc(code: str, expr: str, refs=None) -> FormulaRecord:
    return FormulaRecord(
        id=f"f-{code}",
        formula_type="auto_calc",
        target_cell=code,
        expression=expr,
        refs=refs or [],
    )


def _ctx() -> FormulaContext:
    return FormulaContext(
        row_cache={"unadj": Decimal("1000"), "aje": Decimal("200")}
    )


# ─────────────────────────── 正常回写 ───────────────────────────
@pytest.mark.asyncio
async def test_writeback_sets_audited_not_unadjusted():
    row = FakeTBRow("1122", unadj=1000.0, audited=None)
    db = _mock_db_with_rows([row])
    svc = AdjudicationWritebackService(db)

    f = _auto_calc("1122", "ROW('unadj') + ROW('aje')")
    res = await svc.writeback_formula(
        PROJECT_ID, YEAR, f, ctx=_ctx()
    )

    # 仅 audited 被回写，unadjusted 不变（Req 13.1/13.2）
    assert row.audited_amount == Decimal("1200")
    assert row.unadjusted_amount == Decimal("1000")
    assert res.updated_accounts == ["1122"]
    assert res.values["1122"] == Decimal("1200")
    # 记 last_computed_at（Req 13.3）
    assert "1122" in res.last_computed_at
    assert res.changed is True
    assert res.issues == []
    # 仅 flush 不 commit
    db.flush.assert_awaited()
    db.commit.assert_not_awaited()


# ─────────────────────────── 悬空引用拒写 ───────────────────────────
@pytest.mark.asyncio
async def test_dangling_ref_rejects_writeback(monkeypatch):
    row = FakeTBRow("1122", unadj=1000.0, audited=500.0)
    db = _mock_db_with_rows([row])
    svc = AdjudicationWritebackService(db)

    async def _dangling(**kwargs):
        return ResolveRefResult(found=False, fail_open=False, formula_ref=kwargs.get("formula_ref"))

    monkeypatch.setattr(awb, "resolve_ref", _dangling)

    f = _auto_calc(
        "1122", "ROW('unadj')", refs=[{"formula_ref": "WP('X','sheet','E1')"}]
    )
    res = await svc.writeback_formula(PROJECT_ID, YEAR, f, ctx=_ctx())

    # 拒写：audited 保持原值不变
    assert row.audited_amount == Decimal("500.0")
    assert res.updated_accounts == []
    assert res.changed is False
    assert len(res.issues) == 1
    assert "悬空" in res.issues[0].description


# ─────────────────────────── fail-open 不视为悬空 ───────────────────────────
@pytest.mark.asyncio
async def test_fail_open_not_treated_as_dangling(monkeypatch):
    row = FakeTBRow("1122", unadj=1000.0, audited=None)
    db = _mock_db_with_rows([row])
    svc = AdjudicationWritebackService(db)

    async def _fail_open(**kwargs):
        # ACNR 基础设施不可用 → fail-open（found=False 但 fail_open=True）
        return ResolveRefResult(found=False, fail_open=True, formula_ref=kwargs.get("formula_ref"))

    monkeypatch.setattr(awb, "resolve_ref", _fail_open)

    f = _auto_calc(
        "1122", "ROW('unadj') + ROW('aje')", refs=[{"formula_ref": "WP('X','s','E1')"}]
    )
    res = await svc.writeback_formula(PROJECT_ID, YEAR, f, ctx=_ctx())

    # fail-open 不拒写，照常回写（Req 11.3）
    assert row.audited_amount == Decimal("1200")
    assert res.updated_accounts == ["1122"]
    assert res.issues == []


# ─────────────────────────── 非 auto_calc 拒绝 ───────────────────────────
@pytest.mark.asyncio
async def test_non_auto_calc_rejected():
    row = FakeTBRow("1122", audited=500.0)
    db = _mock_db_with_rows([row])
    svc = AdjudicationWritebackService(db)

    f = FormulaRecord(
        id="f-lc",
        formula_type="logic_check",
        target_cell="1122",
        expression="ROW('unadj') > 0",
    )
    res = await svc.writeback_formula(PROJECT_ID, YEAR, f, ctx=_ctx())

    assert row.audited_amount == Decimal("500.0")  # 不改值
    assert res.updated_accounts == []
    assert len(res.issues) == 1
    assert "auto_calc" in res.issues[0].description


# ─────────────────────────── 科目缺失 ───────────────────────────
@pytest.mark.asyncio
async def test_account_not_found_records_issue():
    db = _mock_db_with_rows([])  # 无匹配行
    svc = AdjudicationWritebackService(db)

    f = _auto_calc("9999", "ROW('unadj')")
    res = await svc.writeback_formula(PROJECT_ID, YEAR, f, ctx=_ctx())

    assert res.updated_accounts == []
    assert res.changed is False
    assert len(res.issues) == 1
    assert "未找到科目" in res.issues[0].description


# ─────────────────────────── 求值失败保留原值 ───────────────────────────
@pytest.mark.asyncio
async def test_eval_failure_keeps_audited():
    row = FakeTBRow("1122", audited=500.0)
    db = _mock_db_with_rows([row])
    svc = AdjudicationWritebackService(db)

    f = _auto_calc("1122", "1 + * 2")  # 解析错误
    res = await svc.writeback_formula(PROJECT_ID, YEAR, f, ctx=_ctx())

    assert row.audited_amount == Decimal("500.0")  # 保留原值
    assert res.updated_accounts == []
    assert len(res.issues) == 1


# ─────────────────────────── 批量触发失效链 ───────────────────────────
@pytest.mark.asyncio
async def test_batch_triggers_acnr_invalidate():
    row = FakeTBRow("1122", unadj=1000.0, audited=None)
    db = _mock_db_with_rows([row])
    svc = AdjudicationWritebackService(db)

    f = _auto_calc("1122", "ROW('unadj') + ROW('aje')")

    with patch(
        "app.services.acnr.events.invalidate", new=AsyncMock()
    ) as mock_invalidate:
        res = await svc.writeback_batch(PROJECT_ID, YEAR, [f], ctx=_ctx())

    assert res.changed is True
    assert row.audited_amount == Decimal("1200")
    # 复用 ACNR 失效链（Req 13.5）
    mock_invalidate.assert_awaited_once()
    _, kwargs = mock_invalidate.call_args
    assert kwargs.get("trigger") == "adjudication_writeback"
    db.commit.assert_not_awaited()  # service 不 commit


@pytest.mark.asyncio
async def test_batch_no_change_no_invalidate():
    db = _mock_db_with_rows([])  # 科目缺失 → 无变更
    svc = AdjudicationWritebackService(db)

    f = _auto_calc("9999", "ROW('unadj')")

    with patch(
        "app.services.acnr.events.invalidate", new=AsyncMock()
    ) as mock_invalidate:
        res = await svc.writeback_batch(PROJECT_ID, YEAR, [f], ctx=_ctx())

    assert res.changed is False
    mock_invalidate.assert_not_awaited()  # 无变更不触发失效链
