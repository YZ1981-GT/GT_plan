"""audit-check-review-gate-hardening Task 2.3 — summary 端点测试

覆盖 `GET /api/projects/{pid}/audit-checks/summary`（`get_audit_checks_summary`）：
- 新字段 `audit_checks` 优先（P13 优先分支）
- 无 `audit_checks` 退回 legacy `fine_checks` 补 `source=fine_rule`（P13 / Req10.4）
- 新鲜度 stale 判定（P3 / Req1.2）：updated_at 晚于 checked_at → stale=true
- never_checked（Req1.3）：无 checked_at
- 项目汇总通过率分母不含 null（P1 / Req5.2）
- 未检查底稿不计通过率（P4 / Req5.1）
- 返回结构字段齐全（Req1.4 / 5.3）
- 时区/字符串比较稳健：解析失败按未过期处理不报错

直接 `await` 调用端点函数（传 mock db），参照 `test_audit_check_characterization.py`
的 `_make_summary_db` mock 模式（`db.execute(...).all()` 返回给定 rows）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.routers.audit_check import get_audit_checks_summary


# ═══════════════════════════════════════════════════════════════════
# mock db（对齐 summary 端点 select 列顺序）
# ═══════════════════════════════════════════════════════════════════

def _make_db(rows: list[tuple]):
    """mock AsyncSession，`db.execute(...)` 的 .all() 返回给定 rows。

    每 row 为 6-tuple：
      (wp_id, parsed_data, updated_at, wp_code, wp_name, audit_cycle)
    —— 对齐 `get_audit_checks_summary` 内部解包顺序。
    """
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute.return_value = result
    return db


async def _call(rows):
    db = _make_db(rows)
    return await get_audit_checks_summary(
        project_id=uuid4(), db=db, current_user=None
    )


def _now():
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════
# 新字段 audit_checks 优先（P13 优先分支）
# ═══════════════════════════════════════════════════════════════════

class TestAuditChecksPreferred:
    @pytest.mark.asyncio
    async def test_audit_checks_used_when_present(self):
        """含 audit_checks（新字段）时直接使用，不读 fine_checks。"""
        wp_id = uuid4()
        checked = _now().isoformat()
        pd = {
            "audit_checks": [
                {"code": "K9-RECON-TB", "source": "cycle_recon", "wp_code": "K9",
                 "severity": "blocking", "check_type": "reconciliation",
                 "passed": True, "message": "审定↔TB 一致", "produced_at": checked},
            ],
            "audit_checks_at": checked,
            # 同时存在 legacy fine_checks（应被忽略）
            "fine_checks": [{"code": "K9-CHK-99", "passed": False, "severity": "blocking"}],
        }
        rows = [(wp_id, pd, _now(), "K9", "管理费用", "K")]
        result = await _call(rows)

        wp = result["workpapers"][0]
        assert len(wp["checks"]) == 1
        assert wp["checks"][0]["code"] == "K9-RECON-TB"
        assert wp["checks"][0]["source"] == "cycle_recon"
        # summary 只统计 audit_checks（1 项 passed）
        assert result["summary"]["decided"] == 1
        assert result["summary"]["passed"] == 1

    @pytest.mark.asyncio
    async def test_empty_audit_checks_list_preferred_over_fine(self):
        """audit_checks 为空列表也视为新字段分支（不退回 fine_checks）。"""
        wp_id = uuid4()
        pd = {
            "audit_checks": [],
            "fine_checks": [{"code": "X-CHK-01", "passed": False, "severity": "blocking"}],
        }
        rows = [(wp_id, pd, _now(), "X", "某底稿", "X")]
        result = await _call(rows)
        assert result["workpapers"][0]["checks"] == []
        assert result["summary"]["total"] == 0


# ═══════════════════════════════════════════════════════════════════
# 退回 legacy fine_checks（P13 / Req10.4）
# ═══════════════════════════════════════════════════════════════════

class TestLegacyFallback:
    @pytest.mark.asyncio
    async def test_fallback_to_fine_checks_with_source_fine_rule(self):
        """无 audit_checks → 退回 fine_checks，补 source=fine_rule + wp_code + produced_at。"""
        wp_id = uuid4()
        extracted = _now().isoformat()
        pd = {
            "fine_checks": [
                {"code": "E1-CHK-01", "type": "balance", "severity": "blocking",
                 "passed": True, "message": "审定↔试算表一致"},
            ],
            "fine_extracted_at": extracted,
        }
        rows = [(wp_id, pd, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)

        chk = result["workpapers"][0]["checks"][0]
        assert chk["source"] == "fine_rule"
        assert chk["wp_code"] == "E1"
        assert chk["wp_id"] == str(wp_id)
        assert chk["produced_at"] == extracted
        # legacy type → check_type（超集）
        assert chk["check_type"] == "balance"
        assert chk["type"] == "balance"
        assert result["summary"]["passed"] == 1

    @pytest.mark.asyncio
    async def test_no_fields_at_all_empty_checks_no_error(self):
        """既无 audit_checks 也无 fine_checks（parsed_data 空）→ checks=[] 不报错。"""
        wp_id = uuid4()
        rows = [(wp_id, {}, _now(), "D2", "应收账款", "D")]
        result = await _call(rows)
        assert result["workpapers"][0]["checks"] == []

    @pytest.mark.asyncio
    async def test_parsed_data_none_no_error(self):
        """parsed_data 为 None（pd = parsed_data or {}）→ 不报错。"""
        wp_id = uuid4()
        rows = [(wp_id, None, _now(), "D2", "应收账款", "D")]
        result = await _call(rows)
        assert result["workpapers"][0]["checks"] == []
        assert result["workpapers"][0]["never_checked"] is True


# ═══════════════════════════════════════════════════════════════════
# 新鲜度：stale / never_checked（P3 / Req1.2-1.4）
# ═══════════════════════════════════════════════════════════════════

class TestFreshness:
    @pytest.mark.asyncio
    async def test_stale_when_updated_after_checked(self):
        """updated_at 晚于 checked_at → stale=true。"""
        wp_id = uuid4()
        checked = _now() - timedelta(hours=2)
        updated = _now()
        pd = {"audit_checks": [], "audit_checks_at": checked.isoformat()}
        rows = [(wp_id, pd, updated, "E1", "货币资金", "E")]
        result = await _call(rows)
        wp = result["workpapers"][0]
        assert wp["stale"] is True
        assert wp["never_checked"] is False

    @pytest.mark.asyncio
    async def test_not_stale_when_checked_after_updated(self):
        """checked_at 晚于 updated_at → stale=false。"""
        wp_id = uuid4()
        updated = _now() - timedelta(hours=2)
        checked = _now()
        pd = {"audit_checks": [], "audit_checks_at": checked.isoformat()}
        rows = [(wp_id, pd, updated, "E1", "货币资金", "E")]
        result = await _call(rows)
        assert result["workpapers"][0]["stale"] is False

    @pytest.mark.asyncio
    async def test_never_checked_when_no_checked_at(self):
        """无 audit_checks_at / fine_extracted_at → never_checked=true, stale=false。"""
        wp_id = uuid4()
        rows = [(wp_id, {}, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        wp = result["workpapers"][0]
        assert wp["never_checked"] is True
        assert wp["stale"] is False
        assert wp["checked_at"] is None

    @pytest.mark.asyncio
    async def test_checked_at_falls_back_to_fine_extracted_at(self):
        """无 audit_checks_at 时 checked_at 取 legacy fine_extracted_at。"""
        wp_id = uuid4()
        extracted = (_now() - timedelta(hours=1)).isoformat()
        pd = {"fine_checks": [], "fine_extracted_at": extracted}
        rows = [(wp_id, pd, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        wp = result["workpapers"][0]
        assert wp["checked_at"] == extracted
        assert wp["never_checked"] is False
        assert wp["stale"] is True  # updated(now) > checked(1h ago)

    @pytest.mark.asyncio
    async def test_unparseable_checked_at_not_stale_no_error(self):
        """checked_at 非法字符串 → 解析失败按未过期处理（stale=false），不报错。"""
        wp_id = uuid4()
        pd = {"audit_checks": [], "audit_checks_at": "not-a-date"}
        rows = [(wp_id, pd, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        wp = result["workpapers"][0]
        assert wp["stale"] is False
        # checked_at 非空 → never_checked=false（曾检查，仅无法解析）
        assert wp["never_checked"] is False

    @pytest.mark.asyncio
    async def test_naive_updated_at_treated_utc(self):
        """naive updated_at（无 tzinfo）视为 UTC，与 aware checked_at 比较不抛。"""
        wp_id = uuid4()
        checked = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        naive_updated = datetime.utcnow()  # naive
        pd = {"audit_checks": [], "audit_checks_at": checked}
        rows = [(wp_id, pd, naive_updated, "E1", "货币资金", "E")]
        result = await _call(rows)
        assert result["workpapers"][0]["stale"] is True

    @pytest.mark.asyncio
    async def test_z_suffix_checked_at_parsed(self):
        """末尾 Z 的 ISO 时间可解析（3.11 前 fromisoformat 不识别 Z）。"""
        wp_id = uuid4()
        checked = "2020-01-01T00:00:00Z"
        pd = {"audit_checks": [], "audit_checks_at": checked}
        rows = [(wp_id, pd, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        wp = result["workpapers"][0]
        assert wp["stale"] is True  # now >> 2020
        assert wp["never_checked"] is False


# ═══════════════════════════════════════════════════════════════════
# 项目汇总口径（P1 通过率分母不含 null / P4 未检查底稿不计）
# ═══════════════════════════════════════════════════════════════════

class TestProjectSummary:
    @pytest.mark.asyncio
    async def test_pass_rate_denominator_excludes_null(self):
        """pass_rate 分母 = decided（passed 非 null），uncovered(null) 不进分母/分子。"""
        wp_id = uuid4()
        pd = {
            "audit_checks": [
                {"code": "C1", "source": "cycle_recon", "wp_code": "E1",
                 "severity": "info", "check_type": "reconciliation",
                 "passed": True, "message": "", "produced_at": ""},
                {"code": "C2", "source": "cycle_recon", "wp_code": "E1",
                 "severity": "info", "check_type": "reconciliation",
                 "passed": False, "message": "", "produced_at": ""},
                {"code": "C3", "source": "cycle_recon", "wp_code": "E1",
                 "severity": "info", "check_type": "reconciliation",
                 "passed": None, "message": "", "produced_at": ""},
            ],
            "audit_checks_at": _now().isoformat(),
        }
        rows = [(wp_id, pd, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        s = result["summary"]
        assert s["total"] == 3
        assert s["decided"] == 2  # passed True + False
        assert s["passed"] == 1
        assert s["failed"] == 1
        assert s["uncovered"] == 1
        assert s["pass_rate"] == 0.5  # 1/2，分母不含 null

    @pytest.mark.asyncio
    async def test_uncovered_workpaper_not_counted(self):
        """未检查底稿（无 checks）不贡献任何 check 项到通过率（P4）。"""
        wp1, wp2 = uuid4(), uuid4()
        pd1 = {
            "audit_checks": [
                {"code": "A", "source": "cycle_recon", "wp_code": "K9",
                 "severity": "info", "check_type": "reconciliation",
                 "passed": True, "message": "", "produced_at": ""},
            ],
            "audit_checks_at": _now().isoformat(),
        }
        rows = [
            (wp1, pd1, _now(), "K9", "管理费用", "K"),
            (wp2, {}, _now(), "K10", "其他收益", "K"),  # 未检查底稿
        ]
        result = await _call(rows)
        s = result["summary"]
        assert s["total"] == 1  # 只有 wp1 的 1 项
        assert s["decided"] == 1
        assert s["pass_rate"] == 1.0
        # wp2 仍出现在 workpapers（never_checked），但不计入汇总
        assert len(result["workpapers"]) == 2
        wp2_entry = next(w for w in result["workpapers"] if w["wp_id"] == str(wp2))
        assert wp2_entry["checks"] == []
        assert wp2_entry["never_checked"] is True

    @pytest.mark.asyncio
    async def test_blocking_open_counted(self):
        """blocking_open = severity=blocking 且 passed=false 的计数。"""
        wp_id = uuid4()
        pd = {
            "audit_checks": [
                {"code": "B1", "source": "cycle_recon", "wp_code": "E1",
                 "severity": "blocking", "check_type": "reconciliation",
                 "passed": False, "message": "", "produced_at": ""},
                {"code": "B2", "source": "cycle_recon", "wp_code": "E1",
                 "severity": "blocking", "check_type": "reconciliation",
                 "passed": True, "message": "", "produced_at": ""},
            ],
            "audit_checks_at": _now().isoformat(),
        }
        rows = [(wp_id, pd, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        assert result["summary"]["blocking_open"] == 1

    @pytest.mark.asyncio
    async def test_empty_project_zero_summary(self):
        """项目无底稿 → summary 全零，pass_rate=None，workpapers=[]。"""
        result = await _call([])
        s = result["summary"]
        assert s["total"] == 0
        assert s["decided"] == 0
        assert s["pass_rate"] is None
        assert result["workpapers"] == []


# ═══════════════════════════════════════════════════════════════════
# 返回结构字段齐全（Req1.4 / 5.3）
# ═══════════════════════════════════════════════════════════════════

class TestResponseShape:
    @pytest.mark.asyncio
    async def test_workpaper_entry_fields_complete(self):
        wp_id = uuid4()
        rows = [(wp_id, {}, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        wp = result["workpapers"][0]
        assert set(wp.keys()) == {
            "wp_id", "wp_code", "wp_name", "audit_cycle", "checks",
            "checked_at", "updated_at", "stale", "never_checked",
        }
        assert wp["wp_id"] == str(wp_id)
        assert wp["wp_code"] == "E1"
        assert wp["wp_name"] == "货币资金"
        assert wp["audit_cycle"] == "E"

    @pytest.mark.asyncio
    async def test_summary_fields_complete(self):
        rows = [(uuid4(), {}, _now(), "E1", "货币资金", "E")]
        result = await _call(rows)
        assert set(result.keys()) == {"summary", "workpapers"}
        assert set(result["summary"].keys()) == {
            "total", "decided", "passed", "failed",
            "uncovered", "pass_rate", "blocking_open",
        }
