"""Tests for SC-3 文件上传病毒扫描服务 (ClamAV 集成)

验证：
1. CLAMAV_ENABLED=False 时跳过扫描，返回 clean=True, scanned=False
2. ClamAV 不可用时降级为跳过（不崩溃）
3. clamd 未安装时降级为跳过
4. ClamAV 可用且检测到威胁时返回 clean=False
5. ClamAV 可用且文件安全时返回 clean=True, scanned=True
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_scan_disabled_returns_clean_not_scanned():
    """CLAMAV_ENABLED=False 时，直接跳过扫描"""
    import app.services.file_scan_service as fsm

    with patch.object(fsm, "settings") as mock_settings:
        mock_settings.CLAMAV_ENABLED = False

        result = await fsm.scan_file(b"test content", "test.pdf")

        assert result["clean"] is True
        assert result["threat"] is None
        assert result["scanned"] is False


@pytest.mark.asyncio
async def test_scan_enabled_but_clamd_not_installed():
    """CLAMAV_ENABLED=True 但 clamd 包未安装时降级"""
    import app.services.file_scan_service as fsm

    with patch.object(fsm, "settings") as mock_settings:
        mock_settings.CLAMAV_ENABLED = True
        mock_settings.CLAMAV_HOST = "localhost"
        mock_settings.CLAMAV_PORT = 3310

        # 模拟 clamd 未安装：移除 sys.modules 中的 clamd 并让 import 失败
        mock_clamd = MagicMock()
        mock_clamd.ClamdNetworkSocket.side_effect = ImportError("No module named 'clamd'")

        # 直接让 import clamd 抛 ImportError
        import sys
        original = sys.modules.get("clamd")
        sys.modules["clamd"] = None  # type: ignore[assignment]
        try:
            result = await fsm.scan_file(b"test content", "test.pdf")
            assert result["clean"] is True
            assert result["threat"] is None
            assert result["scanned"] is False
        finally:
            if original is not None:
                sys.modules["clamd"] = original
            else:
                sys.modules.pop("clamd", None)


@pytest.mark.asyncio
async def test_scan_enabled_but_clamav_unavailable():
    """CLAMAV_ENABLED=True 但 ClamAV 服务不可达时降级"""
    mock_clamd_module = MagicMock()
    mock_socket = MagicMock()
    mock_socket.instream.side_effect = ConnectionRefusedError("Connection refused")
    mock_clamd_module.ClamdNetworkSocket.return_value = mock_socket

    import app.services.file_scan_service as fsm

    with patch.object(fsm, "settings") as mock_settings:
        mock_settings.CLAMAV_ENABLED = True
        mock_settings.CLAMAV_HOST = "localhost"
        mock_settings.CLAMAV_PORT = 3310

        with patch.dict("sys.modules", {"clamd": mock_clamd_module}):
            result = await fsm.scan_file(b"test content", "test.pdf")

            assert result["clean"] is True
            assert result["threat"] is None
            assert result["scanned"] is False


@pytest.mark.asyncio
async def test_scan_detects_threat():
    """ClamAV 检测到威胁时返回 clean=False"""
    mock_clamd_module = MagicMock()
    mock_socket = MagicMock()
    mock_socket.instream.return_value = {"stream": ("FOUND", "Eicar-Test-Signature")}
    mock_clamd_module.ClamdNetworkSocket.return_value = mock_socket

    import app.services.file_scan_service as fsm

    with patch.object(fsm, "settings") as mock_settings:
        mock_settings.CLAMAV_ENABLED = True
        mock_settings.CLAMAV_HOST = "localhost"
        mock_settings.CLAMAV_PORT = 3310

        with patch.dict("sys.modules", {"clamd": mock_clamd_module}):
            result = await fsm.scan_file(b"X5O!P%@AP[4\\PZX", "eicar.com")

            assert result["clean"] is False
            assert result["threat"] == "Eicar-Test-Signature"
            assert result["scanned"] is True


@pytest.mark.asyncio
async def test_scan_clean_file():
    """ClamAV 扫描通过时返回 clean=True, scanned=True"""
    mock_clamd_module = MagicMock()
    mock_socket = MagicMock()
    mock_socket.instream.return_value = {"stream": ("OK", None)}
    mock_clamd_module.ClamdNetworkSocket.return_value = mock_socket

    import app.services.file_scan_service as fsm

    with patch.object(fsm, "settings") as mock_settings:
        mock_settings.CLAMAV_ENABLED = True
        mock_settings.CLAMAV_HOST = "localhost"
        mock_settings.CLAMAV_PORT = 3310

        with patch.dict("sys.modules", {"clamd": mock_clamd_module}):
            result = await fsm.scan_file(b"normal file content", "report.pdf")

            assert result["clean"] is True
            assert result["threat"] is None
            assert result["scanned"] is True


@pytest.mark.asyncio
async def test_scan_result_type_structure():
    """验证返回值结构符合 ScanResult TypedDict"""
    import app.services.file_scan_service as fsm

    with patch.object(fsm, "settings") as mock_settings:
        mock_settings.CLAMAV_ENABLED = False

        result = await fsm.scan_file(b"data", "file.xlsx")

        # 必须包含这三个 key
        assert "clean" in result
        assert "threat" in result
        assert "scanned" in result
        # 类型正确
        assert isinstance(result["clean"], bool)
        assert isinstance(result["scanned"], bool)
