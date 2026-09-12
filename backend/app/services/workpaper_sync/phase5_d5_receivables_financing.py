# -*- coding: utf-8 -*-
"""D5 应收款项融资「明细表 D5-2」—— Phase 5 第五个 canary（harness 无关的独立 entry 双向路径）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Phase 5 (G5-1)

═══ 最简 canary：两级表头但**无账龄组**（FVOCI，17 列 A-Q）═══

受管 sheet = `应收款项融资明细表D5-2`（openpyxl 逐格实测）：两级表头（行 10 组标题 + 行 11 子
标题），17 列 A-Q。组标题：期初数 C:G / 本期变动 H:I / 期末数 J:P（A/B/Q 为 10-11 纵向合并
的单列）。数据区行 12-16，footer 行 17「合计」（**纯两字无空格，同 D3**，非 D7 三空格）。
四个公式列逐行：F=C+E+D（期初审定）、J=C+H-I（期末余额）、L=J+K（期末未审）、O=J+N+M（期末审定）。

🔴 与 D3/D6/D7 关键差异：**无账龄组**，每个 group 下的子列都是不同语义字段（非账龄 4 段），
故本模块无 AGING_GROUPS，只用 SCALAR_FIELD_SPECS 的 group_cell（第 6 列）标注它属于哪个组。

HTML store = `checklist_responses` 单条 item `D5-2-rows`（前端 useD5Detail.ts 的 DetailRow
整行数组 JSON.stringify）。D5-2-rows 全库 0 行（明细表从未录入，同 H1/D3/D6 空表单），空首版。
🔴 useD5Detail.DetailRow 有 19 字段，但 postRealized(R)/eclStage(S) 是**store-only**（模板无
对应列），故本模块只映射 A-Q 的 17 个字段。

wp_code 裁决 = adjudication 的 `['D5']`（载荷落点）；模块 WP_CODES = manifest 冻结的
`{'D5R'}`（宿主 GtD5ReceivablesFinancing CamelCase 幻影码，finder 零命中）。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    FieldSpec,
    SyncContract,
    contract_path_for,
    load_contract,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
from app.services.workpaper_sync.entry_profile import (
    Capability,
    DescriptorFacts,
    RoomFacts,
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
    InstrumentationError,
    build_instrumentation_payload,
    build_template_payload,
    normalized_structure_hash,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    DefinitionKind,
    SyncDomainError,
)


class EntrySelectionError(SyncDomainError):
    """冻结的 canary entry 不再满足选型必要条件。"""

    error_code = "sync_phase5_d5_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法。"""

    error_code = "sync_phase5_d5_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_receivables_financing"
