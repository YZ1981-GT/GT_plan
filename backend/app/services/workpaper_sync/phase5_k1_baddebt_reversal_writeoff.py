# -*- coding: utf-8 -*-
"""K1-9 坏账准备转回（收回）/核销检查表——同 sheet 双区、单 dict store 真双向 provider。

两区共用 checklist item `K1-9-writeoff`，载荷为
`{tables:{reversal:[], writeoff:[]}, auditProcedures, auditNote, conclusion, conclusionOption}`。
实现复用 RowTableSheetSpec 的同 sheet 兄弟区位移链，并用 dedicated merge 保留四个未受管标量。
"""
from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any, Final, Iterator, Mapping

from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION, SyncContract, contract_path_for, parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelInstrumentationSpec, build_instrumentation_payload_for_sheets,
)
from app.services.workpaper_sync.models import AuthorityModel, DefinitionKind
from app.services.workpaper_sync.phase5_entry_orchestration import (
    Phase5EntryConfig, build_orchestration,
)
from app.services.workpaper_sync.phase5_k_adjustment_summary import publish_with_authority
from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec, StoreKind

ENTRY_ID: Final[str] = "xlsx/gt-k1-other-receivables"
ADAPTER_ID: Final[str] = "k1.baddebt_reversal_writeoff_check"
WP_CODES: Final[frozenset[str]] = frozenset({"K1O"})
PILOT_CLASS: Final[str] = "k1_baddebt_reversal_writeoff_check"
TEMPLATE_RELATIVE_PATH: Final[str] = "K/K1 其他应收款.xlsx"
TEMPLATE_SHA256: Final[str] = "4abf05902fe09f7f6bec947c991c648669d26f39187f2f285866392c1c633eab"
MANAGED_SHEET: Final[str] = "坏账准备转回（收回）、核销检查表K1-9"
SHEET_KEY: Final[str] = "k109-managed"
STORE_ITEM_ID: Final[str] = "K1-9-writeoff"
EMPTY_STORE_PAYLOAD: Final[str] = "{}"
ROW_IDENTITY_STORE_KEY: Final[str] = "id"
MANAGED_LAST_COL: Final[str] = "H"
#: 首版 adapter builder 读取 provider 级常量（ExcelInstrumentationSpec 字段名是 uuid_col，
#: 它兼容读取的 uuid_column 不存在）；主区身份锚取 reversal 的 I 列，其余兄弟区由契约表绑定。
UUID_COL: Final[str] = "I"
TABLE_NAME: Final[str] = "GT_K109REV_ROWS"
ROWS_TABLE_KEY: Final[str] = "reversal"
ROWS_TABLE_KEY_REVERSAL: Final[str] = "reversal"
ROWS_TABLE_KEY_WRITEOFF: Final[str] = "writeoff"

REVERSAL_FIELDS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("unit", "A", "editable", "text", "unit", "单位名称", ""),
    ("reason", "B", "editable", "text", "reason", "转回原因", ""),
    ("method", "C", "editable", "text", "method", "收回方式", ""),
    ("basis", "D", "editable", "text", "basis", "原确定坏账准备的依据", ""),
    ("amount", "E", "editable", "amount", "amount", "收回或转回金额", ""),
    ("accum_provision", "F", "editable", "amount", "accumProvision", "收回或转回前累计已计提坏账准备金额", ""),
    ("analysis", "G", "editable", "text", "analysis", "合理性分析", ""),
    ("index_no", "H", "editable", "text", "indexNo", "索引号", ""),
)
WRITEOFF_FIELDS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("unit", "A", "editable", "text", "unit", "单位名称", ""),
    ("nature", "B", "editable", "text", "nature", "其他应收款的性质", ""),
    ("amount", "C", "editable", "amount", "amount", "核销金额", ""),
    ("reason", "D", "editable", "text", "reason", "核销原因", ""),
    ("procedure", "E", "editable", "text", "procedure", "履行的核销程序", ""),
    ("related_party", "F", "editable", "text", "relatedParty", "是否关联方往来", ""),
    ("analysis", "G", "editable", "text", "analysis", "合理性分析", ""),
    ("index_no", "H", "editable", "text", "indexNo", "索引号", ""),
)


