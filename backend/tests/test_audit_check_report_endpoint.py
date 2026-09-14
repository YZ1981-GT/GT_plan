"""audit-check-review-gate-hardening Task 4.2 — 前端上报端点测试

覆盖 `POST /api/projects/{pid}/workpapers/{wp_id}/audit-checks/report`
（`report_audit_checks`）：
- 正常上报 tb_recon items → 200，`parsed_data.audit_checks` 含项 source=tb_recon
  （补齐 wp_code/wp_id/produced_at；passed 三态保留）
- 同 source 重报 → 覆盖不累积（Property 6）
- 上报其他 S6 source（report_cross_check）不影响已存在的 tb_recon 项
- 后端自算 S1-S5 项在上报后被保留（不动其他 source）
- 上报后端专属 source（cycle_recon/fine_rule）→ 400（契约重点，P12）
- 上报非法 source（garbage）→ 400
- 不存在的 wp_id → 404
- HTTPException 不被通用 except 吞成 500（校验/归属置于 try 外）

直接 `await` 调用端点函数（传 mock db），参照 `test_audit_check_summary_endpoint.py`
的 mock 模式。`flag_modified` 对非 ORM 实例会抛，故 patch 为 no-op。

注：`require_project_access("edit")` 是依赖工厂，直接调用端点函数绕过依赖注入，
无法在此单测层触发 403（属接线层 / 契约测试覆盖，见 Task 5.4）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

import app.routers.audit_check as mod
from app.routers.audit_check import (
    ReportAuditChecksRequest,
    ReportedCheckItem,
    report_audit_checks,
)


# ═══════════════════════════════════════════════════════════════════
# mock 底稿 / 索引 / db
# ═══════════════════════════════════════════════════════════════════

class _WP:
    def __init__(self, parsed_data, wp_id):
        self.id = wp_id
        self.parsed_data = parsed_data
        self.wp_index_id = uuid4()


class _IDX:
    def __init__(self, wp_code):
        self.wp_code = wp_code


def _make_db(first_row):
    """mock AsyncSession：`(await db.execute(...)).first()` 返回给定 row（或 None）。"""
    db = AsyncMock()
    result = MagicMock()
    result.first.return_value = first_row
    db.execute.return_value = result
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


async def _call(wp, idx, source, items, *, project_id=None, wp_id=None):
    db = _make_db((wp, idx) if wp is not None else None)
    body = ReportAuditChecksRequest(
        source=source,
        items=[ReportedCheckItem(**it) for it in items],
    )
    with patch.object(mod, "flag_modified", lambda *a, **k: None):
        result = await report_audit_checks(
            project_id=project_id or uuid4(),
            wp_id=wp_id or (wp.id if wp is not None else uuid4()),
            body=body,
            db=db,
            current_user=None,
        )
    return result, db


def _item(code, **kw):
    base = {"code": code, "severity": "warning", "check_type": "reconciliation",
            "message": "", "passed": True}
    base.update(kw)
    return base


# ═══════════════════════════════════════════════════════════════════
# 正常上报（补齐归属 + passed 三态）
# ═══════════════════════════════════════════════════════════════════

class TestNormalReport:
    @pytest.mark.asyncio
    async def test_report_tb_recon_upserts_items(self):
        wp_id = uuid4()
        wp = _WP({}, wp_id)
        idx = _IDX("E1")
        result, db = await _call(
            wp, idx, "tb_recon",
            [_item("E1-TB", passed=False, actual=100.0, expected=90.0, diff=10.0,
                   sheet_hint="E1-1")],
        )
        assert result["reported"] == 1
        assert result["source"] == "tb_recon"
        assert result["total_checks"] == 1

        checks = wp.parsed_data["audit_checks"]
        assert len(checks) == 1
        c = checks[0]
        assert c["source"] == "tb_recon"
        assert c["wp_code"] == "E1"          # 从 idx 补齐
        assert c["wp_id"] == str(wp_id)      # 服务端补齐
        assert c["produced_at"]              # 非空 ISO
        assert c["passed"] is False          # 三态保留
        assert c["actual"] == 100.0
        assert c["diff"] == 10.0
        assert c["sheet_hint"] == "E1-1"
        # 刷新变更时间（供 stale 新鲜度）
        assert wp.parsed_data["audit_checks_at"]
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_passed_none_preserved(self):
        """passed=None（未覆盖三态）原样保留。"""
        wp = _WP({}, uuid4())
        result, _ = await _call(
            wp, _IDX("K9"), "adjustment_recon", [_item("K9-ADJ", passed=None)]
        )
        assert wp.parsed_data["audit_checks"][0]["passed"] is None

    @pytest.mark.asyncio
    async def test_report_multiple_items_one_source(self):
        wp = _WP({}, uuid4())
        result, _ = await _call(
            wp, _IDX("G7"), "report_cross_check",
            [_item("G7-CC-1"), _item("G7-CC-2", passed=False)],
        )
        assert result["reported"] == 2
        assert result["total_checks"] == 2
        assert all(c["source"] == "report_cross_check"
                   for c in wp.parsed_data["audit_checks"])


# ═══════════════════════════════════════════════════════════════════
# upsert 语义（Property 6：同 source 覆盖不累积 + 不动其他 source）
# ═══════════════════════════════════════════════════════════════════

class TestUpsertSemantics:
    @pytest.mark.asyncio
    async def test_same_source_overwrites_not_accumulate(self):
        """同 source 重报覆盖旧项（不累积）。"""
        wp = _WP(
            {"audit_checks": [
                {"code": "OLD-1", "source": "tb_recon", "wp_code": "E1"},
                {"code": "OLD-2", "source": "tb_recon", "wp_code": "E1"},
            ]},
            uuid4(),
        )
        result, _ = await _call(
            wp, _IDX("E1"), "tb_recon", [_item("NEW-1")]
        )
        checks = wp.parsed_data["audit_checks"]
        assert result["total_checks"] == 1
        assert len(checks) == 1
        assert checks[0]["code"] == "NEW-1"
        assert all(c["code"] != "OLD-1" for c in checks)

    @pytest.mark.asyncio
    async def test_other_s6_source_unaffected(self):
        """上报 report_cross_check 不影响已存在的 tb_recon 项。"""
        wp = _WP(
            {"audit_checks": [
                {"code": "TB-1", "source": "tb_recon", "wp_code": "E1"},
            ]},
            uuid4(),
        )
        result, _ = await _call(
            wp, _IDX("E1"), "report_cross_check", [_item("CC-1")]
        )
        checks = wp.parsed_data["audit_checks"]
        assert result["total_checks"] == 2
        sources = {c["source"] for c in checks}
        assert sources == {"tb_recon", "report_cross_check"}
        # 原 tb_recon 项保留
        assert any(c["code"] == "TB-1" for c in checks)

    @pytest.mark.asyncio
    async def test_backend_computed_sources_preserved(self):
        """上报只清同名 S6 source，后端自算 S1-S5 项一律保留。"""
        wp = _WP(
            {"audit_checks": [
                {"code": "CYC-1", "source": "cycle_recon", "wp_code": "K9"},
                {"code": "FINE-1", "source": "fine_rule", "wp_code": "K9"},
                {"code": "QC-1", "source": "qc", "wp_code": "__PROJECT__"},
                {"code": "TB-OLD", "source": "tb_recon", "wp_code": "K9"},
            ]},
            uuid4(),
        )
        result, _ = await _call(
            wp, _IDX("K9"), "tb_recon", [_item("TB-NEW")]
        )
        checks = wp.parsed_data["audit_checks"]
        codes = {c["code"] for c in checks}
        # S1-S5 全保留 + 新 tb_recon；旧 tb_recon 被覆盖
        assert "CYC-1" in codes
        assert "FINE-1" in codes
        assert "QC-1" in codes
        assert "TB-NEW" in codes
        assert "TB-OLD" not in codes
        assert result["total_checks"] == 4

    @pytest.mark.asyncio
    async def test_none_parsed_data_no_error(self):
        """parsed_data 为 None → 视作空，正常 upsert。"""
        wp = _WP(None, uuid4())
        result, _ = await _call(
            wp, _IDX("D2-1"), "cross_sheet", [_item("CS-1")]
        )
        assert result["total_checks"] == 1
        assert wp.parsed_data["audit_checks"][0]["source"] == "cross_sheet"


# ═══════════════════════════════════════════════════════════════════
# source 契约校验（P12 — 拒绝后端专属 / 非法 source，HTTPException 不被吞）
# ═══════════════════════════════════════════════════════════════════

class TestSourceValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_source", [
        "cycle_recon", "fine_rule", "note_validation", "qc",
        "unadjusted_misstatement",
    ])
    async def test_reject_backend_computed_source(self, bad_source):
        """前端试图伪造后端专属 source → 400（契约重点）。"""
        wp = _WP({}, uuid4())
        with pytest.raises(HTTPException) as ei:
            await _call(wp, _IDX("E1"), bad_source, [_item("X")])
        assert ei.value.status_code == 400
        assert "不支持的上报来源" in ei.value.detail
        # 校验发生在写库前：未提交
        assert wp.parsed_data == {}

    @pytest.mark.asyncio
    async def test_reject_garbage_source(self):
        wp = _WP({}, uuid4())
        with pytest.raises(HTTPException) as ei:
            await _call(wp, _IDX("E1"), "garbage", [_item("X")])
        assert ei.value.status_code == 400
        assert "garbage" in ei.value.detail

    @pytest.mark.asyncio
    async def test_reject_empty_source(self):
        wp = _WP({}, uuid4())
        with pytest.raises(HTTPException) as ei:
            await _call(wp, _IDX("E1"), "", [_item("X")])
        assert ei.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# wp 归属校验（404）
# ═══════════════════════════════════════════════════════════════════

class TestWorkpaperOwnership:
    @pytest.mark.asyncio
    async def test_wp_not_found_404(self):
        """wp 不存在（JOIN 查询无结果）→ 404。"""
        with pytest.raises(HTTPException) as ei:
            await _call(None, None, "tb_recon", [_item("X")])
        assert ei.value.status_code == 404
        assert "底稿不存在" in ei.value.detail
