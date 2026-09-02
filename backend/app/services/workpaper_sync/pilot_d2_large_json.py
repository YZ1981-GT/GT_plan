# -*- coding: utf-8 -*-
"""D2 大 JSON 子表 Excel pilot —— **冻结的那一个 D2 entry** 自己的身份、契约与载荷拆分。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 41
Requirements: 6.9, 6.11, 6.12, 12.1, 12.2, 12.10, 14.1, 14.11
Properties: **P27 / P29 / P49 / P60 / P69**

═══ 一、为什么冻结的是 `xlsx/gt-d2-accounts-receivable` ═══

Task 39 的 :func:`~app.services.workpaper_sync.pilot_harness.assess_pilot_classes` 用正则
``(^|[^a-z0-9])d2([^0-9]|$)`` 划出 `d2_large_json` 类，在真实 manifest 上实测**只有 1 个**
候选（`bidirectional` 0 个）—— 没有可选空间，本模块只把它固定下来，并由守卫在
`assess_pilot_classes()` 的真实输出上重新推导。

必要条件逐条现推（不抄 Task 40 的结论 —— 其中第 2 条**形态不同**，见下）：

1. `independent_entry = true`（AC 12.1「每个**独立** entry」）。实测 true、
   `parent_entry_id = None`。
2. **权威模板必须唯一可解且不是「静默回退到别的底稿」**。Task 40 用的判据是
   「wp_code 与 `wp_templates/_index.json` 精确相等」，本 entry **不满足**它 ——
   `wp_match.wp_code_patterns == ["D2A"]`，而索引里三份 D2 模板的 `wp_code` 都是 `D2`。
   但那条判据的**目的**（防止 `find_template_file()` 一路回退到父级程序表、让契约的
   `source_ref` 指向另一份底稿的单元格）在这里由另外三条实测事实同时满足：

   * `find_template_file("D2A")` / `find_template_file_any("D2A")` /
     `find_all_template_files("D2A")` 实测分别是 `None` / `None` / `[]` ——
     `D2A` 既不精确命中、`wp_templates/D` 下没有以 `D2A` 开头的文件、`"-" not in "D2A"`
     所以连子表回退分支都进不去。**零回退的最强形态是"根本没有回退"**。
   * 权威模板由**配置真源**唯一声明：`backend/data/ledger_adapters/wp_render_schema/D2A.yaml`
     的 `template_path` 恰是 :data:`TEMPLATE_RELATIVE_PATH`（该 YAML 是平台渲染 D2A 的
     单一真源，`wp_code: D2A` 与它一一对应）。
   * 该声明与 canonical resolver 一致：`find_template_file("D2")`（父码）实测返回的**正是**
     同一份文件，即声明没有指向"另一份底稿"。

   三条合起来 ⇒ `source_ref` 指向的单元格属于 D2 自己的审定表明细表工作簿。
   :func:`assert_pilot_entry_selectable` 把这三条各写成一个可打红的判据。
3. `scenario_profile.profile_id = xlsx.editable.shared.single.room_service_wired.v1`
   （178 条 entry 的多数形态，与 Task 40 同一形态）⇒ required scenario set 是
   shared+editable 的标准 24 条，不走 authority-model 替换分支，Property 25/26 必跑。
   实测本 entry 的 `required_scenario_set_digest` = ``76d49456…``，与 B60 的
   ``984681c2…`` **不同** —— evidence 按本 bundle 自己的 digest 记录（任务正文要求）。

═══ 二、权威模板只认 `backend/wp_templates/` ═══

:data:`TEMPLATE_RELATIVE_PATH` 指向 ``D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx``
（🔴 文件名里 `D2-4` 与 `应收账款` 之间是**两个空格**，与磁盘逐字一致），
:data:`TEMPLATE_SHA256` 是它的字节哨兵。`基础数据/致同通用审计程序及底稿模板…` 下的同名
文件是**已落后的参考副本**，本模块一次都不读它。:func:`read_authoritative_template`
每次读都比对哨兵，改一个字节就抛（Requirement 9.9：运行时只读）。

工作簿共 **11** 张 sheet：`底稿目录` / `应收账款实质性程序表D2A` / `审定表D2-1` /
`附注披露信息(上市公司）D2-1` / `附注披露信息（国企）D2-1` / `附注披露信息(上市公司)` /
`附注披露信息(国企)` / `明细表D2-2` / `坏账准备明细表D2-3` / `调整分录汇总表D2-4` /
`GT_Custom`。逐 sheet 审核后本契约**只**声明 `明细表D2-2` ——
`excel_extract.managed_tables_of()` 对「受管 sheet 之外还声明了表」显式 fail closed，
一次 extract 只覆盖一张 sheet；而 866KB 的大 JSON 载荷（见 §四）恰好只落在这一张上。

═══ 三、逐字段 source_ref 指向真实单元格（人工审核依据）═══

`明细表D2-2` 的真实网格（openpyxl 直读，dims `A1:AM35`，28 处 merge）：

* **行 11/12 是两级表头**。行 11 给出 24 个列组标题，其中三个横跨 6 列的账龄组
  （`I11:N11 期初审定账龄` / `T11:Y11 期末未审账龄` / `AC11:AH11 期末审定账龄`）
  的二级标题在行 12（`1年以内 / 1-2年 / 2-3年 / 3-4年 / 4-5年 / 5年以上`）；
  其余 21 列都是 `X11:X12` 纵向合并的单级列。故 `header_rows = 2`，
  **21 + 3×6 = 39 列**（A..AM），与 `max_column = 39` 一致。
* **行 13..25 是数据区**（`A25` 是模板占位 `……`）。
* **`Q/S/AB` 三列在数据行里逐行有真公式**：``=E{r}+O{r}-P{r}`` / ``=Q{r}+R{r}`` /
  ``=S{r}+Z{r}+AA{r}`` ⇒ 契约里 `mode=formula` + `formula_mask` 三段区域。
  🔴 `H`（期初审定余额）在模板里**没有**公式（逐格实测），尽管前端
  `useD2Detail.recalcRow()` 把它算成 `priorUnadjusted+priorAje+priorRje` ——
  契约以**源 xlsx** 为准判定 `editable`，并由
  `test_column_h_has_no_formula_in_the_template` 把这条差异钉住：模板哪天真加了公式，
  守卫立刻打红，而不是悄悄让 OO 侧覆盖服务端算的值。
* **`A26 合计` 是 footer**（`E26..AH26` 全是 `SUM(x13:x25)`）⇒
  `footer_anchor = {marker: 合计, search_column: A}`，不写死行号。
* 行 27 `账龄占比` / 行 28 `账龄逻辑校验` / 行 29 `三、审计说明：` / 行 33 `四、审计结论：`
  在受管区域之外，属未管理区域。

隐藏 row UUID 列取 `AN`（`managed_last_col=AM` 右侧第一列，模板里为空）。

═══ 四、866KB 载荷怎么拆：stable field + row UUID，不把整 JSON 当一个字段 ═══

D2 的 HTML store 是 `checklist_responses`（`item_id` → `remark`）。实测真实项目底稿
`wp_id=e2c95d10-181d-4549-8910-d5ab5bc5edd1` 有 **24** 条 `D2-*` item，`remark` 合计
**915,155** 字节，其中 :data:`STORE_ITEM_ID` 一条就占 **906,239** 字节
（885.0 KiB ≈ 0.864 MiB，即 AC 6.12 说的「866KB+」量级），是 **1260 行 × 25 键**
（22 个标量 + 3 个 aging 嵌套对象 × 6 段 ⇒ **每行 40 个叶子**、`rowId` 之外
**39 个受管字段**，与 Excel 的 39 列一一对应）。

🔴 **今天它在库里就是"整 JSON 一个字段"**：整张表是 `D2-detail-rows` 这一条 `remark`
里的一个 JSON 数组字符串。若直接把这条 item 当一个 projection 字段比较，
「任意两行并改」都会形成整表冲突（design §Merge Algorithm 明令禁止的形态）。
本模块提供的拆分就是这条 AC 的实现面：

* :func:`iter_store_rows` —— 流式逐行 yield，**不**二次复制整张结构；
* :func:`split_store_row` —— 一行 → 39 条 `(stable_key, value, spec)`；
* :func:`build_store_projection` —— 逐行喂 `StreamingProjectionBudget`
  （Task 37 的边读边判预算，本模块不写任何阈值数字），产出按
  ``receivable_detail_rows/{rowId}/{column_key}`` 索引的 :class:`Projection`。

行身份取真实载荷里已有的 `rowId`（形如 ``dr-mrgi0qg1-fwwmgum``，实测 1260 行
**零重复、零空值**），因此 `row_identity.json_pointer = /rows/*/rowId`。数组下标
**永不**进入任何 key（Requirement 6.5 / Property 23）。

三源锁死（本模块不是第二个真源，也不自造字段）：

1. **源 xlsx** 行 11/12 的真实表头文本 —— 每个字段的 `header_source_ref` /
   `group_source_ref` 指向具体单元格，守卫用 openpyxl 直读比对；
2. **前端列定义** `useD2DetailColumnPrefs.ts` 的 `FIXED_COLUMNS`（21 个非账龄列，
   顺序与 Excel 列序一致）—— 守卫解析该文件比对键集合与顺序；
3. **账龄段真源** `useAgingConfig.ts` 的 `PRESET_SEGMENTS.FIVE_YEAR`
   （`within1/y1to2/y2to3/y3to4/y4to5/over5` 六段及其 label）—— 守卫比对它与
   行 12 的六个二级表头逐字相等。

═══ 五、顺序与两条登记的上游缺口 ═══

`template → instrumentation → contract → bundle → representation` 的顺序由 Task 12 的
`DefinitionPublisher` 强制，payload 由 Task 17 的 builder 生成 —— 本模块**不**自己拼
payload、不自己算 digest、不自己校验 bundle slot（复制一份的后果不是"更安全"，
而是任一侧被短路都不改变行为 ⇒ 变异检验判 GREEN）。

磁盘契约 ``backend/data/workpaper_sync_contracts/d2.receivable_detail.json`` 与本模块
现算 payload **双向锁死**（:func:`assert_contract_file_matches_source`），且两个生产入口
（:func:`publish_pilot_definitions` / :func:`attach_pilot_adapters`）**都**必须经这把锁 ——
Task 40 实测过「守卫自己调锁、从不检查生产路径」会让整组变异判 GREEN。

两条缺口按 Task 40 的处置办：**fail closed 抛可分辨异常，绝不返回 `None`**，
adapter 不注册、capability 不启用、manifest digest 不变，「契约孤儿」进
`registry.build_report().contract_files_without_adapter` 当可见欠账。

【已于 Task 75 结清】原第一条缺口「缺 published representation artifact →
`FrozenEntryDefinitions` 的公共观测器」已由
:mod:`app.services.workpaper_sync.published_identity_observer` 交付，登记常量已删除。
今天挡住 finalize 的是**供给**：approved bundle / published representation 两表实测
0 行，生产侧 provisioner 是 Task 76 的交付。
* :data:`UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY` —— **本任务新发现**：
  AC 6.9 自己的场景 `dynamic_row_add_delete_reorder_copy`（`evidence.DYNAMIC_SCENARIOS`，
  生产落点 `excel_extract.extract_projection`）只在
  `scenario_profile.mount_cardinality == "dynamic"` 时进 required set，而那个字段量的是
  **前端宿主挂载基数**（`v-for` 挂多个 OO 编辑器），不是「受管表有没有动态行」。
  实测全 manifest 186 条 entry 里 `dynamic` **只有 1 条**且是 **docx**
  （`docx/gt-wp-renderer`）⇒ 该场景对**任何 xlsx entry** 结构性不可达，
  包括 AC 6.9 / 6.12 点名的 D2 本身（其契约声明了 `row_identity` + `delete_policy`、
  真实载荷 1260 行）以及 Tasks 42/43 的 H1 / G7。这正是「additive 注入即死代码」那类
  假绿：场景登记着、分母里永远没有它。本任务不改 `evidence` 的推导（那需要把 contract
  喂进 `derive_for_manifest_entry`，会同时改动 H1/G7 的 required set digest，属设计级
  变更），而是把它登记成**可打红的实测事实**
  （:func:`assert_dynamic_family_is_unreachable_for_xlsx_entries`），并把 Property 27
  落到 required set 里真实存在的 merge 家族两条场景上，用真实 1260 行载荷跑 oracle。
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

__all__ = [
    "AGING_GROUPS",
    "AGING_SEGMENTS",
    "AUTHORITY_MODEL",
    "FIRST_DATA_ROW",
    "FOOTER_MARKER",
    "FOOTER_ROW",
    "FORMULA_MASK",
    "FORMULA_TEMPLATES",
    "HEADER_GROUP_ROW",
    "HEADER_LEAF_ROW",
    "LAST_DATA_ROW",
    "MANAGED_FIELD_SPECS",
    "MANAGED_LAST_COL",
    "MANAGED_SHEET",
    "PILOT_ADAPTER_ID",
    "PILOT_CLASS",
    "PILOT_ENTRY_ID",
    "PILOT_WP_CODES",
    "RENDER_SCHEMA_RELATIVE_PATH",
    "ROWS_TABLE_KEY",
    "ROW_IDENTITY_STORE_KEY",
    "SCALAR_FIELD_SPECS",
    "SHEET_KEY",
    "STORE_ITEM_ID",
    "TABLE_NAME",
    "TEMPLATE_ID",
    "TEMPLATE_RELATIVE_PATH",
    "TEMPLATE_SHA256",
    "UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP",
    "UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY",
    "UUID_COL",
    "PilotDefinitions",
    "PilotSelectionError",
    "StorePayloadError",
    "TemplateResolutionFacts",
    "assert_contract_file_matches_source",
    "assert_dynamic_family_is_unreachable_for_xlsx_entries",
    "assert_no_implicit_template_fallback",
    "assert_manifest_capability_enabled",
    "assert_pilot_entry_selectable",
    "attach_pilot_adapters",
    "authoritative_template_path",
    "authority_model_payload",
    "build_contract_payload",
    "build_pilot_matcher",
    "build_pilot_registration",
    "build_store_projection",
    "contract_file_path",
    "excel_carrier_gate",
    "instrumentation_definition_payload",
    "instrumentation_spec",
    "iter_store_rows",
    "load_pilot_contract",
    "manifest_capability_enabled",
    "publish_pilot_definitions",
    "read_authoritative_template",
    "register_pilot_adapter",
    "render_schema_template_path",
    "resolve_published_frozen_definitions",
    "split_store_row",
    "stable_key_for",
    "store_row_identity",
    "template_definition_payload",
]


class PilotSelectionError(SyncDomainError):
    """冻结的 pilot entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_pilot_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 大 JSON 载荷形态不合法（非数组、缺 row identity、重复 identity）。

    刻意与 :class:`PilotSelectionError` 分型：「选型漂移」与「载荷坏了」是两类完全不同的
    故障，合并成一个错误码会让较早的分支永久不可达（本 spec 已实测 3 次的形态）。
    """

    error_code = "sync_pilot_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的身份常量
# ═══════════════════════════════════════════════════════════════════════════

#: 本 pilot 覆盖的 AC 12.2 四类之一（与 `pilot_harness.PilotClass` 同域）。
PILOT_CLASS: Final[str] = "d2_large_json"

#: 从 source-backed manifest 冻结的 entry（`assess_pilot_classes()` 的唯一 D2 候选）。
PILOT_ENTRY_ID: Final[str] = "xlsx/gt-d2-accounts-receivable"

#: adapter_id == contract_id == 契约文件名（registry RG-4 双向锁死）。
PILOT_ADAPTER_ID: Final[str] = "d2.receivable_detail"

#: matcher 的 wp_code 集合 —— 取自本 entry 的 `wp_match.wp_code_patterns`。
PILOT_WP_CODES: Final[frozenset[str]] = frozenset({"D2A"})

#: `backend/wp_templates/` 下的权威模板（🔴 `D2-4` 与 `应收账款` 之间是两个空格）。
TEMPLATE_RELATIVE_PATH: Final[str] = (
    "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx"
)

#: 权威模板字节哨兵（Requirement 9.9：`backend/wp_templates/` 运行时只读）。
TEMPLATE_SHA256: Final[str] = (
    "31e7992ba1e83952620e1777d108b46f7e7817dcdc9484c07f079f1dd3af0afa"
)

#: 声明权威模板的**配置真源**（`wp_code: D2A` ↔ `template_path` 一一对应）。
RENDER_SCHEMA_RELATIVE_PATH: Final[str] = (
    "backend/data/ledger_adapters/wp_render_schema/D2A.yaml"
)

#: 受管 sheet 的真实 tab 名（构建期选择器；运行时定位一律走 identity 锚点）。
MANAGED_SHEET: Final[str] = "明细表D2-2"

#: instrumentation 的模板短码（进 row UUID 前缀与 `GT_*` defined names）。
TEMPLATE_ID: Final[str] = "D22"

#: 契约 sheet_key —— 必须与 `build_instrumentation_payload` 产出的
#: `managed_sheets[0].sheet_key`（`f"{template_id.lower()}-managed"`）一致。
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"

ROWS_TABLE_KEY: Final[str] = "receivable_detail_rows"

#: 数据区与 footer（逐 sheet 读权威模板得来，见模块 docstring §三）。
FIRST_DATA_ROW: Final[int] = 13
LAST_DATA_ROW: Final[int] = 25
FOOTER_ROW: Final[int] = 26

#: 两级表头的两行：组标题在 11、账龄二级标题在 12。
HEADER_GROUP_ROW: Final[int] = 11
HEADER_LEAF_ROW: Final[int] = 12

#: 最后一列受管业务列（`AM 备注`）与隐藏 row UUID 列（必须在其右侧）。
MANAGED_LAST_COL: Final[str] = "AM"
UUID_COL: Final[str] = "AN"

#: 注入的 Excel Table displayName（OOXML 要求字母/下划线开头、无空格）。
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"

#: 本 pilot 是 projection-based ⇒ 三个 typed child 全部必须是 approved definition。
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: 三个公式列的只读区域（逐格实测 `=E+O-P` / `=Q+R` / `=S+Z+AA`）。
FORMULA_MASK: Final[tuple[str, ...]] = (
    f"Q{FIRST_DATA_ROW}:Q{LAST_DATA_ROW}",
    f"S{FIRST_DATA_ROW}:S{LAST_DATA_ROW}",
    f"AB{FIRST_DATA_ROW}:AB{LAST_DATA_ROW}",
)

#: 公式列 → 数据行公式模板（`{r}` 为行号）。守卫逐行与权威模板比对。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "Q": "=E{r}+O{r}-P{r}",
    "S": "=Q{r}+R{r}",
    "AB": "=S{r}+Z{r}+AA{r}",
}

#: footer 定位标记（`A26` 的真实文本）。
FOOTER_MARKER: Final[str] = "合计"

#: HTML store 里承载整张大表的那一条 item（`checklist_responses.item_id`）。
STORE_ITEM_ID: Final[str] = "D2-detail-rows"

#: 载荷里每行自带的稳定行身份键（形如 `dr-mrgi0qg1-fwwmgum`）。
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: 三个账龄组：`(json 前缀, 组标题单元格, 六列列标, 组标题文本)`。
AGING_GROUPS: Final[tuple[tuple[str, str, tuple[str, ...], str], ...]] = (
    ("agingPrior", f"I{HEADER_GROUP_ROW}", ("I", "J", "K", "L", "M", "N"), "期初审定账龄"),
    ("agingCurrent", f"T{HEADER_GROUP_ROW}", ("T", "U", "V", "W", "X", "Y"), "期末未审账龄"),
    (
        "agingAudited",
        f"AC{HEADER_GROUP_ROW}",
        ("AC", "AD", "AE", "AF", "AG", "AH"),
        "期末审定账龄",
    ),
)

#: 五年段账龄的 `(段 key, 行 12 的二级表头文本)` —— 与前端
#: `useAgingConfig.PRESET_SEGMENTS.FIVE_YEAR` 同序同值（守卫解析该文件比对）。
AGING_SEGMENTS: Final[tuple[tuple[str, str], ...]] = (
    ("within1", "1年以内"),
    ("y1to2", "1-2年"),
    ("y2to3", "2-3年"),
    ("y3to4", "3-4年"),
    ("y4to5", "4-5年"),
    ("over5", "5年以上"),
)

#: 21 个非账龄列：`(column_key, 列标, mode, value_type, json 路径, 行 11 表头文本)`。
#:
#: 🔴 **顺序即 Excel 列序**，并且与前端 `FIXED_COLUMNS` 的键序**逐项相同**
#: （守卫解析 `useD2DetailColumnPrefs.ts` 比对）。`json 路径`是 store 行对象里的键名
#: （camelCase，来自 `useD2Detail.DetailRow`），`column_key` 是契约侧的小写稳定键。
SCALAR_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("seq", "A", "editable", "integer", "seq", "序号"),
    ("customer_name", "B", "editable", "text", "customerName", "客户名称"),
    ("company_code", "C", "editable", "text", "companyCode", "公司代码"),
    ("relation_type", "D", "editable", "enum", "relationType", "关联方类型"),
    ("prior_unadjusted", "E", "editable", "amount", "priorUnadjusted", "期初未审余额"),
    ("prior_aje", "F", "editable", "amount", "priorAje", "期初账项调整"),
    ("prior_rje", "G", "editable", "amount", "priorRje", "期初重分类调整"),
    ("prior_audited", "H", "editable", "amount", "priorAudited", "期初审定余额"),
    ("debit_occurrence", "O", "editable", "amount", "debitOccurrence", "借方发生"),
    ("credit_occurrence", "P", "editable", "amount", "creditOccurrence", "贷方发生"),
    ("end_balance", "Q", "formula", "amount", "endBalance", "期末余额"),
    (
        "reclassification",
        "R",
        "editable",
        "amount",
        "reclassification",
        "被审计单位重分类调整",
    ),
    (
        "current_unadjusted",
        "S",
        "formula",
        "amount",
        "currentUnadjusted",
        "期末未审余额",
    ),
    ("current_aje", "Z", "editable", "amount", "currentAje", "账项调整"),
    ("current_rje", "AA", "editable", "amount", "currentRje", "重分类调整"),
    ("current_audited", "AB", "formula", "amount", "currentAudited", "期末审定余额"),
    (
        "credit_risk_classification",
        "AI",
        "editable",
        "enum",
        "creditRiskClassification",
        "信用风险组合方式",
    ),
    ("group_name", "AJ", "editable", "text", "groupName", "组合名称"),
    ("is_confirmation", "AK", "editable", "boolean", "isConfirmation", "是否函证"),
    ("post_payment", "AL", "editable", "amount", "postPayment", "期后回款"),
    ("remark", "AM", "editable", "text", "remark", "备注"),
)


def _col_index(letters: str) -> int:
    """A1 列标 → 1-based 列序号（`AM` → 39）。"""
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index


def _snake(camel: str) -> str:
    out: list[str] = []
    for char in camel:
        if char.isupper():
            out.append("_")
            out.append(char.lower())
        else:
            out.append(char)
    return "".join(out)


def _aging_field_specs() -> tuple[tuple[str, str, str, str, str, str], ...]:
    """三个账龄组展开成 18 条 spec（形态与 :data:`SCALAR_FIELD_SPECS` 相同）。

    展开而不是「写死 18 行」：段清单来自 :data:`AGING_SEGMENTS`（前端账龄真源的投影），
    列标来自 :data:`AGING_GROUPS`，任一侧变化都必须两边一起动。
    """
    out: list[tuple[str, str, str, str, str, str]] = []
    for json_prefix, _group_cell, columns, _group_label in AGING_GROUPS:
        if len(columns) != len(AGING_SEGMENTS):
            raise PilotSelectionError(
                f"账龄组 {json_prefix} 声明了 {len(columns)} 列，段清单有 "
                f"{len(AGING_SEGMENTS)} 段 —— 列与段必须一一对应"
            )
        prefix_key = _snake(json_prefix)
        for column, (segment_key, leaf_label) in zip(columns, AGING_SEGMENTS):
            out.append(
                (
                    f"{prefix_key}_{segment_key.lower()}",
                    column,
                    "editable",
                    "amount",
                    f"{json_prefix}/{segment_key}",
                    leaf_label,
                )
            )
    return tuple(out)


#: **39 个受管字段** = 21 个标量列 + 18 个账龄列，按 Excel 列序（A → AM）排列。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = tuple(
    sorted(SCALAR_FIELD_SPECS + _aging_field_specs(), key=lambda row: _col_index(row[1]))
)

#: `column_key` → 该字段的**组标题单元格**（只有账龄列有；标量列为空串）。
GROUP_HEADER_CELLS: Final[Mapping[str, str]] = {
    f"{_snake(json_prefix)}_{segment_key.lower()}": group_cell
    for json_prefix, group_cell, _columns, _label in AGING_GROUPS
    for segment_key, _leaf in AGING_SEGMENTS
}

#: `column_key` → 组标题文本（守卫与源 xlsx 比对）。
GROUP_HEADER_LABELS: Final[Mapping[str, str]] = {
    f"{_snake(json_prefix)}_{segment_key.lower()}": group_label
    for json_prefix, _group_cell, _columns, group_label in AGING_GROUPS
    for segment_key, _leaf in AGING_SEGMENTS
}


# ═══════════════════════════════════════════════════════════════════════════
# 2. 权威模板
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_REPO_ROOT: Final[Path] = _BACKEND_ROOT.parent


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


def render_schema_template_path(*, payload: Mapping[str, Any] | None = None) -> str:
    """`D2A.yaml` 里声明的 `template_path`（配置真源，不在本模块复制字面量判定）。

    这条读取存在的意义是让「权威模板由配置唯一声明」成为**运行时可打红的事实**：
    YAML 改指到另一份工作簿，:func:`assert_pilot_entry_selectable` 立刻失败，
    而不是等到契约的 source_ref 已经指向别的底稿才被人发现。

    :param payload: 已解析的 schema。默认现读磁盘 —— 这个参数只为让「配置的 wp_code 与本
        pilot 的 matcher 域脱钩」这一分支可测（否则它对真实数据结构性不可达，永久 GREEN）。
    """
    import yaml

    path = _REPO_ROOT / RENDER_SCHEMA_RELATIVE_PATH
    if payload is None:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError as exc:
            raise PilotSelectionError(f"D2A 渲染 schema 不可读: {path}: {exc}") from exc
    if str(payload.get("wp_code") or "") not in PILOT_WP_CODES:
        raise PilotSelectionError(
            f"{RENDER_SCHEMA_RELATIVE_PATH} 的 wp_code={payload.get('wp_code')!r} 不在本 "
            f"pilot 的 matcher 域 {sorted(PILOT_WP_CODES)} 内 —— 配置真源与 entry 脱钩"
        )
    return str(payload.get("template_path") or "")


# ═══════════════════════════════════════════════════════════════════════════
# 3. 选型必要条件（在真实 manifest / 真实 resolver 上重新推导，不抄结论）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    """`wp_template_finder` 的**实测**解析结果，由调用方提供。

    🔴 为什么不在本模块直接调 `find_template_file*`：Task 19 的 AST 清册把
    `find_template_file` / `find_template_file_any` 列为 **non-canonical resolver 符号**
    （`generate_workpaper_writer_inventory._RESOLVER_SYMBOLS`），生产模块里出现它们会给
    Task 20 的收口门增一条 `unadjudicated_resolver` + 一条 `non_canonical_resolver_only`
    欠账 —— 实测本函数原本被判成 `writer_resolver`（`.replace` 还被当成 artifact write）。
    Task 40 已为同类形态付过一次代价，正解是让那一行从清册里**整行消失**。

    这里需要的是「解析结果」这一**事实**，不是「谁去解析」：调用方（契约生成器与守卫）
    用真实 finder 取事实，本模块只做判定。判定被短路时守卫立刻打红。

    :param by_wp_code: `wp_code → 三个 finder 入口解析出的路径`（本 pilot 要求**全空**）
    :param parent_code: 父码（`D2A` → `D2`）
    :param parent_resolved_path: 父码的 canonical resolver 落点（要求 == 权威模板）
    """

    by_wp_code: Mapping[str, Sequence[Any]]
    parent_code: str
    parent_resolved_path: Any


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
    """本 pilot 的每个 wp_code 在 finder 上都必须解析不到任何文件；父码必须落在权威模板。"""
    missing = sorted(wp_codes - set(resolution.by_wp_code))
    if missing:
        raise PilotSelectionError(
            f"缺少 wp_code {missing} 的 finder 实测结果 —— 零回退判据不得对未观测的码放行"
        )
    leaked = {
        code: [str(item) for item in hits if item]
        for code, hits in resolution.by_wp_code.items()
        if any(hits)
    }
    if leaked:
        raise PilotSelectionError(
            f"wp_code {sorted(leaked)} 在 `wp_template_finder` 上解析到了 {leaked} —— "
            "本 pilot 的零回退判据要求它们**全部**解析不到任何文件（`D2A` 无自有模板、"
            "无同前缀文件、非子码形态），否则契约的 source_ref 可能指向另一份底稿的单元格"
            "（本 spec 已付两次学费的形态）"
        )
    resolved = resolution.parent_resolved_path
    if resolved is None or Path(str(resolved)).resolve() != authoritative_template_path().resolve():
        raise PilotSelectionError(
            f"父码 {resolution.parent_code!r} 的 canonical resolver 落在 {resolved} —— "
            f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件，"
            "说明配置声明指向了另一份底稿"
        )


def assert_pilot_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
    declared_template_path: str | None = None,
) -> Mapping[str, Any]:
    """在**真实** manifest / 真实 resolver 事实上重新推导三条必要条件；任一不成立即抛。

    :param resolution: 见 :class:`TemplateResolutionFacts`。**必填**（没有默认值 ⇒
        不可能出现「没给就跳过」的 fail-open）。
    :param declared_template_path: `D2A.yaml` 声明的 `template_path`。默认现读配置 ——
        这个参数只为让「配置指到别的工作簿」这一分支可测（否则它对真实数据结构性不可达，
        即永久 GREEN）。
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

    assessment = assess_pilot_classes(manifest=payload)[PilotClass.d2_large_json]
    if PILOT_ENTRY_ID not in assessment.candidate_entry_ids:
        raise PilotSelectionError(
            f"{PILOT_ENTRY_ID!r} 不在 assess_pilot_classes() 的 d2_large_json 候选里"
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

    # ── ②-a 本 entry 的 wp_code 在运行时**没有**任何隐式回退（含父码落点）──────
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))

    # ── ②-b 权威模板由配置真源唯一声明 ──────────────────────────────────────
    declared = (
        declared_template_path
        if declared_template_path is not None
        else render_schema_template_path()
    )
    expected = f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}"
    if "/".join(str(declared).split("\\")) != expected:
        raise PilotSelectionError(
            f"{RENDER_SCHEMA_RELATIVE_PATH} 声明的 template_path={declared!r} 与本 pilot "
            f"冻结的权威模板 {expected!r} 不一致 —— 契约的每个 source_ref 都指向后者的"
            "具体单元格，配置指到别处即为「据另一份底稿建契约」"
        )
    return entry


