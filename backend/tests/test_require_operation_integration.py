"""Integration tests for require_operation wiring on first batch endpoints.

每个端点测试两种场景：
1. authorized user (admin) → 通过（非 403）
2. unauthorized user (eqcr/auditor, 无项目角色) → 403 OPERATION_NOT_ALLOWED

注意：这些测试只验证授权层行为，不验证业务逻辑（业务错误如 404/500 也算通过授权）。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import UserRole


# ─── Fake Users ──────────────────────────────────────────────────────────────


class _FakeUser:
    def __init__(self, role: str):
        self.id = uuid.uuid4()
        self.username = f"test_{role}"
        self.email = f"{role}@test.com"
        self.role = MagicMock()
        self.role.value = role
        self.is_active = True
        self.is_deleted = False


ADMIN_USER = _FakeUser("admin")
AUDITOR_USER = _FakeUser("auditor")  # auditor 无 report:sign, archive:manage


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_app_with_router(router, user):
    """创建测试 FastAPI app，注入指定用户 + mock db。

    通过 patch _resolve_project_role 返回 None，确保只用 system_role 判断。
    """
    app = FastAPI()
    app.include_router(router)

    async def _override_user():
        return user

    mock_db = AsyncMock()
    # 让 db.execute 返回一个可用的 mock result
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value = mock_result
    mock_result.first.return_value = None
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.get = AsyncMock(return_value=None)

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db

    return app


# ─── 5.1 wp_html_save.save_html_data → wp:edit ──────────────────────────────


class TestWpHtmlSaveAuth:
    """POST /api/workpapers/{wp_id}/save — require_operation("wp:edit")"""

    @pytest.mark.asyncio
    async def test_admin_passes(self):
        from app.routers.wp_html_save import router

        app = _make_app_with_router(router, ADMIN_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    f"/api/workpapers/{uuid.uuid4()}/save",
                    json={
                        "sheet_name": "Sheet1",
                        "html_data": {},
                        "schema_version": "v2025-R5",
                    },
                )
        # admin 通过授权层（业务层可能 404/500 但不是 403）
        assert resp.status_code != 403, f"Expected non-403, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_eqcr_denied(self):
        """eqcr 无 wp:edit 权限 → 403"""
        from app.routers.wp_html_save import router

        eqcr_user = _FakeUser("eqcr")
        app = _make_app_with_router(router, eqcr_user)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    f"/api/workpapers/{uuid.uuid4()}/save",
                    json={
                        "sheet_name": "Sheet1",
                        "html_data": {},
                        "schema_version": "v2025-R5",
                    },
                )
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error_code"] == "OPERATION_NOT_ALLOWED"


# ─── 5.4 reports.generate_reports → report:edit ──────────────────────────────


class TestReportsGenerateAuth:
    """POST /api/reports/generate — require_operation("report:edit")"""

    @pytest.mark.asyncio
    async def test_admin_passes(self):
        from app.routers.reports import router

        app = _make_app_with_router(router, ADMIN_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    "/api/reports/generate",
                    json={
                        "project_id": str(uuid.uuid4()),
                        "year": 2025,
                    },
                )
        assert resp.status_code != 403, f"Expected non-403, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_auditor_denied(self):
        """auditor 无 report:edit 权限（无项目角色叠加） → 403"""
        from app.routers.reports import router

        app = _make_app_with_router(router, AUDITOR_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    "/api/reports/generate",
                    json={
                        "project_id": str(uuid.uuid4()),
                        "year": 2025,
                    },
                )
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error_code"] == "OPERATION_NOT_ALLOWED"
        assert body["detail"]["operation"] == "report:edit"


# ─── 5.5 archive.orchestrate → archive:manage ───────────────────────────────


class TestArchiveAuth:
    """POST /api/projects/{pid}/archive/orchestrate — require_operation("archive:manage")"""

    @pytest.mark.asyncio
    async def test_admin_passes(self):
        from app.routers.archive import router

        app = _make_app_with_router(router, ADMIN_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    f"/api/projects/{uuid.uuid4()}/archive/orchestrate",
                    json={"scope": "final"},
                )
        # admin 通过 require_operation 授权（后续 require_confirmation_token 可能 403 但不是 OPERATION_NOT_ALLOWED）
        if resp.status_code == 403:
            body = resp.json()
            assert body["detail"] != {"error_code": "OPERATION_NOT_ALLOWED", "operation": "archive:manage"}, \
                "Should not be blocked by require_operation"

    @pytest.mark.asyncio
    async def test_auditor_denied(self):
        """auditor 无 archive:manage 权限 → 403"""
        from app.routers.archive import router

        app = _make_app_with_router(router, AUDITOR_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    f"/api/projects/{uuid.uuid4()}/archive/orchestrate",
                    json={"scope": "final"},
                )
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error_code"] == "OPERATION_NOT_ALLOWED"
        assert body["detail"]["operation"] == "archive:manage"


# ─── 5.6 signatures.sign_document → report:sign ─────────────────────────────


class TestSignaturesAuth:
    """POST /api/signatures/sign — require_operation("report:sign")"""

    @pytest.mark.asyncio
    async def test_admin_passes(self):
        from app.routers.signatures import router

        app = _make_app_with_router(router, ADMIN_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    "/api/signatures/sign",
                    json={
                        "object_type": "report",
                        "object_id": str(uuid.uuid4()),
                        "signer_id": str(ADMIN_USER.id),
                        "signature_level": "partner",
                    },
                    headers={"X-Confirmation-Token": "test-token"},
                )
        # 通过 require_operation 授权层。如果 403 仍来自 OPERATION_NOT_ALLOWED，说明权限矩阵有问题。
        # 其他 403（如 confirmation token 校验）不算 require_operation 失败。
        if resp.status_code == 403:
            body = resp.json()
            assert body.get("detail") != {"error_code": "OPERATION_NOT_ALLOWED", "operation": "report:sign"}, \
                "Admin should NOT be blocked by require_operation('report:sign')"

    @pytest.mark.asyncio
    async def test_auditor_denied(self):
        """auditor 无 report:sign 权限 → 403"""
        from app.routers.signatures import router

        app = _make_app_with_router(router, AUDITOR_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    "/api/signatures/sign",
                    json={
                        "object_type": "report",
                        "object_id": str(uuid.uuid4()),
                        "signer_id": str(AUDITOR_USER.id),
                        "signature_level": "partner",
                    },
                )
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error_code"] == "OPERATION_NOT_ALLOWED"
        assert body["detail"]["operation"] == "report:sign"


# ─── 5.7 adjustments.create_adjustment → wp:edit ────────────────────────────


class TestAdjustmentsAuth:
    """POST /api/projects/{pid}/adjustments — require_operation("wp:edit")"""

    @pytest.mark.asyncio
    async def test_admin_passes(self):
        from app.routers.adjustments import router

        app = _make_app_with_router(router, ADMIN_USER)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    f"/api/projects/{uuid.uuid4()}/adjustments",
                    json={
                        "account_code": "1001",
                        "debit_amount": 100,
                        "credit_amount": 0,
                        "description": "test",
                        "type": "aje",
                        "year": 2025,
                    },
                )
        assert resp.status_code != 403, f"Expected non-403, got {resp.status_code}: {resp.text}"

    @pytest.mark.asyncio
    async def test_eqcr_denied(self):
        """eqcr 无 wp:edit 权限 → 403"""
        from app.routers.adjustments import router

        eqcr_user = _FakeUser("eqcr")
        app = _make_app_with_router(router, eqcr_user)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch("app.deps._resolve_project_role", new_callable=AsyncMock, return_value=None):
                resp = await client.post(
                    f"/api/projects/{uuid.uuid4()}/adjustments",
                    json={
                        "account_code": "1001",
                        "debit_amount": 100,
                        "credit_amount": 0,
                        "description": "test",
                        "type": "aje",
                        "year": 2025,
                    },
                )
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error_code"] == "OPERATION_NOT_ALLOWED"
