"""a17_llm_service — A17-1 章节 LLM 辅助生成服务

提供:
- generate_chapter_draft(db, project_id, chapter_id, context) → AI 建议稿
- generate_kam_description(db, project_id, kam_title, context) → KAM 描述建议稿
- build_cross_chapter_context(target_chapter, all_chapters, budget) → 跨章上下文

设计: 生成结果为「建议稿」，用户编辑后采纳，不自动写入。
RAG: 调用 KnowledgeIndexService.semantic_search 检索同行业知识库，
     embedding 404 时降级 ilike（双保险不崩，per memory.md）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.core import Project

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 跨章节关联矩阵（静态配置）
# 决定 AI 生成时，优先包含哪些关联章节作为上下文
# ---------------------------------------------------------------------------

CHAPTER_AFFINITY: dict[str, list[str]] = {
    "A17-1-ch01": ["A17-1-ch02", "A17-1-ch05"],          # 项目概况 → 审计范围, 了解被审计单位
    "A17-1-ch02": ["A17-1-ch01", "A17-1-ch03"],          # 审计范围 → 概况, 重要性
    "A17-1-ch03": ["A17-1-ch02", "A17-1-ch06"],          # 重要性 → 范围, 风险
    "A17-1-ch04": ["A17-1-ch03", "A17-1-ch06"],          # 审计策略 → 重要性, 风险
    "A17-1-ch05": ["A17-1-ch01", "A17-1-ch09"],          # 了解被审计单位 → 概况, 会计政策
    "A17-1-ch06": ["A17-1-ch14", "A17-1-ch03"],          # 重大错报风险 → 结论, 重要性
    "A17-1-ch07": ["A17-1-ch02", "A17-1-ch14"],          # 集团审计 → 范围, 结论
    "A17-1-ch08": ["A17-1-ch05", "A17-1-ch10"],          # 财报分析 → 了解单位, 持续经营
    "A17-1-ch09": ["A17-1-ch05", "A17-1-ch08"],          # 会计政策 → 了解单位, 财报分析
    "A17-1-ch10": ["A17-1-ch14", "A17-1-ch08"],          # 持续经营 → 结论, 财报分析
    "A17-1-ch11": ["A17-1-ch05", "A17-1-ch15"],          # 关联方 → 了解单位, 舞弊
    "A17-1-ch12": ["A17-1-ch06", "A17-1-ch14"],          # KAM → 风险, 结论
    "A17-1-ch13": ["A17-1-ch14", "A17-1-ch10"],          # 期后事项 → 结论, 持续经营
    "A17-1-ch14": ["A17-1-ch10", "A17-1-ch12", "A17-1-ch15", "A17-1-ch06"],  # 审计结论
    "A17-1-ch15": ["A17-1-ch14", "A17-1-ch06"],          # 舞弊 → 结论, 风险
    "A17-1-ch16": ["A17-1-ch14", "A17-1-ch13"],          # 其他事项 → 结论, 期后
}


def build_cross_chapter_context(
    target_chapter: str,
    all_chapters: dict[str, str],
    budget: int = 4000,
) -> str:
    """构建跨章节上下文

    优先包含 affinity 矩阵中的关联章节，再包含其余非空章节。
    超 budget（字符数）时截断。

    Args:
        target_chapter: 目标章节 ID（不包含在上下文中）
        all_chapters: 所有章节 {chapter_id: content}
        budget: 上下文总字符数上限

    Returns:
        拼接后的跨章上下文字符串
    """
    # 确定优先级顺序：affinity 章节在前，其余按序号排
    affinity_chapters = CHAPTER_AFFINITY.get(target_chapter, [])

    # 收集非空、非目标章节
    non_empty = {
        ch_id: content
        for ch_id, content in all_chapters.items()
        if ch_id != target_chapter and content and content.strip()
    }

    # 按优先级排序
    ordered_ids: list[str] = []
    for ch_id in affinity_chapters:
        if ch_id in non_empty and ch_id not in ordered_ids:
            ordered_ids.append(ch_id)
    # 其余非空章节按序号排
    for ch_id in sorted(non_empty.keys()):
        if ch_id not in ordered_ids:
            ordered_ids.append(ch_id)

    # 按 budget 截断拼接
    parts: list[str] = []
    used = 0
    for ch_id in ordered_ids:
        content = non_empty[ch_id]
        segment = f"[{ch_id}]\n{content.strip()}"
        if used + len(segment) > budget:
            # 截断当前段以填满 budget
            remaining = budget - used
            if remaining > 50:  # 至少保留 50 字符有意义
                parts.append(segment[:remaining])
            break
        parts.append(segment)
        used += len(segment)

    return "\n\n".join(parts)

# ---------------------------------------------------------------------------
# Prompt 模板目录
# ---------------------------------------------------------------------------

_PROMPT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "wp_llm_prompts" / "a17"


def _load_prompt(filename: str) -> str:
    """加载 prompt 模板文件，不存在则返回空字符串"""
    path = _PROMPT_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Prompt 模板文件不存在: %s", path)
    return ""


# 启动时加载（模板不变，只需读一次）
_CHAPTER_SYSTEM = _load_prompt("chapter_draft_system.txt")
_CHAPTER_USER = _load_prompt("chapter_draft_user.txt")
_KAM_SYSTEM = _load_prompt("kam_description_system.txt")
_KAM_USER = _load_prompt("kam_description_user.txt")


# ---------------------------------------------------------------------------
# 章节定义加载
# ---------------------------------------------------------------------------

_CHAPTER_DEFS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "a17_chapter_definitions.json"


def _get_chapter_def(chapter_id: str) -> dict[str, Any] | None:
    """按 chapter_id 查找章节定义"""
    import json
    try:
        defs = json.loads(_CHAPTER_DEFS_PATH.read_text(encoding="utf-8"))
        for ch in defs:
            if ch["id"] == chapter_id:
                return ch
    except Exception as e:
        logger.error("加载章节定义失败: %s", e)
    return None


# ---------------------------------------------------------------------------
# 项目上下文
# ---------------------------------------------------------------------------

async def _get_project_context(db: AsyncSession, project_id: UUID) -> str:
    """构建项目基础上下文字符串"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        return "项目信息不可用"

    parts = []
    if project.name:
        parts.append(f"项目名称: {project.name}")
    if hasattr(project, "client_name") and project.client_name:
        parts.append(f"被审计单位: {project.client_name}")
    if hasattr(project, "industry") and project.industry:
        parts.append(f"行业: {project.industry}")
    if hasattr(project, "audit_period_end") and project.audit_period_end:
        parts.append(f"审计期间截止日: {project.audit_period_end}")
    if hasattr(project, "business_category") and project.business_category:
        parts.append(f"业务类别: {project.business_category}")
    return "\n".join(parts) if parts else "项目基础信息有限"


