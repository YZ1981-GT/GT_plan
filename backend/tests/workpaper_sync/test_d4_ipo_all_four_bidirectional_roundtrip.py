# -*- coding: utf-8 -*-
"""D4-25/26/27/28 **四张表全部**的端到端双向回写 roundtrip（真 OOXML materialize↔extract）。

spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Requirement 2（AC 2.1-2.4）

🔴 回答「这四个底稿都实现双向回写了吗」的权威判据：不靠浏览器点一张、靠对**四张表逐张**
真跑 `build_store_projection → adapter.materialize（落真 xlsx）→ adapter.extract（读回）→
merge_projection_into_rows`，断言：
  - HTML→OO（materialize）：每个受管列的值真的写进了 OO 单元格；
  - OO→HTML（extract+merge）：从 OO 字节反读回来后逐字段与原始一致；
  - checkbox 列勾选=True/未勾按未勾语义往返；amount 数值容差；文本原样。

这一条覆盖四张表 × 两个方向，是「双向回写全部实现」的可复现证据。
"""
from __future__ import annotations

import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Any

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

CODES = CK.CHECKLIST_SHEET_CODES  # ("D4-25","D4-26","D4-27","D4-28")


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _bundle(contract: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d4-4x-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d4-4x-authority"),
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


def _definitions(contract: Any, instrumented: EI.InstrumentedWorkbook, code: str) -> FrozenEntryDefinitions:
    s = CK._SHEETS[code]
    inv = identity_inventory(
        instrumented.instrumented_bytes, expected_table=s["table_name"], uuid_column_letter=s["uuid_col"]
    )
    return FrozenEntryDefinitions(
        entry_id=D4.ENTRY_ID,
        bundle=_bundle(contract),
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=D4.ADAPTER_ID,
            adapter_build_digest=_d(f"d4-4x-adapter-{code}"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inv),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


def _first_row_uuid(instrumented: EI.InstrumentedWorkbook, code: str) -> str:
    s = CK._SHEETS[code]
    inv = identity_inventory(
        instrumented.instrumented_bytes, expected_table=s["table_name"], uuid_column_letter=s["uuid_col"]
    )
    uuids = inv["hidden_uuid_column"]["row_uuids"]
    rid = uuids.get(str(s["first_data_row"])) or uuids.get(s["first_data_row"])
    assert rid, f"{code} 首数据行缺 UUID: {uuids}"
    return str(rid)


def _checked_path(code: str) -> str | None:
    """该表被勾选的那个 checkbox 列 json_path（字段顺序里第一个 boolean 列）；无勾选列返回 None。

    D4-25 全是 text/amount/select，无 checkbox 列 —— 它的双向回写只测文本/金额往返。
    """
    return next((spec[4] for spec in CK._SHEETS[code]["fields"] if spec[3] == "boolean"), None)


def _sample_row(code: str, row_uuid: str) -> dict[str, Any]:
    """造一行可区分的值：**每个** checkbox 都显式赋值（第一个 True，其余 False），
    amount→数值，其余→文本。全部显式设值 ⇒ roundtrip 必须逐字段等于我设的，不受
    模板示例行残值干扰（D4-27 首行是模板示例 陈XX，C/D/J 预填 1）。
    """
    s = CK._SHEETS[code]
    checked = _checked_path(code)
    row: dict[str, Any] = {"rowId": row_uuid}
    for column_key, _c, _m, vt, json_path, _h in s["fields"]:
        if json_path == "seq":
            continue
        if vt == "boolean":
            row[json_path] = (json_path == checked)  # 第一个 True，其余显式 False
        elif vt == "amount":
            row[json_path] = 1234.56
        else:
            row[json_path] = f"v-{json_path}"
    return row


@pytest.mark.parametrize("code", CODES)
def test_bidirectional_roundtrip_through_real_ooxml(
    code: str, contract: Any, instrumented: EI.InstrumentedWorkbook, tmp_path: Path
) -> None:
    """四张表逐张：HTML store → materialize（真 xlsx）→ extract → merge，两向逐字段一致。"""
    s = CK._SHEETS[code]
    row_uuid = _first_row_uuid(instrumented, code)
    store_row = _sample_row(code, row_uuid)

    # HTML → projection（build 侧含 checkbox coercion）
    projection = CK.build_store_projection(code, [store_row], contract=contract)

    definitions = _definitions(contract, instrumented, code)
    binding = X.ExcelIdentityBinding(
        table_name=s["table_name"], uuid_column=s["uuid_col"], table_key=s["table_key"]
    )
    adapter = AX.build_excel_adapter(definitions=definitions, binding=binding, direction="html_to_oo")

    base = tmp_path / f"{code}-base.xlsx"
    base.write_bytes(instrumented.instrumented_bytes)
    staged = tmp_path / AX.STAGING_NAMESPACE / f"{code}-staged.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)

    # ── HTML → OO：materialize 落真 xlsx 字节 ──
    adapter.materialize(substrate=base, projection=projection, output=staged, contract=definitions.contract)
    assert staged.is_file() and staged.read_bytes()[:2] == b"PK", f"{code}: materialize 未产出 xlsx"

    # ── OO → HTML：extract 读回 + merge 回 rows ──
    extracted = adapter.extract(artifact=staged, contract=definitions.contract)
    merged, applied, visited, touched = CK.merge_projection_into_rows(
        code, projection=extracted, base_rows=[{"rowId": row_uuid}]
    )
    assert row_uuid in touched, f"{code}: 本行未被回写"
    out = next(r for r in merged if r["rowId"] == row_uuid)

    # 逐字段核对两向一致
    cb_paths = {spec[4] for spec in s["fields"] if spec[3] == "boolean"}
    amount_paths = {spec[4] for spec in s["fields"] if spec[3] == "amount"}
    checked = _checked_path(code)
    for column_key, _c, _m, vt, json_path, _h in s["fields"]:
        if json_path == "seq":
            continue
        if json_path in cb_paths:
            if json_path == checked:
                assert out.get(json_path) is True, f"{code}.{json_path}: 勾选应往返为 True"
            else:
                # 显式设 False（未勾）：落空格 → extract 缺席/None → merge 回 False ⇒ 绝不为 True
                assert out.get(json_path) in (None, False), (
                    f"{code}.{json_path}: 未勾应往返为未勾，实得 {out.get(json_path)!r}"
                )
        elif json_path in amount_paths:
            assert abs(float(out[json_path]) - 1234.56) <= 0.005, f"{code}.{json_path}: 金额往返超容差"
        else:
            assert out.get(json_path) == f"v-{json_path}", (
                f"{code}.{json_path}: 文本往返丢值/串列（实得 {out.get(json_path)!r}）"
            )


@pytest.mark.parametrize("code", CODES)
def test_managed_column_count_matches_contract(code: str) -> None:
    """四张表受管列数与冻结值一致（双向回写覆盖的字段面不缩水）。"""
    expected = {"D4-25": 13, "D4-26": 19, "D4-27": 17, "D4-28": 15}[code]
    # D4-27 契约字段 17（总计列 M 入 mask 不入契约），列规格 18 —— 这里核契约字段数
    assert CK._SHEETS[code]["field_count"] == expected
