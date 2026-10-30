"""V218 粗裁确认投影在随机 PostgreSQL schema 中的真实迁移 / 并发 / 查询计划测试（follow-up R3）。

- 回填与 Python 规则逐字段一致（含决定指纹：SQL ``jsonb_agg(...)::text`` 与 ``json.dumps`` 逐字节同算法），
  覆盖小写带空格循环、同一时间平局、未消费 / 委派 / 细裁行 / 损坏 JSON / 缺请求号的旧凭证；R218 只删投影；
- 预先存在与凭证不一致的投影行 ⇒ 回填自检 fail-closed，整份迁移回滚；
- 两个会话并发写同一循环：数据库行锁串行，结果与提交先后无关；
- 读确认只走投影主键、不碰预览凭证；共享库已消费凭证（只读复制进临时 schema）回填后与旧读法对拍一致。
所有建表 / 写入都在临时 schema 内，finally 删除；共享 public 只读。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

from app.models.procedure_models import ProcedureOperationPreview  # noqa: E402
from app.services import procedure_trim_confirmation as tc  # noqa: E402
from tests.pg_temp_schema import (  # noqa: E402
    MIGRATIONS,
    V217_PARENT_TABLES,
    create_v217_parents,
    run_sql_file,
    split_sql,
    table_names,
    temporary_schema,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.pg_only]

_V217 = MIGRATIONS / "V225__procedure_identity_and_trim_confirmation.sql"
_V218 = MIGRATIONS / "V218__procedure_trim_cycle_confirmations.sql"
_R218 = MIGRATIONS / "R218__rollback_procedure_trim_cycle_confirmations.sql"
_TABLE = "procedure_trim_cycle_confirmations"
T1 = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)
T2 = T1 + timedelta(hours=1)
TRICKY = '带"引号"\\反斜杠\n换行\t制表\x01控制 😀 é'

_INSERT_PREVIEW = sa.text("""
    INSERT INTO procedure_operation_previews (
        id, actor_user_id, project_id, operation, request_payload_snapshot, consumed_at, consumed_request_id
    ) VALUES (:id, :actor, :project, :operation, CAST(:snapshot AS jsonb), :consumed_at, :request_id)
""")


async def _parents(conn: AsyncConnection) -> None:
    await create_v217_parents(conn)
    await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN username VARCHAR(100)")
    await conn.exec_driver_sql("""
        CREATE TABLE staff_members (
            id UUID PRIMARY KEY, user_id UUID, name VARCHAR(100) NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT false, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def _scope(cycle, code, status="execute", reason=None) -> dict:
    entry = {"kind": "scope", "cycle": cycle, "wp_index_code": code, "target_status": status}
    if reason is not None:
        entry["skip_reason"] = reason
    return entry


def _pid(n: int) -> uuid.UUID:
    return uuid.UUID(int=n)


async def _seed(conn: AsyncConnection, previews: list[dict], users: dict[uuid.UUID, str], projects) -> None:
    for uid, name in users.items():
        await conn.execute(sa.text("INSERT INTO users (id, username) VALUES (:id, :n)"), {"id": uid, "n": name})
    for project in projects:
        await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:id)"), {"id": project})
    for p in previews:
        await conn.execute(_INSERT_PREVIEW, {**p, "snapshot": json.dumps(p["snapshot"], ensure_ascii=False)})


async def _python_view(engine) -> tuple[dict, list[tc.ConsumedPreview]]:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        return await tc.load_projection_rows(s), await tc.load_consumed_previews(s)


