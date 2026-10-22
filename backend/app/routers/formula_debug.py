"""公式调试/模拟器端点（spec: formula-management-deep-optimization · R3）。

POST /api/formula/debug
接收公式文本和项目上下文，构造 FormulaContext，调用 execute 返回逐步 trace。
只读操作，不写数据。
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/formula", tags=["formula-debug"])


class FormulaDebugRequest(BaseModel):
    """调试请求体。"""
    formula: str = Field(..., min_length=1, max_length=2000, description="待调试的公式文本")
    project_id: str = Field(..., description="项目 ID")
    year: int = Field(..., ge=2000, le=2099, description="审计年度")
    scope: str = Field("report", description="作用域：report / note / wp / tb_detail")
    # 可选：用户可传入自定义上下文覆盖自动取数
    custom_context: dict[str, Any] | None = Field(None, description="自定义上下文（覆盖自动取数）")


class FormulaDebugResponse(BaseModel):
    """调试结果。"""
    value: str | None = None
    ok: bool = False
    state: str = "error"
    trace: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    context_summary: dict[str, Any] = {}


@router.post("/debug", response_model=FormulaDebugResponse)
async def debug_formula(
    body: FormulaDebugRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """调试运行公式：构造上下文 → 执行 → 返回 trace。

    鉴权：项目在请求体里（工厂依赖取不到），函数首句直调 ``assert_project_permission``
    判 readonly —— 调试会按该项目实时取数并原样回显（试算表、报表、附注、底稿），
    非成员必须 403 且不触达任何数据（spec formula-governance-coverage-closure R1.1）。
    """
    from app.services.formula_engine import FormulaContext, execute

    try:
        project_id = uuid.UUID(body.project_id)
    except ValueError:
        return FormulaDebugResponse(errors=["无效的项目 ID"], state="error")
    await assert_project_permission(db, _user, project_id, "readonly")

    # ── 构造 FormulaContext ──
    try:
        ctx = await _build_context(db, project_id, body.year, body.scope, body.custom_context)
    except Exception as exc:
        logger.warning("调试上下文构造失败: %s", exc)
        return FormulaDebugResponse(
            errors=[f"上下文构造失败：{exc}"],
            state="error",
        )

    # ── 构建上下文摘要（告诉前端加载了多少数据） ──
    summary = _context_summary(ctx)

    # ── 执行公式 ──
    try:
        result = execute(body.formula, ctx)
    except Exception as exc:
        logger.warning("调试执行失败: %s", exc)
        return FormulaDebugResponse(
            errors=[f"执行异常：{exc}"],
            state="error",
            context_summary=summary,
        )

    return FormulaDebugResponse(
        value=str(result.value) if result.value is not None else None,
        ok=result.ok,
        state=result.state,
        trace=result.trace,
        errors=result.errors,
        warnings=result.warnings,
        context_summary=summary,
    )


async def _build_context(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    scope: str,
    custom_context: dict[str, Any] | None,
) -> "FormulaContext":
    """构造调试用 FormulaContext。

    优先用 custom_context（用户指定的测试数据），否则从项目实时取数。
    """
    from app.services.formula_engine import FormulaContext

    if custom_context:
        # 用户自定义上下文：直接构造
        tb = {k: {c: Decimal(str(v)) for c, v in cols.items()}
              for k, cols in (custom_context.get("tb_data") or {}).items()}
        rows = {k: Decimal(str(v)) for k, v in (custom_context.get("row_cache") or {}).items()}
        return FormulaContext(tb_data=tb, row_cache=rows)

    # 自动取数：从项目的试算表 + 报表行加载数据快照
    tb_data: dict[str, dict[str, Decimal]] = {}
    row_cache: dict[str, Decimal] = {}

    try:
        import sqlalchemy as sa
        from app.models.four_table_models import TrialBalance

        tb_rows = (await db.execute(
            sa.select(
                TrialBalance.account_code,
                TrialBalance.unadjusted_amount,
                TrialBalance.audited_amount,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )).all()
        for row in tb_rows:
            code = row.account_code or ""
            ua = Decimal(str(row.unadjusted_amount or 0))
            aa = Decimal(str(row.audited_amount or 0))
            tb_data[code] = {"未审数": ua, "审定数": aa, "期末余额": aa}
    except Exception:
        logger.warning("调试：试算表取数失败", exc_info=True)

    try:
        import sqlalchemy as sa
        from app.models.report_models import FinancialReport

        report_rows = (await db.execute(
            sa.select(
                FinancialReport.row_code,
                FinancialReport.current_period_amount,
            ).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == sa.false(),
            )
        )).all()
        for row in report_rows:
            if row.row_code:
                row_cache[row.row_code] = Decimal(str(row.current_period_amount or 0))
    except Exception:
        logger.warning("调试：报表行取数失败", exc_info=True)

    return FormulaContext(tb_data=tb_data, row_cache=row_cache)


def _context_summary(ctx: Any) -> dict[str, Any]:
    """生成上下文摘要，告诉前端加载了多少数据。"""
    return {
        "tb_accounts": len(getattr(ctx, "tb_data", {})),
        "report_rows": len(getattr(ctx, "row_cache", {})),
        "prior_accounts": len(getattr(ctx, "prior_tb_data", {})),
        "note_sections": len(getattr(ctx, "note_data", {})),
        "wp_codes": len(getattr(ctx, "wp_data", {})),
        "adj_accounts": len(getattr(ctx, "adj_data", {})),
    }
