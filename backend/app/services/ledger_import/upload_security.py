"""账表导入上传安全校验（F40 / Sprint 7 批次 A）。

对齐 `.kiro/specs/ledger-import-view-refactor/design.md` §D11.1：

- MIME + magic number 双重检查（magic number 为主，MIME 仅做辅助参考）
- 按文件类型限制大小（xlsx ≤ 500MB / csv ≤ 1GB / zip ≤ 200MB）
- xlsx 内部结构扫描：拒绝宏（`xl/vbaProject.bin`）与外部链接
  （`xl/externalLinks/*`）
- zip bomb 检测：总解压后大小 > 压缩后大小 × 100 视为可疑
- 所有被拒绝上传写入 `audit_logs`（通过 `audit_logger.log_action`）

对外 API：`validate_upload_safety(file, *, user_id=None, project_id=None,
ip_address=None) -> None`，通过 raise `HTTPException` 中断流程；合法文件
不抛异常并记一条 `upload_accepted` 审计事件。

运行环境：**不依赖 `python-magic`**（Windows 部署难安装），采用 "库可选 +
字节签名兜底" 策略：

- 若 `python-magic` 可导入，优先用它从前 8KB 字节推断 MIME
- 否则通过文件头字节签名（xlsx/zip 都是 `PK\x03\x04`，csv 按文本可打印
  率判断）+ 扩展名综合判断
"""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, UploadFile

from .errors import ErrorCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_CSV = "text/csv"
MIME_ZIP = "application/zip"

# 按 MIME 设定大小上限（对齐 design D11.1）
_MB = 1024 * 1024
MAX_SIZE_BY_MIME: dict[str, int] = {
    MIME_XLSX: 500 * _MB,
    MIME_CSV: 1024 * _MB,
    MIME_ZIP: 200 * _MB,
}

# 允许的 MIME 白名单（magic number 识别结果必须落在这里）
ALLOWED_MIMES: frozenset[str] = frozenset({MIME_XLSX, MIME_CSV, MIME_ZIP})

# 字节签名（用于 python-magic 不可用时的兜底识别）
_PK_HEADER = b"PK\x03\x04"  # zip / xlsx / docx 等 OOXML 格式的魔数

# zip bomb 压缩比阈值（解压后总大小 / 压缩前文件大小）
ZIP_BOMB_RATIO = 100

# head 读取字节数（magic number + 嗅探 zip 条目足够）
_HEAD_BYTES = 8192


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DetectedType:
    mime: str  # 识别出的 MIME
    detected_by: str  # "magic" | "signature" | "extension"
    size_limit: int  # 对应 MIME 的大小上限


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


