"""底稿 AI 填充服务

基于 AI 模型自动填充审计底稿内容，包括：
- 文本描述填充（审计说明、结论）
- 计算验证（数值计算、钩稽关系）
- 异常标注（标记需要关注的异常项）
- 分析性复核生成
- 底稿数据生成
- 附注初稿生成
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIContent,
    AIContentType,
    AIConfirmationStatus,
    AIWorkpaperTask,
    AIWorkpaperFill,
    ConfidenceLevel,
)
from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentEntry,
    TrialBalance,
    TbLedger,
    TbAuxBalance,
)
from app.models.report_models import DisclosureNote, FinancialReport
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class WorkpaperFillService:
    """底稿 AI 填充服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_fill_task(
        self,
        project_id: UUID,
        workpaper_id: str,
        workpaper_item_id: Optional[str],
        template_type: str,
        context_data: dict[str, Any],
        fill_mode: str = "auto",
        user_id: Optional[str] = None,
    ) -> AIWorkpaperTask:
        """创建底稿填充任务"""
        task = AIWorkpaperTask(
            project_id=project_id,
            workpaper_id=workpaper_id,
            workpaper_item_id=workpaper_item_id,
            template_type=template_type,
            context_data=context_data,
            fill_mode=fill_mode,
            status="pending",
            user_id=user_id,
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def execute_fill_task(
        self,
        task_id: UUID,
        ai_service: AIService,
    ) -> AIWorkpaperFill:
        """
        执行底稿填充任务

        Args:
            task_id: 任务 ID
            ai_service: AI 服务实例

        Returns:
            填充结果记录
        """
        # 获取任务
        result = await self.db.execute(
            select(AIWorkpaperTask).where(AIWorkpaperTask.id == task_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # 更新状态为运行中
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await self.db.commit()

        try:
            # 根据模板类型选择填充策略
            fill_result = await self._fill_by_template(
                task.template_type,
                task.context_data,
                ai_service,
            )

            # 创建填充记录
            fill = AIWorkpaperFill(
                task_id=task_id,
                filled_content=fill_result["content"],
                confidence=fill_result["confidence"],
                model_used=fill_result.get("model_used", "unknown"),
                token_usage=fill_result.get("token_usage", {}),
                processing_time=fill_result.get("processing_time", 0),
            )
            self.db.add(fill)

            # 更新任务状态
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            task.result_summary = fill_result.get("summary")
            await self.db.commit()
            await self.db.refresh(fill)

            return fill

        except Exception as e:
            logger.exception(f"Fill task {task_id} failed")
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            raise

    async def _fill_by_template(
        self,
        template_type: str,
        context_data: dict[str, Any],
        ai_service: AIService,
    ) -> dict[str, Any]:
        """根据模板类型执行填充"""
        template_handlers = {
            "description": self._fill_description,
            "calculation": self._fill_calculation,
            "verification": self._fill_verification,
            "anomaly": self._fill_anomaly,
            "conclusion": self._fill_conclusion,
        }

        handler = template_handlers.get(
            template_type,
            self._fill_description,  # 默认文本填充
        )

        return await handler(context_data, ai_service)

    async def _fill_description(
        self,
        context_data: dict[str, Any],
        ai_service: AIService,
    ) -> dict[str, Any]:
        """填充文本描述类底稿"""
        prompt = self._build_description_prompt(context_data)
        response = await ai_service.chat(
            messages=[{"role": "user", "content": prompt}],
            model="audit",
        )
        return self._parse_ai_response(response)

    async def _fill_calculation(
        self,
        context_data: dict[str, Any],
        ai_service: AIService,
    ) -> dict[str, Any]:
        """填充计算验证类底稿"""
        prompt = self._build_calculation_prompt(context_data)
        response = await ai_service.chat(
            messages=[{"role": "user", "content": prompt}],
            model="audit",
        )
        return self._parse_ai_response(response)

    async def _fill_verification(
        self,
        context_data: dict[str, Any],
        ai_service: AIService,
    ) -> dict[str, Any]:
        """填充核对验证类底稿"""
        prompt = self._build_verification_prompt(context_data)
        response = await ai_service.chat(
            messages=[{"role": "user", "content": prompt}],
            model="audit",
        )
        return self._parse_ai_response(response)

    async def _fill_anomaly(
        self,
        context_data: dict[str, Any],
        ai_service: AIService,
    ) -> dict[str, Any]:
        """填充异常标注类底稿"""
        prompt = self._build_anomaly_prompt(context_data)
        response = await ai_service.chat(
            messages=[{"role": "user", "content": prompt}],
            model="audit",
        )
        return self._parse_ai_response(response)

    async def _fill_conclusion(
        self,
        context_data: dict[str, Any],
        ai_service: AIService,
    ) -> dict[str, Any]:
        """填充审计结论类底稿"""
        prompt = self._build_conclusion_prompt(context_data)
        response = await ai_service.chat(
            messages=[{"role": "user", "content": prompt}],
            model="audit",
        )
        return self._parse_ai_response(response)

    def _build_description_prompt(self, context: dict) -> str:
        """构建文本描述填充提示词"""
        return f"""你是一名资深审计师，请根据以下信息撰写审计说明。

项目信息：
- 被审计单位：{context.get('company_name', '未知')}
- 科目/报表项目：{context.get('account_name', '未知')}
- 审计期间：{context.get('period', '未知')}

业务背景：
{context.get('business_description', '无额外信息')}

数据摘要：
{json.dumps(context.get('data_summary', {}), ensure_ascii=False, indent=2)}

请撰写一段专业的审计说明，包括：
1. 该科目的业务背景
2. 执行的审计程序
3. 审计结论

要求：语言专业、简洁，字数 200-500 字。"""

    def _build_calculation_prompt(self, context: dict) -> str:
        """构建计算验证填充提示词"""
        return f"""你是一名审计师，请验证以下计算的正确性。

科目：{context.get('account_name', '未知')}
数据：
{json.dumps(context.get('data', {}), ensure_ascii=False, indent=2)}

计算公式：
{context.get('formula', '未提供')}

请执行以下任务：
1. 验证各项计算的准确性
2. 指出计算中的任何错误
3. 提供计算过程说明

以 JSON 格式返回结果：
{{
  "valid": true/false,
  "calculations": [...],
  "errors": [...],
  "explanation": "..."
}}"""

    def _build_verification_prompt(self, context: dict) -> str:
        """构建核对验证填充提示词"""
        return f"""你是一名审计师，请执行核对验证。

核对项目：{context.get('verification_item', '未知')}
核对内容：
{json.dumps(context.get('data', {}), ensure_ascii=False, indent=2)}

钩稽关系：
{context.get('relationship', '未指定')}

请执行核对并给出结论。以 JSON 格式返回：
{{
  "passed": true/false,
  "findings": [...],
  "conclusion": "..."
}}"""

    def _build_anomaly_prompt(self, context: dict) -> str:
        """构建异常标注填充提示词"""
        return f"""你是一名审计师，请分析以下数据中的异常项。

科目：{context.get('account_name', '未知')}
数据：
{json.dumps(context.get('data', []), ensure_ascii=False, indent=2)}

阈值设置：变动超过 {context.get('threshold', '20%')} 视为异常

请识别并标注异常项，以 JSON 格式返回：
{{
  "anomalies": [
    {{"item": "...", "value": ..., "expected": ..., "deviation": "..."}}
  ],
  "summary": "..."
}}"""

    def _build_conclusion_prompt(self, context: dict) -> str:
        """构建审计结论填充提示词"""
        return f"""你是一名审计师，请根据以下审计证据给出审计结论。

审计项目：{context.get('audit_item', '未知')}
风险评估：{context.get('risk_level', '中等')}
审计证据：
{json.dumps(context.get('evidence', {}), ensure_ascii=False, indent=2)}

重大事项：
{context.get('material_items', '无')}

请撰写审计结论，包括：
1. 审计意见（无保留/保留/否定/无法表示）
2. 主要理由
3. 需关注事项

以 JSON 格式返回：
{{
  "opinion": "...",
  "reasoning": "...",
  "matters": [...]
}}"""

    def _parse_ai_response(self, response: dict) -> dict[str, Any]:
        """解析 AI 响应，提取结构化结果"""
        content = response.get("content", "")
        model = response.get("model", "unknown")
        usage = response.get("usage", {})

        # 尝试解析 JSON
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return {
                    "content": json.dumps(parsed, ensure_ascii=False, indent=2),
                    "confidence": 0.9,
                    "model_used": model,
                    "token_usage": usage,
                    "summary": parsed.get("summary") or parsed.get("conclusion") or "",
                    "processing_time": 0,
                }
            except json.JSONDecodeError:
                pass

        # 非 JSON 响应，直接返回原文
        return {
            "content": content,
            "confidence": 0.7,
            "model_used": model,
            "token_usage": usage,
            "summary": content[:200] if content else "",
            "processing_time": 0,
        }

    async def get_task(self, task_id: UUID) -> Optional[AIWorkpaperTask]:
        """获取任务详情"""
        result = await self.db.execute(
            select(AIWorkpaperTask).where(AIWorkpaperTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_fill_result(self, task_id: UUID) -> Optional[AIWorkpaperFill]:
        """获取填充结果"""
        result = await self.db.execute(
            select(AIWorkpaperFill).where(AIWorkpaperFill.task_id == task_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        project_id: UUID,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[AIWorkpaperTask]:
        """列出项目的填充任务"""
        query = select(AIWorkpaperTask).where(
            AIWorkpaperTask.project_id == project_id
        )
        if status:
            query = query.where(AIWorkpaperTask.status == status)
        query = query.order_by(AIWorkpaperTask.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # =========================================================================
    # 核心方法实现
    # =========================================================================

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
                TbLedger.project_id == project_id,
                TbLedger.year == year,
                TbLedger.account_code == account_code,
                TbLedger.company_code == company_code,
                TbLedger.is_deleted == False,  # noqa: E712
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
                TbAuxBalance.project_id == project_id,
                TbAuxBalance.year == year,
                TbAuxBalance.account_code == account_code,
                TbAuxBalance.company_code == company_code,
                TbAuxBalance.is_deleted == False,  # noqa: E712
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
                    TbAuxBalance.project_id == project_id,
                    TbAuxBalance.year == year,
                    TbAuxBalance.account_code == row.standard_account_code,
                    TbAuxBalance.is_deleted == False,  # noqa: E712,
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

    # =========================================================================
    # 辅助方法
    # =========================================================================

    async def review_workpaper_with_prompt(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        ai_service: AIService,
    ) -> list[AIContent]:
        """
        提示词驱动的底稿AI智能复核

        1. 通过 workpaper_id 查找 wp_index 获取 audit_cycle
        2. 通过 audit_cycle 匹配 TSJ/ 下对应的审计复核提示词文件
        3. 将提示词注入 LLM system prompt
        4. LLM 按提示词框架逐项检查底稿
        5. 输出结构化复核发现
        6. 每个发现存入 ai_content 表

        Args:
            project_id: 项目ID
            workpaper_id: 底稿ID
            ai_service: AI服务实例

        Returns:
            list[AIContent]: 复核发现列表
        """
        from app.models.workpaper_models import WpIndex, WorkingPaper

        # 1. 获取底稿索引信息
        result = await self.db.execute(
            select(WpIndex).where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == False,  # noqa: E712
            )
        )
        wp_indexes = result.scalars().all()

        # 查找匹配的底稿
        target_wp = None
        audit_cycle = None
        for wp in wp_indexes:
            # 获取底稿文件
            wp_file_result = await self.db.execute(
                select(WorkingPaper).where(
                    WorkingPaper.wp_index_id == wp.id,
                    WorkingPaper.is_deleted == False,  # noqa: E712
                )
            )
            wp_files = wp_file_result.scalars().all()
            for wf in wp_files:
                if str(wf.id) == str(workpaper_id):
                    target_wp = wf
                    audit_cycle = wp.audit_cycle
                    break
            if target_wp:
                break

        if not target_wp:
            logger.warning(f"Workpaper {workpaper_id} not found")
            return []

        # 2. 加载审计复核提示词（从 TSJ/ 目录按 audit_cycle 匹配）
        review_prompt = await self.load_review_prompt(audit_cycle or "general")

        # 3. 读取底稿文件内容，注入提示词占位符 {{#sys.files#}}
        workpaper_content = ""
        try:
            if target_wp.file_path:
                import os
                if os.path.exists(target_wp.file_path):
                    with open(target_wp.file_path, encoding="utf-8") as f:
                        workpaper_content = f.read()
                elif target_wp.content_text:
                    workpaper_content = target_wp.content_text
        except Exception as e:
            logger.warning(f"Failed to read workpaper file: {e}")

        # 4. 替换提示词中的 {{#sys.files#}} 占位符
        if workpaper_content:
            # 截断过长内容避免超出上下文窗口
            max_len = 8000
            if len(workpaper_content) > max_len:
                workpaper_content = workpaper_content[:max_len] + "\n... (内容已截断)"
            prompt_content = review_prompt.replace("{{#sys.files#}}", workpaper_content)
        else:
            prompt_content = review_prompt.replace(
                "{{#sys.files#}}",
                f"[底稿文件 ID: {workpaper_id}]（文件内容不可用）"
            )

        # 5. 构建复核请求
        prompt = f"""{prompt_content}

## 底稿信息
- 底稿ID: {workpaper_id}
- 项目ID: {project_id}
- 审计循环: {audit_cycle or 'general'}

请按提示词框架逐项检查底稿，输出结构化复核发现。
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
            logger.warning(f"AI chat failed for workpaper review: {e}")
            content_text = "【底稿复核】AI复核暂时不可用，请手动复核。"

        # 4. 创建 AI 内容记录
        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.risk_alert,
            content_text=content_text,
            data_sources={
                "audit_cycle": audit_cycle,
                "review_type": "prompt_driven",
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

    async def load_review_prompt(self, audit_cycle: str) -> str:
        """
        加载审计复核提示词

        按科目名称关键词匹配 TSJ/ 下的 .md 文件
        未匹配到时返回通用复核提示词模板

        Args:
            audit_cycle: 审计循环（如 "cash"、"receivable"）

        Returns:
            str: 提示词内容
        """
        import os
        import re
        import glob

        # 1. 查找 TSJ 目录（支持绝对路径或相对路径）
        tsj_base = os.environ.get("TSJ_PROMPT_DIR")
        if not tsj_base:
            # 尝试相对于项目根目录
            backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            tsj_base = os.path.join(backend_root, "..", "TSJ")
        tsj_base = os.path.abspath(tsj_base)

        if not os.path.isdir(tsj_base):
            logger.warning(f"TSJ prompt directory not found: {tsj_base}")
            return self._base_review_prompt

        # 2. 收集所有 .md 文件
        md_files = glob.glob(os.path.join(tsj_base, "*.md"))
        if not md_files:
            logger.warning(f"No .md files found in {tsj_base}")
            return self._base_review_prompt

        # 3. 构造关键词匹配模式（支持中文和英文别名）
        cycle_keywords = self._audit_cycle_aliases.get(audit_cycle.lower(), [audit_cycle])

        matched_file = None
        matched_score = 0

        for md_path in md_files:
            fname = os.path.basename(md_path)
            score = 0
            for kw in cycle_keywords:
                # 匹配文件名中包含关键词（忽略"审计复核提示词"通用部分）
                name_without_suffix = re.sub(r"审计复核提示词\.md$", "", fname)
                if kw.lower() in name_without_suffix.lower():
                    score += 2
                if kw.lower() in fname.lower():
                    score += 1
            if score > matched_score:
                matched_score = score
                matched_file = md_path

        # 4. 读取匹配到的文件内容
        if matched_file and matched_score > 0:
            try:
                with open(matched_file, encoding="utf-8") as f:
                    content = f.read().strip()
                logger.info(f"Loaded TSJ prompt: {os.path.basename(matched_file)} (score={matched_score})")
                return content
            except Exception as e:
                logger.warning(f"Failed to read TSJ file {matched_file}: {e}")

        # 5. 未匹配时按通用关键词模糊搜索
        generic_keywords = ["总体", "general", "审计方案"]
        for md_path in md_files:
            fname = os.path.basename(md_path)
            for kw in generic_keywords:
                if kw.lower() in fname.lower():
                    try:
                        with open(md_path, encoding="utf-8") as f:
                            content = f.read().strip()
                        logger.info(f"Fallback TSJ prompt (generic): {fname}")
                        return content
                    except Exception:
                        pass

        logger.info("No matching TSJ prompt found, using base prompt")
        return self._base_review_prompt

    @property
    def _base_review_prompt(self) -> str:
        """通用复核提示词模板"""
        return """你是审计师，请对审计底稿进行智能复核。

## 复核框架

### 1. 审计认定检查
- 存在性：账面记录是否存在
- 完整性：所有交易是否记录
- 权利和义务：资产是否属于被审计单位
- 计价或分摊：金额是否正确
- 准确性、分类和截止：是否正确记录

### 2. 程序执行检查
- 审计程序是否完整执行
- 样本量是否充分
- 替代程序是否充分

### 3. 数据完整性检查
- 勾稽关系是否正确
- 小计合计是否准确
- 期初期末是否连续

### 4. 风险评估复核
- 异常事项是否标注
- 高风险领域是否充分关注
- 审计结论是否有充分证据支持

请按上述框架检查底稿，识别潜在问题并给出建议。
"""

    # 审计循环关键词别名映射（支持中英文通用术语）
    _audit_cycle_aliases: dict[str, list[str]] = {
        "cash": ["现金", "货币资金"],
        "bank": ["银行", "货币资金"],
        "receivable": ["应收", "应收账款", "其他应收"],
        "payable": ["应付", "应付账款", "其他应付"],
        "inventory": ["存货", "库存"],
        "fixed_asset": ["固定资产", "折旧"],
        "intangible": ["无形", "资产"],
        "revenue": ["收入", "销售", "营业"],
        "expense": ["费用", "成本", "支出"],
        "tax": ["税", "税费", "增值税"],
        "loan": ["借款", "贷款", "金融负债", "应付债券"],
        "equity": ["权益", "股本", "资本", "实收"],
        "investment": ["投资", "金融资产", "债权", "股权"],
        "goodwill": ["商誉", "减值"],
        "lease": ["租赁", "使用权"],
        "consolidation": ["合并", "抵消", "子公司"],
        "contingent": ["或有", "预计负债", "担保"],
        "related_party": ["关联", "关联方", "交易"],
        "subsequent": ["期后", "后续"],
        "going_concern": ["持续经营", "重大不确定"],
        "general": ["总体", "审计方案", "general"],
    }

    async def check_pending_confirmations(
        self,
        project_id: UUID,
        workpaper_id: UUID = None,
    ) -> int:
        """
        检查底稿中未确认的AI内容数量

        Args:
            project_id: 项目ID
            workpaper_id: 底稿ID（可选）

        Returns:
            int: 未确认数量
        """
        query = select(func.count(AIContent.id)).where(
            AIContent.project_id == project_id,
            AIContent.confirmation_status == AIConfirmationStatus.pending,
            AIContent.is_deleted == False,  # noqa: E712
        )
        if workpaper_id:
            query = query.where(AIContent.workpaper_id == workpaper_id)

        result = await self.db.execute(query)
        count = result.scalar()
        return count or 0
