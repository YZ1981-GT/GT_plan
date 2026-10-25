# -*- coding: utf-8 -*-
"""D4-35「其他业务收入检查表」—— 追加受管 sheet（同 adapter `d4.revenue_detail`，同 workbook）。

spec: d4-33-36-writeback-formula-and-io-closure · Wave 3（双向回写）

═══ 结构：均质单区抽凭检查表（17 列 A-Q）═══

与 D4-3 同构（单 sheet、单表头区、均质行、footer 合计），照抄 phase5_d4_other_revenue_sheet 范式。
差异点：
* 两级表头（13/14 行）—— 核对内容 H13:N13 合并，子号 1-6 在 H14:M14；本 provider 受管 6 个核对子列 H-M。
* store 嵌套 ``{rows, sampling, periodAmount}`` —— 受管的是 ``rows`` 数组（均质行）；
  ``sampling``（抽样参数区 8-10 行，非表格行）与 ``periodAmount`` 走 HTML 独立字段，不进 Excel Table 受管区。
* ``isAnomalous`` 是 string（是/否/空），``check1..6`` 是 √/空 —— 均按 text 走。

受管几何：数据 15-25（11 行），footer「合计」A26（F26 有 SUM 公式），本期发生额 A27 / 检查比例 A28。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping

#: 与 phase5_d4_revenue_detail 共享的模板身份（同 workbook）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)

MANAGED_SHEET_D435: Final[str] = "其他业务收入检查表D4-35"
TEMPLATE_ID_D435: Final[str] = "D435"
SHEET_KEY_D435: Final[str] = f"{TEMPLATE_ID_D435.lower()}-managed"

HEADER_ROWS_D435: Final[tuple[int, int]] = (13, 14)
FIRST_DATA_ROW_D435: Final[int] = 15
LAST_DATA_ROW_D435: Final[int] = 25
FOOTER_ROW_D435: Final[int] = 26
FOOTER_MARKER_D435: Final[str] = "合计"

MANAGED_LAST_COL_D435: Final[str] = "Q"
UUID_COL_D435: Final[str] = "R"
TABLE_NAME_D435: Final[str] = f"GT_{TEMPLATE_ID_D435}_ROWS"

STORE_ITEM_ID_D435: Final[str] = "D4-35-data"
ROWS_TABLE_KEY_D435: Final[str] = "other_revenue_check_rows"
ROW_IDENTITY_STORE_KEY_D435: Final[str] = "id"

#: 冻结的列映射摘要（本 provider 首交付即冻结，防后续漂移）。
EXPECTED_MAPPING_DIGEST_D435: Final[str] = (
    "67082d36b06053d607e6697967b8f5ce5f91cfaeae4892a543994a1544bb9b00"
)

#: 16 个契约字段：`(column_key, 列标, mode, value_type, store json 路径, 表头文本)`。
#: rows 数组内每行的字段；派生列（合计/检查比例在 footer，不进受管行）。
MANAGED_FIELD_SPECS_D435: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("date", "A", "editable", "text", "date", "日期"),
    ("voucher_no", "B", "editable", "text", "voucherNo", "凭证编号"),
    ("content", "C", "editable", "text", "content", "业务内容"),
    ("counter_account", "D", "editable", "text", "counterAccount", "对方科目"),
    ("detail_account", "E", "editable", "text", "detailAccount", "明细科目"),
    ("amount", "F", "editable", "amount", "amount", "金额"),
    ("support_doc", "G", "editable", "text", "supportDoc", "支持性文件"),
    ("check1", "H", "editable", "text", "check1", "核对1"),
    ("check2", "I", "editable", "text", "check2", "核对2"),
    ("check3", "J", "editable", "text", "check3", "核对3"),
    ("check4", "K", "editable", "text", "check4", "核对4"),
    ("check5", "L", "editable", "text", "check5", "核对5"),
    ("check6", "M", "editable", "text", "check6", "核对6"),
    ("index_ref", "O", "editable", "text", "indexRef", "索引号"),
    ("is_anomalous", "P", "editable", "text", "isAnomalous", "是否异常"),
    ("remark", "Q", "editable", "text", "remark", "备注说明"),
)


def mapping_digest_payload_d435() -> dict[str, Any]:
    """列映射摘要 payload（锁定字段映射与 template sha 未漂移）。"""
    return {
        "managed_sheet": MANAGED_SHEET_D435,
        "header_rows": list(HEADER_ROWS_D435),
        "first_data_row": FIRST_DATA_ROW_D435,
        "last_data_row": LAST_DATA_ROW_D435,
        "footer_row": FOOTER_ROW_D435,
        "footer_marker_exact": FOOTER_MARKER_D435,
        "contract_fields": [
            {"col": col, "store_key": json_path, "value_type": value_type}
            for _ck, col, _mode, value_type, json_path, _hdr in MANAGED_FIELD_SPECS_D435
        ],
        "mask_cols": [],  # D4-35 受管列均为录入，无 sheet 内公式列（F26 合计在 footer 外）
        "template_sha256": TEMPLATE_SHA256,
    }


def compute_mapping_digest_d435() -> str:
    canon = json.dumps(
        mapping_digest_payload_d435(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def assert_mapping_digest_d435() -> str:
    got = compute_mapping_digest_d435()
    if got != EXPECTED_MAPPING_DIGEST_D435:
        raise ValueError(
            f"D4-35 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D435}"
        )
    if len(MANAGED_FIELD_SPECS_D435) != 16:
        raise ValueError(
            f"D4-35 契约字段数必须为 16，实得 {len(MANAGED_FIELD_SPECS_D435)}"
        )
    return got


def stable_key_for_d435(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D435}/{row_identity}/{column_key}"


def rows_table_payload_d435(*, excel_name: str = MANAGED_SHEET_D435) -> dict[str, Any]:
    """契约 ``sheets[].tables[]`` 条目（header_rows=2）。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D435:
        fields.append(
            {
                "stable_field_key": stable_key_for_d435(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D435}"),
                "header_source_ref": _src(f"{column}{HEADER_ROWS_D435[1]}"),
                "store_item_id": STORE_ITEM_ID_D435,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D435,
        "anchor": f"A{HEADER_ROWS_D435[0]}",
        "header_rows": 2,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D435}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER_D435,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "footer 行 A26「合计」（F26 有 SUM 金额公式）；A27「本期发生额」、"
                "A28「检查比例」（#DIV/0! 公式）为衍生统计，不进受管区（15..25）。"
                "sampling(8-10 行) 与 periodAmount 是非行参数，走 HTML store 独立字段，不进 Excel Table。"
            ),
        },
        "formula_mask": [],
        "fields": fields,
    }


