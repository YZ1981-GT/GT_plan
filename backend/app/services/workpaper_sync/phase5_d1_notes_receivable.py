# -*- coding: utf-8 -*-
"""D1 应收票据「按客户」明细 —— Phase 5 首个 canary（harness 无关的独立 entry 双向路径）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Phase 5 (G5-1)
主控: docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md §Phase 5

═══ 为什么本模块不是「第五个 pilot」 ═══

Phase 4 的四个 pilot（B60/D2/H1/G7）是 :class:`pilot_harness.PilotClass` **封闭枚举**的
四个代表，`assess_pilot_classes()` 用 entry_id 正则把每个 xlsx entry 归到唯一一类
（源码原话「封闭枚举——再加一类不能让分母变松」）。`xlsx/gt-d1-notes-receivable` 的
entry_id 不含 d2/h1/g7 ⇒ 会被归进 catch-all 的 `simple_checklist`，而那一类的唯一
冻结候选是 B60。因此 D1 **不能**照抄 pilot 的 `assess_pilot_classes()[PilotClass.X]` 自证。

主控 §Phase 5 的交付定义正是本模块的形态：「从 manifest 动态分波」「每个 entry 独立
approved contract/bundle/evidence，不跨 entry 复用」。故本模块的选型守卫
:func:`assert_entry_selectable` 直接在**真实 manifest + 真实 template finder** 上核四条
事实（entry 存在 / independent / profile 同型 / wp_code 一致）+ 零回退，**不**触碰
封闭枚举，也不复用任一 pilot 的契约/attach。

═══ 受管对象 ═══

权威模板 :data:`TEMPLATE_RELATIVE_PATH` = ``D/D1 应收票据.xlsx``（21 sheet），只受管
`原值明细表（按客户）D1-3` 一张：单级表头行 10（15 列 A..O）、数据区 11..20、
G/J/L/O 四列逐行公式 ``=D+E+F`` / ``=D+H-I`` / ``=J+K`` / ``=L+M+N``（openpyxl 逐格实测）、
A21 合计 footer。HTML store = `checklist_responses` 的单条 item ``D1-cust-rows``
（前端 useD1DetailCustomer.ts 的 CustomerRow 整行数组 serializeRows() 序列化进 remark），
按 stable field + rowId 拆开，禁止把整 JSON 当一个字段比较。

磁盘契约 ``backend/data/workpaper_sync_contracts/d1.notes_receivable_detail.json`` 与本模块
现算 payload **双向锁死**（:func:`assert_contract_file_matches_source`），且两个生产入口
（:func:`publish_definitions` / :func:`attach_adapters`）都必须经这把锁。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.registry import (
    AdapterRegistration,
    EntryMatcher,
    WorkpaperSyncAdapterRegistry,
)
from app.services.workpaper_sync.contracts import (
    CONTRACT_SCHEMA_VERSION,
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
    """冻结的 canary entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_phase5_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法（非数组、缺 row identity、重复 identity）。"""

    error_code = "sync_phase5_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的身份常量（从真实 manifest 实测，不是自己挑的字符串）
# ═══════════════════════════════════════════════════════════════════════════

#: Phase 5 分波标签（**描述性**，不是 pilot_harness.PilotClass 枚举成员）。
PHASE5_WAVE: Final[str] = "phase5_notes_receivable"

#: 从 source-backed manifest 冻结的 canary entry（实测 document_type=xlsx / independent=True）。
ENTRY_ID: Final[str] = "xlsx/gt-d1-notes-receivable"

#: adapter_id == contract_id == 契约文件名（registry RG-4 双向锁死）。
ADAPTER_ID: Final[str] = "d1.notes_receivable_detail"

#: matcher 的 wp_code 集合 —— 取自本 entry 的 `wp_match.wp_code_patterns`（实测 ['D1N']）。
WP_CODES: Final[frozenset[str]] = frozenset({"D1N"})

#: 冻结的 scenario profile —— 必须与 manifest 上本 entry 的 profile_id 逐字相等。
#: 实测与 D2/B60 同型（shared+editable 的标准 24 条，不走 authority-model 替换分支）。
EXPECTED_PROFILE_ID: Final[str] = "xlsx.editable.shared.single.room_service_wired.v1"

#: `backend/wp_templates/` 下的权威模板（21 sheet 工作簿，D1-3 是其中一张）。
TEMPLATE_RELATIVE_PATH: Final[str] = "D/D1 应收票据.xlsx"

#: 权威模板字节哨兵（Requirement 9.9：`backend/wp_templates/` 运行时只读）。
TEMPLATE_SHA256: Final[str] = (
    "e6e8dcf28ba6e7f6fdf9867c3ac43b2f1a72e1a1b6f2aa477f58dfca39097577"
)

#: 受管 sheet 的真实 tab 名（构建期选择器；运行时定位一律走 identity 锚点）。
MANAGED_SHEET: Final[str] = "原值明细表（按客户）D1-3"

#: instrumentation 的模板短码（进 row UUID 前缀与 `GT_*` defined names）。
TEMPLATE_ID: Final[str] = "D13"

#: 契约 sheet_key —— 必须与 `build_instrumentation_payload` 产出的
#: `managed_sheets[0].sheet_key`（`f"{template_id.lower()}-managed"`）一致。
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"

ROWS_TABLE_KEY: Final[str] = "notes_receivable_detail_rows"

#: 数据区与 footer（逐 sheet 读权威模板得来，见模块 docstring）。
FIRST_DATA_ROW: Final[int] = 11

#: 受管行区间末行（数据区 11..20，共 10 行；无 BP-21 排版占位尾行）。
LAST_DATA_ROW: Final[int] = 20

#: footer 所在行（`A21 合计`）。
FOOTER_ROW: Final[int] = 21

#: 单级表头行（行 10）。D1-3 无两级表头（对比 D2 的 11/12）。
HEADER_ROW: Final[int] = 10

#: 最后一列受管业务列（`O 期末审定数`）与隐藏 row UUID 列（必须在其右侧）。
MANAGED_LAST_COL: Final[str] = "O"
UUID_COL: Final[str] = "P"

#: 注入的 Excel Table displayName（OOXML 要求字母/下划线开头、无空格）。
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"

#: 本 canary 是 projection-based ⇒ 三个 typed child 全部必须是 approved definition。
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: footer 定位标记（`A21` 的真实文本）。
FOOTER_MARKER: Final[str] = "合计"

#: HTML store 里承载整张表的那一条 item（`checklist_responses.item_id`）。
STORE_ITEM_ID: Final[str] = "D1-cust-rows"

#: 「审计师还没录任何一行」时的 store 载荷（本表根形态是行数组 ⇒ 空行集就是 `[]`）。
EMPTY_STORE_PAYLOAD: Final[str] = "[]"

#: 载荷里每行自带的稳定行身份键（前端 CustomerRow.rowId，形如 `dynamic-<uuid>`）。
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: **15 个受管字段** = `(column_key, 列标, mode, value_type, store json 键, 行 10 表头文本)`。
#:
#: 🔴 顺序即 Excel 列序（A→O）。`store json 键`是前端 CustomerRow 的键名（camelCase，来自
#: useD1DetailCustomer.ts），`column_key` 是契约侧的小写稳定键。G/J/L/O 四列在模板里逐行
#: 有真公式（openpyxl 逐格实测）⇒ mode=formula；其余 11 列模板内无公式故判 editable。
#: A/B=text、C=enum（关联关系）、其余金额=amount。表头文本与行 10 逐字相等（守卫比对）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("customer_name", "A", "editable", "text", "customerName", "客户名称"),
    ("company_code", "B", "editable", "text", "companyCode", "公司代码"),
    ("relation_type", "C", "editable", "enum", "relationType", "关联关系"),
    ("prior_unadjusted", "D", "editable", "amount", "priorUnadjusted", "期初未审数"),
    ("prior_aje", "E", "editable", "amount", "priorAje", "账项调整"),
    ("prior_rje", "F", "editable", "amount", "priorRje", "重分类调整"),
    ("prior_audited", "G", "formula", "amount", "priorAudited", "期初审定数"),
    ("current_increase", "H", "editable", "amount", "currentIncrease", "本期增加"),
    ("current_decrease", "I", "editable", "amount", "currentDecrease", "本期减少"),
    ("current_balance", "J", "formula", "amount", "currentBalance", "期末余额"),
    ("reclassification", "K", "editable", "amount", "reclassification", "被审计单位重分类调整"),
    ("current_unadjusted", "L", "formula", "amount", "currentUnadjusted", "期末未审余额"),
    ("current_aje", "M", "editable", "amount", "currentAje", "账项调整"),
    ("current_rje", "N", "editable", "amount", "currentRje", "重分类调整"),
    ("current_audited", "O", "formula", "amount", "currentAudited", "期末审定数"),
)

#: 四个公式列的只读区域（逐格实测 `=D+E+F` / `=D+H-I` / `=J+K` / `=L+M+N`）。
FORMULA_MASK: Final[tuple[str, ...]] = (
    f"G{FIRST_DATA_ROW}:G{LAST_DATA_ROW}",
    f"J{FIRST_DATA_ROW}:J{LAST_DATA_ROW}",
    f"L{FIRST_DATA_ROW}:L{LAST_DATA_ROW}",
    f"O{FIRST_DATA_ROW}:O{LAST_DATA_ROW}",
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。守卫逐行与权威模板比对。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "G": "=D{r}+E{r}+F{r}",
    "J": "=D{r}+H{r}-I{r}",
    "L": "=J{r}+K{r}",
    "O": "=L{r}+M{r}+N{r}",
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_REPO_ROOT: Final[Path] = _BACKEND_ROOT.parent


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    """Task 5 真实 OO 9.4 载体 gate（单一真源，本模块不复制裁决）。"""
    return ExcelIdentityCarrierGate.load()


def authoritative_template_path() -> Path:
    """权威模板的绝对路径（authority-root 越界检查交给 gate，不自己拼 `backend/wp_templates`）。"""
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)


def read_authoritative_template() -> bytes:
    """读权威模板字节并比对 :data:`TEMPLATE_SHA256`；哨兵不符即抛（Requirement 9.9）。"""
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise EntrySelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} 实测 sha256={digest}，"
            f"冻结哨兵={TEMPLATE_SHA256} —— `backend/wp_templates/` 运行时只读"
            "（Requirement 9.9）；模板真要升级必须按 "
            "`template → instrumentation → contract → bundle → representation` 重新发布"
        )
    return data


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（在真实 manifest / 真实 resolver 上直接推导，不经封闭枚举）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    """`wp_template_finder` 的**实测**解析结果，由调用方提供（不在生产模块直接调 finder）。

    本 canary 的零回退形态与 D2 同：manifest 声明的 wp_code（`D1N`）在 finder 上解析不到
    任何文件（find/any 均 None），而父码（`D1`）的 canonical resolver 落在权威模板。

    :param by_wp_code: `wp_code → 三个 finder 入口解析出的路径`（本 canary 要求**全空**）
    :param parent_code: 父码（`D1N` → `D1`）
    :param parent_resolved_path: 父码的 canonical resolver 落点（要求 == 权威模板）
    """

    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
    """本 canary 的每个 wp_code 在 finder 上都必须解析不到任何文件；父码必须落在权威模板。"""
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
            "本 canary 的零回退判据要求它们**全部**解析不到任何文件，否则契约的 source_ref "
            "可能指向另一份底稿的单元格"
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
    """在**真实** manifest / 真实 resolver 事实上直接核四条必要条件；任一不成立即抛。

    🔴 刻意**不**调 `assess_pilot_classes()`：D1 的 entry_id 会被那个封闭枚举归进
    `simple_checklist`（B60 已占）。Phase 5 的判据是「每个独立 entry 各自成立」，
    因此这里核的是 entry 自身的四条 manifest 事实 + 零回退，与四个 pilot 的类边界解耦。

    :param resolution: 见 :class:`TemplateResolutionFacts`。**必填**（无默认 ⇒ 不会出现
        「没给就跳过」的 fail-open）。
    """
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(ENTRY_ID)
    if entry is None:
        raise EntrySelectionError(
            f"冻结的 canary entry {ENTRY_ID!r} 不在 source-backed manifest 里 —— "
            "宿主挂载点已变，必须重新走选型而不是改常量"
        )
    if str(entry.get("document_type") or "") != "xlsx":
        raise EntrySelectionError(
            f"{ENTRY_ID!r} 的 document_type={entry.get('document_type')!r} 非 xlsx —— "
            "本 canary 走 Excel 双向路径"
        )
    if not entry.get("independent_entry"):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} 的 independent_entry={entry.get('independent_entry')!r}"
            f"（parent_entry_id={entry.get('parent_entry_id')!r}）—— 重复入口不得注册 adapter"
            "（AC 12.1「每个独立 entry」）"
        )
    profile_id = str((entry.get("scenario_profile") or {}).get("profile_id") or "")
    if profile_id != EXPECTED_PROFILE_ID:
        raise EntrySelectionError(
            f"{ENTRY_ID!r} 的 profile_id={profile_id!r} 与冻结的 {EXPECTED_PROFILE_ID!r} 不符 —— "
            "profile 决定 required scenario set，漂移即须重核，不得沿用旧契约"
        )
    codes = {str(c) for c in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if codes != set(WP_CODES):
        raise EntrySelectionError(
            f"{ENTRY_ID!r} 的 wp_code_patterns={sorted(codes)} 与冻结的 matcher 域 "
            f"{sorted(WP_CODES)} 不一致 —— matcher 必须覆盖该 entry 的全部 wp_code"
        )
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 4. instrumentation spec 与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    """本 entry 的 Task 17 instrumentation 声明。"""
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
    """template definition 的 canonical payload（发布 DAG 第一段）。"""
    data = read_authoritative_template()
    return build_template_payload(
        spec=instrumentation_spec(),
        template_sha256=TEMPLATE_SHA256,
        structure_hash=normalized_structure_hash(data),
    )


def instrumentation_definition_payload() -> dict[str, Any]:
    """instrumentation definition 的 canonical payload（单向引用 template digest）。"""
    return build_instrumentation_payload(
        spec=instrumentation_spec(),
        template_definition_sha256=canonical_digest(template_definition_payload()),
        template_sha256=TEMPLATE_SHA256,
        gate=excel_carrier_gate(),
    )


def authority_model_payload() -> dict[str, Any]:
    """authoritative model definition 的 canonical payload（独立批准）。"""
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
    """`source_ref` 的统一形态：权威源 xlsx 的 `sheet!单元格`。"""
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


def _spec_d103() -> Any:
    """延迟取 D1-3 的 `RowTableSheetSpec` 声明（Task 15 收敛用）。

    🔴 **必须延迟 import**：`phase5_d1_03_customer` 在模块级 `import phase5_d1_notes_receivable`
    （它的几何数字全从本模块的冻结常量引用，避免两处各写一份而漂移）⇒ 本模块反向做模块级
    import 会成环。函数内 import 是唯一解，且与 D5/D6/D7 收敛时的引擎 import 同款写法。
    """
    from app.services.workpaper_sync.phase5_d1_03_customer import SPEC_D103

    return SPEC_D103


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """薄转发框架层同名函数（Task 15 声明化，逐字节等价）。

    等价性：引擎返回 `f"{spec.table_key}/{row_identity}/{column_key}"`，而
    `SPEC_D103.table_key` 就是本模块的 :data:`ROWS_TABLE_KEY` ⇒ 输出逐字符相同。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        stable_key_for as _engine_stable_key_for,
    )

    return _engine_stable_key_for(_spec_d103(), column_key, row_identity)


