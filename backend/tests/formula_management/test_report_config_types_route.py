"""report-config/types 路由修复 —— Phase 6 Task 6.1（§1 #8 / design §5 步骤 6）

## 这个文件在干什么

§1 锚点 #8 实测坐实：`report_config.py` 无 `GET /types` 路由，`/api/report-config/types`
命中动态路由 `GET /{config_id}`（`config_id: UUID`）→ `"types"` 不是合法 UUID →
FastAPI 路径参数校验失败返 **422**。前端 `FormulaManagerDialog.vue : loadReportTypes`
与 `docStructureTree.ts : buildDocStructureDynamic` 因此只能降级到静态报表子类。

Task 6.1 新增真实 `GET /types` 路由，声明在 `GET /{config_id}` **之前**（FastAPI 按
声明顺序匹配，静态路径须先声明否则仍被 UUID 路由先捕获）。本测试：

  · `test_types_route_returns_200_contract` —— `/types` 返 200，响应为
    `[{report_type, label, formula_count}]`（前端消费契约），不再 422。
  · `test_types_route_declared_before_config_id`（变异反证）—— 把 `/types` 路由从
    router 的路由表里移除后，同一请求回落到 `GET /{config_id}`（UUID 校验）→ 422。
    移除即打红证明：是 `/types` 路由本身在挡住 422，而非别的原因偶然为 200。

## 鉴权口径（Task 5.3 / ADR-FMC-06 同口径）

`/types` 与 `list_report_configs` 一致：给定 project_id 时按 readonly 做项目级鉴权；
无 project_id 时按 enterprise 全局模板读（登录门控）。本测试走无 project_id 路径
（enterprise 标准），只验「路由存在 + 契约 + 顺序」这一 Task 6.1 的核心判据，
不重复 Task 5.1/5.3 的越权坐实。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base
from app.models.core import User, UserRole
from app.models.report_models import FinancialReportType, ReportConfig

# SQLite 没有 JSONB —— 用 JSON 渲染（与既有鉴权端点测试同款）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


@pytest_asyncio.fixture
async def seed(db: AsyncSession) -> User:
    """建一个登录用户，并在 enterprise 标准下播几条带 formula / 无 formula 的报表行。

    - balance_sheet：2 行有 formula（formula_count 应为 2）。
    - income_statement：1 行有 formula、1 行无 formula（formula_count 应为 1）。
    - 其余 4 个报表子类无行（formula_count 应为 0，但仍须在 /types 结果中出现）。
    """
    user = User(
        id=uuid.uuid4(),
        username="types_reader",
        email="types_reader@example.com",
        hashed_password="x",
        role=UserRole.manager,
    )
    db.add(user)

    rows = [
        ReportConfig(
            id=uuid.uuid4(),
            report_type=FinancialReportType.balance_sheet,
            row_number=1, row_code="BS-1", row_name="货币资金",
            applicable_standard="enterprise",
            formula="TB('1001','期末余额')",
            is_deleted=False,
        ),
        ReportConfig(
            id=uuid.uuid4(),
            report_type=FinancialReportType.balance_sheet,
            row_number=2, row_code="BS-2", row_name="应收账款",
            applicable_standard="enterprise",
            formula="TB('1122','期末余额')",
            is_deleted=False,
        ),
        ReportConfig(
            id=uuid.uuid4(),
            report_type=FinancialReportType.income_statement,
            row_number=1, row_code="IS-1", row_name="营业收入",
            applicable_standard="enterprise",
            formula="TB('6001','本期发生额')",
            is_deleted=False,
        ),
        ReportConfig(
            id=uuid.uuid4(),
            report_type=FinancialReportType.income_statement,
            row_number=2, row_code="IS-2", row_name="空公式行",
            applicable_standard="enterprise",
            formula=None,  # 无 formula → 不计入 formula_count
            is_deleted=False,
        ),
    ]
    db.add_all(rows)
    await db.flush()
    await db.commit()
    return user


def _make_app(db: AsyncSession, user: User) -> FastAPI:
    """挂载 report_config router，override 内层 get_db / get_current_user（教训㉕①）。"""
    from app.routers import report_config as report_config_router

    app = FastAPI()
    app.include_router(report_config_router.router)

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


def test_types_route_returns_200_contract(db: AsyncSession, seed: User):
    """`/types` 返 200，契约 = [{report_type, label, formula_count}]，不再 422。"""
    app = _make_app(db, seed)
    client = TestClient(app)

    resp = client.get("/api/report-config/types")

    assert resp.status_code == 200, (
        f"/types 应返 200（不再被 /{{config_id}} 捕获 422），实得 {resp.status_code}: {resp.text}"
    )
    data = resp.json()
    # 响应信封在本测试 app 未挂中间件 ⇒ 直接是裸 list。
    items = data if isinstance(data, list) else data.get("data", [])
    assert isinstance(items, list) and items, "应返回非空报表子类列表"

    by_type = {it["report_type"]: it for it in items}
    # 全部 6 个 FinancialReportType 子类都应出现（含无行的 count=0）。
    expected_types = {t.value for t in FinancialReportType}
    assert set(by_type) == expected_types, f"报表子类集合不符：{set(by_type)}"

    # 契约字段齐全。
    for it in items:
        assert set(it) >= {"report_type", "label", "formula_count"}
        assert isinstance(it["label"], str) and it["label"]
        assert isinstance(it["formula_count"], int)

    # 计数正确：balance_sheet=2、income_statement=1（空公式行不计）、其余 0。
    assert by_type["balance_sheet"]["formula_count"] == 2
    assert by_type["income_statement"]["formula_count"] == 1
    assert by_type["cash_flow_statement"]["formula_count"] == 0
    assert by_type["equity_statement"]["formula_count"] == 0
    # 标签与前端 fallback 对齐。
    assert by_type["balance_sheet"]["label"] == "资产负债表"
    assert by_type["income_statement"]["label"] == "利润表"


def test_types_route_declared_before_config_id(db: AsyncSession, seed: User):
    """变异反证：移除 `/types` 路由后，请求回落到 `GET /{config_id}` 的 UUID 路由 → 422。

    通过在一个克隆 app 上剔除匹配 path=="/api/report-config/types" 的路由，模拟
    「没有 /types 路由」的旧状态；此时 "types" 命中 /{config_id} 的 UUID 解析失败 → 422。
    若未来有人把 /types 声明到 /{config_id} 之后，静态路由也会被动态路由先匹配、
    同样退回 422，本断言一并守护声明顺序。
    """
    app = _make_app(db, seed)

    # 剔除 /types 路由，保留 /{config_id}。
    app.router.routes = [
        r for r in app.router.routes
        if getattr(r, "path", None) != "/api/report-config/types"
    ]
    client = TestClient(app)

    resp = client.get("/api/report-config/types")
    assert resp.status_code == 422, (
        "移除 /types 路由后，/types 应被 /{config_id} 的 UUID 路由捕获为 422（变异反证），"
        f"实得 {resp.status_code}: {resp.text}"
    )
