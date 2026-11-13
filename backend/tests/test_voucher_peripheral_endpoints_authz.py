"""凭证模块外围端点的鉴权与退役（spec voucher-workflow-linkage-lineage-closure R9）

SQLite 真 ORM 行 + 端点级请求（覆盖 get_db / get_current_user，项目成员判定照常跑；服务层在路由模块下一层打桩）：

- 附注章节溯源、发现汇总、底稿 AI 序时账分析、抽样增强页三个取数端点（截止测试 / 账龄 / 月度明细）：
  非成员 403，只读成员 200，未登录 401；
- 单据识别两端点：410 + ENDPOINT_RETIRED，处理函数不依赖数据库、模块不再引用识别服务。
"""

from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
pytestmark = pytest.mark.asyncio

READER, STRANGER, PROJECT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        for uid, name in ((READER, "reader"), (STRANGER, "stranger")):
            session.add(User(id=uid, username=name, email=f"{name}@t.com", hashed_password="x", role="auditor"))
        session.add(Project(id=PROJECT, name="外围端点", client_name="测试", project_type=ProjectType.annual,
                            status=ProjectStatus.execution, created_by=READER))
        session.add(ProjectUser(project_id=PROJECT, user_id=READER, role="auditor", permission_level="readonly",
                                is_deleted=False))
        await session.commit()
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import report_trace, sampling_enhanced, wp_chat, wp_document_recognize
    from app.services.report_trace_service import ReportTraceService
    from app.services.sampling_enhanced_service import AgingAnalysisService, CutoffTestService, MonthlyDetailService
    from app.services.wp_chat_service import WpChatService

    async def _trace(self, _db, project_id, section_number, year=None):
        return {"section": section_number, "project_id": str(project_id)}

    async def _findings(self, _db, project_id):
        return {"project_id": str(project_id), "items": []}

    async def _ledger(self, _db, project_id, account_codes, year):
        return {"project_id": str(project_id)}

    async def _sampling(self, _db, project_id, *args, **kwargs):
        return {"project_id": str(project_id)}

    monkeypatch.setattr(ReportTraceService, "trace_section", _trace)
    monkeypatch.setattr(ReportTraceService, "get_findings_summary", _findings)
    monkeypatch.setattr(WpChatService, "generate_ledger_analysis", _ledger)
    monkeypatch.setattr(CutoffTestService, "run_cutoff_test", _sampling)
    monkeypatch.setattr(AgingAnalysisService, "analyze_aging", _sampling)
    monkeypatch.setattr(MonthlyDetailService, "generate_monthly_detail", _sampling)

    app = FastAPI()
    app.include_router(report_trace.router)
    app.include_router(sampling_enhanced.router)
    app.include_router(wp_chat.router)
    app.include_router(wp_document_recognize.router, prefix="/api")
    state: dict = {"user": READER}

    async def _db():
        yield db

    async def _user():
        if state["user"] is None:
            raise HTTPException(status_code=401, detail="未登录")
        return (await db.execute(sa.select(User).where(User.id == state["user"]))).scalar_one()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        c.as_user = lambda uid: state.update(user=uid)  # type: ignore[attr-defined]
        yield c


def _calls(pid=PROJECT):
    brackets = [{"label": "1年以内", "min_days": 0, "max_days": 365}]
    return [
        ("GET", f"/api/report-review/{pid}/trace/五、1", None),
        ("GET", f"/api/projects/{pid}/findings-summary", None),
        ("POST", f"/api/workpapers/projects/{pid}/ai/generate-ledger-analysis", {"account_codes": ["1002"], "year": 2025}),
        # 抽样增强页三个取数端点（读项目序时账）
        ("POST", f"/api/projects/{pid}/sampling/cutoff-test", {"account_codes": ["6001"], "year": 2025}),
        ("POST", f"/api/projects/{pid}/sampling/aging-analysis",
         {"account_code": "1122", "aging_brackets": brackets, "base_date": "2025-12-31", "year": 2025}),
        ("POST", f"/api/projects/{pid}/sampling/monthly-detail", {"account_code": "6001", "year": 2025}),
    ]


@pytest.mark.parametrize(("who", "status"), [(READER, 200), (STRANGER, 403), (None, 401)], ids=["只读成员", "非成员", "未登录"])
async def test_project_scoped_reads_require_membership(client, who, status):
    client.as_user(who)
    for method, url, body in _calls():
        resp = await client.request(method, url, json=body)
        assert resp.status_code == status, f"{method} {url} → {resp.status_code} {resp.text[:200]}"


@pytest.mark.parametrize(("method", "path"), [("POST", ""), ("GET", "/types")])
async def test_document_recognize_is_retired(client, method, path):
    resp = await client.request(method, f"/api/projects/{PROJECT}/document-recognize{path}",
                                json={"attachments": [{"attachment_id": str(uuid.uuid4())}]} if method == "POST" else None)
    assert resp.status_code == 410
    assert resp.json()["detail"]["error_code"] == "ENDPOINT_RETIRED"
    assert "上传证据" in resp.json()["detail"]["message"]


async def test_document_recognize_handlers_touch_no_db_or_model():
    from app.routers import wp_document_recognize as mod

    for fn in (mod.recognize_documents, mod.get_doc_types):
        assert "db" not in inspect.signature(fn).parameters
    tree = ast.parse((ROUTERS / "wp_document_recognize.py").read_text(encoding="utf-8"))
    imported = {a.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for a in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not {"wp_document_recognizer", "app.services.wp_document_recognizer", "get_db"} & imported
