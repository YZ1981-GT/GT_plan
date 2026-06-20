"""NoteDraftMixin：附注草稿

generate_note_draft、_get_section_accounts、_get_financial_report_data、
_get_trial_balance_data、_build_note_draft_prompt、_generate_fallback_note_draft。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.models.ai_models import (
    AIContent,
    AIContentType,
    AIConfirmationStatus,
    ConfidenceLevel,
)
from app.models.audit_platform_models import (
    TrialBalance,
)
from app.models.report_models import FinancialReport
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class NoteDraftMixin:
    """附注草稿相关方法"""

    async def generate_note_draft(
        self,
        project_id: UUID,
        note_section: str,
        ai_service: AIService,
        year: str = None,
        company_code: str = "001",
    ) -> AIContent:
        """
        按附注章节生成附注初稿

        附注章节类型：
        - 资产类：货币资金、应收账款、存货等
        - 负债类：应付账款、短期借款等
        - 权益类：实收资本、资本公积等
        - 损益类：主营业务收入、主营业务成本等
        - 重要会计政策
        - 或有事项
        - 关联披露

        Args:
            project_id: 项目ID
            note_section: 附注章节（如 "资产类"、"负债类"）
            ai_service: AI服务实例
            year: 审计年度
            company_code: 公司代码

        Returns:
            AIContent: 生成的AI内容记录
        """
        year_int = int(year) if year else datetime.now().year

        # 根据章节类型确定相关科目
        section_accounts = self._get_section_accounts(note_section)

        # 从 FinancialReport 和 TrialBalance 获取数据
        report_data = await self._get_financial_report_data(
            project_id, year_int, note_section
        )

        tb_data = await self._get_trial_balance_data(
            project_id, year_int, section_accounts, company_code
        )

        # 构建提示词
        prompt = self._build_note_draft_prompt(
            note_section=note_section,
            year=str(year_int),
            report_data=report_data,
            tb_data=tb_data,
        )

        # 调用 LLM 生成
        try:
            response = await ai_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            if hasattr(response, "__aiter__"):
                content_parts = []
                async for part in response:
                    content_parts.append(part)
                content_text = "".join(content_parts)
            else:
                content_text = str(response)
        except Exception as e:
            logger.warning(f"AI chat failed for note draft: {e}")
            content_text = self._generate_fallback_note_draft(
                note_section, str(year_int), tb_data
            )

        # 创建 AI 内容记录
        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=None,
            content_type=AIContentType.note_draft,
            content_text=content_text,
            data_sources={
                "note_section": note_section,
                "year": str(year_int),
                "account_count": len(tb_data),
                "report_items": len(report_data),
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.medium,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(ai_content)
        await self.db.commit()
        await self.db.refresh(ai_content)

        return ai_content

    def _get_section_accounts(self, note_section: str) -> list[str]:
        """根据附注章节获取相关科目代码"""
        section_mapping = {
            "资产类": [
                "1001", "1002", "1012", "1122", "1123", "1405",
                "1406", "1601", "1604", "1701", "1702",
            ],
            "负债类": [
                "2001", "2002", "2202", "2203", "2501", "2701",
            ],
            "权益类": [
                "4001", "4002", "4101", "4103", "4104",
            ],
            "损益类": [
                "6001", "6051", "6401", "6402", "6601", "6602",
                "6603", "6701", "6702",
            ],
            "重要会计政策": [],
            "或有事项": [],
            "关联披露": [],
        }
        return section_mapping.get(note_section, [])

    async def _get_financial_report_data(
        self,
        project_id: UUID,
        year: int,
        note_section: str,
    ) -> list[dict]:
        """从 FinancialReport 获取附注相关数据"""
        # 获取报表行映射
        report_types_map = {
            "资产类": "balance_sheet",
            "负债类": "balance_sheet",
            "权益类": "balance_sheet",
            "损益类": "income_statement",
        }
        report_type = report_types_map.get(note_section)
        if not report_type:
            return []

        result = await self.db.execute(
            select(FinancialReport).where(
                FinancialReport.project_id == project_id,
                FinancialReport.year == year,
                FinancialReport.is_deleted == False,  # noqa: E712
            )
        )
        reports = result.scalars().all()

        data = []
        for r in reports:
            data.append({
                "row_code": r.row_code,
                "row_name": r.row_name,
                "current_period": float(r.current_period_amount) if r.current_period_amount else 0.0,
                "prior_period": float(r.prior_period_amount) if r.prior_period_amount else 0.0,
            })

        return data

    async def _get_trial_balance_data(
        self,
        project_id: UUID,
        year: int,
        account_codes: list[str],
        company_code: str,
    ) -> list[dict]:
        """从 TrialBalance 获取科目余额数据"""
        if not account_codes:
            return []

        result = await self.db.execute(
            select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.company_code == company_code,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == False,  # noqa: E712
            )
        )
        rows = result.scalars().all()

        data = []
        for r in rows:
            data.append({
                "account_code": r.standard_account_code,
                "account_name": r.account_name,
                "unadjusted_amount": float(r.unadjusted_amount) if r.unadjusted_amount else 0.0,
                "rje_adjustment": float(r.rje_adjustment) if r.rje_adjustment else 0.0,
                "aje_adjustment": float(r.aje_adjustment) if r.aje_adjustment else 0.0,
                "audited_amount": float(r.audited_amount) if r.audited_amount else 0.0,
                "opening_balance": float(r.opening_balance) if r.opening_balance else 0.0,
            })

        return data

    def _build_note_draft_prompt(
        self,
        note_section: str,
        year: str,
        report_data: list[dict],
        tb_data: list[dict],
    ) -> str:
        """构建附注初稿提示词"""
        prompt = f"""请为以下附注章节生成【初稿】内容。

