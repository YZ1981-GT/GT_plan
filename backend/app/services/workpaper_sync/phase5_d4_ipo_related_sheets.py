# -*- coding: utf-8 -*-
"""D4-21/22/23/24 —— 追加受管 sheet（同 adapter `d4.revenue_detail`，同 workbook）。

spec: d4-21-24-oo-bidirectional-and-cross-sheet-formula · Wave 2 Task 2.1

═══ workbook 裁决（DEC1，见 evidence/T01-T02-adjudication.md）═══

D4-21~24 前端同步宿主全部 `parent_duplicate` / `independentEntry:false`，父 entry =
`xlsx/gt-d4-operating-revenue`，权威 workbook = ``D/D4 收入底稿.xlsx``（与 D4-2/3/5 同一
blob / 同一 TEMPLATE_SHA256），openpyxl 实测该合册含这四张 sheet。故本模块把它们作为
**追加受管 sheet** 挂进同一 entry，而非新建独立 entry。

═══ 四张表的行形态（Wave 1 census，openpyxl data_only=False）═══

* **D4-21 关联方销售情况及价格分析**（动态行）：表头 15，数据 16-30，无合计；边界 31
  「三、审计说明：」。11 受管列 A/B/C/D/E/F/G/H/J/L/M/N；**FORMULA_MASK = I,K**
  （`I=(G-H)/H`、`K=(G-J)/J` 差异率，内部 OO 算术）。**O 列 16-24 是 9 行静态关联关系
  图例**（勿删勿改/实际控制人/…/其他关联方），逐字保留；UUID 用 **P**（避开 O，DEC2）。
* **D4-23 收入与开具发票金额比较**（月份天然键，固定 12 行）：两级表头 10+11，数据
  12-23，footer 24「合计」。8 受管列 A/B/C/E/F/G/H/K；**FORMULA_MASK = D,I,J**
  （`D=B+C`、`I=E+G`、`J=D-I` + footer SUM）。行身份 = 月份 template_row_key。
* **D4-24 第三方回款检查**（动态行）：表头 14，数据 15-22，无合计；边界 23「三、审计说明」。
  12 受管列 A..M；无内部公式；枚举列 J/K。UUID 用 **N**（数据止 M）。
* **D4-22 重要指标分析表**（静态块 + 动态列，DEC3）：表头 11，固定指标行 12-23（12 个
  指标 template_row_key）；固定列 A 指标名 / B 本期 / C 上期 / H 合理性；**同业公司列
  D/E/F/G… 走 `{slot}_{seq}` 动态列**（禁写死列数，平台 H7/G7 范式）。UUID 用另置空列。

四张表几何/字段/mask 的 mapping_digest 冻结于本模块（gen_d4_21_24_mapping_digests.py 算得，
每张表单独锁死），运行态与磁盘契约双向核对由主模块 `assert_contract_file_matches_source` 统一。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping

from app.services.workpaper_sync.json_path import (
    JsonPathMissingSegmentError,
    resolve_json_path,
    set_json_path,
)

# 与 phase5_d4_revenue_detail 共享的模板身份（同 workbook）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "b8fb92d4c22cd5d639e415403a12cb61650639153f136a5330c930b880167b5f"
)


class D4SiblingDigestError(ValueError):
    """sibling sheet mapping_digest 漂移（与 Wave 1 census 不一致）。"""


def _digest(payload: dict) -> str:
    canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _contract_fields_digest_shape(fields) -> list[dict]:
    return [
        {"col": c, "column_key": k, "header": h, "json_path": jp, "mode": m}
        for (k, c, m, _vt, jp, h) in fields
    ]


def _resolve_store_path(row: Mapping[str, Any], json_path: str) -> Any:
    try:
        return resolve_json_path(row, json_path)
    except JsonPathMissingSegmentError:
        return None


def _encode_identity_segment(identity: str) -> str:
    """把行身份编码成 stable key 里的**单段** —— `/` 是 stable key 的段分隔符。

    🔴 D4-22 的行身份是自由文本指标名（`ROW_IDENTITY_STORE_KEY_D422='metricName'`），
    其中 `运输费用/营业收入` 含 `/`，直接嵌进 `表/{身份}/字段` 会多出一段，令
    `endpoint_payloads._resolve_stable_key` 的段级匹配（分段数须与模板一致，这是**故意**的
    fail-closed 反 `remark`↔`remark_typo` 误挂）判定为未登记 → `projection_unknown_stable_field_key`。

    修复不是放宽段级匹配（那会开 fail-open），而是让身份在进入 stable key 前**百分号编码**
    成单段：先编码 `%` 再编码 `/`（顺序保证可逆），使 `运输费用/营业收入` →
    `运输费用%2F营业收入`。store 侧数据一字不动（仍存原始 metricName），只有 stable key 与
    projection.row_key 用编码形态；merge 侧用 :func:`_decode_identity_segment` 解回原始身份
    做 `by_key` 查找。D4-21/23/24 身份是 rowId/月份，本就 `/`-free，编码是恒等无副作用。
    """
    return identity.replace("%", "%25").replace("/", "%2F")


def _decode_identity_segment(encoded: str) -> str:
    """:func:`_encode_identity_segment` 的逆（先解 `/` 再解 `%`，与编码顺序相反）。"""
    return encoded.replace("%2F", "/").replace("%25", "%")


# ═══════════════════════════════════════════════════════════════════════════
# D4-21 关联方销售情况及价格分析（动态行）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D421: Final[str] = "关联方销售情况及价格分析D4-21"
TEMPLATE_ID_D421: Final[str] = "D421"
SHEET_KEY_D421: Final[str] = f"{TEMPLATE_ID_D421.lower()}-managed"
ROWS_TABLE_KEY_D421: Final[str] = "related_party_price_rows"
STORE_ITEM_ID_D421: Final[str] = "D4-21-rows"
ROW_IDENTITY_STORE_KEY_D421: Final[str] = "rowId"

HEADER_ROW_D421: Final[int] = 15
FIRST_DATA_ROW_D421: Final[int] = 16
LAST_DATA_ROW_D421: Final[int] = 30
#: 无「合计」；边界为 A31「三、审计说明：」—— 插行须跟着下移（carries_total_formula=False）。
FOOTER_ROW_D421: Final[int] = 31
FOOTER_MARKER_D421: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D421: Final[str] = "N"
#: 🔴 UUID 避开 O 列（O16-24 是静态关联关系图例，逐字保留，DEC2/Req 1.3）。用 P。
UUID_COL_D421: Final[str] = "P"
TABLE_NAME_D421: Final[str] = f"GT_{TEMPLATE_ID_D421}_ROWS"

#: 11 受管列（I/K 差异率入 mask，不入契约）。
MANAGED_FIELD_SPECS_D421: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("party_name", "A", "editable", "text", "partyName", "关联方客户名称"),
    ("relationship", "B", "editable", "text", "relationship", "关联关系"),
    ("product", "C", "editable", "text", "product", "产品名称"),
    ("qty", "D", "editable", "amount", "qty", "销售数量"),
    ("sales_amount", "E", "editable", "amount", "salesAmount", "销售额"),
    ("sales_ratio", "F", "editable", "amount", "salesRatio", "销售额占同类产品销售额比例"),
    ("avg_price", "G", "editable", "amount", "avgPrice", "平均单价"),
    ("nonrelated_avg_price", "H", "editable", "amount", "nonrelatedAvgPrice", "非关联方销售平均单价"),
    ("fair_price", "J", "editable", "amount", "fairPrice", "可比公允价格"),
    ("prior_sales_ratio", "L", "editable", "amount", "priorSalesRatio", "上年度销售额占同类产品销售额比例"),
    ("prior_avg_price", "M", "editable", "amount", "priorAvgPrice", "上年度销售平均单价"),
    ("remark", "N", "editable", "text", "remark", "备注"),
)
#: I/K 差异率（内部 OO 算术，逐行）—— projection 不得覆盖。
FORMULA_MASK_D421: Final[tuple[str, ...]] = (
    f"I{FIRST_DATA_ROW_D421}:I{LAST_DATA_ROW_D421}",
    f"K{FIRST_DATA_ROW_D421}:K{LAST_DATA_ROW_D421}",
)
#: O 列 16-24 静态关联关系图例（保留原值；不进契约、不进 mask，属未管理静态区）。
O_COLUMN_LEGEND_D421: Final[tuple[str, ...]] = (
    "勿删、勿改", "实际控制人", "控股股东", "控股股东、实际控制人的附属企业",
    "持有5%以上股份的法人或其他组织", "联营企业", "合营企业",
    "董高监等关键管理人员", "其他关联方",
)
EXPECTED_MAPPING_DIGEST_D421: Final[str] = (
    "7bbe2588373203a79eb6182c47c60dfd14ce345cc2d24162c493000153de96b4"
)


def mapping_digest_payload_d421() -> dict[str, Any]:
    return {
        "contract_fields": _contract_fields_digest_shape(MANAGED_FIELD_SPECS_D421),
        "first_data_row": FIRST_DATA_ROW_D421,
        "footer_marker_exact": FOOTER_MARKER_D421,
        "footer_row": FOOTER_ROW_D421,
        "header_row": HEADER_ROW_D421,
        "last_data_row": LAST_DATA_ROW_D421,
        "managed_sheet": MANAGED_SHEET_D421,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }


def assert_mapping_digest_d421() -> str:
    got = _digest(mapping_digest_payload_d421())
    if got != EXPECTED_MAPPING_DIGEST_D421:
        raise D4SiblingDigestError(
            f"D4-21 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D421}"
        )
    if len(MANAGED_FIELD_SPECS_D421) != 12:
        raise D4SiblingDigestError(f"D4-21 契约字段数须为 12，实得 {len(MANAGED_FIELD_SPECS_D421)}")
    return got


def stable_key_for_d421(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D421}/{row_identity}/{column_key}"


def rows_table_payload_d421() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D421}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D421:
        fields.append(
            {
                "stable_field_key": stable_key_for_d421(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D421}"),
                "header_source_ref": _src(f"{column}{HEADER_ROW_D421}"),
                "store_item_id": STORE_ITEM_ID_D421,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D421,
        "anchor": f"A{HEADER_ROW_D421}",
        "header_rows": 1,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D421}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER_D421,
            "search_column": "A",
            "carries_total_formula": False,
            "note": (
                "无「合计」footer；A31「三、审计说明：」是受管区下边界（插行须下移）。"
                "I/K 差异率为内部公式入 mask；O16-24 静态关联关系图例逐字保留、UUID 用 P。"
            ),
        },
        "formula_mask": list(FORMULA_MASK_D421),
        "fields": fields,
    }


def split_store_row_d421(
    row: Mapping[str, Any], *, row_identity: str, contract: Any
) -> Iterator[tuple[str, Any, Any]]:
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS_D421:
        spec = contract.field_by_stable_key(stable_key_for_d421(column_key))
        yield stable_key_for_d421(column_key, row_identity), _resolve_store_path(row, json_path), spec


def merge_projection_into_d421_store_rows(
    *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    return _merge_flat_rows(
        projection=projection,
        base_rows=base_rows,
        table_key=ROWS_TABLE_KEY_D421,
        identity_key=ROW_IDENTITY_STORE_KEY_D421,
        field_specs=MANAGED_FIELD_SPECS_D421,
        seed_first_field="partyName",
    )


def instrumentation_spec_d421(*, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D421,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D421,
        first_data_row=FIRST_DATA_ROW_D421,
        last_data_row=LAST_DATA_ROW_D421,
        footer_row=FOOTER_ROW_D421,
        managed_last_col=MANAGED_LAST_COL_D421,
        uuid_col=UUID_COL_D421,
        table_name=TABLE_NAME_D421,
    )


# ═══════════════════════════════════════════════════════════════════════════
# D4-24 第三方回款检查（动态行）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D424: Final[str] = "第三方回款检查D4-24"
TEMPLATE_ID_D424: Final[str] = "D424"
SHEET_KEY_D424: Final[str] = f"{TEMPLATE_ID_D424.lower()}-managed"
ROWS_TABLE_KEY_D424: Final[str] = "third_party_receipt_rows"
STORE_ITEM_ID_D424: Final[str] = "D4-24-rows"
ROW_IDENTITY_STORE_KEY_D424: Final[str] = "rowId"

HEADER_ROW_D424: Final[int] = 14
FIRST_DATA_ROW_D424: Final[int] = 15
LAST_DATA_ROW_D424: Final[int] = 22
FOOTER_ROW_D424: Final[int] = 23
FOOTER_MARKER_D424: Final[str] = "三、审计说明："
MANAGED_LAST_COL_D424: Final[str] = "M"
UUID_COL_D424: Final[str] = "N"
TABLE_NAME_D424: Final[str] = f"GT_{TEMPLATE_ID_D424}_ROWS"

MANAGED_FIELD_SPECS_D424: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("seq", "A", "editable", "text", "seq", "序号"),
    ("customer_name", "B", "editable", "text", "customerName", "客户名称"),
    ("annual_sales", "C", "editable", "amount", "annualSales", "本年度销售金额"),
    ("ending_ar", "D", "editable", "amount", "endingAr", "期末应收账款余额"),
    ("third_party_amount", "E", "editable", "amount", "thirdPartyAmount", "本年度第三方回款金额"),
    ("payer_name", "F", "editable", "text", "payerName", "第三方回款方名称"),
    ("reason", "G", "editable", "text", "reason", "第三方回款原因"),
    ("payer_customer_relation", "H", "editable", "text", "payerCustomerRelation", "第三方回款方与客户关系"),
    ("payer_entity_relation", "I", "editable", "text", "payerEntityRelation", "第三方回款方与被审计单位关系"),
    ("has_payment_agreement", "J", "editable", "text", "hasPaymentAgreement", "是否有代付协议"),
    ("is_confirmed", "K", "editable", "text", "isConfirmed", "是否函证"),
    ("rationality", "L", "editable", "text", "rationality", "合理性分析"),
    ("index_no", "M", "editable", "text", "indexNo", "索引"),
)
FORMULA_MASK_D424: Final[tuple[str, ...]] = ()  # 无内部业务公式
EXPECTED_MAPPING_DIGEST_D424: Final[str] = (
    "49a96a60800253c075ebf25e744bd745d8e4c39719882fffab24e65518781955"
)


def mapping_digest_payload_d424() -> dict[str, Any]:
    return {
        "contract_fields": _contract_fields_digest_shape(MANAGED_FIELD_SPECS_D424),
        "first_data_row": FIRST_DATA_ROW_D424,
        "footer_marker_exact": FOOTER_MARKER_D424,
        "footer_row": FOOTER_ROW_D424,
        "header_row": HEADER_ROW_D424,
        "last_data_row": LAST_DATA_ROW_D424,
        "managed_sheet": MANAGED_SHEET_D424,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }


def assert_mapping_digest_d424() -> str:
    got = _digest(mapping_digest_payload_d424())
    if got != EXPECTED_MAPPING_DIGEST_D424:
        raise D4SiblingDigestError(
            f"D4-24 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D424}"
        )
    if len(MANAGED_FIELD_SPECS_D424) != 13:
        raise D4SiblingDigestError(f"D4-24 契约字段数须为 13，实得 {len(MANAGED_FIELD_SPECS_D424)}")
    return got


def stable_key_for_d424(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D424}/{row_identity}/{column_key}"


def rows_table_payload_d424() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D424}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D424:
        fields.append(
            {
                "stable_field_key": stable_key_for_d424(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D424}"),
                "header_source_ref": _src(f"{column}{HEADER_ROW_D424}"),
                "store_item_id": STORE_ITEM_ID_D424,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D424,
        "anchor": f"A{HEADER_ROW_D424}",
        "header_rows": 1,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D424}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER_D424,
            "search_column": "A",
            "carries_total_formula": False,
            "note": (
                "无「合计」footer；A23「三、审计说明：」是受管区下边界。无内部公式；"
                "J/K 为是否枚举列。A24 含导航引用 <E1-31>/<D2-7>（走 cross_wp_references）。"
            ),
        },
        "formula_mask": list(FORMULA_MASK_D424),
        "fields": fields,
    }


def split_store_row_d424(
    row: Mapping[str, Any], *, row_identity: str, contract: Any
) -> Iterator[tuple[str, Any, Any]]:
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS_D424:
        spec = contract.field_by_stable_key(stable_key_for_d424(column_key))
        yield stable_key_for_d424(column_key, row_identity), _resolve_store_path(row, json_path), spec


def merge_projection_into_d424_store_rows(
    *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    return _merge_flat_rows(
        projection=projection,
        base_rows=base_rows,
        table_key=ROWS_TABLE_KEY_D424,
        identity_key=ROW_IDENTITY_STORE_KEY_D424,
        field_specs=MANAGED_FIELD_SPECS_D424,
        seed_first_field="seq",
    )


def instrumentation_spec_d424(*, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D424,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D424,
        first_data_row=FIRST_DATA_ROW_D424,
        last_data_row=LAST_DATA_ROW_D424,
        footer_row=FOOTER_ROW_D424,
        managed_last_col=MANAGED_LAST_COL_D424,
        uuid_col=UUID_COL_D424,
        table_name=TABLE_NAME_D424,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 共享：扁平行 merge（D4-21 / D4-24 共用）
# ═══════════════════════════════════════════════════════════════════════════


def _merge_flat_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
    table_key: str,
    identity_key: str,
    field_specs,
    seed_first_field: str,
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    field_to_path = {spec[0]: spec[4] for spec in field_specs}
    prefix = f"{table_key}/"
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(identity_key) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = visited = 0
    touched: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        if not sk.startswith(prefix):
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid_raw = getattr(fv, "row_key", None)
        if not rid_raw:
            continue
        # row_key 是 build 侧编码形态；解回原始身份查 store（rowId 本 `/`-free，解码恒等）。
        rid = _decode_identity_segment(str(rid_raw))
        target = by_id.get(str(rid))
        if target is None:
            target = {identity_key: str(rid), seed_first_field: ""}
            by_id[str(rid)] = target
            order.append(str(rid))
        json_path = field_to_path.get(sk.rsplit("/", 1)[-1])
        if not json_path:
            continue
        visited += 1
        if set_json_path(target, json_path, getattr(fv, "value", None)):
            applied += 1
            touched.add(str(rid))
    return [by_id[rid] for rid in order], applied, visited, touched


# ═══════════════════════════════════════════════════════════════════════════
# D4-23 收入与开具发票金额比较（固定 12 月行，month template_row_key）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D423: Final[str] = "收入与开具发票金额比较分析D4-23"
TEMPLATE_ID_D423: Final[str] = "D423"
SHEET_KEY_D423: Final[str] = f"{TEMPLATE_ID_D423.lower()}-managed"
ROWS_TABLE_KEY_D423: Final[str] = "invoice_compare_rows"
STORE_ITEM_ID_D423: Final[str] = "D4-23-rows"
ROW_IDENTITY_STORE_KEY_D423: Final[str] = "month"

HEADER_ROWS_D423: Final[tuple[int, int]] = (10, 11)
FIRST_DATA_ROW_D423: Final[int] = 12
LAST_DATA_ROW_D423: Final[int] = 23
FOOTER_ROW_D423: Final[int] = 24
FOOTER_MARKER_D423: Final[str] = "合计"
MANAGED_LAST_COL_D423: Final[str] = "K"
UUID_COL_D423: Final[str] = "L"
TABLE_NAME_D423: Final[str] = f"GT_{TEMPLATE_ID_D423}_ROWS"

#: 12 个月份行（天然键，固定行；template_row_key = 月份文本）。
MONTH_ROW_KEYS_D423: Final[tuple[str, ...]] = tuple(f"{i}月" for i in range(1, 13))

#: 8 受管列（D/I/J 内部公式入 mask，不入契约）。
MANAGED_FIELD_SPECS_D423: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("month", "A", "editable", "text", "month", "月份"),
    ("main_revenue", "B", "editable", "amount", "mainRevenue", "主营业务收入"),
    ("other_revenue", "C", "editable", "amount", "otherRevenue", "其他业务收入"),
    ("vat_invoice_amount", "E", "editable", "amount", "vatInvoiceAmount", "增值税发票金额"),
    ("vat_invoice_count", "F", "editable", "amount", "vatInvoiceCount", "防伪税控开具的增值税发票份数"),
    ("plain_invoice_amount", "G", "editable", "amount", "plainInvoiceAmount", "普通发票金额"),
    ("plain_invoice_count", "H", "editable", "amount", "plainInvoiceCount", "开具的普通发票份数"),
    ("index_no", "K", "editable", "text", "indexNo", "索引号"),
)
#: D=B+C（营业收入合计）、I=E+G（申报合计）、J=D-I（差异）+ footer SUM —— 内部算术入 mask。
FORMULA_MASK_D423: Final[tuple[str, ...]] = (
    f"D{FIRST_DATA_ROW_D423}:D{LAST_DATA_ROW_D423}",
    f"I{FIRST_DATA_ROW_D423}:I{LAST_DATA_ROW_D423}",
    f"J{FIRST_DATA_ROW_D423}:J{LAST_DATA_ROW_D423}",
)
EXPECTED_MAPPING_DIGEST_D423: Final[str] = (
    "773034a17f0839765981d0566aa80fb0aada1f68622d4b19053195a8ac130c9d"
)


def mapping_digest_payload_d423() -> dict[str, Any]:
    return {
        "contract_fields": _contract_fields_digest_shape(MANAGED_FIELD_SPECS_D423),
        "first_data_row": FIRST_DATA_ROW_D423,
        "footer_marker_exact": FOOTER_MARKER_D423,
        "footer_row": FOOTER_ROW_D423,
        "header_row": HEADER_ROWS_D423[1],
        "header_rows": list(HEADER_ROWS_D423),
        "last_data_row": LAST_DATA_ROW_D423,
        "managed_sheet": MANAGED_SHEET_D423,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }


def assert_mapping_digest_d423() -> str:
    got = _digest(mapping_digest_payload_d423())
    if got != EXPECTED_MAPPING_DIGEST_D423:
        raise D4SiblingDigestError(
            f"D4-23 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D423}"
        )
    if len(MANAGED_FIELD_SPECS_D423) != 8:
        raise D4SiblingDigestError(f"D4-23 契约字段数须为 8，实得 {len(MANAGED_FIELD_SPECS_D423)}")
    return got


def stable_key_for_d423(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D423}/{row_identity}/{column_key}"


def rows_table_payload_d423() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D423}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D423:
        fields.append(
            {
                "stable_field_key": stable_key_for_d423(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D423}"),
                "header_source_ref": _src(f"{column}{HEADER_ROWS_D423[1]}"),
                "store_item_id": STORE_ITEM_ID_D423,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D423,
        "anchor": f"A{HEADER_ROWS_D423[0]}",
        "header_rows": 2,
        "row_identity": {
            "kind": "template_row_key",
            "template_row_key": ROW_IDENTITY_STORE_KEY_D423,
        },
        # 固定 12 月行，不允许新增/删除 → reject（删除请求一律拒绝）。
        "delete_policy": "reject",
        "footer_anchor": {
            "marker": FOOTER_MARKER_D423,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "两级表头 10+11；数据 12-23 = 1月..12月固定行（月份天然键，不新增/删除）；"
                "A24「合计」footer 带 SUM。D/I/J 为内部算术入 mask。"
            ),
        },
        "formula_mask": list(FORMULA_MASK_D423),
        "fields": fields,
    }


def split_store_row_d423(
    row: Mapping[str, Any], *, row_identity: str, contract: Any
) -> Iterator[tuple[str, Any, Any]]:
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS_D423:
        spec = contract.field_by_stable_key(stable_key_for_d423(column_key))
        yield stable_key_for_d423(column_key, row_identity), _resolve_store_path(row, json_path), spec


def merge_projection_into_d423_store_rows(
    *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """固定 12 月行：按 month 键 merge；不新增行（月份不变），未命中月份忽略。"""
    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS_D423}
    prefix = f"{ROWS_TABLE_KEY_D423}/"
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D423) or "").strip()
        if not rid:
            continue
        by_key[rid] = dict(row)
        order.append(rid)
    # 缺失月份补齐（保证 12 行齐整）
    for mk in MONTH_ROW_KEYS_D423:
        if mk not in by_key:
            by_key[mk] = {ROW_IDENTITY_STORE_KEY_D423: mk}
            order.append(mk)

    applied = visited = 0
    touched: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        if not sk.startswith(prefix):
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid_raw = getattr(fv, "row_key", None)
        # row_key 是 build 侧编码形态；解回原始月份键（月份本 `/`-free，解码恒等）。
        rid = _decode_identity_segment(str(rid_raw)) if rid_raw else None
        target = by_key.get(str(rid)) if rid else None
        if target is None:
            continue  # 月份固定，未知键不新增
        json_path = field_to_path.get(sk.rsplit("/", 1)[-1])
        if not json_path:
            continue
        visited += 1
        if set_json_path(target, json_path, getattr(fv, "value", None)):
            applied += 1
            touched.add(str(rid))
    return [by_key[rid] for rid in order], applied, visited, touched


def instrumentation_spec_d423(*, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D423,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D423,
        first_data_row=FIRST_DATA_ROW_D423,
        last_data_row=LAST_DATA_ROW_D423,
        footer_row=FOOTER_ROW_D423,
        managed_last_col=MANAGED_LAST_COL_D423,
        uuid_col=UUID_COL_D423,
        table_name=TABLE_NAME_D423,
    )


# ═══════════════════════════════════════════════════════════════════════════
# D4-22 重要指标分析表（静态块 + 动态列，DEC3）
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_D422: Final[str] = "重要指标分析表D4-22"
TEMPLATE_ID_D422: Final[str] = "D422"
SHEET_KEY_D422: Final[str] = f"{TEMPLATE_ID_D422.lower()}-managed"
ROWS_TABLE_KEY_D422: Final[str] = "key_indicator_rows"
STORE_ITEM_ID_D422: Final[str] = "D4-22-rows"
ROW_IDENTITY_STORE_KEY_D422: Final[str] = "metricName"

HEADER_ROW_D422: Final[int] = 11
FIRST_DATA_ROW_D422: Final[int] = 12
LAST_DATA_ROW_D422: Final[int] = 23
FOOTER_ROW_D422: Final[int] = 24
FOOTER_MARKER_D422: Final[str] = "三、审计说明"
#: 同业动态列从 D 起。固定列到 C（本期/上期）；H 合理性在动态列右侧。
#: managed_last_col 必须覆盖到动态列可能扩到的最右——取 H（模板 ……占位在 G，H 合理性）。
MANAGED_LAST_COL_D422: Final[str] = "H"
UUID_COL_D422: Final[str] = "I"
TABLE_NAME_D422: Final[str] = f"GT_{TEMPLATE_ID_D422}_ROWS"

#: 12 个固定指标行（template_row_key = 指标名称；固定行、不新增/删除）。
METRIC_ROW_KEYS_D422: Final[tuple[str, ...]] = (
    "年度预算", "主营业务收入", "销售人员数量", "销售人员人均创收",
    "销售区域分布是否变化（占比和区域数量等）", "销售人员业绩指标", "销售人员薪酬",
    "期末在手订单", "息税前利润（利润总额＋财务费用）",
    "薪酬总额（支付给职工以及为职工支付的现金+期末应付职工薪酬-期初应付职工薪酬）",
    "人力投入回报率(ROP)", "运输费用/营业收入",
)

#: 固定列（4 个）：A 指标名（行身份）/ B 本期 / C 上期 / H 合理性分析。
MANAGED_FIELD_SPECS_D422: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("metric_name", "A", "editable", "text", "metricName", "指标名称"),
    ("current_period", "B", "editable", "amount", "currentPeriod", "本期"),
    ("prior_period", "C", "editable", "amount", "priorPeriod", "上期"),
    ("rationality", "H", "editable", "text", "rationality", "合理性分析"),
)
#: 同业列锚点（D 起）。稳定 key = `{slot}_{seq}`（peer_1, peer_2, …），
#: store 侧 peers 数组下标 seq；禁写死列数，禁用 label 作 key（平台 H7/G7 范式）。
DYNAMIC_PEER_SLOT_D422: Final[str] = "peer"
DYNAMIC_PEER_FIRST_COL_D422: Final[str] = "D"
DYNAMIC_PEER_LABEL_ROW_D422: Final[int] = 11
FORMULA_MASK_D422: Final[tuple[str, ...]] = ()  # 无内部业务公式
EXPECTED_MAPPING_DIGEST_D422: Final[str] = (
    "890ad39a1ce36491423320392e67ed9703b27f19d165c54d73a5c9bb14c47e37"
)


def mapping_digest_payload_d422() -> dict[str, Any]:
    p = {
        "contract_fields": _contract_fields_digest_shape(MANAGED_FIELD_SPECS_D422),
        "first_data_row": FIRST_DATA_ROW_D422,
        "footer_marker_exact": FOOTER_MARKER_D422,
        "footer_row": FOOTER_ROW_D422,
        "header_row": HEADER_ROW_D422,
        "last_data_row": LAST_DATA_ROW_D422,
        "managed_sheet": MANAGED_SHEET_D422,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
    }
    p["fixed_metric_rows"] = list(METRIC_ROW_KEYS_D422)
    p["dynamic_columns"] = {
        "slot": DYNAMIC_PEER_SLOT_D422,
        "anchor_first_col": DYNAMIC_PEER_FIRST_COL_D422,
        "label_row": DYNAMIC_PEER_LABEL_ROW_D422,
        "note": "同业公司列，{slot}_{seq} 稳定键，禁写死列数",
    }
    return p


def assert_mapping_digest_d422() -> str:
    got = _digest(mapping_digest_payload_d422())
    if got != EXPECTED_MAPPING_DIGEST_D422:
        raise D4SiblingDigestError(
            f"D4-22 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D422}"
        )
    if len(MANAGED_FIELD_SPECS_D422) != 4:
        raise D4SiblingDigestError(f"D4-22 固定契约字段数须为 4，实得 {len(MANAGED_FIELD_SPECS_D422)}")
    if len(METRIC_ROW_KEYS_D422) != 12:
        raise D4SiblingDigestError(f"D4-22 固定指标行须为 12，实得 {len(METRIC_ROW_KEYS_D422)}")
    return got


def stable_key_for_d422(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY_D422}/{row_identity}/{column_key}"


def rows_table_payload_d422() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D422}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in MANAGED_FIELD_SPECS_D422:
        fields.append(
            {
                "stable_field_key": stable_key_for_d422(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW_D422}"),
                "header_source_ref": _src(f"{column}{HEADER_ROW_D422}"),
                "store_item_id": STORE_ITEM_ID_D422,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY_D422,
        "anchor": f"A{HEADER_ROW_D422}",
        "header_rows": 1,
        "row_identity": {
            "kind": "template_row_key",
            "template_row_key": ROW_IDENTITY_STORE_KEY_D422,
        },
        # 固定 12 指标行，不允许新增/删除 → reject。
        "delete_policy": "reject",
        # 🔴 同业公司列（D 起）走 **HTML store 侧动态**（peers[] 数组，{slot}_{seq} 稳定键，
        #    见 D4_22_PEER_* 常量），**不**在契约里声明 Excel `dynamic_columns`：
        #    materializer 的 assert_dynamic_column_binding_usable 要求每次 materialize 都拿到
        #    `{slot}_{seq}`→Excel 列的实测 binding（G7 pilot 范式），本 entry 与 D4-2/3/5 共享
        #    同一 contract，声明它会让所有 sibling sheet 的 materialize 一律 fail-closed。
        #    peers 由前端 store 持有与渲染；Excel 侧 D~G 空占位列在 OO 往返中保持原样
        #    （不进受管 projection、由未管理区域比对保护）。
        "footer_anchor": {
            "marker": FOOTER_MARKER_D422,
            "search_column": "A",
            "carries_total_formula": False,
            "note": (
                "固定 12 指标行（12-23，template_row_key=指标名称）；本期 B/上期 C/合理性 H "
                "为固定列；同业公司列 D 起为 HTML store 侧 peers[] 动态数据（{slot}_{seq}），"
                "不在 Excel 契约声明 dynamic_columns；A24 下边界。"
            ),
        },
        "formula_mask": list(FORMULA_MASK_D422),
        "fields": fields,
    }


def split_store_row_d422(
    row: Mapping[str, Any], *, row_identity: str, contract: Any
) -> Iterator[tuple[str, Any, Any]]:
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS_D422:
        spec = contract.field_by_stable_key(stable_key_for_d422(column_key))
        yield stable_key_for_d422(column_key, row_identity), _resolve_store_path(row, json_path), spec


def merge_projection_into_d422_store_rows(
    *, projection: Any, base_rows: list[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """固定 12 指标行：按 metricName 键 merge 固定列；动态 peer 列由 sibling binding 处理。"""
    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS_D422}
    prefix = f"{ROWS_TABLE_KEY_D422}/"
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY_D422) or "").strip()
        if not rid:
            continue
        by_key[rid] = dict(row)
        order.append(rid)
    for mk in METRIC_ROW_KEYS_D422:
        if mk not in by_key:
            by_key[mk] = {ROW_IDENTITY_STORE_KEY_D422: mk}
            order.append(mk)

    applied = visited = 0
    touched: set[str] = set()
    for key in projection.stable_keys():
        sk = str(key)
        if not sk.startswith(prefix):
            continue
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid_raw = getattr(fv, "row_key", None)
        # row_key 是编码形态（build 侧编码），解回原始 metricName 才能命中 store by_key。
        rid = _decode_identity_segment(str(rid_raw)) if rid_raw else None
        target = by_key.get(str(rid)) if rid else None
        if target is None:
            continue
        json_path = field_to_path.get(sk.rsplit("/", 1)[-1])
        if not json_path:
            continue
        visited += 1
        if set_json_path(target, json_path, getattr(fv, "value", None)):
            applied += 1
            touched.add(str(rid))
    return [by_key[rid] for rid in order], applied, visited, touched


def instrumentation_spec_d422(*, entry_id: str, template_relative_path: str):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D422,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D422,
        first_data_row=FIRST_DATA_ROW_D422,
        last_data_row=LAST_DATA_ROW_D422,
        footer_row=FOOTER_ROW_D422,
        managed_last_col=MANAGED_LAST_COL_D422,
        uuid_col=UUID_COL_D422,
        table_name=TABLE_NAME_D422,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 统一断言（供主模块 assert_mapping_digest 调用）
# ═══════════════════════════════════════════════════════════════════════════


def assert_all_sibling_mapping_digests() -> dict[str, str]:
    return {
        "D4-21": assert_mapping_digest_d421(),
        "D4-22": assert_mapping_digest_d422(),
        "D4-23": assert_mapping_digest_d423(),
        "D4-24": assert_mapping_digest_d424(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# store projection builders（HTML store JSON → FieldValue projection）
# ═══════════════════════════════════════════════════════════════════════════


def _iter_store_rows(payload, *, identity_key: str, item_id: str):
    """行对象数组迭代（稳定身份，禁下标兜底、禁重复；与主模块 iter_store_rows 同口径）。"""
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows = json.loads(text)
        except ValueError as exc:
            raise D4SiblingDigestError(f"{item_id} remark 非合法 JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise D4SiblingDigestError(f"{item_id} 载荷必须是行对象数组，实得 {type(rows).__name__}")
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise D4SiblingDigestError(f"{item_id} 第 {ordinal} 项不是对象")
        raw = row.get(identity_key)
        if not isinstance(raw, str) or not raw.strip():
            raise D4SiblingDigestError(
                f"{item_id} 第 {ordinal} 行缺稳定行身份 {identity_key!r}（禁下标兜底）"
            )
        identity = raw.strip()
        if identity in seen:
            raise D4SiblingDigestError(f"{item_id} 重复行身份 {identity!r}")
        seen.add(identity)
        yield identity, row


def _build_projection(
    payload, *, contract, table_key, identity_key, item_id, field_specs, stable_key_fn, limits=None
):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _iter_store_rows(payload, identity_key=identity_key, item_id=item_id):
        budget.add_row(table_key)
        # 身份编码成单段，使含 `/` 的自由文本指标名（D4-22）不撑破 stable key 段级匹配。
        # row_key 与 stable key 用**同一**编码形态（否则 _resolve_stable_key 的
        # embedded != row_key 会误判）；merge 侧解码回原始身份查 store。
        enc_identity = _encode_identity_segment(identity)
        row_keys.append(enc_identity)
        for column_key, _c, _m, _vt, json_path, _h in field_specs:
            spec = contract.field_by_stable_key(stable_key_fn(column_key))
            budget.add_field()
            sk = stable_key_fn(column_key, enc_identity)
            values[sk] = FieldValue(
                stable_key=sk,
                value=_resolve_store_path(row, json_path),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=enc_identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={table_key: tuple(row_keys)},
    )


def build_d421_store_projection(payload, *, contract, limits=None):
    return _build_projection(
        payload, contract=contract, table_key=ROWS_TABLE_KEY_D421,
        identity_key=ROW_IDENTITY_STORE_KEY_D421, item_id=STORE_ITEM_ID_D421,
        field_specs=MANAGED_FIELD_SPECS_D421, stable_key_fn=stable_key_for_d421, limits=limits)


def build_d424_store_projection(payload, *, contract, limits=None):
    return _build_projection(
        payload, contract=contract, table_key=ROWS_TABLE_KEY_D424,
        identity_key=ROW_IDENTITY_STORE_KEY_D424, item_id=STORE_ITEM_ID_D424,
        field_specs=MANAGED_FIELD_SPECS_D424, stable_key_fn=stable_key_for_d424, limits=limits)


def build_d423_store_projection(payload, *, contract, limits=None):
    return _build_projection(
        payload, contract=contract, table_key=ROWS_TABLE_KEY_D423,
        identity_key=ROW_IDENTITY_STORE_KEY_D423, item_id=STORE_ITEM_ID_D423,
        field_specs=MANAGED_FIELD_SPECS_D423, stable_key_fn=stable_key_for_d423, limits=limits)


def build_d422_store_projection(payload, *, contract, limits=None):
    return _build_projection(
        payload, contract=contract, table_key=ROWS_TABLE_KEY_D422,
        identity_key=ROW_IDENTITY_STORE_KEY_D422, item_id=STORE_ITEM_ID_D422,
        field_specs=MANAGED_FIELD_SPECS_D422, stable_key_fn=stable_key_for_d422, limits=limits)
