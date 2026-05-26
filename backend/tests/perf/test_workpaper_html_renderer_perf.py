"""Performance benchmark tests for workpaper-html-renderer (Task 13.6).

Validates: design §9.6 性能基准
- Test A: HTML 渲染冷启动 ≤ 500ms (D2 18 sheet 整套)
- Test B: 导出 xlsx ≤ 5s (含模板加载 + openpyxl 写入)
- Test C: openpyxl asyncio.run_in_executor + 信号量 ≤ 10 并发
- Test D: schema cache hit performance (99 hits ≤ 100ms)
- Test E: classification derivation 性能 (1000 calls ≤ 100ms)

Notes:
- 标记为 @pytest.mark.perf, 可通过 -m "not perf" 跳过
- 性能阈值用宽松边界 (×2-3 design target) 避免 CI 抖动
- 不依赖 PostgreSQL/Redis/Playwright, 纯后端 perf
- 每个测试打印实际耗时供调试
"""

from __future__ import annotations

import asyncio
import threading
import time
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

# 部分模块依赖 openpyxl + PyYAML, 若不存在则跳过
openpyxl = pytest.importorskip("openpyxl")
yaml = pytest.importorskip("yaml")

from app.services import wp_xlsx_export_service
from app.services.wp_classification_service import (
    ClassificationResult,
    derive_component_type,
)
from app.services.wp_render_schema_service import WpRenderSchemaService
from app.services.wp_xlsx_export_service import (
    _EXPORT_SEMAPHORE,
    _sync_export_workpaper_xlsx,
    export_workpaper_xlsx,
)

pytestmark = pytest.mark.perf


# ─── Helpers ──────────────────────────────────────────────────────────────


def _make_classification(
    wp_code: str,
    sheet_name: str,
    class_code: str,
) -> ClassificationResult:
    """Build a minimal ClassificationResult for derive_component_type benchmarks."""
    return ClassificationResult(
        wp_code=wp_code,
        sheet_name=sheet_name,
        class_code=class_code,
        class_=class_code,
        scope="standalone",
        is_real_workpaper=True,
        delegated_module=None,
        render_schema_path=None,
        template_version_id=None,
        has_override=False,
    )


def _build_18_sheet_template(tmp_path: Path) -> Path:
    """Build a synthetic 18-sheet xlsx mimicking D2 audit workpaper structure.

    Each sheet contains:
      - 4 fixed-position header cells (entity / period_end / index / page)
      - 6 static text rows
      - A 50-row dynamic table region (rows 10-59)
      - 3 formulas
      - 4 merged-cell ranges
    """
    template_path = tmp_path / "perf_d2_18_sheet.xlsx"
    wb = openpyxl.Workbook()
    # remove default sheet
    wb.remove(wb.active)

    sheet_names = (
        ["底稿目录", "程序表D2A"]
        + [f"审定表D2-{i}" for i in range(1, 5)]
        + ["附注披露信息(上市公司)D2-1", "附注披露信息(国企)D2-1"]
        + [f"明细表D2-{i}" for i in range(2, 9)]
        + ["坏账准备明细表D2-3", "调整分录汇总表D2-4", "GT_Custom"]
    )
    assert len(sheet_names) == 18

    for sheet_name in sheet_names:
        ws = wb.create_sheet(sheet_name)

        # Static text (rows 1-6)
        ws["A1"] = "致同会计师事务所"
        ws["A2"] = sheet_name
        ws["A3"] = "被审计单位名称："
        ws["A4"] = "审计截止日："
        ws["A5"] = "索引号："
        ws["A6"] = "页码："

        # Formulas
        ws["B3"] = "=底稿目录!A2" if sheet_name != "底稿目录" else "客户A"
        ws["B4"] = "=底稿目录!A3" if sheet_name != "底稿目录" else "2025-12-31"
        ws["H3"] = '=CONCATENATE("D2-", ROW())'

        # Merged regions
        ws.merge_cells("A1:H1")
        ws.merge_cells("A2:G2")
        ws.merge_cells("C3:G3")
        ws.merge_cells("C4:G4")

        # Header row for dynamic table
        ws["A9"] = "序号"
        ws["B9"] = "程序描述"
        ws["C9"] = "类别"
        ws["D9"] = "存在"
        ws["E9"] = "完整"
        ws["F9"] = "权属"
        ws["G9"] = "准确"
        ws["H9"] = "列报"

    wb.save(str(template_path))
    wb.close()
    return template_path


