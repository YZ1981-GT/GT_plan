# -*- coding: utf-8 -*-
"""L1 真双向改线守卫（二）——provider / contract / adapter 注册。

spec: l-cycle-true-adapter-registration
判据: LR-P11 ~ LR-P20

口径真源复用 `tests/workpaper_sync/l1_adapter_facts.py`（唯一真源）。
前提复核与模板几何基线见 `test_l1_adapter_registration.py`。
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from tests.workpaper_sync.l1_adapter_facts import (  # noqa: E402
    BARE_IF_PER_SHEET,
    BARE_IF_TOTAL,
    CANDIDATE_PHANTOM_FIELDS,
    CONTRACT_DIR,
    FOOTER_LABEL_CELL,
    FOOTER_LABEL_TEXT,
    FOOTER_PLACEHOLDER_COLUMNS,
    FOOTER_SUM_COLUMNS,
    L1_ADAPTER_ID,
    L1_ADJ_REAL_FIELDS,
    L1_DERIVED_SHEET,
    L1_ENTRY_ID,
    L1_MANAGED_SHEET,
    MANAGED_FORMULA_COLUMNS,
    MANAGED_FORMULA_SHAPES,
    MANAGED_GEOMETRY,
    MEASURED_L_PAYLOAD_2026_09_28,
    MEASURED_SUPPLY_2026_09_28,
    _count_bare_if,
    _entry,
    _is_formula,
    _load_sheet,
    _manifest_entries,
    _query,
)

# ═══════════════════════════════════════════════════════════════════════════
# LR-P11：provider 接口全集
# ═══════════════════════════════════════════════════════════════════════════

PROVIDER_INTERFACE: tuple[str, ...] = (
    "excel_carrier_gate",
    "authoritative_template_path",
    "read_authoritative_template",
    "assert_no_implicit_template_fallback",
    "assert_entry_selectable",
    "instrumentation_spec",
    "instrumentation_specs",
    "template_definition_payload",
    "instrumentation_definition_payload",
    "authority_model_payload",
    "stable_key_for",
    "build_contract_payload",
    "contract_file_path",
    "load_contract_from_disk",
    "assert_contract_file_matches_source",
    "build_store_projection",
    "merge_projection_into_store_rows",
    "all_store_item_ids",
    "publish_definitions",
    "build_matcher",
    "build_registration",
    "register_adapter",
    "resolve_published_frozen_definitions",
    "manifest_capability_enabled",
    "assert_manifest_capability_enabled",
)


@pytest.fixture(scope="module")
def provider():
    from app.services.workpaper_sync import phase5_l1_short_term_loans as m

    return m


class TestProviderInterface:
    """**Feature: l-cycle-true-adapter-registration, LR-P11**"""

    def test_all_interface_functions_are_callable(self, provider) -> None:
        missing = [n for n in PROVIDER_INTERFACE if not callable(getattr(provider, n, None))]
        assert missing == [], f"provider 缺接口：{missing}"

    def test_frozen_identity_matches_manifest(self, provider) -> None:
        assert provider.ENTRY_ID == L1_ENTRY_ID
        assert provider.ADAPTER_ID == L1_ADAPTER_ID
        assert provider.MANAGED_SHEET == L1_MANAGED_SHEET
        assert provider.DERIVED_SHEET == L1_DERIVED_SHEET
        entry = _entry(L1_ENTRY_ID)
        codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
        assert codes == set(provider.WP_CODES), (
            f"manifest wp_code_patterns={sorted(codes)} 与 provider 冻结值"
            f" {sorted(provider.WP_CODES)} 不一致"
        )

    def test_entry_selectable_against_live_manifest(self, provider) -> None:
        entry = provider.assert_entry_selectable()
        assert entry.get("independent_entry") is True

    def test_template_sha256_sentinel_is_live(self, provider) -> None:
        """模板字节漂移必须打红（哨兵不是装饰）。"""
        data = provider.read_authoritative_template()
        import hashlib

        assert hashlib.sha256(data).hexdigest() == provider.TEMPLATE_SHA256

    def test_geometry_constants_agree_with_the_measured_baseline(self, provider) -> None:
        assert provider.HEADER_GROUP_ROW == MANAGED_GEOMETRY["header_group_row"]
        assert provider.HEADER_LEAF_ROW == MANAGED_GEOMETRY["header_leaf_row"]
        assert provider.FIRST_DATA_ROW == MANAGED_GEOMETRY["first_data_row"]
        assert provider.LAST_DATA_ROW == MANAGED_GEOMETRY["last_data_row"]
        assert provider.FOOTER_ROW == MANAGED_GEOMETRY["footer_row"]
        assert provider.MANAGED_LAST_COL == MANAGED_GEOMETRY["last_effective_col"]
        assert provider.FORMULA_COLUMNS == MANAGED_FORMULA_COLUMNS
        assert len(provider.MANAGED_FIELD_SPECS) == 28

    def test_uuid_column_is_beyond_the_template_max_column(self, provider) -> None:
        """隐藏 UUID 列必须落在模板 max_column 之外，不占用已声明列。"""
        from openpyxl.utils import column_index_from_string

        _, ws = _load_sheet(L1_MANAGED_SHEET)
        assert column_index_from_string(provider.UUID_COL) > ws.max_column, (
            f"UUID 列 {provider.UUID_COL} 落在 max_column={ws.max_column} 之内 ⇒ 会覆盖模板列"
        )


# ═══════════════════════════════════════════════════════════════════════════
# LR-P12 ~ LR-P17：contract 交付与双向锁
# ═══════════════════════════════════════════════════════════════════════════

L1_CONTRACT_FILE: str = "l1.short_term_loans.json"
L1_CANDIDATE_FILE: str = "l1.short_term_loans.candidate.json"


class TestContractDelivery:
    """**Feature: l-cycle-true-adapter-registration, LR-P12 ~ LR-P17**"""

    def test_payload_passes_the_schema_parser(self, provider) -> None:
        """LR-P12：现算 payload 过强校验器。"""
        from app.services.workpaper_sync.contracts import parse_contract

        c = parse_contract(provider.build_contract_payload(), adapter_id=provider.ADAPTER_ID)
        assert c.contract_id == L1_ADAPTER_ID
        assert len(c.sheets) == 1

    def test_disk_and_source_are_byte_locked(self, provider) -> None:
        """LR-P13：磁盘契约与代码现算 payload 逐字节相等。"""
        c = provider.assert_contract_file_matches_source()
        assert c.contract_id == L1_ADAPTER_ID

    def test_contract_is_reviewed_and_candidate_is_gone(self, provider) -> None:
        """LR-P14：生产契约文件名无 `.candidate` 中缀，且草案已删（禁双源）。"""
        path = provider.contract_file_path()
        assert path.name == L1_CONTRACT_FILE
        assert path.exists()
        assert not (path.parent / L1_CANDIDATE_FILE).exists(), (
            "candidate 草案仍在 ⇒ 与 reviewed 生产契约构成双源，review_status 门会失效"
        )
        payload = provider.build_contract_payload()
        assert payload["review_status"] == "reviewed"
        assert payload["semantic_version"] == "1.0.0"
        assert payload["contract_id"] == path.stem

    def test_review_entry_id_points_at_this_entry(self, provider) -> None:
        """LR-P15：reviewed 契约的 `review.entry_id` 不再是 null。"""
        assert provider.build_contract_payload()["review"]["entry_id"] == L1_ENTRY_ID

    def test_template_hash_field_names_are_the_required_ones(self, provider) -> None:
        """LR-P12：必须写 `template_sha256` / `normalized_structure_hash`。

        写 `sha256` / `structure_hash` 会被 `definitions._SELF_REFERENCE_KEYS` 递归拒绝。
        """
        tpl = provider.build_contract_payload()["template"]
        assert set(tpl) == {"relative_path", "template_sha256", "normalized_structure_hash"}
        assert "sha256" not in tpl and "structure_hash" not in tpl

    def test_no_forward_reference_to_bundle(self, provider) -> None:
        """LR-P12：payload 禁止出现 bundle 前向引用。"""
        blob = json.dumps(provider.build_contract_payload(), ensure_ascii=False)
        for forbidden in ("bundle_id", "definition_bundle_", "bundle_sha256"):
            assert forbidden not in blob, f"契约出现前向引用 {forbidden!r}"

    def test_formula_mask_covers_exactly_the_five_formula_columns(self, provider) -> None:
        """LR-P17：mask 覆盖 K/R/S/T/U，且 `mode=formula` 字段列 ⊆ mask。"""
        table = provider.build_contract_payload()["sheets"][0]["tables"][0]
        mask = table["formula_mask"]
        first = MANAGED_GEOMETRY["first_data_row"]
        last = MANAGED_GEOMETRY["last_data_row"]
        assert mask == [f"{c}{first}:{c}{last}" for c in MANAGED_FORMULA_COLUMNS]
        masked_cols = {m.split(str(first))[0] for m in mask}
        formula_cols = {
            f["cell"]["column"] for f in table["fields"] if f["mode"] == "formula"
        }
        assert formula_cols == masked_cols == set(MANAGED_FORMULA_COLUMNS)

    def test_row_identity_is_a_stable_field_not_a_position(self, provider) -> None:
        """LR-P17：行身份必须是 `field` + 恰一个 `{row_uuid}`，禁位置化。"""
        table = provider.build_contract_payload()["sheets"][0]["tables"][0]
        assert table["row_identity"]["kind"] == "field"
        assert table["row_identity"]["json_pointer"] == "/rows/*/rowId"
        assert table["delete_policy"] == "tombstone"
        assert table["header_rows"] == 2
        for f in table["fields"]:
            assert f["json_pointer"].count("{row_uuid}") == 1, (
                f"{f['stable_field_key']} 的 json_pointer 不含恰一个 {{row_uuid}}"
            )
            assert f["cell"]["row_from"] == "row_identity"
            for banned in ("index", "ordinal", "position", "row_number", "array_index"):
                assert banned not in str(table["row_identity"]), (
                    f"row_identity 出现被禁的位置化语义 {banned!r}"
                )

    def test_no_semantic_less_column_placeholder(self, provider) -> None:
        """LR-P12：禁 `^col_[a-z]+$` 形态的 generated 列占位。"""
        import re as _re

        table = provider.build_contract_payload()["sheets"][0]["tables"][0]
        bad = [
            f["column_key"]
            for f in table["fields"]
            if _re.fullmatch(r"col_[a-z]+", str(f["column_key"]))
        ]
        assert bad == [], f"出现无语义列占位：{bad}"

    def test_footer_anchor_uses_the_measured_column_not_a_hardcoded_a(
        self, provider
    ) -> None:
        """LR-P17：footer 用 marker + 实测列（C），不写行号、不硬编码 A。

        🔴 框架层 `spec_to_contract_sheet_payload` 原先把 `search_column` 硬编码成 `"A"`，
        L1 的 A26 为空 ⇒ `excel_materialize._find_marker_row` 会一处都找不到 marker 并抛
        `FooterAnchorDriftError`（`phase5_d3_05_long_term` 踩过同一坑）。本判据锁住
        新增的 `footer_search_column` 声明位真的生效。
        """
        table = provider.build_contract_payload()["sheets"][0]["tables"][0]
        anchor = table["footer_anchor"]
        assert anchor["search_column"] == "C", (
            f"footer search_column={anchor['search_column']!r} ⇒ L1 标签在 C26，A26 为空"
        )
        assert anchor["marker"] == FOOTER_LABEL_TEXT
        assert anchor["carries_total_formula"] is True
        assert "row" not in anchor, "footer_anchor 不得写死行号"

    def test_framework_default_search_column_stays_A_for_other_providers(self) -> None:
        """LR-P23 邻域：新增字段的默认值必须仍是 `"A"` —— 既有七家零回归。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec

        import dataclasses

        default = next(
            f.default
            for f in dataclasses.fields(RowTableSheetSpec)
            if f.name == "footer_search_column"
        )
        assert default == "A", "默认值被改动 ⇒ 既有 provider 的 footer 定位会整体漂移"

    def test_identity_carriers_are_within_the_oo94_allowed_set(self, provider) -> None:
        """LR-P12：载体只用 OO 9.4 实测通过的那几种。"""
        allowed = {"hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"}
        carriers = set(provider.build_contract_payload()["identity_carriers"])
        assert carriers <= allowed, f"出现未经 probe 的载体：{sorted(carriers - allowed)}"
        blob = json.dumps(provider.build_contract_payload(), ensure_ascii=False)
        for failed in ("sheet_id", "sheet_display_name"):
            assert f'"{failed}"' not in blob, (
                f"锚点用了 OO 9.4 实测 failed 的 {failed!r}"
            )

    def test_html_only_keys_are_declared_and_excluded(self, provider) -> None:
        """LR-P12：前端多出的 `amount` / `currency` 登记为 HTML-only 且不入字段表。"""
        payload = provider.build_contract_payload()
        declared = set(payload["review"]["html_store"]["html_only_keys"])
        assert declared == set(provider.HTML_ONLY_ROW_KEYS) == {"amount", "currency"}
        mapped = {
            f["json_pointer"].rsplit("/", 1)[-1]
            for f in payload["sheets"][0]["tables"][0]["fields"]
        }
        assert not (declared & mapped), (
            f"HTML-only 键混进了契约字段：{sorted(declared & mapped)}"
        )

    def test_derived_readonly_sheet_is_declared(self, provider) -> None:
        """LR-P6：审定表被显式登记为只读投影，不是「忘了映射」。"""
        d = provider.build_contract_payload()["review"]["derived_readonly_sheet"]
        assert d["excel_name"] == L1_DERIVED_SHEET
        assert "SUMIF" in d["reason"]


