# -*- coding: utf-8 -*-
"""F3 canary 判据：Property 1 / 2 / 3 / 4 / 9 + 契约装配可解析。

spec: f3-sync-coverage-and-first-canary
      Task 3（P1/P2/P3）· Task 4（P4/P9）· Task 7（provider）· Task 8（canary 薄声明）
      Requirements 1.1 / 1.2 / 1.5 / 2.1 / 2.2 / 2.4 / 3.3

🔴 Property 编号 spec-scoped：本文件的 `Property N` 读作 `F3-P{N}`。

═══ 与 F1 判据的差别（防复发）═══

F1 的四个判据文件全部只断言常量（`WP_CODES == {"F1P"}` 之类），**从不真调**
`assert_entry_selectable`、**从不**过 `parse_contract` ⇒ 守卫空转，直到 golden digest 门
才炸出 `table anchor 必须是 A1 单元格，实得 None`。本文件因此强制两条真调：

  * `assert_entry_selectable(resolution=…)` 对**真 manifest** 真调（FC-2 对 E1 空转的防复发）
  * `build_contract_payload()` 过**真 `parse_contract`**（对 F1 手写 payload 的防复发）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_f3_05_overdue as F305  # noqa: E402
from app.services.workpaper_sync import phase5_f3_notes_payable as F3  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_extract import BindingKind  # noqa: E402
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    StoreKind,
    managed_field_specs,
)

F3_ENTRY_ID = "xlsx/gt-f3-notes-payable"

#: 真库实测的 F3-5 载荷（2 行，仅行身份有值 —— 业务字段全空）。
#: 🔴 spec 裁决 F3-H1 写「可做真数据往返」需修正：实测是「真行身份 + 空业务值」
#:    （用户打开过表但没录数）⇒ 有意义数值的 roundtrip 仍需 seed。
REAL_PAYLOAD_ROWS = [
    {
        "rowId": "f3o-mrpn3xhk-ypdgcsm", "seq": 1, "attSlot": 1, "noteType": "", "ticketNo": "",
        "drawer": "", "acceptor": "", "payee": "", "issueDate": "", "dueDate": "",
        "termDays": 0, "overdueDays": 0, "interestRate": 0, "faceValue": 0,
        "postPaymentAmount": 0, "unpaidAmount": 0, "loanConditions": "", "isAdjusted": "",
        "collateralName": "", "collateralAmount": 0, "riskFlags": [],
    },
    {
        "rowId": "f3o-mrpn42p2-50spgcj", "seq": 2, "attSlot": 2, "noteType": "", "ticketNo": "",
        "drawer": "", "acceptor": "", "payee": "", "issueDate": "", "dueDate": "",
        "termDays": 0, "overdueDays": 0, "interestRate": 0, "faceValue": 0,
        "postPaymentAmount": 0, "unpaidAmount": 0, "loanConditions": "", "isAdjusted": "",
        "collateralName": "", "collateralAmount": 0, "riskFlags": [],
    },
]


@pytest.fixture(scope="module")
def manifest_entry() -> dict:
    return manifest_entries_by_id(load_entry_manifest())[F3_ENTRY_ID]


@pytest.fixture(scope="module")
def contract_payload() -> dict:
    return F3.build_contract_payload()


# ═══════════════════════════════════════════════════════════════════════════
# F3-P1：canary 打通后 migration_state 与 legacy_reasons 正确变更
# Validates: 1.5　🔴 现状必红（manifest 尚未重生成，BP-61-1 卡住发布链 ③④⑤ 环）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1MigrationState:
    def test_f3_entry_exists_in_manifest(self, manifest_entry) -> None:
        assert manifest_entry, f"{F3_ENTRY_ID} 不在 source-backed manifest 里"

    def test_current_state_is_adapter_registered(self, manifest_entry) -> None:
        """翻转后：manifest migration_state 已是 adapter_registered。"""
        assert manifest_entry.get("migration_state") == "adapter_registered"

    def test_migration_state_becomes_adapter_registered(self, manifest_entry) -> None:
        assert manifest_entry.get("migration_state") == "adapter_registered"

    def test_legacy_reasons_all_cleared(self, manifest_entry) -> None:
        reasons = (manifest_entry.get("evidence") or {}).get("legacy_reasons") or []
        assert reasons == []

    def test_legacy_reasons_cleared_after_flip(self, manifest_entry) -> None:
        """翻转后 legacy_reasons 应为空。"""
        reasons = set((manifest_entry.get("evidence") or {}).get("legacy_reasons") or [])
        assert reasons == set()


# ═══════════════════════════════════════════════════════════════════════════
# F3-P2：`store_item_id` 逐字等于按值实测值（+ 两条变异）
# Validates: 2.2
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2StoreItemId:
    def test_canary_store_item_id_exact(self) -> None:
        assert F305.STORE_ITEM_ID_F305 == "F3-5-rows"
        assert F3.STORE_ITEM_ID == "F3-5-rows"
        # 🔴 逐键列出当前受管清单 —— 每开一张 sheet 的灰度开关都必须显式更新这里，
        # 才能保住守护力（写成 `len(...) >= 1` 之类就等于放弃校验）。
        assert F3.all_store_item_ids() == (
            "F3-5-rows",
            "F3-6-rows",
            "F3-7-debit-rows",
            "F3-7-credit-rows",
            "F3-7-subsequent-rows",
            "F3-2-rows",
        )

    @pytest.mark.parametrize(
        "mutated",
        [
            "F3-overdue-rows",  # spec 需求 2.2 指定的变异①
            "F3-7-post-rows",  # 变异②：区③键名写成 F1 式 `post`（真实是 `subsequent`）
            "F3-5-overdue-rows",
        ],
    )
    def test_mutated_store_item_id_yields_empty_projection(self, mutated) -> None:
        """变异：键名改错 ⇒ `_spec_of_store_item` 抛，而不是静默投影恒空（D4-35 根因）。"""
        with pytest.raises(F3.StorePayloadError) as exc:
            F3._spec_of_store_item(mutated)
        assert mutated in str(exc.value)
        assert "F3-5-rows" in str(exc.value), "错误消息须列出真实受管清单，便于定位"

    def test_contract_field_store_item_id_matches(self, contract_payload) -> None:
        """契约里每个字段的 `store_item_id` 必须等于**其所属 table 的** spec 声明值。

        🔴 比写死 `== "F3-5-rows"` 强：受管面扩容后，写死字面量只能抓「不是 canary 的键」，
        而按 table 归属校验还能抓「F3-6 的字段错挂了 F3-5 的键」这类跨 sheet 串线。
        """
        by_table = {
            (s.sheet_key, s.table_key): s.store_item_id
            for s in F3.managed_row_table_specs()
        }
        seen: set[str] = set()
        for sheet in contract_payload["sheets"]:
            for table in sheet["tables"]:
                expected = by_table[(sheet["sheet_key"], table["table_key"])]
                for field in table["fields"]:
                    assert field["store_item_id"] == expected, (
                        f"{sheet['sheet_key']}/{table['table_key']} 的字段 "
                        f"{field['column_key']} 挂了 {field['store_item_id']}，"
                        f"应为 {expected}"
                    )
                seen.add(expected)
        assert seen == set(F3.all_store_item_ids()), "契约覆盖的键集合须与受管清单一致"


# ═══════════════════════════════════════════════════════════════════════════
# F3-P3：`binding_kind` / `row_identity_key` 取自前端三元组（不用模板公式数）
# Validates: 2.1
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty3Triad:
    def test_canary_is_excel_table_with_row_id(self) -> None:
        """三元组实证：`F3-5-rows` 键 + addRow/removeRow 各 1 + 行身份 `rowId`。"""
        assert F305.SPEC_F305.binding_kind is BindingKind.excel_table
        assert F305.SPEC_F305.row_identity_key == "rowId"
        assert F305.SPEC_F305.store_kind is StoreKind.rows

    def test_row_identity_is_row_id_not_id(self) -> None:
        """🔴 F3 用 `rowId`（真库 2 行全带 rowId、0 行带 id）——
        与 F5-2/3/5/8 的 `id` 相反，不得照搬（FC-4）。
        """
        assert F305.SPEC_F305.row_identity_key != "id"
        for row in REAL_PAYLOAD_ROWS:
            assert "rowId" in row and "id" not in row

    def test_zero_formula_data_region_is_not_static_region(self) -> None:
        """🔴 反例守卫：F3-5 数据区零公式，若按「公式数阈值」判形态会被误判
        `static_region`。三元组判据必须让它仍是 `excel_table`。
        """
        assert F305.SPEC_F305.formula_columns == ()
        assert F305.SPEC_F305.binding_kind is BindingKind.excel_table
        assert F305.SPEC_F305.uuid_col, "excel_table binding 必须有 UUID 列"


# ═══════════════════════════════════════════════════════════════════════════
# F3-P4：footer marker 逐字（F3-5 是纯「合计」；同册 F3-2/F3-4 是「合␠␠计」）
# Validates: 2.4
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty4FooterMarker:
    def test_canary_footer_marker_is_plain(self) -> None:
        assert F305.FOOTER_MARKER_F305 == "合计"
        assert "  " not in F305.FOOTER_MARKER_F305

    def test_footer_marker_matches_template_cell(self) -> None:
        """逐字比对权威模板 A22 —— `assert_footer_anchor_stable` 是逐字匹配，差空格即定位失败。"""
        from openpyxl import load_workbook

        wb = load_workbook(F3.authoritative_template_path(), data_only=False)
        try:
            ws = wb[F305.MANAGED_SHEET_F305]
            actual = ws.cell(row=F305.FOOTER_ROW_F305, column=1).value
        finally:
            wb.close()
        assert actual == F305.FOOTER_MARKER_F305, (
            f"模板 A{F305.FOOTER_ROW_F305} 实测 {actual!r}，声明 {F305.FOOTER_MARKER_F305!r}"
        )

    def test_footer_carries_total_formula(self, contract_payload) -> None:
        """F3-5 的 footer R22 真有 SUM(J/K/O) ⇒ carries_total_formula=True。"""
        table = contract_payload["sheets"][0]["tables"][0]
        assert table["footer_anchor"]["carries_total_formula"] is True
        assert table["footer_anchor"]["marker"] == "合计"


# ═══════════════════════════════════════════════════════════════════════════
# F3-P9：FC-10 列在换算落地前不受管
# Validates: 3.3
#
# 🔴 判定必须三条同时成立：前端存 % 数值 ∧ 模板百分比格式 ∧ 该列语义确实是比率。
#    只看 `number_format` 会误判 —— F3-5 的 C/D/E 三列（出票人/承兑人/收款人，**文本列**）
#    也被套了 `0.00%` 格式（模板治理债），本 spec 实施中曾据此误判「四列命中」。
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty9Fc10Deferred:
    def test_interest_rate_column_not_in_field_specs(self) -> None:
        columns = {row[1] for row in F305.FIELD_SPECS_F305}
        assert "I" not in columns, "I 列（票面利率）命中 FC-10，换算落地前不得进 field_specs"

    def test_fc10_deferred_registry_records_reason(self) -> None:
        """待换算列必须显式登记（不是"忘了声明"）。"""
        assert len(F305.FC10_DEFERRED_COLUMNS_F305) == 1
        col, key, reason = F305.FC10_DEFERRED_COLUMNS_F305[0]
        assert col == "I" and key == "interestRate"
        assert "0.00%" in reason and "3.5" in reason

    def test_text_columns_with_percent_format_are_still_managed(self) -> None:
        """🔴 C/D/E 是"文本列套错百分比格式"，**不**命中 FC-10 ⇒ 必须仍然受管。

        变异：若把它们也当 FC-10 排除，canary 会少掉三个关系人字段（业务信息丢失）。
        """
        columns = {row[1] for row in F305.FIELD_SPECS_F305}
        for col in ("C", "D", "E"):
            assert col in columns, f"{col} 列是文本列（关系人），不该被 FC-10 排除"
        by_col = {row[1]: row for row in F305.FIELD_SPECS_F305}
        for col in ("C", "D", "E"):
            assert by_col[col][3] == "text", f"{col} 列 value_type 应为 text"

    def test_percent_format_columns_measured_from_template(self) -> None:
        """逐列取证：数据区哪些列是百分比格式（证明结论不是抄 spec）。"""
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter

        wb = load_workbook(F3.authoritative_template_path(), data_only=False)
        try:
            ws = wb[F305.MANAGED_SHEET_F305]
            pct_cols = set()
            for ci in range(1, ws.max_column + 1):
                for r in range(F305.FIRST_DATA_ROW_F305, F305.LAST_DATA_ROW_F305 + 1):
                    if "%" in (ws.cell(row=r, column=ci).number_format or ""):
                        pct_cols.add(get_column_letter(ci))
                        break
        finally:
            wb.close()
        assert pct_cols == {"C", "D", "E", "I"}, (
            f"数据区百分比格式列实测 {sorted(pct_cols)}，与证据表不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 契约装配：必须过真 `parse_contract`（对 F1 手写 payload 的防复发）
# Validates: 1.2 / 1.4
# ═══════════════════════════════════════════════════════════════════════════


class TestContractPayloadIsParseable:
    def test_payload_passes_parse_contract(self, contract_payload) -> None:
        """🔴 F1 的手写 `_rows_table_payload` 在这一步抛
        `table anchor 必须是 A1 单元格，实得 None`。本 provider 走框架层
        `spec_to_contract_sheet_payload` ⇒ 必须过。
        """
        contract = parse_contract(contract_payload, adapter_id=F3.ADAPTER_ID)
        assert contract.contract_id == "f3.notes_payable_detail"
        assert contract.semantic_version == "1.0.0"

    def test_table_has_all_required_structural_keys(self, contract_payload) -> None:
        """逐键断言 —— 这些正是 F1 手写版缺的。"""
        table = contract_payload["sheets"][0]["tables"][0]
        assert table["anchor"] == "A5", "anchor 取 header_group_row"
        assert table["header_rows"] == 2, "R5/R6 两级表头"
        assert table["delete_policy"] == "tombstone"
        assert table["uuid_col"] == "P"
        assert table["row_identity"] == {"kind": "field", "json_pointer": "/rows/*/rowId"}
        assert table["formula_mask"] == [], "数据区零公式 ⇒ mask 为空"

    def test_every_field_has_source_refs(self, contract_payload) -> None:
        table = contract_payload["sheets"][0]["tables"][0]
        assert len(table["fields"]) == 14, "15 列模板 - 1 列 FC-10 待换算 = 14"
        for field in table["fields"]:
            assert field["source_ref"].startswith("源xlsx!逾期票据检查F3-5!")
            assert field["header_source_ref"].startswith("源xlsx!逾期票据检查F3-5!")
            assert field["header_source_ref"].endswith("6"), "表头引用应指向叶子行 R6"
            assert field["json_pointer"].startswith("/rows/{row_uuid}/")
            assert field["cell"]["row_from"] == "row_identity"

    def test_disk_contract_matches_source(self) -> None:
        """磁盘契约与现算 payload 无漂移（发布链第②环）。"""
        contract = F3.assert_contract_file_matches_source()
        assert contract.contract_id == "f3.notes_payable_detail"

    def test_term_days_is_protected_not_editable(self, contract_payload) -> None:
        """FC-7：模板无公式而 HTML 派生的列必须受保护，否则 recalc 静默覆盖用户改动。"""
        table = contract_payload["sheets"][0]["tables"][0]
        by_key = {f["column_key"]: f for f in table["fields"]}
        assert by_key["term_days"]["mode"] == "auto_source"
        from app.services.workpaper_sync.contracts import PROTECTED_MODES

        assert "auto_source" in {m.value if hasattr(m, "value") else m for m in PROTECTED_MODES}


# ═══════════════════════════════════════════════════════════════════════════
# 选型守卫：对**真 manifest** 真调（FC-2 对 E1 空转的防复发）
# Validates: 1.2
# ═══════════════════════════════════════════════════════════════════════════


class TestEntrySelectableRealCall:
    @staticmethod
    def _resolution(codes) -> F3.TemplateResolutionFacts:
        return F3.TemplateResolutionFacts(
            by_wp_code={c: [None] for c in codes},
            parent_code="F3",
            parent_resolved_path=F3.authoritative_template_path(),
        )

    def test_wp_codes_is_phantom(self) -> None:
        assert F3.WP_CODES == frozenset({"F3N"}), "matcher 域用幻影码（FC-2）"

    def test_real_call_on_real_manifest_succeeds(self) -> None:
        """🔴 真调 —— E1 的守卫只断言常量、从不真调，导致签名不兼容也没人发现。"""
        entry = F3.assert_entry_selectable(resolution=self._resolution(F3.WP_CODES))
        assert entry["entry_id"] == F3_ENTRY_ID

    def test_mutation_true_code_raises(self) -> None:
        """变异：把 WP_CODES 当真码 `{"F3"}` 用 ⇒ 与 manifest 的 `F3N` 不一致，必抛。"""
        import unittest.mock as mock

        with mock.patch.object(F3, "WP_CODES", frozenset({"F3"})):
            with pytest.raises(F3.EntrySelectionError, match="wp_code_patterns"):
                F3.assert_entry_selectable(resolution=self._resolution({"F3"}))

    def test_mutation_phantom_code_hits_finder_raises(self) -> None:
        """变异：幻影码在 finder 上命中了真文件 ⇒ 零回退判据必红。"""
        leaked = F3.TemplateResolutionFacts(
            by_wp_code={"F3N": ["F/F3 应付票据.xlsx"]},
            parent_code="F3",
            parent_resolved_path=F3.authoritative_template_path(),
        )
        with pytest.raises(F3.EntrySelectionError, match="零回退"):
            F3.assert_entry_selectable(resolution=leaked)

    def test_build_matcher_is_constructible(self) -> None:
        """🔴 E1 的 WIP 反例：`EntryMatcher(wp_codes=…)` 缺 `document_type` 即 TypeError。"""
        matcher = F3.build_matcher()
        assert matcher.document_type == "xlsx"
        assert set(matcher.wp_codes) == {"F3N"}


# ═══════════════════════════════════════════════════════════════════════════
# 投影 / 合并往返（真库载荷）
# Validates: 1.7
# ═══════════════════════════════════════════════════════════════════════════


class TestProjectionRoundtrip:
    def test_projection_from_real_payload(self) -> None:
        contract = F3.load_contract_from_disk()
        projection = F3.build_store_projection(
            json.dumps(REAL_PAYLOAD_ROWS, ensure_ascii=False), contract=contract
        )
        assert len(projection.values) == 2 * 14, "2 行 × 14 受管字段"
        for row in REAL_PAYLOAD_ROWS:
            key = f"overdue_notes_rows/{row['rowId']}/drawer"
            assert key in projection.values

    def test_projection_rejects_row_without_identity(self) -> None:
        """fail-closed：缺 rowId 的行必抛，不得退回数组下标作身份。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            RowTableStorePayloadError,
        )

        contract = F3.load_contract_from_disk()
        bad = json.dumps([{"noteType": "银行承兑汇票"}], ensure_ascii=False)
        with pytest.raises(RowTableStorePayloadError, match="稳定行身份"):
            F3.build_store_projection(bad, contract=contract)

    def test_merge_writes_back_editable_and_protects_auto_source(self) -> None:
        """OO→HTML：editable 列合并进 store；`auto_source` 列受保护不合并。"""
        from app.services.workpaper_sync.adapters.base import FieldValue, Projection

        contract = F3.load_contract_from_disk()
        rid = REAL_PAYLOAD_ROWS[0]["rowId"]
        values = {
            f"overdue_notes_rows/{rid}/drawer": FieldValue(
                stable_key=f"overdue_notes_rows/{rid}/drawer",
                value="甲公司",
                value_type="text",
                mode="editable",
                row_key=rid,
            ),
            f"overdue_notes_rows/{rid}/face_value": FieldValue(
                stable_key=f"overdue_notes_rows/{rid}/face_value",
                value=1000,
                value_type="amount",
                mode="editable",
                row_key=rid,
            ),
        }
        projection = Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=values,
            row_keys=(rid,),
        )
        merged, visited, applied, touched = F3.merge_projection_into_store_rows(
            projection=projection, base_rows=[dict(r) for r in REAL_PAYLOAD_ROWS]
        )
        assert len(merged) == 2, "行数不变（没有幽灵行）"
        target = next(r for r in merged if r["rowId"] == rid)
        assert target["drawer"] == "甲公司"
        assert target["faceValue"] == 1000
        assert applied == 2 and rid in touched
        # store-only 字段不被清空
        assert target["seq"] == 1 and target["attSlot"] == 1

    def test_managed_field_specs_are_column_ordered(self) -> None:
        specs = managed_field_specs(F305.SPEC_F305)
        from app.services.workpaper_sync.sheet_geometry import col_index

        cols = [col_index(s[1]) for s in specs]
        assert cols == sorted(cols), "字段必须按 Excel 列序排列"
        assert [s[1] for s in specs] == list("ABCDEFGHJKLMNO"), "I 列缺席（FC-10 待换算）"


