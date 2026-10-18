"""表间审核执行 · 五表 run_id 贯穿 + 0 条「无结果」—— Phase 6 Task 6.4

## 这个文件在干什么

tasks.md Task 6.4 验收判据（集成 + 变异反证）：

  · 执行写五表（run / issue / hint / outbox / audit）且 ``run_id`` 贯穿、可按 run_id 查询。
  · 0 条执行返「无结果」而非「成功」。
  · 变异：把 0 条执行改回「成功」应打红；反向断言有可执行条目时正常。

五表真实名：
  run    = draft_refresh_audit（DraftRefreshAudit，id = run_id）
  issue  = cross_check_results（details.run_id）
  hint   = run 记录 detail.hint_count + 响应 hints（随 run_id）
  outbox = formula_runtime_outbox（run_id 列，FK→draft_refresh_audit.id）
  audit  = append_audit_log 哈希链（details.run_id）

## 为什么「0 条」= 无报表源数据

7 条勾稽是固定公式集，无论有无数据都产 7 个 outcome。真正的「0 条可执行」是
``financial_report`` 该项目/年度 0 行 —— 此时在全 0 数据上跑出的「全部通过」是假
成功。本测试用「有源行 → executed」「无源行 → no_result」两侧对拍这一语义，并做
变异反证（把 no_result 判定改回 executed 应使断言打红）。

## 鉴权口径

用 admin 用户走通 require_project_access（admin 跳过项目权限检查）；
dependency_overrides 覆盖**内层** get_db / get_current_user（教训㉕①：不直接覆盖
require_project_access 工厂）。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus
from app.models.core import Project, User, UserRole
from app.models.report_models import FinancialReport, FinancialReportType
from app.models.wp_optimization_models import CrossCheckResult as CrossCheckResultRow
from app.models.workpaper_models import DraftRefreshAudit, FormulaRuntimeOutbox
from app.models.audit_log_models import AuditLogEntry
from app.services.formula_management.cross_check_run import (
    STATUS_EXECUTED,
    STATUS_NO_RESULT,
    execute_cross_check_run,
    get_issues_by_run,
    get_outbox_by_run,
    get_run_record,
)

# SQLite 无 JSONB —— 用 JSON 渲染（与既有鉴权端点测试同款）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

_YEAR = 2025


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s


async def _seed_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        username="cc_run_admin",
        email="cc_run_admin@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_project(db: AsyncSession, *, name: str) -> Project:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        client_name="测试客户",
        status=ProjectStatus.execution,
        is_deleted=False,
    )
    db.add(project)
    await db.flush()
    return project


async def _seed_balanced_report(db: AsyncSession, project_id: uuid.UUID) -> None:
    """造一套平衡的资产负债表 + 利润表行（使勾稽有真实源数据可执行）。"""
    rows = [
        # BS：资产 = 负债 + 权益（100 = 40 + 60），货币资金 >= 0
        (FinancialReportType.balance_sheet, "assets_total", "资产总计", Decimal("100"), True),
        (FinancialReportType.balance_sheet, "liabilities_total", "负债合计", Decimal("40"), True),
        (FinancialReportType.balance_sheet, "equity_total", "所有者权益合计", Decimal("60"), True),
        (FinancialReportType.balance_sheet, "BS-001", "货币资金", Decimal("30"), False),
        # IS：利润总额 - 所得税 = 净利润（20 - 5 = 15）
        (FinancialReportType.income_statement, "IS-001", "营业收入", Decimal("200"), False),
        (FinancialReportType.income_statement, "IS-002", "营业成本", Decimal("150"), False),
        (FinancialReportType.income_statement, "IS-017", "利润总额", Decimal("20"), False),
        (FinancialReportType.income_statement, "IS-018", "所得税费用", Decimal("5"), False),
        (FinancialReportType.income_statement, "IS-019", "净利润", Decimal("15"), False),
    ]
    for rt, code, name, amt, is_total in rows:
        db.add(
            FinancialReport(
                id=uuid.uuid4(),
                project_id=project_id,
                year=_YEAR,
                report_type=rt,
                row_code=code,
                row_name=name,
                current_period_amount=amt,
                is_total_row=is_total,
            )
        )
    await db.flush()


def _make_app(db: AsyncSession, user: User) -> FastAPI:
    from app.routers import formula_logic_check as fc_router

    app = FastAPI()
    app.include_router(fc_router.router)

    async def _override_db():
        yield db

    async def _override_user():
        return user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


# ═══════════════════════════════════════════════════════════════════════════
# 1) 有源数据 → executed，五表写入 + run_id 贯穿 + 可查询
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_executed_writes_five_tables_with_shared_run_id(db: AsyncSession):
    """有报表源数据时：status=executed，run/issue/outbox/audit 共用同一 run_id 且可查询。"""
    user = await _seed_user(db)
    project = await _seed_project(db, name="有数据项目")
    await _seed_balanced_report(db, project.id)
    await db.commit()

    run = await execute_cross_check_run(
        db, project_id=project.id, year=_YEAR, operator_id=user.id
    )
    await db.commit()

    assert run.status == STATUS_EXECUTED, f"有源数据应 executed，实得 {run.status}"
    assert run.executed_count > 0, "executed_count 应 = 报表源行数 > 0"

    # ── run 表（draft_refresh_audit）：id = run_id，可按 run_id 查 ──
    run_row = await get_run_record(db, run.run_id)
    assert run_row is not None, "run 记录应可按 run_id 查到"
    assert run_row.id == run.run_id
    assert run_row.detail.get("status") == STATUS_EXECUTED
    assert run_row.detail.get("kind") == "report_cross_check"
    assert run_row.result_status == "success"

    # ── issue 表（cross_check_results）：details.run_id 贯穿，可按 run_id 查 ──
    issue_rows = await get_issues_by_run(db, run.run_id)
    assert len(issue_rows) == 7, f"7 条勾稽应各落一行 issue，实得 {len(issue_rows)}"
    for row in issue_rows:
        assert row.details.get("run_id") == str(run.run_id), "每行 issue 须带同一 run_id"

    # ── outbox 表（formula_runtime_outbox）：run_id 列贯穿，可按 run_id 查 ──
    outbox_rows = await get_outbox_by_run(db, run.run_id)
    assert len(outbox_rows) == 1, f"应写一条 outbox 事件，实得 {len(outbox_rows)}"
    assert outbox_rows[0].run_id == run.run_id
    assert outbox_rows[0].event_type == "cross_check_executed"

    # ── audit 哈希链（append_audit_log）：details.run_id 贯穿 ──
    audit_rows = (
        (await db.execute(sa.select(AuditLogEntry))).scalars().all()
    )
    audit_for_run = [
        a for a in audit_rows if (a.payload or {}).get("run_id") == str(run.run_id)
    ]
    assert len(audit_for_run) >= 1, "审计链应有一条带同一 run_id 的记录"
    assert audit_for_run[0].payload.get("module") == "report_cross_check"

    # ── run_id 真的是「同一个」贯穿五处 ──
    assert run_row.id == outbox_rows[0].run_id == run.run_id
    assert issue_rows[0].details["run_id"] == str(run.run_id)
    assert audit_for_run[0].payload["run_id"] == str(run.run_id)


# ═══════════════════════════════════════════════════════════════════════════
# 2) 无源数据 → no_result（不是 success），不写 issue/outbox
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_zero_rows_returns_no_result_not_success(db: AsyncSession):
    """无报表源数据时：status=no_result（无结果），绝不冒充 executed/success。"""
    user = await _seed_user(db)
    project = await _seed_project(db, name="空数据项目")
    await db.commit()

    run = await execute_cross_check_run(
        db, project_id=project.id, year=_YEAR, operator_id=user.id
    )
    await db.commit()

    # 0 条 → 显式「无结果」，不是 executed/success。
    assert run.status == STATUS_NO_RESULT, (
        f"无源数据应 no_result（无结果），实得 {run.status} —— "
        f"这正是「去掉执行 0 条仍成功」要防的假成功"
    )
    assert run.executed_count == 0
    assert run.issue_count == 0 and run.hint_count == 0
    assert run.outbox_written is False, "无结果不应写 outbox（无值变更可传播）"
    assert run.result.outcomes == [], "无结果不应带 7 条假「通过」"

    # run 记录仍留痕（事实可查），但 result_status != success。
    run_row = await get_run_record(db, run.run_id)
    assert run_row is not None
    assert run_row.detail.get("status") == STATUS_NO_RESULT
    assert run_row.result_status != "success", "无结果的 run 不得标 success"

    # 不写 issue / outbox。
    assert await get_issues_by_run(db, run.run_id) == []
    assert await get_outbox_by_run(db, run.run_id) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3) 变异反证：把 0 条判定改回「成功」应使断言打红
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_mutation_zero_as_success_would_fail_the_guard(db: AsyncSession, monkeypatch):
    """变异：强制让无源数据也判 executed（= 把「0 条仍成功」改回来）→ 断言应打红。

    通过 monkeypatch 让 `_count_source_rows` 恒返回 7（伪装成有数据），模拟「0 条仍
    成功」的旧缺陷；此时 status 会变成 executed —— 断言 no_result 必然失败，坐实
    本守卫**真的**在卡这个语义（而不是恒绿）。
    """
    import app.services.formula_management.cross_check_run as mod

    user = await _seed_user(db)
    project = await _seed_project(db, name="空数据项目-变异")
    await db.commit()

    async def _fake_count(_db, *, project_id, year):  # noqa: ANN001
        return 7  # 谎报有 7 行源数据 → 触发「0 条仍成功」缺陷

    monkeypatch.setattr(mod, "_count_source_rows", _fake_count)

    run = await execute_cross_check_run(
        db, project_id=project.id, year=_YEAR, operator_id=user.id
    )
    await db.commit()

    # 变异后 status 变 executed；若守卫断言 no_result，则这里会打红 —— 用 pytest.raises
    # 包住「期望 no_result」的断言，证明变异确实改变了结论（守卫非恒绿）。
    assert run.status == STATUS_EXECUTED, "变异谎报源行数后应被判 executed"
    with pytest.raises(AssertionError):
        assert run.status == STATUS_NO_RESULT, "（反证）本断言在变异下必失败"


# ═══════════════════════════════════════════════════════════════════════════
# 4) 端点集成：GET 返回 run_id + status + no_result 标志
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_endpoint_returns_run_id_and_status(db: AsyncSession):
    """端点契约：返回含 run_id / status / no_result；有数据=executed、空=no_result。"""
    user = await _seed_user(db)
    project_with = await _seed_project(db, name="端点-有数据")
    await _seed_balanced_report(db, project_with.id)
    project_empty = await _seed_project(db, name="端点-无数据")
    await db.commit()

    app = _make_app(db, user)
    client = TestClient(app)

    base_with = f"/api/projects/{project_with.id}/formula/report-cross-check"
    resp = client.get(base_with, params={"year": _YEAR})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    body = body if "status" in body else body.get("data", {})
    assert body["status"] == STATUS_EXECUTED
    assert body["no_result"] is False
    assert uuid.UUID(body["run_id"])  # run_id 可解析为 UUID
    assert isinstance(body["results"], list) and len(body["results"]) == 7

    base_empty = f"/api/projects/{project_empty.id}/formula/report-cross-check"
    resp2 = client.get(base_empty, params={"year": _YEAR})
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    body2 = body2 if "status" in body2 else body2.get("data", {})
    assert body2["status"] == STATUS_NO_RESULT, "空项目端点应返 no_result"
    assert body2["no_result"] is True
    assert body2["results"] == [], "无结果不带任何假「通过」"