def _spec(*, table_key: str, template_id: str, uuid_col: str, first: int, last: int,
          footer: int, header: int, fields: tuple, amount_col: str) -> RowTableSheetSpec:
    return RowTableSheetSpec(
        managed_sheet=MANAGED_SHEET, sheet_key=SHEET_KEY, table_key=table_key,
        template_id=template_id, table_name=f"GT_{template_id}_ROWS", uuid_col=uuid_col,
        first_data_row=first, last_data_row=last, footer_row=footer, header_row=header,
        store_item_id=STORE_ITEM_ID, empty_payload=EMPTY_STORE_PAYLOAD,
        row_identity_key=ROW_IDENTITY_STORE_KEY, store_kind=StoreKind.dict,
        field_specs=fields, formula_columns=(), footer_marker="合  计",
        footer_search_column="A", footer_carries_total_formula=True,
        error_label=f"K1-9 {table_key}", ghost_row_anchor_index=0,
    )


SPEC_REVERSAL: Final = _spec(
    table_key=ROWS_TABLE_KEY_REVERSAL, template_id="K109REV", uuid_col="I",
    first=12, last=14, footer=15, header=11, fields=REVERSAL_FIELDS, amount_col="E",
)
SPEC_WRITEOFF: Final = _spec(
    table_key=ROWS_TABLE_KEY_WRITEOFF, template_id="K109WO", uuid_col="J",
    first=18, last=20, footer=21, header=17, fields=WRITEOFF_FIELDS, amount_col="C",
)
SPECS: Final = (SPEC_REVERSAL, SPEC_WRITEOFF)


def _instrumentation(spec: RowTableSheetSpec) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID, template_id=spec.template_id,
        template_relative_path=TEMPLATE_RELATIVE_PATH, managed_sheet=spec.managed_sheet,
        first_data_row=spec.first_data_row, last_data_row=spec.last_data_row,
        footer_row=spec.footer_row, managed_last_col=MANAGED_LAST_COL,
        uuid_col=spec.uuid_col, table_name=spec.table_name, sheet_key=spec.sheet_key,
    )


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return _instrumentation(SPEC_REVERSAL)


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ...]:
    return tuple(_instrumentation(s) for s in SPECS)


def managed_row_table_specs() -> tuple[RowTableSheetSpec, ...]:
    return SPECS


def all_store_item_ids() -> tuple[str, ...]:
    return (STORE_ITEM_ID,)


_HOLDER: dict[str, Any] = {}


def instrumentation_definition_payload() -> dict[str, Any]:
    orch = _HOLDER["orch"]
    return build_instrumentation_payload_for_sheets(
        specs=instrumentation_specs(),
        template_definition_sha256=canonical_digest(orch.template_definition_payload()),
        template_sha256=TEMPLATE_SHA256, gate=orch.excel_carrier_gate(),
    )


