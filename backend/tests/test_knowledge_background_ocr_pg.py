"""真实 PostgreSQL：知识库后台 OCR 的迁移往返与并发认领（spec dsh-kb-ocr-local-first-routing Task 7 / 8 / 11）。

为什么必须真库：
- V198 / R198 是 PG DDL（CHECK 约束、部分索引）；
- 多 worker 不重复认领靠 ``FOR UPDATE SKIP LOCKED``，SQLite 没有行锁，测不到。

隔离：建一个临时 schema（并发用例需要两个连接都看到表，所以要提交），连接一律
``search_path`` 只指向它；结束时 ``DROP SCHEMA ... CASCADE``，不碰 public 下的正式表。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.pg_only

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_COLUMNS = {"ocr_status", "ocr_attempts", "ocr_error", "ocr_due_at"}


def _engine(schema: str | None = None, *, lock_timeout: str | None = None):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise RuntimeError("本用例必须真实 PostgreSQL")
    args: dict = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    server_settings = {}
    if schema:
        server_settings["search_path"] = schema
    if lock_timeout:
        # 变异兜底：若认领语句丢了 SKIP LOCKED，第二个会话会等锁 —— 让它报错而不是挂死
        server_settings["lock_timeout"] = lock_timeout
    if server_settings:
        args["server_settings"] = server_settings
    return create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=args)


async def _run_file(conn, name: str) -> None:
    from app.core.migration_runner import MigrationRunner

    for statement in MigrationRunner._split_sql_statements((MIGRATIONS / name).read_text(encoding="utf-8")):
        await conn.exec_driver_sql(statement)


async def _create_schema(schema: str) -> None:
    from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder

    admin = _engine()
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            await conn.exec_driver_sql("CREATE TABLE users (id uuid PRIMARY KEY)")
            await conn.exec_driver_sql(
                "CREATE TYPE knowledge_access_level AS ENUM ('public', 'project_group', 'private')"
            )
            # 类型由迁移拥有（上一句）。模型里写的 sa.Enum(..., create_type=False) 对通用 sa.Enum
            # 不生效（该参数只属于 postgresql.ENUM，被静默丢弃），table.create() 仍会发 CREATE TYPE，
            # 两张表各发一次 ⇒ 必须 checkfirst=True 让它先查 pg_type（search_path 只含临时 schema）。
            await conn.run_sync(lambda c: KnowledgeFolder.__table__.create(c, checkfirst=True))
            await conn.run_sync(lambda c: KnowledgeDocument.__table__.create(c, checkfirst=True))
    finally:
        await admin.dispose()


async def _drop_schema(schema: str) -> None:
    admin = _engine()
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    finally:
        await admin.dispose()


async def _columns(conn, schema: str) -> set[str]:
    rows = await conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = :s AND table_name = 'knowledge_documents' AND column_name LIKE 'ocr_%'"
    ), {"s": schema})
    return {r[0] for r in rows}


async def _index_def(conn, schema: str) -> str | None:
    return (await conn.execute(sa.text(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = :s AND indexname = 'ix_knowledge_documents_ocr_queue'"
    ), {"s": schema})).scalar_one_or_none()


async def _migration_roundtrip(schema: str) -> dict:
    out: dict = {}
    engine = _engine(schema)
    try:
        async with engine.begin() as conn:
            folder = uuid.uuid4()
            await conn.execute(sa.text("INSERT INTO knowledge_folders (id, name) VALUES (:id, '夹')"), {"id": folder})
            await conn.execute(sa.text(
                "INSERT INTO knowledge_documents (id, folder_id, name, content_text, ocr_status) "
                "VALUES (:id, :f, 'a.pdf', '已识别正文', 'done')"
            ), {"id": uuid.uuid4(), "f": folder})
            out["orm_columns"] = await _columns(conn, schema)
            out["orm_index"] = await _index_def(conn, schema)
            out["orm_rejects_bad_status"] = await _rejects_bad_status(conn)
            await _run_file(conn, "R198__knowledge_documents_background_ocr.sql")
            out["after_rollback"] = await _columns(conn, schema)
            out["index_after_rollback"] = await _index_def(conn, schema)
            out["text_kept"] = (await conn.execute(sa.text("SELECT content_text FROM knowledge_documents"))).scalar_one()
            await _run_file(conn, "V198__knowledge_documents_background_ocr.sql")
            await _run_file(conn, "V198__knowledge_documents_background_ocr.sql")  # 幂等：再跑一次不报错
            out["after_upgrade"] = await _columns(conn, schema)
            out["index_after_upgrade"] = await _index_def(conn, schema)
            out["attempts_default"] = (await conn.execute(sa.text("SELECT ocr_attempts FROM knowledge_documents"))).scalar_one()
            out["bad_status_rejected"] = await _rejects_bad_status(conn)
    finally:
        await engine.dispose()
    return out


async def _rejects_bad_status(conn) -> bool:
    try:
        async with conn.begin_nested():
            await conn.execute(sa.text("UPDATE knowledge_documents SET ocr_status = 'bogus'"))
        return False
    except sa.exc.IntegrityError:
        return True


async def _concurrent_claims(schema: str) -> dict:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.services import knowledge_ocr_service as S

    out: dict = {}
    holder_engine = _engine(schema)
    claimer_engine = _engine(schema, lock_timeout="3s")
    factory = async_sessionmaker(claimer_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        folder = uuid.uuid4()
        ids = [uuid.uuid4(), uuid.uuid4()]
        async with holder_engine.begin() as conn:
            await conn.execute(sa.text("INSERT INTO knowledge_folders (id, name) VALUES (:id, '夹')"), {"id": folder})
            for i, doc_id in enumerate(ids):
                await conn.execute(sa.text(
                    "INSERT INTO knowledge_documents (id, folder_id, name, storage_path, ocr_status, created_at) "
                    "VALUES (:id, :f, :n, 'x.pdf', 'pending', now() - make_interval(secs => :age))"
                ), {"id": doc_id, "f": folder, "n": f"{i}.pdf", "age": 10 - i})
        # 会话 A：拿走排在最前的一行的行锁并保持事务不提交（= 另一个 worker 正在认领它）
        async with holder_engine.connect() as holder:
            trans = await holder.begin()
            locked = (await holder.execute(sa.text(
                "SELECT id FROM knowledge_documents WHERE ocr_status = 'pending' "
                "ORDER BY ocr_due_at ASC NULLS FIRST, created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED"
            ))).scalar_one()
            out["locked"] = locked
            async with factory() as db:
                claim = await S.claim_next(db)
            out["claimed"] = claim.doc_id if claim else None
            await trans.rollback()
        # 锁释放后再认领：拿到剩下那一行；之后没有可认领的
        async with factory() as db:
            later = await S.claim_next(db)
        out["later"] = later.doc_id if later else None
        async with factory() as db:
            out["none_left"] = await S.claim_next(db)
        out["ids"] = ids

        # 围栏：租约过期被重新认领后，旧结果不得覆盖
        async with holder_engine.begin() as conn:
            await conn.execute(sa.text(
                "UPDATE knowledge_documents SET ocr_due_at = now() - interval '1 second' WHERE id = :id"
            ), {"id": out["claimed"]})
        async with factory() as db:
            reclaimed = await S.claim_next(db)

        async def _recognize(_path):
            return {"text": "新结果"}

        stale = S.OcrClaim(out["claimed"], 1, "x.pdf", "1.pdf")
        out["stale_result"] = await S.process(stale, session_factory=factory, recognize=_recognize)
        out["fresh_attempt"] = reclaimed.attempt
        out["fresh_result"] = await S.process(reclaimed, session_factory=factory, recognize=_recognize)
    finally:
        await holder_engine.dispose()
        await claimer_engine.dispose()
    return out


def _run(coro_fn):
    schema = f"kiro_kbocr_{uuid.uuid4().hex[:10]}"

    async def _main():
        await _create_schema(schema)
        try:
            return await coro_fn(schema)
        finally:
            await _drop_schema(schema)

    return asyncio.run(_main())


def test_v198_r198_roundtrip_on_real_postgres():
    out = _run(_migration_roundtrip)
    assert out["orm_columns"] == _COLUMNS  # ORM 形态与 V198 一致
    assert out["orm_index"] and "WHERE" in out["orm_index"]
    assert out["orm_rejects_bad_status"] is True  # ORM 也带同一 CHECK（create_all 建的测试库同样拦）
    assert out["after_rollback"] == set() and out["index_after_rollback"] is None
    assert out["text_kept"] == "已识别正文"  # 回滚只去状态列，已写回的正文保留
    assert out["after_upgrade"] == _COLUMNS
    assert "ocr_due_at" in out["index_after_upgrade"]
    assert "'pending'" in out["index_after_upgrade"] and "'running'" in out["index_after_upgrade"]
    assert out["attempts_default"] == 0
    assert out["bad_status_rejected"] is True


def test_claim_skips_rows_locked_by_another_worker_and_fences_stale_results(monkeypatch):
    from app.services import knowledge_ocr_service as S

    async def _no_refresh(_factory, _doc_id):
        return None

    monkeypatch.setattr(S, "_refresh_index", _no_refresh)
    out = _run(_concurrent_claims)
    assert out["locked"] == out["ids"][0]
    assert out["claimed"] == out["ids"][1], "认领没有跳过被别的 worker 锁住的行"
    assert out["later"] == out["ids"][0]
    assert out["none_left"] is None
    assert out["stale_result"] == "stale"
    assert out["fresh_attempt"] == 2 and out["fresh_result"] == "done"