def assert_dynamic_family_is_unreachable_for_xlsx_entries(
    *, manifest: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    """把 :data:`UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY` 变成实测事实。

    返回 `{"xlsx_dynamic": [...], "dynamic": [...], "total": N}`。判据是**结构性的**：
    `evidence.derive_for_manifest_entry` 只按 `scenario_profile.mount_cardinality ==
    "dynamic"` 追加 `DYNAMIC_SCENARIOS`，所以只要 xlsx 侧该取值为空集，AC 6.9 自己的场景
    就对全部 xlsx entry 不可达。

    🔴 这条**不是**「断言缺口存在所以别管了」：它是欠账的可打红形态 —— 上游哪天把门改成
    按 contract 的 `row_identity` 判定（或给本 entry 的 profile 打上 dynamic），
    `xlsx_dynamic` 就不再是空集，本函数抛错，欠账登记必须同步撤销。
    """
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    dynamic: list[str] = []
    xlsx_dynamic: list[str] = []
    for entry_id, entry in sorted(entries.items()):
        profile = entry.get("scenario_profile") or {}
        if str(profile.get("mount_cardinality") or "") != "dynamic":
            continue
        dynamic.append(entry_id)
        if str(entry.get("document_type") or "") == "xlsx":
            xlsx_dynamic.append(entry_id)
    if xlsx_dynamic:
        raise PilotSelectionError(
            "已有 xlsx entry 的 scenario_profile.mount_cardinality=dynamic："
            f"{xlsx_dynamic} —— `dynamic_row_add_delete_reorder_copy` 不再对 xlsx 侧"
            "结构性不可达，"
            f"{UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY!r} 这条欠账必须撤销，"
            "并把 Property 27 的落点改到该场景上"
        )
    return {"dynamic": tuple(dynamic), "xlsx_dynamic": (), "total": len(entries)}


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
    `opaque_single_onlyoffice` 开放，本 pilot 因此**不会**触发替换，Property 25/26 必跑
    ——「不把整 JSON 当一个字段」正是靠 `merge_model=stable_field_three_way` 表达。
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


def _src(cell: str) -> str:
    """`source_ref` 的统一形态：权威源 xlsx 的 `sheet!单元格`。"""
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """`receivable_detail_rows/{row_uuid}/{column_key}` 的唯一拼装处。"""
    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"


def _rows_table_payload() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, json_path, leaf_label in MANAGED_FIELD_SPECS:
        spec: dict[str, Any] = {
            "stable_field_key": stable_key_for(column_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(
                f"{column}{HEADER_LEAF_ROW if column_key in GROUP_HEADER_CELLS else HEADER_GROUP_ROW}"
            ),
            "store_item_id": STORE_ITEM_ID,
            "header_text": leaf_label,
        }
        group_cell = GROUP_HEADER_CELLS.get(column_key)
        if group_cell:
            spec["group_source_ref"] = _src(group_cell)
            spec["group_header_text"] = GROUP_HEADER_LABELS[column_key]
        fields.append(spec)
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{HEADER_GROUP_ROW}",
        "header_rows": 2,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        "footer_anchor": {"marker": FOOTER_MARKER, "search_column": "A"},
        "formula_mask": list(FORMULA_MASK),
        "fields": fields,
    }


def build_contract_payload() -> dict[str, Any]:
    """本 entry 自己的 per-entry contract canonical payload。

    两个 digest 是**现算的真值**（不是手抄常量）：`template_definition_sha256` 与
    `instrumentation_definition_sha256` 分别是 :func:`template_definition_payload` /
    :func:`instrumentation_definition_payload` 的 canonical digest —— 单向引用，
    payload 里没有任何 bundle 前向引用，也没有自身 hash。
    """
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

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
                "locator": {"anchor": TABLE_SHEET_ANCHOR},
                "tables": [_rows_table_payload()],
            }
        ],
        "review": {
            "entry_id": PILOT_ENTRY_ID,
            "pilot_class": PILOT_CLASS,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_id": STORE_ITEM_ID,
                "row_identity_key": ROW_IDENTITY_STORE_KEY,
                "shape": "json_array_of_row_objects",
                "note": (
                    "整张表今天存成这一条 item 的 remark（一个 JSON 数组字符串）。"
                    "本契约按 stable field + row UUID 拆开，禁止把整 JSON 当一个字段比较"
                    "（AC 6.9 / 6.12 / design §Merge Algorithm）"
                ),
            },
            "reviewed_basis": (
                "openpyxl 逐 sheet 直读权威模板 "
                "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx 的 11 张 sheet，"
                "只取受管 sheet 明细表D2-2：两级表头 11/12 行（三个账龄组各横跨 6 列、"
                "其余 21 列纵向合并）、数据区 13..25 行、Q/S/AB 三列逐行公式 "
                "=E+O-P / =Q+R / =S+Z+AA、H 列模板内无公式故判 editable、A26 合计 footer；"
                "39 个字段的 source_ref / header_source_ref / group_source_ref 均指向上述"
                "真实单元格，字段键集合与前端 useD2DetailColumnPrefs.FIXED_COLUMNS 及 "
                "useAgingConfig.PRESET_SEGMENTS.FIVE_YEAR 三源锁死"
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
            "请用 `py -3 backend/scripts/gen/generate_pilot_d2_large_json_contract.py "
            f"--apply` 重生成 {contract_file_path().name}，并复核 diff"
        )
    # 现算 payload 自己也必须过强校验（磁盘对得上但两边都非法时仍要打红）。
    parse_contract(expected, adapter_id=PILOT_ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 6. 866KB 载荷拆分（stable field + row UUID，流式）
# ═══════════════════════════════════════════════════════════════════════════


def store_row_identity(row: Mapping[str, Any], *, ordinal: int) -> str:
    """取一行的稳定行身份。空/非字符串即抛 —— **绝不**退回数组下标。

    :param ordinal: 只用于错误文案定位（0-based），**不**参与身份构造。
        Requirement 6.5 / Property 23：下标绝不可作持久化身份。
    """
    raw = row.get(ROW_IDENTITY_STORE_KEY)
    if not isinstance(raw, str) or not raw.strip():
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 第 {ordinal} 行缺少稳定行身份 "
            f"{ROW_IDENTITY_STORE_KEY!r}（实得 {raw!r}）—— 不得退回数组下标作身份"
            "（Requirement 6.5 / Property 23）"
        )
    return raw.strip()


