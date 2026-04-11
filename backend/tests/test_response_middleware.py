"""统一响应包装中间件单元测试

Validates: Requirements 4.1
"""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.middleware.response import ResponseWrapperMiddleware


def _create_app() -> FastAPI:
    """创建带中间件的测试应用。"""
    test_app = FastAPI()
    test_app.add_middleware(ResponseWrapperMiddleware)

    @test_app.get("/api/items")
    async def get_items():
        return [{"id": 1, "name": "item1"}]

    @test_app.get("/api/item")
    async def get_item():
        return {"id": 1, "name": "item1"}

    @test_app.get("/api/none")
    async def get_none():
        return None

    @test_app.get("/api/already-wrapped")
    async def get_already_wrapped():
        return {"code": 200, "message": "success", "data": {"id": 1}}

    @test_app.get("/api/error")
    async def get_error():
        return JSONResponse(status_code=400, content={"detail": "bad request"})

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
async def test_wraps_dict_response(client):
    """dict 响应应被包装为 ApiResponse 格式。"""
    resp = await client.get("/api/item")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"] == {"id": 1, "name": "item1"}


@pytest.mark.asyncio
async def test_wraps_list_response(client):
    """list 响应应被包装。"""
    resp = await client.get("/api/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"] == [{"id": 1, "name": "item1"}]


@pytest.mark.asyncio
async def test_wraps_none_response(client):
    """None 响应应被包装。"""
    resp = await client.get("/api/none")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"] is None


@pytest.mark.asyncio
async def test_skips_already_wrapped(client):
    """已经是 ApiResponse 格式的响应不应被二次包装。"""
    resp = await client.get("/api/already-wrapped")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert body["data"] == {"id": 1}
    # 不应有嵌套的 data.data
    assert "data" not in body.get("data", {})


@pytest.mark.asyncio
async def test_skips_error_response(client):
    """非 2xx 响应不应被包装。"""
    resp = await client.get("/api/error")
    assert resp.status_code == 400
    body = resp.json()
    assert body == {"detail": "bad request"}


@pytest.mark.asyncio
async def test_skips_docs_path(client):
    """/docs 路径不应被包装（FastAPI 内置 /docs 返回 HTML）。"""
    resp = await client.get("/docs")
    assert resp.status_code == 200
    # FastAPI /docs 返回 HTML，中间件应跳过不处理
    assert "text/html" in resp.headers.get("content-type", "")
