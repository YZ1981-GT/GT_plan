# -*- coding: utf-8 -*-
"""D4-5 production-path roundtrip — materialize → extract → merge.

spec: d-cycle-sheet-bidirectional-expansion · D4-5 paragraph_block_bidirectional
Uses real ``parse_contract → build_excel_adapter → materialize → extract →
merge_projection_into_d45_*`` on the triple-sheet instrumented D4 template.
"""
from __future__ import annotations

import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

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
from app.services.workpaper_sync.adapters import excel as AX  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
from app.services.workpaper_sync.excel_entry_gate import (  # noqa: E402
    AdapterBuild,
    FrozenEntryDefinitions,
    parse_identity_inventory,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.phase5_d4_policy_check_sheet import (  # noqa: E402
    FIRST_DATA_ROW_D45_GROUPS,
    FIXED_FIELD_SPECS_D45,
    HTML_ONLY_ITEM_IDS_D45,
    MANAGED_FIELD_SPECS_D45_GROUPS,
    ROW_IDENTITY_STORE_KEY_D45,
    ROWS_TABLE_KEY_D45,
    STORE_ITEM_ID_D45_GROUPS,
    STORE_ITEM_IDS_D45_FIXED,
    TABLE_NAME_D45,
    UUID_COL_D45,
    merge_projection_into_d45_fixed_items,
    merge_projection_into_d45_group_rows,
    stable_key_for_d45_fixed,
    stable_key_for_d45_group,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_bundle(contract: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d45-roundtrip-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d45-roundtrip-authority"),
        slots={
            BundleSlot.template: slot(
                BundleSlot.template, contract.template_definition_sha256
            ),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )


def make_definitions(
    contract: Any, inventory_raw: Mapping[str, Any]
) -> FrozenEntryDefinitions:
    return FrozenEntryDefinitions(
        entry_id=D4.ENTRY_ID,
        bundle=make_bundle(contract),
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=D4.ADAPTER_ID,
            adapter_build_digest=_d("d45-roundtrip-adapter-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inventory_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


BINDING_D45 = X.ExcelIdentityBinding(
    table_name=TABLE_NAME_D45,
    uuid_column=UUID_COL_D45,
    table_key=ROWS_TABLE_KEY_D45,
)


@pytest.fixture(scope="module")
def instrumented() -> EI.InstrumentedWorkbook:
    source = D4.read_authoritative_template()
    gate = D4.excel_carrier_gate()
    return EI.instrument_workbook_bytes_multi(
        source, D4.instrumentation_specs(), gate=gate
    )


@pytest.fixture(scope="module")
def contract() -> Any:
    D4.assert_mapping_digest()
    D4.assert_contract_file_matches_source()
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


@pytest.fixture(scope="module")
def definitions(contract: Any, instrumented: EI.InstrumentedWorkbook):
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=TABLE_NAME_D45,
        uuid_column_letter=UUID_COL_D45,
    )
    return make_definitions(contract, inv)


@pytest.fixture(scope="module")
def seed_uuids(instrumented: EI.InstrumentedWorkbook) -> tuple[str, str]:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=TABLE_NAME_D45,
        uuid_column_letter=UUID_COL_D45,
    )
    uuids = inv["hidden_uuid_column"]["row_uuids"]
    r0 = uuids.get(str(FIRST_DATA_ROW_D45_GROUPS)) or uuids.get(FIRST_DATA_ROW_D45_GROUPS)
    r1 = uuids.get(str(FIRST_DATA_ROW_D45_GROUPS + 1)) or uuids.get(
        FIRST_DATA_ROW_D45_GROUPS + 1
    )
    assert r0 and r1, f"D4-5 seed UUIDs missing: {uuids}"
    return str(r0), str(r1)


@pytest.fixture
def base_path(instrumented: EI.InstrumentedWorkbook, tmp_path: Path) -> Path:
    path = tmp_path / "d45-base.xlsx"
    path.write_bytes(instrumented.instrumented_bytes)
    return path


def _sample_groups(rid0: str, rid1: str) -> list[dict[str, Any]]:
    return [
        {
            ROW_IDENTITY_STORE_KEY_D45: rid0,
            "bizName": "销售商品收入",
            "revenuePolicy": "rp-a",
            "industryPolicy": "ip-a",
            "rationalityAnalysis": "ra-a",
        },
        {
            ROW_IDENTITY_STORE_KEY_D45: rid1,
            "bizName": "贸易业务",
            "revenuePolicy": "rp-b",
            "industryPolicy": "ip-b",
            "rationalityAnalysis": "ra-b",
        },
    ]


class TestD45ProductionRoundtrip:
    def test_footer_below_statics_are_html_only(self) -> None:
        excel_items = {spec[3] for spec in FIXED_FIELD_SPECS_D45}
        assert excel_items == set(STORE_ITEM_IDS_D45_FIXED)
        assert set(HTML_ONLY_ITEM_IDS_D45).isdisjoint(excel_items)

    def test_materialize_extract_merge_seed_groups_and_biz(
        self,
        contract: Any,
        definitions: FrozenEntryDefinitions,
        base_path: Path,
        seed_uuids: tuple[str, str],
        tmp_path: Path,
    ) -> None:
        rid0, rid1 = seed_uuids
        groups = _sample_groups(rid0, rid1)
        fixed = {item: f"biz-{item}" for item in STORE_ITEM_IDS_D45_FIXED}
        projection = D4.build_combined_store_projection(
            {
                D4.STORE_ITEM_ID: [],
                "D4-3-rows": [],
                STORE_ITEM_ID_D45_GROUPS: groups,
                **fixed,
            },
            contract=contract,
        )
        assert projection.row_keys[ROWS_TABLE_KEY_D45] == (rid0, rid1)
        assert len(projection.values) >= 4 * 2 + 6  # groups fields + biz fixed

        adapter = AX.build_excel_adapter(
            definitions=definitions, binding=BINDING_D45, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "d45-staged.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path,
            projection=projection,
            output=staged,
            contract=definitions.contract,
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK"
        assert result.managed_field_count >= 14

        extracted = adapter.extract(artifact=staged, contract=definitions.contract)
        for column_key, _c, _m, _vt, json_path, _h in MANAGED_FIELD_SPECS_D45_GROUPS:
            for rid, row in ((rid0, groups[0]), (rid1, groups[1])):
                sk = stable_key_for_d45_group(column_key, rid)
                fv = extracted.get(sk)
                assert fv is not None, f"extract missing {sk}"
                assert str(fv.value) == str(row[json_path])

        for column_key, _col, _row, store_item in FIXED_FIELD_SPECS_D45:
            sk = stable_key_for_d45_fixed(column_key)
            fv = extracted.get(sk)
            assert fv is not None, f"extract missing fixed {sk}"
            assert str(fv.value) == fixed[store_item]

        merged, applied, visited, touched = merge_projection_into_d45_group_rows(
            projection=extracted,
            base_rows=[
                {ROW_IDENTITY_STORE_KEY_D45: rid0, "bizName": ""},
                {ROW_IDENTITY_STORE_KEY_D45: rid1, "bizName": ""},
            ],
        )
        assert visited >= 8 and applied >= 8
        assert {rid0, rid1} <= touched
        by_id = {str(r[ROW_IDENTITY_STORE_KEY_D45]): r for r in merged}
        assert by_id[rid0]["bizName"] == "销售商品收入"
        assert by_id[rid1]["rationalityAnalysis"] == "ra-b"

        fixed_out = merge_projection_into_d45_fixed_items(
            projection=extracted,
            base_by_item={k: "" for k in STORE_ITEM_IDS_D45_FIXED},
        )
        assert fixed_out["D4-5-biz-scene"] == fixed["D4-5-biz-scene"]

    def test_insert_third_group_does_not_hit_static_below_insertion(
        self,
        contract: Any,
        definitions: FrozenEntryDefinitions,
        base_path: Path,
        seed_uuids: tuple[str, str],
        tmp_path: Path,
    ) -> None:
        rid0, rid1 = seed_uuids
        rid2 = str(uuid.uuid4())
        groups = _sample_groups(rid0, rid1) + [
            {
                ROW_IDENTITY_STORE_KEY_D45: rid2,
                "bizName": "第三组",
                "revenuePolicy": "rp-c",
                "industryPolicy": "ip-c",
                "rationalityAnalysis": "ra-c-marker",
            }
        ]
        projection = D4.build_combined_store_projection(
            {
                D4.STORE_ITEM_ID: [],
                "D4-3-rows": [],
                STORE_ITEM_ID_D45_GROUPS: groups,
                **{item: "x" for item in STORE_ITEM_IDS_D45_FIXED},
            },
            contract=contract,
        )
        adapter = AX.build_excel_adapter(
            definitions=definitions, binding=BINDING_D45, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "d45-insert.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path,
            projection=projection,
            output=staged,
            contract=definitions.contract,
        )
        assert result.managed_field_count >= 18
        extracted = adapter.extract(artifact=staged, contract=definitions.contract)
        sk = stable_key_for_d45_group("biz_name", rid2)
        fv = extracted.get(sk)
        assert fv is not None
        assert str(fv.value) == "第三组"