async def validate_upload_safety(
    file: UploadFile,
    *,
    user_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    ip_address: Optional[str] = None,
) -> None:
    """校验上传文件安全性。合法直接返回，非法抛 HTTPException。

    调用点应在接受 `UploadFile` 之后、实际持久化/解析之前立刻调用本函数。

    Args:
        file: FastAPI UploadFile 实例
        user_id: 当前登录用户 ID（用于 audit_log）
        project_id: 关联项目 ID（用于 audit_log）
        ip_address: 客户端 IP（用于 audit_log）

    Raises:
        HTTPException 413: 文件超出大小上限 / 疑似 zip bomb
        HTTPException 415: 不支持的 MIME / 类型
        HTTPException 400: xlsx 含宏或外部链接
    """
    filename = file.filename or "unknown"
    declared_mime = (file.content_type or "").lower().strip()

    # 读取前 8KB 做 magic number 推断（同时用于后续 zip 内部检测）
    try:
        head = await file.read(_HEAD_BYTES)
    finally:
        # 无论成败都尝试复位；失败不抛
        try:
            await file.seek(0)
        except Exception:  # pragma: no cover - StreamingUploadFile 可能不支持 seek
            pass

    detected = _detect_type(head, filename, declared_mime)

    # 1. MIME 白名单
    if detected.mime not in ALLOWED_MIMES:
        await _reject(
            status=415,
            reason="unsupported_file_type",
            message=f"不支持的文件类型: {detected.mime}",
            filename=filename,
            mime=detected.mime,
            size=file.size,
            user_id=user_id,
            project_id=project_id,
            ip_address=ip_address,
            detected_by=detected.detected_by,
            declared_mime=declared_mime,
        )

    # 2. 大小检查
    #   - file.size 是 FastAPI 解析到的声明大小；若 None（streaming），用
    #     head 长度估算上限不靠谱 → 保守只对有确切 size 的文件拦截
    size_known: Optional[int] = file.size
    if size_known is not None and size_known > detected.size_limit:
        limit_mb = detected.size_limit // _MB
        await _reject(
            status=413,
            reason="file_too_large",
            message=f"文件超出 {detected.mime} 类型的大小上限 {limit_mb}MB",
            filename=filename,
            mime=detected.mime,
            size=size_known,
            user_id=user_id,
            project_id=project_id,
            ip_address=ip_address,
            detected_by=detected.detected_by,
            limit_bytes=detected.size_limit,
        )

    # 3. xlsx/zip 结构扫描（magic number = PK\x03\x04 的文件进入此分支）
    if detected.mime in (MIME_XLSX, MIME_ZIP):
        # 读取完整文件到内存做 zip 分析；对超过 MAX_SIZE_BY_MIME 的已经在
        # 第 2 步被拒掉，不会进到这里
        full_bytes = head + await file.read()
        try:
            await file.seek(0)
        except Exception:  # pragma: no cover
            pass

        total_size = len(full_bytes) if size_known is None else size_known
        await _scan_zip_structure(
            full_bytes=full_bytes,
            declared_mime=detected.mime,
            total_size=total_size,
            filename=filename,
            user_id=user_id,
            project_id=project_id,
            ip_address=ip_address,
        )

    # 4. 成功日志（不阻断流程）
    try:
        from app.services.audit_logger_enhanced import audit_logger

        await audit_logger.log_action(
            user_id=user_id or "",
            action="upload_accepted",
            object_type="ledger_import_upload",
            object_id=None,
            project_id=project_id,
            details={
                "filename": filename,
                "mime": detected.mime,
                "detected_by": detected.detected_by,
                "size": size_known,
            },
            ip_address=ip_address,
        )
    except Exception:  # pragma: no cover
        logger.warning("[upload_security] 审计日志写入失败", exc_info=True)


# ---------------------------------------------------------------------------
# 类型识别
# ---------------------------------------------------------------------------


def _detect_type(head: bytes, filename: str, declared_mime: str) -> _DetectedType:
    """综合 magic number / 字节签名 / 扩展名识别 MIME。"""

    # 1. 尝试 python-magic（若可用）
    magic_mime = _try_magic(head)
    if magic_mime:
        # magic 优先：xlsx 通常识别为 `application/vnd.openxmlformats-...`
        # 或 `application/zip`（旧版 libmagic）；csv 识别为 `text/plain` 或
        # `text/csv`
        if magic_mime in ALLOWED_MIMES:
            return _DetectedType(
                mime=magic_mime,
                detected_by="magic",
                size_limit=MAX_SIZE_BY_MIME[magic_mime],
            )
        # text/plain + .csv 扩展名 → 视为 csv
        if magic_mime.startswith("text/") and filename.lower().endswith(".csv"):
            return _DetectedType(
                mime=MIME_CSV,
                detected_by="magic+ext",
                size_limit=MAX_SIZE_BY_MIME[MIME_CSV],
            )
        # application/zip + .xlsx 扩展名 → 视为 xlsx（后续 zip 扫描会
        # 进一步确认内部结构）
        if magic_mime == MIME_ZIP and filename.lower().endswith(".xlsx"):
            return _DetectedType(
                mime=MIME_XLSX,
                detected_by="magic+ext",
                size_limit=MAX_SIZE_BY_MIME[MIME_XLSX],
            )

    # 2. 字节签名兜底
    lower_name = filename.lower()
    if head.startswith(_PK_HEADER):
        # PK\x03\x04 = zip 家族（包括 xlsx/docx/pptx/zip）
        if lower_name.endswith(".xlsx"):
            return _DetectedType(
                mime=MIME_XLSX,
                detected_by="signature+ext",
                size_limit=MAX_SIZE_BY_MIME[MIME_XLSX],
            )
        if lower_name.endswith(".zip"):
            return _DetectedType(
                mime=MIME_ZIP,
                detected_by="signature+ext",
                size_limit=MAX_SIZE_BY_MIME[MIME_ZIP],
            )
        # 其他 OOXML / zip 家族（.docx/.pptx/.jar 等）走 ZIP 类但 MIME 不在白名单
        # → 让上层按 MIME 白名单拒掉
        return _DetectedType(
            mime="application/zip-container",
            detected_by="signature",
            size_limit=MAX_SIZE_BY_MIME[MIME_ZIP],
        )

    # 3. 文本识别（csv 无 magic number，按可打印率 + 扩展名）
    if lower_name.endswith(".csv"):
        if _looks_like_text(head):
            return _DetectedType(
                mime=MIME_CSV,
                detected_by="extension+text",
                size_limit=MAX_SIZE_BY_MIME[MIME_CSV],
            )

    # 4. 其他 → 未知（让白名单拦截）
    # 声明为 xlsx/zip 但字节签名对不上 → 明确视为非法（而非让它走到 zip scan 被
    # 误判为 corrupted_zip），给前端返回清晰的 415 unsupported_file_type
    if declared_mime in (MIME_XLSX, MIME_ZIP):
        return _DetectedType(
            mime="application/octet-stream",
            detected_by="signature-mismatch",
            size_limit=MAX_SIZE_BY_MIME[MIME_XLSX],
        )

    mime = declared_mime if declared_mime in ALLOWED_MIMES else "application/octet-stream"
    return _DetectedType(
        mime=mime,
        detected_by="declared" if declared_mime else "unknown",
        size_limit=MAX_SIZE_BY_MIME.get(mime, MAX_SIZE_BY_MIME[MIME_XLSX]),
    )