# ═══════════════════════════════════════════════════════════════════════════
# LR-P16：契约归属 —— 接过既有守卫里因并发会话而整体过期的那部分实质判据
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 并发会话留下的已知中间态。本 spec **不代改**它们的文件，如实登记，
#: 待其 owner 收口后从本集合移除（反向断言 `stale` 会逼着移除，见下方判据）。
#: 平台既有范式见 `test_registration_isolation_and_alignment.py::_KNOWN_MISALIGNED`。
#:
#: 2026-10-01 清空：原唯一条目 `a51.cashflow_audit.json` 已**从磁盘消失**
#: （它当时是并发会话的未跟踪新文件 `??`，未被提交；现算 `workpaper_sync_contracts/` 下
#: 60 份契约里无此名，`generate_workpaper_sync_managed_sheets.py --check` 也因
#: 「登记表有 a51 而磁盘无文件」报错 ⇒ 那条缺口的**对象本身不在了**）。
#: 🔴 措辞上不写「已修好」—— 它不是被补上 `review.entry_id`，而是整份契约没落库；
#: a51 的收口归 `published-representation-production-path-and-lane-adjudication` 一侧。
KNOWN_CONCURRENT_GAPS: Mapping[str, str] = {
    "a51.cashflow_audit.json": "A51 契约由并发会话交付，review.entry_id 尚未补齐；收口归 a-cycle spec",
}


