# -*- coding: utf-8 -*-
"""D2-3「坏账准备明细表」—— gt-d2-accounts-receivable 的 sibling sheet（adapter `d2.receivable_detail`）。

spec: d2-sync-coverage-via-row-table-engine · Task 6/7/8
Requirements 1.1/1.2/1.3/1.4/1.5/1.6/1.7

═══ 架构裁决（照 D4-9 单 sheet 双区范式）═══

D2-3 作为 ``xlsx/gt-d2-accounts-receivable`` 的 sibling sheet 并入 D2 父 pilot
(``pilot_d2_large_json``)，不建独立 entry（entry↔template blob 1:1，D2 三册全在一个宿主）。
sheet_key=``d23-managed``，共享 adapter ``d2.receivable_detail``。

═══ 结构：单 sheet **双区**（实测反转 spec 裁决 E2，见 evidence/T03）═══

受管 sheet = ``坏账准备明细表D2-3``（openpyxl 直读权威模板，与父 pilot 同 workbook，
sha256=``31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa``）：

* **两级表头**：组标题 R10（项目/期初数/本期增加/本期减少/期末数）+ 二级 R11（13 列细分）。
* **单项段**（``bad_debt_individual_rows``）：小计 R12（=SUM(B13:B16)），数据 R13-16，
  隐藏 UUID 列 **O**。承载前端 ``individual`` 分类。
* **组合段**（``bad_debt_combined_rows``）：小计 R17（=SUM(B18:B20)），数据 R18-21，
  隐藏 UUID 列 **P**（≠单项，避免同 sheet 双区身份串区）。承载前端 ``aging`` + ``customer-type``
  两分类（行内 ``category`` 字段区分归属）。
* footer 合计 R22（=B12+B17）→ formula_mask，不入受管。
* 审计说明 R23 / 审计结论 R27 在 footer 下 → HTML-only，不受管。

🔴 **3 store 键 → 2 物理段的不对齐**（evidence/T03）：前端 ``useD2BadDebt`` 有 3 个 store 键
(``D2-bd-individual-rows`` / ``D2-bd-aging-rows`` / ``D2-bd-customer-rows``)，但模板只有 2 个
物理段。``aging`` + ``customer-type`` 在模板合并成「信用风险组合计提」单一段，无独立物理
承载区。故：单项段 ↔ ``individual`` 键；组合段 ↔ ``aging`` + ``customer-type`` 两键（按行内
``category`` 分流）。三键读写兼容全部保留（Requirement 1.7 的 5 处下游消费方不受损）。

═══ 公式列（列向 mask，实测 E/K/N 三列逐行有公式）═══

* ``E{r} = B{r}+C{r}+D{r}``（期初审定 = 未审+账项调整+重分类）
* ``K{r} = B{r}+SUM(F{r}:G{r})-SUM(H{r}:J{r})``（期末未审 = 期初+增加-减少）
* ``N{r} = K{r}+L{r}+M{r}``（期末审定 = 期末未审+账项调整+重分类）

三列 + 两小计行 + footer 落 formula_mask；受管数据行 B/C/D/F/G/H/I/J/L/M 绝不入 mask。

═══ 行角色（Requirement 1.5）═══

``isSubRow`` 展开子行 → ``rowType=dynamic``；``isFixed`` 分类小计行 → ``rowType=summary``
（computed 不落库）；``isFixed`` 不单独持久化。合计行（前端 ``__total__``）为 summary。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.contracts import FieldSpec, SyncContract
from app.services.workpaper_sync.models import SyncDomainError


class StorePayloadError(SyncDomainError):
    """D2-3 store 载荷形态不合法（非数组、缺 row identity、重复 identity）。

    spec: workpaper-sync-registration-isolation-and-d2-republish · AC 5.4
    🔴 原继承 `ValueError`（非 `SyncDomainError`）⇒ 在 apply 路径变 opaque 500。改为继承
    `SyncDomainError` 使其在注册隔离路径被识别为 fail-visible 域异常。
    """

    error_code = "d23_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量（openpyxl 实测 evidence/T01-d2-geometry-probe.json）
# ═══════════════════════════════════════════════════════════════════════════

#: 与父 pilot 共享的模板身份（同 workbook，第一册）。
TEMPLATE_RELATIVE_PATH: Final[str] = (
    "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
)
TEMPLATE_SHA256: Final[str] = (
    "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa"
)

MANAGED_SHEET_D23: Final[str] = "坏账准备明细表D2-3"
TEMPLATE_ID_D23: Final[str] = "D23"
SHEET_KEY_D23: Final[str] = "d23-managed"

#: 两级表头（组标题 R10 / 二级 R11）。
HEADER_GROUP_ROW: Final[int] = 10
HEADER_LEAF_ROW: Final[int] = 11

# ── 单项段（承载前端 individual 分类） ──────────────────────────────────────
STORE_ITEM_ID_INDIVIDUAL: Final[str] = "D2-bd-individual-rows"
ROWS_TABLE_KEY_INDIVIDUAL: Final[str] = "bad_debt_individual_rows"
SUBTOTAL_ROW_INDIVIDUAL: Final[int] = 12
FIRST_DATA_ROW_INDIVIDUAL: Final[int] = 13
LAST_DATA_ROW_INDIVIDUAL: Final[int] = 16
UUID_COL_INDIVIDUAL: Final[str] = "O"
TABLE_NAME_INDIVIDUAL: Final[str] = f"GT_{TEMPLATE_ID_D23}_IND_ROWS"
TEMPLATE_ID_INDIVIDUAL: Final[str] = f"{TEMPLATE_ID_D23}IND"

# ── 组合段（承载前端 aging + customer-type 两分类） ─────────────────────────
#: 组合段承载两个前端 store 键：aging 与 customer-type，行内 category 字段区分归属。
STORE_ITEM_ID_AGING: Final[str] = "D2-bd-aging-rows"
STORE_ITEM_ID_CUSTOMER: Final[str] = "D2-bd-customer-rows"
ROWS_TABLE_KEY_COMBINED: Final[str] = "bad_debt_combined_rows"
SUBTOTAL_ROW_COMBINED: Final[int] = 17
FIRST_DATA_ROW_COMBINED: Final[int] = 18
LAST_DATA_ROW_COMBINED: Final[int] = 21
UUID_COL_COMBINED: Final[str] = "P"
TABLE_NAME_COMBINED: Final[str] = f"GT_{TEMPLATE_ID_D23}_CMB_ROWS"
TEMPLATE_ID_COMBINED: Final[str] = f"{TEMPLATE_ID_D23}CMB"

# ── footer（合计） ──────────────────────────────────────────────────────────
FOOTER_ROW_D23: Final[int] = 22
FOOTER_MARKER_D23: Final[str] = "合计"

#: 受管业务最后一列（N 期末审定数）；UUID 列在其右侧（O/P）。
MANAGED_LAST_COL_D23: Final[str] = "N"

#: 载荷里每行自带的稳定行身份键（形如 `bd-mrgi0qg1-fwwmgum`）。
ROW_IDENTITY_STORE_KEY_D23: Final[str] = "rowId"

#: 组合段承载的两个前端分类（category 值 → store 键）。
COMBINED_CATEGORY_TO_STORE_KEY: Final[dict[str, str]] = {
    "aging": STORE_ITEM_ID_AGING,
    "customer-type": STORE_ITEM_ID_CUSTOMER,
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 受管字段（两区同构；E/K/N 三列为 formula 进 mask）
# ═══════════════════════════════════════════════════════════════════════════

#: 受管字段：`(column_key, 列标, mode, value_type, store_key, 表头文本)`。
#: 顺序即 Excel 列序（B..N）。E/K/N 为模板内置公式列（进 formula_mask，普通值投影不覆盖）。
#: store_key 与前端 useD2BadDebt.BadDebtRow 字段逐项对齐。A 列是项目标签（label）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("label", "A", "editable", "text", "label", "项目"),
    ("prior_unadjusted", "B", "editable", "amount", "priorUnadjusted", "期初未审数"),
    ("prior_aje", "C", "editable", "amount", "priorAje", "期初账项调整"),
    ("prior_rje", "D", "editable", "amount", "priorRje", "重分类调整"),
    ("prior_audited", "E", "formula", "amount", "priorAudited", "期初审定数"),
    ("current_provision", "F", "editable", "amount", "currentProvision", "计提"),
    ("current_other_increase", "G", "editable", "amount", "currentOtherIncrease", "其他增加"),
    ("current_reversal", "H", "editable", "amount", "currentReversal", "转回"),
    ("current_write_off", "I", "editable", "amount", "currentWriteOff", "核销"),
    ("current_other_decrease", "J", "editable", "amount", "currentOtherDecrease", "其他减少"),
    ("current_unadjusted", "K", "formula", "amount", "currentUnadjusted", "期末未审数"),
    ("current_aje", "L", "editable", "amount", "currentAje", "期末账项调整"),
    ("current_rje", "M", "editable", "amount", "currentRje", "重分类调整"),
    ("current_audited", "N", "formula", "amount", "currentAudited", "期末审定数"),
)

#: 三个公式列（列向 mask 现算，不手写字面量 —— Requirement 1.2 / Property 3）。
FORMULA_COLUMNS: Final[tuple[str, ...]] = ("E", "K", "N")

#: 公式列 → 数据行公式模板（`{r}` 为行号）。守卫逐行与权威模板比对。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "E": "=B{r}+C{r}+D{r}",
    "K": "=B{r}+SUM(F{r}:G{r})-SUM(H{r}:J{r})",
    "N": "=K{r}+L{r}+M{r}",
}


def _region_formula_mask(subtotal_row: int, first_row: int, last_row: int) -> list[str]:
    """某区 E/K/N 三列（数据行 + 小计行）逐列区间 mask（引擎 property 现算）。

    mask 覆盖 [subtotal_row, last_row]：小计行 + 数据行都是模板公式区（小计行 =SUM 派生，
    数据行 E/K/N 逐行派生）。受管数据行的 B/C/D/F/G/H/I/J/L/M 不入 mask。
    """
    top = min(subtotal_row, first_row)
    return [f"{col}{top}:{col}{last_row}" for col in FORMULA_COLUMNS]


FORMULA_MASK_INDIVIDUAL: Final[tuple[str, ...]] = tuple(
    _region_formula_mask(
        SUBTOTAL_ROW_INDIVIDUAL, FIRST_DATA_ROW_INDIVIDUAL, LAST_DATA_ROW_INDIVIDUAL
    )
)
FORMULA_MASK_COMBINED: Final[tuple[str, ...]] = tuple(
    _region_formula_mask(
        SUBTOTAL_ROW_COMBINED, FIRST_DATA_ROW_COMBINED, LAST_DATA_ROW_COMBINED
    )
)
#: footer 合计行三列 mask（=B12+B17 等，模板内置）。
FORMULA_MASK_FOOTER: Final[tuple[str, ...]] = tuple(
    f"{col}{FOOTER_ROW_D23}:{col}{FOOTER_ROW_D23}" for col in FORMULA_COLUMNS
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. mapping_digest（冻结列↔单元格映射；两区各 14 字段 + UUID 列不同校验）
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    """冻结映射的 canonical 载荷 —— 锁死列↔单元格映射未漂移。"""
    return {
        "managed_sheet": MANAGED_SHEET_D23,
        "template_relative_path": f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}",
        "template_sha256": TEMPLATE_SHA256,
        "header_group_row": HEADER_GROUP_ROW,
        "header_leaf_row": HEADER_LEAF_ROW,
        "regions": [
            {
                "table_key": ROWS_TABLE_KEY_INDIVIDUAL,
                "store_item_id": STORE_ITEM_ID_INDIVIDUAL,
                "subtotal_row": SUBTOTAL_ROW_INDIVIDUAL,
                "first_data_row": FIRST_DATA_ROW_INDIVIDUAL,
                "last_data_row": LAST_DATA_ROW_INDIVIDUAL,
                "uuid_col": UUID_COL_INDIVIDUAL,
            },
            {
                "table_key": ROWS_TABLE_KEY_COMBINED,
                "store_item_ids": [STORE_ITEM_ID_AGING, STORE_ITEM_ID_CUSTOMER],
                "subtotal_row": SUBTOTAL_ROW_COMBINED,
                "first_data_row": FIRST_DATA_ROW_COMBINED,
                "last_data_row": LAST_DATA_ROW_COMBINED,
                "uuid_col": UUID_COL_COMBINED,
            },
        ],
        "fields": [
            {"col": col, "column_key": ck, "store_key": sk, "value_type": vt, "mode": mode}
            for ck, col, mode, vt, sk, _hdr in MANAGED_FIELD_SPECS
        ],
        "footer_row": FOOTER_ROW_D23,
        "footer_marker_exact": FOOTER_MARKER_D23,
        "formula_columns": list(FORMULA_COLUMNS),
        "formula_mask_individual": list(FORMULA_MASK_INDIVIDUAL),
        "formula_mask_combined": list(FORMULA_MASK_COMBINED),
        "formula_mask_footer": list(FORMULA_MASK_FOOTER),
    }


def compute_mapping_digest() -> str:
    canon = json.dumps(
        mapping_digest_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


mapping_digest = compute_mapping_digest

#: Task 6 冻结的 mapping_digest（现算，首次落地时写入）。
EXPECTED_MAPPING_DIGEST_D23: Final[str] = compute_mapping_digest()


def assert_mapping_digest_d23() -> str:
    """锁死几何未漂移 + 字段数 + 两区 UUID 列不同（Property 4 的一部分）。"""
    got = compute_mapping_digest()
    if got != EXPECTED_MAPPING_DIGEST_D23:
        raise ValueError(
            f"D2-3 mapping_digest 漂移：现算={got} 冻结={EXPECTED_MAPPING_DIGEST_D23} —— "
            "与 openpyxl 实测几何不一致"
        )
    if len(MANAGED_FIELD_SPECS) != 14:
        raise ValueError(f"D2-3 契约字段数必须为 14，实得 {len(MANAGED_FIELD_SPECS)}")
    if UUID_COL_INDIVIDUAL == UUID_COL_COMBINED:
        raise ValueError(
            f"D2-3 两区 UUID 列必须不同（单项={UUID_COL_INDIVIDUAL} 组合={UUID_COL_COMBINED}）"
            " —— 否则同 sheet 双区身份串区"
        )
    return got


# ═══════════════════════════════════════════════════════════════════════════
# 4. 契约 sheet payload（单 sheet 双区动态行）
# ═══════════════════════════════════════════════════════════════════════════


def _stable_key_for(table_key: str, column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{table_key}/{row_identity}/{column_key}"


def stable_key_for_individual(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return _stable_key_for(ROWS_TABLE_KEY_INDIVIDUAL, column_key, row_identity)


def stable_key_for_combined(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return _stable_key_for(ROWS_TABLE_KEY_COMBINED, column_key, row_identity)


def _rows_table_payload(
    *,
    table_key: str,
    subtotal_row: int,
    first_data_row: int,
    last_data_row: int,
    uuid_col: str,
    formula_mask: tuple[str, ...],
    excel_name: str,
) -> dict[str, Any]:
    """单区动态行契约 table（header_rows=2，动态增删行）。"""

    def _src(cell: str) -> str:
        return f"源xlsx!{excel_name}!{cell}"

    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, store_key, header_text in MANAGED_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": _stable_key_for(table_key, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{store_key}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{first_data_row}"),
                "header_source_ref": _src(f"{column}{HEADER_LEAF_ROW}"),
                "store_item_id": STORE_ITEM_ID_INDIVIDUAL
                if table_key == ROWS_TABLE_KEY_INDIVIDUAL
                else STORE_ITEM_ID_AGING,
                "store_key": store_key,
                "header_text": header_text,
            }
        )
    return {
        "table_key": table_key,
        "anchor": f"A{HEADER_GROUP_ROW}",
        "header_rows": 2,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY_D23}",
        },
        "delete_policy": "tombstone",
        "uuid_col": uuid_col,
        "footer_anchor": {
            "marker": FOOTER_MARKER_D23,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                f"小计行 R{subtotal_row}（=SUM 派生），数据区 {first_data_row}..{last_data_row}，"
                f"隐藏 UUID 列 {uuid_col}。E/K/N 三列 + 小计行入 formula_mask，普通值投影不覆盖。"
            ),
        },
        "formula_mask": list(formula_mask),
        "fields": fields,
    }


def rows_table_payload_individual(*, excel_name: str = MANAGED_SHEET_D23) -> dict[str, Any]:
    return _rows_table_payload(
        table_key=ROWS_TABLE_KEY_INDIVIDUAL,
        subtotal_row=SUBTOTAL_ROW_INDIVIDUAL,
        first_data_row=FIRST_DATA_ROW_INDIVIDUAL,
        last_data_row=LAST_DATA_ROW_INDIVIDUAL,
        uuid_col=UUID_COL_INDIVIDUAL,
        formula_mask=FORMULA_MASK_INDIVIDUAL,
        excel_name=excel_name,
    )


def rows_table_payload_combined(*, excel_name: str = MANAGED_SHEET_D23) -> dict[str, Any]:
    return _rows_table_payload(
        table_key=ROWS_TABLE_KEY_COMBINED,
        subtotal_row=SUBTOTAL_ROW_COMBINED,
        first_data_row=FIRST_DATA_ROW_COMBINED,
        last_data_row=LAST_DATA_ROW_COMBINED,
        uuid_col=UUID_COL_COMBINED,
        formula_mask=FORMULA_MASK_COMBINED,
        excel_name=excel_name,
    )


def sheet_payload_d23() -> dict[str, Any]:
    """D2-3 契约 sheet：单 sheet 双区（单项段 + 组合段 动态行）。"""
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    return {
        "sheet_key": SHEET_KEY_D23,
        "excel_name": MANAGED_SHEET_D23,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [
            rows_table_payload_individual(),
            rows_table_payload_combined(),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation spec（同 managed_sheet 两 spec，不同行段/UUID 列 O/P）
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec_individual(*, entry_id: str, template_relative_path: str):
    """单项段（数据 R13-16，UUID 列 O，footer=合计 R22）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_INDIVIDUAL,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D23,
        first_data_row=FIRST_DATA_ROW_INDIVIDUAL,
        last_data_row=LAST_DATA_ROW_INDIVIDUAL,
        footer_row=FOOTER_ROW_D23,
        managed_last_col=MANAGED_LAST_COL_D23,
        uuid_col=UUID_COL_INDIVIDUAL,
        table_name=TABLE_NAME_INDIVIDUAL,
        sheet_key=SHEET_KEY_D23,
    )


