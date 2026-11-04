"""知识库向量层辅助：向量列门控、向量模型签名与检索结果重排。

从 ``KnowledgeIndexService`` 抽出（该文件已在行数门禁白名单上限附近）。
spec enterprise-embedding-rerank-closure：
- 写入：文本向量列总写；pgvector 列存在时只收 ``INDEX_VECTOR_DIM`` 维（其他维度写 NULL，清掉旧值）；
  每个分块记录生成它的向量模型签名（``llm_runtime.embedding_signature``）。
- 检索：只与同签名分块比较；存在其他签名分块时由调用方决定兜底 / 报「需重建」。
- 重排：权限过滤之后、截断之前按重排分数排序；未启用或失败保持原排序（fail-open）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import KnowledgeIndex

logger = logging.getLogger(__name__)

#: V119 / V263 ``knowledge_index.embedding_vec vector(1024)``；企业向量预设按 MRL 输出同维
INDEX_VECTOR_DIM = 1024
#: 启用重排时各层召回放大倍数与上限（重排模型能把召回靠后的相关段落提上来）
RERANK_RECALL_FACTOR = 3
RERANK_RECALL_CAP = 50
#: 单篇送重排的正文上限（分块 500 字；词法层给的是片段）—— 控制请求体积
RERANK_MAX_DOC_CHARS = 2000


def recall_size(top_k: int, rerank_enabled: bool) -> int:
    """各层召回条数：未启用重排 = top_k；启用 = top_k × 3（上限 50，但不小于 top_k）。"""
    if not rerank_enabled:
        return top_k
    return max(top_k, min(top_k * RERANK_RECALL_FACTOR, RERANK_RECALL_CAP))


def chunk_vector_values(
    vector: list[float], *, pgvector_column: bool, signature: str | None
) -> dict[str, Any]:
    """分块 upsert 的向量相关列。

    ``embedding_vec`` 只在列真实存在时出现在语句里（扩展缺失的库上带它就报 UndefinedColumn）；
    维度不是 ``INDEX_VECTOR_DIM`` 时写 NULL —— 既不让 vector(1024) 拒收整行，也清掉同一分块
    上一个模型留下的旧向量。
    """
    values: dict[str, Any] = {
        "embedding_vector": ",".join(str(v) for v in vector),
        "embedding_model": signature,
    }
    if pgvector_column:
        values["embedding_vec"] = list(vector) if len(vector) == INDEX_VECTOR_DIM else None
    return values


async def has_foreign_signature(
    db: AsyncSession, conditions: list[Any], signature: str
) -> bool:
    """检索范围内是否有其他向量模型（或未记录签名）生成的分块；探测失败按「没有」处理。"""
    try:
        async with db.begin_nested():
            row = (
                await db.execute(
                    select(KnowledgeIndex.id)
                    .where(*conditions, KnowledgeIndex.embedding_model.is_distinct_from(signature))
                    .limit(1)
                )
            ).first()
    except Exception as exc:  # noqa: BLE001 - 只是兜底提示的依据，不能让检索失败
        logger.warning("向量签名覆盖探测失败（按无旧向量处理）：%s: %s", type(exc).__name__, exc)
        return False
    return row is not None


async def resolve_rerank_route(db: AsyncSession, ai_svc: Any) -> list[Any]:
    """在保存点里读重排路由；任何失败（库未迁移、政策全挡）都按未启用处理，不毒化调用方会话。"""
    try:
        async with db.begin_nested():
            return list(await ai_svc.rerank_route())
    except Exception as exc:  # noqa: BLE001 - 重排是可选增强
        logger.warning("重排路由不可用，本次不重排：%s: %s", type(exc).__name__, exc)
        return []


async def rerank_hits(
    ai_svc: Any, route: list[Any], query: str, hits: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """按重排分数从高到低重排命中；失败或无需重排时原样返回。

    重排后 ``score`` 取重排分（跨年合并等按 ``score`` 排序的调用方两侧同口径），
    原召回分保存在 ``recall_score``，重排分另存 ``rerank_score``。
    """
    text = (query or "").strip()
    if not route or not text or len(hits) < 2:
        return hits
    documents = [str(hit.get("content") or "")[:RERANK_MAX_DOC_CHARS] for hit in hits]
    try:
        scores = await ai_svc.rerank(text, documents, route=route)
    except Exception as exc:  # noqa: BLE001 - fail-open：保持召回顺序
        logger.warning("重排失败，保持召回顺序：%s: %s", type(exc).__name__, exc)
        return hits
    by_index = {item.index: item.score for item in scores}
    ranked: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    for index, hit in enumerate(hits):
        if index not in by_index:
            rest.append(hit)
            continue
        item = dict(hit)
        item["recall_score"] = hit.get("score")
        item["rerank_score"] = by_index[index]
        item["score"] = round(by_index[index], 6)
        ranked.append(item)
    ranked.sort(key=lambda item: -float(item["rerank_score"]))
    return ranked + rest