async def test_v218_backfill_matches_python_rule_byte_for_byte_and_r218_drops_only_projection() -> None:
    async with temporary_schema("tmp_v218_ok") as (engine, _schema):
        p1, p2, u1, u2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        row_entry = {"kind": "row", "template_code": "D2", "sheet_key": "程序表", "definition_key": "D2::程序表::x",
                     "target_applicability": "execute"}
        previews = [
            {"id": _pid(0x11), "actor": u1, "project": p1, "operation": "trim", "consumed_at": T1, "request_id": "r1",
             "snapshot": {"operation": "trim", "entries": [
                 _scope("D", "D2", "not_applicable", TRICKY), _scope("D", "D1"), _scope("A", "A1", "skip", "其他"),
                 row_entry]}},
            {"id": _pid(0x21), "actor": u2, "project": p1, "operation": "trim", "consumed_at": T2, "request_id": "r2",
             "snapshot": {"entries": [_scope(" d ", "D3")]}},
            {"id": _pid(0x22), "actor": u1, "project": p1, "operation": "trim", "consumed_at": T2, "request_id": "r3",
             "snapshot": {"entries": [_scope("D", "D4", "skip", "同一时间")]}},
            {"id": _pid(0x31), "actor": u1, "project": p1, "operation": "trim", "consumed_at": None,
             "request_id": None, "snapshot": {"entries": [_scope("E", "E1")]}},
            {"id": _pid(0x32), "actor": u1, "project": p1, "operation": "delegate", "consumed_at": T2,
             "request_id": "d1", "snapshot": {"entries": [_scope("F", "F1")]}},
            {"id": _pid(0x33), "actor": u1, "project": p1, "operation": "trim", "consumed_at": T2,
             "request_id": "row-only", "snapshot": {"entries": [row_entry]}},
            {"id": _pid(0x41), "actor": u2, "project": p2, "operation": "trim", "consumed_at": T1,
             "request_id": "bad-entries", "snapshot": {"entries": {"not": "a list"}}},
            {"id": _pid(0x42), "actor": u2, "project": p2, "operation": "trim", "consumed_at": T1,
             "request_id": "junk", "snapshot": {"entries": [
                 123, "scope", {"kind": "scope", "cycle": 5}, {"kind": "scope", "cycle": "   "},
                 {"kind": "scope", "cycle": "TOOLONGCYCLE1", "wp_index_code": "X1"},
                 {"kind": "scope", "cycle": "B", "wp_index_code": 7, "target_status": None,
                  "skip_reason": {"x": 1}}]}},
            {"id": _pid(0x43), "actor": u1, "project": p2, "operation": "trim", "consumed_at": T2,
             "request_id": None, "snapshot": {"entries": [_scope("C", "C1")]}},
        ]
        async with engine.begin() as conn:
            await _parents(conn)
            await _seed(conn, previews, {u1: "u_one", u2: "u_two"}, (p1, p2))
            await run_sql_file(conn, _V217)
            await run_sql_file(conn, _V218)

        actual, consumed = await _python_view(engine)
        assert actual == tc.expected_projection(consumed), "SQL 回填必须与 Python 规则逐字段一致（含决定指纹）"
        assert {k: (r.source_preview_id, r.revision_no, r.request_id) for k, r in actual.items()} == {
            (p1, "D"): (_pid(0x22), 3, "r3"),            # ' d ' 归一进 D；同一时间平局取凭证 id 大者
            (p1, "A"): (_pid(0x11), 1, "r1"),
            (p2, "B"): (_pid(0x42), 1, "junk"),          # 非字符串字段记空串
            (p2, "C"): (_pid(0x43), 1, f"legacy:{_pid(0x43)}"),
        }
        assert actual[(p2, "B")].cycle_revision_hash == tc.cycle_revision_hash([{}])
        # TRICKY 含引号 / 反斜杠 / 换行 / 制表 / 控制字符 / emoji：上面的逐字段相等已证明 SQL 与 Python 指纹同字节
        report = tc.compare_projection(actual, consumed)
        assert (report.missing, report.unexpected, report.field_mismatches) == ([], [], [])
        assert sorted(m[:2] for m in report.legacy_mismatches) == sorted(
            [(p1, " d "), (p2, "5"), (p2, "   "), (p2, "TOOLONGCYCLE1")]
        ), "旧读法不归一循环、不挑字段类型：只在这些损坏 / 非规范条目上与投影不同"

        async with engine.begin() as conn:
            await run_sql_file(conn, _R218)
            assert _TABLE not in await table_names(conn)
            assert await table_names(conn) == V217_PARENT_TABLES | {
                "staff_members", "procedure_instance_identity_v217_backup"}
            assert await conn.scalar(sa.text("SELECT count(*) FROM procedure_operation_previews")) == len(previews)
            await run_sql_file(conn, _V218)  # 回滚后重放：同样的结果
        again, _ = await _python_view(engine)
        assert again == actual


