"""ReviewPromptMixin：AI 复核（提示词驱动）— 已弃用

`review_workpaper_with_prompt` 已迁移至：
  - POST /api/workpapers/{wp_id}/review  （sheet-level）
  - POST /api/workpapers/{wp_id}/ai/tsj-review  （兼容旧入口，内部走新链路）

本 Mixin 仅保留 `check_pending_confirmations`；
`review_workpaper_with_prompt` / `load_review_prompt` 保留为 deprecated 薄包装，
防止外部脚本直接调用时静默走旧科目级路径。
"""

from __future__ import annotations

import logging
import warnings
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, func

from app.models.ai_models import (
    AIContent,
    AIContentType,
    AIConfirmationStatus,
    ConfidenceLevel,
)
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "review_workpaper_with_prompt 已弃用，请改用 "
    "POST /api/workpapers/{wp_id}/review（底稿级）或 "
    "POST /api/workpapers/{wp_id}/ai/tsj-review（兼容入口）。"
)


class ReviewPromptMixin:
    """提示词驱动的 AI 复核相关方法（部分已弃用）"""

    async def review_workpaper_with_prompt(
        self,
        project_id: UUID,
        workpaper_id: UUID,
        ai_service: AIService,
    ) -> list[AIContent]:
        """
        [DEPRECATED] 科目级提示词驱动复核。

        内部转发到新链路（ReviewPromptService + review_content_loader），
        并将结构化 findings 落库为 AIContent，保持旧调用方兼容。
        """
        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        logger.warning(_DEPRECATION_MSG)

        from app.services.llm_client import chat_completion
        from app.services.llm_response_parser import LlmResponseParser
        from app.services.review_content_loader import load_workpaper_review_content
        from app.services.review_prompt_service import ReviewPromptService

        # 查 wp_code
        wp_code = None
        try:
            from app.models.workpaper_models import WorkingPaper, WpIndex

            result = await self.db.execute(
                select(WorkingPaper, WpIndex)
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(WorkingPaper.id == workpaper_id)
            )
            row = result.first()
            if row:
                wp_code = row[1].wp_code
        except Exception as e:
            logger.warning("deprecated review: failed to resolve wp_code: %s", e)

        prompt_service = ReviewPromptService()
        prompt_result = prompt_service.load_prompt(wp_code or "general", sheet_name=None)
        workpaper_content = await load_workpaper_review_content(workpaper_id, None)

        system_prompt = (
            "你是资深审计师，请根据以下复核提示词对审计底稿内容进行智能复核。\n"
            "请以严格 JSON 格式输出。\n\n"
            f"## 复核提示词\n\n{prompt_result.content}"
        )
        user_prompt = f"以下是需要复核的底稿内容：\n\n{workpaper_content}"

        try:
            if ai_service is not None:
                response = await ai_service.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                )
                if hasattr(response, "__aiter__"):
                    content_parts = []
                    async for part in response:
                        content_parts.append(part)
                    content_text = "".join(content_parts)
                else:
                    content_text = str(response)
            else:
                content_text = await chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.1,
                    max_tokens=3000,
                )
                if not isinstance(content_text, str):
                    content_text = str(content_text or "")
        except Exception as e:
            logger.warning(f"AI chat failed for workpaper review: {e}")
            content_text = "【底稿复核】AI复核暂时不可用，请手动复核。"

        parse_result = LlmResponseParser.parse(content_text)
        created: list[AIContent] = []

        if not parse_result.findings:
            ai_content = AIContent(
                project_id=project_id,
                workpaper_id=workpaper_id,
                content_type=AIContentType.risk_alert,
                content_text=content_text,
                data_sources={
                    "review_type": "prompt_driven_migrated",
                    "prompt_source": prompt_result.source_level,
                    "deprecated_caller": True,
                },
                generation_model="unknown",
                generation_time=datetime.now(timezone.utc),
                confidence_level=ConfidenceLevel.medium,
                confirmation_status=AIConfirmationStatus.pending,
            )
            self.db.add(ai_content)
            created.append(ai_content)
        else:
            for f in parse_result.findings:
                rem = f.suggestion or ""
                text_body = f"{f.description}\n整改建议：{rem}" if rem else f.description
                ai_content = AIContent(
                    project_id=project_id,
                    workpaper_id=workpaper_id,
                    content_type=AIContentType.risk_alert,
                    content_text=text_body,
                    data_sources={
                        "description": f.description,
                        "remediation": rem,
                        "severity": f.risk_level,
                        "issue_type": f.category,
                        "sheet": (f.sheet_location or "").split("!")[0] if f.sheet_location else "",
                        "cell_range": (
                            f.sheet_location.split("!")[-1]
                            if f.sheet_location and "!" in f.sheet_location
                            else ""
                        ),
                        "review_type": "prompt_driven_migrated",
                        "prompt_source": prompt_result.source_level,
                        "deprecated_caller": True,
                    },
                    generation_model="unknown",
                    generation_time=datetime.now(timezone.utc),
                    confidence_level=ConfidenceLevel.medium,
                    confirmation_status=AIConfirmationStatus.pending,
                )
                self.db.add(ai_content)
                created.append(ai_content)

        await self.db.commit()
        for item in created:
            await self.db.refresh(item)
        return created

    async def load_review_prompt(self, audit_cycle: str) -> str:
        """[DEPRECATED] 按 audit_cycle 关键词加载科目级提示词。

        请改用 ReviewPromptService.load_prompt(wp_code, sheet_name)。
        """
        warnings.warn(
            "load_review_prompt 已弃用，请改用 ReviewPromptService.load_prompt",
            DeprecationWarning,
            stacklevel=2,
        )
        from app.services.review_prompt_service import ReviewPromptService

        # 粗略映射：audit_cycle 英文别名 → 尝试 D2 等；否则走 base
        cycle_to_wp = {
            "receivable": "D2",
            "cash": "E1",
            "inventory": "F2",
            "revenue": "D4",
            "payable": "F4",
        }
        wp_code = cycle_to_wp.get((audit_cycle or "").lower(), audit_cycle or "general")
        result = ReviewPromptService().load_prompt(wp_code, sheet_name=None)
        return result.content

    @property
    def _base_review_prompt(self) -> str:
        """通用复核提示词模板（兼容旧属性访问）"""
        from app.services.review_prompt_service import ReviewPromptService

        return ReviewPromptService().load_prompt("general", None).content

    # 审计循环关键词别名映射（保留供外部只读，不再用于主路径）
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
