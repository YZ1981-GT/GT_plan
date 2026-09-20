# -*- coding: utf-8 -*-
"""D4-14「营业收入发生检查表」（穿行测试）—— 追加受管 sheet（同 adapter `d4.revenue_detail`，同 workbook）。

spec: d4-14-walkthrough-writeback · 裁决=路线 A 全受管（业务复核 2026-09-21 签署）

═══ 结构：单宽动态行表（每行一笔交易，横向 37 物理列覆盖 7 个证据维度）═══

引擎范式同 D4-35（`phase5_d4_other_check_sheet`）：单 sheet、两级表头、均质动态行、单行 footer。
差异点（本 provider 独有）：
* **7 维嵌套 json_pointer**：受管字段路径为 `voucher/customerName`、`invoice/amount` 等嵌套路径
  （store `TransactionItem` 是 7 维 sub-object），非 D4-35 的扁平字段。`resolve_json_path`/`set_json_path`
  原生支持嵌套 dict 段。
* **store 直接是数组**（`D4-14-transactions` = `TransactionItem[]`），非 D4-35 的 `{rows,...}` dict 包装。
  故契约 row_identity/json_pointer 前缀是 `/{row_uuid}/...`（无 `/rows` 包装），迭代直接遍历 list（同 D4-7 products）。
* **行身份 = 前端 `id`**（`t-<时间戳>-<random>` 稳定 id，跨会话不变），UUID 列 AL。

受管几何（openpyxl 冻结 `evidence/d414-geometry.json`）：
  两级表头 R13(组)/R14(子字段)；数据区 R15-R36（22 行）；footer marker `合计` A37；
  formula_mask = G37/X37/AF37（SUM 合计）+ G39（=G37/G38 检查比例，footer 下辅助行）；UUID 列 AL（物理列止于 AK）。

裁决（路线 A 全受管，见 `evidence/d414-column-mapping-adjudication.md`）：
  B-AF 全部数据列受管（A 序号=派生自增不入契约；AG/AH=`……` 占位不入契约）；AI/AJ/AK 受管。
  无 HTML-only 数据列（HTML-only 仅 R1-12 / R37-52 说明结论段，走 sampling/note/conclusion 独立 store）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping

#: 与 phase5_d4_revenue_detail 共享的模板身份（同 workbook）。
ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"

MANAGED_SHEET_D414: Final[str] = "营业收入发生检查表D4-14"
TEMPLATE_ID_D414: Final[str] = "D414"
SHEET_KEY_D414: Final[str] = f"{TEMPLATE_ID_D414.lower()}-managed"

HEADER_ROWS_D414: Final[tuple[int, int]] = (13, 14)
FIRST_DATA_ROW_D414: Final[int] = 15
LAST_DATA_ROW_D414: Final[int] = 36
FOOTER_ROW_D414: Final[int] = 37
FOOTER_MARKER_D414: Final[str] = "合计"

MANAGED_LAST_COL_D414: Final[str] = "AK"
UUID_COL_D414: Final[str] = "AL"
TABLE_NAME_D414: Final[str] = f"GT_{TEMPLATE_ID_D414}_ROWS"

STORE_ITEM_ID_D414: Final[str] = "D4-14-transactions"
ROWS_TABLE_KEY_D414: Final[str] = "walkthrough_transactions"
ROW_IDENTITY_STORE_KEY_D414: Final[str] = "id"

#: footer 行 SUM 合计（G37/X37/AF37）+ 检查比例 G39（footer 下辅助行）。数据区列全受管录入。
FORMULA_MASK_D414: Final[tuple[str, ...]] = ("G37", "X37", "AF37", "G39")

#: 34 个受管字段：`(column_key, 列标, mode, value_type, 嵌套 json_path, 表头文本)`。
#: 严格按裁决表（物理列权威）逐列；A 序号=派生自增、AG/AH=占位 均不入契约。
#: value_type：金额=amount；数量前端为 string 型故 text；日期/编号/名称=text。
MANAGED_FIELD_SPECS_D414: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    # 记账凭证组物理列 = B 客户名称 / C 日期 / D 编号 / E 品名 / F 数量 / G 金额（实测源模板 R13-14）。
    # 前端 voucher.month / voucher.accountingDate 在源模板**无对应物理列**，是前端派生字段，
    # 故不入受管区（materialize 不写、extract 不读），OO→HTML merge 时随前端 store 逐字保留。
    ("voucher_customer_name", "B", "editable", "text", "voucher/customerName", "客户名称"),
    ("voucher_date", "C", "editable", "text", "voucher/date", "凭证日期"),
    ("voucher_number", "D", "editable", "text", "voucher/number", "凭证编号"),
    ("voucher_product_name", "E", "editable", "text", "voucher/productName", "凭证品名"),
    ("voucher_quantity", "F", "editable", "text", "voucher/quantity", "凭证数量"),
    ("voucher_amount", "G", "editable", "amount", "voucher/amount", "凭证金额"),
    # 销售合同（H-I）
    ("contract_date", "H", "editable", "text", "contract/date", "合同日期"),
    ("contract_number", "I", "editable", "text", "contract/number", "合同号/订单号"),
    # 出库单（J-M）+ 仓库保管员 N + 发货审批人 O
    ("delivery_date", "J", "editable", "text", "delivery/date", "出库日期"),
    ("delivery_number", "K", "editable", "text", "delivery/number", "出库编号"),
    ("delivery_product_name", "L", "editable", "text", "delivery/productName", "出库品名"),
    ("delivery_quantity", "M", "editable", "text", "delivery/quantity", "出库数量"),
    ("delivery_warehouse_keeper", "N", "editable", "text", "delivery/warehouseKeeper", "仓库保管员"),
    ("delivery_shipping_approver", "O", "editable", "text", "delivery/shippingApprover", "发货审批人"),
    # 运输单（P-T）
    ("shipping_date", "P", "editable", "text", "shipping/date", "运输日期"),
    ("shipping_number", "Q", "editable", "text", "shipping/number", "运输编号"),
    ("shipping_quantity", "R", "editable", "text", "shipping/quantity", "运输数量"),
    ("shipping_company", "S", "editable", "text", "shipping/company", "运输公司"),
    ("shipping_address", "T", "editable", "text", "shipping/address", "运输地址"),
    # 签收单（U-AA）
    ("receipt_date", "U", "editable", "text", "receipt/date", "签收日期"),
    ("receipt_product_name", "V", "editable", "text", "receipt/productName", "签收品名"),
    ("receipt_quantity", "W", "editable", "text", "receipt/quantity", "签收数量"),
    ("receipt_amount", "X", "editable", "amount", "receipt/amount", "签收金额"),
    ("receipt_signer", "Y", "editable", "text", "receipt/signer", "签收人"),
    ("receipt_seal_type", "Z", "editable", "text", "receipt/sealType", "盖章类型"),
    ("receipt_seal_entity", "AA", "editable", "text", "receipt/sealEntity", "盖章单位"),
    # 发票（AB-AF）
    ("invoice_date", "AB", "editable", "text", "invoice/date", "发票日期"),
    ("invoice_number", "AC", "editable", "text", "invoice/number", "发票编号"),
    ("invoice_product_name", "AD", "editable", "text", "invoice/productName", "发票品名"),
    ("invoice_quantity", "AE", "editable", "text", "invoice/quantity", "发票数量"),
    ("invoice_amount", "AF", "editable", "amount", "invoice/amount", "发票金额"),
    # 其他（AI 说明 / AJ 索引号 / AK 是否异常）
    ("other_description", "AI", "editable", "text", "other/description", "其他支持性文件或说明"),
    ("other_index_no", "AJ", "editable", "text", "other/indexNo", "索引号"),
    ("other_anomaly_note", "AK", "editable", "text", "other/anomalyNote", "是否异常"),
)


def mapping_digest_payload_d414() -> dict[str, Any]:
    """列映射摘要 payload（锁定字段映射未漂移）。"""
    return {
        "managed_sheet": MANAGED_SHEET_D414,
        "header_rows": list(HEADER_ROWS_D414),
        "first_data_row": FIRST_DATA_ROW_D414,
        "last_data_row": LAST_DATA_ROW_D414,
        "footer_row": FOOTER_ROW_D414,
        "footer_marker_exact": FOOTER_MARKER_D414,
        "uuid_col": UUID_COL_D414,
        "formula_mask": list(FORMULA_MASK_D414),
        "contract_fields": [
            {"col": col, "json_path": json_path, "value_type": value_type}
            for _ck, col, _mode, value_type, json_path, _hdr in MANAGED_FIELD_SPECS_D414
        ],
    }


def mapping_digest_d414() -> str:
    canon = json.dumps(
        mapping_digest_payload_d414(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def stable_key_for_d414(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D414}/{row_identity}/{column_key}"


def rows_table_payload_d414(*, excel_name: str = MANAGED_SHEET_D414) -> dict[str, Any]:
    """契约 ``sheets[].tables[]`` 条目（header_rows=2，7 维嵌套 json_pointer，store 直接是数组）。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D414:
        fields.append(
            {
                "stable_field_key": stable_key_for_d414(column_key),
                # store 直接是数组：行即 TransactionItem，无 /rows 包装 → /{row_uuid}/<嵌套路径>
                "json_pointer": f"/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D414}"),
                "header_source_ref": _src(f"{column}{HEADER_ROWS_D414[1]}"),
                "store_item_id": STORE_ITEM_ID_D414,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D414,
        "anchor": f"A{HEADER_ROWS_D414[0]}",
        "header_rows": 2,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/*/{ROW_IDENTITY_STORE_KEY_D414}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER_D414,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "footer 行 A37「合计」（G37/X37/AF37 SUM 金额公式）；A38「本期发生额」、"
                "A39「检查比例」（G39=G37/G38 公式）为衍生统计，不进受管区（15..36）。"
                "sampling / auditNote / auditConclusion 走 HTML 独立 store，不进 Excel Table。"
            ),
        },
        "formula_mask": list(FORMULA_MASK_D414),
        "fields": fields,
    }


def _resolve_d414_store_path(row: Mapping[str, Any], json_path: str) -> Any:
    from app.services.workpaper_sync.json_path import (
        JsonPathMissingSegmentError,
        resolve_json_path,
    )

    try:
        return resolve_json_path(row, json_path)
    except JsonPathMissingSegmentError:
        return None


def split_store_row_d414(
    row: Mapping[str, Any], *, row_identity: str, contract: Any
) -> Iterator[tuple[str, Any, Any]]:
    """按 D4-14 受管字段拆行 → ``(stable_key, value, FieldSpec)``（7 维嵌套读值）。"""
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS_D414:
        spec = contract.field_by_stable_key(stable_key_for_d414(column_key))
        yield (
            stable_key_for_d414(column_key, row_identity),
            _resolve_d414_store_path(row, json_path),
            spec,
        )


def _iter_d414_rows(payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """从 D4-14 store（TransactionItem[] 数组）迭代受管行 → (identity, row)。

    payload 可为 list / JSON 字符串 / bytes；每行须有稳定 id（不得退回数组下标）。
    """
    data: Any = payload
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    if isinstance(data, str):
        try:
            data = json.loads(data) if data.strip() else []
        except ValueError as exc:
            raise ValueError(f"{STORE_ITEM_ID_D414} 的 remark 不是合法 JSON: {exc}") from exc
    if not isinstance(data, list):
        return  # legacy 容差：非数组视为空，不打挂全 entry
    seen: set[str] = set()
    for ordinal, row in enumerate(data):
        if not isinstance(row, Mapping):
            raise ValueError(f"{STORE_ITEM_ID_D414} 第 {ordinal} 行不是对象")
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D414) or "").strip()
        if not rid:
            raise ValueError(
                f"{STORE_ITEM_ID_D414} 第 {ordinal} 行缺稳定行身份 "
                f"{ROW_IDENTITY_STORE_KEY_D414!r} —— 不得退回数组下标作身份"
            )
        if rid in seen:
            raise ValueError(f"{STORE_ITEM_ID_D414} 出现重复行身份 {rid!r}")
        seen.add(rid)
        yield rid, row


def build_d414_store_projection(
    payload: Any,
    *,
    contract: Any,
    limits: Any | None = None,
) -> Any:
    """把 D4-14 store（TransactionItem[]）投影成 walkthrough_transactions/* FieldValue。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, Any] = {}
    row_keys: list[str] = []
    for identity, row in _iter_d414_rows(payload):
        budget.add_row(ROWS_TABLE_KEY_D414)
        row_keys.append(identity)
        for stable_key, value, spec in split_store_row_d414(
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
        row_keys={ROWS_TABLE_KEY_D414: tuple(row_keys)},
    )


def merge_projection_into_d414(
    *,
    projection: Any,
    base_payload: Any,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把 extract projection 合进 D4-14 交易行（7 维嵌套写值，均质行）。

    只消费 ``walkthrough_transactions/*`` 键；HTML-only 维度字段（前端派生 / 说明结论）由 HTML 端保留。
    返回 (新交易数组, applied, visited, touched_rows) —— 4-tuple 形态供 oo_to_html mirror 消费。
    """
    from app.services.workpaper_sync.json_path import set_json_path

    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS_D414}
    prefix = f"{ROWS_TABLE_KEY_D414}/"

    base = base_payload
    if isinstance(base, (bytes, bytearray)):
        base = base.decode("utf-8")
    if isinstance(base, str):
        try:
            base = json.loads(base) if base.strip() else []
        except ValueError:
            base = []
    container = base if isinstance(base, list) else []

    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in container:
        if not isinstance(row, Mapping):
            continue
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D414) or "").strip()
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
            target = {ROW_IDENTITY_STORE_KEY_D414: str(rid)}
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


def instrumentation_spec_d414(*, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D414,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D414,
        first_data_row=FIRST_DATA_ROW_D414,
        last_data_row=LAST_DATA_ROW_D414,
        footer_row=FOOTER_ROW_D414,
        managed_last_col=MANAGED_LAST_COL_D414,
        uuid_col=UUID_COL_D414,
        table_name=TABLE_NAME_D414,
        sheet_key=SHEET_KEY_D414,
    )


def instrumentation_specs_d414(*, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH) -> tuple[Any, ...]:
    return (instrumentation_spec_d414(entry_id=entry_id, template_relative_path=template_relative_path),)


def sheet_payload_d414() -> dict[str, Any]:
    return {
        "sheet_key": SHEET_KEY_D414,
        "excel_name": MANAGED_SHEET_D414,
        "template_id": TEMPLATE_ID_D414,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [rows_table_payload_d414()],
    }


def store_item_ids_d414() -> tuple[str, ...]:
    return (STORE_ITEM_ID_D414,)
