"""D4-29: logical customer rows rendered as identity-bearing Excel columns.

此模块现为**薄壳**（spec d4-12-transposed-writeback / Task 3）：几何/身份常量收敛到
``SPEC_D429`` 实例，算法委托通用引擎 :mod:`phase5_transposed_sheet`。既有导出名
（``is_enabled`` / ``materialize_file`` / ``extract_file`` / ``materialize_transposed_workbook``
/ ``extract_transposed_workbook`` / ``assert_mapping_digest`` / ``sheet_payload`` /
``build_store_projection`` / ``merge_projection_into_store`` / ``stable_key_for`` /
``FIELD_ROWS`` / ``FIELD_KEYS`` 等）全部保留，使 adapter / 观测器 / 守卫 import 零改动。

零回归纪律：``sheet_payload()`` / materialize 字节 / extract 字段 / ``EXPECTED_MAPPING_DIGEST``
必须与泛化前逐字/逐字节相同（Task 5 前置门 + test_d4_29_customer_detail_sync.py 钉死）。
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

MANAGED_SHEET = "客户信息检查表D4-29"
SHEET_KEY = "d4-29-managed"
TABLE_KEY = "customer_detail_transposed"
TEMPLATE_ID = "D429"
STORE_ITEM_ID = "D4-29-customers"
IDENTITY_KEY = "id"
HEADER_ROW = 10
FIRST_FIELD_ROW = 11
LAST_FIELD_ROW = 41
FOOTER_ROWS = (42, 46)
STATIC_PROMPT_FIRST_ROW = 48
FIRST_CUSTOMER_COLUMN = "C"
INITIAL_CUSTOMER_COLUMN = "M"
IDENTITY_CARRIER_ROW = 9
IDENTITY_CARRIER_PREFIX = "GT-CUSTOMER-"
DEFINED_NAME = "GT_MANAGED_REGION_D429"
MANAGED_REF = "$C$10:$M$41"

# Rows 27 and 32..33 are source-template continuation slots, not new fields.
FIELD_ROWS = {
    "creditCode": 11, "regAddress": 12, "officeAddress": 13, "website": 14,
    "websiteIp": 15, "email": 16, "establishDate": 17, "registeredCapital": 18,
    "bizScope": 19, "headcount": 20, "legalRep": 21, "shareholder1": 22,
    "shareholder2": 23, "shareholder3": 24, "shareholder4": 25, "shareholder5": 26,
    "chairman": 28, "gm": 29, "otherMgmt": 30, "keyHandler": 31,
    "actualController": 34, "isRelated": 35, "isAlsoSupplier": 36,
    "cooperationStart": 37, "hasOverdue": 38, "bizStatus": 39,
    "isBlacklisted": 40, "infoSource": 41,
}
FIELD_KEYS = tuple(FIELD_ROWS)

#: D4-29 的转置表规格（几何/身份/store 形态的单一真源）。
SPEC_D429 = TransposedSheetSpec(
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
    first_entity_column=FIRST_CUSTOMER_COLUMN,
    initial_entity_column=INITIAL_CUSTOMER_COLUMN,
    identity_carrier_row=IDENTITY_CARRIER_ROW,
    identity_carrier_prefix=IDENTITY_CARRIER_PREFIX,
    defined_name=DEFINED_NAME,
    managed_ref=MANAGED_REF,
    header_field_key="name",
    nested_fields_key="fields",
    pointer_root="customers",
    error_label="D4-29",
    entity_noun="customer",
    entity_noun_plural="customers",
)


# ── 既有导出名（委托通用引擎 + SPEC_D429），签名保持不变 ──────────────


def resolve_managed_sheet(workbook_bytes, *, defined_name=DEFINED_NAME):
    return _resolve_managed_sheet(workbook_bytes, spec=SPEC_D429)


def stable_key_for(customer_id, field_key):
    return _stable_key_for(customer_id, field_key, spec=SPEC_D429)


def build_store_projection(payload, *, contract, limits=None):
    return _build_store_projection(payload, contract=contract, spec=SPEC_D429, limits=limits)


def merge_projection_into_store(*, projection, base_payload):
    return _merge_projection_into_store(projection=projection, base_payload=base_payload, spec=SPEC_D429)


def sheet_payload():
    return _sheet_payload(spec=SPEC_D429)


def mapping_digest_payload():
    return sheet_payload()


def compute_mapping_digest():
    return canonical_digest(mapping_digest_payload())


EXPECTED_MAPPING_DIGEST = "e3193dd9b581ac32041d25d7def13df44955108cce34c0341b05ec30eda17856"


def assert_mapping_digest():
    got = compute_mapping_digest()
    if got != EXPECTED_MAPPING_DIGEST:
        raise ValueError(f"D4-29 mapping_digest drift: {got} != {EXPECTED_MAPPING_DIGEST}")
    return got


def materialize_transposed_workbook(workbook_bytes: bytes, payload, *, sheet_name=MANAGED_SHEET) -> bytes:
    return _materialize_transposed_workbook(workbook_bytes, payload, spec=SPEC_D429)


def extract_transposed_workbook(workbook_bytes: bytes, *, sheet_name=MANAGED_SHEET):
    return _extract_transposed_workbook(workbook_bytes, spec=SPEC_D429)


def row_oriented_sheets(contract):
    """Exclude explicitly dispatched column layouts from row-table instrumentation."""
    excluded = {s["sheet_key"] for s in contract.canonical_payload.get("sheets", [])
                if any(t.get("layout") == "customer_columns" for t in s.get("tables", []))}
    return [s for s in contract.sheets if s.sheet_key not in excluded]


def is_enabled(contract):
    from app.services.workpaper_sync.transposed_registry import resolve_transposed_specs
    return bool(resolve_transposed_specs(contract))


def materialize_file(output, projection, contract):
    if TABLE_KEY not in projection.row_keys:
        return
    current_payload = extract_transposed_workbook(output.read_bytes())
    customers, _, _, _ = merge_projection_into_store(
        projection=projection, base_payload=current_payload
    )
    output.write_bytes(materialize_transposed_workbook(output.read_bytes(), customers))


def extract_file(artifact, contract):
    return build_store_projection(extract_transposed_workbook(artifact.read_bytes()), contract=contract)
