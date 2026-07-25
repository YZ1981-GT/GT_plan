"""audit-check-review-gate-hardening Task 5.2 — 复核签认端点测试

覆盖 `POST /api/projects/{pid}/audit-checks/signoff`（`create_audit_check_signoff`）
与 `GET .../signoff`（`get_latest_audit_check_signoff`）：
- P10 快照一致：写入的 `summary_snapshot` 与响应 `summary` 均等于当时 `_compute_project_summary`
  的 `to_dict()`。
- P14 有阻断仍可签认：`blocking_open > 0` 时**照常写记录并返回成功**（不 raise），
  `blocking_present=True` + message 含「仅提示」。
- note 可选：传则写入，不传为 None。
- GET 读最近一次：无记录返回 `{signoff: null}`；有则返回该记录字段。

直接 `await` 调用端点函数（传 mock db + patch 两个取数 helper），参照
`test_audit_check_report_endpoint.py` 的 mock 模式。`require_project_access` 是依赖工厂，
直接调用端点绕过依赖注入，403 属契约测试覆盖（见 Task 5.4）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.routers.audit_check as mod
from app.routers.audit_check import (
    SignoffRequest,
    create_audit_check_signoff,
    get_latest_audit_check_signoff,
)
from app.services.audit_check.models import ProjectCheckSummary


# ═══════════════════════════════════════════════════════════════════
# mock 工具
# ═══════════════════════════════════════════════════════════════════

def _make_add_capturing_db():
    """mock AsyncSession：捕获 db.add 的实例，refresh 时补齐 id/signed_at。"""
    captured: dict = {}
    db = AsyncMock()

    def _add(obj):
        captured["signoff"] = obj

    async def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        if getattr(obj, "signed_at", None) is None:
            obj.signed_at = datetime.now(timezone.utc)

    db.add = MagicMock(side_effect=_add)
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=_refresh)
    return db, captured


def _user(username="张三"):
    return SimpleNamespace(id=uuid4(), username=username)


async def _call_signoff(summary, *, year=2025, note=None):
    db, captured = _make_add_capturing_db()
    mod._compute_project_summary = AsyncMock(return_value=summary)
    mod._resolve_project_year = AsyncMock(return_value=year)
    user = _user()
    result = await create_audit_check_signoff(
        project_id=uuid4(),
        body=SignoffRequest(note=note) if note is not None else None,
        db=db,
        current_user=user,
    )
    return result, captured.get("signoff"), db, user


# ═══════════════════════════════════════════════════════════════════
# POST 签认
# ═══════════════════════════════════════════════════════════════════

class TestSignoffCreate:
    @pytest.mark.asyncio
    async def test_snapshot_consistent_with_summary_p10(self):
        """P10：写入 summary_snapshot 与响应 summary 均等于当时 summary.to_dict()。"""
        summary = ProjectCheckSummary(
            total=5, decided=4, passed=3, failed=1, uncovered=1,
            pass_rate=0.75, blocking_open=0,
        )
        result, signoff, db, user = await _call_signoff(summary)

        assert result["summary"] == summary.to_dict()
        assert signoff.summary_snapshot == summary.to_dict()
        assert signoff.signed_by == user.id
        assert signoff.signed_by_name == "张三"
        assert signoff.year == 2025
        assert result["signoff_id"]
        assert result["signed_at"]
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_blocking_present_still_succeeds_p14(self):
        """P14：有未处理阻断项也照常写记录并返回成功（只提示不阻断，不 raise）。"""
        summary = ProjectCheckSummary(
            total=6, decided=5, passed=3, failed=2, uncovered=1,
            pass_rate=0.6, blocking_open=2,
        )
        result, signoff, db, _ = await _call_signoff(summary)

        assert result["blocking_present"] is True
        assert signoff.blocking_present is True
        assert "仅提示" in result["message"]
        # 仍成功写入
        db.add.assert_called_once()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_blocking_success_message(self):
        summary = ProjectCheckSummary(
            total=3, decided=3, passed=3, failed=0, uncovered=0,
            pass_rate=1.0, blocking_open=0,
        )
        result, signoff, _, _ = await _call_signoff(summary)
        assert result["blocking_present"] is False
        assert signoff.blocking_present is False
        assert result["message"] == "签认成功"

    @pytest.mark.asyncio
    async def test_note_optional_present(self):
        summary = ProjectCheckSummary()
        _, signoff, _, _ = await _call_signoff(summary, note="已复核通过")
        assert signoff.note == "已复核通过"

    @pytest.mark.asyncio
    async def test_note_optional_absent(self):
        summary = ProjectCheckSummary()
        _, signoff, _, _ = await _call_signoff(summary, note=None)
        assert signoff.note is None

    @pytest.mark.asyncio
    async def test_year_fallback_when_project_year_none(self):
        """项目无审计年度 → 回退当前自然年（year 列 NOT NULL）。"""
        summary = ProjectCheckSummary()
        result, signoff, _, _ = await _call_signoff(summary, year=None)
        assert signoff.year == datetime.now(timezone.utc).year


# ═══════════════════════════════════════════════════════════════════
# GET 最近签认
# ═══════════════════════════════════════════════════════════════════

def _make_scalar_db(scalar_value):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_value
    db.execute.return_value = result
    return db


class TestSignoffGetLatest:
    @pytest.mark.asyncio
    async def test_no_record_returns_null(self):
        db = _make_scalar_db(None)
        result = await get_latest_audit_check_signoff(
            project_id=uuid4(), db=db, current_user=_user(),
        )
        assert result == {"signoff": None}

    @pytest.mark.asyncio
    async def test_returns_latest_fields(self):
        signed_at = datetime.now(timezone.utc)
        row = SimpleNamespace(
            id=uuid4(),
            signed_by=uuid4(),
            signed_by_name="李四",
            signed_at=signed_at,
            summary_snapshot={"total": 2, "blocking_open": 1},
            blocking_present=True,
            note="存在阻断项已记录",
        )
        db = _make_scalar_db(row)
        result = await get_latest_audit_check_signoff(
            project_id=uuid4(), db=db, current_user=_user(),
        )
        s = result["signoff"]
        assert s["id"] == str(row.id)
        assert s["signed_by"] == str(row.signed_by)
        assert s["signed_by_name"] == "李四"
        assert s["blocking_present"] is True
        assert s["summary_snapshot"] == {"total": 2, "blocking_open": 1}
        assert s["note"] == "存在阻断项已记录"
        assert s["signed_at"]
