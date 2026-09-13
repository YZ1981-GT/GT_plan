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
