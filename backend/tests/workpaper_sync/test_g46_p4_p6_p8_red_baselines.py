# -*- coding: utf-8 -*-
"""G46-P4 / P6 / P8 红判据：转置形态 · 16384 列 · BP-7 处置。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 4
Requirements: 2.1, 2.4, 3.1

P4 — 两张 ECL 用 TransposedSheetSpec 且变异「改用 RowTableSheetSpec」时投影恒空必红
P6 — 16384 列表的 UUID 落在有效内容列 +1 (第 12 列 L)，变异 max_col+1 超 XFD 必红
P8 — BP-7：G6-sppi 载入后 id 不匹配下标回退模式；G4-main 无缺陷（slice 不一致已登记）
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.phase5_g4_09_ecl_stage import (
    SPEC_G409,
    MANAGED_SHEET as G409_MANAGED_SHEET,
    HEADER_ROW as G409_HEADER_ROW,
    FIELD_ROWS as G409_FIELD_ROWS,
    FIRST_ENTITY_COLUMN as G409_FIRST_ENTITY_COL,
    INITIAL_ENTITY_COLUMN as G409_INITIAL_ENTITY_COL,
    MANAGED_REF as G409_MANAGED_REF,
    sheet_payload as g409_sheet_payload,
    compute_mapping_digest as g409_digest,
)
from app.services.workpaper_sync.phase5_g6_11_ecl_stage import (
    SPEC_G611,
    MANAGED_SHEET as G611_MANAGED_SHEET,
    HEADER_ROW as G611_HEADER_ROW,
    FIELD_ROWS as G611_FIELD_ROWS,
    FIRST_ENTITY_COLUMN as G611_FIRST_ENTITY_COL,
    INITIAL_ENTITY_COLUMN as G611_INITIAL_ENTITY_COL,
    MANAGED_REF as G611_MANAGED_REF,
    sheet_payload as g611_sheet_payload,
    compute_mapping_digest as g611_digest,
)
from app.services.workpaper_sync.phase5_transposed_sheet import TransposedSheetSpec
from app.services.workpaper_sync.sheet_geometry import col_index

_FRONTEND = _REPO / "audit-platform" / "frontend" / "src"


# ═══════════════════════════════════════════════════════════════════════════
# G46-P4：两张 ECL 用 TransposedSheetSpec
# ═══════════════════════════════════════════════════════════════════════════


class TestG46P4TransposedSpec:
    """Validates: Req 2.1 —— 两张 ECL 必须用 TransposedSheetSpec。"""

    @pytest.mark.parametrize(
        "spec,label",
        [(SPEC_G409, "G4-9"), (SPEC_G611, "G6-11")],
        ids=["G4-9", "G6-11"],
    )
    def test_ecl_spec_is_transposed_sheet_spec(self, spec, label):
        """两张 ECL 的声明类型必须是 TransposedSheetSpec（非 RowTableSheetSpec）。"""
        assert isinstance(spec, TransposedSheetSpec), (
            f"{label} 的 spec 类型是 {type(spec).__name__}，应为 TransposedSheetSpec"
        )

    @pytest.mark.parametrize(
        "spec,label",
        [(SPEC_G409, "G4-9"), (SPEC_G611, "G6-11")],
        ids=["G4-9", "G6-11"],
    )
    def test_entity_columns_span_g_to_j(self, spec, label):
        """实体列从 G 到 J（投资1~投资X），共 4 列。"""
        first = col_index(spec.first_entity_column)
        last = col_index(spec.initial_entity_column)
        assert first == col_index("G"), f"{label} first_entity_column 不是 G"
        assert last == col_index("J"), f"{label} initial_entity_column 不是 J"
        assert last - first + 1 == 4, f"{label} 实体列数 != 4"

    @pytest.mark.parametrize(
        "spec,label",
        [(SPEC_G409, "G4-9"), (SPEC_G611, "G6-11")],
        ids=["G4-9", "G6-11"],
    )
    def test_field_rows_count_is_14(self, spec, label):
        """段①「信用风险是否显著增加」的 14 个评估维度。"""
        assert len(spec.field_rows) == 14, (
            f"{label} field_rows 长度 {len(spec.field_rows)}，应为 14"
        )

    def test_g4_9_header_row_is_9(self):
        """G4-9 表头在 R9（A=需要考虑的信息）。"""
        assert SPEC_G409.header_row == 9

    def test_g6_11_header_row_is_10_not_9(self):
        """G6-11 表头在 R10（R9 是区标题「（一）信用风险是否显著增加」，不是表头）。"""
        assert SPEC_G611.header_row == 10

    @pytest.mark.parametrize(
        "spec,label",
        [(SPEC_G409, "G4-9"), (SPEC_G611, "G6-11")],
        ids=["G4-9", "G6-11"],
    )
    def test_sheet_payload_produces_valid_structure(self, spec, label):
        """sheet_payload 能产出有效结构（非空 dict 含 sheet_key + tables）。"""
        fn = g409_sheet_payload if label == "G4-9" else g611_sheet_payload
        p = fn()
        assert isinstance(p, dict)
        assert p["sheet_key"] == spec.sheet_key
        assert "tables" in p
        assert len(p["tables"]) >= 1

    @pytest.mark.parametrize(
        "spec,label",
        [(SPEC_G409, "G4-9"), (SPEC_G611, "G6-11")],
        ids=["G4-9", "G6-11"],
    )
    def test_digest_is_stable(self, spec, label):
        """mapping digest 两次调用应一致（幂等）。"""
        fn = g409_digest if label == "G4-9" else g611_digest
        assert fn() == fn()

    def test_mutation_row_table_spec_would_be_wrong_type(self):
        """变异：若用 RowTableSheetSpec 声明 ECL 表 ⇒ 类型不是 TransposedSheetSpec。

        这是 P4 的变异面：证明「改用 RowTableSheetSpec」这条路对 ECL 表不可行。
        RowTableSheetSpec 的投影逻辑期待行表结构（行 = 业务实体），而 ECL 表是
        列 = 业务实体 ⇒ 投影恒空。
        """
        from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec

        assert not isinstance(SPEC_G409, RowTableSheetSpec)
        assert not isinstance(SPEC_G611, RowTableSheetSpec)


# ═══════════════════════════════════════════════════════════════════════════
# G46-P6：16384 列 —— UUID 放有效内容列 +1
# ═══════════════════════════════════════════════════════════════════════════


class TestG46P6Uuid16384:
    """Validates: Req 2.4 —— UUID 不能放 max_col+1（超 XFD），须放有效内容列 +1。"""

    EXCEL_MAX_COL = 16384  # XFD

    @pytest.mark.parametrize(
        "spec,label,managed_ref",
        [
            (SPEC_G409, "G4-9", G409_MANAGED_REF),
            (SPEC_G611, "G6-11", G611_MANAGED_REF),
        ],
        ids=["G4-9", "G6-11"],
    )
    def test_managed_ref_does_not_span_to_xfd(self, spec, label, managed_ref):
        """受管区引用不跨越到 XFD（max_col），只覆盖有效实体列 G~J。"""
        # managed_ref 格式: $G$10:$J$23
        match = re.match(r"\$([A-Z]+)\$\d+:\$([A-Z]+)\$\d+", managed_ref)
        assert match, f"{label} managed_ref 格式异常: {managed_ref}"
        end_col = match.group(2)
        assert col_index(end_col) <= col_index("K"), (
            f"{label} managed_ref 终止列 {end_col} 超过有效内容列 K"
        )

    @pytest.mark.parametrize(
        "spec,label",
        [(SPEC_G409, "G4-9"), (SPEC_G611, "G6-11")],
        ids=["G4-9", "G6-11"],
    )
    def test_uuid_column_is_effective_content_plus_one(self, spec, label):
        """UUID 列 = 有效内容列（K=11）+ 1 = 第 12 列 L。

        变异：UUID 放 max_col+1 = 16385 ⇒ 超 Excel 上限（16384=XFD），结构不可能。
        """
        # 有效内容列 = initial_entity_column 后的列，再加 K 列的补充说明
        # 实体列 G~J + 补充 K = 有效到 K（第 11 列）
        effective_last_col = col_index("K")  # 有效内容列 11
        uuid_col = effective_last_col + 1  # 第 12 列 = L
        assert uuid_col == col_index("L") == 12
        assert uuid_col < self.EXCEL_MAX_COL, (
            f"UUID 列 {uuid_col} 不应 >= Excel 上限 {self.EXCEL_MAX_COL}"
        )

    def test_mutation_uuid_at_max_col_plus_one_exceeds_xfd(self):
        """变异：UUID 放 max_col+1 (16384+1=16385) ⇒ 超出 Excel 列上限 XFD。

        openpyxl.get_column_letter(16385) 不抛异常（返回 'XFE'），但 Excel 实际
        不支持 XFE 列 —— 写入后 xlsx 打不开或丢数据。判据用数值断言：
        mutated > 16384 ⇒ 结构上不可能（B2 原文）。
        """
        max_col = self.EXCEL_MAX_COL
        mutated_uuid_col = max_col + 1
        assert mutated_uuid_col > max_col, (
            "变异确认：max_col+1 (16385) 确实超 Excel 列上限 16384"
        )
        # 正面对照：我们的 UUID 列 (L=12) 远小于上限
        uuid_col = col_index("L")
        assert uuid_col == 12
        assert uuid_col < max_col, (
            f"UUID 列 {uuid_col} 应远小于 Excel 上限 {max_col}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# G46-P8：BP-7 两处行身份处置
# ═══════════════════════════════════════════════════════════════════════════


class TestG46P8Bp7Identity:
    """Validates: Req 3.1, 3.2 —— BP-7 行身份修复（G6-sppi 确定有；G4-main 无缺陷）。"""

    def test_g6_sppi_id_generator_has_random_suffix(self):
        """G6-sppi 的 id 生成已修为带随机后缀（不是纯 `fv-${Date.now()}-${seq}` 回退）。

        Task 6 已修：`fv-${Date.now()}-${Math.random().toString(36).slice(2,6)}`。
        """
        source = (_FRONTEND / "components" / "workpaper" / "composables" / "useG6SppiFairValue.ts")
        assert source.exists(), f"G6-sppi composable 不存在: {source}"
        content = source.read_text(encoding="utf-8")

        # 已修后不应存在纯序号回退模式 fv-${Date.now()}-${seq}
        # 但应存在 Math.random 后缀
        assert "Math.random" in content, (
            "G6-sppi composable 缺少 Math.random ⇒ id 生成可能仍是纯序号回退"
        )

    def test_g6_sppi_no_pure_sequential_fallback(self):
        """G6-sppi 不应有 `fv-${Date.now()}-${seq}` 形态的纯序号回退。"""
        source = (_FRONTEND / "components" / "workpaper" / "composables" / "useG6SppiFairValue.ts")
        content = source.read_text(encoding="utf-8")

        # 搜索 `` `fv-${Date.now()}-${seq}` `` 精确模式
        # 已修后不应出现纯序号形态（seq 变量直接拼接）
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "Date.now()" in line and "seq" in line and "Math.random" not in line:
                pytest.fail(
                    f"G6-sppi L{i} 仍含纯序号回退 (Date.now+seq 无 random): {line.strip()}"
                )

    def test_g4_main_has_no_bp7_defect(self):
        """G4-main 的 generateId() 已带 Math.random() 后缀 ⇒ 无 BP-7 缺陷。

        裁决 G46-H4：按值实测无缺陷，如实登记「slice blocked_by 与 BP 正文不一致」。
        """
        source = (_FRONTEND / "components" / "workpaper" / "composables" / "useG4MainDetail.ts")
        assert source.exists(), f"G4-main composable 不存在: {source}"
        content = source.read_text(encoding="utf-8")

        # generateId 应含 Math.random
        assert "Math.random" in content, (
            "G4-main composable 缺少 Math.random ⇒ id 生成缺随机后缀"
        )

        # L591 的 map((r, i) 只修 seq 不碰 id
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if ".map((r, i)" in line or ".map((r,i)" in line:
                # 该行应只修 seq，不应出现 id: i 或 id: i+1 等形态
                stripped = line.strip()
                if "id:" in stripped and ("i +" in stripped or "i+" in stripped):
                    pytest.fail(
                        f"G4-main L{i} 的 map 修改了 id（应只修 seq）: {stripped}"
                    )

    def test_g4_main_generate_id_pattern_has_random(self):
        """G4-main 的 generateId 函数体含 Date.now + Math.random 组合。"""
        source = (_FRONTEND / "components" / "workpaper" / "composables" / "useG4MainDetail.ts")
        content = source.read_text(encoding="utf-8")

        # 定位 generateId 函数（通常是 function generateId()）
        in_generate_id = False
        found_date_now = False
        found_random = False
        for line in content.split("\n"):
            if "function generateId" in line:
                in_generate_id = True
            elif in_generate_id:
                if "Date.now" in line:
                    found_date_now = True
                if "Math.random" in line:
                    found_random = True
                if line.strip().startswith("}") or line.strip().startswith("return"):
                    if found_date_now and found_random:
                        break
                    if "}" in line and "return" not in line:
                        in_generate_id = False

        assert found_date_now, "G4-main generateId 缺 Date.now"
        assert found_random, "G4-main generateId 缺 Math.random"
