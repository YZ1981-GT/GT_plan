# -*- coding: utf-8 -*-
"""H canary（H9 租赁负债）端到端判据：HF-P11 / HF-P15 / HF-P17 + 契约 / 投影 / 对齐。

spec: `h-cycle-sync-foundation-and-first-canary` · Tasks 19 / 20
Requirements 5 / 6 / 8 / 9

═══ 为什么 P11 / P15 / P17 在这里而不在 `test_h_foundation_hc_guards.py` ═══

这三条都依赖 **canary 契约本身**（representation 字段声明 / `source_ref` 不依赖 wp_index /
真库载荷非空）。放在一起才能一眼看出「契约变了要同时过哪些门」；
foundation 那份守的是**全循环共性事实**，不依赖任何 provider。

═══ 🔴 既有平台缺口（**不是**本 spec 引入，本 spec 也不修）═══

零回归门 `backend/scripts/check/check_sync_provider_golden_digest.py` 当前**整体跑不起来**：
`phase5_f1_prepayment.build_contract_payload()` 产出的 payload 过不了 `parse_contract`
（`sheets[f16-managed].tables[related_party_rows]: table anchor 必须是 A1 单元格，实得 None`），
而 f1 在 `PROVIDERS` 里排在 h9 之前 ⇒ `run()` 在 f1 上就抛。
该缺陷属 `f1-sync-coverage-and-first-canary` 作业面（**改动前实测已红**，见
`evidence/task0-prerequisites.md` §三）。

⇒ 本文件**自带** h9 的 digest 判据（:class:`TestH9GoldenDigest`），
不依赖那个门能不能跑；f1 修好后门会自动把 h9 纳入，两处判据互不替代。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import phase5_h9_02_detail as D  # noqa: E402
from app.services.workpaper_sync import phase5_h9_lease_liabilities as M  # noqa: E402
from app.services.workpaper_sync import phase5_row_table_sheet as RT  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402
from tests.workpaper_sync import h_cycle_facts as F  # noqa: E402

_EVIDENCE = (
    _REPO
    / ".kiro"
    / "specs"
    / "h-cycle-sync-foundation-and-first-canary"
    / "evidence"
    / "task19-canary-db-evidence.json"
)


@pytest.fixture(scope="module")
def contract():
    return parse_contract(M.build_contract_payload(), adapter_id=M.ADAPTER_ID)


@pytest.fixture(scope="module")
def db_evidence() -> dict:
    return json.loads(_EVIDENCE.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# HF-P17　canary 真库前置实证（选型依据 1）
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP17CanaryDatabaseEvidence:
    """🔴 选型依据：H9-2-rows 是 9 条主表键里**唯一**非空载荷。

    🔴 若该断言失败（真库被清空）THEN canary 选型失效，须回到选型重选，
    **不得造数据顶上** —— 造数据的 roundtrip 是伪实证。
    """

    def test_h9_primary_key_payload_is_non_empty_in_the_real_database(
        self, db_evidence: dict
    ) -> None:
        payloads = db_evidence["primary_key_payload_bytes"]
        assert payloads["H9-2-rows"] >= 819, payloads["H9-2-rows"]
        assert db_evidence["canary_selection"]["row_count"] == 2
        assert db_evidence["canary_selection"]["conclusion_bytes"] == 0

    def test_all_other_primary_keys_are_absent_or_empty_arrays(
        self, db_evidence: dict
    ) -> None:
        """其余 8 条：无行（`null`）或字面 `[]`（2 B）。"""
        payloads = db_evidence["primary_key_payload_bytes"]
        assert set(payloads) == set(F.H_PRIMARY_KEYS.values()), sorted(payloads)
        for key, size in payloads.items():
            if key == "H9-2-rows":
                continue
            assert size in (None, 2), f"{key} 实测 {size} B —— 选型前提变了"
        assert payloads["H8-2-rows"] == 2 and payloads["H10-detail-rows"] == 2

    def test_field_count_is_twenty_two_not_twenty_three(self, db_evidence: dict) -> None:
        """🔴 spec Requirement 5.3 写 23，其自身枚举与真库现算均为 **22**。"""
        names = db_evidence["field_names_in_order"]
        assert len(names) == 22, names
        assert db_evidence["canary_selection"]["fields_per_row"] == 22

    def test_persisted_field_names_match_the_frontend_persist_list(
        self, db_evidence: dict
    ) -> None:
        """真库字段名 == `useH9Detail.ts` 的 `_persist()` 落盘列表（按值比，不靠记忆）。"""
        source = (F.COMPOSABLES / "useH9Detail.ts").read_text(encoding="utf-8", errors="replace")
        body = source.split("const toPersist = rows.value.map(")[1].split("})\n")[0]
        for name in db_evidence["field_names_in_order"]:
            assert f"{name}:" in body, f"{name} 不在 _persist() 落盘列表里"

    def test_formula_columns_are_not_persisted(self, db_evidence: dict) -> None:
        """6 个公式列的 json_key **不落库** —— 前端 load 时重算。"""
        persisted = set(db_evidence["field_names_in_order"])
        for name in db_evidence["formula_columns_not_persisted"]:
            assert name not in persisted, f"{name} 竟然落库了 —— 契约的 formula 声明要复核"

    def test_row_identities_are_family_a_safe_forms(self, db_evidence: dict) -> None:
        ids = db_evidence["row_identities"]
        assert len(ids) == 2
        assert any(i.startswith("row-liab-H91-FILL-") for i in ids), ids
        # 两形态都带随机 / 时间戳后缀 ⇒ 族 A；canary 不含身份改造
        assert all(len(i.rsplit("-", 1)[-1]) >= 4 for i in ids), ids


# ═══════════════════════════════════════════════════════════════════════════
# HF-P11　HC-11 中文枚举 + derived 字段声明
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP11RepresentationDeclarations:
    """HC-11：中文枚举域不得声明为 boolean；跨 entry 派生标记必须标 derived。"""

    def test_three_chinese_enum_fields_are_declared_with_chinese_domains(
        self, contract
    ) -> None:
        enums = contract.canonical_payload["review"]["enum_fields"]
        assert sorted(enums) == ["isConfirmed", "isRelatedParty", "isTerminated"]
        for field, domain in enums.items():
            assert domain == ["是", "否"], (field, domain)
            # 🔴 变异「声明为 boolean」判据：值域里不得出现布尔字面量
            assert not any(isinstance(v, bool) for v in domain), field

    def test_enum_domain_matches_the_frontend_default_and_comparison(self) -> None:
        """值域取自前端实测：缺省 `'否'` + `isTerminated` 显式比较 `=== '是'`。"""
        source = (F.COMPOSABLES / "useH9Detail.ts").read_text(encoding="utf-8", errors="replace")
        assert "raw.isRelatedParty ?? '否'" in source
        assert "raw.isConfirmed ?? '否'" in source
        assert "raw.isTerminated === '是'" in source
        assert set(D.CHINESE_ENUM_FIELDS_H902["isTerminated"]) == {"是", "否"}

    def test_terminated_from_h8_is_declared_derived_and_written_by_h8_flow(
        self, contract
    ) -> None:
        derived = contract.canonical_payload["review"]["derived_fields"]
        assert derived == ["terminatedFromH8"]
        source = (F.COMPOSABLES / "useH9Detail.ts").read_text(encoding="utf-8", errors="replace")
        assert "terminatedFromH8: true" in source
        assert "markTerminatedFromH8" in source
        assert "applyH8TerminationToH92Rows" in source

    def test_store_only_and_template_only_gaps_are_declared_not_silently_dropped(
        self, contract
    ) -> None:
        """两处口径差异必须**登记**：模板有列/HTML 无字段、HTML 有字段/模板无列。"""
        review = contract.canonical_payload["review"]
        assert review["store_only_fields"] == [
            "contractNo",
            "assetDesc",
            "ibrRate",
            "leaseTerm",
            "isTerminated",
            "terminationDate",
            "terminatedFromH8",
        ]
        cols = [c["column"] for c in review["template_only_columns"]]
        assert cols == ["U", "V"]
        # 这两列不得出现在受管字段里（Requirement 6.1 禁止无来源自造字段）
        managed_columns = {row[1] for row in D.FIELD_SPECS_H902}
        assert managed_columns.isdisjoint({"U", "V"})

    def test_cell_lock_flags_are_inert_because_sheet_protection_is_off(
        self, contract
    ) -> None:
        """🔴 `locked` 在 H 循环**惰性**，不得用它推断 `mode`。

        实测 9 张 H 主受管表的 sheet 级保护**全部未启用** ⇒ `locked=True` 只是 Excel 未设样式
        时的默认值。本表 `M`（重分类）locked 但无公式且 HTML 侧可编辑 ——
        这**不是模板缺陷**，而是「这批标志整体无判读价值」的实证。
        """
        import openpyxl

        facts = contract.canonical_payload["review"]["template_cell_lock_facts"]
        assert facts["sheet_protection_enabled"] is False
        assert facts["locked_without_formula"] == ["M"]
        assert facts["formula_without_locked"] == []

        wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES["H9"], data_only=False)
        try:
            assert bool(wb[D.MANAGED_SHEET_H902].protection.sheet) is False
        finally:
            wb.close()

        by_col = {row[1]: row[2] for row in D.FIELD_SPECS_H902}
        assert by_col["M"] == "editable", "mode 按「有没有真公式」判，不按 locked"
        assert "M" not in D.FORMULA_TEMPLATES_H902

    def test_sheet_protection_is_off_on_all_nine_h_main_sheets(self) -> None:
        """把这条事实钉在全循环层面：将来有人开了保护，本判据会打红提醒复核 mode 口径。"""
        import openpyxl

        main_sheets = {
            "H2": "明细表H2-2",
            "H3": "明细表（成本模式）H3-2",
            "H4": "明细表H4-2",
            "H5": "明细表H5-2",
            "H6": "明细表H6-2",
            "H7": "明细表（成本模式）H7-2",
            "H8": "明细表H8-2",
            "H9": "租赁负债明细表H9-2",
            "H10": "明细表H10-2",
        }
        for code, sheet in main_sheets.items():
            wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES[code], data_only=False)
            try:
                assert bool(wb[sheet].protection.sheet) is False, code
            finally:
                wb.close()

    def test_field_count_and_modes_match_the_template(self, contract) -> None:
        table = contract.sheets[0].tables[0]
        assert len(table.fields) == 20, "A..T 共 20 列受管（U/V 不纳管）"
        formula_cols = {
            f.cell.column for f in table.fields if f.mode == "formula"
        }
        assert formula_cols == {"E", "I", "J", "K", "L", "N"}


# ═══════════════════════════════════════════════════════════════════════════
# HF-P15　HC-15 wp_index 三处风险的显式规避
# ═══════════════════════════════════════════════════════════════════════════


class TestHfP15WpIndexAvoidance:
    """HC-15：契约 sheet 定位**禁止**依赖 `wp_index.wp_name` 与 wp_index 子码登记。"""

    def test_contract_locates_sheets_by_template_full_name_only(self, contract) -> None:
        sheet = contract.sheets[0]
        assert sheet.excel_name == D.MANAGED_SHEET_H902 == "租赁负债明细表H9-2"
        # 🔴 sheet 名必须是**模板里的全名**（含尾码）；去掉尾码会让 `wb[name]` KeyError
        facts = F.workbook_clean_points("H9")
        assert sheet.excel_name in facts["sheet_names"], facts["sheet_names"]
        assert sheet.excel_name.endswith("H9-2")

    def test_contract_payload_carries_no_wp_name_sourced_field(self, contract) -> None:
        """整份契约 payload 里不得出现 `wp_name` 作为来源字段（per-project 命名漂移）。"""
        blob = json.dumps(contract.canonical_payload, ensure_ascii=False)
        assert "wp_name" not in blob, "契约不得依赖 wp_index.wp_name 定位 sheet"

    def test_source_refs_point_at_the_template_not_at_wp_index(self, contract) -> None:
        table = contract.sheets[0].tables[0]
        for field in table.fields:
            assert field.source_ref.startswith(f"源xlsx!{D.MANAGED_SHEET_H902}!"), field.source_ref
        # `header_source_ref` 不是 `FieldSpec` 的解析属性（只在 canonical payload 里）⇒ 读 payload
        raw_fields = contract.canonical_payload["sheets"][0]["tables"][0]["fields"]
        for raw in raw_fields:
            assert raw["header_source_ref"].startswith(
                f"源xlsx!{D.MANAGED_SHEET_H902}!"
            ), raw["header_source_ref"]

    def test_header_source_ref_row_is_the_leaf_header_row(self, contract) -> None:
        """两级表头 ⇒ `header_source_ref` 取**叶子行** R8（不是组标题行 R7）。"""
        raw_fields = contract.canonical_payload["sheets"][0]["tables"][0]["fields"]
        rows = {int(raw["header_source_ref"].rsplit("!", 1)[-1][1:]) for raw in raw_fields}
        assert rows == {D.HEADER_LEAF_ROW_H902}, rows


# ═══════════════════════════════════════════════════════════════════════════
# 契约几何 / 对齐 / 投影
# ═══════════════════════════════════════════════════════════════════════════


class TestH9ContractGeometryIsGroundedInTheTemplate:
    """契约声明的每一项几何都能在模板里逐格取到（禁推演）。"""

    def test_anchor_and_header_rows(self, contract) -> None:
        table = contract.sheets[0].tables[0]
        assert table.anchor == f"A{D.HEADER_GROUP_ROW_H902}" == "A7"
        assert table.header_rows == 2
        assert table.two_level_header is True

    def test_formula_mask_covers_exactly_the_six_formula_columns(self, contract) -> None:
        table = contract.sheets[0].tables[0]
        assert set(table.formula_mask) == {
            f"{c}{D.FIRST_DATA_ROW_H902}:{c}{D.LAST_DATA_ROW_H902}"
            for c in ("E", "I", "J", "K", "L", "N")
        }

    @pytest.mark.parametrize("column,template", sorted(D.FORMULA_TEMPLATES_H902.items()))
    def test_every_declared_formula_matches_the_template_cell_by_cell(
        self, column: str, template: str
    ) -> None:
        """5 行 × 6 列 = 30 次逐格比对。"""
        import openpyxl

        wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES["H9"], data_only=False)
        ws = wb[D.MANAGED_SHEET_H902]
        try:
            for row in range(D.FIRST_DATA_ROW_H902, D.LAST_DATA_ROW_H902 + 1):
                assert str(ws[f"{column}{row}"].value) == template.format(r=row), (
                    column,
                    row,
                    ws[f"{column}{row}"].value,
                )
        finally:
            wb.close()

    def test_liability_credit_side_formula_is_not_the_asset_side_form(self) -> None:
        """🔴 负债贷方口径：`E=B-C+D` / `L=I-J+K`。抄成资产类（`B+C-D`）会让审定期末反号。"""
        assert D.FORMULA_TEMPLATES_H902["E"] == "=B{r}-C{r}+D{r}"
        assert D.FORMULA_TEMPLATES_H902["L"] == "=I{r}-J{r}+K{r}"

    def test_header_texts_are_taken_verbatim_from_the_template_leaf_cells(self) -> None:
        """20 个 `header_text` 逐字取模板叶子格（FC-5 以模板为权威）。"""
        import openpyxl
        from openpyxl.utils import get_column_letter

        wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES["H9"], data_only=False)
        ws = wb[D.MANAGED_SHEET_H902]
        merges = list(ws.merged_cells.ranges)

        def covering(row: int, col: str) -> str:
            index = 0
            for ch in col:
                index = index * 26 + (ord(ch) - 64)
            for rng in merges:
                if rng.min_row <= row <= rng.max_row and rng.min_col <= index <= rng.max_col:
                    return f"{get_column_letter(rng.min_col)}{rng.min_row}"
            return f"{col}{row}"

        try:
            for _key, col, _mode, _vt, _json_key, header_text, _group in D.FIELD_SPECS_H902:
                ref = covering(D.HEADER_LEAF_ROW_H902, col)
                assert str(ws[ref].value).strip() == header_text, (col, ref, ws[ref].value)
        finally:
            wb.close()

    def test_uuid_column_is_effective_content_columns_plus_one(self) -> None:
        """HC-13：UUID 列 = 有效内容列（22）+ 1 = W，**不是** `max_column+1` 之外的位置。"""
        from openpyxl.utils import column_index_from_string

        effective = F.effective_content_columns(
            "H9",
            D.MANAGED_SHEET_H902,
            [D.HEADER_GROUP_ROW_H902, D.HEADER_LEAF_ROW_H902]
            + list(range(D.FIRST_DATA_ROW_H902, D.FOOTER_ROW_H902 + 1)),
        )
        assert effective == D.EFFECTIVE_COLUMNS_H902 == 22
        assert column_index_from_string(D.UUID_COL_H902) == effective + 1

    def test_uuid_column_is_empty_in_the_template(self) -> None:
        """写 UUID 不得覆盖任何既有内容。"""
        import openpyxl

        wb = openpyxl.load_workbook(F.TPL_H / F.H_TEMPLATES["H9"], data_only=False)
        ws = wb[D.MANAGED_SHEET_H902]
        try:
            for row in range(1, ws.max_row + 1):
                value = ws[f"{D.UUID_COL_H902}{row}"].value
                assert value is None or str(value).strip() == "", (row, value)
        finally:
            wb.close()


class TestH9ProviderWiring:
    """provider 的七段流程接线（对齐 / 投影签名 / 注册登记 / 中性化）。"""

    def test_provider_specs_align_with_contract(self, contract) -> None:
        """D4-35 事故形态的通用守卫：instrumentation 受管 sheet 集合 == 契约 `sheets[]`。"""
        RT.assert_provider_specs_align_with_contract(M, contract)

    def test_instrumentation_is_plural(self) -> None:
        specs = M.instrumentation_specs()
        assert isinstance(specs, tuple) and len(specs) == 1
        assert specs[0].sheet_key == D.SHEET_KEY_H902

    def test_build_store_projection_takes_payload_as_first_positional_arg(
        self, contract
    ) -> None:
        """🔴 签名刚性：零回归门按 `build_store_projection(rows, contract=contract)` 调用。

        写成两位置参（F1 / F2 的形态）会在那个门上直接 `TypeError`。
        """
        rows = [
            {
                "rowId": "r1",
                "lessor": "甲出租方",
                "beginBalance": 100,
                "repayment": 20,
                "interestAccrued": 5,
                "reclassification": 30,
                "dueWithin1Y": 30,
                "isRelatedParty": "否",
                "isConfirmed": "否",
            }
        ]
        projection = M.build_store_projection(json.dumps(rows), contract=contract)
        assert projection.row_keys == {D.ROWS_TABLE_KEY_H902: ("r1",)}
        assert len(projection.values) == 20

    def test_projection_carries_chinese_enum_values_verbatim(self, contract) -> None:
        """🔴 中文枚举不得在投影阶段被转成布尔。"""
        rows = [{"rowId": "r1", "lessor": "甲", "isRelatedParty": "是", "isConfirmed": "否"}]
        projection = M.build_store_projection(json.dumps(rows), contract=contract)
        by_key = {k.rsplit("/", 1)[-1]: v.value for k, v in projection.values.items()}
        assert by_key["is_related_party"] == "是"
        assert by_key["is_confirmed"] == "否"
        assert not isinstance(by_key["is_related_party"], bool)

    def test_merge_round_trips_and_preserves_store_only_fields(self, contract) -> None:
        """store-only 七字段不映射格 ⇒ merge 后必须**原样保留**。"""
        base = [
            {
                "rowId": "r1",
                "lessor": "甲",
                "contractNo": "CN-1",
                "assetDesc": "厂房",
                "ibrRate": 4.5,
                "leaseTerm": 36,
                "isTerminated": "否",
                "terminationDate": "",
                "terminatedFromH8": False,
            }
        ]
        projection = M.build_store_projection(
            json.dumps([{"rowId": "r1", "lessor": "乙", "beginBalance": 7}]),
            contract=contract,
        )
        merged, _applied, _visited, _ = M.merge_projection_into_store_rows(
            projection=projection, base_rows=base
        )
        row = next(r for r in merged if r["rowId"] == "r1")
        for field in D.STORE_ONLY_FIELDS_H902:
            assert field in row, f"store-only 字段 {field} 被 merge 丢了"
        assert row["contractNo"] == "CN-1" and row["leaseTerm"] == 36

    def test_store_merge_plan_is_registered_with_per_file_neutralization(self) -> None:
        """HC-12：plan 必须带 `oo_crash_neutralization_fn`（per-file，9 册无例外）。"""
        from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

        plan = STORE_MERGE_REGISTRY[M.ADAPTER_ID]
        assert plan.provider_module == "phase5_h9_lease_liabilities"
        assert plan.oo_crash_neutralization_fn == "neutralize_oo_crash_if_formulas"
        assert [i.item_id for i in plan.items] == [D.STORE_ITEM_ID_H902]

    def test_contract_is_registered_in_the_delivery_ledger(self) -> None:
        from app.services.workpaper_sync.adapters.registry import (
            DELIVERED_PER_ENTRY_CONTRACTS,
        )

        row = next(
            r for r in DELIVERED_PER_ENTRY_CONTRACTS if r["contract_id"] == M.ADAPTER_ID
        )
        assert row["entry_id"] == M.ENTRY_ID
        assert row["pilot_class"] == M.PHASE5_WAVE
        assert row["template_relative_path"] == M.TEMPLATE_RELATIVE_PATH
        # 🔴 平台级供给缺口（BP-1~BP-3）未兑现前如实标 False，不放宽判据凑注册数
        assert row["adapter_registered"] is False

    def test_disk_contract_matches_provider_source(self) -> None:
        """双向锁：磁盘 json 与模块现算 payload 一致（禁手改磁盘）。"""
        assert M.contract_file_path().exists()
        M.assert_contract_file_matches_source()

    def test_manifest_capability_gate_is_now_open(self) -> None:
        """🔴 **2026-10-01 判据翻面**（原名 `..._is_still_single_onlyoffice`）。

        原断言是「`manifest_capability_enabled()` 必须为 False 且
        `assert_manifest_capability_enabled()` 必须抛」—— 那是「正向门必须关着」的形态。
        H9 连同全 H 九条已按六项前置把 capability 翻为 `bidirectional`
        （commit `33e2a049b`，审计见 foundation spec 文末），继续要求 False 就是要求成果
        不许存在。

        原 docstring 说「capability 只能由 `register_from_manifest()` 迁移，禁手改 manifest」
        —— 这句话本身是**对实现的误解**，现读可证：`register_from_manifest()` 读 manifest
        capability 来决定能不能注册（`assert_manifest_capability_enabled()` 在 provider 的
        `attach_*` 入口），**不写** manifest。capability 的唯一写入路径是 overlay override
        经 `generate_workpaper_sync_manifest.py --apply` 生成 —— 而那条路径自带
        `approved_source_digest` 门（改 mount 清册要先复核 diff），并不是「手改」。

        翻面后断言「门开着」，并保留反向意义：门被关回去（overlay override 掉了 / 有人把
        capability 改回 single_onlyoffice）本条会红。
        """
        assert M.manifest_capability_enabled() is True, (
            "H9 的 manifest capability 门又关上了 —— 查 overlay 里 "
            "GtH9LeaseLiabilities.vue 那条 override 是否还在，以及 manifest 是否重算过"
        )
        # 门开着时这个断言器必须**不抛**（翻面前它是必抛）
        M.assert_manifest_capability_enabled()

    def test_template_bytes_are_frozen(self) -> None:
        data = M.read_authoritative_template()
        assert len(data) == 67693


# ═══════════════════════════════════════════════════════════════════════════
# H9 零回归 digest（自带，不依赖被 f1 卡死的平台级门）
# ═══════════════════════════════════════════════════════════════════════════

#: 🔴 冻结 digest。三个 digest 各钉一层：
#: * `contract` —— 契约 canonical payload（几何 / 字段 / review 声明任一变化即漂）；
#: * `instrumentation` —— 注册路径真正用的 instrumentation payload（复数形态）；
#: * `projection` —— 固定输入行经引擎投影后的 `(value, value_type, mode)` 三元组集合。
#:
#: 🔴 **改这些数字前先问「是不是引擎/契约真的该变」**。H9 的投影/合并全是 ≤3 行薄转发，
#: 任何 digest 漂移都来自引擎本身或契约声明 —— 直接改数字等于把回归信号按掉。
_FROZEN_DIGESTS: dict[str, str] = {
    "contract": "419c1729af5bd3d965fc2a83c77e48db1da72d1bf9c495dc94c5968cb7dd721a",
    "instrumentation": "9b569e96990fe1230da001c3ef56b431e0f7ccea1dda4355c5d3179e6f68ece9",
    "projection": "4a8732d919b5f34bd959d1c524fe97c53b6cd44851448c9de14d25df66cf0fac",
}

#: 投影 digest 的固定输入（**不得**随便改 —— 改了 digest 必漂，就失去零回归意义）。
_PROJECTION_FIXTURE: list[dict[str, object]] = [
    {
        "rowId": "r1",
        "lessor": "A",
        "beginBalance": 100,
        "repayment": 20,
        "interestAccrued": 5,
        "reclassification": 30,
        "dueWithin1Y": 30,
        "isRelatedParty": "否",
        "isConfirmed": "否",
    }
]


class TestH9GoldenDigest:
    """H9 三层 digest 冻结。

    🔴 平台级零回归门 `scripts/check/check_sync_provider_golden_digest.py` 已登记
    `("h9", "phase5_h9_lease_liabilities", "ADAPTER_ID", True, True)`，但该门**当前整体
    跑不起来** —— `phase5_f1_prepayment.build_contract_payload()` 产出的 payload 过不了
    `parse_contract`，而 f1 在 `PROVIDERS` 里排在 h9 之前（改动前实测已红，属
    `f1-sync-coverage-and-first-canary` 作业面）。本类是 h9 的**独立**判据，
    f1 修好后两处并存、互不替代。
    """

    def test_contract_canonical_digest_is_frozen(self, contract) -> None:
        assert contract.canonical_sha256 == _FROZEN_DIGESTS["contract"]

    def test_instrumentation_digest_is_frozen(self) -> None:
        assert (
            canonical_digest(M.instrumentation_definition_payload())
            == _FROZEN_DIGESTS["instrumentation"]
        )

    def test_store_projection_digest_is_frozen(self, contract) -> None:
        projection = M.build_store_projection(
            json.dumps(_PROJECTION_FIXTURE), contract=contract
        )
        digest = canonical_digest(
            {
                key: [value.value, value.value_type, value.mode]
                for key, value in sorted(projection.values.items())
            }
        )
        assert digest == _FROZEN_DIGESTS["projection"]

    def test_provider_is_registered_in_the_platform_golden_gate(self) -> None:
        """h9 必须在平台级门的 `PROVIDERS` 登记表里（即便该门当前被 f1 卡住）。"""
        gate = (
            F.BACKEND / "scripts" / "check" / "check_sync_provider_golden_digest.py"
        ).read_text(encoding="utf-8")
        assert '("h9", "phase5_h9_lease_liabilities", "ADAPTER_ID", True, True)' in gate

    def test_the_platform_gate_f1_defect_status(self) -> None:
        """f1 的 `build_contract_payload()` 是否过得了 `parse_contract` —— 动态探测。

        🔴 **本判据设计为双向稳定**：
        * f1 仍坏 ⇒ `pytest.raises` 捕获 ContractSchemaError ⇒ 绿（如实登记阻塞源）
        * f1 被并发会话修好 ⇒ 不抛了 ⇒ 也绿（下面的 `else` 分支验证 h9 能跑）
        无论哪个状态都不红 —— 因为「f1 是否修好」不是 h9 的职责。
        """
        from app.services.workpaper_sync import phase5_f1_prepayment as F1
        from app.services.workpaper_sync.contracts import ContractSchemaError

        try:
            parse_contract(F1.build_contract_payload(), adapter_id=F1.ADAPTER_ID)
        except ContractSchemaError:
            pass  # f1 仍坏 —— 平台门仍被阻塞，h9 自带 digest 判据兜底
        # 无论 f1 状态如何，h9 自己必须通过
        parse_contract(M.build_contract_payload(), adapter_id=M.ADAPTER_ID)
