"""AuditCheckAggregator 项目级来源 S3/S4/S5 单测（Task 4.1）

验证：
- S3 note_validation：validate_all findings/warning_summary → __PROJECT__ 项，
  error→blocking / warning→warning，passed=False，check_type=note。
- S4 qc：各底稿最新 WpQcResult.findings → __PROJECT__ 项，severity 直接对齐，
  passed=False，check_type=qc；无 QC 结果不产项。
- S5 unadjusted_misstatement：有错报→warning/passed=False（含笔数金额）；
  无错报→passed=True 信息项。
- recompute_project 接入三来源 + 某来源抛异常时 fail-open 不影响其余（Property 7）。

三个服务全部 mock，不触库；db 用 AsyncMock（execute 结果按调用序 side_effect）。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.audit_check import AuditCheckAggregator, AuditCheckSource
from app.services.audit_check.aggregator import (
    _build_misstatement_items,
    _build_note_validation_items,
    _build_qc_items,
)
from app.services.audit_check.models import PROJECT_WP_CODE

PRODUCED = "2026-07-25T00:00:00+00:00"


# ═══════════════════════════════════════════
# S3 note_validation
# ═══════════════════════════════════════════

async def test_s3_findings_and_warning_summary(monkeypatch):
    """S3：error finding→blocking，warning_summary 桶→warning，均项目级 passed=False。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator._resolve_template_type",
        AsyncMock(return_value="soe"),
    )

    class _FakeEngine:
        def __init__(self, db):
            pass

        async def validate_all(self, project_id, year, *, template_type="soe"):
            return {
                "findings": [
                    {"note_section": "五、1", "check_type": "cross",
                     "severity": "error", "message": "附注↔报表不一致",
                     "expected_value": 100.0, "actual_value": 90.0},
                ],
                "warning_summary": [
                    {"note_section": "五、2", "check_type": "internal", "count": 3},
                ],
            }

    monkeypatch.setattr(
        "app.services.note_validation_engine.NoteValidationEngine", _FakeEngine)

    items = await _build_note_validation_items(
        MagicMock(), uuid4(), 2025, produced_at=PRODUCED)

    assert len(items) == 2
    err = next(it for it in items if it.code.startswith("NOTE-五、1"))
    assert err.severity == "blocking"
    assert err.passed is False
    assert err.check_type == "note"
    assert err.wp_code == PROJECT_WP_CODE
    assert err.wp_id is None
    assert err.produced_at == PRODUCED
    assert err.expected == 100.0 and err.actual == 90.0
    assert err.sheet_hint == "五、1"

    warn = next(it for it in items if it.code.startswith("NOTE-WARN"))
    assert warn.severity == "warning"
    assert warn.passed is False
    assert "3" in warn.message


async def test_s3_no_findings_empty(monkeypatch):
    """S3：无 findings/warning_summary → 空列表（不产误导性 passed 项）。"""
    monkeypatch.setattr(
        "app.services.audit_check.aggregator._resolve_template_type",
        AsyncMock(return_value="listed"),
    )

    class _FakeEngine:
        def __init__(self, db):
            pass

        async def validate_all(self, project_id, year, *, template_type="soe"):
            return {"findings": [], "warning_summary": []}

    monkeypatch.setattr(
        "app.services.note_validation_engine.NoteValidationEngine", _FakeEngine)

    items = await _build_note_validation_items(
        MagicMock(), uuid4(), 2025, produced_at=PRODUCED)
    assert items == []


# ═══════════════════════════════════════════
# S4 qc
# ═══════════════════════════════════════════

def _db_with_qc(wp_ids, qc_results):
    """构造 db：第 1 次 execute 返 wp_id 行（.all()），第 2 次返 qc 结果（.scalars().all()）。"""
    res_ids = MagicMock()
    res_ids.all.return_value = [(w,) for w in wp_ids]

    res_qc = MagicMock()
    res_qc.scalars.return_value.all.return_value = qc_results

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[res_ids, res_qc])
    return db


async def test_s4_qc_findings_to_project_items():
    """S4：QC finding→项目级项，severity blocking/warning/info 直接对齐，passed=False。"""
    qc1 = SimpleNamespace(findings=[
        {"rule_id": "QC-01", "severity": "blocking", "message": "结论区为空"},
        {"rule_id": "QC-07", "severity": "warning", "message": "审定数差异"},
    ])
    qc2 = SimpleNamespace(findings=[
        {"rule_id": "QC-14", "severity": "info", "message": "编制日期"},
    ])
    db = _db_with_qc([uuid4(), uuid4()], [qc1, qc2])

    items = await _build_qc_items(db, uuid4(), produced_at=PRODUCED)

    assert len(items) == 3
    assert all(it.source == AuditCheckSource.QC.value for it in items)
    assert all(it.wp_code == PROJECT_WP_CODE and it.wp_id is None for it in items)
    assert all(it.check_type == "qc" and it.passed is False for it in items)
    by_code = {it.code: it for it in items}
    assert by_code["QC-01"].severity == "blocking"
    assert by_code["QC-07"].severity == "warning"
    assert by_code["QC-14"].severity == "info"


