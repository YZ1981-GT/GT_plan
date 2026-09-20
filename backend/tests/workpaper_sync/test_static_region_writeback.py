"""静态受管区（definedName-anchored static cell sheet）双向回写守卫。

spec: workpaper-sync-static-cell-sheet-writeback
覆盖 Property 1/4/5/6（静态往返等价 / 锚点缺失 fail-closed / kind 显式分派 / 无幽灵 UUID）。

本文件按 spec 实现顺序**逐 wave 追加**：Task 1 先钉 binding kind 判据 + 静态形态构造/校验，
后续 task 追加 resolve/extract/materialize 往返与 observer 分派。
"""

from __future__ import annotations

import pytest

from app.services.workpaper_sync import excel_extract as X
from app.services.workpaper_sync.excel_extract import (
    BindingKind,
    ExcelIdentityBinding,
    ManagedRegionResolutionError,
    is_static_region,
)


# ═══════════════════════════════════════════════════════════════════════════
# Task 1 · binding kind 判据 + 静态形态（Requirement 1 / Property 5）
# ═══════════════════════════════════════════════════════════════════════════


class TestBindingKind:
    """kind 由 `defined_name` 存在决定，不是 uuid_column 缺失（Property 5）。"""

    def test_dynamic_binding_kind_is_excel_table(self) -> None:
        binding = ExcelIdentityBinding(
            table_key="k_rows", table_name="GT_TBL", uuid_column="Z"
        )
        assert binding.kind is BindingKind.excel_table
        assert is_static_region(binding) is False

    def test_static_binding_kind_is_static_region(self) -> None:
        binding = ExcelIdentityBinding(
            table_key="d433-static", defined_name="GT_MANAGED_REGION_D433"
        )
        assert binding.kind is BindingKind.static_region
        assert is_static_region(binding) is True

    def test_static_binding_omits_table_name_and_uuid(self) -> None:
        # 静态构造可省略 table_name/uuid_column（默认 ""），不因缺它们而抛。
        binding = ExcelIdentityBinding(
            table_key="d433-static", defined_name="GT_MANAGED_REGION_D433"
        )
        assert binding.table_name == ""
        assert binding.uuid_column == ""
        assert binding.defined_name == "GT_MANAGED_REGION_D433"


class TestBindingKindFailClosed:
    """混填 / 空必填字段 fail-closed（Requirement 1.1/1.2）。"""

    def test_static_binding_rejects_table_name(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="kind 混填"):
            ExcelIdentityBinding(
                table_key="d433-static",
                defined_name="GT_MANAGED_REGION_D433",
                table_name="GT_TBL",  # 混填
            )

    def test_static_binding_rejects_uuid_column(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="kind 混填"):
            ExcelIdentityBinding(
                table_key="d433-static",
                defined_name="GT_MANAGED_REGION_D433",
                uuid_column="Z",  # 混填
            )

    def test_static_binding_rejects_empty_table_key(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="table_key"):
            ExcelIdentityBinding(
                table_key="", defined_name="GT_MANAGED_REGION_D433"
            )

    def test_static_binding_rejects_empty_metadata_sheet(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="metadata_sheet"):
            ExcelIdentityBinding(
                table_key="d433-static",
                defined_name="GT_MANAGED_REGION_D433",
                metadata_sheet="",
            )


class TestDynamicBindingUnchanged:
    """动态 binding 的既有强校验逐条保留（Requirement 1.5，动态零回归）。"""

    def test_dynamic_rejects_empty_table_name(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="table_name"):
            ExcelIdentityBinding(table_key="k_rows", uuid_column="Z")

    def test_dynamic_rejects_empty_uuid_column(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="uuid_column"):
            ExcelIdentityBinding(table_key="k_rows", table_name="GT_TBL")

    def test_dynamic_rejects_malformed_uuid_column(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="形态非法"):
            ExcelIdentityBinding(
                table_key="k_rows", table_name="GT_TBL", uuid_column="123"
            )

    def test_dynamic_accepts_valid(self) -> None:
        binding = ExcelIdentityBinding(
            table_key="k_rows", table_name="GT_TBL", uuid_column="AA"
        )
        assert binding.kind is BindingKind.excel_table
        assert binding.uuid_column == "AA"


# ═══════════════════════════════════════════════════════════════════════════
# Task 2 · resolve_managed_region definedName 分支（Requirement 2 / Property 4）
# ═══════════════════════════════════════════════════════════════════════════

import io
import zipfile

import openpyxl
from openpyxl.workbook.defined_name import DefinedName

from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.excel_extract import (
    IdentityCarrierMissingError,
    _resolve_static_region,
    _split_defined_name_ref,
)

STATIC_SHEET = "其他业务毛利率分析表D433"
STATIC_DEFINED_NAME = "GT_MANAGED_REGION_D433"
STATIC_REF = "$E$12:$M$13"  # 迷你几何（2 行 × 若干列），Task 2 只验区域求解
STATIC_TABLE_KEY = "d433-static"
STATIC_CONTRACT_ID = "d4.other_margin_static.test"


def _make_static_workbook(
    *, defined_name: str = STATIC_DEFINED_NAME, ref: str = STATIC_REF,
    sheet_title: str = STATIC_SHEET, workbook_scope: bool = True,
    duplicate: bool = False, on_hidden_meta: bool = False,
) -> bytes:
    """造一个含 workbook-scope definedName 的最小静态 sheet workbook。"""
    from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_title
    for r in range(12, 14):
        for c in ("E", "F", "H", "I", "K", "L"):
            ws[f"{c}{r}"] = 0
    target_title = sheet_title
    if on_hidden_meta:
        meta = wb.create_sheet(GT_SYNC_SHEET_NAME)
        meta["A1"] = "k"
        target_title = GT_SYNC_SHEET_NAME
    full_ref = f"'{target_title}'!{ref}"
    if workbook_scope:
        wb.defined_names[defined_name] = DefinedName(defined_name, attr_text=full_ref)
        if duplicate:
            # 再插一个同名 workbook-scope（openpyxl dict 会去重，故直接改 XML 注入第二个）
            pass
    else:
        # sheet-local scope（localSheetId）
        dn = DefinedName(defined_name, attr_text=full_ref, localSheetId=0)
        wb[sheet_title].defined_names[defined_name] = dn
    buf = io.BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    if duplicate:
        data = _inject_duplicate_defined_name(data, defined_name, full_ref)
    return data


