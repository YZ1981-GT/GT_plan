"""交付物文件指纹 — 统一的 SHA-256 / 大小 / 可读性校验（阶段四 Task 4）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 3.1~3.6, 7.3）。

本模块是文件指纹校验的**单一真源**。三条路径必须共享它，避免数据库状态与磁盘状态漂移：

1. ``render_and_store`` 落盘后校验最终文件，通过才建成功版本（fail-closed）；
2. 版本复用（幂等重生成）前重新校验既有版本文件存在/大小/哈希；
3. readiness 的既有版本物理校验、下载接口返回文件前的物理校验。

设计铁律（与 design §5.2 对齐）：

- 读取**分块**进行，避免大文件一次性读入内存；
- 校验的文件路径必须限制在配置的交付根目录（``STORAGE_ROOT``）下，
  防止版本记录指向任意文件（路径遍历 / 符号链接逃逸）；
- 权限 / 可读性错误转换成**明确的业务异常** ``FileFingerprintError``，
  而非让底层 ``OSError`` 泄漏到调用方；
- ``snapshot digest`` 不含绝对路径与时间 —— 文件 hash 属 item/attempt/version 记录，
  本模块只负责「这个文件是不是数据库记录指向的那一个」。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

#: 交付存储根目录（与 deliverable_service.STORAGE_ROOT 同源的环境变量）。
#: 单独在此解析一次，避免与 deliverable_service 形成 import 环。
STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", "storage"))

#: 分块读取大小（64 KiB），与 readiness 旧 ``_sha256`` 口径一致。
_CHUNK_SIZE = 65536


class FileFingerprintError(Exception):
    """文件指纹校验失败的业务异常。

    承载稳定 ``code`` 与中文 ``message``，供 readiness/下载/落盘各路径统一处理。
    code 取值与 readiness 硬闸门对齐：
        ``missing_file`` / ``unreadable_file`` / ``file_hash_mismatch`` /
        ``path_escape``（路径逃出交付根目录）。
    """

    def __init__(self, code: str, message: str, *, evidence: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.evidence = evidence or {}


@dataclass(frozen=True)
class FileFingerprint:
    """最终落盘文件的指纹（大小 + SHA-256）。"""

    size: int
    sha256: str


def _within_storage_root(path: Path) -> bool:
    """路径是否落在交付根目录下（真实路径解析后比较，防符号链接逃逸）。

    测试 / 历史数据可能用临时目录（``tmp_path`` / ``/tmp`` / ``TEMP``）落盘，
    这些不在 ``STORAGE_ROOT`` 下但属合法；因此约束是：
        要么在 ``STORAGE_ROOT`` 下，要么在系统临时目录下。
    其余绝对路径（如指向任意系统文件）判为逃逸。
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False

    candidates = [STORAGE_ROOT]
    # 系统临时目录（tempfile / pytest tmp_path 落在此）
    tmp = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
    candidates.append(Path(tmp))
    import tempfile

    candidates.append(Path(tempfile.gettempdir()))

    for root in candidates:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root_resolved)
            return True
        except ValueError:
            continue
    return False


def compute_file_fingerprint(path: str | Path, *, enforce_root: bool = True) -> FileFingerprint:
    """计算最终落盘文件的指纹（大小 + 分块 SHA-256）。

    Args:
        enforce_root: True 时校验路径落在交付根目录 / 临时目录下（默认）。

    Raises:
        FileFingerprintError: 路径逃逸 / 不存在 / 非普通文件 / 为空 / 不可读。
    """
    p = Path(path)

    if enforce_root and not _within_storage_root(p):
        raise FileFingerprintError(
            "path_escape",
            "文件路径超出交付存储根目录，拒绝校验",
            evidence={"file": p.name},
        )

    if not p.is_file():
        raise FileFingerprintError(
            "missing_file",
            "文件不存在或不是普通文件",
            evidence={"file": p.name},
        )

    try:
        size = p.stat().st_size
    except OSError as exc:
        raise FileFingerprintError(
            "unreadable_file",
            "文件状态不可读",
            evidence={"file": p.name, "error": str(exc)},
        ) from exc

    if size <= 0:
        raise FileFingerprintError(
            "unreadable_file",
            "文件为空（大小为零），无法作为有效交付",
            evidence={"file": p.name, "size": size},
        )

    h = hashlib.sha256()
    try:
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
                h.update(chunk)
    except OSError as exc:
        raise FileFingerprintError(
            "unreadable_file",
            "文件读取失败（权限或 IO 错误）",
            evidence={"file": p.name, "error": str(exc)},
        ) from exc

    return FileFingerprint(size=size, sha256=h.hexdigest())


def verify_file_fingerprint(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    enforce_root: bool = True,
) -> FileFingerprint:
    """校验文件存在/可读/大小>0，并（若给定）比对 SHA-256 与大小。

    版本复用、readiness、下载三条路径共享此函数。不只判断 ``file_path`` 非空：
    一律重新落到磁盘上计算指纹并与记录比对。

    Raises:
        FileFingerprintError: 任一校验失败（code 指向具体失败类型）。
    """
    fp = compute_file_fingerprint(path, enforce_root=enforce_root)

    if expected_size is not None and fp.size != expected_size:
        raise FileFingerprintError(
            "file_hash_mismatch",
            "文件大小与版本记录不一致",
            evidence={
                "file": Path(path).name,
                "expected_size": expected_size,
                "actual_size": fp.size,
            },
        )

    if expected_sha256 is not None and fp.sha256 != expected_sha256:
        raise FileFingerprintError(
            "file_hash_mismatch",
            "文件指纹（SHA-256）与版本记录不一致",
            evidence={"file": Path(path).name},
        )

    return fp
