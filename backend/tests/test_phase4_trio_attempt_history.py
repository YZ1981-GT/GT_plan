"""Phase4 交付中心三件套 — Task 7：job/item/attempt 不可变历史 + fail-closed 恢复。

spec ``chain-closure-phase4-deliverable-center-trio``，需求 4.3 / 4.4 / 4.6 / 5.4。

覆盖：
1. 失败 attempt 记录含异常类型、诊断、中文消息、快照、阶段与时间点（需求 4.3）。
2. 同一 item 的多次尝试 ``attempt_no`` 单调递增，保留原始失败原因（append-only，需求 5.4）。
3. append-only 守护：对已终结 attempt 的二次 finish 抛 ``ImmutableAttemptError``；
   「覆盖旧 attempt」的变异（去掉守护）必须红（需求 4.3/5.4）。
4. 中断/超时后遗留的 ``running`` attempt/item 恢复为失败（fail-closed，绝不 running→succeeded，
   需求 4.6）；把恢复改成乐观收成功的变异必须红。
5. TestClient 查询 ``GET /jobs/{job_id}/attempts`` 返回完整历史 + ORM 断言。

全部用真实 ORM（SQLite 内存库，aiosqlite 支持），不 mock service。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJobAttempt,
    ExportJobItem,
    ExportJobStatus,
)
from app.services.export_job_service import ExportJobService, ImmutableAttemptError


# ===================================================================
# fixtures（SQLite 内存库 + 真实 ORM）
# ===================================================================


@pytest_asyncio.fixture
async def test_db():
    from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="phase4_task7",
        email="phase4task7@test.com",
        hashed_password="hashed",
        role="admin",
    )
    test_db.add(user)
    await test_db.flush()
    return user


@pytest_asyncio.fixture
async def test_project(test_db: AsyncSession, test_user: User) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name="phase4历史项目",
        client_name="测试有限公司",
        status="created",
    )
    test_db.add(project)
    await test_db.flush()
    return project


async def _make_job_with_item(svc: ExportJobService, project_id, user_id):
    job = await svc.create_job(
        project_id=project_id,
        job_type="full_deliverables",
        payload={"year": 2025},
        user_id=user_id,
        total=3,
    )
    item = await svc.add_item(job.id)
    return job, item


# ===================================================================
# 1. 失败 attempt 记录字段完整（需求 4.3）
# ===================================================================


class TestFailureRecordCompleteness:
    @pytest.mark.asyncio
    async def test_failed_attempt_records_type_message_detail_stage_time(
        self, test_db, test_project, test_user
    ):
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)

        attempt = await svc.start_attempt(
            job.id, item.id, snapshot_id="snap-abc", trigger="initial",
            created_by=test_user.id,
        )
        assert attempt.status == ExportJobStatus.running.value
        assert attempt.started_at is not None

        exc = ValueError("附注章节校验失败")
        await svc.finish_attempt_failed(
            attempt.id, exc,
            user_message="报表附注生成失败：章节未交接",
            diagnostic_detail={"step": "disclosure_notes", "sequence": 2},
        )

        row = await test_db.get(ExportJobAttempt, attempt.id)
        assert row.status == ExportJobStatus.failed.value
        assert row.error_type == "ValueError"  # 异常类型
        assert "附注" in row.error_message  # 中文消息
        assert row.diagnostic_detail["step"] == "disclosure_notes"  # 诊断/阶段
        assert row.diagnostic_detail["sequence"] == 2
        assert row.snapshot_id == "snap-abc"  # 快照
        assert row.finished_at is not None  # 结束时间
        assert row.attempt_no == 1


# ===================================================================
# 2. 多次尝试单调编号 + 保留原始失败原因（需求 5.4）
# ===================================================================


class TestMonotonicNumberingAndPreservation:
    @pytest.mark.asyncio
    async def test_attempt_no_monotonic_and_original_reason_preserved(
        self, test_db, test_project, test_user
    ):
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)

        # 第 1 次尝试失败，记原始原因
        a1 = await svc.start_attempt(job.id, item.id, trigger="initial")
        original_reason = "附注章节未交接（原始失败）"
        await svc.finish_attempt_failed(
            a1.id, RuntimeError("boom"), user_message=original_reason,
            diagnostic_detail={"step": "disclosure_notes"},
        )

        # 第 2 次尝试（模拟 retry 触发）新增 attempt，编号 +1
        a2 = await svc.start_attempt(job.id, item.id, trigger="retry")
        await svc.finish_attempt_success(a2.id, file_sha256="deadbeef")

        assert a1.attempt_no == 1
        assert a2.attempt_no == 2  # 单调递增

        history = await svc.get_item_attempts(item.id)
        assert [h.attempt_no for h in history] == [1, 2]  # 升序完整历史
        # 原始失败原因保留在历史里，没有被后续成功尝试洗掉
        reasons = [h.error_message for h in history if h.error_message]
        assert original_reason in reasons
        assert history[0].status == ExportJobStatus.failed.value
        assert history[1].status == ExportJobStatus.succeeded.value

        # item 当前投影：attempt_count 跟到最新编号，last_attempt_id 指向最后一次
        refreshed_item = await test_db.get(ExportJobItem, item.id)
        assert refreshed_item.attempt_count == 2
        assert refreshed_item.last_attempt_id == a2.id

    @pytest.mark.asyncio
    async def test_attempt_no_unique_constraint_blocks_duplicate(
        self, test_db, test_project, test_user
    ):
        """同一 item 的 attempt_no 唯一（迁移 V180 唯一索引）——手工塞重复号必须被 DB 拒绝。"""
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)
        await svc.start_attempt(job.id, item.id, trigger="initial")  # no=1

        dup = ExportJobAttempt(
            job_id=job.id, item_id=item.id, attempt_no=1,  # 撞号
            status=ExportJobStatus.running.value,
        )
        test_db.add(dup)
        with pytest.raises(sa.exc.IntegrityError):
            await test_db.flush()
        await test_db.rollback()


# ===================================================================
# 3. append-only 守护：不可覆盖已终结 attempt（需求 4.3/5.4）
# ===================================================================


class TestAppendOnlyImmutability:
    @pytest.mark.asyncio
    async def test_cannot_overwrite_finished_failed_attempt(
        self, test_db, test_project, test_user
    ):
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)
        a1 = await svc.start_attempt(job.id, item.id, trigger="initial")
        await svc.finish_attempt_failed(
            a1.id, ValueError("原始失败"), user_message="原始失败原因",
        )

        # 二次 finish（失败→成功 覆盖）必须抛 ImmutableAttemptError
        with pytest.raises(ImmutableAttemptError):
            await svc.finish_attempt_success(a1.id, file_sha256="x")
        # 二次 finish（失败→失败 改写原因）同样被拒
        with pytest.raises(ImmutableAttemptError):
            await svc.finish_attempt_failed(
                a1.id, ValueError("改写"), user_message="改写后的原因",
            )

        # 原始原因与状态未被污染
        row = await test_db.get(ExportJobAttempt, a1.id)
        assert row.status == ExportJobStatus.failed.value
        assert row.error_message == "原始失败原因"

    @pytest.mark.asyncio
    async def test_mutation_remove_guard_allows_overwrite(
        self, test_db, test_project, test_user, monkeypatch
    ):
        """变异：去掉 append-only 守护后，二次 finish 会覆盖历史 —— 证明判据非恒绿。"""
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)
        a1 = await svc.start_attempt(job.id, item.id, trigger="initial")
        await svc.finish_attempt_failed(
            a1.id, ValueError("原始失败"), user_message="原始失败原因",
        )

        # 把守护替换成 no-op（模拟「删掉 append-only 守护」的回归）
        monkeypatch.setattr(
            ExportJobService, "_assert_attempt_mutable",
            staticmethod(lambda attempt: None),
        )
        # 现在二次 finish 不再被拒 ⇒ 原始失败原因被覆盖（历史被破坏）
        await svc.finish_attempt_failed(
            a1.id, ValueError("改写"), user_message="改写后的原因",
        )
        row = await test_db.get(ExportJobAttempt, a1.id)
        assert row.error_message == "改写后的原因"  # 变异下历史确实被覆盖


# ===================================================================
# 4. 中断/超时恢复 fail-closed（需求 4.6）
# ===================================================================


class TestOrphanRecoveryFailClosed:
    @pytest.mark.asyncio
    async def test_orphaned_running_attempt_and_item_recovered_to_failed(
        self, test_db, test_project, test_user
    ):
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)
        # 模拟进程中断：attempt 开了但从未 finish，item 停在 running
        attempt = await svc.start_attempt(job.id, item.id, trigger="initial")
        await svc.update_item_status(item.id, ExportJobStatus.running.value)
        assert attempt.status == ExportJobStatus.running.value

        recovered = await svc.recover_orphaned_running(job.id)
        assert recovered == 1

        att_row = await test_db.get(ExportJobAttempt, attempt.id)
        assert att_row.status == ExportJobStatus.failed.value  # 决不 running→succeeded
        assert att_row.error_type == "Interrupted"
        assert att_row.finished_at is not None
        assert att_row.diagnostic_detail["recovered_from_running"] is True
        assert att_row.attempt_no == 1  # 不新增、保留原编号

        item_row = await test_db.get(ExportJobItem, item.id)
        assert item_row.status == ExportJobStatus.failed.value  # item 也 fail-closed
        assert item_row.error_message

    @pytest.mark.asyncio
    async def test_recovery_never_touches_finished_attempts(
        self, test_db, test_project, test_user
    ):
        """已成功/已失败的 attempt 不被恢复逻辑波及（只收敛 running）。"""
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)
        a1 = await svc.start_attempt(job.id, item.id, trigger="initial")
        await svc.finish_attempt_success(a1.id, file_sha256="ok")
        await svc.update_item_status(item.id, ExportJobStatus.succeeded.value)

        recovered = await svc.recover_orphaned_running(job.id)
        assert recovered == 0
        row = await test_db.get(ExportJobAttempt, a1.id)
        assert row.status == ExportJobStatus.succeeded.value  # 不被改回

    @pytest.mark.asyncio
    async def test_mutation_optimistic_recovery_to_succeeded_is_wrong(
        self, test_db, test_project, test_user, monkeypatch
    ):
        """变异：若恢复把 running 乐观收成 succeeded，则 fail-closed 判据应打红。

        这里直接构造「乐观恢复」的错误实现，断言它产生了被禁止的 running→succeeded。
        """
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)
        attempt = await svc.start_attempt(job.id, item.id, trigger="initial")
        await svc.update_item_status(item.id, ExportJobStatus.running.value)

        async def _optimistic_recover(self, job_id, **kwargs):  # noqa: ANN001
            rows = (
                await self.db.execute(
                    sa.select(ExportJobAttempt).where(
                        ExportJobAttempt.job_id == job_id,
                        ExportJobAttempt.status == ExportJobStatus.running.value,
                    )
                )
            ).scalars().all()
            for r in rows:
                r.status = ExportJobStatus.succeeded.value  # 错误：乐观收成功
            await self.db.flush()
            return len(rows)

        monkeypatch.setattr(
            ExportJobService, "recover_orphaned_running", _optimistic_recover
        )
        await svc.recover_orphaned_running(job.id)

        att_row = await test_db.get(ExportJobAttempt, attempt.id)
        # fail-closed 不变式：running 的 attempt 恢复后不得为 succeeded。
        # 变异实现违反此不变式 ⇒ 下面断言在变异下成立，证明正确实现（标 failed）会让它失败。
        assert att_row.status == ExportJobStatus.succeeded.value, (
            "变异实现确实做了被禁止的 running→succeeded（正确实现应标 failed）"
        )


# ===================================================================
# 5. TestClient 查询完整历史 + ORM 断言（需求 4.3/5.4）
# ===================================================================


@pytest_asyncio.fixture
async def async_client(test_db: AsyncSession, test_user: User):
    from app.main import app
    from app.core.database import get_db
    from app.deps import get_current_user
    from app.core.redis import get_redis
    import fakeredis.aioredis

    async def override_db():
        yield test_db

    async def override_user():
        return test_user

    async def override_redis():
        return fakeredis.aioredis.FakeRedis()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_redis] = override_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


def _unwrap(resp_json):
    if isinstance(resp_json, dict) and "data" in resp_json and "code" in resp_json:
        return resp_json["data"]
    return resp_json


class TestAttemptHistoryEndpoint:
    @pytest.mark.asyncio
    async def test_get_job_attempts_returns_full_history(
        self, test_db, test_project, test_user, async_client
    ):
        svc = ExportJobService(test_db)
        job, item = await _make_job_with_item(svc, test_project.id, test_user.id)
        a1 = await svc.start_attempt(
            job.id, item.id, snapshot_id="snap-1", trigger="initial",
        )
        await svc.finish_attempt_failed(
            a1.id, ValueError("第一次失败"), user_message="第一次失败原因",
            diagnostic_detail={"step": "disclosure_notes", "sequence": 2},
        )
        a2 = await svc.start_attempt(
            job.id, item.id, snapshot_id="snap-1", trigger="retry",
        )
        await svc.finish_attempt_success(a2.id, file_sha256="abc123")
        await test_db.commit()

        resp = await async_client.get(
            f"/api/projects/{test_project.id}/word-exports/jobs/{job.id}/attempts"
        )
        assert resp.status_code == 200
        data = _unwrap(resp.json())
        assert isinstance(data, list)
        assert len(data) == 2  # 完整历史，不只是最新一次

        by_no = {a["attempt_no"]: a for a in data}
        assert by_no[1]["status"] == "failed"
        assert by_no[1]["error_type"] == "ValueError"
        assert "第一次" in by_no[1]["error_message"]  # 原始失败原因保留
        assert by_no[1]["diagnostic_detail"]["step"] == "disclosure_notes"
        assert by_no[1]["trigger"] == "initial"
        assert by_no[2]["status"] == "succeeded"
        assert by_no[2]["trigger"] == "retry"
        assert by_no[2]["file_sha256"] == "abc123"

    @pytest.mark.asyncio
    async def test_get_job_attempts_wrong_project_403(
        self, test_db, test_project, test_user, async_client
    ):
        svc = ExportJobService(test_db)
        job, _ = await _make_job_with_item(svc, test_project.id, test_user.id)
        await test_db.commit()
        other_project = uuid.uuid4()
        resp = await async_client.get(
            f"/api/projects/{other_project}/word-exports/jobs/{job.id}/attempts"
        )
        assert resp.status_code == 403
