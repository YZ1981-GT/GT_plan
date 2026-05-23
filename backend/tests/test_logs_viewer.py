"""日志集中查看路由单测

spec proposal-remaining-18 task 5.7 (MT-8)

覆盖：
- 非 admin 角色 → 403
- 日志文件不存在 → 200 + status=no_log_file
- 读取最近 N 行
- level 过滤
- search 模糊匹配
- lines 上限 5000（>5000 → 422）
- 非法 level → 400
- 跳过非 JSON 行（坏行）
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.models.core import UserRole
from app.routers.logs_viewer import router as logs_viewer_router


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.admin) -> None:
        self.id = uuid.uuid4()
        self.role = role
        self.email = "tester@example.com"
        self.username = "tester"
        self.is_active = True


def _make_app(role: UserRole = UserRole.admin) -> FastAPI:
    app = FastAPI()
    app.include_router(logs_viewer_router)

    async def _override_user():
        return _FakeUser(role=role)

    app.dependency_overrides[get_current_user] = _override_user
    return app


def _write_jsonl(file_path: Path, entries: list[dict]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _sample_entries() -> list[dict]:
    return [
        {"timestamp": "2026-05-22T10:00:00Z", "level": "INFO", "logger": "app.main",
         "message": "Application started", "module": "main", "function": "lifespan",
         "line": 30, "request_id": "-"},
        {"timestamp": "2026-05-22T10:00:01Z", "level": "DEBUG", "logger": "app.db",
         "message": "Connected to PostgreSQL", "module": "db", "function": "connect",
         "line": 50, "request_id": "-"},
        {"timestamp": "2026-05-22T10:00:02Z", "level": "WARNING", "logger": "app.cache",
         "message": "Redis unavailable, fallback to memory",
         "module": "cache", "function": "init", "line": 12, "request_id": "-"},
        {"timestamp": "2026-05-22T10:00:03Z", "level": "ERROR", "logger": "app.api",
         "message": "Failed to fetch user profile",
         "module": "users", "function": "get_profile", "line": 88, "request_id": "abc"},
        {"timestamp": "2026-05-22T10:00:04Z", "level": "INFO", "logger": "app.audit",
         "message": "User logged in: admin",
         "module": "auth", "function": "login", "line": 41, "request_id": "def"},
    ]


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_admin_forbidden(monkeypatch, tmp_path):
    """非 admin 角色访问 → 403"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.auditor)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs")
    assert resp.status_code == 403
    assert "管理员" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_no_log_file_returns_status(monkeypatch, tmp_path):
    """日志文件不存在 → 200 + status=no_log_file + items=[]"""
    log_file = tmp_path / "missing.jsonl"
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "no_log_file"
    assert body["items"] == []
    assert body["log_file_exists"] is False


@pytest.mark.asyncio
async def test_read_recent_lines(monkeypatch, tmp_path):
    """读取最近 N 行（默认 1000，文件 5 行返回 5 行）"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["log_file_exists"] is True
    assert body["total"] == 5
    assert len(body["items"]) == 5
    # 每条都有 timestamp/level/message
    for item in body["items"]:
        assert "timestamp" in item
        assert "level" in item
        assert "message" in item


@pytest.mark.asyncio
async def test_filter_by_level(monkeypatch, tmp_path):
    """level=ERROR 仅返回 ERROR 行"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?level=ERROR")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "ERROR"
    assert "Failed to fetch user profile" in body["items"][0]["message"]


@pytest.mark.asyncio
async def test_filter_by_level_case_insensitive(monkeypatch, tmp_path):
    """level=warning 大小写不敏感"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?level=warning")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "WARNING"


@pytest.mark.asyncio
async def test_search_substring(monkeypatch, tmp_path):
    """search=Redis 模糊匹配 message"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?search=Redis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert "Redis" in body["items"][0]["message"]


@pytest.mark.asyncio
async def test_search_case_insensitive(monkeypatch, tmp_path):
    """search 模糊匹配大小写不敏感"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?search=redis")
    body = resp.json()
    assert body["total"] == 1


@pytest.mark.asyncio
async def test_combined_level_and_search(monkeypatch, tmp_path):
    """level + search 组合过滤"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?level=INFO&search=admin")
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "INFO"
    assert "admin" in body["items"][0]["message"]


@pytest.mark.asyncio
async def test_lines_limit_caps_at_5000(monkeypatch, tmp_path):
    """lines>5000 → 422（FastAPI Query le 校验）"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?lines=99999")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_lines_zero_rejected(monkeypatch, tmp_path):
    """lines=0 → 422"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?lines=0")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_invalid_level_rejected(monkeypatch, tmp_path):
    """非法 level → 400"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?level=NOTREAL")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_skip_malformed_lines(monkeypatch, tmp_path):
    """非 JSON 行被跳过，skipped_lines 计数正确"""
    log_file = tmp_path / "app.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("w", encoding="utf-8") as f:
        f.write(json.dumps(_sample_entries()[0]) + "\n")
        f.write("not a json line\n")
        f.write("\n")  # 空行
        f.write(json.dumps(_sample_entries()[1]) + "\n")
        f.write('{"missing_brace\n')  # 不闭合
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs")
    body = resp.json()
    assert body["total"] == 2  # 2 条合法 JSON
    assert body["skipped_lines"] == 2  # not a json + missing_brace


@pytest.mark.asyncio
async def test_lines_param_returns_only_last_n(monkeypatch, tmp_path):
    """lines=2 仅返回最后 2 行"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())  # 5 行
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.admin)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs?lines=2")
    body = resp.json()
    assert body["total"] == 2
    # 最后 2 行 = ERROR Failed to fetch + INFO User logged in
    levels = [item["level"] for item in body["items"]]
    assert levels == ["ERROR", "INFO"]


@pytest.mark.asyncio
async def test_partner_role_forbidden(monkeypatch, tmp_path):
    """partner 角色（非 admin） → 403"""
    log_file = tmp_path / "app.jsonl"
    _write_jsonl(log_file, _sample_entries())
    monkeypatch.setenv("LOG_FILE_PATH", str(log_file))

    app = _make_app(role=UserRole.partner)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/admin/logs")
    assert resp.status_code == 403
