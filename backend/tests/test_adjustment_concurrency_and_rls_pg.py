"""B9 / F4：调整分录组的真双事务并发与 FORCE RLS 强制隔离验收。

背景（为什么单独一个文件）
--------------------------
1. ``_adjustment_booking_pg_support.booking_pg_world`` 是**单连接回滚事务**夹具，
   无法做"两个事务同时持锁"或"非 superuser 角色读"这类验收；
2. 共享库的应用账号是 ``postgres``（``rolsuper = rolbypassrls = true``），
   ``FORCE ROW LEVEL SECURITY`` 对超级用户**不生效** —— 现有的
   ``test_adjustment_b9_integrity_pg::test_pg_adjustment_rls_objects_are_force_enabled``
   只能断言 ``relrowsecurity / relforcerowsecurity`` 元数据，证明不了真的隔离；
3. 本文件的所有用例都**只在专用验收库**里跑（``GT_ADJ_ACCEPT_DB_URL``），
   连共享库时整体 skip。验收库由 ``scripts/e2e/create_adjustment_accept_db.py``
   一次性建好（结构克隆 + V235 + 非 superuser 探针角色），不碰共享库数据。

跑法::

    python backend/scripts/e2e/create_adjustment_accept_db.py
    set GT_ADJ_ACCEPT_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/gt_adj_accept
    python -m pytest backend/tests/test_adjustment_concurrency_and_rls_pg.py -v
"""
from __future__ import annotations

import asyncio
import importlib
import os
import pkgutil
import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

ACCEPT_URL_ENV = "GT_ADJ_ACCEPT_DB_URL"
_PROBE_ROLE = "gt_rls_probe"
_PROBE_PASSWORD = "gt_rls_probe_pw"


def _accept_url() -> str:
    url = (os.environ.get(ACCEPT_URL_ENV) or "").strip()
    if not url:
        pytest.skip(
            f"需要专用验收库：设置 {ACCEPT_URL_ENV}（见 scripts/e2e/create_adjustment_accept_db.py）"
        )
    if not url.startswith("postgresql"):
        pytest.skip(f"{ACCEPT_URL_ENV} 必须是 PostgreSQL 连接串")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _load_all_models() -> None:
    """导入 app.models 全部模块：ORM 关系解析需要所有表都在 metadata 里。"""
    import app.models as models_pkg

    for mod in pkgutil.iter_modules(models_pkg.__path__):
        if mod.name.startswith("_"):
            continue
        importlib.import_module(f"app.models.{mod.name}")


@pytest.fixture(scope="module", autouse=True)
def _models_loaded():
    _load_all_models()


@pytest.fixture
async def accept_db():
    """验收库的两个独立连接池 + 一个【测试】项目，用完按项目粒度清理。"""
    _accept_url()  # 前置校验（不满足即 skip）
    from app.core.config import settings
    from app.models.base import UserRole
    from app.models.core import Project, ProjectStatus, ProjectType, User

    url = settings.__class__(DATABASE_URL=_accept_url()).DATABASE_URL  # 归一化后的同值
    engines = [create_async_engine(url, poolclass=NullPool) for _ in range(2)]
    sessions = [
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        for engine in engines
    ]
    actor_id, project_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with sessions[0]() as db:
            db.add(User(
                id=actor_id, username=f"t_adj_cc_{uuid.uuid4().hex[:8]}",
                email=f"t_adj_cc_{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="x", role=UserRole.manager,
            ))
            await db.flush()
            db.add(Project(
                id=project_id,
                name=f"【测试】调整并发 {uuid.uuid4().hex[:8]}",
                client_name="【测试】调整并发",
                project_type=ProjectType.annual, status=ProjectStatus.execution,
                company_code="913500001234567890", created_by=actor_id,
            ))
            await db.commit()
        yield {"sessions": sessions, "actor_id": actor_id, "project_id": project_id}
    finally:
        async with sessions[0]() as db:
            # 🔴 每条独立事务：任一语句失败会让 PG 事务 aborted、连带后面全挂。
            # 清单要覆盖 handler 自开 session 写的表（import_event_consumptions /
            # tb_change_history / event_cascade_log），否则 projects 删不掉。
            # 顺序要紧：先删引用 projects/users 的子表，再删父表。
            # 本文件会跑真实 handler，它们自开连接写 import_event_consumptions /
            # tb_change_history / event_cascade_log / logs —— 漏一张 projects 就删不掉。
            for sql in (
                "delete from event_outbox_dlq where project_id = :p",
                "delete from import_event_consumptions where project_id = :p",
                "delete from import_event_outbox where project_id = :p",
                "delete from event_cascade_log where project_id = :p",
                "delete from tb_change_history where project_id = :p",
                "delete from adjustment_treatment_events where project_id = :p",
                "delete from adjustment_client_bookings where project_id = :p",
                "delete from adjustment_review_tasks where project_id = :p",
                "delete from adjustment_entries where entry_group_id in "
                "(select entry_group_id from adjustments where project_id = :p)",
                "delete from adjustments where project_id = :p",
                "delete from trial_balance where project_id = :p",
                "delete from account_chart where project_id = :p",
                "delete from logs where user_id = :u",
                "delete from logs where user_id in "
                "(select id from users where username like 't_adj_rv\\_%')",
                "delete from tb_change_history where operator_id in "
                "(select id from users where username like 't_adj_rv\\_%')",
                "delete from adjustment_review_tasks where submitted_by = :u",
                "delete from adjustment_review_tasks where decided_by in "
                "(select id from users where username like 't_adj_rv\\_%')",
                "delete from projects where id = :p",
                "delete from users where id = :u",
                "delete from users where username like 't_adj_rv\\_%'",
            ):
                try:
                    await db.execute(sa.text(sql), {"p": project_id, "u": actor_id})
                    await db.commit()
                except Exception:  # noqa: BLE001 - 表可能不存在；回滚后继续下一条
                    await db.rollback()
        for engine in engines:
            await engine.dispose()