# ══════════════════════════════════════════════════════════════════════════════
# Task 13：F3-6「关联方及交易检查表」
#
# 证据：openpyxl 逐格实测（见 `phase5_f3_06_related_party` 模块 docstring）
# 本组判据要立住三件事：
#   ① 单级表头 R6（R5 是说明文字）—— 与同册 F3-5 的两级 R5/R6 形成对照
#   ② FC-5 前端等价核：模板 `G=D+F-E` ≡ 前端 `openingBalance+creditMovement-debitMovement`
#   ③ F3-P11 下拉源区保护：`B7:B12` 的 DV 指向表内 `$B$19:$B$26`，受管区不得越界扩行
# ══════════════════════════════════════════════════════════════════════════════
from app.services.workpaper_sync import phase5_f3_06_related_party as F306  # noqa: E402

_F3_TEMPLATE = _BACKEND / "wp_templates" / "F" / "F3 应付票据.xlsx"


def _f306_table(payload: dict) -> dict:
    """按 sheet_key/table_key 取 F3-6 的 table（不用下标，扩容后下标会漂）。"""
    for sheet in payload["sheets"]:
        if sheet["sheet_key"] != F306.SHEET_KEY_F306:
            continue
        for table in sheet["tables"]:
            if table["table_key"] == F306.ROWS_TABLE_KEY_F306:
                return table
    raise AssertionError(
        f"契约缺 {F306.SHEET_KEY_F306}/{F306.ROWS_TABLE_KEY_F306}；"
        f"实得 sheets={[s['sheet_key'] for s in payload['sheets']]}"
    )


