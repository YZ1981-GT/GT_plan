"""Task 12.2 — 导入服务 label 匹配 单元测试。

验证 D2-2/D3-2/F1-2 + 工厂(K1-2/K3-2/G5-2) 导入按账龄 label 匹配当前项目配置，
写入 nested keyed 结构（agingPrior/agingCurrent/agingAudited），
不匹配的账龄列报 warning 并跳过，且 export→import 往返一致。

Feature: aging-config-enhancement, Property 13: Import label matching maps correctly

Validates: Requirements 8.2, 8.3, 8.4
"""
from __future__ import annotations

from app.services.aging_config_service import (
    AgingPreset,
    resolve_segments,
)
from app.routers.wp_render_strategies._cycle_import_export_common import (
    aging_export_values,
    build_aging_headers,
    match_import_aging,
    subject_aging_periods,
)
from app.routers.wp_render_strategies._d2_import_export import (
    _d2_2_export_values,
    _d2_2_skipped_aging_columns,
    _parse_d2_2_rows,
    get_d2_2_columns,
)
from app.routers.wp_render_strategies._d3_import_export import (
    _d3_2_dynamic_headers,
    _export_d3_2_row_dynamic,
    _parse_d3_2_row,
)

FIVE = resolve_segments(AgingPreset.FIVE_YEAR, None)   # 6 段
THREE = resolve_segments(AgingPreset.THREE_YEAR, None)  # 4 段

_LEGACY_FLAT_KEYS = {
    "priorAging1Year", "priorAging1to2", "priorAging2to3", "priorAging3to4",
    "priorAging4to5", "priorAgingOver5",
    "currentAging1Year", "currentAging1to2", "currentAging2to3", "currentAging3to4",
    "currentAging4to5", "currentAgingOver5",
    "auditedAging1Year", "auditedAging1to2", "auditedAging2to3", "auditedAging3to4",
    "auditedAging4to5", "auditedAgingOver5",
}


# ─── match_import_aging 基础行为 ─────────────────────────────────────────────


def test_match_import_aging_maps_by_label():
    """3-period: 每段按 `{label}({period})` 命中 → nested keyed。"""
    values = {}
    for period in ("期初", "期末未审", "期末审定"):
        for seg in FIVE:
            values[f"{seg.label}({period})"] = 10.0
    aging, unmatched = match_import_aging(
        values.get, list(values.keys()), FIVE, subject_aging_periods("D2"),
    )
    assert set(aging.keys()) == {"agingPrior", "agingCurrent", "agingAudited"}
    for field in aging.values():
        assert set(field.keys()) == {s.key for s in FIVE}
        assert all(v == 10.0 for v in field.values())
    assert unmatched == []


def test_match_import_aging_unmatched_reported_and_skipped():
    """不匹配当前配置的账龄列 → 收集到 unmatched（Requirement 8.3）。"""
    values = {f"{seg.label}(期初)": 5.0 for seg in THREE}
    # 混入一个当前(3年段)不存在的段列头
    values["4-5年(期初)"] = 999.0
    aging, unmatched = match_import_aging(
        values.get, list(values.keys()), THREE, subject_aging_periods("D3"),
    )
    assert "4-5年(期初)" in unmatched
    # 匹配段值正确写入，未匹配段(4-5年)不进 nested
    assert set(aging["agingPrior"].keys()) == {s.key for s in THREE}
    assert 999.0 not in aging["agingPrior"].values()


def test_match_import_aging_old_template_missing_columns_zero_init():
    """配置从 3 段变到 5 段后导入旧模板 → 缺列段初始化 0（Requirement 8.4）。"""
    # 旧模板只含 3年段列头
    values = {f"{seg.label}(期初)": 3.0 for seg in THREE}
    values.update({f"{seg.label}(期末未审)": 3.0 for seg in THREE})
    values.update({f"{seg.label}(期末审定)": 3.0 for seg in THREE})
    aging, unmatched = match_import_aging(
        values.get, list(values.keys()), FIVE, subject_aging_periods("D2"),
    )
    # 新配置(5段)每 period 都有 6 键，缺列(3-4/4-5/5年以上)为 0
    for field in aging.values():
        assert set(field.keys()) == {s.key for s in FIVE}
    assert aging["agingPrior"]["y3to4"] == 0.0
    assert aging["agingPrior"]["within1"] == 3.0


# ─── D2-2 导入解析（nested + 无 legacy flat 键） ─────────────────────────────


def _row_from_columns(columns: list[str], values: list) -> dict:
    return {c: v for c, v in zip(columns, values) if c}


