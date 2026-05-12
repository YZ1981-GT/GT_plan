"""F50 / Sprint 8.26: rollback 保护 + force-unbind 接口测试。

验证：
- 绑定 final AuditReport 的 dataset 被 rollback → HTTP 409 SIGNED_REPORTS_BOUND
- 绑定 eqcr_approved AuditReport 的 dataset 同样被拒
- 无绑定报表时 rollback 正常
- force-unbind 需要第二审批人（不能自审批）
- force-unbind 需要第二审批人是 admin
- force-unbind 成功后：AuditReport.status 退回 review、bound_dataset_id 清空、
  后续 rollback 被允许
"""
from __future__ import annotations

import uuid
from datetime import date
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

from app.models.base import Base  # noqa: E402

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 模型注册 — 覆盖所有被 bound_dataset_id 引用的表
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401
import app.models.phase15_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.dataset_models import DatasetStatus, LedgerDataset  # noqa: E402
from app.models.report_models import (  # noqa: E402
    AuditReport,
    CompanyType,
    OpinionType,
    ReportStatus,
)
from app.services.dataset_service import DatasetService  # noqa: E402


YEAR = 2024


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


async def _make_project_with_two_datasets(
    db: AsyncSession,
) -> tuple[User, Project, LedgerDataset, LedgerDataset]:
    """创建 project + V1（superseded）+ V2（active，有 previous 指向 V1）。"""
    user = User(
        id=uuid.uuid4(),
        username="rb_tester",
        email="rb@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    proj = Project(
        id=uuid.uuid4(),
        name="rollback 测试",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        audit_period_end=date(YEAR, 12, 31),
    )
    db.add_all([user, proj])
    await db.flush()

    v1 = LedgerDataset(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        status=DatasetStatus.superseded,
        source_type="import",
        created_by=user.id,
    )
    db.add(v1)
    await db.flush()

    v2 = LedgerDataset(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        status=DatasetStatus.active,
        source_type="import",
        previous_dataset_id=v1.id,
        created_by=user.id,
    )
    db.add(v2)
    await db.commit()
    return user, proj, v1, v2


# ---------------------------------------------------------------------------
# 场景 1：有 final 报表绑定时 rollback 被拒
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_blocked_by_final_report(db_session: AsyncSession):
    user, proj, _v1, v2 = await _make_project_with_two_datasets(db_session)

    # 创建一个已签字 final 的 AuditReport 绑定到 v2
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.final,
        bound_dataset_id=v2.id,
    )
    db_session.add(report)
    await db_session.commit()

    # rollback 必须抛 409
    with pytest.raises(HTTPException) as exc_info:
        await DatasetService.rollback(
            db_session, proj.id, YEAR, performed_by=user.id, reason="test"
        )
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert detail["error_code"] == "SIGNED_REPORTS_BOUND"
    assert detail["dataset_id"] == str(v2.id)
    assert len(detail["reports"]) == 1
    assert detail["reports"][0]["id"] == str(report.id)
    assert detail["reports"][0]["status"] == "final"


# ---------------------------------------------------------------------------
# 场景 2：eqcr_approved 状态同样受保护
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_blocked_by_eqcr_approved_report(db_session: AsyncSession):
    user, proj, _v1, v2 = await _make_project_with_two_datasets(db_session)

    report = AuditReport(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.eqcr_approved,
        bound_dataset_id=v2.id,
    )
    db_session.add(report)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await DatasetService.rollback(
            db_session, proj.id, YEAR, performed_by=user.id, reason="t"
        )
    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert len(detail["reports"]) == 1
    assert detail["reports"][0]["status"] == "eqcr_approved"


# ---------------------------------------------------------------------------
# 场景 3：没有绑定报表时 rollback 正常
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_succeeds_when_no_bound_final_report(db_session: AsyncSession):
    """无 final / eqcr_approved 报表时不触发保护，rollback 正常执行。"""
    user, proj, v1, v2 = await _make_project_with_two_datasets(db_session)

    # 草稿状态的报表不触发保护
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.draft,
        bound_dataset_id=v2.id,
    )
    db_session.add(report)
    await db_session.commit()

    restored = await DatasetService.rollback(
        db_session, proj.id, YEAR, performed_by=user.id, reason="restore"
    )
    await db_session.commit()

    assert restored is not None
    assert restored.id == v1.id
    assert restored.status == DatasetStatus.active


