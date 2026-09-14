# Feature: procedure-delegation-notification — Task 2 V105 expand 模型契约测试
"""V105（程序行任务 expand 模型）迁移与结构契约测试。

Task 2 / 需求 1.1-1.2, 2.1-2.2, 4.2, 10.1, 12.1-12.7, 13.3：

本文件分两层验证，且**不把 `IF NOT EXISTS` 当结构正确性证明**：

1. 静态单元（无需 PG，任意引擎可跑）：
   - V105 迁移文件存在、DO $$ + information_schema 守护列补齐、pg_indexes 守护索引。
   - 迁移**不得**出现 `ON CONFLICT (wp_id`；active 唯一谓词固定 `WHERE is_deleted = false`。
   - 4 张新 ORM 模型 + task_events/notifications 扩展列已登记到 Base.metadata。

2. PostgreSQL 集成（不可达则 skip）——用 information_schema / pg_catalog 精校：
   - 4 张新表列类型/nullable/FK 目标。
   - task_events(Delivery_Outbox) 与 notifications 扩展列。
   - active partial unique index 列顺序与 `WHERE is_deleted = false` 谓词。
   - assignee/reviewer covering index 列 + INCLUDE 列顺序 + partial 谓词。
   - outbox claim/order index 谓词 + idempotency 唯一索引。
   - notifications dedup 唯一索引列 + 谓词。
   - 迁移幂等（连跑两次不报错、结构不漂移）。
   - active partial unique 的运行时行为：非删除行拒绝重复、软删除后允许重建（P4 / 12.2）。
   - ORM ↔ DB Task 2 作用域零漂移（不被未应用的 V103/V104 噪声污染）。

Validates: Requirements 1.1-1.2, 2.1-2.2, 4.2, 10.1, 12.1-12.7, 13.3
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.migration_runner import MigrationRunner
from app.models.base import Base

# 触发 ORM 注册（4 张新表 + 扩展列所在模块）
import app.models.procedure_models  # noqa: F401
import app.models.phase15_models  # noqa: F401
import app.models.core  # noqa: F401

_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = settings.DATABASE_URL.startswith("postgresql")

_NEW_TABLES = (
    "procedure_row_definitions",
    "procedure_row_tasks",
    "procedure_row_task_history",
    "procedure_operation_previews",
)

# task_events(Delivery_Outbox) 扩展列
_TASK_EVENTS_NEW_COLS = (
    "aggregate_type",
    "aggregate_id",
    "aggregate_version",
    "idempotency_key",
    "delegation_batch_id",
    "available_at",
    "lease_expires_at",
    "claimed_by",
    "processed_at",
    "dead_letter_at",
    "last_error",
)
# notifications 聚合通知扩展列
_NOTIFICATIONS_NEW_COLS = ("event_id", "recipient_user_id", "dedup_key", "metadata")


async def _apply_v105(engine) -> None:
    """按运行时口径分句执行 V105（DO $$ 块整体保留），逐条 exec_driver_sql。"""
    sql = _V105.read_text(encoding="utf-8")
    statements = MigrationRunner._split_sql_statements(sql)
    assert statements, "V105 迁移解析出的语句为空"
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (V105 schema contract)")
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
    except Exception:
        await engine.dispose()
        pytest.skip("PG not reachable")
    try:
        yield engine
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# 1. 静态单元（无需 PG）
# ---------------------------------------------------------------------------
class TestV105MigrationStatic:
    def test_migration_file_exists(self):
        assert _V105.is_file(), "V105 procedure_row_tasks 迁移缺失"

    def test_idempotent_guards_present(self):
        content = _V105.read_text(encoding="utf-8")
        # 列补齐用 DO $$ + information_schema.columns 守护
        assert "information_schema.columns" in content
        assert "DO $$" in content
        # 建表/索引幂等
        assert "CREATE TABLE IF NOT EXISTS procedure_row_definitions" in content
        assert "CREATE TABLE IF NOT EXISTS procedure_row_tasks" in content
        assert "CREATE TABLE IF NOT EXISTS procedure_row_task_history" in content
        assert "CREATE TABLE IF NOT EXISTS procedure_operation_previews" in content
        # 唯一/覆盖/claim 索引用 pg_indexes 检测后创建
        assert "pg_indexes" in content

    def test_active_unique_predicate_and_no_wp_id_conflict(self):
        content = _V105.read_text(encoding="utf-8")
        # active partial unique 必须是 (project_id, wp_index_id, sheet_key, definition_key) WHERE is_deleted=false
        assert re.search(
            r"CREATE UNIQUE INDEX uq_procedure_row_tasks_active\s+ON procedure_row_tasks\("
            r"project_id, wp_index_id, sheet_key, definition_key\)\s+WHERE is_deleted = false",
            content,
        ), "active partial unique 索引列/谓词与 design 不一致"
        # 禁止用 nullable wp_id 保证唯一性
        assert "ON CONFLICT (wp_id" not in content
        assert re.search(r"UNIQUE INDEX[^\n]*\(wp_id", content) is None

    def test_covering_and_claim_indexes_declared(self):
        content = _V105.read_text(encoding="utf-8")
        assert "ix_procedure_row_tasks_assignee_cover" in content
        assert "ix_procedure_row_tasks_reviewer_cover" in content
        assert "INCLUDE (id, wp_index_id, wp_id, sheet_key, definition_key, lock_version, assignment_version)" in content
        assert "ix_task_events_claim_order" in content
        assert "uq_task_events_idempotency_key" in content
        assert "uq_notifications_event_recipient" in content

    def test_orm_models_registered(self):
        registered = set(Base.metadata.tables.keys())
        missing = set(_NEW_TABLES) - registered
        assert not missing, f"V105 ORM 表未登记: {sorted(missing)}"

    def test_orm_extension_columns_registered(self):
        te = Base.metadata.tables["task_events"].columns.keys()
        assert set(_TASK_EVENTS_NEW_COLS) <= set(te), (
            f"task_events 缺 outbox 扩展列: {set(_TASK_EVENTS_NEW_COLS) - set(te)}"
        )
        notif = Base.metadata.tables["notifications"].columns.keys()
        assert set(_NOTIFICATIONS_NEW_COLS) <= set(notif), (
            f"notifications 缺聚合通知扩展列: {set(_NOTIFICATIONS_NEW_COLS) - set(notif)}"
        )


# ---------------------------------------------------------------------------
# 2. PostgreSQL 集成契约（information_schema / pg_catalog）
# ---------------------------------------------------------------------------
async def _columns(conn, table: str) -> dict[str, dict]:
    rows = await conn.execute(
        sa.text(
            "SELECT column_name, data_type, is_nullable, character_maximum_length "
            "FROM information_schema.columns WHERE table_schema='public' AND table_name=:t"
        ),
        {"t": table},
    )
    return {
        r[0]: {"type": r[1], "nullable": r[2] == "YES", "maxlen": r[3]}
        for r in rows.fetchall()
    }


async def _fks(conn, table: str) -> dict[str, tuple[str, str]]:
    rows = await conn.execute(
        sa.text(
            """
            SELECT kcu.column_name, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = :t
            """
        ),
        {"t": table},
    )
    return {r[0]: (r[1], r[2]) for r in rows.fetchall()}


async def _indexdef(conn, indexname: str) -> str | None:
    return (
        await conn.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"),
            {"n": indexname},
        )
    ).scalar()


@pytest.mark.asyncio
class TestV105PgContract:
    async def test_apply_is_idempotent_and_tables_exist(self, pg_engine):
        await _apply_v105(pg_engine)
        await _apply_v105(pg_engine)  # 幂等：第二次不得抛错
        async with pg_engine.connect() as conn:
            for tbl in _NEW_TABLES:
                reg = (
                    await conn.execute(
                        sa.text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"}
                    )
                ).scalar()
                assert reg is not None, f"V105 未建成表: {tbl}"

    async def test_definitions_columns_and_types(self, pg_engine):
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            cols = await _columns(conn, "procedure_row_definitions")
        assert cols["definition_key"]["type"] == "character varying"
        assert cols["definition_key"]["maxlen"] == 200
        assert cols["definition_key"]["nullable"] is False
        assert cols["template_revision_hash"]["type"] == "character"
        assert cols["template_revision_hash"]["maxlen"] == 64
        assert cols["template_revision_hash"]["nullable"] is False
        assert cols["source_locator"]["type"] == "jsonb"
        assert cols["procedure_text"]["nullable"] is False
        assert cols["ref_snapshot"]["type"] == "jsonb"
        assert cols["legacy_aliases"]["type"] == "jsonb"
        assert cols["normalized_content"]["type"] == "jsonb"
        assert cols["program_no"]["nullable"] is True

    async def test_row_tasks_columns_nullable_and_fk(self, pg_engine):
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            cols = await _columns(conn, "procedure_row_tasks")
            fks = await _fks(conn, "procedure_row_tasks")
        # 项目锚点非空、wp_id 可空
        assert cols["project_id"]["nullable"] is False
        assert cols["wp_index_id"]["nullable"] is False
        assert cols["wp_id"]["nullable"] is True
        assert cols["definition_key"]["nullable"] is False
        assert cols["sheet_key"]["nullable"] is False
        assert cols["audit_cycle_snapshot"]["nullable"] is False
        assert cols["applicability_status"]["nullable"] is False
        assert cols["workflow_status"]["nullable"] is False
        assert cols["assignment_version"]["type"] == "integer"
        assert cols["lock_version"]["type"] == "integer"
        assert cols["due_at"]["nullable"] is True
        assert cols["migration_detail"]["type"] == "jsonb"
        assert cols["evidence_snapshot"]["type"] == "jsonb"
        # FK 目标
        assert fks["project_id"] == ("projects", "id")
        assert fks["wp_index_id"] == ("wp_index", "id")
        assert fks["wp_id"] == ("working_paper", "id")
        assert fks["definition_key"] == ("procedure_row_definitions", "definition_key")
        assert fks["assignee_staff_id"] == ("staff_members", "id")
        assert fks["reviewer_staff_id"] == ("staff_members", "id")

    async def test_history_and_preview_fk(self, pg_engine):
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            hcols = await _columns(conn, "procedure_row_task_history")
            hfks = await _fks(conn, "procedure_row_task_history")
            pcols = await _columns(conn, "procedure_operation_previews")
            pfks = await _fks(conn, "procedure_operation_previews")
        assert hcols["event_type"]["nullable"] is False
        assert hcols["detail"]["type"] == "jsonb"
        assert hfks["task_id"] == ("procedure_row_tasks", "id")
        assert hfks["project_id"] == ("projects", "id")
        assert hfks["actor_user_id"] == ("users", "id")
        # preview 一次性凭证
        assert pcols["operation"]["nullable"] is False
        assert pcols["request_hash"]["type"] == "character"
        assert pcols["request_hash"]["maxlen"] == 64
        assert pcols["expires_at"]["nullable"] is False
        assert pcols["consumed_at"]["nullable"] is True
        assert pcols["result"]["nullable"] is True
        assert pfks["actor_user_id"] == ("users", "id")
        assert pfks["project_id"] == ("projects", "id")

    async def test_outbox_and_notification_extension_columns(self, pg_engine):
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            te = await _columns(conn, "task_events")
            notif = await _columns(conn, "notifications")
            nfks = await _fks(conn, "notifications")
        for c in _TASK_EVENTS_NEW_COLS:
            assert c in te, f"task_events 缺列 {c}"
        assert te["aggregate_version"]["type"] == "integer"
        assert te["idempotency_key"]["type"] == "character varying"
        assert te["available_at"]["type"] == "timestamp with time zone"
        assert te["processed_at"]["type"] == "timestamp with time zone"
        for c in _NOTIFICATIONS_NEW_COLS:
            assert c in notif, f"notifications 缺列 {c}"
        assert notif["metadata"]["type"] == "jsonb"
        assert notif["recipient_user_id"]["type"] == "uuid"
        assert nfks.get("recipient_user_id") == ("users", "id")

    async def test_active_partial_unique_index_predicate(self, pg_engine):
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            idef = await _indexdef(conn, "uq_procedure_row_tasks_active")
        assert idef is not None, "active partial unique 索引缺失"
        assert "UNIQUE" in idef
        # 列顺序精确
        assert re.search(
            r"\(project_id, wp_index_id, sheet_key, definition_key\)", idef
        ), f"active unique 列顺序不符: {idef}"
        # partial 谓词 = WHERE (is_deleted = false)
        assert re.search(r"WHERE \(is_deleted = false\)", idef), f"partial 谓词不符: {idef}"

    async def test_covering_indexes_columns_and_include(self, pg_engine):
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            adef = await _indexdef(conn, "ix_procedure_row_tasks_assignee_cover")
            rdef = await _indexdef(conn, "ix_procedure_row_tasks_reviewer_cover")
        for name, idef, lead in (
            ("assignee", adef, "assignee_staff_id"),
            ("reviewer", rdef, "reviewer_staff_id"),
        ):
            assert idef is not None, f"{name} covering index 缺失"
            assert re.search(
                rf"\({lead}, workflow_status, due_at, project_id\)", idef
            ), f"{name} covering 主键列顺序不符: {idef}"
            assert re.search(
                r"INCLUDE \(id, wp_index_id, wp_id, sheet_key, definition_key, lock_version, assignment_version\)",
                idef,
            ), f"{name} covering INCLUDE 列顺序不符: {idef}"
            assert re.search(r"WHERE \(is_deleted = false\)", idef), f"{name} partial 谓词不符: {idef}"

    async def test_outbox_claim_and_idempotency_indexes(self, pg_engine):
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            claim = await _indexdef(conn, "ix_task_events_claim_order")
            idem = await _indexdef(conn, "uq_task_events_idempotency_key")
            dedup = await _indexdef(conn, "uq_notifications_event_recipient")
        assert claim is not None
        assert re.search(
            r"\(available_at, lease_expires_at, aggregate_type, aggregate_id, aggregate_version\)",
            claim,
        ), f"claim 索引列顺序不符: {claim}"
        assert "processed_at IS NULL" in claim and "dead_letter_at IS NULL" in claim
        assert idem is not None and "UNIQUE" in idem
        assert "idempotency_key IS NOT NULL" in idem
        assert dedup is not None and "UNIQUE" in dedup
        assert re.search(r"\(event_id, recipient_user_id\)", dedup)
        assert "event_id IS NOT NULL" in dedup and "recipient_user_id IS NOT NULL" in dedup

    async def test_active_unique_enforced_and_soft_delete_reuse(self, pg_engine):
        """P4 / 12.2：active partial unique 拒绝重复活跃行，软删除后允许重建。

        使用已存在的 project/wp_index 复用 FK，整体事务回滚不污染 dev 库。
        """
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                ids = (
                    await conn.execute(
                        sa.text(
                            "SELECT p.id, wi.id FROM projects p "
                            "JOIN wp_index wi ON wi.project_id = p.id LIMIT 1"
                        )
                    )
                ).first()
                if ids is None:
                    pytest.skip("dev 库无 project+wp_index 可复用于唯一性行为测试")
                project_id, wp_index_id = ids

                def_key = f"test::V105::{uuid.uuid4()}"
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_row_definitions "
                        "(definition_key, template_code, template_revision_hash, sheet_key, "
                        " procedure_text) VALUES (:k, 'TESTWP', :h, 'TESTWP', 'p')"
                    ),
                    {"k": def_key, "h": "0" * 64},
                )
                sheet_key = "TESTWP"
                insert_task = sa.text(
                    "INSERT INTO procedure_row_tasks "
                    "(project_id, wp_index_id, definition_key, sheet_key, "
                    " definition_revision_hash, audit_cycle_snapshot) "
                    "VALUES (:p, :w, :k, :s, :h, 'T')"
                )
                params = {
                    "p": project_id,
                    "w": wp_index_id,
                    "k": def_key,
                    "s": sheet_key,
                    "h": "0" * 64,
                }
                await conn.execute(insert_task, params)

                # 重复活跃行 → IntegrityError
                dup_rejected = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(insert_task, params)
                except IntegrityError:
                    dup_rejected = True
                assert dup_rejected, "active partial unique 未拒绝重复活跃行"

                # 软删除后允许重建
                await conn.execute(
                    sa.text(
                        "UPDATE procedure_row_tasks SET is_deleted = true, deleted_at = now() "
                        "WHERE project_id=:p AND wp_index_id=:w AND sheet_key=:s AND definition_key=:k"
                    ),
                    params,
                )
                await conn.execute(insert_task, params)  # 应成功
                active_cnt = (
                    await conn.execute(
                        sa.text(
                            "SELECT count(*) FROM procedure_row_tasks "
                            "WHERE project_id=:p AND wp_index_id=:w AND sheet_key=:s "
                            "AND definition_key=:k AND is_deleted=false"
                        ),
                        params,
                    )
                ).scalar()
                assert active_cnt == 1, "软删除重建后活跃行应恰为 1"
            finally:
                await trans.rollback()

    async def test_orm_db_zero_drift_for_task2_scope(self, pg_engine):
        """ORM ↔ DB Task 2 作用域零漂移（仅限本任务的表/列，规避未应用 V103/V104 噪声）。"""
        await _apply_v105(pg_engine)
        async with pg_engine.connect() as conn:
            for table in _NEW_TABLES:
                db_cols = set((await _columns(conn, table)).keys())
                orm_cols = set(Base.metadata.tables[table].columns.keys())
                assert orm_cols <= db_cols, (
                    f"{table} ORM 列不在 DB（orm_extra 漂移）: {sorted(orm_cols - db_cols)}"
                )
            te_db = set((await _columns(conn, "task_events")).keys())
            assert set(_TASK_EVENTS_NEW_COLS) <= te_db
            notif_db = set((await _columns(conn, "notifications")).keys())
            assert set(_NOTIFICATIONS_NEW_COLS) <= notif_db
