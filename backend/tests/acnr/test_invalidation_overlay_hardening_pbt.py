"""Real-PG16 PBT/contract — ACNR 失效传播与 Overlay 治理加固（Wave 6）

Feature: acnr-invalidation-overlay-hardening
Properties: P1(唯一性) P2(原子upsert) P3(cache-after-commit) P4(治理持久化)
            P5(CAS) P10(Durable_Epoch 抗Redis) P11(Outbox 至少一次+单调)

一次性临时 PG16 库隔离（不污染 dev 库）。无 PG 环境 graceful skip（SQLite 不替代）。
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.migration_runner import MigrationRunner

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
V103 = MIGRATIONS_DIR / "V103__acnr_project_overlay.sql"
V122 = MIGRATIONS_DIR / "V122__acnr_invalidation_overlay_hardening.sql"


def _pg_available() -> bool:
    from app.core.config import settings
    return settings.DATABASE_URL.startswith("postgresql")


def _base_url() -> str:
    from app.core.config import settings
    head, _db = settings.DATABASE_URL.rsplit("/", 1)
    return head


def _connect_args() -> dict:
    from app.core.config import settings
    return {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}


def _split(sql: str) -> list[str]:
    return MigrationRunner._split_sql_statements(sql)


_STUB_PARENTS_SQL = """
CREATE TABLE projects (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), is_deleted boolean DEFAULT false);
CREATE TABLE wp_index (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL, wp_code varchar(40), is_deleted boolean DEFAULT false);
CREATE TABLE working_paper (id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL, wp_index_id uuid, is_deleted boolean DEFAULT false);
"""


@asynccontextmanager
async def _throwaway_engine():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    head = _base_url()
    ca = _connect_args()
    admin_url = head + "/postgres"
    tmp_db = f"acnr_hardening_{uuid.uuid4().hex[:12]}"

    admin = create_async_engine(
        admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
    )
    async with admin.connect() as c:
        await c.exec_driver_sql(f'CREATE DATABASE "{tmp_db}"')
    await admin.dispose()

    eng = create_async_engine(head + "/" + tmp_db, poolclass=NullPool, connect_args=ca)
    try:
        async with eng.begin() as conn:
            for s in _STUB_PARENTS_SQL.strip().split(";"):
                if s.strip():
                    await conn.exec_driver_sql(s)
        for f in (V103, V122):
            for s in _split(f.read_text(encoding="utf-8")):
                if s.strip():
                    async with eng.begin() as conn:
                        await conn.exec_driver_sql(s)
        yield eng
    finally:
        await eng.dispose()
        admin = create_async_engine(
            admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT", connect_args=ca
        )
        async with admin.connect() as c:
            await c.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{tmp_db}' AND pid<>pg_backend_pid()"
            )
            await c.exec_driver_sql(f'DROP DATABASE IF EXISTS "{tmp_db}"')


async def _seed_project(eng) -> uuid.UUID:
    pid = uuid.uuid4()
    async with eng.begin() as conn:
        await conn.exec_driver_sql(
            f"INSERT INTO projects (id, is_deleted) VALUES ('{pid}', false)"
        )
    return pid


pytestmark = pytest.mark.skipif(not _pg_available(), reason="需真实 PostgreSQL 16（SQLite 不替代）")


# ─── P1/P2: Overlay 唯一性 + 原子 upsert + revision 递增 ─────────────────────

@pytest.mark.asyncio
async def test_p1_p2_atomic_upsert_no_dup_revision_increments():
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr.overlay_repository import upsert_overlay

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        async with SM() as s:
            r1 = await upsert_overlay(s, project_id=pid, wp_id=None, parent_wp_code="D2",
                                      sheet_code="D2-2", overlay_type="cust", payload={"a": 1})
            r2 = await upsert_overlay(s, project_id=pid, wp_id=None, parent_wp_code="D2",
                                      sheet_code="D2-2", overlay_type="cust", payload={"a": 2})
            await s.commit()
            # 注：r1/r2 为同一 ORM 对象（identity map），r2 refresh 后 r1 也反映最新值。
            # 关键验证：冲突 UPDATE 后 revision 递增到 2（非陈旧）。
            assert r2.revision == 2  # 冲突 UPDATE → revision+1（刷新非陈旧）
        async with SM() as s:
            cnt = (await s.execute(sa.text(
                "SELECT count(*) FROM acnr_project_overlay WHERE project_id=:p "
                "AND parent_wp_code='D2' AND sheet_code='D2-2' AND overlay_type='cust'"
            ), {"p": str(pid)})).scalar_one()
            assert cnt == 1  # P1：至多一行


@pytest.mark.asyncio
async def test_p1_unique_constraint_rejects_raw_duplicate():
    """约束层兜底：绕过 upsert 的裸重复 INSERT 被 DB 拒绝（R5.3）。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        ins = (
            "INSERT INTO acnr_project_overlay (id, project_id, parent_wp_code, sheet_code, overlay_type, payload) "
            f"VALUES (gen_random_uuid(), '{pid}', 'D2', 'D2-2', 'cust', '{{}}')"
        )
        async with SM() as s:
            await s.execute(sa.text(ins))
            await s.commit()
        with pytest.raises(Exception):  # IntegrityError (unique violation)
            async with SM() as s:
                await s.execute(sa.text(ins))
                await s.commit()


