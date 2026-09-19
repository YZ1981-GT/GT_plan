"""ZipAssembler / ZipReader — 组装与解析 Bulk ZIP。

ZipAssembler：内存组装 ZIP（write→finalize），自动计算 sha256。
ZipReader：解析上传 ZIP，校验 manifest.json 完整性、sha256、大小上限。

核心铁律：
  - ZIP SHALL NOT 包含任何密钥/Token（Req 6.3）
  - 单文件+总大小上限可配（Req 6.5）
  - 中文文件名用 UTF-8 编码存入 ZIP（RFC5987 Content-Disposition 属于路由层）
  - manifest.json 必须存在且可解析

Requirements: 1.4, 6.3, 6.5
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class ZipSizeLimitExceeded(Exception):
    """ZIP 大小超限（单文件或总大小）。

    Requirements: 6.5
    """

    def __init__(self, message: str = "ZIP 大小超限") -> None:
        super().__init__(message)


class ZipManifestMissing(Exception):
    """ZIP 中缺少 manifest.json。"""

    def __init__(self, message: str = "ZIP 中缺少 manifest.json") -> None:
        super().__init__(message)


class ZipIntegrityError(Exception):
    """ZIP 文件完整性校验失败（sha256 不匹配）。"""

    def __init__(self, message: str = "ZIP 文件完整性校验失败") -> None:
        super().__init__(message)


# ---------------------------------------------------------------------------
# Constants (configurable defaults)
# ---------------------------------------------------------------------------

DEFAULT_MAX_SINGLE_FILE_SIZE: int = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_TOTAL_ZIP_SIZE: int = 500 * 1024 * 1024  # 500 MB

# 敏感信息检测模式（Req 6.3）
_SENSITIVE_PATTERNS: list[str] = [
    "Bearer ",
    "Authorization:",
    "-----BEGIN",
    "-----END",
    "sk-",
    "aws_secret_access_key",
    "PRIVATE KEY",
]


# ---------------------------------------------------------------------------
# ZipAssembler
# ---------------------------------------------------------------------------


class ZipAssembler:
    """内存组装 ZIP，自动计算每个文件的 SHA256。

    Usage:
        assembler = ZipAssembler()
        sha = assembler.write("D/D2/D2-2_明细表_模板.xlsx", xlsx_bytes)
        assembler.set_manifest(manifest_dict)
        assembler.set_readme("使用说明...")
        zip_bytes_io = assembler.finalize()
    """

    def __init__(self) -> None:
        self._buffer = io.BytesIO()
        self._zf = zipfile.ZipFile(
            self._buffer, mode="w", compression=zipfile.ZIP_DEFLATED
        )
        self._sha256_map: dict[str, str] = {}
        self._finalized = False

    def write(self, zip_path: str, data: bytes) -> str:
        """向 ZIP 添加一个文件，返回其 SHA256 hex。

        Args:
            zip_path: ZIP 内路径（UTF-8 中文安全）。
            data: 文件字节。

        Returns:
            该文件的 sha256 hex digest。

        Raises:
            RuntimeError: 已 finalize 后再 write。
        """
        if self._finalized:
            raise RuntimeError("ZipAssembler 已 finalize，不可再 write")

        sha256_hex = hashlib.sha256(data).hexdigest()
        self._sha256_map[zip_path] = sha256_hex

        # UTF-8 文件名写入
        self._zf.writestr(zip_path, data)
        return sha256_hex

    def set_manifest(self, manifest_dict: dict[str, Any]) -> None:
        """序列化 manifest dict 为 JSON 并写入 ZIP 根目录。

        Args:
            manifest_dict: manifest 数据字典。
        """
        if self._finalized:
            raise RuntimeError("ZipAssembler 已 finalize，不可再写入")

        manifest_json = json.dumps(
            manifest_dict, ensure_ascii=False, indent=2
        ).encode("utf-8")
        self._zf.writestr("manifest.json", manifest_json)

    def set_readme(self, text: str) -> None:
        """写入 README.txt 到 ZIP 根目录。

        Args:
            text: README 文本内容。
        """
        if self._finalized:
            raise RuntimeError("ZipAssembler 已 finalize，不可再写入")

        self._zf.writestr("README.txt", text.encode("utf-8"))

    @property
    def sha256_map(self) -> dict[str, str]:
        """已写入文件的 zip_path → sha256 映射（不含 manifest/README）。"""
        return dict(self._sha256_map)

    def finalize(self) -> io.BytesIO:
        """关闭 ZIP 并返回完整字节流。

        Returns:
            BytesIO 对象（seek(0) 就绪）。

        Raises:
            RuntimeError: 重复 finalize。
        """
        if self._finalized:
            raise RuntimeError("ZipAssembler 已 finalize，不可重复调用")

        self._finalized = True
        self._zf.close()
        self._buffer.seek(0)
        return self._buffer


# ---------------------------------------------------------------------------
# ZipReader
# ---------------------------------------------------------------------------


class ZipReader:
    """解析上传 ZIP，校验 manifest、sha256、大小上限。

    Usage:
        reader = ZipReader.from_bytes(zip_bytes)
        manifest = reader.manifest
        xlsx = reader.get_file("D/D2/D2-2_明细表_数据.xlsx")
    """

    def __init__(
        self,
        zf: zipfile.ZipFile,
        buffer: io.BytesIO,
        manifest_dict: dict[str, Any],
        *,
        max_single_file_size: int = DEFAULT_MAX_SINGLE_FILE_SIZE,
        max_total_zip_size: int = DEFAULT_MAX_TOTAL_ZIP_SIZE,
    ) -> None:
        self._zf = zf
        self._buffer = buffer
        self._manifest_dict = manifest_dict
        self._max_single_file_size = max_single_file_size
        self._max_total_zip_size = max_total_zip_size

    @classmethod
    def from_bytes(
        cls,
        zip_bytes: bytes,
        *,
        max_single_file_size: int = DEFAULT_MAX_SINGLE_FILE_SIZE,
        max_total_zip_size: int = DEFAULT_MAX_TOTAL_ZIP_SIZE,
    ) -> "ZipReader":
        """从字节流创建 ZipReader 实例，执行基础校验。

        Args:
            zip_bytes: ZIP 文件字节流。
            max_single_file_size: 单文件大小上限（字节）。
            max_total_zip_size: ZIP 总解压大小上限（字节）。

        Returns:
            ZipReader 实例。

        Raises:
            ZipSizeLimitExceeded: ZIP 总大小超限。
            ZipManifestMissing: manifest.json 不存在或不可解析。
            zipfile.BadZipFile: 非合法 ZIP。
        """
        # 总 ZIP 字节流大小校验（压缩态）
        if len(zip_bytes) > max_total_zip_size:
            raise ZipSizeLimitExceeded(
                f"ZIP 文件大小 ({len(zip_bytes)} bytes) 超过上限 "
                f"({max_total_zip_size} bytes)"
            )

        buf = io.BytesIO(zip_bytes)
        zf = zipfile.ZipFile(buf, mode="r")

        # 校验解压后总大小上限
        total_uncompressed = sum(info.file_size for info in zf.infolist())
        if total_uncompressed > max_total_zip_size:
            zf.close()
            raise ZipSizeLimitExceeded(
                f"ZIP 解压后总大小 ({total_uncompressed} bytes) 超过上限 "
                f"({max_total_zip_size} bytes)"
            )

        # 校验单文件大小上限
        for info in zf.infolist():
            if info.file_size > max_single_file_size:
                zf.close()
                raise ZipSizeLimitExceeded(
                    f"文件 '{info.filename}' 大小 ({info.file_size} bytes) "
                    f"超过单文件上限 ({max_single_file_size} bytes)"
                )

        # 校验 manifest.json 存在
        if "manifest.json" not in zf.namelist():
            zf.close()
            raise ZipManifestMissing("ZIP 中缺少 manifest.json")

        # 解析 manifest.json
        try:
            manifest_raw = zf.read("manifest.json")
            manifest_dict = json.loads(manifest_raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            zf.close()
            raise ZipManifestMissing(
                f"manifest.json 解析失败: {e}"
            ) from e

        return cls(
            zf=zf,
            buffer=buf,
            manifest_dict=manifest_dict,
            max_single_file_size=max_single_file_size,
            max_total_zip_size=max_total_zip_size,
        )

    @property
    def manifest(self) -> dict[str, Any]:
        """返回解析后的 manifest 字典。"""
        return self._manifest_dict

    def get_file(self, zip_path: str) -> bytes:
        """提取 ZIP 中指定路径的文件内容。

        Args:
            zip_path: ZIP 内文件路径。

        Returns:
            文件字节内容。

        Raises:
            KeyError: 文件不存在于 ZIP 中。
        """
        if zip_path not in self._zf.namelist():
            raise KeyError(f"ZIP 中不存在文件: {zip_path}")
        return self._zf.read(zip_path)

    def list_files(self) -> list[str]:
        """返回 ZIP 内所有文件路径。"""
        return self._zf.namelist()

    def verify_integrity(self) -> list[str]:
        """校验 manifest 中每个文件的 SHA256 完整性。

        遍历 manifest.files[]，对每个有 sha256 字段的条目：
        1. 检查对应 zip_path 文件存在
        2. 校验 sha256 匹配

        Returns:
            校验失败的文件列表（空列表=全部通过）。

        Raises:
            ZipIntegrityError: 如果有文件校验失败。
        """
        files = self._manifest_dict.get("files", [])
        failed: list[str] = []

        for entry in files:
            zip_path = entry.get("zip_path", "")
            expected_sha256 = entry.get("sha256", "")

            if not zip_path or not expected_sha256:
                continue

            if zip_path not in self._zf.namelist():
                failed.append(f"{zip_path}: 文件不存在")
                continue

            actual_data = self._zf.read(zip_path)
            actual_sha256 = hashlib.sha256(actual_data).hexdigest()

            if actual_sha256 != expected_sha256:
                failed.append(
                    f"{zip_path}: sha256 不匹配 "
                    f"(期望={expected_sha256[:16]}…, "
                    f"实际={actual_sha256[:16]}…)"
                )

        if failed:
            raise ZipIntegrityError(
                f"SHA256 完整性校验失败 ({len(failed)} 个文件): "
                + "; ".join(failed[:5])
            )

        return failed

    def close(self) -> None:
        """关闭内部 ZipFile。"""
        self._zf.close()


# ---------------------------------------------------------------------------
# Helper: 检测敏感信息 (Req 6.3)
# ---------------------------------------------------------------------------


def check_no_secrets(data: bytes, filename: str = "") -> None:
    """检查字节数据中是否含有敏感信息模式。

    对文本类文件（manifest.json / README.txt）做字符串检测。
    对 xlsx 二进制文件不做检测（二进制中不会明文存 token）。

    Args:
        data: 文件内容字节。
        filename: 文件名（用于日志）。

    Raises:
        ValueError: 检测到敏感信息模式。
    """
    # 仅对文本文件检测
    if not filename.endswith((".json", ".txt", ".md", ".csv")):
        return

    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return

    for pattern in _SENSITIVE_PATTERNS:
        if pattern in text:
            raise ValueError(
                f"ZIP 文件 '{filename}' 中检测到敏感信息模式 "
                f"(匹配: '{pattern}')"
            )
