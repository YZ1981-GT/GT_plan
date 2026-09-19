"""WOPI 端点 JWT 鉴权 + 软删守卫 安全导向测试套件

专注测试 GET /api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents 端点的：
- JWT 鉴权（无 token → 403；无效 token → 403；有效 token → 200）
- 软删守卫（底稿软删 → 404；项目软删 → 404）
- 无 secret 直通（测试环境行为）

通过 httpx AsyncClient 测试完整 HTTP 端点行为，Mock DB 模拟各场景。

Validates: Requirements R6, R7
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt

from app.core.config import settings as app_settings
from app.routers.wp_onlyoffice_router import public_router, router


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ONLYOFFICE_SECRET = "onlyoffice-dev-secret-2026"
WOPI_ENDPOINT = "/api/workpapers/{wp_id}/sheets/{sheet_name}/wopi/contents"
XLSX_CONTENT = b"PK\x03\x04fake-xlsx-wopi-auth-test-content-bytes"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_token(secret: str = ONLYOFFICE_SECRET, payload: dict | None = None) -> str:
    """生成有效 JWT token"""
    return jwt.encode(payload or {"sub": "onlyoffice", "doc": "test"}, secret, algorithm="HS256")


def _make_expired_token(secret: str = ONLYOFFICE_SECRET) -> str:
    """生成已过期 JWT token"""
    import time
    payload = {"sub": "onlyoffice", "exp": int(time.time()) - 3600}  # 过期 1 小时
    return jwt.encode(payload, secret, algorithm="HS256")


def _build_app_with_db(fake_db):
    """构建测试 FastAPI app + 注入 mock DB"""
    app = FastAPI()
    app.include_router(router)
    # 🔴 callback / wopi.contents / onlyoffice.health 挂在 `public_router`（机对机入口，
    #    绕过 dedicated_wp_gate 的 get_current_user）。只挂 `router` 的测试 app 里它们
    #    根本不存在 ⇒ 全部 404，与生产 `router_registry.workpaper` 同时注册两个 router
    #    不一致（Task 30 关门时修）。
    app.include_router(public_router)

    async def _override_db():
        yield fake_db

    from app.core.database import get_db
    app.dependency_overrides[get_db] = _override_db

    return app


def _make_db_mock_wp_exists(project_id: uuid.UUID, wp_code: str = "D0"):
    """Mock DB: 底稿存在 + 项目未删除"""
    fake_wp = MagicMock()
    fake_wp.project_id = project_id

    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = fake_row

    fake_proj_result = MagicMock()
    fake_proj_result.scalar.return_value = False  # project NOT deleted

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=[fake_wp_result, fake_proj_result])
    return fake_db


def _make_db_mock_wp_deleted():
    """Mock DB: 底稿已软删（WorkingPaper.is_deleted=True → 查询返回 None）"""
    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = None  # 底稿不存在/已删

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=fake_wp_result)
    return fake_db


def _make_db_mock_project_deleted(project_id: uuid.UUID, wp_code: str = "D0"):
    """Mock DB: 底稿存在但项目已软删"""
    fake_wp = MagicMock()
    fake_wp.project_id = project_id

    fake_row = MagicMock()
    fake_row.__getitem__ = lambda self, idx: fake_wp if idx == 0 else wp_code

    fake_wp_result = MagicMock()
    fake_wp_result.first.return_value = fake_row

    fake_proj_result = MagicMock()
    fake_proj_result.scalar.return_value = True  # project IS deleted

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(side_effect=[fake_wp_result, fake_proj_result])
    return fake_db


def _setup_xlsx_file(tmp_path: Path, project_id: uuid.UUID, wp_code: str = "D0") -> Path:
    """在临时存储目录创建模拟 xlsx 文件"""
    storage_dir = tmp_path / "projects" / str(project_id) / "workpapers" / "onlyoffice"
    storage_dir.mkdir(parents=True)
    target = storage_dir / f"{wp_code}.xlsx"
    target.write_bytes(XLSX_CONTENT)
    return target


# ---------------------------------------------------------------------------
# Tests: JWT 鉴权
# ---------------------------------------------------------------------------


class TestWopiAuthNoJwt:
    """无 JWT → 403：配置了 secret 但请求未携带 token"""

    @pytest.mark.asyncio
    async def test_no_auth_header_no_query_param_returns_403(self, tmp_path, monkeypatch):
        """请求完全无 Authorization header 和 token 参数 → 403

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        fake_db = AsyncMock()
        app = _build_app_with_db(fake_db)

        wp_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/workpapers/{wp_id}/sheets/函证检查表/wopi/contents",
            )

        assert resp.status_code == 403
        assert "WOPI 请求未授权" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_empty_authorization_header_returns_403(self, tmp_path, monkeypatch):
        """Authorization header 为空字符串 → 403

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        fake_db = AsyncMock()
        app = _build_app_with_db(fake_db)

        wp_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/workpapers/{wp_id}/sheets/test_sheet/wopi/contents",
                headers={"Authorization": ""},
            )

        assert resp.status_code == 403


class TestWopiAuthInvalidJwt:
    """无效/过期 JWT → 403"""

    @pytest.mark.asyncio
    async def test_wrong_secret_jwt_returns_403(self, tmp_path, monkeypatch):
        """JWT 使用错误密钥签名 → 403

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        fake_db = AsyncMock()
        app = _build_app_with_db(fake_db)

        # 使用错误密钥签名
        bad_token = jwt.encode({"doc": "test"}, "wrong-secret-key", algorithm="HS256")

        wp_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/workpapers/{wp_id}/sheets/test_sheet/wopi/contents",
                headers={"Authorization": f"Bearer {bad_token}"},
            )

        assert resp.status_code == 403
        assert "WOPI 请求未授权" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_expired_jwt_returns_403(self, tmp_path, monkeypatch):
        """已过期 JWT → 403

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        fake_db = AsyncMock()
        app = _build_app_with_db(fake_db)

        expired_token = _make_expired_token()

        wp_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/workpapers/{wp_id}/sheets/test_sheet/wopi/contents",
                headers={"Authorization": f"Bearer {expired_token}"},
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_malformed_jwt_string_returns_403(self, tmp_path, monkeypatch):
        """完全畸形的 token 字符串 → 403

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        fake_db = AsyncMock()
        app = _build_app_with_db(fake_db)

        wp_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/workpapers/{wp_id}/sheets/test_sheet/wopi/contents",
                headers={"Authorization": "Bearer this.is.not.valid.jwt"},
            )

        assert resp.status_code == 403