# ─── P5: CAS 乐观并发 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p5_cas_conflict_rejected_db_unchanged():
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr.overlay_repository import upsert_overlay, OverlayRevisionConflict

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        async with SM() as s:
            await upsert_overlay(s, project_id=pid, wp_id=None, parent_wp_code="D2",
                                 sheet_code="D2-2", overlay_type="cust", payload={"a": 1})
            await s.commit()
        # CAS 错误 expected → 冲突，DB 不变
        async with SM() as s:
            with pytest.raises(OverlayRevisionConflict):
                await upsert_overlay(s, project_id=pid, wp_id=None, parent_wp_code="D2",
                                     sheet_code="D2-2", overlay_type="cust",
                                     payload={"a": 999}, expected_revision=999)
            await s.rollback()
        async with SM() as s:
            row = (await s.execute(sa.text(
                "SELECT payload->>'a' AS a, revision FROM acnr_project_overlay "
                "WHERE project_id=:p AND parent_wp_code='D2'"
            ), {"p": str(pid)})).first()
            assert row.a == "1" and row.revision == 1  # DB 未被冲突写改动
        # CAS 正确 expected=1 → 成功，revision→2
        async with SM() as s:
            r = await upsert_overlay(s, project_id=pid, wp_id=None, parent_wp_code="D2",
                                     sheet_code="D2-2", overlay_type="cust",
                                     payload={"a": 2}, expected_revision=1)
            await s.commit()
            assert r.revision == 2


# ─── P4: 治理字段持久化 + 重启重载 is_expired ─────────────────────────────────

@pytest.mark.asyncio
async def test_p4_governance_fields_persist_and_is_expired_after_reload():
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr.overlay_repository import upsert_overlay
    from app.services.acnr.overlay import load_project_overlays_from_pg, clear_all_overlays

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        async with SM() as s:
            await upsert_overlay(s, project_id=pid, wp_id=None, parent_wp_code="D2",
                                 sheet_code="D2-2", overlay_type="cust", payload={"a": 1},
                                 reason="past-due", owner="auditor", expires_at="2020-01-01")
            await s.commit()
        clear_all_overlays()  # 模拟进程重启（清内存缓存）
        async with SM() as s:
            patches = await load_project_overlays_from_pg(s, str(pid))
        p = patches["D2/D2-2"]
        assert p.reason == "past-due" and p.owner == "auditor"
        assert p.expires_at == "2020-01-01"
        assert p.is_expired() is True  # 重启后按持久化 expires_at 判定


# ─── P3: Cache_After_Commit（回滚不留脏缓存）─────────────────────────────────

