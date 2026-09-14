"""Tests: OCR Service Extraction

验证：
1. HTTP 调用路径正常工作（mock server）
2. HTTP 超时/错误 → OCRServiceUnavailableError（503）
3. OCR_SERVICE_URL 配置时不加载 PaddleOCR（web worker 内存保护）
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.unified_ocr_service import (
    OCREngine,
    OCRServiceUnavailableError,
    UnifiedOCRService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ocr_service():
    """创建 OCR 服务实例"""
    svc = UnifiedOCRService()
    return svc


@pytest.fixture
def temp_image():
    """创建临时测试图片文件"""
    # 1x1 PNG
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
        b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
        b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(png_data)
        path = f.name
    yield path
    os.unlink(path)


# ---------------------------------------------------------------------------
# Test: HTTP call path
# ---------------------------------------------------------------------------

class TestHTTPCallPath:
    """OCR_SERVICE_URL 配置时走 HTTP 路径"""

    @pytest.mark.asyncio
    async def test_http_recognize_success(self, ocr_service, temp_image):
        """HTTP 调用成功 → 返回 OCR 结果"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "text": "测试文本",
            "engine": "paddle",
            "regions": [{"text": "测试文本", "box": [[0, 0], [1, 0], [1, 1], [0, 1]], "confidence": 0.95}],
        }

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", "http://localhost:9990"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                result = await ocr_service._http_recognize(temp_image)

        assert result["text"] == "测试文本"
        assert result["engine"] == "paddle"
        assert len(result["regions"]) == 1

    @pytest.mark.asyncio
    async def test_http_timeout_raises_503(self, ocr_service, temp_image):
        """HTTP 超时 → 抛出 OCRServiceUnavailableError"""
        import httpx

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", "http://localhost:9990"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
                mock_client_cls.return_value = mock_client

                with pytest.raises(OCRServiceUnavailableError, match="超时"):
                    await ocr_service._http_recognize(temp_image)

    @pytest.mark.asyncio
    async def test_http_connect_error_raises_503(self, ocr_service, temp_image):
        """HTTP 连接失败 → 抛出 OCRServiceUnavailableError"""
        import httpx

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", "http://localhost:9990"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
                mock_client_cls.return_value = mock_client

                with pytest.raises(OCRServiceUnavailableError, match="连接失败"):
                    await ocr_service._http_recognize(temp_image)

    @pytest.mark.asyncio
    async def test_http_500_raises_503(self, ocr_service, temp_image):
        """OCR 服务返回 500 → 抛出 OCRServiceUnavailableError"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", "http://localhost:9990"):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.post = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                with pytest.raises(OCRServiceUnavailableError, match="HTTP 500"):
                    await ocr_service._http_recognize(temp_image)


# ---------------------------------------------------------------------------
# Test: Web worker memory protection
# ---------------------------------------------------------------------------

class TestWebWorkerMemory:
    """OCR_SERVICE_URL 配置时不加载 PaddleOCR"""

    def test_paddle_not_loaded_when_service_url_set(self):
        """配置 OCR_SERVICE_URL 时 _check_paddle_available 返回 False"""
        svc = UnifiedOCRService()
        svc._paddle_available = None  # reset

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", "http://ocr:9990"):
            result = svc._check_paddle_available()

        assert result is False

    def test_tesseract_not_loaded_when_service_url_set(self):
        """配置 OCR_SERVICE_URL 时 _check_tesseract_available 返回 False"""
        svc = UnifiedOCRService()
        svc._tesseract_available = None  # reset

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", "http://ocr:9990"):
            result = svc._check_tesseract_available()

        assert result is False

    @pytest.mark.asyncio
    async def test_recognize_uses_http_when_service_url_set(self, temp_image):
        """recognize() 在配置 OCR_SERVICE_URL 时走 HTTP 而非 in-process"""
        svc = UnifiedOCRService()
        http_called = False

        async def mock_http_recognize(image_path, mode=OCREngine.AUTO):
            nonlocal http_called
            http_called = True
            return {"text": "http_result", "engine": "paddle", "regions": []}

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", "http://ocr:9990"):
            with patch.object(svc, '_http_recognize', side_effect=mock_http_recognize):
                result = await svc.recognize(temp_image)

        assert http_called is True
        assert result["text"] == "http_result"


# ---------------------------------------------------------------------------
# Test: Fallback behavior
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    """OCR_SERVICE_URL 未配置时走 in-process fallback"""

    @pytest.mark.asyncio
    async def test_in_process_when_no_service_url(self, ocr_service, temp_image):
        """未配置 OCR_SERVICE_URL → 走 in-process 路径"""
        in_process_called = False

        async def mock_in_process(image_path, mode):
            nonlocal in_process_called
            in_process_called = True
            return {"text": "local", "engine": "tesseract", "regions": []}

        with patch("app.services.unified_ocr_service.OCR_SERVICE_URL", ""):
            with patch.object(ocr_service, '_in_process_recognize', side_effect=mock_in_process):
                result = await ocr_service.recognize(temp_image)

        assert in_process_called is True
        assert result["text"] == "local"