def _build_18_sheet_schema(template_path: Path) -> dict:
    """Build a render schema dict matching the synthetic 18-sheet template."""
    sheet_names = (
        ["底稿目录", "程序表D2A"]
        + [f"审定表D2-{i}" for i in range(1, 5)]
        + ["附注披露信息(上市公司)D2-1", "附注披露信息(国企)D2-1"]
        + [f"明细表D2-{i}" for i in range(2, 9)]
        + ["坏账准备明细表D2-3", "调整分录汇总表D2-4", "GT_Custom"]
    )
    sheets_schema: dict = {}
    for sheet_name in sheet_names:
        sheets_schema[sheet_name] = {
            "fixed_cells": {
                "A3": "${entity_name}",
                "A4": "${period_end}",
                "A5": "${index_no}",
                "A6": "${page_no}",
            },
            "dynamic_table": {
                "start_row": 10,
                "columns": {
                    "A": {"field": "seq", "type": "number"},
                    "B": {"field": "program_desc", "type": "text"},
                    "C": {"field": "program_category", "type": "text"},
                    "D": {
                        "field": "assertion.existence",
                        "type": "boolean",
                        "render": "checkmark",
                    },
                    "E": {
                        "field": "assertion.completeness",
                        "type": "boolean",
                        "render": "checkmark",
                    },
                    "F": {
                        "field": "assertion.rights",
                        "type": "boolean",
                        "render": "checkmark",
                    },
                    "G": {
                        "field": "assertion.accuracy",
                        "type": "boolean",
                        "render": "checkmark",
                    },
                    "H": {
                        "field": "assertion.presentation",
                        "type": "boolean",
                        "render": "checkmark",
                    },
                },
            },
        }
    return {
        "wp_code": "D2",
        "template_path": str(template_path),
        "template_version": "v2025-R5",
        "sheets": sheets_schema,
    }


def _build_18_sheet_html_data(rows_per_sheet: int = 50) -> dict:
    """Build sample html_data for 18 sheets, rows_per_sheet rows each."""
    sheet_names = (
        ["底稿目录", "程序表D2A"]
        + [f"审定表D2-{i}" for i in range(1, 5)]
        + ["附注披露信息(上市公司)D2-1", "附注披露信息(国企)D2-1"]
        + [f"明细表D2-{i}" for i in range(2, 9)]
        + ["坏账准备明细表D2-3", "调整分录汇总表D2-4", "GT_Custom"]
    )
    rows_template = [
        {
            "seq": i + 1,
            "program_desc": f"审计程序 {i + 1} 描述内容",
            "program_category": "常规★" if i % 2 == 0 else "IPO 加项",
            "assertion": {
                "existence": True,
                "completeness": True,
                "rights": i % 3 == 0,
                "accuracy": True,
                "presentation": i % 2 == 0,
            },
        }
        for i in range(rows_per_sheet)
    ]
    return {sheet: {"rows": list(rows_template)} for sheet in sheet_names}


# ─── Test A: HTML 渲染冷启动 ≤ 500ms ─────────────────────────────────────


