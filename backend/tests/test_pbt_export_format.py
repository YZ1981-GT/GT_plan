"""Property 4: Export Format Matches Workpaper Type (PBT)

Property 4: 表格/审定表/程序表→xlsx，文字→docx，映射确定且穷尽

**Validates: Requirements 1.1**

Testing framework: hypothesis
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_export.export_engine import determine_export_format

# ─── Type Definitions ─────────────────────────────────────────────────────────

# All known workpaper component types
# 🔴 这是 `export_engine._XLSX_TYPES` 的**测试侧副本**（第二真源）——
#    生产集合新增取值必须同步这里，否则表现为「守卫清单漏一张 = 假失败」。
#    `"custom"` = 自定义底稿（componentType=custom），2026-08-06 显式登记。
XLSX_TYPES = [
    "univer", "form", "hybrid", "table", "audit_sheet", "program_sheet", "custom",
]
DOCX_TYPES = ["word", "text"]
ALL_WP_TYPES = XLSX_TYPES + DOCX_TYPES


# ─── Property 4: Export Format Matches Workpaper Type ─────────────────────────


class TestExportFormatMatchesWorkpaperType:
    """Property 4: 表格/审定表/程序表→xlsx，文字→docx，映射确定且穷尽

    **Validates: Requirements 1.1**
    """

    @given(component_type=st.sampled_from(XLSX_TYPES))
    @settings(max_examples=5)
    def test_xlsx_types_produce_xlsx(self, component_type: str) -> None:
        """All xlsx-category types produce "xlsx" format.

        **Validates: Requirements 1.1**
        """
        result = determine_export_format(None, component_type)
        assert result == "xlsx", (
            f"component_type={component_type!r} should produce 'xlsx', got {result!r}"
        )

    @given(component_type=st.sampled_from(DOCX_TYPES))
    @settings(max_examples=5)
    def test_docx_types_produce_docx(self, component_type: str) -> None:
        """All docx-category types produce "docx" format.

        **Validates: Requirements 1.1**
        """
        result = determine_export_format(None, component_type)
        assert result == "docx", (
            f"component_type={component_type!r} should produce 'docx', got {result!r}"
        )

    @given(component_type=st.sampled_from(ALL_WP_TYPES))
    @settings(max_examples=5)
    def test_mapping_is_exhaustive(self, component_type: str) -> None:
        """Every known type maps to either xlsx or docx (no unknown format).

        **Validates: Requirements 1.1**
        """
        result = determine_export_format(None, component_type)
        assert result in ("xlsx", "docx"), (
            f"component_type={component_type!r} produced unexpected format {result!r}"
        )

    @given(component_type=st.sampled_from(ALL_WP_TYPES))
    @settings(max_examples=5)
    def test_format_deterministic(self, component_type: str) -> None:
        """Same component_type always produces the same format (determinism).

        **Validates: Requirements 1.1**
        """
        result1 = determine_export_format(None, component_type)
        result2 = determine_export_format(None, component_type)
        assert result1 == result2, (
            f"Non-deterministic: {component_type!r} → {result1!r} then {result2!r}"
        )
