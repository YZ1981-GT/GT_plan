# -*- coding: utf-8 -*-
"""简单 checklist Excel pilot —— **冻结的那一个 entry** 自己的身份、契约与注册。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 40
Requirements: 3.7, 4.11, 6.8, 6.11, 12.1, 12.2, 12.10, 12.12, 14.1, 14.2
Properties: **P11 / P25 / P26 / P29 / P49 / P55 / P62 / P69**

═══ 一、为什么冻结的是 `xlsx/b60/gt-b60-bundle` ═══

Task 39 的 :func:`~app.services.workpaper_sync.pilot_harness.assess_pilot_classes` 把
`simple_checklist` 这一类定义成「xlsx 且 entry_id 不匹配 d2/h1/g7」，实测 **174** 个候选。
在这 174 个里再叠三条**机器可判**的必要条件，剩下恰好一个：

1. `independent_entry = true`。AC 12.1 的原文是「每个**独立** entry」；44 条
   `parent_duplicate` 在 overlay 里带着 `parent_reason`（"must not be counted as
   independent adapters"），`registry.register()` 也会直接拒它们。
2. entry 的 `wp_match.wp_code_patterns` 里存在一个 **与 `backend/wp_templates/_index.json`
   的 `wp_code` 精确相等**的码。这条是本次选型的关键判据：
   `wp_template_finder.find_template_file()` 对找不到自有模板的 wp_code 会一路回退到
   **父级程序表**（实测 16 个 independent 候选里 15 个都是这种回退），于是契约的
   `source_ref` 会指向另一份底稿的单元格 —— 那正是本 spec 已经付过两次学费的
   「据参考副本/父表重建」形态。`xlsx/b60/gt-b60-bundle` 的 `B60` 是**唯一**零回退的。
3. `scenario_profile.profile_id = xlsx.editable.shared.single.room_service_wired.v1`
   （178 条 entry 的多数形态）⇒ required scenario set 就是 shared+editable 的标准集合，
   不走任何 authority-model 替换分支，因此 Property 25/26 的字段级两场景**必须**跑。

选型脚本与实测输出见 evidence 目录；本模块只把结论固定成常量，并由守卫在
`assess_pilot_classes()` 的真实输出上**重新推导一次**这三条（不是抄结论）。

═══ 二、权威模板只认 `backend/wp_templates/` ═══

:data:`TEMPLATE_RELATIVE_PATH` 指向 `B/B60-1 审计项目工时预算与控制表.xlsx`，
:data:`TEMPLATE_SHA256` 是它的字节哨兵（与 Task 37 的 `TEMPLATE_SHA` 同款）。
`基础数据/致同通用审计程序及底稿模板…` 下的同名文件是**已落后的参考副本**，本模块
一次都不读它。跑完本任务全部测试后 `backend/wp_templates/**` 字节必须原样 ——
:func:`read_authoritative_template` 每次读都比对哨兵，改一个字节就抛。

受管 sheet 是 `B60-1工时预算与控制表`（逐 sheet 读出来的真实 tab 名）。工作簿共 4 张 sheet：
`底稿目录` / `B60-1工时预算与控制表` / `B60-1工时预算与控制板（按阶段）` / 隐藏 `GT_Custom`。
本契约**只**声明第二张 —— `excel_extract.managed_tables_of()` 对「受管 sheet 之外还声明了
表」显式 fail closed，一次 extract 只覆盖一张 sheet。

═══ 三、逐字段 source_ref 指向真实单元格（人工审核依据）═══

受管 sheet 的真实网格（openpyxl 直读，见 evidence 的 sheet dump）：

* 行 5/6 是**两级表头**：`A5 级别` / `B5 姓名` / `C5:D5 预算工时`（`C6 执行工时`、
  `D6 复核工时`）/ `E5 小时费用` / `F5 费用预算` / `G5:H5 实际工时`（`G6 执行工时`、
  `H6 复核工时`）/ `I5 差异说明`。故 `header_rows = 2`。
* 行 7..23 是数据区：`A7 合伙人` … `A22 项目质量控制复核人员`，第 23 行是模板留的可增行
  （只有 `F23` 公式）。
* `F7..F23` 全部是 `=(C{r}+D{r})*E{r}` ⇒ 契约里 `mode=formula` + `formula_mask`。
* `A24 合计` 是 footer ⇒ `footer_anchor = {marker: 合计, search_column: A}`，不写死行号。
* 行 3/4 是元信息标签（`A3 被审计单位名称：` / `C3 编制人：` / `E3 编制日期：` /
  `A4 会计期间：` / `C4 复核人：` / `E4 复核日期：`），值格在各标签右侧一列 ⇒ 静态表。

`G3` 是 `索引号：B60-1`，属固定文案不入契约。

═══ 四、发布顺序不可颠倒，且本模块不是第二个真源 ═══

`template → instrumentation → contract → bundle → representation` 的顺序由 Task 12 的
:class:`~app.services.workpaper_sync.definitions.DefinitionPublisher` 强制；payload 由
Task 17 的 :func:`~app.services.workpaper_sync.excel_instrumentation.build_template_payload`
/ :func:`~app.services.workpaper_sync.excel_instrumentation.build_instrumentation_payload`
生成。本模块**不**自己拼 payload、不自己算 digest、不自己校验 bundle slot —— 复制一份
的后果不是「更安全」，而是任一侧被短路都不改变行为 ⇒ 变异检验判 GREEN（本 spec 已
在 `definitions._normalize_slot_input` 上实测过同一形态）。

磁盘契约 `backend/data/workpaper_sync_contracts/b60.hour_budget.json` 与本模块由
:func:`build_contract_payload` 现算的 payload **双向锁死**
（:func:`assert_contract_file_matches_source`）：改契约不改代码、或改代码不改契约，
两个方向都打红。契约里的两个 digest 因此不是手抄的常量，而是**真实**已发布 payload 的
canonical digest。

═══ 五、capability 的启用是「补齐落后的一侧」，不是放宽 ═══

实测（`entry_source_facts.observe_descriptor_facts`）：本 entry 的宿主**已经**暴露
结构化 ↔ OO 模式切换，故 descriptor mode 事实 = `bidirectional`；而 manifest 的
reviewed capability 还是 `single_onlyoffice` ⇒ `registry.build_report()` 现在就把它算进
`profile_drift`（RG-16）。把 overlay 的 capability 改成 `bidirectional` 并给出 adapter_id
将来是**消除**这条既有漂移、不是绕开判据：`assert_profile_consistent_with_room` 三条
（shared doc_key / doc_key 不含 mtime / participant lease）实测全部已满足。

🔴 但**今天不能改**。任务正文的顺序是「经 Task 36 finalize 成 published representation
后，**方可**注册 adapter / 接宿主 / 启用 capability」，而该 finalize 今天仍缺**供给**
（Task 75 已交付公共观测器；`working_paper_sync_definition_bundle` /
`working_paper_content_representation` 两表实测 0 行，approved bundle 的生产侧
provisioner 是 Task 76 的交付）。此刻把 capability 提前改成
`bidirectional` 就是跳过顺序：manifest 会宣称双向可用，而 registry 里一个 adapter 都没有，
`_registration` 只能给 422 —— 前端显示一个不可兑现的模式切换（Requirement 1.5 明令禁止）。
故 manifest 侧维持 `single_onlyoffice` / `adapter_id=null`，由
:func:`assert_manifest_capability_enabled` 在启用前 fail closed，
`registry.build_report()` 把「契约有了而 adapter 没注册」当**可见欠账**报出来。
"""