# ---------------------------------------------------------------------------
# 场景 4：force-unbind 端点 — 需要第二审批人
# ---------------------------------------------------------------------------

from app.core.database import get_db  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    """FastAPI test client with db + user override。"""
    from httpx import ASGITransport, AsyncClient

    # 操作用户是 admin
    operator = User(
        id=uuid.uuid4(),
        username="admin_op",
        email="op@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(operator)
    await db_session.commit()

    async def _get_db():
        yield db_session

    async def _current_user():
        return operator

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _current_user
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac, operator
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_force_unbind_rejects_self_approval(
    client, db_session: AsyncSession
):
    """第二审批人不能与操作人相同。"""
    ac, operator = client
    user, proj, _v1, v2 = await _make_project_with_two_datasets(db_session)

    resp = await ac.post(
        f"/api/datasets/{v2.id}/force-unbind",
        json={
            "second_approver_id": str(operator.id),
            "reason": "测试自审批",
        },
    )
    assert resp.status_code == 400
    # 全局 http_exception_handler 把 HTTPException.detail 放到 message 字段
    body = resp.json()
    assert body["message"]["error_code"] == "SECOND_APPROVER_SAME_AS_OPERATOR"


@pytest.mark.asyncio
async def test_force_unbind_rejects_non_admin_second_approver(
    client, db_session: AsyncSession
):
    """第二审批人必须是 admin。"""
    ac, _operator = client
    _u, proj, _v1, v2 = await _make_project_with_two_datasets(db_session)

    # 创建一个 partner 用户作为"非 admin"
    partner = User(
        id=uuid.uuid4(),
        username="partner_u",
        email="p@example.com",
        hashed_password="x",
        role=UserRole.partner,
    )
    db_session.add(partner)
    await db_session.commit()

    resp = await ac.post(
        f"/api/datasets/{v2.id}/force-unbind",
        json={
            "second_approver_id": str(partner.id),
            "reason": "测试非 admin 审批",
        },
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["message"]["error_code"] == "SECOND_APPROVER_NOT_ADMIN"


@pytest.mark.asyncio
async def test_force_unbind_unlocks_report_and_allows_rollback(
    client, db_session: AsyncSession
):
    """force-unbind 后:final 报表退回 review → 再次 rollback 成功。"""
    ac, operator = client
    user, proj, v1, v2 = await _make_project_with_two_datasets(db_session)

    # 另一个 admin 作第二审批人
    second_admin = User(
        id=uuid.uuid4(),
        username="admin_2",
        email="a2@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(second_admin)

    # 创建 final AuditReport 绑定 v2
    report = AuditReport(
        id=uuid.uuid4(),
        project_id=proj.id,
        year=YEAR,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        status=ReportStatus.final,
        bound_dataset_id=v2.id,
    )
    db_session.add(report)
    await db_session.commit()

    # Step 1: 初始 rollback 被拒
    with pytest.raises(HTTPException) as exc:
        await DatasetService.rollback(
            db_session, proj.id, YEAR, performed_by=operator.id, reason="t"
        )
    assert exc.value.status_code == 409

    # Step 2: force-unbind 成功
    resp = await ac.post(
        f"/api/datasets/{v2.id}/force-unbind",
        json={
            "second_approver_id": str(second_admin.id),
            "reason": "数据有误需要重新导入",
        },
    )
    assert resp.status_code == 200, resp.text
    # 成功响应被 ResponseWrapperMiddleware 包装为 {code, message, data}
    body = resp.json()
    data = body.get("data", body)
    assert data["dataset_id"] == str(v2.id)
    assert len(data["unlocked_reports"]) == 1
    assert data["unlocked_reports"][0]["id"] == str(report.id)
    assert data["unlocked_reports"][0]["new_status"] == "review"
    assert data["reason"] == "数据有误需要重新导入"

    # Step 3: 验证 AuditReport 已退回 review + bound 清空
    await db_session.refresh(report)
    assert report.status == ReportStatus.review
    assert report.bound_dataset_id is None
    assert report.dataset_bound_at is None

    # Step 4: 现在 rollback 应成功
    restored = await DatasetService.rollback(
        db_session, proj.id, YEAR, performed_by=operator.id, reason="解绑后回滚"
    )
    await db_session.commit()
    assert restored is not None
    assert restored.id == v1.id
    assert restored.status == DatasetStatus.active
