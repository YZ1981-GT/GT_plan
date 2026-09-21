# -*- coding: utf-8 -*-
"""D4-13「营业收入账面金额与ERP系统核对记录」—— 静态受管区（同 adapter `d4.revenue_detail`）。

spec: d-cycle-sheet-bidirectional-expansion · D4-13 paragraph_block_bidirectional
T10 mapping_digest 见 ``evidence/T10-d413-erp-check-field-mapping.json``。

═══ 产品形态 ═══

* HTML：段落式 ``D4TabErpCheck.vue``（核对过程 / 核对结论两段自由文本，debounce 2s 落库）
* Excel：**静态受管区**（spec workpaper-sync-static-cell-sheet-writeback）——两字段
  ``process``（A6）/ ``conclusion``（A16）各锚死行号，无动态行、无 UUID 列、无 Excel Table
* 宿主 **独立**（``D4TabErpCheck`` 自管 dualMode，不进 ``isD4DedicatedSyncSheet``/
  ``isD4DetailSheet``，与 D4-5/D4-33 同款）

═══ 为什么走 static_region 而非动态行表 ═══

D4-13 全篇（A1:E19，openpyxl 直读核实）没有任何会插删行的动态数据区、无公式、无 UUID 列
——跟 D4-33（其他业务毛利率分析，固定 12 月行 × 3 业务类型列组，同样无动态行）同构，
适用引擎的静态受管区路径（``BindingKind.static_region``）：只声明 workbook-scope
``defined_name`` 锚点，注入时只写 definedName，不建 Excel Table / 不注隐藏 UUID 列。

这与 D4-5 固定区（``FIXED_FIELD_SPECS_D45``）不同——D4-5 fixed 字段寄生在 D4-5 **groups
动态表** 自己的 primary spec 之下（那张 primary spec 本身建了 Excel Table），而 D4-13
没有任何姊妹动态表可寄生，必须走独立的 static_sheets 声明（挂在主 spec
``instrumentation_spec()`` 上，同 D4-33/D4-8 的接线方式）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Mapping

TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)

MANAGED_SHEET_D413: Final[str] = "营业收入账面金额与ERP系统核对记录D4-13"
TEMPLATE_ID_D413: Final[str] = "D413"
SHEET_KEY_D413: Final[str] = "d413-managed"
TABLE_KEY_D413: Final[str] = "d413_erp_check_fixed"

#: 静态受管区 workbook-scope definedName 锚点（spec workpaper-sync-static-cell-sheet-writeback）。
DEFINED_NAME_D413: Final[str] = "GT_MANAGED_REGION_D413"
#: 两字段各占单 cell，非连续区间；definedName 覆盖两行所跨的最小矩形（A6:A16，中间行留白不受管）。
MANAGED_REF_D413: Final[str] = "$A$6:$A$16"

STORE_ITEM_ID_D413_PROCESS: Final[str] = "D4-13-process"
STORE_ITEM_ID_D413_CONCLUSION: Final[str] = "D4-13-conclusion"
STORE_ITEM_IDS_D413_FIXED: Final[tuple[str, ...]] = (
    STORE_ITEM_ID_D413_PROCESS,
    STORE_ITEM_ID_D413_CONCLUSION,
)

#: mapping_digest 由 evidence/T10-d413-erp-check-field-mapping.json 现算并锁死
#: （2026-09-21 首次生成时用 compute_mapping_digest_d413() 的真实输出回填）。
EXPECTED_MAPPING_DIGEST_D413: Final[str] = (
    "0ec95fc554f63c40e034ab315027af6f270a2e439b92c2b9a9ad20266e25c55b"
)

#: 固定区字段：(column_key, 列, 行号, store_item_id)。两项均为纯文本、静态、无 mask。
FIXED_FIELD_SPECS_D413: Final[tuple[tuple[str, str, int, str], ...]] = (
    ("process", "A", 6, STORE_ITEM_ID_D413_PROCESS),
    ("conclusion", "A", 16, STORE_ITEM_ID_D413_CONCLUSION),
)


def mapping_digest_payload_d413() -> dict[str, Any]:
    """与 T10 ``digest_payload`` 对齐（读 evidence 文件保证锁死，同 D4-5 的
    ``mapping_digest_payload_d45`` 做法）。"""
    from pathlib import Path

    evidence = (
        Path(__file__).resolve().parents[4]
        / ".kiro/specs/d-cycle-sheet-bidirectional-expansion/evidence"
        / "T10-d413-erp-check-field-mapping.json"
    )
    raw = json.loads(evidence.read_text(encoding="utf-8"))
    return raw["digest_payload"]


def compute_mapping_digest_d413() -> str:
    canon = json.dumps(
        mapping_digest_payload_d413(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def assert_mapping_digest_d413() -> str:
    got = compute_mapping_digest_d413()
    if got != EXPECTED_MAPPING_DIGEST_D413:
        raise ValueError(
            f"D4-13 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D413} —— "
            "与 evidence/T10-d413-erp-check-field-mapping.json 不一致"
        )
    return got


def stable_key_for_d413_fixed(column_key: str) -> str:
    return f"{TABLE_KEY_D413}/{column_key}"


def sheet_payload_d413(*, excel_name: str = MANAGED_SHEET_D413) -> dict[str, Any]:
    """契约用 sheet payload（静态区：``locator.anchor=defined_name_ref``，非 Excel Table 锚点）。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    assert_mapping_digest_d413()

    fields: list[dict[str, Any]] = []
    for column_key, column, row, store_item in FIXED_FIELD_SPECS_D413:
        fields.append(
            {
                "stable_field_key": stable_key_for_d413_fixed(column_key),
                "json_pointer": f"/fixed/{column_key}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": row},
                "mode": "editable",
                "value_type": "text",
                "source_ref": _src(f"{column}{row}"),
                "header_source_ref": _src(f"{column}{row - 1}"),
                "store_item_id": store_item,
                "header_text": column_key,
            }
        )
    return {
        "sheet_key": SHEET_KEY_D413,
        "excel_name": excel_name,
        "template_id": TEMPLATE_ID_D413,
        "locator": {
            "anchor": "defined_name_ref",
            "defined_name": DEFINED_NAME_D413,
        },
        "region_boundary_locator": {
            "anchor": "defined_name_ref",
            "defined_name": DEFINED_NAME_D413,
            "range": MANAGED_REF_D413,
            "region_kind": "static",
        },
        "tables": [
            {
                "table_key": TABLE_KEY_D413,
                "anchor": "A5",
                "header_rows": 1,
                "fields": fields,
            }
        ],
    }