def _contract_sheets() -> list[dict[str, Any]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import spec_to_contract_sheet_payload

    first = spec_to_contract_sheet_payload(SPEC_REVERSAL)
    second = spec_to_contract_sheet_payload(SPEC_WRITEOFF)
    assert first["sheet_key"] == second["sheet_key"] == SHEET_KEY
    first["tables"].extend(second["tables"])
    # 自动派生器以通用 `/rows` 表达；K1 的真 store 是对象内两数组，契约必须诚实写路径。
    for table in first["tables"]:
        region = table["table_key"]
        table["row_identity"]["json_pointer"] = f"/tables/{region}/*/id"
        for field in table["fields"]:
            json_key = field["json_pointer"].rsplit("/", 1)[-1]
            field["json_pointer"] = f"/tables/{region}/{{row_uuid}}/{json_key}"
    return [first]


def build_contract_payload() -> dict[str, Any]:
    orch = _HOLDER["orch"]
    tp = orch.template_definition_payload()
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION, "contract_id": ADAPTER_ID,
        "semantic_version": "1.0.0", "review_status": "reviewed", "document_type": "xlsx",
        "template_definition_sha256": canonical_digest(tp),
        "instrumentation_definition_sha256": canonical_digest(instrumentation_definition_payload()),
        "template": {"relative_path": TEMPLATE_RELATIVE_PATH, "template_sha256": TEMPLATE_SHA256,
                     "normalized_structure_hash": tp["normalized_structure_hash"]},
        "identity_carriers": ["hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"],
        "sheets": _contract_sheets(),
        "review": {
            "entry_id": ENTRY_ID, "pilot_class": PILOT_CLASS,
            "authority_root": "backend/wp_templates",
            "html_store": {"table": "checklist_responses", "item_id": STORE_ITEM_ID,
                           "row_identity_key": ROW_IDENTITY_STORE_KEY,
                           "shape": "json_object_with_two_row_arrays",
                           "store_only_keys": ["isReasonable", "auditProcedures", "auditNote",
                                               "conclusion", "conclusionOption"],
                           "note": "tables.reversal / tables.writeoff 共用一个 remark；两个派生 total 键不反写公式格。"},
            "derived_total_fields": {
                "K1-9-reversal-total": {"mode": "derived", "produced_by": "computed", "template_anchor": "E15"},
                "K1-9-writeoff-total": {"mode": "derived", "produced_by": "computed", "template_anchor": "C21"},
            },
            "cross_sheet_read_fields": {
                "K1-3-baddebt-rows": {"access": "read_only", "upstream_sheet": "坏账准备测算K1-8 / 明细表K1-2"},
                "K1-11-related-party": {"access": "read_only", "upstream_sheet": "关联方往来检查表K1-11"},
            },
            "row_count_mismatch": {
                "template_fixed_rows": 3,
                "overflow_strategy": "HTML 行数大于 3 时在各区合计行前扩行；同 sheet 兄弟区由框架 row-shift 按锚点重算，合计 SUM 范围随最后数据行扩展。",
                "underflow_strategy": "HTML 行数小于 3 时保留模板空行，不物理删行；空行不影响 SUM。",
            },
            "row_delete_api_kind": {
                "arity": 2, "param_order": ["section", "id"], "kind": "by_section_and_identity",
                "call_site_literals": ["reversal", "writeoff"],
                "host": "audit-platform/frontend/src/components/workpaper/k1/inspection/K1TabWriteoffCheck.vue",
            },
            "reviewed_basis": "openpyxl 实测 K1-9：转回 R12:R14/footer E15，核销 R18:R20/footer C21；同 sheet 兄弟区按 I/J 两个独立 UUID 列配对并由框架位移链重算。",
        },
    }


def _contract_path() -> Path:
    return contract_path_for(ADAPTER_ID)


_O = build_orchestration(Phase5EntryConfig(
    phase5_wave=PILOT_CLASS, entry_id=ENTRY_ID, adapter_id=ADAPTER_ID, wp_codes=WP_CODES,
    expected_profile_id="xlsx.editable.shared.single.room_service_wired.v1",
    template_relative_path=TEMPLATE_RELATIVE_PATH, template_sha256=TEMPLATE_SHA256,
    managed_sheet=MANAGED_SHEET, template_id=SPEC_REVERSAL.template_id, sheet_key=SHEET_KEY,
    rows_table_key=ROWS_TABLE_KEY_REVERSAL, first_data_row=SPEC_REVERSAL.first_data_row,
    last_data_row=SPEC_REVERSAL.last_data_row, footer_row=SPEC_REVERSAL.footer_row,
    managed_last_col=MANAGED_LAST_COL, uuid_col=SPEC_REVERSAL.uuid_col,
    table_name=SPEC_REVERSAL.table_name, authority_model=AuthorityModel.projection_contract,
    footer_marker="合  计", store_item_id=STORE_ITEM_ID,
    row_identity_store_key=ROW_IDENTITY_STORE_KEY, error_code_prefix="sync_phase5_k1_writeoff",
    build_contract_payload_fn=build_contract_payload, contract_file_path_fn=_contract_path,
    instrumentation_spec_fn=instrumentation_spec,
))
_HOLDER["orch"] = _O

EntrySelectionError = _O.EntrySelectionError
StorePayloadError = _O.StorePayloadError
Phase5Definitions = _O.Phase5Definitions
excel_carrier_gate = _O.excel_carrier_gate
authoritative_template_path = _O.authoritative_template_path
read_authoritative_template = _O.read_authoritative_template
template_definition_payload = _O.template_definition_payload
authority_model_payload = _O.authority_model_payload
contract_file_path = _O.contract_file_path
load_contract_from_disk = _O.load_contract_from_disk
build_matcher = _O.build_matcher
build_registration = _O.build_registration
register_adapter = _O.register_adapter
attach_adapters = _O.attach_adapters
manifest_capability_enabled = _O.manifest_capability_enabled
assert_manifest_capability_enabled = _O.assert_manifest_capability_enabled