def _rows_table_payload() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_key, header_text in MANAGED_FIELD_SPECS:
        fields.append(
            {
                "stable_field_key": stable_key_for(column_key),
                "json_pointer": f"/rows/{{row_uuid}}/{json_key}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
                "header_source_ref": _src(f"{column}{HEADER_ROW}"),
                "store_item_id": STORE_ITEM_ID,
                "header_text": header_text,
            }
        )
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_ROW}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "footer 行 A21 承载合计公式（D21..O21 = SUM(x11:x20)，openpyxl 逐格实测；"
                "G/J/L/O 列 SUM 覆盖公式列，H/I 为 SUM）。区间末行 20 是模板排版末行，"
                "声明为真使结构性插行有权按声明位移量扩张该区间"
            ),
        },
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


def _expansion_sheet_payloads() -> list[dict[str, Any]]:
    """从 expansion 模块的已启用 specs 自动派生 contract sheet payloads。

    🔴 同一 sheet_key 下多个 table（如 D1-4 个别/组合两区、D1-8 贴现/背书两区）被合并
    进同一个 sheet payload 的 `tables` 数组——契约 schema 要求 `sheet_key` 唯一。
    """
    from app.services.workpaper_sync.phase5_d1_expansion import managed_row_table_specs
    from app.services.workpaper_sync.phase5_row_table_sheet import spec_to_contract_sheet_payload

    by_sheet_key: dict[str, dict[str, Any]] = {}
    for spec in managed_row_table_specs():
        if spec.sheet_key == SHEET_KEY:
            continue  # D1-3 already in the main sheets list
        payload = spec_to_contract_sheet_payload(spec)
        sk = payload["sheet_key"]
        if sk in by_sheet_key:
            # Same sheet, additional table (dual/triple region)
            by_sheet_key[sk]["tables"].extend(payload["tables"])
        else:
            by_sheet_key[sk] = payload
    return list(by_sheet_key.values())


