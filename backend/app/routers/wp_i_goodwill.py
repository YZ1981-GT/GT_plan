"""I 无形资产循环 — I-F4 商誉减值 DCF 模型 LLM 辅助 API

POST /api/projects/{project_id}/workpapers/{wp_id}/i3/goodwill-impairment

输入：CGU ID / 商誉账面价值 / 资产组其他资产账面价值 / 5 年现金流预测 / 折现率 / 终值增长率
输出：可收回金额 + 减值损失 + 商誉减值分摊 + 结论

CAS 8 / IFRS 36 商誉减值分摊逻辑：
    Step 1: 用 DCF 测算 CGU 可收回金额（含 Gordon growth model 终值）
        NPV = Σ(CF_t / (1+r)^t)
        if g > 0:
            TV = CF_n × (1+g) / (r - g)        # Gordon growth model
            NPV += TV / (1+r)^n
    Step 2: 减值损失 = max(0, total_book_value - recoverable_amount)
        其中 total_book_value = goodwill_book_value + other_assets_book_value
    Step 3: 减值分摊
        - 优先冲减商誉（最多至商誉账面价值）
        - 剩余按比例分摊到 CGU 其他资产（前端再细化拆分）

当前为 stub 实现（DCF + 分摊公式正确，LLM 真实接入待 wp_ai_service 升级）。

对应 spec：workpaper-i-intangible-assets-cycle I-F4
对应 ADR：ADR-I3
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.deps import require_project_access

router = APIRouter(
    prefix="/api/projects/{project_id}/workpapers/{wp_id}/i3",
    tags=["wp-i-goodwill"],
)


# ─── Input / Output Schemas ───────────────────────────────────────────────────


class GoodwillImpairmentRequest(BaseModel):
    """商誉减值分析请求"""

    cgu_id: str = Field(..., description="资产组 ID（CGU，如 CGU-G-001）")
    goodwill_book_value: Decimal = Field(
        ..., gt=0, description="商誉账面价值（元，必须 > 0）"
    )
    other_assets_book_value: Decimal = Field(
        ...,
        ge=0,
        description="CGU 其他资产合计账面价值（不含商誉，元）",
    )
    cash_flows: list[Decimal] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="未来 N 年（通常 5 年）预测现金流（元）",
    )
    discount_rate: Decimal = Field(
        ...,
        gt=0,
        lt=1,
        description="折现率 r（0~1，如 0.10 = 10%）",
    )
    terminal_growth_rate: Decimal = Field(
        default=Decimal("0"),
        ge=0,
        description="终值永续增长率 g（Gordon growth model；0 = 不计终值；必须 < 折现率 r）",
    )
    apply_to_sheet: str | None = Field(
        None,
        description="若给出 sheet 名，则将结果写回 working_paper.parsed_data.goodwill_impairment_analyses[sheet]",
    )
    cgu_assets: list[dict] | None = Field(
        default=None,
        description=(
            "可选 — CGU 内资产清单（CAS 8 / IFRS 36 完整版分摊）。"
            "每项含 name (str), book_value (Decimal/数值)，"
            "可选 recoverable_amount (Decimal/数值)。"
            "为 None 或空时仅返回汇总分摊（向后兼容）。"
        ),
    )


class GoodwillImpairmentResponse(BaseModel):
    """商誉减值分析响应"""

    cgu_id: str
    goodwill_book_value: str
    other_assets_book_value: str
    total_book_value: str
    present_value_of_cash_flows: str
    recoverable_amount: str
    impairment_loss: str
    goodwill_writedown: str
    other_assets_writedown: str
    is_impaired: bool
    dcf_details: list[dict]
    asset_allocations: list[dict] = Field(
        default_factory=list,
        description=(
            "CGU 内各资产分摊明细（CAS 8 / IFRS 36 完整版）。"
            "每项含 name / book_value / recoverable_amount / "
            "allocated_impairment / post_impairment_book_value。"
            "未传 cgu_assets 时为空列表（向后兼容）。"
        ),
    )
    summary: str
    is_llm_stub: bool = Field(
        default=True,
        description=(
            "是否为 LLM stub 实现。运行时由 settings.WP_AI_SERVICE_ENABLED 驱动："
            "未配置（默认）→ True / 配置真实 LLM 后 → False。"
        ),
    )
    applied_to_sheet: str | None = None


# ─── DCF + Gordon Growth Calculation ──────────────────────────────────────────


def _quantize(value: Decimal) -> Decimal:
    """保留 2 位小数（四舍五入）"""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _calc_dcf_with_gordon(
    cash_flows: list[Decimal],
    discount_rate: Decimal,
    terminal_growth_rate: Decimal,
) -> tuple[Decimal, list[dict]]:
    """计算未来现金流现值（含 Gordon growth model 终值）

    NPV = Σ(CF_t / (1+r)^t)
    if g > 0:
        TV = CF_n × (1+g) / (r - g)
        NPV += TV / (1+r)^n

    Args:
        cash_flows: N 年现金流列表
        discount_rate: 折现率 r
        terminal_growth_rate: 永续增长率 g（0 表示不计终值）

    Returns:
        (npv, details) where details 是逐年明细
    """
    details: list[dict] = []
    npv = Decimal("0")
    n = len(cash_flows)

    for t, cf in enumerate(cash_flows, start=1):
        discount_factor = (Decimal("1") + discount_rate) ** t
        pv = _quantize(cf / discount_factor)
        npv += pv
        details.append({
            "year": t,
            "cash_flow": str(cf),
            "discount_factor": str(_quantize(discount_factor)),
            "present_value": str(pv),
        })

    # Gordon growth model 终值（仅当 g > 0 且 r > g）
    if terminal_growth_rate > 0:
        last_cf = cash_flows[-1]
        terminal_value_undiscounted = (
            last_cf * (Decimal("1") + terminal_growth_rate)
            / (discount_rate - terminal_growth_rate)
        )
        terminal_discount_factor = (Decimal("1") + discount_rate) ** n
        terminal_pv = _quantize(terminal_value_undiscounted / terminal_discount_factor)
        npv += terminal_pv
        details.append({
            "year": f"终值(Y{n}末, Gordon g={terminal_growth_rate})",
            "cash_flow": str(_quantize(terminal_value_undiscounted)),
            "discount_factor": str(_quantize(terminal_discount_factor)),
            "present_value": str(terminal_pv),
        })

    return _quantize(npv), details


def _allocate_goodwill_impairment(
    impairment_loss: Decimal,
    goodwill_book_value: Decimal,
    cgu_assets: list[dict] | None = None,
) -> tuple[Decimal, Decimal, list[dict]]:
    """商誉减值分摊（CAS 8 / IFRS 36 完整版）

    Step 1: 优先冲减商誉，最多至商誉账面价值
    Step 2: 剩余按 CGU 内各资产 book_value 比例分摊
    Step 3: 每项资产 post-impairment 账面 ≥ max(recoverable_amount, 0)；
            超下限的"溢出"重新按比例分摊到剩余可分摊资产
    Step 4: 迭代至所有资产满足下限或溢出 < 0.01（最多 10 次防死锁）

    Args:
        impairment_loss: 总减值损失
        goodwill_book_value: 商誉账面价值
        cgu_assets: 可选，CGU 内资产清单。每项含 name / book_value
                    （Decimal 或可转 Decimal 的数值）+ 可选 recoverable_amount。
                    为 None 时保持原行为（仅返回 2-tuple-like 但仍返回空列表）。

    Returns:
        (goodwill_writedown, total_other_writedown, asset_allocations)
        - asset_allocations: list[dict]，每项含
          {name, book_value, recoverable_amount, allocated_impairment,
           post_impairment_book_value}；当 cgu_assets 为 None 时为空列表。
    """
    if impairment_loss <= 0:
        # 无减值；若有资产清单则填零分摊以便前端展示
        if cgu_assets:
            allocs = []
            for a in cgu_assets:
                bv = Decimal(str(a["book_value"]))
                ra_raw = a.get("recoverable_amount")
                ra = Decimal(str(ra_raw)) if ra_raw is not None else None
                allocs.append({
                    "name": str(a.get("name", "")),
                    "book_value": str(_quantize(bv)),
                    "recoverable_amount": (
                        str(_quantize(ra)) if ra is not None else None
                    ),
                    "allocated_impairment": "0.00",
                    "post_impairment_book_value": str(_quantize(bv)),
                })
            return Decimal("0.00"), Decimal("0.00"), allocs
        return Decimal("0.00"), Decimal("0.00"), []

    # Step 1: 商誉先冲减
    goodwill_writedown = min(goodwill_book_value, impairment_loss)
    remaining = impairment_loss - goodwill_writedown

    # 向后兼容：未传 cgu_assets 时仅返回汇总
    if not cgu_assets:
        return _quantize(goodwill_writedown), _quantize(remaining), []

    # 初始化资产状态
    assets: list[dict] = []
    for a in cgu_assets:
        bv = Decimal(str(a["book_value"]))
        ra_raw = a.get("recoverable_amount")
        ra = Decimal(str(ra_raw)) if ra_raw is not None else None
        floor = max(ra, Decimal("0")) if ra is not None else Decimal("0")
        max_writedown = max(bv - floor, Decimal("0"))
        assets.append({
            "name": str(a.get("name", "")),
            "book_value": bv,
            "recoverable_amount": ra,
            "floor": floor,
            "max_writedown": max_writedown,
            "allocated": Decimal("0"),
        })

    # Step 2~4: 迭代按比例分摊 + 下限保护
    epsilon = Decimal("0.01")
    max_iter = 10
    overflow = remaining

    for _ in range(max_iter):
        if overflow < epsilon:
            break
        eligible = [
            a for a in assets if a["allocated"] < a["max_writedown"]
        ]
        if not eligible:
            break
        eligible_bv_total = sum(
            (a["book_value"] for a in eligible), Decimal("0")
        )
        if eligible_bv_total <= 0:
            break

        new_overflow = Decimal("0")
        for a in eligible:
            share = overflow * (a["book_value"] / eligible_bv_total)
            available = a["max_writedown"] - a["allocated"]
            actual = min(share, available)
            a["allocated"] += actual
            new_overflow += (share - actual)
        overflow = new_overflow

    total_other_writedown = sum(
        (a["allocated"] for a in assets), Decimal("0")
    )

    allocations = [
        {
            "name": a["name"],
            "book_value": str(_quantize(a["book_value"])),
            "recoverable_amount": (
                str(_quantize(a["recoverable_amount"]))
                if a["recoverable_amount"] is not None
                else None
            ),
            "allocated_impairment": str(_quantize(a["allocated"])),
            "post_impairment_book_value": str(
                _quantize(a["book_value"] - a["allocated"])
            ),
        }
        for a in assets
    ]
    return (
        _quantize(goodwill_writedown),
        _quantize(total_other_writedown),
        allocations,
    )


# ─── Main Endpoint ────────────────────────────────────────────────────────────


@router.post("/goodwill-impairment", response_model=GoodwillImpairmentResponse)
async def i3_goodwill_impairment_analysis(
    project_id: str,
    wp_id: str,
    payload: GoodwillImpairmentRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_project_access("edit")),
) -> GoodwillImpairmentResponse:
    """I-F4 商誉减值 DCF 模型辅助分析（LLM stub 实现）

    可收回金额 = NPV(未来现金流) + 终值（Gordon growth）
    总账面价值 = 商誉 + CGU 其他资产
    减值损失 = max(0, 总账面价值 − 可收回金额)
    分摊：先冲商誉，剩余分摊到其他资产
    """
    try:
        UUID(project_id)
    except Exception:
        raise HTTPException(400, "invalid project_id")

    # 参数校验
    if payload.goodwill_book_value > Decimal("1e15"):
        raise HTTPException(400, "商誉账面价值超出合理范围（不能超过 1e15）")
    if payload.other_assets_book_value > Decimal("1e15"):
        raise HTTPException(400, "CGU 其他资产账面价值超出合理范围（不能超过 1e15）")
    if payload.discount_rate <= 0 or payload.discount_rate >= 1:
        raise HTTPException(400, "折现率必须在 (0, 1) 范围内")
    if payload.terminal_growth_rate < 0:
        raise HTTPException(400, "终值增长率不能为负")
    if payload.terminal_growth_rate >= payload.discount_rate:
        raise HTTPException(
            400,
            "终值增长率必须小于折现率（Gordon growth 公式 r > g 否则发散）",
        )
    if len(payload.cash_flows) == 0:
        raise HTTPException(400, "至少需要 1 年的现金流预测")

    # DCF + Gordon growth 计算
    pv_cash_flows, dcf_details = _calc_dcf_with_gordon(
        payload.cash_flows,
        payload.discount_rate,
        payload.terminal_growth_rate,
    )

    recoverable_amount = pv_cash_flows  # 可收回金额 = DCF NPV（含终值）
    total_book_value = _quantize(
        payload.goodwill_book_value + payload.other_assets_book_value
    )

    # 减值损失 = max(0, 总账面价值 − 可收回金额)
    impairment_loss = _quantize(
        max(Decimal("0"), total_book_value - recoverable_amount)
    )
    is_impaired = impairment_loss > 0

    # 减值分摊：先冲商誉，剩余按 CGU 资产清单（如提供）按比例分摊 + 下限保护
    goodwill_writedown, other_assets_writedown, asset_allocations = (
        _allocate_goodwill_impairment(
            impairment_loss,
            payload.goodwill_book_value,
            cgu_assets=payload.cgu_assets,
        )
    )

    # 生成摘要（含完整变量插值，无论 stub 还是真实 LLM）
    cash_flows_str = " / ".join(f"¥{cf:,.0f}" for cf in payload.cash_flows[:3]) + (
        f" / …({len(payload.cash_flows)} 年)" if len(payload.cash_flows) > 3 else ""
    )
    summary = (
        f"资产组 {payload.cgu_id}：商誉 ¥{payload.goodwill_book_value:,.2f}（占比 "
        f"{(payload.goodwill_book_value / total_book_value * 100) if total_book_value else 0:.1f}%）+ "
        f"其他资产 ¥{payload.other_assets_book_value:,.2f} = "
        f"总账面 ¥{total_book_value:,.2f}；"
        f"未来现金流 [{cash_flows_str}] 现值 ¥{pv_cash_flows:,.2f}（折现率 {payload.discount_rate * 100:.1f}%"
    )
    if payload.terminal_growth_rate > 0:
        summary += f"，Gordon g={payload.terminal_growth_rate * 100:.1f}%"
    summary += f"）。可收回金额 ¥{recoverable_amount:,.2f}。"
    if is_impaired:
        summary += (
            f"应计提减值 ¥{impairment_loss:,.2f}："
            f"先冲减商誉 ¥{goodwill_writedown:,.2f}"
        )
        if other_assets_writedown > 0:
            summary += f"，剩余 ¥{other_assets_writedown:,.2f} 按比例分摊到其他资产"
        summary += "。"
    else:
        summary += "无需计提减值。"
    # 仅在 stub 模式下附加 stub 提示；真实 LLM 接入后此提示自动消失
    is_llm_stub_flag = not settings.WP_AI_SERVICE_ENABLED
    if is_llm_stub_flag:
        summary += "（DCF 公式计算结果，LLM 智能分析待 wp_ai_service 接入。）"

    # 写回
    applied_to_sheet = await _maybe_apply_goodwill_impairment_to_workpaper(
        db, wp_id, payload, pv_cash_flows, recoverable_amount, total_book_value,
        impairment_loss, goodwill_writedown, other_assets_writedown,
        is_impaired, dcf_details, summary,
        asset_allocations=asset_allocations,
    )

    return GoodwillImpairmentResponse(
        cgu_id=payload.cgu_id,
        goodwill_book_value=str(payload.goodwill_book_value),
        other_assets_book_value=str(payload.other_assets_book_value),
        total_book_value=str(total_book_value),
        present_value_of_cash_flows=str(pv_cash_flows),
        recoverable_amount=str(recoverable_amount),
        impairment_loss=str(impairment_loss),
        goodwill_writedown=str(goodwill_writedown),
        other_assets_writedown=str(other_assets_writedown),
        is_impaired=is_impaired,
        dcf_details=dcf_details,
        asset_allocations=asset_allocations,
        summary=summary,
        is_llm_stub=is_llm_stub_flag,
        applied_to_sheet=applied_to_sheet,
    )


# ─── Write-back Helper ────────────────────────────────────────────────────────


async def _maybe_apply_goodwill_impairment_to_workpaper(
    db: AsyncSession,
    wp_id: str,
    payload: GoodwillImpairmentRequest,
    pv_cash_flows: Decimal,
    recoverable_amount: Decimal,
    total_book_value: Decimal,
    impairment_loss: Decimal,
    goodwill_writedown: Decimal,
    other_assets_writedown: Decimal,
    is_impaired: bool,
    dcf_details: list[dict],
    summary: str,
    asset_allocations: list[dict] | None = None,
) -> str | None:
    """若 apply_to_sheet 给出则把商誉减值分析结果写回 working_paper.parsed_data。

    数据结构：
      parsed_data.goodwill_impairment_analyses[sheet] = {
        "cgu_id": "CGU-G-001",
        "goodwill_book_value": "...",
        "other_assets_book_value": "...",
        "total_book_value": "...",
        "discount_rate": "...",
        "terminal_growth_rate": "...",
        "cash_flows": [...],
        "present_value_of_cash_flows": "...",
        "recoverable_amount": "...",
        "impairment_loss": "...",
        "goodwill_writedown": "...",
        "other_assets_writedown": "...",
        "is_impaired": true/false,
        "applied_at": ISO8601,
        "summary": "...",
        "dcf_details": [...],
        "asset_allocations": [...]   # CAS 8 / IFRS 36 完整版分摊明细
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
    pd.setdefault("goodwill_impairment_analyses", {})
    pd["goodwill_impairment_analyses"][payload.apply_to_sheet] = {
        "cgu_id": payload.cgu_id,
        "goodwill_book_value": str(payload.goodwill_book_value),
        "other_assets_book_value": str(payload.other_assets_book_value),
        "total_book_value": str(total_book_value),
        "discount_rate": str(payload.discount_rate),
        "terminal_growth_rate": str(payload.terminal_growth_rate),
        "cash_flows": [str(cf) for cf in payload.cash_flows],
        "present_value_of_cash_flows": str(pv_cash_flows),
        "recoverable_amount": str(recoverable_amount),
        "impairment_loss": str(impairment_loss),
        "goodwill_writedown": str(goodwill_writedown),
        "other_assets_writedown": str(other_assets_writedown),
        "is_impaired": is_impaired,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "dcf_details": dcf_details,
        "asset_allocations": asset_allocations or [],
    }
    wp.parsed_data = pd
    await db.flush()
    await db.commit()
    return payload.apply_to_sheet
