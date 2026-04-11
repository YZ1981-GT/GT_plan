"""WOPI 服务与路由单元测试 — POC 文件模式（非UUID file_id）"""

import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_storage(tmp_path):
    """临时 storage 目录，自动 patch settings.STORAGE_ROOT。"""
    with patch("app.core.config.settings") as mock_settings:
        mock_settings.STORAGE_ROOT = str(tmp_path)
        mock_settings.JWT_SECRET_KEY = "test-secret"
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_settings.CORS_ORIGINS = ["http://localhost:5173"]
        mock_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 120
        mock_settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS = 7
        mock_settings.LOGIN_MAX_ATTEMPTS = 5
        mock_settings.LOGIN_LOCK_MINUTES = 30
        mock_settings.ONLYOFFICE_URL = "http://onlyoffice:80"
        mock_settings.WOPI_BASE_URL = "http://backend:8000/wopi"
        mock_settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
        mock_settings.REDIS_URL = "redis://localhost:6379/0"
        yield tmp_path


# ── WOPI 路由集成测试（POC 文件模式） ──


@pytest.fixture()
def client(tmp_storage):
    """使用临时 storage 的 TestClient。"""
    from app.main import app
    return TestClient(app)


class TestWopiRoutes:
    def test_check_file_info_200(self, client, tmp_storage):
        poc_dir = tmp_storage / "poc"
        poc_dir.mkdir(exist_ok=True)
        (poc_dir / "report.xlsx").write_bytes(b"spreadsheet data")

        resp = client.get("/wopi/files/report.xlsx")
        assert resp.status_code == 200
        body = resp.json()
        assert body["BaseFileName"] == "report.xlsx"
        assert body["Size"] == len(b"spreadsheet data")

    def test_check_file_info_404(self, client, tmp_storage):
        resp = client.get("/wopi/files/ghost.xlsx")
        assert resp.status_code == 404

    def test_get_file_200(self, client, tmp_storage):
        poc_dir = tmp_storage / "poc"
        poc_dir.mkdir(exist_ok=True)
        (poc_dir / "binary.dat").write_bytes(b"\xde\xad\xbe\xef")

        resp = client.get("/wopi/files/binary.dat/contents")
        assert resp.status_code == 200
        assert resp.content == b"\xde\xad\xbe\xef"
        assert resp.headers["content-type"] == "application/octet-stream"

    def test_get_file_404(self, client, tmp_storage):
        resp = client.get("/wopi/files/nope.dat/contents")
        assert resp.status_code == 404

    def test_put_file_creates(self, client, tmp_storage):
        resp = client.post("/wopi/files/upload.xlsx/contents", content=b"file bytes")
        assert resp.status_code == 200
        assert (tmp_storage / "poc" / "upload.xlsx").read_bytes() == b"file bytes"

    def test_put_then_get_roundtrip(self, client, tmp_storage):
        payload = b"roundtrip content \x00\xff"
        client.post("/wopi/files/rt.bin/contents", content=payload)
        resp = client.get("/wopi/files/rt.bin/contents")
        assert resp.status_code == 200
        assert resp.content == payload

    def test_check_file_info_returns_metadata(self, client, tmp_storage):
        poc_dir = tmp_storage / "poc"
        poc_dir.mkdir(exist_ok=True)
        test_file = poc_dir / "test.xlsx"
        test_file.write_bytes(b"hello world")

        resp = client.get("/wopi/files/test.xlsx")
        assert resp.status_code == 200
        body = resp.json()
        assert body["BaseFileName"] == "test.xlsx"
        assert body["Size"] == 11
        assert body["UserCanWrite"] is True
        assert "Version" in body

    def test_get_file_reads_content(self, client, tmp_storage):
        poc_dir = tmp_storage / "poc"
        poc_dir.mkdir(exist_ok=True)
        (poc_dir / "data.bin").write_bytes(b"\x00\x01\x02\xff")

        resp = client.get("/wopi/files/data.bin/contents")
        assert resp.status_code == 200
        assert resp.content == b"\x00\x01\x02\xff"

    def test_put_file_overwrites(self, client, tmp_storage):
        poc_dir = tmp_storage / "poc"
        poc_dir.mkdir(exist_ok=True)
        (poc_dir / "existing.txt").write_bytes(b"old")

        resp = client.post("/wopi/files/existing.txt/contents", content=b"updated")
        assert resp.status_code == 200
        assert (poc_dir / "existing.txt").read_bytes() == b"updated"

    def test_lock_non_uuid_returns_400(self, client, tmp_storage):
        resp = client.post(
            "/wopi/files/not-a-uuid.xlsx",
            headers={"X-WOPI-Override": "LOCK", "X-WOPI-Lock": "lock-1"},
        )
        assert resp.status_code == 400
