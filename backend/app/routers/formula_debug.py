"""公式调试/模拟器端点（spec: formula-management-deep-optimization · R3）。

POST /api/formula/debug
接收公式文本和项目上下文，构造 FormulaContext，调用 execute 返回逐步 trace。
只读操作，不写数据。
"""
from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import assert_project_permission, get_current_user

if TYPE_CHECKING:
    from app.services.formula_engine import FormulaContext

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
    from app.services.formula_engine import execute

    try:
        project_id = uuid.UUID(body.project_id)
    except ValueError:
        return FormulaDebugResponse(errors=["无效的项目 ID"], state="error")
    await assert_project_permission(db, _user, project_id, "readonly")

    # ── 构造 FormulaContext（自动取数时按该公式预载；取数缺口进 warnings） ──
    gaps: list[str] = []
    try:
        ctx = await _build_context(db, project_id, body.year, body.scope, body.custom_context,
                                   formula=body.formula, gaps=gaps)
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
        warnings=[*result.warnings, *gaps],
        context_summary=summary,
    )


async def _build_context(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    scope: str,
    custom_context: dict[str, Any] | None,
    formula: str = "",
    gaps: list[str] | None = None,
) -> "FormulaContext":
    """构造调试用 FormulaContext。

    优先用 custom_context（用户指定的测试数据）；否则按待调试公式走统一预载层（``formula_preloader.preload``）取该项目
    实时数据，与预填 / 报表求值同一套取数（试算表前缀聚合、调整额、辅助核算、底稿锚点、附注、上年、序时账、报表行）。
    调整额口径按作用域：报表 / 附注排除底稿来源（报表路径），底稿 / 明细不排除（底稿路径）。取数缺口写进 ``gaps``。

    原实现自拼上下文：从不存在的 ``app.models.four_table_models`` / ``app.models.disclosure_models`` 导入（被 except
    吞掉，试算表与附注恒空），列名也不对（试算表没有 ``account_code``），调整额 / 底稿 / 上年 / 辅助核算一律不取 ——
    调试结果与真实求值对不上（spec formula-fetch-followup-defect-closure 6.6）。
    """
    from app.services.formula_engine import FormulaContext

    if custom_context:
        # 用户自定义上下文：直接构造
        tb = {k: {c: Decimal(str(v)) for c, v in cols.items()}
              for k, cols in (custom_context.get("tb_data") or {}).items()}
        rows = {k: Decimal(str(v)) for k, v in (custom_context.get("row_cache") or {}).items()}
        return FormulaContext(tb_data=tb, row_cache=rows)

    from app.services.formula_preloader import preload
    from app.services.formula_ref_check import project_ref_scope

    _year, template_type = await project_ref_scope(db, project_id)
    exclude = frozenset({"workpaper"}) if scope in ("report", "note") else frozenset()
    return await preload(db, project_id, year, [formula], adj_exclude_origins=exclude,
                         template_type=template_type, gaps=gaps)


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
