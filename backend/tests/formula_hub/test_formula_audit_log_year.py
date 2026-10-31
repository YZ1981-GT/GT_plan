"""任务 29：公式审计日志按年度与「人工补记」（需求 11.1~11.3，ADR-FHIC-12）。

10 个用例覆盖三个文件的改动：
- ``routers/formula_audit_log.py``：GET 年度过滤 + legacy_without_year；POST ManualNoteBody
- ``services/formula_settings/audit.py``：``audit_project(year=…)`` 载荷写入
- ``routers/wp_formula_audit.py``：``write_wp_formula_audit(year=…)`` details 写入

策略：
- GET 用例：向 SQLite 内存库写入若干 audit_log_entries 行，直接调用路由函数。
- POST 用例：monkeypatch mock ``append_audit_log`` 捕获载荷断言。
- service 用例：同 monkeypatch 捕获载荷。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# ---------------------------------------------------------------------------
# SQLite 内存引擎 + 表结构
# ---------------------------------------------------------------------------
_SQLITE_URL = "sqlite+aiosqlite://"

_CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log_entries (
    id TEXT PRIMARY KEY,
    ts TEXT,
    user_id TEXT,
    session_id TEXT,
    action_type TEXT,
    object_type TEXT,
    object_id TEXT,
    payload TEXT,
    ip TEXT,
    ua TEXT,
    trace_id TEXT,
    prev_hash TEXT DEFAULT '',
    entry_hash TEXT DEFAULT ''
)
"""


@pytest_asyncio.fixture
async def mem_engine():
    engine = create_async_engine(_SQLITE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(_CREATE_AUDIT_TABLE))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def mem_session(mem_engine):
    sm = async_sessionmaker(mem_engine, expire_on_commit=False)
    async with sm() as session:
        yield session


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_PID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_UID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


async def _insert(session: AsyncSession, payload: dict, ts: str = "2026-01-01T00:00:00Z") -> None:
    row_id = str(uuid.uuid4())
    pj = json.dumps(payload, ensure_ascii=False, default=str)
    await session.execute(
        text(
            "INSERT INTO audit_log_entries (id, ts, user_id, action_type, object_type, payload)"
            " VALUES (:id, :ts, :uid, 'formula.changed', 'formula_setting', :pl)"
        ),
        {"id": row_id, "ts": ts, "uid": str(_UID), "pl": pj},
    )
    await session.commit()


class _FakeUser:
    id = _UID
    username = "fh_admin"
    role = "admin"
    is_active = True


class _AsyncCtxMgr:
    """最小 async context manager，替代 db.begin_nested()。"""
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        pass


def _make_mock_db():
    """构造一个 mock db，其 begin_nested() 返回可用的 async context manager。"""
    class _MockDb:
        def begin_nested(self):
            return _AsyncCtxMgr()
    return _MockDb()


# ===========================================================================
# A. GET 年度过滤（直接调路由函数，跳过鉴权依赖）
# ===========================================================================
class TestGetYearFilter:
    """GET 端点的年度过滤逻辑：直接调用 ``get_audit_log`` 函数。"""

    @pytest.mark.asyncio
    async def test_get_only_returns_matching_year(self, mem_session):
        """用例 1+3：year=2025 只返回 payload.year=='2025'，不含 2024。"""
        await _insert(mem_session, {
            "project_id": _PID, "module": "report", "row_code": "BS-001",
            "action": "update", "old_formula": "", "new_formula": "TB('1001')",
            "result_value": "", "year": "2025",
        }, ts="2026-01-01T00:00:03Z")
        await _insert(mem_session, {
            "project_id": _PID, "module": "report", "row_code": "BS-002",
            "action": "update", "old_formula": "", "new_formula": "TB('1002')",
            "result_value": "", "year": "2024",
        }, ts="2026-01-01T00:00:02Z")
        await _insert(mem_session, {
            "project_id": _PID, "module": "report", "row_code": "BS-003",
            "action": "update", "old_formula": "", "new_formula": "TB('1003')",
            "result_value": "",
            # 无 year —— 旧条目
        }, ts="2026-01-01T00:00:01Z")

        from app.routers.formula_audit_log import get_audit_log
        data = await get_audit_log(
            project_id=_PID, year=2025, module="", row_code="",
            legacy_without_year=False, limit=100,
            db=mem_session, current_user=_FakeUser(),
        )
        assert len(data) == 1
        assert data[0]["row_code"] == "BS-001"

    @pytest.mark.asyncio
    async def test_get_legacy_without_year_includes_old_entries(self, mem_session):
        """用例 2：legacy_without_year=true 同时返回无 year 字段的旧条目。"""
        await _insert(mem_session, {
            "project_id": _PID, "module": "report", "row_code": "BS-001",
            "action": "update", "old_formula": "", "new_formula": "TB('1001')",
            "result_value": "", "year": "2025",
        }, ts="2026-01-01T00:00:03Z")
        await _insert(mem_session, {
            "project_id": _PID, "module": "report", "row_code": "BS-002",
            "action": "update", "old_formula": "", "new_formula": "TB('1002')",
            "result_value": "", "year": "2024",
        }, ts="2026-01-01T00:00:02Z")
        await _insert(mem_session, {
            "project_id": _PID, "module": "report", "row_code": "BS-003",
            "action": "update", "old_formula": "", "new_formula": "TB('1003')",
            "result_value": "",
        }, ts="2026-01-01T00:00:01Z")

        from app.routers.formula_audit_log import get_audit_log
        data = await get_audit_log(
            project_id=_PID, year=2025, module="", row_code="",
            legacy_without_year=True, limit=100,
            db=mem_session, current_user=_FakeUser(),
        )
        assert len(data) == 2
        row_codes = {d["row_code"] for d in data}
        assert row_codes == {"BS-001", "BS-003"}


