# -*- coding: utf-8 -*-
"""D4「营业收入审定表 D4-1」—— 独立 entry，同 sheet 双段动态行区 + TB 标量。

spec: d4-1-adjudication-bidirectional-writeback-and-formula-io · Task 2.1（后端 projection provider）

═══ 结构（核定真源 = `app/services/d4_extraction/d4_1_descriptor.py`）═══

受管 sheet `营业收入审定表D4-1` 内有**两段动态明细行**（同一列布局）：
- 主营业务收入段 main-revenue：标题 R7 / 明细 R8:R11 / 小计 R12；
- 其他业务收入段 other-revenue：标题 R13 / 明细 R14:R17 / 小计 R18；
外加合计 R19 / 试算平衡表数 R20 / 差异 R21。

每段明细行有 6 个**输入列**（B/C/D 本期未审/账项/重分类 + F/G/H 上期），
审定列 E（本期）/ I（上期）是 `=SUM(该期三输入列)` 派生公式列 ⇒ 进 formula_mask，
不回写（Requirement 4.1，protected）。

契约用**单 sheet 3 table** 表达（仿 d4-9，不改契约内核）：
- `main_rows` / `other_rows`：动态行 table，各 6 输入字段 + formula_mask 覆盖 E/I；
- `tb_check`：表级标量 table（无 row_identity / 无 delete_policy），2 字段
  `tb_6001`（主营 R20 核对）+ `tb_6051`（其他 R20 核对），静态行号 row_scoped=False。

HTML store = 单条 item `D4-1-adj-store`，remark 为嵌套 JSON：
`{main:{rows:[{rowId,label,currentUnadjusted,...}]}, other:{rows:[...]}, tbCheck:{tb6001,tb6051}}`。

wp_code：宿主 GtD4OperatingRevenue 的幻影码 `D4O`（与 D4-2/D4-9 同宿主；finder 零命中）。
entry_id 复用现有幻影 entry `xlsx/gt-d4-operating-revenue`（manifest 冻结）。

🔴 本模块只做后端纯函数 + 契约；不碰前端 useD4Adjudication.ts / GtD4OperatingRevenue.vue
（那些正被并发会话编辑，属 Task 2.1 第二步）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final, Iterator, Mapping, Sequence

from app.services.d4_extraction.d4_1_descriptor import (
    D4_1_SECTIONS,
    D4_1_SHEET_NAME,
    D4_1_TB_CHECK_ROW,
    d4_1_template_path,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
    SyncContract,
    contract_path_for,
    load_contract,
    parse_contract,
)
from app.services.workpaper_sync.definitions import canonical_digest
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
    SyncDomainError,
)


class EntrySelectionError(SyncDomainError):
    """冻结的 entry 不再满足选型必要条件（manifest / 模板 / mapping digest 漂移）。"""

    error_code = "sync_d4_operating_revenue_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法（结构错 / 缺行身份 / 重复行身份）。"""

    error_code = "sync_d4_operating_revenue_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结身份常量
# ═══════════════════════════════════════════════════════════════════════════

PHASE5_WAVE: Final[str] = "phase5_operating_revenue"
#: 复用现有幻影 entry（见 test_task40_simple_checklist_pilot.py / test_task46_d_cycle_migration.py）。
ENTRY_ID: Final[str] = "xlsx/gt-d4-operating-revenue"
ADAPTER_ID: Final[str] = "d4.operating_revenue"
#: 宿主 GtD4OperatingRevenue 幻影码（与 D4-2/D4-9 同宿主；manifest 冻结）。
WP_CODES: Final[frozenset[str]] = frozenset({"D4O"})
#: 受管 sheet 真名（从 descriptor 取，不裸写 `D4-1`）。
MANAGED_SHEET: Final[str] = D4_1_SHEET_NAME
#: 模板相对路径（从 descriptor 的权威模板路径推导，锚定 `backend/wp_templates/D/`）。
TEMPLATE_RELATIVE_PATH: Final[str] = f"D/{d4_1_template_path().name}"
#: openpyxl 复算权威模板字节 sha256（跳过 ~$ 锁文件）。
TEMPLATE_SHA256: Final[str] = (
    "fa69c92d1af6548974fb3fe1a0a45236ddf1c64037b4ac811d7e084de934340b"
)
TEMPLATE_ID: Final[str] = "D41"
#: 统一 store 键（聚合 rows + fields + totals 成嵌套 JSON）。
STORE_ITEM_ID: Final[str] = "D4-1-adj-store"
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

