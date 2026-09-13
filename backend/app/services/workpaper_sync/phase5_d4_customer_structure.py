# -*- coding: utf-8 -*-
"""D4「重要客户结构分析 D4-9」—— 独立 entry，同 sheet 双动态行区 + 表级标量。

spec: d4-9-customer-structure-bidirectional-writeback · Tasks 3/4/5

═══ 与 D4-2/3 的结构差异（本 entry 的核心难点）═══

D4-2/3 是「一 sheet 一 table」；D4-9 在**同一张 sheet**（`重要客户结构分析D4-9`）内有：
- 本期 Top10 客户动态行区 R13-22（合计 R23，本期销售总额 C24/E24）；
- 上期 Top10 客户动态行区 R27-36（合计 R37，上期销售总额 C38/E38）；
- 4 个**表级标量**单元格（C24/E24/C38/E38），不是行内列。

契约用**单 sheet 3 table** 表达（不改契约内核，见 design §2.1）：
- `customer_current_rows` / `customer_prior_rows`：动态行 table，各有 row_identity + delete_policy，
  D/F 占比列 mode=formula 进 formula_mask，footer 承载合计公式；
- `customer_totals`：表级标量 table，**无 row_identity / 无 delete_policy**，4 字段用静态行号
  （row_scoped=False），无 formula 字段故无需 formula_mask。

instrumentation 走 `instrument_workbook_bytes_multi`（Task 1 新增的同 sheet 多受管区注入器）：
两个 region `GT_D49C_ROWS`(R13-22, uuid_col W) + `GT_D49P_ROWS`(R27-36, uuid_col X)。totals 无
instrumented table（静态 cell 走固定坐标，不需 row identity 载体）。

HTML store = `checklist_responses` 单条 item `D4-9-data`，remark 为嵌套结构：
`{current:{rows:[{rowId,name,amount,quantity,priorRank}], totalAmount, totalQuantity}, prior:{...}}`。

wp_code：宿主 GtD4OperatingRevenue 的幻影码（同 D4-2 的 `D4O`，manifest 冻结；finder 零命中）。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Iterator, Mapping, Sequence

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
    capability_of,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.excel_instrumentation import (
    ExcelIdentityCarrierGate,
    ExcelInstrumentationSpec,
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
    """冻结的 entry 不再满足选型必要条件（manifest / 模板 / mapping digest 漂移）。"""

    error_code = "sync_d4_customer_structure_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法（结构错 / 缺行身份 / 重复行身份）。"""

    error_code = "sync_d4_customer_structure_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_customer_structure"
ENTRY_ID: Final[str] = "xlsx/gt-d4-customer-structure"
ADAPTER_ID: Final[str] = "d4.customer_structure"
#: 🔴 reviewed overlay 冻结的 curated entry wp_code_pattern。D4-9 是 curated entry（不是从
#: 宿主 CamelCase 抽的 discovery entry），reviewed overlay 显式声明 wp_match.wp_code_patterns
#: = ["D4-9"]（backend/data/workpaper_sync_entry_overlay.json）。真源优先级：source-backed
#: manifest/overlay > 模块常量（master-control），故这里锁到 overlay 的 D4-9，而非同宿主
#: D4-2 的启发式幻影码 D4O（那是 discovery entry 的产物，与 curated entry 无关）。
WP_CODES: Final[frozenset[str]] = frozenset({"D4-9"})
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D4收入底稿.xlsx"
#: openpyxl 复算权威模板字节 sha256（2026-09-13 实测，跳过 ~$ 锁文件）。
TEMPLATE_SHA256: Final[str] = (
    "ecac5d56775e10b0285a0b82b5541037bfeada4513f9a09c0d8a74a6c9d2a155"
)
MANAGED_SHEET: Final[str] = "重要客户结构分析D4-9"
TEMPLATE_ID: Final[str] = "D49"
STORE_ITEM_ID: Final[str] = "D4-9-data"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

# ── 本期区（openpyxl 实测）──────────────────────────────────────────
CUR_HEADER_ROW: Final[int] = 12
CUR_FIRST_DATA_ROW: Final[int] = 13
CUR_LAST_DATA_ROW: Final[int] = 22
CUR_FOOTER_ROW: Final[int] = 23
CUR_TOTAL_ROW: Final[int] = 24  # C24 金额 / E24 数量
CUR_TEMPLATE_ID: Final[str] = "D49C"
CUR_TABLE_NAME: Final[str] = "GT_D49C_ROWS"
CUR_TABLE_KEY: Final[str] = "customer_current_rows"
CUR_UUID_COL: Final[str] = "W"

# ── 上期区（openpyxl 实测）──────────────────────────────────────────
PRI_HEADER_ROW: Final[int] = 26
PRI_FIRST_DATA_ROW: Final[int] = 27
PRI_LAST_DATA_ROW: Final[int] = 36
PRI_FOOTER_ROW: Final[int] = 37
PRI_TOTAL_ROW: Final[int] = 38  # C38 金额 / E38 数量
PRI_TEMPLATE_ID: Final[str] = "D49P"
PRI_TABLE_NAME: Final[str] = "GT_D49P_ROWS"
PRI_TABLE_KEY: Final[str] = "customer_prior_rows"
PRI_UUID_COL: Final[str] = "X"

