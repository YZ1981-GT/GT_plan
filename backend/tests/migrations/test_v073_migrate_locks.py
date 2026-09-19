"""V073 迁移测试 — editing-lock-v1-v2-consolidation 任务 1.3~1.7。

把 workpaper_editing_locks 活跃锁迁入 editing_locks（resource_type='workpaper'）。

执行模型铁律：V*.sql 仅真实 PG 由 MigrationRunner 加载，SQLite fixture 不加载迁移
→ 本文件全部标 pg_only（conftest 对非 PG DATABASE_URL 自动 skip）。

隔离铁律：每个测试在一个事务内 `SET LOCAL session_replication_role = replica`
（绕开 FK 触发器，使 hypothesis 随机 UUID + "无对应 user" 边界可行）后 ROLLBACK，
对共享 dev DB 零污染。注意：replica 角色只关 FK/触发器，部分唯一索引
uq_editing_locks_active 仍生效（Property 2 幂等兜底）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.services.conftest import _pg_url

pytestmark = pytest.mark.pg_only

# V073 迁移 SQL（与 test_v074_idempotent.py 同法用 Path 读取）
_ROOT = Path(__file__).resolve().parents[2]
V073_SQL = (_ROOT / "migrations" / "V073__migrate_workpaper_locks_to_editing_locks.sql").read_text(
    encoding="utf-8"
)

_INSERT_SRC = text(
    """
    INSERT INTO workpaper_editing_locks
        (id, wp_id, staff_id, acquired_at, heartbeat_at, released_at, created_at, updated_at)
    VALUES
        (:id, :wp_id, :staff_id, :acquired_at, :heartbeat_at, :released_at, now(), now())
    """
)


def _utc(minutes_ago: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


@pytest_asyncio.fixture
async def pg_engine():
    """函数级 PG 引擎（hypothesis 跨 example 复用，避免重复建连）。"""
    engine = create_async_engine(_pg_url(), echo=False)
    yield engine
    await engine.dispose()


async def _seed(conn, wp_id, staff_id, acquired_at, heartbeat_at, released_at=None):
    await conn.execute(
        _INSERT_SRC,
        {
            "id": uuid.uuid4(),
            "wp_id": wp_id,
            "staff_id": staff_id,
            "acquired_at": acquired_at,
            "heartbeat_at": heartbeat_at,
            "released_at": released_at,
        },
    )


async def _fetch_real_users(conn, limit: int = 5):
    rows = (
        await conn.execute(
            text("SELECT id, username FROM users WHERE is_deleted = false LIMIT :n"),
            {"n": limit},
        )
    ).all()
    return [(r[0], r[1]) for r in rows]


# ---------------------------------------------------------------------------
# Property 1: 迁移字段映射正确性 — Validates: Requirements 1.1, 1.2, 1.3
# ---------------------------------------------------------------------------

_lock_spec = st.fixed_dictionaries(
    {
        "use_real_user": st.booleans(),
        "minutes_ago": st.integers(min_value=0, max_value=4),
    }
)


@given(specs=st.lists(_lock_spec, min_size=1, max_size=4))
@settings(max_examples=3, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property_1_field_mapping(specs, pg_engine):
    # Feature: editing-lock-v1-v2-consolidation, Property 1: 迁移字段映射正确性
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            real_users = await _fetch_real_users(conn)

            seeded = []  # (wp_id, staff_id, expected_holder_name, acquired_at, heartbeat_at)
            for i, spec in enumerate(specs):
                wp_id = uuid.uuid4()
                if spec["use_real_user"] and real_users:
                    staff_id, expected_name = real_users[i % len(real_users)]
                else:
                    staff_id, expected_name = uuid.uuid4(), None
                acquired_at = _utc(spec["minutes_ago"] + 1)
                heartbeat_at = _utc(spec["minutes_ago"])
                await _seed(conn, wp_id, staff_id, acquired_at, heartbeat_at)
                seeded.append((wp_id, staff_id, expected_name, acquired_at, heartbeat_at))

            await conn.execute(text(V073_SQL))

            for wp_id, staff_id, expected_name, acquired_at, heartbeat_at in seeded:
                rid = str(wp_id)
                row = (
                    await conn.execute(
                        text(
                            "SELECT resource_type, resource_id, holder_id, holder_name, "
                            "acquired_at, heartbeat_at, released_at "
                            "FROM editing_locks WHERE resource_type='workpaper' AND resource_id=:rid"
                        ),
                        {"rid": rid},
                    )
                ).all()
                assert len(row) == 1, f"expected exactly 1 migrated lock for {rid}"
                r = row[0]
                assert r[0] == "workpaper"
                assert r[1] == rid
                assert str(r[2]) == str(staff_id)
                assert r[3] == expected_name
                # 源表查回值做时间相等比较（不依赖 python now，规避 tz 偏移歧义）
                src = (
                    await conn.execute(
                        text(
                            "SELECT acquired_at, heartbeat_at FROM workpaper_editing_locks "
                            "WHERE wp_id=:wp AND released_at IS NULL"
                        ),
                        {"wp": wp_id},
                    )
                ).one()
                assert r[4] == src[0], "acquired_at 未保留"
                assert r[5] == src[1], "heartbeat_at 未保留"
                assert r[6] is None
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------
# Property 2: 迁移后同资源活跃锁唯一（去重 + 幂等） — Validates: Requirements 1.4, 1.5
# ---------------------------------------------------------------------------


@given(
    n_locks=st.integers(min_value=2, max_value=5),
    run_twice=st.booleans(),
)
@settings(max_examples=3, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property_2_dedup_and_idempotent(n_locks, run_twice, pg_engine):
    # Feature: editing-lock-v1-v2-consolidation, Property 2: 迁移后同资源活跃锁唯一（去重+幂等）
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            real_users = await _fetch_real_users(conn)
            staff_id = real_users[0][0] if real_users else uuid.uuid4()

            wp_id = uuid.uuid4()
            rid = str(wp_id)
            # 同一 wp_id 多条活跃锁，heartbeat 各异
            heartbeats = []
            for i in range(n_locks):
                hb = _utc(minutes_ago=i)  # i=0 最新
                await _seed(conn, wp_id, staff_id, acquired_at=_utc(i + 10), heartbeat_at=hb)
                heartbeats.append(hb)
            latest_hb = max(heartbeats)

            await conn.execute(text(V073_SQL))
            if run_twice:
                await conn.execute(text(V073_SQL))

            rows = (
                await conn.execute(
                    text(
                        "SELECT heartbeat_at FROM editing_locks "
                        "WHERE resource_type='workpaper' AND resource_id=:rid AND released_at IS NULL"
                    ),
                    {"rid": rid},
                )
            ).all()
            assert len(rows) == 1, f"活跃锁应恰为 1，实际 {len(rows)}"
            assert rows[0][0] == latest_hb, "保留的应是 heartbeat_at 最新者"
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------
# Property 3: 迁移非破坏性 — Validates: Requirements 6.4
# ---------------------------------------------------------------------------


@given(specs=st.lists(_lock_spec, min_size=1, max_size=4))
@settings(max_examples=3, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property_3_non_destructive(specs, pg_engine):
    # Feature: editing-lock-v1-v2-consolidation, Property 3: 迁移非破坏性
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            for spec in specs:
                await _seed(
                    conn,
                    uuid.uuid4(),
                    uuid.uuid4(),
                    acquired_at=_utc(spec["minutes_ago"] + 1),
                    heartbeat_at=_utc(spec["minutes_ago"]),
                )

            snap_sql = text(
                "SELECT id, wp_id, staff_id, acquired_at, heartbeat_at, released_at, "
                "created_at, updated_at FROM workpaper_editing_locks ORDER BY id"
            )
            before = (await conn.execute(snap_sql)).all()

            await conn.execute(text(V073_SQL))

            after = (await conn.execute(snap_sql)).all()
            assert before == after, "V073 只读源表，workpaper_editing_locks 不应被修改"
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------
# 任务 1.6: 迁移单元测试（已知 example + 幂等 + 边界） — Requirements 8.2, 8.3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unit_known_example_idempotent_and_boundary(pg_engine):
    """已知源数据精确字段映射 + 重复执行活跃锁=1 + 边界 holder_name NULL。"""
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            real_users = await _fetch_real_users(conn, limit=1)
            assert real_users, "测试库需至少 1 个用户"
            user_id, username = real_users[0]

            acq = _utc(2)
            hb = _utc(1)

            # case A: 有对应 user → holder_name = username
            wp_a = uuid.uuid4()
            await _seed(conn, wp_a, user_id, acquired_at=acq, heartbeat_at=hb)

            # case B (边界): staff_id 无对应 user → holder_name NULL
            wp_b = uuid.uuid4()
            orphan_staff = uuid.uuid4()
            await _seed(conn, wp_b, orphan_staff, acquired_at=acq, heartbeat_at=hb)

            # 幂等：跑两次
            await conn.execute(text(V073_SQL))
            await conn.execute(text(V073_SQL))

            # case A 精确匹配
            ra = (
                await conn.execute(
                    text(
                        "SELECT resource_type, resource_id, holder_id, holder_name, released_at "
                        "FROM editing_locks WHERE resource_type='workpaper' AND resource_id=:rid"
                    ),
                    {"rid": str(wp_a)},
                )
            ).all()
            assert len(ra) == 1
            assert ra[0][0] == "workpaper"
            assert ra[0][1] == str(wp_a)
            assert str(ra[0][2]) == str(user_id)
            assert ra[0][3] == username
            assert ra[0][4] is None

            # case B 边界：holder_name NULL
            rb = (
                await conn.execute(
                    text(
                        "SELECT holder_name FROM editing_locks "
                        "WHERE resource_type='workpaper' AND resource_id=:rid AND released_at IS NULL"
                    ),
                    {"rid": str(wp_b)},
                )
            ).all()
            assert len(rb) == 1, "幂等：重复执行后活跃锁仍恰为 1"
            assert rb[0][0] is None, "无对应 user 时 holder_name 应为 NULL"
        finally:
            await trans.rollback()


# ---------------------------------------------------------------------------
# Property 14: 迁移时区规整后过期判定一致 — Validates: Requirements 1.2
# ---------------------------------------------------------------------------

# 明确处于窗口内（<5min）或窗口外（>5min），规避 5min 边界抖动
_window_spec = st.sampled_from([1, 2, 3, 8, 12, 20])


@given(minutes_list=st.lists(_window_spec, min_size=1, max_size=5))
@settings(max_examples=3, suppress_health_check=[HealthCheck.function_scoped_fixture])
@pytest.mark.asyncio
async def test_property_14_timezone_expiry_consistency(minutes_list, pg_engine):
    # Feature: editing-lock-v1-v2-consolidation, Property 14: 迁移时区规整后过期判定一致
    async with pg_engine.connect() as conn:
        trans = await conn.begin()
        try:
            await conn.execute(text("SET LOCAL session_replication_role = replica"))
            real_users = await _fetch_real_users(conn, limit=1)
            staff_id = real_users[0][0] if real_users else uuid.uuid4()

            seeded = []  # (rid, expected_active)
            for minutes_ago in minutes_list:
                wp_id = uuid.uuid4()
                await _seed(
                    conn,
                    wp_id,
                    staff_id,
                    acquired_at=_utc(minutes_ago + 1),
                    heartbeat_at=_utc(minutes_ago),
                )
                seeded.append((str(wp_id), minutes_ago < 5))

            await conn.execute(text(V073_SQL))

            for rid, expected_active in seeded:
                # v2 活跃判定：released_at IS NULL AND heartbeat_at > now - 5min
                row = (
                    await conn.execute(
                        text(
                            "SELECT (heartbeat_at > now() - interval '5 minutes') AS active "
                            "FROM editing_locks WHERE resource_type='workpaper' AND resource_id=:rid"
                        ),
                        {"rid": rid},
                    )
                ).one()
                assert bool(row[0]) == expected_active, (
                    f"迁后过期判定与源语义不一致 rid={rid} expected_active={expected_active}"
                )
        finally:
            await trans.rollback()
