"""Runtime 解冻后正向 apply 用例（spec formula-hub-integrity-closure 任务 26；需求 1.2、1.5；ADR-FHIC-07）。

原「冻结闸门」测试（任务 2）已随 ``freeze.py`` 删除。本文件改写为端点级正向用例：
- 【测试】夹具经 ``POST /api/workpapers/draft-refresh`` 真实 apply，目标格读回 = 123（变异 #1 第 2 轮的判据）。
- 计划先于项目锁、报表范围写入在锁后（需求 3.6，变异 #2 的判据）。
- 不含任何「文件 / 常量存在」断言（需求 1.2）。

做法沿用原夹具骨架：TestClient 真发请求，pg_tx_session 回滚隔离。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.routers.draft_refresh as draft_refresh_router
from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import AccountCategory, TbBalance, TrialBalance
from app.models.base import PermissionLevel, ProjectStatus, ProjectType, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpFormula,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.services.formula_management.draft_refresh_orchestrator import DraftRefreshOrchestrator
from tests.authz_world import assert_world_overrides, build_app
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, pg_tx_session

pytestmark = pytest.mark.pg_only

ENDPOINT = "/api/workpapers/draft-refresh"
YEAR = 2025
WP_CODE = "A99"
SHEET = "审定表A99"
CELL = "B5"
BEFORE_VALUE = 7


async def _seed(session):
    """【测试】项目 + 合伙人 + 四表行 + 底稿与 auto_calc 公式（expression=100+23 → 目标值 123）。"""
    tag = uuid.uuid4().hex[:10]
    user = User(username=f"fh_unfreeze_{tag}", email=f"fh_unfreeze_{tag}@example.test",
                hashed_password="x", role=UserRole.partner)
    project = Project(name=f"{TEST_PROJECT_PREFIX}fh_unfreeze_{tag}", client_name=f"{TEST_PROJECT_PREFIX}解冻正向",
                      project_type=ProjectType.annual, status=ProjectStatus.planning,
                      template_type="soe", report_scope="standalone")
    session.add_all([user, project])
    await session.flush()
    session.add(ProjectUser(project_id=project.id, user_id=user.id, role=ProjectUserRole.partner,
                            permission_level=PermissionLevel.edit))
    for code, amount in (("1001", Decimal("1000")), ("2001", Decimal("500"))):
        session.add(TbBalance(project_id=project.id, year=YEAR, company_code="C1", account_code=code,
                              account_name=f"科目{code}", closing_balance=amount))
        session.add(TrialBalance(project_id=project.id, year=YEAR, company_code="C1", standard_account_code=code,
                                 account_name=f"科目{code}", account_category=AccountCategory.asset,
                                 unadjusted_amount=amount))
    index = WpIndex(project_id=project.id, wp_code=WP_CODE, wp_name="解冻正向测试底稿",
                    status=WpStatus.not_started, is_deleted=False)
    session.add(index)
    await session.flush()
    paper = WorkingPaper(project_id=project.id, wp_index_id=index.id, file_path="/tmp/fh-unfreeze.xlsx",
                         source_type=WpSourceType.template, status=WpFileStatus.draft,
                         review_status=WpReviewStatus.not_submitted, is_deleted=False,
                         parsed_data={"html_data": {SHEET: {"cells": {CELL: {"value": BEFORE_VALUE}}}}})
    session.add(paper)
    await session.flush()
    formula = WpFormula(project_id=project.id, wp_id=paper.id, sheet_name=SHEET, target_cell=CELL,
                        expression="100 + 23", formula_type="auto_calc", category="auto_calc",
                        definition_version=1, created_by=user.id)
    session.add(formula)
    await session.commit()
    return project.id, user, formula.id, paper.id


def _make_endpoint(session, user):
    """按生产注册挂 draft_refresh.router 的应用 + TestClient。"""
    api = build_app(draft_refresh_router.router)

    async def _db():
        yield session

    async def _user():
        return user

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)
    return api


def test_runtime_apply_succeeds_after_unfreeze():
    """解冻后 Runtime mutation 计划正常 apply（需求 1.2）：不再返回 409。"""
    with TestClient(build_app(draft_refresh_router.router)) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            project_id, user, formula_id, wp_id = client.portal.call(_seed, session)
            api = client.app
            async def _db():
                yield session
            async def _user():
                return user
            api.dependency_overrides[get_db] = _db
            api.dependency_overrides[get_current_user] = _user
            assert_world_overrides(api)

            body = {"project_id": str(project_id), "year": YEAR, "scopes": ["workpaper:A"]}
            response = client.post(ENDPOINT, json=body)

            cell = client.portal.call(_cell_value, session, wp_id)

    assert response.status_code == 200, response.text
    data = response.json()
    # 正向 apply：状态不是冻结拒绝
    assert data.get("status") != "frozen"
    assert "FORMULA_RUNTIME_FROZEN" not in response.text
    # 🔴 2026-10-31 第 2 轮补（需求 1.2「真实 apply」）：原先只看状态码，Runtime mutation 没落库也照样绿
    assert data.get("applied_count", 0) >= 1, data
    assert cell is not None and Decimal(str(cell)) == Decimal("123"), f"目标格应写成 123，实为 {cell!r}"


async def _cell_value(session, wp_id):
    raw = (await session.execute(text("SELECT parsed_data FROM working_paper WHERE id = :i"), {"i": wp_id})).scalar_one()
    value = (((raw or {}).get("html_data") or {}).get(SHEET, {}).get("cells") or {}).get(CELL)
    return value.get("value") if isinstance(value, dict) else value


def test_plan_before_lock_and_report_writes_after_lock(monkeypatch):
    """需求 3.6 / ADR-FHIC-07 ①③：计划段只读、不取锁，先于项目锁；报表范围的写入（试算表重算）在取锁之后。

    🔴 2026-10-31 第 2 轮补：需求 3.6 的核查用例 ``test_lock_after_freeze`` 随任务 26 删 ``freeze.py`` 一起删了，
    此后「计划先于锁、写入在锁后」没有任何用例（变异 #2 恒绿）。这里只记录调用先后、原实现照常执行。
    """
    from app.services.trial_balance_service import TrialBalanceService

    order: list[str] = []

    def _spy(owner, name: str) -> None:
        original = getattr(owner, name)

        async def spy(*args, **kwargs):
            order.append(name)
            return await original(*args, **kwargs)

        monkeypatch.setattr(owner, name, spy)

    _spy(DraftRefreshOrchestrator, "_plan")
    _spy(DraftRefreshOrchestrator, "_acquire_project_lock")
    _spy(TrialBalanceService, "full_recalc")
    with TestClient(build_app(draft_refresh_router.router)) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            project_id, user, _, _ = client.portal.call(_seed, session)
            client.app.dependency_overrides.update(_overrides(session, user))
            assert_world_overrides(client.app)
            response = client.post(ENDPOINT, json={"project_id": str(project_id), "year": YEAR, "scopes": ["report"]})

    assert response.status_code == 200, response.text
    assert order.count("_plan") == 1 and order.count("_acquire_project_lock") == 1, order
    assert "full_recalc" in order, f"报表范围没有执行试算表重算，判据空转：{order}"
    assert order.index("_plan") < order.index("_acquire_project_lock") < order.index("full_recalc"), order


def _overrides(session, user) -> dict:
    async def _db():
        yield session

    async def _user():
        return user

    return {get_db: _db, get_current_user: _user}


def test_report_scope_still_works():
    """报表范围（无 Runtime mutation）照常执行，审计行数 +1（需求 3.6）。"""
    with TestClient(build_app(draft_refresh_router.router)) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            project_id, user, _, _ = client.portal.call(_seed, session)
            api = client.app
            async def _db():
                yield session
            async def _user():
                return user
            api.dependency_overrides[get_db] = _db
            api.dependency_overrides[get_current_user] = _user
            assert_world_overrides(api)

            # 查 before 审计行数
            before_count = client.portal.call(
                _audit_count, session, project_id
            )
            body = {"project_id": str(project_id), "year": YEAR, "scopes": ["report"]}
            response = client.post(ENDPOINT, json=body)
            after_count = client.portal.call(
                _audit_count, session, project_id
            )

    assert response.status_code == 200, response.text
    assert after_count == before_count + 1


async def _audit_count(session, project_id):
    row = (await session.execute(
        text("SELECT count(*) FROM draft_refresh_audit WHERE project_id = :pid"),
        {"pid": project_id},
    )).scalar()
    return int(row)
