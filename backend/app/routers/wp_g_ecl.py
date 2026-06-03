"""G 投资循环 — G-F5 ECL 三阶段模型 API（IFRS 9 / CAS 22 预期信用损失）

POST /api/projects/{project_id}/workpapers/{wp_id}/g/ecl-calc

输入：stage(1/2/3) + book_value(EAD) + pd_12m + pd_lifetime + lgd
输出：ecl_amount + formula_used + monotonicity_check + is_llm_stub

三阶段模型（IFRS 9 / CAS 22）：
- Stage 1（信用风险未显著增加）：ECL = EAD × PD_12m × LGD
- Stage 2（信用风险显著增加）：ECL = EAD × PD_lifetime × LGD
- Stage 3（已发生信用减值）：ECL = EAD × PD_lifetime × LGD（PD_lifetime 接近 100%）

单调性约束：当 pd_12m ≤ pd_lifetime 时，ECL(1) ≤ ECL(2) ≤ ECL(3)。

适用底稿：G4 债权投资 / G6 其他债权投资。

对应 spec：workpaper-g-investment-cycle G-F5 / ADR-G4
对应 task：Sprint 2 Task 2.8

is_llm_stub = False（纯确定性公式，不涉及 LLM；保留字段保持与其他 G endpoint 形态一致）。
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/g",
    tags=["wp-g-ecl"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class ECLCalcRequest(BaseModel):
    """ECL 三阶段计算请求"""

    stage: Literal[1, 2, 3] = Field(..., description="ECL 阶段（1/2/3）")
    book_value: Decimal = Field(..., description="账面余额 EAD（Exposure At Default，元）")
    pd_12m: Decimal = Field(..., description="12 个月违约概率（0~1）")
    pd_lifetime: Decimal = Field(..., description="存续期违约概率（0~1）")
    lgd: Decimal = Field(..., description="违约损失率 LGD（0~1）")

    # 写回
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.ecl_calcs[sheet]",
    )


class ECLCalcResponse(BaseModel):
    """ECL 三阶段计算响应"""

    stage: int
    ecl_amount: str
    formula_used: str
    monotonicity_check: bool
    is_llm_stub: bool
    applied_to_sheet: str | None = None


# ─── Calculation Helpers ──────────────────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）。"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _validate_inputs(payload: ECLCalcRequest) -> None:
    """校验 ECL 三阶段输入参数。错误返回 HTTP 400。

    错误处理（design.md ADR-G4 / 错误处理段落）：
    - book_value = 0 → "账面余额不能为零"
    - lgd > 1 或 < 0 → "LGD 应在 0~100% 之间"
    - pd_12m / pd_lifetime 越界 → "PD 应在 0~100% 之间"
    - pd_12m > pd_lifetime → "12 个月 PD 不应大于存续期 PD"
    """
    if payload.book_value == 0:
        raise HTTPException(400, "账面余额不能为零")
    if payload.book_value < 0:
        raise HTTPException(400, "账面余额不能为负数")
    if payload.book_value > Decimal("1e15"):
        raise HTTPException(400, "账面余额超出合理范围（不能超过 1e15）")

    if payload.lgd < 0 or payload.lgd > 1:
        raise HTTPException(400, "LGD 应在 0~100% 之间")

    if payload.pd_12m < 0 or payload.pd_12m > 1:
        raise HTTPException(400, "12 个月 PD 应在 0~100% 之间")
    if payload.pd_lifetime < 0 or payload.pd_lifetime > 1:
        raise HTTPException(400, "存续期 PD 应在 0~100% 之间")

    if payload.pd_12m > payload.pd_lifetime:
        raise HTTPException(400, "12 个月 PD 不应大于存续期 PD")


def _calc_ecl_stage_1(book_value: Decimal, pd_12m: Decimal, lgd: Decimal) -> Decimal:
    """Stage 1（信用风险未显著增加）：ECL = EAD × PD_12m × LGD（12 个月预期信用损失）。"""
    return _quantize(book_value * pd_12m * lgd)


def _calc_ecl_stage_2(book_value: Decimal, pd_lifetime: Decimal, lgd: Decimal) -> Decimal:
    """Stage 2（信用风险显著增加）：ECL = EAD × PD_lifetime × LGD（整个存续期，未信用减值）。"""
    return _quantize(book_value * pd_lifetime * lgd)


def _calc_ecl_stage_3(book_value: Decimal, pd_lifetime: Decimal, lgd: Decimal) -> Decimal:
    """Stage 3（已发生信用减值）：ECL = EAD × PD_lifetime × LGD（PD_lifetime 接近 100%）。

    公式与 Stage 2 一致，区别在于业务上 Stage 3 的 pd_lifetime 通常 ≥ 0.9（接近 100%），
    意味着违约几乎已发生。本 endpoint 不强制 Stage 3 的 PD 阈值（用户可输入实际估计值），
    仅依赖单调性前提（pd_12m ≤ pd_lifetime）保证 ECL(1) ≤ ECL(2) ≤ ECL(3)。
    """
    return _quantize(book_value * pd_lifetime * lgd)


def _check_monotonicity(
    book_value: Decimal,
    pd_12m: Decimal,
    pd_lifetime: Decimal,
    lgd: Decimal,
) -> bool:
    """单调性校验：在 pd_12m ≤ pd_lifetime 前提下，ECL(1) ≤ ECL(2) ≤ ECL(3)。

    当输入合法（pd_12m ≤ pd_lifetime，由 _validate_inputs 保证）且金额非负时，
    数学上必然成立；本函数显式计算以提供端到端验证（防御性编程 + 与 PBT-P6 对齐）。
    """
    e1 = _calc_ecl_stage_1(book_value, pd_12m, lgd)
    e2 = _calc_ecl_stage_2(book_value, pd_lifetime, lgd)
    e3 = _calc_ecl_stage_3(book_value, pd_lifetime, lgd)
    return e1 <= e2 <= e3


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/ecl-calc", response_model=ECLCalcResponse)
async def g_ecl_calc(
    project_id: str,
    wp_id: str,
    payload: ECLCalcRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> ECLCalcResponse:
    """G-F5 ECL 三阶段模型计算（IFRS 9 / CAS 22）

    - Stage 1: ECL = EAD × PD_12m × LGD
    - Stage 2: ECL = EAD × PD_lifetime × LGD
    - Stage 3: ECL = EAD × PD_lifetime × LGD（PD 接近 100%）

    输入校验失败返回 HTTP 400；单调性约束在合法输入下必然成立。
    """
    try:
        UUID(project_id)
    except Exception as exc:
        raise HTTPException(400, "invalid project_id") from exc

    _validate_inputs(payload)

    if payload.stage == 1:
        ecl_amount = _calc_ecl_stage_1(payload.book_value, payload.pd_12m, payload.lgd)
        formula_used = (
            f"Stage 1（信用风险未显著增加）：ECL = EAD × PD_12m × LGD = "
            f"{payload.book_value} × {payload.pd_12m} × {payload.lgd}"
        )
    elif payload.stage == 2:
        ecl_amount = _calc_ecl_stage_2(payload.book_value, payload.pd_lifetime, payload.lgd)
        formula_used = (
            f"Stage 2（信用风险显著增加）：ECL = EAD × PD_lifetime × LGD = "
            f"{payload.book_value} × {payload.pd_lifetime} × {payload.lgd}"
        )
    else:
        ecl_amount = _calc_ecl_stage_3(payload.book_value, payload.pd_lifetime, payload.lgd)
        formula_used = (
            f"Stage 3（已发生信用减值，PD 接近 100%）：ECL = EAD × PD_lifetime × LGD = "
            f"{payload.book_value} × {payload.pd_lifetime} × {payload.lgd}"
        )

    monotonicity_check = _check_monotonicity(
        payload.book_value, payload.pd_12m, payload.pd_lifetime, payload.lgd,
    )

    applied_to_sheet = await _maybe_apply_ecl_to_workpaper(
        db, wp_id, payload, ecl_amount, formula_used, monotonicity_check,
    )

    return ECLCalcResponse(
        stage=payload.stage,
        ecl_amount=str(ecl_amount),
        formula_used=formula_used,
        monotonicity_check=monotonicity_check,
        is_llm_stub=False,  # 纯确定性公式，不涉及 LLM
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_ecl_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: ECLCalcRequest,
    ecl_amount: Decimal,
    formula_used: str,
    monotonicity_check: bool,
) -> str | None:
    """若 apply_to_sheet 给出则把 ECL 计算结果写回 working_paper.parsed_data。

    数据结构（与 wp_g_fair_value.py fair_value_tests 对称）：
      parsed_data.ecl_calcs[sheet] = {
        "stage": 1|2|3,
        "ecl_amount": "...",
        "formula_used": "...",
        "monotonicity_check": bool,
        "applied_at": ISO8601,
        "inputs": {
          "book_value": "...",
          "pd_12m": "...",
          "pd_lifetime": "...",
          "lgd": "...",
        },
      }
    """
    if not payload.apply_to_sheet:
        return None

    from datetime import datetime, timezone

    from app.models.workpaper_models import WorkingPaper

    try:
        wp_uuid = UUID(wp_id)
    except Exception:
        return None

    res = await db.execute(sa.select(WorkingPaper).where(WorkingPaper.id == wp_uuid))
    wp = res.scalar_one_or_none()
    if wp is None:
        return None

    pd = wp.parsed_data or {}
    if not isinstance(pd, dict):
        pd = {}
    pd.setdefault("ecl_calcs", {})
    pd["ecl_calcs"][payload.apply_to_sheet] = {
        "stage": payload.stage,
        "ecl_amount": str(ecl_amount),
        "formula_used": formula_used,
        "monotonicity_check": monotonicity_check,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "book_value": str(payload.book_value),
            "pd_12m": str(payload.pd_12m),
            "pd_lifetime": str(payload.pd_lifetime),
            "lgd": str(payload.lgd),
        },
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    from app.services.wp_parsed_data_service import touch_after_parsed_data_commit

    await touch_after_parsed_data_commit(wp, source="wp_g_ecl")
    return payload.apply_to_sheet