def iter_store_rows(payload: str | bytes | Sequence[Any]) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """流式 yield `(row_identity, row)`；重复身份即抛。

    接受三种输入形态（都是真实调用点）：`checklist_responses.remark` 的原始字符串、
    从库里以 bytes 读出的同一串、以及已解析好的数组（pg 侧守卫复用同一份解析结果时）。

    ⚠️ 这里刻意**不**把 39×N 个字段一次性建成 dict —— 那正是 Requirement 6.12 要防的
    「复制多份 866KB+ 结构」。调用方按行消费即可。
    """
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 的 remark 不是合法 JSON: {exc}"
            ) from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 的载荷必须是行对象数组，实得 {type(rows).__name__} —— "
            "整张大表被存成别的形态时必须 fail closed，不得静默当成零行"
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
                f"{STORE_ITEM_ID} 出现重复行身份 {identity!r}（第 {ordinal} 项）—— "
                "复制产生的重复 UUID 默认是结构冲突，不得静默合并成一行"
                "（Requirement 6.15）"
            )
        seen.add(identity)
        yield identity, row


def _resolve_json_path(row: Mapping[str, Any], json_path: str) -> Any:
    """按 `agingPrior/within1` 这类路径取值；缺失返回 `None`（不猜、不造）。"""
    cursor: Any = row
    for segment in json_path.split("/"):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(segment)
    return cursor