async def _draft_group(factory, *, project_id, actor_id, adjustment_no: str) -> uuid.UUID:
    from app.models.audit_platform_models import AdjustmentType, ReviewStatus
    from app.services.adjustment_group_writer import AdjustmentGroupLine, AdjustmentGroupWriter

    group_id = uuid.uuid4()
    async with factory() as db:
        await AdjustmentGroupWriter(db).write_group(
            project_id=project_id, year=2025, company_code="001",
            adjustment_no=adjustment_no, adjustment_type=AdjustmentType.aje,
            description="并发验收", entry_group_id=group_id,
            lines=[
                AdjustmentGroupLine(standard_account_code="1122", account_name="应收账款",
                                    debit_amount=Decimal("10")),
                AdjustmentGroupLine(standard_account_code="6702", account_name="信用减值损失",
                                    credit_amount=Decimal("10")),
            ],
            content_revision=1, audit_phase="final",
            review_status=ReviewStatus.draft, created_by=actor_id,
        )
        await db.commit()
    return group_id


async def _revision(factory, group_id: uuid.UUID) -> int:
    async with factory() as db:
        return int((await db.execute(sa.text(
            "select content_revision from adjustments "
            "where entry_group_id = :g and is_deleted = false limit 1"
        ), {"g": group_id})).scalar_one())


# ---------------------------------------------------------------------------
# F4-1：两个事务同版本并发编辑 → 只有一个成功（行锁 + CAS）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_two_transactions_editing_same_group_only_one_wins(accept_db):
    from app.models.audit_platform_schemas import AdjustmentUpdate
    from app.services.adjustment_service import AdjustmentService

    sessions = accept_db["sessions"]
    project_id, actor_id = accept_db["project_id"], accept_db["actor_id"]
    group_id = await _draft_group(sessions[0], project_id=project_id,
                                  actor_id=actor_id, adjustment_no="AJE-CC-EDIT-1")
    current = await _revision(sessions[0], group_id)
    barrier = asyncio.Barrier(2)

    async def racer(label: str, index: int):
        async with sessions[index]() as db:
            await barrier.wait()
            try:
                result = await AdjustmentService(db).update_entry(
                    project_id, group_id,
                    AdjustmentUpdate(expected_revision=current, description=f"{label} 并发编辑"),
                    actor_id,
                )
                await asyncio.sleep(0.3)  # 持锁到对方也尝试过
                await db.commit()
                return (label, "ok", result.content_revision)
            except Exception as exc:  # noqa: BLE001 - 用分支断言区分预期冲突与死锁
                await db.rollback()
                return (label, type(exc).__name__, str(exc))

    outcomes = await asyncio.wait_for(
        asyncio.gather(racer("T1", 0), racer("T2", 1)), timeout=60,
    )
    winners = [item for item in outcomes if item[1] == "ok"]
    losers = [item for item in outcomes if item[1] != "ok"]
    assert len(winners) == 1, f"同版本并发编辑应恰好一个成功，实际 {outcomes}"
    assert len(losers) == 1
    # 失败方必须是**业务版本冲突**，不是锁超时 / 死锁这类基础设施错误
    assert losers[0][1] == "ValueError", outcomes
    assert "版本" in losers[0][2], outcomes
    # 版本只前进一次
    assert await _revision(sessions[0], group_id) == current + 1