def build_contract_payload() -> dict[str, Any]:
    """本 entry 自己的 per-entry contract canonical payload（两个 digest 现算，单向引用）。"""
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
            },
            *_expansion_sheet_payloads(),
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


#: 契约 `review.html_store.note` 的冻结文本（与磁盘契约逐字相等）。
_HTML_STORE_NOTE: Final[str] = (
    "整张按客户明细表今天存成这一条 item 的 remark（一个 JSON 数组字符串，"
    "serializeRows() 产出）。本契约按 stable field + row rowId 拆开，禁止把整 JSON 当一个"
    "字段比较（对齐 D2 AC 6.9 / 6.12 / design §Merge Algorithm）。前端模型 = "
    "useD1DetailCustomer.ts 的 CustomerRow，STORAGE_KEY='D1-cust-rows'"
)

#: 契约 `review.reviewed_basis` 的冻结文本（与磁盘契约逐字相等）。
_REVIEWED_BASIS: Final[str] = (
    "openpyxl 逐 sheet 直读权威模板 D/D1 应收票据.xlsx 的 21 张 sheet，只取受管 sheet "
    "原值明细表（按客户）D1-3：单级表头行 10（15 列 A..O）、数据区 11..20 行、G/J/L/O 四列"
    "逐行公式 =D+E+F / =D+H-I / =J+K / =L+M+N（openpyxl 逐格实测），其余 A/B/C/D/E/F/H/I/K/M/N "
    "列模板内无公式故判 editable（A/B/C 为 text，其余金额为 amount），A21 合计 footer"
    "（D21..O21 = SUM(x11:x20)）；15 个字段的 source_ref / header_source_ref 均指向上述真实"
    "单元格，字段键集合与前端 useD1DetailCustomer.CustomerRow 逐字段锁死"
    "（customerName/companyCode/relationType/priorUnadjusted/priorAje/priorRje/priorAudited/"
    "currentIncrease/currentDecrease/currentBalance/reclassification/currentUnadjusted/"
    "currentAje/currentRje/currentAudited）。注意 xlsx J 列公式=D+H-I（不含 E/F），前端 "
    "recalcRow 用 priorAudited+inc-dec=G+H-I，数值语义等价但公式文本以 xlsx 为准 ⇒ J 声明为 "
    "formula，materialize 不覆盖公式格由 OO 重算"
)