from __future__ import annotations

import hashlib
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

__all__ = [
    "PILOT_ADAPTER_ID",
    "PILOT_CLASS",
    "PILOT_ENTRY_ID",
    "PILOT_WP_CODES",
    "MANAGED_SHEET",
    "META_TABLE_KEY",
    "ROWS_TABLE_KEY",
    "SHEET_KEY",
    "TEMPLATE_ID",
    "TEMPLATE_RELATIVE_PATH",
    "TEMPLATE_SHA256",
    "FIRST_DATA_ROW",
    "LAST_DATA_ROW",
    "FOOTER_ROW",
    "MANAGED_LAST_COL",
    "UUID_COL",
    "TABLE_NAME",
    "AUTHORITY_MODEL",
    "MANAGED_FIELD_SPECS",
    "META_FIELD_SPECS",
    "PilotDefinitions",
    "PilotSelectionError",
    "assert_contract_file_matches_source",
    "assert_manifest_capability_enabled",
    "assert_pilot_entry_selectable",
    "excel_carrier_gate",
    "resolve_published_frozen_definitions",
    "attach_pilot_adapters",
    "authoritative_template_path",
    "authority_model_payload",
    "build_contract_payload",
    "build_pilot_matcher",
    "build_pilot_registration",
    "contract_file_path",
    "instrumentation_definition_payload",
    "instrumentation_spec",
    "load_pilot_contract",
    "publish_pilot_definitions",
    "read_authoritative_template",
    "register_pilot_adapter",
    "template_definition_payload",
]


class PilotSelectionError(SyncDomainError):
    """冻结的 pilot entry 不再满足选型必要条件（manifest 漂移即打红）。"""

    error_code = "sync_pilot_selection_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的身份常量
# ═══════════════════════════════════════════════════════════════════════════

#: 本 pilot 覆盖的 AC 12.2 四类之一（与 `pilot_harness.PilotClass` 同域）。
PILOT_CLASS: Final[str] = "simple_checklist"

#: 从 source-backed manifest 冻结的 entry（不是自己挑的一个字符串：
#: :func:`assert_pilot_entry_selectable` 在真实 manifest 上重新推导必要条件）。
PILOT_ENTRY_ID: Final[str] = "xlsx/b60/gt-b60-bundle"