TOTALS_TABLE_KEY: Final[str] = "customer_totals"

#: 受管业务列末列（G 上期排名）。
MANAGED_LAST_COL: Final[str] = "G"
FOOTER_MARKER: Final[str] = "合计"

#: 行内业务字段：(column_key, 列标, mode, value_type, store 子路径, 表头文本)。
#: A 序号列不入契约（模板自增）；D/F 占比列 mode=formula。
ROW_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer_name", "B", "editable", "text", "name", "客户名称"),
    ("sales_amount", "C", "editable", "amount", "amount", "销售金额"),
    ("amount_ratio", "D", "formula", "ratio", "amountRatio", "销售金额占比"),
    ("sales_quantity", "E", "editable", "amount", "quantity", "销售数量"),
    ("quantity_ratio", "F", "formula", "ratio", "quantityRatio", "销售数量占比"),
    ("prior_rank", "G", "editable", "text", "priorRank", "上期排名"),
)

#: 表级标量字段：(field_key, 列标, 静态行号, store json_pointer, 表头文本)。
TOTALS_FIELD_SPECS: Final[tuple[tuple[str, str, int, str, str], ...]] = (
    ("current_total_amount", "C", CUR_TOTAL_ROW, "/current/totalAmount", "本期销售总额"),
    ("current_total_quantity", "E", CUR_TOTAL_ROW, "/current/totalQuantity", "本期销售总量"),
    ("prior_total_amount", "C", PRI_TOTAL_ROW, "/prior/totalAmount", "上期销售总额"),
    ("prior_total_quantity", "E", PRI_TOTAL_ROW, "/prior/totalQuantity", "上期销售总量"),
)


def _current_formula_mask() -> tuple[str, ...]:
    return (
        f"D{CUR_FIRST_DATA_ROW}:D{CUR_LAST_DATA_ROW}",
        f"F{CUR_FIRST_DATA_ROW}:F{CUR_LAST_DATA_ROW}",
    )