## 附注信息
- 章节类型：{note_section}
- 审计年度：{year}

## 科目余额数据
"""
        if tb_data:
            for item in tb_data:
                prompt += f"- {item['account_name']}({item['account_code']}): 审定数={item['audited_amount']:,.2f}\n"
        else:
            prompt += "（无明细科目数据）\n"

        prompt += """
## 报表行数据
"""
        if report_data:
            for item in report_data[:10]:  # 限制数量
                prompt += f"- {item['row_name']}: 本期={item['current_period']:,.2f} 上期={item['prior_period']:,.2f}\n"
        else:
            prompt += "（无报表数据）\n"

        prompt += f"""
## 附注内容要求

根据附注章节类型「{note_section}」，请生成相应的附注初稿：

"""
        if note_section == "资产类":
            prompt += """1. 各主要科目的年初余额、年末余额
2. 主要科目的变动说明
3. 应收账款按账龄分类（如适用）
4. 存货分类和计价方法（如适用）
5. 固定资产折旧政策（如适用）
"""
        elif note_section == "负债类":
            prompt += """1. 各主要科目的年初余额、年末余额
2. 主要科目的变动说明
3. 短期借款的期限和利率（如适用）
4. 应付账款账龄分析（如适用）
5. 或有负债披露（如适用）
"""
        elif note_section == "权益类":
            prompt += """1. 股本/实收资本变动
2. 资本公积变动
3. 盈余公积变动
4. 未分配利润变动
"""
        elif note_section == "损益类":
            prompt += """1. 营业收入和营业成本构成
2. 主要科目同比变动分析
3. 费用明细
4. 投资收益明细（如适用）
"""
        elif note_section == "重要会计政策":
            prompt += """1. 会计期间
2. 记账本位币
3. 收入确认政策
4. 存货计价方法
5. 固定资产折旧方法
6. 坏账准备计提政策
"""
        elif note_section == "或有事项":
            prompt += """1. 未决诉讼或仲裁
2. 对外担保
3. 票据贴现
4. 其他或有负债
"""
        elif note_section == "关联披露":
            prompt += """1. 关联方关系
2. 关联交易类型
3. 关联方交易金额
4. 关联方往来余额
"""
        else:
            prompt += """1. 相关科目的年初、年末余额
2. 主要变动说明
"""

        prompt += """
## 输出格式
请以正式附注格式输出，语言专业、完整。

请开始生成附注初稿：
"""
        return prompt

    def _generate_fallback_note_draft(
        self,
        note_section: str,
        year: str,
        tb_data: list[dict],
    ) -> str:
        """当AI不可用时，生成基础附注初稿"""
        content = f"""【{note_section}附注】（{year}年度）

一、主要科目余额

"""
        if tb_data:
            for item in tb_data:
                content += f"- {item['account_name']}({item['account_code']}): {item['audited_amount']:,.2f}\n"
        else:
            content += "（无明细数据）\n"

        content += """
二、变动分析

本年变动情况需结合实质性测试结果进行分析。

三、审计结论

请审计师复核确认后，形成正式附注。

注：此为自动生成初稿，请根据实际情况进行调整。
"""
        return content