class TestF306GeometryIsSingleLevelHeader:
    """① 单级表头 —— 与同册 F3-5 的两级表头形成对照（照抄会让 anchor 错位）。"""

    def test_header_row_is_single_level(self) -> None:
        assert F306.SPEC_F306.header_row == 6
        assert F306.SPEC_F306.header_group_row is None
        assert F306.SPEC_F306.header_leaf_row is None

    def test_diverges_from_f305_two_level_header(self) -> None:
        assert F305.SPEC_F305.header_group_row is not None, "对照项：F3-5 是两级表头"
        assert F305.SPEC_F305.header_leaf_row is not None

    def test_contract_anchor_and_header_rows(self, contract_payload) -> None:
        table = _f306_table(contract_payload)
        assert table["anchor"] == "A6", "单级表头 ⇒ anchor 取 header_row"
        assert table["header_rows"] == 1

    def test_row_five_is_prose_not_header(self) -> None:
        """R5 是一整句说明文字（A5 长句、其余列空）⇒ 不能当表头行。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F306.MANAGED_SHEET_F306]
        try:
            a5 = str(ws["A5"].value or "")
            assert len(a5) > 20, f"A5 应是长说明句，实得 {a5!r}"
            for col in "BCDEFGHIJKLM":
                assert ws[f"{col}5"].value in (None, ""), (
                    f"{col}5 应为空（证明 R5 不是表头行）"
                )
            # R6 才是真表头：13 列全有文字
            for col in "ABCDEFGHIJKLM":
                assert str(ws[f"{col}6"].value or "").strip() != "", f"{col}6 应有表头文字"
        finally:
            wb.close()

    def test_data_range_and_footer(self) -> None:
        spec = F306.SPEC_F306
        assert (spec.first_data_row, spec.last_data_row) == (7, 12)
        assert spec.footer_row == 13
        assert spec.footer_marker == "合计"
        assert spec.footer_carries_total_formula is True

    def test_footer_sum_covers_only_five_columns(self) -> None:
        """实测 R13 的 SUM 只覆盖 D/E/F/G/K —— 不假设"所有数值列都有合计"。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F306.MANAGED_SHEET_F306]
        try:
            with_sum = [
                col
                for col in "ABCDEFGHIJKLM"
                if str(ws[f"{col}13"].value or "").startswith("=SUM(")
            ]
            assert with_sum == ["D", "E", "F", "G", "K"], (
                f"footer SUM 列集实测应为 D/E/F/G/K，实得 {with_sum}"
            )
        finally:
            wb.close()


