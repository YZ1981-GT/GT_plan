"""Tests for Phase 8 Regulatory Service (Task 8) and AI Plugin Executors (Task 13.6-13.13)

- RegulatoryService: CICPA report submission, archival standard submission,
  status tracking, state machine transitions, error handling, retry mechanism
- API endpoints: POST cicpa-report, POST archival-standard, GET status,
  POST retry, GET filings list, POST response
- AI Plugin Executors: stub execute methods for all 8 preset plugins

Validates: Requirements 8.1-8.7, 13.6-13.13
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base, UserRole, ProjectStatus
from app.models.core import User, Project
from app.models.extension_models import RegulatoryFiling

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
FAKE_PROJECT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Create base test data: user + project"""
    user = User(
        id=FAKE_USER_ID,
        username="tester",
        email="t@t.com",
        hashed_password="x",
        role=UserRole.auditor,
    )
    db_session.add(user)
    project = Project(
        id=FAKE_PROJECT_ID,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.created,
    )
    db_session.add(project)
    await db_session.commit()
    return {"user_id": FAKE_USER_ID, "project_id": FAKE_PROJECT_ID}


# ═══════════════════════════════════════════════════════════════════════
# RegulatoryService — Filing Submission Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRegulatorySubmission:

    @pytest.mark.asyncio
    async def test_submit_cicpa_report(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        result = await svc.submit_cicpa_report(
            db_session,
            project_id=FAKE_PROJECT_ID,
            submission_data={"report_number": "2024-001"},
        )
        await db_session.commit()
        assert result["filing_type"] == "cicpa_report"
        assert result["filing_status"] == "submitted"
        assert result["submission_data"]["format"] == "cicpa_v1"
        assert result["submitted_at"] is not None

    @pytest.mark.asyncio
    async def test_submit_archival_standard(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        result = await svc.submit_archival_standard(
            db_session,
            project_id=FAKE_PROJECT_ID,
            submission_data={"archive_id": "ARC-001"},
        )
        await db_session.commit()
        assert result["filing_type"] == "archival_standard"
        assert result["filing_status"] == "submitted"
        assert result["submission_data"]["format"] == "archival_v1"

    @pytest.mark.asyncio
    async def test_submit_cicpa_no_data(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        result = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()
        assert result["filing_status"] == "submitted"
        assert result["submission_data"]["format"] == "cicpa_v1"

    @pytest.mark.asyncio
    async def test_submit_invalid_project(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        with pytest.raises(ValueError, match="项目不存在"):
            await svc.submit_cicpa_report(db_session, project_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_submit_archival_invalid_project(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        with pytest.raises(ValueError, match="项目不存在"):
            await svc.submit_archival_standard(db_session, project_id=uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════
# RegulatoryService — Status Tracking Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRegulatoryStatusTracking:

    @pytest.mark.asyncio
    async def test_check_filing_status(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        status = await svc.check_filing_status(
            db_session, uuid.UUID(filing["id"])
        )
        assert status["filing_status"] == "submitted"
        assert status["filing_type"] == "cicpa_report"

    @pytest.mark.asyncio
    async def test_check_status_not_found(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        with pytest.raises(ValueError, match="备案记录不存在"):
            await svc.check_filing_status(db_session, uuid.uuid4())

    @pytest.mark.asyncio
    async def test_state_transition_submitted_to_pending(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        result = await svc.handle_filing_response(
            db_session,
            filing_id=uuid.UUID(filing["id"]),
            new_status="pending",
            response_data={"tracking_id": "TRK-001"},
        )
        assert result["filing_status"] == "pending"
        assert result["response_data"]["tracking_id"] == "TRK-001"

    @pytest.mark.asyncio
    async def test_state_transition_submitted_to_approved(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        result = await svc.handle_filing_response(
            db_session,
            filing_id=uuid.UUID(filing["id"]),
            new_status="approved",
        )
        assert result["filing_status"] == "approved"

    @pytest.mark.asyncio
    async def test_state_transition_submitted_to_rejected(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        result = await svc.handle_filing_response(
            db_session,
            filing_id=uuid.UUID(filing["id"]),
            new_status="rejected",
            error_message="数据格式不符合要求",
        )
        assert result["filing_status"] == "rejected"
        assert result["error_message"] == "数据格式不符合要求"

    @pytest.mark.asyncio
    async def test_state_transition_pending_to_approved(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        fid = uuid.UUID(filing["id"])
        await svc.handle_filing_response(db_session, fid, "pending")
        result = await svc.handle_filing_response(db_session, fid, "approved")
        assert result["filing_status"] == "approved"

    @pytest.mark.asyncio
    async def test_invalid_state_transition(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        fid = uuid.UUID(filing["id"])
        await svc.handle_filing_response(db_session, fid, "approved")

        with pytest.raises(ValueError, match="非法状态转换"):
            await svc.handle_filing_response(db_session, fid, "submitted")

    @pytest.mark.asyncio
    async def test_invalid_transition_pending_to_submitted(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        fid = uuid.UUID(filing["id"])
        await svc.handle_filing_response(db_session, fid, "pending")

        with pytest.raises(ValueError, match="非法状态转换"):
            await svc.handle_filing_response(db_session, fid, "submitted")


# ═══════════════════════════════════════════════════════════════════════
# RegulatoryService — Retry Mechanism Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRegulatoryRetry:

    @pytest.mark.asyncio
    async def test_retry_rejected_filing(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        fid = uuid.UUID(filing["id"])
        await svc.handle_filing_response(
            db_session, fid, "rejected", error_message="格式错误"
        )

        result = await svc.retry_filing(db_session, fid)
        assert result["filing_status"] == "submitted"
        assert result["response_data"]["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_retry_non_rejected_fails(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        with pytest.raises(ValueError, match="只能重试被拒绝的备案"):
            await svc.retry_filing(db_session, uuid.UUID(filing["id"]))

    @pytest.mark.asyncio
    async def test_retry_max_attempts(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        fid = uuid.UUID(filing["id"])

        # Exhaust retries (3 max)
        for _ in range(3):
            await svc.handle_filing_response(db_session, fid, "rejected")
            await svc.retry_filing(db_session, fid)

        # 4th rejection + retry should fail
        await svc.handle_filing_response(db_session, fid, "rejected")
        with pytest.raises(ValueError, match="已达最大重试次数"):
            await svc.retry_filing(db_session, fid)

    @pytest.mark.asyncio
    async def test_retry_not_found(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        with pytest.raises(ValueError, match="备案记录不存在"):
            await svc.retry_filing(db_session, uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════
# RegulatoryService — List Filings Tests
# ═══════════════════════════════════════════════════════════════════════


class TestRegulatoryListFilings:

    @pytest.mark.asyncio
    async def test_list_all_filings(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await svc.submit_archival_standard(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        filings = await svc.list_filings(db_session)
        assert len(filings) == 2

    @pytest.mark.asyncio
    async def test_list_filings_by_project(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        filings = await svc.list_filings(db_session, project_id=FAKE_PROJECT_ID)
        assert len(filings) == 1
        assert filings[0]["project_id"] == str(FAKE_PROJECT_ID)

    @pytest.mark.asyncio
    async def test_list_filings_by_type(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await svc.submit_archival_standard(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        filings = await svc.list_filings(db_session, filing_type="cicpa_report")
        assert len(filings) == 1
        assert filings[0]["filing_type"] == "cicpa_report"

    @pytest.mark.asyncio
    async def test_list_filings_by_status(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filing = await svc.submit_cicpa_report(db_session, project_id=FAKE_PROJECT_ID)
        await db_session.commit()

        await svc.handle_filing_response(
            db_session, uuid.UUID(filing["id"]), "approved"
        )

        filings = await svc.list_filings(db_session, filing_status="approved")
        assert len(filings) == 1

    @pytest.mark.asyncio
    async def test_list_filings_empty(self, db_session, seeded_db):
        from app.services.regulatory_service import RegulatoryService

        svc = RegulatoryService()
        filings = await svc.list_filings(db_session)
        assert len(filings) == 0


# ═══════════════════════════════════════════════════════════════════════
# AI Plugin Executor Stub Tests (Tasks 13.6-13.13)
# ═══════════════════════════════════════════════════════════════════════


class TestAIPluginExecutors:

    @pytest.mark.asyncio
    async def test_invoice_verify_executor(self):
        from app.services.ai_plugin_service import InvoiceVerifyExecutor

        executor = InvoiceVerifyExecutor()
        result = await executor.execute({"invoice_code": "12345"})
        assert result["plugin"] == "invoice_verify"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_business_info_executor(self):
        from app.services.ai_plugin_service import BusinessInfoExecutor

        executor = BusinessInfoExecutor()
        result = await executor.execute({"company_name": "测试公司"})
        assert result["plugin"] == "business_info"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_bank_reconcile_executor(self):
        from app.services.ai_plugin_service import BankReconcileExecutor

        executor = BankReconcileExecutor()
        result = await executor.execute({"bank_statement_id": "BS-001"})
        assert result["plugin"] == "bank_reconcile"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_seal_check_executor(self):
        from app.services.ai_plugin_service import SealCheckExecutor

        executor = SealCheckExecutor()
        result = await executor.execute({"image_path": "/tmp/seal.png"})
        assert result["plugin"] == "seal_check"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_voice_note_executor(self):
        from app.services.ai_plugin_service import VoiceNoteExecutor

        executor = VoiceNoteExecutor()
        result = await executor.execute({"audio_path": "/tmp/note.wav"})
        assert result["plugin"] == "voice_note"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_wp_review_executor(self):
        from app.services.ai_plugin_service import WpReviewExecutor

        executor = WpReviewExecutor()
        result = await executor.execute({"workpaper_id": "WP-001"})
        assert result["plugin"] == "wp_review"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_continuous_audit_executor(self):
        from app.services.ai_plugin_service import ContinuousAuditExecutor

        executor = ContinuousAuditExecutor()
        result = await executor.execute({"erp_connection": "SAP"})
        assert result["plugin"] == "continuous_audit"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_team_chat_executor(self):
        from app.services.ai_plugin_service import TeamChatExecutor

        executor = TeamChatExecutor()
        result = await executor.execute({"message": "讨论审计方案"})
        assert result["plugin"] == "team_chat"
        assert result["status"] == "stub"

    @pytest.mark.asyncio
    async def test_execute_plugin_via_service(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService

        svc = AIPluginService()
        await svc.load_preset_plugins(db_session)
        await db_session.commit()

        await svc.enable_plugin(db_session, "invoice_verify")
        result = await svc.execute_plugin(
            db_session, "invoice_verify", {"code": "123"}
        )
        assert result["plugin"] == "invoice_verify"

    @pytest.mark.asyncio
    async def test_execute_disabled_plugin(self, db_session, seeded_db):
        from app.services.ai_plugin_service import AIPluginService

        svc = AIPluginService()
        await svc.load_preset_plugins(db_session)
        await db_session.commit()

        with pytest.raises(ValueError, match="未启用"):
            await svc.execute_plugin(
                db_session, "invoice_verify", {"code": "123"}
            )

    @pytest.mark.asyncio
    async def test_plugin_executors_mapping(self):
        from app.services.ai_plugin_service import PLUGIN_EXECUTORS

        expected = [
            "invoice_verify", "business_info", "bank_reconcile",
            "seal_check", "voice_note", "wp_review",
            "continuous_audit", "team_chat",
        ]
        for pid in expected:
            assert pid in PLUGIN_EXECUTORS


# ═══════════════════════════════════════════════════════════════════════
# API Endpoint Tests
# ═══════════════════════════════════════════════════════════════════════


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


class TestRegulatoryAPI:

    @pytest.mark.asyncio
    async def test_submit_cicpa_api(self, client):
        resp = await client.post(
            "/api/regulatory/cicpa-report",
            json={
                "project_id": str(FAKE_PROJECT_ID),
                "submission_data": {"report_number": "RPT-001"},
            },
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["filing_type"] == "cicpa_report"
        assert data["filing_status"] == "submitted"

    @pytest.mark.asyncio
    async def test_submit_archival_api(self, client):
        resp = await client.post(
            "/api/regulatory/archival-standard",
            json={
                "project_id": str(FAKE_PROJECT_ID),
                "submission_data": {"archive_id": "ARC-001"},
            },
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["filing_type"] == "archival_standard"

    @pytest.mark.asyncio
    async def test_submit_invalid_project_api(self, client):
        resp = await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_get_filing_status_api(self, client):
        submit_resp = await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )
        filing_id = submit_resp.json().get("data", submit_resp.json())["id"]

        resp = await client.get(f"/api/regulatory/filings/{filing_id}/status")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["filing_status"] == "submitted"

    @pytest.mark.asyncio
    async def test_get_filing_status_not_found_api(self, client):
        resp = await client.get(
            f"/api/regulatory/filings/{uuid.uuid4()}/status"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_retry_filing_api(self, client):
        # Submit
        submit_resp = await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )
        filing_id = submit_resp.json().get("data", submit_resp.json())["id"]

        # Reject
        await client.post(
            f"/api/regulatory/filings/{filing_id}/response",
            json={"new_status": "rejected", "error_message": "格式错误"},
        )

        # Retry
        resp = await client.post(
            f"/api/regulatory/filings/{filing_id}/retry"
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["filing_status"] == "submitted"

    @pytest.mark.asyncio
    async def test_retry_non_rejected_api(self, client):
        submit_resp = await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )
        filing_id = submit_resp.json().get("data", submit_resp.json())["id"]

        resp = await client.post(
            f"/api/regulatory/filings/{filing_id}/retry"
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_filings_api(self, client):
        await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )
        await client.post(
            "/api/regulatory/archival-standard",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )

        resp = await client.get("/api/regulatory/filings")
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_filings_filter_type_api(self, client):
        await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )
        await client.post(
            "/api/regulatory/archival-standard",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )

        resp = await client.get(
            "/api/regulatory/filings",
            params={"filing_type": "cicpa_report"},
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_handle_response_api(self, client):
        submit_resp = await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )
        filing_id = submit_resp.json().get("data", submit_resp.json())["id"]

        resp = await client.post(
            f"/api/regulatory/filings/{filing_id}/response",
            json={
                "new_status": "approved",
                "response_data": {"approval_code": "APR-001"},
            },
        )
        assert resp.status_code == 200
        data = resp.json().get("data", resp.json())
        assert data["filing_status"] == "approved"

    @pytest.mark.asyncio
    async def test_handle_invalid_transition_api(self, client):
        submit_resp = await client.post(
            "/api/regulatory/cicpa-report",
            json={"project_id": str(FAKE_PROJECT_ID)},
        )
        filing_id = submit_resp.json().get("data", submit_resp.json())["id"]

        # Approve first
        await client.post(
            f"/api/regulatory/filings/{filing_id}/response",
            json={"new_status": "approved"},
        )

        # Try invalid transition
        resp = await client.post(
            f"/api/regulatory/filings/{filing_id}/response",
            json={"new_status": "rejected"},
        )
        assert resp.status_code == 400