def _try_magic(head: bytes) -> Optional[str]:
    """尝试使用 python-magic 识别 MIME；未安装或调用失败返回 None。"""

    try:
        import magic  # type: ignore[import-not-found]
    except Exception:
        return None

    try:
        mime = magic.from_buffer(head, mime=True)
        if isinstance(mime, bytes):
            mime = mime.decode("utf-8", errors="ignore")
        return mime.lower().strip() if mime else None
    except Exception:  # pragma: no cover - libmagic 运行时异常
        logger.debug("[upload_security] python-magic 调用失败，降级到字节签名", exc_info=True)
        return None


def _looks_like_text(head: bytes) -> bool:
    """粗略判断字节序列是否为可打印文本（csv/txt）。"""
    if not head:
        return False
    # 允许 ASCII 可打印 + 制表符/换行/回车 + UTF-8 高位字节
    printable = sum(
        1
        for b in head
        if b in (0x09, 0x0A, 0x0D)
        or 0x20 <= b <= 0x7E
        or 0x80 <= b <= 0xFF  # 允许 UTF-8/GBK 中文
    )
    return printable / len(head) >= 0.90


# ---------------------------------------------------------------------------
# zip 结构扫描（宏 + 外部链接 + zip bomb）
# ---------------------------------------------------------------------------


# xlsx 内部禁用路径（全大小写视为等价；zip 条目大小写敏感，这里保持原样匹配）
_FORBIDDEN_XLSX_ENTRIES = (
    "xl/vbaProject.bin",
    "xl/vbaproject.bin",  # 大小写变种
)
_FORBIDDEN_XLSX_PREFIXES = (
    "xl/externalLinks/",
    "xl/externallinks/",
)


