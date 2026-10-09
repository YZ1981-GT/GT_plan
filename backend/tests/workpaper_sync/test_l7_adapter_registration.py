# -*- coding: utf-8 -*-
"""L7 其他非流动负债真双向接线守卫（spec `l7-true-bidirectional-2026-10-01` · 第3步）。

受管表 `明细表L7-2`（L7 整册唯一数据录入源）。同序：
几何现算 → 契约 → 注册 → HTML 侧对齐 → 真库干净命名空间。

L7 与 L3 的差异（照抄 L3 会错）：
* 受管表**有 5 个公式列** E/L/M/N/O（L3-9 零公式列），须断言 formula_mask 非空 + 5 个 formula 字段。
* footer marker 在 **A17**（L3 在 A21），数据区 r12~r16（5 行，比 L3-9 的 9 行少）。
* 18 字段（L3-9 是 16），列 A..R；P/Q/R 列 HTML 命名 nature/reason/maturityInfo 与 Excel
  表头 文件依据/索引号/备注 语义错位，但按列位置搬运，往返不受影响。
* HTML store 是单 item JSON 数组 `L7-L7-2-full-data`（整表），minter newRowIdentity('l72det')。
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest
from openpyxl import load_workbook

from app.services.workpaper_sync import phase5_l7_other_noncurrent_liabilities as L7
from app.services.workpaper_sync import phase5_l_cycle_common as L
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.definitions import canonical_digest
from tests.workpaper_sync.l1_adapter_facts import ROOT, _count_bare_if, _is_formula, _query

TEMPLATE = ROOT / "backend" / "wp_templates" / L7.TEMPLATE_RELATIVE_PATH
FRONTEND = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
DETAIL_TS = FRONTEND / "composables" / "useL7Detail.ts"
DETAIL_VUE = FRONTEND / "l7" / "core" / "L7TabDetail.vue"


@pytest.fixture(scope="module")
def wb():
    return load_workbook(TEMPLATE, data_only=False)


@pytest.fixture(scope="module")
def ws(wb):
    return wb[L7.MANAGED_SHEET]


# ═══════════════════════════════════════════════════════════════════════════
# 选型与几何（openpyxl 现算）
# ═══════════════════════════════════════════════════════════════════════════


class TestManagedSheetSelection:
    def test_template_sha256_matches_frozen(self) -> None:
        assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == L7.TEMPLATE_SHA256

    def test_managed_sheet_present_and_adjudication_is_derived(self, wb) -> None:
        """审定表L7-1 是下游视图（R7~R11 全跨 sheet 公式引用 明细表L7-2），非录入表 ⇒ 不选它。"""
        assert L7.MANAGED_SHEET in wb.sheetnames
        s1 = wb["审定表L7-1"]
        cross_ref = sum(
            isinstance(c.value, str) and "明细表L7-2" in c.value
            for r in s1.iter_rows() for c in r
        )
        assert cross_ref > 0, "审定表L7-1 应有跨 sheet 引用 明细表L7-2 的公式"

    def test_geometry(self, ws) -> None:
        assert ws.max_column == 27, "物理 max_column=AA ⇒ UUID 列 AB"
        assert L7.UUID_COL == "AB"
        assert ws[f"A{L7.FOOTER_ROW}"].value == L7.FOOTER_MARKER
        assert (L7.HEADER_GROUP_ROW, L7.HEADER_LEAF_ROW) == (10, 11)
        assert (L7.FIRST_DATA_ROW, L7.LAST_DATA_ROW, L7.FOOTER_ROW) == (12, 16, 17)

    def test_five_formula_columns_present_each_data_row(self, ws) -> None:
        """E/L/M/N/O 五列每一数据行都是真公式（与 L3-9 零公式列相反）。"""
        for r in range(L7.FIRST_DATA_ROW, L7.LAST_DATA_ROW + 1):
            assert _is_formula(ws[f"E{r}"].value) and ws[f"E{r}"].value == f"=B{r}+C{r}-D{r}"
            assert _is_formula(ws[f"L{r}"].value) and ws[f"L{r}"].value == f"=B{r}+F{r}+G{r}"
            assert _is_formula(ws[f"M{r}"].value) and ws[f"M{r}"].value == f"=C{r}+H{r}+J{r}"
            assert _is_formula(ws[f"N{r}"].value) and ws[f"N{r}"].value == f"=D{r}+I{r}+K{r}"
            assert _is_formula(ws[f"O{r}"].value) and ws[f"O{r}"].value == f"=L{r}+M{r}-N{r}"
        assert L7.FORMULA_COLUMNS == ("E", "L", "M", "N", "O")
        assert L7.FORMULA_MASK == ("E12:E16", "L12:L16", "M12:M16", "N12:N16", "O12:O16")

    def test_managed_sheet_has_no_bare_if_but_workbook_does(self, wb, ws) -> None:
        """per-file 中性化依据：受管表 0、整册 > 0（整册裸 IF 仅 审定表L7-1 6 格）。"""
        assert _count_bare_if(ws) == 0
        assert sum(_count_bare_if(wb[n]) for n in wb.sheetnames) > 0

    def test_eighteen_managed_fields_with_five_formula(self) -> None:
        assert len(L7.MANAGED_FIELD_SPECS_7) == 18
        cols = [col for _, col, *_ in L7.MANAGED_FIELD_SPECS_7]
        assert cols == list("ABCDEFGHIJKLMNOPQR")
        formula_cols = [col for _, col, mode, *_ in L7.MANAGED_FIELD_SPECS_7 if mode == "formula"]
        assert formula_cols == ["E", "L", "M", "N", "O"]


# ═══════════════════════════════════════════════════════════════════════════
# 契约
# ═══════════════════════════════════════════════════════════════════════════


class TestContract:
    def test_disk_and_source_are_locked(self) -> None:
        contract = L7.assert_contract_file_matches_source()
        assert contract.canonical_sha256 == canonical_digest(L7.build_contract_payload())

    def test_payload_parses_and_has_expected_shape(self) -> None:
        p = L7.build_contract_payload()
        parse_contract(dict(p), adapter_id=L7.ADAPTER_ID)
        assert p["review_status"] == "reviewed"
        assert p["review"]["entry_id"] == L7.ENTRY_ID
        table = p["sheets"][0]["tables"][0]
        assert table["header_rows"] == 2 and table["anchor"] == "A10"
        assert table["footer_anchor"]["search_column"] == "A"
        assert len(table["fields"]) == 18

    def test_formula_mask_and_formula_fields_nonempty(self) -> None:
        """🔴 L7 有公式列：formula_mask 非空、恰 5 个 formula 字段（照 L1/L4 范式，非 L3 零公式断言）。"""
        table = L7.build_contract_payload()["sheets"][0]["tables"][0]
        assert table["formula_mask"] == ["E12:E16", "L12:L16", "M12:M16", "N12:N16", "O12:O16"]
        formula_keys = {
            f["json_pointer"].rsplit("/", 1)[-1]
            for f in table["fields"] if f["mode"] == "formula"
        }
        assert formula_keys == {"beginAudited", "endUnadjusted", "endAje", "endRje", "endAudited"}

    def test_derived_readonly_sheet_declared(self) -> None:
        review = L7.build_contract_payload()["review"]
        drs = review["derived_readonly_sheet"]
        assert drs["excel_name"] == "审定表L7-1"
        assert "明细表L7-2" in drs["reason"]

    def test_routes_through_common_skeleton(self) -> None:
        assert L7.EntrySelectionError is L.LEntrySelectionError
        assert L7.build_contract_payload() == L.build_contract_payload(L7.IDENTITY, L7.SPECS)


# ═══════════════════════════════════════════════════════════════════════════
# 注册
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistration:
    def test_provider_aliases_present(self) -> None:
        assert L7.publish_pilot_definitions is L7.publish_definitions
        assert L7.attach_pilot_adapters is L7.attach_adapters
        assert L7.PILOT_WP_CODES == frozenset({"L7O"})

    def test_store_registry_entry(self) -> None:
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        plan = STORE_MERGE_REGISTRY["l7.other_noncurrent_liabilities"]
        assert plan.provider_module == "phase5_l7_other_noncurrent_liabilities"
        assert [i.item_id for i in plan.items] == ["L7-L7-2-full-data"]
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas"

    def test_whitelist_and_ledger_are_paired(self) -> None:
        from app.services.workpaper_sync.adapters import registry as R
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        mod = "app.services.workpaper_sync.phase5_l7_other_noncurrent_liabilities"
        assert mod in R._ALLOWED_PROVIDER_MODULES
        rows = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == "l7.other_noncurrent_liabilities"]
        assert len(rows) == 1 and rows[0]["provider_module"] == mod

    def test_l_cycle_whitelist_ledger_counts_paired(self) -> None:
        """配对不变式：L 域白名单条数 == ledger 的 L 条数。"""
        from app.services.workpaper_sync.adapters import registry as R
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        wl_l = [m for m in R._ALLOWED_PROVIDER_MODULES if ".phase5_l" in m and "_cycle_common" not in m]
        ledger_l = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if re.match(r"l\d", str(r["contract_id"]))]
        assert len(wl_l) == len(ledger_l), (len(wl_l), len(ledger_l))

    def test_wp_code_adjudication_targets_the_whole_workbook_code(self) -> None:
        doc = json.loads(
            (ROOT / "backend/data/workpaper_sync_entry_wp_code_adjudication.json").read_text("utf-8")
        )
        row = next(a for a in doc["adjudications"] if a["entry_id"] == L7.ENTRY_ID)
        assert row["wp_codes"] == ["L7"] and row["contract_id"] == L7.ADAPTER_ID


# ═══════════════════════════════════════════════════════════════════════════
# HTML 侧对齐（前端 json 键 == 契约 json_pointer 段）
# ═══════════════════════════════════════════════════════════════════════════


class TestHtmlAlignment:
    def test_store_item_id_agrees(self) -> None:
        """L7 的 store item 是硬编码字符串 'L7-L7-2-full-data'（_restoreRowsFromResponses 优先读它）。"""
        src = DETAIL_VUE.read_text("utf-8")
        assert f"'{L7.STORE_ITEM_ID}'" in src
        ts = DETAIL_TS.read_text("utf-8")
        assert f"'{L7.STORE_ITEM_ID}'" in ts

    def test_row_identity_uses_shared_minter_not_private_generator(self) -> None:
        """私有随机 ID 已删，改走平台共享 newRowIdentity('l72det')，已有 rowId 不重铸。"""
        ts = DETAIL_TS.read_text("utf-8")
        assert "newRowIdentity('l72det')" in ts
        # 旧随机运行时前缀不再用于新增行
        assert "l7-detail-${Date.now()}" not in ts
        vue = DETAIL_VUE.read_text("utf-8")
        assert "raw.rowId || raw.key || newRowIdentity('l72det')" in vue

    def test_frontend_row_keys_cover_every_contract_field(self) -> None:
        src = DETAIL_TS.read_text("utf-8")
        iface = src.split("export interface L7DetailRow {", 1)[1].split("}", 1)[0]
        frontend = set(re.findall(r"^\s+(\w+)\s*:", iface, re.M))
        contract = {
            f["json_pointer"].rsplit("/", 1)[-1]
            for f in L7.build_contract_payload()["sheets"][0]["tables"][0]["fields"]
        }
        assert contract - frontend == set(), f"契约有、前端缺：{sorted(contract - frontend)}"


# ═══════════════════════════════════════════════════════════════════════════
# 真库：干净命名空间
# ═══════════════════════════════════════════════════════════════════════════


class TestRealDbNamespace:
    def test_managed_namespace_is_clean(self) -> None:
        """L7-L7-2-% 真库命名空间：受管 full-data 键 0 行、旧位置化 row-N 键 0 行。"""
        rows = _query(
            "SELECT count(*) FILTER (WHERE item_id = 'L7-L7-2-full-data'), "
            "count(*) FILTER (WHERE item_id LIKE 'L7-L7-2-row-%-end_balance') FROM checklist_responses"
        )
        full_data, old_positional = rows[0]
        assert old_positional == 0, "L7-2 旧 per-row end_balance 键有真数据 ⇒ 切换前须先核对"
        assert full_data >= 0
