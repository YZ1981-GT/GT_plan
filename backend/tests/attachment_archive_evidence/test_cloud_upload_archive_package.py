"""归档包推送云端：上传归档包本身、失败抛错、缺依赖库不退回本地复制（spec attachment-archive-and-a-class-evidence ADR-AE-05）。"""
from __future__ import annotations

import uuid

import pytest

from app.services import cloud_storage_service as cs


@pytest.fixture
def package(tmp_path):
    p = tmp_path / f"{uuid.uuid4()}.zip"
    p.write_bytes(b"PK\x03\x04archive")
    return p


async def test_local_mode_copies_package(monkeypatch, tmp_path, package):
    monkeypatch.setattr(cs, "CLOUD_STORAGE_TYPE", "local")
    monkeypatch.setattr(cs, "CLOUD_LOCAL_PATH", str(tmp_path / "cloud"))
    pid = uuid.uuid4()
    result = await cs.CloudStorageService().upload_archive_package(pid, "测试/客户:甲", 2025, package)
    assert result["status"] == "success" and "uploaded_at" in result
    key = f"2025/测试_客户_甲_{str(pid)[:8]}/archive/{package.name}"
    assert result["remote_key"] == key
    assert (tmp_path / "cloud" / key).read_bytes() == package.read_bytes()


async def test_missing_package_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        await cs.CloudStorageService().upload_archive_package(uuid.uuid4(), "x", 2025, tmp_path / "none.zip")


async def test_configured_sftp_without_paramiko_raises(monkeypatch, package):
    import importlib.util

    monkeypatch.setattr(cs, "CLOUD_STORAGE_TYPE", "sftp")
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "paramiko" else real(name, *a))
    with pytest.raises(RuntimeError, match="未安装 paramiko"):
        await cs.CloudStorageService().upload_archive_package(uuid.uuid4(), "x", 2025, package)


async def test_failed_status_raises(monkeypatch, package):
    monkeypatch.setattr(cs, "CLOUD_STORAGE_TYPE", "smb")

    async def failed(self, local_file, remote_key):
        return {"status": "failed", "error": "共享目录不可写"}

    monkeypatch.setattr(cs.CloudStorageService, "_sync_file_smb", failed)
    with pytest.raises(RuntimeError, match="共享目录不可写"):
        await cs.CloudStorageService().upload_archive_package(uuid.uuid4(), "x", 2025, package)