async def _scan_zip_structure(
    *,
    full_bytes: bytes,
    declared_mime: str,
    total_size: int,
    filename: str,
    user_id: Optional[UUID],
    project_id: Optional[UUID],
    ip_address: Optional[str],
) -> None:
    """读取完整 zip 字节 → 扫描条目 → 检查宏 / 外部链接 / zip bomb。"""

    try:
        with zipfile.ZipFile(io.BytesIO(full_bytes)) as zf:
            infos = zf.infolist()
            names = [zi.filename for zi in infos]

            # xlsx 宏 / 外部链接
            if declared_mime == MIME_XLSX:
                for name in names:
                    lower = name.lower()
                    if lower == "xl/vbaproject.bin":
                        await _reject(
                            status=400,
                            reason="macro_detected",
                            message="禁止含宏（vbaProject.bin）的 Excel 文件",
                            filename=filename,
                            mime=declared_mime,
                            size=total_size,
                            user_id=user_id,
                            project_id=project_id,
                            ip_address=ip_address,
                            offending_entry=name,
                        )
                    if lower.startswith("xl/externallinks/"):
                        await _reject(
                            status=400,
                            reason="external_links_detected",
                            message="禁止含外部链接的 Excel 文件",
                            filename=filename,
                            mime=declared_mime,
                            size=total_size,
                            user_id=user_id,
                            project_id=project_id,
                            ip_address=ip_address,
                            offending_entry=name,
                        )

            # zip bomb：总解压后大小 > 压缩前 × 100
            total_uncompressed = sum(max(0, zi.file_size) for zi in infos)
            if total_size > 0 and total_uncompressed > total_size * ZIP_BOMB_RATIO:
                await _reject(
                    status=400,
                    reason="zip_bomb_suspected",
                    message=(
                        f"可疑的高压缩比文件（解压后 {total_uncompressed} 字节 / "
                        f"压缩前 {total_size} 字节 > {ZIP_BOMB_RATIO}×）"
                    ),
                    filename=filename,
                    mime=declared_mime,
                    size=total_size,
                    user_id=user_id,
                    project_id=project_id,
                    ip_address=ip_address,
                    uncompressed_size=total_uncompressed,
                    ratio=total_uncompressed / max(1, total_size),
                )
    except HTTPException:
        raise
    except zipfile.BadZipFile as exc:
        await _reject(
            status=400,
            reason="corrupted_zip",
            message=f"压缩文件已损坏: {exc}",
            filename=filename,
            mime=declared_mime,
            size=total_size,
            user_id=user_id,
            project_id=project_id,
            ip_address=ip_address,
        )


# ---------------------------------------------------------------------------
# 拒绝 + 审计日志
# ---------------------------------------------------------------------------


async def _reject(
    *,
    status: int,
    reason: str,
    message: str,
    filename: str,
    mime: str,
    size: Optional[int],
    user_id: Optional[UUID],
    project_id: Optional[UUID],
    ip_address: Optional[str],
    **extra: object,
) -> None:
    """写 audit_log 并抛 HTTPException。

    审计日志写入失败不阻断拒绝动作——安全拒绝始终优先。
    """
    details = {
        "filename": filename,
        "mime": mime,
        "size": size,
        "reason": reason,
        "message": message,
    }
    details.update(extra)

    try:
        from app.services.audit_logger_enhanced import audit_logger

        await audit_logger.log_action(
            user_id=user_id or "",
            action="upload_rejected",
            object_type="ledger_import_upload",
            object_id=None,
            project_id=project_id,
            details=details,
            ip_address=ip_address,
        )
    except Exception:  # pragma: no cover
        logger.warning("[upload_security] 审计日志写入失败: %s", reason, exc_info=True)

    # 对齐 v2 引擎错误码命名习惯，便于前端统一翻译
    error_code = _REASON_TO_ERROR_CODE.get(reason)
    detail: object
    if error_code:
        detail = {
            "code": error_code.value,
            "reason": reason,
            "message": message,
            "filename": filename,
            "mime": mime,
        }
    else:
        detail = message

    raise HTTPException(status_code=status, detail=detail)


_REASON_TO_ERROR_CODE: dict[str, ErrorCode] = {
    "file_too_large": ErrorCode.FILE_TOO_LARGE,
    "unsupported_file_type": ErrorCode.UNSUPPORTED_FILE_TYPE,
    "zip_bomb_suspected": ErrorCode.FILE_TOO_LARGE,
    # 宏 / 外部链接 / 损坏 zip 无对应语义错误码，使用 UNSUPPORTED_FILE_TYPE 近似
    "macro_detected": ErrorCode.UNSUPPORTED_FILE_TYPE,
    "external_links_detected": ErrorCode.UNSUPPORTED_FILE_TYPE,
    "corrupted_zip": ErrorCode.CORRUPTED_FILE,
}


__all__ = [
    "validate_upload_safety",
    "ALLOWED_MIMES",
    "MAX_SIZE_BY_MIME",
    "ZIP_BOMB_RATIO",
    "MIME_XLSX",
    "MIME_CSV",
    "MIME_ZIP",
]