async def test_v218_self_check_rolls_back_when_existing_rows_disagree() -> None:
    async with temporary_schema("tmp_v218_check") as (engine, _schema):
        p1, u1, u2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await _parents(conn)
            await _seed(conn, [{"id": _pid(1), "actor": u1, "project": p1, "operation": "trim", "consumed_at": T1,
                                "request_id": "r1", "snapshot": {"entries": [_scope("D", "D1")]}}],
                        {u1: "u_one", u2: "u_two"}, (p1,))
            await run_sql_file(conn, _V217)
            create_table = split_sql(_V218)[0]
            assert f"CREATE TABLE IF NOT EXISTS {_TABLE}" in create_table
            await conn.exec_driver_sql(create_table)
            await conn.execute(sa.text(f"""
                INSERT INTO {_TABLE} (project_id, audit_cycle, source_preview_id, confirmed_by, confirmed_at,
                                      request_id, cycle_revision_hash, revision_no)
                VALUES (:p, 'D', :src, :wrong_actor, :at, 'r1', repeat('0', 64), 1)
            """), {"p": p1, "src": _pid(1), "wrong_actor": u2, "at": T1})

        with pytest.raises(sa.exc.DBAPIError) as exc_info:
            async with engine.begin() as conn:
                await run_sql_file(conn, _V218)
        assert "trim cycle confirmation rows differ from consumed previews" in str(exc_info.value)
        async with engine.connect() as conn:
            rows = (await conn.execute(sa.text(f"SELECT confirmed_by FROM {_TABLE}"))).all()
        assert rows == [(u2,)], "迁移整份回滚：预先存在的行原样保留，没有被改写或补插"


async def test_concurrent_writers_converge_regardless_of_commit_order() -> None:
    async with temporary_schema("tmp_v218_race") as (engine, _schema):
        p1, u1, u2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        rows = [
            {"id": _pid(10), "actor": u1, "project": p1, "operation": "trim", "consumed_at": T1, "request_id": "old",
             "snapshot": {"entries": [_scope("D", "D1"), _scope("A", "A1")]}},
            {"id": _pid(20), "actor": u2, "project": p1, "operation": "trim", "consumed_at": T2, "request_id": "new",
             "snapshot": {"entries": [_scope("D", "D2", "skip", "并发"), _scope("A", "A2")]}},
        ]
        async with engine.begin() as conn:
            await _parents(conn)
            await _seed(conn, rows, {u1: "u_one", u2: "u_two"}, (p1,))
            await run_sql_file(conn, _V217)
            await run_sql_file(conn, _V218)
            await conn.execute(sa.text(f"DELETE FROM {_TABLE}"))  # 从空投影开始，两个会话同时第一次写

        def _preview(r) -> ProcedureOperationPreview:
            return ProcedureOperationPreview(
                id=r["id"], actor_user_id=r["actor"], project_id=r["project"], operation="trim",
                request_payload_snapshot=r["snapshot"], consumed_at=r["consumed_at"], consumed_request_id=r["request_id"])

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        for first, second in ((rows[1], rows[0]), (rows[0], rows[1])):
            async with factory() as s1, factory() as s2:
                await tc.record_confirmations(s1, _preview(first))
                pending = asyncio.create_task(tc.record_confirmations(s2, _preview(second)))
                await asyncio.sleep(0.2)
                assert not pending.done(), "第二个会话应等第一个会话的主键行锁"
                await s1.commit()
                await pending
                await s2.commit()
            actual, consumed = await _python_view(engine)
            assert {k[1]: (r.source_preview_id, r.revision_no) for k, r in actual.items()} == {
                "D": (_pid(20), 2), "A": (_pid(20), 2)}, "较新的凭证胜出，与谁先提交无关"
            assert actual == tc.expected_projection(consumed)
            async with engine.begin() as conn:
                await conn.execute(sa.text(f"DELETE FROM {_TABLE}"))