#: adapter_id == contract_id == 契约文件名（registry RG-4 双向锁死）。
PILOT_ADAPTER_ID: Final[str] = "b60.hour_budget"

#: matcher 的 wp_code 集合 —— 取自本 entry 的 `wp_match.wp_code_patterns`。
PILOT_WP_CODES: Final[frozenset[str]] = frozenset({"B60", "B60B"})

#: `backend/wp_templates/` 下的权威模板（唯一载体）。
TEMPLATE_RELATIVE_PATH: Final[str] = "B/B60-1 审计项目工时预算与控制表.xlsx"

#: 权威模板字节哨兵（Requirement 9.9：`backend/wp_templates/` 运行时只读）。
TEMPLATE_SHA256: Final[str] = (
    "65154146ed3b88a3c2908e064ceb29b6bc73e842559934cbaf2b6893421bd0b0"
)

#: 受管 sheet 的真实 tab 名（构建期选择器；运行时定位一律走 identity 锚点）。
MANAGED_SHEET: Final[str] = "B60-1工时预算与控制表"

#: instrumentation 的模板短码（进 row UUID 前缀与 `GT_*` defined names）。
TEMPLATE_ID: Final[str] = "B601"

#: 契约 sheet_key —— 必须与 `build_instrumentation_payload` 产出的
#: `managed_sheets[0].sheet_key`（`f"{template_id.lower()}-managed"`）一致。
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"

ROWS_TABLE_KEY: Final[str] = "hour_budget_rows"
META_TABLE_KEY: Final[str] = "hour_budget_meta"

#: 数据区与 footer（逐 sheet 读权威模板得来，见模块 docstring §三）。
FIRST_DATA_ROW: Final[int] = 7
LAST_DATA_ROW: Final[int] = 23
FOOTER_ROW: Final[int] = 24
HEADER_FIRST_ROW: Final[int] = 5
META_LABEL_ROWS: Final[tuple[int, int]] = (3, 4)

#: 最后一列受管业务列（`I 差异说明`）与隐藏 row UUID 列（必须在其右侧）。
MANAGED_LAST_COL: Final[str] = "I"
UUID_COL: Final[str] = "J"

#: 注入的 Excel Table displayName（OOXML 要求字母/下划线开头、无空格）。
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"

#: 本 pilot 是 projection-based ⇒ 三个 typed child 全部必须是 approved definition。
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: 公式列的只读区域（`F7:F23`，逐格实测 `=(C{r}+D{r})*E{r}`）。
FORMULA_MASK: Final[tuple[str, ...]] = (
    f"F{FIRST_DATA_ROW}:F{LAST_DATA_ROW}",
)

#: footer 定位标记（`A24` 的真实文本）。
FOOTER_MARKER: Final[str] = "合计"


def _src(cell: str) -> str:
    """`source_ref` 的统一形态：权威源 xlsx 的 `sheet!单元格`。"""
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


#: 行域受管字段：`(column_key, 列标, mode, value_type, 表头依据单元格)`。
#:
#: 🔴 **顺序即列序**（A→I）。`header_ref` 指向该列**表头**所在单元格，`source_ref` 指向
#: 第一条数据行的单元格 —— 两者都在守卫里与权威模板 openpyxl 直读的真实文本比对，
#: 因此这张表不能靠"看起来对"通过（假绿第③源：自证式同义反复）。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("grade", "A", "editable", "text", "A5", "级别"),
    ("member_name", "B", "editable", "text", "B5", "姓名"),
    ("budget_execution_hours", "C", "editable", "amount", "C6", "执行工时"),
    ("budget_review_hours", "D", "editable", "amount", "D6", "复核工时"),
    ("hourly_rate", "E", "editable", "amount", "E5", "小时费用"),
    ("budget_cost", "F", "formula", "amount", "F5", "费用预算"),
    ("actual_execution_hours", "G", "editable", "amount", "G6", "执行工时"),
    ("actual_review_hours", "H", "editable", "amount", "H6", "复核工时"),
    ("variance_note", "I", "editable", "text", "I5", "差异说明"),
)

#: 静态元信息字段：`(column_key, 标签单元格, 值列, 行, 标签真实文本)`。
#: 值格恒在标签格右侧一列（`A3 被审计单位名称：` → 值 `B3`）。
META_FIELD_SPECS: Final[tuple[tuple[str, str, str, int, str], ...]] = (
    ("entity_name", "A3", "B", 3, "被审计单位名称："),
    ("accounting_period", "A4", "B", 4, "会计期间："),
    ("preparer", "C3", "D", 3, "编制人："),
    ("reviewer", "C4", "D", 4, "复核人："),
    ("prepared_on", "E3", "F", 3, "编制日期："),
    ("reviewed_on", "E4", "F", 4, "复核日期："),
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]


