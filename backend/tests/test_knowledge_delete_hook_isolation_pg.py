"""真实 PostgreSQL 守卫：删除知识文档时，索引清理钩子失败不得静默回滚删除本身。

═══ 回归背景（2026-09-29 真库 + Playwright 实测）═══

``DELETE /api/knowledge-library/documents/{id}`` 先软删文档，再在**同一事务、commit 之前**
执行 ``_trigger_index_delete``（软删 knowledge_index 条目）。真库的
``knowledge_source_type_enum`` 缺 ``knowledge_doc``（V042 以空文件被登记，见 V168），
钩子 UPDATE 报 ``invalid input value for enum``；钩子 try/except 吞掉异常，但 PG 事务
已进入 aborted 状态，随后 COMMIT 等价于 ROLLBACK —— 接口返回 200「文档已删除」，
文档原样还在。

═══ 为什么必须真库 ═══

判据是「语句失败 → 事务 aborted → COMMIT 变 ROLLBACK」这一 **PostgreSQL 事务语义**。
SQLite / mock 都不会进入 aborted 状态，钩子失败后删除照样提交 —— 修没修都绿，是假绿。
故本文件带**反向对照**：把钩子换回无 SAVEPOINT 的旧实现，断言删除确实被静默回滚。
对照不红，说明夹具没复现出缺陷，正向断言就是空转。

═══ 隔离 ═══

两个 scratch schema（``tmp_kbdel_*``），``search_path`` 只含自己：
  * drifted：enum 缺 ``knowledge_doc``（复现 V168 之前的真库形态）
  * healthy：enum 完整（V168 之后）
表由 **ORM metadata** 派生（去外键、去 ``embedding_vec`` —— 与未装 pgvector 的真库一致）。
结束 ``DROP SCHEMA CASCADE``。全部场景一次 ``asyncio.run`` 跑完落快照。
``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SCHEMA_PREFIX = "tmp_kbdel_"

#: 与未安装 pgvector 的真库一致：V119 在扩展缺失时跳过该列
_ABSENT_COLUMNS = {"knowledge_index": {"embedding_vec"}}


class _HarnessError(RuntimeError):
    """采集自身失败（禁 fail-open：让守卫红，而不是降级成『无数据』）。"""


def _scratch_type(column: sa.Column):
    """enum 列换成显式 ``postgresql.ENUM(create_type=False)``：枚举标签必须由本夹具掌控
    （drifted 变体要故意缺 knowledge_doc）。直接沿用 ORM 的 ``sa.Enum`` 时 ``Table.create``
    会自行 CREATE TYPE（create_type=False 在泛型 Enum 上不可靠），与夹具建的类型撞名。"""
    from sqlalchemy.dialects import postgresql

    t = column.type
    if isinstance(t, sa.Enum) and t.name:
        return postgresql.ENUM(*t.enums, name=t.name, create_type=False)
    return t


def _fk_free_copy(table: sa.Table) -> sa.Table:
    """ORM 表 → 同列同类型、无外键无索引的 scratch 表（列必须从 ORM 派生，禁手抄 DDL）。"""
    absent = _ABSENT_COLUMNS.get(table.name, set())
    return sa.Table(
        table.name,
        sa.MetaData(),
        *[
            sa.Column(
                column.name,
                _scratch_type(column),
                primary_key=column.primary_key,
                nullable=column.nullable,
                server_default=column.server_default,
            )
            for column in table.columns
            if column.name not in absent
        ],
    )


def _enum_ddl(tables: list[sa.Table], drop_labels: dict[str, set[str]]) -> list[str]:
    seen: dict[str, list[str]] = {}
    for table in tables:
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.name:
                labels = [
                    label for label in column.type.enums
                    if label not in drop_labels.get(column.type.name, set())
                ]
                seen.setdefault(column.type.name, labels)
    return [
        "CREATE TYPE {name} AS ENUM ({labels})".format(
            name=name, labels=", ".join(f"'{label}'" for label in labels)
        )
        for name, labels in sorted(seen.items())
    ]


async def _legacy_trigger_index_delete(db, doc_id) -> None:
    """修复前的钩子实现（无 SAVEPOINT）—— 仅作反向对照，证明夹具复现了缺陷。"""
    from sqlalchemy import func, update

    from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType

    try:
        await db.execute(
            update(KnowledgeIndex)
            .where(
                KnowledgeIndex.source_type == KnowledgeSourceType.knowledge_doc,
                KnowledgeIndex.source_id == doc_id,
                KnowledgeIndex.is_deleted == False,  # noqa: E712
            )
            .values(is_deleted=True, updated_at=func.now())
        )
        await db.flush()
    except Exception:  # noqa: BLE001 - 与旧实现一致：吞异常
        pass


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.routers.knowledge_folders as kb_module
    from app.core.config import settings
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.models.ai_models import KnowledgeIndex
    from app.models.core import ProjectUser
    from app.models.knowledge_models import (
        KnowledgeAccessLevel,
        KnowledgeDocument,
        KnowledgeFolder,
    )

    if not str(settings.DATABASE_URL).startswith("postgresql"):
        raise _HarnessError(
            "本守卫的判据是 PostgreSQL 事务 aborted 语义，必须真实 PostgreSQL；"
            f"当前 DATABASE_URL={settings.DATABASE_URL!r}"
        )

    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    # project_users：删除前的资源级授权要解析当前用户的项目成员关系（表缺失时解析会失败）
    tables = [
        KnowledgeFolder.__table__,
        KnowledgeDocument.__table__,
        KnowledgeIndex.__table__,
        ProjectUser.__table__,
    ]
    variants = {
        "drifted": {"knowledge_source_type_enum": {"knowledge_doc"}},
        "healthy": {},
    }
    schemas = {name: f"{_SCHEMA_PREFIX}{name}_{uuid.uuid4().hex[:10]}" for name in variants}
    snap: dict[str, Any] = {"harness_errors": [], "scenarios": {}}

    class _User:
        id = uuid.uuid4()
        username = "kb-del-tester"
        is_active = True
        # 删除需管理权（spec knowledge-base-retrieval-and-authz-closure 6.2）：以系统管理员身份
        # 执行，本守卫只关心「钩子失败不得回滚删除」这一事务语义
        role = "admin"

    async def _run_scenario(engine, *, label: str, legacy_hook: bool, seed_index: bool) -> None:
        Session = async_sessionmaker(engine, expire_on_commit=False)
        folder_id, doc_id = uuid.uuid4(), uuid.uuid4()
        async with Session() as s:
            s.add(KnowledgeFolder(id=folder_id, name=f"删除钩子隔离-{label}", access_level=KnowledgeAccessLevel.public))
            await s.flush()
            s.add(KnowledgeDocument(id=doc_id, folder_id=folder_id, name="probe.txt", file_size=1, content_text="x"))
            if seed_index:
                await s.execute(
                    sa.text(
                        "INSERT INTO knowledge_index (id, project_id, source_type, source_id, content_text, chunk_index) "
                        "VALUES (:id, :pid, 'knowledge_doc', :sid, 'x', 0)"
                    ),
                    {"id": uuid.uuid4(), "pid": uuid.uuid4(), "sid": doc_id},
                )
            await s.commit()

        app = FastAPI()
        app.include_router(kb_module.router)

        async def _override_db():
            async with Session() as session:
                yield session

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: _User()

        original_hook = kb_module._trigger_index_delete
        if legacy_hook:
            kb_module._trigger_index_delete = _legacy_trigger_index_delete
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.delete(f"/api/knowledge-library/documents/{doc_id}")
        finally:
            kb_module._trigger_index_delete = original_hook

        async with Session() as s:
            doc_deleted = (
                await s.execute(sa.select(KnowledgeDocument.is_deleted).where(KnowledgeDocument.id == doc_id))
            ).scalar_one()
            index_rows = (
                await s.execute(sa.select(KnowledgeIndex.is_deleted).where(KnowledgeIndex.source_id == doc_id))
            ).scalars().all()
        snap["scenarios"][label] = {
            "status": resp.status_code,
            "doc_deleted": bool(doc_deleted),
            "index_rows_deleted": [bool(v) for v in index_rows],
        }

    engines = {}
    try:
        for variant, drop_labels in variants.items():
            schema = schemas[variant]
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
            engine = create_async_engine(
                settings.DATABASE_URL,
                poolclass=NullPool,
                connect_args={**ssl_off, "server_settings": {"search_path": schema}},
            )
            engines[variant] = engine
            scratch = [_fk_free_copy(t) for t in tables]
            async with engine.begin() as conn:
                for ddl in _enum_ddl(tables, drop_labels):
                    await conn.exec_driver_sql(ddl)
                for t in scratch:
                    await conn.run_sync(t.create)

        await _run_scenario(engines["drifted"], label="drifted_current", legacy_hook=False, seed_index=False)
        await _run_scenario(engines["drifted"], label="drifted_legacy", legacy_hook=True, seed_index=False)
        await _run_scenario(engines["healthy"], label="healthy_current", legacy_hook=False, seed_index=True)
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        snap["harness_errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        for engine in engines.values():
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                for schema in schemas.values():
                    await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception as exc:  # noqa: BLE001
            snap["harness_errors"].append(f"cleanup: {type(exc).__name__}: {exc}")
        await admin.dispose()
    return snap


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return asyncio.run(_collect())


def test_harness_ran_without_errors(snapshot: dict[str, Any]) -> None:
    assert snapshot["harness_errors"] == []
    assert set(snapshot["scenarios"]) == {"drifted_current", "drifted_legacy", "healthy_current"}


def test_negative_control_legacy_hook_silently_rolls_back_delete(snapshot: dict[str, Any]) -> None:
    """反向对照：旧钩子（无 SAVEPOINT）下接口 200 但文档没删 —— 证明夹具复现了真库缺陷。"""
    s = snapshot["scenarios"]["drifted_legacy"]
    assert s["status"] == 200
    assert s["doc_deleted"] is False, "夹具未复现 aborted 事务语义，下方正向断言会空转"


def test_delete_commits_even_when_index_hook_fails(snapshot: dict[str, Any]) -> None:
    s = snapshot["scenarios"]["drifted_current"]
    assert s["status"] == 200
    assert s["doc_deleted"] is True, "索引钩子失败把文档软删一并回滚了（接口却报成功）"


def test_delete_also_soft_deletes_index_rows_when_enum_healthy(snapshot: dict[str, Any]) -> None:
    s = snapshot["scenarios"]["healthy_current"]
    assert s["status"] == 200
    assert s["doc_deleted"] is True
    assert s["index_rows_deleted"] == [True]
