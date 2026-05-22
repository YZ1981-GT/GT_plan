"""文件上传病毒扫描服务

集成 ClamAV（通过 clamd TCP 连接）。
当 ClamAV 不可用时降级为跳过扫描（记录 warning 日志）。

配置（通过环境变量或 .env）：
  CLAMAV_ENABLED=false (默认关闭)
  CLAMAV_HOST=localhost
  CLAMAV_PORT=3310

使用方式：
  from app.services.file_scan_service import scan_file
  result = await scan_file(file_content, filename)
  if not result["clean"]:
      raise HTTPException(400, f"文件包含威胁: {result['threat']}")
"""

from __future__ import annotations

import io
import logging
from typing import TypedDict

from app.core.config import settings

logger = logging.getLogger(__name__)


class ScanResult(TypedDict):
    """扫描结果类型"""
    clean: bool       # True = 文件安全（或未扫描）
    threat: str | None  # 检测到的威胁名称
    scanned: bool     # True = 实际执行了扫描，False = 跳过


async def scan_file(file_content: bytes, filename: str) -> ScanResult:
    """扫描文件内容，返回扫描结果。

    当 ClamAV 未启用或不可用时，降级为跳过扫描（返回 clean=True, scanned=False）。
    这确保文件上传流程不会因扫描服务不可用而阻断。

    Args:
        file_content: 文件二进制内容
        filename: 文件名（用于日志记录）

    Returns:
        ScanResult: {"clean": bool, "threat": str|None, "scanned": bool}
    """
    if not getattr(settings, "CLAMAV_ENABLED", False):
        logger.debug("ClamAV disabled, skipping scan for %s", filename)
        return {"clean": True, "threat": None, "scanned": False}

    try:
        import clamd  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "clamd package not installed, skipping virus scan for %s. "
            "Install with: pip install pyclamd",
            filename,
        )
        return {"clean": True, "threat": None, "scanned": False}

    try:
        cd = clamd.ClamdNetworkSocket(
            host=getattr(settings, "CLAMAV_HOST", "localhost"),
            port=getattr(settings, "CLAMAV_PORT", 3310),
            timeout=30,
        )
        # 使用 instream 扫描内存中的文件内容
        result = cd.instream(io.BytesIO(file_content))
        # result 格式: {'stream': ('OK', None)} 或 {'stream': ('FOUND', 'Eicar-Test-Signature')}
        status = result.get("stream", ("OK", None))

        if status[0] == "FOUND":
            threat_name = status[1] if len(status) > 1 else "Unknown"
            logger.warning(
                "🚨 Threat detected in %s: %s",
                filename,
                threat_name,
            )
            return {"clean": False, "threat": threat_name, "scanned": True}

        logger.debug("File %s scanned clean by ClamAV", filename)
        return {"clean": True, "threat": None, "scanned": True}

    except Exception as e:
        # ClamAV 不可用时降级 — 不阻断上传流程
        logger.warning(
            "ClamAV unavailable, skipping scan for %s: %s",
            filename,
            str(e),
        )
        return {"clean": True, "threat": None, "scanned": False}