def authoritative_template_path() -> Path:
    """权威模板的绝对路径。

    🔴 不自己拼 `backend/wp_templates`：交给 Task 17 的
    :meth:`ExcelIdentityCarrierGate.assert_template_under_authority`，它同时做
    authority-root 越界检查（`..`、绝对路径、软链）。
    """
    return excel_carrier_gate().assert_template_under_authority(TEMPLATE_RELATIVE_PATH)


def read_authoritative_template() -> bytes:
    """读权威模板字节并比对 :data:`TEMPLATE_SHA256`。

    哨兵不符即抛（不是 warning）：模板库被运行时改写是 Requirement 9.9 明令禁止的，
    静默继续会让后面每一个 digest 都对着一份"新模板"算出来。
    """
    path = authoritative_template_path()
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != TEMPLATE_SHA256:
        raise PilotSelectionError(
            f"权威模板字节已变: {TEMPLATE_RELATIVE_PATH} 实测 sha256={digest}，"
            f"冻结哨兵={TEMPLATE_SHA256} —— `backend/wp_templates/` 运行时只读"
            "（Requirement 9.9）；模板真要升级必须按 "
            "`template → instrumentation → contract → bundle → representation` 重新发布"
        )
    return data


def excel_carrier_gate() -> ExcelIdentityCarrierGate:
    """Task 5 真实 OO 9.4 载体 gate（单一真源，本模块不复制裁决）。"""
    return ExcelIdentityCarrierGate.load()


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（在真实 manifest 上重新推导，不抄结论）
# ═══════════════════════════════════════════════════════════════════════════


def assert_pilot_entry_selectable(
    *, manifest: Mapping[str, Any] | None = None, template_wp_codes: Sequence[str] | None = None
) -> Mapping[str, Any]:
    """在**真实** manifest 上重新推导三条必要条件；任一不成立即抛。

    :param template_wp_codes: `backend/wp_templates/_index.json` 里全部 xlsx 的 `wp_code`。
        默认现读索引 —— 这条参数只为让「索引里没有该码」这一分支可测（否则它对真实
        数据结构性不可达，即永久 GREEN）。
    """
    from app.services.workpaper_sync.pilot_harness import PilotClass, assess_pilot_classes

    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    entry = entries.get(PILOT_ENTRY_ID)
    if entry is None:
        raise PilotSelectionError(
            f"冻结的 pilot entry {PILOT_ENTRY_ID!r} 不在 source-backed manifest 里 —— "
            "宿主挂载点已变，必须重新走选型而不是改常量"
        )

    assessment = assess_pilot_classes(manifest=payload)[PilotClass.simple_checklist]
    if PILOT_ENTRY_ID not in assessment.candidate_entry_ids:
        raise PilotSelectionError(
            f"{PILOT_ENTRY_ID!r} 不在 assess_pilot_classes() 的 simple_checklist 候选里"
            f"（当前 {len(assessment.candidate_entry_ids)} 个候选）—— Property 49 的类边界"
            "由 harness 判定，不由本模块声明"
        )
    if not entry.get("independent_entry"):
        raise PilotSelectionError(
            f"{PILOT_ENTRY_ID!r} 的 independent_entry={entry.get('independent_entry')!r} —— "
            f"parent_entry_id={entry.get('parent_entry_id')!r} 的重复入口不得注册 adapter"
            "（AC 12.1「每个独立 entry」）"
        )
    codes = {str(code) for code in (entry.get("wp_match") or {}).get("wp_code_patterns") or ()}
    if codes != set(PILOT_WP_CODES):
        raise PilotSelectionError(
            f"{PILOT_ENTRY_ID!r} 的 wp_code_patterns={sorted(codes)} 与冻结的 matcher 域 "
            f"{sorted(PILOT_WP_CODES)} 不一致 —— matcher 必须覆盖该 entry 的全部 wp_code，"
            "不得多也不得少"
        )
    index_codes = (
        set(template_wp_codes) if template_wp_codes is not None else _template_index_wp_codes()
    )
    zero_fallback = sorted(codes & index_codes)
    if not zero_fallback:
        raise PilotSelectionError(
            f"{PILOT_ENTRY_ID!r} 的 wp_code {sorted(codes)} 在 wp_templates/_index.json 里"
            "都没有精确对应的模板 ⇒ `find_template_file()` 只能回退到父级程序表，"
            "契约的 source_ref 会指向另一份底稿的单元格 —— 禁止这样发布契约"
        )
    return entry


