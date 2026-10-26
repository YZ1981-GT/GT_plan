"""WOPI 服务与路由单元测试 — POC 文件模式（非UUID file_id）"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture()
def tmp_storage(tmp_path, monkeypatch):
    """临时 storage 目录：只改真实配置对象上的 ``STORAGE_ROOT`` 一个属性（POC 路由按它找文件）。

    🔴 原先用 ``patch("app.core.config.settings")`` 把整个配置对象换成 MagicMock，并在替换期间才
    ``from app.main import app``：单独跑本文件时那是后端应用的首次导入，所有模块级
    ``from app.core.config import settings`` 都绑定到 MagicMock，``main.py`` 的 ``settings.CORS_ORIGINS.split(",")``
    当场 AttributeError（夹具把它设成了 list），且 security / 中间件等 5 个模块从此一直拿着 MagicMock；
    跟别的用例一起跑时应用已被先导入，才碰巧通过。现在应用在本文件导入时加载（真实配置），夹具只改一个属性。
    """
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    yield tmp_path


# ── WOPI 路由集成测试（POC 文件模式） ──


@pytest.fixture()
def client(tmp_storage):
    """使用临时 storage 的 TestClient。"""
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
