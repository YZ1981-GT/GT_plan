# Feature: acnr, Property 7: 生成器确定性（drift=0）与骨架覆盖
"""Property-based test: 生成器确定性（drift=0）与骨架覆盖.

**Validates: Requirements 18.3, 1.1**

验证规则:
- R18.3: generate_catalog.py 连续两次运行（同输入）产出逐字节一致的 JSON
- R1.1: SheetCatalogEntry 骨架 100% 覆盖 classification 记录（每个 distinct wp_code 一条）
- _deterministic_json 对 dict 构造顺序不敏感（key 排序稳定输出）

PBT 策略:
- 用 hypothesis 生成随机 classification 子集 + 随机 dict 构造顺序
- Mock loaders 隔离外部数据源
- 管线运行两次验证字节一致
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

# 确保 backend 目录在 path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from scripts.acnr.generate_catalog import (
    _deterministic_json,
    generate_catalog,
)
from app.services.acnr.loaders.from_classification import SheetCatalogEntry
from app.services.acnr.loaders.from_address_seeds import CellCatalogEntry
from app.services.acnr.loaders.from_render_registry import RenderRegistryData


# ---------------------------------------------------------------------------
# Strategies: 生成随机 classification 记录
# ---------------------------------------------------------------------------

# 有效循环前缀
_CYCLES = list("ABCDEFGHIJKLMNS")

# 有效 class_code
_CLASS_CODES = [
    "A-一般程序表",
    "A-实质性程序",
    "F-审定表",
    "F-明细表",
    "F-检查表",
    "F-分析表",
    "F-数据表",
    "C-附注披露",
    "B-底稿目录",
    "H-辅助说明",
]

# 有效 functional_type
_FUNCTIONAL_TYPES = [
    "adjudication_table",
    "detail_table",
    "checklist",
    "program_table",
    "analysis_table",
    "summary_table",
]


@st.composite
def classification_record_strategy(draw: st.DrawFn) -> dict[str, str]:
    """生成一条随机 classification 记录。"""
    cycle = draw(st.sampled_from(_CYCLES))
    num = draw(st.integers(min_value=1, max_value=20))
    suffix = draw(st.sampled_from(["", "-1", "-2", "-3", "-4", "-5"]))
    wp_code = f"{cycle}{num}{suffix}"

    sheet_name = draw(st.text(
        alphabet=st.characters(categories=("L", "N")),
        min_size=2,
        max_size=15,
    ))
    # 确保 sheet_name 非空
    assume(len(sheet_name.strip()) > 0)

    class_code = draw(st.sampled_from(_CLASS_CODES))
    functional_type = draw(st.sampled_from(_FUNCTIONAL_TYPES))

    return {
        "wp_code": wp_code,
        "sheet_name": sheet_name,
        "class_code": class_code,
        "functional_type": functional_type,
        "template_version_id": f"tpl-{wp_code}",
    }


@st.composite
def classification_records_strategy(draw: st.DrawFn) -> list[dict[str, str]]:
    """生成一组随机 classification 记录（2~10 条，wp_code 唯一）。"""
    records = draw(st.lists(
        classification_record_strategy(),
        min_size=2,
        max_size=10,
    ))
    # 去重：保证每个 wp_code 只出现一次（模拟 classification 表 distinct wp_code）
    seen: set[str] = set()
    unique_records: list[dict[str, str]] = []
    for r in records:
        if r["wp_code"] not in seen:
            seen.add(r["wp_code"])
            unique_records.append(r)
    assume(len(unique_records) >= 2)
    return unique_records


# ---------------------------------------------------------------------------
# Helper: mock 所有 loaders
# ---------------------------------------------------------------------------


def _mock_loaders():
    """返回用于 patch 的 mock 配置，所有外部 loader 返回空数据。"""
    render_data = RenderRegistryData()
    render_data.component_types = {}
    render_data.render_types = {}
    return {
        "scripts.acnr.generate_catalog.load_render_registry_edges": render_data,
        "scripts.acnr.generate_catalog.load_ie_manifest": {},
        "scripts.acnr.generate_catalog.load_cell_entries_from_seeds": [],
        "scripts.acnr.generate_catalog.load_sheet_name_aliases": {},
        "scripts.acnr.generate_catalog._load_overrides": {},
    }


# ---------------------------------------------------------------------------
# Property Test: 生成器确定性（drift=0）与骨架覆盖
# ---------------------------------------------------------------------------


class TestGeneratorDeterminism:
    """Property 7: 生成器确定性（drift=0）与骨架覆盖。

    Validates: Requirements 18.3, 1.1
    """

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(records=classification_records_strategy())
    def test_generate_catalog_deterministic_output(
        self, records: list[dict[str, str]]
    ):
        """R18.3: 同输入连续两次运行产出逐字节一致的 JSON。

        Property: ∀ inputs ∈ valid classification records,
          generate_catalog(inputs) × 2 → byte-identical JSON output
        """
        mocks = _mock_loaders()

        with (
            patch("scripts.acnr.generate_catalog.load_render_registry_edges", return_value=mocks["scripts.acnr.generate_catalog.load_render_registry_edges"]),
            patch("scripts.acnr.generate_catalog.load_ie_manifest", return_value=mocks["scripts.acnr.generate_catalog.load_ie_manifest"]),
            patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds", return_value=mocks["scripts.acnr.generate_catalog.load_cell_entries_from_seeds"]),
            patch("scripts.acnr.generate_catalog.load_sheet_name_aliases", return_value=mocks["scripts.acnr.generate_catalog.load_sheet_name_aliases"]),
            patch("scripts.acnr.generate_catalog._load_overrides", return_value=mocks["scripts.acnr.generate_catalog._load_overrides"]),
        ):
            cat1, _, _ = generate_catalog(
                classification_records=records,
                cycle="d",
                registry_version="fixed-version-001",
            )
            cat2, _, _ = generate_catalog(
                classification_records=records,
                cycle="d",
                registry_version="fixed-version-001",
            )

        json1 = _deterministic_json(cat1)
        json2 = _deterministic_json(cat2)

        assert json1 == json2, (
            "同输入两次运行产出不一致 (drift ≠ 0):\n"
            f"第一次长度={len(json1)}, 第二次长度={len(json2)}"
        )

    @settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(records=classification_records_strategy())
    def test_skeleton_100_percent_coverage(
        self, records: list[dict[str, str]]
    ):
        """R1.1: SheetCatalogEntry 骨架 100% 覆盖 classification 记录。

        Property: ∀ classification records,
          |catalog.sheets| == |distinct wp_codes in records|
          ∧ ∀ wp_code ∈ records, ∃ sheet ∈ catalog.sheets: sheet.sheet_code == wp_code
        """
        mocks = _mock_loaders()

        with (
            patch("scripts.acnr.generate_catalog.load_render_registry_edges", return_value=mocks["scripts.acnr.generate_catalog.load_render_registry_edges"]),
            patch("scripts.acnr.generate_catalog.load_ie_manifest", return_value=mocks["scripts.acnr.generate_catalog.load_ie_manifest"]),
            patch("scripts.acnr.generate_catalog.load_cell_entries_from_seeds", return_value=mocks["scripts.acnr.generate_catalog.load_cell_entries_from_seeds"]),
            patch("scripts.acnr.generate_catalog.load_sheet_name_aliases", return_value=mocks["scripts.acnr.generate_catalog.load_sheet_name_aliases"]),
            patch("scripts.acnr.generate_catalog._load_overrides", return_value=mocks["scripts.acnr.generate_catalog._load_overrides"]),
        ):
            catalog, _, _ = generate_catalog(
                classification_records=records,
                cycle="d",
                registry_version="coverage-test",
            )

        # 输入 distinct wp_code 集合
        input_wp_codes = {r["wp_code"] for r in records}

        # catalog.sheets 的 sheet_code 集合
        catalog_sheet_codes = {s["sheet_code"] for s in catalog["sheets"]}

        # 100% 覆盖：每个输入 wp_code 都对应一条 sheet
        missing = input_wp_codes - catalog_sheet_codes
        assert len(missing) == 0, (
            f"骨架覆盖不完整，缺失 {len(missing)} 条: {missing}"
        )

        # 数量精确匹配
        assert len(catalog_sheet_codes) == len(input_wp_codes), (
            f"catalog sheets 数量 ({len(catalog_sheet_codes)}) "
            f"!= distinct wp_codes ({len(input_wp_codes)})"
        )

    @settings(max_examples=5)
    @given(data=st.data())
    def test_deterministic_json_order_invariant(self, data: st.DataObject):
        """_deterministic_json 对 dict 构造顺序不敏感。

        Property: ∀ dict d 的任意 key 排列，
          _deterministic_json(permute(d)) == _deterministic_json(d)
        """
        # 生成随机 key-value 对
        keys = data.draw(st.lists(
            st.text(alphabet=st.characters(categories=("L", "N")), min_size=1, max_size=8),
            min_size=2,
            max_size=8,
            unique=True,
        ))
        values = data.draw(st.lists(
            st.one_of(
                st.integers(min_value=-1000, max_value=1000),
                st.text(min_size=0, max_size=10),
                st.booleans(),
                st.none(),
            ),
            min_size=len(keys),
            max_size=len(keys),
        ))

        # 原始顺序
        d1 = dict(zip(keys, values))
        # 反转顺序
        d2 = dict(zip(reversed(keys), reversed(values)))

        json1 = _deterministic_json(d1)
        json2 = _deterministic_json(d2)

        assert json1 == json2, (
            f"dict 构造顺序不同但内容相同，输出应字节一致:\n"
            f"d1 keys={list(d1.keys())}\n"
            f"d2 keys={list(d2.keys())}\n"
            f"json1={json1[:200]}\n"
            f"json2={json2[:200]}"
        )
