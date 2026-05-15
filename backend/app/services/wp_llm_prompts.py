"""LLM 审计说明生成 prompt 模板

Sprint 7 Task 7.5: 变动分析/审计结论/函证差异说明/减值假设说明
四种 prompt 模板，统一输出 wrap_ai_output 格式。
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from app.services.llm_client import chat_completion
from app.services.wp_ai_service import wrap_ai_output

logger = logging.getLogger(__name__)

# ─── Prompt 模板 ───────────────────────────────────────────────

PROMPT_VARIATION_ANALYSIS = """你是一名资深审计师，请根据以下科目数据生成变动分析说明。

科目：{account_name}（{account_code}）
本期余额：{current_balance:,.2f}
上期余额：{prior_balance:,.2f}
变动额：{change_amount:,.2f}
变动率：{change_rate}

要求：
1. 用 2-3 句话分析变动原因
2. 如果变动率超过 20%，需要说明是否存在异常
3. 语言简洁专业，适合写入审计底稿
"""

PROMPT_AUDIT_CONCLUSION = """你是一名资深审计师，请根据以下审计程序执行结果生成审计结论。

底稿编码：{wp_code}
底稿名称：{wp_name}
审计程序执行摘要：
{procedure_summary}

已发现问题：
{findings}

要求：
1. 结论分为"无异常"/"存在差异已调整"/"存在重大错报"三种
2. 用 1-2 句话概括结论
3. 如有差异，说明是否已通过调整分录更正
"""

PROMPT_CONFIRMATION_DIFF = """你是一名资深审计师，请根据以下函证回函差异生成差异说明。

科目：{account_name}
账面余额：{book_balance:,.2f}
回函确认金额：{confirmed_balance:,.2f}
差异金额：{difference:,.2f}

已知调节事项：
{reconciling_items}

要求：
1. 逐项说明差异原因
2. 判断差异是否可接受（时间性差异/已知调节事项）
3. 如差异不可解释，建议追加审计程序
"""

PROMPT_IMPAIRMENT_ASSUMPTION = """你是一名资深审计师，请根据以下减值测试参数生成假设说明。

资产类型：{asset_type}
账面价值：{book_value:,.2f}
可收回金额：{recoverable_amount:,.2f}
折现率：{discount_rate}%
预测期间：{forecast_period}年
增长率假设：{growth_rate}%

要求：
1. 说明关键假设的合理性依据
2. 评估假设的敏感性（折现率±1%/增长率±2% 对结果的影响）
3. 结论是否需要计提减值
"""


async def generate_variation_analysis(
    account_code: str,
    account_name: str,
    current_balance: float,
    prior_balance: float,
) -> dict:
    """生成变动分析说明"""
    change = current_balance - prior_balance
    rate = f"{change / prior_balance * 100:.1f}%" if prior_balance != 0 else "N/A"

    prompt = PROMPT_VARIATION_ANALYSIS.format(
        account_code=account_code,
        account_name=account_name,
        current_balance=current_balance,
        prior_balance=prior_balance,
        change_amount=change,
        change_rate=rate,
    )

    text = await chat_completion([
        {"role": "system", "content": "你是审计分析师，请简洁专业地回答。"},
        {"role": "user", "content": prompt},
    ])

    return wrap_ai_output(
        content=text,
        confidence=0.8,
        target_field="variation_analysis",
        source_prompt_version="v1.0",
    )


async def generate_audit_conclusion(
    wp_code: str,
    wp_name: str,
    procedure_summary: str,
    findings: str = "无",
) -> dict:
    """生成审计结论"""
    prompt = PROMPT_AUDIT_CONCLUSION.format(
        wp_code=wp_code,
        wp_name=wp_name,
        procedure_summary=procedure_summary,
        findings=findings,
    )

    text = await chat_completion([
        {"role": "system", "content": "你是审计师，请生成简洁的审计结论。"},
        {"role": "user", "content": prompt},
    ])

    return wrap_ai_output(
        content=text,
        confidence=0.75,
        target_field="audit_conclusion",
        source_prompt_version="v1.0",
    )


async def generate_confirmation_diff_explanation(
    account_name: str,
    book_balance: float,
    confirmed_balance: float,
    reconciling_items: str = "无",
) -> dict:
    """生成函证差异说明"""
    difference = book_balance - confirmed_balance

    prompt = PROMPT_CONFIRMATION_DIFF.format(
        account_name=account_name,
        book_balance=book_balance,
        confirmed_balance=confirmed_balance,
        difference=difference,
        reconciling_items=reconciling_items,
    )

    text = await chat_completion([
        {"role": "system", "content": "你是审计师，请分析函证差异原因。"},
        {"role": "user", "content": prompt},
    ])

    return wrap_ai_output(
        content=text,
        confidence=0.7,
        target_field="confirmation_diff",
        source_prompt_version="v1.0",
    )


async def generate_impairment_assumption(
    asset_type: str,
    book_value: float,
    recoverable_amount: float,
    discount_rate: float,
    forecast_period: int = 5,
    growth_rate: float = 3.0,
) -> dict:
    """生成减值假设说明"""
    prompt = PROMPT_IMPAIRMENT_ASSUMPTION.format(
        asset_type=asset_type,
        book_value=book_value,
        recoverable_amount=recoverable_amount,
        discount_rate=discount_rate,
        forecast_period=forecast_period,
        growth_rate=growth_rate,
    )

    text = await chat_completion([
        {"role": "system", "content": "你是审计师，请评估减值测试假设的合理性。"},
        {"role": "user", "content": prompt},
    ])

    return wrap_ai_output(
        content=text,
        confidence=0.7,
        target_field="impairment_assumption",
        source_prompt_version="v1.0",
    )
