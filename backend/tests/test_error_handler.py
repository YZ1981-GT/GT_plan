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

    @test_app.get("/api/conflict-dict")
    async def conflict_dict():
        # 全仓大量 router 用 dict detail 传结构化错误码，前端按 `detail.error_code`
        # 这类读法取值，所以「dict 不被字符串化」是跨层契约的一部分。
        raise HTTPException(
            status_code=409,
            detail={"error_code": "data_version_conflict", "server_version": 5},
        )

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


@pytest.mark.asyncio
async def test_http_exception_dict_detail_stays_dict(client):
    """dict 形态的 ``detail`` 必须原样落在 ``message``，不得被字符串化。

    跨层契约：前端 ``utils/http.ts::normaliseErrorEnvelope`` 把 ``message`` 回填成
    ``detail`` 供下游读取，``handleApiError`` 与各视图靠 ``detail.error_code`` /
    ``detail.message`` 做分派。一旦这里退化成 ``str(exc.detail)``，前端拿到的就是
    ``"{'error_code': ...}"`` 这种字符串，所有结构化分派会静默失效（只走兜底文案）。
    """
    resp = await client.get("/api/conflict-dict")
    assert resp.status_code == 409
    body = resp.json()
    assert isinstance(body["message"], dict), "dict detail 被字符串化 ⇒ 前端结构化分派全失效"
    assert body["message"]["error_code"] == "data_version_conflict"
    assert body["message"]["server_version"] == 5


@pytest.mark.asyncio
async def test_http_exception_body_has_no_detail_key(client):
    """业务 ``HTTPException`` 的响应体**不含** ``detail`` 键 —— 固化这个事实本身。

    平台信封是 ``{code, message, data}``，全局处理器把 ``exc.detail`` 放进 ``message``。
    但 FastAPI/starlette 原生错误（路由 404、``RequestValidationError``）输出的是
    ``detail``，两种形状在同一个 API 上并存。前端因此在 ``utils/http.ts`` 的响应拦截器里
    统一回填 ``detail``（并有 ``errorEnvelopeNormalisation.spec.ts`` 守着）。

    这条判据是那段前端适配存在的**理由锚点**：若哪天这里改成同时输出 ``detail``，
    它会转红，提示去评估前端适配是否该一并收敛，而不是让两处默默地各写一份。
    真栈实测（2026-09-23，后端 9980）：``GET /api/projects/{不存在}`` ⇒
    ``{"code":404,"message":"项目不存在"}``。
    """
    for path in ("/api/not-found", "/api/forbidden", "/api/conflict-dict"):
        body = (await client.get(path)).json()
        assert "detail" not in body, f"{path} 开始输出 detail 了，请同步评估前端信封适配"
        assert set(body.keys()) == {"code", "message"}


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
