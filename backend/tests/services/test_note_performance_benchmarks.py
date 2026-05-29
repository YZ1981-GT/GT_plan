"""Sprint C.6.2 — Performance benchmarks for note module.

性能基准目标（来自 spec）：
- 173 章节序号渲染 < 100ms（纯计算）
- 集团基线 apply 60 章节 < 3s
- 国企↔上市互转 < 1s
- 离线导出 60 章节 < 5s
- 离线导入 60 章节 diff 预览 < 2s
- 合并附注汇总 N=10 子公司 < 5s

注：这些是 service 层基准，不依赖真 PG 数据库，使用 mock 数据测算法本身性能。
真实环境数据库 IO 会增加额外开销，由 UAT 验证（C.6.1）。
"""
from __future__ import annotations

import time
from io import BytesIO

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _measure(fn, *args, **kwargs):
    """Measure execution time in seconds."""
    start = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - start
    return result, elapsed


# ---------------------------------------------------------------------------
# 1. Section numbering (D13)
# ---------------------------------------------------------------------------


class TestSectionNumberingPerformance:
    """章节序号渲染性能 — 173 章节 < 100ms."""

    def test_render_173_sections_under_100ms(self):
        """173 章节 5 级层级 DFS 渲染必须 < 100ms（纯计算）."""
        from app.services.note_section_numbering_service import (
            cn_number,
            render_section_number,
        )

        # Build 173 mock sections: 9 chapters × ~20 children each
        sections = []
        for ch_idx in range(1, 10):
            sections.append({
                "section_id": f"ch_{ch_idx}",
                "level": 1,
                "parent_section_id": None,
                "sort_index": ch_idx,
            })
            for sub_idx in range(1, 22):
                sections.append({
                    "section_id": f"ch_{ch_idx}_sub_{sub_idx}",
                    "level": 2,
                    "parent_section_id": f"ch_{ch_idx}",
                    "sort_index": sub_idx,
                })

        # Render numbers (per-section LEVEL_FORMATS lookup)
        def render_all():
            counters = {}
            results = {}
            for sec in sections:
                key = (sec["level"], sec["parent_section_id"])
                counters.setdefault(key, 0)
                counters[key] += 1
                results[sec["section_id"]] = render_section_number(
                    sec["level"], counters[key]
                )
            return results

        # Warmup
        render_all()
        # Measure
        _, elapsed = _measure(render_all)
        # 173 sections must render in < 100ms
        assert elapsed < 0.1, f"序号渲染 {elapsed*1000:.1f}ms 超过 100ms 目标"


# ---------------------------------------------------------------------------
# 2. Offline export performance (C.0)
# ---------------------------------------------------------------------------


class TestOfflineExportPerformance:
    """离线导出性能 — 60 章节 < 5s."""

    def test_export_60_sections_under_5s(self):
        """导出 60 章节 xlsx 包必须 < 5s."""
        from app.services.note_offline_export_service import export_sections_to_xlsx

        sections = []
        for i in range(60):
            sections.append({
                "section_id": f"section_{i}",
                "section_title": f"测试章节{i}",
                "table_data": {
                    "headers": ["项目", "金额"],
                    "rows": [
                        {"row_type": "data", "label": f"项目{j}", "cells": [f"label{j}", j * 100]}
                        for j in range(20)
                    ],
                },
                "_cell_meta": {},
                "_formulas": {},
                "_cell_provenance": {},
                "_bindings": {},
                "_row_meta": [],
                "_dynamic_regions": [],
                "_cell_modes": {},
            })

        _, elapsed = _measure(export_sections_to_xlsx, sections)
        assert elapsed < 5.0, f"导出 60 章节耗时 {elapsed:.2f}s 超过 5s 目标"


# ---------------------------------------------------------------------------
# 3. Offline import diff preview (C.0)
# ---------------------------------------------------------------------------


class TestOfflineImportPerformance:
    """离线导入 diff 预览性能 — 60 章节 < 2s."""

    def test_diff_60_sections_under_2s(self):
        """60 章节 diff 计算必须 < 2s."""
        from app.services.note_offline_export_service import export_sections_to_xlsx
        from app.services.note_offline_import_service import (
            diff_sections,
            validate_import_file,
        )

        sections = []
        for i in range(60):
            sections.append({
                "section_id": f"s{i}",
                "section_title": f"章节{i}",
                "table_data": {
                    "headers": [f"列{c}" for c in range(3)],
                    "rows": [
                        {"row_type": "data", "cells": [r * 3 + c for c in range(3)]}
                        for r in range(10)
                    ],
                },
                "_cell_meta": {},
                "_formulas": {},
                "_cell_provenance": {},
                "_bindings": {},
                "_row_meta": [],
                "_dynamic_regions": [],
                "_cell_modes": {},
            })

        # Pre-export
        xlsx_bytes, _ = export_sections_to_xlsx(sections)

        # Validate + diff
        def validate_and_diff():
            validation = validate_import_file(xlsx_bytes)
            return diff_sections(xlsx_bytes, sections, validation.meta_data)

        # Warmup
        validate_and_diff()
        _, elapsed = _measure(validate_and_diff)
        assert elapsed < 2.0, f"60 章节 diff 耗时 {elapsed:.2f}s 超过 2s 目标"