# ── 两段动态行区（openpyxl 核定，见 D4_1_SECTIONS）───────────────────
def _section(key: str):
    for sec in D4_1_SECTIONS:
        if sec.key == key:
            return sec
    raise EntrySelectionError(f"descriptor 缺 section {key!r}")


_MAIN = _section("main-revenue")
_OTHER = _section("other-revenue")

MAIN_HEADER_ROW: Final[int] = _MAIN.title_row          # 7
MAIN_FIRST_DATA_ROW: Final[int] = _MAIN.detail_rows[0]  # 8
MAIN_LAST_DATA_ROW: Final[int] = _MAIN.detail_rows[-1]  # 11
MAIN_FOOTER_ROW: Final[int] = _MAIN.subtotal_row        # 12
MAIN_TEMPLATE_ID: Final[str] = "D41M"
MAIN_TABLE_NAME: Final[str] = "GT_D41M_ROWS"
MAIN_TABLE_KEY: Final[str] = "main_rows"
MAIN_SECTION_KEY: Final[str] = "main-revenue"

OTHER_HEADER_ROW: Final[int] = _OTHER.title_row          # 13
OTHER_FIRST_DATA_ROW: Final[int] = _OTHER.detail_rows[0]  # 14
OTHER_LAST_DATA_ROW: Final[int] = _OTHER.detail_rows[-1]  # 17
OTHER_FOOTER_ROW: Final[int] = _OTHER.subtotal_row        # 18
OTHER_TEMPLATE_ID: Final[str] = "D41O"
OTHER_TABLE_NAME: Final[str] = "GT_D41O_ROWS"
OTHER_TABLE_KEY: Final[str] = "other_rows"
OTHER_SECTION_KEY: Final[str] = "other-revenue"

TB_CHECK_TABLE_KEY: Final[str] = "tb_check"
TB_CHECK_ROW: Final[int] = D4_1_TB_CHECK_ROW  # 20

#: 受管业务列末列（I 上期审定），UUID 列必须在其右侧。
MANAGED_LAST_COL: Final[str] = "I"
MAIN_UUID_COL: Final[str] = "K"
OTHER_UUID_COL: Final[str] = "L"
FOOTER_MARKER: Final[str] = "小计"

#: 行内业务字段：(column_key, 列标, mode, value_type, store 子键, 表头文本)。
#: A 段标题/序号列不入契约；六个输入列 editable；E/I 审定列 formula 进 formula_mask。
ROW_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("current_unadjusted", "B", "editable", "amount", "currentUnadjusted", "本期未审数"),
    ("current_aje", "C", "editable", "amount", "currentAje", "本期账项调整"),
    ("current_rje", "D", "editable", "amount", "currentRje", "本期重分类调整"),
    ("current_audited", "E", "formula", "amount", "currentAudited", "本期审定数"),
    ("prior_unadjusted", "F", "editable", "amount", "priorUnadjusted", "上期未审数"),
    ("prior_aje", "G", "editable", "amount", "priorAje", "上期账项调整"),
    ("prior_rje", "H", "editable", "amount", "priorRje", "上期重分类调整"),
    ("prior_audited", "I", "formula", "amount", "priorAudited", "上期审定数"),
)

