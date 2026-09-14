# Feature: acnr, Property 12: skip_reason 阻断整册 manifest
"""Property-Based Test: skip_reason 阻断整册 manifest。

Validates: Requirements 1.4

Property 12 验证:
1. 当任意 sheet 存在非 null skip_reason 时，manifest_blocked 为 True
2. 当所有 sheet 的 skip_reason 均为 null 时，manifest_blocked 为 False
3. skip_reason 值写入条目（不被静默丢弃）
4. 阻断是"整册 manifest"级别而非仅跳过该 sheet
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

# 确保 backend 在 sys.path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.acnr.generate_catalog import generate_catalog
from app.services.acnr.loaders.from_render_registry import RenderRegistryData


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 合法 wp_code：大写字母 + 数字 + 可选后缀（如 D2-1, F3, G4-2）
_wp_code_st = st.from_regex(r"[D-N]\d-\d{1,2}", fullmatch=True)

# sheet_name: 中文/ASCII 非空字符串
_sheet_name_st = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        min_codepoint=0x30,
        max_codepoint=0x9FFF,
    ),
    min_size=2,
    max_size=15,
)

# skip_reason: 非空字符串（表示有阻断原因）
_skip_reason_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=40,
)

# 单条 classification 记录策略
_record_st = st.fixed_dictionaries({
    "wp_code": _wp_code_st,
    "sheet_name": _sheet_name_st,
    "class_code": st.sampled_from([
        "F-审定表", "F-明细表", "F-检查表", "A-一般程序表",
    ]),
    "functional_type": st.sampled_from([
        "adjudication_table", "detail_table", "check_table", "",
    ]),
    "template_version_id": st.just("tpl-test"),
})

# 一组 classification 记录（2~6 条），要求 wp_code 唯一
_records_st = st.lists(_record_st, min_size=2, max_size=6).filter(
    lambda recs: len({r["wp_code"] for r in recs}) == len(recs)
)


# ---------------------------------------------------------------------------
# Helper: 运行 generate_catalog with mocked loaders
# ---------------------------------------------------------------------------


def _run_pipeline(
    records: list[dict],
    overrides: dict[str, dict],
) -> tuple[dict, dict, bool]:
    """封装 generate_catalog 调用，mock 所有外部 loaders。"""
    with (
        patch("scripts.acnr.generate_catalog.load_render_registry_edges") as mock_render,
        patch("scripts.acnr.generate_catalog.load_sheet_name_aliases") as mock_aliases,
        patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds") as mock_cells,
        patch("scripts.acnr.generate_catalog.load_ie_manifest") as mock_ie,
        patch("scripts.acnr.generate_catalog._load_overrides") as mock_ovr,
    ):
        mock_render.return_value = RenderRegistryData()
        mock_aliases.return_value = {}
        mock_cells.return_value = []
        mock_ie.return_value = {}
        mock_ovr.return_value = overrides

        return generate_catalog(
            classification_records=records,
            cycle="d",
            registry_version="test-skip-reason",
        )


def _build_addr_id(wp_code: str) -> str:
    """从 wp_code 构造 SheetCatalogEntry 的 addr_id。

    规则同 from_classification._extract_parent_wp_code：
    取 X+digits 前缀作为 parent，再 parent/wp_code。
    """
    import re
    m = re.match(r"^([A-S]\d+)", wp_code)
    parent = m.group(1) if m else wp_code
    return f"{parent}/{wp_code}"


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    records=_records_st,
    skip_idx=st.data(),
    skip_reason=_skip_reason_st,
)
def test_any_skip_reason_blocks_entire_manifest(
    records: list[dict],
    skip_idx: st.DataObject,
    skip_reason: str,
):
    """P12 不变量 1: 任一 sheet 有非 null skip_reason → manifest_blocked=True。

    **Validates: Requirements 1.4**
    """
    # 随机选一个 sheet 注入 skip_reason
    idx = skip_idx.draw(st.integers(min_value=0, max_value=len(records) - 1))
    target_wp_code = records[idx]["wp_code"]
    target_addr_id = _build_addr_id(target_wp_code)

    overrides = {target_addr_id: {"skip_reason": skip_reason}}

    _catalog, _report, manifest_blocked = _run_pipeline(records, overrides)

    assert manifest_blocked is True, (
        f"skip_reason='{skip_reason}' on sheet '{target_wp_code}' "
        f"(addr_id={target_addr_id}) 未阻断 manifest"
    )


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(records=_records_st)
def test_no_skip_reason_allows_manifest(records: list[dict]):
    """P12 不变量 2: 所有 sheet skip_reason 均为 null → manifest_blocked=False。

    **Validates: Requirements 1.4**
    """
    # 无任何 override → 所有 skip_reason 保持 None
    overrides: dict[str, dict] = {}

    _catalog, _report, manifest_blocked = _run_pipeline(records, overrides)

    assert manifest_blocked is False, (
        f"无 skip_reason 时 manifest_blocked 不应为 True"
    )


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    records=_records_st,
    skip_idx=st.data(),
    skip_reason=_skip_reason_st,
)
def test_skip_reason_written_into_entry(
    records: list[dict],
    skip_idx: st.DataObject,
    skip_reason: str,
):
    """P12 不变量 3: skip_reason 值写入对应条目，不被静默丢弃。

    **Validates: Requirements 1.4**
    """
    idx = skip_idx.draw(st.integers(min_value=0, max_value=len(records) - 1))
    target_wp_code = records[idx]["wp_code"]
    target_addr_id = _build_addr_id(target_wp_code)

    overrides = {target_addr_id: {"skip_reason": skip_reason}}

    catalog, _report, _blocked = _run_pipeline(records, overrides)

    # 在 catalog sheets 中找到该条目并验证 skip_reason 已写入
    target_sheet = next(
        (s for s in catalog["sheets"] if s.get("sheet_code") == target_wp_code),
        None,
    )
    assert target_sheet is not None, (
        f"sheet '{target_wp_code}' 未出现在 catalog.sheets 中"
    )
    assert target_sheet.get("skip_reason") == skip_reason, (
        f"skip_reason 未正确写入条目: 期望 '{skip_reason}', "
        f"实际 '{target_sheet.get('skip_reason')}'"
    )


@settings(max_examples=5, suppress_health_check=[HealthCheck.too_slow])
@given(
    records=_records_st,
    skip_idx=st.data(),
    skip_reason=_skip_reason_st,
)
def test_blocking_is_entire_manifest_not_just_that_sheet(
    records: list[dict],
    skip_idx: st.DataObject,
    skip_reason: str,
):
    """P12 不变量 4: 阻断级别是"整册 manifest"而非仅跳过该 sheet。

    验证：即使只有一个 sheet 有 skip_reason，所有 sheet 仍在 catalog 中存在
    （不会被删除），但 manifest_blocked 标志指示全局阻断。

    **Validates: Requirements 1.4**
    """
    idx = skip_idx.draw(st.integers(min_value=0, max_value=len(records) - 1))
    target_wp_code = records[idx]["wp_code"]
    target_addr_id = _build_addr_id(target_wp_code)

    overrides = {target_addr_id: {"skip_reason": skip_reason}}

    catalog, report, manifest_blocked = _run_pipeline(records, overrides)

    # 整册被阻断
    assert manifest_blocked is True
    assert report["manifest_blocked"] is True

    # 所有 sheet 仍在 catalog 中存在（不是只删了那个 sheet）
    catalog_wp_codes = {s["sheet_code"] for s in catalog["sheets"]}
    input_wp_codes = {r["wp_code"] for r in records}
    assert input_wp_codes.issubset(catalog_wp_codes), (
        f"缺少 sheet: {input_wp_codes - catalog_wp_codes}。"
        f"skip_reason 应阻断整册 manifest 生成，而非从 catalog 中移除单个 sheet。"
    )

    # report.summary 也反映了有 skip_reason 的 sheet 数量
    assert report["summary"]["sheets_with_skip_reason"] >= 1