# ---------------------------------------------------------------------------
# F4-2：陈旧版本串行编辑被拒（回归基线，证明判据不是恒绿）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stale_revision_serial_edit_is_rejected(accept_db):
    from app.models.audit_platform_schemas import AdjustmentUpdate
    from app.services.adjustment_service import AdjustmentService

    sessions = accept_db["sessions"]
    project_id, actor_id = accept_db["project_id"], accept_db["actor_id"]
    group_id = await _draft_group(sessions[0], project_id=project_id,
                                  actor_id=actor_id, adjustment_no="AJE-CC-STALE-1")
    before = await _revision(sessions[0], group_id)

    async with sessions[0]() as db:
        updated = await AdjustmentService(db).update_entry(
            project_id, group_id,
            AdjustmentUpdate(expected_revision=before, description="第一次编辑"),
            actor_id,
        )
        await db.commit()
        assert updated.content_revision == before + 1

    async with sessions[1]() as db:
        with pytest.raises(ValueError, match="版本"):
            await AdjustmentService(db).update_entry(
                project_id, group_id,
                AdjustmentUpdate(expected_revision=before, description="陈旧编辑"),
                actor_id,
            )
        await db.rollback()


# ---------------------------------------------------------------------------
# F4-3：双人并发批准同一分录组 → 只有一个成功
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_two_reviewers_approving_same_group_only_one_wins(accept_db, monkeypatch):
    """并发批准：行锁 + 任务状态机 + 版本校验，第二个必须被拒。

    ``AdjustmentReviewCoordinator.decide`` 内部会调 TB 与证据服务；本用例只验证
    **并发闸门**，因此把外部副作用（TB 重算 / outbox / 证据）替换成空实现，
    分录组状态、行锁、任务状态机走真实代码路径。
    """
    from app.models.audit_platform_models import ReviewStatus
    from app.models.audit_platform_schemas import ReviewStatusChange
    from app.services import adjustment_review_task_service as tasks
    from app.services.adjustment_service import AdjustmentService

    sessions = accept_db["sessions"]
    project_id, actor_id = accept_db["project_id"], accept_db["actor_id"]
    group_id = await _draft_group(sessions[0], project_id=project_id,
                                  actor_id=actor_id, adjustment_no="AJE-CC-APPROVE-1")

    # 两个不同复核人（SELF_REVIEW_FORBIDDEN 要求复核人 ≠ 编制人）
    from app.models.base import UserRole
    from app.models.core import User

    reviewer_ids = []
    async with sessions[0]() as db:
        for _ in range(2):
            reviewer = User(
                id=uuid.uuid4(), username=f"t_adj_rv_{uuid.uuid4().hex[:8]}",
                email=f"t_adj_rv_{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="x", role=UserRole.manager,
            )
            db.add(reviewer)
            reviewer_ids.append((reviewer.id, reviewer.username))
        await db.commit()

    # 提交复核（生成真实 pending 任务，指派两个复核人）
    async with sessions[0]() as db:
        svc = AdjustmentService(db)
        rows = await svc._get_group_rows(project_id, group_id, for_update=True)
        await tasks.create_task(
            db, project_id=project_id, year=2025, rows=rows,
            reviewer_ids=[str(rid) for rid, _ in reviewer_ids],
            submitted_by=actor_id, note="并发批准验收",
        )
        await svc.change_review_status(
            project_id, group_id,
            ReviewStatusChange(status=ReviewStatus.pending_review, expected_revision=rows[0].content_revision),
            actor_id,
        )
        await db.commit()

    # 只在**并发闸门**上比较：把 decide 之后的重活换掉，保留锁与状态机
    from app.services import adjustment_review_coordinator as coordinator_module

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        coordinator_module.AdjustmentReviewCoordinator, "ensure_tb_rows", _noop,
    )

    class _FakeTb:
        def __init__(self, *_a, **_k):
            pass

        async def recalc_adjustments(self, *_a, **_k):
            return None

        async def recalc_audited(self, *_a, **_k):
            return None

    monkeypatch.setattr(coordinator_module, "TrialBalanceService", _FakeTb, raising=False)

    async def _record_initial_inclusion(*_a, **_k):
        return None

    import app.services.adjustment_treatment_service as treatment_module
    monkeypatch.setattr(treatment_module, "record_initial_inclusion", _record_initial_inclusion)

    from app.services.workpaper_sync.outbox import DurableEventOutboxService

    async def _skip_enqueue(*_a, **_k):
        # 返回一个占位 publication：并发闸门在 enqueue 之前就该拦住第二个
        return None

    monkeypatch.setattr(DurableEventOutboxService, "enqueue_event", _skip_enqueue)

    barrier = asyncio.Barrier(2)

    async def approver(label: str, index: int, user_id, username: str):
        from app.models.core import User as UserModel

        async with sessions[index]() as db:
            actor = await db.get(UserModel, user_id)
            await barrier.wait()
            try:
                await coordinator_module.AdjustmentReviewCoordinator(db).decide(
                    project_id=project_id, entry_group_id=group_id,
                    status=ReviewStatus.approved, actor=actor,
                    reason=f"{label} 批准",
                )
                await asyncio.sleep(0.3)
                await db.commit()
                return (label, "ok")
            except Exception as exc:  # noqa: BLE001
                await db.rollback()
                return (label, type(exc).__name__, str(exc)[:120])

    outcomes = await asyncio.wait_for(
        asyncio.gather(
            approver("A1", 0, reviewer_ids[0][0], reviewer_ids[0][1]),
            approver("A2", 1, reviewer_ids[1][0], reviewer_ids[1][1]),
        ),
        timeout=90,
    )
    winners = [item for item in outcomes if item[1] == "ok"]
    assert len(winners) == 1, f"并发批准应恰好一个成功，实际 {outcomes}"

    # 库里只留一个终态批准任务，一个 active pending 都没有
    async with sessions[0]() as db:
        statuses = [str(getattr(row, "value", row)) for row in (await db.execute(sa.text(
            "select status from adjustment_review_tasks "
            "where project_id = :p and entry_group_id = :g and is_deleted = false order by created_at"
        ), {"p": project_id, "g": group_id})).scalars().all()]
        assert statuses.count("approved") == 1, statuses
        assert "pending" not in statuses, statuses


