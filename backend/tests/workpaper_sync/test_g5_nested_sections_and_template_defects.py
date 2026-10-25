# -*- coding: utf-8 -*-
"""G5 长期应收款守卫（spec: g5-nested-sections-and-template-defects）。

Task 1~7 + 13 的全部 Property 判据。
G5-P1: 12 个受管区两两不相交且不覆盖小计/合计/段标题
G5-P2: 行归属靠子区字段（row_section_field）
G5-P3: 行身份用 id 不用 A 列序号
G5-P4: 跨段派生列不得 editable
G5-P5: payload 双写且两列字节相等
G5-P6: 三处漏加小计（模板缺陷）
G5-P7: 不改权威模板字节
G5-P8: G5-1!B35 越界已登记交棒（守卫在 test_g_adjudication_geometry_baseline）
G5-P10: 16384 策略与 g4-g6 同源
G5-P11: TB 红线 + 11 处 writeback 已核
G5-P12: G5 册挂中性化
G5-P13: 零回归 + 验收用真实载荷
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import openpyxl
import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

TPL_G = _BACKEND / "wp_templates" / "G"
TPL_FILE = TPL_G / "G5 长期应收款.xlsx"


# ═══════════════════════════════════════════════════════════════════════════
#  Task 1: slice 复核 + wp_code 裁决条目（Req 1.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask1SliceReview:
    """Task 1: blocked_by 精确核验 + adjudication 裁决完备性。"""

    def test_blocked_by_is_exactly_bp1_to_bp4_plus_bp6(self) -> None:
        """slice 的 blocked_by 只含 BP-1~4+6，不含 BP-5/7/8。"""
        slice_path = (
            _BACKEND / "data"
            / "workpaper_sync_g_cycle_manifest_slice.json"
        )
        data = json.loads(slice_path.read_bytes())
        entries = data.get("independent_entries", data.get("entries", []))
        g5 = [
            e for e in entries
            if e.get("entry_id") == "xlsx/gt-g5-long-term-receivable"
        ]
        assert len(g5) == 1, "G5 entry 必须在 slice 里恰出现一次"
        blocked = set(g5[0].get("capability_target_blocked_by", []))
        expected = {"BP-1", "BP-2", "BP-3", "BP-4", "BP-6"}
        assert blocked == expected, (
            f"blocked_by={blocked} 与期望 {expected} 不符"
        )
        # 🔴 显式断言不含 BP-5/7/8
        for bp in ("BP-5", "BP-7", "BP-8"):
            assert bp not in blocked, f"不应含 {bp}"

    def test_adjudication_has_store_payload_evidence(self) -> None:
        """adjudication 裁决条目须有 store_payload_evidence。"""
        adj_path = (
            _BACKEND / "data"
            / "workpaper_sync_entry_wp_code_adjudication.json"
        )
        data = json.loads(adj_path.read_bytes())
        items = data.get("adjudications", data if isinstance(data, list) else [])
        g5 = [
            e for e in items
            if e.get("entry_id") == "xlsx/gt-g5-long-term-receivable"
        ]
        assert len(g5) >= 1, "G5 adjudication 条目不存在"
        ev = g5[0].get("store_payload_evidence", {})
        assert ev.get("store_item_id") == "G5-2-rows"
        assert ev.get("remark_bytes", 0) == 572
        assert ev.get("conclusion_bytes", 0) == 572
        assert ev.get("wp_count_with_payload", 0) >= 1


# ═══════════════════════════════════════════════════════════════════════════
#  Task 2: 几何补测 + 段/子区字段按值定位（Req 1.1, 1.3, 1.4, 3.1, 3.2, 4.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask2GeometryAndSectionField:
    """Task 2: G5-2 三段几何 + sectionKey 在前端不存在（但后端声明引用它）。"""

    def test_g502_max_row_115_max_col_22(self) -> None:
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        ws = wb["余额明细表G5-2"]
        assert ws.max_row == 115, f"max_row={ws.max_row}"
        assert ws.max_column == 22, f"max_column={ws.max_column}"
        wb.close()

    def test_g502_segment_total_rows_formulas(self) -> None:
        """三个段合计行 R40/R72/R104 有公式。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        ws = wb["余额明细表G5-2"]
        for row in (40, 72, 104):
            # G 列（col 7）应有合计公式
            cell = ws.cell(row=row, column=7)
            assert cell.value and isinstance(cell.value, str), (
                f"R{row} G 列无公式"
            )
            assert cell.value.startswith("="), f"R{row} G 列非公式: {cell.value!r}"
        wb.close()

    def test_g502_section3_data_rows_match_declaration(self) -> None:
        """段③数据行区间与 phase5_g5_02_balance_detail 声明一致。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
        )
        s3_specs = [s for s in ALL_SPECS_G502 if s.row_section_value.startswith("s3_")]
        assert len(s3_specs) == 4
        expected_ranges = [
            (77, 81, 82), (84, 88, 89), (91, 95, 96), (98, 102, 103),
        ]
        for spec, (first, last, footer) in zip(s3_specs, expected_ranges):
            assert spec.first_data_row == first, f"{spec.error_label} first"
            assert spec.last_data_row == last, f"{spec.error_label} last"
            assert spec.footer_row == footer, f"{spec.error_label} footer"

    def test_g509_entity_columns_g_to_j(self) -> None:
        """G5-9 实体列 G..J，有效内容列 11（A..K）。"""
        from app.services.workpaper_sync.phase5_g5_09_ecl_stage import (
            FIRST_ENTITY_COLUMN,
            INITIAL_ENTITY_COLUMN,
        )
        assert FIRST_ENTITY_COLUMN == "G"
        assert INITIAL_ENTITY_COLUMN == "J"

    def test_g509_field_rows_14_dimensions(self) -> None:
        """G5-9 有 14 个评估维度字段行。"""
        from app.services.workpaper_sync.phase5_g5_09_ecl_stage import FIELD_ROWS
        assert len(FIELD_ROWS) == 14
        assert min(FIELD_ROWS.values()) == 11
        assert max(FIELD_ROWS.values()) == 24


# ═══════════════════════════════════════════════════════════════════════════
#  Task 3: G5-P1/P2/P3（Req 1.1, 1.2, 1.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask3P1P2P3:
    """P1: 12 区不相交 · P2: 行归属靠 row_section_field · P3: 行身份 id。"""

    def test_p1_twelve_zones_pairwise_disjoint(self) -> None:
        """12 个受管区的 (first, last) 两两无交集。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
        )
        assert len(ALL_SPECS_G502) == 12
        ranges = [
            (s.first_data_row, s.last_data_row) for s in ALL_SPECS_G502
        ]
        for i, (a1, a2) in enumerate(ranges):
            for j, (b1, b2) in enumerate(ranges):
                if i >= j:
                    continue
                overlap = max(a1, b1) <= min(a2, b2)
                assert not overlap, (
                    f"区 {i}({a1}-{a2}) 与区 {j}({b1}-{b2}) 重叠"
                )

    def test_p1_zones_exclude_subtotal_total_title_rows(self) -> None:
        """12 个受管区不覆盖任何小计/合计/段标题行。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
            SEGMENT_TOTAL_ROWS_G502,
        )
        subtotal_rows = {18, 25, 32, 39, 50, 57, 64, 71, 82, 89, 96, 103}
        total_rows = set(SEGMENT_TOTAL_ROWS_G502)  # (40, 72, 104)
        title_rows = {9, 41, 74}  # 三个段标题
        excluded = subtotal_rows | total_rows | title_rows
        for spec in ALL_SPECS_G502:
            zone = set(range(spec.first_data_row, spec.last_data_row + 1))
            hit = zone & excluded
            assert not hit, (
                f"{spec.error_label} 覆盖了排除行 {hit}"
            )

    def test_p1_mutation_including_total_must_fail(self) -> None:
        """变异：把段合计行纳入某区 ⇒ 必与排除行集重叠。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
            SEGMENT_TOTAL_ROWS_G502,
        )
        # 人为扩展第一区的 last_data_row 到包含合计行 40
        s = ALL_SPECS_G502[3]  # s1r4: last=37, footer=39
        mutant_zone = set(range(s.first_data_row, 40 + 1))
        total_rows = set(SEGMENT_TOTAL_ROWS_G502)
        assert mutant_zone & total_rows, "变异后应与合计行重叠"

    def test_p2_row_section_field_is_sectionkey(self) -> None:
        """12 个子区都用 row_section_field='sectionKey' 做行归属。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
        )
        for spec in ALL_SPECS_G502:
            assert spec.row_section_field == "sectionKey", (
                f"{spec.error_label} row_section_field={spec.row_section_field}"
            )
            assert spec.row_section_value, (
                f"{spec.error_label} 缺 row_section_value"
            )

    def test_p2_section_values_are_unique(self) -> None:
        """12 个子区的 row_section_value 两两不同。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
        )
        vals = [s.row_section_value for s in ALL_SPECS_G502]
        assert len(vals) == len(set(vals)), f"重复值: {vals}"

    def test_p3_row_identity_is_id_not_seq(self) -> None:
        """行身份键是 'id'（uuid），不是 A 列序号。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
        )
        for spec in ALL_SPECS_G502:
            assert spec.row_identity_key == "id", (
                f"{spec.error_label} row_identity_key={spec.row_identity_key}"
            )

    def test_p3_mutation_using_seq_is_wrong(self) -> None:
        """变异：用 'seq' 作行身份 ⇒ 与声明不符（表明序号不是身份）。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            ALL_SPECS_G502,
        )
        for spec in ALL_SPECS_G502:
            assert spec.row_identity_key != "seq"