class TestF306Fc5FrontendEquivalence:
    """② FC-5：模板公式与前端派生**同口径**，不需要统一改造。

    🔴 判据读前端源码做**结构核对**而非字符串包含：只断言"文件里有这串"会被注释里的
    旧写法说明误命中（TB 红线判据第一版正栽于此）。这里先剥注释再比对。
    """

    _TS = (
        _BACKEND.parent
        / "audit-platform"
        / "frontend"
        / "src"
        / "components"
        / "workpaper"
        / "composables"
        / "useF3RelatedParty.ts"
    )

    @staticmethod
    def _strip_ts_comments(text: str) -> str:
        import re

        without_block = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        return re.sub(r"(?<!:)//[^\n]*", "", without_block)

    def test_formula_columns_is_exactly_g(self) -> None:
        assert F306.SPEC_F306.formula_columns == ("G",)
        assert F306.SPEC_F306.formula_templates == {"G": "=D{r}+F{r}-E{r}"}

    def test_template_matches_every_data_row(self) -> None:
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F306.MANAGED_SHEET_F306]
        try:
            for row in range(
                F306.SPEC_F306.first_data_row, F306.SPEC_F306.last_data_row + 1
            ):
                assert ws[f"G{row}"].value == f"=D{row}+F{row}-E{row}"
        finally:
            wb.close()

    def test_frontend_derives_closing_with_same_operands(self) -> None:
        """前端 `closingBalance = 期初 + 贷方 − 借方`，与模板 `G=D+F-E` 同口径。

        列语义（R6 表头实测）：D 期初余额 / E 借方发生 / F 贷方发生 ⇒
        模板 `D+F-E` = 期初 + 贷方 − 借方，两边逐项对应。
        """
        assert self._TS.exists(), "useF3RelatedParty.ts 不存在（路径漂移需同步判据）"
        code = self._strip_ts_comments(self._TS.read_text(encoding="utf-8"))
        assert "openingBalance + stored.creditMovement - stored.debitMovement" in code, (
            "前端派生口径变了 —— 与模板 G=D+F-E 不再等价，FC-5 需重新裁决"
        )
        # spec Task 13 写的函数名不存在，真名是 computeRelatedPartyRow（结论不变）
        assert "function computeRelatedPartyRow" in code
        assert "recalcRelatedPartyRow" not in code

    def test_closing_balance_is_not_a_managed_field(self) -> None:
        """G 列由模板算 ⇒ 不进 field_specs（否则投影会把公式覆盖成字面值）。"""
        columns = {row[1] for row in F306.FIELD_SPECS_F306}
        assert "G" not in columns
        json_keys = {row[4] for row in F306.FIELD_SPECS_F306}
        assert "closingBalance" not in json_keys

    def test_contract_formula_mask_is_g_over_data_range(self, contract_payload) -> None:
        table = _f306_table(contract_payload)
        assert table["formula_mask"] == ["G7:G12"], (
            f"mask 应是 G 列 × 数据区，实得 {table['formula_mask']}"
        )


