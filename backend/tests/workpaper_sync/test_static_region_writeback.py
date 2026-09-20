"""静态受管区（definedName-anchored static cell sheet）双向回写守卫。

spec: workpaper-sync-static-cell-sheet-writeback
覆盖 Property 1/4/5/6（静态往返等价 / 锚点缺失 fail-closed / kind 显式分派 / 无幽灵 UUID）。

本文件按 spec 实现顺序**逐 wave 追加**：Task 1 先钉 binding kind 判据 + 静态形态构造/校验，
后续 task 追加 resolve/extract/materialize 往返与 observer 分派。
"""

from __future__ import annotations

import pytest

from app.services.workpaper_sync import excel_extract as X
from app.services.workpaper_sync.excel_extract import (
    BindingKind,
    ExcelIdentityBinding,
    ManagedRegionResolutionError,
    is_static_region,
)


# ═══════════════════════════════════════════════════════════════════════════
# Task 1 · binding kind 判据 + 静态形态（Requirement 1 / Property 5）
# ═══════════════════════════════════════════════════════════════════════════


class TestBindingKind:
    """kind 由 `defined_name` 存在决定，不是 uuid_column 缺失（Property 5）。"""

    def test_dynamic_binding_kind_is_excel_table(self) -> None:
        binding = ExcelIdentityBinding(
            table_key="k_rows", table_name="GT_TBL", uuid_column="Z"
        )
        assert binding.kind is BindingKind.excel_table
        assert is_static_region(binding) is False

    def test_static_binding_kind_is_static_region(self) -> None:
        binding = ExcelIdentityBinding(
            table_key="d433-static", defined_name="GT_MANAGED_REGION_D433"
        )
        assert binding.kind is BindingKind.static_region
        assert is_static_region(binding) is True

    def test_static_binding_omits_table_name_and_uuid(self) -> None:
        # 静态构造可省略 table_name/uuid_column（默认 ""），不因缺它们而抛。
        binding = ExcelIdentityBinding(
            table_key="d433-static", defined_name="GT_MANAGED_REGION_D433"
        )
        assert binding.table_name == ""
        assert binding.uuid_column == ""
        assert binding.defined_name == "GT_MANAGED_REGION_D433"


class TestBindingKindFailClosed:
    """混填 / 空必填字段 fail-closed（Requirement 1.1/1.2）。"""

    def test_static_binding_rejects_table_name(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="kind 混填"):
            ExcelIdentityBinding(
                table_key="d433-static",
                defined_name="GT_MANAGED_REGION_D433",
                table_name="GT_TBL",  # 混填
            )

    def test_static_binding_rejects_uuid_column(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="kind 混填"):
            ExcelIdentityBinding(
                table_key="d433-static",
                defined_name="GT_MANAGED_REGION_D433",
                uuid_column="Z",  # 混填
            )

    def test_static_binding_rejects_empty_table_key(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="table_key"):
            ExcelIdentityBinding(
                table_key="", defined_name="GT_MANAGED_REGION_D433"
            )

    def test_static_binding_rejects_empty_metadata_sheet(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="metadata_sheet"):
            ExcelIdentityBinding(
                table_key="d433-static",
                defined_name="GT_MANAGED_REGION_D433",
                metadata_sheet="",
            )


class TestDynamicBindingUnchanged:
    """动态 binding 的既有强校验逐条保留（Requirement 1.5，动态零回归）。"""

    def test_dynamic_rejects_empty_table_name(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="table_name"):
            ExcelIdentityBinding(table_key="k_rows", uuid_column="Z")

    def test_dynamic_rejects_empty_uuid_column(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="uuid_column"):
            ExcelIdentityBinding(table_key="k_rows", table_name="GT_TBL")

    def test_dynamic_rejects_malformed_uuid_column(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="形态非法"):
            ExcelIdentityBinding(
                table_key="k_rows", table_name="GT_TBL", uuid_column="123"
            )

    def test_dynamic_accepts_valid(self) -> None:
        binding = ExcelIdentityBinding(
            table_key="k_rows", table_name="GT_TBL", uuid_column="AA"
        )
        assert binding.kind is BindingKind.excel_table
        assert binding.uuid_column == "AA"