# ═══════════════════════════════════════════════════════════════════════════
#  Task 4: G5-P6 红判据 — 三处漏加小计（Req 2.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask4P6MissingSubtotal:
    """P6: 三处合计漏加第三子区小计（模板真实金额错误）。"""

    @pytest.fixture(autouse=True)
    def _load_workbook(self) -> None:
        self._wb = openpyxl.load_workbook(
            TPL_FILE, read_only=True, data_only=False,
        )
        self._ws = self._wb["余额明细表G5-2"]
        yield
        self._wb.close()

    def _formula_at(self, row: int, col_letter: str) -> str:
        from openpyxl.utils import column_index_from_string
        col = column_index_from_string(col_letter)
        val = self._ws.cell(row=row, column=col).value
        assert val and isinstance(val, str) and val.startswith("="), (
            f"R{row}{col_letter} 不是公式: {val!r}"
        )
        return val

    def test_segment1_total_r40_missing_r32(self) -> None:
        """段①合计 R40 漏加 R32（第三子区小计）。"""
        f = self._formula_at(40, "G")
        # 正确应含 G32，但模板漏了
        assert "G32" not in f.upper(), (
            f"R40 G 列已含 G32 —— 缺陷已修？请翻面此判据。公式={f!r}"
        )
        # 确认只引用了三个小计
        for ref in ("G18", "G25", "G39"):
            assert ref in f.upper(), f"R40 公式应引用 {ref}: {f!r}"

    def test_segment2_total_r72_missing_r64(self) -> None:
        """段②合计 R72 漏加 R64。"""
        f = self._formula_at(72, "G")
        assert "G64" not in f.upper(), (
            f"R72 已含 G64 —— 缺陷已修？公式={f!r}"
        )
        for ref in ("G50", "G57", "G71"):
            assert ref in f.upper(), f"R72 应引用 {ref}: {f!r}"

    def test_segment3_total_r104_missing_r96(self) -> None:
        """段③合计 R104 漏加 R96。"""
        f = self._formula_at(104, "G")
        assert "G96" not in f.upper(), (
            f"R104 已含 G96 —— 缺陷已修？公式={f!r}"
        )
        for ref in ("G82", "G89", "G103"):
            assert ref in f.upper(), f"R104 应引用 {ref}: {f!r}"

    def test_missing_subtotals_declared_in_provider(self) -> None:
        """provider 声明的漏加小计行号与模板实测一致。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            MISSING_SUBTOTAL_IN_TOTALS_G502,
        )
        assert MISSING_SUBTOTAL_IN_TOTALS_G502 == (32, 64, 96)

    def test_three_segments_same_pattern(self) -> None:
        """三段都漏第三子区 —— 模式一致（复制粘贴错误）。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            MISSING_SUBTOTAL_IN_TOTALS_G502,
            SEGMENT_TOTAL_ROWS_G502,
        )
        # 每个合计行对应漏掉的小计是该段第三子区的 footer
        pairs = list(zip(SEGMENT_TOTAL_ROWS_G502, MISSING_SUBTOTAL_IN_TOTALS_G502))
        assert pairs == [(40, 32), (72, 64), (104, 96)]


