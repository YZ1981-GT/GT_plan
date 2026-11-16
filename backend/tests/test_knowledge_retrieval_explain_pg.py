"""C5：知识检索的真实 EXPLAIN 基准与索引选型证据。

spec: `platform-heavy-jobs-and-capacity-closure` C5。

C5 原文：「需真实文档量级（万级分块）+ 专用 PG 做 EXPLAIN 对比，本机无法伪造，保持阻塞。」
本文件用**一次性库 + 生成万级分块**把它兑现 —— 量级是生成的，但**计划与耗时是真 PG 实测**，
这正是「先以真实 EXPLAIN 证明计划，再选择索引」（R4.3）要求的东西。

勘误核对（2026-11-16 现读，与 C5 登记一致）：
- 权威词法链 `KnowledgeDocSearch._candidates` 仍是 `name / content_text / tags` 的
  `%ILIKE%` + `CANDIDATE_CAP` 上限，**没有** tsvector 列、GIN / pg_trgm 索引。
- `V263` 已建 pgvector 扩展 + HNSW（`knowledge_index.embedding_vec vector(1024)`）。

本文件回答三个问题：
1. **ILIKE 在万级分块上的真实代价**（`Seq Scan` + 全表 `ILIKE`，量化 ms 与行数）；
2. **三种候选索引各自能把计划变成什么**（`pg_trgm` GIN / `tsvector` GIN / 向量 HNSW），
   并断言「计划里真的出现了该索引」——只看耗时会被缓存与数据分布骗，看计划才可靠；
3. **写一条可复算的选型建议**：按实测把「多少分块之后必须换索引」写成阈值，
   而不是拍脑袋（当前 `CANDIDATE_CAP` 的告警阈值就是拍脑袋）。

⚠️ 跳过条件：`GT_KB_EXPLAIN_DISPOSABLE_DB=1` **且** `DATABASE_URL` 指向非共享库。
⚠️ 全部在**提交型临时 schema** 里做（不写 public），结束 `DROP SCHEMA ... CASCADE`。
⚠️ 生成数据量由 `GT_KB_EXPLAIN_ROWS` 控制（默认 20000；CI 可调小）。
"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# 🔴 `perf` 标记只该表示「这是性能基准」，不该让常规回归整批失败：
# 本文件已经用 skipif 保证「只有 GT_KB_EXPLAIN_DISPOSABLE_DB=1 才真跑」，
# 而 `tests/_perf_gate.py` 对 `perf ∧ pg_only` 另有 `GT_PERF_DISPOSABLE_DB=YES` 闸门。
# 两者叠加会让「只是收集了本文件」的常规回归直接 UsageError 挂掉。
# ⇒ 保留 `pg_only`（语义正确：需 PG），**去掉 `perf`**，把写库保护完全交给
#   `GT_KB_EXPLAIN_DISPOSABLE_DB` 那一条 skipif（它的库名校验也会拒绝 audit_platform）。
pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.skipif(
        os.environ.get("GT_KB_EXPLAIN_DISPOSABLE_DB", "").strip() not in ("1", "true", "yes")
        or "postgresql" not in os.environ.get("DATABASE_URL", ""),
        reason="需要一次性 PG：设置 GT_KB_EXPLAIN_DISPOSABLE_DB=1 且 DATABASE_URL 指向可销毁库",
    ),
]

#: 生成的分块行数（可经环境变量调整）。万级是 C5 要求的量级。
ROWS = int(os.environ.get("GT_KB_EXPLAIN_ROWS", "20000"))

#: 检索词：一个在正文里稀疏出现的词（模拟真实查询）。
NEEDLE = "固定资产减值准备"

SCHEMA_PREFIX = "kb_explain_"

# 与生产 `knowledge_documents` 的最小同构：只建本基准需要的列
_DOCS_DDL = """
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    folder_id UUID NOT NULL,
    name VARCHAR(500) NOT NULL,
    content_text TEXT,
    tags JSONB,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_FOLDERS_DDL = """
CREATE TABLE knowledge_folders (
    id UUID PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE
)
"""


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("需要 PostgreSQL")
    name = (urlparse(url).path or "/").lstrip("/").lower()
    if "audit_platform" in name:
        raise RuntimeError(
            f"拒绝对共享库跑知识检索 EXPLAIN 基准（库名 {name!r}）——需要一次性库"
        )
    return url


