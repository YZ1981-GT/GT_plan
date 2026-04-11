"""PDF导出引擎测试

Validates: Requirements 7.1, 7.2, 7.3, 7.7
"""

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.report_models import (
    ExportTask,
    ExportTaskStatus,
    ExportTaskType,
)
from app.services.pdf_export_engine import PDFExportEngine, EXPORT_DIR

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


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


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建测试项目"""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="PDF导出测试_2025",
        client_name="PDF导出测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.commit()
    return FAKE_PROJECT_ID


# ===== HTML 渲染测试 =====


def test_render_audit_report_html():
    """渲染审计报告 HTML"""
    from app.services.pdf_export_engine import _render_audit_report_html
    html = _render_audit_report_html({
        "paragraphs": {"审计意见段": "我们审计了..."}
    })
    assert "审计报告" in html
    assert "审计意见段" in html
    assert "我们审计了" in html


def test_render_financial_report_html():
    """渲染财务报表 HTML"""
    from app.services.pdf_export_engine import _render_financial_report_html
    html = _render_financial_report_html({
        "report_type": "资产负债表",
        "rows": [
            {"row_name": "货币资金", "current_period_amount": 100, "prior_period_amount": 80},
            {"row_name": "资产合计", "current_period_amount": 100, "prior_period_amount": 80, "is_total": True},
        ],
    })
    assert "资产负债表" in html
    assert "货币资金" in html
    assert "100" in html


def test_render_disclosure_notes_html():
    """渲染附注 HTML"""
    from app.services.pdf_export_engine import _render_disclosure_notes_html
    html = _render_disclosure_notes_html({
        "notes": [{
            "note_section": "五、1",
            "section_title": "货币资金",
            "table_data": {
                "headers": ["项目", "期末余额", "期初余额"],
                "rows": [{"label": "库存现金", "values": [50000, 45000]}],
            },
        }],
    })
    assert "财务报表附注" in html
    assert "货币资金" in html
    assert "库存现金" in html


# ===== render_document 测试 =====


@pytest.mark.asyncio
async def test_render_document_html_fallback(db_session: AsyncSession, seeded_db, tmp_path):
    """render_document 在无 WeasyPrint 时回退到 HTML"""
    engine = PDFExportEngine(db_session)
    output = engine.render_document(
        "audit_report",
        {"paragraphs": {"审计意见段": "测试内容"}},
        tmp_path / "test_output",
    )
    # Should produce either .pdf or .html
    assert output.exists()
    assert output.suffix in (".pdf", ".html")


# ===== 导出任务 CRUD 测试 =====


@pytest.mark.asyncio
async def test_create_export_task(db_session: AsyncSession, seeded_db):
    """创建导出任务"""
    engine = PDFExportEngine(db_session)
    task = await engine.create_export_task(
        project_id=FAKE_PROJECT_ID,
        task_type=ExportTaskType.single_document,
        document_type="audit_report",
    )
    await db_session.commit()

    assert task is not None
    assert task.status == ExportTaskStatus.queued
    assert task.project_id == FAKE_PROJECT_ID
    assert task.document_type == "audit_report"


@pytest.mark.asyncio
async def test_execute_export(db_session: AsyncSession, seeded_db):
    """执行导出任务"""
    engine = PDFExportEngine(db_session)
    task = await engine.create_export_task(
        project_id=FAKE_PROJECT_ID,
        task_type=ExportTaskType.single_document,
        document_type="financial_report",
    )
    await db_session.flush()

    result = await engine.execute_export(task.id)
    await db_session.commit()

    assert result.status == ExportTaskStatus.completed
    assert result.progress_percentage == 100
    assert result.file_path is not None
    assert result.completed_at is not None


@pytest.mark.asyncio
async def test_execute_export_not_found(db_session: AsyncSession, seeded_db):
    """执行不存在的导出任务"""
    engine = PDFExportEngine(db_session)
    with pytest.raises(ValueError, match="导出任务不存在"):
        await engine.execute_export(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_task_status(db_session: AsyncSession, seeded_db):
    """查询导出任务状态"""
    engine = PDFExportEngine(db_session)
    task = await engine.create_export_task(
        project_id=FAKE_PROJECT_ID,
        task_type=ExportTaskType.full_archive,
    )
    await db_session.commit()

    status = await engine.get_task_status(task.id)
    assert status is not None
    assert status.id == task.id


@pytest.mark.asyncio
async def test_get_task_status_not_found(db_session: AsyncSession, seeded_db):
    """查询不存在的任务"""
    engine = PDFExportEngine(db_session)
    status = await engine.get_task_status(uuid.uuid4())
    assert status is None


@pytest.mark.asyncio
async def test_get_history(db_session: AsyncSession, seeded_db):
    """获取导出历史"""
    engine = PDFExportEngine(db_session)
    # Create two tasks
    await engine.create_export_task(
        project_id=FAKE_PROJECT_ID,
        task_type=ExportTaskType.single_document,
        document_type="audit_report",
    )
    await engine.create_export_task(
        project_id=FAKE_PROJECT_ID,
        task_type=ExportTaskType.full_archive,
    )
    await db_session.commit()

    history = await engine.get_history(FAKE_PROJECT_ID)
    assert len(history) == 2


@pytest.mark.asyncio
async def test_get_history_empty(db_session: AsyncSession, seeded_db):
    """空项目无导出历史"""
    engine = PDFExportEngine(db_session)
    history = await engine.get_history(uuid.uuid4())
    assert len(history) == 0


# ===== API 路由测试 =====


@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    """创建测试 HTTP 客户端"""
    from app.core.database import get_db
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_create_export_task(client: AsyncClient):
    """POST /api/export/create"""
    resp = await client.post(
        "/api/export/create",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "task_type": "single_document",
            "document_type": "audit_report",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["status"] == "completed"
    assert result["progress_percentage"] == 100


@pytest.mark.asyncio
async def test_api_get_task_status(client: AsyncClient):
    """GET /api/export/{task_id}/status"""
    # Create first
    create_resp = await client.post(
        "/api/export/create",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "task_type": "single_document",
            "document_type": "financial_report",
        },
    )
    create_data = create_resp.json()
    task_id = create_data.get("data", create_data)["id"]

    resp = await client.get(f"/api/export/{task_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_api_get_task_status_not_found(client: AsyncClient):
    """GET 不存在的任务返回 404"""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/export/{fake_id}/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_get_history(client: AsyncClient):
    """GET /api/export/{project_id}/history"""
    # Create a task first
    await client.post(
        "/api/export/create",
        json={
            "project_id": str(FAKE_PROJECT_ID),
            "task_type": "full_archive",
        },
    )

    resp = await client.get(f"/api/export/{FAKE_PROJECT_ID}/history")
    assert resp.status_code == 200
    data = resp.json()
    result = data.get("data", data)
    tasks = result.get("tasks", result) if isinstance(result, dict) else result
    assert len(tasks) >= 1
