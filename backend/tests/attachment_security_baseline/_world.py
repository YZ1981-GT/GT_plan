"""spec attachment-security-baseline 的端点测试夹具（不是测试文件，不被收集）。

在 ``tests.authz_world`` 的六张表之外，再建附件 / 底稿 / 函证 / 证据链接 / 溯源 / 治理版本 / 法定保全这些表，
复用 ``AuthzWorld`` 的身份工厂与客户端（只替换 ``get_current_user`` 与 ``get_db``，判定链真实执行）。

- SQLite 版 ``sqlite_attachment_world``：大多数用例。
- PG 版 ``pg_attachment_world``（``pg_only``）：法定保全的判定用裸 SQL 按 ``str(uuid)`` 绑定，SQLite 上存的是
  32 位十六进制、恒不命中，只能在真 PG 上测。做法同 ``authz_world.pg_world``：同一事务内建临时 schema、
  ``search_path`` 只含它，会话以保存点加入，结束整体回滚。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable, Table

import app.models  # noqa: F401  注册全部模型（外键目标解析需要）
from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.confirmation_models import Confirmation, ConfirmationActionLog, ConfirmationAttachmentLink
from app.models.core import Project
from app.models.evidence_governance_models import AttachmentVersion, LegalHold, LegalHoldScope
from app.models.wp_optimization_models import EvidenceLink
from app.models.workpaper_models import WorkingPaper, WpIndex
from tests.authz_world import WORLD_TABLES, AuthzWorld, _index_statement, create_world_schema, pg_engine

EXTRA_TABLES: tuple[Table, ...] = (
    WpIndex.__table__, WorkingPaper.__table__, Attachment.__table__, AttachmentWorkingPaper.__table__,
    Confirmation.__table__, ConfirmationAttachmentLink.__table__, ConfirmationActionLog.__table__,
    EvidenceLink.__table__, AttachmentLineage.__table__, AttachmentVersion.__table__,
    LegalHold.__table__, LegalHoldScope.__table__,
)
_ALL_NAMES = frozenset(t.name for t in (*WORLD_TABLES, *EXTRA_TABLES))


def _extra_enum_types() -> dict[str, tuple[str, ...]]:
    found: dict[str, tuple[str, ...]] = {}
    for table in EXTRA_TABLES:
        for column in table.columns:
            if isinstance(column.type, SAEnum) and column.type.name:
                found[column.type.name] = tuple(column.type.enums)
    return found


def create_schema(conn: Connection) -> None:
    """六张基础表 + 本 spec 需要的表；外键只保留指向已建表的。"""
    create_world_schema(conn)
    dialect = conn.dialect.name
    if dialect == "postgresql":
        for name, labels in sorted(_extra_enum_types().items()):
            postgresql.ENUM(*labels, name=name).create(conn, checkfirst=True)
    for table in EXTRA_TABLES:
        fks = [fk for fk in table.foreign_key_constraints if fk.referred_table.name in _ALL_NAMES]
        conn.execute(CreateTable(table, include_foreign_key_constraints=fks))
        for index in sorted(table.indexes, key=lambda item: item.name):
            statement = _index_statement(index, dialect)
            if isinstance(statement, str):
                conn.exec_driver_sql(statement)
            else:
                conn.execute(statement)


@asynccontextmanager
async def sqlite_attachment_world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AuthzWorld]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(create_schema)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            world = await AuthzWorld.create(session, monkeypatch)
            try:
                yield world
            finally:
                await world.redis.aclose()
    finally:
        await engine.dispose()


@asynccontextmanager
async def pg_attachment_world(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AuthzWorld]:
    engine = pg_engine()
    schema = f"asb_world_{uuid.uuid4().hex[:12]}"
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            try:
                await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                await conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
                await conn.run_sync(create_schema)
                async with AsyncSession(
                    bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint",
                ) as session:
                    world = await AuthzWorld.create(session, monkeypatch, schema=schema)
                    try:
                        yield world
                    finally:
                        await world.redis.aclose()
            finally:
                await outer.rollback()
    finally:
        await engine.dispose()


# ─── 造数 ────────────────────────────────────────────────────────────────────


def _first_enum(column) -> Any:
    enum_class = getattr(column.type, "enum_class", None)
    return list(enum_class)[0] if enum_class is not None else column.type.enums[0]


async def add_wp(world: AuthzWorld, project: Project, *, wp_code: str = "D0") -> WorkingPaper:
    index = await world._add(WpIndex(project_id=project.id, wp_code=wp_code, wp_name=f"{wp_code} 测试底稿"))
    source = _first_enum(WorkingPaper.__table__.c.source_type)
    return await world._add(WorkingPaper(
        project_id=project.id, wp_index_id=index.id, file_path=f"storage/{wp_code}.xlsx", source_type=source,
    ))


async def add_attachment(world: AuthzWorld, project: Project, **values: Any) -> Attachment:
    row = Attachment(
        project_id=project.id, file_name=values.pop("file_name", "证据.pdf"),
        file_path=values.pop("file_path", "storage/attachments/x/evidence/证据.pdf"),
        file_type=values.pop("file_type", "pdf"), file_size=values.pop("file_size", 10),
        storage_type=values.pop("storage_type", "local"), **values,
    )
    return await world._add(row)


async def add_confirmation(world: AuthzWorld, project: Project, *, wp: WorkingPaper | None = None,
                           status: str = "sent") -> Confirmation:
    return await world._add(Confirmation(
        project_id=project.id, confirm_type="receivable", counterparty="测试客户", status=status,
        wp_id=wp.id if wp is not None else None, book_amount=100,
    ))


async def add_outbound_link(world: AuthzWorld, confirmation: Confirmation, attachment: Attachment) -> ConfirmationAttachmentLink:
    return await world._add(ConfirmationAttachmentLink(
        confirmation_id=confirmation.id, attachment_id=attachment.id, role="outbound", match_status="manual",
    ))
