"""复核模式接入与 SystemMessageAssembler（Task 20）

Feature: dsh-agent-panel-integration
Requirements:
  - 9.1：仅 AuthorizedHostContext=workpaper 且有权 sheet 时加载 ReviewPromptService
  - 9.2：GET /review-prompt 只返回 source_level/tips/checklist/risk_areas/version，
    不返回正文
  - 9.3：SystemMessageAssembler 合成一条 system（政策 + review + 数据定界）
  - 9.5：prompt 加载失败以 typed error 终止，不静默普通问答
  - 9.6：review mode 保存到 server session
Design: "Components and Interfaces → 9. 复核模式与 SystemMessageAssembler"

## SystemMessageAssembler

将以下内容**合成恰好一条 system message**（Req 9.3）：
1. NATIVE_SYSTEM_POLICY（平台通用审计顾问政策）
2. review prompt（复核模式时，从 ReviewPromptService 加载的底稿级提示词正文）
3. 数据定界（UNTRUSTED_DATA_NOTICE + CONTEXT_BLOCK_OPEN/CLOSE 包裹的上下文数据）

## 复核模式激活条件（Req 9.1）

- host_type == workpaper
- 用户请求 review_mode=True
- wp_code 可从 host 解析
- ReviewPromptService 能加载到 prompt（至少 base level）
- **prompt 加载失败 → typed error 终止 run**（Req 9.5）

## review mode session 持久化（Req 9.6）

review_mode 标志保存在 ai_chat_session.metadata 中，恢复时不写 localStorage。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_chat.contracts import HostType
from app.services.ai_chat.host_context import AuthorizedHostContext

logger = logging.getLogger(__name__)

__all__ = [
    "ReviewModeContext",
    "ReviewModePreview",
    "ReviewModeFailed",
    "SystemMessageAssembler",
    "resolve_review_mode",
    "save_review_mode_to_session",
    "load_review_mode_from_session",
]


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


class ReviewModeFailed(Exception):
    """复核模式加载失败（Req 9.5：typed error 终止，不静默普通问答）。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ReviewModeContext:
    """复核模式的服务端上下文（正文不下发前端）。"""

    enabled: bool
    wp_code: str
    sheet_name: str | None
    source_level: str  # sheet / subject / base
    prompt_content: str  # 正文（只在 SystemMessageAssembler 内消费，不返回前端）
    tips: list[str]
    checklist: list[str]
    risk_areas: list[dict[str, str]]
    version: str


@dataclass(frozen=True)
class ReviewModePreview:
    """复核模式前端预览（Req 9.2：不含正文）。"""

    enabled: bool
    source_level: str
    tips: list[str]
    checklist: list[str]
    risk_areas: list[dict[str, str]]
    version: str
    wp_code: str = ""
    sheet_name: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "source_level": self.source_level,
            "tips": self.tips,
            "checklist": self.checklist,
            "risk_areas": self.risk_areas,
            "version": self.version,
            "wp_code": self.wp_code,
            "sheet_name": self.sheet_name or "",
        }


# ---------------------------------------------------------------------------
# 复核模式解析
# ---------------------------------------------------------------------------


async def resolve_review_mode(
    db: AsyncSession,
    *,
    host: AuthorizedHostContext,
    review_mode: bool,
    sheet_name: str | None = None,
) -> ReviewModeContext | None:
    """解析复核模式上下文。

    Req 9.1：仅 workpaper host 且 review_mode=True 时激活。
    Req 9.5：prompt 加载失败以 typed error 终止。

    Returns:
        ReviewModeContext 或 None（未启用时）

    Raises:
        ReviewModeFailed: prompt 加载失败
    """
    if not review_mode:
        return None

    # 仅 workpaper host 支持复核模式
    if host.resource_type is not HostType.workpaper:
        return None

    # 解析 wp_code
    wp_code = await _resolve_wp_code(db, host.resource_id)
    if not wp_code:
        raise ReviewModeFailed(
            "wp_code_unavailable",
            "无法从当前底稿解析 wp_code，复核模式不可用",
        )

    # 加载 prompt
    try:
        from app.services.review_prompt_service import ReviewPromptService

        service = ReviewPromptService()
        result = service.load_prompt(wp_code, sheet_name)
    except Exception as exc:
        logger.error(
            "ReviewPromptService.load_prompt 失败 wp_code=%s sheet=%s: %s",
            wp_code, sheet_name, exc,
        )
        raise ReviewModeFailed(
            "prompt_load_failed",
            f"复核提示词加载失败：{type(exc).__name__}",
        ) from exc

    if not result.content:
        raise ReviewModeFailed(
            "prompt_empty",
            f"底稿 {wp_code} 无可用复核提示词",
        )

    return ReviewModeContext(
        enabled=True,
        wp_code=wp_code,
        sheet_name=sheet_name or "",
        source_level=result.source_level,
        prompt_content=result.content,
        tips=result.tips,
        checklist=result.checklist,
        risk_areas=[
            {"level": ra.level, "text": ra.text}
            for ra in result.risk_areas
        ],
        version=result.version,
    )


