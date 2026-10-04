"""判据：D1-6 QA 矩阵 `NOT_EXPRESSIBLE` 登记的三段实证链条不假。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 30 · Requirement 5.6
证据: .kiro/specs/d1-sync-row-table-engine-and-d1-coverage/evidence/task30-d1-6-feasibility.md

三段链条（不信推演，逐段现实测）：
1. 模板真实几何：`B17:D20` 确为 4×3 矩阵，行 21/22 是硬编码引用矩阵的派生公式行。
2. schema 硬约束：`contracts.py:_parse_field` 的 `cell.row_from` 只收单 int / `row_identity`，
   逐字确认。
3. 登记文案点名约束来源、owner、修法路径（同 `pilot_h1` 范式）。
"""
from __future__ import annotations

import io
import os
import sys
import warnings
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")
warnings.filterwarnings("ignore")

from app.services.workpaper_sync import phase5_d1_06_business_mode as D106  # noqa: E402
from app.services.workpaper_sync import phase5_d1_notes_receivable as D1  # noqa: E402


@pytest.fixture(scope="module")
def workbook() -> "openpyxl.Workbook":  # type: ignore[name-defined]
    import openpyxl

    return openpyxl.load_workbook(
        io.BytesIO(D1.read_authoritative_template()), data_only=False
    )


class TestQaMatrixGeometryIsAMeasuredFact:
    """段①：`B17:D20` 确为 4×3 矩阵，非推演。"""

    def test_matrix_header_row_has_three_fixed_combination_labels(
        self, workbook: "openpyxl.Workbook"  # type: ignore[name-defined]
    ) -> None:
        sheet = workbook["应收票据业务模式分析D1-6"]
        assert sheet["B16"].value == "信用等级高的银行承兑汇票"
        assert sheet["C16"].value == "信用等级低的银行承兑汇票"
        assert sheet["D16"].value == "商业承兑汇票"

    def test_matrix_data_rows_17_to_20_hold_yes_no_answers(
        self, workbook: "openpyxl.Workbook"  # type: ignore[name-defined]
    ) -> None:
        sheet = workbook["应收票据业务模式分析D1-6"]
        for row in (17, 18, 19, 20):
            for col in ("B", "C", "D"):
                value = sheet[f"{col}{row}"].value
                assert value in ("是", "否"), (
                    f"{col}{row}={value!r} 不是「是/否」二值——矩阵前提不成立"
                )

    def test_rows_21_22_are_derived_formulas_not_matrix_cells(
        self, workbook: "openpyxl.Workbook"  # type: ignore[name-defined]
    ) -> None:
        """行 21/22 是硬编码引用 B17:D20 的派生公式行，不是矩阵本身的一部分。"""
        sheet = workbook["应收票据业务模式分析D1-6"]
        for col in ("B", "C", "D"):
            formula_21 = str(sheet[f"{col}21"].value)
            assert formula_21.startswith("=IF("), formula_21
            assert f"{col}17" in formula_21 and f"{col}18" in formula_21, formula_21
            formula_22 = str(sheet[f"{col}22"].value)
            assert formula_22.startswith("=IF("), formula_22
            assert f"{col}21" in formula_22, formula_22


class TestStaticRegionSchemaConstraintIsAMeasuredFact:
    """段②：`contracts.py` 的 `cell.row_from` schema 硬约束逐字确认。"""

    def test_row_from_only_accepts_row_identity_or_single_int(self) -> None:
        source = (_BACKEND / "app/services/workpaper_sync/contracts.py").read_text(
            encoding="utf-8"
        )
        assert 'row_from == "row_identity"' in source
        assert "isinstance(row_from, int) and row_from >= 1" in source
        assert (
            "cell.row_from 必须是 `row_identity` 或 >=1 的静态行号" in source
        ), "schema 约束文案已变，NOT_EXPRESSIBLE 登记的依据需要重新核实"

    def test_no_range_or_list_branch_exists_for_row_from(self) -> None:
        """反证：schema 里确实没有第三种「行区间」分支（不是本判据凑不出反例）。"""
        source = (_BACKEND / "app/services/workpaper_sync/contracts.py").read_text(
            encoding="utf-8"
        )
        # `_parse_field` 函数体内只有两个合法分支（row_identity / 单 int），
        # 若未来有人加了 range/list 分支，这条会因分支数变化而需要人工复核。
        idx = source.index("def _parse_field")
        body = source[idx : idx + 3000]
        assert body.count("cell = CellMapping(") == 2, (
            "row_from 分支数不是预期的 2（row_identity + 单 int）——"
            "若新增了行区间分支，D1-6 的 NOT_EXPRESSIBLE 登记需要重新评估"
        )


class TestTransposedSheetSpecMismatchIsAMeasuredFact:
    """`TransposedSheetSpec` 的动态多实体假设与 D1-6 固定网格不匹配（对照 D4-12 真实先例）。"""

    def test_d4_12_is_a_dynamic_multi_entity_transposed_sheet(self) -> None:
        from app.services.workpaper_sync import phase5_d4_12_contract as D412

        assert D412.SPEC_D412.header_field_key is None
        assert D412.SPEC_D412.nested_fields_key is None
        # D4-12 是"字段数固定、实体列数可扩"——与 D1-6"实体列数固定、字段/问题数固定"相反。
        assert len(D412.SPEC_D412.field_rows) >= 20, (
            "D4-12 应有约 21 个字段行（每字段一整行）——若字段数骤降，"
            "对照结论(D1-6 与它形态不同)需要重新核实"
        )


class TestNotExpressibleRegistrationCitesTheRealConstraint:
    """段③：登记文案点名真实约束来源、owner、修法路径。"""

    def test_registration_note_cites_contracts_schema_constraint(self) -> None:
        note = D106.QA_MATRIX_NO_ROW_RANGE_CELL_MAPPING_NOT_EXPRESSIBLE
        assert "contracts.py" in note
        assert "row_from" in note
        assert "D1-6" in note or "D1-bm-qa-matrix" in note
        assert "owner" in note

    def test_registration_note_names_both_rejected_paths(self) -> None:
        """两条候选路径（TransposedSheetSpec / static_region）都要点名，不能只提一条。"""
        note = D106.QA_MATRIX_NO_ROW_RANGE_CELL_MAPPING_NOT_EXPRESSIBLE
        assert "TransposedSheetSpec" in note
        assert "static_region" in note

    def test_module_declares_no_row_table_sheet_spec(self) -> None:
        """本模块只登记评估结论，**不声明** `RowTableSheetSpec`——避免误导下游以为已可用。"""
        source = (
            _BACKEND / "app/services/workpaper_sync/phase5_d1_06_business_mode.py"
        ).read_text(encoding="utf-8")
        assert "RowTableSheetSpec(" not in source
        assert "TransposedSheetSpec(" not in source