def contract_file_path() -> Path:
    """磁盘契约路径（`contracts.contract_path_for` 是唯一拼路径处）。"""
    return contract_path_for(ADAPTER_ID)


def load_contract_from_disk() -> SyncContract:
    """从磁盘加载并强校验本 canary 的生产契约。"""
    return load_contract(ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    """磁盘契约 ↔ 本模块现算 payload **双向**锁死。"""
    expected = build_contract_payload()
    on_disk = load_contract_from_disk()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise EntrySelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            "请用 `& d:/GT_plan/.venv/Scripts/python.exe "
            "backend/scripts/gen/generate_phase5_d1_contract.py --apply` 重生成 "
            f"{contract_file_path().name}，并复核 diff"
        )
    parse_contract(expected, adapter_id=ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. HTML store 载荷拆分（stable field + row UUID，流式）
# ═══════════════════════════════════════════════════════════════════════════


#: 🔴 Task 15 声明化：`store_row_identity` / `iter_store_rows` / `split_store_row` 三个
#: **模块内部** helper 已收敛进框架层 `phase5_row_table_sheet`（收敛前已 grep 确认全仓零
#: 模块外调用方，与 D5/D6/D7 同款处置）。`build_store_projection` /
#: `merge_projection_into_store_rows` 保留同名薄转发（它们是 provider 的公开门面，
#: `store_projection_response` / `oo_to_html` 按名调用）。


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """薄转发框架层 `build_store_projection(SPEC_D103, ...)`（逐字节等价）。

    🔴 **必须转译引擎异常**：引擎抛 `RowTableStorePayloadError(Exception)` 非 domain 错误，
    直接冒泡会被 `wp_sync_router` 当未知异常 ⇒ **opaque 500**；而本函数收敛前抛
    `StorePayloadError(SyncDomainError)` 带 `error_code` ⇒ 映射 **4xx**。畸形 store 载荷是
    用户侧数据问题（OCR/导入/手改都能写出非数组），必须保持 4xx。
    D3/D5/D6/D7 在 Task 16/17 收敛时**漏了这一步**、四家一起从 4xx 退化成 500（2026-09-26
    实测确认并修复），本家收敛一开始就带上转译，不重犯。
    判据：`test_store_payload_error_stays_domain_error.py`（D1 在其正式参数化清单内）。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableStorePayloadError,
        build_store_projection as _engine_build_store_projection,
    )

    try:
        return _engine_build_store_projection(
            _spec_d103(), payload, contract=contract, limits=limits
        )
    except RowTableStorePayloadError as exc:
        raise StorePayloadError(str(exc)) from exc


def merge_projection_into_store_rows(
    *,
    projection: Any,
    base_rows: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int, int, set[str]]:
    """把已 extract 的 projection 合进 D1-cust-rows HTML store 行（不读盘）。

    🔴 field_id（契约侧 snake column_key）→ store json 键（前端 camelCase）的映射由
    :data:`MANAGED_FIELD_SPECS` 的第 0/4 列给出，两侧不可能各写一份而脱钩。

    🔴 幽灵行防护（D4-2 同源缺陷，2026-09-22 用户实测）：Excel Table 边界被扩展时，
    若新行只有一个杂散的 editable 格非空（公式列已由 is_protected 挡掉），这一个
    字段就会让 identity 通过 shell 创建关卡，而 customer_name（该行的业务名称，
    契约首列）因从未在 Excel 里写入内容、根本不产出 FieldValue，永久停在空值——
    用户在结构化视图里看到的正是「有 rowId、没数据」的行。只对**本次新增**的
    identity 加这道门：已存在的行永不受影响（清空是合法编辑）。

    🔴 Task 15 声明化：本体已收敛进框架层，此处只薄转发。幽灵行防护锚点取
    `SPEC_D103.ghost_row_anchor_index`（默认 0 = `customer_name`，与收敛前的
    `MANAGED_FIELD_SPECS[0][4]` 逐字同一列）—— D1 首列就是自由文本业务名称，
    不需要 D5/D6 那样的非零锚点例外。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        merge_projection_into_store_rows as _engine_merge,
    )

    return _engine_merge(_spec_d103(), projection=projection, base_rows=base_rows)