def split_store_row(
    row: Mapping[str, Any], *, row_identity: str, contract: SyncContract
) -> Iterator[tuple[str, Any, FieldSpec]]:
    """一行 → 39 条 `(stable_key, value, spec)`。

    `spec` 从 **contract** 取（`field_by_stable_key` 对未登记键直接抛），因此这里写错
    一个 column_key 会立刻炸，而不是静默产出一个契约里没有的字段。
    """
    for column_key, _column, _mode, _vt, json_path, _label in MANAGED_FIELD_SPECS:
        spec = contract.field_by_stable_key(stable_key_for(column_key))
        yield (
            stable_key_for(column_key, row_identity),
            _resolve_json_path(row, json_path),
            spec,
        )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """把 HTML store 的大 JSON 载荷拆成按 stable field key 索引的 :class:`Projection`。

    行/field 预算由 Task 37 的 :class:`StreamingProjectionBudget` **边读边判**
    （本函数不含任何阈值数字）；越界即 `BudgetExceededError`，不截断、不静默丢行。
    """
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


# ═══════════════════════════════════════════════════════════════════════════
# 7. 发布（顺序由 Task 12 的 publisher 强制）
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
# 8. adapter 注册与宿主接线
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
    `bidirectional`（overlay 裁决后），两侧不一致时 `registry.register()` 会打红 ——
    这条不能靠这里"填对"。
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


