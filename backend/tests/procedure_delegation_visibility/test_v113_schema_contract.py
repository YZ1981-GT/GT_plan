# Feature: procedure-delegation-visibility-isolation — Task 2 V113 schema contract
"""V113（统一委派历史、安全审计 outbox、持久 policy epoch/invalidation outbox）迁移契约测试。

Task 2 / Requirements 3.13-3.15, 5.18, 9.8-9.11, 14.20-14.21：

两层验证，且**不把 `IF NOT EXISTS` 当结构正确性证明**：

1. 静态单元（无需 PG）：
   - V113/R113 迁移文件存在；幂等守护（CREATE TABLE/INDEX IF NOT EXISTS、
     CREATE OR REPLACE FUNCTION/TRIGGER）；append-only 触发器声明；
     reason CHECK 枚举含全部 10 值（含 rate_limited）；invalidation change_type CHECK；
     epoch 单调触发器；migration head 重扫（V113 = 下一空闲版本，不静态占用）。
   - 4 张 ORM 模型登记到 Base.metadata；append-only 表不带 updated_at；epoch=BIGINT。

2. PostgreSQL 集成（不可达则 skip）——information_schema / pg_catalog 精校：
   - 4 张表列类型/nullable/FK 目标；reason/change_type CHECK 生效；
   - append-only 触发器：history 与两 outbox 的 UPDATE/DELETE 被拒（'55000'），
     维护逃生舱 `SET LOCAL app.wp_visibility_maintenance='on'` 放行；
   - policy epoch 单调：递减被拒、递增允许；
   - 权限变更事务原子递增 epoch + 写 invalidation row（Req 14.20）；
   - 迁移幂等（连跑两次不漂移）；
   - R113 事务内回滚（PG DDL 事务性，drop 后 ROLLBACK 恢复，不污染 dev 库）；
   - ORM ↔ DB Task 2 作用域零漂移。

Validates: Requirements 3.13-3.15, 5.18, 9.8-9.11, 14.20-14.21
"""
from __future__ import annotations

import asyncio
import random
import re
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.migration_runner import MigrationRunner
from app.models.base import Base

# 触发 ORM 注册
import app.models.wp_visibility_models  # noqa: F401
import app.models.core  # noqa: F401

_MIG_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
_V113 = _MIG_DIR / "V113__wp_visibility_delegation_history_audit_epoch.sql"
_R113 = _MIG_DIR / "R113__rollback_wp_visibility_delegation_history_audit_epoch.sql"
_IS_PG = settings.DATABASE_URL.startswith("postgresql")

_NEW_TABLES = (
    "workpaper_delegation_history",
    "wp_access_security_outbox",
    "wp_visibility_policy_epoch",
    "wp_visibility_invalidation_outbox",
)

_APPEND_ONLY_TABLES = (
    "workpaper_delegation_history",
    "wp_access_security_outbox",
    "wp_visibility_invalidation_outbox",
)

_REASON_ENUM = (
    "not_found", "cross_project", "out_of_scope", "not_delegated", "sheet_unmapped",
    "action_denied", "historical_version", "binding_conflict", "token_invalid", "rate_limited",
)


# ---------------------------------------------------------------------------
# DDL 锁竞争拆环（全库并行收集下的测试隔离修复）
#
# 本文件的 DDL（DROP/CREATE TABLE、DROP/CREATE TRIGGER、CREATE OR REPLACE FUNCTION）对 V113
# 的四张表取 AccessExclusiveLock/ShareRowExclusiveLock；而同目录的委派/缺口 PBT（Task 7/14）
# 逐 example 向这四张表及其 FK 父表 INSERT，持 RowExclusive/RowShareLock。二者共用同一 dev 库
# （audit_platform），单独/成对跑不冲突，但全库收集时会在极短窗口内交叠 → PostgreSQL 死锁。
#
# 修复（不隐藏、不放宽任何断言）：给所有 DDL 事务设 lock_timeout < 默认 deadlock_timeout(1s)，
# 使 DDL 在死锁检测触发前先以 LockNotAvailable 主动让路并回滚，从而在成环前拆环（DML 侧因此
# 不会被选为牺牲者）；随后带抖动重试。迁移语义仍被后续 information_schema/pg_catalog 断言完整
# 校验；R113 事务性（drop 后 ROLLBACK 恢复）亦不变。
# ---------------------------------------------------------------------------
_DDL_LOCK_TIMEOUT_MS = 800      # < 1000ms（PG 默认 deadlock_timeout）→ 成环前先超时让路
_DDL_MAX_ATTEMPTS = 8
_TRANSIENT_LOCK_SQLSTATES = {"40P01", "55P03", "40001"}
_TRANSIENT_LOCK_TEXT = (
    "deadlock detected", "locknotavailable", "lock timeout",
    "canceling statement due to lock timeout",
)


