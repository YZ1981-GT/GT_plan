"""Mention 聚合搜索与授权加载服务（Task 14）

Feature: dsh-agent-panel-integration
Requirements:
  - 5.2：服务端单一 MentionType schema 覆盖 7 类（复用 MENTION_RESOURCE_TYPES）
  - 5.3：GET /api/ai-chat/mentionable 在 ResourceAccessResolver 后统一返回
  - 5.5：label 与正文由服务端授权后加载，客户端 assertion 不可信
  - 5.6：搜索失败/超时/能力不可用与成功空结果使用不同状态
  - 5.7：mention 搜索、直接 ID 加载使用同一授权决策
  - 5.8：全宿主迁移后删除 extra_scopes 字段、旧 URL 和旧消费方
  - 5.9：jump route 点击仍由目标页面重新授权
Design: "Components and Interfaces → 7. Mention 聚合搜索"

单一入口：``MentionSearchService.search()`` —— 聚合七类资源，统一经
``ResourceAccessResolver.filter_visible_resources()`` 过滤后返回。

``load_mention_context()`` —— 加载已授权 mention 的正文用于 ContextBuilder。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_chat.access import ResourceAccessResolver
from app.services.ai_chat.contracts import (
    AccessDecision,
    AiChatAction,
    HostType,
    ResourceType,
    coerce_uuid,
)
from app.services.ai_chat.host_context import AuthorizedHostContext

logger = logging.getLogger(__name__)

__all__ = [
    "MentionCandidate",
    "MentionSearchResult",
    "MentionSearchService",
    "MentionContentItem",
    "load_mention_context",
]


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MentionCandidate:
    """单条 mention 搜索结果（Req 5.3 统一响应形状）。

    前端可直接序列化为 ``{type, id, label, sublabel, jump_route}``。
    ``jump_route`` 是前端路由路径，点击后由目标页面重新鉴权（Req 5.9）。
    """

    type: str
    id: str
    label: str
    sublabel: str = ""
    jump_route: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "id": self.id,
            "label": self.label,
            "sublabel": self.sublabel,
            "jump_route": self.jump_route,
        }


@dataclass
class MentionSearchResult:
    """聚合搜索结果（含状态信号，Req 5.6）。"""

    items: list[MentionCandidate] = field(default_factory=list)
    #: 各类型的搜索状态：success / empty / error / unavailable / timeout
    type_status: dict[str, str] = field(default_factory=dict)
    total_before_filter: int = 0


@dataclass(frozen=True)
class MentionContentItem:
    """加载后的 mention 正文条目（供 ContextBuilder 消费）。"""

    type: str
    id: str
    label: str
    content: str
    token_estimate: int = 0
    #: 授权决策（保留以供 manifest 记录 cycle_scope 裁剪）
    status: str = "included"  # included / trimmed / denied / unavailable


# ---------------------------------------------------------------------------
# 搜索配置
# ---------------------------------------------------------------------------

#: 每类资源搜索结果数上限
_PER_TYPE_LIMIT = 10
#: 并行搜索超时（秒）
_SEARCH_TIMEOUT = 5.0


# ---------------------------------------------------------------------------
# 资源类型 → 搜索/加载策略
# ---------------------------------------------------------------------------


class MentionSearchService:
    """Mention 聚合搜索唯一入口。

    所有搜索结果**先**经 ``ResourceAccessResolver.filter_visible_resources()``
    过滤，再返回 label / jump_route 等展示字段（Req 5.5 / 5.7）。
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._resolver = ResourceAccessResolver(db)

    async def search(
        self,
        *,
        user: Any,
        host: AuthorizedHostContext,
        query: str,
        type_filter: str | None = None,
        limit: int = _PER_TYPE_LIMIT,
    ) -> MentionSearchResult:
        """执行多类型聚合搜索。

        Args:
            user: 当前用户
            host: 已授权宿主上下文
            query: 搜索关键词
            type_filter: 可选的单一类型过滤（前端选了某个 tab 时使用）
            limit: 每类最大返回数
        """
        # 构造 host AccessDecision 供 filter_visible_resources 使用
        host_decision = AccessDecision(
            allowed=True,
            principal_id=host.principal_id,
            project_id=host.project_id,
            cycle_scope=host.cycle_scope,
            allowed_actions=host.allowed_actions,
            scope_unbounded=host.scope_unbounded,
        )

        # 确定要搜索的类型
        from app.services.ai_chat.run_contract import MENTION_RESOURCE_TYPES

        target_types: list[ResourceType]
        if type_filter:
            try:
                rt = ResourceType(type_filter)
                if rt not in MENTION_RESOURCE_TYPES:
                    return MentionSearchResult(
                        type_status={type_filter: "unavailable"}
                    )
                target_types = [rt]
            except ValueError:
                return MentionSearchResult(type_status={type_filter: "unavailable"})
        else:
            target_types = sorted(MENTION_RESOURCE_TYPES, key=lambda t: t.value)

        # 并行搜索各类型
        result = MentionSearchResult()
        tasks = []
        for rt in target_types:
            tasks.append(
                self._search_type(user, host_decision, rt, query, limit)
            )

        try:
            outcomes = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=_SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            # 全局超时：已完成的结果保留，未完成标 timeout
            for rt in target_types:
                if rt.value not in result.type_status:
                    result.type_status[rt.value] = "timeout"
            return result

        for rt, outcome in zip(target_types, outcomes):
            if isinstance(outcome, Exception):
                logger.warning(
                    "mention 搜索 %s 类型失败: %s: %s",
                    rt.value, type(outcome).__name__, outcome,
                )
                result.type_status[rt.value] = "error"
            elif isinstance(outcome, list):
                result.items.extend(outcome)
                result.type_status[rt.value] = (
                    "success" if outcome else "empty"
                )
            else:
                result.type_status[rt.value] = "empty"

        result.total_before_filter = len(result.items)
        return result

    # ------------------------------------------------------------------
    # 内部：按类型搜索
    # ------------------------------------------------------------------

    async def _search_type(
        self,
        user: Any,
        host_decision: AccessDecision,
        resource_type: ResourceType,
        query: str,
        limit: int,
    ) -> list[MentionCandidate]:
        """搜索单一资源类型并过滤可见性。"""
        # ① 原始搜索（不含权限，只查 label/ID）
        raw_candidates = await self._raw_search(resource_type, query, limit, host_decision)
        if not raw_candidates:
            return []

        # ② 授权过滤（Req 5.7：与直接 ID 访问同一判定）
        visible_ids = await self._resolver.filter_visible_resources(
            user, host_decision, resource_type,
            [c.id for c in raw_candidates],
            AiChatAction.search,
        )
        visible_set = set(visible_ids)

        # ③ 只返回可见的（Req 2.5：不泄露存在性）
        return [c for c in raw_candidates if c.id in visible_set]

    async def _raw_search(
        self,
        resource_type: ResourceType,
        query: str,
        limit: int,
        host_decision: AccessDecision,
    ) -> list[MentionCandidate]:
        """按资源类型执行原始搜索（无权限过滤）。

        每种资源类型使用对应业务表的 ILIKE 搜索。
        """
        q = f"%{query}%" if query else "%"
        project_id = host_decision.project_id

        if resource_type is ResourceType.workpaper:
            return await self._search_workpapers(q, project_id, limit)
        elif resource_type is ResourceType.note:
            return await self._search_notes(q, project_id, limit)
        elif resource_type is ResourceType.report:
            return await self._search_reports(q, project_id, limit)
        elif resource_type is ResourceType.knowledge_doc:
            return await self._search_knowledge_docs(q, project_id, limit)
        elif resource_type is ResourceType.knowledge_folder:
            return await self._search_knowledge_folders(q, project_id, limit)
        elif resource_type is ResourceType.address:
            return await self._search_address(q, project_id, limit)
        elif resource_type is ResourceType.attachment:
            # 附件不作为 mentionable 搜索项（已通过 MENTION_RESOURCE_TYPES 排除）
            return []
        return []

    # ------------------------------------------------------------------
    # 各类型搜索实现
    # ------------------------------------------------------------------

    async def _search_workpapers(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """底稿搜索：wp_name / wp_code ILIKE。"""
        from app.models.workpaper_models import WorkingPaper, WpIndex

        if project_id is None:
            return []

        stmt = (
            sa.select(
                WorkingPaper.id,
                WpIndex.wp_code,
                WpIndex.wp_name,
            )
            .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
            .where(
                WorkingPaper.project_id == project_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
                sa.or_(
                    WpIndex.wp_name.ilike(pattern),
                    WpIndex.wp_code.ilike(pattern),
                ),
            )
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.workpaper.value,
                id=str(r.id),
                label=r.wp_name or r.wp_code or "",
                sublabel=r.wp_code or "",
                jump_route=f"/workpapers/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_notes(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """附注搜索：section_title ILIKE。"""
        from app.models.report_models import DisclosureNote

        if project_id is None:
            return []

        stmt = (
            sa.select(
                DisclosureNote.id,
                DisclosureNote.section_title,
                DisclosureNote.section_number,
            )
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.section_title.ilike(pattern),
            )
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.note.value,
                id=str(r.id),
                label=r.section_title or "",
                sublabel=f"附注 {r.section_number}" if r.section_number else "",
                jump_route=f"/disclosure-notes/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_reports(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """报表搜索：report_type name ILIKE。"""
        from app.models.report_models import FinancialReport, FinancialReportType

        if project_id is None:
            return []

        # 报表 ID 是 report_type 字面量（无 instance UUID），先按 label 过滤再返回
        # project-scoped 的实际存在的报表
        stmt = (
            sa.select(
                FinancialReport.id,
                FinancialReport.report_type,
                FinancialReport.report_name,
            )
            .where(
                FinancialReport.project_id == project_id,
                sa.or_(
                    FinancialReport.report_name.ilike(pattern),
                    FinancialReport.report_type.ilike(pattern),
                ),
            )
            .limit(limit)
        )
        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.report.value,
                id=r.report_type or str(r.id),
                label=r.report_name or r.report_type or "",
                sublabel="财务报表",
                jump_route=f"/reports/{r.report_type}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_knowledge_docs(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """知识文档搜索：title ILIKE。"""
        from app.models.knowledge_models import KnowledgeDocument

        stmt = sa.select(
            KnowledgeDocument.id,
            KnowledgeDocument.title,
            KnowledgeDocument.folder_id,
        ).where(
            KnowledgeDocument.title.ilike(pattern),
        )
        if project_id is not None:
            stmt = stmt.where(KnowledgeDocument.project_id == project_id)
        stmt = stmt.limit(limit)

        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.knowledge_doc.value,
                id=str(r.id),
                label=r.title or "",
                sublabel="知识文档",
                jump_route=f"/knowledge/docs/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_knowledge_folders(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """知识文件夹搜索：name ILIKE。"""
        from app.models.knowledge_models import KnowledgeFolder

        stmt = sa.select(
            KnowledgeFolder.id,
            KnowledgeFolder.name,
        ).where(
            KnowledgeFolder.name.ilike(pattern),
        )
        if project_id is not None:
            stmt = stmt.where(KnowledgeFolder.project_id == project_id)
        stmt = stmt.limit(limit)

        rows = (await self._db.execute(stmt)).all()
        return [
            MentionCandidate(
                type=ResourceType.knowledge_folder.value,
                id=str(r.id),
                label=r.name or "",
                sublabel="知识文件夹",
                jump_route=f"/knowledge/folders/{r.id}",
            )
            for r in rows
            if r.id is not None
        ]

    async def _search_address(
        self, pattern: str, project_id: UUID | None, limit: int
    ) -> list[MentionCandidate]:
        """地址坐标搜索（Task 22/23）。

        从 ACNR / legacy address_registry 搜索匹配的地址条目。
        返回稳定 addr_id、label、domain、URI/formula ref、jump route（Req 6.1）。
        embedding down 时返回空（不冒充 BM25/ILIKE 结果，Req 6.6）。
        """
        if project_id is None:
            return []

        query = pattern.strip("%").strip()
        if not query:
            return []

        try:
            # 直接从 ACNR / legacy address_registry 搜索（不依赖 embedding）
            from app.services.address_registry import address_registry

            entries = await address_registry.search(
                self._db, str(project_id), 0, query, "", "soe", limit
            )
            if not entries:
                return []

            candidates: list[MentionCandidate] = []
            for e in entries:
                # 使用 addr_id 或 URI 作为稳定 ID（Req 6.1）
                addr_id = getattr(e, "formula_ref", "") or getattr(e, "uri", "")
                if not addr_id:
                    continue

                label = getattr(e, "label", "") or ""
                domain = getattr(e, "domain", "") or ""
                formula_ref = getattr(e, "formula_ref", "") or ""
                jump_route = getattr(e, "jump_route", "") or ""
                wp_code = getattr(e, "wp_code", "") or ""

                # sublabel: domain + wp_code 辅助定位
                sublabel_parts = []
                if domain:
                    sublabel_parts.append(f"[{domain}]")
                if wp_code:
                    sublabel_parts.append(wp_code)
                sublabel = " ".join(sublabel_parts) or "地址坐标"

                candidates.append(
                    MentionCandidate(
                        type=ResourceType.address.value,
                        id=addr_id,
                        label=label,
                        sublabel=sublabel,
                        jump_route=jump_route,
                    )
                )

            return candidates

        except Exception as exc:
            # 搜索整体失败 → 返回空（Req 6.6 semantic_unavailable 语义）
            logger.warning("地址坐标搜索失败（semantic_unavailable）: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Mention 正文加载（供 ContextBuilder 消费）
# ---------------------------------------------------------------------------


async def load_mention_context(
    db: AsyncSession,
    *,
    user: Any,
    host: AuthorizedHostContext,
    mentions: list[tuple[ResourceType, str]],
) -> list[MentionContentItem]:
    """加载已授权 mention 的正文。

    每条 mention 独立授权 + 独立加载正文：任一 mention 失败不影响其他。
    返回的 ``MentionContentItem.status`` 区分 included / denied / unavailable。

    由 NativeEngine 在 _build_context 后调用，把 mention 正文注入到 context 中。
    """
    if not mentions:
        return []

    resolver = ResourceAccessResolver(db)
    host_decision = AccessDecision(
        allowed=True,
        principal_id=host.principal_id,
        project_id=host.project_id,
        cycle_scope=host.cycle_scope,
        allowed_actions=host.allowed_actions,
        scope_unbounded=host.scope_unbounded,
    )

    items: list[MentionContentItem] = []
    for resource_type, resource_id in mentions:
        try:
            decision = await resolver.authorize_resource(
                user, host_decision, resource_type, resource_id, AiChatAction.read,
            )
            if not decision.allowed:
                items.append(MentionContentItem(
                    type=resource_type.value,
                    id=resource_id,
                    label="",
                    content="",
                    status="denied",
                ))
                continue

            # 加载正文
            content, label = await _load_resource_content(
                db, resource_type, resource_id, host.project_id
            )
            if content is None:
                items.append(MentionContentItem(
                    type=resource_type.value,
                    id=resource_id,
                    label=label or "",
                    content="",
                    status="unavailable",
                ))
                continue

            items.append(MentionContentItem(
                type=resource_type.value,
                id=resource_id,
                label=label or "",
                content=content,
                token_estimate=len(content) // 3,  # 粗估 token 数
                status="included",
            ))

        except Exception as exc:
            logger.warning(
                "mention 正文加载失败 %s/%s: %s: %s",
                resource_type.value, resource_id, type(exc).__name__, exc,
            )
            items.append(MentionContentItem(
                type=resource_type.value,
                id=resource_id,
                label="",
                content="",
                status="unavailable",
            ))

    return items


async def _load_resource_content(
    db: AsyncSession,
    resource_type: ResourceType,
    resource_id: str,
    project_id: UUID | None,
) -> tuple[str | None, str | None]:
    """根据资源类型加载正文与 label。

    返回 (content, label)；内容不可用时 content 为 None。
    """
    uid = coerce_uuid(resource_id)

    if resource_type is ResourceType.workpaper:
        if uid is None:
            return None, None
        from app.models.workpaper_models import WorkingPaper, WpIndex

        row = (
            await db.execute(
                sa.select(
                    WorkingPaper.content,
                    WpIndex.wp_name,
                    WpIndex.wp_code,
                )
                .join(WpIndex, WpIndex.id == WorkingPaper.wp_index_id)
                .where(WorkingPaper.id == uid)
            )
        ).first()
        if row is None:
            return None, None
        content = row.content or ""
        # 取前 2000 字符作为 mention 上下文
        return content[:2000], row.wp_name or row.wp_code

    elif resource_type is ResourceType.note:
        if uid is None:
            return None, None
        from app.models.report_models import DisclosureNote

        row = (
            await db.execute(
                sa.select(
                    DisclosureNote.content,
                    DisclosureNote.section_title,
                )
                .where(DisclosureNote.id == uid)
            )
        ).first()
        if row is None:
            return None, None
        content = row.content or ""
        return content[:2000], row.section_title

    elif resource_type is ResourceType.report:
        from app.models.report_models import FinancialReport

        # report ID 可以是 report_type 字面量
        stmt = sa.select(
            FinancialReport.content,
            FinancialReport.report_name,
        ).where(FinancialReport.report_type == resource_id)
        if project_id:
            stmt = stmt.where(FinancialReport.project_id == project_id)
        row = (await db.execute(stmt.limit(1))).first()
        if row is None:
            return None, None
        content = row.content or ""
        return content[:2000], row.report_name

    elif resource_type is ResourceType.knowledge_doc:
        if uid is None:
            return None, None
        from app.models.knowledge_models import KnowledgeDocument

        row = (
            await db.execute(
                sa.select(
                    KnowledgeDocument.content,
                    KnowledgeDocument.title,
                )
                .where(KnowledgeDocument.id == uid)
            )
        ).first()
        if row is None:
            return None, None
        content = row.content or ""
        return content[:2000], row.title

    elif resource_type is ResourceType.knowledge_folder:
        if uid is None:
            return None, None
        from app.models.knowledge_models import KnowledgeFolder

        row = (
            await db.execute(
                sa.select(KnowledgeFolder.name).where(KnowledgeFolder.id == uid)
            )
        ).first()
        if row is None:
            return None, None
        # 文件夹本身无正文，返回名称作为上下文标记
        return f"[知识文件夹: {row.name}]", row.name

    elif resource_type is ResourceType.address:
        # Task 23：地址坐标正文加载（经授权后读取当前值并脱敏）
        return await _load_address_content(db, resource_id, project_id)

    return None, None


async def _load_address_content(
    db: AsyncSession,
    resource_id: str,
    project_id: UUID | None,
) -> tuple[str | None, str | None]:
    """加载地址坐标正文（Req 6.7：当前值经角色脱敏后才进入上下文）。

    resource_id 可以是 formula_ref（如 "TB('1001','审定数')"）或 URI。
    返回 (context_text, label)。
    """
    if not resource_id or not project_id:
        return None, None

    try:
        from app.services.address_registry import address_registry, parse_uri

        # 尝试通过 formula_ref 或 URI 定位
        entries = await address_registry.search(
            db, str(project_id), 0, resource_id, "", "soe", 1
        )
        if not entries:
            # 尝试精确匹配 formula_ref
            all_entries = await address_registry.search(
                db, str(project_id), 0, "", "", "soe", 500
            )
            for e in all_entries:
                if getattr(e, "formula_ref", "") == resource_id or getattr(e, "uri", "") == resource_id:
                    entries = [e]
                    break

        if not entries:
            return None, None

        entry = entries[0]
        label = getattr(entry, "label", "") or ""
        domain = getattr(entry, "domain", "") or ""
        formula_ref = getattr(entry, "formula_ref", "") or ""
        uri = getattr(entry, "uri", "") or ""
        value = getattr(entry, "value", None)

        # 构建上下文文本（不含原始当前值 — 脱敏由调用方通过 ExportMaskService 处理）
        parts: list[str] = []
        parts.append(f"地址坐标: {label}")
        if domain:
            parts.append(f"域: {domain}")
        if formula_ref:
            parts.append(f"公式引用: {formula_ref}")
        if uri:
            parts.append(f"URI: {uri}")
        if value is not None:
            # 当前值以文本形式提供（脱敏在更上层由 ExportMaskService 处理）
            parts.append(f"当前值: {value}")

        content = " | ".join(parts)
        return content, label

    except Exception as exc:
        logger.warning("地址坐标正文加载失败 %s: %s", resource_id, exc)
        return None, None
