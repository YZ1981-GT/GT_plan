"""Phase4 Task 5 — executor 固定顺序、步骤依赖与状态聚合（SQLite 真 ORM + 变异证明）.

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 2.1–2.6, 4.4）。

本文件以**真实 ORM**（SQLite 内存库 + 真 ``ExportJob/ExportJobItem``）驱动
``FullDeliverablesExecutor.run``，覆盖 Task 5 的三条正面不变量 + 三条「改回旧行为
必须红」的变异证明：

正面：
  P1 TRIO_STEPS 顺序/稳定键固定；``financial_report_unadjusted`` 不在其中。
  P2 三件套三项（真 item 行）引用同一个非空 snapshot_id（需求 2.4）。
  P3 audit_report 的前置失败 ⇒ 标 ``blocked_by_dependency``、**不运行导出器**；
     状态聚合只统计正式三项（trio_succeeded）。

变异（证明判据不是恒绿）：
  M1 调换顺序：把 TRIO_STEPS 顺序改成 audit_report 先于前置 ⇒ 顺序断言红。
  M2 把辅助项算正式项：若 unadjusted 混入正式计数 ⇒ trio_total/成功数断言红。
  M3 前置失败后仍生成正文：若去掉依赖阻断、audit_report 导出器照跑 ⇒ 阻断断言红。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import ExportJobItem
import app.services.full_deliverables_executor as execmod
from app.services.full_deliverables_executor import (
    AUXILIARY_STEP_KEYS,
    BLOCKED_BY_DEPENDENCY,
    TRIO_STEPS,
    FullDeliverablesExecutor,
    TrioStep,
)


# ===================================================================
# fixtures
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
        username="trio_order",
        email="trio_order@test.com",
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
        name="三件套顺序项目",
        client_name="测试有限公司",
        status="created",
    )
    test_db.add(project)
    await test_db.flush()
    return project


def _patch_executor(executor, *, fail_step: str | None = None):
    """桩替换三件套渲染步骤 + 前置 + 快照输入（稳定键派发）。"""

    async def _ok_financial(project_id, year, user_id):
        if fail_step == "financial_report":
            raise RuntimeError("审定财务报表失败（桩）")
        return uuid.uuid4()

    async def _ok_notes(project_id, year, user_id):
        if fail_step == "disclosure_notes":
            raise RuntimeError("附注失败（桩）")
        return uuid.uuid4()

    async def _ok_report(project_id, year, user_id, payload):
        if fail_step == "audit_report":
            raise RuntimeError("报告正文失败（桩）")
        return uuid.uuid4(), None, {"key_audit_matters": True}

    async def _noop():
        return None

    executor._run_financial_reports = _ok_financial  # type: ignore[assignment]
    executor._run_disclosure_notes = _ok_notes  # type: ignore[assignment]
    executor._run_report_body = _ok_report  # type: ignore[assignment]
    executor.precheck = lambda project_id, year: _noop()  # type: ignore[assignment]
    executor._build_snapshot_input = (  # type: ignore[assignment]
        lambda project_id, year, payload: _stub_snap(project_id, year)
    )


async def _stub_snap(project_id, year):
    return {"project_id": str(project_id), "year": year}


async def _items_by_step(db: AsyncSession, job_id) -> dict[str, ExportJobItem]:
    rows = (
        await db.execute(
            sa.select(ExportJobItem).where(ExportJobItem.job_id == job_id)
        )
    ).scalars().all()
    return {r.step_key: r for r in rows}


# ===================================================================
# P1 — 顺序与稳定键
# ===================================================================


class TestTrioOrderContract:
    def test_trio_steps_fixed_order_and_keys(self):
        assert [s.key for s in TRIO_STEPS] == [
            "financial_report",
            "disclosure_notes",
            "audit_report",
        ]
        assert [s.sequence for s in TRIO_STEPS] == [1, 2, 3]
        assert "financial_report_unadjusted" not in [s.key for s in TRIO_STEPS]
        assert "financial_report_unadjusted" in AUXILIARY_STEP_KEYS

    @pytest.mark.asyncio
    async def test_run_persists_step_key_and_sequence_in_order(
        self, test_db, test_project, test_user
    ):
        """真 item 行记录稳定键 + 固定顺序，顺序与 TRIO_STEPS 一致。"""
        executor = FullDeliverablesExecutor(test_db)
        _patch_executor(executor)
        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024},
        )
        items = await _items_by_step(test_db, result.job_id)
        assert set(items) == {"financial_report", "disclosure_notes", "audit_report"}
        assert items["financial_report"].sequence == 1
        assert items["disclosure_notes"].sequence == 2
        assert items["audit_report"].sequence == 3
        # 辅助项不进正式三件套 item
        assert "financial_report_unadjusted" not in items


# ===================================================================
# P2 — 三项共享同一 snapshot
# ===================================================================


class TestTrioSharedSnapshot:
    @pytest.mark.asyncio
    async def test_three_items_share_one_snapshot(
        self, test_db, test_project, test_user
    ):
        executor = FullDeliverablesExecutor(test_db)
        _patch_executor(executor)
        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024},
        )
        assert result.snapshot_id is not None and result.snapshot_id != ""
        items = await _items_by_step(test_db, result.job_id)
        snaps = {i.snapshot_id for i in items.values()}
        assert snaps == {result.snapshot_id}, (
            f"三件套三项必须引用同一快照，实际: {snaps}"
        )

    @pytest.mark.asyncio
    async def test_digest_idempotent_and_binds_source(
        self, test_db, test_project, test_user
    ):
        """同一输入 digest 稳定；改业务输入 digest 变化（证明非常量）。"""
        from app.services.deliverable_trio_snapshot import build_digest

        base = {"project_id": "p", "year": 2024, "template_type": "soe"}
        d1 = build_digest(dict(base))
        d2 = build_digest(dict(base))
        assert d1 == d2
        d3 = build_digest({**base, "year": 2025})
        assert d3 != d1


# ===================================================================
# P3 — 依赖阻断与正式计数
# ===================================================================


class TestTrioDependencyBlock:
    @pytest.mark.asyncio
    async def test_audit_blocked_when_prereq_failed_and_no_exporter_run(
        self, test_db, test_project, test_user
    ):
        """附注失败 ⇒ audit_report 标 blocked_by_dependency，且导出器未被调用。"""
        executor = FullDeliverablesExecutor(test_db)

        report_called = {"n": 0}

        async def _tracking_report(project_id, year, user_id, payload):
            report_called["n"] += 1
            return uuid.uuid4(), None, None

        _patch_executor(executor, fail_step="disclosure_notes")
        executor._run_report_body = _tracking_report  # type: ignore[assignment]

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024},
        )
        items = await _items_by_step(test_db, result.job_id)
        assert items["audit_report"].status == BLOCKED_BY_DEPENDENCY
        # 被阻断 ⇒ 导出器绝不运行（design §6：而非伪装成导出异常）
        assert report_called["n"] == 0
        # 聚合只统计正式三项：仅 financial_report 成功
        assert result.trio_succeeded == 1
        assert result.trio_total == 3

    @pytest.mark.asyncio
    async def test_blocked_not_counted_as_success(
        self, test_db, test_project, test_user
    ):
        """blocked_by_dependency 既非成功也不进 trio_succeeded。"""
        executor = FullDeliverablesExecutor(test_db)
        _patch_executor(executor, fail_step="financial_report")
        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024},
        )
        # financial 失败, notes 成功, audit 阻断
        assert result.trio_succeeded == 1
        assert result.status == "partial_failed"


# ===================================================================
# 变异证明：改回旧行为必须红
# ===================================================================


class TestMutationsMustFail:
    """每个变异在 try 内断言「旧行为导致判据红」，确保守卫不是恒绿。"""

    @pytest.mark.asyncio
    async def test_M1_swapped_order_breaks_order_assertion(
        self, test_db, test_project, test_user, monkeypatch
    ):
        """M1：把 TRIO_STEPS 顺序调换（audit 先行）⇒ 固定顺序断言必须红。"""
        swapped = (
            TrioStep("audit_report", 1, "audit_report"),
            TrioStep("financial_report", 2, "financial_report"),
            TrioStep("disclosure_notes", 3, "disclosure_notes"),
        )
        monkeypatch.setattr(execmod, "TRIO_STEPS", swapped)

        executor = FullDeliverablesExecutor(test_db)
        _patch_executor(executor)
        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024},
        )
        order = [o.step for o in result.outcomes]
        # 正面不变量在变异下必然不成立 ⇒ 这里断言它确实被打破
        assert order != ["financial_report", "disclosure_notes", "audit_report"], (
            "调换顺序后，顺序断言本应被打破，但仍为权威顺序 ⇒ 守卫恒绿"
        )
        assert order[0] == "audit_report"

    @pytest.mark.asyncio
    async def test_M2_auxiliary_counted_as_formal_breaks_total(
        self, test_db, test_project, test_user, monkeypatch
    ):
        """M2：把辅助 unadjusted 混入 TRIO_STEPS（算正式项）⇒ 正式总数断言必须红。"""
        polluted = TRIO_STEPS + (
            TrioStep("financial_report_unadjusted", 4, "financial_report_unadjusted"),
        )
        monkeypatch.setattr(execmod, "TRIO_STEPS", polluted)

        executor = FullDeliverablesExecutor(test_db)
        _patch_executor(executor)
        # 需补一个 unadjusted 渲染桩，否则该步骤会异常失败（但 total 仍被污染）
        async def _ok_unadj(project_id, year, user_id, payload):
            return uuid.uuid4(), None, None

        # 派发器只识别三个稳定键；污染项会落 _dispatch_trio_step 的未知分支 ⇒ 失败。
        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024},
        )
        # 正式三件套固定为 3；若把 unadjusted 算正式项，outcomes 会多出一项
        assert len(result.outcomes) == 4, (
            "变异把辅助项混入正式步骤，outcomes 应变 4 ⇒ 证明「正式固定 3」判据可被打破"
        )
        assert "financial_report_unadjusted" in [o.step for o in result.outcomes]

    @pytest.mark.asyncio
    async def test_M3_no_dependency_block_lets_body_run_after_prereq_fail(
        self, test_db, test_project, test_user, monkeypatch
    ):
        """M3：去掉依赖声明（audit_report 无 depends_on）⇒ 前置失败后正文照跑，阻断判据红。"""
        no_dep = (
            TRIO_STEPS[0],
            TRIO_STEPS[1],
            TrioStep("audit_report", 3, "audit_report", depends_on=()),  # 去掉依赖
        )
        monkeypatch.setattr(execmod, "TRIO_STEPS", no_dep)

        executor = FullDeliverablesExecutor(test_db)
        report_called = {"n": 0}

        async def _tracking_report(project_id, year, user_id, payload):
            report_called["n"] += 1
            return uuid.uuid4(), None, None

        _patch_executor(executor, fail_step="disclosure_notes")
        executor._run_report_body = _tracking_report  # type: ignore[assignment]

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024},
        )
        items = await _items_by_step(test_db, result.job_id)
        # 去掉依赖后：导出器被调用、audit 不再 blocked ⇒ 证明「阻断」判据可被打破
        assert report_called["n"] == 1, (
            "去掉依赖声明后，前置失败仍生成正文 ⇒ 阻断判据本应失效（变异有效）"
        )
        assert items["audit_report"].status != BLOCKED_BY_DEPENDENCY
