"""audit-check-review-gate-hardening Task 5.3 — 审计检查导出端点测试

覆盖 `POST /api/projects/{pid}/audit-checks/export`（`export_audit_checks`）：
- 有数据：返回非空 xlsx 字节（ZIP `PK` 签名）+ Content-Disposition 为 RFC5987 中文名
  （含 `filename*=UTF-8''`）。
- 无数据不报错：导出空模板（表头齐全、无数据行）+ 汇总 decided=0，正常 200。
- 复用 summary 端点的 `_resolve_wp_checks`（audit_checks 优先，退回 legacy fine_checks）。

直接 `await` 调用端点函数（传 mock db + patch `_resolve_project_year`），
参照 `test_audit_check_report_endpoint.py` 的 mock 模式。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.routers.audit_check as mod
from app.routers.audit_check import export_audit_checks


# ═══════════════════════════════════════════════════════════════════
# mock 工具
# ═══════════════════════════════════════════════════════════════════

def _make_export_db(project_row, wp_rows):
    """mock：第一次 execute → 项目名 row（.first）；第二次 → wp rows（.all）。"""
    db = AsyncMock()
    proj_result = MagicMock()
    proj_result.first.return_value = project_row
    wp_result = MagicMock()
    wp_result.all.return_value = wp_rows
    db.execute = AsyncMock(side_effect=[proj_result, wp_result])
    return db


def _check_dict(code, **kw):
    base = {
        "code": code, "type": "reconciliation", "check_type": "reconciliation",
        "severity": "warning", "description": "描述", "passed": True,
        "message": "消息", "source": "cycle_recon",
    }
    base.update(kw)
    return base


async def _read_body(resp) -> bytes:
    chunks = [c async for c in resp.body_iterator]
    return b"".join(c if isinstance(c, bytes) else c.encode("utf-8") for c in chunks)


async def _call_export(project_row, wp_rows, *, year=2025):
    db = _make_export_db(project_row, wp_rows)
    mod._resolve_project_year = AsyncMock(return_value=year)
    resp = await export_audit_checks(
        project_id=uuid4(), db=db, current_user=None,
    )
    return resp


# ═══════════════════════════════════════════════════════════════════
# 有数据导出
# ═══════════════════════════════════════════════════════════════════

class TestExportWithData:
    @pytest.mark.asyncio
    async def test_exports_nonempty_xlsx(self):
        parsed = {
            "audit_checks": [
                _check_dict("E1-01", passed=True),
                _check_dict("E1-02", passed=False, severity="blocking"),
                _check_dict("E1-03", passed=None, severity="info"),
            ]
        }
        wp_rows = [(uuid4(), parsed, "E1", "货币资金")]
        resp = await _call_export(("重药控股安徽项目", "重药控股安徽"), wp_rows)

        assert resp.media_type == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        body = await _read_body(resp)
        assert len(body) > 0
        assert body[:2] == b"PK"  # xlsx = zip 容器签名

    @pytest.mark.asyncio
    async def test_rfc5987_chinese_filename_header(self):
        wp_rows = [(uuid4(), {"audit_checks": [_check_dict("K9-01")]}, "K9", "管理费用")]
        resp = await _call_export(("客户名", "客户名"), wp_rows)

        cd = resp.headers["content-disposition"]
        assert "filename*=UTF-8''" in cd  # RFC5987 编码
        assert 'filename="' in cd          # ASCII 回退名
        # 中文文件名经百分号编码，含"审计检查结果"编码片段
        from urllib.parse import quote
        assert quote("审计检查结果", safe="") in cd

    @pytest.mark.asyncio
    async def test_legacy_fine_checks_fallback(self):
        """无 audit_checks 时退回 legacy fine_checks（补 source=fine_rule），不报错。"""
        parsed = {
            "fine_checks": [
                {"code": "CHK-01", "type": "balance", "severity": "warning",
                 "description": "余额勾稽", "passed": False, "message": "差异"},
            ],
            "fine_extracted_at": "2025-01-01T00:00:00Z",
        }
        wp_rows = [(uuid4(), parsed, "D2", "应收账款")]
        resp = await _call_export(("P", "P"), wp_rows)
        body = await _read_body(resp)
        assert body[:2] == b"PK"


# ═══════════════════════════════════════════════════════════════════
# 无数据导出空模板（不报错）
# ═══════════════════════════════════════════════════════════════════

class TestExportEmpty:
    @pytest.mark.asyncio
    async def test_no_workpapers_empty_template(self):
        """无底稿 → 空模板（表头齐全、无数据行），正常 200 不报错。"""
        resp = await _call_export(("空项目", "空项目"), [])
        body = await _read_body(resp)
        assert body[:2] == b"PK"
        assert len(body) > 0

    @pytest.mark.asyncio
    async def test_workpapers_without_checks_empty_detail(self):
        """底稿存在但无检查项 → 明细为空，仍正常导出。"""
        wp_rows = [(uuid4(), {}, "E1", "货币资金"), (uuid4(), None, "K9", "管理费用")]
        resp = await _call_export(("P", "P"), wp_rows)
        body = await _read_body(resp)
        assert body[:2] == b"PK"

    @pytest.mark.asyncio
    async def test_no_project_row_no_crash(self):
        """项目行查不到（None）→ 文件名回退无项目段，不报错。"""
        resp = await _call_export(None, [])
        body = await _read_body(resp)
        assert body[:2] == b"PK"
        cd = resp.headers["content-disposition"]
        assert "filename*=UTF-8''" in cd
