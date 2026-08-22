# Feature: dsh-agent-panel-integration — Task 3 AI chat 持久化模型与并发约束行为守卫
"""AI chat 持久化模型、并发幂等与 history 顺序/元数据的行为守卫。

Requirements: 4.10, 4.11, 7.3, 8.2, 8.3
Properties:
  - **Property 6（会话与 Run 并发幂等）**：100 个并发相同 session key 的首次请求最终只
    产生一个 session；100 个相同 idempotency key 请求只产生一个 run、一条 user message
    和一次 engine invocation。
    **Validates: Requirements 4.6, 4.11**
  - **Property 10（最近历史顺序与元数据完整）**：history 对超过 N 条消息的会话返回最近
    N 条并按时间正序，且每条包含真实 ID、run status、engine、citations 与已有 usage
    metadata。
    **Validates: Requirements 4.10**
  - **Property 21（项目笔记并发幂等）**：同一 note idempotency key 的并发请求只创建一个
    folder/document/receipt；保存内容来自服务端 messages，并包含 run/message/citation/
    hash 溯源。
    **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

判据一律落在**真实执行**上：真实 PG 唯一索引、真实并发（100 个 asyncio task 各持独立
连接与独立事务，真提交真回滚）、真实 SQL 语句流、真实 CHECK/外键定义与真实 history
返回值。不使用"源码里出现 ON CONFLICT"之类字符存在判据。

## 两类夹具，各自的理由

- **回滚型**（``_fixtures.run_with_fixture``）：单事务内插入 + 整体回滚，用于顺序性、
  语句流、约束触发等不需要跨连接可见性的判据。复用 Task 1 的共享夹具。
- **提交型**（``_concurrency_and_schema_snapshot``）：并发幂等**必须**跨连接，未提交的
  行对其他连接不可见 ⇒ 只能真写真提交。因此本文件对 dev 库有真实写入，并在 ``finally``
  分**独立事务**逐步清理（一个事务里全清，任一步失败会把前面的清理一起回滚）。
  🔴 全部快照在**一次** ``asyncio.run`` 内取完：每个测试各自 ``asyncio.run`` 会污染
  共享连接池（第二个起报 ``NoneType has no attribute send``）。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import settings as app_settings
from app.models.ai_models import (
    AIChatActionReceipt,
    AIChatAttachment,
    AIChatMessage,
    AIChatRun,
    AIChatSession,
    ActionReceiptStatus,
    ActionReceiptType,
    AttachmentOcrStatus,
    ChatEngineName,
    ChatMessageStatus,
    ChatRunStatus,
    ChatToolCallStatus,
)
from app.models.base import UserRole
from app.models.core import Project, User
from app.services.ai_chat.contracts import GLOBAL_KNOWLEDGE_HOST_ID, HostType
from app.services.ai_chat.persistence import (
    NO_PROJECT_SENTINEL,
    NO_YEAR_SENTINEL,
    SESSION_KEY_VERSION,
    build_session_key,
    claim_action_receipt,
    content_hash,
    load_recent_history,
    settle_action_receipt,
    upsert_run,
    upsert_session,
)
from app.services.ai_chat.persistence import append_message as persist_append_message
from app.services import doc_chat_persistence

from ._fixtures import IS_PG, AccessFixture, run_with_fixture

pytestmark = pytest.mark.skipif(not IS_PG, reason="need PostgreSQL (AI chat 持久化约束)")

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    REPO_ROOT
    / "backend"
    / "migrations"
    / "V147__ai_chat_persistence_runs_and_session_key.sql"
)

#: 并发规模（Property 6 明确要求 100）。
CONCURRENCY = 100

#: history 判据用的消息总数与取数上限（12 > 5 ⇒ 最早 5 条与最近 5 条**互斥**，
#: 于是"取最早 N 条"的旧实现必然打红，而不是碰巧通过）。
HISTORY_TOTAL = 12
HISTORY_LIMIT = 5


# ---------------------------------------------------------------------------
# 提交型快照：100 并发 × 3 场景 + 真实 schema 结构，一次 asyncio.run 取完
# ---------------------------------------------------------------------------


def _extract_balanced(source: str, start_token: str) -> str:
    """从 ``start_token`` 起按圆括号配对截取完整表达式。

    🔴 不用固定字符窗口：迁移里的表达式跨多行、含嵌套函数调用，窗口截断会得到
    语法不完整的片段并让判据变成"能不能解析"而不是"值是否一致"。
    """
    i = source.index(start_token)
    depth = 0
    for j in range(i, len(source)):
        ch = source[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return source[i : j + 1]
    raise AssertionError(f"括号未配对，无法截取 {start_token!r} 表达式")


async def _run_concurrency(engine, session_id_holder: dict[str, Any]) -> dict[str, Any]:
    """三个 100 并发场景，各自独立连接/事务，真提交。"""
    user_id = session_id_holder["user_id"]
    project_id = session_id_holder["project_id"]
    host_id = session_id_holder["host_id"]
    audit_year = 2025

    # ── 场景 A：100 个并发相同 session key 的首次创建 ──────────────────────
    async def _one_session(_i: int) -> bool:
        async with AsyncSession(bind=engine) as db:
            _, created = await upsert_session(
                db,
                user_id=user_id,
                project_id=project_id,
                audit_year=audit_year,
                host_type=HostType.workpaper,
                host_id=host_id,
            )
            await db.commit()
            return created

    session_created_flags = await asyncio.gather(
        *[_one_session(i) for i in range(CONCURRENCY)]
    )

    key = build_session_key(
        user_id=user_id,
        project_id=project_id,
        audit_year=audit_year,
        host_type=HostType.workpaper,
        host_id=host_id,
    )
    async with engine.begin() as conn:
        session_rows = (
            await conn.execute(
                sa.text(
                    "SELECT id FROM ai_chat_session "
                    "WHERE user_id = :u AND session_key = :k"
                ),
                {"u": user_id, "k": key},
            )
        ).fetchall()
    assert len(session_rows) >= 1, "并发 upsert 后一个 session 都没有 = 环境异常"
    session_id = session_rows[0][0]
    session_id_holder["session_id"] = session_id

    # ── 场景 B：100 个并发相同 idempotency key 的 run 创建 ────────────────
    idem = f"idem-{uuid.uuid4().hex[:12]}"
    engine_invocations: list[str] = []

    async def _one_run(_i: int) -> bool:
        async with AsyncSession(bind=engine) as db:
            run, created = await upsert_run(
                db,
                session_id=session_id,
                actor_id=user_id,
                idempotency_key=idem,
                project_id=project_id,
                host_type=HostType.workpaper,
                host_id=host_id,
                engine=ChatEngineName.native,
            )
            run_pk = run.id  # commit 前取值（commit 会 expire 属性）
            if created:
                # 🔴 user message 与 run 插入在**同一事务**：竞争者的 run 插入被唯一
                # 索引拒绝时整个事务回滚，消息随之消失 ⇒ "一个 run 一条 user message"
                # 由数据库原子性保证，不靠应用层判断。
                session_obj = (
                    await db.execute(
                        sa.select(AIChatSession).where(AIChatSession.id == session_id)
                    )
                ).scalar_one()
                await persist_append_message(
                    db,
                    session_obj,
                    role="user",
                    text="并发幂等提问",
                    run_id=run.id,
                )
            await db.commit()
            if created:
                engine_invocations.append(str(run_pk))
            return created

    run_created_flags = await asyncio.gather(
        *[_one_run(i) for i in range(CONCURRENCY)]
    )

    async with engine.begin() as conn:
        run_count = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM ai_chat_runs "
                    "WHERE actor_id = :u AND session_id = :s AND idempotency_key = :k"
                ),
                {"u": user_id, "s": session_id, "k": idem},
            )
        ).scalar_one()
        run_id = (
            await conn.execute(
                sa.text(
                    "SELECT id FROM ai_chat_runs "
                    "WHERE actor_id = :u AND session_id = :s AND idempotency_key = :k"
                ),
                {"u": user_id, "s": session_id, "k": idem},
            )
        ).scalar_one()
        user_msg_count = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM ai_chat_message "
                    "WHERE run_id = :r AND role = 'user'"
                ),
                {"r": run_id},
            )
        ).scalar_one()

    # ── 场景 C：100 个并发相同 note idempotency key 的收据抢占 ────────────
    note_idem = f"note-{uuid.uuid4().hex[:12]}"

    async def _one_receipt(_i: int) -> tuple[bool, str | None]:
        async with AsyncSession(bind=engine) as db:
            receipt, claimed = await claim_action_receipt(
                db,
                action_type=ActionReceiptType.note_create,
                actor_id=user_id,
                session_id=session_id,
                idempotency_key=note_idem,
                source_message_hash=content_hash("服务端权威正文"),
            )
            if claimed:
                # 只有抢到收据的调用才创建目标资源（Task 18 在此写 folder/document）。
                await settle_action_receipt(
                    db,
                    receipt,
                    status=ActionReceiptStatus.succeeded,
                    result_resource_id=uuid.uuid4(),
                )
            # commit 前取值（commit 会 expire 属性，之后访问触发懒加载 ⇒ MissingGreenlet）
            resource_id = (
                str(receipt.result_resource_id) if receipt.result_resource_id else None
            )
            await db.commit()
            return claimed, resource_id

    receipt_results = await asyncio.gather(
        *[_one_receipt(i) for i in range(CONCURRENCY)]
    )

    async with engine.begin() as conn:
        receipt_rows = (
            await conn.execute(
                sa.text(
                    "SELECT id, result_resource_id, status, source_message_hash "
                    "FROM ai_chat_action_receipts "
                    "WHERE action_type = :a AND actor_id = :u "
                    "AND session_id = :s AND idempotency_key = :k"
                ),
                {
                    "a": ActionReceiptType.note_create.value,
                    "u": user_id,
                    "s": session_id,
                    "k": note_idem,
                },
            )
        ).fetchall()

    return {
        "session_created_count": sum(1 for c in session_created_flags if c),
        "session_row_count": len(session_rows),
        "run_created_count": sum(1 for c in run_created_flags if c),
        "run_row_count": run_count,
        "engine_invocation_count": len(engine_invocations),
        "user_message_count": user_msg_count,
        "receipt_claimed_count": sum(1 for claimed, _ in receipt_results if claimed),
        "receipt_row_count": len(receipt_rows),
        "receipt_resource_ids": sorted(
            {str(r[1]) for r in receipt_rows if r[1] is not None}
        ),
        "receipt_statuses": sorted({r[2] for r in receipt_rows}),
        "receipt_source_hashes": sorted({r[3] for r in receipt_rows if r[3]}),
    }


async def _load_schema_snapshot(engine) -> dict[str, Any]:
    """真实 PG 结构快照：CHECK 定义、外键删除规则、列、唯一索引。"""
    tables = (
        "ai_chat_session",
        "ai_chat_message",
        "ai_chat_runs",
        "ai_chat_tool_calls",
        "ai_chat_attachments",
        "ai_chat_action_receipts",
    )
    async with engine.begin() as conn:
        checks = {
            r[0]: r[1]
            for r in (
                await conn.execute(
                    sa.text(
                        "SELECT c.conname, pg_get_constraintdef(c.oid) "
                        "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE c.contype = 'c' AND t.relname = ANY(:tbls)"
                    ),
                    {"tbls": list(tables)},
                )
            ).fetchall()
        }
        # confdeltype 是 PG 的 "char" 类型，asyncpg 返回 bytes（b'c'/b'r'/b'n'/b'a'）⇒ 解码
        fks = {
            (r[0], r[1], r[2]): (
                r[3].decode() if isinstance(r[3], (bytes, bytearray)) else str(r[3])
            )
            for r in (
                await conn.execute(
                    sa.text(
                        "SELECT t.relname, c.conname, "
                        "  pg_get_constraintdef(c.oid), c.confdeltype "
                        "FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
                        "WHERE c.contype = 'f' AND t.relname = ANY(:tbls)"
                    ),
                    {"tbls": list(tables)},
                )
            ).fetchall()
        }
        columns: dict[str, dict[str, dict[str, Any]]] = {}
        for row in (
            await conn.execute(
                sa.text(
                    "SELECT table_name, column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = ANY(:tbls)"
                ),
                {"tbls": list(tables)},
            )
        ).fetchall():
            columns.setdefault(row[0], {})[row[1]] = {
                "type": row[2],
                "nullable": row[3] == "YES",
            }
        indexes = {
            r[0]: r[1]
            for r in (
                await conn.execute(
                    sa.text(
                        "SELECT i.relname, pg_get_indexdef(i.oid) "
                        "FROM pg_class t JOIN pg_index x ON x.indrelid = t.oid "
                        "JOIN pg_class i ON i.oid = x.indexrelid "
                        "WHERE t.relname = ANY(:tbls)"
                    ),
                    {"tbls": list(tables)},
                )
            ).fetchall()
        }

        # 迁移回填表达式 ↔ Python build_session_key 同输入求值比对
        migration_src = MIGRATION.read_text(encoding="utf-8")
        expr = _extract_balanced(migration_src, "encode(")
        probe_user = uuid.uuid4()
        probe_project = uuid.uuid4()
        probe_host = uuid.uuid4()
        probe_locator = f"workpaper:{probe_host}:{probe_user}"
        probe_sql = (
            f"SELECT {expr} AS k FROM (SELECT "
            f"'{probe_user}'::uuid AS user_id, "
            f"'{probe_project}'::uuid AS project_id, "
            f"NULL::int AS audit_year, "
            f"'{probe_locator}'::text AS context_summary) s"
        )
        sql_key = (await conn.exec_driver_sql(probe_sql)).scalar_one()

    return {
        "checks": checks,
        "fks": fks,
        "columns": columns,
        "indexes": indexes,
        "backfill_sql_key": sql_key,
        "backfill_probe": {
            "user_id": probe_user,
            "project_id": probe_project,
            "host_id": str(probe_host),
        },
        "backfill_expr": expr,
    }


async def _collect() -> dict[str, Any]:
    """建真实 user/project → 跑三个并发场景 → 取结构快照 → finally 逐步清理。"""
    # 🔴 不开 pool_pre_ping：asyncpg 下 pre-ping 会在池回收路径上以同步方式调用
    #    `ping()`，落在 greenlet 上下文之外 ⇒ MissingGreenlet（实测踩过）。
    engine = create_async_engine(
        app_settings.DATABASE_URL, pool_size=20, max_overflow=10
    )
    holder: dict[str, Any] = {"host_id": str(uuid.uuid4())}
    cleanup: dict[str, Any] = {}
    try:
        async with AsyncSession(bind=engine) as db:
            user = User(
                username=f"ai_t3_{uuid.uuid4().hex[:10]}",
                email=f"{uuid.uuid4().hex[:12]}@ai-task3.example",
                hashed_password="x",
                role=UserRole("auditor"),
                is_active=True,
            )
            db.add(user)
            await db.flush()
            project = Project(
                name=f"ai_t3_proj_{uuid.uuid4().hex[:8]}", client_name="Task3 并发夹具"
            )
            db.add(project)
            await db.flush()
            # 🔴 commit 前取值：commit 会 expire 属性，之后访问 `.id` 会触发懒加载，
            #    在 asyncio.run 的同步段里就是 MissingGreenlet（实测踩过）。
            holder["user_id"] = user.id
            holder["project_id"] = project.id
            # 🔴 清理登记必须在 commit **之前**完成：若登记写在 commit 之后，而 commit
            #    或紧随其后的任一步抛异常，finally 里 uid/pid 仍是 None ⇒ 真实写入的
            #    user/project 变成 dev 库垃圾（实测踩过，留下 3 个孤儿账号）。
            cleanup["user_id"] = user.id
            cleanup["project_id"] = project.id
            await db.commit()

        concurrency = await _run_concurrency(engine, holder)
        cleanup["session_id"] = holder.get("session_id")
        schema = await _load_schema_snapshot(engine)
        return {"concurrency": concurrency, "schema": schema, "ids": dict(holder)}
    finally:
        # 🔴 逐步独立事务清理：一个 engine.begin() 里全清，任一步失败会把前面的清理
        #    一起回滚，dev 库就留下垃圾。成败一律以再查数据为准，不看异常有无。
        stmts: list[tuple[str, dict[str, Any]]] = []
        sid = cleanup.get("session_id")
        uid = cleanup.get("user_id")
        pid = cleanup.get("project_id")
        if sid:
            stmts += [
                ("DELETE FROM ai_chat_action_receipts WHERE session_id = :s", {"s": sid}),
                ("DELETE FROM ai_chat_attachments WHERE session_id = :s", {"s": sid}),
                ("DELETE FROM ai_chat_message WHERE session_id = :s", {"s": sid}),
                (
                    "DELETE FROM ai_chat_tool_calls WHERE run_id IN "
                    "(SELECT id FROM ai_chat_runs WHERE session_id = :s)",
                    {"s": sid},
                ),
                ("DELETE FROM ai_chat_runs WHERE session_id = :s", {"s": sid}),
                ("DELETE FROM ai_chat_session WHERE id = :s", {"s": sid}),
            ]
        if uid:
            stmts += [
                ("DELETE FROM ai_chat_action_receipts WHERE actor_id = :u", {"u": uid}),
                ("DELETE FROM ai_chat_attachments WHERE owner_id = :u", {"u": uid}),
                (
                    "DELETE FROM ai_chat_message WHERE session_id IN "
                    "(SELECT id FROM ai_chat_session WHERE user_id = :u)",
                    {"u": uid},
                ),
                ("DELETE FROM ai_chat_runs WHERE actor_id = :u", {"u": uid}),
                ("DELETE FROM ai_chat_session WHERE user_id = :u", {"u": uid}),
            ]
        if pid:
            stmts.append(("DELETE FROM projects WHERE id = :p", {"p": pid}))
        if uid:
            stmts.append(("DELETE FROM users WHERE id = :u", {"u": uid}))

        for sql, params in stmts:
            try:
                async with engine.begin() as conn:
                    await conn.execute(sa.text(sql), params)
            except Exception as exc:  # noqa: BLE001 - 记录并继续清理下一条
                print(f"[cleanup] {sql[:60]}… 失败: {type(exc).__name__}: {exc}")

        leftovers: dict[str, int] = {}
        try:
            async with engine.begin() as conn:
                for table, col, val in (
                    ("ai_chat_session", "user_id", uid),
                    ("ai_chat_runs", "actor_id", uid),
                    ("ai_chat_action_receipts", "actor_id", uid),
                    ("users", "id", uid),
                    ("projects", "id", pid),
                ):
                    if val is None:
                        continue
                    leftovers[table] = (
                        await conn.execute(
                            sa.text(f"SELECT count(*) FROM {table} WHERE {col} = :v"),
                            {"v": val},
                        )
                    ).scalar_one()
        except Exception as exc:  # noqa: BLE001
            print(f"[cleanup] 复核失败: {type(exc).__name__}: {exc}")
        if any(leftovers.values()):
            print(f"[cleanup] ⚠️ 仍有残留（需人工清理）: {leftovers}")
        await engine.dispose()


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    """模块级：一次 ``asyncio.run`` 取完并发结果与结构快照。"""
    return asyncio.run(_collect())


# ---------------------------------------------------------------------------
# Property 6：会话与 Run 并发幂等
# ---------------------------------------------------------------------------


def test_concurrent_identical_session_keys_produce_exactly_one_session(snapshot):
    """100 个并发相同 session key 的首次请求最终只产生一个 session。

    **Validates: Requirements 4.11**
    Property 6（前半）。保证来自部分唯一索引 ``uq_ai_chat_session_user_key``，
    不是"先查后建"—— 后者在并发下必然产生多行（见
    ``test_session_upsert_issues_on_conflict_before_any_select``）。
    """
    c = snapshot["concurrency"]
    assert c["session_row_count"] == 1, (
        f"同一 session key 落库 {c['session_row_count']} 行（应为 1）—— "
        "唯一约束缺失或退回了先查后建"
    )
    assert c["session_created_count"] == 1, (
        f"{c['session_created_count']} 个并发调用都自称创建者（应恰好 1）"
    )


def test_concurrent_identical_idempotency_keys_produce_one_run_one_message(snapshot):
    """100 个相同 idempotency key 只产生一个 run、一条 user message、一次 engine 调用。

    **Validates: Requirements 4.6, 4.11**
    Property 6（后半）。user message 与 run 在同一事务内写入 ⇒ 竞争者的 run 被唯一
    索引拒绝时消息随事务回滚，"一个 run 一条 user message"由数据库原子性保证。
    """
    c = snapshot["concurrency"]
    assert c["run_row_count"] == 1, f"run 落库 {c['run_row_count']} 行（应为 1）"
    assert c["run_created_count"] == 1, (
        f"{c['run_created_count']} 个并发调用都自称 run 创建者（应恰好 1）"
    )
    assert c["user_message_count"] == 1, (
        f"该 run 下有 {c['user_message_count']} 条 user message（应为 1）—— "
        "重复请求重复保存了用户消息"
    )
    assert c["engine_invocation_count"] == 1, (
        f"engine 被调用 {c['engine_invocation_count']} 次（应为 1）"
    )


# ---------------------------------------------------------------------------
# Property 21：项目笔记并发幂等
# ---------------------------------------------------------------------------


def test_concurrent_note_idempotency_keys_create_one_receipt_and_one_resource(snapshot):
    """同一 note idempotency key 的并发请求只创建一个收据与一个目标资源。

    **Validates: Requirements 8.2, 8.3**
    Property 21。唯一约束 ``uq_ai_chat_action_receipts_idempotency`` 是并发去重的
    唯一依据（Req 8.3 明令"而非仅先查后建"）。
    """
    c = snapshot["concurrency"]
    assert c["receipt_row_count"] == 1, (
        f"收据落库 {c['receipt_row_count']} 行（应为 1）—— 会创建重复文件夹/文档"
    )
    assert c["receipt_claimed_count"] == 1, (
        f"{c['receipt_claimed_count']} 个并发调用都抢到收据（应恰好 1）"
    )
    assert len(c["receipt_resource_ids"]) == 1, (
        f"收据指向 {len(c['receipt_resource_ids'])} 个目标资源（应为 1）"
    )
    assert c["receipt_statuses"] == [ActionReceiptStatus.succeeded.value]


def test_receipt_carries_server_side_content_hash_not_client_text(snapshot):
    """收据保存的是服务端算出的 message content hash（溯源，不重复存正文）。

    **Validates: Requirements 8.4**
    """
    c = snapshot["concurrency"]
    assert c["receipt_source_hashes"] == [content_hash("服务端权威正文")]
    assert all(len(h) == 64 for h in c["receipt_source_hashes"])


# ---------------------------------------------------------------------------
# 真实 schema 结构：唯一约束、CHECK ↔ Python 取值域双向、外键删除规则
# ---------------------------------------------------------------------------


def _check_values(defn: str) -> set[str]:
    """从 ``pg_get_constraintdef`` 里抽出 CHECK 的字符串取值集合。"""
    return set(re.findall(r"'([^']+)'::(?:character varying|text)", defn))


@pytest.mark.parametrize(
    "conname,enum_cls",
    [
        ("ck_ai_chat_session_host_type", HostType),
        ("ck_ai_chat_runs_status", ChatRunStatus),
        ("ck_ai_chat_runs_engine", ChatEngineName),
        ("ck_ai_chat_runs_host_type", HostType),
        ("ck_ai_chat_message_status", ChatMessageStatus),
        ("ck_ai_chat_tool_calls_status", ChatToolCallStatus),
        ("ck_ai_chat_attachments_ocr_status", AttachmentOcrStatus),
        ("ck_ai_chat_action_receipts_action", ActionReceiptType),
        ("ck_ai_chat_action_receipts_status", ActionReceiptStatus),
    ],
)
def test_check_constraint_value_domain_equals_python_enum(snapshot, conname, enum_cls):
    """每个取值域 CHECK 与 Python 枚举**双向**相等（DB ⊆ Python 且 Python ⊆ DB）。

    **Validates: Requirements 4.11**
    单向包含会漏掉两类漂移：DB 多出取值（应用层无法产生 ⇒ 死取值域）与 Python 多出
    取值（写库即被 CHECK 拒绝 ⇒ 运行时 500）。这里要求集合相等。
    """
    defn = snapshot["schema"]["checks"].get(conname)
    assert defn, f"CHECK {conname} 不存在（迁移未应用或被改名）"
    db_values = _check_values(defn)
    py_values = {m.value for m in enum_cls}
    assert db_values == py_values, (
        f"{conname} 取值域漂移：\n  DB 多出 {sorted(db_values - py_values)}\n"
        f"  Python 多出 {sorted(py_values - db_values)}"
    )


def test_session_and_run_and_receipt_unique_indexes_are_real(snapshot):
    """三个并发幂等所依赖的唯一索引真实存在、列组与谓词正确。

    **Validates: Requirements 4.11, 8.3**
    """
    idx = snapshot["schema"]["indexes"]

    sess = idx.get("uq_ai_chat_session_user_key", "")
    assert "UNIQUE" in sess and "(user_id, session_key)" in sess, sess
    assert "session_key IS NOT NULL" in sess, (
        "部分唯一索引必须带 session_key IS NOT NULL 谓词，否则存量 NULL 行语义含混"
    )

    run = idx.get("uq_ai_chat_runs_idempotency", "")
    assert "UNIQUE" in run and "(actor_id, session_id, idempotency_key)" in run, run

    receipt = idx.get("uq_ai_chat_action_receipts_idempotency", "")
    assert "UNIQUE" in receipt, receipt
    assert "(action_type, actor_id, session_id, idempotency_key)" in receipt, receipt


def test_attachment_session_fk_is_restrict_so_metadata_never_orphans_files(snapshot):
    """附件 → 会话外键是 RESTRICT，run/tool/receipt 是 CASCADE。

    **Validates: Requirements 7.3**
    Req 7.9 明令"磁盘删除失败不得删除 metadata 后失去追踪"。若附件外键是 CASCADE，
    clear session 会连带删掉 metadata，``storage/ai_chat/`` 下的文件变成孤儿。

    判据取**两侧**：live PG 的 ``confdeltype`` 与迁移文件里的声明。只看 live PG 时，
    已应用迁移的文件被改坏不会被发现（下一个环境从 clean checkout 跑迁移就是
    CASCADE）；只看文件时，手工 ALTER 过的库不会被发现。
    """
    # fks: {(table, conname, condef): confdeltype}；confdeltype 'c'=CASCADE
    # 'r'=RESTRICT 'n'=SET NULL 'a'=NO ACTION
    delete_rules: dict[tuple[str, str], str] = {}
    for (tbl, _conname, condef), rule in snapshot["schema"]["fks"].items():
        referenced = condef.split("REFERENCES ")[1].split("(")[0].strip()
        delete_rules[(tbl, referenced)] = rule

    assert delete_rules.get(("ai_chat_attachments", "ai_chat_session")) == "r", (
        f"附件→会话外键删除规则应为 RESTRICT('r')，实测 "
        f"{delete_rules.get(('ai_chat_attachments', 'ai_chat_session'))!r}"
    )
    for tbl in ("ai_chat_runs", "ai_chat_action_receipts"):
        assert delete_rules.get((tbl, "ai_chat_session")) == "c", (
            f"{tbl}→会话外键删除规则应为 CASCADE('c')，实测 "
            f"{delete_rules.get((tbl, 'ai_chat_session'))!r}"
        )
    assert delete_rules.get(("ai_chat_tool_calls", "ai_chat_runs")) == "c"

    # 第二侧：迁移文件的声明（clean checkout 从头跑迁移时生效的那一份）
    src = MIGRATION.read_text(encoding="utf-8")
    attach_block = src[src.index("CREATE TABLE IF NOT EXISTS ai_chat_attachments") :]
    attach_block = attach_block[: attach_block.index("CONSTRAINT ck_ai_chat_attachments")]
    session_fk_lines = [
        ln for ln in attach_block.splitlines()
        if "REFERENCES ai_chat_session(id)" in ln
    ]
    assert len(session_fk_lines) == 1, f"附件表的会话外键声明应恰好一行：{session_fk_lines}"
    assert "ON DELETE RESTRICT" in session_fk_lines[0], (
        "迁移里附件→会话外键未声明 RESTRICT（clean checkout 会建出 CASCADE）："
        f"{session_fk_lines[0].strip()}"
    )


def test_citations_reuse_referenced_sources_without_duplicate_column(snapshot):
    """citations 复用既有 ``referenced_sources``，没有第二个同义列。

    **Validates: Requirements 4.10**
    design 明确"复用已有 referenced_sources、model/token/latency 字段（存在即不
    重复新增）"。本判据锁死"不要为同一件事造第二列"。
    """
    cols = snapshot["schema"]["columns"]["ai_chat_message"]
    assert "referenced_sources" in cols
    assert "citations" not in cols, "新增了 citations 列 = 与 referenced_sources 重复"
    for existing in ("model_used", "tokens_used", "latency_ms"):
        assert existing in cols, f"{existing} 消失了（应复用而非重造）"
    for dup in ("model", "tokens", "latency", "token_count"):
        assert dup not in cols, (
            f"新增了 {dup} 列 = 与既有 model_used/tokens_used/latency_ms 重复"
        )


def test_task3_columns_and_tables_exist_with_expected_shape(snapshot):
    """Task 3 声明的字段/表在真实 PG 上齐备（Req 7.3 的附件 metadata 逐项核对）。

    **Validates: Requirements 7.3**
    """
    cols = snapshot["schema"]["columns"]

    for c in (
        "session_key", "host_type", "host_id", "audit_year",
        "engine_preference", "review_mode", "last_message_at",
    ):
        assert c in cols["ai_chat_session"], f"ai_chat_session.{c} 缺失"
    assert cols["ai_chat_session"]["project_id"]["nullable"] is True, (
        "project_id 必须可空，否则受限全局知识模式只能用空 UUID 伪装项目"
    )

    for c in ("seq", "run_id", "status", "content_hash", "context_manifest"):
        assert c in cols["ai_chat_message"], f"ai_chat_message.{c} 缺失"

    for c in (
        "session_id", "request_id", "idempotency_key", "actor_id", "project_id",
        "host_type", "host_id", "engine", "status", "capability_snapshot",
        "queued_at", "started_at", "finished_at", "cancel_requested_at",
        "error_code", "usage", "latency_ms", "retry_count",
        "lease_owner", "lease_expires_at",
    ):
        assert c in cols["ai_chat_runs"], f"ai_chat_runs.{c} 缺失"

    for c in (
        "run_id", "parent_call_id", "tool_call_id", "tool_name",
        "arg_hash", "result_bytes", "status", "error_code",
        "started_at", "finished_at",
    ):
        assert c in cols["ai_chat_tool_calls"], f"ai_chat_tool_calls.{c} 缺失"

    # Req 7.3 逐项：attachment ID / owner / project / session / run / hash / 状态 /
    # 路径 / 大小 / MIME / 创建时间 / 过期时间
    for c in (
        "id", "owner_id", "project_id", "session_id", "run_id", "sha256",
        "original_name", "storage_name", "mime_type", "size_bytes",
        "ocr_status", "ocr_text_protected", "error_code",
        "created_at", "expires_at", "legal_hold", "deleted_at",
    ):
        assert c in cols["ai_chat_attachments"], f"ai_chat_attachments.{c} 缺失"

    for c in (
        "action_type", "actor_id", "session_id", "idempotency_key",
        "source_message_hash", "result_resource_id", "status", "error_code",
    ):
        assert c in cols["ai_chat_action_receipts"], f"ai_chat_action_receipts.{c} 缺失"


def test_session_key_sql_backfill_matches_python(snapshot):
    """V147 的回填表达式与 ``build_session_key`` 对同一输入求出同一 hash。

    **Validates: Requirements 4.11**
    两侧不一致 = 存量行的 key 与运行时算出的 key 错位 ⇒ 同一会话两行、历史分裂。
    判据在**真实 PG 上求值**（不是比对字符串长得像）。
    """
    schema = snapshot["schema"]
    probe = schema["backfill_probe"]
    py_key = build_session_key(
        user_id=probe["user_id"],
        project_id=probe["project_id"],
        audit_year=None,
        host_type=HostType.workpaper,
        host_id=probe["host_id"],
    )
    assert schema["backfill_sql_key"] == py_key, (
        "迁移回填表达式与 Python build_session_key 不一致：\n"
        f"  SQL   = {schema['backfill_sql_key']}\n  Python= {py_key}\n"
        f"  表达式 = {schema['backfill_expr'][:200]}"
    )


def test_migration_records_dedup_rule_and_orders_backfill_before_unique_index():
    """迁移把"回填 → 合并重复 → 建唯一约束"的顺序写实，且显式记录去重规则。

    **Validates: Requirements 4.11**
    顺序颠倒（先建唯一索引再回填）在存在重复 locator 的库上会让整个迁移失败；
    去重规则不写明则下次改动无从复现胜者选择。判据落在**语句序**上。
    """
    src = MIGRATION.read_text(encoding="utf-8")
    i_backfill = src.index("SET host_type = split_part")
    i_merge = src.index("PARTITION BY s.user_id, s.session_key")
    i_unique = src.index("CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_chat_session_user_key")
    assert i_backfill < i_merge < i_unique, (
        "顺序必须是 回填 → 合并 → 建唯一索引"
        f"（实测 {i_backfill} / {i_merge} / {i_unique}）"
    )
    assert "去重规则" in src, "迁移必须显式记录去重规则（胜者选择依据）"
    # 合并分两条语句（改挂消息 + 删败者），两个 CTE 的胜者排序必须**逐字相同**：
    # 只改其中一个会让"消息挂到 A、删掉 B"这种撕裂发生，而"token 是否出现过"
    # 这类判据看不出来（另一处还在）⇒ 用出现次数锁死。
    order_by = "ORDER BY s.total_messages DESC NULLS LAST, s.created_at ASC, s.id ASC"
    assert src.count(order_by) == 2, (
        f"胜者排序应在两个合并 CTE 中逐字出现 2 次，实测 {src.count(order_by)} 次 —— "
        "两处不一致会导致消息改挂与删除选出不同胜者"
    )


# ---------------------------------------------------------------------------
# session_key：五要素绑定与 sentinel（纯函数，无 IO）
# ---------------------------------------------------------------------------


def test_session_key_binds_all_five_locator_elements():
    """user / project / year / host type / host ID 任一变化，session_key 必变。

    **Validates: Requirements 4.11**
    """
    base = dict(
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        project_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        audit_year=2025,
        host_type=HostType.workpaper,
        host_id="33333333-3333-3333-3333-333333333333",
    )
    baseline = build_session_key(**base)
    assert len(baseline) == 64 and baseline == build_session_key(**base)

    variants = {
        "user": {**base, "user_id": uuid.uuid4()},
        "project": {**base, "project_id": uuid.uuid4()},
        "year": {**base, "audit_year": 2024},
        "year_none": {**base, "audit_year": None},
        "host_type": {**base, "host_type": HostType.note},
        "host_id": {**base, "host_id": str(uuid.uuid4())},
    }
    keys = {name: build_session_key(**kw) for name, kw in variants.items()}
    for name, k in keys.items():
        assert k != baseline, f"改变 {name} 后 session_key 未变 = 该要素没进定位键"
    assert len(set(keys.values())) == len(keys), "不同要素组合撞到了同一 key"


def test_global_knowledge_uses_explicit_sentinel_not_empty_string():
    """无项目模式用显式 sentinel；空 host_id / 未登记 host_type 一律拒绝。

    **Validates: Requirements 4.11**
    """
    assert NO_PROJECT_SENTINEL == GLOBAL_KNOWLEDGE_HOST_ID, (
        "无项目 sentinel 必须复用 Task 1 冻结的常量，不新造第二个"
    )
    assert NO_PROJECT_SENTINEL and NO_YEAR_SENTINEL
    assert SESSION_KEY_VERSION == "v1"

    ok = build_session_key(
        user_id=uuid.uuid4(),
        project_id=None,
        audit_year=None,
        host_type=HostType.global_knowledge,
        host_id=GLOBAL_KNOWLEDGE_HOST_ID,
    )
    assert len(ok) == 64

    with pytest.raises(ValueError):
        build_session_key(
            user_id=uuid.uuid4(),
            project_id=None,
            audit_year=2025,
            host_type=HostType.global_knowledge,
            host_id="",
        )
    with pytest.raises(ValueError):
        build_session_key(
            user_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            audit_year=2025,
            host_type="workpapers",  # 未登记
            host_id="x",
        )


# ---------------------------------------------------------------------------
# 回滚型判据：语句流、history 顺序与元数据、约束触发
# ---------------------------------------------------------------------------


def test_session_upsert_issues_on_conflict_before_any_select():
    """会话创建的**第一条**触及 ai_chat_session 的语句是 INSERT … ON CONFLICT。

    **Validates: Requirements 4.11**
    "先查后建"在并发下必然产生两行；只看最终行数在单线程测试里查不出来，所以这里
    直接断言**语句序**：定位查询不得先于插入发生。第二次调用命中冲突并读回同一行。
    """

    async def body(fx: AccessFixture, sql_log: list[str]):
        db = fx.session
        user = fx.actor("manager")
        args = dict(
            user_id=user.id,
            project_id=fx.project_a.id,
            audit_year=2025,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
        )
        sql_log.clear()
        first, created_first = await upsert_session(db, **args)
        first_statements = [s for s in sql_log if "ai_chat_session" in s]
        second, created_second = await upsert_session(db, **args)
        return {
            "first_statements": first_statements,
            "first_id": first.id,
            "second_id": second.id,
            "created_first": created_first,
            "created_second": created_second,
            "session_key": first.session_key,
            "host_type": first.host_type,
            "host_id": first.host_id,
            "audit_year": first.audit_year,
        }

    r = run_with_fixture(body, capture_sql=True)

    assert r["first_statements"], "未捕获到任何触及 ai_chat_session 的语句"
    head = " ".join(r["first_statements"][0].split()).upper()
    assert head.startswith("INSERT INTO AI_CHAT_SESSION"), (
        f"第一条语句不是 INSERT（疑似退回先查后建）：{head[:160]}"
    )
    assert "ON CONFLICT" in head, f"INSERT 未带 ON CONFLICT：{head[:200]}"

    assert r["created_first"] is True and r["created_second"] is False
    assert r["first_id"] == r["second_id"], "重复调用创建了第二个会话"
    assert r["session_key"] and len(r["session_key"]) == 64
    assert r["host_type"] == HostType.workpaper.value
    assert r["audit_year"] == 2025


def test_history_returns_most_recent_n_ascending_with_real_metadata():
    """history 取**最近** N 条并按时间正序，携带真实 message/run metadata。

    **Validates: Requirements 4.10**
    Property 10。会话共 12 条、limit=5 ⇒ 最早 5 条与最近 5 条**互斥**：旧实现
    (``ORDER BY created_at LIMIT N`` 取最早 N 条) 必然打红。第 6/7 条故意共享同一
    ``created_at``，用来证明 ``seq`` 提供了确定性兜底（``now()`` 是事务开始时刻，
    同一事务内追加的消息时间完全相同）。
    """

    async def body(fx: AccessFixture, _sql: list[str]):
        db = fx.session
        user = fx.actor("manager")
        session, _ = await upsert_session(
            db,
            user_id=user.id,
            project_id=fx.project_a.id,
            audit_year=2025,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
        )
        run, _ = await upsert_run(
            db,
            session_id=session.id,
            actor_id=user.id,
            idempotency_key=f"hist-{uuid.uuid4().hex[:8]}",
            project_id=fx.project_a.id,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
            engine="native",
        )

        citations = [{"source_type": "workpaper", "source_id": str(fx.wp_d.id)}]
        created: list[dict[str, Any]] = []
        for i in range(1, HISTORY_TOTAL + 1):
            is_assistant = i % 2 == 0
            msg = await persist_append_message(
                db,
                session,
                role="assistant" if is_assistant else "user",
                text=f"消息{i:02d}",
                run_id=run.id if is_assistant else None,
                citations=citations if is_assistant else None,
                model_used="Qwen3.5-27B-NVFP4" if is_assistant else None,
                tokens_used=100 + i if is_assistant else None,
                latency_ms=1000 + i if is_assistant else None,
            )
            created.append({"id": msg.id, "text": msg.message_text})

        # created_at 默认是事务开始时刻（12 条完全相同）⇒ 显式错开，并让第 6/7 条
        # 共享同一时间，专门检验 seq 兜底。
        base = datetime(2026, 1, 1, 8, 0, 0)
        for idx, item in enumerate(created):
            offset = idx if idx < 6 else max(idx - 1, 5)
            await db.execute(
                sa.update(AIChatMessage)
                .where(AIChatMessage.id == item["id"])
                .values(created_at=base + timedelta(minutes=offset))
            )
        await db.flush()

        entries = await load_recent_history(
            db, session_id=session.id, limit=HISTORY_LIMIT
        )
        all_entries = await load_recent_history(
            db, session_id=session.id, limit=HISTORY_TOTAL
        )
        return {
            "entries": [e.as_dict() for e in entries],
            "all_texts": [e.content for e in all_entries],
            "total_messages": session.total_messages,
            "last_message_at": session.last_message_at,
            "run_id": str(run.id),
        }

    r = run_with_fixture(body)
    entries = r["entries"]

    assert len(entries) == HISTORY_LIMIT, f"应返回 {HISTORY_LIMIT} 条，实得 {len(entries)}"
    expected_recent = [f"消息{i:02d}" for i in range(8, HISTORY_TOTAL + 1)]
    got = [e["content"] for e in entries]
    assert got == expected_recent, (
        f"未返回最近 {HISTORY_LIMIT} 条的正序结果：\n  期望 {expected_recent}\n  实得 {got}"
    )
    earliest = [f"消息{i:02d}" for i in range(1, HISTORY_LIMIT + 1)]
    assert set(got).isdisjoint(earliest), "返回了最早 N 条（旧实现的行为）"

    # 全量取回时顺序仍是插入序（含第 6/7 条同一时间，靠 seq 定序）
    assert r["all_texts"] == [f"消息{i:02d}" for i in range(1, HISTORY_TOTAL + 1)]

    # 时间非递减（正序）
    stamps = [e["created_at"] for e in entries]
    assert stamps == sorted(stamps), f"返回顺序不是时间正序：{stamps}"

    # 真实元数据（Req 4.10：message ID / citations / engine / model / usage /
    # latency / run status）
    assistant = [e for e in entries if e["role"] == "assistant"]
    assert assistant, "样本里没有 assistant 消息，元数据判据会空转"
    for e in assistant:
        assert uuid.UUID(e["message_id"])
        assert e["run_id"] == r["run_id"]
        assert e["run_status"] == ChatRunStatus.queued.value
        assert e["engine"] == ChatEngineName.native.value
        assert e["model"] == "Qwen3.5-27B-NVFP4"
        assert isinstance(e["tokens"], int) and e["tokens"] > 0
        assert isinstance(e["latency_ms"], int) and e["latency_ms"] > 0
        assert e["citations"] and e["citations"][0]["source_type"] == "workpaper"
        assert e["status"] == ChatMessageStatus.completed.value
        assert e["content_hash"] == content_hash(e["content"])

    assert r["total_messages"] == HISTORY_TOTAL, "会话计数未随消息追加同步"
    assert r["last_message_at"] is not None, "last_message_at 未被写入"


def test_global_knowledge_session_allowed_without_project_but_others_rejected():
    """无项目会话只允许全局知识模式；其他宿主为 NULL 项目时被 CHECK 拒绝。

    **Validates: Requirements 4.11**
    这条约束是"禁止用空 UUID / 空串伪装项目"的数据库层落点。
    """

    async def body(fx: AccessFixture, _sql: list[str]):
        db = fx.session
        user = fx.actor("manager")
        global_session, created = await upsert_session(
            db,
            user_id=user.id,
            project_id=None,
            audit_year=None,
            host_type=HostType.global_knowledge,
            host_id=GLOBAL_KNOWLEDGE_HOST_ID,
        )
        await db.flush()

        rejected = None
        try:
            async with db.begin_nested():
                await upsert_session(
                    db,
                    user_id=user.id,
                    project_id=None,
                    audit_year=2025,
                    host_type=HostType.workpaper,
                    host_id=str(fx.wp_d.id),
                )
                await db.flush()
        except IntegrityError as exc:
            rejected = str(exc.orig)
        return {
            "created": created,
            "project_id": global_session.project_id,
            "host_id": global_session.host_id,
            "rejected": rejected,
        }

    r = run_with_fixture(body)
    assert r["created"] is True
    assert r["project_id"] is None
    assert r["host_id"] == GLOBAL_KNOWLEDGE_HOST_ID
    assert r["rejected"], "非全局宿主的 NULL 项目会话竟被接受（CHECK 缺失）"
    assert "ck_ai_chat_session_project_required" in r["rejected"]


def test_attachment_metadata_blocks_session_delete_and_is_hash_idempotent():
    """附件 metadata 阻止会话被直接删除；同 owner+session+hash 二次插入被拒。

    **Validates: Requirements 7.3**
    前者对应 Req 7.9（metadata 不得先于文件消失），后者对应"重复 owner/session/hash
    幂等"。两条都由真实约束触发，不看源码。
    """

    async def body(fx: AccessFixture, _sql: list[str]):
        db = fx.session
        user = fx.actor("manager")
        session, _ = await upsert_session(
            db,
            user_id=user.id,
            project_id=fx.project_a.id,
            audit_year=2025,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
        )
        digest = content_hash("扫描件内容")
        db.add(
            AIChatAttachment(
                owner_id=user.id,
                project_id=fx.project_a.id,
                session_id=session.id,
                sha256=digest,
                original_name="凭证.png",
                storage_name=f"{uuid.uuid4().hex}.bin",
                mime_type="image/png",
                size_bytes=1024,
                ocr_status=AttachmentOcrStatus.pending.value,
            )
        )
        await db.flush()

        dup_error = None
        try:
            async with db.begin_nested():
                db.add(
                    AIChatAttachment(
                        owner_id=user.id,
                        project_id=fx.project_a.id,
                        session_id=session.id,
                        sha256=digest,
                        original_name="凭证-副本.png",
                        storage_name=f"{uuid.uuid4().hex}.bin",
                        mime_type="image/png",
                        size_bytes=1024,
                    )
                )
                await db.flush()
        except IntegrityError as exc:
            dup_error = str(exc.orig)

        delete_error = None
        try:
            async with db.begin_nested():
                await db.execute(
                    sa.delete(AIChatSession).where(AIChatSession.id == session.id)
                )
                await db.flush()
        except IntegrityError as exc:
            delete_error = str(exc.orig)

        return {"dup_error": dup_error, "delete_error": delete_error}

    r = run_with_fixture(body)
    assert r["dup_error"], "同 owner+session+hash 的重复附件被接受（幂等约束缺失）"
    assert "uq_ai_chat_attachments_owner_session_hash" in r["dup_error"]
    assert r["delete_error"], (
        "挂着附件 metadata 的会话可被直接删除 —— 物理文件将变成无人追踪的孤儿"
    )
    assert "ai_chat_attachments" in r["delete_error"]


def test_run_and_receipt_reject_empty_idempotency_key():
    """空 idempotency key 一律拒绝（否则"幂等"退化为每次都新建）。

    **Validates: Requirements 8.2**
    """

    async def body(fx: AccessFixture, _sql: list[str]):
        db = fx.session
        user = fx.actor("manager")
        session, _ = await upsert_session(
            db,
            user_id=user.id,
            project_id=fx.project_a.id,
            audit_year=2025,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
        )
        errors = {}
        try:
            await upsert_run(
                db,
                session_id=session.id,
                actor_id=user.id,
                idempotency_key="",
                project_id=fx.project_a.id,
                host_type=HostType.workpaper,
                host_id=str(fx.wp_d.id),
            )
        except ValueError as exc:
            errors["run"] = str(exc)
        try:
            await claim_action_receipt(
                db,
                action_type=ActionReceiptType.note_create,
                actor_id=user.id,
                session_id=session.id,
                idempotency_key="",
            )
        except ValueError as exc:
            errors["receipt"] = str(exc)
        return errors

    r = run_with_fixture(body)
    assert "run" in r and "receipt" in r, f"空 idempotency key 未被拒绝：{r}"


def test_run_row_carries_engine_and_status_and_host_binding():
    """run 行绑定 engine / status / host / project，且状态从 queued 起。

    **Validates: Requirements 4.11**
    """

    async def body(fx: AccessFixture, _sql: list[str]):
        db = fx.session
        user = fx.actor("manager")
        session, _ = await upsert_session(
            db,
            user_id=user.id,
            project_id=fx.project_a.id,
            audit_year=2025,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
        )
        run, created = await upsert_run(
            db,
            session_id=session.id,
            actor_id=user.id,
            idempotency_key=f"shape-{uuid.uuid4().hex[:8]}",
            project_id=fx.project_a.id,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
            engine=ChatEngineName.native,
            capability_snapshot={"tools": False},
        )
        await db.flush()
        row = (
            await db.execute(sa.select(AIChatRun).where(AIChatRun.id == run.id))
        ).scalar_one()
        return {
            "created": created,
            "status": row.status,
            "engine": row.engine,
            "host_type": row.host_type,
            "host_id": row.host_id,
            "project_id": row.project_id,
            "retry_count": row.retry_count,
            "queued_at": row.queued_at is not None,
            "capability_snapshot": row.capability_snapshot,
            "request_id": row.request_id is not None,
        }

    r = run_with_fixture(body)
    assert r["created"] is True
    assert r["status"] == ChatRunStatus.queued.value
    assert r["engine"] == ChatEngineName.native.value
    assert r["host_type"] == HostType.workpaper.value
    assert r["project_id"] is not None
    assert r["retry_count"] == 0
    assert r["queued_at"] and r["request_id"]
    assert r["capability_snapshot"] == {"tools": False}


def test_doc_facade_history_resolves_with_and_without_year():
    """宿主门面：带 year 精确命中；不带 year 退回"最近使用的会话"，不伪造 year。

    **Validates: Requirements 4.10, 4.11**
    ``GET/DELETE …/history`` 端点历史上不带 year 参数（前端契约由 Task 2/9 改），而
    Req 4.11 要求 locator **必须**含 year。两者的兼容点是：定位键仍绑五要素（不放宽
    唯一约束），只读查询在缺 year 时按 ``last_message_at`` 取最近一个。
    **给错 year 时不得回退** —— 否则"跨年度会话隔离"就成了空话。
    """

    async def body(fx: AccessFixture, _sql: list[str]):
        db = fx.session
        user = fx.actor("manager")
        session = await doc_chat_persistence.get_or_create_session(
            db, HostType.workpaper.value, str(fx.wp_d.id), user.id, fx.project_a.id, 2025
        )
        await doc_chat_persistence.append_message(db, session, "user", "带年度的问题")
        await doc_chat_persistence.append_message(
            db, session, "assistant", "带年度的回答"
        )

        exact = await doc_chat_persistence.get_history(
            db,
            HostType.workpaper.value,
            str(fx.wp_d.id),
            user.id,
            project_id=fx.project_a.id,
            audit_year=2025,
        )
        no_year = await doc_chat_persistence.get_history(
            db,
            HostType.workpaper.value,
            str(fx.wp_d.id),
            user.id,
            project_id=fx.project_a.id,
        )
        wrong_year = await doc_chat_persistence.get_history(
            db,
            HostType.workpaper.value,
            str(fx.wp_d.id),
            user.id,
            project_id=fx.project_a.id,
            audit_year=2024,
        )
        missing_host = await doc_chat_persistence.get_history(
            db,
            HostType.workpaper.value,
            str(uuid.uuid4()),
            user.id,
            project_id=fx.project_a.id,
        )
        return {
            "exact": [e["content"] for e in exact],
            "no_year": [e["content"] for e in no_year],
            "wrong_year": wrong_year,
            "missing_host": missing_host,
            "context_summary": session.context_summary,
        }

    r = run_with_fixture(body)
    assert r["exact"] == ["带年度的问题", "带年度的回答"]
    assert r["no_year"] == r["exact"], "不带 year 的只读查询未回退到最近会话"
    assert r["wrong_year"] == [], "给了错误 year 却仍返回历史 = 跨年度隔离失效"
    assert r["missing_host"] == [], "不存在的宿主返回了历史"
    # 旧格式定位串仍作为人工排查旁注写入（V147 的回填依赖该格式）
    assert r["context_summary"].startswith(f"{HostType.workpaper.value}:")


def test_receipt_failure_is_retriable_and_records_error_code():
    """收据失败态记录 error_code、可重置后重试（不因失败永久占位）。

    **Validates: Requirements 8.2**
    """

    async def body(fx: AccessFixture, _sql: list[str]):
        db = fx.session
        user = fx.actor("manager")
        session, _ = await upsert_session(
            db,
            user_id=user.id,
            project_id=fx.project_a.id,
            audit_year=2025,
            host_type=HostType.workpaper,
            host_id=str(fx.wp_d.id),
        )
        key = f"retry-{uuid.uuid4().hex[:8]}"
        receipt, claimed_first = await claim_action_receipt(
            db,
            action_type=ActionReceiptType.note_create,
            actor_id=user.id,
            session_id=session.id,
            idempotency_key=key,
        )
        await settle_action_receipt(
            db, receipt, status=ActionReceiptStatus.failed, error_code="adopt_log_failed"
        )
        again, claimed_again = await claim_action_receipt(
            db,
            action_type=ActionReceiptType.note_create,
            actor_id=user.id,
            session_id=session.id,
            idempotency_key=key,
        )
        count = (
            await db.execute(
                sa.select(sa.func.count())
                .select_from(AIChatActionReceipt)
                .where(AIChatActionReceipt.idempotency_key == key)
            )
        ).scalar_one()
        return {
            "claimed_first": claimed_first,
            "claimed_again": claimed_again,
            "same_row": again.id == receipt.id,
            "status": again.status,
            "error_code": again.error_code,
            "count": count,
        }

    r = run_with_fixture(body)
    assert r["claimed_first"] is True
    assert r["claimed_again"] is False, "失败收据被二次抢占 = 会创建重复资源"
    assert r["same_row"] is True and r["count"] == 1
    assert r["status"] == ActionReceiptStatus.failed.value
    assert r["error_code"] == "adopt_log_failed"
