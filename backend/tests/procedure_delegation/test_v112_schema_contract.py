# Feature: procedure-delegation-notification — Task 2 V112 cutover-hardening 契约测试
"""V112（current-revision registry + append-only 防护）迁移与结构契约测试。

Task 2 / 需求 15.1-15.2, 15.11, 12.1-12.7：

1. 静态单元：
   - V112 迁移文件存在、procedure_template_revisions 与 procedure_row_definition_revisions 建表。
   - partial unique 保证每个 template_code 最多一个 is_current=true。
   - history append-only trigger 存在。
   - ORM 模型已登记。

2. PostgreSQL 集成（不可达则 skip）：
   - 列类型/nullable/FK/CHECK 约束。
   - (template_code, revision_hash) unique。
   - partial unique WHERE is_current=true 的 template_code 唯一性。
   - 回填逻辑：唯一 revision 设 current，多 revision 设 reconcile_pending。
   - append-only trigger 拒绝 UPDATE/DELETE（除非 maintenance 开关）。
   - current revision 唯一性运行时行为（P35）。

Validates: Requirements 15.1-15.2, 15.11
**Validates: Requirements 15.1-15.2**
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.migration_runner import MigrationRunner
from app.models.base import Base

# 确保 ORM 模型注册
import app.models.procedure_models  # noqa: F401

_V112 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V112__procedure_current_revision_registry.sql"
)
_V105 = (
    Path(__file__).resolve().parent.parent.parent
    / "migrations"
    / "V105__procedure_row_tasks.sql"
)
_IS_PG = settings.DATABASE_URL.startswith("postgresql")


async def _apply_migrations(engine) -> None:
    """Apply V105 then V112 (V112 depends on V105 tables)."""
    for path in (_V105, _V112):
        sql = path.read_text(encoding="utf-8")
        statements = MigrationRunner._split_sql_statements(sql)
        async with engine.begin() as conn:
            for stmt in statements:
                await conn.exec_driver_sql(stmt)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (V112 schema contract)")
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


async def _indexdef(conn, indexname: str) -> str | None:
    return (
        await conn.execute(
            sa.text("SELECT indexdef FROM pg_indexes WHERE indexname = :n"),
            {"n": indexname},
        )
    ).scalar()


async def _check_constraints(conn, table: str) -> dict[str, str]:
    rows = await conn.execute(
        sa.text(
            "SELECT conname, pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c "
            "JOIN pg_class rel ON rel.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = rel.relnamespace "
            "WHERE rel.relname = :t AND n.nspname = 'public' AND c.contype = 'c'"
        ),
        {"t": table},
    )
    return {r[0]: r[1] for r in rows.fetchall()}


# ---------------------------------------------------------------------------
# 1. 静态单元
# ---------------------------------------------------------------------------
class TestV112MigrationStatic:
    def test_migration_file_exists(self):
        assert _V112.is_file(), "V112 cutover-hardening 迁移缺失"

    def test_creates_template_revisions_table(self):
        content = _V112.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS procedure_template_revisions" in content

    def test_creates_definition_revisions_table(self):
        content = _V112.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS procedure_row_definition_revisions" in content

    def test_identity_unique_index(self):
        content = _V112.read_text(encoding="utf-8")
        assert "uq_procedure_template_revisions_identity" in content

    def test_current_partial_unique_index(self):
        content = _V112.read_text(encoding="utf-8")
        assert "uq_procedure_template_revisions_current" in content
        assert "WHERE is_current = true" in content

    def test_append_only_trigger(self):
        content = _V112.read_text(encoding="utf-8")
        assert "prevent_procedure_row_task_history_mutation" in content
        assert "procedure_row_task_history is append-only" in content
        assert "trg_procedure_row_task_history_append_only" in content

    def test_backfill_logic_no_timestamp_guessing(self):
        content = _V112.read_text(encoding="utf-8")
        # Unique revision → current; multiple → reconcile_pending
        assert "revision_count = 1" in content
        assert "reconcile_pending" in content
        assert "multiple_revisions_require_reconcile" in content
        # Must NOT use created_at, max hash, or "most recent" for guessing
        assert "ORDER BY created_at" not in content
        assert "max(" not in content.lower() or "max_examples" in content.lower()

    def test_orm_v109_tables_registered(self):
        registered = set(Base.metadata.tables.keys())
        assert "procedure_template_revisions" in registered
        assert "procedure_row_definition_revisions" in registered


# ---------------------------------------------------------------------------
# 2. PostgreSQL 集成（P35 数据库属性测试）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestV112PgContract:
    async def test_apply_is_idempotent(self, pg_engine):
        await _apply_migrations(pg_engine)
        await _apply_migrations(pg_engine)  # 幂等：第二次不得抛错
        async with pg_engine.connect() as conn:
            reg = (
                await conn.execute(
                    sa.text("SELECT to_regclass('public.procedure_template_revisions')")
                )
            ).scalar()
            assert reg is not None

    async def test_template_revisions_columns_and_types(self, pg_engine):
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            cols = await _columns(conn, "procedure_template_revisions")
        assert cols["template_code"]["type"] == "character varying"
        assert cols["template_code"]["maxlen"] == 80
        assert cols["template_code"]["nullable"] is False
        assert cols["revision_hash"]["type"] == "character"
        assert cols["revision_hash"]["maxlen"] == 64
        assert cols["revision_hash"]["nullable"] is False
        assert cols["status"]["type"] == "character varying"
        assert cols["status"]["nullable"] is False
        assert cols["is_current"]["type"] == "boolean"
        assert cols["is_current"]["nullable"] is False
        assert cols["supersedes_revision_hash"]["nullable"] is True
        assert cols["activated_at"]["nullable"] is True
        assert cols["activated_by"]["nullable"] is True
        assert cols["reconcile_detail"]["type"] == "jsonb"

    async def test_definition_revisions_columns(self, pg_engine):
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            cols = await _columns(conn, "procedure_row_definition_revisions")
        assert cols["template_code"]["nullable"] is False
        assert cols["revision_hash"]["nullable"] is False
        assert cols["sheet_key"]["nullable"] is False
        assert cols["definition_key"]["nullable"] is False

    async def test_check_constraints_status(self, pg_engine):
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            checks = await _check_constraints(conn, "procedure_template_revisions")
        # status only allows registered/current/reconcile_pending
        status_check = checks.get("ck_procedure_template_revision_status", "")
        assert "registered" in status_check
        assert "current" in status_check
        assert "reconcile_pending" in status_check
        # is_current=true 必须 status='current'
        current_check = checks.get("ck_procedure_template_revision_current_status", "")
        assert "is_current" in current_check

    async def test_identity_unique_index_predicate(self, pg_engine):
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            idef = await _indexdef(conn, "uq_procedure_template_revisions_identity")
        assert idef is not None, "identity unique 索引缺失"
        assert "UNIQUE" in idef
        assert re.search(r"\(template_code, revision_hash\)", idef)

    async def test_current_partial_unique_index_predicate(self, pg_engine):
        """P35 核心：每个 template_code 最多一个 active current revision。"""
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            idef = await _indexdef(conn, "uq_procedure_template_revisions_current")
        assert idef is not None, "current partial unique 索引缺失"
        assert "UNIQUE" in idef
        assert re.search(r"\(template_code\)", idef)
        assert re.search(r"WHERE \(is_current = true\)", idef)

    async def test_member_unique_index(self, pg_engine):
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            idef = await _indexdef(conn, "uq_procedure_row_definition_revision_member")
        assert idef is not None
        assert "UNIQUE" in idef
        assert re.search(
            r"\(template_code, revision_hash, sheet_key, definition_key\)", idef
        )

    async def test_current_revision_uniqueness_enforced(self, pg_engine):
        """P35: 同一 template_code 不能有两个 is_current=true。"""
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                tc = f"TEST_P35_{uuid.uuid4().hex[:8]}"
                h1 = "a" * 64
                h2 = "b" * 64
                # 插入第一个 current
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_template_revisions "
                        "(template_code, revision_hash, status, is_current) "
                        "VALUES (:tc, :h, 'current', true)"
                    ),
                    {"tc": tc, "h": h1},
                )
                # 第二个 current → 被 partial unique 拒绝
                rejected = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            sa.text(
                                "INSERT INTO procedure_template_revisions "
                                "(template_code, revision_hash, status, is_current) "
                                "VALUES (:tc, :h, 'current', true)"
                            ),
                            {"tc": tc, "h": h2},
                        )
                except IntegrityError:
                    rejected = True
                assert rejected, "partial unique 未拒绝同 template_code 的第二个 current"
            finally:
                await trans.rollback()

    async def test_history_append_only_rejects_update_delete(self, pg_engine):
        """P35: history append-only 防护拒绝 UPDATE/DELETE。"""
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                # 需要先有一条 history（依赖 project/task 存在）
                ids = (
                    await conn.execute(
                        sa.text(
                            "SELECT t.id, t.project_id FROM procedure_row_tasks t LIMIT 1"
                        )
                    )
                ).first()
                if ids is None:
                    pytest.skip("dev 库无 procedure_row_tasks 行可测 history trigger")
                task_id, project_id = ids
                # 插入一条测试 history
                hist_id = uuid.uuid4()
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_row_task_history "
                        "(id, task_id, project_id, event_type) "
                        "VALUES (:id, :tid, :pid, 'test_trigger')"
                    ),
                    {"id": hist_id, "tid": task_id, "pid": project_id},
                )

                # UPDATE 应被 trigger 拒绝
                update_rejected = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            sa.text(
                                "UPDATE procedure_row_task_history "
                                "SET event_type='hacked' WHERE id=:id"
                            ),
                            {"id": hist_id},
                        )
                except DBAPIError:
                    update_rejected = True
                assert update_rejected, "append-only trigger 未拒绝 UPDATE"

                # DELETE 应被 trigger 拒绝
                delete_rejected = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(
                            sa.text(
                                "DELETE FROM procedure_row_task_history WHERE id=:id"
                            ),
                            {"id": hist_id},
                        )
                except DBAPIError:
                    delete_rejected = True
                assert delete_rejected, "append-only trigger 未拒绝 DELETE"
            finally:
                await trans.rollback()

    async def test_history_maintenance_mode_allows_mutation(self, pg_engine):
        """maintenance 模式下允许清理。"""
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                ids = (
                    await conn.execute(
                        sa.text(
                            "SELECT t.id, t.project_id FROM procedure_row_tasks t LIMIT 1"
                        )
                    )
                ).first()
                if ids is None:
                    pytest.skip("dev 库无 procedure_row_tasks")
                task_id, project_id = ids
                hist_id = uuid.uuid4()
                await conn.execute(
                    sa.text(
                        "INSERT INTO procedure_row_task_history "
                        "(id, task_id, project_id, event_type) "
                        "VALUES (:id, :tid, :pid, 'test_maintenance')"
                    ),
                    {"id": hist_id, "tid": task_id, "pid": project_id},
                )
                # 开启 maintenance 模式
                await conn.execute(
                    sa.text("SET LOCAL app.procedure_history_maintenance = 'on'")
                )
                # 现在 DELETE 应该成功（trigger 放行）
                await conn.execute(
                    sa.text(
                        "DELETE FROM procedure_row_task_history WHERE id=:id"
                    ),
                    {"id": hist_id},
                )
                # 验证已删除
                cnt = (
                    await conn.execute(
                        sa.text(
                            "SELECT count(*) FROM procedure_row_task_history WHERE id=:id"
                        ),
                        {"id": hist_id},
                    )
                ).scalar()
                assert cnt == 0
            finally:
                await trans.rollback()

    async def test_backfill_unique_revision_sets_current(self, pg_engine):
        """回填逻辑：唯一 revision 的 template_code 自动设 current。"""
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            # 查是否有唯一 revision 且 is_current=true 的
            row = (
                await conn.execute(
                    sa.text(
                        "SELECT template_code, revision_hash, status, is_current "
                        "FROM procedure_template_revisions "
                        "WHERE is_current = true LIMIT 1"
                    )
                )
            ).first()
            if row is None:
                # 可能 definitions 表为空
                def_count = (
                    await conn.execute(
                        sa.text("SELECT count(*) FROM procedure_row_definitions")
                    )
                ).scalar()
                if def_count == 0:
                    pytest.skip("definitions 表为空，backfill 无对象")
                # 有 definitions 但无 current → 全部歧义
                pending = (
                    await conn.execute(
                        sa.text(
                            "SELECT count(*) FROM procedure_template_revisions "
                            "WHERE status = 'reconcile_pending'"
                        )
                    )
                ).scalar()
                assert pending > 0, "有 definitions 却无 current 也无 reconcile_pending"
            else:
                assert row.status == "current"
                assert row.is_current is True

    async def test_backfill_multi_revision_marks_reconcile_pending(self, pg_engine):
        """回填逻辑：多 revision 标记 reconcile_pending 而不猜测。"""
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            # 查 reconcile_pending 的 detail
            rows = (
                await conn.execute(
                    sa.text(
                        "SELECT template_code, reconcile_detail "
                        "FROM procedure_template_revisions "
                        "WHERE status = 'reconcile_pending' LIMIT 5"
                    )
                )
            ).fetchall()
            for row in rows:
                detail = row.reconcile_detail
                if isinstance(detail, dict):
                    assert detail.get("reason") == "multiple_revisions_require_reconcile"
                    assert "revision_count" in detail
                    assert detail["revision_count"] > 1

    async def test_orm_db_zero_drift_v109_scope(self, pg_engine):
        """ORM ↔ DB V112 作用域零漂移。"""
        await _apply_migrations(pg_engine)
        async with pg_engine.connect() as conn:
            for table in ("procedure_template_revisions", "procedure_row_definition_revisions"):
                db_rows = await conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:t"
                    ),
                    {"t": table},
                )
                db_cols = set(r[0] for r in db_rows.fetchall())
                orm_cols = set(Base.metadata.tables[table].columns.keys())
                assert orm_cols <= db_cols, (
                    f"{table} ORM 列不在 DB: {sorted(orm_cols - db_cols)}"
                )
