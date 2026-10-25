# -*- coding: utf-8 -*-
"""F4 canary 判据：Property 1 / 2 / 3 / 4 / 16 + F4A 撞码隔离 + 契约可解析。

spec: f4-sync-coverage-and-first-canary
      Task 3（P1~P4）· Task 4（P15/P16/P18）· Task 6（provider）· Task 7（canary 薄声明）
      Requirements 1.1 / 1.2 / 1.3 / 1.5 / 2.1 / 2.2 / 2.3 / 2.4 / 7.6

🔴 Property 编号 spec-scoped：本文件的 `Property N` 读作 `F4-P{N}`。
共同说明（为何强制"真调 + 过 parse_contract"）见 `test_f3_canary_and_contract.py` 顶部。
"""
from __future__ import annotations

import json
import sys
import unittest.mock as mock
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import phase5_f4_06_related_party as F406  # noqa: E402
from app.services.workpaper_sync import phase5_f4_accounts_payable as F4  # noqa: E402
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

F4_ENTRY_ID = "xlsx/gt-f4-accounts-payable"


@pytest.fixture(scope="module")
def manifest_entry() -> dict:
    return manifest_entries_by_id(load_entry_manifest())[F4_ENTRY_ID]


@pytest.fixture(scope="module")
def contract_payload() -> dict:
    return F4.build_contract_payload()