# ---------------------------------------------------------------------------
# F4-4：真实 RLS —— 非 superuser 角色只能看到当前项目（fail closed）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_force_rls_isolates_projects_for_non_superuser_role(accept_db):
    """用 NOSUPERUSER NOBYPASSRLS 角色读三张调整新表，逐表验证隔离与 fail-closed。

    超级用户对照必须"能看到"，否则本用例证明不了 RLS 真的在起作用（可能是空表）。

    🔴 变异口径（2026-11-15 实测）：把 ``FORCE ROW LEVEL SECURITY`` 改成
    ``NO FORCE`` **打不红**本用例 —— ``gt_rls_probe`` 不是表 owner，
    ``ENABLE ROW LEVEL SECURITY`` 已足以约束它；``FORCE`` 只影响 owner。
    真正能打红的变异是 ``DROP POLICY project_isolation``（实测三张表计数全变 0
    ⇒ 断言失败）。因此本用例除了行为断言，还断言策略确实存在，
    以免"策略被删但恰好没数据"这类静默退化。
    """
    sessions = accept_db["sessions"]
    admin_factory = sessions[0]
    project_a, actor_id = accept_db["project_id"], accept_db["actor_id"]
    project_b = uuid.uuid4()

    from app.models.core import Project, ProjectStatus, ProjectType
    async with admin_factory() as db:
        db.add(Project(
            id=project_b, name=f"【测试】调整并发B {uuid.uuid4().hex[:8]}",
            client_name="【测试】调整并发B", project_type=ProjectType.annual,
            status=ProjectStatus.execution, company_code="913500001234567890",
            created_by=actor_id,
        ))
        await db.commit()

    group_a = await _draft_group(admin_factory, project_id=project_a,
                                 actor_id=actor_id, adjustment_no="AJE-RLS-A")
    group_b = await _draft_group(admin_factory, project_id=project_b,
                                 actor_id=actor_id, adjustment_no="AJE-RLS-B")

    # 三张新表各插一行（走真实列约束）
    async with admin_factory() as db:
        for project_id, group_id in ((project_a, group_a), (project_b, group_b)):
            await db.execute(sa.text("""
                insert into adjustment_client_bookings
                    (id, project_id, year, entry_group_id, action, sequence, voucher_keys, created_by)
                values (:id, :p, 2025, :g, 'book', 1, '[]'::jsonb, :u)
            """), {"id": uuid.uuid4(), "p": project_id, "g": group_id, "u": actor_id})
            await db.execute(sa.text("""
                insert into adjustment_treatment_events
                    (id, project_id, year, entry_group_id, sequence, action, reason, created_by)
                values (:id, :p, 2025, :g, 1, 'include_in_working_tb', 'RLS 探针', :u)
            """), {"id": uuid.uuid4(), "p": project_id, "g": group_id, "u": actor_id})
            await db.execute(sa.text("""
                insert into adjustment_review_tasks
                    (id, project_id, year, entry_group_id, status, required_level,
                     revision, group_content_revision, assigned_reviewer_ids, submitted_by)
                values (:id, :p, 2025, :g, 'withdrawn', 'manager', 1, 1, '[]'::jsonb, :u)
            """), {"id": uuid.uuid4(), "p": project_id, "g": group_id, "u": actor_id})
        await db.commit()

    tables = ("adjustment_client_bookings", "adjustment_treatment_events", "adjustment_review_tasks")

    async def visible_counts(url: str, *, ctx_project, use_role: bool) -> dict[str, int]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                if use_role:
                    await conn.execute(sa.text(f'SET ROLE "{_PROBE_ROLE}"'))
                await conn.execute(
                    sa.text("select set_config('app.current_project_id', :v, false)"),
                    {"v": str(ctx_project) if ctx_project else ""},
                )
                counts = {}
                for table in tables:
                    counts[table] = int(await conn.scalar(
                        sa.text(f"select count(*) from {table}")  # noqa: S608 - 表名来自常量元组
                    ) or 0)
                if use_role:
                    await conn.execute(sa.text("RESET ROLE"))
                return counts
        finally:
            await engine.dispose()

    url = _accept_url()

    # ⓪ 前置：三张表必须各有一条 project_isolation 策略（策略被删则隔离静默失效）
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            policy_tables = {row[0] for row in (await conn.execute(sa.text("""
                select tablename from pg_policies
                where schemaname = 'public' and policyname = 'project_isolation'
            """))).all()}
            missing = set(tables) - policy_tables
            assert not missing, f"缺少 project_isolation 策略：{sorted(missing)}"
    finally:
        await engine.dispose()

    # ① 超级用户对照：能看到两行（证明数据真的写进去了）
    superuser_counts = await visible_counts(url, ctx_project=project_a, use_role=False)
    assert all(count >= 2 for count in superuser_counts.values()), superuser_counts

    # ② 非 superuser 且上下文 = 项目 A：每张表恰好看到 1 行
    role_counts_a = await visible_counts(url, ctx_project=project_a, use_role=True)
    assert role_counts_a == {table: 1 for table in tables}, role_counts_a

    # ③ 上下文 = 项目 B：也恰好 1 行，且不是同一批（换成 B 的视角）
    role_counts_b = await visible_counts(url, ctx_project=project_b, use_role=True)
    assert role_counts_b == {table: 1 for table in tables}, role_counts_b

    # ④ 上下文为空 → fail closed，0 行
    role_counts_none = await visible_counts(url, ctx_project=None, use_role=True)
    assert role_counts_none == {table: 0 for table in tables}, role_counts_none

    # 清理项目 B
    async with admin_factory() as db:
        for sql in (
            "delete from adjustment_treatment_events where project_id = :p",
            "delete from adjustment_client_bookings where project_id = :p",
            "delete from adjustment_review_tasks where project_id = :p",
            "delete from adjustment_entries where entry_group_id in "
            "(select entry_group_id from adjustments where project_id = :p)",
            "delete from adjustments where project_id = :p",
            "delete from projects where id = :p",
        ):
            await db.execute(sa.text(sql), {"p": project_b})
        await db.commit()