def _template_index_wp_codes() -> set[str]:
    """`backend/wp_templates/_index.json` 里全部 xlsx 模板的 `wp_code`。

    🔴 索引位置取自 :data:`app.services.wp_template_finder.INDEX_FILE`，本模块**不**自己拼
    ``_BACKEND_ROOT / "wp_templates" / "_index.json"``：

    * 模板库在哪由 `wp_template_finder` 单独持有（它是运行时查模板的唯一入口）。这里再拼
      一次就是同一事实的第二个真源 —— 模板库换根时两处各说各话，而本函数的用途恰恰是
      「判断 `find_template_file()` 会不会回退到父级程序表」，两侧看的不是同一个索引时
      这个判断本身就失效了。
    * Task 19/20 的 writer/resolver 清册按 AST 把「函数内出现 ``… / "wp_templates" / …``
      的路径拼接」一律记成一条 resolver 欠账：实测本函数曾在
      `backend/data/workpaper_writer_inventory.json` 里带
      ``resolver_identities=["<ad_hoc_path_construction>"]`` 且
      ``non_canonical_resolver_only=true``，同时命中 `unadjudicated_resolver`，
      给收口门禁贡献 2 条 blocking fact。它既不解析底稿实体文件、也永远不该走
      `resolve_wp_file`（那是底稿产物的 canonical resolver，不是模板索引的），
      所以正确的收敛方式是**不再自己拼路径**，而不是给它盖一个 domain 标签。
    """
    import json

    from app.services.wp_template_finder import INDEX_FILE

    try:
        payload = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PilotSelectionError(f"模板索引不可读: {INDEX_FILE}: {exc}") from exc
    return {
        str(row.get("wp_code") or "")
        for row in payload.get("files") or []
        if str(row.get("relative_path") or "").lower().endswith(".xlsx")
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. instrumentation spec 与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    """本 entry 的 Task 17 instrumentation 声明。"""
    return ExcelInstrumentationSpec(
        entry_id=PILOT_ENTRY_ID,
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
    """authoritative model definition 的 canonical payload（独立批准）。

    `projection_contract` ⇒ 三个 typed child 全部必须是 approved definition；AC 12.12
    的「字段级两场景替换」只对 `custom_authoritative_ooxml` /
    `opaque_single_onlyoffice` 开放，本 pilot 因此**不会**触发替换，Property 25/26 必跑。
    """
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
        "entry_id": PILOT_ENTRY_ID,
        "pilot_class": PILOT_CLASS,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. per-entry contract
# ═══════════════════════════════════════════════════════════════════════════


def _rows_table_payload() -> dict[str, Any]:
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_FIRST_ROW}",
        "header_rows": 2,
        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
        "delete_policy": "tombstone",
        "footer_anchor": {"marker": FOOTER_MARKER, "search_column": "A"},
        "formula_mask": list(FORMULA_MASK),
        "fields": [
            {
                "stable_field_key": f"{ROWS_TABLE_KEY}/{{row_uuid}}/{column_key}",
                "json_pointer": f"/rows/{{row_uuid}}/{column_key}",
                "column_key": column_key,
                "cell": {"column": column, "row_from": "row_identity"},
                "mode": mode,
                "value_type": value_type,
                "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
                "header_source_ref": _src(header_cell),
            }
            for column_key, column, mode, value_type, header_cell, _label in (
                MANAGED_FIELD_SPECS
            )
        ],
    }


def _meta_table_payload() -> dict[str, Any]:
    return {
        "table_key": META_TABLE_KEY,
        "anchor": f"A{META_LABEL_ROWS[0]}",
        "header_rows": 1,
        "fields": [
            {
                "stable_field_key": f"{META_TABLE_KEY}/{column_key}",
                "json_pointer": f"/meta/{column_key}",
                "column_key": column_key,
                "cell": {"column": value_col, "row_from": row},
                "mode": "editable",
                "value_type": "text",
                "source_ref": _src(f"{value_col}{row}"),
                "header_source_ref": _src(label_cell),
            }
            for column_key, label_cell, value_col, row, _label in META_FIELD_SPECS
        ],
    }


def build_contract_payload() -> dict[str, Any]:
    """本 entry 自己的 per-entry contract canonical payload。

    两个 digest 是**现算的真值**（不是手抄常量）：`template_definition_sha256` 与
    `instrumentation_definition_sha256` 分别是 :func:`template_definition_payload` /
    :func:`instrumentation_definition_payload` 的 canonical digest —— 单向引用，
    payload 里没有任何 bundle 前向引用，也没有自身 hash。
    """
    template_payload = template_definition_payload()
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": PILOT_ADAPTER_ID,
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
                "locator": {"anchor": "excel_table_sheet_association"},
                "tables": [_rows_table_payload(), _meta_table_payload()],
            }
        ],
        "review": {
            "entry_id": PILOT_ENTRY_ID,
            "pilot_class": PILOT_CLASS,
            "authority_root": "backend/wp_templates",
            "reviewed_basis": (
                "openpyxl 逐 sheet 直读权威模板 B/B60-1 审计项目工时预算与控制表.xlsx 的 "
                "受管 sheet B60-1工时预算与控制表：两级表头 5/6 行、数据区 7..23 行、"
                "F 列 =(C+D)*E 公式、A24 合计 footer、3/4 行元信息标签 —— 逐字段 "
                "source_ref/header_source_ref 均指向上述真实单元格"
            ),
        },
    }