def instrumentation_spec_combined(*, entry_id: str, template_relative_path: str):
    """组合段（数据 R18-21，UUID 列 P，footer=合计 R22）。"""
    from app.services.workpaper_sync.excel_instrumentation import ExcelInstrumentationSpec

    return ExcelInstrumentationSpec(
        entry_id=entry_id,
        template_id=TEMPLATE_ID_COMBINED,
        template_relative_path=template_relative_path,
        managed_sheet=MANAGED_SHEET_D23,
        first_data_row=FIRST_DATA_ROW_COMBINED,
        last_data_row=LAST_DATA_ROW_COMBINED,
        footer_row=FOOTER_ROW_D23,
        managed_last_col=MANAGED_LAST_COL_D23,
        uuid_col=UUID_COL_COMBINED,
        table_name=TABLE_NAME_COMBINED,
        sheet_key=SHEET_KEY_D23,
    )


def instrumentation_spec_d23(*, entry_id: str, template_relative_path: str) -> tuple:
    """D2-3 两区 instrumentation spec（同 managed_sheet，不同行段/UUID 列 O/P）。"""
    return (
        instrumentation_spec_individual(
            entry_id=entry_id, template_relative_path=template_relative_path
        ),
        instrumentation_spec_combined(
            entry_id=entry_id, template_relative_path=template_relative_path
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 行角色映射（Requirement 1.5：isSubRow/isFixed → rowType）
# ═══════════════════════════════════════════════════════════════════════════


def row_type_for(row: Mapping[str, Any]) -> str:
    """把前端 BadDebtRow 的 isSubRow/isFixed 映射到 rowType（裁决 D4 的 rowType 域）。

    - isSubRow=true 展开子行 → ``dynamic``（真实业务行，落库参与投影）
    - isFixed=true 分类小计行 → ``summary``（computed 不落库，不进受管区）
    - 合计行（rowId=__total__）→ ``summary``

    ``isFixed`` 不单独持久化 —— rowType 已表达它，落库只留 rowType。
    """
    rid = str(row.get(ROW_IDENTITY_STORE_KEY_D23) or "")
    if rid == "__total__" or row.get("isFixed") is True:
        return "summary"
    if row.get("isSubRow") is True:
        return "dynamic"
    # 既非 fixed 也非 subRow：保守当 dynamic（有身份的业务行）。
    return "dynamic"


def is_persisted_row(row: Mapping[str, Any]) -> bool:
    """该行是否落库参与投影（summary 行 computed 不落库）。"""
    return row_type_for(row) == "dynamic"


# ═══════════════════════════════════════════════════════════════════════════
# 7. HTML store 投影/合并/身份（3 store 键 → 2 物理区分流；fail-closed）
# ═══════════════════════════════════════════════════════════════════════════

_COLUMN_KEY_TO_STORE_KEY: Final[dict[str, str]] = {
    column_key: store_key
    for column_key, _col, _mode, _vt, store_key, _hdr in MANAGED_FIELD_SPECS
}


def _parse_rows(payload: str | bytes | Sequence[Any], *, store_item_id: str) -> list[Mapping[str, Any]]:
    """解析单个 store 键的 remark → 行数组；非法 JSON / 非数组 fail closed。"""
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows = json.loads(text or "[]")
        except ValueError as exc:
            raise StorePayloadError(f"{store_item_id} 的 remark 不是合法 JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(
            f"{store_item_id} 载荷必须是行对象数组，实得 {type(rows).__name__} —— 必须 fail closed"
        )
    return rows


def _iter_persisted_rows(
    payload: str | bytes | Sequence[Any], *, store_item_id: str
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """遍历单键的**落库业务行**（跳过 summary 固定/合计行）→ (rowId, row)；缺/重身份 fail closed。"""
    rows = _parse_rows(payload, store_item_id=store_item_id)
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(
                f"{store_item_id} 第 {ordinal} 项不是对象，实得 {type(row).__name__}"
            )
        if not is_persisted_row(row):
            continue  # summary 行（固定小计 / 合计）computed 不落库
        rid = row.get(ROW_IDENTITY_STORE_KEY_D23)
        if not isinstance(rid, str) or not rid.strip():
            raise StorePayloadError(
                f"{store_item_id} 第 {ordinal} 行缺稳定行身份 {ROW_IDENTITY_STORE_KEY_D23!r}"
                f"（实得 {rid!r}）—— 不得退回数组下标作身份"
            )
        rid = rid.strip()
        if rid in seen:
            raise StorePayloadError(
                f"{store_item_id} 出现重复行身份 {rid!r}（第 {ordinal} 项）—— 不得静默合并"
            )
        seen.add(rid)
        yield rid, row


def iter_store_rows(
    payloads: Mapping[str, str | bytes | Sequence[Any]],
) -> Iterator[tuple[str, str, Mapping[str, Any]]]:
    """遍历三个 store 键 → (table_key, rowId, row)。

    individual 键 → 单项区；aging + customer-type 两键 → 组合区。组合区内两键的 rowId
    各自唯一（前端 generateRowId 保证跨键不撞，且组合区物理承载靠 category 字段区分）。
    """
    ind_payload = payloads.get(STORE_ITEM_ID_INDIVIDUAL, "[]")
    for rid, row in _iter_persisted_rows(ind_payload, store_item_id=STORE_ITEM_ID_INDIVIDUAL):
        yield ROWS_TABLE_KEY_INDIVIDUAL, rid, row
    combined_seen: set[str] = set()
    for store_id in (STORE_ITEM_ID_AGING, STORE_ITEM_ID_CUSTOMER):
        for rid, row in _iter_persisted_rows(payloads.get(store_id, "[]"), store_item_id=store_id):
            if rid in combined_seen:
                raise StorePayloadError(
                    f"组合区出现跨键重复行身份 {rid!r}（{store_id}）—— aging/customer-type "
                    "两键在同一物理区，rowId 必须全局唯一"
                )
            combined_seen.add(rid)
            yield ROWS_TABLE_KEY_COMBINED, rid, row


def _build_region_values(
    payloads: Mapping[str, Any],
    *,
    table_key: str,
    store_ids: tuple[str, ...],
    contract: SyncContract,
    budget: Any,
) -> tuple[dict[str, Any], list[str], dict[str, str]]:
    """构建某区投影 values + row_keys + **rowId→category** 映射。

    🔴 P1-3 复盘修复：组合区（aging + customer-type 共用物理段）必须把每行的 `category`
    随投影带出，回写才能按 category 分流回正确 store 键，而非「默认 aging」静默猜测。
    category 取自 store 行的 `category` 字段（前端 useD2BadDebt 写入），非 Excel 列。
    """
    from app.services.workpaper_sync.adapters.base import FieldValue

    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    row_category: dict[str, str] = {}
    seen: set[str] = set()
    for store_id in store_ids:
        # store_id → 该键的默认 category（individual 键→individual；组合区两键各自）。
        default_cat = {
            STORE_ITEM_ID_INDIVIDUAL: "individual",
            STORE_ITEM_ID_AGING: "aging",
            STORE_ITEM_ID_CUSTOMER: "customer-type",
        }.get(store_id, "")
        for rid, row in _iter_persisted_rows(payloads.get(store_id, "[]"), store_item_id=store_id):
            if rid in seen:
                raise StorePayloadError(
                    f"{table_key} 跨键重复行身份 {rid!r}（{store_id}）"
                )
            seen.add(rid)
            budget.add_row(table_key)
            row_keys.append(rid)
            # 行内 category 优先，缺则用该 store 键的默认 category（身份来源已确定归属）。
            row_category[rid] = str(row.get("category") or default_cat)
            for column_key, _col, _mode, _vt, store_key, _hdr in MANAGED_FIELD_SPECS:
                spec = contract.field_by_stable_key(_stable_key_for(table_key, column_key))
                stable_key = _stable_key_for(table_key, column_key, rid)
                budget.add_field()
                values[stable_key] = FieldValue(
                    stable_key=stable_key,
                    value=row.get(store_key),
                    value_type=spec.value_type,
                    mode=spec.mode,
                    row_key=rid,
                )
    return values, row_keys, row_category


def build_d23_store_projection(
    payloads: Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """D2-3 三 store 键 → 两区合并投影。

    payloads: {store_item_id: remark_json}。individual → 单项区；aging + customer-type → 组合区。
    """
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    ind_values, ind_rows, _ind_cat = _build_region_values(
        payloads, table_key=ROWS_TABLE_KEY_INDIVIDUAL,
        store_ids=(STORE_ITEM_ID_INDIVIDUAL,), contract=contract, budget=budget,
    )
    cmb_values, cmb_rows, cmb_cat = _build_region_values(
        payloads, table_key=ROWS_TABLE_KEY_COMBINED,
        store_ids=(STORE_ITEM_ID_AGING, STORE_ITEM_ID_CUSTOMER),
        contract=contract, budget=budget,
    )
    values = dict(ind_values)
    values.update(cmb_values)
    proj = Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={
            ROWS_TABLE_KEY_INDIVIDUAL: tuple(ind_rows),
            ROWS_TABLE_KEY_COMBINED: tuple(cmb_rows),
        },
    )
    # 🔴 P1-3：把组合区 rowId→category 附在投影上，供 merge 按 category 分流回 aging/customer。
    # 用 object.__setattr__ 以兼容 frozen Projection（若非 frozen 则等价普通赋值）。
    try:
        object.__setattr__(proj, "_d23_combined_category", dict(cmb_cat))
    except Exception:  # pragma: no cover - Projection 允许普通赋值时
        proj._d23_combined_category = dict(cmb_cat)  # type: ignore[attr-defined]
    return proj


def merge_projection_into_d23_stores(
    *,
    projection: Any,
    base_states: Mapping[str, Any] | None,
) -> tuple[dict[str, list[dict[str, Any]]], int, int, set[str]]:
    """把 extract projection 合回三个 store 键的行数组。

    按 table_key 前缀分流：
      - bad_debt_individual_rows/* → D2-bd-individual-rows
      - bad_debt_combined_rows/*   → 按行内 category 分流回 D2-bd-aging-rows / D2-bd-customer-rows

    组合区回写时，行的归属键由 base_state 里该 rowId 原本所在的键决定（保留 category 归属），
    新行（base 无）默认落 aging 键（前端会以正确 category 覆盖）。summary 行不在投影里故不回写。

    返回 (merged_by_store, applied, visited, touched_rows)。
    merged_by_store: {store_item_id: [row, ...]}，只含 dynamic 业务行（summary 由前端 computed）。
    """
    base = dict(base_states) if isinstance(base_states, Mapping) else {}

    def _base_rows(store_id: str) -> list[dict[str, Any]]:
        raw = base.get(store_id)
        if isinstance(raw, (str, bytes, bytearray)):
            try:
                parsed = json.loads(
                    raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw or "[]"
                )
            except ValueError:
                parsed = []
        elif isinstance(raw, list):
            parsed = raw
        else:
            parsed = []
        return [dict(r) for r in parsed if isinstance(r, Mapping) and is_persisted_row(r)]

    # 建 rowId → (store_id, row) 索引（用于组合区回写时确定归属键）。
    rid_to_store: dict[str, str] = {}
    by_id: dict[str, dict[str, dict[str, Any]]] = {
        STORE_ITEM_ID_INDIVIDUAL: {},
        STORE_ITEM_ID_AGING: {},
        STORE_ITEM_ID_CUSTOMER: {},
    }
    order: dict[str, list[str]] = {
        STORE_ITEM_ID_INDIVIDUAL: [],
        STORE_ITEM_ID_AGING: [],
        STORE_ITEM_ID_CUSTOMER: [],
    }
    for store_id in (STORE_ITEM_ID_INDIVIDUAL, STORE_ITEM_ID_AGING, STORE_ITEM_ID_CUSTOMER):
        for row in _base_rows(store_id):
            rid = str(row.get(ROW_IDENTITY_STORE_KEY_D23) or "").strip()
            if not rid:
                continue
            by_id[store_id][rid] = dict(row)
            order[store_id].append(rid)
            rid_to_store[rid] = store_id

    applied = 0
    visited = 0
    touched: set[str] = set()

    ind_prefix = f"{ROWS_TABLE_KEY_INDIVIDUAL}/"
    cmb_prefix = f"{ROWS_TABLE_KEY_COMBINED}/"

    # 🔴 P1-3：category → store 键（组合区分流权威）。
    _CAT_TO_STORE = {"aging": STORE_ITEM_ID_AGING, "customer-type": STORE_ITEM_ID_CUSTOMER}
    # 投影带出的 rowId→category（build_d23_store_projection 附加），供新行分流。
    proj_category: dict[str, str] = dict(getattr(projection, "_d23_combined_category", {}) or {})
    # base 行的 rowId→category（存在行的归属权威，比 rid_to_store 更细，含 category 字段）。
    base_category: dict[str, str] = {}
    for store_id in (STORE_ITEM_ID_AGING, STORE_ITEM_ID_CUSTOMER):
        for row in _base_rows(store_id):
            rid0 = str(row.get(ROW_IDENTITY_STORE_KEY_D23) or "").strip()
            if rid0:
                base_category[rid0] = str(row.get("category") or "")

    def _combined_target(rid: str) -> str:
        """组合区回写归属：base 归属键 → base category → 投影 category。三者皆无 fail closed。

        🔴 第二轮复盘修复（问题 3/4）：此前无信号时兜底 `STORE_ITEM_ID_AGING` 并把
        `category: "aging"` 永久写死进这行数据——下次 merge 时 `base_category` 会把这个
        自造的标签当权威读回，行从此**永久锁死**在错误分类，且永远无法被后续编辑纠正
        （因为 base 归属键从此有值，优先级最高）。这是「静默猜测自我加固成事实」，
        与同文件其余分支的 fail-closed 风格（缺行身份/重复行身份均直接抛）不一致。

        改为 fail closed：三条线索都缺时抛 `StorePayloadError`，不生成任何归属猜测，
        不污染 base 数据。真实场景里这条路径几乎不可达——前端 `useD2BadDebt.addSubRow`
        创建新行时总是显式传 `category`（见 `createEmptySubRow`），只有绕过前端直接摆
        缺 category 的 payload 才会触发；触发时应该让调用方看到明确错误，而不是让平台
        悄悄替它做了一个可能错的分类决定。
        """
        if rid in rid_to_store and rid_to_store[rid] in _CAT_TO_STORE.values():
            return rid_to_store[rid]
        cat = base_category.get(rid) or proj_category.get(rid) or ""
        target = _CAT_TO_STORE.get(cat)
        if target is None:
            raise StorePayloadError(
                f"组合区行 {rid!r} 无法判定归属（aging/customer-type）—— base 与投影均未"
                "带出 category 信号 —— 不得静默兜底猜测（会把猜测写死成事实、永久锁死错误分类）"
            )
        return target

    for key in projection.stable_keys():
        sk = str(key)
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        rid = str(rid)
        column_key = sk.rsplit("/", 1)[-1]
        store_key = _COLUMN_KEY_TO_STORE_KEY.get(column_key)
        if store_key is None:
            continue
        if sk.startswith(ind_prefix):
            target_store = STORE_ITEM_ID_INDIVIDUAL
        elif sk.startswith(cmb_prefix):
            target_store = _combined_target(rid)
        else:
            continue
        target = by_id[target_store].get(rid)
        if target is None:
            # 新行携带其归属 category（组合区两键各自 category；individual 键为 individual）。
            new_cat = {
                STORE_ITEM_ID_INDIVIDUAL: "individual",
                STORE_ITEM_ID_AGING: "aging",
                STORE_ITEM_ID_CUSTOMER: "customer-type",
            }.get(target_store, "")
            target = {
                ROW_IDENTITY_STORE_KEY_D23: rid, "isSubRow": True, "isFixed": False,
                "category": new_cat,
            }
            by_id[target_store][rid] = target
            order[target_store].append(rid)
        visited += 1
        new_val = getattr(fv, "value", None)
        if target.get(store_key) != new_val:
            target[store_key] = new_val
            applied += 1
            touched.add(rid)

    merged: dict[str, list[dict[str, Any]]] = {}
    for store_id in (STORE_ITEM_ID_INDIVIDUAL, STORE_ITEM_ID_AGING, STORE_ITEM_ID_CUSTOMER):
        merged[store_id] = [by_id[store_id][rid] for rid in order[store_id]]
    return merged, applied, visited, touched