def test_d2_2_parse_writes_nested_no_legacy_flat():
    columns = get_d2_2_columns(FIVE)
    src = {
        "seq": 1, "customerName": "客户A", "companyCode": "C1", "relationType": "非关联方",
        "priorUnadjusted": 100.0, "priorAje": 0.0, "priorRje": 0.0, "priorAudited": 100.0,
        "agingPrior": {s.key: float(i + 1) for i, s in enumerate(FIVE)},
        "debitOccurrence": 0.0, "creditOccurrence": 0.0, "endBalance": 100.0,
        "reclassification": 0.0, "currentUnadjusted": 100.0,
        "agingCurrent": {s.key: float(i + 10) for i, s in enumerate(FIVE)},
        "currentAje": 0.0, "currentRje": 0.0, "currentAudited": 100.0,
        "agingAudited": {s.key: float(i + 20) for i, s in enumerate(FIVE)},
        "creditRiskClassification": "账龄组合", "groupName": "组合1",
        "isConfirmation": True, "postPayment": 0.0, "remark": "",
    }
    exported = _d2_2_export_values(src, FIVE)
    row = _row_from_columns(columns, exported)

    parsed = _parse_d2_2_rows([row], FIVE)
    assert len(parsed) == 1
    p = parsed[0]
    # nested 结构完整
    assert set(p["agingPrior"].keys()) == {s.key for s in FIVE}
    assert p["agingPrior"]["within1"] == 1.0
    assert p["agingCurrent"]["within1"] == 10.0
    assert p["agingAudited"]["within1"] == 20.0
    # 无 legacy flat 键（Requirement/Property 11）
    assert not (_LEGACY_FLAT_KEYS & set(p.keys()))
    assert p["customerName"] == "客户A"
    assert p["isConfirmation"] is True


def test_d2_2_skipped_columns_detects_foreign_aging():
    columns = get_d2_2_columns(FIVE)
    exported = _d2_2_export_values({}, FIVE)
    row = _row_from_columns(columns, exported)
    row["6-7年(期初)"] = 1.0  # 当前配置外的账龄列
    skipped = _d2_2_skipped_aging_columns([row], FIVE)
    assert "6-7年(期初)" in skipped


# ─── D3-2 动态 export→import 往返 ────────────────────────────────────────────


def test_d3_2_dynamic_roundtrip():
    segments = THREE
    headers = _d3_2_dynamic_headers(segments)
    src = {
        "rowId": "r1", "customerName": "供应商B", "companyCode": "X1",
        "nature": "其他", "relationType": "非关联方",
        "priorUnadjusted": 50.0, "priorAdjustment": 0.0, "priorReclass": 0.0,
        "agingPrior": {s.key: float(i + 1) for i, s in enumerate(segments)},
        "debit": 0.0, "credit": 0.0, "entityReclass": 0.0, "endAje": 0.0, "endRje": 0.0,
        "agingAudited": {s.key: float(i + 5) for i, s in enumerate(segments)},
        "isConfirmed": "Y", "postPeriodSettlement": 0.0, "remark": "备注",
    }
    exported = _export_d3_2_row_dynamic(src, segments)
    parsed = _parse_d3_2_row(tuple(exported), headers, segments)

    assert parsed["customerName"] == "供应商B"
    assert parsed["isConfirmed"] == "Y"
    for i, s in enumerate(segments):
        assert parsed["agingPrior"][s.key] == float(i + 1)
        assert parsed["agingAudited"][s.key] == float(i + 5)


def test_d3_2_legacy_parse_still_works():
    """segments=None → 旧固定列头解析（round-trip PBT 依赖）。"""
    headers = [
        "对方单位名称", "期初审定账龄(1年以下)", "审定账龄(1年以下)",
    ]
    row = ("供应商C", 7.0, 9.0)
    parsed = _parse_d3_2_row(row, headers)  # 2 args → legacy
    assert parsed["agingPrior"]["within1"] == 7.0
    assert parsed["agingAudited"]["within1"] == 9.0


# ─── 工厂风格（K1/K3/G5）往返 ────────────────────────────────────────────────


def test_factory_style_aging_roundtrip():
    """build_aging_headers/aging_export_values ↔ match_import_aging 往返。"""
    segments = FIVE
    periods = subject_aging_periods("K1")
    headers = build_aging_headers(segments, periods)
    src = {
        "agingPrior": {s.key: float(i + 1) for i, s in enumerate(segments)},
        "agingCurrent": {s.key: float(i + 2) for i, s in enumerate(segments)},
        "agingAudited": {s.key: float(i + 3) for i, s in enumerate(segments)},
    }
    values = aging_export_values(src, segments, periods)
    lookup = {h: v for h, v in zip(headers, values)}
    aging, unmatched = match_import_aging(lookup.get, headers, segments, periods)
    assert unmatched == []
    assert aging == {
        "agingPrior": src["agingPrior"],
        "agingCurrent": src["agingCurrent"],
        "agingAudited": src["agingAudited"],
    }