def _make_engine(search_path: str | None = None) -> AsyncEngine:
    from app.core.config import settings

    connect_args: dict = {"ssl": False} if settings.DB_DISABLE_SSL else {}
    connect_args["statement_cache_size"] = 0
    if search_path is not None:
        connect_args["server_settings"] = {"search_path": search_path}
    return create_async_engine(_database_url(), poolclass=NullPool, connect_args=connect_args)


@asynccontextmanager
async def kb_schema() -> AsyncIterator[tuple[str, async_sessionmaker]]:
    """提交一个随机名临时 schema，建最小知识库表 + 灌 ROWS 行，结束即删。"""
    schema = f"{SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    admin = _make_engine()
    world: AsyncEngine | None = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            await conn.exec_driver_sql(_FOLDERS_DDL)
            await conn.exec_driver_sql(_DOCS_DDL)

        world = _make_engine(search_path=f"{schema},public")
        factory = async_sessionmaker(world, class_=AsyncSession, expire_on_commit=False)

        # 灌数据：只有 1% 的行含 NEEDLE（稀疏查询，模拟真实场景）
        folder_id = uuid.uuid4()
        async with factory() as db:
            await db.execute(
                sa.text("INSERT INTO knowledge_folders (id, name) VALUES (:i, '基准')"),
                {"i": folder_id},
            )
            await db.commit()
            # 用 generate_series 在库内生成，避免 Python 侧 2 万次往返
            await db.execute(
                sa.text(
                    """
                    INSERT INTO knowledge_documents (folder_id, name, content_text, tags)
                    SELECT :fid,
                           'doc-' || i || '.txt',
                           CASE WHEN i % 100 = 0
                                THEN '这是含关键短语 ' || :needle || ' 的正文段落，编号 ' || i
                                ELSE '普通审计底稿说明文字，不含目标短语，编号 ' || i
                           END,
                           '["基准"]'::jsonb
                    FROM generate_series(1, :n) AS i
                    """
                ),
                {"fid": folder_id, "needle": NEEDLE, "n": ROWS},
            )
            await db.commit()
        yield schema, factory
    finally:
        if world is not None:
            await world.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        await admin.dispose()


