"""D4-12: 合同检查表 —— 转置动态表（一列=一份合同，一行=一个字段）。

spec: d4-12-transposed-writeback / Requirement 3

薄壳同 D4-29：几何/身份收敛到 ``SPEC_D412``，算法委托通用引擎
:mod:`phase5_transposed_sheet`。与 D4-29 的差异（Task 1 冻结）：
* 首列 B（A 是字段标签列，无独立 label 子列）；末预留列 K（模板预画 B–K 共 10 列）。
* 21 字段连续 R11–R31。
* header_row R10 存索引号 ``D4-12-N``（非受管业务字段）→ ``header_field_key=None``。
* store item 扁平 ``{id, ...21 平铺字段}``（无 D4-29 的 fields 嵌套）→ ``nested_fields_key=None``。
* 模板无 definedName + 无隐藏载体行 → 由 instrumentation 注入（Task 7）。
"""
from __future__ import annotations

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

MANAGED_SHEET = "合同检查表D4-12"
SHEET_KEY = "d4-12-managed"
TABLE_KEY = "contract_inspection_transposed"
TEMPLATE_ID = "D412"
STORE_ITEM_ID = "D4-12-contracts-v2"
IDENTITY_KEY = "id"
HEADER_ROW = 10
FOOTER_ROWS = (32, 36)
STATIC_PROMPT_FIRST_ROW = 38
FIRST_CONTRACT_COLUMN = "B"
INITIAL_CONTRACT_COLUMN = "K"
IDENTITY_CARRIER_ROW = 9
IDENTITY_CARRIER_PREFIX = "GT-CONTRACT-"
DEFINED_NAME = "GT_MANAGED_REGION_D412"
MANAGED_REF = "$B$10:$K$31"

# 21 字段 ↔ R11–R31 连续（Task 1 openpyxl 冻结 + 前端 ContractInspectionItem 逐项对齐）。
FIELD_ROWS = {
    "contractNo": 11, "counterparty": 12, "signDate": 13, "serviceContent": 14,
    "contractAmount": 15, "deliveryTime": 16, "deliveryMethod": 17, "settlementMethod": 18,
    "settlementTime": 19, "warrantyClause": 20, "returnClause": 21, "breachClause": 22,
    "specialTerms": 23, "isSigned": 24, "isSealed": 25, "recognitionMethod": 26,
    "acceptanceClause": 27, "recognitionTime": 28, "controlTransferDoc": 29,
    "specialTransaction": 30, "conclusion": 31,
}
FIELD_KEYS = tuple(FIELD_ROWS)

#: 数值语义字段（Requirement 3.4a）。合同金额 value_type=amount。
#: 🔴 名实边界：value_type=amount **仅用于契约声明**（下游校验/展示语义）；通用引擎的
#: materialize/extract 对它与其它字段**同走 text 编解码**，无 amount 专用类型化。故非空数值
#: openpyxl 原样往返保数值（12345/0 不丢）、空值往返成空字符串 ''（不静默投 0），前端
#: `ContractInspectionItem.contractAmount:number` 经 parseNum('')===0 兜底。见
#: test_d4_12_transposed_roundtrip.test_contract_amount_numeric_semantics。
#: 注意小写化后比对（stable_field_key 已小写），且 ValueType 枚举用 'amount' 非 'number'。
NUMERIC_FIELDS = ("contractamount",)

#: D4-12 的转置表规格（几何/身份/store 形态单一真源）。
SPEC_D412 = TransposedSheetSpec(
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
    first_entity_column=FIRST_CONTRACT_COLUMN,
    initial_entity_column=INITIAL_CONTRACT_COLUMN,
    identity_carrier_row=IDENTITY_CARRIER_ROW,
    identity_carrier_prefix=IDENTITY_CARRIER_PREFIX,
    defined_name=DEFINED_NAME,
    managed_ref=MANAGED_REF,
    header_field_key=None,
    nested_fields_key=None,
    numeric_fields=NUMERIC_FIELDS,
    pointer_root="contracts",
    error_label="D4-12",
    entity_noun="contract",
    entity_noun_plural="contracts",
)


# ── 既有导出名（委托通用引擎 + SPEC_D412），签名与 D4-29 薄壳对齐 ──────


def resolve_managed_sheet(workbook_bytes, *, defined_name=DEFINED_NAME):
    return _resolve_managed_sheet(workbook_bytes, spec=SPEC_D412)


def stable_key_for(contract_id, field_key):
    return _stable_key_for(contract_id, field_key, spec=SPEC_D412)


def build_store_projection(payload, *, contract, limits=None):
    return _build_store_projection(payload, contract=contract, spec=SPEC_D412, limits=limits)


def merge_projection_into_store(*, projection, base_payload):
    return _merge_projection_into_store(projection=projection, base_payload=base_payload, spec=SPEC_D412)


def sheet_payload():
    return _sheet_payload(spec=SPEC_D412)


def mapping_digest_payload():
    return sheet_payload()


def compute_mapping_digest():
    return canonical_digest(mapping_digest_payload())


# Task 6 隔离 probe 往返 + 契约结构冻结后回填（sheet_payload canonical digest）。
EXPECTED_MAPPING_DIGEST: str | None = "2d3a1c5f77f198283603ac42b4eb54f5d67ef2f4dfa7aa57a2673a023c689e9a"


def assert_mapping_digest():
    got = compute_mapping_digest()
    if EXPECTED_MAPPING_DIGEST is None:
        return got
    if got != EXPECTED_MAPPING_DIGEST:
        raise ValueError(f"D4-12 mapping_digest drift: {got} != {EXPECTED_MAPPING_DIGEST}")
    return got


def materialize_transposed_workbook(workbook_bytes: bytes, payload, *, sheet_name=MANAGED_SHEET) -> bytes:
    return _materialize_transposed_workbook(workbook_bytes, payload, spec=SPEC_D412)


def extract_transposed_workbook(workbook_bytes: bytes, *, sheet_name=MANAGED_SHEET):
    return _extract_transposed_workbook(workbook_bytes, spec=SPEC_D412)


def materialize_file(output, projection, contract):
    if TABLE_KEY not in projection.row_keys:
        return
    current_payload = extract_transposed_workbook(output.read_bytes())
    contracts, _, _, _ = merge_projection_into_store(
        projection=projection, base_payload=current_payload
    )
    output.write_bytes(materialize_transposed_workbook(output.read_bytes(), contracts))


def extract_file(artifact, contract):
    return build_store_projection(extract_transposed_workbook(artifact.read_bytes()), contract=contract)