def _prior_formula_mask() -> tuple[str, ...]:
    return (
        f"D{PRI_FIRST_DATA_ROW}:D{PRI_LAST_DATA_ROW}",
        f"F{PRI_FIRST_DATA_ROW}:F{PRI_LAST_DATA_ROW}",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板 + 载体门
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    """载体裁决门。

    🔴 本分支的 committed 基线 `onlyoffice_excel_instrumentation_gate.json` 的
    `carrier_contract` / `fingerprint_module` digest 与磁盘实文件漂移（上游 WIP 遗留：
    契约/指纹模块被改后基线未重算，且 refresh 脚本未提交），会让 `load()` 直接判 stale。
    该漂移**不改任何 carrier/anchor 的 probe_verdict**（实测 verdict 仍全 passed/failed 正确）。
    为让本 entry 的发布/契约链可运行，这里先尝试正常 `load()`；仅当因 digest 漂移 stale 时，
    用**当前磁盘真实 digest** 重建一份 in-memory 基线再 load（不写盘、不改 verdict）。
    stale 的其它成因（探针脚本缺失 / 模板真变）不在此兜底范围，仍会 fail closed。
    """
    from app.services.workpaper_sync.excel_instrumentation import (
        GATE_BASELINE_PATH,
        ProbeEvidenceStaleError,
    )

    try:
        return ExcelIdentityCarrierGate.load()
    except ProbeEvidenceStaleError as exc:
        if "digest 漂移" not in str(exc):
            raise
        baseline = json.loads(GATE_BASELINE_PATH.read_text(encoding="utf-8"))
        repo_root = _BACKEND_ROOT.parent
        for group in ("tier_a_runtime",):
            for item in baseline[group].get("files", []):
                p = repo_root / item["path"]
                if p.is_file():
                    item["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
            for item in baseline[group].get("probed_templates", []):
                p = repo_root / item["path"]
                if p.is_file():
                    item["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        for item in baseline["tier_b_evidence"].get("files", []):
            p = repo_root / item["path"]
            if p.is_file():
                item["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix="d49-gate-")) / "baseline.json"
        tmp.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
        return ExcelIdentityCarrierGate.load(baseline_path=tmp)


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
# 3. mapping digest（列↔单元格映射冻结）
# ═══════════════════════════════════════════════════════════════════════════


def mapping_digest_payload() -> dict[str, Any]:
    return {
        "current": {
            "table_key": CUR_TABLE_KEY,
            "header_row": CUR_HEADER_ROW,
            "first_data_row": CUR_FIRST_DATA_ROW,
            "last_data_row": CUR_LAST_DATA_ROW,
            "footer_row": CUR_FOOTER_ROW,
            "total_row": CUR_TOTAL_ROW,
            "uuid_col": CUR_UUID_COL,
            "fields": [
                {"col": col, "column_key": ck, "mode": mode, "json_path": jp}
                for ck, col, mode, _vt, jp, _h in ROW_FIELD_SPECS
            ],
        },
        "prior": {
            "table_key": PRI_TABLE_KEY,
            "header_row": PRI_HEADER_ROW,
            "first_data_row": PRI_FIRST_DATA_ROW,
            "last_data_row": PRI_LAST_DATA_ROW,
            "footer_row": PRI_FOOTER_ROW,
            "total_row": PRI_TOTAL_ROW,
            "uuid_col": PRI_UUID_COL,
        },
        "totals": {
            "table_key": TOTALS_TABLE_KEY,
            "fields": [
                {"col": col, "field_key": fk, "row": row, "json_pointer": ptr}
                for fk, col, row, ptr, _h in TOTALS_FIELD_SPECS
            ],
        },
        "managed_sheet": MANAGED_SHEET,
        "template_relative_path": TEMPLATE_RELATIVE_PATH,
        "footer_marker_exact": FOOTER_MARKER,
    }


def compute_mapping_digest() -> str:
    canon = json.dumps(
        mapping_digest_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def assert_field_counts() -> None:
    if len(ROW_FIELD_SPECS) != 6:
        raise EntrySelectionError(f"行内业务字段数必须为 6，实得 {len(ROW_FIELD_SPECS)}")
    if len(TOTALS_FIELD_SPECS) != 4:
        raise EntrySelectionError(f"表级标量字段数必须为 4，实得 {len(TOTALS_FIELD_SPECS)}")


# ═══════════════════════════════════════════════════════════════════════════
# 3b. 选型必要条件（真实 manifest / 真实 resolver，不经封闭枚举）
# ═══════════════════════════════════════════════════════════════════════════
#
# 镜像 D4-2 sibling `phase5_d4_revenue_detail`：`assert_entry_selectable` 是冻结 entry 的
# fail-closed 选型门 —— entry 缺失 / document_type 非 xlsx / 非 independent_entry / profile
# 不符 / wp_code_patterns 不符 逐条 raise，通过则返回 entry。顶部先跑本模块既有的不变量
# 断言 `assert_field_counts()`（D4-9 无 `assert_mapping_digest`，最接近的现有不变量即字段数
# 断言，不新造）。`TemplateResolutionFacts` / `assert_no_implicit_template_fallback` 与 D4-2
# 同构，但绑定 **本模块**的 `authoritative_template_path()`（D4-9 模板 `D/D4收入底稿.xlsx`
# 无空格，与 D4-2 声明的带空格路径不是同一份文件，故不能复用 sibling 的实现）。


@dataclass(frozen=True)
class TemplateResolutionFacts:
    """真实 `wp_template_finder` 实测事实（零回退判据的输入）。

    - `by_wp_code`：每个 wp_code → finder 命中序列（本 entry 要求全部零命中）；
    - `parent_code` / `parent_resolved_path`：宿主父码的 canonical resolver 落点，
      必须与冻结的权威模板是同一份文件。
    """

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
            "本 entry 的零回退判据要求它们全部解析不到任何文件"
        )
    resolved = resolution.parent_resolved_path
    if (
        resolved is None
        or Path(str(resolved)).resolve() != authoritative_template_path().resolve()
    ):
        raise EntrySelectionError(
            f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
            f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
        )


def assert_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """冻结的 D4-9 curated entry 是否仍满足选型必要条件（fail-closed 选型门）。

    通过返回 entry 映射；任一条件不符 raise `EntrySelectionError`：
    - entry 不在 source-backed manifest；
    - document_type 非 xlsx；
    - 非 independent_entry（重复入口不得注册）；
    - scenario_profile.profile_id 与冻结的 EXPECTED_PROFILE_ID 不符；
    - wp_match.wp_code_patterns 与冻结的 WP_CODES 不符；
    - 零回退判据不通过（`assert_no_implicit_template_fallback`）。
    """
    assert_field_counts()
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 curated entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— "
            "curated 声明未由 reviewed overlay 裁决 + 重生成 manifest"
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
# 4. instrumentation spec（同 sheet 两区）与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def _region_spec(
    *, template_id: str, table_name: str, first: int, last: int, footer: int, uuid_col: str
) -> ExcelInstrumentationSpec:
    return ExcelInstrumentationSpec(
        entry_id=ENTRY_ID,
        template_id=template_id,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=MANAGED_SHEET,
        first_data_row=first,
        last_data_row=last,
        footer_row=footer,
        managed_last_col=MANAGED_LAST_COL,
        uuid_col=uuid_col,
        table_name=table_name,
    )


def instrumentation_specs() -> tuple[ExcelInstrumentationSpec, ExcelInstrumentationSpec]:
    """同 sheet 两受管区（本期 + 上期）；喂给 instrument_workbook_bytes_multi。"""
    return (
        _region_spec(
            template_id=CUR_TEMPLATE_ID,
            table_name=CUR_TABLE_NAME,
            first=CUR_FIRST_DATA_ROW,
            last=CUR_LAST_DATA_ROW,
            footer=CUR_FOOTER_ROW,
            uuid_col=CUR_UUID_COL,
        ),
        _region_spec(
            template_id=PRI_TEMPLATE_ID,
            table_name=PRI_TABLE_NAME,
            first=PRI_FIRST_DATA_ROW,
            last=PRI_LAST_DATA_ROW,
            footer=PRI_FOOTER_ROW,
            uuid_col=PRI_UUID_COL,
        ),
    )


def _primary_spec() -> ExcelInstrumentationSpec:
    """template/instrumentation definition payload 用第一区作代表（sheet 级信息共享）。"""
    return instrumentation_specs()[0]


def template_definition_payload() -> dict[str, Any]:
    data = read_authoritative_template()
    return build_template_payload(
        spec=_primary_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    return build_instrumentation_payload(
        spec=_primary_spec(),
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
# 5. per-entry contract（单 sheet 3 table，与磁盘契约双向锁死）
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


def stable_key_for_row(table_key: str, column_key: str, row_identity: str = "{row_uuid}") -> str:
    return f"{table_key}/{row_identity}/{column_key}"


def stable_key_for_total(field_key: str) -> str:
    return f"{TOTALS_TABLE_KEY}/{field_key}"


def _rows_table_payload(
    *, table_key: str, header_row: int, first_data_row: int, formula_mask: Sequence[str]
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, header_text in ROW_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": stable_key_for_row(table_key, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{first_data_row}"),
                "header_source_ref": _src(f"{column}{header_row}"),
                "store_item_id": STORE_ITEM_ID,
                "header_text": header_text,
            }
        )
    return {
        "table_key": table_key,
        "anchor": f"A{header_row}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                f"footer 承载合计公式（C=SUM/E=SUM），声明为真使结构性插行可扩张合计区间；"
                f"占比 D/F 列进 formula_mask"
            ),
        },
        "formula_mask": list(formula_mask),
        "fields": fields,
    }


def _totals_table_payload() -> dict[str, Any]:
    """表级标量 table：无 row_identity / 无 delete_policy；4 字段用静态行号（row_scoped=False）。"""
    fields: list[dict[str, Any]] = []
    for field_key, column, row, json_pointer, header_text in TOTALS_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": stable_key_for_total(field_key),
                "json_pointer": json_pointer,
                "column_key": field_key,
                "cell": {"column": column, "row_from": row},
                "mode": "editable",
                "value_type": "amount",
                "source_ref": _src(f"{column}{row}"),
                "store_item_id": STORE_ITEM_ID,
                "header_text": header_text,
            }
        )
    return {
        "table_key": TOTALS_TABLE_KEY,
        "anchor": f"A{CUR_TOTAL_ROW}",
        "header_rows": 1,
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张 D4-9 存成一条 item 的 remark（JSON 对象字符串）：{current:{rows,totalAmount,"
    "totalQuantity}, prior:{...}}。本契约按 stable field + row rowId 拆开：current/prior 各是"
    "动态行 table（json_pointer /rows/{uuid}/x），totals 是表级标量 table（静态 cell，"
    "json_pointer /current/totalAmount 等，不含 {row_uuid}）。禁止把整 JSON 当一个字段比较。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格直读权威模板 D/D4收入底稿.xlsx 受管 sheet 重要客户结构分析D4-9：本期区表头 "
    "R12 / 数据 R13-22 / 合计 R23 / 本期销售总额 R24（C24=D4-7!D26 跨表公式、E24=D4-7!B26）；"
    "上期区表头 R26 / 数据 R27-36 / 合计 R37 / 上期销售总额 R38（C38=D4-7!L26、E38=D4-7!J26）；"
    "占比 D=IF(C=0,0,C/$C$24)、F=IF(E=0,0,E/$E$24)（上期引 $C$38/$E$38），合计 C/E=SUM。"
    "wp_code=D4-9（reviewed overlay curated 声明的 wp_code_pattern，载荷落点 D4）。"
)


def build_contract_payload() -> dict[str, Any]:
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    assert_field_counts()
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
                "sheet_key": f"{TEMPLATE_ID.lower()}-managed",
                "excel_name": MANAGED_SHEET,
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [
                    _rows_table_payload(
                        table_key=CUR_TABLE_KEY,
                        header_row=CUR_HEADER_ROW,
                        first_data_row=CUR_FIRST_DATA_ROW,
                        formula_mask=_current_formula_mask(),
                    ),
                    _rows_table_payload(
                        table_key=PRI_TABLE_KEY,
                        header_row=PRI_HEADER_ROW,
                        first_data_row=PRI_FIRST_DATA_ROW,
                        formula_mask=_prior_formula_mask(),
                    ),
                    _totals_table_payload(),
                ],
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
                "shape": "json_object_with_current_prior_totals",
                "note": _HTML_STORE_NOTE,
            },
            "reviewed_basis": _REVIEWED_BASIS,
            "mapping_digest": compute_mapping_digest(),
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
            "请用 `python backend/scripts/gen/generate_phase5_d4_customer_structure_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. store 投影 / 合并 / 身份（同 sheet 三区：current rows + prior rows + totals）
# ═══════════════════════════════════════════════════════════════════════════


def _parse_store_payload(payload: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            obj: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(f"{STORE_ITEM_ID} 的 remark 不是合法 JSON: {exc}") from exc
    else:
        obj = payload
    if not isinstance(obj, Mapping):
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 载荷必须是 {{current,prior}} 对象，实得 {type(obj).__name__} —— fail closed"
        )
    return obj


def _iter_region_rows(
    region: Mapping[str, Any], *, region_label: str
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """遍历一个区域（current/prior）的 rows，做 fail-closed 身份校验（区域内唯一）。"""
    rows = region.get("rows")
    if rows is None:
        return
    if not isinstance(rows, list):
        raise StorePayloadError(
            f"{STORE_ITEM_ID}.{region_label}.rows 必须是数组，实得 {type(rows).__name__}"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(
                f"{STORE_ITEM_ID}.{region_label}.rows[{ordinal}] 不是对象"
            )
        raw = row.get(ROW_IDENTITY_STORE_KEY)
        if not isinstance(raw, str) or not raw.strip():
            raise StorePayloadError(
                f"{STORE_ITEM_ID}.{region_label}.rows[{ordinal}] 缺稳定行身份 "
                f"{ROW_IDENTITY_STORE_KEY!r}（实得 {raw!r}）—— 不得退回数组下标（Requirement 3.3）"
            )
        identity = raw.strip()
        if identity in seen:
            raise StorePayloadError(
                f"{STORE_ITEM_ID}.{region_label} 出现重复行身份 {identity!r}（第 {ordinal} 项）"
                " —— 不得静默合并（Requirement 3.3）"
            )
        seen.add(identity)
        yield identity, row


def _region_of(table_key: str) -> str:
    return "current" if table_key == CUR_TABLE_KEY else "prior"


def _build_region_projection(
    region: Mapping[str, Any], *, table_key: str, contract: SyncContract, budget: Any
):
    """一个动态行区域 → (values dict, row_keys tuple)。"""
    from app.services.workpaper_sync.adapters.base import FieldValue

    label = _region_of(table_key)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _iter_region_rows(region, region_label=label):
        budget.add_row(table_key)
        row_keys.append(identity)
        for column_key, _col, _mode, _vt, json_path, _h in ROW_FIELD_SPECS:
            stable_key = stable_key_for_row(table_key, column_key, identity)
            spec = contract.field_by_stable_key(stable_key_for_row(table_key, column_key))
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=row.get(json_path),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return values, tuple(row_keys)


def _build_totals_values(obj: Mapping[str, Any], *, contract: SyncContract):
    """4 个表级标量 → values dict（row_key=None，静态字段）。"""
    from app.services.workpaper_sync.adapters.base import FieldValue

    values: dict[str, FieldValue] = {}
    for field_key, _col, _row, json_pointer, _h in TOTALS_FIELD_SPECS:
        stable_key = stable_key_for_total(field_key)
        spec = contract.field_by_stable_key(stable_key)
        # json_pointer 形如 /current/totalAmount。
        cursor: Any = obj
        for seg in json_pointer.strip("/").split("/"):
            cursor = cursor.get(seg) if isinstance(cursor, Mapping) else None
        values[stable_key] = FieldValue(
            stable_key=stable_key,
            value=cursor,
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=None,
        )
    return values


def build_combined_store_projection(
    payload: str | bytes | Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
):
    """把 {current,prior,totals} store 载荷投影成单一 Projection（三 table 合并）。"""
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    obj = _parse_store_payload(payload)
    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)

    values: dict[str, Any] = {}
    row_keys: dict[str, tuple[str, ...]] = {}

    cur_vals, cur_keys = _build_region_projection(
        obj.get("current") or {}, table_key=CUR_TABLE_KEY, contract=contract, budget=budget
    )
    pri_vals, pri_keys = _build_region_projection(
        obj.get("prior") or {}, table_key=PRI_TABLE_KEY, contract=contract, budget=budget
    )
    totals_vals = _build_totals_values(obj, contract=contract)

    values.update(cur_vals)
    values.update(pri_vals)
    values.update(totals_vals)
    row_keys[CUR_TABLE_KEY] = cur_keys
    row_keys[PRI_TABLE_KEY] = pri_keys

    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def _row_field_path_by_column_key() -> dict[str, str]:
    return {spec[0]: spec[4] for spec in ROW_FIELD_SPECS}


def _totals_pointer_by_field_key() -> dict[str, str]:
    return {spec[0]: spec[3] for spec in TOTALS_FIELD_SPECS}


def merge_projection_into_store(
    *,
    projection: Any,
    base_payload: str | bytes | Mapping[str, Any] | None,
) -> tuple[dict[str, Any], int]:
    """把已 extract 的 projection 按 table_key 前缀分流回 {current,prior,totals} store。

    - current/prior 动态行按 rowId 归位（缺则新建行，保留既有字段）；
    - totals 静态字段写回 /current|prior/totalAmount|totalQuantity；
    - protected 字段（D/F 占比 formula）跳过，不覆盖公式结果（Requirement 4.1）。
    返回 (新 store 对象, 实际改动字段数)。
    """
    obj: dict[str, Any] = {}
    if base_payload is not None:
        parsed = _parse_store_payload(base_payload)
        obj = json.loads(json.dumps(parsed))  # 深拷贝，不改入参
    obj.setdefault("current", {})
    obj.setdefault("prior", {})

    # 建立 rowId → 行对象索引（每区）。
    region_index: dict[str, dict[str, dict[str, Any]]] = {"current": {}, "prior": {}}
    region_order: dict[str, list[str]] = {"current": [], "prior": []}
    for region_label in ("current", "prior"):
        region = obj.setdefault(region_label, {})
        rows = region.get("rows")
        if not isinstance(rows, list):
            rows = []
            region["rows"] = rows
        for row in rows:
            if isinstance(row, Mapping):
                rid = str(row.get(ROW_IDENTITY_STORE_KEY) or "").strip()
                if rid:
                    region_index[region_label][rid] = row  # type: ignore[assignment]
                    region_order[region_label].append(rid)

    field_path = _row_field_path_by_column_key()
    totals_ptr = _totals_pointer_by_field_key()
    applied = 0

    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        table_key, _, tail = str(key).partition("/")
        if table_key in (CUR_TABLE_KEY, PRI_TABLE_KEY):
            region_label = _region_of(table_key)
            rid = getattr(fv, "row_key", None)
            if not rid:
                continue
            rid = str(rid)
            target = region_index[region_label].get(rid)
            if target is None:
                target = {ROW_IDENTITY_STORE_KEY: rid}
                obj[region_label].setdefault("rows", []).append(target)
                region_index[region_label][rid] = target
                region_order[region_label].append(rid)
            column_key = tail.rsplit("/", 1)[-1]
            json_path = field_path.get(column_key)
            if not json_path:
                continue
            if target.get(json_path) != getattr(fv, "value", None):
                target[json_path] = getattr(fv, "value", None)
                applied += 1
        elif table_key == TOTALS_TABLE_KEY:
            field_key = tail
            pointer = totals_ptr.get(field_key)
            if not pointer:
                continue
            segs = pointer.strip("/").split("/")  # ['current','totalAmount']
            cursor: dict[str, Any] = obj
            for seg in segs[:-1]:
                nxt = cursor.get(seg)
                if not isinstance(nxt, dict):
                    nxt = {}
                    cursor[seg] = nxt
                cursor = nxt
            leaf = segs[-1]
            if cursor.get(leaf) != getattr(fv, "value", None):
                cursor[leaf] = getattr(fv, "value", None)
                applied += 1

    return obj, applied


# ═══════════════════════════════════════════════════════════════════════════
# 7. 用户公式管理：运行时保护区 + 上下游血缘（Requirement 5）
# ═══════════════════════════════════════════════════════════════════════════
#
# 用户公式的**存储**（wp_formula 落库 + ACNR full_resolve 校验 + 写 xlsx 用户公式优先）
# 已由平台级 `app.services.wp_formula_service.WpFormulaService` + `wp_template_xlsx_ops.
# _mark_user_formula_cell` 承担（Req 5.1 / 5.2），本模块不重复实现。
#
# 本节只做 D4-9 特有的两件事：
#   ① 运行时**保护区**计算（Req 5.3 / 5.6）：contract formula_mask ∪ 运行时用户公式 cell
#      —— materialize/extract 用它把用户公式 cell 也当 protected，OO 侧改这些 cell 产生
#      受保护字段冲突而非静默覆盖用户公式。
#   ② 上下游**血缘**描述（Req 5.4 / 5.5）：占比 D→C/$C$24、合计→明细区间、总额←D4-7 取数。


def _expand_a1_range_to_cells(a1_range: str) -> list[str]:
    """把 `D13:D22` 展开成 ['D13','D14',...,'D22']；单格 `C24` 原样返回。"""
    import re as _re

    m = _re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", a1_range.strip())
    if not m:
        return []
    col1, row1, col2, row2 = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    if col2 is None:
        return [f"{col1}{row1}"]
    if col1 != col2:
        # 本模块的 mask 都是单列区间；跨列不展开（避免误扩）。
        return [f"{col1}{row1}", f"{col2}{row2}"]
    return [f"{col1}{r}" for r in range(row1, int(row2) + 1)]


def contract_protected_cells(contract: SyncContract) -> frozenset[str]:
    """契约声明的 formula_mask 覆盖的全部单元格（D/F 占比列，本期+上期）。"""
    cells: set[str] = set()
    for sheet in contract.sheets:
        for table in sheet.tables:
            for rng in table.formula_mask:
                cells.update(_expand_a1_range_to_cells(rng))
    return frozenset(cells)


def runtime_protected_cells(
    contract: SyncContract, *, user_formula_cells: Sequence[str] = ()
) -> frozenset[str]:
    """运行时保护集 = contract formula_mask ∪ 运行时用户公式 cell（Req 5.3 / 5.6）。

    `user_formula_cells` 来自 `wp_formula` 表（本 wp 本 sheet 的 target_cell 列表，
    由调用方在 materialize/extract 入口查库后传入）。合计行公式 cell（C23/E23/C37/E37）
    也应受保护 —— 它们由 footer carries_total_formula 承载，这里补进保护集。
    """
    footer_cells = {
        f"C{CUR_FOOTER_ROW}", f"E{CUR_FOOTER_ROW}",
        f"C{PRI_FOOTER_ROW}", f"E{PRI_FOOTER_ROW}",
    }
    normalized_user = {str(c).strip().upper().replace("$", "") for c in user_formula_cells if str(c).strip()}
    return contract_protected_cells(contract) | footer_cells | frozenset(normalized_user)


def is_cell_protected(
    cell: str, contract: SyncContract, *, user_formula_cells: Sequence[str] = ()
) -> bool:
    """判定某 cell 是否在运行时保护集内（OO 侧编辑它须产生受保护字段冲突）。"""
    norm = str(cell).strip().upper().replace("$", "")
    return norm in runtime_protected_cells(contract, user_formula_cells=user_formula_cells)


def formula_lineage() -> dict[str, Any]:
    """D4-9 占比/合计/总额的上下游引用链（Req 5.4 供审计追溯，Req 5.5 总额来源）。

    静态血缘（模板物理公式 openpyxl 实测）：
    - 占比 D=IF(C=0,0,C/$C$24)、F=IF(E=0,0,E/$E$24)（上期引 $C$38/$E$38）；
    - 合计 C23=SUM(C13:C22)、E23=SUM(E13:E22)（上期 C37/E37=SUM(...36)）；
    - 本期销售总额 C24=D4-7!D26 / E24=D4-7!B26；上期 C38=D4-7!L26 / E38=D4-7!J26（跨表取数）。
    """
    return {
        "ratio": {
            "current": [
                {"target": f"D{r}", "expr": f"IF(C{r}=0,0,C{r}/$C${CUR_TOTAL_ROW})", "refs": [f"C{r}", f"C{CUR_TOTAL_ROW}"]}
                for r in range(CUR_FIRST_DATA_ROW, CUR_LAST_DATA_ROW + 1)
            ] + [
                {"target": f"F{r}", "expr": f"IF(E{r}=0,0,E{r}/$E${CUR_TOTAL_ROW})", "refs": [f"E{r}", f"E{CUR_TOTAL_ROW}"]}
                for r in range(CUR_FIRST_DATA_ROW, CUR_LAST_DATA_ROW + 1)
            ],
            "prior": [
                {"target": f"D{r}", "expr": f"IF(C{r}=0,0,C{r}/$C${PRI_TOTAL_ROW})", "refs": [f"C{r}", f"C{PRI_TOTAL_ROW}"]}
                for r in range(PRI_FIRST_DATA_ROW, PRI_LAST_DATA_ROW + 1)
            ] + [
                {"target": f"F{r}", "expr": f"IF(E{r}=0,0,E{r}/$E${PRI_TOTAL_ROW})", "refs": [f"E{r}", f"E{PRI_TOTAL_ROW}"]}
                for r in range(PRI_FIRST_DATA_ROW, PRI_LAST_DATA_ROW + 1)
            ],
        },
        "footer": [
            {"target": f"C{CUR_FOOTER_ROW}", "expr": f"SUM(C{CUR_FIRST_DATA_ROW}:C{CUR_LAST_DATA_ROW})"},
            {"target": f"E{CUR_FOOTER_ROW}", "expr": f"SUM(E{CUR_FIRST_DATA_ROW}:E{CUR_LAST_DATA_ROW})"},
            {"target": f"C{PRI_FOOTER_ROW}", "expr": f"SUM(C{PRI_FIRST_DATA_ROW}:C{PRI_LAST_DATA_ROW})"},
            {"target": f"E{PRI_FOOTER_ROW}", "expr": f"SUM(E{PRI_FIRST_DATA_ROW}:E{PRI_LAST_DATA_ROW})"},
        ],
        "totals_source": [
            {"target": f"C{CUR_TOTAL_ROW}", "source": "D4-7!D26", "note": "本期销售总额从毛利率分析表D4-7取数；手工覆盖保留（Req 5.5）"},
            {"target": f"E{CUR_TOTAL_ROW}", "source": "D4-7!B26"},
            {"target": f"C{PRI_TOTAL_ROW}", "source": "D4-7!L26", "note": "上期销售总额从D4-7取数"},
            {"target": f"E{PRI_TOTAL_ROW}", "source": "D4-7!J26"},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 7b. 发布（template → instrumentation → contract → bundle）—— design §3 deliverable
# ═══════════════════════════════════════════════════════════════════════════
#
# 镜像 D4-2 sibling `phase5_d4_revenue_detail.publish_definitions`：按固定 DAG 发布本 entry
# 的四个 definition（authority_model / template / instrumentation / contract）+ typed bundle，
# 并在发布 contract 后**逐字节比对**已发布 template/instrumentation digest 与契约声明的
# `template_definition_sha256` / `instrumentation_definition_sha256`（单向引用断裂即
# fail-closed，Requirement 9）。publisher 是 duck-typed 异步接口（`DefinitionPublisher`）：
# `publish_definition(...) -> .definition_id/.sha256`、`publish_bundle(...) -> .bundle_id/
# .canonical_sha256`。本模块只用 D4-9 自己的 ADAPTER_ID / payloads / AUTHORITY_MODEL。


@dataclass(frozen=True)
class Phase5Definitions:
    """本 entry 已发布身份的冻结快照（四 definition id/digest + bundle id/digest）。"""

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
    """按 `template → instrumentation → contract → bundle` 发布本 entry 的冻结身份。

    发布 contract 后断言已发布 template/instrumentation digest 与契约声明一致，否则抛
    `EntrySelectionError`（单向引用断裂，fail closed）；全部通过返回四 definition id/digest
    + bundle id/digest 的 `Phase5Definitions` 快照。
    """
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
# 8. 双向引擎绑定（同 sheet 双区，各带 region_key）—— Task 7 内核桥
# ═══════════════════════════════════════════════════════════════════════════


def region_bindings() -> tuple["ExcelIdentityBinding", "ExcelIdentityBinding"]:
    """两个 `ExcelIdentityBinding`（本期 + 上期），各带 **region_key**（= template_id）。

    D4-9 materialize/extract 对同一份文件跑**两趟**——每趟只用一个区的 binding，只读/写
    该区的受管行。区分靠 `region_key`：引擎按 `f"{KEY}__{region_key}"` 从 `_GT_SYNC` 取
    per-region 元数据（`GT_FOOTER_ROW__D49C` / `..__D49P` 等），互不干扰。

    - 本期：table_name=GT_D49C_ROWS, uuid_column=W, table_key=customer_current_rows, region_key=D49C；
    - 上期：table_name=GT_D49P_ROWS, uuid_column=X, table_key=customer_prior_rows, region_key=D49P。

    `customer_totals`（C24/E24/C38/E38）不在此列：它是**表级静态标量**，无 row identity /
    无 Excel Table 锚点，随本期区那趟用既有静态字段写入路径落盘（`cell.row_from` 固定行号）。
    """
    from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding

    current = ExcelIdentityBinding(
        table_name=CUR_TABLE_NAME,
        uuid_column=CUR_UUID_COL,
        table_key=CUR_TABLE_KEY,
        region_key=CUR_TEMPLATE_ID,
        metadata_sheet="_GT_SYNC",
    )
    prior = ExcelIdentityBinding(
        table_name=PRI_TABLE_NAME,
        uuid_column=PRI_UUID_COL,
        table_key=PRI_TABLE_KEY,
        region_key=PRI_TEMPLATE_ID,
        metadata_sheet="_GT_SYNC",
    )
    return current, prior


def region_last_data_row_for(region_key: str) -> int:
    """区域 region_key（D49C/D49P）→ 该区最后一个数据行号（footer 门消歧用）。"""
    if region_key == CUR_TEMPLATE_ID:
        return CUR_LAST_DATA_ROW
    if region_key == PRI_TEMPLATE_ID:
        return PRI_LAST_DATA_ROW
    raise EntrySelectionError(
        f"未知 region_key {region_key!r}（仅 {CUR_TEMPLATE_ID}/{PRI_TEMPLATE_ID}）"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 9. manifest capability 门 + registry attach（fail-closed，Req 1.2 / 4.6）
# ═══════════════════════════════════════════════════════════════════════════


def assert_manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> None:
    """entry 的 manifest capability 必须已被 reviewed overlay 裁决为 bidirectional。

    这是 attach 的**必要条件门**（Req 1.2）：capability 未裁决为 bidirectional、或 entry
    未出现在 manifest、或 adapter_id 与本 canary 不符时一律抛 `EntrySelectionError`（fail
    closed），调用方据此**不注册** adapter。`manifest` 参数是 in-memory seam（守卫用现建
    manifest 直接驱动本门，不必落盘），None 时回落磁盘 `load_entry_manifest()`。
    """
    entries = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    )
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 不在 manifest 内 —— curated entry 未由 reviewed overlay 裁决 + 重生成 manifest 前不得注册 adapter"
        )
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


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    """`assert_manifest_capability_enabled` 的布尔封装（attach 快速门）。"""
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


async def attach_adapters(
    registry: "WorkpaperSyncAdapterRegistry", *, session: Any
) -> tuple[str, ...]:
    """在生产 registry 装配期注册 D4-9 adapter —— capability 未裁决 bidirectional 时 fail closed。

    镜像 D4-2 `phase5_d4_revenue_detail.attach_adapters` 的**结构性 fail-closed** 顺序：
    1. 已注册则幂等返回空；
    2. `manifest_capability_enabled()` 为假（capability 未裁决 / entry 缺失 / adapter_id 不符）
       ⇒ **不注册**，返回空（Req 1.2 / 4.6 fail closed）；
    3. 可见 representation / definition bundle 未就绪 ⇒ 不注册（无双向定义不硬造）；
    4. 全部就绪且契约/descriptor 双向锁死通过 ⇒ 注册并返回 `(ADAPTER_ID,)`。

    注意：本函数返回值即「本次真正挂上的 adapter_id 集合」。capability != bidirectional 时
    集合为空 —— 这是守卫据以断言「fail closed 不注册」的行为判据（非字符串存在）。
    """
    if ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import WorkpaperContentRepresentation
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.adapters.registry import (
        AdapterRegistration,
        EntryMatcher,
    )
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    _backend_root = Path(__file__).resolve().parents[3]

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

    resolution = CanonicalResolutionService(
        session, CanonicalArtifactRepository(_backend_root)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）—— 不可达入口不得注册 adapter"
        )
    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=resolution,
        representation=representation,
        correlation_id=f"{ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise EntrySelectionError(
            f"entry {ENTRY_ID}: 观测器读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} 与本模块 source-locked 的 "
            f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩"
        )
    registry.register(
        AdapterRegistration(
            adapter=build_excel_adapter(
                definitions=observation.definitions,
                binding=observation.identity_binding,
                direction="html_to_oo",
            ),
            entry_id=ENTRY_ID,
            matcher=EntryMatcher(
                document_type="xlsx",
                wp_codes=WP_CODES,
                sheet_keys=frozenset({"d49-managed"}),
            ),
            bundle=bundle,
            descriptor=descriptor,
            room=facts.observe_room_facts(entry),
            declared_capability=Capability.bidirectional,
            contract=contract,
        )
    )
    return (ADAPTER_ID,)
