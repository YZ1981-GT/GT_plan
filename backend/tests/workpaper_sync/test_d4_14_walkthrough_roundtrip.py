# -*- coding: utf-8 -*-
"""D4-14 穿行测试生产路径 roundtrip —— materialize → extract → merge（真实 instrumented D4 模板）。

spec: d4-14-walkthrough-writeback · Wave 5（守卫）· Property 2/3

照抄 test_d435_production_roundtrip.py 范式，验证 D4-14 单宽动态行 7 维嵌套双向回写端到端：
- instrument_workbook_bytes_multi(含 D4-14 spec) 注入不抛错（UUID 列 AL / Table GT_D414_ROWS）
- build_combined_store_projection 把 D4-14 交易行投影进 walkthrough_transactions/*（7 维嵌套读值）
- materialize → extract 往返后受管字段逐字段一致（Property 3）
- merge_projection_into_d414 回写受管 7 维字段，HTML-only 派生字段（month/accountingDate/
  consistencyScore/conclusion）逐字保留不被抹（Property 2）
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
from app.services.workpaper_sync.phase5_d4_14_occurrence import (  # noqa: E402
    FIRST_DATA_ROW_D414,
    MANAGED_FIELD_SPECS_D414,
    ROWS_TABLE_KEY_D414,
    ROW_IDENTITY_STORE_KEY_D414,
    STORE_ITEM_ID_D414,
    TABLE_NAME_D414,
    UUID_COL_D414,
    merge_projection_into_d414,
    stable_key_for_d414,
)
from app.services.workpaper_sync.json_path import resolve_json_path  # noqa: E402
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def make_bundle(contract: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d414-roundtrip-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d414-roundtrip-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )


def make_definitions(contract: Any, inventory_raw: Mapping[str, Any]) -> FrozenEntryDefinitions:
    return FrozenEntryDefinitions(
        entry_id=D4.ENTRY_ID,
        bundle=make_bundle(contract),
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=D4.ADAPTER_ID,
            adapter_build_digest=_d("d414-roundtrip-adapter-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inventory_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


BINDING_D414 = X.ExcelIdentityBinding(
    table_name=TABLE_NAME_D414,
    uuid_column=UUID_COL_D414,
    table_key=ROWS_TABLE_KEY_D414,
)


@pytest.fixture(scope="module")
def instrumented() -> EI.InstrumentedWorkbook:
    source = D4.read_authoritative_template()
    gate = D4.excel_carrier_gate()
    return EI.instrument_workbook_bytes_multi(source, D4.instrumentation_specs(), gate=gate)


@pytest.fixture(scope="module")
def contract() -> Any:
    D4.assert_contract_file_matches_source()
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


@pytest.fixture(scope="module")
def definitions(contract: Any, instrumented: EI.InstrumentedWorkbook):
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=TABLE_NAME_D414,
        uuid_column_letter=UUID_COL_D414,
    )
    return make_definitions(contract, inv)


@pytest.fixture(scope="module")
def seed_uuids(instrumented: EI.InstrumentedWorkbook) -> tuple[str, str]:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=TABLE_NAME_D414,
        uuid_column_letter=UUID_COL_D414,
    )
    uuids = inv["hidden_uuid_column"]["row_uuids"]
    r0 = uuids.get(str(FIRST_DATA_ROW_D414)) or uuids.get(FIRST_DATA_ROW_D414)
    r1 = uuids.get(str(FIRST_DATA_ROW_D414 + 1)) or uuids.get(FIRST_DATA_ROW_D414 + 1)
    assert r0 and r1, f"D4-14 seed UUIDs missing: {uuids}"
    return str(r0), str(r1)


@pytest.fixture
def base_path(instrumented: EI.InstrumentedWorkbook, tmp_path: Path) -> Path:
    path = tmp_path / "d414-base.xlsx"
    path.write_bytes(instrumented.instrumented_bytes)
    return path


def _sample_tx(rid0: str, rid1: str) -> list[dict[str, Any]]:
    """两笔穿行交易，7 维全填 + HTML-only 派生字段（month/accountingDate/consistencyScore/conclusion）。"""
    def mk(rid: str, seq: int) -> dict[str, Any]:
        s = str(seq)
        return {
            "id": rid, "indexNo": f"D4-14-{seq}", "label": f"事项{seq}",
            "voucher": {"month": s, "customerName": f"客户{seq}", "date": f"2024-0{seq}-01",
                        "number": f"PZ-{seq}", "productName": f"产品{seq}", "quantity": "10",
                        "amount": 5000.0 * seq, "accountingDate": f"2024-0{seq}-02"},
            "contract": {"date": f"2024-0{seq}-05", "number": f"HT-{seq}", "productName": f"产品{seq}",
                         "amount": 5000.0 * seq, "approver": "张三", "confirmor": "李四"},
            "delivery": {"date": f"2024-0{seq}-06", "number": f"CK-{seq}", "productName": f"产品{seq}",
                         "quantity": "10", "amount": 5000.0 * seq, "warehouseKeeper": "王五",
                         "shippingApprover": "赵六"},
            "shipping": {"date": f"2024-0{seq}-07", "number": f"YS-{seq}", "productName": f"产品{seq}",
                         "quantity": "10", "amount": 5000.0 * seq, "company": "顺丰", "address": "北京"},
            "receipt": {"date": f"2024-0{seq}-08", "productName": f"产品{seq}", "quantity": "10",
                        "amount": 5000.0 * seq, "signer": "钱七", "sealType": "公章", "sealEntity": f"乙{seq}"},
            "invoice": {"date": f"2024-0{seq}-09", "number": f"FP-{seq}", "productName": f"产品{seq}",
                        "quantity": "10", "amount": 5000.0 * seq},
            "other": {"description": f"说明{seq}", "indexNo": f"IX-{seq}", "anomalyNote": "无异常"},
            "consistencyScore": 100, "consistencyDetails": None, "conclusion": "无异常", "isAnomalous": False,
        }
    return [mk(rid0, 1), mk(rid1, 2)]


class TestD414WalkthroughRoundtrip:
    def test_instrument_injects_d414_table_and_uuid_column(
        self, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        inv = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=TABLE_NAME_D414,
            uuid_column_letter=UUID_COL_D414,
        )
        assert inv["hidden_uuid_column"]["row_uuids"], "D4-14 未注入 UUID 行"

    def test_materialize_extract_roundtrip_nested_7dim(
        self, contract: Any, definitions: FrozenEntryDefinitions,
        base_path: Path, seed_uuids: tuple[str, str], tmp_path: Path,
    ) -> None:
        """Property 3：34 受管字段 7 维嵌套 materialize→extract 逐字段往返一致。"""
        rid0, rid1 = seed_uuids
        rows = _sample_tx(rid0, rid1)
        projection = D4.build_combined_store_projection(
            {D4.STORE_ITEM_ID: [], "D4-3-rows": [], STORE_ITEM_ID_D414: rows},
            contract=contract,
        )
        assert projection.row_keys[ROWS_TABLE_KEY_D414] == (rid0, rid1)

        adapter = AX.build_excel_adapter(
            definitions=definitions, binding=BINDING_D414, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "d414-staged.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        adapter.materialize(
            substrate=base_path, projection=projection, output=staged, contract=definitions.contract
        )
        assert staged.is_file() and staged.read_bytes()[:2] == b"PK"

        extracted = adapter.extract(artifact=staged, contract=definitions.contract)
        for column_key, _c, _m, value_type, json_path, _h in MANAGED_FIELD_SPECS_D414:
            for rid, row in ((rid0, rows[0]), (rid1, rows[1])):
                sk = stable_key_for_d414(column_key, rid)
                fv = extracted.get(sk)
                assert fv is not None, f"extract missing {sk}"
                expected = resolve_json_path(row, json_path)
                if value_type == "amount":
                    assert float(fv.value or 0) == float(expected or 0), f"{sk}: {fv.value!r} != {expected!r}"
                else:
                    assert str(fv.value) == str(expected), f"{sk}: {fv.value!r} != {expected!r}"

    def test_merge_preserves_html_only_derived_fields(
        self, contract: Any, definitions: FrozenEntryDefinitions,
        base_path: Path, seed_uuids: tuple[str, str], tmp_path: Path,
    ) -> None:
        """Property 2：OO→HTML merge 回写受管字段，HTML-only 派生字段逐字保留不被抹。"""
        rid0, rid1 = seed_uuids
        rows = _sample_tx(rid0, rid1)
        projection = D4.build_combined_store_projection(
            {D4.STORE_ITEM_ID: [], "D4-3-rows": [], STORE_ITEM_ID_D414: rows},
            contract=contract,
        )
        adapter = AX.build_excel_adapter(
            definitions=definitions, binding=BINDING_D414, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "d414-merge.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        adapter.materialize(
            substrate=base_path, projection=projection, output=staged, contract=definitions.contract
        )
        extracted = adapter.extract(artifact=staged, contract=definitions.contract)

        # base 只含 id + HTML-only 派生字段（模拟 OO→HTML：受管字段回写，派生字段应保留）
        base = [
            {"id": rid0, "label": "事项1原",
             "voucher": {"month": "1", "accountingDate": "2024-01-02"},
             "consistencyScore": 100, "conclusion": "无异常", "isAnomalous": False},
            {"id": rid1, "label": "事项2原",
             "voucher": {"month": "2", "accountingDate": "2024-02-02"},
             "consistencyScore": 67, "conclusion": "存在差异已解释", "isAnomalous": True},
        ]
        merged, applied, visited, touched = merge_projection_into_d414(
            projection=extracted, base_payload=base
        )
        assert applied > 0 and touched == {rid0, rid1}
        by_id = {r["id"]: r for r in merged}
        # 受管字段回写成功（7 维嵌套）
        assert by_id[rid0]["voucher"]["customerName"] == "客户1"
        assert by_id[rid0]["delivery"]["shippingApprover"] == "赵六"
        assert by_id[rid0]["receipt"]["sealEntity"] == "乙1"
        assert by_id[rid0]["invoice"]["productName"] == "产品1"
        assert by_id[rid0]["other"]["anomalyNote"] == "无异常"
        # HTML-only 派生字段保留（受管列不覆盖 voucher.month/accountingDate/consistencyScore/conclusion）
        assert by_id[rid0]["voucher"]["month"] == "1", "voucher.month(派生)应保留"
        assert by_id[rid0]["voucher"]["accountingDate"] == "2024-01-02", "accountingDate(派生)应保留"
        assert by_id[rid0]["consistencyScore"] == 100, "consistencyScore(派生)应保留"
        assert by_id[rid0]["conclusion"] == "无异常"
        assert by_id[rid1]["consistencyScore"] == 67
        assert by_id[rid1]["isAnomalous"] is True
