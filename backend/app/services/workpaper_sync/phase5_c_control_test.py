# -*- coding: utf-8 -*-
"""C 控制测试汇总表的结构化投影 provider（C 循环首张 canary）。

spec: c-cycle-sync-foundation-and-first-canary · Task 22/23
entry: `xlsx/gt-c-control-test`（一条 entry 覆盖 **28** 个 wp_code —— CC-61）

═══ C 域与 D~N 的三处结构性差异（照抄 D4 会错的点）═══

1. 🔴 **store 形态是 per-field 标量行，不是 JSON 数组**。
   D4/J1 把整张表存成一个 `item_id` 的 `remark` JSON 数组；C 是**每个字段一行**
   `checklist_responses`：`C{n}-sum-{m}-{field}`（15 字段/行 ⇒ 15 行/控制点）。
   ⇒ `build_store_projection` 要从**多行**重建行对象，不是 `json.loads` 一个数组。

2. 🔴 **位置化存储槽 `m` 不得作为声明的行身份**。序列化处 `const m = i + 1`
   （`useCControlTestData.ts`）是**数组下标**，而引擎的 `RowIdentityKind` 明令
   只接受 `field` / `template_row_key`，且 `FORBIDDEN_ROW_IDENTITY_KINDS` 含
   `index`/`ordinal`/`position`/`array_index`。
   ⇒ 声明的行身份取 **B 列「控制编号」`controlId`**（审计业务键）；`m` 降级为
   provider 内部的存储槽下标，不出现在契约里。merge 时按 `controlId` 定位目标行、
   回写到它当前占用的 `m` 槽 —— 于是 HTML 侧重排行不再错位到别的 Excel 行。

3. 🔴 **一 entry 覆盖 14 本同构主册**。C2~C15 各自独立成册（C2 册…C15 册），
   而契约的 `template.relative_path` 只能声明**一本**。本 canary 声明 **C2 册**为
   权威样本；C3~C15 的 13 本已实证与 C2 六项指标逐值一致（公式格 12 / 裸 IF 0 /
   definedName 0-0 / 超列 0 / max_col 18 / 表头逐字相同），按同一 sheet_payload 扩。

═══ 几何（openpyxl 逐格实测 `C/C2 销售循环控制测试.xlsx` 的 `C2控制测试汇总表`）═══

  · r1/r2 标题（merged A1:O1 / A2:O2）· r3/r4 页眉（6 个跨 sheet 引用公式）
  · r5 「下拉选择」提示行（**不是表头也不是数据**）
  · **r6 表头**：15 列 A~O 逐字为
    子流程 / 控制编号 / 控制名称 / 详细控制描述 / 受影响的交易、账户余额和披露 /
    认定 / 控制属性 / 控制频率 / 与控制相关的风险 / 测试方法 / 范围（样本量）/
    是否识别出偏差 / 整改期间（如有）/ 识别出的缺陷 / 索引号
  · **数据区 r7~r21**（15 行，模板内全空 —— 待填底稿）
  · **r22 = `提示1：与控制相关的风险`** ⇒ footer 边界（引擎要求 footer_row > last_data_row）
  · 🔴 **数据区零公式**（全册 6 个公式全在 r3/r4 页眉）⇒ `formula_mask` 为空
  · max_column = 15（O）且 last_value_col = 15 ⇒ UUID 列放 **P**
  · 无 Excel Table · `ws.protection.sheet=False` ⇒ locked 惰性
  · 数据区 r7~r21 **无 merged**（merged 全在 r1/r2 标题与 r23+ 提示区）

前端真源：`GtCControlTest.vue` + `useCControlTestData.ts`（`SummaryRow` 15 字段与
15 列一一对应）。
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Final

from app.services.workpaper_sync.models import SyncDomainError
from dataclasses import dataclass
from app.services.workpaper_sync.models import AuthorityModel
from app.services.workpaper_sync.definitions import DefinitionKind
from app.services.workpaper_sync.definitions import BundleSlot


class EntrySelectionError(SyncDomainError):
    """冻结的 C canary entry 不再满足选型必要条件（manifest / 模板 / digest 漂移）。"""

    error_code = "sync_phase5_c_selection_invalid"


class StorePayloadError(SyncDomainError):
    """C 控制测试 store 载荷形态不合法（缺行身份 / 行身份重复）。"""

    error_code = "sync_phase5_c_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_c_control_test_summary"
ENTRY_ID: Final[str] = "xlsx/gt-c-control-test"
ADAPTER_ID: Final[str] = "c2.control_test_summary"

#: 🔴 本 entry 的真实 wp_code 是 **28 个**（`C2`~`C15` 主册 + `C2-2`~`C15-2` 偏差册，
#: 经 `wp_code_overrides.json` 反查 componentType `c-control-test` 现算）。
#: manifest 的 `wp_code_patterns` 是**空数组**（pattern_less 跨循环共享宿主）⇒
#: matcher 不能靠 pattern，必须用真实码集合（CC-1 / CC-61）。
WP_CODES_MAIN: Final[tuple[str, ...]] = tuple(f"C{n}" for n in range(2, 16))
WP_CODES_DEVIATION: Final[tuple[str, ...]] = tuple(f"C{n}-2" for n in range(2, 16))
WP_CODES: Final[frozenset[str]] = frozenset(WP_CODES_MAIN + WP_CODES_DEVIATION)

#: 本 canary 声明的权威样本册（14 本同构主册之一）。
CANARY_CYCLE_NUMBER: Final[int] = 2
TEMPLATE_RELATIVE_PATH: Final[str] = "C/C2 销售循环控制测试.xlsx"
#: openpyxl 实测（29135 B）。漂移即 `assert_entry_selectable` 打红。
TEMPLATE_SHA256: Final[str] = (
    "1f3035e9f78b1561cd1a418249d4ccc5a7aea77d7bf074bc7b1ac235328aaa41"
)

MANAGED_SHEET: Final[str] = "C2控制测试汇总表"
TEMPLATE_ID: Final[str] = "C2SUM"
SHEET_KEY: Final[str] = "c2-summary-managed"
TABLE_KEY: Final[str] = "c_control_test_summary_rows"

# ═══════════════════════════════════════════════════════════════════════════
# 2. 几何常量（逐格实测，禁推演）
# ═══════════════════════════════════════════════════════════════════════════

HEADER_ROW: Final[int] = 6
FIRST_DATA_ROW: Final[int] = 7
LAST_DATA_ROW: Final[int] = 21
#: r22 = `提示1：与控制相关的风险`（静态说明区首行）。引擎要求 footer_row > last_data_row。
FOOTER_ROW: Final[int] = 22
FOOTER_MARKER: Final[str] = "提示1：与控制相关的风险"
MANAGED_LAST_COL: Final[str] = "O"
UUID_COL: Final[str] = "P"

# ═══════════════════════════════════════════════════════════════════════════
# 3. 受管字段规格（15 列 A~O，与前端 SummaryRow 15 字段一一对应）
# ═══════════════════════════════════════════════════════════════════════════
#
# 元组语义：`(store_field, 列标, mode, value_type, 表头原文)`
#   · `store_field` 是前端 `SummaryRow` 的字段名（也是 item_id 尾段）
#   · 表头原文取**模板原字节**（禁归一化；含全角括号「范围（样本量）」等）
#
# 🔴 `controlId`（B 列）既是受管字段**也是行身份**（见模块 docstring 差异 2）。
#    它仍作为普通 editable 字段声明 —— 行身份只是"用哪个字段定位行"，不排除它被回写。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str], ...]] = (
    ("subProcess", "A", "editable", "text", "子流程"),
    ("controlId", "B", "editable", "text", "控制编号"),
    ("controlName", "C", "editable", "text", "控制名称"),
    ("description", "D", "editable", "text", "详细控制描述"),
    ("affectedItems", "E", "editable", "text", "受影响的交易、账户余额和披露"),
    ("assertion", "F", "editable", "text", "认定"),
    ("attribute", "G", "editable", "text", "控制属性"),
    ("frequency", "H", "editable", "text", "控制频率"),
    ("relatedRisk", "I", "editable", "text", "与控制相关的风险"),
    ("testMethod", "J", "editable", "text", "测试方法"),
    ("sampleSize", "K", "editable", "amount", "范围（样本量）"),
    ("hasDeviation", "L", "editable", "text", "是否识别出偏差"),
    ("remediation", "M", "editable", "text", "整改期间（如有）"),
    ("defect", "N", "editable", "text", "识别出的缺陷"),
    ("indexRef", "O", "editable", "text", "索引号"),
)

#: 行身份字段（B 列控制编号，审计业务键）。
ROW_IDENTITY_FIELD: Final[str] = "controlId"

#: 🔴 数据区零公式 ⇒ 空 mask。写成显式常量而非省略，让「为什么是空」可追溯。
FORMULA_MASK: Final[tuple[str, ...]] = ()

#: 前端 `useCControlTestData.ts` 里存 `conclusion` 槽（枚举类）的字段集合；
#: 其余字段存 `remark` 槽。provider 读 store 时据此取值。
_CONCLUSION_SLOT_FIELDS: Final[frozenset[str]] = frozenset(
    {"assertion", "attribute", "frequency", "relatedRisk", "testMethod", "hasDeviation"}
)
#: `sampleSize` 存 conclusion 槽但是数值（前端 `String(value)` 落库）。
_NUMERIC_SLOT_FIELDS: Final[frozenset[str]] = frozenset({"sampleSize"})


def _snake(field: str) -> str:
    return re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), field)


def store_slot_of(field: str) -> str:
    """该字段落 `conclusion` 还是 `remark` 槽（与前端序列化逐值对齐）。"""
    if field in _NUMERIC_SLOT_FIELDS or field in _CONCLUSION_SLOT_FIELDS:
        return "conclusion"
    return "remark"


def summary_item_id(cycle_number: int, slot: int, field: str) -> str:
    """`C{n}-sum-{m}-{field}` —— m 是 **1-based 存储槽**（非声明行身份）。"""
    return f"C{cycle_number}-sum-{slot}-{field}"


def stable_key_for(field: str, identity: str = "{row_uuid}") -> str:
    return f"{TABLE_KEY}/{identity}/{_snake(field)}"

# ═══════════════════════════════════════════════════════════════════════════
# 4. mapping digest（几何漂移哨兵）
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    return {
        "managed_sheet": MANAGED_SHEET,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "header_row": HEADER_ROW,
        "first_data_row": FIRST_DATA_ROW,
        "last_data_row": LAST_DATA_ROW,
        "footer_row": FOOTER_ROW,
        "footer_marker": FOOTER_MARKER,
        "managed_last_col": MANAGED_LAST_COL,
        "uuid_col": UUID_COL,
        "row_identity_field": ROW_IDENTITY_FIELD,
        "fields": [list(f) for f in MANAGED_FIELD_SPECS],
        "formula_mask": list(FORMULA_MASK),
    }


def mapping_digest() -> str:
    payload = json.dumps(mapping_digest_payload(), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_mapping_digest() -> None:
    """几何声明自证（字段数 / 列序 / 区间）。漂移即抛，不静默放过。"""
    if len(MANAGED_FIELD_SPECS) != 15:
        raise EntrySelectionError(
            f"受管字段数 {len(MANAGED_FIELD_SPECS)} != 15 —— "
            "C 汇总表是 15 列 A~O，字段数变化说明几何漂移"
        )
    cols = [f[1] for f in MANAGED_FIELD_SPECS]
    expected_cols = [chr(ord("A") + i) for i in range(15)]
    if cols != expected_cols:
        raise EntrySelectionError(f"列序漂移: {cols} != {expected_cols}")
    if MANAGED_LAST_COL != expected_cols[-1]:
        raise EntrySelectionError(
            f"managed_last_col {MANAGED_LAST_COL} 应为 {expected_cols[-1]}"
        )
    if LAST_DATA_ROW - FIRST_DATA_ROW + 1 != 15:
        raise EntrySelectionError(
            f"数据区行数 {LAST_DATA_ROW - FIRST_DATA_ROW + 1} != 15"
        )
    if FOOTER_ROW <= LAST_DATA_ROW:
        raise EntrySelectionError(
            f"footer_row {FOOTER_ROW} 必须 > last_data_row {LAST_DATA_ROW}"
        )
    if ROW_IDENTITY_FIELD not in {f[0] for f in MANAGED_FIELD_SPECS}:
        raise EntrySelectionError(
            f"行身份字段 {ROW_IDENTITY_FIELD!r} 不在受管字段集合内"
        )

# ═══════════════════════════════════════════════════════════════════════════
# 5. 契约 sheet payload
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


def sheet_payload() -> dict[str, Any]:
    """单张受管 sheet / 单张动态行 table（行身份 = controlId 业务键）。"""
    fields = [
        {
            "stable_field_key": stable_key_for(spec[0]),
            "json_pointer": f"/rows/{{row_uuid}}/{spec[0]}",
            "column_key": _snake(spec[0]),
            "cell": {"column": spec[1], "row_from": "row_identity"},
            "mode": spec[2],
            "value_type": spec[3],
            "source_ref": _src(f"{spec[1]}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(f"{spec[1]}{HEADER_ROW}"),
            "header_text": spec[4],
        }
        for spec in MANAGED_FIELD_SPECS
    ]
    table: dict[str, Any] = {
        "table_key": TABLE_KEY,
        "anchor": f"A{HEADER_ROW}",
        "header_rows": 1,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_FIELD}",
        },
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": False,
        },
        "fields": fields,
        "uuid_col": UUID_COL,
    }
    if FORMULA_MASK:
        table["formula_mask"] = list(FORMULA_MASK)
    return {
        "sheet_key": SHEET_KEY,
        "excel_name": MANAGED_SHEET,
        "template_id": TEMPLATE_ID,
        "locator": {"anchor": "excel_table_sheet_association"},
        "tables": [table],
    }


def instrumentation_spec(
    *, entry_id: str = ENTRY_ID, template_relative_path: str = TEMPLATE_RELATIVE_PATH
):
    from app.services.workpaper_sync.excel_instrumentation import (
        ExcelInstrumentationSpec,
    )

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=f"GT_{TEMPLATE_ID}_ROWS",
        sheet_key=SHEET_KEY,
    )


def instrumentation_specs() -> tuple[Any, ...]:
    return (instrumentation_spec(),)

# ═══════════════════════════════════════════════════════════════════════════
# 6. store ↔ projection（🔴 C 域独有：per-field 标量行，不是 JSON 数组）
# ═══════════════════════════════════════════════════════════════════════════

#: `C{n}-sum-{m}-{field}` 解析正则。m 是 1-based 存储槽。
_SUM_ITEM_ID_RE: Final[re.Pattern[str]] = re.compile(
    r"^C(?P<cycle>\d+)-sum-(?P<slot>\d+)-(?P<field>\w+)$"
)

_FIELD_NAMES: Final[frozenset[str]] = frozenset(f[0] for f in MANAGED_FIELD_SPECS)


def parse_store_rows(
    responses: Any, *, cycle_number: int | None = None
) -> list[tuple[str, int, dict[str, Any]]]:
    """把 `checklist_responses` 多行重建成行对象列表。

    入参 `responses` 是 `[{item_id, conclusion, remark}, ...]`（端点原样返回）。

    返回 `[(identity, slot, row_dict), ...]`，按 slot 升序：
      · `identity` = `controlId` 的值（声明的行身份）
      · `slot`     = item_id 里的 `m`（内部存储槽，**不进契约**）

    🔴 与 D4/J1 的根本差异：那边 `json.loads` 一个数组；这边要**按 item_id 分组**。
    🔴 fail-closed：`controlId` 为空或重复即抛 —— 行身份不可靠时宁可拒绝，
       不能静默用下标兜底（那会把位置化身份偷偷带回来）。
    """
    if isinstance(responses, (bytes, bytearray)):
        responses = responses.decode("utf-8")
    if isinstance(responses, str):
        responses = json.loads(responses) if responses.strip() else []
    if not isinstance(responses, list):
        raise StorePayloadError(
            f"checklist_responses 载荷必须是数组，实得 {type(responses).__name__}"
        )

    by_slot: dict[int, dict[str, Any]] = {}
    for item in responses:
        if not isinstance(item, Mapping):
            continue
        item_id = str(item.get("item_id") or "").strip()
        m = _SUM_ITEM_ID_RE.match(item_id)
        if m is None:
            continue
        if cycle_number is not None and int(m.group("cycle")) != cycle_number:
            continue
        field = m.group("field")
        if field not in _FIELD_NAMES:
            continue
        slot = int(m.group("slot"))
        row = by_slot.setdefault(slot, {})
        slot_name = store_slot_of(field)
        value = item.get(slot_name)
        if value is None and slot_name == "remark":
            # 前端对部分文本字段有 `remark || conclusion` 的兼容读法
            value = item.get("conclusion")
        row[field] = value

    out: list[tuple[str, int, dict[str, Any]]] = []
    seen: set[str] = set()
    for slot in sorted(by_slot):
        row = by_slot[slot]
        identity = str(row.get(ROW_IDENTITY_FIELD) or "").strip()
        if not identity:
            raise StorePayloadError(
                f"C{cycle_number}-sum-{slot}-* 缺少行身份 {ROW_IDENTITY_FIELD!r}"
                "（B 列控制编号）—— 行身份不可靠时拒绝投影，禁用下标兜底"
            )
        if identity in seen:
            raise StorePayloadError(
                f"行身份 {identity!r} 在槽 {slot} 重复 —— 控制编号须在本循环内唯一"
            )
        seen.add(identity)
        out.append((identity, slot, row))
    return out


def build_store_projection(
    responses: Any, *, contract: Any, cycle_number: int | None = None, limits: Any | None = None
):
    """store（多行标量）→ Projection（受管字段）。"""
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.contracts import FieldMode, ValueType

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, _slot, row in parse_store_rows(responses, cycle_number=cycle_number):
        row_keys.append(identity)
        for field, _col, mode, value_type, _label in MANAGED_FIELD_SPECS:
            sk = stable_key_for(field, identity)
            values[sk] = FieldValue(
                stable_key=sk,
                value=row.get(field),
                value_type=ValueType(value_type),
                mode=FieldMode(mode),
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={TABLE_KEY: tuple(row_keys)},
    )


def merge_projection_into_store_items(
    *, projection: Any, base_responses: Any, cycle_number: int
) -> list[dict[str, Any]]:
    """OO→HTML：Projection 合并回 `checklist_responses` items。

    🔴 按 `controlId` 定位目标行，回写到它**当前占用的槽 `m`**——
    于是 HTML 侧重排行不会把数据写到别的 Excel 行上（差异 2 的落地点）。
    🔴 只覆盖受管字段；未在 projection 里出现的行/字段原样保留（不做删除）。
    """
    existing = parse_store_rows(base_responses, cycle_number=cycle_number)
    slot_of_identity = {identity: slot for identity, slot, _ in existing}
    next_slot = (max(slot_of_identity.values()) + 1) if slot_of_identity else 1

    prefix = TABLE_KEY + "/"
    # 先按 row_key 聚合 projection 的字段值
    merged: dict[str, dict[str, Any]] = {}
    for sk in projection.stable_keys():
        key = str(sk)
        if not key.startswith(prefix):
            continue
        fv = projection.get(sk)
        identity = getattr(fv, "row_key", None)
        if not identity:
            continue
        parts = key.split("/")
        if len(parts) < 3:
            continue
        snake = parts[2]
        field = next(
            (f[0] for f in MANAGED_FIELD_SPECS if _snake(f[0]) == snake), None
        )
        if field is None:
            continue
        merged.setdefault(str(identity), {})[field] = getattr(fv, "value", None)

    items: list[dict[str, Any]] = []
    for identity, fields in merged.items():
        slot = slot_of_identity.get(identity)
        if slot is None:
            slot = next_slot
            next_slot += 1
        for field, value in fields.items():
            slot_name = store_slot_of(field)
            text = None if value is None else str(value)
            items.append(
                {
                    "item_id": summary_item_id(cycle_number, slot, field),
                    "conclusion": text if slot_name == "conclusion" else None,
                    "remark": text if slot_name == "remark" else None,
                }
            )
    return items

# ═══════════════════════════════════════════════════════════════════════════
# 7. 契约 payload
# ═══════════════════════════════════════════════════════════════════════════

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格实测 C/C2 销售循环控制测试.xlsx 的 `C2控制测试汇总表`（"
    "r1/r2 标题 merged A1:O1 / A2:O2 · r3/r4 页眉 6 个跨 sheet 引用公式 · "
    "r5 是「下拉选择」提示行**非表头非数据** · **r6 表头 15 列 A~O** 逐字为 "
    "子流程/控制编号/控制名称/详细控制描述/受影响的交易、账户余额和披露/认定/"
    "控制属性/控制频率/与控制相关的风险/测试方法/范围（样本量）/是否识别出偏差/"
    "整改期间（如有）/识别出的缺陷/索引号 · **数据区 r7~r21 共 15 行**（模板内全空，"
    "待填底稿）· **r22 = `提示1：与控制相关的风险`** 是静态说明区首行 ⇒ footer 边界 · "
    "🔴 **数据区零公式**（全册 6 个公式全在 r3/r4 页眉）⇒ formula_mask 为空 · "
    "max_column=15(O) 且 last_value_col=15 ⇒ UUID 放 **P** · 无 Excel Table · "
    "ws.protection.sheet=False ⇒ locked 惰性 · 数据区无 merged（merged 全在标题与 r23+ 提示区）)"
    " + 前端 `useCControlTestData.ts` 按值 grep（`SummaryRow` 15 字段与 15 列一一对应；"
    "序列化 `C{n}-sum-{m}-{field}`，枚举类 6 字段 + sampleSize 存 conclusion 槽、其余存 remark 槽)"
    " + 🔴 **行身份改口径**（序列化处 `const m = i + 1` 是数组下标，而引擎 "
    "`FORBIDDEN_ROW_IDENTITY_KINDS` 明令禁 `index`/`ordinal`/`position`/`array_index` ⇒ "
    "声明的行身份取 **B 列控制编号 `controlId`** 业务键，`m` 降级为 provider 内部存储槽不进契约；"
    "merge 时按 controlId 定位目标行回写其当前槽)"
)

_HTML_STORE_NOTE: Final[str] = (
    "🔴 **C 域 store 形态与 D~N 根本不同**：D4/J1 把整表存成一个 item_id 的 remark "
    "JSON 数组，C 是**每个字段一行** checklist_responses（`C{n}-sum-{m}-{field}`，"
    "15 字段/行 ⇒ 15 行/控制点）⇒ build_store_projection 要按 item_id 分组重建行，"
    "不是 json.loads 一个数组。🔴 **槽位 `m` 不是声明的行身份**（见 reviewed_basis 末段）。"
    "🔴 **一 entry 覆盖 28 个 wp_code / 14 本同构主册**（CC-61）：契约只能声明一本册，"
    "本 canary 声明 C2 册为权威样本，C3~C15 已实证六项指标与 C2 逐值一致，按同一 "
    "sheet_payload 扩；14 本 `-2` 偏差册另有 definedName 232/broken 181 污染（外部依赖 36）。"
)


def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.definitions import canonical_digest
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    assert_mapping_digest()
    template_payload = template_definition_payload()
    return {
        "schema_version": "contract-definition:v1",
        "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(template_payload),
        "instrumentation_definition_sha256": canonical_digest(
            instrumentation_definition_payload()
        ),
        "template": {
            "relative_path": TEMPLATE_RELATIVE_PATH,
            "template_sha256": TEMPLATE_SHA256,
            "normalized_structure_hash": template_payload["normalized_structure_hash"],
        },
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "excel_table",
            "hidden_uuid_column",
        ],
        "sheets": [
            {
                "sheet_key": SHEET_KEY,
                "excel_name": MANAGED_SHEET,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": sheet_payload()["tables"],
            }
        ],
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "reviewed_basis": _REVIEWED_BASIS,
            "mapping_digest": mapping_digest(),
            "canary_scope": {
                "declared_workbook": TEMPLATE_RELATIVE_PATH,
                "wp_code_count": len(WP_CODES),
                "wp_codes_main": list(WP_CODES_MAIN),
                "wp_codes_deviation": list(WP_CODES_DEVIATION),
                "homogeneous_main_books": 14,
                "note": (
                    "🔴 CC-61：一 componentType 覆盖 28 个 wp_code。本契约声明 C2 册为 "
                    "canary 权威样本；C3~C15 的 13 本主册已实证与 C2 六项指标逐值一致"
                    "（公式格 12 / 裸 IF 0 / definedName 0-0 / 超列 0 / max_col 18 / 表头逐字同）。"
                ),
            },
            "html_store": {
                "table": "checklist_responses",
                "shape": "per_field_scalar_rows",
                "item_id_pattern": "C{n}-sum-{m}-{field}",
                "row_identity_key": ROW_IDENTITY_FIELD,
                "storage_slot_key": "m（1-based，provider 内部，不进契约）",
                "note": _HTML_STORE_NOTE,
                "conclusion_slot_fields": sorted(
                    _CONCLUSION_SLOT_FIELDS | _NUMERIC_SLOT_FIELDS
                ),
            },
            "data_area_zero_formula": True,
            "formula_mask_empty_reason": (
                "数据区 r7~r21 零公式（全册 6 个公式全在 r3/r4 页眉跨 sheet 引用）"
            ),
            "sheet_protection_enabled": False,
            "merged_in_data_area": 0,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 8. definition payload（template / instrumentation）
# ═══════════════════════════════════════════════════════════════════════════

def _template_abs_path():
    """权威模板绝对路径（`backend/wp_templates/` 下）。"""
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[3]
    return backend_root / "wp_templates" / TEMPLATE_RELATIVE_PATH


def read_authoritative_template() -> bytes:
    """读取权威模板文件字节。"""
    path = _template_abs_path()
    if not path.exists():
        raise EntrySelectionError(f"权威模板不存在: {TEMPLATE_RELATIVE_PATH}")
    return path.read_bytes()


def template_definition_payload() -> dict[str, Any]:
    """权威模板的结构声明（含 normalized_structure_hash）。"""
    from app.services.workpaper_sync.definitions import canonical_digest

    structure = {
        "managed_sheet": MANAGED_SHEET,
        "header_row": HEADER_ROW,
        "first_data_row": FIRST_DATA_ROW,
        "last_data_row": LAST_DATA_ROW,
        "footer_row": FOOTER_ROW,
        "managed_last_col": MANAGED_LAST_COL,
        "uuid_col": UUID_COL,
        "columns": [
            {"column": spec[1], "header_text": spec[4], "column_key": _snake(spec[0])}
            for spec in MANAGED_FIELD_SPECS
        ],
    }
    return {
        "schema_version": "template-definition:v1",
        "relative_path": TEMPLATE_RELATIVE_PATH,
        "template_sha256": TEMPLATE_SHA256,
        "structure": structure,
        "normalized_structure_hash": canonical_digest(structure),
    }


def instrumentation_definition_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.definitions import canonical_digest
    spec = instrumentation_spec()
    return {
        "schema_version": "instrumentation-definition:v1",
        "entry_id": ENTRY_ID,
        "template_id": TEMPLATE_ID,
        "template_definition_sha256": canonical_digest(template_definition_payload()),
        "template_sha256": TEMPLATE_SHA256,
        "sheet_key": spec.resolved_sheet_key,
        "managed_sheet": MANAGED_SHEET,
        "first_data_row": FIRST_DATA_ROW,
        "last_data_row": LAST_DATA_ROW,
        "footer_row": FOOTER_ROW,
        "managed_last_col": MANAGED_LAST_COL,
        "uuid_col": UUID_COL,
        "table_name": f"GT_{TEMPLATE_ID}_ROWS",
        "mapping_digest": mapping_digest(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 9. 选型前置与 manifest 校验
# ═══════════════════════════════════════════════════════════════════════════


def assert_entry_selectable() -> None:
    """模板存在 + sha256 未漂移 + 几何自证通过。"""
    assert_mapping_digest()
    path = _template_abs_path()
    if not path.exists():
        raise EntrySelectionError(f"权威模板不存在: {TEMPLATE_RELATIVE_PATH}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板 sha256 漂移: 声明 {TEMPLATE_SHA256} / 实测 {actual} —— "
            "模板变更须重新逐格复核几何后更新常量"
        )


def assert_manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> None:
    from app.services.workpaper_sync.entry_profile import (
        Capability,
        capability_of,
        load_entry_manifest,
        manifest_entries_by_id,
    )

    entries = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    )
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(f"entry {ENTRY_ID} 不在 source-backed manifest 中")
    capability = capability_of(entry)
    if capability is not Capability.bidirectional:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest capability={capability.value} —— "
            "注册 bidirectional adapter 前必须先由 reviewed overlay 裁决为 bidirectional 并重生成 manifest"
        )


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except Exception:
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# 10. 契约加载与注册
# ═══════════════════════════════════════════════════════════════════════════


def contract_path():
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[3]
    return backend_root / "data" / "workpaper_sync_contracts" / f"{ADAPTER_ID}.json"


def load_contract_from_disk():
    """读磁盘契约并强校验成 SyncContract。"""
    from app.services.workpaper_sync.contracts import parse_contract

    path = contract_path()
    if not path.exists():
        raise EntrySelectionError(f"契约文件不存在: {path.name}")
    payload = json.loads(path.read_bytes().decode("utf-8"))
    return parse_contract(payload, adapter_id=ADAPTER_ID)


def assert_contract_file_matches_source():
    """磁盘契约与本模块现算 payload 逐字节一致（双重漂移门）。"""
    from app.services.workpaper_sync.definitions import canonical_digest

    contract = load_contract_from_disk()
    disk_digest = canonical_digest(contract.canonical_payload)
    source_digest = canonical_digest(build_contract_payload())
    if disk_digest != source_digest:
        raise EntrySelectionError(
            f"契约漂移：磁盘 {disk_digest[:16]}… != 本模块现算 {source_digest[:16]}… —— "
            "改了 provider 常量后须重新生成契约文件（scripts/gen/gen_c_control_test_contract.py）"
        )
    return contract


def build_matcher():
    from app.services.workpaper_sync.adapters.registry import EntryMatcher

    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def build_registration(*, adapter, bundle, descriptor, room, contract=None):
    from app.services.workpaper_sync.adapters.registry import AdapterRegistration
    from app.services.workpaper_sync.entry_profile import Capability

    return AdapterRegistration(
        adapter=adapter,
        entry_id=ENTRY_ID,
        matcher=build_matcher(),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=contract if contract is not None else load_contract_from_disk(),
    )


async def attach_adapters(registry, *, session) -> tuple[str, ...]:
    """逐 entry attach（白名单入口 `attach_pilot_adapters` 的实现）。

    早退顺序与 D4 / E1 一致：已注册 → capability 未裁决 → 无 published representation
    → 无 definition bundle。每个早退都 `return ()`，由 registry 侧换算成显式原因。
    """
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.entry_profile import (
        load_entry_manifest,
        manifest_entries_by_id,
    )
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    assert_entry_selectable()

    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=ENTRY_ID
    )
    if representation_id is None:
        return ()
    representation = (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == representation_id
            )
        )
    ).scalar_one_or_none()
    if representation is None or representation.definition_bundle_id is None:
        return ()

    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[3]
    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(backend_root)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）"
        )
    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=resolution,
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest 与 source-locked 不一致"
        )
    registration = build_registration(
        adapter=build_excel_adapter(
            definitions=observation.definitions,
            binding=observation.identity_binding,
            direction="html_to_oo",
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    registry.register(registration)
    return (ADAPTER_ID,)


# ═══════════════════════════════════════════════════════════════════════════
# 11. 白名单接口别名
# ═══════════════════════════════════════════════════════════════════════════


AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract


def authority_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "entry_id": ENTRY_ID,
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "pilot_class": "phase5",
        "reason": (
            f"{ENTRY_ID}：结构化 Tab（HTML store）与 OnlyOffice 共写同一份权威模板，"
            "投影契约是唯一权威 —— 与 D1~D7 / E1 / F3~F5 同型"
        ),
    }


@dataclass(frozen=True)
class Phase5Definitions:
    """发布结果（与 F3/F4/F5/H 系各家同形）。"""
    authority_model_definition_id: Any
    authority_model_definition_sha256: str
    template_definition_id: Any
    template_definition_sha256: str
    instrumentation_definition_id: Any
    instrumentation_definition_sha256: str
    contract_definition_id: Any
    contract_definition_sha256: str
    bundle_id: Any
    bundle_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": ENTRY_ID,
            "adapter_id": ADAPTER_ID,
            "authority_model": AUTHORITY_MODEL.value,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "contract_definition_id": str(self.contract_definition_id),
            "contract_definition_sha256": self.contract_definition_sha256,
            "definition_bundle_id": str(self.bundle_id),
            "definition_bundle_sha256": self.bundle_sha256,
        }


async def publish_definitions(publisher: Any) -> Phase5Definitions:
    """发布五个 definition + bundle（照 F3/D3 范式）。"""
    contract = assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    template_payload = template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f"{ADAPTER_ID}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(),
        structure_hash=template_payload["normalized_structure_hash"],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(),
        logical_id=f"{ADAPTER_ID}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=ADAPTER_ID,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        from app.services.workpaper_sync.adapters.registry import RegistrationError
        raise RegistrationError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        from app.services.workpaper_sync.adapters.registry import RegistrationError
        raise RegistrationError(
            f"已发布 instrumentation digest {instrumentation.sha256} 与契约声明 "
            f"{contract.instrumentation_definition_sha256} 不一致 —— 单向引用断裂"
        )
    bundle = await publisher.publish_bundle(
        authority_model_definition_id=authority.definition_id,
        authority_model=AUTHORITY_MODEL,
        authority_model_definition_sha256=authority.sha256,
        slots={
            BundleSlot.template: {
                "type": "definition",
                "ref": f"definition:{template.definition_id}",
                "digest": template.sha256,
            },
            BundleSlot.instrumentation: {
                "type": "definition",
                "ref": f"definition:{instrumentation.definition_id}",
                "digest": instrumentation.sha256,
            },
            BundleSlot.contract: {
                "type": "definition",
                "ref": f"definition:{contract_definition.definition_id}",
                "digest": contract_definition.sha256,
            },
        },
    )
    return Phase5Definitions(
        authority_model_definition_id=authority.definition_id,
        authority_model_definition_sha256=authority.sha256,
        template_definition_id=template.definition_id,
        template_definition_sha256=template.sha256,
        instrumentation_definition_id=instrumentation.definition_id,
        instrumentation_definition_sha256=instrumentation.sha256,
        contract_definition_id=contract_definition.definition_id,
        contract_definition_sha256=contract_definition.sha256,
        bundle_id=bundle.bundle_id,
        bundle_sha256=bundle.canonical_sha256,
    )


publish_pilot_definitions = publish_definitions

attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
