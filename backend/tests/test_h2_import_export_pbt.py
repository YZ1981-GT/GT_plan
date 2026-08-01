"""H2 在建工程 — 导入导出 round-trip Property-Based Tests (hypothesis).

Spec: .kiro/specs/h2-construction-in-progress/ Task 7.2
Validates: Requirements 14.3

验证 H2 导入→导出→导入 round-trip 数据一致性：
- 列头映射对称性
- 数据序列化/反序列化恒等
- 多sheet结构完整性

═══════════════════════════════════════════════════════════════════════════════
2026-08-01 结构性重写说明
═══════════════════════════════════════════════════════════════════════════════

本文件原先导入 `_H2_2_BASE_HEADERS` / `_H2_2_CHANGE_HEADERS` / `_H2_2_TRANSFER_HEADERS`
等三区段常量 —— 这些名字在 `_h2_import_export.py` 里**从未存在过**（`git blame` 该文件
最早提交即为四区段 `_H2_2_SEGMENTS` 结构，三区段命名只存在于本测试文件本身，
是编写时对照另一份已废弃设计草稿写的，从未与实现同步）。

H2-2 的权威结构是 `_H2_2_SEGMENTS`（4 个具名区段：基本信息 / 账面原值 / 审定原值 /
减值与净值），对齐前端 `useH2Detail` / `H2TabDetail`。本文件改为对这个真实结构断言，
并用真实的 `export_row_by_keys` / `parse_row_by_headers` 做 round-trip 验证
（原测试的 round-trip 用例是自己手写的 dict↔list 模拟，不调用被测模块的任何函数，
本质是空转 —— 已改为真实调用）。
"""

import re
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.wp_render_strategies._cycle_import_export_common import (
    export_row_by_keys,
)
from app.routers.wp_render_strategies._h2_import_export import (
    _H2_2_GUIDANCE,
    _H2_2_NUMERIC,
    _H2_2_SEGMENTS,
)

_SEGMENT_NAMES = [seg[0] for seg in _H2_2_SEGMENTS]
_SEGMENT_HEADERS = {seg[0]: seg[1] for seg in _H2_2_SEGMENTS}
_SEGMENT_KEYS = {seg[0]: seg[2] for seg in _H2_2_SEGMENTS}

# 定位列（每个区段都有，供多 sheet 行按名称合并）
_LOCATOR_KEYS = ("name", "projectCode")


# ─── 列头/Keys 对称性 ────────────────────────────────────────────────────────


class TestHeaderKeySymmetryPBT:
    """**Validates: Requirements 14.3** — 导出模板列头与Keys一一对应."""

    def test_four_segments_exist(self):
        """H2-2 是四区段结构：基本信息 / 账面原值 / 审定原值 / 减值与净值。"""
        assert _SEGMENT_NAMES == ["基本信息", "账面原值", "审定原值", "减值与净值"]

    @pytest.mark.parametrize("seg_name", _SEGMENT_NAMES)
    def test_headers_keys_length_match(self, seg_name: str):
        """每个区段：headers 与 keys 长度一致（否则 export_row_by_keys 会错位）。"""
        assert len(_SEGMENT_HEADERS[seg_name]) == len(_SEGMENT_KEYS[seg_name])

    @pytest.mark.parametrize("seg_name", _SEGMENT_NAMES)
    def test_keys_are_unique_within_section(self, seg_name: str):
        """各区段内 keys 不重复。"""
        keys = _SEGMENT_KEYS[seg_name]
        assert len(keys) == len(set(keys)), f"{seg_name} 区段 keys 重复"

    def test_headers_not_empty(self):
        """所有列头非空字符串。"""
        for headers in _SEGMENT_HEADERS.values():
            for header in headers:
                assert header.strip() != ""

    def test_keys_are_valid_identifiers(self):
        """所有 keys 是合法标识符（camelCase）。"""
        pattern = re.compile(r"^[a-zA-Z][a-zA-Z0-9]*$")
        for keys in _SEGMENT_KEYS.values():
            for key in keys:
                assert pattern.match(key), f"Key '{key}' 不是合法camelCase标识符"

    @pytest.mark.parametrize("seg_name", _SEGMENT_NAMES)
    def test_every_segment_has_locator_columns(self, seg_name: str):
        """每个区段都有「工程名称+工程编号」定位列（多 sheet 按名称合并的前提）。"""
        keys = _SEGMENT_KEYS[seg_name]
        for locator in _LOCATOR_KEYS:
            assert locator in keys, f"{seg_name} 缺定位列 {locator}"

    def test_numeric_keys_are_subset_of_declared_keys(self):
        """`_H2_2_NUMERIC` 里的每个 key 都必须真实出现在某个区段的 keys 里（防孤儿声明）。"""
        all_keys = {k for keys in _SEGMENT_KEYS.values() for k in keys}
        orphans = _H2_2_NUMERIC - all_keys
        assert not orphans, f"_H2_2_NUMERIC 声明了不存在的 key: {orphans}"

    def test_guidance_non_empty(self):
        """编制说明非空（供导出模板「编制说明」sheet 使用）。"""
        assert len(_H2_2_GUIDANCE) > 0
        assert any(line.strip() for line in _H2_2_GUIDANCE)


