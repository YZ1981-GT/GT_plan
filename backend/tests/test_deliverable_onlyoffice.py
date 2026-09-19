"""deliverable-center 任务 14：OnlyOffice 降级与 callback 鉴权测试

覆盖：
- Property 54: OnlyOffice 不可用降级 — 健康检查失败时编辑降级只读，
  而预览/下载/版本端点仍可正常响应。Validates: Requirements 28.1
- Property 55: callback JWT 鉴权 — 合法 JWT 被接受并创建新版本；
  非法 JWT 被拒绝（401）且写入一条安全日志。
  Validates: Requirements 29.1, 29.2, 29.3
- 单元测试 14.4: OnlyOffice 不可用核心功能可用（预览/下载/版本端点）。
  Validates: Requirements 28.2, 28.3
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings as app_settings
from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_log_models import AuditLogEntry
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.phase13_models import (
    WordExportStatus,
    WordExportTask,
    WordExportTaskVersion,
)
from app.routers.deliverable import router as deliverable_router
from app.services.onlyoffice_callback_service import OnlyOfficeCallbackService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if hasattr(SQLiteTypeCompiler, "visit_uuid"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_TABLES = [
    User.__table__,
    Project.__table__,
    WordExportTask.__table__,
    WordExportTaskVersion.__table__,
    AuditLogEntry.__table__,
]

ONLYOFFICE_SECRET = "test-onlyoffice-secret"


class _FakeUser:
    def __init__(self, uid, role=UserRole.admin):
        self.id = uid
        self.username = "oo_tester"
        self.email = "oo@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession, *, with_file: bool, tmp_dir: Path | None = None):
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    suffix = user_id.hex[:8]
    db.add(
        User(
            id=user_id,
            username=f"oo_{suffix}",
            email=f"oo_{suffix}@test.com",
            hashed_password="x",
            role=UserRole.admin,
        )
    )
    db.add(
        Project(
            id=project_id,
            name="OO测试项目",
            client_name="OO客户",
            project_type=ProjectType.annual,
            status=ProjectStatus.execution,
            created_by=user_id,
        )
    )
    await db.flush()

    task = WordExportTask(
        id=uuid.uuid4(),
        project_id=project_id,
        doc_type="audit_report",
        status=WordExportStatus.editing.value,
        created_by=user_id,
    )
    db.add(task)
    await db.flush()

    file_path = None
    if with_file and tmp_dir is not None:
        file_path = tmp_dir / "audit_report_v1.docx"
        file_path.write_bytes(b"PK\x03\x04 fake docx content")

    version = WordExportTaskVersion(
        id=uuid.uuid4(),
        word_export_task_id=task.id,
        version_no=1,
        file_path=str(file_path) if file_path else None,
        file_size=file_path.stat().st_size if file_path else None,
        created_by=user_id,
        created_via="generate",
    )
    db.add(version)
    await db.flush()
    return {
        "user_id": user_id,
        "project_id": project_id,
        "task_id": task.id,
        "version_no": 1,
    }


def _build_client(db: AsyncSession, user_id: uuid.UUID) -> AsyncClient:
    app = FastAPI()
    app.include_router(deliverable_router)

    async def _override_db():
        yield db

    async def _override_user():
        return _FakeUser(user_id)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Property 54: OnlyOffice 不可用降级
# ---------------------------------------------------------------------------


# Feature: audit-report-deliverable-center, Property 54: OnlyOffice 不可用降级
@pytest.mark.asyncio
@given(health_ok=st.booleans(), secret_present=st.booleans())
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_property_54_onlyoffice_unavailable_degradation(
    db_session, monkeypatch, health_ok, secret_present
):
    """Property 54: 健康检查失败（或未配置）时编辑降级为只读，
    而预览/下载/版本端点仍可正常响应。

    Validates: Requirements 28.1
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        seed = await _seed(db_session, with_file=True, tmp_dir=Path(tmp))

        monkeypatch.setattr(
            app_settings,
            "ONLYOFFICE_JWT_SECRET",
            ONLYOFFICE_SECRET if secret_present else "",
        )
        # 健康探测结果由参数决定（隔离真实网络）
        async def _fake_health(self):
            return health_ok

        monkeypatch.setattr(OnlyOfficeCallbackService, "health_check", _fake_health)
        # EQCR 判定隔离（无需真实 staff/assignment 表）
        monkeypatch.setattr(
            "app.routers.deliverable._is_project_eqcr",
            _async_false,
        )

        pid, tid, vno = seed["project_id"], seed["task_id"], seed["version_no"]
        async with _build_client(db_session, seed["user_id"]) as client:
            # 健康端点：当密钥缺失或健康探测失败时，available 必为 False（编辑降级信号）
            health = await client.get(f"/api/projects/{pid}/deliverables/onlyoffice/health")
            assert health.status_code == 200
            hbody = health.json()
            edit_available = hbody["available"]
            if not secret_present:
                assert hbody["enabled"] is False
                assert edit_available is False
            else:
                assert hbody["enabled"] is True
                assert edit_available is health_ok

            # 不变式：无论 OnlyOffice 是否可用，核心端点都正常响应
            versions = await client.get(
                f"/api/projects/{pid}/deliverables/{tid}/versions"
            )
            assert versions.status_code == 200
            assert len(versions.json()) >= 1

            preview = await client.get(
                f"/api/projects/{pid}/deliverables/{tid}/versions/{vno}/preview-url"
            )
            assert preview.status_code == 200

            download = await client.get(
                f"/api/projects/{pid}/deliverables/{tid}/versions/{vno}/download"
            )
            assert download.status_code == 200


