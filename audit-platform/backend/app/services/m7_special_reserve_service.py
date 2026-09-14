"""M7 专项储备 — 业务逻辑服务

提供功能：
- 安全生产费计提测试（纯函数）
- 按产量分档计提 / 按营业收入比例计提
- 计提差异计算
- 底稿汇总数据

科目4201专项储备（**贷方/权益类！**）：期末=期初+贷方-借方
安全生产费计提：高危行业按产量分档，其他按营业收入×比例。

Requirements: 4.2-4.3
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_M7_ACCOUNT_CODE = "4201"


# ═══════════════════════════════════════════════════════════════════════════════
# 纯函数：安全生产费计提引擎
# ═══════════════════════════════════════════════════════════════════════════════


def calc_accrual_by_output(tiers: list[dict]) -> float:
    """按产量分档计提安全生产费：Σ(各档产量×档位标准)

    适用场景：
    - 矿山企业：按开采原矿产量分档（如：≤100万吨部分 5元/吨，>100万吨部分 4元/吨）
    - 危险品企业：按营业收入超额累退分档

    Args:
        tiers: 各档 [{"output": 产量/基数, "rate": 档位标准/比例}, ...]

    Returns:
        应计金额合计

    Example:
        >>> calc_accrual_by_output([{"output": 100, "rate": 5}, {"output": 50, "rate": 4}])
        700.0
    """
    if not tiers:
        return 0.0
    total = 0.0
    for tier in tiers:
        output = float(tier.get("output", 0) or 0)
        rate = float(tier.get("rate", 0) or 0)
        total += output * rate
    return total


def calc_accrual_by_revenue(revenue: float, rate: float) -> float:
    """按营业收入×单一比例计提安全生产费

    适用场景：
    - 建筑施工企业：以建筑安装工程造价为基数×比例
    - 其他企业：以营业收入为基数×单一比例

    Args:
        revenue: 营业收入/建安造价（基数）
        rate: 计提比例（如 0.015 = 1.5%）

    Returns:
        应计金额

    Example:
        >>> calc_accrual_by_revenue(10000000, 0.015)
        150000.0
    """
    return float(revenue or 0) * float(rate or 0)


def calc_accrual_diff(estimated: float, booked: float) -> float:
    """计提差异 = 应计提 − 账面计提

    方向说明：
    - 正差 → 应补提（少计提=审计风险点）
    - 负差 → 多计提（需要冲回）
    - 零 → 计提准确

    Args:
        estimated: 应计提金额（按标准计算的应提数）
        booked: 账面计提金额（企业实际计提数）

    Returns:
        计提差异

    Example:
        >>> calc_accrual_diff(150000, 120000)
        30000.0
    """
    return float(estimated or 0) - float(booked or 0)


def run_accrual_test(params: dict) -> dict:
    """执行完整计提测试流程，返回结果字典

    支持两种计提基础：
    1. 按产量分档计提（tiers模式）
    2. 按营业收入计提（revenue模式）

    Args:
        params: {
            "method": "output" | "revenue",  # 计提方式
            "tiers": [{"output": float, "rate": float}, ...],  # 按产量时
            "revenue": float,  # 按收入时
            "rate": float,     # 按收入时的比例
            "booked": float,   # 账面计提金额
            "threshold": float,  # 差异阈值（可选，默认0）
        }

    Returns:
        {
            "method": str,
            "estimated": float,     # 应计提金额
            "booked": float,        # 账面计提
            "diff": float,          # 差异（正=少提）
            "abs_diff": float,      # 绝对差异
            "threshold": float,     # 阈值
            "exceed_threshold": bool, # 是否超阈值
            "conclusion": str,      # 结论文本
        }
    """
    method = params.get("method", "output")
    booked = float(params.get("booked", 0) or 0)
    threshold = float(params.get("threshold", 0) or 0)

    # 计算应计提金额
    if method == "revenue":
        revenue = float(params.get("revenue", 0) or 0)
        rate = float(params.get("rate", 0) or 0)
        estimated = calc_accrual_by_revenue(revenue, rate)
    else:
        # 默认按产量分档
        tiers = params.get("tiers", [])
        estimated = calc_accrual_by_output(tiers if tiers else [])

    # 计算差异
    diff = calc_accrual_diff(estimated, booked)
    abs_diff = abs(diff)
    exceed_threshold = abs_diff > threshold if threshold > 0 else False

    # 生成结论
    if abs_diff < 1.0:
        conclusion = "计提准确，应计提与账面一致。"
    elif diff > 0:
        conclusion = f"少计提 {diff:,.2f} 元"
        if exceed_threshold:
            conclusion += "，超过重要性阈值，需关注。"
        else:
            conclusion += "。"
    else:
        conclusion = f"多计提 {abs(diff):,.2f} 元"
        if exceed_threshold:
            conclusion += "，超过重要性阈值，需关注。"
        else:
            conclusion += "。"

    return {
        "method": method,
        "estimated": round(estimated, 2),
        "booked": round(booked, 2),
        "diff": round(diff, 2),
        "abs_diff": round(abs_diff, 2),
        "threshold": round(threshold, 2),
        "exceed_threshold": exceed_threshold,
        "conclusion": conclusion,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 数据库查询：底稿汇总
# ═══════════════════════════════════════════════════════════════════════════════


async def get_m7_summary(
    session: AsyncSession,
    project_id: str,
    wp_id: str,
) -> dict[str, Any]:
    """获取M7底稿汇总数据

    从TB取科目4201余额 + 从checklist_responses提取计提/使用合计。
    用于跨底稿联动核对（如M5/M6/H1）。

    Args:
        session: 数据库会话
        project_id: 项目ID
        wp_id: M7底稿ID

    Returns:
        {
            "account_code": "4201",
            "tb_unadjusted": float,
            "tb_audited": float,
            "begin_balance": float,
            "credit_total": float,  # 贷方发生（计提）
            "debit_total": float,   # 借方发生（使用）
            "end_balance": float,   # 期末=期初+贷方-借方
            "accrual_test": {...} | None,  # 计提测试结果
            "ready": bool,
        }
    """
    import sqlalchemy as sa
    from app.models.audit_platform_models import ChecklistResponse

    # Step 1: 从TB取科目4201余额
    tb_unadjusted = 0.0
    tb_audited = 0.0
    try:
        tb_result = await session.execute(
            sa.text("""
                SELECT
                    COALESCE(tb.unadjusted_amount, 0) as unadj,
                    COALESCE(tb.aje_adjustment, 0) as aje,
                    COALESCE(tb.rje_adjustment, 0) as rje,
                    COALESCE(tb.audited_amount, 0) as audited
                FROM trial_balance tb
                WHERE tb.project_id = :project_id
                  AND tb.standard_account_code = :account_code
                LIMIT 1
            """),
            {"project_id": project_id, "account_code": _M7_ACCOUNT_CODE},
        )
        tb_row = tb_result.fetchone()
        if tb_row:
            tb_unadjusted = float(tb_row.unadj or 0)
            tb_audited = float(tb_row.audited or 0)
    except Exception as e:
        logger.warning("M7 TB查询失败: %s", e)

    # Step 2: 从checklist_responses提取审定表汇总数据
    begin_balance = 0.0
    credit_total = 0.0
    debit_total = 0.0

    try:
        stmt = sa.select(ChecklistResponse).where(
            ChecklistResponse.wp_id == wp_id,
            ChecklistResponse.item_id.like("M7-1-%"),
        )
        result = await session.execute(stmt)
        responses = result.scalars().all()

        for resp in responses:
            if not resp.remark:
                continue
            try:
                data = json.loads(resp.remark)
            except (json.JSONDecodeError, TypeError):
                continue

            item_id = resp.item_id
            if "begin" in item_id or "opening" in item_id:
                begin_balance += float(data.get("value", 0) or 0)
            elif "credit" in item_id or "accrual" in item_id:
                credit_total += float(data.get("value", 0) or 0)
            elif "debit" in item_id or "usage" in item_id:
                debit_total += float(data.get("value", 0) or 0)
    except Exception as e:
        logger.warning("M7 checklist_responses查询失败: %s", e)

    # 权益类期末 = 期初 + 贷方 - 借方
    end_balance = begin_balance + credit_total - debit_total

    # Step 3: 检查是否有计提测试结果
    accrual_test_result = None
    try:
        stmt = sa.select(ChecklistResponse).where(
            ChecklistResponse.wp_id == wp_id,
            ChecklistResponse.item_id == "M7-4-accrual-test-result",
        )
        result = await session.execute(stmt)
        test_resp = result.scalar_one_or_none()
        if test_resp and test_resp.remark:
            accrual_test_result = json.loads(test_resp.remark)
    except Exception as e:
        logger.warning("M7 计提测试结果查询失败: %s", e)

    return {
        "account_code": _M7_ACCOUNT_CODE,
        "tb_unadjusted": round(tb_unadjusted, 2),
        "tb_audited": round(tb_audited, 2),
        "begin_balance": round(begin_balance, 2),
        "credit_total": round(credit_total, 2),
        "debit_total": round(debit_total, 2),
        "end_balance": round(end_balance, 2),
        "accrual_test": accrual_test_result,
        "ready": tb_audited != 0.0 or begin_balance != 0.0,
    }
