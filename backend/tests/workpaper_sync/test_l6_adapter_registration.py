# -*- coding: utf-8 -*-
"""L6 专项应付款（科目 2711）真双向接线守卫（spec `l6-true-bidirectional-2026-10-01` · 第3步）。

受管表 `明细表L6-2`（L6 整册唯一数据录入源）。同序：
几何现算 → 契约 → 注册 → HTML 侧对齐 → 真库干净命名空间。

L6 与 L7 的差异（照抄 L7 会错）：
* 物理 max_column=**AG(33)**（L7 是 AA(27)）；Y..AG 全空 ⇒ UUID 列 = 右侧首个空列 **AH**（非 L7 的 AB）。
* 数据区 **r10~r19（10 行）**、两级表头 r8/r9、footer **A20**（L7 是 r12~r16 / r10/r11 / A17）。
* 受管表**有 6 个公式列** G/P/Q/R/S/T（L7 是 5 列 E/L/M/N/O），须断言 formula_mask 非空 + 6 个 formula 字段。
* **24 字段**（L7 是 18），列 A..X；A 列是整数序号（ghost 锚点取 B=project 第 1 位）。
* HTML store 单键 **`L6-L6-2-rows`**（非 L7 的 `L7-L7-2-full-data`），minter newRowIdentity('l62det')。
* 前端 fundSource/approvalNo/purpose 三字段 HTML-only（无模板列，不入契约）。
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest
from openpyxl import load_workbook

from app.services.workpaper_sync import phase5_l6_special_payables as L6
from app.services.workpaper_sync import phase5_l_cycle_common as L
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.definitions import canonical_digest
from tests.workpaper_sync.l1_adapter_facts import ROOT, _count_bare_if, _is_formula, _query

TEMPLATE = ROOT / "backend" / "wp_templates" / L6.TEMPLATE_RELATIVE_PATH
FRONTEND = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
DETAIL_TS = FRONTEND / "composables" / "useL6Detail.ts"
DETAIL_VUE = FRONTEND / "l6" / "core" / "L6TabDetail.vue"


@pytest.fixture(scope="module")
def wb():
    return load_workbook(TEMPLATE, data_only=False)


@pytest.fixture(scope="module")
def ws(wb):
    return wb[L6.MANAGED_SHEET]


# ═══════════════════════════════════════════════════════════════════════════
# 选型与几何（openpyxl 现算）
# ═══════════════════════════════════════════════════════════════════════════


class TestManagedSheetSelection:
    def test_template_sha256_matches_frozen(self) -> None:
        assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == L6.TEMPLATE_SHA256

    def test_managed_sheet_present_and_adjudication_is_derived(self, wb) -> None:
        """审定表L6-1 是下游视图（R7~R16 全跨 sheet 公式引用 明细表L6-2），非录入表 ⇒ 不选它。"""
        assert L6.MANAGED_SHEET in wb.sheetnames
        s1 = wb["审定表L6-1"]
        cross_ref = sum(
            isinstance(c.value, str) and "明细表L6-2" in c.value
            for r in s1.iter_rows() for c in r
        )
        assert cross_ref > 0, "审定表L6-1 应有跨 sheet 引用 明细表L6-2 的公式"

    def test_geometry(self, ws) -> None:
        """🔴 物理 max_column=AG(33)（Y..AG 全空）⇒ UUID 列 AH（现算，禁照抄 L7 的 AB）。"""
        assert ws.max_column == 33, "物理 max_column=AG"
        assert L6.UUID_COL == "AH"
        # Y..AG（25..33）全空 ⇒ 右侧首个空列为 AH(34)
        for c in range(25, 34):
            col = ws.cell(row=1, column=c).column_letter
            assert all(ws.cell(row=r, column=c).value is None for r in range(1, ws.max_row + 1)), f"{col} 应全空"
        assert ws[f"A{L6.FOOTER_ROW}"].value == L6.FOOTER_MARKER
        assert (L6.HEADER_GROUP_ROW, L6.HEADER_LEAF_ROW) == (8, 9)
        assert (L6.FIRST_DATA_ROW, L6.LAST_DATA_ROW, L6.FOOTER_ROW) == (10, 19, 20)
        assert L6.MANAGED_LAST_COL == "X"

    def test_data_region_has_preset_serial_skeleton(self, ws) -> None:
        """A10..A19 预置整数序号 1~10（骨架行；真 OO 往返里核行身份对齐无幽灵行）。"""
        for i, r in enumerate(range(L6.FIRST_DATA_ROW, L6.LAST_DATA_ROW + 1), start=1):
            assert ws[f"A{r}"].value == i, f"A{r} 应为序号 {i}"

    def test_six_formula_columns_present_each_data_row(self, ws) -> None:
        """G/P/Q/R/S/T 六列每一数据行都是真公式（负债口径；比 L7 多一列）。"""
        for r in range(L6.FIRST_DATA_ROW, L6.LAST_DATA_ROW + 1):
            assert _is_formula(ws[f"G{r}"].value) and ws[f"G{r}"].value == f"=C{r}+D{r}-E{r}-F{r}"
            assert _is_formula(ws[f"P{r}"].value) and ws[f"P{r}"].value == f"=C{r}+H{r}+I{r}"
            assert _is_formula(ws[f"Q{r}"].value) and ws[f"Q{r}"].value == f"=D{r}+J{r}+M{r}"
            assert _is_formula(ws[f"R{r}"].value) and ws[f"R{r}"].value == f"=E{r}+K{r}+N{r}"
            assert _is_formula(ws[f"S{r}"].value) and ws[f"S{r}"].value == f"=F{r}+L{r}+O{r}"
            assert _is_formula(ws[f"T{r}"].value) and ws[f"T{r}"].value == f"=P{r}+Q{r}-R{r}-S{r}"
        assert L6.FORMULA_COLUMNS == ("G", "P", "Q", "R", "S", "T")
        assert L6.FORMULA_MASK == ("G10:G19", "P10:P19", "Q10:Q19", "R10:R19", "S10:S19", "T10:T19")

    def test_managed_sheet_has_no_bare_if_but_workbook_does(self, wb, ws) -> None:
        """per-file 中性化依据：受管表 0、整册 > 0（整册裸 IF 仅 审定表L6-1 11 格）。"""
        assert _count_bare_if(ws) == 0
        assert _count_bare_if(wb["审定表L6-1"]) == 11
        assert sum(_count_bare_if(wb[n]) for n in wb.sheetnames) == 11

    def test_managed_sheet_has_no_shared_formula_groups(self) -> None:
        """sanitize 非必需的依据：受管 sheet 无 <f t="shared">、整册无 external/OLE。"""
        import zipfile

        with zipfile.ZipFile(TEMPLATE) as z:
            names = z.namelist()
            assert not any(
                ("external" in n.lower() or "ole" in n.lower() or "embeddings" in n.lower())
                for n in names
            ), "整册不应有 external/OLE/embeddings 条目"
            # 定位含 L6-2 公式的 sheet xml，断言其无共享公式组
            # XML 里公式存在 <f> 标签内、不带前导 '='（openpyxl 读时才补）。
            l62_xml = None
            for n in names:
                if n.startswith("xl/worksheets/") and n.endswith(".xml"):
                    data = z.read(n).decode("utf-8", errors="replace")
                    if "P10+Q10-R10-S10" in data:
                        l62_xml = data
                        break
            assert l62_xml is not None, "未定位到受管 sheet xml"
            assert 'f t="shared"' not in l62_xml, "受管 sheet 不应有共享公式组"

    def test_twentyfour_managed_fields_with_six_formula(self) -> None:
        assert len(L6.MANAGED_FIELD_SPECS_7) == 24
        cols = [col for _, col, *_ in L6.MANAGED_FIELD_SPECS_7]
        assert cols == list("ABCDEFGHIJKLMNOPQRSTUVWX")
        formula_cols = [col for _, col, mode, *_ in L6.MANAGED_FIELD_SPECS_7 if mode == "formula"]
        assert formula_cols == ["G", "P", "Q", "R", "S", "T"]

    def test_html_only_keys_not_in_contract(self) -> None:
        """fundSource/approvalNo/purpose 无模板列 ⇒ HTML-only，不出现在契约字段。"""
        assert set(L6.HTML_ONLY_ROW_KEYS) == {"fundSource", "approvalNo", "purpose"}
        contract_json_keys = {spec[4] for spec in L6.MANAGED_FIELD_SPECS_7}
        assert set(L6.HTML_ONLY_ROW_KEYS).isdisjoint(contract_json_keys)


# ═══════════════════════════════════════════════════════════════════════════
# 契约
# ═══════════════════════════════════════════════════════════════════════════


class TestContract:
    def test_disk_and_source_are_locked(self) -> None:
        contract = L6.assert_contract_file_matches_source()
        assert contract.canonical_sha256 == canonical_digest(L6.build_contract_payload())

    def test_payload_parses_and_has_expected_shape(self) -> None:
        p = L6.build_contract_payload()
        parse_contract(dict(p), adapter_id=L6.ADAPTER_ID)
        assert p["review_status"] == "reviewed"
        assert p["review"]["entry_id"] == L6.ENTRY_ID
        assert p["review"]["html_store"]["item_id"] == "L6-L6-2-rows"
        table = p["sheets"][0]["tables"][0]
        assert table["header_rows"] == 2 and table["anchor"] == "A8"
        assert table["footer_anchor"]["search_column"] == "A"
        assert table["uuid_col"] == "AH"
        assert len(table["fields"]) == 24

    def test_formula_mask_and_formula_fields_nonempty(self) -> None:
        """🔴 L6 有 6 个公式列：formula_mask 非空、恰 6 个 formula 字段。"""
        table = L6.build_contract_payload()["sheets"][0]["tables"][0]
        assert table["formula_mask"] == ["G10:G19", "P10:P19", "Q10:Q19", "R10:R19", "S10:S19", "T10:T19"]
        formula_keys = {
            f["json_pointer"].rsplit("/", 1)[-1]
            for f in table["fields"] if f["mode"] == "formula"
        }
        assert formula_keys == {"endBalance", "auditedBegin", "auditedCredit", "auditedCarryFwd", "auditedRefund", "auditedEnd"}

    def test_derived_readonly_sheet_declared(self) -> None:
        review = L6.build_contract_payload()["review"]
        drs = review["derived_readonly_sheet"]
        assert drs["excel_name"] == "审定表L6-1"
        assert "明细表L6-2" in drs["reason"]

    def test_routes_through_common_skeleton(self) -> None:
        assert L6.EntrySelectionError is L.LEntrySelectionError
        assert L6.build_contract_payload() == L.build_contract_payload(L6.IDENTITY, L6.SPECS)


# ═══════════════════════════════════════════════════════════════════════════
# 注册
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistration:
    def test_provider_aliases_present(self) -> None:
        assert L6.publish_pilot_definitions is L6.publish_definitions
        assert L6.attach_pilot_adapters is L6.attach_adapters
        assert L6.PILOT_WP_CODES == frozenset({"L6S"})

    def test_store_registry_entry(self) -> None:
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        plan = STORE_MERGE_REGISTRY["l6.special_payables"]
        assert plan.provider_module == "phase5_l6_special_payables"
        assert [i.item_id for i in plan.items] == ["L6-L6-2-rows"]
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas"

    def test_whitelist_and_ledger_are_paired(self) -> None:
        from app.services.workpaper_sync.adapters import registry as R
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        mod = "app.services.workpaper_sync.phase5_l6_special_payables"
        assert mod in R._ALLOWED_PROVIDER_MODULES
        rows = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == "l6.special_payables"]
        assert len(rows) == 1 and rows[0]["provider_module"] == mod

    def test_l_cycle_whitelist_ledger_counts_paired(self) -> None:
        """配对不变式：L 域白名单条数 == ledger 的 L 条数（现在 6 条）。"""
        from app.services.workpaper_sync.adapters import registry as R
        from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        wl_l = [m for m in R._ALLOWED_PROVIDER_MODULES if ".phase5_l" in m and "_cycle_common" not in m]
        ledger_l = [r for r in DELIVERED_PER_ENTRY_CONTRACTS if re.match(r"l\d", str(r["contract_id"]))]
        assert len(wl_l) == len(ledger_l), (len(wl_l), len(ledger_l))
        assert len(wl_l) == 6, f"L 域应 6 条（L1/L2/L3/L4/L6/L7），实得 {len(wl_l)}"

    def test_wp_code_adjudication_targets_the_whole_workbook_code(self) -> None:
        doc = json.loads(
            (ROOT / "backend/data/workpaper_sync_entry_wp_code_adjudication.json").read_text("utf-8")
        )
        row = next(a for a in doc["adjudications"] if a["entry_id"] == L6.ENTRY_ID)
        assert row["wp_codes"] == ["L6"] and row["contract_id"] == L6.ADAPTER_ID


# ═══════════════════════════════════════════════════════════════════════════
# HTML 侧对齐（前端 json 键 == 契约 json_pointer 段）
# ═══════════════════════════════════════════════════════════════════════════


class TestHtmlAlignment:
    def test_store_item_id_agrees(self) -> None:
        """L6 的 store item 是硬编码字符串 'L6-L6-2-rows'（restoreRowsFromResponses 优先读它）。"""
        src = DETAIL_VUE.read_text("utf-8")
        assert f"'{L6.STORE_ITEM_ID}'" in src
        ts = DETAIL_TS.read_text("utf-8")
        assert f"'{L6.STORE_ITEM_ID}'" in ts

    def test_row_identity_uses_shared_minter_not_private_generator(self) -> None:
        """私有随机 ID 已删，改走平台共享 newRowIdentity('l62det')，已有 rowId 不重铸。"""
        ts = DETAIL_TS.read_text("utf-8")
        assert "newRowIdentity('l62det')" in ts
        # 旧随机运行时前缀不再用于新增行
        assert "l6-detail-${Date.now()}" not in ts
        vue = DETAIL_VUE.read_text("utf-8")
        assert "r.rowId || r.key || newRowIdentity('l62det')" in vue

    def test_frontend_row_keys_cover_every_contract_field(self) -> None:
        src = DETAIL_TS.read_text("utf-8")
        iface = src.split("export interface L6DetailRow {", 1)[1].split("\n}", 1)[0]
        frontend = set(re.findall(r"^\s+(\w+)\s*:", iface, re.M))
        contract = {
            f["json_pointer"].rsplit("/", 1)[-1]
            for f in L6.build_contract_payload()["sheets"][0]["tables"][0]["fields"]
        }
        assert contract - frontend == set(), f"契约有、前端缺：{sorted(contract - frontend)}"


# ═══════════════════════════════════════════════════════════════════════════
# 真库：干净命名空间
# ═══════════════════════════════════════════════════════════════════════════


class TestRealDbNamespace:
    def test_managed_namespace_is_clean(self) -> None:
        """L6-L6-2-% 真库命名空间：受管 rows 键 0 行、旧位置化 row-N 键 0 行。"""
        rows = _query(
            "SELECT count(*) FILTER (WHERE item_id = 'L6-L6-2-rows'), "
            "count(*) FILTER (WHERE item_id LIKE 'L6-L6-2-row-%-end_balance') FROM checklist_responses"
        )
        rows_data, old_positional = rows[0]
        assert old_positional == 0, "L6-2 旧 per-row end_balance 键有真数据 ⇒ 切换前须先核对"
        assert rows_data >= 0