# ===========================================================================
# B. POST 端点 ManualNoteBody（monkeypatch append_audit_log）
# ===========================================================================
class TestPostManualNote:
    """POST /api/formula-audit-log/{project_id}/{year}：人工补记。"""

    @pytest.mark.asyncio
    async def test_post_manual_note_payload(self, monkeypatch):
        """用例 4：ManualNoteBody(note='测试补记') → 载荷含 action=manual_note + year。"""
        from app.routers.formula_audit_log import add_audit_log, ManualNoteBody

        captured: list[dict] = []

        async def mock_append(db, payload):
            captured.append(payload)
            return uuid.uuid4()

        # append_audit_log 在函数体内 lazy import —— 要 patch 源模块
        monkeypatch.setattr("app.services.audit_log_helper.append_audit_log", mock_append)

        # 直接调用路由函数（跳过鉴权）
        body = ManualNoteBody(note="测试补记")
        result = await add_audit_log(
            project_id=_PID, year=2025, body=body,
            db=AsyncMock(), current_user=_FakeUser(),
        )
        assert result["ok"] is True
        assert len(captured) == 1
        details = captured[0]["details"]
        assert details["action"] == "manual_note"
        assert details["year"] == "2025"
        assert details["note"] == "测试补记"

    def test_post_rejects_extra_fields(self):
        """用例 5：带 old_formula 字段 → pydantic 422（extra='forbid'）。"""
        from pydantic import ValidationError
        from app.routers.formula_audit_log import ManualNoteBody

        with pytest.raises(ValidationError):
            ManualNoteBody(note="ok", old_formula="EVIL")  # type: ignore[call-arg]

    def test_post_rejects_note_over_500(self):
        """用例 6：note 超 500 字 → pydantic 422。"""
        from pydantic import ValidationError
        from app.routers.formula_audit_log import ManualNoteBody

        with pytest.raises(ValidationError):
            ManualNoteBody(note="x" * 501)