def _is_transient_lock_error(exc: BaseException) -> bool:
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        code = getattr(cur, "sqlstate", None) or getattr(cur, "pgcode", None)
        if code in _TRANSIENT_LOCK_SQLSTATES:
            return True
        text = f"{type(cur).__name__}: {cur}".lower()
        if any(t in text for t in _TRANSIENT_LOCK_TEXT):
            return True
        cur = getattr(cur, "orig", None) or getattr(cur, "__cause__", None)
    return False


async def _exec_ddl_with_retry(engine, statements: list[str]) -> None:
    """在带 lock_timeout 的自动提交事务内顺序执行 DDL；瞬时锁竞争则回滚重试。"""
    for attempt in range(_DDL_MAX_ATTEMPTS):
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql(f"SET LOCAL lock_timeout = '{_DDL_LOCK_TIMEOUT_MS}ms'")
                for stmt in statements:
                    await conn.exec_driver_sql(stmt)
            return
        except Exception as exc:  # noqa: BLE001
            if _is_transient_lock_error(exc) and attempt < _DDL_MAX_ATTEMPTS - 1:
                await asyncio.sleep(0.15 * (attempt + 1) + random.random() * 0.1)
                continue
            raise


async def _apply_sql_file(engine, path: Path) -> None:
    statements = MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8"))
    assert statements, f"{path.name} 解析出的语句为空"
    await _exec_ddl_with_retry(engine, statements)