async def _resolve_wp_code(db: AsyncSession, workpaper_id: str) -> str | None:
    """从 working paper ID 解析 wp_code。"""
    from app.models.workpaper_models import WorkingPaper, WpIndex
    from app.services.ai_chat.contracts import coerce_uuid

    uid = coerce_uuid(workpaper_id)
    if uid is None:
        return None

    row = (
        await db.execute(
            sa.select(WpIndex.wp_code)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(WorkingPaper.id == uid)
        )
    ).scalar_one_or_none()
    return row


# ---------------------------------------------------------------------------
# Session 持久化（Req 9.6）
# ---------------------------------------------------------------------------


async def save_review_mode_to_session(
    db: AsyncSession,
    session_id: UUID,
    *,
    review_mode: bool,
    sheet_name: str | None = None,
) -> None:
    """将 review_mode 保存到 server session metadata。"""
    from app.models.ai_models import AIChatSession

    # 使用 JSONB 字段存储 review_mode 配置
    metadata_patch = {"review_mode": review_mode}
    if sheet_name:
        metadata_patch["review_sheet_name"] = sheet_name

    await db.execute(
        sa.update(AIChatSession)
        .where(AIChatSession.id == session_id)
        .values(
            metadata=sa.func.coalesce(
                AIChatSession.metadata, sa.cast({}, sa.JSON)
            ).op("||")(sa.cast(metadata_patch, sa.JSON))
        )
    )


async def load_review_mode_from_session(
    db: AsyncSession, session_id: UUID
) -> tuple[bool, str | None]:
    """从 server session 恢复 review_mode 状态。

    Returns:
        (review_mode, sheet_name)
    """
    from app.models.ai_models import AIChatSession

    row = (
        await db.execute(
            sa.select(AIChatSession.metadata).where(AIChatSession.id == session_id)
        )
    ).scalar_one_or_none()

    if not row or not isinstance(row, dict):
        return False, None

    return (
        bool(row.get("review_mode", False)),
        row.get("review_sheet_name"),
    )


# ---------------------------------------------------------------------------
# SystemMessageAssembler
# ---------------------------------------------------------------------------


class SystemMessageAssembler:
    """将政策、复核 prompt 和数据定界合成一条 system message（Req 9.3）。

    替代 native_engine._build_native_messages 中的内联组装逻辑，
    使复核模式接入独立于引擎实现。

    Usage::

        assembler = SystemMessageAssembler()
        system_content = assembler.assemble(
            review_context=review_ctx,
            project_summary="...",
            doc_excerpt="...",
            knowledge_hits=[...],
            mention_texts=[...],
        )
        messages = [{"role": "system", "content": system_content}]
    """

    def assemble(
        self,
        *,
        review_context: ReviewModeContext | None = None,
        project_summary: str = "",
        doc_excerpt: str = "",
        knowledge_hits: list[Any] | None = None,
        mention_texts: list[tuple[str, str]] | None = None,
        attachment_texts: list[tuple[str, str]] | None = None,
    ) -> str:
        """组装完整 system message 内容。

        组装顺序（恰好一条 system）：
        1. NATIVE_SYSTEM_POLICY
        2. review prompt（如有）
        3. 数据定界块（项目信息 + 文档内容 + 关联知识 + mentions + attachments）
        """
        from app.services.ai_chat.native_engine import (
            CONTEXT_BLOCK_CLOSE,
            CONTEXT_BLOCK_OPEN,
            NATIVE_SYSTEM_POLICY,
            UNTRUSTED_DATA_NOTICE,
        )

        parts: list[str] = [NATIVE_SYSTEM_POLICY.strip()]

        # ② review prompt
        if review_context and review_context.enabled and review_context.prompt_content:
            parts.append("【底稿复核要求】\n" + review_context.prompt_content.strip())

        # ③ 数据定界块
        data_blocks: list[str] = []

        if project_summary:
            data_blocks.append(f"【项目信息】\n{project_summary}")
        if doc_excerpt:
            data_blocks.append(f"【当前文档内容】\n{doc_excerpt}")

        # mentions
        if mention_texts:
            mention_rendered = "\n\n".join(
                f"【引用：{label}】\n{text}" for label, text in mention_texts
            )
            data_blocks.append(f"【用户引用的资源】\n{mention_rendered}")

        # attachments / OCR
        if attachment_texts:
            att_rendered = "\n\n".join(
                f"【附件：{name}】\n{text}" for name, text in attachment_texts
            )
            data_blocks.append(f"【附件内容】\n{att_rendered}")

        # knowledge hits
        if knowledge_hits:
            rendered = "\n\n".join(
                f"【{getattr(h, 'source_name', None) or getattr(h, 'source_type', '知识')}】\n"
                f"{getattr(h, 'content', '')}"
                for h in knowledge_hits[:5]
            )
            data_blocks.append(f"【关联知识】\n{rendered}")

        if data_blocks:
            parts.append(
                "\n".join([
                    UNTRUSTED_DATA_NOTICE,
                    CONTEXT_BLOCK_OPEN,
                    "\n\n".join(data_blocks),
                    CONTEXT_BLOCK_CLOSE,
                ])
            )

        return "\n\n".join(parts)
