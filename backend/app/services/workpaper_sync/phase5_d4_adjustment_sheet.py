# -*- coding: utf-8 -*-
"""D4-4 营业收入调整分录汇总双向回写 provider。

spec: d4-4-adjustment-summary-bidirectional-writeback · Task 3/4

单张受管 sheet、单张动态行 table，共享 D4 revenue entry `xlsx/gt-d4-operating-revenue`
（本表是该 entry 下第 36 张受管 sheet，也是 D4 全组最后一张脱离 `single_html` 的表）。

几何（openpyxl 直读 `D/D4 收入底稿.xlsx` sheet `营业收入调整分录汇总D4-4`，A1:J23 —— 全部
11 项已由 spec Task 1 现算逐条对账，零更正）：
  · 单级表头 R5（A~J 十列全非空）；数据区 R6~R20（15 行）；footer marker A21「提示：」（63 字）
  · 受管列 **A~J 连续十列无跳**，与前端 `D4AdjustmentRow` 的 10 个业务字段 1:1 双射
  · 数据区公式格 **0**、非空格 **0**、无合并单元格（合并仅标题 A1:J1 / A2:J2）
  · UUID 载体列 **K**：模板 K~O 五列本就全空，紧邻受管末列 J 右侧 ⇒ **无需注入列**
    （对比参照实现 D4-19 是「模板无空列 → 注入列 P」才落地的）

与参照实现 `phase5_d4_discount_sheet.py`（D4-19）的 **4 处差异**，逐条标注在下方常量处：
  1. 行身份键是 `rowId` 而非 `id`；
  2. `formula_mask` 为**空**（数据区公式格现算 0；借贷合计/平衡差额是前端 `computed` 不落 cell）；
  3. UUID 列用现成空列 K（非注入）；
  4. 行身份**两种格式并存** ⇒ `_rows()` 禁加格式正则（见 `_rows` docstring）。

前端真源：`D4TabAdjustment.vue` + store item `D4-4-rows`（JSON 数组）。

🔴 本 provider 的 `merge_projection_into_d44_rows` 返回**裸 list**（同 D4-19），因此
`STORE_ITEM_ID_D44` 必须登记进 `phase5_d4_revenue_detail._RAW_PAYLOAD_ITEM_TABLE_KEYS`，
否则 `_normalize_merge_updates` 归一不到 4-tuple ⇒ `store_mirror.py` 的硬解包
`for item_id, (merged_rows, applied, _visited, _touched) in updates.items()` 抛 `ValueError`
⇒ **打挂整个 entry 的回写**（D4-8 踩过这个坑）。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.json_path import resolve_json_path

ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4 收入底稿.xlsx"

MANAGED_SHEET_D44: Final[str] = "营业收入调整分录汇总D4-4"
TEMPLATE_ID_D44: Final[str] = "D44"
SHEET_KEY_D44: Final[str] = "d44-managed"
STORE_ITEM_ID_D44: Final[str] = "D4-4-rows"
TABLE_KEY_D44: Final[str] = "d4_4_rows"

#: 🔴 差异 1/4：行身份键是 `rowId`（前端 `D4AdjustmentRow.rowId`），**不是** D4-19 的 `id`。
ROW_IDENTITY_KEY_D44: Final[str] = "rowId"

HEADER_ROW_D44: Final[int] = 5
FIRST_DATA_ROW_D44: Final[int] = 6
LAST_DATA_ROW_D44: Final[int] = 20
FOOTER_ROW_D44: Final[int] = 21
#: A21 完整文本 63 字，取前缀作 marker（引擎按前缀搜 A 列定位 footer 锚）。
FOOTER_MARKER_D44: Final[str] = "提示："
MANAGED_LAST_COL_D44: Final[str] = "J"
#: 🔴 差异 3/4：模板 K~O 五列全空，取紧邻 J 右侧首个 ⇒ 现成载体，无需注入。
UUID_COL_D44: Final[str] = "K"

#: 受管字段 10 个，与前端 `D4AdjustmentRow` 的 10 个业务字段 1:1（`rowId` 是身份不计入）。
#: 元组形态 `(field, col, mode, value_type, json_key, header_text)` —— 与 D4-19 同构。
#:
#: 🔴 `stable_field_key` 经 `_snake()` 全小写（`reportItem` → `report_item` 等），而
#:    `json_pointer` / store 写回**保持驼峰**（前端真源）。两者刻意分离：D4-8 曾直接用驼峰
#:    前端字段名生成 180 个含大写的非法 key，打挂整份契约 parse。
MANAGED_FIELD_SPECS_D44: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("description", "A", "editable", "text", "description", "调整事项说明"),
    ("category", "B", "editable", "text", "category", "类别（报表调整/账项调整/其他）"),
    ("reportItem", "C", "editable", "text", "reportItem", "报表项目"),
    ("accountName", "D", "editable", "text", "accountName", "科目名称"),
    ("noteItem", "E", "editable", "text", "noteItem", "附注项目"),
    ("placeholder", "F", "editable", "text", "placeholder", "……"),
    ("debitAmount", "G", "editable", "amount", "debitAmount", "借方调整金额"),
    ("creditAmount", "H", "editable", "amount", "creditAmount", "贷方调整金额"),
    ("indexRef", "I", "editable", "text", "indexRef", "索引"),
    ("remark", "J", "editable", "text", "remark", "备注"),
)

#: 🔴 差异 2/4：`formula_mask` 为**空**。判据（Req 2.2，Task 1 已现算）：
#:    ① 数据区 R6~R20 公式格数 = 0；
#:    ② 借贷合计 `debitTotal`/`creditTotal`、平衡差额 `balanceDiff`/`isBalanced` 全是前端
#:       `computed`，**不落 cell**（与 D4-19 的 E 列折扣比例不同 —— 那一列模板里有派生位）。
#:    ⇒ 契约 schema 校验 CS-13「formula 字段必须落在 formula_mask 内」在本表是**空分母成立**
#:      （本表无 `mode="formula"` 字段），不得因 `formula_mask` 为空而被误判违规。
_FORMULA_MASK_D44: Final[tuple[str, ...]] = ()


def _snake(field: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def stable_key_for_d44(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY_D44}/{identity}/{_snake(field)}"


def formula_mask_cells_d44() -> tuple[str, ...]:
    return _FORMULA_MASK_D44


def mapping_digest_payload_d44() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET_D44,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "header_row": HEADER_ROW_D44,
        "first_data_row": FIRST_DATA_ROW_D44,
        "last_data_row": LAST_DATA_ROW_D44,
        "footer_row": FOOTER_ROW_D44,
        "footer_marker": FOOTER_MARKER_D44,
        "uuid_col": UUID_COL_D44,
        "fields": list(MANAGED_FIELD_SPECS_D44),
        "formula_mask": list(_FORMULA_MASK_D44),
    }


def mapping_digest_d44() -> str:
    payload = json.dumps(mapping_digest_payload_d44(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sheet_payload_d44() -> dict[str, Any]:
    def _src(cell: str) -> str:
        return f"源xlsx!{MANAGED_SHEET_D44}!{cell}"

    fields = [
        {
            "stable_field_key": stable_key_for_d44(f[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{f[4]}",
            "column_key": _snake(f[0]),
            "cell": {"column": f[1], "row_from": "row_identity"},
            "mode": f[2],
            "value_type": f[3],
            "source_ref": _src(f"{f[1]}{FIRST_DATA_ROW_D44}"),
            "header_source_ref": _src(f"{f[1]}{HEADER_ROW_D44}"),
            "store_item_id": STORE_ITEM_ID_D44,
            "header_text": f[5],
        }
        for f in MANAGED_FIELD_SPECS_D44
    ]
    return {
        "sheet_key": SHEET_KEY_D44,
        "excel_name": MANAGED_SHEET_D44,
        "template_id": TEMPLATE_ID_D44,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [
            {
                "table_key": TABLE_KEY_D44,
                # anchor = 表头行 A5（= 首数据行 - 1，同 D4-19 的约定）。
                "anchor": f"A{FIRST_DATA_ROW_D44 - 1}",
                "header_rows": 1,
                "row_identity": {
                    "kind": "field",
                    "json_pointer": f"/rows/*/{ROW_IDENTITY_KEY_D44}",
                },
                "delete_policy": "tombstone",
                # footer marker 是 R21 的提示文本，**不承载合计公式** ⇒
                # `carries_total_formula=False`（Req 6.4：插行不得覆盖该提示文本）。
                "footer_anchor": {
                    "marker": FOOTER_MARKER_D44,
                    "search_column": "A",
                    "carries_total_formula": False,
                },
                "formula_mask": list(_FORMULA_MASK_D44),
                "fields": fields,
            }
        ],
    }


def instrumentation_spec_d44(
    *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH
):
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_D44,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D44,
        first_data_row=FIRST_DATA_ROW_D44,
        last_data_row=LAST_DATA_ROW_D44,
        footer_row=FOOTER_ROW_D44,
        managed_last_col=MANAGED_LAST_COL_D44,
        uuid_col=UUID_COL_D44,
        table_name=f"GT_{TEMPLATE_ID_D44}_ROWS",
        sheet_key=SHEET_KEY_D44,
    )


def _decode(payload: Any) -> Any:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        if not payload.strip():
            return []
        try:
            return json.loads(payload)
        except ValueError:
            # 🔴 容差（T4）：坏 JSON 视为空载荷而不是抛。本 provider 与其余 35 张 sheet
            #    共享同一个 entry，任何一处抛异常都会**打挂整个 entry** 的 rematerialize
            #    （D4-9 真实踩过：对 legacy 形态抛 StorePayloadError 卡死全 entry）。
            return []
    return payload


def _rows(payload: Any) -> list[tuple[str, Mapping[str, Any]]]:
    """store 载荷 → `[(identity, row), ...]`。

    ═══ 校验分两层，强度刻意不同（T4 / design §4）═══

    **容器层容差**（None / 空串 / 坏 JSON / 非 list 一律当空载荷，**不抛**）：
    这些形态代表「这个 store item 还没被用过」或「是 legacy 形态」——都是正常状态。
    本 provider 与另外 35 张 sheet 共享 entry `xlsx/gt-d4-operating-revenue`，
    在这里抛异常会让**整个 entry** 的 rematerialize 卡死（D4-9 的真实事故）。

    **行层 fail-closed**（缺 `rowId` / `rowId` 重复 → 抛 `ValueError`）：
    这是「数据真的坏了」。静默跳过会丢行身份，而丢身份的后果是 materialize 在错误的
    受管区插行、extract 反读出错位字段 key —— 那类缺陷极难归因（D4-1 的 W22 错位身份
    追了七层才定位）。所以行身份必须可见地失败，不得退回数组下标作身份（Property 23）。

    🔴 **禁加 rowId 格式正则**（差异 4/4，design §4）：本表行身份**两种格式并存** ——
    前端 `generateRowId()` 产 `d4a-{base36时间}-{7位随机}`（如 `d4a-ms2p8tkl-juz5kck`），
    导入侧 `_parse_d4_4_row` 产标准 `uuid4()`。两者都是唯一字符串，引擎只要求身份稳定。
    写 `assert rowId.startswith('d4a-')` 之类断言会让导入产生的行在下次 sync 时被拒。
    """
    value = _decode(payload)
    if not isinstance(value, list):
        return []
    out: list[tuple[str, Mapping[str, Any]]] = []
    seen: set[str] = set()
    for ordinal, row in enumerate(value):
        if not isinstance(row, Mapping):
            # 容器层容差的延伸：非对象元素跳过而不打挂全 entry。
            continue
        rid = str(row.get(ROW_IDENTITY_KEY_D44) or "").strip()
        if not rid:
            raise ValueError(
                f"{STORE_ITEM_ID_D44}[{ordinal}] 缺少行身份 {ROW_IDENTITY_KEY_D44!r} —— "
                "不得退回数组下标作身份（Property 23）"
            )
        if rid in seen:
            raise ValueError(
                f"{STORE_ITEM_ID_D44} 行身份 {rid!r} 重复（第 {ordinal} 项）—— 不得静默合并"
            )
        seen.add(rid)
        out.append((rid, row))
    return out


def build_store_projection_d44(payload: Any, *, contract: Any, limits: Any | None = None):
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _rows(payload):
        row_keys.append(identity)
        for field, _col, mode, value_type, path, _label in MANAGED_FIELD_SPECS_D44:
            value = resolve_json_path(row, path) if "/" in path else row.get(path)
            sk = stable_key_for_d44(field, identity)
            # `value_type`/`mode` 必须经枚举转换后再进 FieldValue —— 裸字符串会在下游
            # 比较/归一处静默失配（D4-19 与 ipo_interview 两处都修过这个既有 bug）。
            values[sk] = FieldValue(
                stable_key=sk,
                value=value,
                value_type=ValueType(value_type),
                mode=FieldMode(mode),
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY_D44: tuple(row_keys)},
    )


def merge_projection_into_d44_rows(*, projection: Any, base_payload: Any) -> Any:
    """projection → store 行数组（**返回裸 list**，同 D4-19）。

    🔴 返回裸 list 意味着 `STORE_ITEM_ID_D44` 必须登记进
    `phase5_d4_revenue_detail._RAW_PAYLOAD_ITEM_TABLE_KEYS`，否则
    `_normalize_merge_updates` 归一不到 4-tuple ⇒ `store_mirror.py` 的硬解包抛
    `ValueError` ⇒ 打挂整个 entry 的回写。

    只回写受管的 10 个字段；base 里的其它键（以及未受管字段）原样保留，行序按 base。
    """
    base = _decode(base_payload)
    container = base if isinstance(base, list) else []
    rows = [
        (str(r.get(ROW_IDENTITY_KEY_D44)), dict(r))
        for r in container
        if isinstance(r, Mapping) and r.get(ROW_IDENTITY_KEY_D44)
    ]
    by_id = {i: r for i, r in rows}
    order = [i for i, _ in rows]
    prefix = TABLE_KEY_D44 + "/"
    # snake（契约侧 key 段）→ 驼峰（store 侧字段名）。两侧刻意不同，见 MANAGED_FIELD_SPECS_D44。
    snake_to_path = {_snake(s[0]): s[4] for s in MANAGED_FIELD_SPECS_D44}

    for sk in projection.stable_keys():
        if not str(sk).startswith(prefix):
            continue
        fv = projection.get(sk)
        identity = getattr(fv, "row_key", None)
        if not identity:
            continue
        parts = str(sk).split("/")
        if len(parts) < 3:
            continue
        path = snake_to_path.get(parts[2])
        target = by_id.get(identity)
        if path is None or target is None:
            continue
        target[path] = getattr(fv, "value", None)

    return [by_id[i] for i in order]


def store_item_id_d44() -> str:
    return STORE_ITEM_ID_D44