# ===========================================================================
# C. audit_project year 参数
# ===========================================================================
class TestAuditProjectYear:
    """services/formula_settings/audit.py::audit_project 的 year 参数。"""

    @pytest.mark.asyncio
    async def test_audit_project_year_in_payload(self, monkeypatch):
        """用例 7：audit_project(year=2025) 载荷含 year: '2025'。"""
        from app.services.formula_settings.audit import audit_project

        captured: list[dict] = []

        async def mock_append(db, payload):
            captured.append(payload)
            return uuid.uuid4()

        monkeypatch.setattr("app.services.formula_settings.audit.append_audit_log", mock_append)

        await audit_project(
            None,  # type: ignore[arg-type]
            user_id=_UID,
            project_id=uuid.UUID(_PID),
            domain="report",
            action="sync_global",
            source="test",
            changes=[{"slot_key": "BS:BS-001", "old_formula": "", "new_formula": "TB('1001')"}],
            year=2025,
        )
        assert len(captured) == 1
        assert captured[0]["details"]["year"] == "2025"

    @pytest.mark.asyncio
    async def test_audit_project_no_year_resolves_project_year(self, monkeypatch):
        """D-1：调用方不传 year ⇒ 按项目审计年度补齐（全部生产调用方都不传）。"""
        from app.services.formula_settings.audit import audit_project

        captured: list[dict] = []

        async def mock_append(db, payload):
            captured.append(payload)
            return uuid.uuid4()

        async def mock_year(db, project_id, requested_year=None):
            assert str(project_id) == _PID
            return 2024

        monkeypatch.setattr("app.services.formula_settings.audit.append_audit_log", mock_append)
        monkeypatch.setattr("app.services.project_audit_year.resolve_project_audit_year_for_request", mock_year)
        await audit_project(
            None,  # type: ignore[arg-type]
            user_id=_UID,
            project_id=uuid.UUID(_PID),
            domain="report",
            action="sync_global",
            source="test",
            changes=[{"slot_key": "BS:BS-001", "old_formula": "", "new_formula": "TB('1001')"}],
        )
        assert len(captured) == 1
        assert captured[0]["details"]["year"] == "2024"

    @pytest.mark.asyncio
    async def test_audit_project_no_year_no_key(self, monkeypatch):
        """用例 8：调用方不传 year 且项目没有审计年度 ⇒ 载荷无 year 键。"""
        from app.services.formula_settings.audit import audit_project

        captured: list[dict] = []

        async def mock_append(db, payload):
            captured.append(payload)
            return uuid.uuid4()

        async def mock_year(db, project_id, requested_year=None):
            return None

        monkeypatch.setattr("app.services.formula_settings.audit.append_audit_log", mock_append)
        monkeypatch.setattr("app.services.project_audit_year.resolve_project_audit_year_for_request", mock_year)

        await audit_project(
            None,  # type: ignore[arg-type]
            user_id=_UID,
            project_id=uuid.UUID(_PID),
            domain="report",
            action="sync_global",
            source="test",
            changes=[{"slot_key": "BS:BS-001", "old_formula": "", "new_formula": "TB('1001')"}],
        )
        assert len(captured) == 1
        assert "year" not in captured[0]["details"]


# ===========================================================================
# D. write_wp_formula_audit year 参数
# ===========================================================================
class TestWpFormulaAuditYear:
    """routers/wp_formula_audit.py::write_wp_formula_audit 的 year 参数。"""

    @pytest.mark.asyncio
    async def test_wp_audit_year_in_details(self, monkeypatch):
        """用例 9：write_wp_formula_audit(year=2025) details 含 year: '2025'。"""
        from app.routers.wp_formula_audit import write_wp_formula_audit

        captured: list[dict] = []

        async def mock_append(db, payload):
            captured.append(payload)
            return uuid.uuid4()

        # lazy import 在函数体内 —— patch 源模块
        monkeypatch.setattr("app.services.audit_log_helper.append_audit_log", mock_append)

        mock_db = _make_mock_db()

        await write_wp_formula_audit(
            mock_db,
            user=_FakeUser(),  # type: ignore[arg-type]
            project_id=uuid.UUID(_PID),
            wp_code="D1-1",
            target_cell="B5",
            action="update",
            old_formula="100",
            new_formula="200",
            year=2025,
        )
        assert len(captured) == 1
        assert captured[0]["details"]["year"] == "2025"

    @pytest.mark.asyncio
    async def test_wp_audit_no_year_no_key(self, monkeypatch):
        """用例 10：调用方不传 year 且项目没有审计年度 ⇒ details 无 year 键
        （项目有审计年度时按它补齐，见 test_formula_history_year_writers.py 的 ⑨）。"""
        from app.routers.wp_formula_audit import write_wp_formula_audit

        captured: list[dict] = []

        async def mock_append(db, payload):
            captured.append(payload)
            return uuid.uuid4()

        async def mock_year(db, project_id, requested_year=None):
            return None

        monkeypatch.setattr("app.services.audit_log_helper.append_audit_log", mock_append)
        monkeypatch.setattr("app.services.project_audit_year.resolve_project_audit_year_for_request", mock_year)

        mock_db = _make_mock_db()

        await write_wp_formula_audit(
            mock_db,
            user=_FakeUser(),  # type: ignore[arg-type]
            project_id=uuid.UUID(_PID),
            wp_code="D1-1",
            target_cell="B5",
            action="update",
            old_formula="100",
            new_formula="200",
        )
        assert len(captured) == 1
        assert "year" not in captured[0]["details"]
