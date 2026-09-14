"""audit_check 模型层纯函数单测（Task 1.2）

验证：
- ProjectCheckSummary.from_items 通过率口径（分母不含 null/uncovered）
- decided=0 时 pass_rate=None
- from_fine_check_dict 转换补齐 source/wp_code + check_type（type → check_type）
- AuditCheckItem.to_dict 与 legacy fine_checks 项字段超集兼容
- source 子集常量正确划分（后端自算 S1-S5 / 前端可上报 S6）
"""

from app.services.audit_check import (
    ALL_SOURCES,
    BACKEND_COMPUTED_SOURCES,
    FRONTEND_REPORTABLE_SOURCES,
    AuditCheckItem,
    AuditCheckSource,
    ProjectCheckSummary,
    from_fine_check_dict,
)
from app.services.audit_check.models import SEVERITY_BLOCKING, SEVERITY_INFO


def _item(passed, severity=SEVERITY_INFO):
    return AuditCheckItem(
        code="X",
        source=AuditCheckSource.FINE_RULE.value,
        wp_code="D2",
        severity=severity,
        check_type="balance",
        description="d",
        message="m",
        produced_at="2026-07-25T00:00:00",
        passed=passed,
    )


# ── ProjectCheckSummary.from_items 通过率口径 ─────────────────────

def test_pass_rate_denominator_excludes_uncovered():
    """3 通过 / 2 未通过 / 5 未覆盖 → decided=5, pass_rate=0.6，分母不含 null。"""
    items = (
        [_item(True) for _ in range(3)]
        + [_item(False) for _ in range(2)]
        + [_item(None) for _ in range(5)]
    )
    s = ProjectCheckSummary.from_items(items)
    assert s.total == 10
    assert s.passed == 3
    assert s.failed == 2
    assert s.uncovered == 5
    assert s.decided == 5  # 3 + 2，绝不含 5 个未覆盖
    assert s.pass_rate == 0.6  # 3 / 5


def test_pass_rate_none_when_no_decided():
    """decided=0（全未覆盖）时 pass_rate=None，不是 0/绿灯。"""
    items = [_item(None) for _ in range(4)]
    s = ProjectCheckSummary.from_items(items)
    assert s.decided == 0
    assert s.uncovered == 4
    assert s.pass_rate is None


def test_empty_items_summary():
    s = ProjectCheckSummary.from_items([])
    assert s.total == 0
    assert s.decided == 0
    assert s.pass_rate is None
    assert s.blocking_open == 0


def test_blocking_open_counts_only_blocking_failed():
    """blocking_open 只计 severity=blocking 且 passed is False。"""
    items = [
        _item(False, severity=SEVERITY_BLOCKING),   # 计入
        _item(False, severity=SEVERITY_INFO),       # 非 blocking，不计
        _item(True, severity=SEVERITY_BLOCKING),    # 通过，不计
        _item(None, severity=SEVERITY_BLOCKING),    # 未覆盖，不计
    ]
    s = ProjectCheckSummary.from_items(items)
    assert s.blocking_open == 1


def test_all_passed_full_rate():
    items = [_item(True) for _ in range(4)]
    s = ProjectCheckSummary.from_items(items)
    assert s.decided == 4
    assert s.pass_rate == 1.0


# ── from_fine_check_dict 转换 ────────────────────────────────────

def test_from_fine_check_dict_fills_source_and_wp_code():
    legacy = {
        "code": "CHK-01",
        "type": "balance",
        "severity": "blocking",
        "description": "审定表合计 vs 试算平衡表",
        "passed": False,
        "actual": 100.0,
        "expected": 90.0,
        "diff": 10.0,
        "message": "差异 10.00",
    }
    item = from_fine_check_dict(
        legacy, wp_code="E1", wp_id="wp-123", produced_at="2026-07-25T08:00:00"
    )
    # 补齐 source / wp_code / produced_at
    assert item.source == AuditCheckSource.FINE_RULE.value
    assert item.wp_code == "E1"
    assert item.wp_id == "wp-123"
    assert item.produced_at == "2026-07-25T08:00:00"
    # legacy type → check_type
    assert item.check_type == "balance"
    # 其余字段原样带过
    assert item.code == "CHK-01"
    assert item.severity == "blocking"
    assert item.passed is False
    assert item.actual == 100.0
    assert item.expected == 90.0
    assert item.diff == 10.0
    assert item.message == "差异 10.00"


def test_from_fine_check_dict_missing_fields_defaults():
    """缺字段（pending 项常见）安全默认，passed 保留 None。"""
    legacy = {"code": "CHK-12", "type": "aging", "passed": None}
    item = from_fine_check_dict(legacy, wp_code="D2")
    assert item.source == AuditCheckSource.FINE_RULE.value
    assert item.wp_code == "D2"
    assert item.wp_id is None
    assert item.produced_at == ""
    assert item.severity == SEVERITY_INFO
    assert item.check_type == "aging"
    assert item.passed is None
    assert item.actual is None


# ── to_dict 超集兼容 ─────────────────────────────────────────────

def test_to_dict_superset_of_legacy_fine_check():
    """to_dict 输出包含 legacy fine_checks 的全部键（前端统一渲染）。"""
    legacy = {
        "code": "CHK-03",
        "type": "cross_ref",
        "severity": "warning",
        "description": "现金审定 vs 明细合计",
        "passed": True,
        "actual": 5.0,
        "expected": 5.0,
        "diff": 0.0,
        "message": "通过",
    }
    d = from_fine_check_dict(legacy, wp_code="E1", produced_at="t").to_dict()
    legacy_keys = {
        "code", "type", "severity", "description",
        "passed", "actual", "expected", "diff", "message",
    }
    assert legacy_keys.issubset(d.keys())  # 超集
    # legacy type 值保留
    assert d["type"] == "cross_ref"
    # 新增字段也在
    for k in ("source", "check_type", "wp_code", "wp_id", "sheet_hint", "produced_at"):
        assert k in d
    assert d["check_type"] == d["type"] == "cross_ref"


def test_roundtrip_legacy_to_item_to_dict_preserves_verdict():
    legacy = {"code": "C", "type": "balance", "passed": False, "message": "x"}
    d = from_fine_check_dict(legacy, wp_code="D2").to_dict()
    assert d["passed"] is False
    assert d["code"] == "C"


# ── source 子集常量 ──────────────────────────────────────────────

def test_source_subsets_partition():
    """后端自算 与 前端可上报 两子集不相交，并集 = 全部 source。"""
    assert BACKEND_COMPUTED_SOURCES.isdisjoint(FRONTEND_REPORTABLE_SOURCES)
    assert (BACKEND_COMPUTED_SOURCES | FRONTEND_REPORTABLE_SOURCES) == ALL_SOURCES
    # S1-S5 后端自算
    assert AuditCheckSource.FINE_RULE.value in BACKEND_COMPUTED_SOURCES
    assert AuditCheckSource.CYCLE_RECON.value in BACKEND_COMPUTED_SOURCES
    assert AuditCheckSource.QC.value in BACKEND_COMPUTED_SOURCES
    # S6 前端可上报
    assert AuditCheckSource.TB_RECON.value in FRONTEND_REPORTABLE_SOURCES
    assert AuditCheckSource.REPORT_CROSS_CHECK.value in FRONTEND_REPORTABLE_SOURCES
    assert AuditCheckSource.CROSS_SHEET.value in FRONTEND_REPORTABLE_SOURCES
    # 全部合法 source 都是 AuditCheckSource 值
    assert ALL_SOURCES == {s.value for s in AuditCheckSource}
