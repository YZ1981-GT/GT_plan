"""全套生成执行器测试 — audit-report-template-integration task 15.5.

覆盖：
1. ``resolve_opt_defaults`` OPT 默认优先级链（纯函数，无 DB）。
2. 单项失败隔离 + 进度递增（DB 集成，monkeypatch 单步实现）。

注：完整 E2E（真实模板 + 报表/附注/报告渲染）依赖 DB 数据 + 模板资产，
本测试聚焦风险点（OPT 解析 + 失败隔离 + 进度），渲染步骤以桩替换。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.services.full_deliverables_executor import (
    FullDeliverablesExecutor,
    resolve_opt_defaults,
)


# ===================================================================
# 1. resolve_opt_defaults — OPT 默认优先级链（纯函数）
# ===================================================================


class TestResolveOptDefaults:
    """OPT 默认勾选优先级链（design §14）。"""

    def test_payload_explicit_wins(self):
        """① payload 显式 optional_sections 最高优先。"""
        result = resolve_opt_defaults(
            payload_optional_sections={"emphasis": True},
            last_optional_sections={"emphasis": False},
            registry_defaults={"emphasis": False},
            kam_required=True,
        )
        assert result == {"emphasis": True}

    def test_last_choice_when_no_payload(self):
        """② payload 缺失时用项目上次人工选择。"""
        result = resolve_opt_defaults(
            payload_optional_sections=None,
            last_optional_sections={"key_audit_matters": True, "comparative": False},
            registry_defaults={"emphasis": True},
            kam_required=False,
        )
        assert result == {"key_audit_matters": True, "comparative": False}

    def test_registry_when_no_payload_no_last(self):
        """③ 无 payload + 无上次选择时用 registry opt_defaults。"""
        result = resolve_opt_defaults(
            payload_optional_sections=None,
            last_optional_sections=None,
            registry_defaults={"key_audit_matters": True, "comparative": True},
            kam_required=False,
        )
        assert result == {"key_audit_matters": True, "comparative": True}

    def test_hardcoded_fallback_kam_required_true(self):
        """④ 全空兜底：kam_required=True → KAM 勾选、comparative=True、其余 False。"""
        result = resolve_opt_defaults(
            payload_optional_sections=None,
            last_optional_sections=None,
            registry_defaults=None,
            kam_required=True,
        )
        assert result["key_audit_matters"] is True
        assert result["comparative"] is True
        assert result["emphasis"] is False
        assert result["going_concern"] is False
        assert result["other_matter"] is False
        assert result["other_information"] is False

    def test_hardcoded_fallback_kam_required_false(self):
        """④ 兜底：kam_required=False → KAM 不勾选。"""
        result = resolve_opt_defaults(
            payload_optional_sections=None,
            last_optional_sections=None,
            registry_defaults=None,
            kam_required=False,
        )
        assert result["key_audit_matters"] is False
        assert result["comparative"] is True

    def test_empty_dicts_treated_as_absent(self):
        """空 dict 视为未提供，继续向下回退到兜底。"""
        result = resolve_opt_defaults(
            payload_optional_sections={},
            last_optional_sections={},
            registry_defaults={},
            kam_required=True,
        )
        # 落到兜底硬编码
        assert result["key_audit_matters"] is True
        assert result["comparative"] is True


# ===================================================================
# 2. 单项失败隔离 + 进度递增（DB 集成）
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
        username="test_full_deliv",
        email="fulldeliv@test.com",
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
        name="全套测试项目",
        client_name="测试有限公司",
        status="created",
    )
    test_db.add(project)
    await test_db.flush()
    return project


def _patch_steps(
    executor: FullDeliverablesExecutor,
    *,
    fail_step: str | None = None,
    kam_warning: str | None = None,
):
    """以桩替换正式三件套的三个渲染步骤，避免依赖真实模板/报表数据。

    phase4 权威三件套的稳定键是 ``financial_report / disclosure_notes / audit_report``；
    ``audit_report`` 复用 ``_run_report_body`` 渲染路径。``fail_step`` 用稳定键指定要失败的步骤。
    """

    async def _ok_financial(project_id, year, user_id):
        if fail_step == "financial_report":
            raise RuntimeError("审定财务报表生成失败（桩）")
        return uuid.uuid4()

    async def _ok_notes(project_id, year, user_id):
        if fail_step == "disclosure_notes":
            raise RuntimeError("附注生成失败（桩）")
        return uuid.uuid4()

    async def _ok_report(project_id, year, user_id, payload):
        if fail_step == "audit_report":
            raise RuntimeError("审计报告正文生成失败（桩）")
        return uuid.uuid4(), kam_warning, {"key_audit_matters": True}

    executor._run_financial_reports = _ok_financial  # type: ignore[assignment]
    executor._run_disclosure_notes = _ok_notes  # type: ignore[assignment]
    executor._run_report_body = _ok_report  # type: ignore[assignment]
    # 跳过试算表前置（桩测不插入 trial_balance）
    executor.precheck = lambda project_id, year: _noop()  # type: ignore[assignment]
    # 跳过真实 snapshot refs 捕获（桩测无报表/附注数据），digest 仍由稳定输入计算。
    executor._build_snapshot_input = (  # type: ignore[assignment]
        lambda project_id, year, payload: _snapshot_stub(project_id, year)
    )


async def _noop():
    return None


async def _snapshot_stub(project_id, year):
    return {"project_id": str(project_id), "year": year, "_stub": True}


class TestFullDeliverablesExecutor:
    """全套生成执行器 — 正式三件套顺序、失败隔离、依赖阻断与状态聚合（phase4）。"""

    @pytest.mark.asyncio
    async def test_all_steps_succeed(self, test_db, test_project, test_user):
        """正式三件套全成功 → job succeeded，trio 3/3，0 失败，固定顺序与稳定键。"""
        executor = FullDeliverablesExecutor(test_db)
        _patch_steps(executor)

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024, "template_variant": "simple"},
        )
        assert result.done == 3
        assert result.failed == 0
        assert result.status == "succeeded"
        assert result.trio_total == 3
        assert result.trio_succeeded == 3
        assert len(result.outcomes) == 3
        # 固定顺序 financial_report → disclosure_notes → audit_report（需求 2.1）
        assert [o.step for o in result.outcomes] == [
            "financial_report",
            "disclosure_notes",
            "audit_report",
        ]
        assert [o.sequence for o in result.outcomes] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_single_step_failure_isolated(self, test_db, test_project, test_user):
        """中间步骤（附注）失败 ⇒ audit_report 被依赖阻断，financial 仍成功 → partial_failed。"""
        executor = FullDeliverablesExecutor(test_db)
        _patch_steps(executor, fail_step="disclosure_notes")

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024, "template_variant": "simple"},
        )
        # 1 成功（financial_report）+ 1 失败（disclosure_notes）+ 1 阻断（audit_report）
        assert result.done == 1
        assert result.failed == 2  # failed + blocked 合并计数（均非正式成功）
        assert result.status == "partial_failed"
        assert result.trio_succeeded == 1
        by_step = {o.step: o for o in result.outcomes}
        assert by_step["disclosure_notes"].succeeded is False
        assert by_step["financial_report"].succeeded is True
        # audit_report 因前置附注失败被标 blocked_by_dependency（而非伪装成导出异常）
        assert by_step["audit_report"].status == "blocked_by_dependency"
        assert by_step["audit_report"].succeeded is False

    @pytest.mark.asyncio
    async def test_first_step_failure_blocks_dependent(self, test_db, test_project, test_user):
        """首步（财报）失败后续附注仍执行；audit_report 因前置缺失被阻断（需求 2.1/4.4）。"""
        executor = FullDeliverablesExecutor(test_db)
        _patch_steps(executor, fail_step="financial_report")

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024, "template_variant": "simple"},
        )
        by_step = {o.step: o for o in result.outcomes}
        # financial_report 失败；disclosure_notes 无依赖，仍执行成功
        assert by_step["financial_report"].succeeded is False
        assert by_step["disclosure_notes"].succeeded is True
        # audit_report 依赖 financial_report（已失败）⇒ 阻断
        assert by_step["audit_report"].status == "blocked_by_dependency"
        assert result.status == "partial_failed"
        assert result.trio_succeeded == 1

    @pytest.mark.asyncio
    async def test_all_fail_is_failed_status(self, test_db, test_project, test_user):
        """前两项均失败 ⇒ audit 被阻断 ⇒ 三项无一正式成功 → failed。"""
        executor = FullDeliverablesExecutor(test_db)

        async def _boom_financial(project_id, year, user_id):
            raise RuntimeError("财报失败")

        async def _boom_notes(project_id, year, user_id):
            raise RuntimeError("附注失败")

        _patch_steps(executor)
        executor._run_financial_reports = _boom_financial  # type: ignore[assignment]
        executor._run_disclosure_notes = _boom_notes  # type: ignore[assignment]

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024, "template_variant": "simple"},
        )
        assert result.done == 0
        assert result.trio_succeeded == 0
        assert result.status == "failed"

    @pytest.mark.asyncio
    async def test_kam_warning_persisted_in_payload(self, test_db, test_project, test_user):
        """KAM 警告写入 job.payload metadata（design §14 第 6 步）。"""
        executor = FullDeliverablesExecutor(test_db)
        warning = "上市公司或公共利益实体审计报告必须包含至少一个关键审计事项(KAM)"
        _patch_steps(executor, kam_warning=warning)

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024, "template_variant": "simple"},
        )
        assert result.kam_warning == warning
        job = await executor.job_svc.get_job(result.job_id)
        assert job.payload.get("kam_warning") == warning

    @pytest.mark.asyncio
    async def test_progress_increments_per_item(self, test_db, test_project, test_user):
        """每步创建一个 job item，trio_total 固定 3，progress_total == 3。"""
        executor = FullDeliverablesExecutor(test_db)
        _patch_steps(executor)

        result = await executor.run(
            project_id=test_project.id,
            user_id=test_user.id,
            payload={"year": 2024, "template_variant": "simple"},
        )
        job = await executor.job_svc.get_job(result.job_id)
        items = await executor.job_svc.get_job_items(result.job_id)
        assert job.progress_total == 3
        assert job.progress_done == 3
        assert job.trio_total == 3
        assert job.trio_succeeded == 3
        assert len(items) == 3
