"""D2 兄弟受管 sheet 的跨表引用传播 —— 未管理区域校验必须按声明逆替换（spec d2-online-edit-platform-closure R4）。

真栈形态（2026-10-10 dry-run）：D2-2 明细表 741 行 ⇒ 模板 12 行占位要插行 ⇒ 工作簿级传播把
审定表D2-1 上的 `SUMIF('明细表D2-2'!$AI$13:$AI$25,…)` 改成 `…$754`。D2-1 本身是受管 sheet
（静态区 binding），它的单元格 digest 只认自身 `row_shift`，从不读传播声明 ⇒ 4 个 binding 里
唯独 D2-1 判 `managed_sheet_unmanaged_cells` 漂移，发布与 materialize 恒失败。

判据全部用**真权威模板 + 真 instrumentation + 真 materialize**，不 mock 校验函数：
1. 声明内的改写判等价（修复前红）；
2. 声明之外改公式仍判漂移；
3. 改样式索引 `s` 仍判漂移（`s` 没有被从 digest 里拿掉）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
import warnings
import zipfile
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")
warnings.filterwarnings("ignore")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as EE  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import pilot_d2_large_json as D2  # noqa: E402
from app.services.workpaper_sync.adapters import excel as AX  # noqa: E402
from app.services.workpaper_sync.adapters.base import UnmanagedRegionDriftError  # noqa: E402
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
from app.services.workpaper_sync.phase5_row_table_sheet import attach_sibling_bindings  # noqa: E402
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

#: 远超模板 12 行占位 ⇒ D2-2 必然插行 ⇒ D2-1 的 SUMIF 区间必然被传播改写。
ROWS = 40
#: 审定表D2-1 —— 跨表引用明细表D2-2 的兄弟受管 sheet。
D21_SHEET = "审定表D2-1"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _definitions(contract: Any, inventory_raw: Mapping[str, Any]) -> FrozenEntryDefinitions:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d2-sibling-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d2-sibling-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    return FrozenEntryDefinitions(
        entry_id=D2.PILOT_ENTRY_ID,
        bundle=bundle,
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=D2.PILOT_ADAPTER_ID,
            adapter_build_digest=_d("d2-sibling-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inventory_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D2.build_contract_payload(), adapter_id=D2.PILOT_ADAPTER_ID)


@pytest.fixture(scope="module")
def instrumented() -> Any:
    return EI.instrument_workbook_bytes_multi(
        D2.read_authoritative_template(), D2.instrumentation_specs(), gate=D2.excel_carrier_gate()
    )


@pytest.fixture(scope="module")
def adapter(contract: Any, instrumented: Any) -> Any:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=D2.TABLE_NAME,
        uuid_column_letter=D2.UUID_COL,
    )
    primary = EE.ExcelIdentityBinding(
        table_name=D2.TABLE_NAME, uuid_column=D2.UUID_COL, table_key=D2.ROWS_TABLE_KEY
    )
    # 兄弟 binding 用生产 attach 同一个对齐内核 —— 测的就是生产会走到的那组 binding。
    siblings = attach_sibling_bindings(
        provider=D2, primary=primary, contract=contract, dynamic_bindings={}
    )
    return AX.build_excel_adapter(
        definitions=_definitions(contract, inv),
        binding=primary,
        direction="html_to_oo",
        sibling_bindings=tuple(siblings),
    )


def _store_rows(n: int) -> list[dict[str, Any]]:
    return [
        {
            "rowId": f"d2-sib-{i:03d}",
            "seq": i + 1,
            "customerName": f"测试客户{i}",
            "relationType": "非关联方",
            "priorUnadjusted": 100.0 + i,
            "currentUnadjusted": 200.0 + i,
        }
        for i in range(n)
    ]


@pytest.fixture(scope="module")
def materialized(adapter: Any, contract: Any, instrumented: Any, tmp_path_factory: Any) -> dict:
    work = tmp_path_factory.mktemp("d2-sibling")
    base = work / "base.xlsx"
    base.write_bytes(instrumented.instrumented_bytes)
    projection = D2.build_combined_store_projection(
        {D2.STORE_ITEM_ID: json.dumps(_store_rows(ROWS), ensure_ascii=False)}, contract=contract
    )
    out = work / AX.STAGING_NAMESPACE / "after.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    result = adapter.materialize(
        substrate=base, projection=projection, output=out, contract=contract
    )
    return {"base": base, "after": out, "result": result, "work": work}


def _verify(adapter: Any, contract: Any, materialized: dict, after: Path) -> Any:
    result = materialized["result"]
    return adapter.verify_unmanaged_regions(
        before=materialized["base"],
        after=after,
        contract=contract,
        row_shift=getattr(result, "row_shift", None),
        total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
        propagation=getattr(result, "workbook_row_change", None),
        per_table_shift=getattr(result, "per_table_shift", None),
    )


def _sheet_part(path: Path, sheet_name: str) -> str:
    with zipfile.ZipFile(path) as zf:
        return EE._sheet_parts(zf)[sheet_name]


def _rewrite_part(src: Path, dst: Path, part: str, edit: Any) -> None:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == part:
                data = edit(data.decode("utf-8")).encode("utf-8")
            zout.writestr(item, data)


# ═══════════════════════════════════════════════════════════════════════════
# 判据 0：前提 —— 传播真的改写了 D2-1 的跨表引用（否则本文件测的不是原缺陷）
# ═══════════════════════════════════════════════════════════════════════════


def test_premise_propagation_rewrites_d21_cross_sheet_refs(materialized: dict) -> None:
    plan = getattr(materialized["result"], "workbook_row_change", None)
    assert plan is not None, "D2-2 插行必须产出工作簿级传播声明"
    part = _sheet_part(materialized["after"], D21_SHEET)
    declared = [e for e in plan.propagations if e.part == part]
    assert declared, f"传播声明里没有 {D21_SHEET}（{part}）的条目 —— 前提不成立"
    with zipfile.ZipFile(materialized["base"]) as zb, zipfile.ZipFile(materialized["after"]) as za:
        before, after = zb.read(part).decode("utf-8"), za.read(part).decode("utf-8")
    assert "$AI$25" in before and "$AI$25" not in after, "D2-1 的 SUMIF 区间应被传播改写"


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1：声明内的改写判等价（修复前此处恒报 managed_sheet_unmanaged_cells 漂移）
# ═══════════════════════════════════════════════════════════════════════════


def test_declared_cross_sheet_rewrite_is_equivalent(
    adapter: Any, contract: Any, materialized: dict
) -> None:
    report = _verify(adapter, contract, materialized, materialized["after"])
    assert report.equivalent, report.first_difference


# ═══════════════════════════════════════════════════════════════════════════
# 判据 2：声明之外改公式 ⇒ 仍判漂移（逆替换只还原声明，不放过别的改动）
# ═══════════════════════════════════════════════════════════════════════════


def test_undeclared_formula_edit_on_d21_is_still_drift(
    adapter: Any, contract: Any, materialized: dict
) -> None:
    part = _sheet_part(materialized["after"], D21_SHEET)
    tampered = materialized["work"] / "tampered-formula.xlsx"

    def edit(xml: str) -> str:
        # 把一处已被传播改写的 SUMIF 再改一笔声明里没有的东西（求和列 S → T）。
        new, n = re.subn(r"(SUMIF\('明细表D2-2'!\$AI\$13:\$AI\$\d+,\"[^\"]+\",'明细表D2-2'!)\$S\$",
                         r"\1$T$", xml, count=1)
        assert n == 1, "没找到可篡改的 SUMIF —— 判据失去靶子"
        return new

    _rewrite_part(materialized["after"], tampered, part, edit)
    with pytest.raises(UnmanagedRegionDriftError, match="managed_sheet_unmanaged_cells"):
        _verify(adapter, contract, materialized, tampered)


# ═══════════════════════════════════════════════════════════════════════════
# 判据 3：改样式索引 `s` ⇒ 仍判漂移（`s` 仍在单元格 digest 里）
# ═══════════════════════════════════════════════════════════════════════════


def test_style_index_edit_on_d21_is_still_drift(
    adapter: Any, contract: Any, materialized: dict
) -> None:
    part = _sheet_part(materialized["after"], D21_SHEET)
    tampered = materialized["work"] / "tampered-style.xlsx"

    def edit(xml: str) -> str:
        # A1 是 D2-1 的标题格（非受管）；把它的样式索引换成另一个合法值。
        m = re.search(r'<c r="A1"([^>]*?)\ss="(\d+)"', xml)
        assert m, "D2-1 的 A1 没有样式索引 —— 判据失去靶子"
        new_s = "0" if m.group(2) != "0" else "1"
        return xml[: m.start(2)] + new_s + xml[m.end(2):]

    _rewrite_part(materialized["after"], tampered, part, edit)
    with pytest.raises(UnmanagedRegionDriftError, match="managed_sheet_unmanaged_cells"):
        _verify(adapter, contract, materialized, tampered)
