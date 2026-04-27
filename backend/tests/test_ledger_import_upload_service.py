import io
import uuid

import pytest
from fastapi import HTTPException, UploadFile

from app.services.ledger_import_upload_service import LedgerImportUploadService


def _make_upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_create_bundle_rejects_excess_file_count(monkeypatch):
    project_id = uuid.uuid4()
    files = [
        _make_upload("a.csv", b"1"),
        _make_upload("b.csv", b"2"),
    ]

    monkeypatch.setattr(LedgerImportUploadService, "cleanup_expired_bundles", classmethod(lambda cls, project_id: None))
    monkeypatch.setattr("app.services.ledger_import_upload_service.settings.LEDGER_UPLOAD_MAX_FILE_COUNT", 1)

    with pytest.raises(HTTPException, match="上传文件数超过限制") as exc:
        await LedgerImportUploadService.create_bundle(project_id, "tester", files)

    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_create_bundle_rejects_excess_total_size(monkeypatch, tmp_path):
    project_id = uuid.uuid4()
    files = [
        _make_upload("a.csv", b"a" * 600_000),
        _make_upload("b.csv", b"b" * 600_000),
    ]

    monkeypatch.setattr(LedgerImportUploadService, "ROOT", tmp_path)
    monkeypatch.setattr(LedgerImportUploadService, "cleanup_expired_bundles", classmethod(lambda cls, project_id: None))
    monkeypatch.setattr("app.services.ledger_import_upload_service.settings.LEDGER_UPLOAD_MAX_FILE_COUNT", 10)
    monkeypatch.setattr("app.services.ledger_import_upload_service.settings.MAX_UPLOAD_SIZE_MB", 10)
    monkeypatch.setattr("app.services.ledger_import_upload_service.settings.LEDGER_UPLOAD_MAX_TOTAL_SIZE_MB", 1)

    with pytest.raises(HTTPException, match="上传总大小超过限制") as exc:
        await LedgerImportUploadService.create_bundle(project_id, "tester", files)

    assert exc.value.status_code == 413