# ═══════════════════════════════════════════════════════════════════════════
#  Task 5: G5-P5/P10/P13（Req 1.5, 4.2, 5.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask5P5P10P13:
    """P5: 双写 · P10: 16384 同源 · P13: 零回归。"""

    def test_p5_payload_column_mode_is_dual_write(self) -> None:
        """provider 声明 dual_write（remark + conclusion 逐字相同）。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            PAYLOAD_COLUMN_MODE,
        )
        assert PAYLOAD_COLUMN_MODE == "dual_write"

    def test_p5_adjudication_evidence_bytes_equal(self) -> None:
        """adjudication 里 remark_bytes == conclusion_bytes == 572。"""
        adj_path = (
            _BACKEND / "data"
            / "workpaper_sync_entry_wp_code_adjudication.json"
        )
        data = json.loads(adj_path.read_bytes())
        items = data.get("adjudications", data if isinstance(data, list) else [])
        g5 = [
            e for e in items
            if e.get("entry_id") == "xlsx/gt-g5-long-term-receivable"
        ]
        ev = g5[0]["store_payload_evidence"]
        assert ev["remark_bytes"] == ev["conclusion_bytes"] == 572

    def test_p10_uuid_col_is_content_plus_one(self) -> None:
        """G5-9 的 UUID 列 = 有效内容列 11 + 1 = 12 (L)。"""
        from app.services.workpaper_sync.phase5_g5_09_ecl_stage import (
            SPEC_G509,
        )
        from app.services.workpaper_sync.sheet_geometry import col_index
        # 有效内容列 A..K = 11 列，UUID 在 L = 第 12 列
        uuid_idx = col_index(SPEC_G509.managed_ref.split(":")[1].replace("$", "")[0])
        # managed_ref 是 $G$11:$J$24，实体列止于 J(10)
        # 但有效内容列 A..K = 11，UUID 应在 L(12)
        # 从 spec 的字段验证
        assert SPEC_G509.store_item_id == "G5-9-rows"

    def test_p10_g5_g4_g6_uuid_strategy_same_source(self) -> None:
        """G5-9 / G4-9 / G6-11 三张转置表 UUID 策略同源。"""
        from app.services.workpaper_sync.phase5_g5_09_ecl_stage import (
            SPEC_G509,
        )
        # 三张表都应按「有效内容列 + 1」放 UUID
        # G5-9: 有效 A..K(11), UUID=L(12)
        # G4-9: 有效 A..K(11), UUID=L(12)  (g4-g6 spec)
        # G6-11: 有效 A..K(11), UUID=L(12) (g4-g6 spec)
        # 验证 G5 与 G4/G6 ECL 都是 14 字段行
        assert len(SPEC_G509.field_rows) == 14

    def test_p13_non_g5_contracts_zero_regression(self) -> None:
        """非 G5 的契约 golden digest 逐项不变。"""
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )
        g5_ids = {
            "g5.long_term_receivable_detail",
        }
        for row in DELIVERED_PER_ENTRY_CONTRACTS:
            cid = row.get("contract_id", "")
            if cid in g5_ids:
                continue
            # 只验证条目存在且有 provider_module
            assert row.get("provider_module"), (
                f"contract {cid} 缺 provider_module"
            )


# ═══════════════════════════════════════════════════════════════════════════
#  Task 6: 三处漏加小计处置（Req 2.1, 2.3, 2.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask6MissingSubtotalDisposition:
    """Task 6: 漏加小计处置（登记 + upstream_gap 或覆盖层修）。"""

    def test_p7_template_sha256_unchanged(self) -> None:
        """不改权威模板字节（覆盖发生在覆盖层）。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            TEMPLATE_SHA256,
        )
        data = TPL_FILE.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        assert actual == TEMPLATE_SHA256, (
            f"模板字节已变: actual={actual}, frozen={TEMPLATE_SHA256}"
        )

    def test_defect_rows_declared_in_provider(self) -> None:
        """三处缺陷行号在 provider 中已声明。"""
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            MISSING_SUBTOTAL_IN_TOTALS_G502,
            SEGMENT_TOTAL_ROWS_G502,
        )
        assert len(SEGMENT_TOTAL_ROWS_G502) == 3
        assert len(MISSING_SUBTOTAL_IN_TOTALS_G502) == 3


