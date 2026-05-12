"""Sprint 7 批次 A：`validate_upload_safety` 安全校验测试（F40）。

覆盖 3 类恶意文件全拒绝 + audit_log 写入：

1. `.exe` 文件改名 `.xlsx` → 被 magic/signature 检查识别为非法 MIME（415）
2. zip bomb（高压缩比）→ 被 ZIP 扫描拒绝（400）
3. xlsx 含 `xl/vbaProject.bin` 宏 → 被 zip 内部条目扫描拒绝（400）
4. xlsx 含 `xl/externalLinks/externalLink1.xml` → 同类拒绝（400）
5. 超出大小上限 → 413
6. 合法 xlsx / csv → 通过

同时校验：所有被拒上传都通过 audit_logger.log_action 写 action="upload_rejected"
审计事件；合法上传写 "upload_accepted" 事件。
"""

from __future__ import annotations

import io
import uuid
import zipfile
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, UploadFile

from app.services.ledger_import.upload_security import (
    MAX_SIZE_BY_MIME,
    MIME_CSV,
    MIME_XLSX,
    validate_upload_safety,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_upload(filename: str, content: bytes, content_type: str | None = None) -> UploadFile:
    """构造 FastAPI UploadFile。

    content_type 通过 Starlette Headers 构造时传入（`UploadFile.headers` 是只读
    的 `Headers` 对象，构造后不能修改）。
    """
    from starlette.datastructures import Headers

    headers: Headers | None = None
    if content_type is not None:
        headers = Headers({"content-type": content_type})
    upload = UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        size=len(content),
        headers=headers,
    )
    return upload


def _build_valid_xlsx_bytes(extra_entries: dict[str, bytes] | None = None) -> bytes:
    """构造最小合法 xlsx 骨架（仅含必要的 OOXML 结构）。

    可选通过 `extra_entries` 追加额外 zip 条目（如 vbaProject.bin 模拟宏、
    externalLinks/ 模拟外部链接）。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        zf.writestr(
            "_rels/.rels",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>',
        )
        zf.writestr(
            "xl/workbook.xml",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
        )
        if extra_entries:
            for name, data in extra_entries.items():
                zf.writestr(name, data)
    return buf.getvalue()


def _build_zip_bomb_bytes() -> bytes:
    """构造高压缩比 zip：写入 2MB 全零 → 压缩后 ~2KB（ratio ≈ 1000×）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # 2MB 全零高度可压缩
        zf.writestr("payload.bin", b"\x00" * (2 * 1024 * 1024))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audit_log_calls(monkeypatch):
    """拦截 audit_logger.log_action 调用，返回 (调用参数列表)。"""
    from app.services import audit_logger_enhanced

    calls: list[dict] = []

    async def _capture(**kwargs):
        calls.append(kwargs)
        return kwargs

    mock = AsyncMock(side_effect=_capture)
    monkeypatch.setattr(audit_logger_enhanced.audit_logger, "log_action", mock)
    return calls


# ---------------------------------------------------------------------------
# 1. .exe 改名为 .xlsx（magic number 拒绝）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exe_renamed_as_xlsx_is_rejected(audit_log_calls):
    # PE 文件头 "MZ"（Windows 可执行文件）
    pe_bytes = b"MZ\x90\x00" + b"\x00" * 1024
    file = _make_upload("evil.xlsx", pe_bytes, content_type=MIME_XLSX)

    uid = uuid.uuid4()
    pid = uuid.uuid4()
    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_safety(
            file, user_id=uid, project_id=pid, ip_address="10.0.0.1"
        )

    assert exc_info.value.status_code == 415

    # 必有 upload_rejected 审计记录
    reject_events = [c for c in audit_log_calls if c.get("action") == "upload_rejected"]
    assert len(reject_events) == 1, audit_log_calls
    rej = reject_events[0]
    assert rej["user_id"] == uid
    assert rej["project_id"] == pid
    assert rej["ip_address"] == "10.0.0.1"
    assert rej["details"]["reason"] == "unsupported_file_type"
    assert rej["details"]["filename"] == "evil.xlsx"