class TestF306Property11DropdownSourceProtection:
    """③ F3-P11：`B7:B12` 的 DV 指向表内源区 `$B$19:$B$26`，受管区不得越界扩行。"""

    def test_declared_source_rows(self) -> None:
        assert F306.DROPDOWN_SOURCE_ROWS_F306 == (18, 26)

    def test_data_validations_recorded_verbatim(self) -> None:
        recorded = {sqref: (kind, f1) for sqref, kind, f1 in F306.DATA_VALIDATIONS_F306}
        assert recorded["B7:B12"] == ("list", "$B$19:$B$26")
        assert recorded["C7:C12"] == ("list", "银行承兑汇票,商业承兑汇票")

    def test_template_dv_matches_declaration(self) -> None:
        """逐条比对模板真实 DV —— 声明漂移会让"源区保护"保护错地方。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F306.MANAGED_SHEET_F306]
        try:
            actual = {
                str(dv.sqref): (dv.type, dv.formula1) for dv in ws.data_validations.dataValidation
            }
            for sqref, kind, f1 in F306.DATA_VALIDATIONS_F306:
                assert sqref in actual, f"模板缺 DV {sqref}；实得 {sorted(actual)}"
                assert actual[sqref][0] == kind
                assert actual[sqref][1].strip('"') == f1, (
                    f"{sqref} 的 formula1 实测 {actual[sqref][1]!r}，声明 {f1!r}"
                )
        finally:
            wb.close()

    def test_source_rows_really_hold_the_enum(self) -> None:
        """源区 B19:B26 真有 8 个关联关系枚举值，B18 是 `勿改、勿删` 标记行。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F306.MANAGED_SHEET_F306]
        try:
            assert str(ws["B18"].value or "").strip() == "勿改、勿删"
            values = [str(ws[f"B{r}"].value or "").strip() for r in range(19, 27)]
            assert all(values), f"B19:B26 应全部非空，实得 {values}"
            assert len(set(values)) == 8, f"8 个枚举值应互不相同，实得 {values}"
            assert "实际控制人" in values and "其他关联方" in values
        finally:
            wb.close()

    def test_last_data_row_stops_before_source_zone(self) -> None:
        """🔴 硬上限：受管区末行 + footer 必须留在源区之上，否则插行会推走 DV 源区
        （DV 的 formula1 是字面量 `$B$19:$B$26`，不随插行位移）。
        """
        spec = F306.SPEC_F306
        source_first = F306.DROPDOWN_SOURCE_ROWS_F306[0]
        assert spec.last_data_row < spec.footer_row < source_first, (
            f"数据区末行 {spec.last_data_row} / footer {spec.footer_row} 必须都在"
            f"源区起始行 {source_first} 之上"
        )

    def test_uuid_col_is_n_and_within_max_column(self) -> None:
        from openpyxl import load_workbook
        from openpyxl.utils import column_index_from_string

        assert F306.UUID_COL_F306 == "N"
        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F306.MANAGED_SHEET_F306]
        try:
            assert column_index_from_string(F306.UUID_COL_F306) <= ws.max_column
            for r in range(1, ws.max_row + 1):
                assert ws[f"N{r}"].value is None, f"uuid 列 N{r} 应为空"
        finally:
            wb.close()

    def test_sibling_uuid_cols_distinct(self) -> None:
        cols = [s.uuid_col for s in F3.managed_row_table_specs()]
        assert len(cols) == len(set(cols)), f"同 entry 内 uuid_col 不得重复：{cols}"


