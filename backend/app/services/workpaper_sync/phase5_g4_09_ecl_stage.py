# -*- coding: utf-8 -*-
"""G4-9「债权投资三阶段划分」—— 转置表薄声明（16384 列 + 实体列 G..J）。

spec: `g4-g6-shared-workbook-three-entry-lanes` · Task 10

═══ 几何（openpyxl 逐格实测）═══

`债权投资三阶段划分G4-9`：`max_row=61` / **`max_col=16384`** / 有效列 **11**（A..K）。

* **实体列 G..J**（`投资1：` / `投资2：` / `投资3：` / `投资X：`）—— 一列一个逻辑投资。
  身份载体行 R9（放实体列标签）。
* **字段行 R10-R23**（段①「信用风险是否显著增加」的 14 个评估维度）：
  A 列问题 + B 列说明（不受管）+ G..J 各投资的评估值（受管）。
* 段②③ 是清单式（序号+条件），R28-R31 / R37-R45 不进受管字段（列表非填列）。
* footer / 分析结论 R24 + 提示区 R53-R60（不受管）。
* 🔴 **16384 列策略**（裁决 G46-H3）：有效内容列 11（A..K），UUID 放**第 12 列 L**
  （有效内容列 +1），**不放 max_col+1**（后者超 Excel XFD 上限）。
* payload：`dual_write`。
"""
from __future__ import annotations

from typing import Final

from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.phase5_transposed_sheet import (
    TransposedSheetSpec,
    build_store_projection as _build_store_projection,
    extract_transposed_workbook as _extract_transposed_workbook,
    materialize_transposed_workbook as _materialize_transposed_workbook,
    merge_projection_into_store as _merge_projection_into_store,
    resolve_managed_sheet as _resolve_managed_sheet,
    sheet_payload as _sheet_payload,
    stable_key_for as _stable_key_for,
)

MANAGED_SHEET: Final[str] = "债权投资三阶段划分G4-9"
SHEET_KEY: Final[str] = "g409-managed"
TABLE_KEY: Final[str] = "bond_ecl_stage_transposed"
TEMPLATE_ID: Final[str] = "G409"
STORE_ITEM_ID: Final[str] = "G4-9-rows"
IDENTITY_KEY: Final[str] = "id"
HEADER_ROW: Final[int] = 9
FOOTER_ROWS: Final[tuple[int, int]] = (24, 24)
STATIC_PROMPT_FIRST_ROW: Final[int] = 53
#: 🔴 实体列从 G 起（A/B 是问题+说明，C..F 被 B10:F10 合并覆盖）
FIRST_ENTITY_COLUMN: Final[str] = "G"
#: 模板预画到 J 列（投资X）
INITIAL_ENTITY_COLUMN: Final[str] = "J"
IDENTITY_CARRIER_ROW: Final[int] = 9
IDENTITY_CARRIER_PREFIX: Final[str] = "GT-G4ECL-"
DEFINED_NAME: Final[str] = "GT_MANAGED_REGION_G409"
#: 🔴 16384 列表：受管区取有效内容列 G..J（4 实体列 × 14 字段行）
MANAGED_REF: Final[str] = "$G$10:$J$23"

#: 段①「信用风险是否显著增加」的 14 个评估维度（R10-R23）。
FIELD_ROWS: Final[dict[str, int]] = {
    "internalPriceIndicator": 10,
    "rateOrTermChange": 11,
    "externalMarketIndicator": 12,
    "creditRatingChange": 13,
    "issuerBizFinanceChange": 14,
    "issuerOperatingResult": 15,
    "issuerRegulatoryChange": 16,
    "otherInstrumentCreditChange": 17,
    "guaranteeCreditChange": 18,
    "repaymentMechanismChange": 19,
    "contractTermChange": 20,
    "overduePerformanceChange": 21,
    "creditMgmtMethodChange": 22,
    "overdueInfo": 23,
}
FIELD_KEYS: Final[tuple[str, ...]] = tuple(FIELD_ROWS)

SPEC_G409: Final[TransposedSheetSpec] = TransposedSheetSpec(
    managed_sheet=MANAGED_SHEET,
    sheet_key=SHEET_KEY,
    table_key=TABLE_KEY,
    template_id=TEMPLATE_ID,
    store_item_id=STORE_ITEM_ID,
    identity_key=IDENTITY_KEY,
    header_row=HEADER_ROW,
    field_rows=FIELD_ROWS,
    footer_rows=FOOTER_ROWS,
    static_prompt_first_row=STATIC_PROMPT_FIRST_ROW,
    first_entity_column=FIRST_ENTITY_COLUMN,
    initial_entity_column=INITIAL_ENTITY_COLUMN,
    identity_carrier_row=IDENTITY_CARRIER_ROW,
    identity_carrier_prefix=IDENTITY_CARRIER_PREFIX,
    defined_name=DEFINED_NAME,
    managed_ref=MANAGED_REF,
    header_field_key="investName",
    nested_fields_key="fields",
    pointer_root="rows",
    error_label="G4-9",
    entity_noun="investment",
    entity_noun_plural="investments",
)


def resolve_managed_sheet(workbook_bytes, *, defined_name=DEFINED_NAME):
    return _resolve_managed_sheet(workbook_bytes, spec=SPEC_G409)


def stable_key_for(invest_id, field_key):
    return _stable_key_for(invest_id, field_key, spec=SPEC_G409)


def build_store_projection(payload, *, contract, limits=None):
    return _build_store_projection(payload, contract=contract, spec=SPEC_G409, limits=limits)


def merge_projection_into_store(*, projection, base_payload):
    return _merge_projection_into_store(projection=projection, base_payload=base_payload, spec=SPEC_G409)


def sheet_payload():
    return _sheet_payload(spec=SPEC_G409)


def compute_mapping_digest():
    return canonical_digest(sheet_payload())
