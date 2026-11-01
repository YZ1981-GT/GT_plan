"""跨附件与知识库共用文件摄入原语的边界测试。"""
from __future__ import annotations

import hashlib
from io import BytesIO

import pytest
from fastapi import UploadFile

from app.services.attachment_upload_policy import UploadRejected
from app.services.safe_file_ingress import read_upload_bounded, sniff_media_type


def _upload(name: str, content: bytes) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content))


@pytest.mark.asyncio
async def test_reads_in_chunks_and_returns_verified_identity() -> None:
    content = b"%PDF-1.7\nverified"
    result = await read_upload_bounded(
        _upload("evidence.PDF", content),
        allowed_extensions={".pdf"},
        max_bytes=1024,
        chunk_size=3,
    )

    assert result.content == content
    assert result.content_hash == hashlib.sha256(content).hexdigest()
    assert result.byte_size == len(content)
    assert result.extension == ".pdf"
    assert result.detected_media_type == "application/pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "content", "max_bytes", "code"),
    [
        ("empty.txt", b"", 10, "EMPTY_FILE"),
        ("too-large.txt", b"12345", 4, "ATTACHMENT_TOO_LARGE"),
        ("blocked.exe", b"plain", 10, "FILE_TYPE_NOT_ALLOWED"),
        ("fake.pdf", b"plain text", 100, "MEDIA_TYPE_MISMATCH"),
        ("script.txt", b"#!/bin/sh\necho unsafe", 100, "UNSAFE_CONTENT"),
    ],
)
async def test_rejects_invalid_or_unsafe_content_before_storage(
    name: str,
    content: bytes,
    max_bytes: int,
    code: str,
) -> None:
    with pytest.raises(UploadRejected) as exc:
        await read_upload_bounded(
            _upload(name, content),
            allowed_extensions={".txt", ".pdf"},
            max_bytes=max_bytes,
            chunk_size=2,
        )

    assert exc.value.code == code


def test_sniff_media_type_uses_content_not_declared_header() -> None:
    assert sniff_media_type(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert sniff_media_type(b"PK\x03\x04rest") == "application/zip"
    assert sniff_media_type(b"ordinary utf-8 text") == "text/plain"
    assert sniff_media_type(b"\x00\x01\x02") is None