@pytest.mark.asyncio
async def test_p3_cache_after_commit_rollback_no_dirty_cache():
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr.overlay import (
        write_overlay, load_project_overlays_from_pg, clear_all_overlays,
        get_project_overlays,
    )

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        # write_overlay 经 validate_ownership 校验 wp_code 属该项目 → seed wp_index
        async with eng.begin() as conn:
            await conn.exec_driver_sql(
                "INSERT INTO wp_index (id, project_id, wp_code, is_deleted) "
                f"VALUES (gen_random_uuid(), '{pid}', 'D2', false)"
            )
        SM = async_sessionmaker(eng, expire_on_commit=False)
        clear_all_overlays()
        # write_overlay 写 PG（flush）后清缓存；随后回滚 → PG 无该行
        async with SM() as s:
            await write_overlay(s, str(pid), "D2/D2-2", {"a": 1}, overlay_type="cust")
            # write_overlay 清了缓存（不 set 未提交状态）
            assert get_project_overlays(str(pid)) == {}
            await s.rollback()
        # 回滚后从 PG read-through 重载 → 无该 overlay（不含未提交脏状态）
        clear_all_overlays()
        async with SM() as s:
            patches = await load_project_overlays_from_pg(s, str(pid))
        assert "D2/D2-2" not in patches


# ─── P10: Durable_Epoch DB 单调（Redis 不可用仍递增）─────────────────────────

@pytest.mark.asyncio
async def test_p10_durable_epoch_db_monotonic_without_redis():
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr import cache_epoch

    async with _throwaway_engine() as eng:
        pid = str(await _seed_project(eng))
        SM = async_sessionmaker(eng, expire_on_commit=False)
        cache_epoch.set_redis_client(None)  # 模拟 Redis 不可用
        try:
            async with SM() as s:
                e1 = await cache_epoch.increment_epoch(pid, session=s)
                e2 = await cache_epoch.increment_epoch(pid, session=s)
                await s.commit()
            assert e1 == 1 and e2 == 2  # Redis 不可用 DB 仍单调递增（不返回 0 丢失）
            async with SM() as s:
                cur = await cache_epoch._read_db_epoch(pid, session=s)
            assert cur == 2
        finally:
            cache_epoch.set_redis_client(cache_epoch._UNSET)  # 复位注入哨兵


# ─── P11: Outbox 至少一次 + 单调 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p11_outbox_dispatch_advances_epoch_and_marks_dispatched():
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr import cache_epoch
    from app.services.acnr.invalidation_outbox import enqueue, _dispatch_batch

    async with _throwaway_engine() as eng:
        pid = str(await _seed_project(eng))
        SM = async_sessionmaker(eng, expire_on_commit=False)
        cache_epoch.set_redis_client(None)
        try:
            async with SM() as s:
                await enqueue(s, pid, domain="overlay")
                await enqueue(s, pid, domain="overlay")
                await s.commit()
            async with SM() as s:
                n, broadcasts = await _dispatch_batch(s)
                await s.commit()
            assert n == 2  # 处理 2 行
            assert len(broadcasts) == 2  # #5：待广播 payload 于 commit 后发送
            async with SM() as s:
                undispatched = (await s.execute(sa.text(
                    "SELECT count(*) FROM acnr_invalidation_outbox WHERE project_id=:p AND dispatched_at IS NULL"
                ), {"p": pid})).scalar_one()
                epoch = await cache_epoch._read_db_epoch(pid, session=s)
            assert undispatched == 0  # 全部投递
            assert epoch >= 2  # Durable_Epoch 至少递增 2 次（每行一次）
        finally:
            cache_epoch.set_redis_client(cache_epoch._UNSET)


# ─── P12: 受控入口 capability + ownership + 同事务 outbox ────────────────────