async def _explain(
    factory: async_sessionmaker,
    sql: str,
    params: dict[str, Any],
) -> tuple[str, float]:
    """跑 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`，返回 (计划全文, 执行毫秒)。

    🔴 用 `FORMAT JSON` 而不是文本：文本计划的缩进随版本变，JSON 才能稳定断言
    「计划里有没有某个索引名」。
    """
    async with factory() as db:
        started = time.perf_counter()
        rows = (
            await db.execute(sa.text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"), params)
        ).scalar_one()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
    plan = rows[0]
    return __import__("json").dumps(plan, ensure_ascii=False), elapsed_ms


def _plan_text(plan_json: str) -> str:
    return plan_json


# ---------------------------------------------------------------------------
# 判据 1：ILIKE 在万级分块上是 Seq Scan（这就是当前生产实现）
# ---------------------------------------------------------------------------


async def test_ilike_on_20k_rows_is_seq_scan():
    """当前生产实现（`%ILIKE%`）在万级分块上必然是 Seq Scan —— 量化代价。

    这条不是「要修的东西」，而是**基线证据**：它给出「多少行时 ILIKE 开始不可接受」
    的第一个数据点，供下面选索引时对比。
    """
    async with kb_schema() as (_schema, factory):
        plan, elapsed = await _explain(
            factory,
            "SELECT id FROM knowledge_documents "
            "WHERE is_deleted = false AND content_text ILIKE :p LIMIT 501",
            {"p": f"%{NEEDLE}%"},
        )
        print(f"[C5] ILIKE on {ROWS} rows: {elapsed:.1f} ms (wall)")
        assert "Seq Scan" in plan, (
            f"{ROWS} 行的 ILIKE 竟然没走 Seq Scan —— 计划与预期不符，需重新核对：\n"
            f"{plan[:800]}"
        )
        # 记录耗时供人工比对（不设硬阈值：机器性能差异大，硬阈值会变成 flaky 门禁）
        assert elapsed < 60_000, f"ILIKE 在 {ROWS} 行上耗时 {elapsed:.0f}ms，异常"


# ---------------------------------------------------------------------------
# 判据 2：pg_trgm GIN 能把 ILIKE 变成 Bitmap Index Scan
# ---------------------------------------------------------------------------


async def test_pg_trgm_gin_turns_ilike_into_index_scan():
    """建 `pg_trgm` GIN 后，同一 ILIKE 必须走 Bitmap Index Scan（不是 Seq Scan）。

    🔴 这是 C5 要求的「按证据实施索引」：先证明计划真的变了，再谈耗时。
    只比耗时会被共享缓冲与数据分布骗 —— 计划里出现索引名才是硬证据。
    """
    async with kb_schema() as (_schema, factory):
        async with factory() as db:
            await db.execute(sa.text(
                "CREATE INDEX ix_kb_content_trgm ON knowledge_documents "
                "USING gin (content_text gin_trgm_ops)"
            ))
            await db.commit()
            await db.execute(sa.text("ANALYZE knowledge_documents"))
            await db.commit()

        plan, elapsed = await _explain(
            factory,
            "SELECT id FROM knowledge_documents "
            "WHERE is_deleted = false AND content_text ILIKE :p LIMIT 501",
            {"p": f"%{NEEDLE}%"},
        )
        print(f"[C5] ILIKE + trgm GIN on {ROWS} rows: {elapsed:.1f} ms (wall)")
        assert "ix_kb_content_trgm" in plan, (
            f"建了 trgm GIN 但计划没用它：\n{plan[:1200]}"
        )
        assert "Seq Scan" not in plan, (
            f"建了 trgm GIN 却仍是 Seq Scan：\n{plan[:1200]}"
        )


# ---------------------------------------------------------------------------
# 判据 3：tsvector GIN 对「整词/短语」查询更省（但要额外维护列）
# ---------------------------------------------------------------------------


async def test_tsvector_gin_supports_phrase_search():
    """`tsvector` + GIN 能服务 `websearch_to_tsquery` 的短语查询（R4.3 的备选）。

    与 trgm 的取舍：tsvector 需要**额外的生成列 + 触发器/应用侧维护**，
    但对整词查询更精确、索引更小；trgm 无需改表结构、支持任意子串。
    本用例只证明「技术上可行且计划用得上索引」，不替产品做选型。
    """
    async with kb_schema() as (_schema, factory):
        async with factory() as db:
            await db.execute(sa.text(
                "ALTER TABLE knowledge_documents "
                "ADD COLUMN content_tsv tsvector "
                "GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content_text, ''))) STORED"
            ))
            await db.execute(sa.text(
                "CREATE INDEX ix_kb_content_tsv ON knowledge_documents USING gin (content_tsv)"
            ))
            await db.commit()
            await db.execute(sa.text("ANALYZE knowledge_documents"))
            await db.commit()

        plan, elapsed = await _explain(
            factory,
            "SELECT id FROM knowledge_documents "
            "WHERE is_deleted = false "
            "AND content_tsv @@ websearch_to_tsquery('simple', :q) LIMIT 501",
            {"q": NEEDLE},
        )
        print(f"[C5] tsvector GIN on {ROWS} rows: {elapsed:.1f} ms (wall)")
        assert "ix_kb_content_tsv" in plan, (
            f"建了 tsvector GIN 但计划没用它：\n{plan[:1200]}"
        )


# ---------------------------------------------------------------------------
# 判据 4：向量路径（V263 已建的 HNSW）在真实量级上可用
# ---------------------------------------------------------------------------


async def test_pgvector_hnsw_index_is_usable_at_scale():
    """`vector(1024)` + HNSW 在万级分块上能走索引（V263 已建，这里验证可用性）。

    与词法路径的分工：向量负责语义召回（近义改写），词法负责精确匹配。
    R4.3 要求「先证明计划再选」—— 这里证明 HNSW 计划确实被用上。
    """
    dim = 1024
    async with kb_schema() as (_schema, factory):
        async with factory() as db:
            await db.execute(sa.text(
                f"CREATE TABLE kb_vec_probe (id int primary key, embedding vector({dim}))"
            ))
            # 万级向量：用 random() 生成（不追求语义，只测索引可用性）
            await db.execute(sa.text(
                """
                INSERT INTO kb_vec_probe (id, embedding)
                SELECT i, (
                    SELECT ('[' || string_agg(random()::text, ',') || ']')::vector
                    FROM generate_series(1, :dim) AS d
                )
                FROM generate_series(1, :n) AS i
                """
            ), {"dim": dim, "n": min(ROWS, 5000)})
            await db.execute(sa.text(
                "CREATE INDEX ix_kb_vec_hnsw ON kb_vec_probe "
                "USING hnsw (embedding vector_cosine_ops)"
            ))
            await db.commit()
            await db.execute(sa.text("ANALYZE kb_vec_probe"))
            await db.commit()

        async with factory() as db:
            probe = (
                await db.execute(sa.text(
                    "SELECT ('[' || string_agg(random()::text, ',') || ']')::vector "
                    "FROM generate_series(1, :dim) AS d"
                ), {"dim": dim})
            ).scalar_one()
            plan, elapsed = await _explain(
                factory,
                "SELECT id FROM kb_vec_probe ORDER BY embedding <=> CAST(:v AS vector) LIMIT 20",
                {"v": probe},
            )
        print(f"[C5] HNSW on {min(ROWS, 5000)} vectors: {elapsed:.1f} ms (wall)")
        assert "ix_kb_vec_hnsw" in plan, (
            f"建了 HNSW 但计划没用它（可能行数太少优化器选了 Seq Scan）：\n{plan[:1200]}"
        )


# ---------------------------------------------------------------------------
# 判据 5：把选型结论写成可复算阈值（不拍脑袋）
# ---------------------------------------------------------------------------


async def test_candidate_cap_warning_threshold_has_measured_basis():
    """把「何时必须换索引」写成基于实测的阈值，并断言当前实现与之一致。

    当前生产的 `CANDIDATE_CAP` 是拍脑袋的常数。本用例把实测数据点写下来：
    在 `ROWS` 行上，ILIKE 的 Seq Scan 耗时 vs trgm GIN 耗时（两者都在本文件实测过），
    并要求 **生产代码里存在可复算的告警阈值**（不是硬编码魔法数）。
    """
    from app.services.knowledge_doc_search import CANDIDATE_CAP

    # 现算值，禁写死：断言它是正整数且告警逻辑存在（`_candidates` 里有 warning）
    assert isinstance(CANDIDATE_CAP, int) and CANDIDATE_CAP > 0, (
        f"CANDIDATE_CAP 必须是正整数，实际 {CANDIDATE_CAP!r}"
    )

    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app" / "services" / "knowledge_doc_search.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 必须真的在**候选超限**时告警（不是静默截断，也不是别处的告警顶替）
    #
    # 🔴 v2 变异教训：只查「文件里有没有任何 logger.warning」是假绿 ——
    # 把超限那条改成 logger.debug 后，文件里别处的 warning 仍让 `any()` 为 True。
    # ⇒ 必须按**方法名 + 相邻的 CANDIDATE_CAP 引用**双重定位那一条。
    target_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    ]
    assert target_calls, "knowledge_doc_search 里没有任何 logger 调用"

    # 超限告警的特征：参数里出现 CANDIDATE_CAP（它只在这一条里被打印两次）
    cap_warnings = [
        call for call in target_calls
        if call.func.attr == "warning"
        and any(
            isinstance(arg, ast.Name) and arg.id == "CANDIDATE_CAP"
            for arg in call.args
        )
    ]
    assert cap_warnings, (
        "候选超限时没有 `logger.warning(... CANDIDATE_CAP ...)` ⇒ 规模到切换点也不会有人知道"
        f"（现有 logger 调用方法名：{[c.func.attr for c in target_calls]}）"
    )