def contract_file_path() -> Path:
    """磁盘契约路径（`contracts.contract_path_for` 是唯一拼路径处）。"""
    return contract_path_for(PILOT_ADAPTER_ID)


def load_pilot_contract() -> SyncContract:
    """从磁盘加载并强校验本 pilot 的生产契约。"""
    return load_contract(PILOT_ADAPTER_ID)


def assert_contract_file_matches_source() -> SyncContract:
    """磁盘契约 ↔ 本模块现算 payload **双向**锁死。

    单向（"磁盘能被 parse_contract 接受"）不够：那样改代码不改契约、或改契约不改代码
    都能悄悄漂移，而契约里的 digest 一旦与真实 definition payload 脱钩，
    `assert_contract_identity_frozen` 就只是在比两个都错的值。
    """
    expected = build_contract_payload()
    on_disk = load_pilot_contract()
    if canonical_digest(on_disk.canonical_payload) != canonical_digest(expected):
        raise PilotSelectionError(
            "磁盘 per-entry contract 与本模块现算 payload 不一致 —— "
            f"disk={canonical_digest(on_disk.canonical_payload)} "
            f"source={canonical_digest(expected)}；"
            f"请用 `py -3 backend/scripts/gen/generate_pilot_simple_checklist_contract.py "
            f"--apply` 重生成 {contract_file_path().name}，并复核 diff"
        )
    # 现算 payload 自己也必须过强校验（磁盘对得上但两边都非法时仍要打红）。
    parse_contract(expected, adapter_id=PILOT_ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. 发布（顺序由 Task 12 的 publisher 强制）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class PilotDefinitions:
    """本 pilot 一次完整发布的四个 definition + 一个 non-null bundle。"""

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
            "entry_id": PILOT_ENTRY_ID,
            "adapter_id": PILOT_ADAPTER_ID,
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


async def publish_pilot_definitions(publisher: Any) -> PilotDefinitions:
    """按 `template → instrumentation → contract → bundle` 发布本 entry 自己的身份。

    :param publisher: Task 12 的
        :class:`~app.services.workpaper_sync.definitions.DefinitionPublisher`。
        顺序、payload 校验、DAG 前置与 bundle slot 规范化全部由它负责 —— 本函数只
        编排，不复制判据。

    🔴 authority model 独立先发布：它是 bundle 的必填 child，而 `PUBLISH_DAG` 只管
    template/instrumentation/contract 三段。
    """
    contract = assert_contract_file_matches_source()

    authority = await publisher.publish_definition(
        kind=DefinitionKind.authority_model,
        payload=authority_model_payload(),
        logical_id=f"{PILOT_ADAPTER_ID}.authority-model",
        semantic_version="1.0.0",
    )
    template_payload = template_definition_payload()
    template = await publisher.publish_definition(
        kind=DefinitionKind.template,
        payload=template_payload,
        logical_id=f"{PILOT_ADAPTER_ID}.template",
        semantic_version="1.0.0",
        blob_bytes=read_authoritative_template(),
        structure_hash=template_payload["normalized_structure_hash"],
    )
    instrumentation = await publisher.publish_definition(
        kind=DefinitionKind.instrumentation,
        payload=instrumentation_definition_payload(),
        logical_id=f"{PILOT_ADAPTER_ID}.instrumentation",
        semantic_version="1.0.0",
    )
    contract_definition = await publisher.publish_definition(
        kind=DefinitionKind.contract,
        payload=dict(contract.canonical_payload),
        logical_id=PILOT_ADAPTER_ID,
        semantic_version=contract.semantic_version,
    )
    if template.sha256 != contract.template_definition_sha256:
        raise PilotSelectionError(
            f"已发布 template definition digest {template.sha256} 与契约声明的 "
            f"{contract.template_definition_sha256} 不一致 —— 单向引用断裂"
        )
    if instrumentation.sha256 != contract.instrumentation_definition_sha256:
        raise PilotSelectionError(
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
    return PilotDefinitions(
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
# 7. adapter 注册与宿主接线
# ═══════════════════════════════════════════════════════════════════════════


def build_pilot_matcher() -> EntryMatcher:
    """本 entry 的匹配域（精确 wp_code 集合，不用 glob）。"""
    return EntryMatcher(document_type="xlsx", wp_codes=PILOT_WP_CODES)


def build_pilot_registration(
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    """组一条注册记录。

    `declared_capability` 恒为 `bidirectional`：manifest 侧的 capability 也必须是
    `bidirectional`（overlay 已裁决），两侧不一致时 `registry.register()` 会以
    `FakeBidirectionalError` 或 `RegistrationError` 打红 —— 这条不能靠这里"填对"。
    """
    return AdapterRegistration(
        adapter=adapter,
        entry_id=PILOT_ENTRY_ID,
        matcher=build_pilot_matcher(),
        bundle=bundle,
        descriptor=descriptor,
        room=room,
        declared_capability=Capability.bidirectional,
        contract=contract if contract is not None else load_pilot_contract(),
    )


def register_pilot_adapter(
    registry: WorkpaperSyncAdapterRegistry,
    *,
    adapter: Any,
    bundle: Any,
    descriptor: DescriptorFacts,
    room: RoomFacts,
    contract: SyncContract | None = None,
) -> AdapterRegistration:
    """把本 pilot 注册进 registry（全部准入判据由 `registry.register()` 执行）。"""
    registration = build_pilot_registration(
        adapter=adapter, bundle=bundle, descriptor=descriptor, room=room, contract=contract
    )
    registry.register(registration)
    return registration


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """从已 published representation **现读** :class:`FrozenEntryDefinitions`。

    ═══ Task 75 交付：原先这里 `raise` ═══

    Task 40 交付时这里按「缺公共观测器」的欠账登记 fail closed —— 缺的是
    「published representation artifact → FrozenEntryDefinitions」的公共观测器
    （`ExcelEntryDefinitionLoader.load()` 的四个运行时实测入参当时只有 finalize 时刻的
    candidate evidence 一个来源）。Task 75 把那个观测器建成了
    :mod:`app.services.workpaper_sync.published_identity_observer`，本函数改为**调它**，
    那条欠账登记随之删除（本模块现在一个字都不再提它）。

    唯一实现在
    :func:`~app.services.workpaper_sync.published_identity_observer.observe_published_frozen_definitions`
    —— 四个 pilot 共用同一个观测器，本函数**不复制**它的任何一步判据（复制一份的后果不是
    「更安全」，而是任一侧被短路都不改变行为 ⇒ 变异判 GREEN）。

    `contract` 入参在这里被**消费**而不是摆设：观测器按 representation 上**冻结的**
    `adapter_id` 独立加载磁盘契约，本函数随后把它与本模块 source-locked 的那一份逐 digest
    比对。两侧来源不同（一边是冻结 representation → 磁盘契约，一边是本模块现算 payload），
    因此这是跨来源比对而不是自我比对。

    失败一律上抛（观测器的 `PublishedIdentityObserverError` 子类带 error_code + stage +
    bundle/authority identity + typed child inventory + correlation id）。**绝不**返回
    `None` 或空 identity：返回 `None` 会让上游把「观测失败」表现成「这个 entry 没有身份」，
    而后者会一路静默走到「注册一个没有 identity binding 的 adapter」—— 本 spec 最贵的一类
    缺陷（fail-open 掩盖接线错误）。
    """
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.published_identity_observer import (
        observe_published_frozen_definitions,
    )
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    observation = await observe_published_frozen_definitions(
        session=session,
        resolution=CanonicalResolutionService(
            # 🔴 BP-29：根是 `_BACKEND_ROOT`（= `backend/`）而非 `storage_root()`
        #    —— `relative_path` 自带 `storage/` 前缀，用后者拼出双层路径，读写
        #    错层则 adapter 组装必抛。实测分布 142 : 4，详见分工书 §17.3。
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
        ),
        representation=representation,
        correlation_id=f"{PILOT_ADAPTER_ID}@{getattr(representation, 'id', None)}",
    )
    if observation.definitions.contract.canonical_sha256 != contract.canonical_sha256:
        raise PilotSelectionError(
            f"entry {PILOT_ENTRY_ID}: 观测器按 representation 冻结的 adapter_id 读出的契约 "
            f"digest {observation.definitions.contract.canonical_sha256} 与本模块 "
            f"source-locked 的 "
            f"{contract.canonical_sha256} 不一致 —— 冻结身份与生产契约脱钩，"
            "不得按其中任一侧继续组装 adapter"
        )
    return observation


async def attach_pilot_adapters(
    registry: WorkpaperSyncAdapterRegistry, *, session: Any
) -> tuple[str, ...]:
    """**生产接线点**：把已 published representation 的 pilot entry 接进 registry。

    调用方是 `wp_sync_router`（`_registration` 与 `_apply_durable_incoming`）。返回
    本次成功注册的 adapter_id 元组。

    顺序不可交换，且没有任何 `except: pass`：

    1. `entry_state` 必须已有 **published** representation（Task 36 finalize 之后才有）。
       没有就返回空元组 —— 这不是吞异常，而是"这个 entry 今天还没 finalize"这一事实的
       忠实表达：注册一个没有 published representation 的 adapter 会让 `_registration`
       把 candidate 当成可打开的底稿（AC 6.19 明令禁止）。**今天恒走这一条**。
    2. representation 必须绑定 approved bundle；bundle 快照由
       `CanonicalResolutionService.load_bundle_snapshot` 按 frozen FK 读出，不按 registry
       alias 取"最新版"。
    3. descriptor/room 事实由 `entry_source_facts` 的**实测**观察器给出，不从 manifest
       读回 —— 两侧都读 manifest 时 RG-16/17 退化成自我比对（假绿第③源）。
    4. adapter 组装：由 :func:`resolve_published_frozen_definitions` 现读冻结身份（Task 75 起是真实现，那条欠账登记已删）。
    """
    if PILOT_ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
    )
    from app.services.workpaper_sync.projection_target_resolution import (
        resolve_visible_current_representation_id,
    )
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    # 🔴 BP-27：按 entry 取 current representation 必须**同时**满足「底稿可见」与
    #    「多实例下确定」。`entry_state` 主键是 `(wp_id, entry_id)` ⇒ 同一 entry 在多个
    #    底稿实例上有状态是合法设计；此前四个 pilot 各写一份只按 entry_id 过滤、无
    #    ORDER BY、不看项目软删除的 `.first()`，H1 实测同时命中两行（一条在活项目
    #    `c71b7c54`、一条在已删项目 `f663b18c`）⇒ adapter 可能绑到前端 404 的那份。
    #    可见性口径的唯一真源是 `projection_target_resolution.TARGET_VISIBILITY_SQL`。
    representation_id = await resolve_visible_current_representation_id(
        session, entry_id=PILOT_ENTRY_ID
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
        # 🔴 BP-29：根是 `_BACKEND_ROOT`（= `backend/`）而非 `storage_root()`
        #    —— `relative_path` 自带 `storage/` 前缀，用后者拼出双层路径，读写
        #    错层则 adapter 组装必抛。实测分布 142 : 4，详见分工书 §17.3。
        session, CanonicalArtifactRepository(_BACKEND_ROOT)
    )
    bundle = await resolution.load_bundle_snapshot(representation.definition_bundle_id)
    contract = assert_contract_file_matches_source()
    entry = manifest_entries_by_id(load_entry_manifest())[PILOT_ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise PilotSelectionError(
            f"entry {PILOT_ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）—— "
            "不可达入口不得注册 adapter（Requirement 1.7）"
        )
    assert_manifest_capability_enabled()
    observation = await resolve_published_frozen_definitions(
        session=session, representation=representation, contract=contract
    )
    definitions = observation.definitions
    register_pilot_adapter(
        registry,
        adapter=build_excel_adapter(
            definitions=definitions,
            # 🔴 BP-17：`FrozenEntryDefinitions` **没有** `identity_binding` 字段，
            #    原先这里写 `definitions.identity_binding` ⇒ 观测器一返回就 AttributeError。
            #    binding 由 Task 75 的观测器与 definitions 一起产出（同一份冻结 instrumentation
            #    + 同一份物理列跨度派生），因此两者不可能互相脱钩。
            binding=observation.identity_binding,
            direction="html_to_oo",
        ),
        bundle=bundle,
        descriptor=descriptor,
        room=facts.observe_room_facts(entry),
        contract=contract,
    )
    return (PILOT_ADAPTER_ID,)


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    """manifest 侧 capability/adapter_id 必须已启用（overlay 裁决 + 重生成之后）。

    🔴 **今天必然抛**：任务正文的顺序是「finalize 成 published representation 后，
    **方可**注册 adapter / 接宿主 / 启用 capability」。finalize 被
    **供给**挡住（Task 75 已交付公共观测器；approved bundle / published representation
    两表实测 0 行，生产侧 provisioner 是 Task 76 的交付）⇒ 提前把 overlay 的
    capability 改成 `bidirectional` 就是**跳过顺序**：manifest 会宣称双向可用，而
    registry 里一个 adapter 都没有，`_registration` 只会给 422。
    """
    entry = manifest_entries_by_id(
        manifest if manifest is not None else load_entry_manifest()
    )[PILOT_ENTRY_ID]
    capability = capability_of(entry)
    if capability is not Capability.bidirectional:
        raise PilotSelectionError(
            f"entry {PILOT_ENTRY_ID} 的 manifest capability={capability.value} —— "
            "注册 bidirectional adapter 前必须先由 reviewed overlay 裁决为 bidirectional "
            "并重生成 manifest（RG-18 会以 FakeBidirectionalError 拒绝伪双向）"
        )
    if str(entry.get("adapter_id") or "") != PILOT_ADAPTER_ID:
        raise PilotSelectionError(
            f"entry {PILOT_ENTRY_ID} 的 manifest adapter_id={entry.get('adapter_id')!r} "
            f"与本 pilot 的 {PILOT_ADAPTER_ID!r} 不符"
        )


def _unused_instrumentation_error_guard() -> type[InstrumentationError]:
    """保留 `InstrumentationError` 的显式引用（它是本模块 payload 构建的失败类型）。"""
    return InstrumentationError
