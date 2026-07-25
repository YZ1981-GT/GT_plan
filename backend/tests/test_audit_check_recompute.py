# -*- coding: utf-8 -*-
"""audit-check-review-gate-hardening Task 3.2 — recompute 端点测试

覆盖 `POST /api/projects/{pid}/audit-checks/recompute`（`recompute_audit_checks`）：
- 带 wp_id → 先查 wp+idx 后调 `AuditCheckAggregator.recompute_workpaper`（单张）
- 不带 wp_id → 遍历项目底稿逐张 `recompute_workpaper`（Req2.4 端点层收集失败明细）
- 单张失败不阻断其余（Req2.4）：一张抛异常 → 记入 failed，其余仍重算，端点仍返回
- `db.commit()` 被调用（持久化，参照 fine-extract commit 模式）
- 并发去重/幂等（Req2.3）：进行中重复触发返回 status=in_progress
- 权限依赖为编制级（Req2.5）：`require_project_access("edit")`（闭包捕获 min_permission）
- 非法/不存在 wp_id → 400/404

直接 `await` 调用端点函数（mock db + patch 聚合器/年度/汇总辅助），参照
`test_audit_check_summary_endpoint.py` 的 mock 模式。
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers import audit_check as ac
from app.routers.audit_check import (
    RecomputeRequest,
    recompute_audit_checks,
    router,
    _recompute_in_progress,
)
from app.services.audit_check.models import ProjectCheckSummary


# ═══════════════════════════════════════════════════════════════════
# mock 工具
# ═══════════════════════════════════════════════════════════════════

class _Result:
    """轻量 result stub：.first() / .all()。"""

    def __init__(self, first=None, all_rows=None):
        self._first = first
        self._all = all_rows or []

    def first(self):
        return self._first

    def all(self):
        return self._all


def _make_db(result: _Result) -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return db


def _wp(wp_id=None):
    return SimpleNamespace(id=wp_id or uuid4())


def _idx(wp_code="D2"):
    return SimpleNamespace(wp_code=wp_code)


def _patches(agg):
    """统一 patch 聚合器 + 年度解析 + 项目汇总（后二者不触 db）。"""
    return (
        patch.object(ac, "AuditCheckAggregator", return_value=agg),
        patch.object(ac, "_resolve_project_year", AsyncMock(return_value=2025)),
        patch.object(
            ac, "_compute_project_summary",
            AsyncMock(return_value=ProjectCheckSummary()),
        ),
    )


# ═══════════════════════════════════════════════════════════════════
# 单张：带 wp_id → recompute_workpaper（先查 wp+idx）
# ═══════════════════════════════════════════════════════════════════

class TestSingleWorkpaper:
    @pytest.mark.asyncio
    async def test_single_wp_calls_recompute_workpaper(self):
        wp_id = uuid4()
        wp, idx = _wp(wp_id), _idx("D2")
        db = _make_db(_Result(first=(wp, idx)))
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(return_value=[])

        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            resp = await recompute_audit_checks(
                project_id=uuid4(),
                body=RecomputeRequest(wp_id=str(wp_id)),
                db=db, current_user=None,
            )

        # 调 recompute_workpaper 一次，且传入查出的 wp/idx + year
        agg.recompute_workpaper.assert_awaited_once()
        args, kwargs = agg.recompute_workpaper.call_args
        assert args[1] is wp and args[2] is idx
        assert kwargs["year"] == 2025

        assert resp["status"] == "completed"
        assert resp["recomputed"] == 1
        assert resp["failed"] == []
        assert "summary" in resp
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_single_wp_failure_recorded_not_raised(self):
        """单张重算异常 → 记入 failed（不抛），仍 commit + 返回。"""
        wp_id = uuid4()
        wp, idx = _wp(wp_id), _idx("K9")
        db = _make_db(_Result(first=(wp, idx)))
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(side_effect=RuntimeError("规则缺失"))

        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            resp = await recompute_audit_checks(
                project_id=uuid4(),
                body=RecomputeRequest(wp_id=str(wp_id)),
                db=db, current_user=None,
            )

        assert resp["recomputed"] == 0
        assert len(resp["failed"]) == 1
        assert resp["failed"][0]["wp_code"] == "K9"
        assert resp["failed"][0]["reason"] == "规则缺失"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_wp_id_returns_400(self):
        db = _make_db(_Result())
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(return_value=[])
        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            with pytest.raises(HTTPException) as ei:
                await recompute_audit_checks(
                    project_id=uuid4(),
                    body=RecomputeRequest(wp_id="not-a-uuid"),
                    db=db, current_user=None,
                )
        assert ei.value.status_code == 400

    @pytest.mark.asyncio
    async def test_wp_not_found_returns_404(self):
        db = _make_db(_Result(first=None))
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(return_value=[])
        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            with pytest.raises(HTTPException) as ei:
                await recompute_audit_checks(
                    project_id=uuid4(),
                    body=RecomputeRequest(wp_id=str(uuid4())),
                    db=db, current_user=None,
                )
        assert ei.value.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 全部：不带 wp_id → 遍历逐张 recompute_workpaper
# ═══════════════════════════════════════════════════════════════════

class TestAllWorkpapers:
    @pytest.mark.asyncio
    async def test_all_recomputes_each_workpaper(self):
        rows = [(_wp(), _idx("D2")), (_wp(), _idx("E1")), (_wp(), _idx("K9"))]
        db = _make_db(_Result(all_rows=rows))
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(return_value=[])

        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            resp = await recompute_audit_checks(
                project_id=uuid4(), body=None, db=db, current_user=None,
            )

        assert agg.recompute_workpaper.await_count == 3
        assert resp["recomputed"] == 3
        assert resp["failed"] == []
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_body_omitted_treated_as_all(self):
        """body=None（不带 wp_id）视为项目全部重算。"""
        rows = [(_wp(), _idx("D2"))]
        db = _make_db(_Result(all_rows=rows))
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(return_value=[])
        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            resp = await recompute_audit_checks(
                project_id=uuid4(), body=None, db=db, current_user=None,
            )
        assert resp["recomputed"] == 1

    @pytest.mark.asyncio
    async def test_single_failure_not_block_others(self):
        """全项目重算：中间一张失败 → 记 failed，其余仍成功，端点仍返回并 commit（Req2.4）。"""
        wp1, wp2, wp3 = _wp(), _wp(), _wp()
        idx1, idx2, idx3 = _idx("D2"), _idx("E1"), _idx("K9")
        db = _make_db(_Result(all_rows=[(wp1, idx1), (wp2, idx2), (wp3, idx3)]))

        async def _side(db_, wp, idx, *, year):
            if wp is wp2:
                raise RuntimeError("文件缺失")
            return []

        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(side_effect=_side)

        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            resp = await recompute_audit_checks(
                project_id=uuid4(), body=None, db=db, current_user=None,
            )

        assert resp["recomputed"] == 2               # wp1 + wp3 成功
        assert len(resp["failed"]) == 1              # wp2 失败
        assert resp["failed"][0]["wp_code"] == "E1"
        assert resp["failed"][0]["reason"] == "文件缺失"
        assert agg.recompute_workpaper.await_count == 3  # 三张都尝试（失败不中断）
        db.commit.assert_awaited_once()              # 仍 commit


# ═══════════════════════════════════════════════════════════════════
# 并发去重/幂等（Req2.3）
# ═══════════════════════════════════════════════════════════════════

class TestConcurrencyDedup:
    @pytest.mark.asyncio
    async def test_in_progress_returns_in_progress_status(self):
        pid = uuid4()
        _recompute_in_progress.add(str(pid))
        try:
            resp = await recompute_audit_checks(
                project_id=pid, body=None, db=AsyncMock(), current_user=None,
            )
            assert resp["status"] == "in_progress"
            assert resp["recomputed"] == 0
            assert resp["summary"] is None
        finally:
            _recompute_in_progress.discard(str(pid))

    @pytest.mark.asyncio
    async def test_in_progress_flag_cleared_after_completion(self):
        """完成后进行中标志被清除（finally），可再次触发。"""
        pid = uuid4()
        rows = [(_wp(), _idx("D2"))]
        db = _make_db(_Result(all_rows=rows))
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(return_value=[])
        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            await recompute_audit_checks(
                project_id=pid, body=None, db=db, current_user=None,
            )
        assert str(pid) not in _recompute_in_progress

    @pytest.mark.asyncio
    async def test_in_progress_flag_cleared_after_error(self):
        """内部异常（404）后仍清除进行中标志（finally）。"""
        pid = uuid4()
        db = _make_db(_Result(first=None))
        agg = MagicMock()
        agg.recompute_workpaper = AsyncMock(return_value=[])
        p1, p2, p3 = _patches(agg)
        with p1, p2, p3:
            with pytest.raises(HTTPException):
                await recompute_audit_checks(
                    project_id=pid,
                    body=RecomputeRequest(wp_id=str(uuid4())),
                    db=db, current_user=None,
                )
        assert str(pid) not in _recompute_in_progress


# ═══════════════════════════════════════════════════════════════════
# 权限门控（Req2.5）：编制级 require_project_access("edit")
# ═══════════════════════════════════════════════════════════════════

class TestPermissionGate:
    def test_recompute_uses_require_project_access(self):
        sig = inspect.signature(recompute_audit_checks)
        assert "current_user" in sig.parameters
        dep = sig.parameters["current_user"].default
        assert dep is not None and hasattr(dep, "dependency")

    def test_recompute_permission_level_is_edit(self):
        """真实验证权限级别为 edit（编制权）：闭包捕获的 min_permission，非仅源码匹配。"""
        sig = inspect.signature(recompute_audit_checks)
        dep = sig.parameters["current_user"].default
        inner = dep.dependency
        freevars = inner.__code__.co_freevars
        assert "min_permission" in freevars
        idx = freevars.index("min_permission")
        captured = inner.__closure__[idx].cell_contents
        assert captured == "edit", f"recompute 权限应为 edit，实际 {captured!r}"

    def test_recompute_edit_higher_than_readonly(self):
        """交叉验证：edit 高于 readonly（写操作门槛），且源码绑定 edit 未放宽。"""
        from app.deps import PERMISSION_HIERARCHY

        assert PERMISSION_HIERARCHY["edit"] > PERMISSION_HIERARCHY["readonly"]
        src = inspect.getsource(recompute_audit_checks)
        assert 'require_project_access("edit")' in src
        assert 'require_project_access("readonly")' not in src

    def test_recompute_route_is_post(self):
        route = next(
            r for r in router.routes
            if getattr(r, "path", "")
            == "/api/projects/{project_id}/audit-checks/recompute"
        )
        assert route.methods == {"POST"}
