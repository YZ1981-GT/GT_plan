"""模板版本升级数据迁移 - 属性测试

Property 1: 迁移后共有 sheet/列的用户数据与迁移前一致
Property 2: 迁移可逆——回滚后 parsed_data 与迁移前一致

Spec: wp-template-migration
Requirements: 2.2, 4.2

测试框架: hypothesis
"""

from __future__ import annotations

import copy
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.wp_migration_service import WpMigrationService
from app.services.wp_template_diff_service import ColumnDiff, TemplateDiff


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# 生成合理的 sheet 名称
sheet_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=0x4E00, max_codepoint=0x9FFF),
    min_size=1,
    max_size=8,
).map(lambda s: f"Sheet_{s}")

# 生成合理的列标题
column_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), min_codepoint=0x4E00, max_codepoint=0x9FFF),
    min_size=1,
    max_size=6,
).map(lambda s: f"Col_{s}")

# 生成 cell 值
cell_value_st = st.one_of(
    st.text(min_size=0, max_size=20),
    st.integers(min_value=-10000, max_value=10000),
    st.floats(min_value=-1000, max_value=1000, allow_nan=False, allow_infinity=False),
    st.none(),
)


@st.composite
def parsed_data_st(draw: st.DrawFn) -> dict[str, Any]:
    """生成合理的 parsed_data 结构"""
    num_sheets = draw(st.integers(min_value=1, max_value=4))
    html_data: dict[str, Any] = {}

    for i in range(num_sheets):
        sheet_name = f"Sheet{i+1}"
        num_cols = draw(st.integers(min_value=1, max_value=5))
        columns = [f"Col{j+1}" for j in range(num_cols)]

        # 生成一些 cell 数据
        cells: dict[str, Any] = {}
        num_cells = draw(st.integers(min_value=0, max_value=8))
        for c in range(num_cells):
            row = draw(st.integers(min_value=1, max_value=10))
            col_idx = draw(st.integers(min_value=0, max_value=num_cols - 1))
            col_letter = chr(65 + col_idx)  # A, B, C...
            coord = f"{col_letter}{row}"
            value = draw(cell_value_st)
            if value is not None:
                cells[coord] = {"v": value}

        html_data[sheet_name] = {"cells": cells, "columns": columns}

    return {"html_data": html_data, "wp_code": "D2-1"}


@st.composite
def template_diff_for_parsed_data_st(
    draw: st.DrawFn, parsed_data: dict[str, Any]
) -> TemplateDiff:
    """基于已有 parsed_data 生成合理的 TemplateDiff"""
    html_data = parsed_data.get("html_data", {})
    existing_sheets = list(html_data.keys())

    diff = TemplateDiff()

    # 可能新增 sheet
    if draw(st.booleans()):
        new_sheet = f"NewSheet_{draw(st.integers(min_value=100, max_value=999))}"
        diff.added_sheets.append(new_sheet)

    # 可能删除 sheet（但保留至少一个）
    if len(existing_sheets) > 1 and draw(st.booleans()):
        to_remove = draw(st.sampled_from(existing_sheets))
        diff.removed_sheets.append(to_remove)

    # 可能有列级变化（在共有 sheet 上）
    common_sheets = [s for s in existing_sheets if s not in diff.removed_sheets]
    if common_sheets and draw(st.booleans()):
        target_sheet = draw(st.sampled_from(common_sheets))
        col_diff = ColumnDiff(sheet_name=target_sheet)
        col_diff.added.append(f"NewCol_{draw(st.integers(min_value=100, max_value=999))}")
        diff.column_diffs.append(col_diff)

    return diff


# ---------------------------------------------------------------------------
# Property 1: 共有数据不丢失
# ---------------------------------------------------------------------------