class TestHtmlRenderColdStart:
    """Test A: HTML render cold start should be ≤ 500ms for a D2 18-sheet bundle.

    Measures the core path: schema YAML load + componentType derivation +
    render_config-style assembly for 18 sheets, simulating a single backend
    request to /workpapers/{id}/render-config.
    """

    def test_cold_start_18_sheets_under_1000ms(self, tmp_path):
        """Schema load + classification + render_config assembly for 18 sheets.

        Design target: ≤ 500ms; CI-relaxed bound: ≤ 1000ms (×2).
        """
        # ── Setup: write 18 minimal schema YAMLs to a temp dir ──────────
        schema_dir = tmp_path / "wp_render_schema"
        schema_dir.mkdir()

        wp_codes = [f"PERF{i:02d}" for i in range(18)]
        for wp_code in wp_codes:
            schema_data = {
                "wp_code": wp_code,
                "template_path": "stub.xlsx",
                "template_version": "v2025-R5",
                "applicable_standards": ["soe_standalone", "listed_standalone"],
                "sheets": {
                    f"sheet_{wp_code}": {
                        "component_type": "a-program-console",
                        "fixed_cells": {
                            "A1": "致同",
                            "A3": "${entity_name}",
                            "A4": "${period_end}",
                        },
                        "dynamic_table": {
                            "start_row": 10,
                            "columns": {
                                "A": {"field": "seq", "type": "number"},
                                "B": {"field": "desc", "type": "text"},
                            },
                        },
                    }
                },
            }
            (schema_dir / f"{wp_code}.yaml").write_text(
                yaml.dump(schema_data, allow_unicode=True), encoding="utf-8"
            )

        # ── Redirect _SCHEMA_DIR to temp dir ────────────────────────────
        import app.services.wp_render_schema_service as schema_module

        orig_dir = schema_module._SCHEMA_DIR
        schema_module._SCHEMA_DIR = schema_dir

        try:
            # ── Measure cold start ──────────────────────────────────────
            start = time.perf_counter()

            service = WpRenderSchemaService()  # fresh, empty cache
            render_configs = []
            for wp_code in wp_codes:
                schema = service.load_schema(wp_code)
                # Simulate classification derivation per sheet
                clr = _make_classification(
                    wp_code, f"sheet_{wp_code}", "A-程序表"
                )
                component_type = derive_component_type(clr)
                # Assemble render_config response
                render_configs.append(
                    {
                        "wp_code": wp_code,
                        "sheet_name": f"sheet_{wp_code}",
                        "component_type": component_type,
                        "schema": schema,
                        "scope": clr.scope,
                        "is_real_workpaper": clr.is_real_workpaper,
                    }
                )

            elapsed = time.perf_counter() - start
        finally:
            schema_module._SCHEMA_DIR = orig_dir

        elapsed_ms = elapsed * 1000
        print(
            f"\n[Test A] HTML render cold start (18 sheets): {elapsed_ms:.1f}ms "
            f"(design target ≤ 500ms, CI bound ≤ 1000ms)"
        )

        assert len(render_configs) == 18
        assert all(rc["component_type"] == "a-program-console" for rc in render_configs)
        assert elapsed_ms <= 1000, (
            f"Cold start took {elapsed_ms:.1f}ms, exceeding 1000ms CI bound "
            f"(design target ≤ 500ms)"
        )


# ─── Test B: 导出 xlsx ≤ 5s ───────────────────────────────────────────────


