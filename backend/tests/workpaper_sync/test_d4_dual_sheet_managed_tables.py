# -*- coding: utf-8 -*-
"""D4 dual-sheet (D4-2 + D4-3) — managed_tables_of scope + multi-instrument smoke.

spec: d-cycle-sheet-bidirectional-expansion · Tasks 2–3
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.phase5_d4_other_revenue_sheet import (  # noqa: E402
    EXPECTED_MAPPING_DIGEST_D43,
    TABLE_NAME_D43,
    TEMPLATE_ID_D43,
    assert_mapping_digest_d43,
)


def test_mapping_digests_both_sheets_locked() -> None:
    assert D4.assert_mapping_digest() == D4.EXPECTED_MAPPING_DIGEST
    assert assert_mapping_digest_d43() == EXPECTED_MAPPING_DIGEST_D43
    from app.services.workpaper_sync.phase5_d4_policy_check_sheet import (
        EXPECTED_MAPPING_DIGEST_D45,
        assert_mapping_digest_d45,
    )

    assert assert_mapping_digest_d45() == EXPECTED_MAPPING_DIGEST_D45


def test_managed_tables_of_succeeds_with_two_sheets_binding_d42() -> None:
    """契约含 d42 + d43 (+ d45) 时，binding 指向 d42 不得因 sibling 被拒。"""
    payload = D4.build_contract_payload()
    assert len(payload["sheets"]) >= 2
    sheet_keys = {s["sheet_key"] for s in payload["sheets"]}
    assert {"d42-managed", "d43-managed"} <= sheet_keys
    assert "d45-managed" in sheet_keys

    from app.services.workpaper_sync.contracts import parse_contract

    contract = parse_contract(payload, adapter_id=D4.ADAPTER_ID)
    binding = X.ExcelIdentityBinding(
        table_name=D4.TABLE_NAME,
        uuid_column=D4.UUID_COL,
        table_key=D4.ROWS_TABLE_KEY,
    )
    dynamic, statics = X.managed_tables_of(contract, binding=binding)
    assert dynamic.table_key == D4.ROWS_TABLE_KEY
    assert statics == ()


def test_instrumentation_payload_lists_both_managed_sheets() -> None:
    payload = D4.instrumentation_definition_payload()
    keys = [s["sheet_key"] for s in payload["managed_sheets"]]
    assert keys[:2] == ["d42-managed", "d43-managed"]
    assert "d45-managed" in keys
    assert f"GT_MANAGED_REGION_{D4.TEMPLATE_ID}" in payload["defined_names"]
    assert f"GT_MANAGED_REGION_{TEMPLATE_ID_D43}" in payload["defined_names"]
    assert payload["hidden_metadata_sheet"]["managed_sheet_keys"] == keys


def test_multi_instrument_clean_d4_template_defines_both_regions() -> None:
    """干净 D4 模板一次注入多张受管 sheet；defined name + table part 均存在。"""
    import io
    import zipfile

    from app.services.workpaper_sync.phase5_d4_policy_check_sheet import TEMPLATE_ID_D45

    source = D4.read_authoritative_template()
    gate = D4.excel_carrier_gate()
    specs = D4.instrumentation_specs()
    inst = EI.instrument_workbook_bytes_multi(source, specs, gate=gate)

    assert f"GT_MANAGED_REGION_{D4.TEMPLATE_ID}" in inst.defined_name_refs
    assert f"GT_MANAGED_REGION_{TEMPLATE_ID_D43}" in inst.defined_name_refs
    assert f"GT_MANAGED_REGION_{TEMPLATE_ID_D45}" in inst.defined_name_refs
    assert f"GT_FOOTER_ANCHOR_{TEMPLATE_ID_D43}" in inst.defined_name_refs
    keys = inst.gt_sync_pairs.get("GT_MANAGED_SHEET_KEYS", "")
    assert "d42-managed" in keys and "d43-managed" in keys and "d45-managed" in keys
    assert TABLE_NAME_D43 in inst.gt_sync_pairs.get("GT_MANAGED_TABLES", "")
    assert inst.gt_sync_pairs.get("GT_FOOTER_ROW_D42") == str(D4.FOOTER_ROW)
    assert inst.gt_sync_pairs.get("GT_FOOTER_ROW_D43") == "20"

    with zipfile.ZipFile(io.BytesIO(inst.instrumented_bytes)) as zf:
        names = set(zf.namelist())
    assert "xl/tables/tableGtRowId.xml" in names  # primary historical
    assert f"xl/tables/tableGtRowId_{TEMPLATE_ID_D43}.xml" in names
    assert f"xl/tables/tableGtRowId_{TEMPLATE_ID_D45}.xml" in names

    inv_d42 = identity_inventory(
        inst.instrumented_bytes,
        expected_table=D4.TABLE_NAME,
        uuid_column_letter=D4.UUID_COL,
    )
    assert inv_d42["excel_table"]["present"] is True
    assert f"GT_MANAGED_REGION_{D4.TEMPLATE_ID}" in inv_d42["defined_name"]["names"]
    assert f"GT_MANAGED_REGION_{TEMPLATE_ID_D43}" in inv_d42["defined_name"]["names"]

    inv_d43 = identity_inventory(
        inst.instrumented_bytes,
        expected_table=TABLE_NAME_D43,
        uuid_column_letter="O",
    )
    assert inv_d43["excel_table"]["present"] is True
    assert inv_d43["excel_table"]["table_ref"].startswith("A13:O")


# ═══════════════════════════════════════════════════════════════════════════
# 回归：多 sheet 契约下 _plan_row_shift 必须按 region.table_key 取本表 footer
#
# spec: oo-html-writeback-performance（附带修复）/ 真实缺陷复现
#
# 缺陷形态（真实 D4-29 编辑触发，materialize 500 `footer_formula_range_stale`）：
# `_plan_row_shift` 组装 `total_formula_rows` 时，
#   ① anchor 取「跨全部 sheet 的第一张 footer 表」= combined 契约里恒是 primary D4-2；
#   ② frozen row 取裸主键 `GT_FOOTER_ROW` = primary sheet 的行（31）。
# 于是给 sibling 表 D4-23（footer 在 24 行）算扩张时，`total_formula_rows` 塞进 31，
# `shift_sheet_rows` 的 `is_total_row = block.row in {31}` 对 24 行主格恒假 ⇒ 合计公式
# 不扩张 ⇒ 位移后 footer 落在 36 行、公式仍 stale `SUM(B12:B23)` ⇒ apply-phase gate 打红。
#
# 修复 = 用 `region.table_key` 定位本表 footer_anchor + `_resolve_frozen_footer_row(
# sheet_key=...)` 取本表 `GT_FOOTER_ROW_{TID}`。本组判据钉死两半，且证明旧路径会取错值。
# ═══════════════════════════════════════════════════════════════════════════


def _d4_contract():
    from app.services.workpaper_sync.contracts import parse_contract

    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


def test_sibling_table_resolves_its_own_sheet_key_not_primary() -> None:
    """D4-23（invoice_compare_rows）的 sheet_key 必须解析到 `d423-managed`，不是主 sheet。"""
    from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import (
        ROWS_TABLE_KEY_D423,
        SHEET_KEY_D423,
    )

    contract = _d4_contract()
    sheet_key = M._sheet_key_for_table(contract, ROWS_TABLE_KEY_D423)
    assert sheet_key == SHEET_KEY_D423, sheet_key
    # primary（D4-2）的 sheet_key 与它不同 —— 否则本判据空转。
    primary_sheet_key = M._sheet_key_for_table(contract, D4.ROWS_TABLE_KEY)
    assert primary_sheet_key != sheet_key, (primary_sheet_key, sheet_key)


def test_frozen_footer_row_picks_sibling_template_key_over_bare_primary() -> None:
    """runtime binding 里 bare `GT_FOOTER_ROW`（primary 31）≠ `GT_FOOTER_ROW_D423`（24）时，
    按 sibling sheet_key 解析必须取 24；旧路径（裸主键）取 31 —— 那正是缺陷。"""
    from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import (
        FOOTER_ROW_D423,
        SHEET_KEY_D423,
    )

    # 故意让主键 = primary 的 footer 行（31），sibling 键 = D4-23 真实 footer（24）。
    runtime_binding = {
        "GT_FOOTER_ROW": "31",
        "GT_FOOTER_ROW_D42": "31",
        "GT_FOOTER_ROW_D423": str(FOOTER_ROW_D423),
    }
    resolved = M._resolve_frozen_footer_row(runtime_binding, sheet_key=SHEET_KEY_D423)
    assert resolved == str(FOOTER_ROW_D423) == "24", resolved
    # 🔴 非空证明：旧路径（不传 sheet_key，等价于裸主键）会取回 primary 的 31 —— 缺陷形态。
    bug_value = M._resolve_frozen_footer_row(runtime_binding, sheet_key=None)
    assert bug_value == "31", bug_value
    assert resolved != bug_value, "sheet_key 解析必须与裸主键分道，否则 sibling 扩张打错行"


def test_footer_anchor_selected_by_region_table_key_not_first_across_sheets() -> None:
    """anchor 必须按 `region.table_key` 取本表的，而不是「跨全部 sheet 第一张有 footer 的表」。

    combined D4 契约里第一张有 footer_anchor 的表恒是 primary（D4-2）。旧实现取第一张 ⇒
    给 D4-23 region 算扩张时用的是 D4-2 的 anchor。本判据证明按 table_key 取到的是 D4-23 自己。
    """
    from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import ROWS_TABLE_KEY_D423

    contract = _d4_contract()

    def _anchor_for(table_key: str):
        return next(
            (
                t.footer_anchor
                for s in contract.sheets
                for t in s.tables
                if t.table_key == table_key and t.footer_anchor is not None
            ),
            None,
        )

    def _first_anchor_across_sheets():  # 旧（错）实现
        return next(
            (
                t.footer_anchor
                for s in contract.sheets
                for t in s.tables
                if t.footer_anchor is not None
            ),
            None,
        )

    d423_anchor = _anchor_for(ROWS_TABLE_KEY_D423)
    primary_anchor = _anchor_for(D4.ROWS_TABLE_KEY)
    first_anchor = _first_anchor_across_sheets()

    assert d423_anchor is not None, "D4-23 应声明 footer_anchor"
    assert d423_anchor.carries_total_formula is True, "D4-23 footer 携带合计公式"
    # 旧实现的「第一张」= primary（D4-2），而不是 D4-23 —— 证明缺陷路径取错表。
    assert first_anchor is primary_anchor, "combined 契约第一张 footer 表应是 primary"
    assert d423_anchor is not first_anchor, (
        "按 region.table_key 取到的 D4-23 anchor 必须不同于「第一张」——"
        "否则本判据无法区分修复前后"
    )


def _instrumented_d4_entries() -> dict[str, bytes]:
    """把干净 D4 模板一次注入多受管 sheet，拆成 {zip part: bytes}。"""
    import io
    import zipfile

    source = D4.read_authoritative_template()
    gate = D4.excel_carrier_gate()
    specs = D4.instrumentation_specs()
    inst = EI.instrument_workbook_bytes_multi(source, specs, gate=gate)
    with zipfile.ZipFile(io.BytesIO(inst.instrumented_bytes)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def _sheet_part_of_name(entries: dict[str, bytes], sheet_name: str) -> str:
    import re

    wbxml = entries["xl/workbook.xml"].decode("utf-8")
    rels = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    # sheet 元素顺序里找 name==sheet_name 的 r:id
    order = re.findall(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wbxml)
    rid = next(r for n, r in order if n == sheet_name)
    target = re.search(rf'<Relationship[^>]*Id="{rid}"[^>]*Target="([^"]+)"', rels).group(1)
    return "xl/" + target if not target.startswith("/") else target[1:]


def test_plan_row_shift_extends_sibling_footer_not_primary() -> None:
    """🔴 端到端守卫（缺陷复现）：给 sibling D4-23 region 算插行计划时，

    `_plan_row_shift` 返回的 `total_formula_rows` 必须是 D4-23 自己的 footer 行（24），
    而不是 primary D4-2 的行（GT_FOOTER_ROW=31）。修复前此处返回 (31,) ⇒ 位移时
    D4-23 的 `SUM(B12:B23)` 不扩张 ⇒ apply-phase `footer_formula_range_stale`。
    """
    from app.services.workpaper_sync.excel_extract import (
        EmptyRowIdentityDisposition,
        ManagedRegion,
        RowIdentityScan,
    )
    from app.services.workpaper_sync.phase5_d4_ipo_related_sheets import (
        FIRST_DATA_ROW_D423,
        FOOTER_ROW_D423,
        LAST_DATA_ROW_D423,
        MANAGED_SHEET_D423,
        ROWS_TABLE_KEY_D423,
        TABLE_NAME_D423,
        UUID_COL_D423,
    )

    contract = _d4_contract()
    entries = _instrumented_d4_entries()
    sheet_part = _sheet_part_of_name(entries, MANAGED_SHEET_D423)

    # 12 个月份物理行 12-23（天然键），无 minted。
    row_identity_by_row = {
        r: f"{r - FIRST_DATA_ROW_D423 + 1}月"
        for r in range(FIRST_DATA_ROW_D423, LAST_DATA_ROW_D423 + 1)
    }
    scan = RowIdentityScan(
        table_key=ROWS_TABLE_KEY_D423,
        sheet_name=MANAGED_SHEET_D423,
        uuid_column=UUID_COL_D423,
        row_identity_by_row=row_identity_by_row,
        minted_by_row={},
        empty_rows=(),
        rows_by_identity={v: (k,) for k, v in row_identity_by_row.items()},
        reused_tombstones=(),
        disposition=EmptyRowIdentityDisposition.assign_new_id,
    )
    region = ManagedRegion(
        table_key=ROWS_TABLE_KEY_D423,
        table_name=TABLE_NAME_D423,
        sheet_name=MANAGED_SHEET_D423,
        sheet_part=sheet_part,
        table_ref=f"A{FIRST_DATA_ROW_D423}:{UUID_COL_D423}{LAST_DATA_ROW_D423}",
        first_row=FIRST_DATA_ROW_D423,
        last_row=LAST_DATA_ROW_D423,
        first_column="A",
        last_column=UUID_COL_D423,
        uuid_column=UUID_COL_D423,
    )
    # 🔴 runtime binding 里 bare 主键 = primary（31），sibling 键 = D4-23（24）。
    runtime_binding = {
        "GT_FOOTER_ROW": "31",
        "GT_FOOTER_ROW_D42": "31",
        f"GT_FOOTER_ROW_D423": str(FOOTER_ROW_D423),
    }
    plan, total_formula_rows, table_part, shifted_xml = M._plan_row_shift(
        orphan=["GTROW-D423-NEW-0001"],  # 1 个 orphan → 插 1 行
        contract=contract,
        region=region,
        scan=scan,
        substrate_entries=entries,
        runtime_binding=runtime_binding,
    )
    assert total_formula_rows == (FOOTER_ROW_D423,) == (24,), total_formula_rows
    # 🔴 缺陷值是 (31,)：证明修复真正改变了行为，而不是恰好巧合。
    assert total_formula_rows != (31,), "取到 primary 的 footer 行 = 缺陷未修"
    assert table_part.startswith("xl/tables/"), table_part
    # 干跑位移后的 XML 里，D4-23 footer 应位移到 25 行且合计区间扩张到 24。
    assert "SUM(B12:B24)" in shifted_xml, "sibling footer 合计公式未随插行扩张"