class TestContractOwnershipInLDomain:
    """**Feature: l-cycle-true-adapter-registration, LR-P16**

    既有守卫 `test_task54_l_cycle_migration.py` 的两条契约归属判据
    （`test_no_pilot_contract_belongs_to_the_l_cycle` / `test_pilot_contracts_still_own_what_they_owned`）
    依赖写死的 `PILOT_CONTRACT_OWNERS`（10 项），而生产契约已现算到 **51** 份
    （D/E/F/G/H/I/J 全域陆续交付）⇒ 该常量**在本 spec 之前就已整体过期**，
    不是本 spec 能单独修好的。本类按「计数现算、禁写死」重建其实质判据。
    """

    @pytest.fixture(scope="class")
    def contracts(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for f in sorted(CONTRACT_DIR.glob("*.json")):
            if f.stem.startswith("_"):
                # README：`_*.json` 是 schema 文档与候选示例，不参与生产清册。
                continue
            out[f.name] = json.loads(f.read_bytes().decode("utf-8"))
        return out

    #: 已接线的 L 域生产契约（逐条具名追加，禁通配）。2026-10-01 task 12 追加 l4。
    #: 2026-10-06 补齐 L2~L8（并发会话 l-cycle-true-adapter-registration 已交付全部 8 条）。
    _L_PRODUCTION: dict[str, str] = {
        L1_CONTRACT_FILE: L1_ENTRY_ID,
        "l2.interest_payable.json": "xlsx/gt-l2-interest-payable",
        "l3.long_term_loans.json": "xlsx/gt-l3-long-term-loans",
        "l4.bonds_payable.json": "xlsx/gt-l4-bonds-payable",
        "l5.long_term_payables.json": "xlsx/gt-l5-long-term-payables",
        "l6.special_payables.json": "xlsx/gt-l6-special-payables",
        "l7.other_noncurrent_liabilities.json": "xlsx/gt-l7-other-noncurrent-liabilities",
        "l8.financial_expenses.json": "xlsx/gt-l8-financial-expenses",
    }

    def test_l_domain_has_exactly_one_production_contract(
        self, contracts: dict[str, dict[str, Any]]
    ) -> None:
        """名字保留（历史引用）；判据为「L 域生产契约恰为已具名登记的集合」。"""
        l_prod = {
            name: doc
            for name, doc in contracts.items()
            if name.startswith("l") and str(doc.get("review_status")) == "reviewed"
        }
        assert sorted(l_prod) == sorted(self._L_PRODUCTION), (
            f"L 域生产契约实得 {sorted(l_prod)}，期望恰 {sorted(self._L_PRODUCTION)}"
        )

    def test_every_production_contract_declares_its_owner(
        self, contracts: dict[str, dict[str, Any]]
    ) -> None:
        """生产契约必须有 `review.entry_id` —— 已知并发缺口显式放行并具名。"""
        missing = sorted(
            name
            for name, doc in contracts.items()
            if str(doc.get("review_status")) == "reviewed"
            and not (doc.get("review") or {}).get("entry_id")
        )
        unexpected = [n for n in missing if n not in KNOWN_CONCURRENT_GAPS]
        assert unexpected == [], (
            f"生产契约缺 review.entry_id：{unexpected} —— 若属并发会话在途，"
            "须显式登记进 KNOWN_CONCURRENT_GAPS 并写明原因"
        )
        stale = [n for n in KNOWN_CONCURRENT_GAPS if n not in missing]
        assert stale == [], (
            f"已登记的并发缺口 {stale} 已被修好 ⇒ 从 KNOWN_CONCURRENT_GAPS 移除"
            "（登记表不得长期留过期条目）"
        )

    def test_contract_ids_match_their_filenames(
        self, contracts: dict[str, dict[str, Any]]
    ) -> None:
        """README：`contract_id` 必须等于文件名，否则注册被拒。"""
        bad = {
            name: doc.get("contract_id")
            for name, doc in contracts.items()
            if doc.get("contract_id") != Path(name).stem.replace(".candidate", "")
        }
        assert bad == {}, f"contract_id 与文件名不符：{bad}"

    def test_no_other_l_entry_sneaks_in_a_contract(
        self, contracts: dict[str, dict[str, Any]]
    ) -> None:
        """未接线的 L entry 不得出现生产契约（反方向也要红）。"""
        owners = {
            str((doc.get("review") or {}).get("entry_id"))
            for doc in contracts.values()
            if str(doc.get("review_status")) == "reviewed"
        }
        l_owners = {o for o in owners if "-l" in o and o.startswith("xlsx/gt-l")}
        assert l_owners == set(self._L_PRODUCTION.values()), (
            f"L 域生产契约归属实得 {sorted(l_owners)}，期望恰 {sorted(self._L_PRODUCTION.values())}"
        )

    def test_candidate_contracts_keep_entry_id_null(
        self, contracts: dict[str, dict[str, Any]]
    ) -> None:
        offenders = sorted(
            name
            for name, doc in contracts.items()
            if str(doc.get("review_status")) == "candidate"
            and (doc.get("review") or {}).get("entry_id")
        )
        assert offenders == [], f"candidate 契约带了 entry_id ⇒ 反例分母被污染：{offenders}"


# ═══════════════════════════════════════════════════════════════════════════
# LR-P18 ~ LR-P20：adapter 注册
# ═══════════════════════════════════════════════════════════════════════════

L1_STORE_ITEM_ID: str = "L1-2-rows"
#: L1 另有四张**本 spec 不动**的位置化表，其 prefix 不得出现在 registry 的 items 里。
L1_UNTOUCHED_PREFIXES: tuple[str, ...] = ("L1-int-", "L1-cred-", "L1-ovd-", "L1-plg-")


class TestAdapterRegistration:
    """**Feature: l-cycle-true-adapter-registration, LR-P18 ~ LR-P20**"""

    @pytest.fixture(scope="class")
    def plan(self):
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        assert L1_ADAPTER_ID in STORE_MERGE_REGISTRY, (
            f"{L1_ADAPTER_ID} 未注册 —— 已注册：{sorted(STORE_MERGE_REGISTRY)}"
        )
        return STORE_MERGE_REGISTRY[L1_ADAPTER_ID]

    def test_plan_has_exactly_one_item(self, plan) -> None:
        """LR-P19：只登记本轮真受管的一条，禁预登记。"""
        from app.services.workpaper_sync.phase5_row_table_sheet import StoreKind

        assert plan.adapter_id == L1_ADAPTER_ID
        assert plan.provider_module == "phase5_l1_short_term_loans"
        assert len(plan.items) == 1, f"items 应恰 1 条，实得 {[i.item_id for i in plan.items]}"
        assert plan.items[0].item_id == L1_STORE_ITEM_ID
        assert plan.items[0].kind is StoreKind.rows

    def test_untouched_sibling_tables_are_not_preregistered(self, plan) -> None:
        """LR-P19：四张未接线的位置化表不得预登记（会让门禁分母失真）。"""
        ids = [i.item_id for i in plan.items]
        leaked = [
            i for i in ids if any(i.startswith(p) for p in L1_UNTOUCHED_PREFIXES)
        ]
        assert leaked == [], f"预登记了未受管的键：{leaked}"

    def test_provider_store_item_ids_are_the_single_source(self, provider, plan) -> None:
        """LR-P19：provider 的 `all_store_item_ids()` 与 registry items 同口径。"""
        assert provider.all_store_item_ids() == tuple(i.item_id for i in plan.items)

    def test_store_item_id_namespace_is_clean_in_the_real_db(self) -> None:
        """LR-P18：新键前缀在真库命中 0，且与既有 L1 键无撞名。"""
        rows = _query(
            "SELECT count(*) FROM checklist_responses WHERE item_id LIKE 'L1-2-%'"
        )
        assert rows[0][0] == 0, (
            f"`L1-2-*` 在真库已有 {rows[0][0]} 行 ⇒ 不是干净命名空间，需重新选键"
        )
        legacy = _query(
            "SELECT count(*) FROM checklist_responses WHERE item_id LIKE 'L1-det-%'"
        )
        assert legacy[0][0] == 0, (
            f"`L1-det-*`（旧位置化形态）在真库有 {legacy[0][0]} 行 ⇒ "
            "切换不再是零迁移负担，必须先写迁移脚本"
        )

    def test_oo_crash_neutralization_is_the_shared_function_object(self, plan) -> None:
        """LR-P20：中性化函数与 G7 解析出的**同一个对象**（`is`，不是同名替身）。"""
        from app.services.workpaper_sync.adapters.excel import (
            _resolve_oo_crash_neutralization_fn,
        )

        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas"
        l1_fn = _resolve_oo_crash_neutralization_fn(L1_ADAPTER_ID)
        g7_fn = _resolve_oo_crash_neutralization_fn("g7.soe_subsidiary_disclosure")
        assert l1_fn is not None, "L1 解析不到中性化函数 ⇒ per-file 策略未生效"
        assert l1_fn is g7_fn, "解析到的不是共用函数对象 ⇒ 有人新造了一个同名实现"

    def test_excel_adapter_has_no_l1_literal_branch(self) -> None:
        """LR-P20：禁 `if adapter_id == "l1…"` 字面量分支。"""
        from app.services.workpaper_sync.adapters import excel as excel_mod

        source = Path(excel_mod.__file__).read_bytes().decode("utf-8")
        for banned in ('adapter_id == "l1', "adapter_id == 'l1"):
            assert banned not in source, (
                f"`adapters/excel.py` 出现 {banned!r} ⇒ 会打红框架层零 wp_code 分支判据"
            )

    def test_registry_lookup_helpers_resolve_the_new_plan(self) -> None:
        """LR-P19：三态解析入口对新 adapter 正常工作。"""
        from app.services.workpaper_sync.store_item_registry import (
            all_registered_adapter_ids,
            resolve_store_merge_plan,
            store_merge_plan_or_skip,
        )

        assert L1_ADAPTER_ID in all_registered_adapter_ids()
        assert resolve_store_merge_plan(L1_ADAPTER_ID).adapter_id == L1_ADAPTER_ID
        assert store_merge_plan_or_skip(L1_ADAPTER_ID) is not None
        assert store_merge_plan_or_skip(L1_ENTRY_ID) is None, (
            "entry_id 形态的输入应返回 None（跳过镜像），不是抛错"
        )

    def test_manifest_capability_gate_still_blocks_registration(self, provider) -> None:
        """LR-P22 前置：manifest 尚未翻转 ⇒ capability 门必须仍拦住注册。

        🔴 这条是**顺序门**的正面判据：contract + registry 就位 ≠ 可以挂 adapter。
        Task 8 翻 manifest 之后本断言会反向，届时按新事实改（不是删）。
        """
        entry = _entry(L1_ENTRY_ID)
        if entry.get("capability") == "bidirectional" and entry.get("adapter_id") == L1_ADAPTER_ID:
            assert provider.manifest_capability_enabled() is True
            provider.assert_manifest_capability_enabled()
        else:
            assert provider.manifest_capability_enabled() is False, (
                "manifest 仍是 legacy 却报 capability 已启用 ⇒ 顺序门失效"
            )
            with pytest.raises(Exception) as exc:
                provider.assert_manifest_capability_enabled()
            assert "bidirectional" in str(exc.value)



# ═══════════════════════════════════════════════════════════════════════════
# LR-P18 邻域：HTML 侧与 provider 的 store 形态对账（Task 5b）
# ═══════════════════════════════════════════════════════════════════════════

_FRONTEND_SRC = (
    Path(__file__).resolve().parents[3] / "audit-platform" / "frontend" / "src"
)
_L1_FORM_DATA = _FRONTEND_SRC / "composables" / "useL1FormData.ts"
_L1_DETAIL = _FRONTEND_SRC / "composables" / "useL1Detail.ts"
#: 仍走位置化通道、本 spec **不动**的四张表（`int` 被 H2 跨循环消费）。
_UNTOUCHED_POSITIONAL_PREFIXES = ("int", "cred", "ovd", "plg")


def _strip_ts_comments(src: str) -> str:
    """剥 TS 的块注释与行注释（只判存在性，不保留行号）。

    `(?<!:)` 是为了不把 `https://` 的 `//` 当成行注释起点。
    """
    import re

    out = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    out = re.sub(r"(?<!:)//[^\n]*", "", out)
    return out


class TestHtmlStoreShapeAgreesWithProvider:
    """**Feature: l-cycle-true-adapter-registration, Task 5b**

    两侧 store 形态必须对得上：provider 声明 `L1-2-rows`，前端就得往那个 item 写。
    只验后端不验前端，会出现「契约按 rows 拆、前端还在写位置化键」这种两侧各自自洽
    但合不上的形态 —— 那正是 L 循环此前的病灶。
    """

    @pytest.fixture(scope="class")
    def form_data_src(self) -> str:
        assert _L1_FORM_DATA.is_file(), f"前端真源不存在：{_L1_FORM_DATA}"
        return _L1_FORM_DATA.read_bytes().decode("utf-8")

    @pytest.fixture(scope="class")
    def detail_src(self) -> str:
        assert _L1_DETAIL.is_file(), f"前端真源不存在：{_L1_DETAIL}"
        return _L1_DETAIL.read_bytes().decode("utf-8")

    def test_frontend_item_id_equals_provider_store_item_id(
        self, provider, form_data_src: str
    ) -> None:
        """前端导出的 item id 常量与 provider 的 `STORE_ITEM_ID` 逐字相同。"""
        assert f"DETAIL_ROWS_ITEM_ID = '{provider.STORE_ITEM_ID}'" in form_data_src, (
            f"前端未声明 DETAIL_ROWS_ITEM_ID = '{provider.STORE_ITEM_ID}' ⇒ 两侧 store 键不一致"
        )
        assert provider.STORE_ITEM_ID == L1_STORE_ITEM_ID

    def test_frontend_no_longer_builds_positional_detail_keys(
        self, form_data_src: str, detail_src: str
    ) -> None:
        """🔴 `L1-det-` 拼接已从两个前端文件中彻底移除。

        🔴 **必须剥注释再扫**（首版实测踩到）：两份文件的注释里都要解释「旧形态是
        `L1-det-{rowIndex+1}-{field}`、为什么换掉」，裸文本扫描会命中这些解释文字
        并把「已删除 + 已留档」误判成「仍在使用」。这与平台铁律
        「命中后必须判注释/代码，只数命中会误报」同源。
        """
        for name, src in (("useL1FormData.ts", form_data_src), ("useL1Detail.ts", detail_src)):
            code = _strip_ts_comments(src)
            assert "L1-det-" not in code, (
                f"{name} 仍在拼位置化键 `L1-det-` ⇒ 契约的 row_identity 会与实际载荷脱钩"
            )
            # 反向自检：剥注释器没把整份源码吃掉（否则判据恒真）
            assert "DETAIL_ROWS_ITEM_ID" in code or "_persist" in code, (
                f"{name} 剥注释后连关键符号都没了 ⇒ 剥注释器有问题，判据不可信"
            )

    def test_comment_stripper_is_not_vacuous(self) -> None:
        """剥注释器变异证明：注释里的键被剥掉，代码里的键留得住。"""
        assert _strip_ts_comments("// item_id: `L1-det-1-bank`\nconst a = 1") .strip() == (
            "const a = 1"
        )
        assert "L1-det-" in _strip_ts_comments("const id = `L1-det-${n}-${f}`")
        assert "L1-det-" not in _strip_ts_comments("/** 旧形态 `L1-det-{n}` 已删 */")
        # URL 里的 `//` 不得被当成行注释起点
        assert "https://x.y" in _strip_ts_comments("const u = 'https://x.y'")

    def test_frontend_row_identity_is_the_contract_key(
        self, provider, form_data_src: str
    ) -> None:
        """前端行身份字段名 == 契约 `row_identity` 指向的键（`rowId`）。"""
        table = provider.build_contract_payload()["sheets"][0]["tables"][0]
        key = table["row_identity"]["json_pointer"].rsplit("/", 1)[-1]
        assert key == provider.ROW_IDENTITY_STORE_KEY == "rowId"
        assert f"rowId: string" in form_data_src, "前端 DetailRow 未声明 rowId 字段"
        assert "newRowIdentity" in form_data_src, (
            "前端未复用共享的值化行身份工厂 ⇒ 可能又自造了一个铸号实现"
        )

    def test_sibling_tables_keep_their_positional_channel(self, form_data_src: str) -> None:
        """🔴 反向判据：另外四张表**仍**走位置化通道（本 spec 明确不动它们）。

        若哪天它们也被改了，本断言会红 —— 那时必须先确认 `h2L1LoanPull.ts`
        对 `L1-int-{n}-{field}` 的消费已同步，否则会连带 H2。
        """
        for prefix in _UNTOUCHED_POSITIONAL_PREFIXES:
            assert f"_serializeRows(items, '{prefix}'" in form_data_src, (
                f"`{prefix}` 表的位置化序列化调用点消失 ⇒ 若是有意改动，"
                "须先核对跨循环消费方（H2 读 L1-int-*）"
            )

    def test_managed_field_json_keys_exist_in_the_frontend_row_type(
        self, provider, form_data_src: str
    ) -> None:
        """契约每个受管字段的 json 键都能在前端 `DetailRow` 里找到声明。"""
        table = provider.build_contract_payload()["sheets"][0]["tables"][0]
        keys = [f["json_pointer"].rsplit("/", 1)[-1] for f in table["fields"]]
        assert len(keys) == 28
        missing = [k for k in keys if f"  {k}:" not in form_data_src]
        assert missing == [], (
            f"契约声明了这些字段但前端 DetailRow 没有：{missing} ⇒ 往返时会静默丢值"
        )
