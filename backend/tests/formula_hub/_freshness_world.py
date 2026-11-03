"""报表新鲜度用例的共用夹具（spec formula-hub-integrity-closure 任务 14；需求 5.1 读取部分、5.5；ADR-FHIC-04）。

一个【测试】项目（soe 单体 ⇒ 准则 ``soe_standalone``）+ 资产负债表定义 + 报表行，行的形态与两种读者的期望见 :data:`SHAPES`；
另有两行噪声（已删的存量行、上一年度的存量行），任何读者都不得计入本年度。行次用 ``FHT14-`` 前缀（快照库的真实准则行里
没有），PG 上同样可写：准则行与本项目行都在 ``pg_tx_session`` 的外层事务里，用例结束回滚。

- :func:`sqlite_world` / :func:`pg_world`：会话 + 已提交（PG 上只释放保存点）的夹具；
- :func:`report_client`：应用按生产注册只挂 ``routers/reports.py``（``tests.authz_world.build_app``），TestClient 真发请求，
  只替换 ``get_current_user`` / ``get_db``；会话与夹具建在 TestClient 的事件循环线程里（``client.portal``）。
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  全量注册（外键引用的表要在 metadata 里）
import app.routers.reports as reports_router
from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import Materiality, UnadjustedMisstatement
from app.models.base import Base, PermissionLevel, ProjectStatus, ProjectType, ProjectUserRole, UserRole
from app.models.core import Project, ProjectUser, User
from app.models.report_models import DisclosureNote, FinancialReport, FinancialReportType, ReportConfig
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.report_freshness import CALC_VERSION
from tests.authz_world import assert_world_overrides, build_app
from tests.formula_hub._pg_harness import TEST_PROJECT_PREFIX, pg_tx_session

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

YEAR = 2025
STANDARD = "soe_standalone"
BS = FinancialReportType.balance_sheet


@dataclass(frozen=True)
class Shape:
    """一行报表：生成时公式、准则行公式、本项目覆盖公式（有则为有效定义）、计算版本与两种原因 + 两种读者的期望。"""

    code: str
    note: str
    formula_used: str | None
    standard_formula: str | None
    calc_version: int | None
    is_stale: bool = False
    calc_error: str | None = None
    blank_reason: str | None = None
    override: str | None = None
    summary_stale: bool = False  # stale_clause（汇总类读者）
    row_stale: bool = False  # is_effectively_stale（逐行读者）


SHAPES: tuple[Shape, ...] = (
    Shape("FHT14-001", "存量行：计算版本为空（D13-A）", "TB('1001','期末余额')", "TB('1001','期末余额')", None,
          summary_stale=True, row_stale=True),
    Shape("FHT14-002", "新鲜：生成时公式只差首尾空白", " TB('1002','期末余额') ", "TB('1002','期末余额')", CALC_VERSION),
    Shape("FHT14-003", "公式改了（尚未标过期）：只有逐行读者判过期", "TB('1121','期末余额')", "TB('1122','期末余额')",
          CALC_VERSION, row_stale=True),
    Shape("FHT14-004", "计算失败：保留旧值并标过期", "TB('1123','期末余额')", "TB('1123','期末余额')", CALC_VERSION,
          is_stale=True, calc_error="除数为 0", summary_stale=True, row_stale=True),
    Shape("FHT14-005", "口径留空：金额为空、不过期", "TB('1131','期末余额')", "TB('1131','期末余额')", CALC_VERSION,
          blank_reason="取数超出合并口径"),
    Shape("FHT14-006", "本项目覆盖 = 生成时公式（准则行不同）⇒ 新鲜", "TB('1601','期末余额')", "TB('1602','期末余额')",
          CALC_VERSION, override="TB('1601','期末余额')"),
    Shape("FHT14-007", "旧计算版本", "TB('1701','期末余额')", "TB('1701','期末余额')", CALC_VERSION - 1,
          summary_stale=True, row_stale=True),
)
BY_CODE = {s.code: s for s in SHAPES}
SUMMARY_STALE = sorted(s.code for s in SHAPES if s.summary_stale)
ROW_STALE = sorted(s.code for s in SHAPES if s.row_stale)
CALC_ERROR = sorted(s.code for s in SHAPES if s.calc_error)
BLANK = sorted(s.code for s in SHAPES if s.blank_reason)


@dataclass(frozen=True)
class World:
    session: AsyncSession
    user: User
    project_id: uuid.UUID


def _amount(shape: Shape, index: int) -> Decimal | None:
    return None if shape.blank_reason else Decimal(100 * index)


async def seed(session: AsyncSession, *, tag: str) -> World:
    suffix = uuid.uuid4().hex[:10]
    user = User(id=uuid.uuid4(), username=f"{tag}_{suffix}", email=f"{tag}_{suffix}@example.test",
                hashed_password="x", role=UserRole.auditor, is_active=True)
    project = Project(id=uuid.uuid4(), name=f"{TEST_PROJECT_PREFIX}{tag}_{suffix}",
                      client_name=f"{TEST_PROJECT_PREFIX}报表新鲜度", project_type=ProjectType.annual,
                      status=ProjectStatus.planning, template_type="soe", report_scope="standalone")
    session.add_all([user, project])
    await session.flush()
    session.add(ProjectUser(project_id=project.id, user_id=user.id, role=ProjectUserRole.auditor,
                            permission_level=PermissionLevel.readonly))
    for index, shape in enumerate(SHAPES, 1):
        session.add(ReportConfig(report_type=BS, row_number=9000 + index, row_code=shape.code,
                                 row_name=f"新鲜度{index}", formula=shape.standard_formula,
                                 applicable_standard=STANDARD))
        if shape.override is not None:
            session.add(ReportConfig(report_type=BS, row_number=9000 + index, row_code=shape.code,
                                     row_name=f"新鲜度{index}", formula=shape.override,
                                     applicable_standard=f"project:{project.id}"))
        session.add(FinancialReport(project_id=project.id, year=YEAR, report_type=BS, row_code=shape.code,
                                    row_name=f"新鲜度{index}", current_period_amount=_amount(shape, index),
                                    formula_used=shape.formula_used, is_stale=shape.is_stale,
                                    calc_version=shape.calc_version, calc_error=shape.calc_error,
                                    blank_reason=shape.blank_reason))
    # 噪声：已删的存量行、上一年度的存量行 —— 本年度任何读者都不得计入
    session.add_all([
        FinancialReport(project_id=project.id, year=YEAR, report_type=BS, row_code="FHT14-900", row_name="已删",
                        formula_used="TB('1001','期末余额')", is_deleted=True),
        FinancialReport(project_id=project.id, year=YEAR - 1, report_type=BS, row_code="FHT14-001",
                        row_name="上年", formula_used="TB('1001','期末余额')"),
    ])
    await session.commit()  # pg_tx：只释放保存点，夹具留在外层事务里
    return World(session, user, project.id)


#: SQLite 建表范围 = 读者会查的表（stale_summary_aggregate 还查底稿 / 附注 / 错报 / 重要性）
_MODELS = (User, Project, ProjectUser, ReportConfig, FinancialReport, WpIndex, WorkingPaper, DisclosureNote,
           UnadjustedMisstatement, Materiality)


@asynccontextmanager
async def sqlite_world(*, tag: str = "fh_fresh") -> AsyncIterator[World]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[m.__table__ for m in _MODELS]))
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
            yield await seed(session, tag=tag)
    finally:
        await engine.dispose()


@asynccontextmanager
async def pg_world(*, tag: str = "fh_fresh_pg") -> AsyncIterator[World]:
    async with pg_tx_session() as session:
        yield await seed(session, tag=tag)


@contextmanager
def report_client(world_cm) -> Iterator[tuple[TestClient, World]]:
    """``world_cm`` = :func:`sqlite_world` / :func:`pg_world` 的返回值（未进入的异步上下文管理器）。"""
    api = build_app(reports_router.router)
    with TestClient(api) as client:
        with client.portal.wrap_async_context_manager(world_cm) as world:
            async def _db():
                yield world.session

            async def _user():
                return world.user

            api.dependency_overrides[get_db] = _db
            api.dependency_overrides[get_current_user] = _user
            assert_world_overrides(api)
            yield client, world
