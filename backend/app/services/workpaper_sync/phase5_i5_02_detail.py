# -*- coding: utf-8 -*-
"""I5-2「其他非流动资产明细表」—— sheet 层薄声明（I 循环结构最深的一张）。

spec: `i2-i4-i5-carrier-and-structure-exceptions` · Task 11 / 17

═══ 🔴 三区完全镜像：**同一行同时出现在三个区**（平台新形态）═══

```
R10  '其他非流动资产原值：'   区标题
R11-R21  第 1 区（11 行）    A 列**字面标签** · B..K editable · E/L/M/N/O formula  → gross.*
R22      footer 合计        B..O 各 =SUM(x11:x21)
R23  '减值准备：'            区标题
R24-R34  第 2 区（11 行）    🔴 A 列 **=A11..=A21 镜像公式** · B..K editable · E/L/M/N/O formula → impairment.*
R35      footer 合计        B..O 各 =SUM(x24:x34)
R36  '净值：'                区标题
R37-R47  第 3 区（11 行）    🔴 **A..O 全列 =x11-x24 逐格派生** → fully_derived_region
R48      footer 合计        B..O 各 =SUM(x37:x47)
```

🔴 **与平台既有两种多区范式都不同**：

| 范式 | 形态 | 先例 |
|---|---|---|
| 一区一 store 键 | 各区行集互斥，各有自己的 item_id | `phase5_d3_04_analysis` 双区 |
| `region_filter` | 同一 store 键，行按字段值**分到**某一个区 | G9/G1 三区（`section` 字段） |
| 🔴 **本表** | 同一 store 键，**一行同时在三个区**（gross 在区①、impairment 在区②、净值派生） | 无先例 |

⇒ 处置：**建两个 spec 共享同一 `store_item_id`**（`I5-2-rows`），
`field_specs` 的 `json_key` 分别走嵌套路径 `gross/*` 与 `impairment/*`；
**第 3 区不建 spec**（`fully_derived_region`，整区跳过不接受用户输入 ——
若允许写入，用户改的净值会在下次 render 被 `=x11-x24` 覆盖、静默丢失）。

🔴 **三区行数必须相同（各 11）且按行序镜像对应**；变异「把某一区改成 10 行」SHALL 打红
—— 镜像一破，第 3 区就会按错行去减。

═══ 🔴 内置行「删除」= 原位重置（IE-4）═══

`useI5Detail.ts#L821-839` 的 `removeRow(rowId)`：
`if (row.isBuiltin) rows[idx] = emptyI5DetailRow({...}) else rows.splice(idx, 1)`

传入 `emptyI5DetailRow` 的字段里**原本不含 `rowId`**，而 `emptyI5DetailRow` 内
`#L305 rowId: generateRowId()` ⇒ **重置后 rowId 变了**且 `_persist()` 会把新 rowId 落库。

🔴 双重影响：①行数不变（按行数或 `projectName` 比对会认为没变）②rowId 变了
（按 rowId 比对会认为「删一行 + 增一行」）。

**已修（修复①）**：`#L826` 现在传 `rowId: row.rowId` 保留原身份。
**契约层兜底（修复②）**：声明 `builtin_row_identity_field = "projectName"` ——
实现自己就在用它反查 `indexRef`（`#L830` 的
`I5_BUILTIN_CATEGORIES.find(c => c.name === row.projectName)?.indexRef`）⇒
已落库的漂移数据仍能按 `projectName` 对上。

═══ CD-3：分类 clean（唯一正例之一）═══

`I5_BUILTIN_CATEGORIES`（**10 条**）对 `明细表I5-2!A11:A20`（openpyxl 真读 10 格），
**有序等值 10/10** ⇒ verdict `MATCH` / status `clean`。
边界：`A21` = `……`（可扩位）· `A22` = `合计` ⇒ 声明区间边界正确。

═══ 几何（openpyxl 逐格实测）═══

`max_row=63` / `max_column=26` / **有效内容列 17（A..Q）** / definedName **334** /
merged **8** / 无 Excel Table / `ws.protection.sheet=False` / **334 公式（全 I 最多）**。

* **两级表头 R8 / R9**（全 I 最浅）
* 公式列（两区同形）：`E = SUM(B:C)-D` · `L = B+F+G` · `M = C+H+J` · `N = D+I+K` · `O = L+M-N`
* UUID 列 **R**（= 有效内容列 17 + 1）。`max_column` 是 26，差 9 列。

🔴 **definedName 334**：与 I4 的 476 一起构成「基线不增长」口径的唯一实证场
（其余四册全 0 ⇒ 照抄 H 的「断言全 0」只有这两册会打红）。**不删**（模板公式的命名引用）。

═══ payload mode `passthrough` 未被真库证实 + 真库载荷是 E2E 种子 ═══

真库 `I5-2-rows` **745 B**（全 I 最大）但 `rowId == "e2e-i52-contract"` ⇒
🔴 **是 E2E 测试种子不是业务数据**（随 E2E 套件可被重置）⇒
标 `live_payload_is_e2e_seed_not_business_data`，**不得**据此宣称 `passthrough` 已被证实；
roundtrip 用**合成载荷**并标 `synthetic_payload`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    StoreKind,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 共享常量
# ═══════════════════════════════════════════════════════════════════════════

MANAGED_SHEET_I502: Final[str] = "明细表I5-2"
TEMPLATE_ID_I502: Final[str] = "I52"
UUID_COL_I502: Final[str] = "R"
HEADER_GROUP_ROW_I502: Final[int] = 8
HEADER_LEAF_ROW_I502: Final[int] = 9
EFFECTIVE_COLUMNS_I502: Final[int] = 17
MAX_COLUMN_I502: Final[int] = 26
FOOTER_MARKER_I502: Final[str] = "合计"
#: 🔴 IC-10：definedName 基线（**非 0** —— 与 I4 476 一起是「基线不增长」口径的唯一实证场）
DEFINED_NAME_BASELINE_I502: Final[int] = 334

#: 三区共享同一个 store 键（**一行同时在三个区**，平台新形态）。
STORE_ITEM_ID_I502: Final[str] = "I5-2-rows"
ROW_IDENTITY_STORE_KEY_I502: Final[str] = "rowId"
EMPTY_PAYLOAD_I502: Final[str] = "[]"

#: 🔴 IE-4：内置行的**事实主键**（重置时 rowId 会变，projectName 与 indexRef 被保留）。
BUILTIN_ROW_IDENTITY_FIELD_I502: Final[str] = "projectName"
BUILTIN_ROW_DELETE_SEMANTICS_I502: Final[str] = "reset_in_place"

#: 🔴 三区镜像事实（行数必须相同、按行序对应）。
REGION_MIRROR_I502: Final[dict[str, object]] = {
    "row_count_each": 11,
    "mirrored_by": "row_order",
    "region_1": {"rows": [11, 21], "footer": 22, "role": "gross", "label_form": "字面标签"},
    "region_2": {
        "rows": [24, 34],
        "footer": 35,
        "role": "impairment",
        "label_form": "A 列 =A11..=A21 镜像公式（A 列本身是 FORMULA 不是 editable）",
    },
    "region_3": {
        "rows": [37, 47],
        "footer": 48,
        "role": "carrying",
        "kind": "fully_derived_region",
        "label_form": "A 列 =A24..=A34",
        "value_form": "A..O 全列逐格 =x11-x24（原值 − 减值）",
        "managed": False,
    },
    "note": (
        "🔴 三区行数必须相同（各 11）且按行序镜像对应；变异「把某一区改成 10 行」SHALL 打红 "
        "—— 镜像一破，第 3 区就会按错行去减。"
        "🔴 第 3 区 **fully_derived_region**：整区跳过不接受用户输入 —— 若允许写入，"
        "用户改的净值会在下次 render 被 =x11-x24 覆盖、静默丢失。"
    ),
}

#: CD-3：分类 clean（有序等值 10/10）。
CLASSIFICATION_FACTS_I502: Final[dict[str, object]] = {
    "impl_constant": "I5_BUILTIN_CATEGORIES",
    "impl_count": 10,
    "source_ref": "明细表I5-2!A11:A20",
    "source_real_count": 10,
    "verdict": "MATCH",
    "status": "clean",
    "boundary_note": "A21 = `……`（可扩位）· A22 = `合计` ⇒ 声明区间边界正确",
}

TEMPLATE_CELL_LOCK_FACTS_I502: Final[dict[str, object]] = {
    "sheet_protection_enabled": False,
    "note": "ws.protection.sheet=False ⇒ locked 惰性；mode 按「该格逐行有没有真公式」判。",
}

#: 两区同形的公式列（模板有列、store 侧是前端重算的派生值）。
_FORMULA_COLUMNS: Final[tuple[str, ...]] = ("E", "L", "M", "N", "O")
TEMPLATE_ONLY_FORMULA_COLUMNS_I502: Final[tuple[tuple[str, str], ...]] = (
    ("E", "期末数（未审）= SUM(B:C)-D"),
    ("L", "期初数（审定）= B+F+G"),
    ("M", "本期增加（审定）= C+H+J"),
    ("N", "本期减少（审定）= D+I+K"),
    ("O", "期末数（审定）= L+M-N"),
)


def _formula_templates(first_row: int) -> dict[str, str]:
    """两区公式逐字同形（只差行号），故由同一处生成 —— 抄两遍就是两个漂移面。"""
    del first_row  # 模板用 `{r}` 占位，行号由引擎代入
    return {
        "E": "=SUM(B{r}:C{r})-D{r}",
        "L": "=B{r}+F{r}+G{r}",
        "M": "=C{r}+H{r}+J{r}",
        "N": "=D{r}+I{r}+K{r}",
        "O": "=L{r}+M{r}-N{r}",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. 字段声明（两区同构，只差 json_key 的嵌套前缀）
# ═══════════════════════════════════════════════════════════════════════════

#: 列 → (column_key 后缀, value_type, I5RollAmounts 字段名, 模板叶子标题, group_header_cell)
#: 🔴 A 列在两区语义不同（区① editable 字面标签 / 区② FORMULA 镜像）⇒ 不在此表，各区单独给。
_ROLL_COLUMNS: Final[tuple[tuple[str, str, str, str, str], ...]] = (
    ("unadj_opening", "B", "unadjOpening", "期初数", "B8"),
    ("unadj_increase", "C", "unadjIncrease", "本期增加", "B8"),
    ("unadj_decrease", "D", "unadjDecrease", "本期减少", "B8"),
    ("opening_aje", "F", "openingAje", "账项调整", "F8"),
    ("opening_rje", "G", "openingRje", "重分类调整", "F8"),
    ("aje_increase", "H", "ajeIncrease", "本期增加", "H8"),
    ("aje_decrease", "I", "ajeDecrease", "本期减少", "H8"),
    ("rje_increase", "J", "rjeIncrease", "本期增加", "J8"),
    ("rje_decrease", "K", "rjeDecrease", "本期减少", "J8"),
)


def _field_specs_for(
    block: str, *, label_mode: str, label_json_key: str
) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """装配某一区的 field_specs。

    :param block: 嵌套前缀（`gross` / `impairment`）—— json_key 走 `{block}/{字段名}`。
    :param label_mode: A 列的 mode（区① `editable` 字面标签 / 区② `formula` 镜像）。
    :param label_json_key: A 列映射的 store 字段（区① `projectName` / 区② 空串=不映射）。
    """
    head: list[tuple[str, str, str, str, str, str, str]] = []
    if label_mode == "editable":
        head.append(
            ("project_name", "A", "editable", "text", label_json_key, "项目名称", "")
        )
    return tuple(
        head
        + [
            (
                f"{block}_{key}",
                col,
                "editable",
                "amount",
                f"{block}/{json_field}",
                header,
                group,
            )
            for key, col, json_field, header, group in _ROLL_COLUMNS
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 两个 spec（共享 store_item_id，第 3 区不建 spec）
# ═══════════════════════════════════════════════════════════════════════════

SHEET_KEY_GROSS_I502: Final[str] = "i52-gross-managed"
ROWS_TABLE_KEY_GROSS_I502: Final[str] = "other_noncurrent_gross_rows"
SHEET_KEY_IMPAIRMENT_I502: Final[str] = "i52-impairment-managed"
ROWS_TABLE_KEY_IMPAIRMENT_I502: Final[str] = "other_noncurrent_impairment_rows"

#: 第 1 区：原值（A 列是 editable 字面标签 ⇒ 映射 `projectName`）
SPEC_I502_GROSS: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_I502,
    sheet_key=SHEET_KEY_GROSS_I502,
    table_key=ROWS_TABLE_KEY_GROSS_I502,
    template_id=f"{TEMPLATE_ID_I502}G",
    table_name=f"GT_{TEMPLATE_ID_I502}G_ROWS",
    uuid_col=UUID_COL_I502,
    first_data_row=11,
    last_data_row=21,
    footer_row=22,
    header_group_row=HEADER_GROUP_ROW_I502,
    header_leaf_row=HEADER_LEAF_ROW_I502,
    store_item_id=STORE_ITEM_ID_I502,
    empty_payload=EMPTY_PAYLOAD_I502,
    row_identity_key=ROW_IDENTITY_STORE_KEY_I502,
    store_kind=StoreKind.rows,
    field_specs=_field_specs_for(
        "gross", label_mode="editable", label_json_key="projectName"
    ),
    formula_columns=_FORMULA_COLUMNS,
    formula_templates=_formula_templates(11),
    footer_marker=FOOTER_MARKER_I502,
    error_label="I5-2 其他非流动资产明细表（原值区）",
)

#: 第 2 区：减值准备（🔴 A 列是 **FORMULA 镜像** `=A11`..`=A21` ⇒ **不映射任何 store 字段**）
SPEC_I502_IMPAIRMENT: Final[RowTableSheetSpec] = RowTableSheetSpec(
    managed_sheet=MANAGED_SHEET_I502,
    sheet_key=SHEET_KEY_IMPAIRMENT_I502,
    table_key=ROWS_TABLE_KEY_IMPAIRMENT_I502,
    template_id=f"{TEMPLATE_ID_I502}I",
    table_name=f"GT_{TEMPLATE_ID_I502}I_ROWS",
    uuid_col=UUID_COL_I502,
    first_data_row=24,
    last_data_row=34,
    footer_row=35,
    header_group_row=HEADER_GROUP_ROW_I502,
    header_leaf_row=HEADER_LEAF_ROW_I502,
    store_item_id=STORE_ITEM_ID_I502,
    empty_payload=EMPTY_PAYLOAD_I502,
    row_identity_key=ROW_IDENTITY_STORE_KEY_I502,
    store_kind=StoreKind.rows,
    field_specs=_field_specs_for(
        "impairment", label_mode="formula", label_json_key=""
    ),
    #: 🔴 A 列也进 formula_columns（`=A11` 镜像）—— 否则 merge 会拿 HTML 的 None 覆盖镜像公式
    formula_columns=("A",) + _FORMULA_COLUMNS,
    formula_templates={"A": "=A{mirror_r}", **_formula_templates(24)},
    footer_marker=FOOTER_MARKER_I502,
    error_label="I5-2 其他非流动资产明细表（减值准备区）",
)

ALL_SPECS_I502: Final[tuple[RowTableSheetSpec, ...]] = (
    SPEC_I502_GROSS,
    SPEC_I502_IMPAIRMENT,
)