# ---------------------------------------------------------------------------
# RAG — 知识库检索（非阻塞，失败不影响 LLM 生成）
# ---------------------------------------------------------------------------

async def _retrieve_rag_context(
    db: AsyncSession, project_id: UUID, query: str, *, top_k: int = 5
) -> str:
    """尝试从知识库检索相关文档片段，拼接为 evidence_context。

    embedding 404 / 服务不可用时静默降级（返回空串），LLM 照常生成。
    """
    if not query.strip():
        return ""
    try:
        from app.services.knowledge_index_service import KnowledgeIndexService

        svc = KnowledgeIndexService(db)
        results = await svc.semantic_search(
            project_id, query, top_k=top_k, scope="knowledge_doc"
        )
        if not results:
            return ""
        # 拼接检索结果为上下文文本
        snippets = []
        for r in results[:top_k]:
            title = r.get("title") or r.get("file_name") or ""
            content = r.get("content") or r.get("text") or ""
            if content:
                snippet = f"【{title}】{content[:500]}" if title else content[:500]
                snippets.append(snippet)
        return "\n---\n".join(snippets) if snippets else ""
    except Exception as e:
        logger.debug("RAG 检索降级（非阻塞）: %s", e)
        return ""


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------


class A17LlmService:
    """A17 LLM 辅助生成服务"""

    async def generate_chapter_draft(
        self,
        db: AsyncSession,
        project_id: UUID,
        chapter_id: str,
        *,
        user_hint: str = "",
        mode: str = "generate",
        current_content: str = "",
        all_chapters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """为指定章节生成 AI 建议稿

        Args:
            mode: "generate"（从头生成）或 "polish"（润色改进已有内容）
            current_content: 当前章节内容（polish 模式必需）
            all_chapters: 所有章节内容（用于构建跨章上下文）

        Returns:
            {"draft": str, "model": str, "confidence": float}
            或 {"error": str} 表示不可用
        """
        # 检查 AI 服务是否启用
        if not settings.WP_AI_SERVICE_ENABLED:
            return {"error": "AI 服务未启用（WP_AI_SERVICE_ENABLED=False）"}

        # 1. 加载章节定义
        chapter_def = _get_chapter_def(chapter_id)
        if not chapter_def:
            return {"error": f"未找到章节定义: {chapter_id}"}

        # 2. 构建项目上下文（始终包含 industry + audit_period_end）
        project_context = await _get_project_context(db, project_id)

        # 3. 构建跨章上下文
        cross_chapter_ctx = ""
        if all_chapters:
            cross_chapter_ctx = build_cross_chapter_context(
                target_chapter=chapter_id,
                all_chapters=all_chapters,
                budget=4000,
            )

        # 4. RAG 检索相关知识库内容（非阻塞）
        rag_query = f"{chapter_def.get('title', '')} {project_context.split(chr(10))[2] if len(project_context.split(chr(10))) > 2 else ''}"
        evidence_context = await _retrieve_rag_context(db, project_id, rag_query.strip())

        # 5. 构建 prompt（根据 mode 区分）
        user_prompt = _CHAPTER_USER.replace(
            "{{chapter_title}}", chapter_def.get("title", "")
        ).replace(
            "{{chapter_guidance}}", chapter_def.get("guidance", "")
        ).replace(
            "{{project_context}}", project_context
        ).replace(
            "{{evidence_context}}", evidence_context or "（本版本暂无自动拉取的审计证据）"
        ).replace(
            "{{user_hint}}", user_hint or "无"
        )

        # 追加跨章上下文
        if cross_chapter_ctx:
            user_prompt += f"\n\n## 其他章节上下文（供参考，确保一致性）\n{cross_chapter_ctx}"

        # mode=polish: 追加当前内容 + 润色指令
        if mode == "polish" and current_content:
            user_prompt += (
                f"\n\n## 当前章节已有内容（请在此基础上润色改进）\n{current_content.strip()}"
                "\n\n## 润色要求\n"
                "请保留原有结构和核心判断，优化文字表述、改善逻辑连贯性、"
                "确保与其他章节结论一致、补充遗漏要点。不要从头重写。"
            )

        messages = [
            {"role": "system", "content": _CHAPTER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        # 6. 调用 LLM
        try:
            from app.services.llm_client import chat_completion

            draft = await chat_completion(
                messages=messages,
                temperature=0.4,
                max_tokens=2000,
            )

            # 检测 llm_client 返回的错误标记
            if isinstance(draft, str) and draft.startswith("["):
                return {"error": draft}

            return {
                "draft": draft,
                "model": settings.DEFAULT_CHAT_MODEL,
                "confidence": 0.7,
            }
        except Exception as e:
            logger.error("章节 AI 生成失败 (chapter=%s): %s", chapter_id, e, exc_info=True)
            return {"error": f"AI 生成失败: {e}"}

    async def generate_kam_description(
        self,
        db: AsyncSession,
        project_id: UUID,
        kam_title: str,
        *,
        user_hint: str = "",
        wp_refs: str = "",
    ) -> dict[str, Any]:
        """为 KAM 条目生成三要素描述建议稿

        Returns:
            {"draft": str, "model": str, "confidence": float}
            或 {"error": str} 表示不可用
        """
        # 检查 AI 服务是否启用
        if not settings.WP_AI_SERVICE_ENABLED:
            return {"error": "AI 服务未启用（WP_AI_SERVICE_ENABLED=False）"}

        # 构建项目上下文
        project_context = await _get_project_context(db, project_id)

        # RAG 检索同行业 KAM 案例
        rag_query = f"关键审计事项 {kam_title}"
        evidence_context = await _retrieve_rag_context(db, project_id, rag_query)

        # 构建 prompt
        user_prompt = _KAM_USER.replace(
            "{{kam_title}}", kam_title
        ).replace(
            "{{project_context}}", project_context
        ).replace(
            "{{evidence_context}}", evidence_context or "（暂无同行业 KAM 参考案例）"
        ).replace(
            "{{wp_refs}}", wp_refs or "无"
        ).replace(
            "{{user_hint}}", user_hint or "无"
        )

        messages = [
            {"role": "system", "content": _KAM_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        # 调用 LLM
        try:
            from app.services.llm_client import chat_completion

            draft = await chat_completion(
                messages=messages,
                temperature=0.4,
                max_tokens=2000,
            )

            if isinstance(draft, str) and draft.startswith("["):
                return {"error": draft}

            return {
                "draft": draft,
                "model": settings.DEFAULT_CHAT_MODEL,
                "confidence": 0.7,
            }
        except Exception as e:
            logger.error("KAM AI 生成失败 (kam=%s): %s", kam_title, e, exc_info=True)
            return {"error": f"AI 生成失败: {e}"}


# 模块级单例
a17_llm_service = A17LlmService()