ENTRY_ID: Final[str] = "xlsx/gt-d5-receivables-financing"
ADAPTER_ID: Final[str] = "d5.receivables_financing_detail"
WP_CODES: Final[frozenset[str]] = frozenset({"D5R"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D5 应收款项融资.xlsx"
TEMPLATE_SHA256: Final[str] = (
    "92c5f7f2d2d54340c29bef6094b24a9360edcfa730fcfd406aeb071d4d138ac4"
)
MANAGED_SHEET: Final[str] = "应收款项融资明细表D5-2"
TEMPLATE_ID: Final[str] = "D52"
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"
ROWS_TABLE_KEY: Final[str] = "receivables_financing_detail_rows"

#: 两级表头：组标题在行 10，子标题在行 11。
HEADER_GROUP_ROW: Final[int] = 10
HEADER_LEAF_ROW: Final[int] = 11

#: 数据区与 footer（openpyxl 逐格实测：数据 12-16，合计 17）。
FIRST_DATA_ROW: Final[int] = 12
LAST_DATA_ROW: Final[int] = 16
FOOTER_ROW: Final[int] = 17

MANAGED_LAST_COL: Final[str] = "Q"
UUID_COL: Final[str] = "R"

TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract
#: 🔴 footer A17「合计」（纯两字无空格，同 D3，非 D7 三空格）。
FOOTER_MARKER: Final[str] = "合计"

STORE_ITEM_ID: Final[str] = "D5-2-rows"
EMPTY_STORE_PAYLOAD: Final[str] = "[]"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 17 个受管字段：`(column_key, 列标, mode, value_type, store json 键, 行 11 子标题, 组标题单元格|"")`。
#: 🔴 顺序即 Excel 列序。store 键 = 前端 useD5Detail.DetailRow 的 camelCase 键。
#: F/J/L/O 四列在模板里逐行有真公式（F=C+E+D / J=C+H-I / L=J+K / O=J+N+M）⇒ formula。
#: 第 6 列 = 组标题单元格（C-G 属期初数 C10 / H-I 属本期变动 H10 / J-P 属期末数 J10；A/B/Q 空）。
#: 🔴 D5 无账龄组，group 下每个子列是不同语义字段（非 4 段账龄），故不展开账龄。
#: 🔴 useD5Detail 的 postRealized(R)/eclStage(S) 是 store-only（模板无列），不列入。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("category", "A", "editable", "enum", "category", "类别", ""),
    ("item_name", "B", "editable", "text", "itemName", "明细项目", ""),
    ("prior_unadjusted", "C", "editable", "amount", "priorUnadjusted", "未审数", "C10"),
    ("prior_aje", "D", "editable", "amount", "priorAje", "账项调整", "C10"),
    ("prior_rje", "E", "editable", "amount", "priorRje", "重分类调整", "C10"),
    ("prior_audited", "F", "formula", "amount", "priorAudited", "审定数", "C10"),
    ("oci_impairment", "G", "editable", "amount", "ociImpairment", "其他综合收益-应收款项融资减值准备余额", "C10"),
    ("period_increase", "H", "editable", "amount", "periodIncrease", "本期增加", "H10"),
    ("period_decrease", "I", "editable", "amount", "periodDecrease", "本期减少", "H10"),
    ("end_balance", "J", "formula", "amount", "endBalance", "期末余额", "J10"),
    ("entity_reclass", "K", "editable", "amount", "entityReclass", "被审计单位重分类调整", "J10"),
    ("end_unadjusted", "L", "formula", "amount", "endUnadjusted", "期末未审余额", "J10"),
    ("end_aje", "M", "editable", "amount", "endAje", "账项调整", "J10"),
    ("end_rje", "N", "editable", "amount", "endRje", "重分类调整", "J10"),
    ("end_audited", "O", "formula", "amount", "endAudited", "审定数", "J10"),
    ("end_oci_impairment", "P", "editable", "amount", "endOciImpairment", "其他综合收益-应收款项融资减值准备余额", "J10"),
    ("remark", "Q", "editable", "text", "remark", "备注", ""),
)


def _col_index(letters: str) -> int:
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx


#: 四个公式列的只读区域（F/J/L/O）。
FORMULA_MASK: Final[tuple[str, ...]] = (
    f"F{FIRST_DATA_ROW}:F{LAST_DATA_ROW}",
    f"J{FIRST_DATA_ROW}:J{LAST_DATA_ROW}",
    f"L{FIRST_DATA_ROW}:L{LAST_DATA_ROW}",
    f"O{FIRST_DATA_ROW}:O{LAST_DATA_ROW}",
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path() -> Path:
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)


def read_authoritative_template() -> bytes:
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} 实测 sha256={digest}，"
            f"冻结哨兵={TEMPLATE_SHA256} —— `backend/wp_templates/` 运行时只读（Requirement 9.9）"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise EntrySelectionError(
            f"缺少 wp_code {missing} 的 finder 实测结果 —— 零回退判据不得对未观测的码放行"
        )
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise EntrySelectionError(
            f"wp_code {sorted(leaked)} 在 `wp_template_finder` 上解析到了 {leaked} —— "
            "本 canary 的零回退判据要求它们全部解析不到任何文件"
        )
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise EntrySelectionError(
            f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
            f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 canary entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— 宿主挂载点已变"
        )
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(f"{ENTRY_ID!r} document_type 非 xlsx")
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} independent_entry={entry.get('independent_entry')!r} —— 重复入口不得注册"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} profile_id={profile_id!r} 与冻结的 {EXPECTED_PROFILE_ID!r} 不符"
        )
    codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if codes != set(WP_CODES):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} wp_code_patterns={sorted(codes)} 与冻结的 {sorted(WP_CODES)} 不一致"
        )
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. instrumentation spec 与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=TEMPLATE_ID,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=MANAGED_SHEET,
        first_data_row=FIRST_DATA_ROW,
        last_data_row=LAST_DATA_ROW,
        footer_row=FOOTER_ROW,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=UUID_COL,
        table_name=TABLE_NAME,
    )


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload(
        spec=instrumentation_spec(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload() -> dict[str, Any]:
    return {
        "schema_version": "authority-model-definition:v1",
        "authority_model": AUTHORITY_MODEL.value,
        "content_authority": "structured_projection",
        "merge_model": "stable_field_three_way",
        "required_slots": [
            BundleSlot.template.value,
            BundleSlot.instrumentation.value,
            BundleSlot.contract.value,
        ],
        "entry_id": ENTRY_ID,
        "pilot_class": PHASE5_WAVE,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. per-entry contract（与磁盘契约双向锁死）
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"


def _rows_table_payload() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, leaf_text, group_cell in MANAGED_FIELD_SPECS:
        # 有组标题的列表头指向行 11（子标题）；无组的（A/B/Q）指向行 10。
        header_row = HEADER_LEAF_ROW if group_cell else HEADER_GROUP_ROW
        spec: dict[str, Any] = {
            "stable_field_key": stable_key_for(column_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(f"{column}{header_row}"),
            "store_item_id": STORE_ITEM_ID,
            "header_text": leaf_text,
        }
        if group_cell:
            spec["group_source_ref"] = _src(group_cell)
        fields.append(spec)
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_GROUP_ROW}",
        "header_rows": 2,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
            "note": "footer 行 A17「合计」（纯两字无空格，同 D3）。声明为真使结构性插行按声明位移量扩张。",
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张应收款项融资明细表存成这一条 item 的 remark（JSON 数组字符串，useD5Detail 的 "
    "JSON.stringify(rows)）。本契约按 stable field + row rowId 拆开。🔴 无账龄组，两级表头的组"
    "（期初数/本期变动/期末数）下每个子列是不同语义字段。postRealized/eclStage 是 store-only 不入。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐 sheet 直读净化后权威模板 D/D5 应收款项融资.xlsx（外链净化后 sha256 92c5f7f2），"
    "只取受管 sheet 应收款项融资明细表D5-2：两级表头 行 10（组标题 期初数 C:G / 本期变动 H:I / "
    "期末数 J:P）/ 行 11（子标题），17 列 A-Q，数据区 12-16，F/J/L/O 四列逐行公式 =C+E+D / "
    "=C+H-I / =J+K / =J+N+M，A17「合计」footer（纯两字）；FVOCI 无账龄组；字段键与前端 "
    "useD5Detail.DetailRow 逐字段锁死（postRealized/eclStage store-only 不入）。wp_code=D5"
    "（载荷落点：D5-2-rows 全库 0 行同 H1/D3/D6 空表单，D5 wp 未删除有 file_path；非 D5R 幻影码）"
)


def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    template_payload = template_definition_payload()
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
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
                "tables": [_rows_table_payload()],
            }
        ],
        "review": {
            "entry_id": ENTRY_ID,
            "pilot_class": PHASE5_WAVE,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_id": STORE_ITEM_ID,
                "row_identity_key": ROW_IDENTITY_STORE_KEY,
                "shape": "json_array_of_row_objects",
                "note": _HTML_STORE_NOTE,
            },
            "reviewed_basis": _REVIEWED_BASIS,
        },
    }