class TestF306FieldsAndFc10:
    def test_twelve_managed_fields(self, contract_payload) -> None:
        table = _f306_table(contract_payload)
        assert len(table["fields"]) == 12, "13 列模板 - 1 列公式(G) = 12"
        columns = {f["cell"]["column"] for f in table["fields"]}
        assert columns == set("ABCDEF") | set("HIJKLM")

    def test_store_only_keys_registered(self) -> None:
        store_only = dict(F306.STORE_ONLY_KEYS_F306)
        assert set(store_only) == {"seq", "concentration", "riskFlags"}
        json_keys = {row[4] for row in F306.FIELD_SPECS_F306}
        for key in store_only:
            assert key not in json_keys

    def test_fc10_not_applicable(self) -> None:
        """整表 0 个百分比格式 ⇒ FC-10 不命中（与同册 F3-5 的 I 列命中形成对照）。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F306.MANAGED_SHEET_F306]
        try:
            pct = [
                f"{c.column_letter}{c.row}"
                for row in ws.iter_rows()
                for c in row
                if "%" in str(c.number_format or "")
            ]
            assert pct == [], f"F3-6 不该有百分比格式格，实得 {pct}"
        finally:
            wb.close()

    def test_row_identity_is_row_id(self, contract_payload) -> None:
        assert F306.SPEC_F306.row_identity_key == "rowId"
        table = _f306_table(contract_payload)
        assert table["row_identity"] == {
            "kind": "field",
            "json_pointer": "/rows/*/rowId",
        }

    def test_store_item_id_matches_frontend(self) -> None:
        assert F306.STORE_ITEM_ID_F306 == "F3-6-rows"
        assert F306.STORE_ITEM_ID_F306 in F3.all_store_item_ids()

    def test_projection_roundtrip(self) -> None:
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            build_store_projection,
        )

        contract = F3.load_contract_from_disk()
        projection = build_store_projection(
            spec=F306.SPEC_F306,
            contract=contract,
            payload=json.dumps(
                [
                    {
                        "rowId": "f3rp-e2e-1",
                        "seq": 1,
                        "partyName": "关联方甲",
                        "relationship": "控股股东",
                        "noteType": "银行承兑汇票",
                        "openingBalance": 1000,
                        "debitMovement": 300,
                        "creditMovement": 500,
                        "aging": "1年以内",
                        "pricingPolicy": "市场定价",
                        "transactionReason": "采购货款",
                        "subsequentPaymentAmount": 200,
                        "indexNo": "F3-6-1",
                        "remark": "",
                    }
                ]
            ),
        )
        base = F306.ROWS_TABLE_KEY_F306
        assert projection.values[f"{base}/f3rp-e2e-1/party_name"].value == "关联方甲"
        assert projection.values[f"{base}/f3rp-e2e-1/opening_balance"].value == 1000
        # G 列是公式列 ⇒ 不该出现在投影里
        assert not any(
            key.endswith("/closing_balance") for key in projection.values
        ), "公式列不得进投影"

    def test_contract_parses_with_every_managed_sheet(self, contract_payload) -> None:
        """整份契约过 `parse_contract`，且 sheet_key 集合与受管清单一致。

        🔴 逐值列出（不写 `>= 2`）：新开一张 sheet 必须显式更新这里。
        """
        from app.services.workpaper_sync import phase5_f3_07_voucher_check as F307

        contract = parse_contract(contract_payload, adapter_id=F3.ADAPTER_ID)
        keys = {s.sheet_key for s in contract.sheets}
        assert keys == {
            F305.SHEET_KEY_F305,
            F306.SHEET_KEY_F306,
            F307.SHEET_KEY_F307,
            "f32-managed",
        }
        # F3-7 三区共享一个 sheet_key ⇒ sheet 数 4、table 数 6（含 F3-2）
        tables = [t for s in contract.sheets for t in s.tables]
        assert len(tables) == len(F3.managed_row_table_specs())

    def test_instrumentation_covers_both_sheets(self) -> None:
        specs = F3.instrumentation_specs()
        assert len(specs) == len(F3.managed_row_table_specs())
        assert F306.SHEET_KEY_F306 in {str(s.resolved_sheet_key) for s in specs}


# ══════════════════════════════════════════════════════════════════════════════
# Task 14：F3-7「应付票据检查表」三区
#
# 本组判据的核心命题是**三区不可互换** —— 它们看起来对称（都是「记账凭证 + 证据 +
# 索引/异常」），但区② 的证据组宽 7 列而区①③ 宽 5 列，其后所有列右移 2 列。
# 拿区① 的 field_specs 套区②，会把「索引号」写进「……」列 —— 一整列静默错位，
# 且三谓词全都会通过（值都落库了，只是落错列）。判据必须把这条差异钉死。
# ══════════════════════════════════════════════════════════════════════════════
from app.services.workpaper_sync import phase5_f3_07_voucher_check as F307  # noqa: E402

_F307_SPEC_BY_SECTION = {
    "debit": F307.SPEC_F307_DEBIT,
    "credit": F307.SPEC_F307_CREDIT,
    "subsequent": F307.SPEC_F307_SUBSEQUENT,
}


def _f307_table(payload: dict, section: str) -> dict:
    want = f"voucher_{section}_rows"
    for sheet in payload["sheets"]:
        if sheet["sheet_key"] != F307.SHEET_KEY_F307:
            continue
        for table in sheet["tables"]:
            if table["table_key"] == want:
                return table
    raise AssertionError(
        f"契约缺 {F307.SHEET_KEY_F307}/{want}；"
        f"实得 {[t['table_key'] for s in payload['sheets'] for t in s['tables']]}"
    )


class TestF307ThreeZonesAreNotInterchangeable:
    """三区列布局分叉 —— 照抄任一区都会让另一区整列错位。"""

    def test_single_shared_sheet_key(self) -> None:
        """🔴 D3-4 先例：同 managed_sheet 的多区必须共享一个 sheet_key。"""
        assert F307.SHEET_KEY_F307 == "f37-managed"
        for spec in F307.SPECS_F307:
            assert spec.sheet_key == F307.SHEET_KEY_F307
            assert spec.managed_sheet == F307.MANAGED_SHEET_F307

    def test_table_keys_and_names_are_zone_scoped(self) -> None:
        table_keys = [s.table_key for s in F307.SPECS_F307]
        assert table_keys == [
            "voucher_debit_rows",
            "voucher_credit_rows",
            "voucher_subsequent_rows",
        ]
        names = [s.table_name for s in F307.SPECS_F307]
        assert len(set(names)) == 3, f"table_name 必须逐区唯一：{names}"
        ids = [s.template_id for s in F307.SPECS_F307]
        assert len(set(ids)) == 3, f"template_id 必须逐区唯一：{ids}"

    def test_uuid_cols_are_distinct_across_zones(self) -> None:
        """兄弟 Table ref 位移靠 uuid_col 配对 spec↔table ⇒ 三区必须互不相同。"""
        assert F307.UUID_COLS_F307 == {"debit": "S", "credit": "T", "subsequent": "U"}
        cols = [s.uuid_col for s in F3.managed_row_table_specs()]
        assert len(cols) == len(set(cols)), f"同 entry 内 uuid_col 不得重复：{cols}"

    def test_uuid_cols_exceed_max_column_and_are_empty(self) -> None:
        from openpyxl import load_workbook
        from openpyxl.utils import column_index_from_string

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            for section, col in F307.UUID_COLS_F307.items():
                assert column_index_from_string(col) > ws.max_column, (
                    f"{section} 的 uuid 列 {col} 应超出 max_column({ws.max_column}) ⇒ 需扩列"
                )
            for col in F307.UUID_COLS_F307.values():
                for r in range(1, ws.max_row + 1):
                    assert ws[f"{col}{r}"].value is None
        finally:
            wb.close()

    def test_three_zones_have_different_row_counts(self) -> None:
        """🔴 行数 20/18/17 不是笔误 —— 模板就是这么画的，不得"对称化"。"""
        counts = {
            section: spec.last_data_row - spec.first_data_row + 1
            for section, spec in _F307_SPEC_BY_SECTION.items()
        }
        assert counts == {"debit": 20, "credit": 18, "subsequent": 17}

    def test_geometry_matches_template_anchors(self) -> None:
        """逐区核对：标题行 / 两级表头 / footer 合计 的真实位置。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            expected_titles = {14: "1.本期借方金额检查", 38: "2.贷方金额检查", 60: "3.资产负债表日后借方检查"}
            for row, text in expected_titles.items():
                assert str(ws[f"A{row}"].value or "").strip() == text
            for section, spec in _F307_SPEC_BY_SECTION.items():
                # 两级表头：组标题行 A 列是「记账凭证」，叶子行 A 列是「日期」
                assert str(ws[f"A{spec.header_group_row}"].value or "").strip() == "记账凭证"
                assert str(ws[f"A{spec.header_leaf_row}"].value or "").strip() == "日期"
                assert str(ws[f"A{spec.footer_row}"].value or "").strip() == "合计", (
                    f"{section} 的 footer 行 A{spec.footer_row} 应是「合计」"
                )
        finally:
            wb.close()

    def test_evidence_group_widths_diverge(self) -> None:
        """🔴 核心差异：区② 证据组宽 7 列（H:K + L:N），区①③ 宽 5 列（H:I + J:L）。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            merged = {str(r) for r in ws.merged_cells.ranges}
            # 区①（R15）与区③（R61）：付款审批单 2 列 + 银行回单 3 列
            for row in (15, 61):
                assert f"H{row}:I{row}" in merged, f"区（R{row}）应有 H:I 两列证据组"
                assert f"J{row}:L{row}" in merged, f"区（R{row}）应有 J:L 三列证据组"
            # 区②（R39）：入库单 4 列 + 采购发票 3 列
            assert "H39:K39" in merged, "区② 应有 H:K 四列证据组"
            assert "L39:N39" in merged, "区② 应有 L:N 三列证据组"
            # 反向：区② 不得出现区①③ 的分组，否则说明我读错了模板
            assert "H39:I39" not in merged
            assert "J39:L39" not in merged
        finally:
            wb.close()

    def test_index_and_abnormal_columns_shift_in_credit_zone(self) -> None:
        """索引号/是否异常在区①③ 是 N/O，在区② 右移到 P/Q（整列错位的根因）。"""
        by_section = {
            section: {row[0]: row[1] for row in spec.field_specs}
            for section, spec in _F307_SPEC_BY_SECTION.items()
        }
        for section in ("debit", "subsequent"):
            assert by_section[section]["index_no"] == "N"
            assert by_section[section]["is_abnormal"] == "O"
            assert by_section[section]["other_evidence"] == "M"
        assert by_section["credit"]["index_no"] == "P"
        assert by_section["credit"]["is_abnormal"] == "Q"
        assert by_section["credit"]["other_evidence"] == "O"

    def test_template_headers_confirm_the_shift(self) -> None:
        """不靠声明自证 —— 回模板逐格读表头文字确认位移。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            # 区①（组标题 R15）：M「……」/ N「索引号」/ O「是否异常」
            assert str(ws["N15"].value or "").strip() == "索引号"
            assert str(ws["O15"].value or "").strip() == "是否异常"
            # 区②（组标题 R39）：O「……」/ P「索引号」/ Q「是否异常」
            assert str(ws["P39"].value or "").strip() == "索引号"
            assert str(ws["Q39"].value or "").strip() == "是否异常"
            # 区③（组标题 R61）同区①
            assert str(ws["N61"].value or "").strip() == "索引号"
            assert str(ws["O61"].value or "").strip() == "是否异常"
        finally:
            wb.close()

    def test_field_counts_per_zone(self, contract_payload) -> None:
        """区①③ 15 个字段（A-O），区② 17 个（A-Q）。"""
        assert len(_f307_table(contract_payload, "debit")["fields"]) == 15
        assert len(_f307_table(contract_payload, "subsequent")["fields"]) == 15
        assert len(_f307_table(contract_payload, "credit")["fields"]) == 17

    def test_debit_and_subsequent_share_column_layout(self) -> None:
        """区①③ 列布局相同（只有 amount 表头与组锚格不同）⇒ 可以共用 `_payment_tail`。"""
        debit = {row[0]: row[1] for row in F307.FIELD_SPECS_F307_DEBIT}
        subseq = {row[0]: row[1] for row in F307.FIELD_SPECS_F307_SUBSEQUENT}
        assert debit == subseq, "区①③ 的 column_key→列 映射应完全一致"

    def test_credit_zone_uses_purchase_evidence_keys(self) -> None:
        """区② 用 receipt*/invoice*，不得出现区①③ 的 approval*/bank*（反之亦然）。"""
        credit_keys = {row[0] for row in F307.FIELD_SPECS_F307_CREDIT}
        payment_keys = {row[0] for row in F307.FIELD_SPECS_F307_DEBIT}
        assert {"receipt_date_no", "receipt_product", "receipt_unit", "receipt_qty"} <= credit_keys
        assert {"invoice_date_no", "invoice_counterparty", "invoice_amount"} <= credit_keys
        assert not ({"approval_date_no", "bank_amount"} & credit_keys)
        assert {"approval_date_no", "approval_proper", "bank_amount"} <= payment_keys
        assert not ({"receipt_qty", "invoice_amount"} & payment_keys)