# ---------------------------------------------------------------------------
# 4. Consol aggregation (D12)
# ---------------------------------------------------------------------------


class TestConsolAggregationPerformance:
    """合并附注汇总性能 — N=10 子公司 < 5s（不含 DB IO）."""

    def test_aggregate_10_subsidiaries_under_5s(self):
        """10 子公司汇总 simple_sum 必须 < 5s."""
        from app.services.consol_note_aggregation_service import _simple_sum

        # Mock 10 subsidiaries × 20 rows each
        child_data = []
        for sub_idx in range(10):
            child_data.append({
                "subsidiary_id": f"sub_{sub_idx}",
                "rows": [
                    {
                        "row_type": "dynamic_data",
                        "label": f"客户_{sub_idx}_{r}",
                        "cells": [f"客户_{sub_idx}_{r}", float(r * 100 + sub_idx)],
                    }
                    for r in range(20)
                ],
            })

        def aggregate():
            return _simple_sum(child_data, config={})

        # Warmup
        aggregate()
        _, elapsed = _measure(aggregate)
        assert elapsed < 5.0, f"10 子公司汇总耗时 {elapsed:.2f}s 超过 5s 目标"


# ---------------------------------------------------------------------------
# 5. Cross-template conversion (D14)
# ---------------------------------------------------------------------------


class TestTemplateConversionPerformance:
    """国企↔上市互转性能 — < 1s（不含 DB）."""

    def test_template_conversion_under_1s(self):
        """模板转换计算必须 < 1s (173 章节，跳过 diff_data 加载用 mock)."""
        from app.services.consol_cross_template_service import translate_child_section

        # Build minimal diff_data mock
        diff_data = {"common_sections": [{"section_id": f"s{i}"} for i in range(150)]}

        sections = []
        for i in range(173):
            sections.append({
                "section_id": f"s{i}",
                "section_title": f"章节{i}",
                "table_data": {
                    "headers": ["项目", "金额"],
                    "rows": [{"cells": [f"item{j}", j * 100]} for j in range(10)],
                },
            })

        def translate_all():
            return [
                translate_child_section(sec, "soe", "listed", diff_data=diff_data)
                for sec in sections
            ]

        # Warmup
        translate_all()
        _, elapsed = _measure(translate_all)
        assert elapsed < 1.0, f"模板转换 173 章节耗时 {elapsed:.2f}s 超过 1s 目标"


# ---------------------------------------------------------------------------
# 6. Word visual style application (C.4)
# ---------------------------------------------------------------------------


class TestWordStylePerformance:
    """Word 样式应用性能 — 大表 100 行 < 500ms."""

    def test_apply_dynamic_styles_100_rows_under_500ms(self):
        """100 行表格逐 cell 应用动态样式必须 < 500ms."""
        from docx import Document

        from app.services.note_word_dynamic_styles import (
            apply_dynamic_col_style,
            apply_dynamic_row_style,
        )

        doc = Document()
        table = doc.add_table(rows=100, cols=5)

        def apply_all():
            for r_idx in range(100):
                for c_idx in range(5):
                    cell = table.rows[r_idx].cells[c_idx]
                    if r_idx % 3 == 0:
                        apply_dynamic_row_style(cell)
                    elif c_idx == 4:
                        apply_dynamic_col_style(cell)

        _, elapsed = _measure(apply_all)
        assert elapsed < 0.5, f"100 行样式应用耗时 {elapsed:.2f}s 超过 500ms 目标"


# ---------------------------------------------------------------------------
# 7. Section version DAG validation (C.2)
# ---------------------------------------------------------------------------


class TestVersionTreeDagPerformance:
    """版本树 DAG 校验性能 — 100 节点 < 50ms."""

    def test_validate_dag_100_nodes_under_50ms(self):
        from app.services.note_section_version_tree_service import (
            VersionNode,
            VersionTree,
        )

        # Build 100-node linear chain
        nodes = []
        for i in range(100):
            nodes.append(
                VersionNode(
                    id=f"n{i}",
                    branch="main",
                    parent_node_id=f"n{i-1}" if i > 0 else None,
                )
            )
        tree = VersionTree(nodes)

        def validate():
            return tree.validate_dag()

        # Warmup
        validate()
        _, elapsed = _measure(validate)
        assert elapsed < 0.05, f"100 节点 DAG 校验耗时 {elapsed*1000:.1f}ms 超过 50ms 目标"
