"""OCR 本机优先、服务器兜底（spec llm-ocr-local-first-routing，ADR-ROUTE-009）。

候选按能力槽（文字识别 / 版面解析）取已启用模型，本机在前；OCR 幂等，前序候选任何失败都换下一个，
最后一个失败才报错并逐个列出原因。路由解析在这里替换掉（不读库），``resolve_ocr_route`` 本身
另用 SQLite 建表验证。
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.ai_models import AIModelConfig, AIModelType, AIProvider


@pytest.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(AIModelConfig.__table__.create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------


def _remote_ocr_candidate(name="paddleocrv6", capability="ocr", deployment="server"):
    from app.services.remote_ocr_runtime import OCRRouteCandidate, RemoteOCRConfig

    config = RemoteOCRConfig(
        model_id=uuid4(), model_name=name, capability=capability, protocol="paddlex_json",
        endpoint_url="https://ai.gt-china.com.cn:10080",
        api_path="/ocr" if capability == "ocr" else "/layout-parsing",
        auth_scheme="none", auth_header_name=None, api_key=None,
        timeout_seconds=60, deployment=deployment,
    )
    return OCRRouteCandidate(capability, deployment, name, config.model_id, config)


def _local_ocr_candidate(capability="ocr"):
    from app.services.remote_ocr_runtime import OCRRouteCandidate

    return OCRRouteCandidate(capability, "local", "paddleocr", uuid4())


@pytest.fixture
def ocr_route(monkeypatch):
    """替换路由解析（不读库）并隔离冷却记录；``state["route"]`` 由用例设置。"""
    from app.services import remote_ocr_runtime as remote
    from app.services.llm_route import reset_route_health

    reset_route_health()
    state: dict = {"route": [], "capabilities": []}

    async def _route(capability, *, db=None):
        state["capabilities"].append(capability)
        return list(state["route"])

    monkeypatch.setattr(remote, "resolve_ocr_route", _route)
    yield state
    reset_route_health()


def _no_local_engines(svc):
    svc._paddle_available = False
    svc._tesseract_available = False
    svc._mineru_available = False
    return svc


_REMOTE_TEXT = {
    "text": "远程识别", "engine": "paddleocr_remote",
    "regions": [], "layout_blocks": [], "capability": "ocr",
}


@pytest.mark.asyncio
async def test_unified_ocr_uses_local_engine_first(monkeypatch, ocr_route):
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    server = _remote_ocr_candidate()
    ocr_route["route"] = [_local_ocr_candidate(), server]
    remote_call = AsyncMock(return_value=dict(_REMOTE_TEXT))
    monkeypatch.setattr("app.services.remote_ocr_runtime.recognize_remote_file", remote_call)
    svc = UnifiedOCRService()
    svc._local_recognize = AsyncMock(return_value={"text": "本机识别", "engine": "tesseract", "regions": []})

    result = await svc.recognize("evidence.png", OCREngine.AUTO)

    assert result["text"] == "本机识别"
    assert result["route"]["deployment"] == "local"
    assert result["route"]["fallback_used"] is False
    remote_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_unified_ocr_falls_back_to_server_when_local_engine_missing(monkeypatch, ocr_route):
    from app.services import unified_ocr_service as mod
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    server = _remote_ocr_candidate()
    ocr_route["route"] = [_local_ocr_candidate(), server]
    remote_call = AsyncMock(return_value=dict(_REMOTE_TEXT))
    monkeypatch.setattr("app.services.remote_ocr_runtime.recognize_remote_file", remote_call)
    monkeypatch.setattr(mod, "OCR_SERVICE_URL", "")

    result = await _no_local_engines(UnifiedOCRService()).recognize("evidence.png", OCREngine.AUTO)

    assert result["text"] == "远程识别"
    remote_call.assert_awaited_once_with(server.config, "evidence.png")
    assert result["route"]["deployment"] == "server"
    assert result["route"]["model_name"] == "paddleocrv6"
    assert result["route"]["fallback_used"] is True
    assert any("没有可用的本机 OCR 引擎" in note for note in result["route"]["attempts"])
    assert ocr_route["capabilities"] == ["ocr"]


@pytest.mark.asyncio
async def test_unified_ocr_falls_back_when_local_recognition_fails(monkeypatch, ocr_route):
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    ocr_route["route"] = [_local_ocr_candidate(), _remote_ocr_candidate()]
    remote_call = AsyncMock(return_value=dict(_REMOTE_TEXT))
    monkeypatch.setattr("app.services.remote_ocr_runtime.recognize_remote_file", remote_call)
    svc = UnifiedOCRService()
    svc._local_recognize = AsyncMock(side_effect=RuntimeError("PaddleOCR 推理崩溃"))

    result = await svc.recognize("evidence.png", OCREngine.AUTO)

    assert result["route"]["fallback_used"] is True
    assert result["route"]["attempts"] == ["本机 OCR 引擎：PaddleOCR 推理崩溃"]
    remote_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_unified_ocr_reports_every_candidate_when_all_fail(monkeypatch, ocr_route):
    from app.services.llm_route import is_cooling
    from app.services.remote_ocr_runtime import RemoteOCRRuntimeError
    from app.services.unified_ocr_service import (
        OCREngine,
        OCRServiceUnavailableError,
        UnifiedOCRService,
    )

    server = _remote_ocr_candidate()
    ocr_route["route"] = [_local_ocr_candidate(), server]
    monkeypatch.setattr(
        "app.services.remote_ocr_runtime.recognize_remote_file",
        AsyncMock(side_effect=RemoteOCRRuntimeError("ocr_unreachable", "远程 OCR 不可达", kind="unavailable")),
    )
    svc = UnifiedOCRService()
    svc._local_recognize = AsyncMock(side_effect=RuntimeError("没有可用的本机 OCR 引擎"))

    with pytest.raises(OCRServiceUnavailableError) as caught:
        await svc.recognize("evidence.png", OCREngine.AUTO)

    message = str(caught.value)
    assert "本机 OCR 引擎：没有可用的本机 OCR 引擎" in message
    assert "服务器 OCR「paddleocrv6」：远程 OCR 不可达" in message
    assert is_cooling(server.identity)


@pytest.mark.asyncio
async def test_unified_ocr_skips_cooling_server_but_names_it(monkeypatch, ocr_route):
    from app.services.llm_route import mark_unavailable
    from app.services.unified_ocr_service import (
        OCREngine,
        OCRServiceUnavailableError,
        UnifiedOCRService,
    )

    server = _remote_ocr_candidate()
    ocr_route["route"] = [_local_ocr_candidate(), server]
    mark_unavailable(server.identity, "远程 OCR 不可达")
    remote_call = AsyncMock(return_value=dict(_REMOTE_TEXT))
    monkeypatch.setattr("app.services.remote_ocr_runtime.recognize_remote_file", remote_call)
    svc = UnifiedOCRService()
    svc._local_recognize = AsyncMock(side_effect=RuntimeError("没有可用的本机 OCR 引擎"))

    with pytest.raises(OCRServiceUnavailableError, match="冷却中（远程 OCR 不可达）"):
        await svc.recognize("evidence.png", OCREngine.AUTO)
    remote_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_unified_ocr_single_candidate_keeps_original_reason(monkeypatch, ocr_route):
    from app.services import unified_ocr_service as mod
    from app.services.unified_ocr_service import (
        OCREngine,
        OCRServiceUnavailableError,
        UnifiedOCRService,
    )
    from app.services.remote_ocr_runtime import OCRRouteCandidate

    ocr_route["route"] = [OCRRouteCandidate("ocr", "local", "本机 OCR 引擎", implicit=True)]
    monkeypatch.setattr(mod, "OCR_SERVICE_URL", "")

    with pytest.raises(OCRServiceUnavailableError) as caught:
        await _no_local_engines(UnifiedOCRService()).recognize("evidence.png", OCREngine.AUTO)
    assert str(caught.value).startswith("没有可用的本机 OCR 引擎")


@pytest.mark.asyncio
async def test_unified_ocr_layout_without_enabled_row_is_unconfigured(monkeypatch, ocr_route):
    from app.services.unified_ocr_service import (
        OCREngine,
        OCRServiceUnavailableError,
        UnifiedOCRService,
    )

    ocr_route["route"] = []
    svc = UnifiedOCRService()
    svc._local_recognize = AsyncMock()

    with pytest.raises(OCRServiceUnavailableError, match="未配置已启用的版面解析模型"):
        await svc.recognize("report.pdf", OCREngine.LAYOUT_PARSING)
    assert ocr_route["capabilities"] == ["layout_parsing"]
    svc._local_recognize.assert_not_awaited()


@pytest.mark.asyncio
async def test_unified_ocr_layout_uses_layout_slot(monkeypatch, ocr_route):
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    layout = _remote_ocr_candidate("paddleocrvl-1.6", capability="layout_parsing")
    ocr_route["route"] = [layout]
    remote_call = AsyncMock(return_value={"text": "版面", "engine": "paddleocr_remote", "regions": []})
    monkeypatch.setattr("app.services.remote_ocr_runtime.recognize_remote_file", remote_call)

    result = await UnifiedOCRService().recognize("report.pdf", OCREngine.LAYOUT_PARSING)

    remote_call.assert_awaited_once_with(layout.config, "report.pdf")
    assert result["route"] == {
        "deployment": "server", "model_name": "paddleocrvl-1.6",
        "fallback_used": False, "attempts": [],
    }


@pytest.mark.asyncio
async def test_unified_ocr_missing_file_does_not_fail_over(monkeypatch, ocr_route):
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    ocr_route["route"] = [_local_ocr_candidate(), _remote_ocr_candidate()]
    remote_call = AsyncMock(return_value=dict(_REMOTE_TEXT))
    monkeypatch.setattr("app.services.remote_ocr_runtime.recognize_remote_file", remote_call)
    svc = UnifiedOCRService()
    svc._local_recognize = AsyncMock(side_effect=FileNotFoundError("evidence.png"))

    with pytest.raises(FileNotFoundError):
        await svc.recognize("evidence.png", OCREngine.AUTO)
    remote_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_unified_ocr_forced_local_engine_skips_route(ocr_route):
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    svc = UnifiedOCRService()
    svc._local_recognize = AsyncMock(return_value={"text": "t", "engine": "tesseract", "regions": []})

    await svc.recognize("evidence.png", OCREngine.TESSERACT)

    svc._local_recognize.assert_awaited_once_with("evidence.png", OCREngine.TESSERACT)
    assert ocr_route["capabilities"] == []


@pytest.mark.asyncio
async def test_resolve_ocr_route_orders_local_first(session_factory):
    from app.services.remote_ocr_runtime import resolve_ocr_route

    async with session_factory() as db:
        assert [c.implicit for c in await resolve_ocr_route("ocr", db=db)] == [True]
        assert await resolve_ocr_route("layout_parsing", db=db) == []
        db.add_all([
            AIModelConfig(
                model_name="paddleocrv6", model_type=AIModelType.ocr,
                provider=AIProvider.paddleocr, endpoint_url="https://ai.gt-china.com.cn:10080",
                ocr_capability="ocr", ocr_protocol="paddlex_json", api_path="/ocr",
                auth_scheme="none", deployment="server", is_active=True, is_deleted=False,
            ),
            AIModelConfig(
                model_name="paddleocr", model_type=AIModelType.ocr,
                provider=AIProvider.paddleocr, ocr_capability="ocr", ocr_protocol="local",
                auth_scheme="none", deployment="local", is_active=True, is_deleted=False,
            ),
            AIModelConfig(
                model_name="paddleocrvl-1.6", model_type=AIModelType.ocr,
                provider=AIProvider.paddleocr, endpoint_url="https://ai.gt-china.com.cn:10080",
                ocr_capability="layout_parsing", ocr_protocol="paddlex_json",
                api_path="/layout-parsing", auth_scheme="bearer", deployment="server",
                is_active=True, is_deleted=False,
            ),
        ])
        await db.commit()
        text_route = await resolve_ocr_route("ocr", db=db)
        layout_route = await resolve_ocr_route("layout_parsing", db=db)

    assert [(c.deployment, c.model_name, c.local_engine) for c in text_route] == [
        ("local", "paddleocr", True), ("server", "paddleocrv6", False),
    ]
    # 缺 Key 的服务器行仍作为候选出现（执行时按失败处理并给出原因），不会被静默丢弃
    assert len(layout_route) == 1 and layout_route[0].config is None
    assert layout_route[0].error is not None and layout_route[0].error.code == "api_key_required"
    assert layout_route[0].label == "服务器 OCR「paddleocrvl-1.6」"