def contract_file_path() -> Path:
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} source={canonical_digest(expected)}；"
            "请用 `& d:/GT_plan/.venv/Scripts/python.exe "
            "backend/scripts/gen/generate_phase5_d5_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷拆分（stable field + row UUID，流式；D5 无 nested）
# ═══════════════════════════════════════════════════════════════════════════


def store_row_identity(row: Mapping[str, Any], *, ordinal: int) -> str:
    raw = row.get(ROW_IDENTITY_STORE_KEY)
    if not isinstance(raw, str) or not raw.strip():
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 第 {ordinal} 行缺少稳定行身份 {ROW_IDENTITY_STORE_KEY!r}"
            f"（实得 {raw!r}）—— 不得退回数组下标作身份（Requirement 6.5 / Property 23）"
        )
    return raw.strip()


def iter_store_rows(
    payload: str | bytes | Sequence[Any],
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(f"{STORE_ITEM_ID} 的 remark 不是合法 JSON: {exc}") from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 的载荷必须是行对象数组，实得 {type(rows).__name__} —— 必须 fail closed"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 第 {ordinal} 项不是对象，实得 {type(row).__name__}"
            )
        identity = store_row_identity(row, ordinal=ordinal)
        if identity in seen:
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 出现重复行身份 {identity!r}（第 {ordinal} 项）—— 不得静默合并"
            )
        seen.add(identity)
        yield identity, row


