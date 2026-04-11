"""操作日志中间件单元测试

Validates: Requirements 4.5, 4.6, 4.12
"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.middleware.audit_log import (
    AuditLogMiddleware,
    _extract_client_ip,
    _extract_object_id,
    _extract_object_type,
    _extract_user_id_from_token,
)


# ---------------------------------------------------------------------------
# Helper: 创建测试 token
# ---------------------------------------------------------------------------

def _make_token(user_id: str) -> str:
    """创建一个真实的 JWT token 用于测试。"""
    from app.core.security import create_access_token
    return create_access_token({"sub": user_id})


# ---------------------------------------------------------------------------
# 纯函数单元测试
# ---------------------------------------------------------------------------


class TestExtractClientIp:
    """IP 提取逻辑测试。"""

    def test_x_forwarded_for_single(self):
        """单个 IP 的 X-Forwarded-For。"""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "192.168.1.100"}
        request.client = MagicMock(host="10.0.0.1")
        assert _extract_client_ip(request) == "192.168.1.100"

    def test_x_forwarded_for_chain(self):
        """多级代理链，取第一个 IP。"""
        request = MagicMock()
        request.headers = {"x-forwarded-for": "203.0.113.50, 70.41.3.18, 150.172.238.178"}
        request.client = MagicMock(host="10.0.0.1")
        assert _extract_client_ip(request) == "203.0.113.50"

    def test_fallback_to_client_host(self):
        """无 X-Forwarded-For 时回退到 request.client.host。"""
        request = MagicMock()
        request.headers = {}
        request.client = MagicMock(host="127.0.0.1")
        assert _extract_client_ip(request) == "127.0.0.1"

    def test_no_client(self):
        """无 client 信息时返回 None。"""
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert _extract_client_ip(request) is None


class TestExtractObjectType:
    """object_type 提取逻辑测试。"""

    def test_users_path(self):
        assert _extract_object_type("/api/users") == "user"

    def test_users_with_id(self):
        assert _extract_object_type("/api/users/some-uuid") == "user"

    def test_projects_path(self):
        assert _extract_object_type("/api/projects") == "project"

    def test_auth_path(self):
        assert _extract_object_type("/api/auth/logout") == "auth"

    def test_wopi_path(self):
        assert _extract_object_type("/wopi/files/test.xlsx") == "file"

    def test_empty_path(self):
        assert _extract_object_type("/api/") == "unknown"


class TestExtractObjectId:
    """object_id 提取逻辑测试。"""

    def test_uuid_in_path(self):
        uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        result = _extract_object_id(f"/api/users/{uid}")
        assert result == uuid.UUID(uid)

    def test_no_uuid(self):
        assert _extract_object_id("/api/users") is None

    def test_uppercase_uuid(self):
        uid = "A1B2C3D4-E5F6-7890-ABCD-EF1234567890"
        result = _extract_object_id(f"/api/users/{uid}")
        assert result == uuid.UUID(uid)


class TestExtractUserIdFromToken:
    """从 Authorization header 提取 user_id 测试。"""

    def test_valid_token(self):
        uid = str(uuid.uuid4())
        token = _make_token(uid)
        request = MagicMock()
        request.headers = {"authorization": f"Bearer {token}"}
        result = _extract_user_id_from_token(request)
        assert result == uuid.UUID(uid)

    def test_no_auth_header(self):
        request = MagicMock()
        request.headers = {}
        assert _extract_user_id_from_token(request) is None

    def test_invalid_token(self):
        request = MagicMock()
        request.headers = {"authorization": "Bearer invalid.token.here"}
        assert _extract_user_id_from_token(request) is None

    def test_non_bearer_scheme(self):
        request = MagicMock()
        request.headers = {"authorization": "Basic dXNlcjpwYXNz"}
        assert _extract_user_id_from_token(request) is None


# ---------------------------------------------------------------------------
# 中间件集成测试（使用 mock 替代数据库写入）
# ---------------------------------------------------------------------------


def _create_app() -> FastAPI:
    """创建带审计日志中间件的测试应用。"""
    test_app = FastAPI()
    test_app.add_middleware(AuditLogMiddleware)

    @test_app.post("/api/users")
    async def create_user():
        return {"id": str(uuid.uuid4()), "username": "testuser"}

    @test_app.put("/api/users/{user_id}")
    async def update_user(user_id: str):
        return {"id": user_id, "username": "updated"}

    @test_app.delete("/api/users/{user_id}")
    async def delete_user(user_id: str):
        return {"deleted": True}

    @test_app.get("/api/users")
    async def list_users():
        return [{"id": "1", "username": "user1"}]

    @test_app.post("/api/auth/login")
    async def login():
        return {"access_token": "xxx"}

    @test_app.post("/api/health")
    async def health_post():
        return {"status": "ok"}

    return test_app


@pytest.fixture
def app():
    return _create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_post_creates_audit_log(client):
    """POST 请求应触发审计日志写入。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.post("/api/users")
        assert resp.status_code == 200
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "create"
        assert call_kwargs["object_type"] == "user"


@pytest.mark.asyncio
async def test_put_creates_update_log(client):
    """PUT 请求应记录 update 类型日志。"""
    uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.put(f"/api/users/{uid}")
        assert resp.status_code == 200
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "update"
        assert call_kwargs["object_id"] == uuid.UUID(uid)


@pytest.mark.asyncio
async def test_delete_creates_delete_log(client):
    """DELETE 请求应记录 delete 类型日志。"""
    uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.delete(f"/api/users/{uid}")
        assert resp.status_code == 200
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["action_type"] == "delete"


@pytest.mark.asyncio
async def test_get_does_not_create_log(client):
    """GET 请求不应触发审计日志。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.get("/api/users")
        assert resp.status_code == 200
        mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_skip_login_path(client):
    """登录路径应跳过日志记录。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.post("/api/auth/login")
        assert resp.status_code == 200
        mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_skip_health_path(client):
    """/api/health 路径应跳过日志记录。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.post("/api/health")
        assert resp.status_code == 200
        mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_captures_ip_from_x_forwarded_for(client):
    """应从 X-Forwarded-For 提取 IP。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.post(
            "/api/users",
            headers={"X-Forwarded-For": "203.0.113.50, 70.41.3.18"},
        )
        assert resp.status_code == 200
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["ip_address"] == "203.0.113.50"


@pytest.mark.asyncio
async def test_captures_new_value_from_response(client):
    """应从响应体捕获 new_value。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.post("/api/users")
        assert resp.status_code == 200
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["new_value"] is not None
        assert "username" in call_kwargs["new_value"]


@pytest.mark.asyncio
async def test_old_value_is_none(client):
    """中间件层 old_value 暂为 None（后续由 CRUD 服务增强）。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.post("/api/users")
        assert resp.status_code == 200
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["old_value"] is None


@pytest.mark.asyncio
async def test_response_body_preserved(client):
    """审计日志中间件不应改变响应体内容。"""
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock):
        resp = await client.post("/api/users")
        assert resp.status_code == 200
        body = resp.json()
        assert "username" in body
        assert body["username"] == "testuser"


@pytest.mark.asyncio
async def test_captures_user_id_from_token(client):
    """应从 JWT token 中提取 user_id。"""
    uid = str(uuid.uuid4())
    token = _make_token(uid)
    with patch("app.middleware.audit_log._write_log", new_callable=AsyncMock) as mock_log:
        resp = await client.post(
            "/api/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["user_id"] == uuid.UUID(uid)