#: 🔴 **登记的上游缺口 ②（本任务新发现）**：AC 6.9 自己的场景对 xlsx entry 结构性不可达。
#:
#: 由 :func:`assert_dynamic_family_is_unreachable_for_xlsx_entries` 把它变成可打红的
#: 实测事实；缺口一旦被上游修掉，那个函数会抛错，提醒撤销本条登记。
UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY: Final[str] = (
    "Task 41 欠账：`evidence.derive_for_manifest_entry` 只在 "
    "`scenario_profile.mount_cardinality == \"dynamic\"` 时追加 DYNAMIC_SCENARIOS，而该"
    "字段量的是**前端宿主挂载基数**（v-for 挂几个 OO 编辑器），不是「受管表有没有动态"
    "行」。实测全 manifest 只有 1 条 entry 为 dynamic 且是 docx ⇒ AC 6.9 自己的场景 "
    "`dynamic_row_add_delete_reorder_copy`（生产落点 excel_extract.extract_projection）"
    "对**任何 xlsx entry** 都进不了 required set，包括 AC 6.9/6.12 点名的 D2 与 Tasks "
    "42/43 的 H1/G7。修法需要把 contract 的 row_identity 声明喂进 required-set 推导"
    "（会改动 H1/G7 的 required digest），属设计级变更。owner 建议归 evidence 推导侧"
    "（Task 39 后续）；在此之前 Property 27 落在 merge 家族两条场景上，用真实 1260 行"
    "载荷跑 delete/update oracle"
)