@pytest_asyncio.fixture
async def pg_engine():
    if not _IS_PG:
        pytest.skip("need PostgreSQL (V113 schema contract)")
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True, echo=False,
                                 connect_args={"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {})
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
class TestV113MigrationStatic:
    def test_migration_and_rollback_files_exist(self):
        assert _V113.is_file(), "V113 迁移缺失"
        assert _R113.is_file(), "R113 回滚脚本缺失"

    def test_migration_head_rescanned_next_free_version(self):
        """迁移 head 重扫：V113 是下一空闲版本，不存在 V113 之外更高版本占位。"""
        versions = sorted(
            int(m.group(1))
            for f in _MIG_DIR.iterdir()
            if (m := re.match(r"^V(\d+)__.*\.sql$", f.name, re.IGNORECASE))
        )
        assert 113 in versions, "V113 未登记"
        assert max(versions) == 113, f"存在高于 V113 的迁移，head 需重扫: max={max(versions)}"
        # 连续无缺口到 113（重扫确认 head=112 → 下一空闲=113）
        assert 112 in versions and 113 in versions

    def test_idempotent_guards_present(self):
        content = _V113.read_text(encoding="utf-8")
        for tbl in _NEW_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {tbl}" in content, f"{tbl} 非幂等建表"
        assert "CREATE OR REPLACE FUNCTION wp_visibility_forbid_mutation()" in content
        assert "CREATE OR REPLACE FUNCTION wp_visibility_epoch_monotonic()" in content

    def test_append_only_triggers_declared(self):
        content = _V113.read_text(encoding="utf-8")
        for tbl in _APPEND_ONLY_TABLES:
            assert re.search(
                rf"CREATE TRIGGER \w+\s+BEFORE UPDATE OR DELETE ON {tbl}\s+"
                rf"FOR EACH ROW EXECUTE FUNCTION wp_visibility_forbid_mutation\(\)",
                content,
            ), f"{tbl} 缺 append-only BEFORE UPDATE OR DELETE 触发器"
        # policy epoch 用单调触发器（BEFORE UPDATE），非 append-only
        assert re.search(
            r"CREATE TRIGGER \w+\s+BEFORE UPDATE ON wp_visibility_policy_epoch\s+"
            r"FOR EACH ROW EXECUTE FUNCTION wp_visibility_epoch_monotonic\(\)",
            content,
        ), "policy_epoch 缺单调触发器"

    def test_reason_enum_check_has_all_values_incl_rate_limited(self):
        content = _V113.read_text(encoding="utf-8")
        assert "ck_wp_access_security_outbox_reason" in content
        for val in _REASON_ENUM:
            assert f"'{val}'" in content, f"security outbox reason 枚举缺 {val}"
        assert "'rate_limited'" in content, "reason 枚举必须含 rate_limited"

    def test_invalidation_change_type_check(self):
        content = _V113.read_text(encoding="utf-8")
        assert "ck_wp_visibility_invalidation_change_type" in content
        for val in ("permission", "delegation", "history", "scope", "role", "membership"):
            assert f"'{val}'" in content

    def test_no_sensitive_columns_declared(self):
        """敏感正文/token/文件字节不入表：4 张表 ORM 列名不得含敏感语义（按列名精确判定，
        不扫注释文本，避免把说明性文字误判）。"""
        forbidden_substrings = (
            "token", "prompt", "file_bytes", "raw_body", "content_body",
            "traceback", "secret", "password", "payload_body",
        )
        for tbl in _NEW_TABLES:
            for col in Base.metadata.tables[tbl].columns.keys():
                low = col.lower()
                for bad in forbidden_substrings:
                    assert bad not in low, f"{tbl}.{col} 疑似敏感列（含 {bad}）"

    def test_orm_models_registered(self):
        registered = set(Base.metadata.tables.keys())
        missing = set(_NEW_TABLES) - registered
        assert not missing, f"V113 ORM 表未登记: {sorted(missing)}"

    def test_append_only_orm_has_no_updated_at(self):
        """append-only 表 ORM 不带 updated_at（DB 无此列，避免 orm_extra 漂移）。"""
        for tbl in _APPEND_ONLY_TABLES:
            cols = set(Base.metadata.tables[tbl].columns.keys())
            assert "updated_at" not in cols, f"{tbl} 不应有 updated_at"
            assert "created_at" in cols, f"{tbl} 应有 created_at"

    def test_epoch_column_is_bigint(self):
        for tbl in ("wp_visibility_policy_epoch", "wp_visibility_invalidation_outbox"):
            col = Base.metadata.tables[tbl].columns["epoch"]
            assert "BIGINT" in str(col.type).upper(), f"{tbl}.epoch 应为 BIGINT，实际 {col.type}"

    def test_rollback_only_drops_v113_objects(self):
        content = _R113.read_text(encoding="utf-8")
        for tbl in _NEW_TABLES:
            assert f"DROP TABLE IF EXISTS {tbl}" in content, f"R113 未 drop {tbl}"
        assert "DROP FUNCTION IF EXISTS wp_visibility_forbid_mutation()" in content
        assert "DROP FUNCTION IF EXISTS wp_visibility_epoch_monotonic()" in content
        # 不得误删非 V113 对象
        assert "procedure_row_task" not in content
        assert "TRUNCATE" not in content.upper()


# ---------------------------------------------------------------------------
# 2. PostgreSQL 集成契约
# ---------------------------------------------------------------------------
async def _columns(conn, table: str) -> dict[str, dict]:
    rows = await conn.execute(
        sa.text(
            "SELECT column_name, data_type, is_nullable, character_maximum_length "
            "FROM information_schema.columns WHERE table_schema='public' AND table_name=:t"
        ),
        {"t": table},
    )
    return {r[0]: {"type": r[1], "nullable": r[2] == "YES", "maxlen": r[3]} for r in rows.fetchall()}


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


async def _reuse_ids(conn):
    """复用已有 project/wp_index/user 供 FK，若缺则 skip。"""
    row = (
        await conn.execute(
            sa.text(
                "SELECT p.id, wi.id FROM projects p "
                "JOIN wp_index wi ON wi.project_id = p.id LIMIT 1"
            )
        )
    ).first()
    uid = (await conn.execute(sa.text("SELECT id FROM users LIMIT 1"))).scalar()
    if row is None or uid is None:
        pytest.skip("dev 库无 project+wp_index+user 可复用于行为测试")
    return row[0], row[1], uid


@pytest.mark.asyncio
class TestV113PgContract:
    async def test_apply_is_idempotent_and_tables_exist(self, pg_engine):
        await _apply_sql_file(pg_engine, _V113)
        await _apply_sql_file(pg_engine, _V113)  # 幂等：第二次不得抛错
        async with pg_engine.connect() as conn:
            for tbl in _NEW_TABLES:
                reg = (await conn.execute(sa.text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"})).scalar()
                assert reg is not None, f"V113 未建成表: {tbl}"

    async def test_history_columns_and_fk(self, pg_engine):
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            cols = await _columns(conn, "workpaper_delegation_history")
            fks = await _fks(conn, "workpaper_delegation_history")
        assert cols["project_id"]["nullable"] is False
        assert cols["wp_index_id"]["nullable"] is False
        assert cols["wp_id"]["nullable"] is True                    # 底稿可能未生成
        assert cols["layer"]["nullable"] is False
        assert cols["target_role"]["nullable"] is False
        assert cols["actor_user_id"]["nullable"] is False
        assert cols["sheet_key"]["nullable"] is True                # lead 层整稿
        assert cols["new_user_id"]["nullable"] is True
        assert cols["scope_before"]["type"] == "jsonb"
        assert cols["scope_after"]["type"] == "jsonb"
        assert fks["project_id"] == ("projects", "id")
        assert fks["wp_index_id"] == ("wp_index", "id")
        assert fks["wp_id"] == ("working_paper", "id")
        assert fks["task_id"] == ("procedure_row_tasks", "id")
        assert fks["actor_user_id"] == ("users", "id")
        assert fks["new_staff_id"] == ("staff_members", "id")

    async def test_security_outbox_columns_and_reason_check(self, pg_engine):
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            cols = await _columns(conn, "wp_access_security_outbox")
        assert cols["entrypoint"]["nullable"] is False
        assert cols["reason"]["nullable"] is False
        assert cols["project_id"]["nullable"] is True              # 可空绑定
        assert cols["wp_id"]["nullable"] is True
        assert cols["delivery_state"]["type"] == "character varying"
        assert cols["detail"]["type"] == "jsonb"

    async def test_reason_check_rejects_unknown_and_accepts_rate_limited(self, pg_engine):
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                # 非法 reason 被 CHECK 拒绝
                rejected = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(sa.text(
                            "INSERT INTO wp_access_security_outbox (entrypoint, reason) "
                            "VALUES ('e', 'bogus_reason')"
                        ))
                except Exception:
                    rejected = True
                assert rejected, "reason CHECK 未拒绝非法值"
                # 合法 rate_limited 通过
                await conn.execute(sa.text(
                    "INSERT INTO wp_access_security_outbox (entrypoint, reason) "
                    "VALUES ('e', 'rate_limited')"
                ))
            finally:
                await trans.rollback()

    async def test_epoch_and_invalidation_columns(self, pg_engine):
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            ep = await _columns(conn, "wp_visibility_policy_epoch")
            inv = await _columns(conn, "wp_visibility_invalidation_outbox")
            ep_fk = await _fks(conn, "wp_visibility_policy_epoch")
        assert ep["project_id"]["nullable"] is False
        assert ep["epoch"]["type"] == "bigint"
        assert "updated_at" in ep and "created_at" not in ep
        assert ep_fk["project_id"] == ("projects", "id")
        assert inv["epoch"]["type"] == "bigint"
        assert inv["change_type"]["nullable"] is False

    async def test_append_only_triggers_block_update_and_delete(self, pg_engine):
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                project_id, wp_index_id, uid = await _reuse_ids(conn)
                # history 插入一行
                hid = (await conn.execute(
                    sa.text(
                        "INSERT INTO workpaper_delegation_history "
                        "(project_id, wp_index_id, layer, target_role, action, actor_user_id) "
                        "VALUES (:p, :w, 'lead', 'lead', 'assign', :u) RETURNING id"
                    ),
                    {"p": project_id, "w": wp_index_id, "u": uid},
                )).scalar()

                for op_sql, label in (
                    (sa.text("UPDATE workpaper_delegation_history SET reason='x' WHERE id=:i"), "UPDATE"),
                    (sa.text("DELETE FROM workpaper_delegation_history WHERE id=:i"), "DELETE"),
                ):
                    blocked = False
                    try:
                        async with conn.begin_nested():
                            await conn.execute(op_sql, {"i": hid})
                    except Exception as exc:  # noqa: BLE001
                        blocked = True
                        assert "append-only" in str(exc).lower()
                    assert blocked, f"append-only 未拦截 history {label}"

                # 维护逃生舱放行 DELETE
                async with conn.begin_nested():
                    await conn.execute(sa.text("SET LOCAL app.wp_visibility_maintenance = 'on'"))
                    await conn.execute(sa.text("DELETE FROM workpaper_delegation_history WHERE id=:i"), {"i": hid})
                    gone = (await conn.execute(
                        sa.text("SELECT count(*) FROM workpaper_delegation_history WHERE id=:i"), {"i": hid}
                    )).scalar()
                    assert gone == 0, "维护逃生舱未放行 DELETE"
            finally:
                await trans.rollback()

    async def test_outbox_tables_are_append_only(self, pg_engine):
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                project_id, _wp_index_id, _uid = await _reuse_ids(conn)
                sid = (await conn.execute(sa.text(
                    "INSERT INTO wp_access_security_outbox (entrypoint, reason) "
                    "VALUES ('e', 'not_found') RETURNING id"
                ))).scalar()
                blocked = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(sa.text(
                            "UPDATE wp_access_security_outbox SET delivery_state='done' WHERE id=:i"
                        ), {"i": sid})
                except Exception:
                    blocked = True
                assert blocked, "security outbox 允许了 UPDATE（应 append-only）"

                iid = (await conn.execute(sa.text(
                    "INSERT INTO wp_visibility_invalidation_outbox (project_id, epoch, change_type) "
                    "VALUES (:p, 5, 'delegation') RETURNING id"
                ), {"p": project_id})).scalar()
                blocked = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(sa.text(
                            "DELETE FROM wp_visibility_invalidation_outbox WHERE id=:i"
                        ), {"i": iid})
                except Exception:
                    blocked = True
                assert blocked, "invalidation outbox 允许了 DELETE（应 append-only）"
            finally:
                await trans.rollback()

    async def test_policy_epoch_monotonic_and_atomic_increment(self, pg_engine):
        """Req 14.20：权限变更事务原子递增 epoch + 写 invalidation row；epoch 单调非递减。"""
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            trans = await conn.begin()
            try:
                project_id, _wp_index_id, uid = await _reuse_ids(conn)
                # 同事务：upsert epoch=1 → 递增到 2 + 写 invalidation row
                await conn.execute(sa.text(
                    "INSERT INTO wp_visibility_policy_epoch (project_id, epoch) VALUES (:p, 1) "
                    "ON CONFLICT (project_id) DO UPDATE SET epoch = wp_visibility_policy_epoch.epoch + 1, updated_at = now()"
                ), {"p": project_id})
                new_epoch = (await conn.execute(sa.text(
                    "UPDATE wp_visibility_policy_epoch SET epoch = epoch + 1, updated_at = now() "
                    "WHERE project_id = :p RETURNING epoch"
                ), {"p": project_id})).scalar()
                await conn.execute(sa.text(
                    "INSERT INTO wp_visibility_invalidation_outbox (project_id, epoch, change_type, actor_user_id) "
                    "VALUES (:p, :e, 'permission', :u)"
                ), {"p": project_id, "e": new_epoch, "u": uid})
                inv_cnt = (await conn.execute(sa.text(
                    "SELECT count(*) FROM wp_visibility_invalidation_outbox WHERE project_id=:p AND epoch=:e"
                ), {"p": project_id, "e": new_epoch})).scalar()
                assert inv_cnt == 1, "epoch 递增未原子写 invalidation row"

                # 递减被单调触发器拒绝
                blocked = False
                try:
                    async with conn.begin_nested():
                        await conn.execute(sa.text(
                            "UPDATE wp_visibility_policy_epoch SET epoch = epoch - 5 WHERE project_id=:p"
                        ), {"p": project_id})
                except Exception as exc:  # noqa: BLE001
                    blocked = True
                    assert "单调" in str(exc) or "monotonic" in str(exc).lower()
                assert blocked, "epoch 单调触发器未拦截递减"
            finally:
                await trans.rollback()

    async def test_rollback_r113_transactional(self, pg_engine):
        """R113 事务内回滚：PG DDL 事务性，drop 后 ROLLBACK 恢复，不污染 dev 库。

        DROP TABLE 取 AccessExclusiveLock，全库并行下会与并发 INSERT 竞争；此处以
        lock_timeout(<deadlock_timeout) 在成环前主动让路 + 重试拆环（不放宽 DDL 事务性断言）。
        """
        await _apply_sql_file(pg_engine, _V113)
        drop_stmts = MigrationRunner._split_sql_statements(_R113.read_text(encoding="utf-8"))

        async def _drop_verify_and_rollback() -> None:
            async with pg_engine.connect() as conn:
                trans = await conn.begin()
                try:
                    await conn.exec_driver_sql(
                        f"SET LOCAL lock_timeout = '{_DDL_LOCK_TIMEOUT_MS}ms'"
                    )
                    for stmt in drop_stmts:
                        await conn.exec_driver_sql(stmt)
                    # 事务内：表已 drop
                    for tbl in _NEW_TABLES:
                        reg = (await conn.execute(sa.text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"})).scalar()
                        assert reg is None, f"R113 未 drop {tbl}"
                finally:
                    await trans.rollback()  # DDL 事务性：drop 全部撤销

        # 瞬时锁竞争则整体重试（drop 已回滚，天然幂等）；断言失败照常向上抛。
        for attempt in range(_DDL_MAX_ATTEMPTS):
            try:
                await _drop_verify_and_rollback()
                break
            except Exception as exc:  # noqa: BLE001
                if _is_transient_lock_error(exc) and attempt < _DDL_MAX_ATTEMPTS - 1:
                    await asyncio.sleep(0.15 * (attempt + 1) + random.random() * 0.1)
                    continue
                raise

        # 回滚后：表恢复
        async with pg_engine.connect() as conn2:
            for tbl in _NEW_TABLES:
                reg = (await conn2.execute(sa.text("SELECT to_regclass(:t)"), {"t": f"public.{tbl}"})).scalar()
                assert reg is not None, f"ROLLBACK 后 {tbl} 未恢复"

    async def test_orm_db_zero_drift_for_task2_scope(self, pg_engine):
        """ORM ↔ DB Task 2 作用域零漂移：ORM 列与 DB 列完全一致（无 orm_extra / db_extra）。"""
        await _apply_sql_file(pg_engine, _V113)
        async with pg_engine.connect() as conn:
            for table in _NEW_TABLES:
                db_cols = set((await _columns(conn, table)).keys())
                orm_cols = set(Base.metadata.tables[table].columns.keys())
                assert orm_cols == db_cols, (
                    f"{table} ORM↔DB 列不一致 "
                    f"orm_extra={sorted(orm_cols - db_cols)} db_extra={sorted(db_cols - orm_cols)}"
                )
