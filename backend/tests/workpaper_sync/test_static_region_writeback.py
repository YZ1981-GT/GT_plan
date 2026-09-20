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