#: 🔴 **登记的上游缺口 ③（本任务新发现）**：`value_type=boolean` 的 Excel 格在平台上
#: **端到端不自洽**，每行都会产生一条 `type_normalization_failure` schema 冲突。
#:
#: 实测链条（三段各自可打红，见守卫 `TestBooleanCellIsAKnownUpstreamIncoherence`）：
#:
#: 1. `excel_materialize._write_kind_for()` 把 `ValueType.boolean` 归到
#:    `CellWriteKind.number_literal`，`_render_number(True)` 渲染成 ``1``
#:    ⇒ 落盘形态是 ``<c r="AK13"><v>1</v></c>``（没有 `t="b"`）；
#: 2. extract 用 openpyxl 读回得到 **int 1**；
#: 3. `merge.normalize_value(1, ValueType.boolean)` 明令拒绝（「0/1 与 'True' 都不折叠」）
#:    ⇒ 每一行的该字段都变成 `type_normalization_failure`。
#:
#: 本 pilot **不**为绕开它而改 value_type：`is_confirmation` 的类型真源是前端
#: `useD2Detail.DetailRow.isConfirmation: boolean`，改成 `text`/`enum` 就得在拆分里
#: 自造一个 bool→"是/否" 映射（无来源自造字段，Requirement 6.1 明令禁止）。
#: 正确修法在 engine 侧二选一：`_write_kind_for` 对 boolean 走 `t="b"` 布尔格，
#: 或 `normalize_value` 对 boolean 折叠 0/1。owner 建议归 Task 37/38 后续。
UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP: Final[str] = (
    "Task 41 欠账：`value_type=boolean` 的 Excel 受管格端到端不自洽 —— materialize 按 "
    "number_literal 写 `<v>1</v>`（无 t=\"b\"），extract 读回 int 1，而 "
    "`merge.normalize_value` 对 boolean 拒绝 0/1 折叠 ⇒ 每行一条 "
    "type_normalization_failure schema 冲突。本 entry 唯一的 boolean 列是 "
    "`is_confirmation`（AK 是否函证），类型真源是前端 DetailRow.isConfirmation，"
    "不得为绕开缺口自造 bool→文本映射。修法二选一：`excel_materialize._write_kind_for` "
    "对 boolean 写真布尔格，或 `merge.normalize_value` 对 boolean 折叠 0/1。"
    "owner 建议归 engine 侧（Task 37/38 后续）"
)


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """从已 published representation **现读** :class:`FrozenEntryDefinitions`。

    ═══ Task 75 交付：原先这里 `raise` ═══

    Task 41 交付时这里按「缺公共观测器」的欠账登记 fail closed —— 缺的是
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
    """**生产接线点**：把已 published representation 的本 pilot entry 接进 registry。

    调用方是 `wp_sync_router`（`_attach_pilot_adapters` 与 `_apply_durable_incoming`）。
    返回本次成功注册的 adapter_id 元组。顺序不可交换，且没有任何 `except: pass`：

    1. manifest capability 必须**已启用**。没启用就返回空元组并且**一次库都不读** ——
       这不是吞异常，而是"这个 entry 今天还不是双向 pilot"这一事实的忠实表达
       （见下方注释里 Task 28 实测的教训）。**今天恒走这一条**。
    2. `entry_state` 必须已有 **published** representation（Task 36 finalize 之后才有）。
       没有同样返回空元组：注册一个没有 published representation 的 adapter 会让
       `_registration` 把 candidate 当成可打开的底稿（AC 6.19 明令禁止）。
    3. representation 必须绑定 approved bundle；bundle 快照由
       `CanonicalResolutionService.load_bundle_snapshot` 按 frozen FK 读出。
    4. descriptor/room 事实由 `entry_source_facts` 的**实测**观察器给出，不从 manifest
       读回 —— 两侧都读 manifest 时 RG-16/17 退化成自我比对（假绿第③源）。
    5. adapter 组装：由 :func:`resolve_published_frozen_definitions` 现读冻结身份（Task 75 起是真实现，那条欠账登记已删）。
    """
    if PILOT_ADAPTER_ID in {reg.adapter_id for reg in registry.registrations()}:
        return ()
    if not manifest_capability_enabled():
        # 🔴 「capability 还没启用」与「还没 finalize」是**同一类事实**：这个 entry 今天不是
        #    双向 pilot，不注册 adapter 就是对它的忠实表达，因此 return 而**不是** raise。
        #
        #    首轮实测（Task 28 的路由守卫 8 例打红）：它的 fixture 用的 `ENTRY` 正是本 pilot
        #    冻结的 `xlsx/gt-d2-accounts-receivable`，于是这里一抛就让 `_registration` /
        #    `_apply_durable_incoming` 对**所有** entry 都 500 —— 一个尚未启用的 pilot 把
        #    整条 sync 路由拖下水。
        #
        #    判据没有被放宽：`assert_manifest_capability_enabled()` 仍是顺序门（守卫直接调
        #    它、变异 M33 仍打红），本 entry 在 registry 里依旧没有 adapter ⇒ `_registration`
        #    以 422 `adapter_not_ready` 收场（fail visible），契约孤儿仍在
        #    `RegistryReport.contract_files_without_adapter` 里可见。
        return ()

    import sqlalchemy as sa

    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
        WorkpaperSyncEntryState,
    )
    from app.services.workpaper_sync import entry_source_facts as facts
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.resolution import CanonicalResolutionService

    representation_id = (
        (
            await session.execute(
                sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                    WorkpaperSyncEntryState.entry_id == PILOT_ENTRY_ID
                )
            )
        )
        .scalars()
        .first()
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
    entry = manifest_entries_by_id(load_entry_manifest())[PILOT_ENTRY_ID]
    descriptor = facts.observe_descriptor_facts(entry)
    if descriptor is None:
        raise PilotSelectionError(
            f"entry {PILOT_ENTRY_ID} 的宿主实测不可达（产不出 descriptor 事实）—— "
            "不可达入口不得注册 adapter（Requirement 1.7）"
        )
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


def manifest_capability_enabled(*, manifest: Mapping[str, Any] | None = None) -> bool:
    """capability 是否已启用（接线路径的「今天不是我的回合」分支用它做真值判定）。

    🔴 实现**委派**给 :func:`assert_manifest_capability_enabled`，只把它的异常翻成布尔：
    两处各写一套判据会让「接线路径放行、顺序门仍红」这种不一致悄悄发生。`except` 只捕获
    :class:`PilotSelectionError` 这一个窄类型 —— 宽 `except Exception` 会把 manifest 读不出来
    之类的真故障也吞成「未启用」（本 spec 最贵的 fail-open 形态）。
    """
    try:
        assert_manifest_capability_enabled(manifest=manifest)
    except PilotSelectionError:
        return False
    return True


def assert_manifest_capability_enabled(
    *, manifest: Mapping[str, Any] | None = None
) -> None:
    """manifest 侧 capability/adapter_id 必须已启用（overlay 裁决 + 重生成之后）。

    🔴 **今天必然抛**：任务正文的顺序是「仅在 Task 36 将其 non-current candidate
    finalize 为 published representation 后**才**启用 adapter/宿主」。finalize 被
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
