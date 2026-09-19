# -*- coding: utf-8 -*-
"""D4-3 production-path roundtrip — materialize → extract → merge.

spec: d-cycle-sheet-bidirectional-expansion · Task 2
Must use real ``parse_contract → build_excel_adapter → materialize → extract →
merge_projection_into_d43_store_rows`` on the dual-sheet instrumented D4 template.
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
from app.services.workpaper_sync.phase5_d4_other_revenue_sheet import (  # noqa: E402
    FIRST_DATA_ROW_D43,
    MANAGED_FIELD_SPECS_D43,
    ROW_IDENTITY_STORE_KEY_D43,
    ROWS_TABLE_KEY_D43,
    STORE_ITEM_ID_D43,
    TABLE_NAME_D43,
    UUID_COL_D43,
    merge_projection_into_d43_store_rows,
    stable_key_for_d43,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_bundle(contract: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d43-roundtrip-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d43-roundtrip-authority"),
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
            adapter_build_digest=_d("d43-roundtrip-adapter-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inventory_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


BINDING_D43 = X.ExcelIdentityBinding(
    table_name=TABLE_NAME_D43,
    uuid_column=UUID_COL_D43,
    table_key=ROWS_TABLE_KEY_D43,
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
        expected_table=TABLE_NAME_D43,
        uuid_column_letter=UUID_COL_D43,
    )
    return make_definitions(contract, inv)


@pytest.fixture(scope="module")
def d43_row_uuid(instrumented: EI.InstrumentedWorkbook) -> str:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=TABLE_NAME_D43,
        uuid_column_letter=UUID_COL_D43,
    )
    uuids = inv["hidden_uuid_column"]["row_uuids"]
    rid = uuids.get(str(FIRST_DATA_ROW_D43)) or uuids.get(FIRST_DATA_ROW_D43)
    assert rid, f"D4-3 row {FIRST_DATA_ROW_D43} missing UUID: {uuids}"
    return str(rid)


@pytest.fixture
def base_path(instrumented: EI.InstrumentedWorkbook, tmp_path: Path) -> Path:
    path = tmp_path / "d43-base.xlsx"
    path.write_bytes(instrumented.instrumented_bytes)
    return path


def _sample_store_row(row_uuid: str) -> dict[str, Any]:
    return {
        ROW_IDENTITY_STORE_KEY_D43: row_uuid,
        "item": "出租固定资产",
        "currentUnadjusted": 1200.5,
        "currentAdjustment": -10.0,
        "priorUnadjusted": 980.25,
        "priorAdjustment": 5.5,
        "remark": "g5d43-roundtrip",
    }


class TestD43ProductionRoundtrip:
    def test_materialize_extract_merge_six_fields(
        self,
        contract: Any,
        definitions: FrozenEntryDefinitions,
        base_path: Path,
        d43_row_uuid: str,
        tmp_path: Path,
    ) -> None:
        store_row = _sample_store_row(d43_row_uuid)
        projection = D4.build_d43_store_projection([store_row], contract=contract)
        assert len(projection.values) == 6
        assert projection.row_keys[ROWS_TABLE_KEY_D43] == (d43_row_uuid,)

        adapter = AX.build_excel_adapter(
            definitions=definitions, binding=BINDING_D43, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "d43-staged.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        result = adapter.materialize(
            substrate=base_path,
            projection=projection,
            output=staged,
            contract=definitions.contract,
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK"
        assert result.managed_field_count == 6

        extracted = adapter.extract(artifact=staged, contract=definitions.contract)
        for column_key, _col, _mode, _vt, json_path, _hdr in MANAGED_FIELD_SPECS_D43:
            sk = stable_key_for_d43(column_key, d43_row_uuid)
            fv = extracted.get(sk)
            assert fv is not None, f"extract missing {sk}"
            expected = store_row[json_path]
            if _vt == "amount":
                assert float(fv.value) == float(expected)
            else:
                assert str(fv.value) == str(expected)

        # Formula / reclass columns must not appear as editable projection keys.
        for sk in extracted.stable_keys():
            if not str(sk).startswith(f"{ROWS_TABLE_KEY_D43}/"):
                continue
            field_id = str(sk).rsplit("/", 1)[-1]
            assert field_id in {s[0] for s in MANAGED_FIELD_SPECS_D43}

        base_for_merge = [
            {
                ROW_IDENTITY_STORE_KEY_D43: d43_row_uuid,
                "item": "",
                "currentUnadjusted": 0,
                "currentAdjustment": 0,
                "priorUnadjusted": 0,
                "priorAdjustment": 0,
                "remark": "",
            }
        ]
        merged, applied, visited, touched = merge_projection_into_d43_store_rows(
            projection=extracted, base_rows=base_for_merge
        )
        # extract 会带回同表其它物理行的模板值；至少本行 6 字段必须被 visit/apply。
        assert visited >= 6 and applied >= 6
        assert d43_row_uuid in touched
        by_id = {str(r[ROW_IDENTITY_STORE_KEY_D43]): r for r in merged}
        out = by_id[d43_row_uuid]
        assert out["item"] == store_row["item"]
        assert float(out["currentUnadjusted"]) == store_row["currentUnadjusted"]
        assert float(out["currentAdjustment"]) == store_row["currentAdjustment"]
        assert float(out["priorUnadjusted"]) == store_row["priorUnadjusted"]
        assert float(out["priorAdjustment"]) == store_row["priorAdjustment"]
        assert out["remark"] == store_row["remark"]

    def test_combined_merge_isolates_d43_from_d42(
        self, contract: Any, d43_row_uuid: str
    ) -> None:
        """Dual-store merge must only touch D4-3-rows for other_revenue keys."""
        store_row = _sample_store_row(d43_row_uuid)
        projection = D4.build_combined_store_projection(
            {
                D4.STORE_ITEM_ID: [],
                STORE_ITEM_ID_D43: [store_row],
            },
            contract=contract,
        )
        updates = D4.merge_projection_into_all_d4_stores(
            projection=projection,
            base_by_item={
                D4.STORE_ITEM_ID: [],
                STORE_ITEM_ID_D43: [
                    {
                        ROW_IDENTITY_STORE_KEY_D43: d43_row_uuid,
                        "item": "old",
                        "currentUnadjusted": 0,
                        "currentAdjustment": 0,
                        "priorUnadjusted": 0,
                        "priorAdjustment": 0,
                        "remark": "",
                    }
                ],
            },
        )
        d42_rows, d42_applied, *_ = updates[D4.STORE_ITEM_ID]
        d43_rows, d43_applied, d43_visited, _ = updates[STORE_ITEM_ID_D43]
        assert d42_rows == [] and d42_applied == 0
        assert d43_visited == 6 and d43_applied == 6
        assert d43_rows[0]["item"] == "出租固定资产"
        assert d43_rows[0]["remark"] == "g5d43-roundtrip"
