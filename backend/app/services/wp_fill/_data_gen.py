"""DataGenMixin：底稿数据生成

generate_workpaper_data、_generate_tb_analytical_data、
_generate_inventory_observation_data、_generate_confirmation_data、
_generate_other_workpaper_data、_generate_fallback_tb_analytical。
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
    TbAuxBalance,
)
from app.services.ai_service import AIService
from app.services.dataset_query import get_active_filter

logger = logging.getLogger(__name__)


class DataGenMixin:
    """底稿数据生成相关方法"""

    async def generate_workpaper_data(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        template_type: str,
        ai_service: AIService,
        year: str = None,
    ) -> list[AIContent]:
        """
        按底稿模板类型生成填充数据

        模板类型：
        - TB_analytical_procedure: 试算表分析程序
        - inventory_observation: 存货监盘
        - confirm_account_balance: 往来函证
        - other: 其他底稿

        Args:
            project_id: 项目ID
            workpaper_id: 底稿ID
            template_type: 模板类型
            ai_service: AI服务实例
            year: 审计年度

        Returns:
            list[AIContent]: 生成的AI内容列表
        """
        year_int = int(year) if year else datetime.now().year

        # 根据模板类型选择处理逻辑
        handlers = {
            "TB_analytical_procedure": self._generate_tb_analytical_data,
            "inventory_observation": self._generate_inventory_observation_data,
            "confirm_account_balance": self._generate_confirmation_data,
            "other": self._generate_other_workpaper_data,
        }

        handler = handlers.get(template_type, self._generate_other_workpaper_data)
        return await handler(project_id, workpaper_id, year_int, ai_service)

    async def _generate_tb_analytical_data(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        year: int,
        ai_service: AIService,
    ) -> list[AIContent]:
        """生成试算表分析程序数据"""
        # 获取试算表数据
        result = await self.db.execute(
            select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.is_deleted == False,  # noqa: E712
            ).order_by(TrialBalance.standard_account_code)
        )
        tb_rows = result.scalars().all()

        # 按科目类别分组
        assets = [r for r in tb_rows if r.account_category.value == "asset"]
        liabilities = [r for r in tb_rows if r.account_category.value == "liability"]
        equity = [r for r in tb_rows if r.account_category.value == "equity"]
        revenue = [r for r in tb_rows if r.account_category.value == "revenue"]
        expenses = [r for r in tb_rows if r.account_category.value == "expense"]

        # 计算合计
        def calc_total(rows):
            return sum(
                float(r.audited_amount or 0) for r in rows
            )

        # 构建数据摘要
        data_summary = {
            "assets_total": calc_total(assets),
            "liabilities_total": calc_total(liabilities),
            "equity_total": calc_total(equity),
            "revenue_total": calc_total(revenue),
            "expenses_total": calc_total(expenses),
            "account_count": len(tb_rows),
        }

        # 计算关键比率
        assets_total = data_summary["assets_total"]
        liabilities_total = data_summary["liabilities_total"]
        if assets_total != 0:
            debt_ratio = liabilities_total / assets_total
        else:
            debt_ratio = 0

        # 生成分析内容
        prompt = f"""请基于以下试算表汇总数据，生成【分析性复核程序】的底稿内容。

## 试算表汇总数据（{year}年度）
- 资产类合计：{data_summary['assets_total']:,.2f}
- 负债类合计：{data_summary['liabilities_total']:,.2f}
- 权益类合计：{data_summary['equity_total']:,.2f}
- 收入类合计：{data_summary['revenue_total']:,.2f}
- 费用类合计：{data_summary['expenses_total']:,.2f}
- 科目数量：{data_summary['account_count']}

## 关键财务比率
- 资产负债率：{debt_ratio:.2%}

## 分析要求

请生成以下底稿内容：

1. **报表平衡性检查**
   - 资产 = 负债 + 所有者权益
   - 利润表汇总验证

2. **重大波动分析**
   - 识别变动超过20%的科目
   - 说明可能原因

3. **钩稽关系检查**
   - 报表间数据一致性
   - 与上年数据勾稽

4. **审计风险提示**
   - 高风险科目标注
   - 建议重点关注领域

请以结构化格式输出：
"""
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
            logger.warning(f"AI chat failed for TB analytical: {e}")
            content_text = self._generate_fallback_tb_analytical(data_summary, debt_ratio, year)

        # 创建 AI 内容记录
        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.data_fill,
            content_text=content_text,
            data_sources={
                "template_type": "TB_analytical_procedure",
                "year": year,
                "summary": data_summary,
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.medium,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(ai_content)
        await self.db.commit()
        await self.db.refresh(ai_content)

        return [ai_content]

    async def _generate_inventory_observation_data(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        year: int,
        ai_service: AIService,
    ) -> list[AIContent]:
        """生成存货监盘底稿数据"""
        # 提示用户需要实际数据
        prompt = """请生成【存货监盘程序】的底稿内容模板。

## 存货监盘程序要点

1. **监盘前准备**
   - 获取存货明细表
   - 了解存货存放地点
   - 确定监盘日期

