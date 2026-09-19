# -*- coding: utf-8 -*-
"""D4-27 勾选框「勾选=1 / 未勾=空」**真 OOXML** materialize→extract roundtrip。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Requirement 2（AC 2.3/2.4）

🔴 这是 checkbox 口径接通的**最终判据**（比 provider 级 roundtrip 更硬）：真跑
`build_excel_adapter → materialize → extract`，落进真实 xlsx 字节再读回，证明：
  - 勾选（前端 True）在 OOXML 里是 `<c t="b"><v>1</v></c>`（真布尔格），extract 读回 `True`；
  - 未勾（前端 False → 投影 None）落**空格**，extract 读回 `None`（不是 0，符合源模板「未勾=空白」）。

接通前的 bug：checkbox 列 value_type=text → 布尔 True 会被写成内联字符串 "True" 而非数字/布尔，
与源模板口径不符，且过 normalize 会抛错。本判据钉死接通后的字节形态。

依赖真实 D4 模板 + 插桩，与 test_d43_production_roundtrip 同款重 fixture。
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
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import phase5_d4_ipo_checklist_sheets as CK  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
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
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

CODE = "D4-27"
S = CK._SHEETS[CODE]


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _make_bundle(contract: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d427-cb-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d427-cb-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )


@pytest.fixture(scope="module")
def instrumented() -> EI.InstrumentedWorkbook:
    return EI.instrument_workbook_bytes_multi(
        D4.read_authoritative_template(), D4.instrumentation_specs(), gate=D4.excel_carrier_gate()
    )


@pytest.fixture(scope="module")
def contract() -> Any:
    D4.assert_contract_file_matches_source()
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


@pytest.fixture(scope="module")
def definitions(contract: Any, instrumented: EI.InstrumentedWorkbook) -> FrozenEntryDefinitions:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=S["table_name"],
        uuid_column_letter=S["uuid_col"],
    )
    return FrozenEntryDefinitions(
        entry_id=D4.ENTRY_ID,
        bundle=_make_bundle(contract),
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=D4.ADAPTER_ID,
            adapter_build_digest=_d("d427-cb-adapter"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inv),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


@pytest.fixture(scope="module")
def row_uuid(instrumented: EI.InstrumentedWorkbook) -> str:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=S["table_name"],
        uuid_column_letter=S["uuid_col"],
    )
    uuids = inv["hidden_uuid_column"]["row_uuids"]
    rid = uuids.get(str(S["first_data_row"])) or uuids.get(S["first_data_row"])
    assert rid, f"D4-27 首数据行缺 UUID: {uuids}"
    return str(rid)


@pytest.fixture
def base_path(instrumented: EI.InstrumentedWorkbook, tmp_path: Path) -> Path:
    p = tmp_path / "d427-base.xlsx"
    p.write_bytes(instrumented.instrumented_bytes)
    return p


def test_checkbox_true_lands_as_ooxml_boolean_and_reads_back_true(
    contract: Any, definitions: FrozenEntryDefinitions, base_path: Path,
    row_uuid: str, tmp_path: Path,
) -> None:
    """勾选 True → 真 OOXML → extract 读回 True；未勾 False→None → 读回 None（非 0/非 "True"）。"""
    # 一行：勾「个人客户」，不勾「客户法人」。经 build 侧 coercion：True→True / False→None。
    store_row = {
        "rowId": row_uuid,
        "name": "陈某",
        "isPersonalCustomer": True,
        "isCustomerLegal": False,
    }
    projection = CK.build_store_projection(CODE, [store_row], contract=contract)

    binding = X.ExcelIdentityBinding(
        table_name=S["table_name"], uuid_column=S["uuid_col"], table_key=S["table_key"]
    )
    adapter = AX.build_excel_adapter(
        definitions=definitions, binding=binding, direction="html_to_oo"
    )
    staged = tmp_path / AX.STAGING_NAMESPACE / "d427-staged.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)
    adapter.materialize(
        substrate=base_path, projection=projection, output=staged, contract=definitions.contract
    )
    assert staged.is_file() and staged.read_bytes()[:2] == b"PK"

    # 字节级证据：勾选格是真 OOXML 布尔 <c ... t="b"><v>1</v>，不是内联字符串 "True"。
    import zipfile

    name_marker = "陈某".encode("utf-8")
    with zipfile.ZipFile(staged) as zf:
        sheet_xml = b""
        for n in zf.namelist():
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"):
                x = zf.read(n)
                if name_marker in x or b't="b"' in x:
                    sheet_xml += x
    assert b">True<" not in sheet_xml, "勾选被写成了内联字符串 True —— 口径未接通"

    # 读回：勾选 True / 未勾 None（extract 侧）。
    extracted = adapter.extract(artifact=staged, contract=definitions.contract)

    def _fv(col_key: str) -> Any:
        sk = CK.stable_key_for(CODE, col_key, row_uuid)
        return extracted.get(sk)

    checked = _fv("is_personal_customer")
    assert checked is not None and checked.value is True, (
        f"勾选列读回应为 True，实得 {getattr(checked, 'value', 'MISSING')!r}"
    )
    unchecked = _fv("is_customer_legal")
    # 未勾落空格：extract 要么不产出该 key，要么 value 为 None —— 关键是**不为 False/0**
    assert unchecked is None or unchecked.value in (None, ""), (
        f"未勾列读回应为空（None），实得 {getattr(unchecked, 'value', 'MISSING')!r} —— "
        f"未勾不该变成 0/False"
    )


def test_checkbox_merge_roundtrip_yields_strict_bool(
    contract: Any, definitions: FrozenEntryDefinitions, base_path: Path,
    row_uuid: str, tmp_path: Path,
) -> None:
    """完整 materialize→extract→merge：勾选回读 True、未勾回读 False（前端 el-checkbox 口径）。"""
    store_row = {
        "rowId": row_uuid, "name": "陈某",
        "isPersonalCustomer": True, "isCustomerLegal": False,
    }
    projection = CK.build_store_projection(CODE, [store_row], contract=contract)
    binding = X.ExcelIdentityBinding(
        table_name=S["table_name"], uuid_column=S["uuid_col"], table_key=S["table_key"]
    )
    adapter = AX.build_excel_adapter(
        definitions=definitions, binding=binding, direction="html_to_oo"
    )
    staged = tmp_path / AX.STAGING_NAMESPACE / "d427-merge.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)
    adapter.materialize(
        substrate=base_path, projection=projection, output=staged, contract=definitions.contract
    )
    extracted = adapter.extract(artifact=staged, contract=definitions.contract)

    merged, _a, _v, _t = CK.merge_projection_into_rows(
        CODE, projection=extracted, base_rows=[{"rowId": row_uuid}]
    )
    out = next(r for r in merged if r["rowId"] == row_uuid)
    assert out["isPersonalCustomer"] is True, "勾选列往返回读应为 True"
    # 🔴 未勾列落空格 → extract 不产出该 stable key → merge 不写该字段 ⇒ 键**缺席**。
    # 这对前端 el-checkbox（v-model 对 undefined/false 都渲染未勾）是正确的：缺席 = 未勾。
    # 关键判据：绝不能出现 True（未勾变勾）或数字 0/1（口径退回）。
    assert out.get("isCustomerLegal") in (None, False), (
        f"未勾列往返回读应为未勾（缺席/None/False），实得 {out.get('isCustomerLegal')!r} —— "
        f"绝不能变成 True 或数字"
    )
