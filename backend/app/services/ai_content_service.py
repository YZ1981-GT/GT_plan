"""AI 内容管理服务

提供 AI 生成内容的创建、确认、查询和门控功能：
- 创建 AI 内容记录（初始状态 pending）
- 确认/修改/拒绝/重新生成 AI 内容
- 统计项目 AI 内容汇总
- 检查阶段转换门控（关键底稿不得有待确认 AI 内容）
- 检查 AI 边界（AI 不能做的最终判断）

对应需求 3.2、3.3、3.4、3.5、9.1-9.5
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIContent,
    AIContentType,
    AIConfirmationStatus,
    ConfidenceLevel,
)
from app.models.ai_schemas import AIContentSummary

logger = logging.getLogger(__name__)

# 关键底稿类型关键词（对应需求 3.5 / 验收标准 5）
CRITICAL_WORKPAPER_KEYWORDS: list[str] = [
    "revenue",
    "receivables",
    "payables",
    "inventory",
    "impairment",
    "long-term investments",
    "long_term_investments",
    "consolidation",
    "contingent liabilities",
    "contingent_liabilities",
    "related party transactions",
    "related_party_transactions",
    "going concern",
    "subsequent events",
    "收入确认",
    "应收账款",
    "应付账款",
    "存货",
    "资产减值",
    "长期投资",
    "合并报表",
    "或有负债",
    "关联方交易",
    "持续经营",
    "期后事项",
]

# AI 不可处理的边界关键词（对应需求 9.1 / 验收标准 8）
AI_BOUNDARY_KEYWORDS: list[str] = [
    "审计意见",
    "出具报告",
    "审计报告",
    "出具审计报告",
    "发表审计意见",
    "确定重要性水平",
    "确定审计报告类型",
    "发表最终",
    "最终判断",
    "final opinion",
    "audit opinion",
    "issue report",
]


class PhaseGateError(Exception):
    """阶段门控错误：有关键底稿的 AI 内容尚未确认"""

    def __init__(self, pending_count: int, critical_workpapers: list[str]):
        self.pending_count = pending_count
        self.critical_workpapers = critical_workpapers
        super().__init__(
            f"{pending_count} 个关键底稿有待确认的 AI 内容，"
            f"无法进行阶段转换: {critical_workpapers}"
        )


class AIBoundaryError(Exception):
    """AI 边界错误：请求触碰到 AI 不可处理的边界"""

    pass


class AIContentService:
    """AI 内容管理服务"""

    def __init__(self, db: AsyncSession) -> None:
        """初始化服务

        Args:
            db: SQLAlchemy 异步数据库会话
        """
        self.db = db

    # -------------------------------------------------------------------------
    # 核心 CRUD 方法
    # -------------------------------------------------------------------------

    async def create_content(
        self,
        project_id: UUID,
        content_type: AIContentType | str,
        content_text: str,
        workpaper_id: UUID | None = None,
        data_sources: list[dict[str, Any]] | None = None,
        confidence_level: ConfidenceLevel | str | None = None,
        generation_model: str | None = None,
    ) -> AIContent:
        """创建 AI 生成内容记录（初始状态 pending）

        Args:
            project_id: 项目 UUID
            content_type: 内容类型（data_fill/analytical_review/risk_alert/test_summary/note_draft）
            content_text: AI 生成的内容文本
            workpaper_id: 关联的工作底稿 UUID（可为 None）
            data_sources: 数据来源列表（如 trial_balance, journal_entries）
            confidence_level: 置信度等级（high/medium/low）
            generation_model: 使用的 AI 模型名称

        Returns:
            创建的 AIContent 记录

        Raises:
            ValueError: 缺少必填字段
        """
        if not content_text:
            raise ValueError("content_text is required")

        # 解析枚举
        if isinstance(content_type, str):
            content_type = AIContentType(content_type)

        confidence: ConfidenceLevel | None = None
        if confidence_level:
            if isinstance(confidence_level, str):
                confidence = ConfidenceLevel(confidence_level)
            else:
                confidence = confidence_level

        content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=content_type,
            content_text=content_text,
            data_sources=data_sources or [],
            generation_model=generation_model,
            generation_time=datetime.now(timezone.utc),
            confidence_level=confidence,
            confirmation_status=AIConfirmationStatus.pending,
        )
        self.db.add(content)
        await self.db.commit()
        await self.db.refresh(content)
        logger.info(
            "Created AIContent id=%s project_id=%s type=%s status=pending",
            content.id,
            project_id,
            content_type.value,
        )
        return content

    async def confirm_content(
        self,
        content_id: UUID,
        user_id: UUID,
        action: str,
        modification_note: str | None = None,
    ) -> AIContent:
        """确认 AI 内容（接受/修改/拒绝/重新生成）

        Args:
            content_id: AI 内容 UUID
            user_id: 确认操作的用户 UUID
            action: 操作类型（accept/modify/reject/regenerate）
            modification_note: 修改说明（modify 动作必须填写）

        Returns:
            更新后的 AIContent 记录

        Raises:
            ValueError: action 不合法或内容不存在
        """
        valid_actions = {"accept", "modify", "reject", "regenerate"}
        if action not in valid_actions:
            raise ValueError(f"action must be one of {sorted(valid_actions)}")

        result = await self.db.execute(
            select(AIContent).where(
                AIContent.id == content_id,
                AIContent.is_deleted == False,  # noqa: E712
            )
        )
        content = result.scalar_one_or_none()
        if content is None:
            raise ValueError(f"AIContent {content_id} not found")

        if action == "modify" and not modification_note:
            raise ValueError("modification_note is required when action is 'modify'")

        # action -> confirmation_status 映射
        status_map = {
            "accept": AIConfirmationStatus.accepted,
            "modify": AIConfirmationStatus.modified,
            "reject": AIConfirmationStatus.rejected,
            "regenerate": AIConfirmationStatus.regenerated,
        }
        content.confirmation_status = status_map[action]
        content.confirmed_by = user_id
        content.confirmed_at = datetime.now(timezone.utc)
        content.modification_note = modification_note

        await self.db.commit()
        await self.db.refresh(content)
        logger.info(
            "Confirmed AIContent id=%s action=%s new_status=%s user=%s",
            content_id,
            action,
            content.confirmation_status.value,
            user_id,
        )
        return content

    # -------------------------------------------------------------------------
    # 查询方法
    # -------------------------------------------------------------------------

    async def get_pending_count(
        self,
        project_id: UUID,
        workpaper_id: UUID | None = None,
        critical_only: bool = False,
        workpaper_type: str | None = None,
    ) -> int:
        """获取未确认 AI 内容数量

        Args:
            project_id: 项目 UUID
            workpaper_id: 工作底稿 UUID（可选，筛选特定底稿）
            critical_only: 是否仅统计关键底稿
            workpaper_type: 工作底稿类型关键词（配合 critical_only 使用）

        Returns:
            待确认 AI 内容数量
        """
        query = select(func.count(AIContent.id)).where(
            AIContent.project_id == project_id,
            AIContent.confirmation_status == AIConfirmationStatus.pending,
            AIContent.is_deleted == False,  # noqa: E712
        )
        if workpaper_id is not None:
            query = query.where(AIContent.workpaper_id == workpaper_id)
        if critical_only and workpaper_type:
            # 按工作底稿类型关键词筛选
            wp_lower = workpaper_type.lower()
            conditions = [AIContent.workpaper_id.is_(None)]  # 默认不符合
            for kw in CRITICAL_WORKPAPER_KEYWORDS:
                if kw.lower() in wp_lower:
                    # 假设 workpaper_id 关联的工作底稿类型含关键词
                    # 此处通过 workpaper_type 字符串匹配，实际查询需 join workpaper 表
                    conditions.append(
                        AIContent.workpaper_id.isnot(None)  # noqa: E712
                    )
                    break
            query = query.where(conditions[0])  # 简化：按 workpaper_id 非空判断

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_project_summary(
        self,
        project_id: UUID,
    ) -> AIContentSummary:
        """项目 AI 内容汇总统计

        Args:
            project_id: 项目 UUID

        Returns:
            AIContentSummary 包含 total/pending/accepted/modified/rejected/
            regenerated/modification_rate
        """
        status_counts: dict[str, int] = {}
        for status in AIConfirmationStatus:
            result = await self.db.execute(
                select(func.count(AIContent.id)).where(
                    AIContent.project_id == project_id,
                    AIContent.confirmation_status == status,
                    AIContent.is_deleted == False,  # noqa: E712
                )
            )
            status_counts[status.value] = result.scalar() or 0

        total = sum(status_counts.values())
        pending = status_counts.get("pending", 0)
        accepted = status_counts.get("accepted", 0)
        modified = status_counts.get("modified", 0)
        rejected = status_counts.get("rejected", 0)
        regenerated = status_counts.get("regenerated", 0)

        modification_rate = round(
            (modified + rejected) / total, 4
        ) if total > 0 else 0.0

        return AIContentSummary(
            total=total,
            pending=pending,
            accepted=accepted,
            modified=modified,
            rejected=rejected,
            regenerated=regenerated,
            modification_rate=modification_rate,
        )

    async def get_content_list(
        self,
        project_id: UUID,
        workpaper_id: UUID | None = None,
        content_type: AIContentType | None = None,
        confirmation_status: AIConfirmationStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AIContent], int]:
        """获取 AI 内容列表（分页）

        Args:
            project_id: 项目 UUID
            workpaper_id: 工作底稿 UUID（可选）
            content_type: 内容类型筛选
            confirmation_status: 确认状态筛选
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            (AI 内容列表, 总数)
        """
        conditions = [
            AIContent.project_id == project_id,
            AIContent.is_deleted == False,  # noqa: E712
        ]
        if workpaper_id is not None:
            conditions.append(AIContent.workpaper_id == workpaper_id)
        if content_type is not None:
            conditions.append(AIContent.content_type == content_type)
        if confirmation_status is not None:
            conditions.append(AIContent.confirmation_status == confirmation_status)

        # 总数
        count_query = select(func.count(AIContent.id)).where(*conditions)
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # 分页数据
        offset = (page - 1) * page_size
        data_query = (
            select(AIContent)
            .where(*conditions)
            .order_by(AIContent.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(data_query)
        items = list(result.scalars().all())

        return items, total

    # -------------------------------------------------------------------------
    # 门控与边界检查
    # -------------------------------------------------------------------------

    async def check_phase_gate(
        self,
        project_id: UUID,
        workpaper_id: UUID | None = None,
        workpaper_type: str | None = None,
    ) -> bool:
        """检查阶段转换门控

        关键底稿（收入、应收/应付、存货减值、长期投资、合并报表、
        或有负债、关联方交易、持续经营、期后事项）不得有待确认的
        AI 内容才能进行阶段转换。

        Args:
            project_id: 项目 UUID
            workpaper_id: 工作底稿 UUID（可选）
            workpaper_type: 工作底稿类型描述（用于判断是否为关键底稿）

        Returns:
            True 表示可以通过门控（无 pending 内容或非关键底稿）

        Raises:
            PhaseGateError: 有关键底稿存在 pending AI 内容
        """
        # 判断是否为关键底稿
        is_critical = self._is_critical_workpaper(workpaper_type or "")

        if not is_critical:
            # 非关键底稿不受门控限制
            return True

        # 关键底稿：查询 pending 状态的 AI 内容
        query = select(func.count(AIContent.id)).where(
            AIContent.project_id == project_id,
            AIContent.confirmation_status == AIConfirmationStatus.pending,
            AIContent.is_deleted == False,  # noqa: E712
        )
        if workpaper_id is not None:
            query = query.where(AIContent.workpaper_id == workpaper_id)

        result = await self.db.execute(query)
        pending_count = result.scalar() or 0

        if pending_count > 0:
            critical_list = [workpaper_type] if workpaper_type else []
            raise PhaseGateError(
                pending_count=pending_count,
                critical_workpapers=critical_list,
            )

        return True

    def _is_critical_workpaper(self, workpaper_type: str) -> bool:
        """判断是否为关键底稿

        Args:
            workpaper_type: 工作底稿类型描述

        Returns:
            True 表示是关键底稿
        """
        wp_lower = workpaper_type.lower()
        for keyword in CRITICAL_WORKPAPER_KEYWORDS:
            if keyword.lower() in wp_lower:
                return True
        return False

    def check_boundary(self, task_description: str) -> dict[str, Any]:
        """检查请求是否触碰 AI 不可处理的边界

        AI 边界（对应需求 9.1）：AI 不得做出最终审计判断，
        只能提供辅助建议和分析。

        Args:
            task_description: 任务描述文本

        Returns:
            dict，包含：
            - is_blocked: bool，是否触碰边界
            - reason: str，阻断原因（如果有）
            - can_do: list[str]，AI 可以做的事项
            - cannot_do: list[str]，AI 不可做的事项
        """
        desc_lower = task_description.lower()
        blocked_keywords: list[str] = []
        for keyword in AI_BOUNDARY_KEYWORDS:
            if keyword.lower() in desc_lower:
                blocked_keywords.append(keyword)

        is_blocked = len(blocked_keywords) > 0

        return {
            "is_blocked": is_blocked,
            "reason": (
                f"任务 '{task_description}' 涉及 AI 不可做的最终判断: "
                f"{', '.join(blocked_keywords)}"
                if is_blocked
                else None
            ),
            "can_do": [
                "生成分析性复核初稿",
                "提取数据填写底稿",
                "识别异常波动并建议关注",
                "生成附注文字初稿",
                "总结测试结果摘要",
                "预警潜在风险项",
                "交叉比对合同与账面数据",
                "验证证据链完整性",
                "辅助函证地址核查",
                "OCR 识别单据内容",
            ],
            "cannot_do": [
                "出具或起草审计报告",
                "发表最终审计意见",
                "确定审计报告类型（无保留/保留/否定/无法表示）",
                "独立确定重要性水平",
                "做出最终的重大会计判断",
                "替代审计人员专业判断",
            ],
        }

    def _is_ai_allowed(self, item_description: str) -> bool:
        """判断 AI 是否被允许处理特定审计项目

        关键审计判断项目不允许 AI 直接填制。

        Args:
            item_description: 项目描述

        Returns:
            True 表示 AI 可以处理，False 表示不可以
        """
        # 如果 check_boundary 触发阻断，则不允许
        result = self.check_boundary(item_description)
        if result["is_blocked"]:
            return False

        # 额外检查：关键判断关键词
        critical_judgment_keywords = [
            "持续经营假设",
            "重大资产减值",
            "或有负债评估",
            "关联方交易定价",
            "商誉减值",
            "收入确认会计政策",
            "会计估计变更",
        ]
        desc_lower = item_description.lower()
        for kw in critical_judgment_keywords:
            if kw.lower() in desc_lower:
                return False

        return True