2. **监盘程序**
   - 实地盘点存货
   - 实施抽盘程序
   - 截止测试
   - 了解存货状况

3. **特殊考虑**
   - 寄销存货
   - 第三方保管存货
   - 积压存货

4. **审计结论**
   - 盘点结果与账面核对
   - 账实差异分析

请生成完整的监盘说明和结论模板：
"""
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
            logger.warning(f"AI chat failed for inventory observation: {e}")
            content_text = "【存货监盘程序】\n\n请按实际盘点结果填写。"

        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.test_summary,
            content_text=content_text,
            data_sources={
                "template_type": "inventory_observation",
                "year": year,
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.low,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(ai_content)
        await self.db.commit()
        await self.db.refresh(ai_content)

        return [ai_content]

    async def _generate_confirmation_data(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        year: int,
        ai_service: AIService,
    ) -> list[AIContent]:
        """生成往来函证底稿数据"""
        # 获取往来科目余额
        receivable_codes = ["1122", "1123", "2202", "2203"]  # 应收/其他应收/应付/其他应付
        result = await self.db.execute(
            select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(receivable_codes),
                TrialBalance.is_deleted == False,  # noqa: E712
            )
        )
        tb_rows = result.scalars().all()

        # 获取辅助余额（客户/供应商明细）
        confirm_balances = []
        for row in tb_rows:
            aux_result = await self.db.execute(
                select(TbAuxBalance).where(
                    await get_active_filter(self.db, TbAuxBalance.__table__, project_id, year),
                    TbAuxBalance.account_code == row.standard_account_code,
                    func.abs(func.coalesce(TbAuxBalance.closing_balance, 0)) > 0,
                ).order_by(desc(func.abs(TbAuxBalance.closing_balance))).limit(10)
            )
            aux_rows = aux_result.scalars().all()
            for aux in aux_rows:
                confirm_balances.append({
                    "account_code": row.standard_account_code,
                    "account_name": row.account_name or "",
                    "aux_name": aux.aux_name or "",
                    "aux_type": aux.aux_type or "",
                    "balance": float(aux.closing_balance or 0),
                })

        prompt = f"""请基于以下往来账款数据，生成【往来函证程序】的底稿内容。

## 往来账款数据（{year}年度）
"""
        if confirm_balances:
            for item in confirm_balances:
                prompt += f"- {item['account_name']}({item['account_code']}) - {item['aux_name']}: {item['balance']:,.2f}\n"
        else:
            prompt += "（无明细数据）\n"

        prompt += """
## 函证程序要点

1. **函证对象选择**
   - 大额余额（占比80%）
   - 异常余额
   - 关联方往来

2. **函证方式**
   - 积极式函证
   - 消极式函证

3. **替代程序**
   - 检查期后收付款
   - 检查销售/采购合同

4. **不符事项处理**
   - 分析差异原因
   - 必要时扩大样本

请生成函证结论模板：
"""
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
            logger.warning(f"AI chat failed for confirmation: {e}")
            content_text = f"【往来函证程序 - {year}年度】\n\n待函证余额数量：{len(confirm_balances)}\n\n请按实际函证结果填写。"

        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.test_summary,
            content_text=content_text,
            data_sources={
                "template_type": "confirm_account_balance",
                "year": year,
                "confirm_count": len(confirm_balances),
                "balances": confirm_balances[:20],  # 限制数量
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.medium,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(ai_content)
        await self.db.commit()
        await self.db.refresh(ai_content)

        return [ai_content]

    async def _generate_other_workpaper_data(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        year: int,
        ai_service: AIService,
    ) -> list[AIContent]:
        """生成其他类型底稿数据"""
        prompt = f"""请为以下审计底稿生成填充内容。

## 底稿信息
- 底稿类型：其他
- 审计年度：{year}

## 生成要求
1. 审计程序说明
2. 测试结果记录
3. 异常事项标注
4. 审计结论

请生成通用底稿内容模板：
"""
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
            logger.warning(f"AI chat failed for other workpaper: {e}")
            content_text = f"【审计程序 - {year}年度】\n\n请根据实际情况填写。"

        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.data_fill,
            content_text=content_text,
            data_sources={
                "template_type": "other",
                "year": year,
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.low,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(ai_content)
        await self.db.commit()
        await self.db.refresh(ai_content)

        return [ai_content]

    def _generate_fallback_tb_analytical(
        self,
        data_summary: dict,
        debt_ratio: float,
        year: int,
    ) -> str:
        """当AI不可用时，生成基础试算表分析"""
        return f"""【试算表分析性复核程序 - {year}年度】

一、报表平衡性检查
1. 资产类合计：{data_summary['assets_total']:,.2f}
2. 负债类合计：{data_summary['liabilities_total']:,.2f}
3. 权益类合计：{data_summary['equity_total']:,.2f}
4. 收入类合计：{data_summary['revenue_total']:,.2f}
5. 费用类合计：{data_summary['expenses_total']:,.2f}

二、关键财务指标
- 资产负债率：{debt_ratio:.2%}

三、审计结论
报表结构基本正常，请结合实质性测试结果综合判断。

注：此为自动生成内容，请审计师复核确认。
"""
