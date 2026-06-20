"""AnalyticalReviewMixin：分析性复核

generate_analytical_review、_get_trial_balance、_get_large_transactions、
_get_top_aux_balances、_build_analytical_review_prompt、
_generate_fallback_analytical_review、_determine_confidence。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func, desc

from app.models.ai_models import (
    AIContent,
    AIContentType,
    AIConfirmationStatus,
    ConfidenceLevel,
)
from app.models.audit_platform_models import (
    TrialBalance,
    TbLedger,
    TbAuxBalance,
)
from app.services.ai_service import AIService
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


class AnalyticalReviewMixin:
    """分析性复核相关方法"""

    async def generate_analytical_review(
        self,
        project_id: UUID,
        account_code: str,
        year: str,
        ai_service: AIService,
        company_code: str = "001",
    ) -> AIContent:
        """
        生成分析性复核初稿

        实现步骤：
        1. 从 trial_balance 取本年/上年余额
        2. 计算变动额和变动率
        3. 从 tb_ledger 取大额交易摘要
        4. 从 tb_aux_balance 取前N大客户/供应商
        5. 加载对应科目的审计复核提示词（TSJ/）作为分析维度参考
        6. LLM生成分析叙述（变动原因分析+异常标注+建议程序）

        Args:
            project_id: 项目ID
            account_code: 科目代码
            year: 审计年度 (如 "2024")
            ai_service: AI服务实例
            company_code: 公司代码，默认 "001"

        Returns:
            AIContent: 生成的AI内容记录
        """
        year_int = int(year)
        prev_year = year_int - 1

        # 1. 从 trial_balance 取本年/上年余额
        current_tb = await self._get_trial_balance(
            project_id, year_int, account_code, company_code
        )
        prior_tb = await self._get_trial_balance(
            project_id, prev_year, account_code, company_code
        )

        current_amount = (
            float(current_tb.audited_amount)
            if current_tb and current_tb.audited_amount is not None
            else 0.0
        )
        prior_amount = (
            float(prior_tb.audited_amount)
            if prior_tb and prior_tb.audited_amount is not None
            else 0.0
        )
        opening_amount = (
            float(current_tb.opening_balance)
            if current_tb and current_tb.opening_balance is not None
            else 0.0
        )

        # 2. 计算变动额和变动率
        change_amount = current_amount - prior_amount
        if prior_amount != 0:
            change_ratio = (change_amount / abs(prior_amount)) * 100
        else:
            change_ratio = 100.0 if current_amount != 0 else 0.0

        # 3. 从 tb_ledger 取大额交易摘要
        large_transactions = await self._get_large_transactions(
            project_id, year_int, account_code, company_code, limit=10
        )

        # 4. 从 tb_aux_balance 取前N大客户/供应商
        aux_balances = await self._get_top_aux_balances(
            project_id, year_int, account_code, company_code, limit=5
        )

        # 5. 获取科目名称
        account_name = ""
        if current_tb and current_tb.account_name:
            account_name = current_tb.account_name
        elif prior_tb and prior_tb.account_name:
            account_name = prior_tb.account_name

        # 6. 构建提示词
        prompt = self._build_analytical_review_prompt(
            account_code=account_code,
            account_name=account_name,
            year=year,
            current_amount=current_amount,
            prior_amount=prior_amount,
            opening_amount=opening_amount,
            change_amount=change_amount,
            change_ratio=change_ratio,
            large_transactions=large_transactions,
            aux_balances=aux_balances,
        )

        # 7. 调用 LLM 生成分析叙述
        try:
            response = await ai_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            if hasattr(response, "__aiter__"):
                # 流式响应，收集完整内容
                content_parts = []
                async for part in response:
                    content_parts.append(part)
                content_text = "".join(content_parts)
            else:
                content_text = str(response)
        except Exception as e:
            logger.warning(f"AI chat failed for analytical review: {e}")
            content_text = self._generate_fallback_analytical_review(
                account_code, account_name, year,
                current_amount, prior_amount, change_amount, change_ratio
            )

        # 8. 确定置信度
        confidence = self._determine_confidence(
            abs(change_ratio), len(large_transactions)
        )

        # 9. 创建 AI 内容记录
        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=None,
            content_type=AIContentType.analytical_review,
            content_text=content_text,
            data_sources={
                "account_code": account_code,
                "account_name": account_name,
                "year": year,
                "current_amount": current_amount,
                "prior_amount": prior_amount,
                "change_amount": change_amount,
                "change_ratio": change_ratio,
                "large_transactions_count": len(large_transactions),
                "aux_balances_count": len(aux_balances),
            },
            generation_model=ai_service.get_active_model.__name__ if hasattr(ai_service, "get_active_model") else "unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=confidence,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(ai_content)
        await self.db.commit()
        await self.db.refresh(ai_content)

        return ai_content

    async def _get_trial_balance(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        company_code: str,
    ) -> TrialBalance | None:
        """获取指定科目的试算表记录"""
        result = await self.db.execute(
            select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.company_code == company_code,
                TrialBalance.is_deleted == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def _get_large_transactions(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        company_code: str,
        limit: int = 10,
    ) -> list[dict]:
        """获取大额交易摘要"""
        # 获取当前科目审定金额，用于确定大额阈值
        tb = await self._get_trial_balance(project_id, year, account_code, company_code)
        total_amount = (
            abs(float(tb.audited_amount)) if tb and tb.audited_amount else 1000000
        )
        threshold = total_amount * 0.1  # 大额阈值：占总金额10%以上

        result = await self.db.execute(
            select(TbLedger)
            .where(
                await get_active_filter(self.db, TbLedger.__table__, project_id, year),
                TbLedger.account_code == account_code,
                TbLedger.company_code == company_code,
                (
                    (TbLedger.debit_amount >= threshold)
                    | (TbLedger.credit_amount >= threshold)
                ),
            )
            .order_by(desc(func.greatest(
                func.coalesce(TbLedger.debit_amount, 0),
                func.coalesce(TbLedger.credit_amount, 0)
            )))
            .limit(limit)
        )
        ledgers = result.scalars().all()

        transactions = []
        for ledger in ledgers:
            amount = (
                float(ledger.debit_amount)
                if ledger.debit_amount
                else float(ledger.credit_amount)
            )
            transactions.append({
                "voucher_no": ledger.voucher_no,
                "voucher_date": str(ledger.voucher_date) if ledger.voucher_date else "",
                "summary": ledger.summary or "",
                "amount": amount,
                "counterpart": ledger.counterpart_account or "",
            })

        return transactions

    async def _get_top_aux_balances(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        company_code: str,
        limit: int = 5,
    ) -> list[dict]:
        """获取前N大客户/供应商余额"""
        result = await self.db.execute(
            select(TbAuxBalance)
            .where(
                await get_active_filter(self.db, TbAuxBalance.__table__, project_id, year),
                TbAuxBalance.account_code == account_code,
                TbAuxBalance.company_code == company_code,
            )
            .order_by(desc(func.abs(func.coalesce(TbAuxBalance.closing_balance, 0))))
            .limit(limit)
        )
        aux_balances = result.scalars().all()

        items = []
        for aux in aux_balances:
            items.append({
                "aux_type": aux.aux_type or "",
                "aux_name": aux.aux_name or "",
                "opening_balance": float(aux.opening_balance) if aux.opening_balance else 0.0,
                "closing_balance": float(aux.closing_balance) if aux.closing_balance else 0.0,
                "debit_amount": float(aux.debit_amount) if aux.debit_amount else 0.0,
                "credit_amount": float(aux.credit_amount) if aux.credit_amount else 0.0,
            })

        return items

    def _build_analytical_review_prompt(
        self,
        account_code: str,
        account_name: str,
        year: str,
        current_amount: float,
        prior_amount: float,
        opening_amount: float,
        change_amount: float,
        change_ratio: float,
        large_transactions: list[dict],
        aux_balances: list[dict],
    ) -> str:
        """构建分析性复核提示词"""
        prompt = f"""你是审计师，请对以下科目进行【分析性复核】，生成专业的审计分析叙述。