class TestF307StoreKeysAndFooter:
    def test_store_keys_match_frontend_item_keys(self) -> None:
        """🔴 区③ 是 `subsequent` 不是 F1 式的 `post`（spec 变异②点名的形态）。"""
        assert F307.STORE_ITEM_IDS_F307 == {
            "debit": "F3-7-debit-rows",
            "credit": "F3-7-credit-rows",
            "subsequent": "F3-7-subsequent-rows",
        }
        for key in F307.STORE_ITEM_IDS_F307.values():
            assert key in F3.all_store_item_ids()
        assert "F3-7-post-rows" not in F3.all_store_item_ids()

    def test_frontend_item_keys_verbatim(self) -> None:
        """回前端源码逐字核对（剥注释后比对，避免注释里的旧键名误命中）。"""
        import re

        ts = (
            _BACKEND.parent
            / "audit-platform"
            / "frontend"
            / "src"
            / "components"
            / "workpaper"
            / "composables"
            / "useF3VoucherCheck.ts"
        )
        assert ts.exists(), "useF3VoucherCheck.ts 不存在（路径漂移需同步判据）"
        raw = ts.read_text(encoding="utf-8")
        code = re.sub(r"(?<!:)//[^\n]*", "", re.sub(r"/\*.*?\*/", "", raw, flags=re.S))
        for key in F307.STORE_ITEM_IDS_F307.values():
            assert f"'{key}'" in code, f"前端未出现 {key}"
        assert "'F3-7-post-rows'" not in code

    def test_footer_sum_columns_diverge_per_zone(self) -> None:
        """🔴 区② 的第二个 SUM 列是 N（采购发票金额），区①③ 是 L（银行回单金额）。"""
        assert F307.FOOTER_SUM_COLUMNS_F307 == {
            "debit": ("F", "L"),
            "credit": ("F", "N"),
            "subsequent": ("F", "L"),
        }

    def test_template_footer_sums_match_declaration(self) -> None:
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            for section, spec in _F307_SPEC_BY_SECTION.items():
                row = spec.footer_row
                actual = tuple(
                    col
                    for col in "ABCDEFGHIJKLMNOPQR"
                    if str(ws[f"{col}{row}"].value or "").startswith("=SUM(")
                )
                assert actual == F307.FOOTER_SUM_COLUMNS_F307[section], (
                    f"{section} footer R{row} 的 SUM 列集实测 {actual}，"
                    f"声明 {F307.FOOTER_SUM_COLUMNS_F307[section]}"
                )
                # SUM 区间须覆盖该区数据区
                first = spec.first_data_row
                last = spec.last_data_row
                assert ws[f"F{row}"].value == f"=SUM(F{first}:F{last})"
        finally:
            wb.close()

    def test_all_zones_have_zero_formula_in_data_range(self) -> None:
        """三区数据区零公式（公式只在页眉 / footer / R83-85 比例区）。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            for section, spec in _F307_SPEC_BY_SECTION.items():
                assert spec.formula_columns == (), f"{section} 应声明零公式"
                for row in range(spec.first_data_row, spec.last_data_row + 1):
                    for col in "ABCDEFGHIJKLMNOPQR":
                        value = ws[f"{col}{row}"].value
                        assert not (
                            isinstance(value, str) and value.startswith("=")
                        ), f"{col}{row} 不该有公式（{section} 数据区应全可编辑）"
        finally:
            wb.close()

    def test_contract_formula_mask_is_empty_for_all_zones(self, contract_payload) -> None:
        for section in _F307_SPEC_BY_SECTION:
            table = _f307_table(contract_payload, section)
            assert table["formula_mask"] == [], f"{section} mask 应为空"
            assert table["footer_anchor"]["carries_total_formula"] is True
            assert table["footer_anchor"]["marker"] == "合计"

    def test_contract_anchors_per_zone(self, contract_payload) -> None:
        expected = {"debit": "A15", "credit": "A39", "subsequent": "A61"}
        for section, anchor in expected.items():
            table = _f307_table(contract_payload, section)
            assert table["anchor"] == anchor, f"{section} anchor 应为 {anchor}"
            assert table["header_rows"] == 2, "三区都是两级表头"

    def test_data_validation_is_inline_without_source_zone(self) -> None:
        """🔴 与 F3-6 对照：F3-7 的 DV 是**内联枚举**，不依赖表内源区 ⇒ 插行不打断 DV。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            dvs = list(ws.data_validations.dataValidation)
            assert len(dvs) == 1, f"F3-7 应只有一条 DV，实得 {len(dvs)}"
            dv = dvs[0]
            assert dv.type == "list"
            assert "$" not in (dv.formula1 or ""), (
                f"formula1 不该引用表内区域（实得 {dv.formula1!r}）"
            )
            declared_sqref, declared_kind, declared_f1 = F307.DATA_VALIDATIONS_F307[0]
            assert str(dv.sqref) == declared_sqref
            assert dv.type == declared_kind
            assert (dv.formula1 or "").strip('"') == declared_f1
        finally:
            wb.close()

    def test_note_type_enum_debt_registered(self) -> None:
        """模板债：前端 4 值 vs 模板 DV 2 值（登记不改字节）。"""
        frontend, template, note = F307.NOTE_TYPE_ENUM_DEBT_F307
        assert len(frontend) == 4 and len(template) == 2
        assert set(template) < set(frontend), "模板枚举应是前端枚举的真子集"
        assert "软校验" in note and "不阻塞受管" in note

    def test_fc10_not_applicable_to_managed_ranges(self) -> None:
        """百分比格式全在 R83~R87 比例区，三个数据区零命中。"""
        from openpyxl import load_workbook

        wb = load_workbook(_F3_TEMPLATE, data_only=False)
        ws = wb[F307.MANAGED_SHEET_F307]
        try:
            pct_rows = {
                c.row
                for row in ws.iter_rows()
                for c in row
                if "%" in str(c.number_format or "")
            }
            managed_rows: set[int] = set()
            for spec in F307.SPECS_F307:
                managed_rows |= set(range(spec.first_data_row, spec.last_data_row + 1))
            assert not (pct_rows & managed_rows), (
                f"受管数据区不该有百分比格式，命中行 {sorted(pct_rows & managed_rows)}"
            )
            assert pct_rows <= {83, 84, 85, 86, 87}, f"百分比格式行实测 {sorted(pct_rows)}"
        finally:
            wb.close()

    def test_store_only_keys_registered(self) -> None:
        store_only = dict(F307.STORE_ONLY_KEYS_F307)
        assert set(store_only) == {"seq", "attSlot", "issueDesc", "sampleSource"}
        for spec in F307.SPECS_F307:
            json_keys = {row[4] for row in spec.field_specs}
            for key in store_only:
                assert key not in json_keys, f"{key} 是 store-only，不该进 field_specs"

    def test_projection_roundtrip_per_zone(self) -> None:
        """三区各自投影一行，键前缀必须落在自己的 table_key 下（不串线）。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import (
            build_store_projection,
        )

        contract = F3.load_contract_from_disk()
        for section, spec in _F307_SPEC_BY_SECTION.items():
            payload = json.dumps(
                [
                    {
                        "rowId": f"f3v-{section}-1",
                        "seq": 1,
                        "attSlot": 1,
                        "voucherDate": "2099-12-31",
                        "voucherNo": f"{section.upper()}-001",
                        "businessContent": "e2e",
                        "counterAccount": "1002",
                        "detailAccount": "基本户",
                        "amount": 1234,
                        "noteType": "银行承兑汇票",
                        "indexNo": "F3-7-1",
                        "isAbnormal": "否",
                    }
                ]
            )
            projection = build_store_projection(
                spec=spec, contract=contract, payload=payload
            )
            base = spec.table_key
            assert projection.values[f"{base}/f3v-{section}-1/amount"].value == 1234
            assert projection.values[f"{base}/f3v-{section}-1/index_no"].value == "F3-7-1"
            for key in projection.values:
                assert key.startswith(f"{base}/"), (
                    f"{section} 的投影键串到了别的 table：{key}"
                )

    def test_instrumentation_covers_all_five_tables(self) -> None:
        specs = F3.instrumentation_specs()
        assert len(specs) == len(F3.managed_row_table_specs())
        # 三区共享 sheet_key + F3-2 独立 sheet_key ⇒ resolved_sheet_key 去重后 4 个
        assert len({str(s.resolved_sheet_key) for s in specs}) == 4

    def test_html_only_anchor_rows_registered(self) -> None:
        rows = dict(F307.HTML_ONLY_ANCHOR_ROWS_F307)
        assert rows[14] == "1.本期借方金额检查"
        assert rows[38] == "2.贷方金额检查"
        assert rows[60] == "3.资产负债表日后借方检查"
        assert rows[81] == "四、审计说明："
        assert rows[88] == "五、审计结论："


# ═══════════════════════════════════════════════════════════════════════════
# F3-2 I 列（期限天数）模板无公式守卫（复盘改进 ①）
# FC-7 auto_source 列：模板 I 列必须为空（前端 termDays 是 computed 派生）
# ═══════════════════════════════════════════════════════════════════════════


class TestF302ColumnIHasNoTemplateFormula:
    """I 列（期限天数）在模板中应无公式（FC-7 auto_source）。

    如果将来有人给模板 I 列加公式，本判据打红——防止 editable/formula 混淆。
    """

    def test_i_column_empty_in_data_area(self) -> None:
        from openpyxl import load_workbook
        from app.services.workpaper_sync import phase5_f3_02_detail as F302

        wb = load_workbook(F3.authoritative_template_path(), data_only=False)
        try:
            ws = wb[F302.MANAGED_SHEET_F302]
            for r in range(F302.FIRST_DATA_ROW_F302, F302.LAST_DATA_ROW_F302 + 1):
                cell = ws[f"I{r}"]
                assert cell.value is None and cell.data_type != "f", (
                    f"I{r} 应为空（FC-7 auto_source），实得 value={cell.value!r} dtype={cell.data_type}"
                )
        finally:
            wb.close()