@pytest.mark.asyncio
async def test_p12_controlled_entry_capability_and_same_tx_outbox():
    from unittest.mock import MagicMock
    from fastapi import HTTPException
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr.overlay import apply_project_overlay, clear_all_overlays

    def _actor(role: str):
        u = MagicMock()
        u.role = MagicMock()
        u.role.value = role
        return u

    async with _throwaway_engine() as eng:
        pid = str(await _seed_project(eng))
        async with eng.begin() as conn:
            await conn.exec_driver_sql(
                "INSERT INTO wp_index (id, project_id, wp_code, is_deleted) "
                f"VALUES (gen_random_uuid(), '{pid}', 'D2', false)"
            )
        SM = async_sessionmaker(eng, expire_on_commit=False)
        clear_all_overlays()

        # capability 不足 → 403，且不写任何 overlay/outbox
        async with SM() as s:
            with pytest.raises(HTTPException) as exc:
                await apply_project_overlay(
                    s, pid, "D2/D2-2", {"a": 1}, actor=_actor("staff"), overlay_type="cust"
                )
            assert exc.value.status_code == 403
            await s.rollback()
        async with SM() as s:
            n_ovl = (await s.execute(sa.text(
                "SELECT count(*) FROM acnr_project_overlay WHERE project_id=:p"
            ), {"p": pid})).scalar_one()
            n_box = (await s.execute(sa.text(
                "SELECT count(*) FROM acnr_invalidation_outbox WHERE project_id=:p"
            ), {"p": pid})).scalar_one()
            assert n_ovl == 0 and n_box == 0

        # 授权角色 → 写 overlay + 同事务 outbox（提交后均落库）
        async with SM() as s:
            await apply_project_overlay(
                s, pid, "D2/D2-2", {"a": 1}, actor=_actor("manager"),
                reason="r", owner="mgr", overlay_type="cust",
            )
            await s.commit()
        async with SM() as s:
            n_ovl = (await s.execute(sa.text(
                "SELECT count(*) FROM acnr_project_overlay WHERE project_id=:p"
            ), {"p": pid})).scalar_one()
            n_box = (await s.execute(sa.text(
                "SELECT count(*) FROM acnr_invalidation_outbox WHERE project_id=:p AND domain='overlay'"
            ), {"p": pid})).scalar_one()
            assert n_ovl == 1 and n_box == 1  # overlay 与 outbox 同事务原子提交


@pytest.mark.asyncio
async def test_p11_dispatch_failure_keeps_undispatched_attempts_incremented():
    """投递失败 → 不标 dispatched，仅 attempts++（至少一次，R11.6）。"""
    from unittest.mock import patch
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr import cache_epoch
    from app.services.acnr.invalidation_outbox import enqueue, _dispatch_batch

    async with _throwaway_engine() as eng:
        pid = str(await _seed_project(eng))
        SM = async_sessionmaker(eng, expire_on_commit=False)
        cache_epoch.set_redis_client(None)
        try:
            async with SM() as s:
                await enqueue(s, pid, domain="overlay")
                await s.commit()
            # 模拟 increment_epoch 抛异常 → dispatch 该行失败
            # （_dispatch_batch 内惰性 import，patch 源模块 cache_epoch.increment_epoch）
            with patch(
                "app.services.acnr.cache_epoch.increment_epoch",
                side_effect=RuntimeError("boom"),
            ):
                async with SM() as s:
                    await _dispatch_batch(s)
                    await s.commit()
            async with SM() as s:
                row = (await s.execute(sa.text(
                    "SELECT dispatched_at, attempts FROM acnr_invalidation_outbox WHERE project_id=:p"
                ), {"p": pid})).first()
            assert row.dispatched_at is None  # 未标 dispatched → 会重试
            assert row.attempts == 1  # attempts++
        finally:
            cache_epoch.set_redis_client(cache_epoch._UNSET)


# ─── 复盘加固 #3/#4/#5：Outbox 生命周期（prune / 死信 / 广播后置）────────────────

