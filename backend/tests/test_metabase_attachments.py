"""Tests for Task 14 (Metabase) and Task 15 (Attachments/Paperless-ngx)

Validates: Requirements 13.1-13.6, 14.1-14.8
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.workpaper_models import WpIndex, WpStatus, WpSourceType, WpFileStatus, WorkingPaper

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
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    project = Project(
        id=FAKE_PROJECT_ID, name="集成测试", client_name="测试",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    idx = WpIndex(project_id=FAKE_PROJECT_ID, wp_code="E1-1", wp_name="货币资金", status=WpStatus.in_progress)
    db_session.add(idx)
    await db_session.flush()
    wp = WorkingPaper(
        project_id=FAKE_PROJECT_ID, wp_index_id=idx.id,
        file_path=f"{FAKE_PROJECT_ID}/E1-1.xlsx",
        source_type=WpSourceType.template, status=WpFileStatus.draft,
        file_version=1, created_by=FAKE_USER_ID,
    )
    db_session.add(wp)
    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID, "wp": wp}


# ── Metabase Service ──

class TestMetabaseService:

    def test_get_embed_url(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService(metabase_url="http://localhost:3000", embedding_secret="test-secret")
        url = svc.get_embed_url("dashboard", 1, {"project_id": "abc"})
        assert "http://localhost:3000/embed/dashboard/" in url
        assert "#bordered=false" in url

    def test_get_dashboard_configs(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService()
        configs = svc.get_dashboard_configs()
        assert len(configs) == 5
        assert configs[0]["id"] == "project_overview"

    def test_get_sql_templates(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService()
        templates = svc.get_sql_templates()
        assert len(templates) == 4
        assert templates[0]["id"] == "total_ledger"


# ── Attachment Service ──

class TestAttachmentService:

    @pytest.mark.asyncio
    async def test_create_attachment(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        result = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "合同.pdf", "file_path": "/storage/合同.pdf",
            "file_type": "pdf", "file_size": 1024000,
        })
        await db_session.commit()
        assert result["file_name"] == "合同.pdf"
        assert result["ocr_status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_attachments(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "发票.jpg", "file_path": "/storage/发票.jpg",
            "file_type": "image", "file_size": 500000,
        })
        await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "合同.pdf", "file_path": "/storage/合同.pdf",
            "file_type": "pdf", "file_size": 1024000,
        })
        await db_session.commit()
        items = await svc.list_attachments(FAKE_PROJECT_ID)
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_filter_by_type(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "发票.jpg", "file_path": "/a", "file_type": "image", "file_size": 100,
        })
        await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "合同.pdf", "file_path": "/b", "file_type": "pdf", "file_size": 200,
        })
        await db_session.commit()
        pdfs = await svc.list_attachments(FAKE_PROJECT_ID, file_type="pdf")
        assert len(pdfs) == 1

    @pytest.mark.asyncio
    async def test_get_attachment(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        created = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "test.pdf", "file_path": "/test", "file_type": "pdf", "file_size": 100,
        })
        await db_session.commit()
        detail = await svc.get_attachment(uuid.UUID(created["id"]))
        assert detail is not None
        assert detail["file_name"] == "test.pdf"

    @pytest.mark.asyncio
    async def test_get_not_found(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        result = await svc.get_attachment(uuid.uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_update_ocr_status(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        created = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "scan.pdf", "file_path": "/scan", "file_type": "pdf", "file_size": 100,
        })
        await db_session.flush()
        updated = await svc.update_ocr_status(
            uuid.UUID(created["id"]), "completed", "OCR识别的文本内容"
        )
        assert updated["ocr_status"] == "completed"

    @pytest.mark.asyncio
    async def test_associate_with_wp(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "证据.pdf", "file_path": "/evidence", "file_type": "pdf", "file_size": 100,
        })
        await db_session.flush()
        link = await svc.associate_with_wp(
            uuid.UUID(att["id"]), seeded_db["wp"].id, "evidence", "审计证据"
        )
        assert link["association_type"] == "evidence"

    @pytest.mark.asyncio
    async def test_get_wp_attachments(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "证据.pdf", "file_path": "/evidence", "file_type": "pdf", "file_size": 100,
        })
        await db_session.flush()
        await svc.associate_with_wp(uuid.UUID(att["id"]), seeded_db["wp"].id)
        await db_session.commit()
        items = await svc.get_wp_attachments(seeded_db["wp"].id)
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_search(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "银行对账单.pdf", "file_path": "/bank", "file_type": "pdf", "file_size": 100,
        })
        await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "合同.pdf", "file_path": "/contract", "file_type": "pdf", "file_size": 200,
        })
        await db_session.commit()
        results = await svc.search(FAKE_PROJECT_ID, "银行")
        assert len(results) == 1
        assert "银行" in results[0]["file_name"]


# ── API Tests ──

@pytest_asyncio.fixture
async def client(db_session: AsyncSession, seeded_db):
    import fakeredis.aioredis
    from httpx import ASGITransport, AsyncClient
    from app.core.database import get_db
    from app.core.redis import get_redis
    from app.main import app

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def override_get_db():
        yield db_session

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestMetabaseAPI:

    @pytest.mark.asyncio
    async def test_dashboards_api(self, client):
        resp = await client.get("/api/metabase/dashboards")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_embed_url_api(self, client):
        resp = await client.get("/api/metabase/embed-url", params={
            "resource_type": "dashboard", "resource_id": 1,
        })
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert "embed_url" in data

    @pytest.mark.asyncio
    async def test_sql_templates_api(self, client):
        resp = await client.get("/api/metabase/sql-templates")
        assert resp.status_code == 200


class TestAttachmentAPI:

    @pytest.mark.asyncio
    async def test_create_api(self, client):
        resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/attachments", json={
            "file_name": "test.pdf", "file_path": "/test", "file_type": "pdf", "file_size": 100,
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_api(self, client):
        await client.post(f"/api/projects/{FAKE_PROJECT_ID}/attachments", json={
            "file_name": "a.pdf", "file_path": "/a", "file_type": "pdf", "file_size": 100,
        })
        resp = await client.get(f"/api/projects/{FAKE_PROJECT_ID}/attachments")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_detail_api(self, client):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/attachments", json={
            "file_name": "b.pdf", "file_path": "/b", "file_type": "pdf", "file_size": 200,
        })
        aid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.get(f"/api/attachments/{aid}")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_api(self, client):
        await client.post(f"/api/projects/{FAKE_PROJECT_ID}/attachments", json={
            "file_name": "银行流水.xlsx", "file_path": "/bank", "file_type": "excel", "file_size": 500,
        })
        resp = await client.get("/api/attachments/search", params={
            "project_id": str(FAKE_PROJECT_ID), "q": "银行",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_associate_api(self, client, seeded_db):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/attachments", json={
            "file_name": "evidence.pdf", "file_path": "/ev", "file_type": "pdf", "file_size": 100,
        })
        aid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.post(f"/api/attachments/{aid}/associate", json={
            "wp_id": str(seeded_db["wp"].id), "association_type": "evidence",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_not_found_api(self, client):
        resp = await client.get(f"/api/attachments/{uuid.uuid4()}")
        assert resp.status_code == 404


# ── 15.5 自动文档分类 + 15.6 函证回函 OCR ──

class TestDocumentClassification:

    @pytest.mark.asyncio
    async def test_classify_contract(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "客户A-销售合同-2025.pdf", "file_path": "/a.pdf",
            "file_type": "pdf", "file_size": 100,
        })
        await db_session.flush()
        result = await svc.classify_document(uuid.UUID(att["id"]))
        assert result["document_type"] == "contract"
        assert result["period_hint"] == "2025"

    @pytest.mark.asyncio
    async def test_classify_invoice(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "增值税发票-202501.jpg", "file_path": "/inv.jpg",
            "file_type": "image", "file_size": 500,
        })
        await db_session.flush()
        result = await svc.classify_document(uuid.UUID(att["id"]))
        assert result["document_type"] == "invoice"
        assert result["file_category"] == "image"

    @pytest.mark.asyncio
    async def test_classify_bank(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "工商银行对账单-2025-06.xlsx", "file_path": "/bank.xlsx",
            "file_type": "excel", "file_size": 200,
        })
        await db_session.flush()
        result = await svc.classify_document(uuid.UUID(att["id"]))
        assert result["document_type"] == "bank_statement"
        assert result["period_hint"] is not None

    @pytest.mark.asyncio
    async def test_classify_confirmation(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "函证回函-客户B.pdf", "file_path": "/conf.pdf",
            "file_type": "pdf", "file_size": 300,
        })
        await db_session.flush()
        result = await svc.classify_document(uuid.UUID(att["id"]))
        assert result["document_type"] == "confirmation"

    @pytest.mark.asyncio
    async def test_classify_unknown(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "readme.txt", "file_path": "/readme.txt",
            "file_type": "text", "file_size": 50,
        })
        await db_session.flush()
        result = await svc.classify_document(uuid.UUID(att["id"]))
        assert result["document_type"] == "unknown"

    @pytest.mark.asyncio
    async def test_classify_not_found(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        with pytest.raises(ValueError, match="附件不存在"):
            await svc.classify_document(uuid.uuid4())


class TestConfirmationOCR:

    @pytest.mark.asyncio
    async def test_extract_full(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "回函.pdf", "file_path": "/reply.pdf",
            "file_type": "pdf", "file_size": 100,
        })
        await db_session.flush()
        await svc.update_ocr_status(uuid.UUID(att["id"]), "completed",
            "致：致同会计师事务所\n"
            "经核对，截至2025年12月31日，贵公司在我行的存款余额为：¥1,234,567.89元。\n"
            "单位：中国工商银行北京分行\n"
            "日期：2026年1月15日"
        )
        await db_session.flush()

        result = await svc.extract_confirmation_reply(uuid.UUID(att["id"]))
        assert result["reply_amount"] == 1234567.89
        assert result["reply_date"] is not None
        assert result["confidence"] in ("high", "medium")

    @pytest.mark.asyncio
    async def test_extract_amount_only(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "回函2.pdf", "file_path": "/reply2.pdf",
            "file_type": "pdf", "file_size": 100,
        })
        await db_session.flush()
        await svc.update_ocr_status(uuid.UUID(att["id"]), "completed",
            "余额：500,000.00元"
        )
        await db_session.flush()

        result = await svc.extract_confirmation_reply(uuid.UUID(att["id"]))
        assert result["reply_amount"] == 500000.00
        assert result["confidence"] == "medium"

    @pytest.mark.asyncio
    async def test_extract_empty_ocr(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        att = await svc.create_attachment(FAKE_PROJECT_ID, {
            "file_name": "空回函.pdf", "file_path": "/empty.pdf",
            "file_type": "pdf", "file_size": 100,
        })
        await db_session.flush()

        result = await svc.extract_confirmation_reply(uuid.UUID(att["id"]))
        assert result["confidence"] == "low"
        assert "OCR 文本为空" in result["message"]

    @pytest.mark.asyncio
    async def test_extract_not_found(self, db_session, seeded_db):
        from app.services.attachment_service import AttachmentService
        svc = AttachmentService(db_session)
        with pytest.raises(ValueError, match="附件不存在"):
            await svc.extract_confirmation_reply(uuid.uuid4())


class TestClassifyAndOCRAPI:

    @pytest.mark.asyncio
    async def test_classify_api(self, client):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/attachments", json={
            "file_name": "合同-客户C-2025.pdf", "file_path": "/c.pdf",
            "file_type": "pdf", "file_size": 100,
        })
        aid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.post(f"/api/attachments/{aid}/classify")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["document_type"] == "contract"

    @pytest.mark.asyncio
    async def test_extract_confirmation_api(self, client):
        create_resp = await client.post(f"/api/projects/{FAKE_PROJECT_ID}/attachments", json={
            "file_name": "回函.pdf", "file_path": "/reply.pdf",
            "file_type": "pdf", "file_size": 100,
        })
        aid = create_resp.json().get("data", create_resp.json())["id"]
        resp = await client.post(f"/api/attachments/{aid}/extract-confirmation")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
# Task 14.5: Metabase Drilldown Tests
# ═══════════════════════════════════════════════════════════════════════


class TestMetabaseDrilldown:

    def test_get_drilldown_config(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService()
        config = svc.get_drilldown_config()
        assert len(config) == 5
        ids = [c["id"] for c in config]
        assert "balance_to_ledger" in ids
        assert "ledger_to_voucher" in ids
        assert "balance_to_aux" in ids

    def test_drilldown_config_structure(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService()
        for path in svc.get_drilldown_config():
            assert "id" in path
            assert "name" in path
            assert "source" in path
            assert "target_level" in path

    def test_build_drilldown_url_ledger(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService()
        url = svc.build_drilldown_url(
            "proj-123", 2024, "ledger", {"account_code": "1001"}
        )
        assert "/projects/proj-123/ledger" in url
        assert "level=ledger" in url
        assert "account_code=1001" in url

    def test_build_drilldown_url_voucher(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService()
        url = svc.build_drilldown_url(
            "proj-123", 2024, "voucher", {"voucher_no": "记-001"}
        )
        assert "level=voucher" in url
        assert "voucher_no=" in url

    def test_build_drilldown_url_aux(self):
        from app.services.metabase_service import MetabaseService
        svc = MetabaseService()
        url = svc.build_drilldown_url(
            "proj-123", 2024, "aux_balance", {"account_code": "1122"}
        )
        assert "level=aux_balance" in url

    @pytest.mark.asyncio
    async def test_drilldown_config_api(self, client):
        resp = await client.get("/api/metabase/drilldown-config")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 5

    @pytest.mark.asyncio
    async def test_drilldown_url_api(self, client):
        resp = await client.get("/api/metabase/drilldown-url", params={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2024,
            "target_level": "ledger",
            "account_code": "1001",
        })
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert "drilldown_url" in data
        assert "ledger" in data["drilldown_url"]
        assert data["target_level"] == "ledger"

    @pytest.mark.asyncio
    async def test_drilldown_url_api_voucher(self, client):
        resp = await client.get("/api/metabase/drilldown-url", params={
            "project_id": str(FAKE_PROJECT_ID),
            "year": 2024,
            "target_level": "voucher",
            "voucher_no": "记-001",
        })
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["target_level"] == "voucher"