async def test_projection_read_uses_primary_key_and_never_touches_previews() -> None:
    async with temporary_schema("tmp_v218_plan") as (engine, _schema):
        target, u1, u2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with engine.begin() as conn:
            await _parents(conn)
            await _seed(conn, [], {u1: "u_one", u2: "u_two"}, (target,))
            await conn.execute(sa.text("INSERT INTO staff_members (id, user_id, name) VALUES (:i, :u, '王经理')"),
                               {"i": uuid.uuid4(), "u": u1})
            await run_sql_file(conn, _V217)
            await run_sql_file(conn, _V218)
            await conn.exec_driver_sql("ALTER TABLE procedure_trim_cycle_confirmations "
                                       "DROP CONSTRAINT procedure_trim_cycle_confirmations_project_id_fkey")
            await conn.exec_driver_sql("ALTER TABLE procedure_trim_cycle_confirmations "
                                       "DROP CONSTRAINT procedure_trim_cycle_confirmations_source_preview_id_fkey")
            await conn.execute(sa.text(f"""
                INSERT INTO {_TABLE} (project_id, audit_cycle, source_preview_id, confirmed_by, confirmed_at,
                                      request_id, cycle_revision_hash, revision_no)
                SELECT CASE WHEN g <= 3 THEN CAST(:target AS uuid) ELSE gen_random_uuid() END,
                       chr(64 + (g % 20) + 1), gen_random_uuid(), CASE WHEN g % 2 = 0 THEN CAST(:u1 AS uuid)
                       ELSE CAST(:u2 AS uuid) END, :at, 'r', repeat('0', 64), 1
                FROM generate_series(1, 2000) AS g
            """), {"target": target, "u1": u1, "u2": u2, "at": T1})
            await conn.exec_driver_sql(f"ANALYZE {_TABLE}")

        captured: list[tuple[str, tuple]] = []

        def _capture(_conn, _cursor, statement, parameters, *_args):
            captured.append((statement, parameters))

        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        event.listen(engine.sync_engine, "before_cursor_execute", _capture)
        try:
            async with factory() as s:
                out = await tc.load_projection(s, target)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", _capture)
        assert {c: v["confirmed_by"] for c, v in out.items()} == {"B": "u_two", "C": "王经理", "D": "u_two"}
        selects = [(st, params) for st, params in captured if _TABLE in st]
        assert len(selects) == 1 and not [st for st, _ in captured if "procedure_operation_previews" in st]
        statement, parameters = selects[0]
        async with engine.connect() as conn:
            await conn.exec_driver_sql("SET enable_seqscan = off")
            plan = await conn.exec_driver_sql(f"EXPLAIN (FORMAT JSON) {statement}", parameters)
            text_plan = json.dumps(plan.scalar())
        assert "procedure_trim_cycle_confirmations_pkey" in text_plan, text_plan


async def test_shared_db_consumed_previews_backfill_agrees_with_legacy_scan() -> None:
    """共享库已消费的粗裁凭证只读复制进临时 schema，跑真实 V225（身份约束，原 V217）+ V218，与旧读法逐循环对拍。"""
    async with temporary_schema("tmp_v218_real") as (engine, _schema):
        async with engine.begin() as conn:
            await _parents(conn)
            await conn.exec_driver_sql("""
                INSERT INTO users (id, username)
                SELECT u.id, u.username FROM public.users AS u
                WHERE u.id IN (SELECT actor_user_id FROM public.procedure_operation_previews WHERE operation = 'trim')
            """)
            await conn.exec_driver_sql("""
                INSERT INTO projects (id)
                SELECT DISTINCT project_id FROM public.procedure_operation_previews WHERE operation = 'trim'
            """)
            await conn.exec_driver_sql("""
                INSERT INTO procedure_operation_previews (
                    id, actor_user_id, project_id, operation, request_payload_snapshot, consumed_at, consumed_request_id)
                SELECT id, actor_user_id, project_id, operation, request_payload_snapshot, consumed_at,
                       consumed_request_id
                FROM public.procedure_operation_previews WHERE operation = 'trim'
            """)
            await run_sql_file(conn, _V217)
            await run_sql_file(conn, _V218)
        actual, consumed = await _python_view(engine)
        report = tc.compare_projection(actual, consumed)
        assert report.ok, report
        assert report.projection_rows == report.expected_rows == len(tc.legacy_scan_candidates(consumed))
        if any(tc.scope_entries_by_cycle(tc.snapshot_entries(p.snapshot)) for p in consumed):
            assert report.projection_rows > 0, "共享库有已消费的粗裁凭证，回填不应为空"