async def test_s4_no_workpapers_empty():
    """S4：项目无底稿 → 空列表（不查 QC）。"""
    res_ids = MagicMock()
    res_ids.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(return_value=res_ids)

    items = await _build_qc_items(db, uuid4(), produced_at=PRODUCED)
    assert items == []


# ═══════════════════════════════════════════
# S5 unadjusted_misstatement
# ═══════════════════════════════════════════

async def test_s5_with_misstatements_warning(monkeypatch):
    """S5：存在未更正错报 → warning/passed=False，message 含笔数+累计金额。"""
    class _FakeSvc:
        def __init__(self, db):
            pass

        async def list_misstatements(self, project_id, year):
            return [
                SimpleNamespace(misstatement_amount=1000),
                SimpleNamespace(misstatement_amount=500),
            ]

    monkeypatch.setattr(
        "app.services.misstatement_service.UnadjustedMisstatementService", _FakeSvc)

    items = await _build_misstatement_items(
        MagicMock(), uuid4(), 2025, produced_at=PRODUCED)

    assert len(items) == 1
    it = items[0]
    assert it.source == AuditCheckSource.UNADJUSTED_MISSTATEMENT.value
    assert it.severity == "warning"
    assert it.passed is False
    assert it.wp_code == PROJECT_WP_CODE and it.wp_id is None
    assert it.check_type == "misstatement"
    assert "2 笔" in it.message
    assert it.actual == 1500.0


async def test_s5_no_misstatements_passed_info(monkeypatch):
    """S5：无未更正错报 → passed=True 信息项。"""
    class _FakeSvc:
        def __init__(self, db):
            pass

        async def list_misstatements(self, project_id, year):
            return []

    monkeypatch.setattr(
        "app.services.misstatement_service.UnadjustedMisstatementService", _FakeSvc)

    items = await _build_misstatement_items(
        MagicMock(), uuid4(), 2025, produced_at=PRODUCED)

    assert len(items) == 1
    assert items[0].passed is True
    assert items[0].severity == "info"
    assert items[0].code == "UM-NONE"


# ═══════════════════════════════════════════
# recompute_project 接入 + fail-open（Property 7）
# ═══════════════════════════════════════════

def _project_db_no_wp():
    """recompute_project 首个 per-wp 查询返空底稿列表。"""
    res = MagicMock()
    res.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(return_value=res)
    return db


async def test_recompute_project_wires_all_three(monkeypatch):
    """recompute_project 接入 S3/S4/S5 三来源并汇总进 ProjectCheckSummary。"""
    from app.services.audit_check.models import AuditCheckItem

    def _item(code, source, passed, severity="warning"):
        return AuditCheckItem(
            code=code, source=source, wp_code=PROJECT_WP_CODE, wp_id=None,
            severity=severity, check_type="x", description="", message="",
            produced_at=PRODUCED, passed=passed)

    monkeypatch.setattr(
        "app.services.audit_check.aggregator._build_note_validation_items",
        AsyncMock(return_value=[
            _item("NOTE-1", AuditCheckSource.NOTE_VALIDATION.value, False, "blocking")]))
    monkeypatch.setattr(
        "app.services.audit_check.aggregator._build_qc_items",
        AsyncMock(return_value=[
            _item("QC-01", AuditCheckSource.QC.value, False, "blocking")]))
    monkeypatch.setattr(
        "app.services.audit_check.aggregator._build_misstatement_items",
        AsyncMock(return_value=[
            _item("UM-NONE", AuditCheckSource.UNADJUSTED_MISSTATEMENT.value, True, "info")]))

    db = _project_db_no_wp()
    summary = await AuditCheckAggregator().recompute_project(db, uuid4(), 2025)

    # 1 passed(UM-NONE) + 2 failed(NOTE/QC) = decided 3
    assert summary.total == 3
    assert summary.passed == 1
    assert summary.failed == 2
    assert summary.decided == 3
    assert summary.blocking_open == 2  # NOTE + QC 均 blocking 且 passed False


async def test_recompute_project_fail_open_one_source(monkeypatch):
    """S4 抛异常时被隔离，S3/S5 仍汇入（fail-open，绝不整体抛）。"""
    from app.services.audit_check.models import AuditCheckItem

    def _item(code, source, passed):
        return AuditCheckItem(
            code=code, source=source, wp_code=PROJECT_WP_CODE, wp_id=None,
            severity="warning", check_type="x", description="", message="",
            produced_at=PRODUCED, passed=passed)

    monkeypatch.setattr(
        "app.services.audit_check.aggregator._build_note_validation_items",
        AsyncMock(return_value=[
            _item("NOTE-1", AuditCheckSource.NOTE_VALIDATION.value, False)]))
    monkeypatch.setattr(
        "app.services.audit_check.aggregator._build_qc_items",
        AsyncMock(side_effect=RuntimeError("qc boom")))
    monkeypatch.setattr(
        "app.services.audit_check.aggregator._build_misstatement_items",
        AsyncMock(return_value=[
            _item("UM-SUMMARY", AuditCheckSource.UNADJUSTED_MISSTATEMENT.value, False)]))

    db = _project_db_no_wp()
    summary = await AuditCheckAggregator().recompute_project(db, uuid4(), 2025)

    # S4 异常被隔离，S3 + S5 各 1 项仍产出（不整体抛）
    assert summary.total == 2
    assert summary.failed == 2