def assert_contract_file_matches_source() -> SyncContract:
    expected = build_contract_payload()
    parse_contract(expected, adapter_id=ADAPTER_ID)
    disk = load_contract_from_disk()
    if canonical_digest(disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "K1-9 磁盘契约与 provider 现算 payload 不一致；请运行 "
            "generate_phase5_k_contracts.py --apply"
        )
    return disk


class K1StorePayloadError(ValueError):
    """K1-9 dict store 载荷不合法。"""


def _parse_payload(payload: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
    try:
        data = json.loads(text or "{}")
    except ValueError as exc:
        raise K1StorePayloadError(f"{STORE_ITEM_ID} JSON 非法: {exc}") from exc
    if isinstance(data, Mapping):
        return data
    if isinstance(data, list):
        return {}  # 历史容差；不把 list 猜成任一区
    raise K1StorePayloadError(f"{STORE_ITEM_ID} 须为对象，实得 {type(data).__name__}")


def _iter_region(data: Mapping[str, Any], region: str) -> Iterator[tuple[str, Mapping[str, Any]]]:
    tables = data.get("tables")
    rows = tables.get(region) if isinstance(tables, Mapping) else None
    if rows is None:
        return
    if not isinstance(rows, list):
        raise K1StorePayloadError(f"{STORE_ITEM_ID}.tables.{region} 须为数组")
    seen: set[str] = set()
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise K1StorePayloadError(f"{STORE_ITEM_ID}.tables.{region}[{i}] 非对象")
        rid = row.get(ROW_IDENTITY_STORE_KEY)
        if not isinstance(rid, str) or not rid.strip():
            raise K1StorePayloadError(f"{STORE_ITEM_ID}.tables.{region}[{i}] 缺 id")
        rid = rid.strip()
        if rid in seen:
            raise K1StorePayloadError(f"{STORE_ITEM_ID}.tables.{region} 重复 id {rid!r}")
        seen.add(rid)
        yield rid, row


def _region_projection(data: Mapping[str, Any], region: str, spec: RowTableSheetSpec,
                       contract: SyncContract, budget: Any) -> tuple[dict[str, Any], list[str]]:
    from app.services.workpaper_sync.adapters.base import FieldValue
    from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs, stable_key_for

    values: dict[str, FieldValue] = {}
    keys: list[str] = []
    for rid, row in _iter_region(data, region):
        budget.add_row(spec.table_key)
        keys.append(rid)
        for col_key, _col, _mode, _vt, json_key, _hdr, _group in managed_field_specs(spec):
            stable = stable_key_for(spec, col_key, rid)
            field = contract.field_by_stable_key(stable_key_for(spec, col_key))
            budget.add_field()
            values[stable] = FieldValue(
                stable_key=stable, value=row.get(json_key), value_type=field.value_type,
                mode=field.mode, row_key=rid,
            )
    return values, keys


def build_store_projection(payload: Any, *, contract: SyncContract, limits: Any = None,
                           store_item_id: str = STORE_ITEM_ID) -> Any:
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    if store_item_id != STORE_ITEM_ID:
        raise StorePayloadError(f"K1-9 未登记 store item {store_item_id!r}")
    data = _parse_payload(payload)
    budget = StreamingProjectionBudget(limits or load_limits())
    rv, rk = _region_projection(data, "reversal", SPEC_REVERSAL, contract, budget)
    wv, wk = _region_projection(data, "writeoff", SPEC_WRITEOFF, contract, budget)
    return Projection(
        contract_id=contract.contract_id, semantic_version=contract.semantic_version,
        document_type=contract.document_type, values={**rv, **wv},
        row_keys={ROWS_TABLE_KEY_REVERSAL: tuple(rk), ROWS_TABLE_KEY_WRITEOFF: tuple(wk)},
    )


def merge_projection_into_k1_store(*, projection: Any,
                                   base_state: Mapping[str, Any] | None) -> tuple[dict[str, Any], int, int, set[str]]:
    from app.services.workpaper_sync.phase5_row_table_sheet import managed_field_specs

    base = dict(base_state) if isinstance(base_state, Mapping) else {}
    base_tables = base.get("tables") if isinstance(base.get("tables"), Mapping) else {}
    regions = {
        "reversal": list(base_tables.get("reversal") or []),
        "writeoff": list(base_tables.get("writeoff") or []),
    }
    maps = {
        "reversal": {x[0]: x[4] for x in managed_field_specs(SPEC_REVERSAL)},
        "writeoff": {x[0]: x[4] for x in managed_field_specs(SPEC_WRITEOFF)},
    }
    by_id: dict[str, dict[str, dict[str, Any]]] = {"reversal": {}, "writeoff": {}}
    order: dict[str, list[str]] = {"reversal": [], "writeoff": []}
    for region, rows in regions.items():
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            rid = str(row.get("id") or "").strip()
            if not rid:
                continue
            by_id[region][rid] = dict(row)
            order[region].append(rid)

    applied = visited = 0
    touched: set[str] = set()
    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        stable = str(key)
        region = next((r for r in ("reversal", "writeoff") if stable.startswith(f"{r}/")), None)
        if region is None or not getattr(fv, "row_key", None):
            continue
        rid = str(fv.row_key)
        target = by_id[region].get(rid)
        if target is None:
            target = {"id": rid}
            by_id[region][rid] = target
            order[region].append(rid)
        json_key = maps[region].get(stable.rsplit("/", 1)[-1])
        if json_key is None:
            continue
        visited += 1
        if target.get(json_key) != fv.value:
            target[json_key] = fv.value
            applied += 1
            touched.add(f"{region}:{rid}")

    merged = dict(base)
    merged_tables = dict(base_tables)
    for region in ("reversal", "writeoff"):
        merged_tables[region] = [by_id[region][rid] for rid in order[region]]
    merged["tables"] = merged_tables
    return merged, applied, visited, touched


def merge_k1_from_projection(*, projection: Any,
                             base_state: Mapping[str, Any] | None) -> tuple[dict[str, Any], int, int]:
    merged, applied, visited, _ = merge_projection_into_k1_store(
        projection=projection, base_state=base_state,
    )
    return merged, applied, visited


def merge_projection_into_store_rows(*, projection: Any, base_rows: Any,
                                     store_item_id: str = STORE_ITEM_ID):
    if store_item_id != STORE_ITEM_ID:
        raise StorePayloadError(f"K1-9 未登记 store item {store_item_id!r}")
    return merge_projection_into_k1_store(projection=projection, base_state=base_rows)


def iter_store_rows(payload: Any, *, store_item_id: str = STORE_ITEM_ID):
    if store_item_id != STORE_ITEM_ID:
        raise StorePayloadError(f"K1-9 未登记 store item {store_item_id!r}")
    data = _parse_payload(payload)
    for region in ("reversal", "writeoff"):
        yield from _iter_region(data, region)


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: Any
) -> Any:
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import observe_published_frozen_definitions
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    backend_root = Path(__file__).resolve().parents[3]
    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(session, CanonicalArtifactRepository(backend_root)),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 冻结契约 digest {observation.definitions.contract.canonical_sha256} "
            f"与 source-locked {contract.canonical_sha256} 不一致"
        )
    return observation


async def publish_definitions(publisher: Any) -> Any:
    assert_contract_file_matches_source()
    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model, payload=authority_model_payload(),
        logical_id=f"{ADAPTER_ID}.authority-model", semantic_version="1.0.0",
    )
    proxy = types.SimpleNamespace(**vars(_O))
    proxy.instrumentation_definition_payload = instrumentation_definition_payload
    proxy.assert_contract_file_matches_source = assert_contract_file_matches_source
    return await publish_with_authority(proxy, publisher, authority)


publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES

__all__ = [
    "ENTRY_ID", "ADAPTER_ID", "WP_CODES", "PILOT_WP_CODES", "STORE_ITEM_ID",
    "SPEC_REVERSAL", "SPEC_WRITEOFF", "SPECS", "instrumentation_spec",
    "instrumentation_specs", "managed_row_table_specs", "build_contract_payload",
    "build_store_projection", "merge_projection_into_k1_store", "merge_k1_from_projection",
    "publish_definitions", "publish_pilot_definitions", "attach_adapters", "attach_pilot_adapters",
]
