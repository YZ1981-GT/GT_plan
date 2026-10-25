# -*- coding: utf-8 -*-
"""D4-5「营业收入会计政策检查」—— 第三受管 sheet（同 adapter `d4.revenue_detail`）。

spec: d-cycle-sheet-bidirectional-expansion · D4-5 paragraph_block_bidirectional
T09 mapping_digest =
``5e261da248cb0df23ba45f562099c1fdfdb450130df96022fb41ec4275f12eee``

═══ 产品形态 ═══

* HTML：段落式 ``useD4PolicyCheck``（多 item_id + 可增删 policyGroups）
* Excel：分组带做 **紧凑受管表**（A–D + Z UUID，一行一组），经营模式 6 项走
  B 列 static；宿主 **独立**（``D4TabPolicyCheck`` 自管 dualMode，不进
  ``isD4DetailSheet``）
* 插删组：标准 GTROW 插行，footer 锚 = ``（三）信用政策``（下移信用/说明/结论）

═══ 布局正规化 ═══

权威模板分组区原为多行叙述块。契约受管几何改为紧凑表（T09
``layout_normalization=compact_group_table``）；HTML UX 不变。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)

MANAGED_SHEET_D45: Final[str] = "营业收入会计政策检查D4-5"
TEMPLATE_ID_D45: Final[str] = "D45"
SHEET_KEY_D45: Final[str] = "d45-managed"

#: 分组紧凑表（一行一组）。
HEADER_ROW_D45_GROUPS: Final[int] = 17  # 「（二）会计政策…」作表头锚（非列标题）
FIRST_DATA_ROW_D45_GROUPS: Final[int] = 18
#: 模板种子 2 组；插删后由引擎扩张。
LAST_DATA_ROW_D45_GROUPS_SEED: Final[int] = 19
FOOTER_MARKER_D45: Final[str] = "（三）信用政策"
#: 模板上信用政策标题行；插行后靠 marker 重定位。
FOOTER_ROW_D45_SEED: Final[int] = 47
MANAGED_LAST_COL_D45: Final[str] = "D"
UUID_COL_D45: Final[str] = "Z"
TABLE_NAME_D45: Final[str] = f"GT_{TEMPLATE_ID_D45}_GROUPS"

ROWS_TABLE_KEY_D45: Final[str] = "d45_policy_groups"
FIXED_TABLE_KEY_D45: Final[str] = "d45_policy_fixed"
ROW_IDENTITY_STORE_KEY_D45: Final[str] = "id"

STORE_ITEM_ID_D45_GROUPS: Final[str] = "D4-5-policy-groups"
STORE_ITEM_IDS_D45_FIXED: Final[tuple[str, ...]] = (
    "D4-5-biz-scene",
    "D4-5-biz-order",
    "D4-5-biz-produce",
    "D4-5-biz-sales",
    "D4-5-biz-pricing",
    "D4-5-biz-delivery",
)

EXPECTED_MAPPING_DIGEST_D45: Final[str] = (
    "5e261da248cb0df23ba45f562099c1fdfdb450130df96022fb41ec4275f12eee"
)

#: 分组表字段：(column_key, 列, mode, value_type, store json 路径, 表头)
MANAGED_FIELD_SPECS_D45_GROUPS: Final[
    tuple[tuple[str, str, str, str, str, str], ...]
] = (
    ("biz_name", "A", "editable", "text", "bizName", "业务类型"),
    ("revenue_policy", "B", "editable", "text", "revenuePolicy", "收入会计政策"),
    ("industry_policy", "C", "editable", "text", "industryPolicy", "同行业相关政策"),
    (
        "rationality_analysis",
        "D",
        "editable",
        "text",
        "rationalityAnalysis",
        "合理性分析",
    ),
)

#: 固定区 static（仅插入带**上方**可声明 ``static_row``）。
#: 信用/说明/结论在 footer 之下：引擎对 ``contract_static_row_below_insertion``
#: fail-closed（extract 仍按死行号反读），故**不入契约**；仍由 HTML
#: ``useD4PolicyCheck`` 持久化。待 marker-relative content 字段落地后再扩。
FIXED_FIELD_SPECS_D45: Final[tuple[tuple[str, str, int, str], ...]] = (
    ("biz_scene", "B", 11, "D4-5-biz-scene"),
    ("biz_order", "B", 12, "D4-5-biz-order"),
    ("biz_produce", "B", 13, "D4-5-biz-produce"),
    ("biz_sales", "B", 14, "D4-5-biz-sales"),
    ("biz_pricing", "B", 15, "D4-5-biz-pricing"),
    ("biz_delivery", "B", 16, "D4-5-biz-delivery"),
)

#: HTML-only（footer 下移区）；不进 Excel 契约 field 列表。
HTML_ONLY_ITEM_IDS_D45: Final[tuple[str, ...]] = (
    "D4-5-credit-policy",
    "D4-5-audit-note",
    "D4-5-audit-conclusion",
)


def mapping_digest_payload_d45() -> dict[str, Any]:
    """与 T09 ``digest_payload`` 对齐（含 layout 与宿主独立声明）。"""
    # 直接读 T09 文件保证锁死
    from pathlib import Path

    evidence = (
        Path(__file__).resolve().parents[4]
        / ".kiro/specs/d-cycle-sheet-bidirectional-expansion/evidence"
        / "T09-d45-block-field-mapping.json"
    )
    raw = json.loads(evidence.read_text(encoding="utf-8"))
    return raw["digest_payload"]


def compute_mapping_digest_d45() -> str:
    canon = json.dumps(
        mapping_digest_payload_d45(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def assert_mapping_digest_d45() -> str:
    got = compute_mapping_digest_d45()
    if got != EXPECTED_MAPPING_DIGEST_D45:
        raise ValueError(
            f"D4-5 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D45} —— "
            "与 evidence/T09-d45-block-field-mapping.json 不一致"
        )
    return got


def stable_key_for_d45_group(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D45}/{row_identity}/{column_key}"


def stable_key_for_d45_fixed(column_key: str) -> str:
    return f"{FIXED_TABLE_KEY_D45}/{column_key}"


def groups_table_payload_d45(*, excel_name: str = MANAGED_SHEET_D45) -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D45_GROUPS:
        fields.append(
            {
                "stable_field_key": stable_key_for_d45_group(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D45_GROUPS}"),
                "header_source_ref": _src(f"A{HEADER_ROW_D45_GROUPS}"),
                "store_item_id": STORE_ITEM_ID_D45_GROUPS,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D45,
        "anchor": f"A{HEADER_ROW_D45_GROUPS}",
        "header_rows": 1,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D45}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER_D45,
            "search_column": "A",
            "carries_total_formula": False,
            "note": (
                "footer 锚为「（三）信用政策」标题行；分组紧凑表插删后信用/说明/结论下移。"
                "layout_normalization=compact_group_table（T09）。"
            ),
        },
        "formula_mask": [],
        "fields": fields,
    }


def fixed_table_payload_d45(*, excel_name: str = MANAGED_SHEET_D45) -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, row, store_item in FIXED_FIELD_SPECS_D45:
        fields.append(
            {
                "stable_field_key": stable_key_for_d45_fixed(column_key),
                "json_pointer": f"/fixed/{column_key}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": row},
                "mode": "editable",
                "value_type": "text",
                "source_ref": _src(f"{column}{row}"),
                "header_source_ref": _src(f"A{row}"),
                "store_item_id": store_item,
                "header_text": column_key,
            }
        )
    return {
        "table_key": FIXED_TABLE_KEY_D45,
        "anchor": "B11",
        "header_rows": 1,
        "fields": fields,
    }


def sheet_payload_d45() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    assert_mapping_digest_d45()
    return {
        "sheet_key": SHEET_KEY_D45,
        "excel_name": MANAGED_SHEET_D45,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [groups_table_payload_d45(), fixed_table_payload_d45()],
    }


def instrumentation_spec_d45(*, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D45,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D45,
        first_data_row=FIRST_DATA_ROW_D45_GROUPS,
        last_data_row=LAST_DATA_ROW_D45_GROUPS_SEED,
        footer_row=FOOTER_ROW_D45_SEED,
        managed_last_col=MANAGED_LAST_COL_D45,
        uuid_col=UUID_COL_D45,
        table_name=TABLE_NAME_D45,
    )


def iter_d45_group_rows(
    payload: str | bytes | Sequence[Any],
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text) if text else []
        except ValueError as exc:
            raise ValueError(f"{STORE_ITEM_ID_D45_GROUPS} 不是合法 JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise ValueError(f"{STORE_ITEM_ID_D45_GROUPS} 必须是数组")
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{STORE_ITEM_ID_D45_GROUPS}[{ordinal}] 不是对象")
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D45) or "").strip()
        if not rid:
            raise ValueError(
                f"{STORE_ITEM_ID_D45_GROUPS}[{ordinal}] 缺少 {ROW_IDENTITY_STORE_KEY_D45}"
            )
        if rid in seen:
            raise ValueError(f"重复 policy group id {rid!r}")
        seen.add(rid)
        yield rid, row


def build_d45_groups_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: Any,
) -> Any:
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for rid, row in iter_d45_group_rows(payload):
        row_keys.append(rid)
        for column_key, _c, _m, _vt, json_path, _h in MANAGED_FIELD_SPECS_D45_GROUPS:
            sk = stable_key_for_d45_group(column_key, rid)
            spec = contract.field_by_stable_key(stable_key_for_d45_group(column_key))
            values[sk] = FieldValue(
                stable_key=sk,
                value=row.get(json_path),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=rid,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={ROWS_TABLE_KEY_D45: tuple(row_keys)},
    )


def build_d45_fixed_store_projection(
    payloads_by_item: Mapping[str, str | None],
    *,
    contract: Any,
) -> Any:
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    values: dict[str, FieldValue] = {}
    for column_key, _col, _row, store_item in FIXED_FIELD_SPECS_D45:
        sk = stable_key_for_d45_fixed(column_key)
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


def merge_projection_into_d45_group_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    from app.services.workpaper_sync.json_path import set_json_path

    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS_D45_GROUPS}
    prefix = f"{ROWS_TABLE_KEY_D45}/"
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D45) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = 0
    visited = 0
    touched: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        if not sk.startswith(prefix):
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY_D45: str(rid), "bizName": ""}
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = sk.rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        if set_json_path(target, json_path, getattr(fv, "value", None)):
            applied += 1
            touched.add(str(rid))
    return [by_id[rid] for rid in order], applied, visited, touched


def merge_projection_into_d45_fixed_items(
    *,
    projection: Any,
    base_by_item: Mapping[str, str | None],
) -> dict[str, str]:
    """返回 item_id → 新 remark 文本（仅 touched）。"""
    out: dict[str, str] = {}
    for column_key, _col, _row, store_item in FIXED_FIELD_SPECS_D45:
        sk = stable_key_for_d45_fixed(column_key)
        fv = projection.get(sk) if hasattr(projection, "get") else None
        if fv is None:
            # try values dict
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
