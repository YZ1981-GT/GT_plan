# -*- coding: utf-8 -*-
"""Task 40 离线守卫：简单 checklist Excel pilot 的选型、契约与 Property oracle 落点。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 40
Requirements: 3.7, 4.11, 6.8, 6.11, 12.1, 12.2, 12.10, 12.12, 14.1, 14.2
Properties: **P11 / P25 / P26 / P29 / P49 / P55 / P62 / P69**

═══ 这一半证的是「判据本身正确 + 契约真有来源」 ═══

`test_task40_simple_checklist_pilot_pg.py` 在真库上跑完整 run（发布四个 definition、
组 non-null bundle、逐场景 record、finalize）。本文件不连库，只证三件事：

1. **冻结的 entry 不是拍脑袋挑的**：三条必要条件在真实 manifest / 真实
   `wp_templates/_index.json` 上重新推导一遍（不是断言常量等于常量）。
2. **契约逐字段有来源**：每个 `source_ref` / `header_source_ref` 指向的单元格，用
   openpyxl 直读权威模板取出**真实文本/公式**再比对。这是"源侧推导期望值"而不是
   "用被测函数算期望值"（假绿第③源）。
3. **Property 11/25/26/29/49/55/62/69 的 oracle 各有落点**，且今天的判定态与
   `pilot_harness` 的封闭枚举一致。

═══ 反假绿 ═══

* 覆盖计数硬判据：受管字段 15 / editable 14 / protected 1 / 表头比对 15 次 /
  静态标签比对 6 次，全部 `> 0` 且等于真实模板事实（空集恒等价不算通过）。
* 双向锁：磁盘契约 ↔ 现算 payload（改任一侧都打红）。
* 顺序判据：`instrumentation` payload 不得含 `contract_`/`bundle_` 反向引用；
  `contract` payload 不得含 bundle 前向引用；两条都由真实 payload 现跑。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import pilot_simple_checklist as P  # noqa: E402
from app.services.workpaper_sync import pilot_harness as PH  # noqa: E402
from app.services.workpaper_sync.adapters import registry as RG  # noqa: E402
from app.services.workpaper_sync.contracts import (  # noqa: E402
    ContractError,
    FieldMode,
    available_contract_ids,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Capability,
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)

_MANIFEST_PATH = _BACKEND / "data" / "workpaper_sync_entry_manifest.json"
_TEMPLATE_INDEX = _BACKEND / "wp_templates" / "_index.json"


# ═══════════════════════════════════════════════════════════════════════════
# fixtures：真实 manifest / 真实权威模板（不手搓 xlsx）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def entry(manifest: dict[str, Any]) -> dict[str, Any]:
    return dict(manifest_entries_by_id(manifest)[P.PILOT_ENTRY_ID])


@pytest.fixture(scope="module")
def worksheet() -> Any:
    """openpyxl 直读权威模板的受管 sheet（源侧事实，用于推导期望值）。"""
    import openpyxl

    wb = openpyxl.load_workbook(P.authoritative_template_path(), data_only=False)
    return wb[P.MANAGED_SHEET]


@pytest.fixture(scope="module")
def contract() -> Any:
    return P.load_pilot_contract()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的 entry：三条必要条件在真实数据上重新推导
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenEntrySelection:
    def test_entry_is_frozen_from_the_source_backed_manifest(
        self, manifest: dict[str, Any]
    ) -> None:
        """选型必要条件由 `assert_pilot_entry_selectable` 在真实 manifest 上现推。"""
        got = P.assert_pilot_entry_selectable(manifest=manifest)
        assert got["entry_id"] == P.PILOT_ENTRY_ID

    def test_entry_is_in_the_harness_simple_checklist_candidate_set(
        self, manifest: dict[str, Any]
    ) -> None:
        """Property 49 的类边界由 harness 判定，不由本模块声明。"""
        assessment = PH.assess_pilot_classes(manifest=manifest)[
            PH.PilotClass.simple_checklist
        ]
        assert P.PILOT_ENTRY_ID in assessment.candidate_entry_ids
        # 候选集非空且远大于 1 —— 「唯一候选」会让第 ② 条必要条件变成空转。
        assert len(assessment.candidate_entry_ids) > 100, len(
            assessment.candidate_entry_ids
        )

    def test_entry_is_independent_and_not_a_parent_duplicate(
        self, entry: dict[str, Any]
    ) -> None:
        assert entry["independent_entry"] is True
        assert entry["parent_entry_id"] is None

    def test_wp_code_has_an_exact_template_in_the_authority_index(self) -> None:
        """零回退判据：wp_code 必须在 `wp_templates/_index.json` 里精确命中。"""
        index = json.loads(_TEMPLATE_INDEX.read_text(encoding="utf-8"))
        xlsx_codes = {
            str(row.get("wp_code") or "")
            for row in index["files"]
            if str(row["relative_path"]).lower().endswith(".xlsx")
        }
        assert P.PILOT_WP_CODES & xlsx_codes, sorted(P.PILOT_WP_CODES)

    def test_runtime_finder_resolves_to_the_frozen_template(self) -> None:
        """运行时权威解析（`wp_template_finder`）必须落在冻结的那份模板上。

        这条是「零回退」的**行为**判据：只比 wp_code 集合还不够，
        `find_template_file()` 的模糊/回退分支可能把它解析到父级程序表。
        """
        from app.services.wp_template_finder import find_template_file

        resolved = {
            code: find_template_file(code) for code in sorted(P.PILOT_WP_CODES)
        }
        hits = {
            code: path
            for code, path in resolved.items()
            if path is not None
            and path.resolve() == P.authoritative_template_path().resolve()
        }
        assert hits, f"没有一个 wp_code 解析到冻结模板，实得 {resolved}"

    def test_selection_fails_closed_when_the_entry_disappears(
        self, manifest: dict[str, Any]
    ) -> None:
        payload = {
            **manifest,
            "entries": [
                e for e in manifest["entries"] if e["entry_id"] != P.PILOT_ENTRY_ID
            ],
        }
        with pytest.raises(P.PilotSelectionError, match="不在 source-backed manifest"):
            P.assert_pilot_entry_selectable(manifest=payload)

    def test_selection_fails_closed_when_no_template_wp_code_matches(
        self, manifest: dict[str, Any]
    ) -> None:
        """索引里没有该码 ⇒ 只能回退到父表 ⇒ 禁止发布契约。"""
        with pytest.raises(P.PilotSelectionError, match="回退到父级程序表"):
            P.assert_pilot_entry_selectable(
                manifest=manifest, template_wp_codes=["ZZZ-NOPE"]
            )

    def test_selection_fails_closed_on_parent_duplicate(
        self, manifest: dict[str, Any]
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["independent_entry"] = False
                item["parent_entry_id"] = "xlsx/gt-d4-operating-revenue"
        with pytest.raises(P.PilotSelectionError, match="independent_entry"):
            P.assert_pilot_entry_selectable(manifest=patched)

    def test_selection_fails_closed_on_wp_code_drift(
        self, manifest: dict[str, Any]
    ) -> None:
        patched = json.loads(json.dumps(manifest))
        for item in patched["entries"]:
            if item["entry_id"] == P.PILOT_ENTRY_ID:
                item["wp_match"]["wp_code_patterns"] = ["B60"]
        with pytest.raises(P.PilotSelectionError, match="wp_code_patterns"):
            P.assert_pilot_entry_selectable(manifest=patched)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板只认 backend/wp_templates/ 且字节不变
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthoritativeTemplate:
    def test_template_bytes_are_unchanged(self) -> None:
        """跑完本文件 `backend/wp_templates/` 必须原样（Requirement 9.9）。"""
        data = P.read_authoritative_template()
        assert hashlib.sha256(data).hexdigest() == P.TEMPLATE_SHA256

    def test_template_lives_under_the_authority_root(self) -> None:
        path = P.authoritative_template_path()
        assert path.is_file()
        assert path.resolve().is_relative_to((_BACKEND / "wp_templates").resolve())

    def test_reference_copy_is_never_read(self) -> None:
        """参考副本（`基础数据/致同通用审计程序及底稿模板…`）不得进入**代码**路径。

        🔴 判据必须剥掉 docstring/注释：本模块的 docstring 刻意写明「一次都不读它」，
        纯词面搜索会把这句说明本身判成违规（词面搜索的经典假阳性）。判据落在
        AST 的**非 docstring 字符串常量** + 真实文件读取调用上。
        """
        import ast

        source = (
            _BACKEND / "app" / "services" / "workpaper_sync" / "pilot_simple_checklist.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                first = (node.body or [None])[0]
                if (
                    isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)
                ):
                    docstrings.add(id(first.value))
        literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ]
        assert literals, "AST 判据自身失效：没有采到任何非 docstring 字符串常量"
        offenders = [text for text in literals if "基础数据" in text or "致同通用审计程序" in text]
        assert not offenders, (
            f"生产模块的代码字面量引用了已落后的参考副本: {offenders} —— "
            "权威载体只认 backend/wp_templates/"
        )
        # 正向：权威根确实出现在代码字面量里（否则上面这条是空集恒真）。
        assert any("wp_templates" in text for text in literals)

    def test_managed_sheet_exists_and_siblings_are_not_declared(
        self, worksheet: Any, contract: Any
    ) -> None:
        """受管 sheet 是真实 tab；契约只声明它一张（`managed_tables_of` fail closed）。"""
        assert worksheet.title == P.MANAGED_SHEET
        assert [sheet.excel_name for sheet in contract.sheets] == [P.MANAGED_SHEET]

    def test_template_sentinel_rejects_a_mutated_workbook(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """哨兵不是装饰：字节变了必须抛（反向自检）。"""
        fake = tmp_path / "mutated.xlsx"
        fake.write_bytes(P.read_authoritative_template() + b"\x00")
        monkeypatch.setattr(P, "authoritative_template_path", lambda: fake)
        with pytest.raises(P.PilotSelectionError, match="权威模板字节已变"):
            P.read_authoritative_template()


# ═══════════════════════════════════════════════════════════════════════════
# 3. 契约逐字段有来源（期望值从源侧 openpyxl 直读推导）
# ═══════════════════════════════════════════════════════════════════════════

_SRC_RE = re.compile(r"^源xlsx!(?P<sheet>[^!]+)!(?P<cell>[A-Z]+\d+)$")


def _cell_ref(source_ref: str) -> tuple[str, str]:
    match = _SRC_RE.match(source_ref)
    assert match is not None, f"source_ref 形态非法: {source_ref!r}"
    return match.group("sheet"), match.group("cell")


class TestContractIsGroundedInTheTemplate:
    def test_disk_contract_matches_the_source_of_truth(self) -> None:
        """磁盘契约 ↔ 现算 payload 双向锁死。"""
        assert P.assert_contract_file_matches_source().contract_id == P.PILOT_ADAPTER_ID

    def test_contract_is_registered_in_the_delivery_ledger(self) -> None:
        ledger = {row["contract_id"]: row for row in RG.DELIVERED_PER_ENTRY_CONTRACTS}
        assert P.PILOT_ADAPTER_ID in ledger
        row = ledger[P.PILOT_ADAPTER_ID]
        assert row["entry_id"] == P.PILOT_ENTRY_ID
        assert row["pilot_class"] == P.PILOT_CLASS
        assert row["template_relative_path"] == P.TEMPLATE_RELATIVE_PATH
        assert P.PILOT_ADAPTER_ID in available_contract_ids()

    def test_field_counts_are_the_real_template_facts(self, contract: Any) -> None:
        """覆盖计数硬判据（空集恒等价不算通过）。"""
        assert len(contract.all_fields()) == len(P.MANAGED_FIELD_SPECS) + len(
            P.META_FIELD_SPECS
        ) == 15
        assert len(contract.editable_field_keys()) == 14
        assert len(contract.protected_field_keys()) == 1

    def test_every_managed_header_matches_the_real_cell_text(
        self, contract: Any, worksheet: Any
    ) -> None:
        """行域字段的 `header_source_ref` 指向的单元格文本 == 登记的表头 label。"""
        by_column_key = {
            spec[0]: spec for spec in P.MANAGED_FIELD_SPECS
        }
        compared = 0
        table = next(t for t in contract.sheets[0].tables if t.table_key == P.ROWS_TABLE_KEY)
        payload_fields = {
            field["column_key"]: field
            for field in contract.canonical_payload["sheets"][0]["tables"][0]["fields"]
        }
        assert len(table.fields) == len(P.MANAGED_FIELD_SPECS)
        for field in table.fields:
            column_key = field.column_key
            assert column_key in by_column_key, column_key
            _key, column, mode, value_type, header_cell, label = by_column_key[column_key]
            # 列标/模式/类型三向与登记表一致
            assert field.cell is not None and field.cell.column == column
            assert field.mode.value == mode and field.value_type.value == value_type
            # 表头文本来自源侧
            sheet_name, cell = _cell_ref(payload_fields[column_key]["header_source_ref"])
            assert sheet_name == P.MANAGED_SHEET
            assert cell == header_cell
            assert str(worksheet[cell].value).strip() == label, (
                f"{column_key}: 权威模板 {cell} 实测 {worksheet[cell].value!r}，"
                f"契约登记 {label!r}"
            )
            compared += 1
        assert compared == 9, compared

    def test_every_meta_label_matches_the_real_cell_text(
        self, contract: Any, worksheet: Any
    ) -> None:
        payload_fields = {
            field["column_key"]: field
            for field in contract.canonical_payload["sheets"][0]["tables"][1]["fields"]
        }
        compared = 0
        for column_key, label_cell, value_col, row, label in P.META_FIELD_SPECS:
            sheet_name, cell = _cell_ref(payload_fields[column_key]["header_source_ref"])
            assert sheet_name == P.MANAGED_SHEET and cell == label_cell
            assert str(worksheet[cell].value).strip() == label, (
                f"{column_key}: {cell} 实测 {worksheet[cell].value!r} != {label!r}"
            )
            _s, value_ref = _cell_ref(payload_fields[column_key]["source_ref"])
            assert value_ref == f"{value_col}{row}"
            compared += 1
        assert compared == 6, compared

    def test_formula_column_is_really_a_formula_in_the_template(
        self, contract: Any, worksheet: Any
    ) -> None:
        """`mode=formula` 的列在权威模板里必须**真的**是公式，且逐行形态一致。"""
        protected = contract.protected_field_keys()
        assert len(protected) == 1
        spec = contract.field_by_stable_key(protected[0])
        assert spec.mode is FieldMode.formula and spec.cell is not None
        column = spec.cell.column
        seen = 0
        for row in range(P.FIRST_DATA_ROW, P.LAST_DATA_ROW + 1):
            value = worksheet[f"{column}{row}"].value
            assert isinstance(value, str) and value.startswith("="), (
                f"{column}{row} 实测 {value!r} —— 契约声明它是 formula"
            )
            assert value.replace(" ", "") == f"=(C{row}+D{row})*E{row}", value
            seen += 1
        assert seen == P.LAST_DATA_ROW - P.FIRST_DATA_ROW + 1 == 17

    def test_formula_mask_covers_the_formula_column(self, contract: Any) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.ROWS_TABLE_KEY
        )
        assert table.formula_mask == P.FORMULA_MASK
        assert table.two_level_header is True and table.header_rows == 2

    def test_footer_marker_is_the_real_cell_text(self, worksheet: Any, contract: Any) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.ROWS_TABLE_KEY
        )
        assert table.footer_anchor is not None
        assert table.footer_anchor.search_column == "A"
        assert (
            str(worksheet[f"A{P.FOOTER_ROW}"].value).strip()
            == table.footer_anchor.marker
            == P.FOOTER_MARKER
        )

    def test_header_rows_are_two_level_in_the_template(self, worksheet: Any) -> None:
        """`header_rows=2` 不是猜的：第 6 行确有二级表头文本，第 5 行有合并列组。"""
        second_level = [
            worksheet[f"{col}{P.HEADER_FIRST_ROW + 1}"].value for col in ("C", "D", "G", "H")
        ]
        assert all(isinstance(v, str) and v.strip() for v in second_level), second_level
        merged = {str(rng) for rng in worksheet.merged_cells.ranges}
        assert {"C5:D5", "G5:H5"} <= merged, sorted(merged)

    def test_row_identity_is_not_positional(self, contract: Any) -> None:
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.ROWS_TABLE_KEY
        )
        assert table.row_identity is not None
        assert table.row_identity.kind.value == "field"
        assert table.row_identity.json_pointer == "/rows/*/rowUuid"
        assert table.delete_policy is not None and table.delete_policy.value == "tombstone"

    def test_contract_declares_no_metadata_sheet(self, contract: Any) -> None:
        from app.services.workpaper_sync.excel_entry_gate import (
            assert_contract_declares_no_metadata_sheet,
        )

        assert_contract_declares_no_metadata_sheet(contract)

    def test_uuid_column_sits_right_of_the_managed_business_columns(
        self, contract: Any
    ) -> None:
        """隐藏 UUID 列必须严格落在受管业务列**右侧**（Requirement 6.13）。

        🔴 期望值取自**磁盘契约的真实列集合**，不是 `P.MANAGED_LAST_COL` 自己。
        变异检验实测：原来的 `spec.uuid_col == P.UUID_COL` /
        `spec.managed_last_col == P.MANAGED_LAST_COL` 两条是自证式同义反复
        （两侧都读同一个常量，改常量两侧同时变），真正抓住 `UUID_COL="H"` 的是
        Task 17 `ExcelInstrumentationSpec` 的构造期校验 —— 那条判据不在本测试里。
        """
        table = next(
            t for t in contract.sheets[0].tables if t.table_key == P.ROWS_TABLE_KEY
        )
        columns = sorted(
            {f.cell.column for f in table.fields if f.cell is not None and f.cell.column}
        )
        assert columns == list("ABCDEFGHI"), columns
        spec = P.instrumentation_spec()
        assert spec.managed_last_col == columns[-1]
        assert spec.uuid_col > columns[-1], (spec.uuid_col, columns[-1])
        assert spec.footer_row > spec.last_data_row
        assert spec.row_count == 17

    def test_mutated_contract_payload_is_rejected(self) -> None:
        """反向自检：把 formula 字段挪出 formula_mask 必须被 parse_contract 拒。"""
        payload = json.loads(json.dumps(P.build_contract_payload()))
        payload["sheets"][0]["tables"][0]["formula_mask"] = ["Z7:Z23"]
        with pytest.raises(ContractError, match="formula_mask"):
            parse_contract(payload, adapter_id=P.PILOT_ADAPTER_ID)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 发布顺序单向（真实 payload 现跑，不是文档承诺）
# ═══════════════════════════════════════════════════════════════════════════


class TestPublishDagIsOneWay:
    def test_template_payload_has_no_self_or_forward_reference(self) -> None:
        from app.services.workpaper_sync.definitions import validate_template_payload

        payload = P.template_definition_payload()
        validate_template_payload(payload)
        assert payload["template_sha256"] == P.TEMPLATE_SHA256
        assert payload["authority_root"] == "backend/wp_templates"

    def test_instrumentation_payload_references_template_only(self) -> None:
        from app.services.workpaper_sync.definitions import (
            validate_instrumentation_payload,
        )

        payload = P.instrumentation_definition_payload()
        validate_instrumentation_payload(payload)
        assert payload["template_definition_sha256"] == canonical_digest(
            P.template_definition_payload()
        )
        blob = json.dumps(payload, ensure_ascii=False)
        assert '"contract_' not in blob and '"bundle_' not in blob

    def test_contract_payload_references_both_and_no_bundle(self, contract: Any) -> None:
        from app.services.workpaper_sync.definitions import validate_contract_payload

        payload = dict(contract.canonical_payload)
        validate_contract_payload(payload)
        assert payload["template_definition_sha256"] == canonical_digest(
            P.template_definition_payload()
        )
        assert payload["instrumentation_definition_sha256"] == canonical_digest(
            P.instrumentation_definition_payload()
        )
        blob = json.dumps(payload, ensure_ascii=False)
        assert '"definition_bundle_' not in blob and '"bundle_' not in blob

    def test_authority_model_is_projection_contract(self) -> None:
        from app.services.workpaper_sync.definitions import (
            validate_authority_model_payload,
        )

        model = validate_authority_model_payload(P.authority_model_payload())
        assert model is P.AUTHORITY_MODEL
        assert model.value == "projection_contract"

    def test_instrumentation_sheet_key_matches_the_contract(self, contract: Any) -> None:
        """instrumentation payload 的 sheet_key 必须与契约的 sheet_key 同一个值。"""
        payload = P.instrumentation_definition_payload()
        assert payload["managed_sheets"][0]["sheet_key"] == P.SHEET_KEY
        assert contract.sheets[0].sheet_key == P.SHEET_KEY

    def test_instrumentation_declares_no_disproved_anchor(self) -> None:
        payload = json.dumps(P.instrumentation_definition_payload(), ensure_ascii=False)
        for anchor in ("sheet_id", "sheet_display_name"):
            assert f'"anchor": "{anchor}"' not in payload, anchor


# ═══════════════════════════════════════════════════════════════════════════
# 5. Property oracle 落点（P11 / P25 / P26 / P29 / P49 / P55 / P62 / P69）
# ═══════════════════════════════════════════════════════════════════════════

#: 本任务要验的 8 条 Property → 它在 harness required scenario set 里的落点场景。
PROPERTY_ORACLE_LANDING: dict[str, tuple[str, ...]] = {
    "P11": ("html_to_oo",),
    "P25": ("different_field_merge",),
    "P26": ("same_field_conflict_resolve",),
    "P29": ("oo_to_html",),
    "P49": ("identity_retention",),
    "P55": ("html_to_oo", "oo_to_html"),
    "P62": ("refresh_required_reopen",),
    "P69": ("single_participant_close",),
}


class TestPropertyOracleLanding:
    def test_every_property_lands_on_a_registered_oracle(self) -> None:
        """八条 Property 各有 oracle，**且**该 oracle 真的在本 entry 的 required set 里。

        只查「oracle 登记表里有这个 id」不够：一条全平台登记、但本 pilot 的 required set
        里根本不包含的场景，等于这条 Property 在本 entry 上从未被跑到（分母不含它）。
        """
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        required = set(
            derive_for_manifest_entry(
                entry, authority_model=P.AUTHORITY_MODEL
            ).scenario_ids
        )
        assert len(PROPERTY_ORACLE_LANDING) == 8, sorted(PROPERTY_ORACLE_LANDING)
        for prop, scenarios in sorted(PROPERTY_ORACLE_LANDING.items()):
            assert scenarios, prop
            for scenario_id in scenarios:
                assert scenario_id in PH.SCENARIO_ORACLES, (prop, scenario_id)
                assert scenario_id in required, (prop, scenario_id)

    def test_field_level_properties_are_not_substituted_away(self) -> None:
        """`projection_contract` ⇒ AC 12.12 的字段级两场景**不得**被替换。"""
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        required = derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL)
        ids = set(required.scenario_ids)
        assert "different_field_merge" in ids
        assert "same_field_conflict_resolve" in ids
        assert "authoritative_revision_conflict" not in ids
        assert "no_silent_overwrite" not in ids

    def test_required_scenario_set_is_the_shared_editable_standard(self) -> None:
        from app.services.workpaper_sync.evidence import derive_for_manifest_entry

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        required = derive_for_manifest_entry(entry, authority_model=P.AUTHORITY_MODEL)
        assert required.editability.value == "editable"
        assert required.room_model.value == "shared"
        assert required.close_required is True
        # 空集 fail closed 的另一半：分母必须非空且覆盖八条无条件族。
        PH.assert_required_set_non_empty(required)
        ids = set(required.scenario_ids)
        for scenario_id in (
            "html_to_oo",
            "oo_to_html",
            "identity_retention",
            "frozen_base_status_6_2_dedupe",
            "refresh_required_reopen",
            "rollback",
            "download_only_zero_three_entities",
            "single_participant_close",
        ):
            assert scenario_id in ids, scenario_id

    def test_black_box_properties_are_unverifiable_without_real_onlyoffice(self) -> None:
        """P11/P29/P49/P55/P62 的 oracle 都需要真实 OO/浏览器 ⇒ 今天只能 UNVERIFIABLE。"""
        need_black_box = {
            scenario_id
            for scenarios in PROPERTY_ORACLE_LANDING.values()
            for scenario_id in scenarios
        }
        offline_only = {"different_field_merge", "same_field_conflict_resolve",
                        "single_participant_close"}
        for scenario_id in sorted(need_black_box - offline_only):
            assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id

    def test_pilot_class_stays_unverifiable_until_server_recompute(self) -> None:
        """Property 49 的后半句：文档声明不得计为通过。"""
        assessment = PH.assess_pilot_classes()[PH.PilotClass.simple_checklist]
        assert assessment.status is PH.PilotClassStatus.unverifiable
        assert assessment.verified_entry_ids == ()
        assert PH.pilot_coverage_summary()["all_verified"] is False


# ═══════════════════════════════════════════════════════════════════════════
# 6. 顺序门：finalize 之前不得注册 adapter / 启用 capability
# ═══════════════════════════════════════════════════════════════════════════


class TestOrderingGate:
    def test_capability_is_not_enabled_before_finalize(self) -> None:
        """任务正文：finalize 成 published representation 后**方可**启用 capability。

        Task 75 已交付该 finalize 缺的公共观测器；今天挡住它的是**供给**（approved
        bundle / published representation / entry_state 三表实测 0 行，生产侧 provisioner
        是 Task 76 的交付）。所以
        manifest capability 必须仍是 `single_onlyoffice` —— 提前改成 bidirectional
        就是跳过顺序（manifest 宣称双向，registry 里一个 adapter 都没有）。
        """
        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        assert capability_of(entry) is Capability.single_onlyoffice
        assert entry["adapter_id"] is None
        with pytest.raises(P.PilotSelectionError, match="manifest capability"):
            P.assert_manifest_capability_enabled()

    def test_published_identity_observer_debt_is_cleared_by_task75(self) -> None:
        """Task 75 已交付公共观测器 ⇒ 本 pilot 的那条欠账登记必须**已删**且函数是真实现。

        判据三条，逐条可打红：① 模块不再导出该常量、源码零出现；② `resolve_published_
        frozen_definitions()` 顶层没有 `raise`（不是「删了登记却仍 fail closed」）；
        ③ 它真的 `await` 了共享观测器（AST 判据，不是字符串出现即算）。
        """
        import ast
        import inspect

        name = "UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER"
        assert not hasattr(P, name)
        assert name not in (P.__all__ or ())
        source = Path(inspect.getsourcefile(P) or "").read_text(encoding="utf-8")
        assert name not in source
        node = next(
            n
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "resolve_published_frozen_definitions"
        )
        assert [s for s in node.body if isinstance(s, ast.Raise)] == [], (
            "欠账登记删了但函数顶层仍 raise ⇒ 中间形态①"
        )
        awaited = {
            inner.value.func.id
            for inner in ast.walk(node)
            if isinstance(inner, ast.Await)
            and isinstance(inner.value, ast.Call)
            and isinstance(inner.value.func, ast.Name)
        }
        assert "observe_published_frozen_definitions" in awaited, sorted(awaited)

    def test_ledger_records_adapter_not_registered_yet(self) -> None:
        row = next(
            r
            for r in RG.DELIVERED_PER_ENTRY_CONTRACTS
            if r["contract_id"] == P.PILOT_ADAPTER_ID
        )
        assert row["adapter_registered"] is False
        assert "方可注册 adapter" in row["reason"]

    def test_contract_orphan_is_visible_in_the_registry_report(self) -> None:
        """契约有了但 adapter 没注册 ⇒ 必须作为**可见欠账**报出来（不是静默）。"""
        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        report = registry.build_report(contract_ids=available_contract_ids())
        assert P.PILOT_ADAPTER_ID in report.contract_files_without_adapter
        assert report.closed is False

    def test_registration_is_refused_while_manifest_says_single_onlyoffice(self) -> None:
        """capability 未启用时注册必须被拒 —— 且拒的是 **RG-16** 而不是 RG-18。

        🔴 判定顺序不可交换（`registry.register()` 的 ③ profile 先于 ④ 伪双向）：
        本 entry 的宿主**实测**已暴露模式切换 ⇒ descriptor mode 事实 = bidirectional，
        与 manifest 的 `single_onlyoffice` 直接矛盾，于是 RG-16 先打红。断言成
        `FakeBidirectionalError` 会是错的期望值（守卫把错值当基线 = 假绿第③源）；
        断成"抛了任意异常"又会让顺序变化不可见。
        """

        class _Adapter:
            adapter_id = P.PILOT_ADAPTER_ID
            document_type = "xlsx"
            contract_version = "1.0.0"

            async def read_current_projection(self, ctx: Any) -> Any: ...
            async def stage_projection_mutation(self, ctx: Any, merged: Any, **kw: Any) -> Any: ...
            def materialize(self, **kw: Any) -> Any: ...
            def extract(self, **kw: Any) -> Any: ...
            def verify_unmanaged_regions(self, **kw: Any) -> Any: ...

        from app.services.workpaper_sync.entry_profile import EntryProfileDriftError

        registry = RG.WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        with pytest.raises(EntryProfileDriftError, match="descriptor mode=bidirectional"):
            P.register_pilot_adapter(
                registry,
                adapter=_Adapter(),
                bundle=object(),
                descriptor=_descriptor_facts(),
                room=_room_facts(),
                contract=P.load_pilot_contract(),
            )
        assert registry.registrations() == (), "被拒的注册不得留下半成品"

    def test_capability_enable_would_clear_the_existing_rg16_drift(self) -> None:
        """把 capability 改成 bidirectional 是**消除**既有 RG-16 漂移，不是放宽判据。

        这条把「为什么本 pilot 选它」写成可执行事实：同一 profile 在
        `single_onlyoffice` 下 RG-16 打红、在 `bidirectional` 下三条 profile 判据全过。
        """
        from app.services.workpaper_sync.entry_profile import (
            assert_profile_consistent_with_capability,
            assert_profile_consistent_with_descriptor,
            assert_profile_consistent_with_room,
            extract_entry_profile,
        )

        entry = manifest_entries_by_id(load_entry_manifest())[P.PILOT_ENTRY_ID]
        profile = extract_entry_profile(entry)
        assert_profile_consistent_with_capability(profile, Capability.bidirectional)
        assert_profile_consistent_with_descriptor(
            profile, Capability.bidirectional, _descriptor_facts()
        )
        assert_profile_consistent_with_room(profile, _room_facts())


def _descriptor_facts() -> Any:
    from app.services.workpaper_sync.entry_profile import DescriptorFacts, DescriptorMode

    return DescriptorFacts(mode=DescriptorMode.bidirectional, exposes_mode_switch=True)


def _room_facts() -> Any:
    from app.services.workpaper_sync.entry_profile import RoomFacts

    return RoomFacts(shared_doc_key=True, doc_key_includes_mtime=False, participant_lease=True)


# ═══════════════════════════════════════════════════════════════════════════
# 7. 生产接线（非 additive 死代码）
# ═══════════════════════════════════════════════════════════════════════════

_ROUTER = _BACKEND / "app" / "routers" / "wp_sync_router.py"


class TestProductionWiring:
    def test_router_calls_attach_pilot_adapters_on_both_paths(self) -> None:
        """两个生产接线点都必须真的调用 attach（AST 判据，不是字符串出现即算）。

        `_registration` 是 HTML→OO 的解析入口，`_apply_durable_incoming` 是 callback
        之后的 apply 入口。只接一侧会形成「能打开 OO、回写找不到 adapter」的半接线。
        """
        import ast

        tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
        called_in: dict[str, bool] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in {"_attach_pilot_adapters", "_apply_durable_incoming"}:
                continue
            called_in[node.name] = any(
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "attach_pilot_adapters"
                for inner in ast.walk(node)
            )
        assert called_in.get("_attach_pilot_adapters") is True
        assert called_in.get("_apply_durable_incoming") is True

    def test_registration_helper_awaits_the_attach(self) -> None:
        import ast

        tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
        fn = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_registration"
        )
        awaited = {
            inner.value.func.id
            for inner in ast.walk(fn)
            if isinstance(inner, ast.Await)
            and isinstance(inner.value, ast.Call)
            and isinstance(inner.value.func, ast.Name)
        }
        assert "_attach_pilot_adapters" in awaited

    def test_both_production_paths_go_through_the_bidirectional_contract_lock(self) -> None:
        """发布与接线**都**必须经 `assert_contract_file_matches_source()` 取契约。

        🔴 变异检验实测（M26）：把 `publish_pilot_definitions()` 里的
        `assert_contract_file_matches_source()` 换成 `load_pilot_contract()` 之后
        **82 例全绿** —— 因为 `test_disk_contract_matches_the_source_of_truth` 是自己直接
        调那把锁，从不检查生产路径用的是哪一个。判据与生产路径脱钩 = 一份被手改过的
        契约可以照常发布，而"双向锁"只在守卫里成立。
        """
        import ast

        tree = ast.parse(Path(P.__file__).read_text(encoding="utf-8"))
        sources: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in {"publish_pilot_definitions", "attach_pilot_adapters"}:
                continue
            sources[node.name] = {
                inner.func.id
                for inner in ast.walk(node)
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            }
        assert set(sources) == {"publish_pilot_definitions", "attach_pilot_adapters"}, sources
        for name, calls in sorted(sources.items()):
            assert "assert_contract_file_matches_source" in calls, (name, sorted(calls))
            assert "load_pilot_contract" not in calls, (
                f"{name} 直接读磁盘契约 —— 生产路径必须走双向锁，"
                "只读磁盘会让「改契约不改代码」悄悄通过"
            )

    def test_resolve_published_definitions_never_returns_none(self) -> None:
        """找不到载体必须抛可分辨异常，绝不返回 None（fail-open 是最贵的一类缺陷）。

        Task 75 起抛的是观测器的 `RepresentationShapeError`（「representation 为空 ⇒ 无法确定
        project scope」），而不是原先那条欠账 `PilotSelectionError`。意图一字不改：**不返回
        None、不返回空 identity**。
        """
        import asyncio

        from app.services.workpaper_sync.published_identity_observer import (
            RepresentationShapeError,
        )

        with pytest.raises(RepresentationShapeError):
            asyncio.run(
                P.resolve_published_frozen_definitions(
                    session=None, representation=None, contract=P.load_pilot_contract()
                )
            )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 本 pilot 不得给 writer/resolver 清册增债（Requirement 9.11 / Task 19-20 收口门）
# ═══════════════════════════════════════════════════════════════════════════

_GENERATOR_PATH = _REPO / "backend" / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
_INVENTORY_PATH = _BACKEND / "data" / "workpaper_writer_inventory.json"
_OVERLAY_PATH = _BACKEND / "data" / "workpaper_writer_domain_overlay.json"

#: 被裁决掉的那一条 ad-hoc 路径拼接的**原始形态**（反向自检的输入，不是文档说明）。
_RETIRED_AD_HOC_PATH_SHAPE = '    index_path = _BACKEND_ROOT / "wp_templates" / "_index.json"'


@pytest.fixture(scope="module")
def inventory_generator() -> Any:
    """Task 19 清册生成器本体 —— 判据必须用**它的**分类谓词，不是本文件重写一份。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("_t40_wp_inv_gen", _GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPilotIntroducesNoResolverDebt:
    """本模块每个函数在**真实分类器**下都不得被判成 writer / resolver。

    为什么这条必须存在：`_template_index_wp_codes()` 原来自己拼
    ``_BACKEND_ROOT / "wp_templates" / "_index.json"``，于是被 Task 19 的 AST 分类器
    记成一条 `<ad_hoc_path_construction>` resolver，同时命中
    `unadjudicated_resolver` 与 `non_canonical_resolver_only` 两条 blocking fact。
    改成取 `wp_template_finder.INDEX_FILE` 之后欠账归零，但**如果没有这条守卫**，
    任何人（包括未来的自己）把路径拼回来都不会有任何判据打红 —— 收口门禁的数字
    要等下一次 `--apply` 重生成清册才会悄悄涨回去。
    """

    def test_no_function_in_this_module_is_classified_as_writer_or_resolver(
        self, inventory_generator: Any
    ) -> None:
        import ast

        module_path = Path(P.__file__)
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        classified: dict[str, str] = {}
        checked = 0
        for _parent, function in inventory_generator._iter_functions(tree):
            checked += 1
            facts = inventory_generator._collect_facts(function)
            kind = inventory_generator._classify(facts, delegates_to=[])
            if kind is not None:
                classified[function.name] = kind
        assert checked >= 20, f"只走到 {checked} 个函数 —— 遍历谓词失效，空集恒等价"
        assert classified == {}, (
            f"{module_path.name} 给 writer/resolver 清册增债：{classified} —— "
            "本模块只读权威模板与索引，不解析也不写底稿实体文件"
        )

    def test_the_generator_would_still_flag_the_retired_ad_hoc_path(
        self, inventory_generator: Any
    ) -> None:
        """反向自检：把旧形态喂回去必须仍被判成 resolver（否则上一条是空判据）。"""
        import ast
        import textwrap

        source = textwrap.dedent(
            f"""
            def _probe() -> set[str]:
                import json
            {_RETIRED_AD_HOC_PATH_SHAPE}
                return set(json.loads(index_path.read_text(encoding="utf-8")))
            """
        )
        function = ast.parse(source).body[0]
        facts = inventory_generator._collect_facts(function)
        assert facts.ad_hoc_paths, "旧形态不再被识别 ⇒ 上一条测试恒真"
        assert inventory_generator._classify(facts, delegates_to=[]) == "resolver"
        identities = inventory_generator._resolver_identities(facts.as_dict())
        assert identities == ["<ad_hoc_path_construction>"]
        assert "resolve_wp_file" not in identities, (
            "旧形态确实是 non_canonical_resolver_only 的那一类"
        )

    def test_index_path_comes_from_the_template_finder(self) -> None:
        """索引位置只有一个真源，且真读得出东西（不是只查符号出现）。"""
        from app.services.wp_template_finder import INDEX_FILE

        codes = P._template_index_wp_codes()
        assert INDEX_FILE.name == "_index.json"
        assert INDEX_FILE.is_file()
        assert len(codes) > 100, len(codes)
        assert "B60" in codes
        # 与本模块另一条真源（carrier gate 的 authority root）落在同一棵模板库下。
        assert INDEX_FILE.parent == P.authoritative_template_path().parent.parent

    def test_neither_overlay_bucket_carries_this_module(self) -> None:
        """裁决结论：不进 `adjudications`，也不进 `retired_adjudications`。

        `adjudications` 只清 `unadjudicated_resolver`，`non_canonical_resolver_only`
        是 AST 派生事实、盖 domain 标签清不掉；`retired_adjudications` 则被生成器的
        `_build_retired_writers()` 明文拒绝（"is discovered as a writer/resolver again"）——
        一个仍被发现的行不可能是"已退役"。两条路都不通，正确解法是让它不再被发现。
        """
        overlay = json.loads(_OVERLAY_PATH.read_text(encoding="utf-8"))
        for bucket in ("adjudications", "retired_adjudications"):
            offenders = [
                writer_id
                for writer_id in (overlay.get(bucket) or {})
                if "pilot_simple_checklist" in writer_id
            ]
            assert offenders == [], (bucket, offenders)

    def test_inventory_on_disk_has_no_row_for_this_module(self) -> None:
        inventory = json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))
        rows = [
            entry["writer_id"]
            for entry in inventory["entries"]
            if entry["module"] == P.__name__
        ]
        assert rows == [], rows
        retired = [
            item["writer_id"]
            for item in inventory.get("retired_writers") or []
            if "pilot_simple_checklist" in item["writer_id"]
        ]
        assert retired == [], retired