def static_sheet_payload_d413() -> dict[str, Any]:
    """instrumentation ``static_sheets`` 元素（寄生在主 primary spec 上，同 D4-33/D4-8）。

    只声明 workbook-scope definedName 锚点几何；注入时只写 definedName，不注 Excel Table /
    UUID 列 / 隐藏行（引擎静态路径）。``_static_region_bindings`` 会自动从这个声明生成
    对应的 ``ExcelIdentityBinding``，不需要再手动接线 sibling_bindings。
    """
    return {
        "sheet_key": SHEET_KEY_D413,
        "excel_name": MANAGED_SHEET_D413,
        "template_id": TEMPLATE_ID_D413,
        "region_boundary_locator": {
            "anchor": "defined_name_ref",
            "defined_name": DEFINED_NAME_D413,
            "range": MANAGED_REF_D413,
            "region_kind": "static",
        },
        "tables": [{"table_key": TABLE_KEY_D413}],
    }


def build_d413_fixed_store_projection(
    payloads_by_item: Mapping[str, str | None],
    *,
    contract: Any,
) -> Any:
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    values: dict[str, FieldValue] = {}
    for column_key, _col, _row, store_item in FIXED_FIELD_SPECS_D413:
        sk = stable_key_for_d413_fixed(column_key)
        spec = contract.field_by_stable_key(sk)
        raw = payloads_by_item.get(store_item)
        values[sk] = FieldValue(
            stable_key=sk,
            value=raw if raw is not None else "",
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=None,
        )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={},
    )


def merge_projection_into_d413_fixed_items(
    *,
    projection: Any,
    base_by_item: Mapping[str, str | None],
) -> dict[str, str]:
    """返回 item_id → 新 remark 文本（仅 touched），同 D4-5 的
    ``merge_projection_into_d45_fixed_items`` 做法。"""
    out: dict[str, str] = {}
    for column_key, _col, _row, store_item in FIXED_FIELD_SPECS_D413:
        sk = stable_key_for_d413_fixed(column_key)
        fv = projection.get(sk) if hasattr(projection, "get") else None
        if fv is None:
            values = getattr(projection, "values", None)
            if isinstance(values, Mapping):
                fv = values.get(sk)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        new_val = getattr(fv, "value", None)
        text = "" if new_val is None else str(new_val)
        old = base_by_item.get(store_item) or ""
        if text != old:
            out[store_item] = text
    return out
