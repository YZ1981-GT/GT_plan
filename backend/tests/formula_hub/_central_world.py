"""中央执行合同用例的共用夹具（spec formula-hub-integrity-closure 任务 11 / 12；需求 2.1、2.2、2.4、2.8、4.3）。

- :class:`Row` / :func:`seed`：按标签建【测试】项目（每项目一个 readonly 成员身份）+ 试算表行 + 已审批调整分录（借本科目、
  贷 2241；只有本科目进试算表）。PG 上在 ``pg_tx_session`` 的外层事务里写，用例结束回滚。
- :func:`sqlite_endpoint`：应用按生产注册只挂 ``formula.router``、``formula_debug.router`` 与 ``report_config.router``（任务 13
  报表配置两个执行端点；``tests.authz_world.build_app``），
  TestClient 真发请求，只替换 ``get_current_user`` / ``get_db``（门禁 ``assert_project_permission`` 真实运行）；SQLite 引擎、
  会话与夹具建在 TestClient 的事件循环线程里（``client.portal``）。
- :func:`pg_endpoint`：同一应用，会话 = ``pg_tx_session``（独立连接 + 外层事务 + 保存点，退出一律回滚；只连快照库）。
- Redis（不是判定）：``app.core.redis`` 的两个客户端名临时换成独立 FakeServer 的 fakeredis（同 ``tests.authz_world``）——
  ``/api/formula/execute`` 依赖 ``get_redis``（会 ping），不换就连本机真实 Redis。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import fakeredis
import fakeredis.aioredis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.core.redis as core_redis
import app.models  # noqa: F401  全量注册（外键引用的表要在 metadata 里）
import app.routers.formula as formula_router
import app.routers.formula_debug as formula_debug_router
import app.routers.report_config as report_config_router
from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import (
    AccountCategory,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectType, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import FinancialReport
from tests.authz_world import assert_world_overrides, build_app
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, pg_tx_session

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

D = Decimal
YEAR = 2025
EXECUTE_PATH = "/api/formula/execute"
BATCH_PATH = "/api/formula/batch-execute"
DEBUG_PATH = "/api/formula/debug"
REPORT_EXECUTE_PATH = "/api/report-config/execute-formula"
REPORT_BATCH_PATH = "/api/report-config/execute-formulas-batch"
_NAMES = {"1001": "库存现金", "1002": "银行存款", "1122": "应收账款", "1231": "坏账准备", "1601": "固定资产"}


@dataclass(frozen=True)
class Row:
    """一行试算表；``aje`` / ``rje`` 同时是试算表调整列与同科目已审批分录的金额。"""

    code: str
    audited: Decimal
    unadjusted: Decimal
    aje: Decimal = D(0)
    rje: Decimal = D(0)


@dataclass(frozen=True)
class World:
    session: AsyncSession
    user: User
    projects: dict[str, uuid.UUID]


def _name(code: str) -> str:
    return _NAMES.get(code.split("-")[0], f"科目{code}") + ("" if "-" not in code else f"-{code.split('-')[1]}")


async def _approved_entry(session: AsyncSession, pid: uuid.UUID, user_id: uuid.UUID,
                          kind: AdjustmentType, code: str, amount: Decimal) -> None:
    group = uuid.uuid4()
    adjustment = Adjustment(project_id=pid, year=YEAR, company_code="001", adjustment_no=f"{kind.value.upper()}-{code}",
                            adjustment_type=kind, account_code=code, account_name=_name(code), debit_amount=amount,
                            credit_amount=D(0), entry_group_id=group, review_status=ReviewStatus.approved,
                            created_by=user_id)
    session.add(adjustment)
    await session.flush()
    session.add_all([
        AdjustmentEntry(adjustment_id=adjustment.id, entry_group_id=group, line_no=1, standard_account_code=code,
                        account_name=_name(code), debit_amount=amount, credit_amount=D(0)),
        AdjustmentEntry(adjustment_id=adjustment.id, entry_group_id=group, line_no=2, standard_account_code="2241",
                        account_name="其他应付款", debit_amount=D(0), credit_amount=amount),
    ])
    await session.flush()


def new_user(tag: str) -> User:
    suffix = uuid.uuid4().hex[:10]
    return User(id=uuid.uuid4(), username=f"{tag}_{suffix}", email=f"{tag}_{suffix}@example.test",
                hashed_password="x", role=UserRole.auditor, is_active=True)


def membership(project_id: uuid.UUID, user: User) -> ProjectUser:
    return ProjectUser(project_id=project_id, user_id=user.id, role=ProjectUserRole.auditor,
                       permission_level=PermissionLevel.readonly)


async def seed(session: AsyncSession, fixtures: Mapping[str, Iterable[Row]], *, tag: str) -> World:
    """每个标签一个【测试】项目 + 同一个 readonly 成员 + 试算表行 + 已审批调整分录。"""
    user = new_user(tag)
    suffix = uuid.uuid4().hex[:10]
    projects = {label: Project(id=uuid.uuid4(), name=f"{TEST_PROJECT_PREFIX}{tag}_{label}_{suffix}",
                               client_name=f"{TEST_PROJECT_PREFIX}中央执行合同", project_type=ProjectType.annual,
                               status=ProjectStatus.planning, template_type="soe", report_scope="standalone")
                for label in fixtures}
    session.add_all([user, *projects.values()])
    await session.flush()
    for label, rows in fixtures.items():
        pid = projects[label].id
        rows = tuple(rows)
        session.add(membership(pid, user))
        for r in rows:
            session.add(TrialBalance(project_id=pid, year=YEAR, company_code="001", standard_account_code=r.code,
                                     account_name=_name(r.code), account_category=AccountCategory.asset,
                                     audited_amount=r.audited, unadjusted_amount=r.unadjusted, opening_balance=D(0),
                                     aje_adjustment=r.aje, rje_adjustment=r.rje))
        await session.flush()
        for r in rows:
            for kind, amount in ((AdjustmentType.aje, r.aje), (AdjustmentType.rje, r.rje)):
                if amount:
                    await _approved_entry(session, pid, user.id, kind, r.code, amount)
    await session.commit()  # pg_tx：只释放保存点，夹具留在外层事务里
    return World(session, user, {label: p.id for label, p in projects.items()})


_MODELS = (User, Project, ProjectUser, TrialBalance, Adjustment, AdjustmentEntry, FinancialReport)


@asynccontextmanager
async def sqlite_world(fixtures: Mapping[str, Iterable[Row]], *, tag: str) -> AsyncIterator[World]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[m.__table__ for m in _MODELS]))
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            yield await seed(session, fixtures, tag=tag)
    finally:
        await engine.dispose()


@contextmanager
def _fake_redis() -> Iterator[None]:
    saved = (core_redis.redis_client, core_redis._redis_client)
    fake = fakeredis.aioredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    core_redis.redis_client = core_redis._redis_client = fake
    try:
        yield
    finally:
        core_redis.redis_client, core_redis._redis_client = saved


def _app() -> FastAPI:
    return build_app(formula_router.router, formula_debug_router.router, report_config_router.router)


def authenticate(api: FastAPI, session: AsyncSession, user: User) -> None:
    async def _db():
        yield session

    async def _user():
        return user

    api.dependency_overrides[get_db] = _db
    api.dependency_overrides[get_current_user] = _user
    assert_world_overrides(api)


@contextmanager
def sqlite_endpoint(fixtures: Mapping[str, Iterable[Row]], *, tag: str = "fh_central") -> Iterator[tuple[TestClient, World]]:
    api = _app()
    with _fake_redis(), TestClient(api) as client:
        with client.portal.wrap_async_context_manager(sqlite_world(fixtures, tag=tag)) as world:
            authenticate(api, world.session, world.user)
            yield client, world


@contextmanager
def pg_endpoint() -> Iterator[tuple[TestClient, AsyncSession, FastAPI]]:
    api = _app()
    with _fake_redis(), TestClient(api) as client:
        with client.portal.wrap_async_context_manager(pg_tx_session()) as session:
            yield client, session, api


def _request(pid: uuid.UUID, formula: str) -> dict[str, Any]:
    return {"project_id": str(pid), "year": YEAR, "formula_type": "TB", "params": {"formula": formula}}


def send_execute(client: TestClient, pid: uuid.UUID, formula: str):
    return client.post(EXECUTE_PATH, json=_request(pid, formula))


def send_batch(client: TestClient, pid: uuid.UUID, formulas: Iterable[str]):
    return client.post(BATCH_PATH, json=[_request(pid, f) for f in formulas])


def send_debug(client: TestClient, pid: uuid.UUID, formula: str, scope: str = "report"):
    return client.post(DEBUG_PATH, json={"formula": formula, "project_id": str(pid), "year": YEAR, "scope": scope})


def _ok_json(response) -> Any:
    assert response.status_code == 200, response.text
    return response.json()


def post_execute(client: TestClient, pid: uuid.UUID, formula: str) -> dict[str, Any]:
    return _ok_json(send_execute(client, pid, formula))


def post_batch(client: TestClient, pid: uuid.UUID, formulas: Iterable[str]) -> list[dict[str, Any]]:
    return _ok_json(send_batch(client, pid, formulas))


def post_debug(client: TestClient, pid: uuid.UUID, formula: str, scope: str = "report") -> dict[str, Any]:
    return _ok_json(send_debug(client, pid, formula, scope))