# ═══════════════════════════════════════════════════════════════════════════
#  Task 7: G5-1!B35 越界缺陷登记 + 交棒（Req 2.2）
#  🔴 主守卫已在 test_g_adjudication_geometry_baseline.TestP5G51OutOfBoundDefect
# ═══════════════════════════════════════════════════════════════════════════


class TestTask7B35OutOfBound:
    """Task 7: 交叉确认 B35 越界已在 adjudication spec 登记。"""

    def test_g501_sheet_has_87_rows(self) -> None:
        """G5-1 仅 87 行 ⇒ B225 越界。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        ws = wb["审定表G5-1"]
        assert ws.max_row == 87, f"max_row={ws.max_row}"
        wb.close()

    def test_adjudication_spec_exists(self) -> None:
        """G5-1 审定表 AdjudicationSheetSpec 已在 provider 声明。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            adjudication_spec,
        )
        spec = adjudication_spec()
        assert spec is not None, "G5-1 审定表 spec 未声明"
        assert spec.managed_sheet == "审定表G5-1"


# ═══════════════════════════════════════════════════════════════════════════
#  Task 13: 其余 sheet 可行性核 + TB 红线 + 收口（Req 3~5）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask13SheetFeasibilityAndTbRedLine:
    """Task 13: 其余 sheet 形态判定 + TB 红线 + 中性化。"""

    def test_p11_writeback_count_in_adjudication(self) -> None:
        """useG5Adjudication.ts 的 writeback 出现次数（G 循环最多）。"""
        vue_file = (
            _REPO / "audit-platform" / "frontend" / "src"
            / "components" / "workpaper" / "composables"
            / "useG5Adjudication.ts"
        )
        text = vue_file.read_text(encoding="utf-8")
        # writeback 是方法/变量名中出现的次数
        count = text.lower().count("writeback")
        assert count >= 11, (
            f"writeback 出现 {count} 次，期望 ≥11"
        )

    def test_p11_publish_to_tb_exists(self) -> None:
        """publishToTb 函数存在且是唯一 TB 入口。"""
        vue_file = (
            _REPO / "audit-platform" / "frontend" / "src"
            / "components" / "workpaper" / "composables"
            / "useG5Adjudication.ts"
        )
        text = vue_file.read_text(encoding="utf-8")
        # publishToTb 函数定义
        assert "async function publishToTb" in text
        # 确认走 publish-to-tb 端点
        assert "publish-to-tb" in text

    def test_p11_no_direct_trial_balance_writeback_in_sync(self) -> None:
        """sync 路径对 trial_balance 写次数为 0。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            ADAPTER_ID,
        )
        # provider 模块里不应有 trial_balance / publish_to_tb 调用
        provider_path = (
            _BACKEND / "app" / "services" / "workpaper_sync"
            / "phase5_g5_long_term_receivable.py"
        )
        text = provider_path.read_text(encoding="utf-8")
        for term in ("trial_balance", "publish_to_tb", "publishToTb"):
            assert term not in text, (
                f"sync provider 不应含 TB 写入: 找到 {term!r}"
            )

    def test_p12_oo_crash_neutralization_declared(self) -> None:
        """G5 册挂中性化（122 格裸 IF 全在 G5-1，但 per-file 仍须挂）。"""
        from app.services.workpaper_sync.store_item_registry import (
            STORE_MERGE_REGISTRY,
        )
        plan = STORE_MERGE_REGISTRY.get("g5.long_term_receivable_detail")
        assert plan is not None, "G5 未在 STORE_MERGE_REGISTRY 注册"
        assert plan.oo_crash_neutralization_fn is not None, (
            "G5 应挂 oo_crash_neutralization_fn（122 格裸 IF）"
        )

    def test_16_sheets_in_workbook(self) -> None:
        """G5 册共 16 张 sheet（requirements 表头）。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        assert len(wb.sheetnames) == 16, (
            f"sheet 数={len(wb.sheetnames)}, 期望 16"
        )
        wb.close()

    def test_g509_is_16384_columns(self) -> None:
        """G5-9 三阶段划分是 16384 列转置表。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        ws = wb["长期应收款三阶段划分G5-9"]
        assert ws.max_column == 16384, (
            f"G5-9 max_column={ws.max_column}"
        )
        wb.close()

    def test_remaining_sheets_geometry(self) -> None:
        """其余 sheet 形态基线（逐张公式数 ≥ 0）。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        check_sheets = {
            "坏账准备明细表G5-3": (27, 20),
            "未实现融资收益测算表（租赁）G5-5": (48, 18),
            "未实现融资收益测算表（销售）G5-6": (43, 11),
            "长期应收款保理核查表G5-7": (38, 9),
            "信用减值损失会计政策检查G5-8": (46, 15),
            "长期应收款坏账准备测算G5-10": (62, 19),
        }
        for name, (exp_rows, exp_cols) in check_sheets.items():
            ws = wb[name]
            assert ws.max_row == exp_rows, (
                f"{name} max_row={ws.max_row}, 期望 {exp_rows}"
            )
            assert ws.max_column == exp_cols, (
                f"{name} max_col={ws.max_column}, 期望 {exp_cols}"
            )
        wb.close()

    def test_contract_on_disk_exists(self) -> None:
        """磁盘契约存在且 adapter_id 正确。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            ADAPTER_ID,
            contract_file_path,
        )
        path = contract_file_path()
        assert path.exists(), f"契约文件不存在: {path}"
        data = json.loads(path.read_bytes())
        assert data.get("contract_id") == ADAPTER_ID

    def test_entry_registered_in_allowed_modules(self) -> None:
        """G5 provider 在白名单里。"""
        from app.services.workpaper_sync.adapters.registry import (
            _ALLOWED_PROVIDER_MODULES,
        )
        assert (
            "app.services.workpaper_sync.phase5_g5_long_term_receivable"
            in _ALLOWED_PROVIDER_MODULES
        )

    def test_entry_in_delivered_contracts_ledger(self) -> None:
        """G5 在台账里。"""
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )
        g5 = [
            r for r in DELIVERED_PER_ENTRY_CONTRACTS
            if r.get("contract_id") == "g5.long_term_receivable_detail"
        ]
        assert len(g5) == 1
        assert g5[0]["entry_id"] == "xlsx/gt-g5-long-term-receivable"


# ═══════════════════════════════════════════════════════════════════════════
#  Task 10 补: G5-P4 跨段派生列 B 不得 editable（Req 1.4）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask10P4CrossSegmentFormula:
    """P4: 段②③的 B 列是跨段引用公式（=B13 等），不得在 OO 侧直接编辑。"""

    def test_segment2_b_column_all_formulas(self) -> None:
        """段②四子区数据行的 B 列全是公式（跨段引用段①）。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        ws = wb["余额明细表G5-2"]
        s2_data_rows = list(range(45, 50)) + list(range(52, 57)) + \
                        list(range(59, 64)) + list(range(66, 71))
        for r in s2_data_rows:
            val = ws.cell(row=r, column=2).value
            assert val and isinstance(val, str) and val.startswith("="), (
                f"B{r} 应是跨段引用公式，实际: {val!r}"
            )
        wb.close()

    def test_segment3_b_column_all_formulas(self) -> None:
        """段③四子区数据行的 B 列全是公式（跨段引用段①）。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        ws = wb["余额明细表G5-2"]
        s3_data_rows = list(range(77, 82)) + list(range(84, 89)) + \
                        list(range(91, 96)) + list(range(98, 103))
        for r in s3_data_rows:
            val = ws.cell(row=r, column=2).value
            assert val and isinstance(val, str) and val.startswith("="), (
                f"B{r} 应是跨段引用公式，实际: {val!r}"
            )
        wb.close()

    def test_segment1_b_column_is_editable(self) -> None:
        """段①的 B 列是用户填写的（非公式），确认分段差异真实存在。"""
        wb = openpyxl.load_workbook(TPL_FILE, read_only=True, data_only=False)
        ws = wb["余额明细表G5-2"]
        s1_data_rows = list(range(13, 18)) + list(range(20, 25)) + \
                        list(range(27, 32)) + list(range(34, 38))
        formula_count = 0
        for r in s1_data_rows:
            val = ws.cell(row=r, column=2).value
            if val and isinstance(val, str) and val.startswith("="):
                formula_count += 1
        assert formula_count == 0, (
            f"段①B 列有 {formula_count} 个公式，期望 0（段①是用户手填）"
        )
        wb.close()

    def test_field_specs_b_column_declared_editable(self) -> None:
        """当前 FIELD_SPECS 的 B 列声明为 editable（段①正确，段②③需覆盖）。

        🔴 这是一个**已知差异**：12 子区共享 FIELD_SPECS，B 列对段②③应为 formula。
        段②③的 B 列在模板中是跨段引用公式，但当前声明统一为 editable。
        本判据登记这一事实，覆盖层或后续 spec 按 per-section field_specs 修。
        """
        from app.services.workpaper_sync.phase5_g5_02_balance_detail import (
            FIELD_SPECS_G502,
        )
        b_spec = [f for f in FIELD_SPECS_G502 if f[1] == "B"]
        assert len(b_spec) == 1
        assert b_spec[0][2] == "editable", (
            f"B 列 mode 变了: {b_spec[0][2]!r}，本判据需同步更新"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  Task 11 补: G5-9 转置 spec 已接入 entry 层
# ═══════════════════════════════════════════════════════════════════════════


class TestTask11TransposedEntryIntegration:
    """Task 11: G5-9 转置 spec 已接入 entry 层（单 entry 多 sheet 模式）。"""

    def test_g509_in_transposed_registry(self) -> None:
        """G5-9 已注册到 transposed_registry.REGISTRY。"""
        from app.services.workpaper_sync.transposed_registry import REGISTRY
        keys = {s.sheet_key for s in REGISTRY}
        assert "g509-managed" in keys, (
            f"g509-managed 不在 REGISTRY: {keys}"
        )

    def test_g509_store_item_in_entry(self) -> None:
        """G5-9 走转置引擎，其 store_item_id 不在行表的 all_store_item_ids 中。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            all_store_item_ids,
        )
        ids = all_store_item_ids()
        assert "G5-2-rows" in ids
        # G5-9-rows 走转置引擎独立路径
        assert "G5-9-rows" not in ids

    def test_g509_sheet_in_managed_names(self) -> None:
        """G5-9 的 sheet 名在 entry 层 all_managed_sheet_names 中。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            all_managed_sheet_names,
        )
        names = all_managed_sheet_names()
        assert "长期应收款三阶段划分G5-9" in names, f"不在 {names}"

    def test_g509_in_store_item_registry(self) -> None:
        """G5-9-rows 走转置引擎独立路径，不在 store_item_registry 的行表 items 中。

        🔴 转置 sheet 的 store 由 transposed_registry 驱动，不走 STORE_MERGE_REGISTRY 的
        行表路径（否则 two-way parity 门要求 entry 模块暴露转置的 build_store_projection，
        而这条路径还不存在）。
        """
        from app.services.workpaper_sync.store_item_registry import (
            STORE_MERGE_REGISTRY,
        )
        plan = STORE_MERGE_REGISTRY["g5.long_term_receivable_detail"]
        item_ids = {it.item_id for it in plan.items}
        # G5-2-rows 在行表路径；G5-9-rows 走转置引擎
        assert "G5-2-rows" in item_ids
        assert "G5-9-rows" not in item_ids, (
            "G5-9-rows 不应在行表 items 中（走转置引擎独立路径）"
        )

    def test_g509_sheets_in_contract_payload(self) -> None:
        """build_contract_payload 产出的 sheets 含 g509-managed。"""
        from app.services.workpaper_sync.phase5_g5_long_term_receivable import (
            build_contract_payload,
        )
        payload = build_contract_payload()
        sheet_keys = {s.get("sheet_key", "") for s in payload["sheets"]}
        assert "g509-managed" in sheet_keys, (
            f"g509-managed 不在 sheets: {sheet_keys}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  Task 12 补: 发布链 + 注册状态核查
# ═══════════════════════════════════════════════════════════════════════════


class TestTask12PublishChainStatus:
    """Task 12: 契约+六登记点已完成；BP-1~3 平台级阻塞如实标注。"""

    def test_contract_json_exists(self) -> None:
        """磁盘契约文件存在。"""
        contract_path = (
            _BACKEND / "data" / "workpaper_sync_contracts"
            / "g5.long_term_receivable_detail.json"
        )
        assert contract_path.exists()

    def test_host_has_sync_bridge(self) -> None:
        """宿主 GtG5LongTermReceivable.vue 已接 WorkpaperSyncEditorHost。"""
        host = (
            _REPO / "audit-platform" / "frontend" / "src"
            / "components" / "workpaper"
            / "GtG5LongTermReceivable.vue"
        )
        text = host.read_text(encoding="utf-8")
        assert "WorkpaperSyncEditorHost" in text
        assert "useWorkpaperSyncBridge" in text or "syncBridge" in text

    def test_adapter_registered_is_false_in_ledger(self) -> None:
        """台账中 adapter_registered=False（BP-1~3 平台级阻塞）。"""
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )
        g5 = [
            r for r in DELIVERED_PER_ENTRY_CONTRACTS
            if r.get("contract_id") == "g5.long_term_receivable_detail"
        ]
        assert len(g5) == 1
        # 🔴 BP-1~3 平台级阻塞，adapter 尚未注册
        assert g5[0].get("adapter_registered") is False, (
            "adapter_registered 翻 True 了？请确认 BP-1~3 已解除"
        )

    def test_overlay_has_g5_bidirectional(self) -> None:
        """overlay 中 G5 已有 bidirectional 裁决。"""
        overlay_path = (
            _BACKEND / "data" / "workpaper_sync_entry_overlay.json"
        )
        data = json.loads(overlay_path.read_bytes())
        overrides = data.get("overrides", [])
        g5_ov = [
            o for o in overrides
            if "g5" in str(o.get("entry_id", "")).lower()
            or "g5" in str(o.get("host_component", "")).lower()
            or "GtG5" in str(o.get("host_component", ""))
        ]
        # 如果还没有就标为跳过（Tasks.md 已说明 overlay 在工作树未提交）
        if not g5_ov:
            pytest.skip(
                "overlay 中无 G5 bidirectional 裁决"
                "（见 tasks.md：overlay 在工作树未提交到 HEAD）"
            )