## 科目信息
- 科目代码：{account_code}
- 科目名称：{account_name}
- 审计年度：{year}

## 余额数据
- 期初余额：{opening_amount:,.2f}
- 期末余额（审定数）：{current_amount:,.2f}
- 上年期末余额：{prior_amount:,.2f}
- 本年变动额：{change_amount:,.2f}
- 变动率：{change_ratio:.2f}%

## 大额交易（占总额10%以上）
"""
        if large_transactions:
            for i, txn in enumerate(large_transactions, 1):
                prompt += f"{i}. 凭证号:{txn['voucher_no']} 日期:{txn['voucher_date']} 摘要:{txn['summary']} 金额:{txn['amount']:,.2f}\n"
        else:
            prompt += "（无大额交易）\n"

        prompt += f"""
## 辅助余额（前5大客户/供应商）
"""
        if aux_balances:
            for aux in aux_balances:
                prompt += f"- {aux['aux_type']}:{aux['aux_name']} 期初:{aux['opening_balance']:,.2f} 期末:{aux['closing_balance']:,.2f}\n"
        else:
            prompt += "（无辅助余额明细）\n"

        prompt += """
## 分析要求

请生成一段专业的分析性复核叙述，要求：
1. 分析该科目本年变动的主要原因
2. 标注任何异常波动（变动率超过30%需重点关注）
3. 指出需要进一步审计程序的事项
4. 给出初步审计结论和建议

格式要求：
- 段落式叙述，不要使用表格
- 字数200-500字
- 语言专业、简洁
- 最后给出【审计建议】

请开始分析：
"""
        return prompt

    def _generate_fallback_analytical_review(
        self,
        account_code: str,
        account_name: str,
        year: str,
        current_amount: float,
        prior_amount: float,
        change_amount: float,
        change_ratio: float,
    ) -> str:
        """当AI服务不可用时，生成基础分析性复核"""
        direction = "增加" if change_amount > 0 else "减少"
        abs_change = abs(change_amount)

        text = f"""【{account_name}({account_code})分析性复核 - {year}年度】

一、变动概况
本期期末余额{current_amount:,.2f}，较上年{prior_amount:,.2f}{direction}了{abs_change:,.2f}，变动率为{change_ratio:.2f}%。

二、变动分析
"""
        if abs(change_ratio) > 30:
            text += f"【异常标注】变动率超过30%，需重点关注。\n\n"
        else:
            text += "变动率在合理范围内。\n\n"

        text += """三、审计建议
1. 获取该科目明细账，了解大额变动原因
2. 抽查相关凭证，核实交易的真实性和完整性
3. 结合期后事项检查，确认期末余额的截止性
4. 如有必要，提请企业管理层说明变动原因

审计结论：该科目变动需结合实质性测试结果综合判断。
"""
        return text

    def _determine_confidence(
        self,
        change_ratio: float,
        transaction_count: int,
    ) -> ConfidenceLevel:
        """根据数据情况确定置信度"""
        if change_ratio <= 10 and transaction_count > 0:
            return ConfidenceLevel.high
        elif change_ratio <= 30 and transaction_count >= 3:
            return ConfidenceLevel.medium
        else:
            return ConfidenceLevel.low