# ---------------------------------------------------------------------------
# 2. zip bomb 拒绝
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zip_bomb_is_rejected(audit_log_calls):
    bomb_bytes = _build_zip_bomb_bytes()
    # 高压缩 zip 以 .zip 上传（MIME=application/zip 允许，但压缩比会被拦）
    file = _make_upload("bomb.zip", bomb_bytes, content_type="application/zip")

    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_safety(file, user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert exc_info.value.status_code == 400

    reject_events = [c for c in audit_log_calls if c.get("action") == "upload_rejected"]
    assert len(reject_events) == 1
    assert reject_events[0]["details"]["reason"] == "zip_bomb_suspected"
    assert reject_events[0]["details"]["uncompressed_size"] > 0
    assert reject_events[0]["details"]["ratio"] > 100


# ---------------------------------------------------------------------------
# 3. xlsx 宏文件拒绝（vbaProject.bin）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_xlsx_with_macro_is_rejected(audit_log_calls):
    xlsx_bytes = _build_valid_xlsx_bytes(
        extra_entries={"xl/vbaProject.bin": b"fake-vba-binary-payload"}
    )
    file = _make_upload("with_macro.xlsx", xlsx_bytes, content_type=MIME_XLSX)

    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_safety(file, user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert exc_info.value.status_code == 400

    reject_events = [c for c in audit_log_calls if c.get("action") == "upload_rejected"]
    assert len(reject_events) == 1
    details = reject_events[0]["details"]
    assert details["reason"] == "macro_detected"
    assert details["offending_entry"].lower() == "xl/vbaproject.bin"


@pytest.mark.asyncio
async def test_xlsx_with_external_links_is_rejected(audit_log_calls):
    xlsx_bytes = _build_valid_xlsx_bytes(
        extra_entries={"xl/externalLinks/externalLink1.xml": b"<externalLink/>"}
    )
    file = _make_upload("with_extlink.xlsx", xlsx_bytes, content_type=MIME_XLSX)

    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_safety(file, user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert exc_info.value.status_code == 400

    reject_events = [c for c in audit_log_calls if c.get("action") == "upload_rejected"]
    assert len(reject_events) == 1
    assert reject_events[0]["details"]["reason"] == "external_links_detected"


# ---------------------------------------------------------------------------
# 4. 大小上限（413）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oversized_xlsx_is_rejected(audit_log_calls):
    xlsx_bytes = _build_valid_xlsx_bytes()
    file = _make_upload("huge.xlsx", xlsx_bytes, content_type=MIME_XLSX)
    # 人为注入 size 超过 500MB
    file.size = MAX_SIZE_BY_MIME[MIME_XLSX] + 1

    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_safety(file, user_id=uuid.uuid4(), project_id=uuid.uuid4())

    assert exc_info.value.status_code == 413

    reject_events = [c for c in audit_log_calls if c.get("action") == "upload_rejected"]
    assert len(reject_events) == 1
    assert reject_events[0]["details"]["reason"] == "file_too_large"


# ---------------------------------------------------------------------------
# 5. 合法文件通过
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_xlsx_is_accepted(audit_log_calls):
    xlsx_bytes = _build_valid_xlsx_bytes()
    file = _make_upload("clean.xlsx", xlsx_bytes, content_type=MIME_XLSX)

    # 不应抛异常
    await validate_upload_safety(file, user_id=uuid.uuid4(), project_id=uuid.uuid4())

    accept_events = [c for c in audit_log_calls if c.get("action") == "upload_accepted"]
    reject_events = [c for c in audit_log_calls if c.get("action") == "upload_rejected"]
    assert len(reject_events) == 0
    assert len(accept_events) == 1
    assert accept_events[0]["details"]["mime"] == MIME_XLSX


@pytest.mark.asyncio
async def test_valid_csv_is_accepted(audit_log_calls):
    csv_bytes = b"\xef\xbb\xbfcode,name\n1001,test\n1002,demo\n"
    file = _make_upload("clean.csv", csv_bytes, content_type=MIME_CSV)

    await validate_upload_safety(file, user_id=uuid.uuid4(), project_id=uuid.uuid4())

    accept_events = [c for c in audit_log_calls if c.get("action") == "upload_accepted"]
    assert len(accept_events) == 1
    assert accept_events[0]["details"]["mime"] == MIME_CSV


# ---------------------------------------------------------------------------
# 6. File pointer 复位（确保校验后后续流程仍能读取）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_pointer_resets_after_validation(audit_log_calls):
    xlsx_bytes = _build_valid_xlsx_bytes()
    file = _make_upload("clean.xlsx", xlsx_bytes, content_type=MIME_XLSX)

    await validate_upload_safety(file, user_id=uuid.uuid4(), project_id=uuid.uuid4())

    # 校验后应能重新从头读
    content = await file.read()
    assert content.startswith(b"PK\x03\x04")
    assert len(content) == len(xlsx_bytes)