def _resolution(codes) -> F4.TemplateResolutionFacts:
    return F4.TemplateResolutionFacts(
        by_wp_code={c: [None] for c in codes},
        parent_code="F4",
        parent_resolved_path=F4.authoritative_template_path(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# F4-P1：migration_state（🔴 现状必红，卡 BP-61-1）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty1MigrationState:
    def test_current_state_is_adapter_registered(self, manifest_entry) -> None:
        """翻转后：manifest migration_state 已是 adapter_registered。"""
        assert manifest_entry.get("migration_state") == "adapter_registered"

    def test_becomes_adapter_registered(self, manifest_entry) -> None:
        assert manifest_entry.get("migration_state") == "adapter_registered"

    def test_legacy_reasons_cleared_after_flip(self, manifest_entry) -> None:
        """翻转后 legacy_reasons 应为空。"""
        reasons = set((manifest_entry.get("evidence") or {}).get("legacy_reasons") or [])
        assert reasons == set()


# ═══════════════════════════════════════════════════════════════════════════
# F4-P2：`F4A` 幻影码与真实程序表路由码隔离（四条子判据）
# Validates: 1.3
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2PhantomCodeCollision:
    """🔴 全 F 循环唯一「幻影码撞真码」：`wp_code_overrides.json` 的程序表路由码
    与 manifest 的 `wp_code_patterns` 字面相同（均为 `F4A`）。两侧都不改（裁决 F4-H2）。
    """

    def test_wp_codes_is_the_phantom_code(self) -> None:
        assert F4.WP_CODES == frozenset({"F4A"})

    def test_index_json_has_f4_but_not_f4a(self) -> None:
        """子判据①：finder 域（`wp_templates/_index.json`）零命中幻影码。"""
        index = json.loads((_BACKEND / "wp_templates" / "_index.json").read_text(encoding="utf-8"))
        codes = {f.get("wp_code") for f in index["files"]}
        assert "F4" in codes, "真码必须在 finder 域"
        assert "F4A" not in codes, "🔴 幻影码不得在 finder 域（否则会命中真模板）"
        f_codes = sorted(c for c in codes if isinstance(c, str) and c.startswith("F"))
        assert f_codes == ["F0", "F1", "F2", "F3", "F4", "F5"], (
            f"F 循环 finder 域实测 {f_codes} —— 只应有六个真码"
        )

    def test_route_table_has_f4a_but_not_f4(self) -> None:
        """子判据②：路由域确实有 `F4A`（撞码事实源），且 `F4` 本身没有 override 条目。

        🔴 spec requirements 的表述「F4A 是程序表路由码」属实，但它没说 `F4` 无条目 ——
        撞码只有「幻影码与路由码字面相同」这一种形态，不是两条 F4* 并存互相干扰。
        """
        overrides = json.loads(
            (_BACKEND / "app" / "data" / "wp_code_overrides.json").read_text(encoding="utf-8")
        )
        table = overrides.get("overrides", overrides)
        assert table.get("F4A") == "f4-accounts-payable"
        assert "F4" not in table

    def test_provisioner_uses_true_code(self) -> None:
        """子判据③：provisioner 的 wp_code 裁决用真码 `["F4"]`，不用幻影码。"""
        adj = json.loads(
            (_BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json").read_text(
                encoding="utf-8"
            )
        )
        entry = next(e for e in adj["adjudications"] if e["entry_id"] == F4_ENTRY_ID)
        assert entry["wp_codes"] == ["F4"]
        assert entry["contract_id"] == "f4.accounts_payable_detail"
        collision = entry["phantom_code_collision"]
        assert collision["phantom_code"] == "F4A"
        iso = collision["isolation_evidence"]
        assert iso["index_json_has_f4a"] is False
        assert iso["wp_index_f4a_rows"] == 0
        assert iso["provisioner_uses"] == ["F4"]

    def test_fallback_guard_passes_for_phantom_code(self) -> None:
        """子判据④：`assert_no_implicit_template_fallback('F4A')` 通过（零命中）。"""
        F4.assert_no_implicit_template_fallback(
            _resolution(F4.WP_CODES), wp_codes=frozenset({"F4A"})
        )

    def test_mutation_phantom_code_hitting_finder_raises(self) -> None:
        """变异：幻影码在 finder 上命中真文件 ⇒ 必红（这正是撞码最危险的后果）。"""
        leaked = F4.TemplateResolutionFacts(
            by_wp_code={"F4A": ["F/F4 应付账款.xlsx"]},
            parent_code="F4",
            parent_resolved_path=F4.authoritative_template_path(),
        )
        with pytest.raises(F4.EntrySelectionError, match="零回退"):
            F4.assert_entry_selectable(resolution=leaked)


# ═══════════════════════════════════════════════════════════════════════════
# F4-P3：`store_item_id` 取主键不取 legacy 别名
# Validates: 2.2 / 2.3
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty3StoreItemIdPrimaryKey:
    def test_canary_store_item_id_exact(self) -> None:
        assert F406.STORE_ITEM_ID_F406 == "F4-6-rows"
        items = F4.all_store_item_ids()
        assert "F4-6-rows" in items
        assert "F4-5-rows" in items
        assert "F4-8-debit-rows" in items
        assert "F4-8-credit-rows" in items
        # F4-7 五区
        assert "F4-7-payment-window-rows" in items
        assert "F4-7-estimated-inbound-rows" in items
        assert "F4-7-unprocessed-invoice-rows" in items
        assert "F4-7-subsequent-payment-rows" in items
        assert "F4-7-subsequent-increase-rows" in items
        assert "F4-2-rows" in items
        assert len(items) == 10

    @pytest.mark.parametrize(
        "alias",
        [
            "F4-7-receipt",  # F4-7 区② 的 legacy 别名
            "F4-7-invoice",  # F4-7 区③ 的 legacy 别名
            "F4-9-factoring-rows",  # F4-9 的 7 个 legacy 键之一
            "F4-6-note",  # note 键不是行数组键
        ],
    )
    def test_legacy_alias_is_not_a_managed_region(self, alias) -> None:
        """别名不得被当受管区（会造成一区两 binding）。"""
        with pytest.raises(F4.StorePayloadError):
            F4._spec_of_store_item(alias)

    def test_zero_writer_read_keys_registered_not_managed(self) -> None:
        """🔴 F4-8 读的两个零写入键：登记为兼容回退，但不进受管清单（P18）。"""
        assert F4.ZERO_WRITER_READ_KEYS == ("F4-8-debit-note", "F4-8-credit-note")
        for key in F4.ZERO_WRITER_READ_KEYS:
            assert key not in F4.all_store_item_ids()


# ═══════════════════════════════════════════════════════════════════════════
# F4-P4：三元组 + 公式镜像（同型不等于同式）
# Validates: 2.1
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty4TriadAndMirroredFormula:
    def test_canary_is_excel_table_with_row_id(self) -> None:
        assert F406.SPEC_F406.binding_kind is BindingKind.excel_table
        assert F406.SPEC_F406.row_identity_key == "rowId"
        assert F406.SPEC_F406.store_kind is StoreKind.rows

    def test_formula_is_liability_direction_not_asset(self) -> None:
        """🔴 负债类 `=C+E-D`（期初+贷方−借方），与 F1-6 资产类 `=C+D-E` 镜像。

        变异：照搬 F1-6 的式子 ⇒ 借贷方向反，期末余额算错。
        """
        assert F406.FORMULA_TEMPLATES_F406 == {"F": "=C{r}+E{r}-D{r}"}
        assert F406.FORMULA_TEMPLATES_F406["F"] != "=C{r}+D{r}-E{r}", "不得照搬 F1-6 的资产类方向"

    def test_formula_matches_template_cells(self) -> None:
        """逐格比对权威模板 F7..F11。"""
        from openpyxl import load_workbook

        wb = load_workbook(F4.authoritative_template_path(), data_only=False)
        try:
            ws = wb[F406.MANAGED_SHEET_F406]
            for r in range(F406.FIRST_DATA_ROW_F406, F406.LAST_DATA_ROW_F406 + 1):
                assert ws[f"F{r}"].value == f"=C{r}+E{r}-D{r}"
        finally:
            wb.close()

    def test_formula_mask_is_engine_derived(self, contract_payload) -> None:
        table = contract_payload["sheets"][0]["tables"][0]
        assert table["formula_mask"] == ["F7:F11"], "mask 由引擎从 formula_columns × 数据行现算"


# ═══════════════════════════════════════════════════════════════════════════
# F4-P16：FC-10 在 F4 不命中（结论须有证据，需求 7.6）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty16Fc10NotApplicable:
    def test_canary_sheet_has_zero_percent_format_cells(self) -> None:
        """🔴 逐格取证 —— 不是"以为不命中"。"""
        from openpyxl import load_workbook

        wb = load_workbook(F4.authoritative_template_path(), data_only=False)
        try:
            ws = wb[F406.MANAGED_SHEET_F406]
            pct = [
                f"{c.column_letter}{c.row}"
                for row in ws.iter_rows()
                for c in row
                if "%" in (c.number_format or "")
            ]
        finally:
            wb.close()
        assert pct == [], f"F4-6 实测应零百分比格式格，实得 {pct}"

    def test_no_fc10_deferred_columns_declared(self) -> None:
        """F4 是四个 F spec 里唯一无 FC-10 阻塞的 ⇒ 声明层不该有待换算列登记。"""
        assert not hasattr(F406, "FC10_DEFERRED_COLUMNS_F406")


# ═══════════════════════════════════════════════════════════════════════════
# 契约装配 + 选型真调 + 模板缺陷登记
# ═══════════════════════════════════════════════════════════════════════════


class TestContractAndSelection:
    def test_payload_passes_parse_contract(self, contract_payload) -> None:
        contract = parse_contract(contract_payload, adapter_id=F4.ADAPTER_ID)
        assert contract.contract_id == "f4.accounts_payable_detail"

    def test_table_structural_keys(self, contract_payload) -> None:
        table = contract_payload["sheets"][0]["tables"][0]
        assert table["anchor"] == "A6", "单级表头 ⇒ anchor 取 header_row"
        assert table["header_rows"] == 1
        assert table["uuid_col"] == "M"
        assert table["delete_policy"] == "tombstone"
        assert table["row_identity"] == {"kind": "field", "json_pointer": "/rows/*/rowId"}
        assert table["footer_anchor"] == {
            "marker": "合计",
            "search_column": "A",
            "carries_total_formula": True,
        }
        assert len(table["fields"]) == 12

    def test_disk_contract_matches_source(self) -> None:
        assert F4.assert_contract_file_matches_source().contract_id == "f4.accounts_payable_detail"

    def test_real_call_on_real_manifest(self) -> None:
        entry = F4.assert_entry_selectable(resolution=_resolution(F4.WP_CODES))
        assert entry["entry_id"] == F4_ENTRY_ID

    def test_mutation_true_code_raises(self) -> None:
        with mock.patch.object(F4, "WP_CODES", frozenset({"F4"})):
            with pytest.raises(F4.EntrySelectionError, match="wp_code_patterns"):
                F4.assert_entry_selectable(resolution=_resolution({"F4"}))

    def test_build_matcher_constructible(self) -> None:
        matcher = F4.build_matcher()
        assert matcher.document_type == "xlsx"
        assert set(matcher.wp_codes) == {"F4A"}

    def test_template_defect_registered(self) -> None:
        """🔴 F4-6 的 DV 悬空引用登记（不改模板字节）。"""
        defect = F406.TEMPLATE_DEFECT_F406
        assert defect["where"] == "B8:B11"
        assert defect["formula1"] == "$N$7:$N$14"
        assert "不改模板字节" in defect["handling"]

    def test_template_defect_is_real(self) -> None:
        """逐格证明缺陷属实：`B8:B11` 的 DV 源区 N 列确实全空。"""
        from openpyxl import load_workbook

        wb = load_workbook(F4.authoritative_template_path(), data_only=False)
        try:
            ws = wb[F406.MANAGED_SHEET_F406]
            dvs = {str(dv.sqref): str(dv.formula1) for dv in ws.data_validations.dataValidation}
            assert dvs.get("B8:B11") == "$N$7:$N$14"
            assert dvs.get("B7") == "$B$18:$B$25", "B7 是正确形态（指向真实枚举源）"
            n_values = [ws.cell(row=r, column=14).value for r in range(7, 15)]
            assert all(v is None for v in n_values), f"N7:N14 应全空，实得 {n_values}"
        finally:
            wb.close()

    def test_field_order_and_source_refs(self, contract_payload) -> None:
        table = contract_payload["sheets"][0]["tables"][0]
        assert [f["cell"]["column"] for f in table["fields"]] == list("ABCDEFGHIJKL")
        for field in table["fields"]:
            assert field["store_item_id"] == "F4-6-rows"
            assert field["source_ref"].startswith("源xlsx!关联方及交易检查表F4-6!")
            assert field["header_source_ref"].endswith("6"), "单级表头 R6"

    def test_managed_field_specs_column_ordered(self) -> None:
        from app.services.workpaper_sync.sheet_geometry import col_index

        cols = [col_index(s[1]) for s in managed_field_specs(F406.SPEC_F406)]
        assert cols == sorted(cols)


# ═══════════════════════════════════════════════════════════════════════════
# F4-P17：零回归基线（golden digest 现算）
# spec: f4-sync-coverage-and-first-canary · Task 5
# Validates: 7.4
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty17GoldenDigestBaseline:
    """F4 纳入 golden digest 门后，既有 provider 的 digest 不变。

    🔴 真正的逐字节比对在 `check_sync_provider_golden_digest.py` 的 `_compare` 中完成。
    测试层验证：F4 已在 PROVIDERS 中登记、三段 digest 可算出且格式正确。
    """

    def test_f4_is_in_golden_providers(self) -> None:
        """F4 已登记到 golden digest PROVIDERS 中。"""
        import importlib
        mod = importlib.import_module("scripts.check.check_sync_provider_golden_digest")
        labels = {p[0] for p in mod.PROVIDERS}
        assert "f4" in labels, "F4 应已纳入 golden digest PROVIDERS"

    def test_contract_payload_digest_is_valid_hex(self) -> None:
        """F4 的 contract payload 能现算出合法 sha256 hex。"""
        import hashlib, json
        payload = F4.build_contract_payload()
        text = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)

    def test_instrumentation_digest_is_valid_hex(self) -> None:
        """F4 的 instrumentation specs 能现算出合法 sha256 hex。"""
        import hashlib, json
        specs = F4.instrumentation_specs()
        assert len(specs) >= 1, "至少 1 条 instrumentation spec（canary F4-6）"
        canonical = [
            {f: getattr(s, f) for f in (
                "entry_id", "template_id", "template_relative_path", "managed_sheet",
                "sheet_key", "table_key", "first_data_row", "last_data_row", "footer_row",
                "header_row", "managed_last_col", "uuid_col", "table_name",
            ) if hasattr(s, f)}
            for s in specs
        ]
        text = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert len(digest) == 64

    def test_projection_digest_is_valid_hex(self) -> None:
        """F4 的 store projection 能用合成载荷现算出合法 sha256 hex。"""
        import hashlib, json
        payload = F4.build_contract_payload()
        contract = parse_contract(payload, adapter_id=F4.ADAPTER_ID)
        from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs as mfs
        row_specs = F4.managed_row_table_specs()
        spec = next(s for s in row_specs if s.store_item_id == F4.STORE_ITEM_ID)
        fields = mfs(spec)
        rows = []
        for i in range(2):
            row = {spec.row_identity_key: f"synthetic-{i}"}
            for fs in fields:
                vt, jp = fs[3], fs[4]
                val = (i + 1) * 100 if vt in ("amount", "integer") else f"v{i}"
                parts = str(jp).split("/")
                cursor = row
                for seg in parts[:-1]:
                    nxt = cursor.get(seg)
                    if not isinstance(nxt, dict):
                        nxt = {}
                        cursor[seg] = nxt
                    cursor = nxt
                cursor[parts[-1]] = val
            rows.append(row)
        projection = F4.build_store_projection(rows, contract=contract)
        assert projection.contract_id == F4.ADAPTER_ID
        keys = list(projection.stable_keys())
        assert len(keys) > 0, "投影应有非空 stable_keys"


# ═══════════════════════════════════════════════════════════════════════════
# F4-P11：行身份 custom-${index} 修复守卫（BP-7 同型）
# spec: f4-sync-coverage-and-first-canary · Task 19（部分）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty11RowIdentityNoOrdinal:
    """F4-1 审定表的 migrateF4AdjRows 不含旧的下标派生 `custom-${index}`。

    修复前：`custom-${index}`（index 是 map 下标）⇒ 位置派生身份。
    修复后：`custom-${crypto.randomUUID()}`（稳定 UUID）。
    """

    _COMPOSABLE_PATH = (
        Path(__file__).resolve().parents[3]
        / "audit-platform"
        / "frontend"
        / "src"
        / "components"
        / "workpaper"
        / "composables"
        / "useF4Adjudication.ts"
    )

    def test_no_ordinal_custom_pattern_in_source(self) -> None:
        """活代码不含 `custom-${index}` 模板字符串（下标派生）。"""
        import re
        text = self._COMPOSABLE_PATH.read_text(encoding="utf-8")
        stripped = re.sub(r"/\*[\s\S]*?\*/", "", text)
        stripped = re.sub(r"//[^\n]*", "", stripped)
        hits = re.findall(r"`custom-\$\{index\}`", stripped)
        assert not hits, (
            f"useF4Adjudication.ts 活代码含旧下标模板字符串 {hits}"
        )

    def test_custom_uses_random_uuid(self) -> None:
        """兜底键用 crypto.randomUUID()（稳定 UUID）。"""
        text = self._COMPOSABLE_PATH.read_text(encoding="utf-8")
        assert "crypto.randomUUID()" in text, (
            "useF4Adjudication.ts 应含 crypto.randomUUID() 兜底"
        )