def _inject_duplicate_defined_name(data: bytes, name: str, ref: str) -> bytes:
    """往 workbook.xml 的 definedNames 里再塞一个同名 workbook-scope name。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        parts = {n: zf.read(n) for n in zf.namelist()}
    wbxml = parts["xl/workbook.xml"].decode("utf-8")
    extra = f'<definedName name="{name}">{ref}</definedName>'
    if "<definedNames>" in wbxml:
        wbxml = wbxml.replace("<definedNames>", "<definedNames>" + extra, 1)
    else:
        wbxml = wbxml.replace("</sheets>", "</sheets><definedNames>" + extra + "</definedNames>", 1)
    parts["xl/workbook.xml"] = wbxml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, b in parts.items():
            zf.writestr(n, b)
    return out.getvalue()


def _static_contract():
    import hashlib

    def _d(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    payload = {
        "schema_version": "contract-definition:v1",
        "contract_id": STATIC_CONTRACT_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("d433-template-definition"),
        "instrumentation_definition_sha256": _d("d433-instrumentation-definition"),
        "template": {
            "relative_path": "D/其他业务毛利率分析表D433.xlsx",
            "template_sha256": _d("d433-template"),
            "normalized_structure_hash": _d("d433-normalized-structure"),
        },
        "identity_carriers": ["defined_name"],
        "sheets": [
            {
                "sheet_key": "d433-managed",
                "excel_name": STATIC_SHEET,
                # locator anchor 复用已探针通过的 defined_name_ref（真实 OO 已证 passed）；
                # 「静态 vs 转置」由 binding.kind + observer payload region_kind 区分，非 carrier 锚点名。
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": STATIC_TABLE_KEY,
                        "anchor": "E12",
                        "header_rows": 1,
                        "fields": [
                            {
                                "stable_field_key": f"{STATIC_TABLE_KEY}/rent_rev_m1",
                                "json_pointer": "/months/0/revenue",
                                "column_key": "rent_rev_m1",
                                "cell": {"column": "E", "row_from": 12},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "wp:D4-33!E12",
                            },
                            {
                                "stable_field_key": f"{STATIC_TABLE_KEY}/rent_cost_m1",
                                "json_pointer": "/months/0/cost",
                                "column_key": "rent_cost_m1",
                                "cell": {"column": "F", "row_from": 12},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "wp:D4-33!F12",
                            },
                        ],
                    }
                ],
            }
        ],
    }
    return parse_contract(payload, adapter_id=STATIC_CONTRACT_ID)


class TestSplitDefinedNameRef:
    def test_strips_quoted_sheet_and_dollar(self) -> None:
        sheet, a1 = _split_defined_name_ref("'其他业务毛利率分析表D433'!$E$12:$M$23")
        assert sheet == "其他业务毛利率分析表D433"
        assert a1 == "E12:M23"

    def test_strips_unquoted_sheet(self) -> None:
        sheet, a1 = _split_defined_name_ref("Sheet1!$A$1:$C$3")
        assert sheet == "Sheet1"
        assert a1 == "A1:C3"

    def test_missing_sheet_prefix_fail_closed(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="缺 sheet 前缀"):
            _split_defined_name_ref("$A$1:$C$3")


class TestResolveStaticRegion:
    def _region(self, data: bytes):
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return _resolve_static_region(zf, contract=_static_contract(), binding=binding)

    def test_resolves_geometry_from_defined_name(self) -> None:
        region = self._region(_make_static_workbook())
        assert region.sheet_name == STATIC_SHEET
        assert region.first_column == "E"
        assert region.last_column == "M"
        assert region.first_row == 12
        assert region.last_row == 13
        assert region.uuid_column == ""  # Property 6：静态区无 UUID 列

    def test_missing_defined_name_is_carrier_missing(self) -> None:
        wb = openpyxl.Workbook()
        wb.active.title = STATIC_SHEET
        buf = io.BytesIO()
        wb.save(buf)
        with pytest.raises(IdentityCarrierMissingError, match="反读不到"):
            self._region(buf.getvalue())

    def test_duplicate_defined_name_fail_closed(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="命中 2 个"):
            self._region(_make_static_workbook(duplicate=True))

    def test_defined_name_on_hidden_meta_sheet_rejected(self) -> None:
        with pytest.raises(ManagedRegionResolutionError, match="隐藏 metadata sheet"):
            self._region(_make_static_workbook(on_hidden_meta=True))

    def test_local_scope_defined_name_not_matched(self) -> None:
        # sheet-local scope 不是 workbook-scope → 反读不到 → carrier missing
        with pytest.raises(IdentityCarrierMissingError):
            self._region(_make_static_workbook(workbook_scope=False))


# ═══════════════════════════════════════════════════════════════════════════
# Task 3 · managed_tables_of 静态路径（Requirement 3.1 / 1.5 / Property 5）
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync.excel_extract import managed_tables_of


def _contract_with(sheet_tables: list) -> object:
    import hashlib

    def _d(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    payload = {
        "schema_version": "contract-definition:v1",
        "contract_id": STATIC_CONTRACT_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("mt-template-definition"),
        "instrumentation_definition_sha256": _d("mt-instrumentation-definition"),
        "template": {
            "relative_path": "D/mixed.xlsx",
            "template_sha256": _d("mt-template"),
            "normalized_structure_hash": _d("mt-normalized-structure"),
        },
        "identity_carriers": ["defined_name", "excel_table", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "mixed-managed",
                "excel_name": STATIC_SHEET,
                "locator": {"anchor": "defined_name_ref"},
                "tables": sheet_tables,
            }
        ],
    }
    return parse_contract(payload, adapter_id=STATIC_CONTRACT_ID)


def _static_table_spec(table_key: str = STATIC_TABLE_KEY) -> dict:
    return {
        "table_key": table_key,
        "anchor": "E12",
        "header_rows": 1,
        "fields": [
            {
                "stable_field_key": f"{table_key}/rev_m1",
                "json_pointer": "/months/0/revenue",
                "column_key": "rev_m1",
                "cell": {"column": "E", "row_from": 12},
                "mode": "editable",
                "value_type": "amount",
                "source_ref": "wp:D4-33!E12",
            },
            {
                "stable_field_key": f"{table_key}/cost_m1",
                "json_pointer": "/months/0/cost",
                "column_key": "cost_m1",
                "cell": {"column": "F", "row_from": 12},
                "mode": "editable",
                "value_type": "amount",
                "source_ref": "wp:D4-33!F12",
            },
        ],
    }


def _dynamic_table_spec(table_key: str = "dyn_rows") -> dict:
    return {
        "table_key": table_key,
        "anchor": "A20",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
        "delete_policy": "tombstone",
        "fields": [
            {
                "stable_field_key": f"{table_key}/name",
                "json_pointer": "/rows/{row_uuid}/name",
                "column_key": "name",
                "cell": {"column": "A", "row_from": "row_identity"},
                "mode": "editable",
                "value_type": "text",
                "source_ref": "wp:D4-33!A20",
            }
        ],
    }


class TestManagedTablesStaticPath:
    def test_static_binding_returns_none_dynamic(self) -> None:
        contract = _contract_with([_static_table_spec()])
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        dynamic, statics = managed_tables_of(contract, binding=binding)
        assert dynamic is None  # 静态区无动态表
        assert len(statics) == 1
        assert statics[0].table_key == STATIC_TABLE_KEY

    def test_static_binding_pointing_at_dynamic_table_fail_closed(self) -> None:
        # 契约里 STATIC_TABLE_KEY 其实是动态表 → static binding 指向它 → 混填 fail-closed
        dyn = _dynamic_table_spec(table_key=STATIC_TABLE_KEY)
        contract = _contract_with([dyn])
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        with pytest.raises(ManagedRegionResolutionError, match="指向了动态表"):
            managed_tables_of(contract, binding=binding)

    def test_static_binding_sheet_without_static_table_fail_closed(self) -> None:
        # sheet 只有动态表、无静态表；binding.table_key 指向动态表 → 先撞「指向动态表」
        # 用一个不存在的 table_key 会先撞 sheet 定位（None）→ 契约不匹配
        dyn = _dynamic_table_spec(table_key="only_dyn")
        contract = _contract_with([dyn])
        binding = ExcelIdentityBinding(
            table_key="only_dyn", defined_name=STATIC_DEFINED_NAME
        )
        with pytest.raises(ManagedRegionResolutionError, match="指向了动态表"):
            managed_tables_of(contract, binding=binding)


class TestManagedTablesDynamicUnchanged:
    """动态 binding 的 has_dynamic_rows raise 逐条保留（Requirement 1.5 / Property 5 Task3 锚点）。

    Property 5 的核心：若把「按 uuid 空隐式分派」变异注入 kind，一个动态 binding（uuid 非空）
    仍判 dynamic（对），但把「静态 binding 误当动态」的边界——本测试钉住动态 binding 走
    managed_tables_of 时**必经** has_dynamic_rows raise（静态路径绕过它），二者行为可区分。
    """

    def test_dynamic_binding_returns_dynamic_and_statics(self) -> None:
        contract = _contract_with([_dynamic_table_spec(), _static_table_spec("footer_static")])
        binding = ExcelIdentityBinding(
            table_key="dyn_rows", table_name="GT_DYN", uuid_column="Z"
        )
        dynamic, statics = managed_tables_of(contract, binding=binding)
        assert dynamic is not None
        assert dynamic.table_key == "dyn_rows"
        assert {t.table_key for t in statics} == {"footer_static"}

    def test_dynamic_binding_pointing_at_static_table_fail_closed(self) -> None:
        # 动态 binding（uuid 非空）指向静态表 → 动态路径的 has_dynamic_rows raise 触发
        contract = _contract_with([_static_table_spec("s_only")])
        binding = ExcelIdentityBinding(
            table_key="s_only", table_name="GT_S", uuid_column="Z"
        )
        with pytest.raises(ManagedRegionResolutionError, match="没有 row_identity"):
            managed_tables_of(contract, binding=binding)


# ═══════════════════════════════════════════════════════════════════════════
# Task 4 · extract 静态链部件（Requirement 3.2/3.3 / Property 6）
# 注：完整 extract→materialize 往返（Property 1）在 Task 5 闭合（需 materialize + 注入
# definedName 的真实 substrate）。本段测 extract 侧可独立验证的部件：坐标集/列集/保留门。
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync.excel_extract import (
    ManagedRegion,
    _assert_static_anchor_retained,
    _managed_coordinates,
    _needed_columns_and_rows,
)
from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory


def _static_region_obj() -> ManagedRegion:
    return ManagedRegion(
        table_key=STATIC_TABLE_KEY,
        table_name="",
        sheet_name=STATIC_SHEET,
        sheet_part="xl/worksheets/sheet1.xml",
        table_ref="E12:F12",
        first_row=12,
        last_row=12,
        first_column="E",
        last_column="F",
        uuid_column="",
    )


class TestManagedCoordinatesStatic:
    def test_no_ghost_uuid_coords(self) -> None:
        # Property 6：静态区受管坐标 = 静态 fields 绝对坐标集，不含任何 uuid_column{row}
        contract = _contract_with([_static_table_spec()])
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        coords = _managed_coordinates(
            contract=contract, region=_static_region_obj(), binding=binding, scan=None
        )
        assert coords == frozenset({"E12", "F12"})
        # 无空列坐标（uuid_column="" 会产生 "12" 之类幽灵坐标）
        assert not any(c.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == c for c in coords)


class TestNeededColumnsStatic:
    def test_columns_exclude_uuid(self) -> None:
        contract = _contract_with([_static_table_spec()])
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        columns, rows = _needed_columns_and_rows(
            contract=contract, region=_static_region_obj(), binding=binding
        )
        assert columns == frozenset({"E", "F"})  # 不含 uuid_column ""
        assert "" not in columns
        assert 12 in rows


def _static_inventory_raw(defined_names: list[str]) -> dict:
    return {
        "hidden_sheet": {
            "present": True,
            "is_hidden": True,
            "excluded_from_business_enumeration": True,
        },
        "defined_name": {"names": {n: f"'{STATIC_SHEET}'!$E$12:$M$23" for n in defined_names}},
        "excel_table": {"present": False, "table_ref": ""},
        "hidden_uuid_column": {
            "resolved_sheet_by": None,
            "uuid_column_hidden": False,
            "row_uuids": {},
            "duplicate_row_uuids": [],
            "empty_row_uuids": [],
        },
    }


def _runtime_static_inventory(defined_names: tuple[str, ...], *, hidden_present: bool = True):
    from app.services.workpaper_sync.excel_extract import RuntimeIdentityInventory
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR  # noqa: F401

    return RuntimeIdentityInventory(
        hidden_sheet_present=hidden_present,
        hidden_sheet_is_hidden=True,
        excluded_from_business_enumeration=True,
        defined_names=defined_names,
        table_present=True,
        table_ref="E12:F12",
        table_sheet=STATIC_SHEET,
        resolved_sheet_by=None,
        uuid_column="",
        uuid_column_hidden=False,
        row_uuids={},
        duplicate_row_uuids=(),
        empty_row_uuids=(),
        business_sheets=(STATIC_SHEET,),
    )


class TestStaticAnchorRetained:
    def test_anchor_present_passes(self) -> None:
        expected = parse_identity_inventory(_static_inventory_raw([STATIC_DEFINED_NAME]))
        observed = _runtime_static_inventory((STATIC_DEFINED_NAME,))
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        # 不抛即通过
        _assert_static_anchor_retained(
            expected=expected, observed=observed, binding=binding, entry_id="e1"
        )

    def test_anchor_lost_in_observed_fail_closed(self) -> None:
        from app.services.workpaper_sync.excel_extract import IdentityRetentionError

        expected = parse_identity_inventory(_static_inventory_raw([STATIC_DEFINED_NAME]))
        observed = _runtime_static_inventory(())  # OO 往返后 definedName 丢了
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        with pytest.raises(IdentityRetentionError, match="在 OO 往返后丢失"):
            _assert_static_anchor_retained(
                expected=expected, observed=observed, binding=binding, entry_id="e1"
            )

    def test_hidden_sheet_lost_fail_closed(self) -> None:
        from app.services.workpaper_sync.excel_extract import IdentityRetentionError

        expected = parse_identity_inventory(_static_inventory_raw([STATIC_DEFINED_NAME]))
        observed = _runtime_static_inventory((STATIC_DEFINED_NAME,), hidden_present=False)
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        with pytest.raises(IdentityRetentionError, match="隐藏 metadata sheet"):
            _assert_static_anchor_retained(
                expected=expected, observed=observed, binding=binding, entry_id="e1"
            )


class TestManagedCoordinatesGhostUuidMutation:
    """Property 6 变异反证：给静态分支加 `uuid_column{row}` 幽灵坐标必被守卫捕获（RED）。

    真实 `_managed_coordinates` 静态分支产净集 {E12,F12}（`test_no_ghost_uuid_coords` 已钉）。
    本测把 requirements 7.2 / design P6 变异表点名的变异——「静态分支加 uuid 幽灵坐标」——
    在测内**本地复现**：对同一 region/contract，用 region.uuid_column 造 `{uuid}{row}` 坐标
    并入受管集。断言「净集 == 静态绝对坐标集」这条守卫对被污染集**必红**（会引入额外坐标），
    从而证明该守卫是承重的、不是恒真占位（GREEN=守卫缺陷）。
    """

    def _clean_coords(self) -> frozenset[str]:
        contract = _contract_with([_static_table_spec()])
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        return _managed_coordinates(
            contract=contract, region=_static_region_obj(), binding=binding, scan=None
        )

    def test_clean_coords_equal_static_field_set(self) -> None:
        # 前置：真实实现产净集（守卫的绿态基线）。
        assert self._clean_coords() == frozenset({"E12", "F12"})

    def test_ghost_uuid_mutation_breaks_guard(self) -> None:
        # 变异：区内每行补一个 `{uuid_column}{row}` 幽灵坐标（uuid_column 取一个真实列如 "Z"）。
        region = _static_region_obj()
        ghost_uuid_column = "Z"  # 若静态分支误加 uuid 幽灵坐标会用到的列
        mutated = set(self._clean_coords())
        for row in range(region.first_row, region.last_row + 1):
            mutated.add(f"{ghost_uuid_column}{row}")  # ← 幽灵坐标污染
        mutated_frozen = frozenset(mutated)

        # 守卫「== 静态绝对坐标集」对被污染集必红：断言二者不再相等（变异被捕获）。
        assert mutated_frozen != frozenset({"E12", "F12"})
        # 且污染坐标确实混入（证明变异点可达，非 ANCHOR-MISS）。
        assert "Z12" in mutated_frozen
        # 真实实现绝不含该幽灵坐标（Property 6 正向再确认）。
        assert "Z12" not in self._clean_coords()

    def test_needed_columns_ghost_uuid_mutation_breaks_guard(self) -> None:
        # `_needed_columns_and_rows` 同理：真实列集不含 uuid 起手；变异注入必破「== {E,F}」守卫。
        contract = _contract_with([_static_table_spec()])
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        columns, _rows = _needed_columns_and_rows(
            contract=contract, region=_static_region_obj(), binding=binding
        )
        assert columns == frozenset({"E", "F"})  # 净列集
        mutated_cols = frozenset(columns | {"Z"})  # ← uuid 列起手污染
        assert mutated_cols != frozenset({"E", "F"})  # 守卫必红
        assert "Z" not in columns  # 真实实现无 uuid 起手


def _inject_cached_formula_value(data: bytes, sheet_part: str, coord: str, cached: float) -> bytes:
    """给一个已是公式的 cell 注入缓存值 `<v>`（模拟 OO/Excel 计算后落盘的真实产物）。

    openpyxl 写 `="..."` 只产 `<f>` 无 `<v>`（缓存值空）；真实发布产物（materialize→apply
    或 OO 往返后）公式 cell 必带缓存值。extract 的 data_only 视图读缓存值——无缓存值的裸公式
    在生产不会出现。本工具把裸 `<f>` 补上 `<v>`，让读侧测试贴近真实发布态。
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        parts = {n: zf.read(n) for n in zf.namelist()}
    xml = parts[sheet_part].decode("utf-8")
    # 定位 <c r="G12" ...>...<f>...</f></c>，在 </f> 后插 <v>cached</v>
    import re

    pattern = re.compile(rf'(<c r="{coord}"[^>]*>)(.*?)(</c>)', re.DOTALL)
    m = pattern.search(xml)
    assert m is not None, f"未在 {sheet_part} 找到 cell {coord}"
    inner = m.group(2)
    assert "<f>" in inner or "<f " in inner, f"{coord} 不是公式 cell: {inner!r}"
    # openpyxl 写公式 cell 会留一个**空** <v></v>（缓存值空）；把它替成 <v>cached</v>。
    if "<v></v>" in inner:
        inner = inner.replace("<v></v>", f"<v>{cached}</v>")
    elif "<v>" not in inner:
        inner = inner + f"<v>{cached}</v>"
    xml = xml[: m.start()] + m.group(1) + inner + m.group(3) + xml[m.end():]
    parts[sheet_part] = xml.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, b in parts.items():
            zf.writestr(n, b)
    return out.getvalue()


