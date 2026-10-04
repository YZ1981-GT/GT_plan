"""知识库文档正文词法检索 —— 方案 A 的权威检索层。

spec: knowledge-base-retrieval-and-authz-closure（Requirement 2 / 3，design §三）

═══ 为什么需要它 ═══

2026-09-29 真库：``knowledge_index`` 0 行、embedding 服务 502、无 ``embedding_vec`` 列，
索引写路径在当前环境不可能产出一行（design §十一 方案 B 前置清单）。原先所有 RAG 消费方
都只查索引 ⇒ 用户上传的文档**永远**不会被任何 AI 功能引用。本模块直接在
``knowledge_documents``（name / content_text / tags）上检索：文档表是知识正文的唯一真源，
索引只是可选的召回加速。

═══ 纪律 ═══

* **判定只调一处**：可见性一律 ``KnowledgeAccessPolicy.can_retrieve``（单一判定面）。
* **先判权再读正文**：候选 SQL 只取判权三元组与元数据；只对通过判定者读 ``content_text``。
* **范围在截断前生效**：restrict_to 下推进 SQL，不做 top_k 之后的后置过滤。
* **默认只召回最新版本**：同名重传形成的版本链里，被未删除后继指向的旧版不返回
  （restrict_to 点名的文档除外）。
* 本模块只读，不 flush / commit；调用方负责事务（内核在 SAVEPOINT 内调用）。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
from app.services._zh_tokenize import query_terms
from app.services.knowledge_access_policy import (
    KnowledgeAccessPolicy,
    KnowledgeAccessSubject,
    KnowledgeResource,
    KnowledgeRetrievalMode,
)

logger = logging.getLogger(__name__)

__all__ = [
    "SNIPPET_CHARS",
    "CANDIDATE_CAP",
    "DocSearchRequest",
    "DocMeta",
    "DocHit",
    "FolderPath",
    "KnowledgeDocSearch",
    "best_window",
    "escape_like",
    "score_document",
]

#: 片段长度（与 knowledge_index 的分块尺寸一致，chunk_index 语义对齐）
SNIPPET_CHARS = 500
#: 候选行上限（只含判权三元组与元数据，不含正文）；命中即记 WARNING（规模切换点信号）
CANDIDATE_CAP = 1000
#: 读正文的候选数 = top_k × 该系数（其余候选只参与判定，不读正文）
CONTENT_FETCH_FACTOR = 3
#: 每个检索词在正文中最多记录的出现位置数（片段窗口计算用）
_MAX_POSITIONS_PER_TERM = 200
#: 片段起点向左留出的上下文字数
_SNIPPET_LEAD = 50
_CATEGORY_BONUS = 0.15
_BOOST_PER_TERM = 0.05
_BOOST_CAP = 0.15
#: 文件夹路径回溯的最大层数（防御 parent_id 成环；目录树无外键约束）
_MAX_FOLDER_DEPTH = 32


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DocSearchRequest:
    """一次词法检索的全部输入（不可变，便于 PBT 与日志）。"""

    query: str
    mode: KnowledgeRetrievalMode
    subject: KnowledgeAccessSubject | None
    project_id: UUID | None = None
    top_k: int = 10
    #: 文档 ID 与文件夹 ID 的并集；文件夹含全部子孙（Req 2.7）
    restrict_to: tuple[UUID, ...] = ()
    #: 预设分类：该分类根文件夹子树内的文档排序加分（不做硬过滤，Req 2.8）
    category: str | None = None
    #: 上下文词（底稿编码 / 科目名等）：命中加分，不参与召回
    boost_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class DocMeta:
    """文档元数据 + 判权三元组（**不含正文**）。"""

    doc_id: UUID
    folder_id: UUID
    name: str
    file_type: str | None
    file_size: int
    version: int
    tags: tuple[str, ...]
    created_by: UUID | None
    created_at: datetime | None
    updated_at: datetime | None
    document: KnowledgeResource
    folder: KnowledgeResource | None


@dataclass(frozen=True)
class DocHit:
    meta: DocMeta
    score: float
    snippet: str
    chunk_index: int
    matched_terms: tuple[str, ...]


@dataclass(frozen=True)
class FolderPath:
    folder_id: UUID
    name: str
    #: ``/根/…/当前``
    path: str
    #: 根 → 当前（含当前）
    ancestor_ids: tuple[UUID, ...]


# ---------------------------------------------------------------------------
# 纯函数（打分 / 片段 / 转义）
# ---------------------------------------------------------------------------


def escape_like(term: str) -> str:
    """转义 LIKE 通配符，配合 ``ESCAPE '\\'`` 使用（Req 2.2：``%`` 不得匹配全部文档）。"""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _norm(text: str | None) -> str:
    return (text or "").lower()


def score_document(
    terms: Sequence[str],
    name: str,
    content: str,
    *,
    tags: Sequence[str] = (),
    in_category: bool = False,
    boost_terms: Sequence[str] = (),
) -> tuple[float, tuple[str, ...]]:
    """文档相关性分数 ∈ [0, 1] 与命中词（Req 2.5）。

    ``0.7·覆盖率 + 0.2·词频 + 0.1·文件名命中``，再加分类 / 上下文加分，封顶 1。
    覆盖率为主：命中 3/3 个检索词的文档总是排在只命中 1/3 的文档前面。
    """
    if not terms:
        bonus = _CATEGORY_BONUS if in_category else 0.0
        return round(min(1.0, bonus), 4), ()
    # 与正文同样折叠大小写（不依赖调用方已小写）
    terms = tuple(dict.fromkeys(t.lower() for t in terms if t))
    boost_terms = tuple(b.lower() for b in boost_terms if b)
    text = _norm(content)
    nm = _norm(name)
    tg = _norm(" ".join(str(t) for t in tags if t is not None))
    matched = tuple(t for t in terms if t in text or t in nm or t in tg)
    coverage = len(matched) / len(terms)
    tf = sum(math.log1p(text.count(t)) for t in matched)
    tf_norm = min(1.0, tf / (len(terms) * math.log1p(8)))
    name_hit = 0.1 if any(t in nm for t in terms) else 0.0
    score = 0.7 * coverage + 0.2 * tf_norm + name_hit
    if in_category:
        score += _CATEGORY_BONUS
    if boost_terms:
        hits = sum(1 for b in boost_terms if b and (b in text or b in nm))
        score += min(_BOOST_CAP, _BOOST_PER_TERM * hits)
    return round(min(1.0, score), 4), matched


def best_window(
    content: str, terms: Sequence[str], size: int = SNIPPET_CHARS
) -> tuple[str, int]:
    """取命中最密集的 ``size`` 字窗口作为片段，返回 ``(片段, chunk_index)``。

    窗口优先级：不同检索词数最多 → 总出现次数最多 → 位置最靠前（确定性）。
    起点左移 ``_SNIPPET_LEAD`` 字保留上下文，并夹在 ``[0, len-size]`` 内。
    正文未命中（只命中文件名/标签）时取开头。``chunk_index = 起点 // size``。
    """
    if not content:
        return "", 0
    if len(content) <= size:
        return content, 0
    low = content.lower()
    case_insensitive = len(low) == len(content)
    if not case_insensitive:  # 极少数字符 lower 后长度变化 → 退回大小写敏感定位
        low = content
    positions: list[tuple[int, int]] = []
    for idx, term in enumerate(terms):
        if not term or len(term) > size:
            continue
        # 🔴 词也要同样折叠大小写：正文 lower 了而词没 lower，「A」永远定位不到
        #    （PBT 抓到；生产侧 query_terms 已小写，但本函数不能依赖调用方）
        needle = term.lower() if case_insensitive else term
        start = 0
        for _ in range(_MAX_POSITIONS_PER_TERM):
            p = low.find(needle, start)
            if p < 0:
                break
            positions.append((p, idx))
            start = p + 1
    if not positions:
        return content[:size], 0
    positions.sort()

    counter: dict[int, int] = {}
    best_key: tuple[int, int, int] | None = None
    best_start = 0
    j = 0
    for i, (p_i, t_i) in enumerate(positions):
        limit = p_i + size
        while j < len(positions) and positions[j][0] + len(terms[positions[j][1]]) <= limit:
            counter[positions[j][1]] = counter.get(positions[j][1], 0) + 1
            j += 1
        key = (len(counter), sum(counter.values()), -p_i)
        if best_key is None or key > best_key:
            best_key, best_start = key, p_i
        # positions[i] 一定已入窗（检索词长度 ≤ size），移出它再看下一个起点
        counter[t_i] -= 1
        if counter[t_i] == 0:
            del counter[t_i]

    start = max(0, min(best_start - _SNIPPET_LEAD, len(content) - size))
    return content[start : start + size], start // size


def _coerce_uuids(values: Iterable[Any]) -> tuple[UUID, ...]:
    out: list[UUID] = []
    for v in values or ():
        try:
            u = v if isinstance(v, UUID) else UUID(str(v))
        except (ValueError, TypeError, AttributeError):
            continue
        if u not in out:
            out.append(u)
    return tuple(out)


def _ts(value: datetime | None) -> float:
    if value is None:
        return 0.0
    try:
        return value.timestamp()
    except (OverflowError, OSError, ValueError):  # pragma: no cover - 极端时间值
        return 0.0


# ---------------------------------------------------------------------------
# 检索组件
# ---------------------------------------------------------------------------

_D = KnowledgeDocument
_F = KnowledgeFolder

#: 候选/可见性查询的列（**不含** content_text —— Req 2.9 先判权再读正文）
_META_COLUMNS = (
    _D.id,
    _D.folder_id,
    _D.name,
    _D.file_type,
    _D.file_size,
    _D.version,
    _D.tags,
    _D.created_by,
    _D.created_at,
    _D.updated_at,
    _D.access_level,
    _D.project_ids,
    _F.access_level.label("folder_access_level"),
    _F.project_ids.label("folder_project_ids"),
    _F.created_by.label("folder_created_by"),
)


def _meta_from_row(row: Any) -> DocMeta:
    tags_raw = row.tags or ()
    if isinstance(tags_raw, str):
        tags_raw = (tags_raw,)
    return DocMeta(
        doc_id=row.id,
        folder_id=row.folder_id,
        name=row.name or "",
        file_type=row.file_type,
        file_size=int(row.file_size or 0),
        version=int(row.version or 1),
        tags=tuple(str(t) for t in tags_raw if t is not None),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        document=KnowledgeResource.of_row(row.access_level, row.project_ids, row.created_by),
        folder=KnowledgeResource.of_row(
            row.folder_access_level, row.folder_project_ids, row.folder_created_by
        ),
    )


def _not_superseded(always_allow: Sequence[UUID]) -> Any:
    """最新版本条件：没有未删除的后继指向它；``always_allow`` 中的文档豁免（显式点名）。"""
    successor = aliased(KnowledgeDocument)
    cond = ~sa.exists().where(
        successor.previous_version_id == _D.id,
        successor.is_deleted == sa.false(),
    )
    if always_allow:
        cond = sa.or_(cond, _D.id.in_(list(always_allow)))
    return cond


def _validate(req: DocSearchRequest) -> None:
    mode = KnowledgeRetrievalMode(req.mode)
    if mode is KnowledgeRetrievalMode.project and req.project_id is None:
        raise ValueError("project 检索模式必须提供 project_id")
    if mode is not KnowledgeRetrievalMode.project and req.subject is None:
        raise ValueError(f"{mode.value} 检索模式必须提供用户主体")
    if req.top_k <= 0:
        raise ValueError("top_k 必须为正整数")


class KnowledgeDocSearch:
    """知识库文档词法检索 + 可见性解析 + 文件夹路径。只读，不提交事务。"""

    def __init__(self, db: AsyncSession):
        self._db = db

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    async def search(self, req: DocSearchRequest) -> list[DocHit]:
        _validate(req)
        raw_query = (req.query or "").strip()
        terms = query_terms(raw_query)
        if raw_query and not terms:
            # 非空查询但分词后无有效检索词（纯标点 / 通配符 / 停用词）：返回空，
            # 绝不退化成「列表模式」—— 否则查询 "%" 会把最近的全部文档注入 RAG 上下文。
            return []
        explicit_docs, folder_scope = await self.resolve_restriction(req.restrict_to)
        if req.restrict_to and not explicit_docs and not folder_scope:
            return []  # 点名的范围全部不存在：返回空，绝不退化成全库检索
        category_scope = await self._category_scope(req.category)

        metas = await self._candidates(terms, explicit_docs, folder_scope)
        visible = [
            m
            for m in metas
            if KnowledgeAccessPolicy.can_retrieve(
                req.mode, req.subject, req.project_id, m.document, m.folder
            )
        ]
        if not visible:
            return []

        head = visible[: max(req.top_k * CONTENT_FETCH_FACTOR, req.top_k)]
        contents = await self._contents([m.doc_id for m in head])
        boost = tuple(t for raw in req.boost_terms for t in query_terms(raw or ""))

        hits: list[DocHit] = []
        for m in head:
            content = contents.get(m.doc_id) or ""
            score, matched = score_document(
                terms,
                m.name,
                content,
                tags=m.tags,
                in_category=m.folder_id in category_scope,
                boost_terms=boost,
            )
            if terms:
                snippet, chunk_index = best_window(content, matched or terms)
            else:
                snippet, chunk_index = content[:SNIPPET_CHARS], 0
            hits.append(
                DocHit(
                    meta=m,
                    score=score,
                    snippet=snippet,
                    chunk_index=chunk_index,
                    matched_terms=matched,
                )
            )
        hits.sort(key=lambda h: (-h.score, -_ts(h.meta.updated_at), str(h.meta.doc_id)))
        return hits[: req.top_k]

    async def _candidates(
        self,
        terms: Sequence[str],
        explicit_docs: Sequence[UUID],
        folder_scope: Sequence[UUID],
    ) -> list[DocMeta]:
        conds: list[Any] = [_D.is_deleted == sa.false(), _F.is_deleted == sa.false()]
        if explicit_docs or folder_scope:
            scope_parts = []
            if explicit_docs:
                scope_parts.append(_D.id.in_(list(explicit_docs)))
            if folder_scope:
                scope_parts.append(_D.folder_id.in_(list(folder_scope)))
            conds.append(sa.or_(*scope_parts))
        conds.append(_not_superseded(explicit_docs))

        order_by: list[Any]
        columns: list[Any] = list(_META_COLUMNS)
        if terms:
            tags_text = sa.cast(_D.tags, sa.String)
            matchers = []
            for term in terms:
                pattern = f"%{escape_like(term)}%"
                matchers.append(
                    sa.or_(
                        _D.name.ilike(pattern, escape="\\"),
                        _D.content_text.ilike(pattern, escape="\\"),
                        tags_text.ilike(pattern, escape="\\"),
                    )
                )
            conds.append(sa.or_(*matchers))
            hits = sum((sa.case((m, 1), else_=0) for m in matchers), sa.literal(0))
            hits_label = hits.label("term_hits")
            columns.append(hits_label)
            order_by = [hits_label.desc(), _D.updated_at.desc(), _D.id]
        else:
            order_by = [_D.updated_at.desc(), _D.id]

        stmt = (
            sa.select(*columns)
            .select_from(_D)
            .join(_F, _F.id == _D.folder_id)
            .where(*conds)
            .order_by(*order_by)
            .limit(CANDIDATE_CAP + 1)
        )
        rows = (await self._db.execute(stmt)).all()
        if len(rows) > CANDIDATE_CAP:
            logger.warning(
                "[KB 词法检索] 候选超过上限 %d（仅按命中词数取前 %d 条判定）—— "
                "文档规模已到切换点，应启用向量检索或 trigram 索引（spec design §3.2）",
                CANDIDATE_CAP,
                CANDIDATE_CAP,
            )
            rows = rows[:CANDIDATE_CAP]
        return [_meta_from_row(r) for r in rows]

    async def _contents(self, doc_ids: Sequence[UUID]) -> dict[UUID, str]:
        if not doc_ids:
            return {}
        rows = (
            await self._db.execute(
                sa.select(_D.id, _D.content_text).where(_D.id.in_(list(doc_ids)))
            )
        ).all()
        return {r[0]: r[1] or "" for r in rows}

    # ------------------------------------------------------------------
    # 范围解析
    # ------------------------------------------------------------------
    async def resolve_restriction(
        self, restrict_to: Sequence[Any]
    ) -> tuple[tuple[UUID, ...], tuple[UUID, ...]]:
        """restrict_to → (显式文档 ID, 文件夹子树 ID)。ID 先按文件夹识别，其余视为文档。"""
        ids = _coerce_uuids(restrict_to)
        if not ids:
            return (), ()
        folder_roots = {
            r[0]
            for r in (
                await self._db.execute(
                    sa.select(_F.id).where(_F.id.in_(list(ids)), _F.is_deleted == sa.false())
                )
            ).all()
        }
        explicit_docs = tuple(i for i in ids if i not in folder_roots)
        subtree = await self.folder_subtree(folder_roots) if folder_roots else ()
        return explicit_docs, tuple(subtree)

    async def _category_scope(self, category: str | None) -> frozenset[UUID]:
        if not category:
            return frozenset()
        roots = {
            r[0]
            for r in (
                await self._db.execute(
                    sa.select(_F.id).where(_F.category == category, _F.is_deleted == sa.false())
                )
            ).all()
        }
        if not roots:
            return frozenset()  # 未知分类：不加分（Req 2.8）
        return frozenset(await self.folder_subtree(roots))

    async def folder_subtree(self, roots: Iterable[UUID]) -> list[UUID]:
        """未删除文件夹子树（含根）。递归 CTE 用 UNION 去重 —— parent_id 无外键，成环也终止。"""
        root_ids = list(_coerce_uuids(roots))
        if not root_ids:
            return []
        base = (
            sa.select(_F.id.label("id"))
            .where(_F.id.in_(root_ids), _F.is_deleted == sa.false())
            .cte("kb_folder_subtree", recursive=True)
        )
        child = aliased(KnowledgeFolder)
        tree = base.union(
            sa.select(child.id).join(base, child.parent_id == base.c.id).where(
                child.is_deleted == sa.false()
            )
        )
        rows = (await self._db.execute(sa.select(tree.c.id))).all()
        return sorted({r[0] for r in rows}, key=str)

    # ------------------------------------------------------------------
    # 可见性解析（向量命中过滤 / 按 ID 取文档 共用）
    # ------------------------------------------------------------------
    async def visible_documents(
        self,
        doc_ids: Iterable[Any],
        *,
        mode: KnowledgeRetrievalMode,
        subject: KnowledgeAccessSubject | None,
        project_id: UUID | None,
        allow_superseded: Iterable[Any] = (),
    ) -> dict[UUID, DocMeta]:
        """给定文档 ID 中**检索可见**者的元数据（已删除 / 文件夹已删除 / 被取代版本剔除）。"""
        ids = _coerce_uuids(doc_ids)
        if not ids:
            return {}
        explicit = tuple(i for i in _coerce_uuids(allow_superseded) if i in ids)
        stmt = (
            sa.select(*_META_COLUMNS)
            .select_from(_D)
            .join(_F, _F.id == _D.folder_id)
            .where(
                _D.id.in_(list(ids)),
                _D.is_deleted == sa.false(),
                _F.is_deleted == sa.false(),
                _not_superseded(explicit),
            )
        )
        metas = [_meta_from_row(r) for r in (await self._db.execute(stmt)).all()]
        return {
            m.doc_id: m
            for m in metas
            if KnowledgeAccessPolicy.can_retrieve(mode, subject, project_id, m.document, m.folder)
        }

    async def load_contents(self, doc_ids: Sequence[UUID]) -> dict[UUID, str]:
        """读正文（调用方必须已完成判定 —— 只传 ``visible_documents`` 返回的 ID）。"""
        return await self._contents(list(doc_ids))

    # ------------------------------------------------------------------
    # 文件夹路径（引用展示 / 附注 doc_filter 祖先链匹配）
    # ------------------------------------------------------------------
    async def folder_paths(self, folder_ids: Iterable[Any]) -> dict[UUID, FolderPath]:
        """``folder_id → FolderPath``。逐层向上取父级（最多 ``_MAX_FOLDER_DEPTH`` 层，防成环）。"""
        wanted = _coerce_uuids(folder_ids)
        if not wanted:
            return {}
        known: dict[UUID, tuple[str, UUID | None]] = {}
        frontier = set(wanted)
        for _ in range(_MAX_FOLDER_DEPTH):
            need = [f for f in frontier if f not in known]
            if not need:
                break
            rows = (
                await self._db.execute(
                    sa.select(_F.id, _F.name, _F.parent_id).where(_F.id.in_(need))
                )
            ).all()
            for fid, name, parent in rows:
                known[fid] = (name or "", parent)
            frontier = {known[f][1] for f in need if f in known and known[f][1] is not None}

        out: dict[UUID, FolderPath] = {}
        for fid in wanted:
            if fid not in known:
                continue
            chain: list[UUID] = []
            cur: UUID | None = fid
            while cur is not None and cur in known and cur not in chain:
                chain.append(cur)
                if len(chain) >= _MAX_FOLDER_DEPTH:
                    break
                cur = known[cur][1]
            chain.reverse()
            out[fid] = FolderPath(
                folder_id=fid,
                name=known[fid][0],
                path="/" + "/".join(known[c][0] for c in chain),
                ancestor_ids=tuple(chain),
            )
        return out
