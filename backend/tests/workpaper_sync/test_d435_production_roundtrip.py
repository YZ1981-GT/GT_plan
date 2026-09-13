# -*- coding: utf-8 -*-
"""D4-35 生产路径 roundtrip —— materialize → extract → merge（真实 instrumented D4 模板）。

spec: d4-33-36-writeback-formula-and-io-closure · Wave 3（双向回写）
照抄 test_d45_production_roundtrip.py 范式，验证 D4-35 均质行双向回写端到端：
- instrument_workbook_bytes_multi(含 D4-35 spec) 注入不抛错（UUID 列 R / Table GT_D435_ROWS）
- build_combined_store_projection 把 D4-35 rows 投影进 other_revenue_check_rows/*
- materialize → extract 往返后录入字段逐字段一致
- merge_d435_from_projection 保留 sampling/periodAmount（Property 3 回写侧）
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
from app.services.workpaper_sync.phase5_d4_other_check_sheet import (  # noqa: E402
    FIRST_DATA_ROW_D435,
    MANAGED_FIELD_SPECS_D435,
    ROWS_TABLE_KEY_D435,
    ROW_IDENTITY_STORE_KEY_D435,
    STORE_ITEM_ID_D435,
    TABLE_NAME_D435,
    UUID_COL_D435,
    merge_projection_into_d435_store_rows,
    stable_key_for_d435,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_bundle(contract: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d435-roundtrip-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d435-roundtrip-authority"),
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
            adapter_build_digest=_d("d435-roundtrip-adapter-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inventory_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


BINDING_D435 = X.ExcelIdentityBinding(
    table_name=TABLE_NAME_D435,
    uuid_column=UUID_COL_D435,
    table_key=ROWS_TABLE_KEY_D435,
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
        expected_table=TABLE_NAME_D435,
        uuid_column_letter=UUID_COL_D435,
    )
    return make_definitions(contract, inv)


@pytest.fixture(scope="module")
def seed_uuids(instrumented: EI.InstrumentedWorkbook) -> tuple[str, str]:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=TABLE_NAME_D435,
        uuid_column_letter=UUID_COL_D435,
    )
    uuids = inv["hidden_uuid_column"]["row_uuids"]
    r0 = uuids.get(str(FIRST_DATA_ROW_D435)) or uuids.get(FIRST_DATA_ROW_D435)
    r1 = uuids.get(str(FIRST_DATA_ROW_D435 + 1)) or uuids.get(FIRST_DATA_ROW_D435 + 1)
    assert r0 and r1, f"D4-35 seed UUIDs missing: {uuids}"
    return str(r0), str(r1)


@pytest.fixture
def base_path(instrumented: EI.InstrumentedWorkbook, tmp_path: Path) -> Path:
    path = tmp_path / "d435-base.xlsx"
    path.write_bytes(instrumented.instrumented_bytes)
    return path


def _sample_rows(rid0: str, rid1: str) -> list[dict[str, Any]]:
    return [
        {
            ROW_IDENTITY_STORE_KEY_D435: rid0,
            "date": "2024-03-01", "voucherNo": "PZ-1", "content": "材料销售",
            "counterAccount": "银行存款", "detailAccount": "其他业务收入",
            "amount": 12000.0, "supportDoc": "发票",
            "check1": "√", "check2": "√", "check3": "", "check4": "√", "check5": "", "check6": "",
            "indexRef": "IX-1", "isAnomalous": "是", "remark": "大额",
        },
        {
            ROW_IDENTITY_STORE_KEY_D435: rid1,
            "date": "2024-03-02", "voucherNo": "PZ-2", "content": "废料处置",
            "counterAccount": "应收账款", "detailAccount": "其他业务收入",
            "amount": 3400.0, "supportDoc": "合同",
            "check1": "√", "check2": "", "check3": "√", "check4": "√", "check5": "", "check6": "",
            "indexRef": "IX-2", "isAnomalous": "否", "remark": "",
        },
    ]


class TestD435ProductionRoundtrip:
    def test_instrument_injects_d435_table_and_uuid_column(
        self, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        """instrument 对 D4-35 sheet 注入 Table + UUID 列成功（多 sheet 注入不抛错）。"""
        inv = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=TABLE_NAME_D435,
            uuid_column_letter=UUID_COL_D435,
        )
        assert inv["hidden_uuid_column"]["row_uuids"], "D4-35 未注入 UUID 行"

    def test_materialize_extract_merge_roundtrip(
        self,
        contract: Any,
        definitions: FrozenEntryDefinitions,
        base_path: Path,
        seed_uuids: tuple[str, str],
        tmp_path: Path,
    ) -> None:
        rid0, rid1 = seed_uuids
        rows = _sample_rows(rid0, rid1)
        projection = D4.build_combined_store_projection(
            {
                D4.STORE_ITEM_ID: [],
                "D4-3-rows": [],
                STORE_ITEM_ID_D435: {"rows": rows, "sampling": {"sampleSize": "2"}, "periodAmount": "50000"},
            },
            contract=contract,
        )
        assert projection.row_keys[ROWS_TABLE_KEY_D435] == (rid0, rid1)

        adapter = AX.build_excel_adapter(
            definitions=definitions, binding=BINDING_D435, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "d435-staged.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        adapter.materialize(
            substrate=base_path,
            projection=projection,
            output=staged,
            contract=definitions.contract,
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK"

        extracted = adapter.extract(artifact=staged, contract=definitions.contract)
        for column_key, _c, _m, value_type, json_path, _h in MANAGED_FIELD_SPECS_D435:
            for rid, row in ((rid0, rows[0]), (rid1, rows[1])):
                sk = stable_key_for_d435(column_key, rid)
                fv = extracted.get(sk)
                assert fv is not None, f"extract missing {sk}"
                expected = row[json_path]
                if value_type == "amount":
                    # 金额往返数值比较（Excel 会把 12000.0 规范化为 12000）
                    assert float(fv.value or 0) == float(expected or 0), f"{sk}: {fv.value!r} != {expected!r}"
                else:
                    assert str(fv.value) == str(expected), f"{sk}: {fv.value!r} != {expected!r}"

    def test_merge_preserves_sampling_and_period_amount(
        self,
        contract: Any,
        definitions: FrozenEntryDefinitions,
        base_path: Path,
        seed_uuids: tuple[str, str],
        tmp_path: Path,
    ) -> None:
        """OO→HTML 回读：merge_d435_from_projection 保留 sampling/periodAmount（Property 3）。"""
        rid0, rid1 = seed_uuids
        rows = _sample_rows(rid0, rid1)
        projection = D4.build_combined_store_projection(
            {
                D4.STORE_ITEM_ID: [],
                "D4-3-rows": [],
                STORE_ITEM_ID_D435: {"rows": rows, "sampling": {}, "periodAmount": ""},
            },
            contract=contract,
        )
        adapter = AX.build_excel_adapter(
            definitions=definitions, binding=BINDING_D435, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "d435-merge.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        adapter.materialize(
            substrate=base_path, projection=projection, output=staged, contract=definitions.contract
        )
        extracted = adapter.extract(artifact=staged, contract=definitions.contract)

        merged, applied, _visited = D4.merge_d435_from_projection(
            projection=extracted,
            base_state={
                "rows": [
                    {ROW_IDENTITY_STORE_KEY_D435: rid0},
                    {ROW_IDENTITY_STORE_KEY_D435: rid1},
                ],
                "sampling": {"sampleSize": "99", "samplingMethod": "货币单元抽样"},
                "periodAmount": "888888",
            },
        )
        assert applied >= 8
        # 关键：sampling / periodAmount 不被 OO 回读冲掉
        assert merged["sampling"] == {"sampleSize": "99", "samplingMethod": "货币单元抽样"}
        assert merged["periodAmount"] == "888888"
        by_id = {str(r[ROW_IDENTITY_STORE_KEY_D435]): r for r in merged["rows"]}
        assert by_id[rid0]["voucherNo"] == "PZ-1"
        assert by_id[rid0]["isAnomalous"] == "是"
        assert by_id[rid1]["content"] == "废料处置"