def _resolve_d435_store_path(row: Mapping[str, Any], json_path: str) -> Any:
    from app.services.workpaper_sync.json_path import (
        JsonPathMissingSegmentError,
        resolve_json_path,
    )

    try:
        return resolve_json_path(row, json_path)
    except JsonPathMissingSegmentError:
        return None


def split_store_row_d435(
    row: Mapping[str, Any], *, row_identity: str, contract: Any
) -> Iterator[tuple[str, Any, Any]]:
    """按 D4-35 十六字段拆行 → ``(stable_key, value, FieldSpec)``。"""
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS_D435:
        spec = contract.field_by_stable_key(stable_key_for_d435(column_key))
        yield (
            stable_key_for_d435(column_key, row_identity),
            _resolve_d435_store_path(row, json_path),
            spec,
        )


def merge_projection_into_d435_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把 extract projection 合进 D4-35 rows（扁平字段，均质行）。

    只消费 ``other_revenue_check_rows/*`` 键；sampling/periodAmount 由 HTML 端保留。
    """
    from app.services.workpaper_sync.json_path import set_json_path

    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS_D435}
    prefix = f"{ROWS_TABLE_KEY_D435}/"
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D435) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = 0
    visited = 0
    touched_rows: set[str] = set()
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
            target = {ROW_IDENTITY_STORE_KEY_D435: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = sk.rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if set_json_path(target, json_path, new_val):
            applied += 1
            touched_rows.add(str(rid))

    return [by_id[rid] for rid in order], applied, visited, touched_rows


def instrumentation_spec_d435(*, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D435,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D435,
        first_data_row=FIRST_DATA_ROW_D435,
        last_data_row=LAST_DATA_ROW_D435,
        footer_row=FOOTER_ROW_D435,
        managed_last_col=MANAGED_LAST_COL_D435,
        uuid_col=UUID_COL_D435,
        table_name=TABLE_NAME_D435,
    )


def _iter_d435_rows(payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """从 D4-35 dict store（{rows,sampling,periodAmount}）迭代受管行 → (identity, row)。

    payload 可为 dict / JSON 字符串 / bytes；rows 每行须有稳定 id（不得退回数组下标）。
    """
    import json as _json

    data: Any = payload
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    if isinstance(data, str):
        try:
            data = _json.loads(data) if data.strip() else {}
        except ValueError as exc:
            raise ValueError(f"{STORE_ITEM_ID_D435} 的 remark 不是合法 JSON: {exc}") from exc
    rows = data.get("rows") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        return
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{STORE_ITEM_ID_D435} 第 {ordinal} 行不是对象")
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D435) or "").strip()
        if not rid:
            raise ValueError(
                f"{STORE_ITEM_ID_D435} 第 {ordinal} 行缺稳定行身份 "
                f"{ROW_IDENTITY_STORE_KEY_D435!r} —— 不得退回数组下标作身份"
            )
        if rid in seen:
            raise ValueError(f"{STORE_ITEM_ID_D435} 出现重复行身份 {rid!r}")
        seen.add(rid)
        yield rid, row


def build_d435_store_projection(
    payload: Any,
    *,
    contract: Any,
    limits: Any | None = None,
) -> Any:
    """把 D4-35 dict store 的 rows 投影成 other_revenue_check_rows/* FieldValue。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, Any] = {}
    row_keys: list[str] = []
    for identity, row in _iter_d435_rows(payload):
        budget.add_row(ROWS_TABLE_KEY_D435)
        row_keys.append(identity)
        for stable_key, value, spec in split_store_row_d435(
            row, row_identity=identity, contract=contract
        ):
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=value,
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={ROWS_TABLE_KEY_D435: tuple(row_keys)},
    )
