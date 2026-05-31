"""
TSJ 提示词分段复核服务

按认定章节（存在性/完整性/准确性/权利义务/分类/截止/计价和分摊）拆分 TSJ 提示词，
每段独立 LLM 调用 + 独立 token 预算，超 8000 字符底稿自动走分段。
"""

import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import (
    AIConfirmationStatus,
    AIContent,
    AIContentType,
    ConfidenceLevel,
)
from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# 分段阈值：超过此字符数自动走分段复核
SEGMENTATION_THRESHOLD = 8000

# 每段独立 token 预算
SEGMENT_MAX_TOKENS = 2000

# 认定章节标题正则：匹配 ## 开头的二级标题
_HEADING_PATTERN = re.compile(r"^## (.+)$", re.MULTILINE)


def split_prompt_by_assertions(prompt_text: str) -> list[dict]:
    """
    按 TSJ 提示词的认定章节（## 级标题）拆分。

    常见认定章节：存在性、完整性、准确性、权利义务、分类、截止、计价和分摊

    Args:
        prompt_text: TSJ 提示词全文

    Returns:
        list[dict]: 每项 {"assertion": str, "content": str}
        若无 ## 标题，返回整段作为单一 segment
    """
    matches = list(_HEADING_PATTERN.finditer(prompt_text))

    if not matches:
        return [{"assertion": "全文", "content": prompt_text}]

    segments: list[dict] = []

    # 如果第一个标题前有内容，作为"前言"段
    if matches[0].start() > 0:
        preamble = prompt_text[: matches[0].start()].strip()
        if preamble:
            segments.append({"assertion": "前言", "content": preamble})

    for i, match in enumerate(matches):
        assertion = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(prompt_text)
        content = prompt_text[start:end].strip()
        segments.append({"assertion": assertion, "content": content})

    return segments


async def review_segmented(
    db: AsyncSession,
    project_id: UUID,
    workpaper_id: UUID,
    workpaper_content: str,
    prompt_segments: list[dict],
    ai_service: AIService,
    audit_cycle: str | None = None,
) -> list[AIContent]:
    """
    分段复核：每个认定章节独立 LLM 调用。

    Args:
        db: 数据库会话
        project_id: 项目 ID
        workpaper_id: 底稿 ID
        workpaper_content: 底稿文本内容
        prompt_segments: split_prompt_by_assertions 返回的段列表
        ai_service: AI 服务实例
        audit_cycle: 审计循环名称

    Returns:
        list[AIContent]: 所有段的复核结果
    """
    results: list[AIContent] = []

    for segment in prompt_segments:
        assertion = segment["assertion"]
        segment_prompt = segment["content"]

        prompt = (
            f"## 复核认定：{assertion}\n\n"
            f"{segment_prompt}\n\n"
            f"---\n## 底稿内容\n\n{workpaper_content}\n\n"
            f"请按上述认定框架检查底稿，输出复核发现。"
        )

        try:
            response = await ai_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=SEGMENT_MAX_TOKENS,
            )
            if hasattr(response, "__aiter__"):
                parts = []
                async for part in response:
                    parts.append(part)
                content_text = "".join(parts)
            else:
                content_text = str(response)
        except Exception as e:
            logger.warning(
                f"AI 分段复核失败 [{assertion}]: {e}"
            )
            content_text = f"【{assertion}】AI 复核暂时不可用，请手动复核。"

        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.risk_alert,
            content_text=content_text,
            data_sources={
                "audit_cycle": audit_cycle,
                "assertion": assertion,
                "review_type": "segmented",
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.medium,
            confirmation_status=AIConfirmationStatus.pending,
        )
        db.add(ai_content)
        results.append(ai_content)

    await db.commit()
    for r in results:
        await db.refresh(r)

    logger.info(
        f"分段复核完成: project={project_id}, wp={workpaper_id}, "
        f"segments={len(results)}"
    )
    return results


async def review_with_auto_segment(
    db: AsyncSession,
    project_id: UUID,
    workpaper_id: UUID,
    workpaper_content: str,
    prompt_text: str,
    ai_service: AIService,
    audit_cycle: str | None = None,
) -> list[AIContent]:
    """
    自动判断是否分段复核。

    - 底稿内容 > 8000 字符：按认定章节分段调用
    - 底稿内容 ≤ 8000 字符：单次调用（现有行为）

    Args:
        db: 数据库会话
        project_id: 项目 ID
        workpaper_id: 底稿 ID
        workpaper_content: 底稿文本内容
        prompt_text: TSJ 提示词全文
        ai_service: AI 服务实例
        audit_cycle: 审计循环名称

    Returns:
        list[AIContent]: 复核结果列表
    """
    if len(workpaper_content) > SEGMENTATION_THRESHOLD:
        # 超阈值：分段复核
        segments = split_prompt_by_assertions(prompt_text)
        logger.info(
            f"底稿超 {SEGMENTATION_THRESHOLD} 字符 "
            f"({len(workpaper_content)} chars), 分 {len(segments)} 段复核"
        )
        return await review_segmented(
            db=db,
            project_id=project_id,
            workpaper_id=workpaper_id,
            workpaper_content=workpaper_content,
            prompt_segments=segments,
            ai_service=ai_service,
            audit_cycle=audit_cycle,
        )
    else:
        # 未超阈值：单次调用
        prompt = (
            f"{prompt_text}\n\n"
            f"---\n## 底稿内容\n\n{workpaper_content}\n\n"
            f"请按提示词框架逐项检查底稿，输出复核发现。"
        )

        try:
            response = await ai_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=SEGMENT_MAX_TOKENS,
            )
            if hasattr(response, "__aiter__"):
                parts = []
                async for part in response:
                    parts.append(part)
                content_text = "".join(parts)
            else:
                content_text = str(response)
        except Exception as e:
            logger.warning(f"AI 单次复核失败: {e}")
            content_text = "【底稿复核】AI 复核暂时不可用，请手动复核。"

        ai_content = AIContent(
            project_id=project_id,
            workpaper_id=workpaper_id,
            content_type=AIContentType.risk_alert,
            content_text=content_text,
            data_sources={
                "audit_cycle": audit_cycle,
                "assertion": "全文",
                "review_type": "single",
            },
            generation_model="unknown",
            generation_time=datetime.now(timezone.utc),
            confidence_level=ConfidenceLevel.medium,
            confirmation_status=AIConfirmationStatus.pending,
        )
        db.add(ai_content)
        await db.commit()
        await db.refresh(ai_content)

        logger.info(
            f"单次复核完成: project={project_id}, wp={workpaper_id}"
        )
        return [ai_content]