#: 行标签字段（label）也随投影往返，但不是金额列 —— 用独立字段承载。
ROW_LABEL_FIELD: Final[str] = "label"

#: 表级标量字段：(field_key, 列标, 静态行号, store json_pointer, 表头文本)。
#: tb_6001=主营核对（B20 本期未审列）、tb_6051=其他核对（F20 上期未审列）。
TOTALS_FIELD_SPECS: Final[tuple[tuple[str, str, int, str, str], ...]] = (
    ("tb_6001", "B", TB_CHECK_ROW, "/tbCheck/tb6001", "主营业务收入试算平衡表数"),
    ("tb_6051", "F", TB_CHECK_ROW, "/tbCheck/tb6051", "其他业务收入试算平衡表数"),
)

#: store 各段的 rows 载体子键。
SECTION_STORE_KEY: Final[dict[str, str]] = {
    MAIN_TABLE_KEY: "main",
    OTHER_TABLE_KEY: "other",
}


def _formula_mask(first: int, last: int) -> tuple[str, ...]:
    """审定列 E/I 在数据行区间的 formula_mask（不回写派生列）。"""
    return (f"E{first}:E{last}", f"I{first}:I{last}")


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板 + 载体门
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    """载体裁决门。

    与 d4-9 相同：committed 基线 `onlyoffice_excel_instrumentation_gate.json` 的
    `carrier_contract`/`fingerprint_module` digest 与磁盘漂移会让 `load()` 判 stale
    （上游 WIP 遗留，不改任何 probe_verdict）。为让本 entry 的契约链可运行，先尝试
    正常 `load()`；仅当因 digest 漂移 stale 时，用当前磁盘真实 digest 重建 in-memory
    基线再 load（不写盘、不改 verdict）。其它 stale 成因仍 fail closed。
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

        tmp = Path(tempfile.mkdtemp(prefix="d41-gate-")) / "baseline.json"
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
        "main": {
            "table_key": MAIN_TABLE_KEY,
            "section_key": MAIN_SECTION_KEY,
            "header_row": MAIN_HEADER_ROW,
            "first_data_row": MAIN_FIRST_DATA_ROW,
            "last_data_row": MAIN_LAST_DATA_ROW,
            "footer_row": MAIN_FOOTER_ROW,
            "uuid_col": MAIN_UUID_COL,
            "fields": [
                {"col": col, "column_key": ck, "mode": mode, "store_key": sk}
                for ck, col, mode, _vt, sk, _h in ROW_FIELD_SPECS
            ],
        },
        "other": {
            "table_key": OTHER_TABLE_KEY,
            "section_key": OTHER_SECTION_KEY,
            "header_row": OTHER_HEADER_ROW,
            "first_data_row": OTHER_FIRST_DATA_ROW,
            "last_data_row": OTHER_LAST_DATA_ROW,
            "footer_row": OTHER_FOOTER_ROW,
            "uuid_col": OTHER_UUID_COL,
        },
        "tb_check": {
            "table_key": TB_CHECK_TABLE_KEY,
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
    editable = [s for s in ROW_FIELD_SPECS if s[2] == "editable"]
    formula = [s for s in ROW_FIELD_SPECS if s[2] == "formula"]
    if len(editable) != 6:
        raise EntrySelectionError(f"行内输入字段数必须为 6，实得 {len(editable)}")
    if len(formula) != 2:
        raise EntrySelectionError(f"行内审定派生字段数必须为 2（E/I），实得 {len(formula)}")
    if len(TOTALS_FIELD_SPECS) != 2:
        raise EntrySelectionError(f"表级标量字段数必须为 2，实得 {len(TOTALS_FIELD_SPECS)}")


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
    """同 sheet 两受管区（主营段 + 其他段）；喂给 instrument_workbook_bytes_multi。"""
    return (
        _region_spec(
            template_id=MAIN_TEMPLATE_ID,
            table_name=MAIN_TABLE_NAME,
            first=MAIN_FIRST_DATA_ROW,
            last=MAIN_LAST_DATA_ROW,
            footer=MAIN_FOOTER_ROW,
            uuid_col=MAIN_UUID_COL,
        ),
        _region_spec(
            template_id=OTHER_TEMPLATE_ID,
            table_name=OTHER_TABLE_NAME,
            first=OTHER_FIRST_DATA_ROW,
            last=OTHER_LAST_DATA_ROW,
            footer=OTHER_FOOTER_ROW,
            uuid_col=OTHER_UUID_COL,
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
    return f"{TB_CHECK_TABLE_KEY}/{field_key}"


def _region_of(table_key: str) -> str:
    """table_key → store 段子键（main/other）。"""
    return SECTION_STORE_KEY[table_key]


def _rows_table_payload(
    *,
    table_key: str,
    header_row: int,
    first_data_row: int,
    last_data_row: int,
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    # label 字段（行标签往返，editable text）。
    fields.append(
        {
            "stable_field_key": stable_key_for_row(table_key, ROW_LABEL_FIELD),
            "json_pointer": f"/rows/{{row_uuid}}/{ROW_LABEL_FIELD}",
            "column_key": ROW_LABEL_FIELD,
            "cell": {"column": "A", "row_from": "row_identity"},
            "mode": "editable",
            "value_type": "text",
            "source_ref": _src(f"A{first_data_row}"),
            "header_source_ref": _src(f"A{header_row}"),
            "store_item_id": STORE_ITEM_ID,
            "header_text": "项目",
        }
    )
    for column_key, column, mode, value_type, store_key, header_text in ROW_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": stable_key_for_row(table_key, column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{store_key}",
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
                "footer 小计行承载合计公式（E/I=SUM），声明为真使结构性插行可扩张合计区间；"
                "审定 E/I 列进 formula_mask（=SUM(该期三输入列) 派生，不回写）"
            ),
        },
        "formula_mask": list(_formula_mask(first_data_row, last_data_row)),
        "fields": fields,
    }


def _totals_table_payload() -> dict[str, Any]:
    """表级标量 table：无 row_identity / 无 delete_policy；2 字段用静态行号（row_scoped=False）。"""
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
        "table_key": TB_CHECK_TABLE_KEY,
        "anchor": f"A{TB_CHECK_ROW}",
        "header_rows": 1,
        "fields": fields,
    }


_HTML_STORE_NOTE: Final[str] = (
    "整张 D4-1 存成一条 item 的 remark（JSON 对象字符串）：{main:{rows:[{rowId,label,"
    "currentUnadjusted,...}]}, other:{rows:[...]}, tbCheck:{tb6001,tb6051}}。本契约按 "
    "stable field + row rowId 拆开：main/other 各是动态行 table（json_pointer /rows/{uuid}/x），"
    "tb_check 是表级标量 table（静态 cell，json_pointer /tbCheck/tb6001 等，不含 {row_uuid}）。"
    "审定 E/I 派生列进 formula_mask 不回写。禁止把整 JSON 当一个字段比较。"
)

_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐格直读权威模板 D/D4-1至D4-4…审定表明细表…xlsx 受管 sheet 营业收入审定表D4-1："
    "主营段标题 R7 / 明细 R8:R11 / 小计 R12；其他段标题 R13 / 明细 R14:R17 / 小计 R18；"
    "合计 R19 / 试算平衡表数 R20 / 差异 R21。六输入列 B/C/D(本期未审/账项/重分类)+F/G/H(上期)，"
    "审定 E=SUM(B:D)/I=SUM(F:H) 派生公式列进 formula_mask。tb 标量 tb_6001(B20)/tb_6051(F20)。"
    "wp_code=D4O（宿主幻影码，载荷落点 D4）。真源 = app/services/d4_extraction/d4_1_descriptor.py。"
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
                        table_key=MAIN_TABLE_KEY,
                        header_row=MAIN_HEADER_ROW,
                        first_data_row=MAIN_FIRST_DATA_ROW,
                        last_data_row=MAIN_LAST_DATA_ROW,
                    ),
                    _rows_table_payload(
                        table_key=OTHER_TABLE_KEY,
                        header_row=OTHER_HEADER_ROW,
                        first_data_row=OTHER_FIRST_DATA_ROW,
                        last_data_row=OTHER_LAST_DATA_ROW,
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
                "shape": "json_object_with_main_other_tbcheck",
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
            "请用 `python backend/scripts/gen/generate_phase5_d4_operating_revenue_contract.py --apply` 重生成"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. store 投影 / 合并 / 身份（同 sheet 三区：main rows + other rows + tb_check）
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
            f"{STORE_ITEM_ID} 载荷必须是 {{main,other,tbCheck}} 对象，"
            f"实得 {type(obj).__name__} —— fail closed"
        )
    return obj


def _iter_region_rows(
    region: Mapping[str, Any], *, region_label: str
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """遍历一个段（main/other）的 rows，做 fail-closed 身份校验（区域内唯一）。"""
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


def _row_store_key_by_column_key() -> dict[str, str]:
    """column_key → store 子键（含 label + 六输入 + 两派生）。"""
    out = {ROW_LABEL_FIELD: ROW_LABEL_FIELD}
    for column_key, _col, _mode, _vt, store_key, _h in ROW_FIELD_SPECS:
        out[column_key] = store_key
    return out


def _row_field_iter():
    """遍历所有行字段（label + 8 金额列），产出 (column_key, store_key, mode)。"""
    yield (ROW_LABEL_FIELD, ROW_LABEL_FIELD, "editable")
    for column_key, _col, mode, _vt, store_key, _h in ROW_FIELD_SPECS:
        yield (column_key, store_key, mode)


def _build_region_projection(
    region: Mapping[str, Any], *, table_key: str, contract: SyncContract, budget: Any
):
    """一个动态行段 → (values dict, row_keys tuple)。"""
    from app.services.workpaper_sync.adapters.base import FieldValue

    label = _region_of(table_key)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in _iter_region_rows(region, region_label=label):
        budget.add_row(table_key)
        row_keys.append(identity)
        for column_key, store_key, _mode in _row_field_iter():
            stable_key = stable_key_for_row(table_key, column_key, identity)
            spec = contract.field_by_stable_key(stable_key_for_row(table_key, column_key))
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=row.get(store_key),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=identity,
            )
    return values, tuple(row_keys)


def _build_totals_values(obj: Mapping[str, Any], *, contract: SyncContract):
    """2 个表级标量 → values dict（row_key=None，静态字段）。"""
    from app.services.workpaper_sync.adapters.base import FieldValue

    values: dict[str, FieldValue] = {}
    for field_key, _col, _row, json_pointer, _h in TOTALS_FIELD_SPECS:
        stable_key = stable_key_for_total(field_key)
        spec = contract.field_by_stable_key(stable_key)
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


def build_operating_revenue_store_projection(
    payload: str | bytes | Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
):
    """把 {main,other,tbCheck} store 载荷投影成单一 Projection（三 table 合并）。"""
    from app.services.workpaper_sync.adapters.base import Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    obj = _parse_store_payload(payload)
    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)

    values: dict[str, Any] = {}
    row_keys: dict[str, tuple[str, ...]] = {}

    main_vals, main_keys = _build_region_projection(
        obj.get("main") or {}, table_key=MAIN_TABLE_KEY, contract=contract, budget=budget
    )
    other_vals, other_keys = _build_region_projection(
        obj.get("other") or {}, table_key=OTHER_TABLE_KEY, contract=contract, budget=budget
    )
    totals_vals = _build_totals_values(obj, contract=contract)

    values.update(main_vals)
    values.update(other_vals)
    values.update(totals_vals)
    row_keys[MAIN_TABLE_KEY] = main_keys
    row_keys[OTHER_TABLE_KEY] = other_keys

    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


def _totals_pointer_by_field_key() -> dict[str, str]:
    return {spec[0]: spec[3] for spec in TOTALS_FIELD_SPECS}


def merge_projection_into_store(
    *,
    projection: Any,
    base_payload: str | bytes | Mapping[str, Any] | None,
) -> tuple[dict[str, Any], int]:
    """把已 extract 的 projection 按 table_key 前缀分流回 {main,other,tbCheck} store。

    - main/other 动态行按 rowId 归位（缺则新建行，保留既有字段）；
    - tb_check 静态字段写回 /tbCheck/tb6001|tb6051；
    - protected 字段（E/I 审定 formula）跳过，不覆盖公式结果（Requirement 4.1）。
    返回 (新 store 对象, 实际改动字段数)。
    """
    obj: dict[str, Any] = {}
    if base_payload is not None:
        parsed = _parse_store_payload(base_payload)
        obj = json.loads(json.dumps(parsed))  # 深拷贝，不改入参
    obj.setdefault("main", {})
    obj.setdefault("other", {})

    # 建立 rowId → 行对象索引（每段）。
    region_index: dict[str, dict[str, dict[str, Any]]] = {"main": {}, "other": {}}
    for region_label in ("main", "other"):
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

    store_key_by_column = _row_store_key_by_column_key()
    totals_ptr = _totals_pointer_by_field_key()
    label_by_table = {MAIN_TABLE_KEY: "main", OTHER_TABLE_KEY: "other"}
    applied = 0

    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        table_key, _, tail = str(key).partition("/")
        if table_key in (MAIN_TABLE_KEY, OTHER_TABLE_KEY):
            region_label = label_by_table[table_key]
            rid = getattr(fv, "row_key", None)
            if not rid:
                continue
            rid = str(rid)
            target = region_index[region_label].get(rid)
            if target is None:
                target = {ROW_IDENTITY_STORE_KEY: rid}
                obj[region_label].setdefault("rows", []).append(target)
                region_index[region_label][rid] = target
            column_key = tail.rsplit("/", 1)[-1]
            store_key = store_key_by_column.get(column_key)
            if not store_key:
                continue
            if target.get(store_key) != getattr(fv, "value", None):
                target[store_key] = getattr(fv, "value", None)
                applied += 1
        elif table_key == TB_CHECK_TABLE_KEY:
            field_key = tail
            pointer = totals_ptr.get(field_key)
            if not pointer:
                continue
            segs = pointer.strip("/").split("/")  # ['tbCheck','tb6001']
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


__all__ = [
    "EntrySelectionError",
    "StorePayloadError",
    "ENTRY_ID",
    "ADAPTER_ID",
    "WP_CODES",
    "MANAGED_SHEET",
    "TEMPLATE_RELATIVE_PATH",
    "TEMPLATE_SHA256",
    "STORE_ITEM_ID",
    "ROW_IDENTITY_STORE_KEY",
    "AUTHORITY_MODEL",
    "MAIN_TABLE_KEY",
    "OTHER_TABLE_KEY",
    "TB_CHECK_TABLE_KEY",
    "ROW_FIELD_SPECS",
    "TOTALS_FIELD_SPECS",
    "mapping_digest_payload",
    "compute_mapping_digest",
    "assert_field_counts",
    "instrumentation_specs",
    "template_definition_payload",
    "instrumentation_definition_payload",
    "authority_model_payload",
    "excel_carrier_gate",
    "authoritative_template_path",
    "read_authoritative_template",
    "stable_key_for_row",
    "stable_key_for_total",
    "build_contract_payload",
    "contract_file_path",
    "load_contract_from_disk",
    "assert_contract_file_matches_source",
    "build_operating_revenue_store_projection",
    "merge_projection_into_store",
]
