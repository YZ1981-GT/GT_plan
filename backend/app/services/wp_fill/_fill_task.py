"""FillTaskMixin：AI 填充任务

create/execute_fill_task、_fill_*、_build_*_prompt、_parse_ai_response、
get_task、get_fill_result、list_tasks。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select

from app.models.ai_models import (
    AIWorkpaperTask,
    AIWorkpaperFill,
)
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)


class FillTaskMixin:
    """AI 填充任务相关方法"""

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
