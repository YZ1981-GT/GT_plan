"""参照文档服务 — RAG 辅助生成的文档上下文加载

在生成附注正文/审计报告/底稿审计说明时，自动或手动选择参照文档注入 LLM 上下文。

参照来源：
1. 上年报告/附注/底稿（连续审计场景自动带入）
2. 知识库文档（用户手动选择）
3. 项目内其他文档（如模板、准则）

用法：
    docs = await ReferenceDocService.load_context(
        db, project_id, year,
        source_type="prior_year_notes",  # 或 "knowledge_base" / "prior_year_report"
        section_hint="货币资金",  # 可选，按章节匹配
    )
    result = await chat_completion(messages, context_documents=docs)
"""

from __future__ import annotations

import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ReferenceDocService:
    """参照文档加载服务"""

    @staticmethod
    async def load_prior_year_notes(
        db: AsyncSession,
        project_id: UUID,
        year: int,
        section_hint: str | None = None,
    ) -> list[str]:
        """加载上年附注作为参照（连续审计场景）"""
        from app.models.report_models import DisclosureNote

        prior_year = year - 1
        query = sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == prior_year,
        )
        if section_hint:
            query = query.where(DisclosureNote.note_section == section_hint)

        result = await db.execute(query)
        notes = result.scalars().all()

        docs: list[str] = []
        for note in notes:
            content_parts = [f"【上年附注 {note.note_section} {note.section_title}】"]
            if note.text_content:
                content_parts.append(note.text_content[:2000])
            if note.table_data and isinstance(note.table_data, dict):
                rows = note.table_data.get("rows") or []
                for row in rows[:10]:
                    label = row.get("label", "")
                    values = row.get("values") or []
                    content_parts.append(f"  {label}: {values}")
            docs.append("\n".join(content_parts))

        return docs

    @staticmethod
    async def load_prior_year_report(
        db: AsyncSession,
        project_id: UUID,
        year: int,
    ) -> list[str]:
        """加载上年审计报告作为参照"""
        from app.models.report_models import AuditReport

        prior_year = year - 1
        result = await db.execute(
            sa.select(AuditReport).where(
                AuditReport.project_id == project_id,
                AuditReport.year == prior_year,
            )
        )
        report = result.scalar_one_or_none()
        if not report:
            return []

        docs: list[str] = []
        if report.paragraphs and isinstance(report.paragraphs, dict):
            for section, content in report.paragraphs.items():
                docs.append(f"【上年审计报告 - {section}】\n{content[:1500]}")

        return docs

    @staticmethod
    async def load_prior_year_workpaper(
        db: AsyncSession,
        project_id: UUID,
        year: int,
        wp_code: str | None = None,
    ) -> list[str]:
        """加载上年底稿 parsed_data 作为参照"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        prior_year = year - 1
        query = (
            sa.select(WpIndex.wp_code, WpIndex.wp_name, WorkingPaper.parsed_data)
            .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WpIndex.project_id == project_id,
                WpIndex.is_deleted == sa.false(),
                WorkingPaper.is_deleted == sa.false(),
                WorkingPaper.parsed_data.isnot(None),
            )
        )
        if wp_code:
            query = query.where(WpIndex.wp_code == wp_code)

        result = await db.execute(query.limit(5))
        rows = result.all()

        docs: list[str] = []
        for code, name, parsed in rows:
            content = f"【上年底稿 {code} {name}】\n"
            if isinstance(parsed, dict):
                # 提取审计说明和结论
                explanation = parsed.get("explanation") or parsed.get("audit_explanation") or ""
                conclusion = parsed.get("conclusion") or ""
                if explanation:
                    content += f"审计说明：{explanation[:1000]}\n"
                if conclusion:
                    content += f"结论：{conclusion[:500]}\n"
            docs.append(content)

        return docs

    @staticmethod
    async def load_from_knowledge_base(
        project_id: UUID,
        category: str = "notes",
        keywords: list[str] | None = None,
        max_docs: int = 3,
        db: AsyncSession | None = None,
    ) -> list[str]:
        """从知识库加载参照文档（优先新模型，降级旧服务）"""

        # 优先从新知识库模型（KnowledgeDocument.content_text）检索
        if db:
            try:
                from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
                import sqlalchemy as _sa

                query = (
                    _sa.select(KnowledgeDocument.name, KnowledgeDocument.content_text)
                    .join(KnowledgeFolder, KnowledgeDocument.folder_id == KnowledgeFolder.id)
                    .where(
                        KnowledgeDocument.is_deleted == _sa.false(),
                        KnowledgeDocument.content_text.isnot(None),
                        KnowledgeFolder.is_deleted == _sa.false(),
                    )
                )
                # 按分类过滤
                if category:
                    query = query.where(KnowledgeFolder.category == category)
                # 按关键词过滤（文档名或内容包含关键词）
                if keywords:
                    keyword_filters = []
                    for kw in keywords:
                        keyword_filters.append(KnowledgeDocument.name.ilike(f"%{kw}%"))
                        keyword_filters.append(KnowledgeDocument.content_text.ilike(f"%{kw}%"))
                    query = query.where(_sa.or_(*keyword_filters))

                query = query.limit(max_docs)
                result = await db.execute(query)
                rows = result.all()

                if rows:
                    return [f"【知识库 - {name}】\n{(text or '')[:2000]}" for name, text in rows]
            except Exception as e:
                logger.debug(f"新知识库检索失败，降级到旧服务: {e}")

        # 降级：从旧 KnowledgeService（文件系统）加载
        try:
            from app.services.knowledge_service import KnowledgeService

            docs_list = KnowledgeService.list_documents(category)
            if not docs_list:
                return []

            if keywords:
                filtered = []
                for doc in docs_list:
                    doc_name = doc.get("name", "").lower()
                    if any(kw.lower() in doc_name for kw in keywords):
                        filtered.append(doc)
                docs_list = filtered or docs_list[:max_docs]

            results: list[str] = []
            for doc in docs_list[:max_docs]:
                content = KnowledgeService.get_document_content(category, doc.get("name", ""))
                if content:
                    results.append(f"【知识库 - {doc.get('name', '')}】\n{content[:2000]}")

            return results
        except Exception as e:
            logger.debug(f"知识库加载失败: {e}")
            return []

    @staticmethod
    async def load_context(
        db: AsyncSession,
        project_id: UUID,
        year: int,
        source_type: str = "auto",
        section_hint: str | None = None,
        wp_code: str | None = None,
        knowledge_category: str | None = None,
        knowledge_keywords: list[str] | None = None,
    ) -> list[str]:
        """统一入口：根据 source_type 加载参照文档

        source_type:
        - "auto": 自动选择（优先上年同类文档）
        - "prior_year_notes": 上年附注
        - "prior_year_report": 上年审计报告
        - "prior_year_workpaper": 上年底稿
        - "knowledge_base": 知识库
        - "all": 全部来源（截断到 token 预算）
        """
        docs: list[str] = []

        if source_type in ("auto", "prior_year_notes", "all"):
            notes = await ReferenceDocService.load_prior_year_notes(db, project_id, year, section_hint)
            docs.extend(notes)

        if source_type in ("prior_year_report", "all"):
            report = await ReferenceDocService.load_prior_year_report(db, project_id, year)
            docs.extend(report)

        if source_type in ("prior_year_workpaper", "all"):
            wps = await ReferenceDocService.load_prior_year_workpaper(db, project_id, year, wp_code)
            docs.extend(wps)

        if source_type in ("knowledge_base", "all") or knowledge_category:
            kb = await ReferenceDocService.load_from_knowledge_base(
                project_id,
                category=knowledge_category or "notes",
                keywords=knowledge_keywords,
                db=db,
            )
            docs.extend(kb)

        return docs
