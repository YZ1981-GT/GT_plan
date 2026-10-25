"""统一文件指纹校验 — phase4 交付中心 fail-closed 基础设施

提供两个核心函数：
- ``compute_file_fingerprint(path)`` — 分块读取，返回 size + sha256
- ``verify_file_fingerprint(version)`` — 比较 DB 记录 vs 磁盘文件

以及 ``render_and_store_fail_closed`` 四阶段版本创建流程。

版本复用、readiness 和下载都共享 ``verify_file_fingerprint``。
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# 分块大小 256 KB
_CHUNK_SIZE = 256 * 1024

# 交付物根目录 — 指纹校验时路径必须落在此目录下
DELIVERY_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage")) / "deliverables"


# ── 异常体系 ──────────────────────────────────────────────────────────

class FileFingerprintError(Exception):
    """文件指纹校验基类异常"""

    def __init__(self, message: str, *, stage: str = "", path: str = ""):
        self.stage = stage
        self.path = path
        super().__init__(message)


class FileNotFoundOnDisk(FileFingerprintError):
    """版本记录引用的文件在磁盘上不存在"""


class FileNotReadable(FileFingerprintError):
    """版本记录引用的文件不可读"""


class FileEmptyError(FileFingerprintError):
    """文件大小为零"""


class FileSizeMismatch(FileFingerprintError):
    """文件大小与数据库记录不一致"""


class FileHashMismatch(FileFingerprintError):
    """文件 SHA-256 与数据库记录不一致"""


class FilePersistError(FileFingerprintError):
    """文件落盘阶段失败（生成/写入/移动）"""


class PathOutsideDeliveryRoot(FileFingerprintError):
    """路径不在配置的交付根目录下"""


# ── 数据结构 ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FileFingerprint:
    """不可变文件指纹"""
    size: int
    sha256: str


# ── 核心函数 ──────────────────────────────────────────────────────────

def compute_file_fingerprint(
    path: Path,
    *,
    delivery_root: Path | None = None,
) -> FileFingerprint:
    """对最终落盘文件计算 SHA-256 和字节大小。

    采用分块读取，不一次性 read_bytes() 整个文件。
    路径必须是已存在、可读、非空的普通文件。

    Args:
        path: 文件路径
        delivery_root: 交付根目录（默认 DELIVERY_ROOT）

    Raises:
        FileNotFoundOnDisk: 文件不存在
        FileNotReadable: 不可读
        FileEmptyError: 大小为零
        PathOutsideDeliveryRoot: 路径不在交付根目录下
    """
    _assert_within_delivery_root(path, delivery_root=delivery_root)
    _assert_file_accessible(path)

    hasher = hashlib.sha256()
    file_size = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
            file_size += len(chunk)

    if file_size == 0:
        raise FileEmptyError(
            f"文件大小为零: {path}",
            stage="fingerprint",
            path=str(path),
        )

    return FileFingerprint(size=file_size, sha256=hasher.hexdigest())


def verify_file_fingerprint(
    *,
    file_path: str | None,
    expected_size: int | None,
    expected_sha256: str | None,
    delivery_root: Path | None = None,
) -> FileFingerprint:
    """验证数据库版本记录与磁盘文件一致。

    版本复用、readiness 和下载接口都调用此函数。

    Returns:
        FileFingerprint — 当前磁盘文件的真实指纹

    Raises:
        FileNotFoundOnDisk: file_path 为 None 或文件不存在
        FileNotReadable: 不可读
        FileEmptyError: 大小为零
        FileSizeMismatch: 大小不一致
        FileHashMismatch: SHA-256 不一致
    """
    if not file_path:
        raise FileNotFoundOnDisk(
            "版本记录未绑定文件路径",
            stage="verify",
            path="",
        )

    path = Path(file_path)
    fp = compute_file_fingerprint(path, delivery_root=delivery_root)

    if expected_size is not None and fp.size != expected_size:
        raise FileSizeMismatch(
            f"文件大小不一致: 记录 {expected_size} 字节, 实际 {fp.size} 字节",
            stage="verify",
            path=str(path),
        )

    if expected_sha256 is not None and fp.sha256 != expected_sha256:
        raise FileHashMismatch(
            f"文件指纹不一致: 记录 {expected_sha256[:16]}…, 实际 {fp.sha256[:16]}…",
            stage="verify",
            path=str(path),
        )

    return fp


# ── 四阶段落盘 ────────────────────────────────────────────────────────

def persist_file_fail_closed(
    content: bytes,
    final_path: Path,
    *,
    delivery_root: Path | None = None,
) -> FileFingerprint:
    """四阶段 fail-closed 文件落盘。

    阶段 1: 在唯一临时路径写入文件
    阶段 2: 原子移动到最终存储路径（同 fs 时 rename，跨 fs 时 copy+delete）
    阶段 3: 对最终路径执行 is_file、可读、st_size > 0、SHA-256
    阶段 4: 返回 FileFingerprint（由调用方创建版本并绑定指纹）

    失败时清理本次临时/最终文件，不删除旧有效版本。
    抛出带阶段和路径的异常，调用方不应创建版本。

    Args:
        content: 文件字节内容
        final_path: 最终落盘路径
        delivery_root: 校验根目录（默认 DELIVERY_ROOT）

    Returns:
        FileFingerprint — 最终落盘文件的指纹

    Raises:
        FilePersistError: 写入/移动阶段失败
        FileNotFoundOnDisk/FileNotReadable/FileEmptyError: 校验阶段失败
    """
    root = delivery_root or DELIVERY_ROOT

    if not content:
        raise FilePersistError(
            "无文件内容可存储",
            stage="generate",
            path=str(final_path),
        )

    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = None

    try:
        # ── 阶段 1: 写临时文件 ──
        fd, tmp_str = tempfile.mkstemp(
            dir=str(final_path.parent),
            prefix=".phase4_",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_str)
        try:
            os.write(fd, content)
            os.fsync(fd)
        finally:
            os.close(fd)

        # ── 阶段 2: 原子移动 ──
        try:
            shutil.move(str(tmp_path), str(final_path))
            tmp_path = None  # 移动成功，临时文件已不存在
        except Exception as exc:
            raise FilePersistError(
                f"文件移动失败: {exc}",
                stage="move",
                path=str(final_path),
            ) from exc

        # ── 阶段 3: 校验最终文件 ──
        fp = compute_file_fingerprint(final_path, delivery_root=root)
        return fp

    except FileFingerprintError:
        # 已经是业务异常，清理后向上传播
        _cleanup_attempt_files(tmp_path, final_path)
        raise
    except Exception as exc:
        _cleanup_attempt_files(tmp_path, final_path)
        raise FilePersistError(
            f"文件落盘失败: {exc}",
            stage="write",
            path=str(final_path),
        ) from exc


# ── 内部工具 ──────────────────────────────────────────────────────────

def _assert_within_delivery_root(path: Path, *, delivery_root: Path | None = None) -> None:
    """校验路径在交付根目录下（防止版本记录指向任意文件）"""
    root = delivery_root or DELIVERY_ROOT
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (ValueError, OSError):
        raise PathOutsideDeliveryRoot(
            f"路径不在交付根目录下: {path}",
            stage="path_check",
            path=str(path),
        )


def _assert_file_accessible(path: Path) -> None:
    """校验文件存在、是普通文件、可读"""
    if not path.exists():
        raise FileNotFoundOnDisk(
            f"文件不存在: {path}",
            stage="verify",
            path=str(path),
        )
    if not path.is_file():
        raise FileNotFoundOnDisk(
            f"路径不是普通文件: {path}",
            stage="verify",
            path=str(path),
        )
    if not os.access(path, os.R_OK):
        raise FileNotReadable(
            f"文件不可读: {path}",
            stage="verify",
            path=str(path),
        )
    if path.stat().st_size == 0:
        raise FileEmptyError(
            f"文件大小为零: {path}",
            stage="verify",
            path=str(path),
        )


def _cleanup_attempt_files(
    tmp_path: Path | None,
    final_path: Path | None,
) -> None:
    """清理本次 attempt 产生的临时/最终文件。不删除旧有效版本。"""
    for p in (tmp_path, final_path):
        if p is not None:
            try:
                if p.exists():
                    p.unlink()
            except OSError:
                logger.warning("清理失败文件时异常: %s", p, exc_info=True)
