"""文档级 AI 对话上下文构建器

ContextBuilder 负责组装文档级 AI 对话的 RAG 上下文：
① 当前文档内容（parsed_data / content_text）
② semantic_search 关联知识
③ 项目摘要
④ 用户自定义范围（extra_scopes）

复用 KnowledgeIndexService.semantic_search + AIService。
每条 knowledge_hit 必带可定位 source（文件 id + 段落）— 属性 D3。
token 预算管理：chunk + 相关性排序 + 截断（top_k 最相关段落，非全文）— 属性 D1。

需求: 1.2, 2.1, 2.3, 2.4
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, ProjectUser
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder, KnowledgeAccessLevel
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.knowledge_index_service import KnowledgeIndexService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token 预算配置（D1 属性：ContextBuilder 输出 token_estimate ≤ 配置上限）
# ---------------------------------------------------------------------------

# 默认 token 预算上限（可通过环境变量 DOC_AI_TOKEN_BUDGET 覆盖）
DEFAULT_TOKEN_BUDGET = 8000

# 各部分预算分配比例
DOC_EXCERPT_BUDGET_RATIO = 0.4       # 当前文档内容占 40%
KNOWLEDGE_HITS_BUDGET_RATIO = 0.5    # 关联知识占 50%
PROJECT_SUMMARY_BUDGET_RATIO = 0.1   # 项目摘要占 10%

# chunk 大小（字符数，约 250 token）
CHUNK_SIZE_CHARS = 500


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class SearchHit:
    """单条知识检索命中（含可定位 source — D3 属性）"""

    source_type: str          # 来源类型（如 workpaper / knowledge_doc / trial_balance）
    source_id: str            # 来源文件/记录 UUID
    content: str              # 命中文本片段
    score: float              # 相似度分数
    chunk_index: int | None   # 段落/chunk 索引（可定位）
    source_name: str = ""     # 来源名称（用于前端展示）
    doc_version: int | None = None  # 文档版本号（P2-2.1）
    is_stale: bool = False    # 索引是否过期（P2-2.2）


@dataclass
class Citation:
    """引用来源（可追溯 — D3 属性）

    P2-2.1: 增加 doc_version 和 is_stale 字段，AI 引用必须返回版本信息。
    """

    source_type: str          # 来源类型
    source_id: str            # 来源文件 UUID
    source_name: str          # 来源名称（文件名/底稿编号）
    paragraph_index: int | None  # 段落索引（精确定位）
    excerpt: str = ""         # 引用片段摘要
    doc_version: int | None = None  # 文档版本号（P2-2.1）
    is_stale: bool = False    # 索引是否过期（P2-2.2）


@dataclass
class ChatContext:
    """文档级 AI 对话上下文"""

    doc_excerpt: str                        # 当前文档内容
    knowledge_hits: list[SearchHit]         # 关联知识（含 source 引用）
    project_summary: str                    # 项目摘要
    citations: list[Citation]               # 引用来源（可追溯）
    token_estimate: int                     # token 估算（Task 2 管理预算）


# ---------------------------------------------------------------------------
# ContextBuilder 服务
# ---------------------------------------------------------------------------


class ContextBuilder:
    """文档级 AI 对话上下文构建器

    组装：① 当前文档内容 ② semantic_search 关联知识 ③ 项目摘要 ④ 用户自定义范围。
    token 预算内 chunk + 相关性排序 + 截断（D1：token_estimate ≤ 配置上限）。
    """

    def __init__(self, db: AsyncSession, *, token_budget: int | None = None):
        self._db = db
        self._knowledge_svc = KnowledgeIndexService(db)
        self._token_budget = token_budget or self._load_token_budget()

    async def build(
        self,
        *,
        doc_type: str,
        doc_id: str,
        project_id: UUID,
        year: int,
        query: str,
        user: Any,
        extra_scopes: list[str] | None = None,
    ) -> ChatContext:
        """组装文档级 AI 对话上下文。

        Args:
            doc_type: 文档类型（workpaper / note / report / knowledge_doc / knowledge_folder）
            doc_id: 文档 ID
            project_id: 项目 ID
            year: 审计年度
            query: 用户提问
            user: 当前用户（用于权限过滤）
            extra_scopes: 用户自定义额外知识范围（文件夹 ID 列表）

        Returns:
            ChatContext 包含文档内容、关联知识、项目摘要、引用来源、token 估算
        """
        # ① 当前文档内容
        doc_excerpt = await self._get_doc_content(doc_type, doc_id, project_id)

        # ② semantic_search 关联知识
        knowledge_hits = await self._search_related_knowledge(
            project_id=project_id,
            query=query,
            user=user,
            extra_scopes=extra_scopes,
        )

        # ③ 项目摘要
        project_summary = await self._get_project_summary(project_id)

        # ④ token 预算管理：chunk + 相关性排序 + 截断（D1 属性）
        doc_excerpt, knowledge_hits, project_summary = self._enforce_token_budget(
            doc_excerpt, knowledge_hits, project_summary
        )

        # 构建引用列表（D3：每条 hit 必带可定位 source）
        citations = self._build_citations(knowledge_hits)

        # token 估算（预算截断后，必 ≤ 配置上限）
        token_estimate = self._estimate_tokens(doc_excerpt, knowledge_hits, project_summary)

        return ChatContext(
            doc_excerpt=doc_excerpt,
            knowledge_hits=knowledge_hits,
            project_summary=project_summary,
            citations=citations,
            token_estimate=token_estimate,
        )

    # -------------------------------------------------------------------------
    # Token 预算管理（D1 属性）
    # -------------------------------------------------------------------------

    @staticmethod
    def _load_token_budget() -> int:
        """从环境变量加载 token 预算上限，默认 DEFAULT_TOKEN_BUDGET"""
        import os
        try:
            return int(os.environ.get("DOC_AI_TOKEN_BUDGET", DEFAULT_TOKEN_BUDGET))
        except (ValueError, TypeError):
            return DEFAULT_TOKEN_BUDGET

    @property
    def token_budget(self) -> int:
        """当前配置的 token 预算上限"""
        return self._token_budget

    def _enforce_token_budget(
        self,
        doc_excerpt: str,
        knowledge_hits: list[SearchHit],
        project_summary: str,
    ) -> tuple[str, list[SearchHit], str]:
        """token 预算管理：chunk + 相关性排序 + 截断。

        策略：
        1. 项目摘要：截断到预算的 10%
        2. 文档内容：截断到预算的 40%
        3. 知识 hits：按相关性排序（已排），从低分开始裁剪直到总量 ≤ 预算

        D1 属性保证：返回后 _estimate_tokens() ≤ self._token_budget
        """
        budget = self._token_budget

        # 各部分预算（token 数）
        summary_budget = int(budget * PROJECT_SUMMARY_BUDGET_RATIO)
        doc_budget = int(budget * DOC_EXCERPT_BUDGET_RATIO)
        knowledge_budget = int(budget * KNOWLEDGE_HITS_BUDGET_RATIO)

        # 1) 截断项目摘要
        project_summary = self._truncate_text_to_tokens(project_summary, summary_budget)

        # 2) 截断文档内容（chunk 后取前 N 个 chunk）
        doc_excerpt = self._truncate_text_to_tokens(doc_excerpt, doc_budget)

        # 3) 知识 hits：按相关性排序（高→低），从末尾裁剪
        knowledge_hits = self._truncate_knowledge_hits(knowledge_hits, knowledge_budget)

        # 最终校验：如果总量仍超预算，进一步裁剪知识 hits
        total = self._estimate_tokens(doc_excerpt, knowledge_hits, project_summary)
        if total > budget:
            # 计算剩余可用 token 给知识 hits
            used_by_doc_and_summary = self._count_tokens_text(doc_excerpt) + self._count_tokens_text(project_summary)
            remaining_for_knowledge = max(0, budget - used_by_doc_and_summary)
            knowledge_hits = self._truncate_knowledge_hits(knowledge_hits, remaining_for_knowledge)

        return doc_excerpt, knowledge_hits, project_summary

    def _truncate_text_to_tokens(self, text: str, max_tokens: int) -> str:
        """将文本截断到不超过 max_tokens 的 token 数。

        中文为主文本约 2 字符 ≈ 1 token，截断到 max_tokens * 2 字符。
        """
        if not text:
            return text
        max_chars = max_tokens * 2
        if len(text) <= max_chars:
            return text
        # 截断并加省略标记
        return text[:max_chars] + "…[已截断]"

    def _truncate_knowledge_hits(
        self, hits: list[SearchHit], max_tokens: int
    ) -> list[SearchHit]:
        """按相关性排序保留 top_k hits，总 token 不超 max_tokens。

        hits 已按 score 降序排列（最相关在前）。
        从最相关开始累加，超预算时停止（即从低分端裁剪）。
        单条 hit 内容超过 CHUNK_SIZE_CHARS 时先 chunk 截断。
        """
        if not hits:
            return []

        result: list[SearchHit] = []
        used_tokens = 0

        for hit in hits:
            # 单条 hit chunk 截断
            content = hit.content
            if len(content) > CHUNK_SIZE_CHARS:
                content = content[:CHUNK_SIZE_CHARS]

            hit_tokens = self._count_tokens_text(content)

            if used_tokens + hit_tokens > max_tokens:
                # 预算不够放完整 hit，尝试放部分
                remaining_tokens = max_tokens - used_tokens
                if remaining_tokens > 50:  # 至少 50 token 才值得放
                    truncated_content = content[: remaining_tokens * 2]
                    result.append(SearchHit(
                        source_type=hit.source_type,
                        source_id=hit.source_id,
                        content=truncated_content,
                        score=hit.score,
                        chunk_index=hit.chunk_index,
                        source_name=hit.source_name,
                    ))
                break

            # 放入截断后的 hit
            result.append(SearchHit(
                source_type=hit.source_type,
                source_id=hit.source_id,
                content=content,
                score=hit.score,
                chunk_index=hit.chunk_index,
                source_name=hit.source_name,
            ))
            used_tokens += hit_tokens

        return result

    @staticmethod
    def _count_tokens_text(text: str) -> int:
        """估算单段文本的 token 数（中文约 2 字符/token）"""
        return len(text) // 2 if text else 0

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    async def _get_doc_content(
        self, doc_type: str, doc_id: str, project_id: UUID
    ) -> str:
        """获取当前文档内容（parsed_data / content_text）"""
        doc_uuid = UUID(doc_id)

        if doc_type == "workpaper":
            return await self._get_workpaper_content(doc_uuid, project_id)
        elif doc_type == "knowledge_doc":
            return await self._get_knowledge_doc_content(doc_uuid)
        elif doc_type == "knowledge_folder":
            return await self._get_knowledge_folder_content(doc_uuid)
        elif doc_type in ("note", "report"):
            # 附注/报表：从 parsed_data 获取（结构类似底稿）
            return await self._get_workpaper_content(doc_uuid, project_id)
        else:
            logger.warning(f"未知文档类型: {doc_type}, doc_id={doc_id}")
            return ""

    async def _get_workpaper_content(self, doc_id: UUID, project_id: UUID) -> str:
        """从底稿 parsed_data 提取文本内容"""
        result = await self._db.execute(
            sa.select(WorkingPaper.parsed_data, WpIndex.wp_code, WpIndex.wp_name)
            .join(WpIndex, WorkingPaper.wp_index_id == WpIndex.id)
            .where(
                WorkingPaper.id == doc_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
        row = result.first()
        if not row:
            return ""

        parsed_data, wp_code, wp_name = row
        if not parsed_data:
            return f"[底稿 {wp_code} {wp_name}：暂无解析内容]"

        # 从 parsed_data 提取可读文本
        return self._extract_text_from_parsed_data(parsed_data, wp_code, wp_name)

    async def _get_knowledge_doc_content(self, doc_id: UUID) -> str:
        """从知识库文档获取 content_text"""
        result = await self._db.execute(
            sa.select(KnowledgeDocument.content_text, KnowledgeDocument.name)
            .where(
                KnowledgeDocument.id == doc_id,
                KnowledgeDocument.is_deleted == sa.false(),
            )
        )
        row = result.first()
        if not row:
            return ""

        content_text, name = row
        if not content_text:
            return f"[知识文档 {name}：暂无文本内容]"
        return content_text

    async def _get_knowledge_folder_content(self, folder_id: UUID) -> str:
        """获取文件夹下所有文档的内容摘要（文件夹级对话）"""
        result = await self._db.execute(
            sa.select(KnowledgeDocument.name, KnowledgeDocument.content_text, KnowledgeDocument.content_summary)
            .where(
                KnowledgeDocument.folder_id == folder_id,
                KnowledgeDocument.is_deleted == sa.false(),
            )
            .limit(20)  # 限制文档数量避免超 token
        )
        rows = result.all()
        if not rows:
            return "[文件夹下暂无文档]"

        parts: list[str] = []
        for name, content_text, content_summary in rows:
            # 优先用摘要，其次截取 content_text 前 500 字
            text = content_summary or (content_text[:500] if content_text else "")
            if text:
                parts.append(f"【{name}】\n{text}")
        return "\n\n".join(parts) if parts else "[文件夹下文档暂无文本内容]"

    async def _search_related_knowledge(
        self,
        *,
        project_id: UUID,
        query: str,
        user: Any,
        extra_scopes: list[str] | None = None,
    ) -> list[SearchHit]:
        """调用 semantic_search 检索关联知识（D2：只含 user 有权访问的知识文件）"""
        if not query.strip():
            return []

        try:
            raw_results = await self._knowledge_svc.semantic_search(
                project_id=project_id,
                query=query,
                top_k=10,
            )
        except Exception as e:
            logger.warning(f"semantic_search 失败: {e}")
            raw_results = []

        # 转换为 SearchHit（确保每条都有可定位 source — D3）
        hits: list[SearchHit] = []
        for r in raw_results:
            hits.append(SearchHit(
                source_type=r.get("source_type", "unknown"),
                source_id=r.get("source_id", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                chunk_index=r.get("chunk_index"),
                doc_version=r.get("doc_version"),
                is_stale=r.get("is_stale", False),
            ))

        # extra_scopes：额外检索指定文件夹下的知识文档
        if extra_scopes:
            extra_hits = await self._search_extra_scopes(
                project_id=project_id,
                query=query,
                folder_ids=extra_scopes,
                user=user,
            )
            hits.extend(extra_hits)

        # D2 权限过滤：只保留 user 有权访问的知识文件
        hits = await self._filter_hits_by_permission(hits, user)

        # 按相关性排序
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits

    async def _search_extra_scopes(
        self,
        *,
        project_id: UUID,
        query: str,
        folder_ids: list[str],
        user: Any,
    ) -> list[SearchHit]:
        """检索额外指定文件夹范围的知识文档（D2：权限过滤）"""
        # 获取用户有权访问的项目 ID 列表
        user_project_ids = await self._get_user_project_ids(user)

        hits: list[SearchHit] = []
        for folder_id_str in folder_ids:
            try:
                folder_id = UUID(folder_id_str)
            except (ValueError, TypeError):
                continue

            # 先检查文件夹权限
            folder_result = await self._db.execute(
                sa.select(KnowledgeFolder).where(
                    KnowledgeFolder.id == folder_id,
                    KnowledgeFolder.is_deleted == sa.false(),
                )
            )
            folder = folder_result.scalars().first()
            if not folder:
                continue

            # D2: 检查用户是否有权访问该文件夹
            if not self._check_folder_access(folder, user, user_project_ids):
                continue

            result = await self._db.execute(
                sa.select(
                    KnowledgeDocument.id,
                    KnowledgeDocument.name,
                    KnowledgeDocument.content_text,
                    KnowledgeDocument.access_level,
                    KnowledgeDocument.project_ids,
                    KnowledgeDocument.created_by,
                )
                .where(
                    KnowledgeDocument.folder_id == folder_id,
                    KnowledgeDocument.is_deleted == sa.false(),
                    KnowledgeDocument.content_text.isnot(None),
                )
                .limit(5)
            )
            rows = result.all()
            for doc_id, doc_name, content_text, doc_access_level, doc_project_ids, doc_created_by in rows:
                # D2: 检查文档级权限
                if not self._check_doc_access(
                    doc_access_level, doc_project_ids, doc_created_by,
                    user, user_project_ids,
                ):
                    continue

                if content_text:
                    hits.append(SearchHit(
                        source_type="knowledge_doc",
                        source_id=str(doc_id),
                        content=content_text[:500],
                        score=0.5,  # extra_scope 默认中等相关性
                        chunk_index=0,
                        source_name=doc_name,
                    ))
        return hits

    # -------------------------------------------------------------------------
    # 权限过滤（D2 属性：对话上下文只含 user 有权访问的知识文件）
    # -------------------------------------------------------------------------

    async def _get_user_project_ids(self, user: Any) -> list[UUID]:
        """获取用户所属的项目 ID 列表"""
        if not user or not getattr(user, "id", None):
            return []

        result = await self._db.execute(
            sa.select(ProjectUser.project_id).where(
                ProjectUser.user_id == user.id,
                ProjectUser.is_deleted == sa.false(),
            )
        )
        return [row[0] for row in result.all()]

    async def _filter_hits_by_permission(
        self, hits: list[SearchHit], user: Any
    ) -> list[SearchHit]:
        """D2: 过滤 knowledge_doc 类型的 hits，只保留用户有权访问的文档。

        非 knowledge_doc 类型（如 workpaper/trial_balance）不过滤
        （由路由层 require_project_access 保障）。
        """
        if not hits:
            return []

        # 分离 knowledge_doc hits 和其他类型 hits
        knowledge_hits: list[SearchHit] = []
        other_hits: list[SearchHit] = []
        for hit in hits:
            if hit.source_type == "knowledge_doc" and hit.source_id:
                knowledge_hits.append(hit)
            else:
                other_hits.append(hit)

        if not knowledge_hits:
            return other_hits

        # 批量查询这些知识文档的权限信息
        doc_ids: list[UUID] = []
        for h in knowledge_hits:
            try:
                doc_ids.append(UUID(h.source_id))
            except (ValueError, TypeError):
                pass

        if not doc_ids:
            return other_hits

        # 查询文档权限信息（含文件夹权限用于继承）
        result = await self._db.execute(
            sa.select(
                KnowledgeDocument.id,
                KnowledgeDocument.access_level,
                KnowledgeDocument.project_ids,
                KnowledgeDocument.created_by,
                KnowledgeFolder.access_level.label("folder_access_level"),
                KnowledgeFolder.project_ids.label("folder_project_ids"),
                KnowledgeFolder.created_by.label("folder_created_by"),
            )
            .join(KnowledgeFolder, KnowledgeDocument.folder_id == KnowledgeFolder.id)
            .where(KnowledgeDocument.id.in_(doc_ids))
        )
        doc_permissions = {row[0]: row for row in result.all()}

        # 获取用户项目 ID 列表
        user_project_ids = await self._get_user_project_ids(user)
        user_id = getattr(user, "id", None)

        # 过滤
        allowed_hits: list[SearchHit] = []
        for hit in knowledge_hits:
            try:
                doc_uuid = UUID(hit.source_id)
            except (ValueError, TypeError):
                continue

            perm = doc_permissions.get(doc_uuid)
            if not perm:
                continue  # 文档不存在，跳过

            _doc_id, doc_access, doc_proj_ids, doc_created_by, folder_access, folder_proj_ids, folder_created_by = perm

            # 文档自身权限优先，None 则继承文件夹权限
            effective_access = doc_access if doc_access is not None else folder_access
            effective_proj_ids = doc_proj_ids if doc_access is not None else folder_proj_ids
            effective_created_by = doc_created_by if doc_access is not None else folder_created_by

            if self._user_has_access(
                effective_access, effective_proj_ids, effective_created_by,
                user_id, user_project_ids,
            ):
                allowed_hits.append(hit)

        return other_hits + allowed_hits

    @staticmethod
    def _check_folder_access(
        folder: KnowledgeFolder, user: Any, user_project_ids: list[UUID]
    ) -> bool:
        """检查用户是否有权访问指定文件夹"""
        user_id = getattr(user, "id", None)
        if folder.access_level == KnowledgeAccessLevel.public:
            return True
        elif folder.access_level == KnowledgeAccessLevel.project_group:
            if user_project_ids and folder.project_ids:
                return any(
                    str(pid) in [str(x) for x in folder.project_ids]
                    for pid in user_project_ids
                )
            return False
        elif folder.access_level == KnowledgeAccessLevel.private:
            return user_id is not None and folder.created_by == user_id
        return False

    @staticmethod
    def _check_doc_access(
        doc_access_level: KnowledgeAccessLevel | None,
        doc_project_ids: list | None,
        doc_created_by: UUID | None,
        user: Any,
        user_project_ids: list[UUID],
    ) -> bool:
        """检查用户是否有权访问指定文档（文档级权限）"""
        if doc_access_level is None:
            # 继承文件夹权限 — 文件夹已在上层检查通过
            return True
        return ContextBuilder._user_has_access(
            doc_access_level, doc_project_ids, doc_created_by,
            getattr(user, "id", None), user_project_ids,
        )

    @staticmethod
    def _user_has_access(
        access_level: KnowledgeAccessLevel | None,
        project_ids: list | None,
        created_by: UUID | None,
        user_id: UUID | None,
        user_project_ids: list[UUID],
    ) -> bool:
        """通用权限判断：用户是否有权访问指定资源"""
        if access_level is None or access_level == KnowledgeAccessLevel.public:
            return True
        elif access_level == KnowledgeAccessLevel.project_group:
            if user_project_ids and project_ids:
                return any(
                    str(pid) in [str(x) for x in project_ids]
                    for pid in user_project_ids
                )
            return False
        elif access_level == KnowledgeAccessLevel.private:
            return user_id is not None and created_by == user_id
        return False

    async def _get_project_summary(self, project_id: UUID) -> str:
        """获取项目摘要信息"""
        result = await self._db.execute(
            sa.select(Project.name, Project.client_name, Project.audit_period_start, Project.audit_period_end)
            .where(Project.id == project_id)
        )
        row = result.first()
        if not row:
            return ""

        name, client_name, period_start, period_end = row
        period_str = ""
        if period_start and period_end:
            period_str = f"，审计期间 {period_start} 至 {period_end}"

        return f"项目：{name}，客户：{client_name}{period_str}"

    def _build_citations(self, knowledge_hits: list[SearchHit]) -> list[Citation]:
        """从 knowledge_hits 构建引用列表（D3：每条必带可定位 source）

        P2-2.1: 每条 citation 包含 doc_version 和 is_stale 信息。
        """
        citations: list[Citation] = []
        seen: set[tuple[str, str, int | None]] = set()

        for hit in knowledge_hits:
            key = (hit.source_type, hit.source_id, hit.chunk_index)
            if key in seen:
                continue
            seen.add(key)

            citations.append(Citation(
                source_type=hit.source_type,
                source_id=hit.source_id,
                source_name=hit.source_name or f"{hit.source_type}:{hit.source_id[:8]}",
                paragraph_index=hit.chunk_index,
                excerpt=hit.content[:100] if hit.content else "",
                doc_version=hit.doc_version,
                is_stale=hit.is_stale,
            ))

        return citations

    def _estimate_tokens(
        self,
        doc_excerpt: str,
        knowledge_hits: list[SearchHit],
        project_summary: str,
    ) -> int:
        """估算 token 数（中文约 1.5 字/token，英文约 4 字符/token，取平均 ~2 字符/token）"""
        total_chars = len(doc_excerpt) + len(project_summary)
        for hit in knowledge_hits:
            total_chars += len(hit.content)
        # 中文为主的文本，约 2 字符 ≈ 1 token
        return total_chars // 2

    @staticmethod
    def _extract_text_from_parsed_data(
        parsed_data: dict, wp_code: str, wp_name: str
    ) -> str:
        """从底稿 parsed_data 提取可读文本"""
        parts: list[str] = [f"[底稿 {wp_code} {wp_name}]"]

        # parsed_data 常见结构：html_data / cells / content_text
        if "content_text" in parsed_data:
            parts.append(parsed_data["content_text"])
        elif "html_data" in parsed_data:
            # html_data 是 {sheet_name: html_string} 结构
            for sheet_name, html_content in parsed_data["html_data"].items():
                if isinstance(html_content, str) and html_content.strip():
                    # 简单去 HTML 标签提取文本
                    text = _strip_html_tags(html_content)
                    if text:
                        parts.append(f"[{sheet_name}]\n{text[:1000]}")
        elif "cells" in parsed_data:
            # cells 结构：提取有值的单元格
            cells = parsed_data["cells"]
            if isinstance(cells, dict):
                for sheet_name, sheet_cells in cells.items():
                    cell_texts = _extract_cell_texts(sheet_cells)
                    if cell_texts:
                        parts.append(f"[{sheet_name}]\n{cell_texts[:1000]}")

        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _strip_html_tags(html: str) -> str:
    """简单去除 HTML 标签（不引入额外依赖）"""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_cell_texts(sheet_cells: Any) -> str:
    """从 cells 结构提取文本"""
    if isinstance(sheet_cells, list):
        texts: list[str] = []
        for row in sheet_cells:
            if isinstance(row, list):
                row_texts = [str(c) for c in row if c is not None and str(c).strip()]
                if row_texts:
                    texts.append(" | ".join(row_texts))
            elif isinstance(row, dict):
                val = row.get("v") or row.get("value") or ""
                if val:
                    texts.append(str(val))
        return "\n".join(texts[:50])  # 限制行数
    elif isinstance(sheet_cells, dict):
        texts = []
        for cell_ref, cell_data in list(sheet_cells.items())[:100]:
            if isinstance(cell_data, dict):
                val = cell_data.get("v") or cell_data.get("value") or ""
            else:
                val = cell_data
            if val is not None and str(val).strip():
                texts.append(f"{cell_ref}: {val}")
        return "\n".join(texts[:50])
    return ""