class TestWopiAuthValidJwt:
    """有效 JWT → 200 返回文件内容"""

    @pytest.mark.asyncio
    async def test_valid_bearer_header_returns_xlsx(self, tmp_path, monkeypatch):
        """Authorization: Bearer <valid_jwt> → 200 + xlsx 文件内容

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        project_id = uuid.uuid4()
        wp_code = "D0"
        _setup_xlsx_file(tmp_path, project_id, wp_code)

        fake_db = _make_db_mock_wp_exists(project_id, wp_code)
        app = _build_app_with_db(fake_db)

        token = _make_valid_token()

        wp_id = uuid.uuid4()
        with patch("app.services.wp_template_finder.find_template_file_any", return_value=None):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/函证检查表/wopi/contents",
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert resp.status_code == 200
        assert resp.content == XLSX_CONTENT
        # 验证 Content-Type 是 xlsx MIME
        assert "spreadsheetml" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_valid_query_param_token_returns_xlsx(self, tmp_path, monkeypatch):
        """?token=<valid_jwt> → 200 + xlsx 文件内容

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        project_id = uuid.uuid4()
        wp_code = "D0"
        _setup_xlsx_file(tmp_path, project_id, wp_code)

        fake_db = _make_db_mock_wp_exists(project_id, wp_code)
        app = _build_app_with_db(fake_db)

        token = _make_valid_token()

        wp_id = uuid.uuid4()
        with patch("app.services.wp_template_finder.find_template_file_any", return_value=None):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/替代程序表/wopi/contents",
                    params={"token": token},
                )

        assert resp.status_code == 200
        assert resp.content == XLSX_CONTENT


# ---------------------------------------------------------------------------
# Tests: 软删守卫
# ---------------------------------------------------------------------------


class TestWopiSoftDeleteGuard:
    """软删守卫：底稿或项目已软删 → 404"""

    @pytest.mark.asyncio
    async def test_wp_soft_deleted_returns_404(self, tmp_path, monkeypatch):
        """底稿 WorkingPaper.is_deleted=True → 404 "底稿不存在"

        Validates: Requirements R7
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        fake_db = _make_db_mock_wp_deleted()
        app = _build_app_with_db(fake_db)

        token = _make_valid_token()

        wp_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/workpapers/{wp_id}/sheets/test_sheet/wopi/contents",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 404
        assert "底稿不存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_project_soft_deleted_returns_404(self, tmp_path, monkeypatch):
        """项目 projects.is_deleted=True → 404 "项目已删除"

        Validates: Requirements R7
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", ONLYOFFICE_SECRET)

        project_id = uuid.uuid4()
        fake_db = _make_db_mock_project_deleted(project_id, "D0")
        app = _build_app_with_db(fake_db)

        token = _make_valid_token()

        wp_id = uuid.uuid4()
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/workpapers/{wp_id}/sheets/test_sheet/wopi/contents",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 404
        assert "项目已删除" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Tests: 无 secret 直通（测试环境）
# ---------------------------------------------------------------------------


class TestWopiNoSecretPassthrough:
    """ONLYOFFICE_JWT_SECRET 为空时，请求直通不校验 JWT"""

    @pytest.mark.asyncio
    async def test_no_secret_no_token_passes_through(self, tmp_path, monkeypatch):
        """无 secret 配置 + 无 token → 直通返回文件（测试环境行为）

        Validates: Requirements R6
        """
        monkeypatch.setattr(app_settings, "STORAGE_ROOT", str(tmp_path))
        monkeypatch.setattr(app_settings, "ONLYOFFICE_JWT_SECRET", "")

        project_id = uuid.uuid4()
        wp_code = "D0"
        _setup_xlsx_file(tmp_path, project_id, wp_code)

        fake_db = _make_db_mock_wp_exists(project_id, wp_code)
        app = _build_app_with_db(fake_db)

        wp_id = uuid.uuid4()
        with patch("app.services.wp_template_finder.find_template_file_any", return_value=None):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # 完全无 token 也能通过
                resp = await client.get(
                    f"/api/workpapers/{wp_id}/sheets/test_sheet/wopi/contents",
                )

        assert resp.status_code == 200
        assert resp.content == XLSX_CONTENT