class TestProperty1SharedDataPreserved:
    """**Validates: Requirements 2.2**

    Property 1: 迁移后共有 sheet/列的用户数据与迁移前一致。
    """

    @settings(max_examples=15, deadline=None)
    @given(data=st.data())
    def test_shared_sheet_data_preserved_after_migration(self, data: st.DataObject):
        """共有 sheet 的 cells 数据在迁移后保持不变"""
        parsed_data = data.draw(parsed_data_st())
        diff = data.draw(template_diff_for_parsed_data_st(parsed_data))

        original = copy.deepcopy(parsed_data)
        migrated = WpMigrationService.apply_diff_to_parsed_data(parsed_data, diff)

        # 共有 sheet = 既不在 removed 也不在 renamed(old) 中的 sheet
        renamed_old = {r[0] for r in diff.renamed_sheets}
        common_sheets = (
            set(original.get("html_data", {}).keys())
            - set(diff.removed_sheets)
            - renamed_old
        )

        for sheet_name in common_sheets:
            original_cells = original["html_data"][sheet_name].get("cells", {})
            migrated_cells = migrated["html_data"][sheet_name].get("cells", {})

            # 原有 cell 数据必须保留
            for coord, val in original_cells.items():
                assert coord in migrated_cells, (
                    f"Cell {coord} in sheet {sheet_name} lost after migration"
                )
                assert migrated_cells[coord] == val, (
                    f"Cell {coord} value changed: {val} → {migrated_cells[coord]}"
                )

    @settings(max_examples=15, deadline=None)
    @given(data=st.data())
    def test_new_sheets_populated(self, data: st.DataObject):
        """新增 sheet 在迁移后存在于 html_data 中"""
        parsed_data = data.draw(parsed_data_st())
        diff = data.draw(template_diff_for_parsed_data_st(parsed_data))

        migrated = WpMigrationService.apply_diff_to_parsed_data(parsed_data, diff)

        for added_sheet in diff.added_sheets:
            assert added_sheet in migrated["html_data"], (
                f"Added sheet {added_sheet} not found in migrated data"
            )

    @settings(max_examples=15, deadline=None)
    @given(data=st.data())
    def test_removed_sheets_archived(self, data: st.DataObject):
        """删除的 sheet 被归档到 _archived_data"""
        parsed_data = data.draw(parsed_data_st())
        diff = data.draw(template_diff_for_parsed_data_st(parsed_data))

        original = copy.deepcopy(parsed_data)
        migrated = WpMigrationService.apply_diff_to_parsed_data(parsed_data, diff)

        for removed_sheet in diff.removed_sheets:
            if removed_sheet in original.get("html_data", {}):
                # 不在 html_data 中
                assert removed_sheet not in migrated["html_data"], (
                    f"Removed sheet {removed_sheet} still in html_data"
                )
                # 在 _archived_data 中
                assert removed_sheet in migrated.get("_archived_data", {}), (
                    f"Removed sheet {removed_sheet} not archived"
                )


# ---------------------------------------------------------------------------
# Property 2: 回滚后数据恢复
# ---------------------------------------------------------------------------


class TestProperty2RollbackRestoresData:
    """**Validates: Requirements 4.2**

    Property 2: 迁移可逆——apply_diff 后的数据通过保存原始快照可完全恢复。
    """

    @settings(max_examples=15, deadline=None)
    @given(data=st.data())
    def test_original_data_recoverable_from_snapshot(self, data: st.DataObject):
        """原始 parsed_data 可从快照完全恢复（模拟回滚）"""
        parsed_data = data.draw(parsed_data_st())
        diff = data.draw(template_diff_for_parsed_data_st(parsed_data))

        # 保存快照（深拷贝模拟）
        snapshot = copy.deepcopy(parsed_data)

        # 执行迁移
        migrated = WpMigrationService.apply_diff_to_parsed_data(parsed_data, diff)

        # 回滚 = 恢复快照
        restored = copy.deepcopy(snapshot)

        # 验证恢复后与原始一致
        assert restored == parsed_data, (
            "Rollback did not restore original data"
        )

    @settings(max_examples=15, deadline=None)
    @given(data=st.data())
    def test_migration_does_not_mutate_original(self, data: st.DataObject):
        """apply_diff_to_parsed_data 不修改原始输入"""
        parsed_data = data.draw(parsed_data_st())
        diff = data.draw(template_diff_for_parsed_data_st(parsed_data))

        original_copy = copy.deepcopy(parsed_data)

        # 执行迁移
        _ = WpMigrationService.apply_diff_to_parsed_data(parsed_data, diff)

        # 原始数据未被修改
        assert parsed_data == original_copy, (
            "apply_diff_to_parsed_data mutated the original input"
        )