class TestExportXlsxPerformance:
    """Test B: Single workpaper xlsx export (18 sheets) should be ≤ 5s.

    Measures the full sync path: template load + openpyxl write + BytesIO save.
    """

    def test_export_18_sheet_workpaper_under_5s(self, tmp_path):
        """End-to-end sync export of an 18-sheet workpaper.

        Design target: ≤ 5s; CI bound: ≤ 5s (already generous).
        """
        # Build synthetic template + schema + data
        template_path = _build_18_sheet_template(tmp_path)
        schema = _build_18_sheet_schema(template_path)
        html_data = _build_18_sheet_html_data(rows_per_sheet=50)
        project_meta = {
            "entity_name": "性能测试公司",
            "period_end": "2025-12-31",
            "index_no": "D2-001",
            "page_no": "1/1",
        }

        # ── Measure ─────────────────────────────────────────────────────
        start = time.perf_counter()
        result = _sync_export_workpaper_xlsx(schema, html_data, project_meta)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        print(
            f"\n[Test B] Export xlsx (18 sheets × 50 rows): {elapsed_ms:.1f}ms "
            f"(design target ≤ 5000ms)"
        )

        assert isinstance(result, BytesIO)
        # Verify the result is a valid workbook
        result.seek(0)
        wb = openpyxl.load_workbook(result, read_only=True)
        assert len(wb.sheetnames) == 18
        wb.close()

        assert elapsed_ms <= 5000, (
            f"Export took {elapsed_ms:.1f}ms, exceeding 5000ms target"
        )


# ─── Test C: openpyxl 并发信号量 ≤ 10 ─────────────────────────────────────


class TestExportSemaphoreConcurrency:
    """Test C: _EXPORT_SEMAPHORE limits concurrent openpyxl operations to ≤ 10.

    Replaces _sync_export_workpaper_xlsx with a tracking version that bumps
    a counter under a Lock. Concurrent batch of 30 exports should never
    exceed 10 simultaneously in-flight.
    """

    def test_semaphore_value_is_10(self):
        """The module-level export semaphore is configured at 10."""
        # Internal _value reflects current available permits when fully released
        assert _EXPORT_SEMAPHORE._value == 10, (
            f"_EXPORT_SEMAPHORE should be initialized to 10, "
            f"got {_EXPORT_SEMAPHORE._value}"
        )

    def test_concurrent_30_exports_throttled_to_10(self, monkeypatch):
        """Run 30 concurrent exports; max in-flight must be ≤ 10."""
        # Tracking state
        lock = threading.Lock()
        in_flight = [0]
        max_in_flight = [0]
        completed = [0]

        def tracking_sync_export(schema, html_data, project_meta):
            with lock:
                in_flight[0] += 1
                if in_flight[0] > max_in_flight[0]:
                    max_in_flight[0] = in_flight[0]
            time.sleep(0.05)  # simulate 50ms openpyxl work
            with lock:
                in_flight[0] -= 1
                completed[0] += 1
            return BytesIO(b"fake-xlsx-bytes")

        # Replace the module-level sync function
        monkeypatch.setattr(
            wp_xlsx_export_service,
            "_sync_export_workpaper_xlsx",
            tracking_sync_export,
        )

        # Build minimal valid inputs (sync function is replaced anyway)
        schema = {"template_path": "x.xlsx", "sheets": {}}
        html_data: dict = {}
        project_meta = {
            "entity_name": "并发测试公司",
            "period_end": "2025-12-31",
        }

        async def run_batch():
            tasks = [
                export_workpaper_xlsx(
                    f"WP{i:02d}", html_data, schema, project_meta
                )
                for i in range(30)
            ]
            return await asyncio.gather(*tasks)

        start = time.perf_counter()
        results = asyncio.run(run_batch())
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        print(
            f"\n[Test C] 30 concurrent exports: max_in_flight={max_in_flight[0]}, "
            f"elapsed={elapsed_ms:.1f}ms (semaphore=10, work=50ms each)"
        )

        # All 30 finished
        assert completed[0] == 30
        assert len(results) == 30
        # Max concurrent did not exceed semaphore limit
        assert max_in_flight[0] <= 10, (
            f"max_in_flight={max_in_flight[0]} exceeded semaphore limit of 10"
        )
        # Throttling actually happened: 30 tasks × 50ms / 10 concurrent ≈ 150ms
        # plus executor / event-loop overhead. Lower bound 100ms proves
        # the batch was not fully parallel.
        assert elapsed_ms >= 100, (
            f"Total elapsed {elapsed_ms:.1f}ms is suspiciously low — "
            f"semaphore may not be throttling"
        )


