"""科目工作包程序状态测试

覆盖:
- 3.5 刷新后状态不丢失（PATCH 后 GET 返回相同状态）
- 3.6 程序标记不适用时必须填写理由
- 3.7 复核状态变更记录 reviewer 和 reviewed_at
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
from httpx import ASGITransport

from app.models.account_package_models import AccountPackageProgramStatus
from app.services.account_package_program_status_service import (
    AccountPackageProgramStatusService,
    ProgramStatusValidationError,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_user():
    """Mock authenticated user"""
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


@pytest.fixture
def project_id():
    return uuid.uuid4()


@pytest.fixture
def app_with_db(mock_user):
    """Create test app with real-ish mock DB that stores state in memory"""
    from fastapi import FastAPI
    from app.routers.account_packages import router
    from app.core.database import get_db
    from app.deps import get_current_user

    app = FastAPI()
    app.include_router(router)

    # In-memory store to simulate DB persistence
    store: dict[str, AccountPackageProgramStatus] = {}

    class FakeDB:
        """Fake async DB session that persists state in dict"""

        def __init__(self):
            self._added = []

        def add(self, obj):
            self._added.append(obj)

        async def execute(self, stmt):
            # Simple mock: find by composite key
            result = MagicMock()
            # Extract filter criteria from the statement (simplified)
            # We'll intercept via service patching instead
            result.scalar_one_or_none.return_value = None
            result.scalars.return_value = MagicMock(all=lambda: [])
            return result

        async def flush(self):
            for obj in self._added:
                key = f"{obj.project_id}:{obj.account_package_id}:{obj.program_code}"
                store[key] = obj
                self._added = []

        async def commit(self):
            pass

    app.dependency_overrides[get_current_user] = lambda: mock_user
    # We'll use a patched service approach for tests instead
    return app, mock_user, store


@pytest.fixture
def app(mock_user):
    """Create test app with patched service for integration tests"""
    from fastapi import FastAPI
    from app.routers.account_packages import router
    from app.core.database import get_db
    from app.deps import get_current_user

    app = FastAPI()
    app.include_router(router)

    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    return app


# ─── 3.5: 刷新后状态不丢失 ──────────────────────────────────────────────────


class TestProgramStatusPersistence:
    """3.5 测试：PATCH 后 GET 返回相同状态（模拟刷新）"""

    @pytest.mark.asyncio
    async def test_patch_then_get_returns_same_state(self, mock_user, project_id):
        """PATCH 更新后，GET 能获取到相同状态值"""
        from fastapi import FastAPI
        from app.routers.account_packages import router
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        # Simulated persistent storage
        persisted_record = None

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            if persisted_record is not None:
                result.scalar_one_or_none.return_value = persisted_record
                result.scalars.return_value = MagicMock(all=lambda: [persisted_record])
            else:
                result.scalar_one_or_none.return_value = None
                result.scalars.return_value = MagicMock(all=lambda: [])
            return result

        mock_db.execute = mock_execute

        def mock_add(obj):
            nonlocal persisted_record
            persisted_record = obj

        mock_db.add = mock_add

        async def mock_flush():
            pass  # record already set via add

        mock_db.flush = mock_flush

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        pkg_id = "D1_notes_receivable"
        program_code = "D1A"

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # PATCH: set status to in_progress with evidence
            resp = await client.patch(
                f"/projects/{project_id}/account-packages/{pkg_id}/program-status/{program_code}",
                json={
                    "status": "in_progress",
                    "evidence": "已检查银行回单",
                },
            )
            assert resp.status_code == 200
            patch_data = resp.json()
            assert patch_data["status"] == "in_progress"
            assert patch_data["evidence"] == "已检查银行回单"

            # GET: simulate page refresh — should get same state
            resp2 = await client.get(
                f"/projects/{project_id}/account-packages/{pkg_id}/program-status/{program_code}",
            )
            assert resp2.status_code == 200
            get_data = resp2.json()
            assert get_data["status"] == "in_progress"
            assert get_data["evidence"] == "已检查银行回单"
            assert get_data["program_code"] == program_code

    @pytest.mark.asyncio
    async def test_upsert_creates_then_updates(self, project_id, mock_user):
        """service upsert: 首次创建，二次更新同一记录"""
        mock_db = AsyncMock()
        persisted = None

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = persisted
            return result

        mock_db.execute = mock_execute
        mock_db.flush = AsyncMock()

        added_objects = []
        mock_db.add = lambda obj: added_objects.append(obj)

        service = AccountPackageProgramStatusService(mock_db)

        # First upsert: creates
        result = await service.upsert_status(
            project_id, "D1_notes_receivable", "D1A",
            {"status": "in_progress"},
            mock_user.id,
        )
        assert result.status == "in_progress"
        assert result.updated_by == mock_user.id
        assert len(added_objects) == 1

        # Simulate persisted record exists for second call
        persisted = result

        async def mock_execute_2(stmt):
            r = MagicMock()
            r.scalar_one_or_none.return_value = persisted
            return r

        mock_db.execute = mock_execute_2

        # Second upsert: updates existing
        result2 = await service.upsert_status(
            project_id, "D1_notes_receivable", "D1A",
            {"status": "completed", "conclusion": "未发现异常"},
            mock_user.id,
        )
        assert result2.status == "completed"
        assert result2.conclusion == "未发现异常"
        # Should not add new object (update existing)
        assert len(added_objects) == 1


# ─── 3.6: 程序标记不适用时必须填写理由 ────────────────────────────────────────


class TestNotApplicableRequiresReason:
    """3.6 测试：applicable=False 时 not_applicable_reason 必须非空"""

    @pytest.mark.asyncio
    async def test_patch_not_applicable_without_reason_returns_422(
        self, mock_user, project_id
    ):
        """PATCH applicable=False 且无 not_applicable_reason 返回 422"""
        from fastapi import FastAPI
        from app.routers.account_packages import router
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.patch(
                f"/projects/{project_id}/account-packages/D1_notes_receivable/program-status/D1-12",
                json={"applicable": False},
            )
            assert resp.status_code == 422
            assert "不适用理由" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_patch_not_applicable_with_empty_reason_returns_422(
        self, mock_user, project_id
    ):
        """PATCH applicable=False 且 reason 为空字符串返回 422"""
        from fastapi import FastAPI
        from app.routers.account_packages import router
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.patch(
                f"/projects/{project_id}/account-packages/D1_notes_receivable/program-status/D1-12",
                json={"applicable": False, "not_applicable_reason": "   "},
            )
            assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_not_applicable_with_reason_succeeds(
        self, mock_user, project_id
    ):
        """PATCH applicable=False 且有合法 reason 返回 200"""
        from fastapi import FastAPI
        from app.routers.account_packages import router
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.patch(
                f"/projects/{project_id}/account-packages/D1_notes_receivable/program-status/D1-12",
                json={
                    "applicable": False,
                    "not_applicable_reason": "本期无应收票据质押业务",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["applicable"] is False
            assert data["not_applicable_reason"] == "本期无应收票据质押业务"

    @pytest.mark.asyncio
    async def test_service_validation_raises_error(self, project_id, mock_user):
        """Service 层直接验证 applicable=False 无 reason 抛异常"""
        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute

        service = AccountPackageProgramStatusService(mock_db)

        with pytest.raises(ProgramStatusValidationError) as exc_info:
            await service.upsert_status(
                project_id, "D1_notes_receivable", "D1-12",
                {"applicable": False},
                mock_user.id,
            )
        assert "不适用理由" in str(exc_info.value.message)


# ─── 3.7: 复核状态变更记录 reviewer 和 reviewed_at ───────────────────────────


class TestReviewRecordsReviewerAndTimestamp:
    """3.7 测试：设置 review_result 时自动记录 reviewer 和 reviewed_at"""

    @pytest.mark.asyncio
    async def test_setting_review_result_records_reviewer(
        self, mock_user, project_id
    ):
        """PATCH review_result 时自动填充 reviewer=当前用户、reviewed_at=当前时间"""
        from fastapi import FastAPI
        from app.routers.account_packages import router
        from app.core.database import get_db
        from app.deps import get_current_user

        app = FastAPI()
        app.include_router(router)

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_db] = lambda: mock_db

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.patch(
                f"/projects/{project_id}/account-packages/D1_notes_receivable/program-status/D1A",
                json={
                    "status": "reviewed",
                    "review_result": "pass",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["review_result"] == "pass"
            assert data["reviewer"] == str(mock_user.id)
            assert data["reviewed_at"] is not None

    @pytest.mark.asyncio
    async def test_review_result_none_does_not_set_reviewer(
        self, mock_user, project_id
    ):
        """不设置 review_result 时不记录 reviewer"""
        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        service = AccountPackageProgramStatusService(mock_db)
        result = await service.upsert_status(
            project_id, "D1_notes_receivable", "D1A",
            {"status": "in_progress", "evidence": "检查完毕"},
            mock_user.id,
        )
        assert result.reviewer is None
        assert result.reviewed_at is None

    @pytest.mark.asyncio
    async def test_service_sets_reviewer_on_review_result(
        self, mock_user, project_id
    ):
        """Service 层 review_result 非空时自动设置 reviewer + reviewed_at"""
        mock_db = AsyncMock()

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = mock_execute
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        service = AccountPackageProgramStatusService(mock_db)
        result = await service.upsert_status(
            project_id, "D1_notes_receivable", "D1A",
            {"review_result": "conditional", "status": "reviewed"},
            mock_user.id,
        )
        assert result.reviewer == mock_user.id
        assert result.reviewed_at is not None
        assert result.updated_by == mock_user.id
        assert result.updated_at is not None
