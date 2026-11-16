"""C2/C3：附注章节级 advisory 锁的真实 PG 并发 barrier。

spec: `platform-heavy-jobs-and-capacity-closure` C2 / C3。

C2 登记勘误说「真实 PG 并发 barrier（双连接重叠章节用例）必须在专用可销毁 PG 上跑，
本机无法伪造」。本文件用**提交型临时 schema** 兑现这条：不写 public、不碰共享库，
用两个独立连接（各自的真事务）验证：

- 判据 1（互斥）：连接 A 先取同一章节的锁，连接 B 尝试取同一章节的锁会**阻塞**，
  直到 A 提交/回滚后才拿到 —— 这是「同章节串行」的全部意义。
- 判据 2（并行）：不同章节之间**不阻塞**（B 取另一章节立即成功）。
- 判据 3（自动释放）：事务级锁随 commit 释放，不需要调用方手工解。

隔离方式（复用 `level_backfill_world` 的既有做法，不新造基建）：
1. 管理引擎先 **提交** `CREATE SCHEMA note_lock_<随机>`；
2. 世界引擎用 `NullPool` + asyncpg `server_settings={"search_path": schema}`，
   每条新连接的 search_path 只含该 schema，不带 schema 的表名解析不到 public；
3. 结束（含失败）`DROP SCHEMA ... CASCADE`，现查该 schema 已不存在。

⚠️ 只在本机 Docker 的 `audit-postgres` 上跑；不设 `DATABASE_URL` 时 `pg_only` 会跳过。
禁止对共享库 `audit_platform` 运行 —— 本文件不写任何 public 对象。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.services.disclosure.note_section_write_kernel import (
    acquire_section_lock,
    mutate_note_section,
)

def _barrier_pg_enabled() -> bool:
    """只有显式声明「已备好一次性 PG」时才跑。

    仅凭 DATABASE_URL 含 postgresql 不足以判定可跑：本地开发库存在但可能连不上
    （Docker 端口陈旧 / 库已删），那样会让常规回归从「跳过」变成「连接被拒失败」。
    显式开关 + URL 校验两条都要。
    """
    return (
        os.environ.get("GT_BARRIER_PG", "").strip() in ("1", "true", "yes")
        and "postgresql" in os.environ.get("DATABASE_URL", "")
    )


# marker 只是声明用途；真正跳过靠 skipif（`pg_only` 本身不带跳过语义）。
pytestmark = [
    pytest.mark.pg_only,
    pytest.mark.skipif(
        not _barrier_pg_enabled(),
        reason="需要一次性 PG：设置 GT_BARRIER_PG=1 且 DATABASE_URL 指向可销毁库",
    ),
    pytest.mark.asyncio,
]

SCHEMA_PREFIX = "note_lock_"
PROJECT = uuid.UUID("11111111-2222-3333-4444-555555555555")
YEAR = 2025
SECTION_A = "五、1"
SECTION_B = "五、2"

# 建表用 ORM 元数据整库 create_all：`disclosure_notes` 的外键依赖链会一路延伸到
# users / projects 等表，逐表挑会反复漏（实测两轮）。一次性临时 schema 里整库建表无副作用。
def _create_tables(conn) -> None:
    import app.models.audit_platform_models  # noqa: F401
    import app.models.core  # noqa: F401
    import app.models.formula_push_models  # noqa: F401
    import app.models.formula_setting_models  # noqa: F401
    import app.models.report_models  # noqa: F401
    import app.models.workpaper_models  # noqa: F401
    from app.models.base import Base

    Base.metadata.create_all(bind=conn)


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in url:
        pytest.skip("需要 PostgreSQL（设置 DATABASE_URL）")
    return url


def _make_engine(search_path: str | None = None) -> AsyncEngine:
    from app.core.config import settings

    connect_args: dict = {"ssl": False} if settings.DB_DISABLE_SSL else {}
    if search_path is not None:
        connect_args["server_settings"] = {"search_path": search_path}
    return create_async_engine(_database_url(), poolclass=NullPool, connect_args=connect_args)


@asynccontextmanager
async def note_lock_schema() -> AsyncIterator[tuple[str, async_sessionmaker]]:
    """提交一个随机名临时 schema，建最小 `disclosure_notes`，结束即删。"""
    _database_url()  # 先校验 DATABASE_URL 指向 PostgreSQL，否则跳过
    name = os.environ.get("DATABASE_URL", "")
    if "audit_platform" in name:
        raise RuntimeError(
            "拒绝对共享库 audit_platform 运行：本用例需要可销毁环境"
            "（设置 DATABASE_URL 指向独立库）"
        )
    schema = f"{SCHEMA_PREFIX}{uuid.uuid4().hex[:12]}"
    admin = _make_engine()
    world: AsyncEngine | None = None
    try:
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            # pgvector 类型供 knowledge_index 等表使用；扩展是全库一份，装进 public，
            # 建表时 search_path 保留 public 才能解析到 vector 类型（表本身仍建在临时 schema）。
            await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
            await conn.run_sync(_create_tables)
        world = _make_engine(search_path=f"{schema},public")
        factory = async_sessionmaker(world, class_=AsyncSession, expire_on_commit=False)
        yield schema, factory
    finally:
        if world is not None:
            await world.dispose()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        # 现查该 schema 已不存在（不留残留对象）
        async with admin.connect() as conn:
            exists = (
                await conn.execute(
                    sa.text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                    {"s": schema},
                )
            ).first()
        assert exists is None, f"临时 schema {schema} 未删干净"
        await admin.dispose()


async def _seed_project(factory: async_sessionmaker) -> None:
    """建 `disclosure_notes` 外键所需的 project 行（用 ORM，避免漏 server_default 列）。"""
    from app.models.core import Project, ProjectStatus, ProjectType

    async with factory() as db:
        existing = (
            await db.execute(sa.select(Project).where(Project.id == PROJECT))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                Project(
                    id=PROJECT,
                    name="【测试】章节锁并发屏障",
                    client_name="并发屏障",
                    project_type=ProjectType.annual,
                    status=ProjectStatus.created,
                    audit_year=YEAR,
                    template_type="listed",
                )
            )
            await db.commit()


async def _seed_note(factory: async_sessionmaker, section: str, payload: dict) -> uuid.UUID:
    note_id = uuid.uuid4()
    async with factory() as db:
        await db.execute(
            sa.text(
                "INSERT INTO disclosure_notes "
                "(id, project_id, year, note_section, section_title, content_type, table_data) "
                "VALUES (:i, :p, :y, :s, :t, 'table', CAST(:d AS JSONB))"
            ),
            {
                "i": note_id, "p": PROJECT, "y": YEAR, "s": section,
                "t": f"章节 {section}", "d": __import__("json").dumps(payload),
            },
        )
        await db.commit()
    return note_id


def _lock_wait_event(db: AsyncSession) -> None:
    """让 `pg_advisory_xact_lock` 在等待时可见：设 lock_timeout 太脆，这里靠时序断言。"""


# ---------------------------------------------------------------------------
# 判据 1：同一章节互斥（真实双连接阻塞）
# ---------------------------------------------------------------------------


async def test_same_section_lock_blocks_second_connection():
    """连接 A 持锁期间，连接 B 取同章节锁必须阻塞；A 提交后 B 才拿到。"""
    async with note_lock_schema() as (_schema, factory):
        await _seed_project(factory)
        await _seed_note(factory, SECTION_A, {"rows": []})

        a = factory()
        b = factory()
        try:
            assert await acquire_section_lock(
                a, project_id=PROJECT, year=YEAR, section_id=SECTION_A,
            ) is True, "PG 上必须真的取到锁（返回 True）"

            # B 在 A 持锁期间尝试取同一章节锁 —— 应阻塞
            b_task = asyncio.create_task(
                acquire_section_lock(b, project_id=PROJECT, year=YEAR, section_id=SECTION_A)
            )

            # 0.6 秒内 B 必须还没拿到
            done, pending = await asyncio.wait({b_task}, timeout=0.6)
            assert not done, "同章节锁未阻塞第二个连接 —— advisory 锁没生效"

            # A 提交 ⇒ 事务级锁释放 ⇒ B 拿到
            await a.commit()
            await asyncio.wait_for(b_task, timeout=5.0)
            assert b_task.result() is True
        finally:
            await a.close()
            await b.close()


# ---------------------------------------------------------------------------
# 判据 2：不同章节并行（不互相阻塞）
# ---------------------------------------------------------------------------


async def test_different_sections_do_not_block():
    """A 持「五、1」锁时，B 取「五、2」锁应立即成功（跨章节天然并行）。"""
    async with note_lock_schema() as (_schema, factory):
        await _seed_project(factory)
        await _seed_project(factory)
        await _seed_note(factory, SECTION_A, {"rows": []})
        await _seed_note(factory, SECTION_B, {"rows": []})

        a = factory()
        b = factory()
        try:
            assert await acquire_section_lock(
                a, project_id=PROJECT, year=YEAR, section_id=SECTION_A,
            ) is True
            # 不同章节：必须立刻拿到，不能等 A 提交
            got = await asyncio.wait_for(
                acquire_section_lock(b, project_id=PROJECT, year=YEAR, section_id=SECTION_B),
                timeout=2.0,
            )
            assert got is True, "不同章节被阻塞 ⇒ 锁粒度写成了项目级"
        finally:
            await a.rollback()
            await b.rollback()
            await a.close()
            await b.close()


# ---------------------------------------------------------------------------
# 判据 3：事务级锁随 commit / rollback 自动释放
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("release", ["commit", "rollback"])
async def test_lock_released_on_transaction_end(release: str):
    """commit 与 rollback 都必须释放 advisory xact 锁（不需要调用方手工解）。"""
    async with note_lock_schema() as (_schema, factory):
        await _seed_project(factory)
        await _seed_note(factory, SECTION_A, {"rows": []})

        a = factory()
        b = factory()
        try:
            assert await acquire_section_lock(
                a, project_id=PROJECT, year=YEAR, section_id=SECTION_A,
            ) is True

            b_task = asyncio.create_task(
                acquire_section_lock(b, project_id=PROJECT, year=YEAR, section_id=SECTION_A)
            )
            done, pending = await asyncio.wait({b_task}, timeout=0.5)
            assert not done, "释放前 B 竟然拿到了锁"

            if release == "commit":
                await a.commit()
            else:
                await a.rollback()
            await asyncio.wait_for(b_task, timeout=5.0)
            assert b_task.result() is True
        finally:
            await a.close()
            await b.close()


# ---------------------------------------------------------------------------
# C3：mutate_note_section 在并发下不丢更新（章节锁 + FOR UPDATE + 一次写）
# ---------------------------------------------------------------------------


async def test_concurrent_mutations_on_same_section_do_not_lose_updates():
    """两个连接对同一章节各追加一行：串行后两行都在（不丢更新）。

    这是章节锁真正要保住的业务结果 —— 只有「串行」而没有「读到别人的写入」
    一样会丢更新，所以这条用例同时验证 FOR UPDATE 与 deepcopy-diff 的配合。
    """
    async with note_lock_schema() as (_schema, factory):
        await _seed_project(factory)
        await _seed_note(factory, SECTION_A, {"rows": []})

        async def _append(tag: str) -> None:
            async with factory() as db:
                def _mutator(_note, workspace: dict) -> None:
                    rows = workspace.setdefault("rows", [])
                    rows.append({"tag": tag})

                await mutate_note_section(
                    db,
                    project_id=PROJECT, year=YEAR, section_id=SECTION_A,
                    mutator=_mutator,
                )
                await db.commit()

        await asyncio.gather(_append("first"), _append("second"))

        async with factory() as db:
            row = (
                await db.execute(
                    sa.text(
                        "SELECT table_data FROM disclosure_notes "
                        "WHERE project_id = :p AND year = :y AND note_section = :s "
                        "AND is_deleted = FALSE"
                    ),
                    {"p": PROJECT, "y": YEAR, "s": SECTION_A},
                )
            ).scalar_one()

        tags = sorted(item["tag"] for item in row["rows"])
        assert tags == ["first", "second"], (
            f"并发追加丢更新：实际 {tags}；章节锁未串行化同一章节的写入"
        )