def _resolve_json_path(row: Mapping[str, Any], json_path: str) -> Any:
    cursor: Any = row
    for segment in json_path.split("/"):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(segment)
    return cursor


def split_store_row(
    row: Mapping[str, Any], *, row_identity: str, contract: SyncContract
) -> Iterator[tuple[str, Any, FieldSpec]]:
    for column_key, _column, _mode, _vt, json_path, _leaf, _grp in MANAGED_FIELD_SPECS:
        spec = contract.field_by_stable_key(stable_key_for(column_key))
        yield stable_key_for(column_key, row_identity), _resolve_json_path(row, json_path), spec


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in iter_store_rows(payload):
        budget.add_row(ROWS_TABLE_KEY)
        row_keys.append(identity)
        for stable_key, value, spec in split_store_row(
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
        row_keys={ROWS_TABLE_KEY: tuple(row_keys)},
    )


def _set_json_path(row: dict[str, Any], json_path: str, value: Any) -> bool:
    parts = json_path.split("/")
    cursor: dict[str, Any] = row
    for seg in parts[:-1]:
        nxt = cursor.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[seg] = nxt
        cursor = nxt
    leaf = parts[-1]
    if cursor.get(leaf) != value:
        cursor[leaf] = value
        return True
    return False


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把已 extract 的 projection 合进 D5-2-rows HTML store 行（不读盘）。"""
    field_to_path = {spec[0]: spec[4] for spec in MANAGED_FIELD_SPECS}
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(ROW_IDENTITY_STORE_KEY) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    applied = 0
    visited = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {ROW_IDENTITY_STORE_KEY: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = str(key).rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if _set_json_path(target, json_path, new_val):
            applied += 1
            touched_rows.add(str(rid))

    return [by_id[rid] for rid in order], applied, visited, touched_rows


# ═══════════════════════════════════════════════════════════════════════════
# 7. 发布
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Phase5Definitions:
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    contract_definition_id: uuid.UUID
    contract_definition_sha256: str
    bundle_id: uuid.UUID
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
        raise EntrySelectionError(
            f"已发布 template digest {template.sha256} 与契约声明 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise EntrySelectionError(
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


# ═══════════════════════════════════════════════════════════════════════════
# 8. adapter 注册与宿主接线
# ═══════════════════════════════════════════════════════════════════════════


def build_matcher() -> EntryMatcher:
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
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


def register_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    registration = build_registration(
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract
    )
    registry.register(registration)
    return registration


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(
            session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} 与本模块 source-locked 的 "
            f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩"
        )
    return observation


async def attach_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = await resolve_visible_current_representation_id(session, entry_id=ENTRY_ID)
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

    resolution = CanonicalResolutionService(session, CanonicalArtifactRepository(_BACKEND_ROOT))
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）—— 不可达入口不得注册 adapter"
        )
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    register_adapter(
        registry,
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
    return (ADAPTER_ID,)


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> None:
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    )[ENTRY_ID]
    capability = capability_of(entry)
    if capability is not Capability.bidirectional:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest capability={capability.value} —— "
            "注册 bidirectional adapter 前必须先由 reviewed overlay 裁决为 bidirectional 并重生成 manifest"
        )
    if str(entry.get("adapter_id") or "") != ADAPTER_ID:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest adapter_id={entry.get('adapter_id')!r} 与本 canary 的 {ADAPTER_ID!r} 不符"
        )


def _unused_instrumentation_error_guard() -> type[InstrumentationError]:
    return InstrumentationError


# ═══════════════════════════════════════════════════════════════════════════
# 9. provisioning / attach 白名单接口别名
# ═══════════════════════════════════════════════════════════════════════════

publish_pilot_definitions = publish_definitions
attach_pilot_adapters = attach_adapters
PILOT_WP_CODES = WP_CODES