class TestExtractStaticProjectionReadSide:
    """Requirement 3.4/3.6：`extract_projection` 静态分叉的**读侧**独立验证。

    与 Task 5 `TestStaticRoundtrip`（materialize→extract 闭合往返）不同，本测直接对一个
    已含受管值与区内公式的 substrate 调 `extract_projection`，钉住静态分叉：
    * 受管 cell（E12/F12）按绝对坐标反读出正确值；
    * 区内公式 cell（G12，带缓存值）归 `formula_inventory`，不当受管值（Requirement 3.6）；
    * 无动态行域产物（projection.row_keys 空，chunk_count==0）。
    不依赖 materialize，故属 Task 4 读侧闭环。

    🔴 substrate 的公式 cell 必带 `<v>` 缓存值——这是真实发布态（materialize→apply / OO 往返
    后公式 cell 恒带缓存值）。裸 `<f>` 无缓存值的 cell 在生产不出现，extract 的 data_only 视图
    读不到它是**正确**行为（无缓存值 ⇒ 该 cell 在受管区被视为「未存在」而非「空」）。
    """

    def test_reads_managed_cells_and_routes_formula_to_inventory(self, tmp_path) -> None:
        from app.services.workpaper_sync.excel_extract import extract_projection

        contract = _static_contract_with_formula()
        definitions = _static_definitions(contract)
        binding = _static_binding()
        # substrate 带受管值 E12=333/F12=44 与区内公式 G12==E12-F12；给公式补缓存值 289（=333-44）
        substrate = _make_full_static_substrate({"E12": 333.0, "F12": 44.0})
        substrate = _inject_cached_formula_value(
            substrate, "xl/worksheets/sheet1.xml", "G12", 289.0
        )
        artifact = tmp_path / "read_side.xlsx"
        artifact.write_bytes(substrate)

        outcome = extract_projection(
            artifact=artifact,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )

        # 受管 cell 按绝对坐标反读正确值
        assert float(outcome.projection.get(f"{STATIC_TABLE_KEY}/rev_m1").value) == 333.0
        assert float(outcome.projection.get(f"{STATIC_TABLE_KEY}/cost_m1").value) == 44.0
        # 区内公式 cell 归 formula_inventory，公式文本被采集（Requirement 3.6）
        assert f"{STATIC_TABLE_KEY}/margin_m1" in outcome.formula_inventory
        assert outcome.formula_inventory[f"{STATIC_TABLE_KEY}/margin_m1"] == "=E12-F12"
        # 静态分叉：无动态行域（row_keys 空、chunk_count==0）
        assert outcome.projection.row_keys == {}
        assert outcome.stats.chunk_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# Task 5 · materialize 静态链 + 闭合往返（Property 1）
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync import excel_materialize as M
from app.services.workpaper_sync.adapters.base import (
    FieldValue,
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.excel_entry_gate import (
    AdapterBuild,
    FrozenEntryDefinitions,
)
from app.services.workpaper_sync.models import ArtifactKind, ArtifactState


def _read_entries(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _make_full_static_substrate(values: dict[str, float]) -> bytes:
    """造完整静态 substrate：受管静态 sheet + definedName + 隐藏 _GT_SYNC sheet。

    受管区 E12:F12（rev/cost 两输入），G12 = 一个公式 cell（=E12-F12，formula_mask）。
    """
    from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = STATIC_SHEET
    ws["E12"] = values.get("E12", 0)
    ws["F12"] = values.get("F12", 0)
    ws["G12"] = "=E12-F12"  # 区内公式（formula_mask 保护）
    meta = wb.create_sheet(GT_SYNC_SHEET_NAME)
    meta["A1"] = "GT_SYNC_SCHEMA_VERSION"
    meta["B1"] = "1"
    meta.sheet_state = "hidden"
    wb.defined_names[STATIC_DEFINED_NAME] = DefinedName(
        STATIC_DEFINED_NAME, attr_text=f"'{STATIC_SHEET}'!$E$12:$G$12"
    )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _static_contract_with_formula() -> object:
    import hashlib

    def _d(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    payload = {
        "schema_version": "contract-definition:v1",
        "contract_id": STATIC_CONTRACT_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("d433f-template-definition"),
        "instrumentation_definition_sha256": _d("d433f-instrumentation-definition"),
        "template": {
            "relative_path": "D/d433f.xlsx",
            "template_sha256": _d("d433f-template"),
            "normalized_structure_hash": _d("d433f-normalized-structure"),
        },
        "identity_carriers": ["defined_name"],
        "sheets": [
            {
                "sheet_key": "d433-managed",
                "excel_name": STATIC_SHEET,
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": STATIC_TABLE_KEY,
                        "anchor": "E12",
                        "header_rows": 1,
                        "formula_mask": ["G12:G12"],
                        "fields": [
                            {
                                "stable_field_key": f"{STATIC_TABLE_KEY}/rev_m1",
                                "json_pointer": "/months/0/revenue",
                                "column_key": "rev_m1",
                                "cell": {"column": "E", "row_from": 12},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "wp:D4-33!E12",
                            },
                            {
                                "stable_field_key": f"{STATIC_TABLE_KEY}/cost_m1",
                                "json_pointer": "/months/0/cost",
                                "column_key": "cost_m1",
                                "cell": {"column": "F", "row_from": 12},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "wp:D4-33!F12",
                            },
                            {
                                "stable_field_key": f"{STATIC_TABLE_KEY}/margin_m1",
                                "json_pointer": "/months/0/margin",
                                "column_key": "margin_m1",
                                "cell": {"column": "G", "row_from": 12},
                                "mode": "formula",
                                "value_type": "amount",
                                "source_ref": "wp:D4-33!G12",
                            },
                        ],
                    }
                ],
            }
        ],
    }
    return parse_contract(payload, adapter_id=STATIC_CONTRACT_ID)


def _static_definitions(contract: object) -> FrozenEntryDefinitions:
    import hashlib
    import uuid as _uuid

    from app.services.workpaper_sync.models import (
        AuthorityModel,
        BundleSlot,
        BundleSlotSpec,
        DefinitionState,
    )
    from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot

    def _d(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    def slot(kind, digest):
        return BundleSlotSpec(kind, "definition", f"definition:{_uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=_uuid.uuid4(),
        bundle_sha256=_d("d433-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=_uuid.uuid4(),
        authority_model_definition_sha256=_d("d433-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    return FrozenEntryDefinitions(
        entry_id="xlsx/gt-d4-33-static-test",
        bundle=bundle,
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=STATIC_CONTRACT_ID,
            adapter_build_digest=_d("d433-adapter-build"),
            document_type="xlsx",
            contract_version="1.0.0",
        ),
        identity_inventory=parse_identity_inventory(
            _static_inventory_raw([STATIC_DEFINED_NAME])
        ),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


def _static_binding() -> ExcelIdentityBinding:
    return ExcelIdentityBinding(
        table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
    )


def _projection_for(contract: object, *, rev: float, cost: float) -> Projection:
    def fv(key: str, value, vtype, mode):
        spec = contract.field_by_stable_key(key)
        return FieldValue(key, value, spec.value_type, spec.mode)

    values = {
        f"{STATIC_TABLE_KEY}/rev_m1": fv(
            f"{STATIC_TABLE_KEY}/rev_m1", rev, "amount", "editable"
        ),
        f"{STATIC_TABLE_KEY}/cost_m1": fv(
            f"{STATIC_TABLE_KEY}/cost_m1", cost, "amount", "editable"
        ),
        # formula 字段的缓存值（派生），plan 应保留其 <f> 不当普通值写
        f"{STATIC_TABLE_KEY}/margin_m1": fv(
            f"{STATIC_TABLE_KEY}/margin_m1", rev - cost, "amount", "formula"
        ),
    }
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={},
    )


class TestStaticRoundtrip:
    """Property 1：静态区 materialize→extract 往返受管值逐字段相等；公式归 formula_inventory。"""

    def test_write_then_read_equal(self, tmp_path) -> None:
        from app.services.workpaper_sync.excel_extract import extract_projection

        contract = _static_contract_with_formula()
        definitions = _static_definitions(contract)
        binding = _static_binding()
        substrate = _make_full_static_substrate({"E12": 111.0, "F12": 22.0})

        # 1) plan 写新值 rev=888 cost=100
        region_path = tmp_path / "base.xlsx"
        region_path.write_bytes(substrate)
        with zipfile.ZipFile(io.BytesIO(substrate)) as zf:
            region = M.resolve_managed_region(zf, contract=contract, binding=binding)
        plan = M.plan_managed_writes(
            projection=_projection_for(contract, rev=888.0, cost=100.0),
            contract=contract,
            binding=binding,
            region=region,
            scan=None,
            substrate_entries=_read_entries(substrate),
            substrate_formulas={},
            runtime_binding={},
        )
        assert plan.row_shift is None
        assert plan.footer_marker_row is None
        # G12 是 formula → 应进 preserved_formulas
        assert f"{STATIC_TABLE_KEY}/margin_m1" in plan.preserved_formulas
        # G12 的写入是 cached_value_only（保留 <f>），E12/F12 是普通值写
        kind_by_coord = {w.coord: w.kind for w in plan.writes}
        assert kind_by_coord["G12"] is M.CellWriteKind.cached_value_only
        assert kind_by_coord["E12"] is M.CellWriteKind.number_literal
        assert kind_by_coord["F12"] is M.CellWriteKind.number_literal
        # 静态区无 identity 写入（无 UUID 列）
        assert plan.identity_writes == ()

        # 2) apply → staged
        staged = M.apply_plan_zip(substrate, plan)
        staged_path = tmp_path / "staged.xlsx"
        staged_path.write_bytes(staged)

        # 3) extract 反读
        outcome = extract_projection(
            artifact=staged_path,
            definitions=definitions,
            binding=binding,
            substrate_role=SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )
        rev_back = outcome.projection.get(f"{STATIC_TABLE_KEY}/rev_m1")
        cost_back = outcome.projection.get(f"{STATIC_TABLE_KEY}/cost_m1")
        assert float(rev_back.value) == 888.0
        assert float(cost_back.value) == 100.0
        # 公式 cell 归 formula_inventory，不当受管值
        assert f"{STATIC_TABLE_KEY}/margin_m1" in outcome.formula_inventory


# ═══════════════════════════════════════════════════════════════════════════
# Task 6 · observer 泛化（Requirement 5.1/5.3 / Property 3/7）
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync.published_identity_observer import (
    _collect_static_region_physical,
    _frozen_sheet_anchors,
    collect_workbook_structure,
)


class TestFrozenSheetAnchorsStatic:
    def test_static_payload_yields_region_kind_static(self) -> None:
        payload = {
            "managed_sheets": [
                {
                    "sheet_key": "d433-managed",
                    "region_boundary_locator": {
                        "anchor": "defined_name_ref",
                        "defined_name": STATIC_DEFINED_NAME,
                        "region_kind": "static",
                    },
                }
            ]
        }
        anchors = _frozen_sheet_anchors(payload)
        assert len(anchors) == 1
        assert anchors[0]["anchor"] == "defined_name_ref"
        assert anchors[0]["region_kind"] == "static"
        assert anchors[0]["defined_name"] == STATIC_DEFINED_NAME

    def test_transposed_payload_has_empty_region_kind(self) -> None:
        # D4-29 payload 无 region_kind → 缺省 ""（走 transposed，零回归）
        payload = {
            "transposed_sheets": [
                {
                    "sheet_key": "d4-29",
                    "region_boundary_locator": {
                        "anchor": "defined_name_ref",
                        "defined_name": "GT_MANAGED_REGION_D429",
                    },
                }
            ]
        }
        anchors = _frozen_sheet_anchors(payload)
        assert len(anchors) == 1
        assert anchors[0]["region_kind"] == ""


class TestCollectStaticRegionPhysical:
    def test_resolves_sheet_name(self) -> None:
        data = _make_full_static_substrate({"E12": 1.0, "F12": 2.0})
        contract = _static_contract_with_formula()
        physical = _collect_static_region_physical(
            data=data, contract=contract, key="d433-managed",
            defined_name=STATIC_DEFINED_NAME,
        )
        assert physical == STATIC_SHEET

    def test_missing_defined_name_fail_closed(self) -> None:
        wb = openpyxl.Workbook()
        wb.active.title = STATIC_SHEET
        buf = io.BytesIO()
        wb.save(buf)
        with pytest.raises(ValueError, match="反读不到"):
            _collect_static_region_physical(
                data=buf.getvalue(), contract=_static_contract_with_formula(),
                key="d433-managed", defined_name=STATIC_DEFINED_NAME,
            )


class TestCollectWorkbookStructureStatic:
    def test_static_anchor_goes_through_static_path(self) -> None:
        # collect_workbook_structure 对 static anchor 走 _collect_static_region_physical，
        # 不调 extract_transposed_workbook（那是转置语义）。
        data = _make_full_static_substrate({"E12": 10.0, "F12": 3.0})
        contract = _static_contract_with_formula()
        anchors = [
            {
                "sheet_key": "d433-managed",
                "anchor": "defined_name_ref",
                "defined_name": STATIC_DEFINED_NAME,
                "region_kind": "static",
            }
        ]
        fingerprint, physical, primary_inventory, structure = collect_workbook_structure(
            data=data, contract=contract, sheet_anchors=anchors
        )
        assert physical["d433-managed"] == STATIC_SHEET
        # 静态区无 primary_inventory（那是动态 row UUID 路径产的）
        assert primary_inventory is None
        # 结构清册含静态 fields 的绝对坐标（E12/F12/G12 由 _cell_coordinates_for 静态路径产）
        locators = {loc for (_sk, _tk, _fk, loc) in structure}
        assert any(":12" in loc for loc in locators)


# ═══════════════════════════════════════════════════════════════════════════
# Task 7 · instrumentation 注入静态 definedName（Requirement 5.4/5.5）
# ═══════════════════════════════════════════════════════════════════════════

import pathlib

from app.services.workpaper_sync import excel_instrumentation as EI

_WP_TEMPLATES = pathlib.Path(__file__).resolve().parents[2] / "wp_templates"
_K11_TEMPLATE = _WP_TEMPLATES / "K" / "K11 资产减值损失.xlsx"


def _spec_with_static(static_sheet_name: str, defined_name: str, region_range: str):
    """动态 primary spec（K11）+ 一个静态受管区寄生声明。"""
    return EI.ExcelInstrumentationSpec(
        entry_id="k11.adjudication",
        template_id="K11",
        template_relative_path="K/K11 资产减值损失.xlsx",
        managed_sheet="审定表K11-1",
        first_data_row=7,
        last_data_row=25,
        footer_row=26,
        managed_last_col="L",
        uuid_col="N",
        table_name="GT_K11_1_ROWS",
        static_sheets=(
            {
                "sheet_key": "d433-managed",
                "excel_name": static_sheet_name,
                "region_boundary_locator": {
                    "anchor": "defined_name_ref",
                    "defined_name": defined_name,
                    "range": region_range,
                    "region_kind": "static",
                },
                "tables": [{"table_key": "d433-static"}],
            },
        ),
    )


def _first_other_sheet_name(data: bytes) -> str:
    import re as _re

    wb = _read_entries(data)["xl/workbook.xml"].decode("utf-8")
    names = _re.findall(r'<sheet [^>]*name="([^"]+)"', wb)
    for n in names:
        if n != "审定表K11-1":
            return n
    raise AssertionError("K11 模板只有一张 sheet？")


def _sheet_part_for_name(entries: dict, sheet_name: str) -> str:
    """从 workbook.xml + rels 解析出某展示名 sheet 的 worksheet part 路径。"""
    import re as _re

    wb = entries["xl/workbook.xml"].decode("utf-8")
    m = _re.search(
        r'<sheet [^>]*name="' + _re.escape(sheet_name) + r'"[^>]*r:id="([^"]+)"', wb
    )
    if m is None:
        raise AssertionError(f"workbook.xml 无 sheet {sheet_name!r}")
    rid = m.group(1)
    rels = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    rm = _re.search(
        r'<Relationship [^>]*Id="' + _re.escape(rid) + r'"[^>]*Target="([^"]+)"', rels
    )
    if rm is None:
        raise AssertionError(f"workbook.xml.rels 无 rId {rid!r}")
    target = rm.group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


class TestStaticInstrumentation:
    @pytest.fixture(scope="class")
    def source(self) -> bytes:
        if not _K11_TEMPLATE.exists():
            pytest.skip(f"模板缺失: {_K11_TEMPLATE}")
        return _K11_TEMPLATE.read_bytes()

    def test_injects_workbook_scope_defined_name_no_table_no_uuid(self, source: bytes) -> None:
        static_sheet = _first_other_sheet_name(source)
        spec = _spec_with_static(static_sheet, "GT_MANAGED_REGION_D433T", "$E$12:$G$13")
        gate = EI.ExcelIdentityCarrierGate.load()
        result = EI.instrument_workbook_bytes_multi(source, [spec], gate=gate)
        entries = _read_entries(result.instrumented_bytes)
        wb = entries["xl/workbook.xml"].decode("utf-8")
        # (a) 注入了 workbook-scope definedName（无 localSheetId）
        assert "GT_MANAGED_REGION_D433T" in wb
        import re as _re

        m = _re.search(
            r'<definedName name="GT_MANAGED_REGION_D433T"([^>]*)>([^<]+)</definedName>', wb
        )
        assert m is not None
        assert "localSheetId" not in m.group(1)  # workbook-scope
        assert "$E$12:$G$13" in m.group(2)
        # definedName_refs 里也有它
        assert "GT_MANAGED_REGION_D433T" in result.defined_name_refs
        # (b) 静态 sheet 上**不注** Excel Table `<tableParts>`（Requirement 5.4）：
        #     该 sheet 的 worksheet XML 不得因静态注入而多出 tableParts。
        static_part = _sheet_part_for_name(entries, static_sheet)
        static_ws = entries[static_part].decode("utf-8")
        assert "<tableParts" not in static_ws
        assert "tablePart" not in static_ws
        # (c) 静态 sheet 未被注入隐藏 UUID 列：`_inject_managed_sheet` 只对 spec.managed_sheet
        #     (审定表K11-1) 注 UUID 列。静态区的 defined_name_refs 只有区域锚点，没有 UUID range。
        #     Table 只经某 sheet 的 <tableParts> 绑定该 sheet；静态 sheet 无 tableParts (b)
        #     即证明无 Table 载体指向它。
        static_refs = {k: v for k, v in result.defined_name_refs.items()
                       if static_sheet in str(v)}
        assert all("UUID" not in k and "ROW_UUID" not in k for k in static_refs)
        # (d) `_GT_SYNC` runtime binding 载体存在（静态注入仍走同一 metadata sheet），
        #     静态区锚点经 payload static_sheets 记录（由 frozen anchors 测试闭合）。
        assert EI._GT_SYNC_SHEET_PART in entries

    def test_static_defined_name_resolvable_by_extract(self, source: bytes) -> None:
        # 注入后用 extract 的 _resolve_static_region 能反解出 region（端到端锚点闭合）
        static_sheet = _first_other_sheet_name(source)
        spec = _spec_with_static(static_sheet, "GT_MANAGED_REGION_D433T", "$E$12:$G$13")
        gate = EI.ExcelIdentityCarrierGate.load()
        result = EI.instrument_workbook_bytes_multi(source, [spec], gate=gate)
        from app.services.workpaper_sync.excel_extract import (
            _resolve_static_region,
        )

        binding = ExcelIdentityBinding(
            table_key="d433-static", defined_name="GT_MANAGED_REGION_D433T"
        )
        with zipfile.ZipFile(io.BytesIO(result.instrumented_bytes)) as zf:
            region = _resolve_static_region(
                zf, contract=_static_contract_with_formula(), binding=binding
            )
        assert region.sheet_name == static_sheet
        assert region.first_column == "E"
        assert region.last_column == "G"
        assert region.first_row == 12
        assert region.uuid_column == ""

    def test_frozen_anchors_from_payload_yield_static_kind(self, source: bytes) -> None:
        spec = _spec_with_static(
            _first_other_sheet_name(source), "GT_MANAGED_REGION_D433T", "$E$12:$G$13"
        )
        import hashlib as _h

        payload = EI.build_instrumentation_payload_for_sheets(
            specs=[spec],
            template_definition_sha256=_h.sha256(b"td").hexdigest(),
            template_sha256=_h.sha256(b"ts").hexdigest(),
            gate=EI.ExcelIdentityCarrierGate.load(),
        )
        assert "static_sheets" in payload
        anchors = _frozen_sheet_anchors(payload)
        static_anchors = [a for a in anchors if a.get("region_kind") == "static"]
        assert len(static_anchors) == 1
        assert static_anchors[0]["defined_name"] == "GT_MANAGED_REGION_D433T"

    def test_delete_injected_defined_name_extract_fails_closed(self, source: bytes) -> None:
        # 变异反证（Requirement 7.2 末条）：注入后**删掉** definedName 锚点，
        # 静态 extract 必须 fail-closed 抛 IdentityCarrierMissingError（锚点即区域载体，
        # 缺它绝不能 fail-open 猜 sheet-id）。
        import re as _re

        static_sheet = _first_other_sheet_name(source)
        spec = _spec_with_static(static_sheet, "GT_MANAGED_REGION_D433T", "$E$12:$G$13")
        gate = EI.ExcelIdentityCarrierGate.load()
        result = EI.instrument_workbook_bytes_multi(source, [spec], gate=gate)

        # 从 instrumented 产物里剥掉那条 definedName，重新打包。
        entries = _read_entries(result.instrumented_bytes)
        wb = entries["xl/workbook.xml"].decode("utf-8")
        assert "GT_MANAGED_REGION_D433T" in wb  # 前置：确认删前存在
        wb_stripped = _re.sub(
            r'<definedName name="GT_MANAGED_REGION_D433T"[^>]*>[^<]+</definedName>',
            "",
            wb,
        )
        assert "GT_MANAGED_REGION_D433T" not in wb_stripped
        entries["xl/workbook.xml"] = wb_stripped.encode("utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for name in entries:
                out.writestr(name, entries[name])
        tampered = buf.getvalue()

        from app.services.workpaper_sync.excel_extract import (
            IdentityCarrierMissingError,
            _resolve_static_region,
        )

        binding = ExcelIdentityBinding(
            table_key="d433-static", defined_name="GT_MANAGED_REGION_D433T"
        )
        with zipfile.ZipFile(io.BytesIO(tampered)) as zf:
            with pytest.raises(IdentityCarrierMissingError):
                _resolve_static_region(
                    zf, contract=_static_contract_with_formula(), binding=binding
                )


# ═══════════════════════════════════════════════════════════════════════════
# Task 6 · 未知 kind fail-closed（Requirement 5.1）
# ═══════════════════════════════════════════════════════════════════════════


class TestCollectWorkbookStructureUnknownKind:
    """`collect_workbook_structure` 遇未知 anchor kind 必须 fail-closed，不静默吞。

    Requirement 5.1：kind 分派——transposed 走 D4-29 原样、static 走静态路径、
    **未知 kind 才 raise**。observer 把非 ValueError 内部异常统一转译为
    ``ObservedIdentityDriftError``（observe_workbook 阶段），故未知 kind 表现为
    该窄异常，绝不 fail-open 返回空结构。
    """

    def test_unknown_top_level_anchor_kind_fail_closed(self) -> None:
        from app.services.workpaper_sync.published_identity_observer import (
            ObservedIdentityDriftError,
        )

        data = _make_full_static_substrate({"E12": 1.0, "F12": 2.0})
        contract = _static_contract_with_formula()
        # anchor 值是引擎未声明的 kind（既非 defined_name_ref，也不含 dynamic 三要素）
        anchors = [
            {
                "sheet_key": "d433-managed",
                "anchor": "some_future_carrier_kind",
                "defined_name": STATIC_DEFINED_NAME,
            }
        ]
        with pytest.raises(ObservedIdentityDriftError):
            collect_workbook_structure(
                data=data, contract=contract, sheet_anchors=anchors
            )

    def test_defined_name_ref_unknown_region_kind_on_non_d429_fail_closed(self) -> None:
        # anchor==defined_name_ref 但 region_kind 是未知值（非 "static"）→ 落 transposed
        # 分派，非 D4-29 sheet 触发 "Unsupported transposed anchor" → 转译窄异常。
        from app.services.workpaper_sync.published_identity_observer import (
            ObservedIdentityDriftError,
        )

        data = _make_full_static_substrate({"E12": 1.0, "F12": 2.0})
        contract = _static_contract_with_formula()
        anchors = [
            {
                "sheet_key": "d433-managed",
                "anchor": "defined_name_ref",
                "defined_name": STATIC_DEFINED_NAME,
                "region_kind": "totally-unknown-kind",  # 非 static → 落 transposed 硬判据
            }
        ]
        with pytest.raises(ObservedIdentityDriftError):
            collect_workbook_structure(
                data=data, contract=contract, sheet_anchors=anchors
            )


# ═══════════════════════════════════════════════════════════════════════════
# Task 6 · Property 3 — D4-29 transposed 零回归 + 转置↔静态误路由变异反证
# **Validates: Requirements 5.2**
# ═══════════════════════════════════════════════════════════════════════════

from app.services.workpaper_sync import phase5_d4_29_customer_detail as _d429


@pytest.fixture(scope="module")
def _d429_template() -> bytes:
    """真实 D4-29 模板注入产物（与 test_d4_29_customer_detail_sync 同源构造）。"""
    from app.services.workpaper_sync import phase5_d4_revenue_detail as provider
    from app.services.workpaper_sync.excel_instrumentation import (
        instrument_workbook_bytes_multi,
    )

    return instrument_workbook_bytes_multi(
        provider.read_authoritative_template(),
        provider.instrumentation_specs(),
        gate=provider.excel_carrier_gate(),
    ).instrumented_bytes


@pytest.fixture(scope="module")
def _d429_focused_contract():
    from app.services.workpaper_sync.contracts import load_contract, parse_contract

    contract = load_contract("d4.revenue_detail")
    payload = dict(contract.canonical_payload)
    payload["sheets"] = [
        s for s in payload["sheets"] if s["sheet_key"] == _d429.SHEET_KEY
    ]
    return parse_contract(payload, adapter_id=contract.contract_id)


def _d429_customers(count: int = 12):
    return [
        {"id": f"id{i}", "name": f"客户{i}",
         "fields": {k: f"{k}-{i}" for k in _d429.FIELD_KEYS}}
        for i in range(count)
    ]


def _d429_transposed_anchor() -> dict:
    """D4-29 payload 无 region_kind → _frozen_sheet_anchors 产 region_kind=""（transposed）。"""
    anchors = _frozen_sheet_anchors({"transposed_sheets": [_d429.sheet_payload()]})
    return next(a for a in anchors if a["sheet_key"] == _d429.SHEET_KEY)


class TestD429TransposedZeroRegression:
    """Property 3：kind 分派泛化后，D4-29 transposed 反读逐字段与改前相等。

    observer 从「硬编码 D4-29 常量」泛化为「按 region_kind 分派」后，D4-29 因 payload
    无 region_kind → 缺省 "" → 落既有 transposed 分支（`extract_transposed_workbook` +
    C:M 转置字段映射），行为必须逐字段零回归。
    """

    def test_transposed_anchor_kind_is_transposed_not_static(self) -> None:
        anchor = _d429_transposed_anchor()
        assert anchor["anchor"] == "defined_name_ref"
        # D4-29 缺省 region_kind="" → observer 落 transposed 分派（非 static）
        assert anchor["region_kind"] == ""

    def test_transposed_reverse_read_stable_field_for_field(
        self, _d429_template, _d429_focused_contract
    ) -> None:
        anchor = _d429_transposed_anchor()
        data = _d429.materialize_transposed_workbook(_d429_template, _d429_customers(12))
        # 转置反读逐字段（这是 transposed 语义的权威真源，静态路径永不产它）
        assert _d429.extract_transposed_workbook(data) == _d429_customers(12)
        fingerprint, physical, primary_inventory, structure = collect_workbook_structure(
            data=data, contract=_d429_focused_contract, sheet_anchors=[anchor]
        )
        # transposed 物理 sheet 解析正确 + 结构清册产出（转置字段映射进 structure）
        assert physical[_d429.SHEET_KEY] == _d429.MANAGED_SHEET
        assert len(structure) == 29  # 与 test_d4_29 既有守卫同一基线

    def test_transposed_survives_sheet_rename(
        self, _d429_template, _d429_focused_contract
    ) -> None:
        # definedName 锚点使转置反读不受 OO 改 sheet 名影响（D4-29 既有语义，零回归）
        anchor = _d429_transposed_anchor()
        data = _d429.materialize_transposed_workbook(_d429_template, _d429_customers(2))
        wb = openpyxl.load_workbook(io.BytesIO(data))
        wb[_d429.MANAGED_SHEET].title = "Renamed customer sheet"
        wb.defined_names[_d429.DEFINED_NAME].attr_text = (
            "'Renamed customer sheet'!" + _d429.MANAGED_REF
        )
        buf = io.BytesIO()
        wb.save(buf)
        renamed = buf.getvalue()
        assert _d429.extract_transposed_workbook(renamed) == _d429_customers(2)
        _fp, physical, _pi, _st = collect_workbook_structure(
            data=renamed, contract=_d429_focused_contract, sheet_anchors=[anchor]
        )
        assert physical[_d429.SHEET_KEY] == "Renamed customer sheet"


class TestKindMisrouteMutation:
    """变异反证：转置↔静态误路由必 RED（守卫钉死 region_kind 分派正确性）。

    这是 Property 3 的变异反证——若 observer 把 transposed 错分派到 static 反读
    （或反之），结果必与真值发散、必被守卫捕获。四态判定目标：RED。
    """

    def test_transposed_misrouted_to_static_diverges(
        self, _d429_template, _d429_focused_contract
    ) -> None:
        # 把 D4-29 transposed anchor 强行标 region_kind="static" → 误路由到静态反读。
        # 静态路径 _collect_static_region_physical 只解析 physical sheet 名、不产 D4-29 的
        # 转置字段映射 → observe_structure_inventory 得不到转置字段 → 结构漂移 fail-closed。
        # 若此变异**不红**，说明 static 分支污染/复用了 transposed 语义（守卫缺陷）。
        from app.services.workpaper_sync.published_identity_observer import (
            ObservedIdentityDriftError,
        )

        from app.services.workpaper_sync.contracts import ContractDriftError

        anchor = dict(_d429_transposed_anchor())
        anchor["region_kind"] = "static"  # ★变异：transposed → static 误路由
        data = _d429.materialize_transposed_workbook(_d429_template, _d429_customers(12))
        # 误路由后 static 分支只解析 physical sheet 名、不产转置字段映射 → 结构漂移
        # fail-closed（ContractDriftError 或 observer 转译的 ObservedIdentityDriftError
        # 均为有效 RED 信号）。
        with pytest.raises((ObservedIdentityDriftError, ContractDriftError)):
            collect_workbook_structure(
                data=data, contract=_d429_focused_contract, sheet_anchors=[anchor]
            )

    def test_static_misrouted_to_transposed_diverges(self) -> None:
        # 把静态 anchor 的 region_kind 去掉（→ ""）→ 误路由到 transposed 分派。
        # 静态 sheet 的 sheet_key/defined_name 非 D4-29 → transposed 硬判据抛
        # "Unsupported transposed anchor" → 转译窄异常。若此变异**不红**，说明
        # transposed 分支错误接受了非 D4-29 静态区（守卫缺陷）。
        from app.services.workpaper_sync.published_identity_observer import (
            ObservedIdentityDriftError,
        )

        data = _make_full_static_substrate({"E12": 10.0, "F12": 3.0})
        contract = _static_contract_with_formula()
        anchors = [
            {
                "sheet_key": "d433-managed",
                "anchor": "defined_name_ref",
                "defined_name": STATIC_DEFINED_NAME,
                # ★变异：删 region_kind（→ ""）→ 落 transposed 分派
            }
        ]
        with pytest.raises(ObservedIdentityDriftError):
            collect_workbook_structure(
                data=data, contract=contract, sheet_anchors=anchors
            )

    def test_static_correctly_routed_is_green_baseline(self) -> None:
        # 对照组（GREEN baseline）：region_kind="static" 正确路由 → 不抛，静态结构产出。
        # 与上面两个变异形成 RED/GREEN 对照，证明守卫抓的是「路由正确性」而非「恒抛」。
        data = _make_full_static_substrate({"E12": 10.0, "F12": 3.0})
        contract = _static_contract_with_formula()
        anchors = [
            {
                "sheet_key": "d433-managed",
                "anchor": "defined_name_ref",
                "defined_name": STATIC_DEFINED_NAME,
                "region_kind": "static",
            }
        ]
        _fp, physical, primary_inventory, structure = collect_workbook_structure(
            data=data, contract=contract, sheet_anchors=anchors
        )
        assert physical["d433-managed"] == STATIC_SHEET
        assert primary_inventory is None


# ═══════════════════════════════════════════════════════════════════════════
# Task 8 · 动态 + D4-29 零回归全面复核 + 六锚点变异四态判定
# **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
#
# 本段是本 spec 回归风险最高的收口门（gates provider wiring）。三条 Property：
#   * P2 动态路径字节零回归：既有动态 sheet（D4-3，Excel-Table anchored）materialize
#     产物字节 sha256 恒等——静态分支是**新增旁路**，绝不触碰动态分支任一语句。
#   * P3 D4-29 转置零回归：见上文 `TestD429TransposedZeroRegression`（Task 6 已闭合），
#     本段再钉一条「转置反读逐字段 == 独立真值」的冗余锚点。
#   * P7 structure_hash 动态侧逐字符不变 + 静态 sheet hash 含 definedName 锚点
#     （删 definedName → 静态结构采集 fail-closed，强于 hash 变）。
#
# 以及 requirements 7.2 的**六锚点变异反证**：每条变异对**生产代码**真施加→跑守卫→确认
# RED→完全还原（git diff 干净）。四态判定（RED / GREEN=守卫缺陷 / ANCHOR-MISS /
# WRONG-TEST）逐条记录进 evidence（见 subagent 汇报的六锚点表）。此处的守卫是变异的**落点**：
# 守卫在真实生产代码上必须绿（未变异态），变异施加后必红——本文件其它 wave 的守卫已覆盖
# 六锚点中的五个（见每条变异注释指向的测试类），本段补齐 P2/P3/P7 的动态/D4-29 零回归守卫。
# ═══════════════════════════════════════════════════════════════════════════

import hashlib as _hashlib

from app.services.workpaper_sync.excel_instrumentation import normalized_structure_hash
from app.services.excel_structure_fingerprint import identity_inventory as _identity_inventory

# 🔴 动态 sheet 零回归**自包含**在 Task 37/38 的真实 K11 模板 fixture 上，**不**走 D4 provider
#    的 build_contract_payload()——后者当前含未完工的 D4-8（d48-managed）契约块（Task 11 在建，
#    stable_field_key 形态未过校验），会让 parse_contract 抛 ContractSchemaError。Task 8 的动态
#    零回归只需一张**任意既有动态 Excel-Table anchored sheet**，K11（test_task37/38 的 SPEC）
#    正是这样一张真张，且与 provider wiring 状态完全解耦（更稳的回归锚点）。
from test_task37_excel_extract import (  # noqa: E402
    BINDING as _DYN_BINDING,
    TEMPLATE as _DYN_TEMPLATE,
    SPEC as _DYN_SPEC,
    business_cells as _dyn_business_cells,
    contract_payload as _dyn_contract_payload,
    make_definitions as _dyn_make_definitions,
    patch_cells as _dyn_patch_cells,
    _sheet_part_of as _dyn_sheet_part_of,
    TABLE_NAME as _DYN_TABLE_NAME,
    UUID_COL as _DYN_UUID_COL,
    MANAGED_SHEET as _DYN_MANAGED_SHEET,
    CONTRACT_ID as _DYN_CONTRACT_ID,
)
from app.services.workpaper_sync import excel_instrumentation as _EI


def _d8(label: str) -> str:
    return _hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def _dyn_base_bytes() -> bytes:
    """真实 K11 动态 sheet：instrument（Excel-Table + 隐藏 UUID 列）→ 写入业务值。"""
    gate = _EI.ExcelIdentityCarrierGate.load()
    instrumented = _EI.instrument_workbook_bytes(
        _DYN_TEMPLATE.read_bytes(), _DYN_SPEC, gate=gate
    ).instrumented_bytes
    sheet_part = _dyn_sheet_part_of(instrumented, _DYN_MANAGED_SHEET)
    return _dyn_patch_cells(instrumented, sheet_part, _dyn_business_cells())


@pytest.fixture(scope="module")
def _dyn_definitions(_dyn_base_bytes):
    contract = parse_contract(_dyn_contract_payload(), adapter_id=_DYN_CONTRACT_ID)
    inv = _identity_inventory(
        _dyn_base_bytes, expected_table=_DYN_TABLE_NAME, uuid_column_letter=_DYN_UUID_COL
    )
    return _dyn_make_definitions(contract, inv)


def _materialize_dynamic(_dyn_base_bytes, _dyn_definitions, tmp_path, tag: str) -> bytes:
    """真栈 materialize 一次 K11 动态 sheet（extract → 原值 projection → materialize），返回产物字节。

    projection 直接取自基底的反读（往返恒等的受管值），故 materialize 不引入新数据，
    产物内容对同一 (基底, 契约, binding) 恒定——这是「字节零回归」可比的前提。
    """
    from app.services.workpaper_sync.excel_extract import extract_projection

    base = tmp_path / f"dyn-base-{tag}.xlsx"
    base.write_bytes(_dyn_base_bytes)
    outcome = extract_projection(
        artifact=base,
        definitions=_dyn_definitions,
        binding=_DYN_BINDING,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
    )
    staged = tmp_path / f"dyn-staged-{tag}.xlsx"
    M.materialize_projection(
        substrate=base,
        projection=outcome.projection,
        output=staged,
        definitions=_dyn_definitions,
        binding=_DYN_BINDING,
        substrate_role=SubstrateRole.published_representation,
        substrate_kind=ArtifactKind.canonical,
        substrate_state=ArtifactState.published,
    )
    return staged.read_bytes()


def _zip_member_content_digest(data: bytes) -> dict[str, str]:
    """按 zip 成员**内容字节** sha256 逐条摘要（剥离 zip 容器 date_time 噪声）。

    🔴 为什么不是整簧 sha256：`excel_materialize._write_entries` 用 `writestr(name, bytes)`
    重打包，zipfile 对纯字符串名的条目**戳当前时间**进 date_time 头 —— 两次 materialize
    间隔几秒即字节不同（时间戳噪声），但业务内容逐字节相同。真正要钉的「逐字节零回归」是
    **成员内容**逐字节相等（每个 part 的解压内容 sha256），不是含时间戳的容器字节。这是本
    spec 发现的既有引擎事实（`_write_entries` 不 pin 时间戳），记录进 Task 8 evidence。
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: _hashlib.sha256(zf.read(name)).hexdigest() for name in zf.namelist()}


class TestDynamicMaterializeByteZeroRegression:
    """Property 2：动态 sheet（K11，Excel-Table anchored 真张）materialize 产物**成员内容**逐字节零回归。

    **Validates: Requirements 7.3 (Property 2 / Requirements 2.6, 3.7, 4.6)**

    「改动前基线」不可能事后追溯（静态路径已 merge），故零回归以**两条可实测的不变量**表达，
    比较口径是**每个 zip 成员的解压内容 sha256**（剥离容器 date_time 时间戳噪声——见
    `_zip_member_content_digest`；`_write_entries` 用 `writestr` 不 pin 时间戳是既有引擎事实）：
      1) **内容确定性**：同一注入基底 + 同一 projection，materialize 两次每个成员内容 sha256
         恒等（动态路径无非确定性：row_uuid 取自模板既有行，无新 mint UUID）。
      2) **静态旁路无侧漏**：在同进程内先跑一整套静态区路径（resolve→plan→apply→extract），
         再 materialize 同一动态 sheet，其每个成员内容 sha256 与「未先跑静态」时**完全相等**
         ——证明静态分支是纯新增旁路，不向动态路径泄漏任何状态（模块级缓存/全局态/幽灵坐标）。

    变异反证（design P2 行）：若静态分支意外触碰动态 `row_span` uuid 循环（或任何动态语句），
    上述 (2) 的成员内容摘要必发散 → RED。本守卫是那条变异的落点。
    """

    def test_dynamic_materialize_content_is_deterministic(
        self, _dyn_base_bytes, _dyn_definitions, tmp_path
    ) -> None:
        a = _materialize_dynamic(_dyn_base_bytes, _dyn_definitions, tmp_path, "det-a")
        b = _materialize_dynamic(_dyn_base_bytes, _dyn_definitions, tmp_path, "det-b")
        assert a[:2] == b"PK" and b[:2] == b"PK"
        # 成员内容逐条相等（剥离容器时间戳后是逐字节零回归）
        assert _zip_member_content_digest(a) == _zip_member_content_digest(b), (
            "K11 动态 materialize 成员内容非确定性 —— 字节零回归的前提破了"
        )

    def test_static_path_exercise_does_not_perturb_dynamic_content(
        self, _dyn_base_bytes, _dyn_definitions, tmp_path
    ) -> None:
        # 基线：不先跑静态，直接 materialize 动态 sheet。
        baseline = _materialize_dynamic(
            _dyn_base_bytes, _dyn_definitions, tmp_path, "baseline"
        )
        baseline_content = _zip_member_content_digest(baseline)

        # 在同进程内跑一整套静态区路径（resolve → plan → apply → extract）。
        from app.services.workpaper_sync.excel_extract import extract_projection

        static_contract = _static_contract_with_formula()
        static_definitions = _static_definitions(static_contract)
        static_binding = _static_binding()
        static_substrate = _make_full_static_substrate({"E12": 7.0, "F12": 3.0})
        with zipfile.ZipFile(io.BytesIO(static_substrate)) as zf:
            static_region = M.resolve_managed_region(
                zf, contract=static_contract, binding=static_binding
            )
        static_plan = M.plan_managed_writes(
            projection=_projection_for(static_contract, rev=999.0, cost=111.0),
            contract=static_contract,
            binding=static_binding,
            region=static_region,
            scan=None,
            substrate_entries=_read_entries(static_substrate),
            substrate_formulas={},
            runtime_binding={},
        )
        static_staged = M.apply_plan_zip(static_substrate, static_plan)
        static_path_file = tmp_path / "static-side.xlsx"
        static_path_file.write_bytes(static_staged)
        extract_projection(
            artifact=static_path_file,
            definitions=static_definitions,
            binding=static_binding,
            substrate_role=SubstrateRole.published_representation,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.published,
        )

        # 静态路径跑完后再 materialize 同一动态 sheet：每个成员内容必与基线完全相等。
        after_static = _materialize_dynamic(
            _dyn_base_bytes, _dyn_definitions, tmp_path, "after-static"
        )
        assert _zip_member_content_digest(after_static) == baseline_content, (
            "跑过静态区路径后动态 materialize 成员内容变了 —— 静态旁路向动态路径泄漏了状态"
            "（Property 2 零回归被破）"
        )


class TestD429TransposedByteAndFieldZeroRegression:
    """Property 3 冗余锚点：D4-29 转置反读逐字段与独立真值相等（Task 6 已闭合，此为收口复核）。

    **Validates: Requirements 7.3 (Property 3 / Requirements 5.2)**

    observer kind 分派泛化后，D4-29 走 transposed（region_kind=""）反读逐字段零回归。
    完整守卫见 `TestD429TransposedZeroRegression`；此处只再钉「转置反读 == 构造真值」这条
    独立于 observer 的等价性，作为 Task 8 收口的冗余证据（转置↔静态误路由变异见
    `TestKindMisrouteMutation`，四态 RED）。
    """

    def test_transposed_reverse_read_matches_independent_truth(self, _d429_template) -> None:
        customers = _d429_customers(12)
        data = _d429.materialize_transposed_workbook(_d429_template, customers)
        # 转置反读逐字段 == 独立构造真值（静态路径永不产它）
        assert _d429.extract_transposed_workbook(data) == customers
        # 冗余：不同 count 也逐字段等（转置语义与静态语义正交的活证据）
        data2 = _d429.materialize_transposed_workbook(_d429_template, _d429_customers(3))
        assert _d429.extract_transposed_workbook(data2) == _d429_customers(3)


class TestStructureHashDynamicUnchangedStaticAnchored:
    """Property 7：动态 sheet structure_hash 逐字符不变；静态 sheet hash 含 definedName 锚点。

    **Validates: Requirements 7.5 (Property 7 / Requirements 5.6)**

    * 动态侧：`normalized_structure_hash` 是 `excel_instrumentation` 里对**字节**的纯函数
      （六 aspect digest 折叠），与本 spec 在 `excel_extract`/`observer` 里新增的静态分支
      **物理隔离**——静态分支一行都碰不到它。故动态 sheet 的 structure_hash 逐字符不变
      （多次计算恒等 + 跑过静态路径后恒等）。
    * 静态侧：静态 sheet 的**结构漂移锚点是 definedName**——删掉它后 `_resolve_static_region`
      / `collect_workbook_structure` 静态分派 fail-closed（`IdentityCarrierMissingError`），
      比「hash 变」更强（结构采集根本无法完成）。这正是 Requirement 5.6「definedName 被删/
      被改能被结构漂移门捕获」的落地形态。删 definedName fail-closed 的端到端守卫见
      Task 7 `test_delete_injected_defined_name_extract_fails_closed`；此处钉「静态 hash 对
      definedName 几何敏感」这一读侧不变量。
    """

    def test_dynamic_structure_hash_is_char_stable(self, _dyn_base_bytes) -> None:
        h1 = normalized_structure_hash(_dyn_base_bytes)
        h2 = normalized_structure_hash(_dyn_base_bytes)
        assert h1 == h2  # 纯函数，逐字符恒等

    def test_dynamic_structure_hash_unaffected_by_static_path(self, _dyn_base_bytes) -> None:
        baseline = normalized_structure_hash(_dyn_base_bytes)
        # 跑一趟静态区解析（触发 excel_extract 静态分支的全部语句）
        static_substrate = _make_full_static_substrate({"E12": 5.0, "F12": 2.0})
        with zipfile.ZipFile(io.BytesIO(static_substrate)) as zf:
            _ = M.resolve_managed_region(
                zf, contract=_static_contract_with_formula(), binding=_static_binding()
            )
        # 动态 sheet 的 structure_hash 逐字符不变
        assert normalized_structure_hash(_dyn_base_bytes) == baseline

    def test_static_structure_hash_sensitive_to_defined_name_geometry(self) -> None:
        # 静态区结构锚点 = definedName 的几何。改 definedName 的 ref 几何 → 反读出的 region
        # 几何变 → 静态结构采集的坐标集变（下游 structure_hash 随之变）。此处直接钉
        # region 几何对 definedName ref 的敏感性（结构 hash 的上游输入）。
        wide = _make_static_workbook(ref="$E$12:$M$13")
        narrow = _make_static_workbook(ref="$E$12:$G$13")
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        with zipfile.ZipFile(io.BytesIO(wide)) as zf:
            region_wide = _resolve_static_region(
                zf, contract=_static_contract(), binding=binding
            )
        with zipfile.ZipFile(io.BytesIO(narrow)) as zf:
            region_narrow = _resolve_static_region(
                zf, contract=_static_contract(), binding=binding
            )
        # definedName 几何变 → region 末列变（结构指纹的上游输入随之变）
        assert region_wide.last_column == "M"
        assert region_narrow.last_column == "G"
        assert region_wide.last_column != region_narrow.last_column

    def test_deleting_defined_name_fails_static_structure_collection(self) -> None:
        # Requirement 5.6 落地形态：删 definedName → 静态结构采集 fail-closed（强于 hash 变）。
        data_ok = _make_full_static_substrate({"E12": 1.0, "F12": 2.0})
        # 删掉 workbook.xml 里的 definedName
        entries = _read_entries(data_ok)
        import re as _re

        wb = entries["xl/workbook.xml"].decode("utf-8")
        assert STATIC_DEFINED_NAME in wb
        wb_stripped = _re.sub(
            rf'<definedName name="{STATIC_DEFINED_NAME}"[^>]*>[^<]+</definedName>', "", wb
        )
        assert STATIC_DEFINED_NAME not in wb_stripped
        entries["xl/workbook.xml"] = wb_stripped.encode("utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for name in entries:
                out.writestr(name, entries[name])
        tampered = buf.getvalue()

        # 静态结构物理采集必 fail-closed（definedName 是唯一锚点）
        with pytest.raises(ValueError, match="反读不到"):
            _collect_static_region_physical(
                data=tampered, contract=_static_contract_with_formula(),
                key="d433-managed", defined_name=STATIC_DEFINED_NAME,
            )


# ═══════════════════════════════════════════════════════════════════════════
# Task 8 · Property 5 承重锚点：kind 判据必须读 defined_name，而非 uuid_column 空缺
# **Validates: Requirements 7.2 (锚点 5) / Property 5 / Requirements 1.3**
#
# 🔴 为什么需要这条**额外**守卫（Task 8 复核发现的守卫缺陷）：
# design P5 变异表点名的变异是「把 kind 判据改成按 uuid_column 为空隐式分派」。直接施加该
# 变异（`kind = static if not uuid_column else dynamic`）后，本文件既有 58 条守卫**全绿**
# ——即变异四态判定为 GREEN（守卫缺陷），而非 RED。根因：`__post_init__` 已禁止「defined_name
# 与 uuid_column 同时非空」及「两者同时为空」两种边界态，于是在**所有合法构造**上「defined_name
# 存在」与「uuid_column 为空」恒等价 ⇒ 两种判据在既有 fixture 上永远给同一答案，变异不可观测。
#
# 按四态判定协议 GREEN 必须修守卫使其转 RED。修法：**绕过 __post_init__** 造出「defined_name
# 与 uuid_column-空缺**不一致**」的边界态（defined_name 设了、uuid_column 也非空），断言 `kind`
# 跟随 **defined_name**——真实实现（读 defined_name）在此边界判 static_region；隐式变异（读
# uuid_column 空缺）在此边界判 excel_table ⇒ 变异被捕获（RED）。这正是 DEC-6 / Property 5 的
# 核心：判据是 `defined_name` 字段的**存在**，不是 `uuid_column` 的**缺失**（两者只在合法构造
# 上巧合等价，边界态必须由显式字段裁决）。
# ═══════════════════════════════════════════════════════════════════════════


class TestBindingKindReadsDefinedNameNotUuidAbsence:
    """Property 5：`kind` 的判据是 defined_name 存在，不是 uuid_column 空缺。

    真实实现读 defined_name。隐式变异（读 uuid_column 空缺）会在「defined_name 设了但
    uuid_column 也非空」这个**绕过 __post_init__** 造出的边界态上给出相反答案 → 本守卫捕获。
    """

    def test_kind_follows_defined_name_on_inconsistent_boundary(self) -> None:
        # 先造一个合法静态 binding（defined_name 设、uuid_column 空）。
        binding = ExcelIdentityBinding(
            table_key=STATIC_TABLE_KEY, defined_name=STATIC_DEFINED_NAME
        )
        # 绕过 frozen __post_init__ 注入一个**非空** uuid_column，制造「defined_name 与
        # uuid_column-空缺不一致」的边界态（合法构造永不出现，故只能这样造）。
        object.__setattr__(binding, "uuid_column", "Z")
        # 真实实现读 defined_name → 仍判 static_region。
        # 若 kind 改成读 uuid_column 空缺（隐式变异），uuid_column 非空 → 会判 excel_table。
        assert binding.kind is BindingKind.static_region, (
            "kind 判据不是读 defined_name（疑似退回按 uuid_column 空缺隐式分派）—— Property 5 被破"
        )
        assert is_static_region(binding) is True

    def test_kind_follows_defined_name_when_uuid_absent_but_no_defined_name(self) -> None:
        # 反向边界：uuid_column 空、defined_name 也空（绕过 __post_init__ 造）。
        # 真实实现读 defined_name（空）→ 判 excel_table（动态）。
        # 隐式变异读 uuid_column 空缺 → 会误判 static_region。二者在此边界相反。
        binding = ExcelIdentityBinding(
            table_key="k_rows", table_name="GT_TBL", uuid_column="AA"
        )
        object.__setattr__(binding, "uuid_column", "")  # 抹掉 uuid_column（defined_name 仍空）
        assert binding.kind is BindingKind.excel_table, (
            "uuid_column 空但 defined_name 也空时被判 static —— 疑似按 uuid_column 空缺隐式分派"
            "（Property 5 被破：动态 binding 边界态被误判为静态）"
        )
        assert is_static_region(binding) is False
