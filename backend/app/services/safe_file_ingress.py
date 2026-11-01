"""跨附件与知识库共用的有界文件摄入原语。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile

from app.services.attachment_upload_policy import UploadRejected, scan_content

DEFAULT_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class IngressBytes:
    content: bytes
    content_hash: str
    byte_size: int
    extension: str
    detected_media_type: str | None


def sniff_media_type(head: bytes) -> str | None:
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "application/x-ole-storage"
    if b"\x00" not in head:
        try:
            head.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    return None


def _content_matches_extension(extension: str, detected: str | None) -> bool:
    if detected is None:
        return True
    expected = {
        ".pdf": {"application/pdf"},
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"},
        ".gif": {"image/gif"},
        ".docx": {"application/zip"}, ".xlsx": {"application/zip"},
        ".xlsm": {"application/zip"}, ".pptx": {"application/zip"},
        ".doc": {"application/x-ole-storage"}, ".xls": {"application/x-ole-storage"},
        ".ppt": {"application/x-ole-storage"},
        ".txt": {"text/plain"}, ".md": {"text/plain"}, ".csv": {"text/plain"},
    }.get(extension)
    return expected is None or detected in expected


async def read_upload_bounded(
    file: UploadFile,
    *,
    allowed_extensions: Iterable[str],
    max_bytes: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> IngressBytes:
    """边读边计数/hash，超限立即停止；内容安全检查发生在落盘前。"""
    extension = Path(file.filename or "").suffix.lower()
    allowed = frozenset(value.lower() for value in allowed_extensions)
    if extension not in allowed:
        raise UploadRejected("FILE_TYPE_NOT_ALLOWED", "不支持的文件类型")
    content = bytearray()
    digest = hashlib.sha256()
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        if len(content) + len(chunk) > max_bytes:
            raise UploadRejected("ATTACHMENT_TOO_LARGE", f"文件超过 {max_bytes // 1024 // 1024}MB 限制")
        content.extend(chunk)
        digest.update(chunk)
    if not content:
        raise UploadRejected("EMPTY_FILE", "空文件不能上传")
    detected = sniff_media_type(bytes(content[:4096]))
    data = bytes(content)
    # 恶意签名优先于 MIME 不匹配：脚本/可执行内容不能被降格成普通格式错误。
    await scan_content(data)
    if not _content_matches_extension(extension, detected):
        raise UploadRejected("MEDIA_TYPE_MISMATCH", "文件扩展名与实际内容类型不一致")
    return IngressBytes(data, digest.hexdigest(), len(data), extension, detected)