@pytest.mark.asyncio
async def test_outbox_deadletter_excludes_poison_rows_from_dispatch():
    """#4 死信：attempts >= MAX 的毒行不再被 _dispatch_batch 选中（不占批次槽位/不永久重试）。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr import cache_epoch
    from app.services.acnr.invalidation_outbox import (
        enqueue, _dispatch_batch, MAX_DISPATCH_ATTEMPTS,
    )

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        cache_epoch.set_redis_client(None)
        try:
            async with SM() as s:
                # 毒行：attempts 已达上限
                await enqueue(s, pid, domain="overlay")
                await enqueue(s, pid, domain="overlay")  # 正常行
                await s.commit()
            # 把第一行 attempts 置到 MAX（模拟已连续失败到阈值）
            async with SM() as s:
                await s.execute(sa.text(
                    "UPDATE acnr_invalidation_outbox SET attempts = :m "
                    "WHERE id = (SELECT id FROM acnr_invalidation_outbox "
                    "WHERE project_id=:p ORDER BY created_at LIMIT 1)"
                ), {"m": MAX_DISPATCH_ATTEMPTS, "p": pid})
                await s.commit()
            # dispatch：只应处理 1 行（正常行），毒行被排除
            async with SM() as s:
                n, broadcasts = await _dispatch_batch(s)
                await s.commit()
            assert n == 1
            assert len(broadcasts) == 1
            # 毒行仍在表中（保留供排查），未被标 dispatched
            async with SM() as s:
                poison = (await s.execute(sa.text(
                    "SELECT count(*) FROM acnr_invalidation_outbox "
                    "WHERE project_id=:p AND attempts >= :m AND dispatched_at IS NULL"
                ), {"p": pid, "m": MAX_DISPATCH_ATTEMPTS})).scalar_one()
            assert poison == 1  # 死信行保留，从活跃队列剔除
        finally:
            cache_epoch.set_redis_client(cache_epoch._UNSET)


@pytest.mark.asyncio
async def test_outbox_dispatch_defers_broadcast_until_after_commit():
    """#5 广播后置：_dispatch_batch 本身不 broadcast_raw（仅收集 payload），
    广播由 run_once 在 commit 之后发送。"""
    from unittest.mock import patch
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr import cache_epoch
    from app.services.acnr.invalidation_outbox import enqueue, _dispatch_batch

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        cache_epoch.set_redis_client(None)
        try:
            async with SM() as s:
                await enqueue(s, pid, domain="overlay")
                await s.commit()
            with patch("app.services.event_bus.event_bus.broadcast_raw") as mock_bc:
                async with SM() as s:
                    n, broadcasts = await _dispatch_batch(s)
                    await s.commit()
                # _dispatch_batch 内不广播（延后到 run_once 提交后）
                mock_bc.assert_not_called()
            assert n == 1 and len(broadcasts) == 1
            assert broadcasts[0]["project_id"] == str(pid)
        finally:
            cache_epoch.set_redis_client(cache_epoch._UNSET)


@pytest.mark.asyncio
async def test_outbox_prune_deletes_old_dispatched_only():
    """#3 prune：删除 older_than_days 之前的已投递行；未投递行 + 近期已投递行保留。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.services.acnr.invalidation_outbox import enqueue, prune_dispatched

    async with _throwaway_engine() as eng:
        pid = await _seed_project(eng)
        SM = async_sessionmaker(eng, expire_on_commit=False)
        async with SM() as s:
            await enqueue(s, pid, domain="old")      # 将标为旧的已投递
            await enqueue(s, pid, domain="recent")   # 近期已投递
            await enqueue(s, pid, domain="pending")  # 未投递
            await s.commit()
        # 旧已投递：dispatched_at = 30 天前
        async with SM() as s:
            await s.execute(sa.text(
                "UPDATE acnr_invalidation_outbox SET dispatched_at = now() - interval '30 days' "
                "WHERE project_id=:p AND domain='old'"
            ), {"p": pid})
            # 近期已投递：dispatched_at = now
            await s.execute(sa.text(
                "UPDATE acnr_invalidation_outbox SET dispatched_at = now() "
                "WHERE project_id=:p AND domain='recent'"
            ), {"p": pid})
            await s.commit()
        async with SM() as s:
            deleted = await prune_dispatched(s, older_than_days=7)
            await s.commit()
        assert deleted == 1  # 仅删旧已投递行
        async with SM() as s:
            remaining = (await s.execute(sa.text(
                "SELECT domain FROM acnr_invalidation_outbox WHERE project_id=:p ORDER BY domain"
            ), {"p": pid})).scalars().all()
        assert remaining == ["pending", "recent"]  # 旧已投递被删，其余保留