# ═══════════════════════════════════════════════════════════════════════════
# 7. 发布（顺序由 Task 12 的 publisher 强制）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Phase5Definitions:
    """本 canary 一次完整发布的四个 definition + 一个 non-null bundle。"""

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
    """按 `template → instrumentation → contract → bundle` 发布本 entry 的身份。

    :param publisher: Task 12 的 DefinitionPublisher。顺序、payload 校验、DAG 前置与
        bundle slot 规范化全部由它负责 —— 本函数只编排，不复制判据。authority model
        独立先发布（它是 bundle 的必填 child，而 PUBLISH_DAG 只管 template/instr/contract）。
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
            f"已发布 template definition digest {template.sha256} 与契约声明的 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise EntrySelectionError(
            f"已发布 instrumentation definition digest {instrumentation.sha256} 与契约声明的 "
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
    """本 entry 的匹配域（精确 wp_code 集合，不用 glob）。"""
    return EntryMatcher(document_type="xlsx", wp_codes=WP_CODES)


def build_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    """组一条注册记录。`declared_capability` 恒为 bidirectional（两侧不一致 registry 打红）。"""
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
    """把本 canary 注册进 registry（全部准入判据由 `registry.register()` 执行）。"""
    registration = build_registration(
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract
    )
    registry.register(registration)
    return registration


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """从已 published representation **现读** FrozenEntryDefinitions（复用四 pilot 同一观测器）。

    唯一实现在 published_identity_observer.observe_published_frozen_definitions —— 本函数
    不复制它的任何一步判据。失败一律上抛，**绝不**返回 None（返回 None 会让上游把「观测失败」
    表现成「这个 entry 没有身份」，一路静默走到「注册没有 identity binding 的 adapter」）。
    """
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
            f"entry {ENTRY_ID}: 观测器按 representation 冻结的 adapter_id 读出的契约 digest "
            f"{observation.definitions.contract.canonical_sha256} 与本模块 source-locked 的 "
            f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩"
        )
    return observation


async def attach_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """**生产接线点**：把已 published representation 的本 canary entry 接进 registry。

    调用方是 `wp_sync_router`（`_attach_pilot_adapters` 与 `_apply_durable_incoming`）。
    返回本次成功注册的 adapter_id 元组。顺序不可交换，且没有任何 `except: pass`：

    1. manifest capability 必须**已启用**。没启用返回空元组且**一次库都不读** ——
       这是「这个 entry 今天还不是双向」这一事实的忠实表达（今天恒走这一条，直到 Task 4
       把 overlay 裁决为 bidirectional 并重生 manifest）。
    2. entry_state 必须已有 published representation（Task 3 finalize 之后才有）。
    3. representation 必须绑定 approved bundle。
    4. descriptor/room 由 entry_source_facts 的实测观察器给出，不从 manifest 读回。
    5. adapter 组装：由 resolve_published_frozen_definitions 现读冻结身份。
    """
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
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）—— "
            "不可达入口不得注册 adapter（Requirement 1.7）"
        )
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    definitions = observation.definitions
    register_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=definitions,
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
    """capability 是否已启用（接线路径的「今天不是我的回合」分支用它做真值判定）。

    实现**委派**给 :func:`assert_manifest_capability_enabled`，只把它的异常翻成布尔；
    `except` 只捕获 :class:`EntrySelectionError` 这一个窄类型（宽 except 会把真故障吞成假）。
    """
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except EntrySelectionError:
        return False
    return True


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    """manifest 侧 capability/adapter_id 必须已启用（overlay 裁决 + 重生成之后）。

    🔴 **今天必然抛**：Task 4 把 overlay 裁决为 bidirectional 并重生 manifest 之前，
    本 entry 的 capability 是 single_onlyoffice。提前改就是跳过顺序。
    """
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    )[ENTRY_ID]
    capability = capability_of(entry)
    if capability is not Capability.bidirectional:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest capability={capability.value} —— "
            "注册 bidirectional adapter 前必须先由 reviewed overlay 裁决为 bidirectional "
            "并重生成 manifest（RG-18 会以 FakeBidirectionalError 拒绝伪双向）"
        )
    if str(entry.get("adapter_id") or "") != ADAPTER_ID:
        raise EntrySelectionError(
            f"entry {ENTRY_ID} 的 manifest adapter_id={entry.get('adapter_id')!r} "
            f"与本 canary 的 {ADAPTER_ID!r} 不符"
        )


def _unused_instrumentation_error_guard() -> type[InstrumentationError]:
    """保留 `InstrumentationError` 的显式引用（它是本模块 payload 构建的失败类型）。"""
    return InstrumentationError


# ═══════════════════════════════════════════════════════════════════════════
# 9. 与 provisioning / attach 白名单的接口别名
# ═══════════════════════════════════════════════════════════════════════════
#
# `projection_provisioning.load_projection_supply` 与 `registry.build_manifest_
# registration_plan` 按**统一命名**读 provider（四个 pilot 都叫 `publish_pilot_definitions`
# / `attach_pilot_adapters` / `PILOT_WP_CODES`）。本模块的语义名是 Phase-5 口径
# （`publish_definitions` / `attach_adapters` / `WP_CODES`），此处提供别名让供给层
# 零改动即可接入 —— 别名与本体是**同一个对象**，不可能各自漂移。

#: provisioning / attach 白名单读的统一名（== :func:`publish_definitions`）。
publish_pilot_definitions = publish_definitions

#: attach 接线点的统一名（== :func:`attach_adapters`）。
attach_pilot_adapters = attach_adapters

#: registration plan 读的统一 wp_code 名（== :data:`WP_CODES`）。
PILOT_WP_CODES = WP_CODES
