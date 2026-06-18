"""a17_llm_service — A17-1 章节 LLM 辅助生成服务

提供:
- generate_chapter_draft(db, project_id, chapter_id, context) → AI 建议稿
- generate_kam_description(db, project_id, kam_title, context) → KAM 描述建议稿

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
    ) -> dict[str, Any]:
        """为指定章节生成 AI 建议稿

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

        # 2. 构建项目上下文
        project_context = await _get_project_context(db, project_id)

        # 3. RAG 检索相关知识库内容（非阻塞）
        rag_query = f"{chapter_def.get('title', '')} {project_context.split(chr(10))[2] if len(project_context.split(chr(10))) > 2 else ''}"
        evidence_context = await _retrieve_rag_context(db, project_id, rag_query.strip())

        # 4. 构建 prompt
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

        messages = [
            {"role": "system", "content": _CHAPTER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]

        # 5. 调用 LLM
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