# ─── Test D: schema cache hit performance ────────────────────────────────


class TestSchemaCachePerformance:
    """Test D: After priming, 99 cache-hit loads complete in ≤ 100ms total."""

    def test_99_cache_hits_under_100ms(self, tmp_path, monkeypatch):
        """Cache hits should average < 1ms per load."""
        # Setup minimal schema dir
        schema_dir = tmp_path / "wp_render_schema"
        schema_dir.mkdir()

        wp_code = "CACHE_TEST"
        schema_data = {
            "wp_code": wp_code,
            "template_path": "stub.xlsx",
            "sheets": {
                f"sheet_{i}": {"component_type": "a-program-console"}
                for i in range(18)
            },
        }
        (schema_dir / f"{wp_code}.yaml").write_text(
            yaml.dump(schema_data, allow_unicode=True), encoding="utf-8"
        )

        import app.services.wp_render_schema_service as schema_module

        monkeypatch.setattr(schema_module, "_SCHEMA_DIR", schema_dir)

        service = WpRenderSchemaService()

        # Prime cache with first load
        service.load_schema(wp_code)

        # Measure 99 cache hits
        start = time.perf_counter()
        for _ in range(99):
            schema = service.load_schema(wp_code)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        avg_ms = elapsed_ms / 99
        print(
            f"\n[Test D] 99 schema cache hits: total={elapsed_ms:.1f}ms, "
            f"avg={avg_ms:.3f}ms/hit (target ≤ 100ms total / ≤ 1ms avg)"
        )

        assert schema["wp_code"] == wp_code
        assert elapsed_ms <= 100, (
            f"99 cache hits took {elapsed_ms:.1f}ms, exceeding 100ms target"
        )


# ─── Test E: classification derivation 性能 ──────────────────────────────


class TestClassificationDerivationPerformance:
    """Test E: derive_component_type 1000 calls ≤ 100ms (≤ 0.1ms per call)."""

    def test_1000_derivations_under_100ms(self):
        """Classification derivation should be O(1) and well under 0.1ms."""
        # Mix of class_codes covering all routing branches
        class_codes = [
            "A-程序表",
            "B-底稿目录",
            "C-附注披露",
            "D-检查表",
            "D-函证",
            "D-盘点",
            "D-访谈",
            "D-询证",
            "D-政策检查",
            "D-业务模式",
            "D-复核记录",
            "D-复核",
            "E-控制测试",
            "F-数据表",
            "G-测算表",
            "H-辅助说明",
            "I-占位",
        ]

        results = []
        start = time.perf_counter()
        for i in range(1000):
            class_code = class_codes[i % len(class_codes)]
            clr = _make_classification(
                f"WP{i:04d}", f"sheet_{i}", class_code
            )
            component_type = derive_component_type(clr)
            results.append(component_type)
        elapsed = time.perf_counter() - start

        elapsed_ms = elapsed * 1000
        avg_us = elapsed_ms * 1000 / 1000
        print(
            f"\n[Test E] 1000 derive_component_type: total={elapsed_ms:.1f}ms, "
            f"avg={avg_us:.1f}μs/call (target ≤ 100ms total / ≤ 100μs avg)"
        )

        assert len(results) == 1000
        # Spot-check routing
        assert "a-program-console" in results
        assert "b-index" in results
        assert "c-note-table" in results
        assert "e-control-test" in results
        assert "univer" in results  # F + G
        assert "h-static-doc" in results
        assert "skip" in results
        assert "d-form-confirmation" in results
        assert "d-form-paragraph" in results
        assert "d-form-qa" in results
        assert "d-form-review" in results
        assert "d-form-table" in results

        assert elapsed_ms <= 100, (
            f"1000 derivations took {elapsed_ms:.1f}ms, exceeding 100ms target"
        )