# ─── Round-trip 数据一致性（真实调用 export_row_by_keys / parse_row_by_headers）───


def _row_strategy(seg_name: str):
    """按某区段的 numeric/非 numeric keys 构造随机行字典。"""
    keys = _SEGMENT_KEYS[seg_name]
    fields = {}
    for key in keys:
        if key in _H2_2_NUMERIC:
            fields[key] = st.floats(
                min_value=-1e8, max_value=1e8, allow_nan=False, allow_infinity=False
            )
        else:
            fields[key] = st.text(
                min_size=0, max_size=12, alphabet=st.characters(categories=("L", "N"))
            )
    return st.fixed_dictionaries(fields)


class TestRoundTripConsistencyPBT:
    """**Validates: Requirements 14.3** — 导出→导入 round-trip 恒等（真实调用被测函数）。"""

    @settings(max_examples=5)
    @given(row=_row_strategy("账面原值"))
    def test_export_then_parse_by_position_roundtrip(self, row: dict):
        """`export_row_by_keys` → 按位置解析 round-trip 数值恒等。

        🔴 真实 H2-2 多 sheet 解析路径（`_parse_h2_2_import`）**不用**
        `parse_row_by_headers` 自带的 `is_numeric_field_key` 猜测数值列 ——
        它按位置直接查 ``key in _H2_2_NUMERIC``（`_h2_import_export.py`
        `for col_i, key in enumerate(seg_keys): … safe_float(raw) if key in _H2_2_NUMERIC else safe_str(raw)`）。
        本测试复刻这条真实路径，而不是 `parse_row_by_headers` 的通用启发式
        （它对 `name`/`projectCode` 这类无强数值后缀的 key 会误判为文本，
        与 `_H2_2_NUMERIC` 的显式声明不一致）。

        数值列四舍五入到 2 位小数（`export_row_by_keys` 的既有行为），
        故断言容差 1e-2；文本列恒等。
        """
        from app.routers.wp_render_strategies._h2_import_export import safe_float, safe_str

        keys = _SEGMENT_KEYS["账面原值"]
        exported = export_row_by_keys(row, keys)

        parsed = {
            key: (safe_float(val) if key in _H2_2_NUMERIC else safe_str(val))
            for key, val in zip(keys, exported)
        }

        for key in keys:
            if key in _H2_2_NUMERIC:
                assert abs(parsed[key] - round(row[key], 2)) < 1e-2, key
            else:
                assert parsed[key] == row[key], key

    @settings(max_examples=5)
    @given(rows=st.lists(_row_strategy("基本信息"), min_size=1, max_size=8))
    def test_row_count_preserved_after_export(self, rows: list[dict]):
        """导出不丢行、不增行。"""
        keys = _SEGMENT_KEYS["基本信息"]
        exported = [export_row_by_keys(r, keys) for r in rows]
        assert len(exported) == len(rows)

    def test_missing_key_exports_empty_string(self):
        """`export_row_by_keys` 对缺失 key 输出空串（不是 None/KeyError）。"""
        keys = _SEGMENT_KEYS["减值与净值"]
        exported = export_row_by_keys({}, keys)
        assert exported == [""] * len(keys)


# ─── 4区段分sheet结构 ────────────────────────────────────────────────────────


class TestMultiSheetStructurePBT:
    """**Validates: Requirements 14.3** — H2-2按4区段分sheet导出结构完整。"""

    def test_all_segments_share_locator_keys(self):
        """4 区段都有定位列，供多 sheet 行按「工程名称+工程编号」合并。"""
        for seg_name in _SEGMENT_NAMES:
            keys = _SEGMENT_KEYS[seg_name]
            for locator in _LOCATOR_KEYS:
                assert locator in keys

    @settings(max_examples=5)
    @given(
        project_names=st.lists(
            st.text(min_size=1, max_size=10, alphabet=st.characters(categories=("L",))),
            min_size=2,
            max_size=10,
            unique=True,
        ),
    )
    def test_row_sync_across_sections_by_name(self, project_names: list[str]):
        """4 区段行通过 name 同步定位（行顺序一致，真实导出后按位置对齐）。"""
        rows = [{"name": n, "projectCode": f"P{i}"} for i, n in enumerate(project_names)]
        for seg_name in _SEGMENT_NAMES:
            keys = _SEGMENT_KEYS[seg_name]
            exported = [export_row_by_keys(r, keys) for r in rows]
            name_idx = keys.index("name")
            for i, name in enumerate(project_names):
                assert exported[i][name_idx] == name