async def _async_false(*args, **kwargs):
    return False


# ---------------------------------------------------------------------------
# Property 55: callback JWT 鉴权
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        return None


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url):
        return _FakeResponse(b"PK\x03\x04 edited docx bytes")


async def _count_versions(db: AsyncSession, task_id) -> int:
    res = await db.execute(
        sa.select(sa.func.count())
        .select_from(WordExportTaskVersion)
        .where(WordExportTaskVersion.word_export_task_id == task_id)
    )
    return int(res.scalar_one())


async def _count_security_logs(db: AsyncSession) -> int:
    res = await db.execute(
        sa.select(sa.func.count())
        .select_from(AuditLogEntry)
        .where(AuditLogEntry.action_type == "onlyoffice_callback_rejected")
    )
    return int(res.scalar_one())


# Feature: audit-report-deliverable-center, Property 55: callback JWT 鉴权
@pytest.mark.asyncio
@given(valid=st.booleans())
@settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
async def test_property_55_callback_jwt_auth(db_session, monkeypatch, valid):
    """Property 55: 合法 JWT → 接受并创建新版本；
    非法 JWT → 401 拒绝且写入一条安全日志。

    Validates: Requirements 29.1, 29.2, 29.3
    """
    seed = await _seed(db_session, with_file=False)
    pid, tid = seed["project_id"], seed["task_id"]

    monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)
    # 隔离快照与文件下载
    monkeypatch.setattr(
        "app.services.deliverable_snapshot_service.DeliverableSnapshotService.capture_snapshot_refs",
        _fake_capture,
    )
    monkeypatch.setattr(
        "app.services.onlyoffice_callback_service.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    body = {"status": 2, "url": "http://onlyoffice/cache/edited.docx"}
    if valid:
        token = jwt.encode(body, ONLYOFFICE_SECRET, algorithm="HS256")
        headers = {"Authorization": token}
    else:
        headers = {"Authorization": "forged.invalid.token"}

    before_versions = await _count_versions(db_session, tid)
    before_logs = await _count_security_logs(db_session)

    async with _build_client(db_session, seed["user_id"]) as client:
        resp = await client.post(
            f"/api/projects/{pid}/deliverables/onlyoffice/callback/{tid}?year=2024",
            json=body,
            headers=headers,
        )

    await db_session.commit()
    after_versions = await _count_versions(db_session, tid)
    after_logs = await _count_security_logs(db_session)

    if valid:
        assert resp.status_code == 200
        assert resp.json() == {"error": 0}
        # 合法回调 → 创建新版本
        assert after_versions == before_versions + 1
        # 不写安全日志
        assert after_logs == before_logs
    else:
        assert resp.status_code == 401
        # 非法回调 → 不创建版本
        assert after_versions == before_versions
        # 写入一条安全日志
        assert after_logs == before_logs + 1


async def _fake_capture(self, project_id, year, doc_type):
    return {"tb_hash": "fake_hash", "doc_type": doc_type, "year": year}


# ---------------------------------------------------------------------------
# 单元测试 14.4: OnlyOffice 不可用核心功能可用
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unit_core_endpoints_available_when_onlyoffice_down(
    db_session, monkeypatch
):
    """14.4: OnlyOffice 健康检查失败时，预览/下载/版本端点仍正常响应。

    Validates: Requirements 28.2, 28.3
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        seed = await _seed(db_session, with_file=True, tmp_dir=Path(tmp))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        async def _down(self):
            return False

        monkeypatch.setattr(OnlyOfficeCallbackService, "health_check", _down)
        monkeypatch.setattr(
            "app.routers.deliverable._is_project_eqcr", _async_false
        )

        pid, tid, vno = seed["project_id"], seed["task_id"], seed["version_no"]
        async with _build_client(db_session, seed["user_id"]) as client:
            health = await client.get(
                f"/api/projects/{pid}/deliverables/onlyoffice/health"
            )
            assert health.status_code == 200
            assert health.json()["available"] is False  # 需求 28.3 健康检查可用且报告不可用

            # 需求 28.2：核心功能不中断
            assert (
                await client.get(
                    f"/api/projects/{pid}/deliverables/{tid}/versions"
                )
            ).status_code == 200
            assert (
                await client.get(
                    f"/api/projects/{pid}/deliverables/{tid}/versions/{vno}/preview-url"
                )
            ).status_code == 200
            assert (
                await client.get(
                    f"/api/projects/{pid}/deliverables/{tid}/versions/{vno}/download"
                )
            ).status_code == 200


@pytest.mark.asyncio
async def test_unit_jwt_failure_writes_security_log(db_session, monkeypatch):
    """29.2: JWT 校验失败写入安全日志（service 级直接校验）。"""
    seed = await _seed(db_session, with_file=False)
    monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

    svc = OnlyOfficeCallbackService(db_session)
    assert svc.verify_callback_jwt("forged.token", {"status": 2}) is False

    before = await _count_security_logs(db_session)
    await svc.write_security_log(
        seed["task_id"], project_id=seed["project_id"], reason="callback JWT 校验失败"
    )
    after = await _count_security_logs(db_session)
    assert after == before + 1
