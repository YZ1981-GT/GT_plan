"""H3 投资性房地产 — 互转引擎端点

POST /api/workpapers/{wp_id}/h3/transfer/calculate → 三方向计算
POST /api/workpapers/{wp_id}/h3/transfer/validate → 验证转出=转入一致性

纯函数实现（与前端 useH3TransferEngine.ts 对等逻辑）
CAS3投资性房地产互转规则：
- 自用→投资(公允): 公允>账面→差额入OCI；公允<账面→差额入PL
- 投资→自用: 公允价值作为入账成本
- 在建→投资(成本): 账面价值=入账成本
- 在建→投资(公允): 公允价值作为入账成本，差额入PL
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["h3-transfer"])


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：互转计算引擎（与前端 useH3TransferEngine.ts 对等）
# ═══════════════════════════════════════════════════════════════════════════════


def calc_self_to_invest_fair(book_value: float, fair_value: float) -> dict[str, float]:
    """自用→投资(公允模式): 公允>账面→OCI；公允<账面→PL.

    Returns:
        {"entry_value": fair_value, "oci": max(diff,0), "pl": min(diff,0), "diff": diff}
    """
    diff = fair_value - book_value
    return {
        "entry_value": fair_value,
        "oci": max(diff, 0.0),
        "pl": min(diff, 0.0),
        "diff": diff,
    }


def calc_invest_to_self(fair_value: float) -> dict[str, float]:
    """投资→自用: 公允价值作为新入账成本.

    Returns:
        {"entry_value": fair_value}
    """
    return {"entry_value": fair_value}


def calc_cip_to_invest_cost(cip_book_value: float) -> dict[str, float]:
    """在建→投资(成本模式): 账面价值直接转入.

    Returns:
        {"entry_value": cip_book_value, "diff": 0}
    """
    return {"entry_value": cip_book_value, "diff": 0.0}


def calc_cip_to_invest_fair(cip_book_value: float, fair_value: float) -> dict[str, float]:
    """在建→投资(公允模式): 公允→入账，差额入PL.

    Returns:
        {"entry_value": fair_value, "diff": fair_value - cip_book_value, "pl": fair_value - cip_book_value}
    """
    diff = fair_value - cip_book_value
    return {
        "entry_value": fair_value,
        "diff": diff,
        "pl": diff,
    }


def calc_transfer_diff(transfer_out: float, transfer_in: float) -> float:
    """转出=转入差额（应为0）."""
    return transfer_out - transfer_in


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════════════════════════


class TransferItem(BaseModel):
    asset_name: str = ""
    direction: str = Field(description="selfToInvest / investToSelf / cipToInvest")
    measurement_model: str = Field(default="cost", description="cost / fair_value")
    book_value: float = Field(default=0.0, description="转出方账面价值")
    fair_value: float = Field(default=0.0, description="公允价值（公允模式必填）")
    cip_book_value: float = Field(default=0.0, description="在建工程账面（cipToInvest方向）")


class CalculateRequest(BaseModel):
    items: list[TransferItem] = Field(min_length=1, description="互转项目列表")


class TransferResult(BaseModel):
    asset_name: str = ""
    direction: str = ""
    entry_value: float = 0.0
    oci: float = 0.0
    pl: float = 0.0
    diff: float = 0.0


class CalculateResponse(BaseModel):
    results: list[TransferResult]
    total_transfer_out: float = 0.0
    total_transfer_in: float = 0.0
    total_oci: float = 0.0
    total_pl: float = 0.0


class ValidateRequest(BaseModel):
    items: list[TransferItem] = Field(min_length=1, description="互转项目列表")
    tolerance: float = Field(default=0.01, description="允许差异容忍度（元）")


class ValidateResponse(BaseModel):
    is_valid: bool
    total_transfer_out: float
    total_transfer_in: float
    total_difference: float
    summary: str
    details: list[TransferResult]


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


def _calculate_item(item: TransferItem) -> TransferResult:
    """计算单项互转."""
    if item.direction == "selfToInvest":
        r = calc_self_to_invest_fair(item.book_value, item.fair_value)
        return TransferResult(
            asset_name=item.asset_name,
            direction=item.direction,
            entry_value=r["entry_value"],
            oci=r["oci"],
            pl=r["pl"],
            diff=r["diff"],
        )
    elif item.direction == "investToSelf":
        r = calc_invest_to_self(item.fair_value)
        return TransferResult(
            asset_name=item.asset_name,
            direction=item.direction,
            entry_value=r["entry_value"],
        )
    elif item.direction == "cipToInvest":
        if item.measurement_model == "fair_value":
            r = calc_cip_to_invest_fair(item.cip_book_value, item.fair_value)
            return TransferResult(
                asset_name=item.asset_name,
                direction=item.direction,
                entry_value=r["entry_value"],
                pl=r["pl"],
                diff=r["diff"],
            )
        else:
            r = calc_cip_to_invest_cost(item.cip_book_value)
            return TransferResult(
                asset_name=item.asset_name,
                direction=item.direction,
                entry_value=r["entry_value"],
                diff=r["diff"],
            )
    else:
        raise ValueError(f"不支持的方向: {item.direction}")


@router.post("/api/workpapers/{wp_id}/h3/transfer/calculate", response_model=CalculateResponse)
async def h3_transfer_calculate(
    wp_id: str,
    body: CalculateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalculateResponse:
    """互转三方向计算（自用→投资 / 投资→自用 / 在建→投资）."""
    results: list[TransferResult] = []
    for item in body.items:
        try:
            results.append(_calculate_item(item))
        except ValueError as e:
            raise HTTPException(400, str(e))

    # 汇总
    total_out = sum(item.book_value or item.cip_book_value for item in body.items)
    total_in = sum(r.entry_value for r in results)
    total_oci = sum(r.oci for r in results)
    total_pl = sum(r.pl for r in results)

    return CalculateResponse(
        results=results,
        total_transfer_out=round(total_out, 2),
        total_transfer_in=round(total_in, 2),
        total_oci=round(total_oci, 2),
        total_pl=round(total_pl, 2),
    )


@router.post("/api/workpapers/{wp_id}/h3/transfer/validate", response_model=ValidateResponse)
async def h3_transfer_validate(
    wp_id: str,
    body: ValidateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValidateResponse:
    """验证转出=转入一致性."""
    results: list[TransferResult] = []
    for item in body.items:
        try:
            results.append(_calculate_item(item))
        except ValueError as e:
            raise HTTPException(400, str(e))

    total_out = sum(item.book_value or item.cip_book_value for item in body.items)
    total_in = sum(r.entry_value for r in results)
    total_difference = calc_transfer_diff(total_out, total_in)
    is_valid = abs(total_difference) <= body.tolerance

    # 对于公允模式互转，差异由OCI/PL吸收，这是正常的
    # 因此实际验证的是：转出原值 与 转入入账价值 + OCI + PL 的差异
    total_oci = sum(r.oci for r in results)
    total_pl = sum(r.pl for r in results)
    adjusted_diff = total_out - (total_in - total_oci - total_pl)
    adjusted_valid = abs(adjusted_diff) <= body.tolerance

    summary = (
        f"互转一致性验证：\n"
        f"转出合计={total_out:,.2f}元，转入合计={total_in:,.2f}元，"
        f"直接差异={total_difference:,.2f}元，"
        f"OCI={total_oci:,.2f}元，PL={total_pl:,.2f}元，"
        f"调整后差异={adjusted_diff:,.2f}元，"
        f"容忍度={body.tolerance:,.2f}元，"
        f"结果：{'通过' if adjusted_valid else '差异超容忍度'}"
    )

    return ValidateResponse(
        is_valid=adjusted_valid,
        total_transfer_out=round(total_out, 2),
        total_transfer_in=round(total_in, 2),
        total_difference=round(total_difference, 2),
        summary=summary,
        details=results,
    )
