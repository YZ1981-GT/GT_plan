"""全局异常处理器单元测试

Validates: Requirements 4.2, 4.3, 4.4
"""

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from app.middleware.error_handler import (
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


def _create_app() -> FastAPI:
    """创建注册了异常处理器的测试应用。"""
    test_app = FastAPI(debug=False)

    # 注册异常处理器
    test_app.add_exception_handler(HTTPException, http_exception_handler)
    test_app.add_exception_handler(RequestValidationError, validation_exception_handler)
    test_app.add_exception_handler(Exception, generic_exception_handler)

    class ItemCreate(BaseModel):
        name: str = Field(..., min_length=1)
        price: float = Field(..., gt=0)

    @test_app.get("/api/not-found")
    async def not_found():
        raise HTTPException(status_code=404, detail="资源不存在")

    @test_app.get("/api/forbidden")
    async def forbidden():
        raise HTTPException(status_code=403, detail="权限不足")

    @test_app.post("/api/items")
    async def create_item(item: ItemCreate):
        return {"id": 1, "name": item.name}

    @test_app.get("/api/crash")
    async def crash():
        raise RuntimeError("数据库连接失败")

    @test_app.get("/api/ok")
    async def ok():
        return {"status": "ok"}

    return test_app


@pytest.fixture
def app():
    return _create_app()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- HTTPException 处理 ---


@pytest.mark.asyncio
async def test_http_exception_404(client):
    """HTTPException 404 应返回对应状态码和消息。"""
    resp = await client.get("/api/not-found")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 404
    assert body["message"] == "资源不存在"


@pytest.mark.asyncio
async def test_http_exception_403(client):
    """HTTPException 403 应返回对应状态码和消息。"""
    resp = await client.get("/api/forbidden")
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == 403
    assert body["message"] == "权限不足"


# --- RequestValidationError 处理 ---


@pytest.mark.asyncio
async def test_validation_error_missing_fields(client):
    """缺少必填字段应返回 422 + 字段级错误详情。"""
    resp = await client.post("/api/items", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 422
    assert body["message"] == "请求参数校验失败"
    assert isinstance(body["detail"], list)
    assert len(body["detail"]) > 0
    # 验证包含字段级错误信息
    field_names = [e["loc"][-1] for e in body["detail"]]
    assert "name" in field_names
    assert "price" in field_names


@pytest.mark.asyncio
async def test_validation_error_invalid_value(client):
    """字段值不合法应返回 422 + 字段级错误详情。"""
    resp = await client.post("/api/items", json={"name": "", "price": -1})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 422
    assert body["message"] == "请求参数校验失败"
    assert len(body["detail"]) > 0


# --- 未捕获异常处理 ---


@pytest.mark.asyncio
async def test_generic_exception_returns_500(client):
    """未捕获异常应返回 500 通用消息。"""
    resp = await client.get("/api/crash")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == 500
    assert body["message"] == "服务器内部错误"


@pytest.mark.asyncio
async def test_generic_exception_hides_internal_info(client):
    """500 响应不应暴露堆栈、文件路径或内部变量名。"""
    resp = await client.get("/api/crash")
    body = resp.json()
    raw = str(body)
    assert "traceback" not in raw.lower()
    assert "RuntimeError" not in raw
    assert "数据库连接失败" not in raw
    assert ".py" not in raw
    # 只有 code 和 message 两个字段
    assert set(body.keys()) == {"code", "message"}


@pytest.mark.asyncio
async def test_normal_endpoint_unaffected(client):
    """正常端点不受异常处理器影响。"""
    resp = await client.get("/api/ok")
    assert resp.status_code == 200
