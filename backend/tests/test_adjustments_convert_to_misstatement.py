"""R1 需求 3 — AJE 一键转错报端点集成测试

Validates: Round 1 Requirement 3 (UnconvertedRejectedAJERule suggested_action endpoint)
对应 tasks.md Sprint 1 Task 9。
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user, require_project_access
from app.models.base import Base, UserRole
from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
    Adjustment,
    AdjustmentType,
    ReviewStatus,
    UnadjustedMisstatement,
)
from app.models.core import Project, ProjectStatus, ProjectType
from app.routers.adjustments import router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "test_partner"
        self.email = "partner@test.com"
        self.role = UserRole.admin  # admin 跳过 require_project_access 项目级检查
        self.is_active = True
        self.is_deleted = False


TEST_USER = _FakeUser()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


async def _make_project(db: AsyncSession, name: str = "AJE转错报测试") -> uuid.UUID:
    project = Project(
        id=uuid.uuid4(),
        name=name,
        client_name=name,
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=TEST_USER.id,
    )
    db.add(project)
    await db.flush()

    # 标准科目（AJE 引用）
    db.add_all([
        AccountChart(
            project_id=project.id, account_code="1122", account_name="应收账款",
            direction=AccountDirection.debit, level=1,
            category=AccountCategory.asset, source=AccountSource.standard,
        ),
        AccountChart(
            project_id=project.id, account_code="6001", account_name="主营业务收入",
            direction=AccountDirection.credit, level=1,
            category=AccountCategory.revenue, source=AccountSource.standard,
        ),
    ])
    await db.flush()
    return project.id


def _make_rejected_aje_row(
    project_id: uuid.UUID,
    entry_group_id: uuid.UUID,
    year: int,
    adjustment_no: str,
    account_code: str,
    account_name: str,
    debit: Decimal,
    credit: Decimal,
    description: str | None = "客户拒绝调整",
) -> Adjustment:
    return Adjustment(
        project_id=project_id,
        year=year,
        company_code="001",
        adjustment_no=adjustment_no,
        adjustment_type=AdjustmentType.aje,
        description=description,
        account_code=account_code,
        account_name=account_name,
        debit_amount=debit,
        credit_amount=credit,
        entry_group_id=entry_group_id,
        review_status=ReviewStatus.rejected,
        rejection_reason="客户不同意",
        created_by=TEST_USER.id,
    )


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncClient:
    app = FastAPI()
    app.include_router(router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return TEST_USER

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ───────────────────────────── 正常路径 ─────────────────────────────


@pytest.mark.asyncio
async def test_convert_single_line_rejected_aje(client: AsyncClient, db_session: AsyncSession):
    """单行 rejected AJE 转换成功，返回 misstatement_id 与 net_amount。"""
    pid = await _make_project(db_session)
    group_id = uuid.uuid4()
    db_session.add(_make_rejected_aje_row(
        pid, group_id, 2025, "AJE-001", "1122", "应收账款",
        debit=Decimal("5000"), credit=Decimal("0"),
        description="应收减值",
    ))
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ) as mock_log:
        resp = await client.post(
            f"/api/projects/{pid}/adjustments/{group_id}/convert-to-misstatement",
            json={},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "misstatement_id" in body
    assert uuid.UUID(body["misstatement_id"])  # 合法 UUID
    assert body["source_entry_group_id"] == str(group_id)
    assert Decimal(body["net_amount"]) == Decimal("5000")
    assert body["misstatement_type"] == "factual"
    assert body["year"] == 2025
    assert body["adjustment_count"] == 1
    assert body["created_at"]

    # 审计日志被调用
    assert mock_log.await_count == 1
    call_kwargs = mock_log.await_args.kwargs
    assert call_kwargs["action"] == "adjustment.converted_to_misstatement"
    assert call_kwargs["object_type"] == "adjustment_group"
    assert str(call_kwargs["object_id"]) == str(group_id)
    assert call_kwargs["project_id"] == pid
    assert call_kwargs["details"]["misstatement_id"] == body["misstatement_id"]
    assert call_kwargs["details"]["adjustment_count"] == 1

    # DB 落库
    rows = (
        await db_session.execute(
            UnadjustedMisstatement.__table__.select().where(
                UnadjustedMisstatement.project_id == pid,
            )
        )
    ).fetchall()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_convert_multi_line_group_net_amount(client: AsyncClient, db_session: AsyncSession):
    """多行 group：借 5000 / 贷 5000 → 净额取借方 5000。"""
    pid = await _make_project(db_session)
    group_id = uuid.uuid4()
    db_session.add_all([
        _make_rejected_aje_row(
            pid, group_id, 2025, "AJE-010", "1122", "应收账款",
            debit=Decimal("5000"), credit=Decimal("0"),
            description="收入调整",
        ),
        _make_rejected_aje_row(
            pid, group_id, 2025, "AJE-010", "6001", "主营业务收入",
            debit=Decimal("0"), credit=Decimal("5000"),
            description="收入调整",
        ),
    ])
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        resp = await client.post(
            f"/api/projects/{pid}/adjustments/{group_id}/convert-to-misstatement",
            json={"force": False},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # debit == credit 时 service 取 total_debit
    assert Decimal(body["net_amount"]) == Decimal("5000")
    assert body["adjustment_count"] == 2


# ───────────────────────────── 幂等 ─────────────────────────────


@pytest.mark.asyncio
async def test_convert_idempotent_returns_409(client: AsyncClient, db_session: AsyncSession):
    """同一 group 第二次调用 → 409 ALREADY_CONVERTED，返回现有 misstatement_id。"""
    pid = await _make_project(db_session)
    group_id = uuid.uuid4()
    db_session.add(_make_rejected_aje_row(
        pid, group_id, 2025, "AJE-020", "1122", "应收账款",
        debit=Decimal("3000"), credit=Decimal("0"),
    ))
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        first = await client.post(
            f"/api/projects/{pid}/adjustments/{group_id}/convert-to-misstatement",
            json={},
        )
        assert first.status_code == 200, first.text
        first_ms_id = first.json()["misstatement_id"]

        second = await client.post(
            f"/api/projects/{pid}/adjustments/{group_id}/convert-to-misstatement",
            json={},
        )

    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["error_code"] == "ALREADY_CONVERTED"
    assert detail["existing_misstatement_id"] == first_ms_id


@pytest.mark.asyncio
async def test_convert_force_bypasses_idempotency(client: AsyncClient, db_session: AsyncSession):
    """force=true 允许同一 group 再建第二条错报（备用场景）。"""
    pid = await _make_project(db_session)
    group_id = uuid.uuid4()
    db_session.add(_make_rejected_aje_row(
        pid, group_id, 2025, "AJE-030", "1122", "应收账款",
        debit=Decimal("2000"), credit=Decimal("0"),
    ))
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
    ):
        first = await client.post(
            f"/api/projects/{pid}/adjustments/{group_id}/convert-to-misstatement",
            json={},
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/projects/{pid}/adjustments/{group_id}/convert-to-misstatement",
            json={"force": True},
        )

    assert second.status_code == 200, second.text
    assert second.json()["misstatement_id"] != first.json()["misstatement_id"]

    # DB 有两条
    count_row = (
        await db_session.execute(
            UnadjustedMisstatement.__table__.select().where(
                UnadjustedMisstatement.project_id == pid,
            )
        )
    ).fetchall()
    assert len(count_row) == 2


# ───────────────────────────── 错误路径 ─────────────────────────────


@pytest.mark.asyncio
async def test_convert_nonexistent_group_returns_400(client: AsyncClient, db_session: AsyncSession):
    """group 不存在 → 400。"""
    pid = await _make_project(db_session)
    missing_group = uuid.uuid4()

    resp = await client.post(
        f"/api/projects/{pid}/adjustments/{missing_group}/convert-to-misstatement",
        json={},
    )
    assert resp.status_code == 400
    assert "不存在" in resp.json()["detail"] or "不属于" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_convert_group_from_other_project_returns_400(
    client: AsyncClient, db_session: AsyncSession
):
    """在项目 A 下调用但 group 属于项目 B → 400（项目归属校验）。"""
    pid_a = await _make_project(db_session, name="项目A")
    pid_b = await _make_project(db_session, name="项目B")

    group_id_b = uuid.uuid4()
    db_session.add(_make_rejected_aje_row(
        pid_b, group_id_b, 2025, "AJE-B-001", "1122", "应收账款",
        debit=Decimal("1000"), credit=Decimal("0"),
    ))
    await db_session.commit()

    resp = await client.post(
        f"/api/projects/{pid_a}/adjustments/{group_id_b}/convert-to-misstatement",
        json={},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_convert_audit_log_failure_does_not_block(
    client: AsyncClient, db_session: AsyncSession
):
    """审计日志调用抛异常时业务仍成功（非强一致）。"""
    pid = await _make_project(db_session)
    group_id = uuid.uuid4()
    db_session.add(_make_rejected_aje_row(
        pid, group_id, 2025, "AJE-040", "1122", "应收账款",
        debit=Decimal("800"), credit=Decimal("0"),
    ))
    await db_session.commit()

    with patch(
        "app.services.audit_logger_enhanced.audit_logger.log_action",
        new_callable=AsyncMock,
        side_effect=RuntimeError("mock audit failure"),
    ):
        resp = await client.post(
            f"/api/projects/{pid}/adjustments/{group_id}/convert-to-misstatement",
            json={},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["net_amount"]) == Decimal("800")
