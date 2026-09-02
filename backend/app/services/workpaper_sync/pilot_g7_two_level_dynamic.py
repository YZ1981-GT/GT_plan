# -*- coding: utf-8 -*-
"""G7 两级动态表 Excel pilot —— **冻结的那一个 G7 entry** 自己的身份、契约与动态列绑定。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 43
Requirements: 6.3, 6.4, 6.10, 6.16, 12.1, 12.2, 12.10, 14.1
Properties: **P22 / P28 / P49 / P66 / P69**

本模块**不借用** Task 40（`b60.hour_budget`）/ Task 41（`d2.receivable_detail`）/
Task 42（`h1.disposal_check`）的任何 definition identity：authority model / template /
instrumentation / contract / bundle 全部是本 entry 自己发布的（任务正文明令
「metadata sheet、candidate 与其他 entry bundle 均不得作为运行态 substrate」）。

═══ 一、为什么冻结的是 `xlsx/gt-g7-long-term-equity-main` ═══

Task 39 的 :func:`~app.services.workpaper_sync.pilot_harness.assess_pilot_classes` 用正则
``(^|[^a-z0-9])g7([^0-9]|$)`` 划出 `g7_two_level_dynamic` 类，在真实 manifest（186 条
entry）上实测 **3 个**候选、`bidirectional` **0 个**：

* `xlsx/gt-g7-equity-method`（`wp_code_patterns == ["G7E"]`）
* `xlsx/gt-g7-equity-subsidiary`（`wp_code_patterns == ["G7E"]`）
* `xlsx/gt-g7-long-term-equity-main`（`wp_code_patterns == ["G7L"]`）

必要条件逐条现推（**不抄** Task 40/41/42 的结论）：

1. `independent_entry = true`（AC 12.1「每个**独立** entry」）。三个候选实测都是 true。
2. **权威模板必须唯一可解且不是「静默回退到别的底稿」**。本条在本 pilot 上是**第四种形态**
   （Task 40 = 「wp_code 与 `_index.json` 精确相等」；Task 41 = 「三个 finder 入口全空 +
   YAML 声明同码」；Task 42 = 「码是名字提取产物 + 零回退 + 码族精确唯一」）：本 pilot 是
   **Task 42 那三条 + 一条新的「matcher 域在 entry 之间必须唯一」**，而正是最后这一条把
   三个候选收敛到一个：

   * `G7L` 与 `G7E` 都是 manifest 生成器的**名字提取产物**：
     `generate_workpaper_sync_manifest._source_match()` 对宿主文件名主干跑正则
     :data:`WP_CODE_EXTRACTION_PATTERN`，``GtG7LongTermEquityMain`` 命中 ``G7L``、
     ``GtG7EquityMethod`` / ``GtG7EquitySubsidiary`` 都命中 ``G7E``。
   * 三者在 `wp_template_finder` 上**零回退**：`find_template_file("G7L")` /
     `find_template_file_any("G7L")` / `find_all_template_files("G7L")` 实测分别是
     `None` / `None` / `[]`（`G7L` 不在 `_index.json` 的 `wp_code` 值域里、没有以 `G7L`
     开头的模板文件名、``"-" not in "G7L"`` 所以连子码回退分支都进不去）。
   * 码族 `G7` 在 `_index.json` 里**精确唯一**（恰 1 行，`relative_path` 就是
     :data:`TEMPLATE_RELATIVE_PATH`），三个 finder 入口全部落在同一份工作簿。
   * 🔴 **新增的第四条**：`G7E` 被 **2 个** entry 共用，`G7L` 只属 **1 个**。
     `EntryMatcher.wp_codes` 是 adapter 的匹配域，registry 的 **RG-3**
     （:class:`~app.services.workpaper_sync.adapters.registry.MatcherOverlapError`）
     禁止两个 adapter 在同一 `document_type` 上重叠 wp_code，而
     `resolve()` 对重叠域会抛 `AmbiguousAdapterError`。⇒ 以 `G7E` 为 matcher 的 pilot
     **在结构上**无法与它的孪生 entry 共存；`G7L` 是三个候选里唯一 matcher 域独占的。
     判据见 :func:`assert_matcher_domain_is_exclusive`。

3. `scenario_profile.profile_id = xlsx.editable.shared.single.room_service_wired.v1`
   ⇒ required scenario set 是 shared+editable 的标准 **24** 条，不走 authority-model
   替换分支，Property 25/26 必跑。实测本 entry 的 `required_scenario_set_digest` =
   ``8fc41bfb…``，与 B60 的 ``984681c2…``、D2 的 ``76d49456…``、H1 的 ``319d10b4…``
   **都不同** —— evidence 按本 bundle 自己的 digest 记录（任务正文要求）。

═══ 二、权威模板只认 `backend/wp_templates/` ═══

:data:`TEMPLATE_RELATIVE_PATH` 指向 ``G/G7 长期股权投资.xlsx``（263,335 字节），
:data:`TEMPLATE_SHA256` 是它的字节哨兵。`基础数据/致同通用审计程序及底稿模板（2025年
修订）/` 下的参考副本**一次都不读**（memory 铁律：运行时权威只认 `backend/wp_templates/`；
参考副本已实测落后）。:func:`read_authoritative_template` 每次读都比对哨兵。

工作簿共 **22** 张 sheet。逐 sheet 审核（openpyxl 直读全部 22 张，见守卫
`TestAuthoritativeTemplate` 与 evidence 的 `sheet_audit.json`）后本契约只声明受管 sheet
``附注披露信息（国企）`` —— `excel_extract.managed_tables_of()` 对「受管 sheet 之外还声明
了表」显式 fail closed，一次 extract 只覆盖一张 sheet。

选它而不选另外 21 张的**实测理由**（每条都是可打红的判据，见
`TestManagedSheetSelectionIsMeasured`）：

* 任务正文要求「复用源 xlsx↔seed↔运行时↔渲染层真源」。那套四边真源
  （已归档 spec `g7-column-alignment-and-extraction-closure` 的成果）只覆盖**两张披露
  sheet**：`backend/data/g7_column_source_facts.json` 的 `_meta.sheet_names` 实测恰为
  ``["附注披露信息（上市公司）", "附注披露信息（国企）"]``，共 **38** 张表、其中
  `is_two_level` **24** 张、`single_slot_exemption` **4** 张 ⇒ 应渲染两级 **20** 张。
* 两张披露 sheet 里带动态列占位（facts 的 ``<DYNAMIC:cN>``）的表共 **9** 张。其中
  上市侧 5 张的数据格在源模板里**全是跨 sheet 公式**（`='被投资单位财务信息（合营、
  联营）G7-5'!E10` 一类）⇒ 契约里只能全部 `mode=formula`，**零 editable 字段**，而
  `different_field_merge` / `same_field_conflict_resolve` 两条 required scenario 的
  oracle 需要「改 A / 改 B 且 conflict_count=0」，全受保护时结构上不可满足（假绿第④源：
  真实数据上分支不可达）。国企侧 ``主要财务信息``（源 `A61:L73`）的 100 个数据格逐格实测
  **全空** ⇒ 全部 editable。故受管 sheet 取国企侧。
* 该 sheet 上还有 ``（1）原子公司的基本情况``（源 `A77:G83`）—— 5 行**记录型**动态行，
  `A79..A83` 是字面量 1..5、`B79..G83` 是跨 sheet 公式 ⇒ 它提供本契约的 `row_identity` /
  `delete_policy` / `formula_mask` / 受保护字段。两张表在同一张 sheet 上，
  `managed_tables_of()` 的「一张动态行表 + 若干静态块」形态因此天然成立。

═══ 三、逐格审核受管 sheet（人工审核依据）═══

受管 sheet dims `A1:Q355`、**187 处 merge**、0 条数据验证、0 条条件格式、
`sheetProtection` 关；列占用实测 `A..M` 有内容、`N..Q` **一格都没有**。

**表 1（静态块，动态列）`minority_financials` = 源「（四）重要非全资子公司情况 / 2、主要
财务信息」**：

* **两级表头 62/63**（`header_rows = 2`，Requirement 6.3 的「两级表头」本体）：
  `A62:B63` 纵向合并 `项  目`（**双空格**，label 跨 A:B 两列 ⇒ facts 的
  `label_xlsx_span = 2`）；行 62 有 **5 个横向合并** `C62:D62` / `E62:F62` / `G62:H62` /
  `I62:J62` / `K62:L62`，**值全部为空** —— 这正是源模板自己的**动态列占位**
  （facts 的 `dynamic_group_rule`：「值为空的横向合并 = 动态列占位，源模板留给审计师填
  被投资单位名」，按锚列记作 ``<DYNAMIC:c3>`` / ``c5`` / ``c7`` / ``c9`` / ``c11``）。
* 行 63 是叶子：`C63..L63` 交替 ``期末数/本期发生额`` / ``期初数/上期发生额``。
  🔴 **Property 22 在本表上有真实（非合成）oracle**：**10 列只有 2 个不同 label**，
  每个 label 各重复 **5 次**。identity 若用 label 就会撞键（平台 H7 已付学费）；本契约的
  `column_key` 是 ``{table_key}_{seq}``、与 label 完全解耦，10 个键互不相同。
* 行 64..73 是 **10 个 metric 行**，标签在 `A{r}:B{r}` 合并格里：
  ``流动资产 / 非流动资产 / 资产合计 / 流动负债 / 非流动负债 / 负债合计 / 营业收入 /
  净利润 / 综合收益总额 / 经营活动现金流量``。
* `C64:L73` 共 **100 格逐格实测全空** ⇒ 全部 `mode=editable`、`value_type=amount`。
  🔴 `资产合计` / `负债合计` 语义上是合计，但源模板**没有**公式 ⇒ 按
  Requirement 6.1「禁止无来源自造字段」**不**声明成 formula，也不给它们造 mask。
* `A74` 是本表下方的第一条真内容（`【提示：上述财务数据以合并日子公司可辨认资产和负债的
  公允价值为基础进行调整；被划分为持有待售资产的，不需要披露该子公司的上述财务信息。】`），
  属未管理区域。
* 🔴 **本表是静态块而不是动态行表**，理由是结构性的：契约的 `mode` 是**按字段（=按列）**
  声明的，而本 sheet 上所有「实体作列头」的矩阵其公式/可编辑性是**按行**分布的
  （见 §二第二条：上市侧同构表的 `资产合计` 行是 `=SUM(...)`）。把矩阵当动态行表 ⇒
  10 个列字段只能取同一个 mode ⇒ 行级受保护语义丢失。静态块的字段是 `(metric, column)`
  逐格声明，`mode` 精确到格。本 pilot 的 100 格恰好同 mode，但结构选择必须按可表达性
  而不是按巧合。

**表 2（动态行表，绑定 Excel Table）`former_subsidiary_basic` = 源「（六）本期不再纳入
合并范围的原子公司 / （1）原子公司的基本情况」**：

* `header_rows = 1`（行 78：`序号 / 企业名称 / 注册地 / 业务性质 / 持股比例（%） /
  表决权比例（%） / 本期不再成为子公司的原因`；两个百分号括号是**全角**）。
* 行 79..83 是 5 行骨架：`A79..A83` 是字面量 `1..5`（⇒ `mode=auto_source`），
  `B79..G83` 逐格是跨 sheet 公式 `='处置子公司测试表（不包含一揽子交易）G7-11'!{列}{9+i}`
  （⇒ `mode=formula`，`formula_mask = ["B79:G83"]`，**30 格逐格实测**）。
* `footer_anchor` 取 `A85` 的真实文本 ``（2）本期出售的子公司出售日的财务状况``
  （`search_column = "A"`，不写死行号）。🔴 本 sheet 的受管区域**没有** `合计` 行 ——
  它是披露 sheet 而不是审定表；`A84` 是空行，`A85` 是下一小节标题，也就是「受管区域到此
  为止、插行时必须跟着下移」的那条可见标记。因此
  `excel_materialize.assert_footer_formula_covers_managed_rows()` 在本 entry 上返回
  **空元组**（footer 行上没有任何公式格），这是**源侧事实**而不是判据空转，由
  `TestFooterHasNoTotalFormula` 单独钉住（源侧哪天真加了合计公式即打红）。
* 🔴 UUID 列取 **N** 而不是 M：`M` 列实测有 13 格内容（`M9..M19` 等），隐藏它会藏掉可见
  业务格（Requirement 6.13「不得改变业务公式/标签」）。`N..Q` 全空 ⇒ `N` 是最左的安全列。
  `managed_last_col = "M"`：受管区域必须覆盖到矩阵最右列 `L`，而 UUID 列必须在
  `managed_last_col` 右侧（`ExcelInstrumentationSpec.__post_init__` 强制），故取 `M`/`N`。

═══ 四、动态列 `{slot}_{seq}` 的实测绑定（本 pilot 是第一个真正做它的）═══

Task 37/38 在 extractor / materializer 两侧都已 **fail closed**：契约声明了
`dynamic_columns` 但调用方没给 ``{slot}_{seq}`` → Excel 列的**实测绑定**时，分别抛
`DynamicColumnBindingMissingError` / `DynamicColumnWriteError`（不按声明列右移猜 ——
猜错会把某家公司的金额读到另一家名下）。Task 40/41/42 三个 entry 都没有动态列，本 pilot
是**第一个**把实测绑定真正写进 representation 身份的：

* `slot` 取 frozen contract 的稳定 `table_key`（``minority_financials``）——
  契约里没有别的稳定 slot 名，而 sheet 展示名/列 label 都是可改字符串。
* `seq` 从 1 起、按 **Excel 列序**枚举（不是按实体序）：
  `excel_materialize.assert_dynamic_column_binding_usable` 的绑定形态是
  `{key: 列标}`，一个键恰对一列，因此 5 个实体 × 2 个子列 = **10** 个键。
* 键的生成**唯一**走 Task 36 的
  :func:`~app.services.workpaper_sync.excel_entry_gate.dynamic_column_stable_keys`
  （`(slot, count)` 两参，签名里根本拿不到 label ⇒ 「改名改了 key」在构造上不可能）；
  本模块的 :func:`dynamic_column_keys_for_entities` 只把「实体名列表 × 子列定义」翻成
  `count`，**不写死列数**（平台铁律：按公司/单位横向展开的表禁写死列数）。
* **渲染层的对应键是 ``{slot}_{seq}_{subKey}``**（`g7SlotColumns.buildG7SlotColumns`，
  实测 `minority-fs-company_1_current` … `_5_prior`）。两套键空间**刻意不同**：Excel 侧
  一列一键，渲染层一实体两子列。:func:`render_column_key_for_seq` 是这个双射的**唯一**
  换算处，并由守卫用 `g7SlotColumns.ts` 的真实规则反向核对（第四边）。

═══ 五、四边真源（源 xlsx ↔ seed ↔ 运行时 ↔ 渲染层）═══

归档 spec `g7-column-alignment-and-extraction-closure` 的最贵教训（memory 已登记）：
**模型声明 `column.group`、三向守卫 39 例全绿，而任何 `.vue` 零引用 ⇒ 两级表头 0/38 张
从未渲染**。⇒ 判「某声明是否真生效」不能只比数据层。本 pilot 的四边各自的比对方式：

1. **源 xlsx** —— openpyxl 直读 :data:`TEMPLATE_RELATIVE_PATH` 的受管 sheet，逐格取
   merge / 文本 / 公式 / 空值，作为一切期望值的推导源（本模块的每个 `source_ref` /
   `header_source_ref` / `group_source_ref` 都指向具体单元格）；
2. **seed**（派生投影）—— `backend/data/g7_column_source_facts.json` 的
   `soe["七、重要非全资子公司"]["主要财务信息"]` 与
   `soe["七、本期不再纳入合并"]["原子公司的基本情况"]`：`is_two_level` / `level_count` /
   `label_xlsx_span` / `label_header` / `columns[].group` 逐项与本契约比对
   （:func:`source_facts_for_managed_tables`）；
3. **运行时** —— 真实注入产物上跑 Task 37 的 `extract_projection`，比对 identity
   inventory、受管字段集合、公式清册与未管理区域 digest；
4. **渲染层** —— `g7SoeDisclosureModel.ts` 的 `MINORITY_FS_SLOT` / `MINORITY_FS_SUB` /
   `minorityFsLabels` / `formerSubsidiaryColumns` 与 `g7SlotColumns.ts` 的
   `buildG7SlotColumns` 键规则；**并且**落到「有渲染宿主」这一层：
   `G7TabDisclosureSOE.vue` 必须真的以两级表头渲染本表（`G7DisclosureCell` +
   `g7DisclosureHeaderBlocks`），由 :func:`render_layer_two_level_facts` 取事实、守卫
   `TestFourthEdgeRenderLayer` 用「遍历 + 外层门控 + 内层嵌套」三要素判定，缺一即红。

🔴 `is_two_level` 是**源侧物理结构**字段，不能直接当期望值：须剔除已登记的
`single_slot_exemption` 才是「应渲染两级」的期望（24 → **20**）。本 pilot 的两张表都
**不在**豁免表里（:func:`assert_managed_tables_are_not_exempted`）。

═══ 六、HTML store ═══

国企披露 Tab 的 store 是 `checklist_responses`，`item_id` = :data:`STORE_ITEM_ID`
（``G7-main-disclosure-soe-v2``，来自 `G7TabDisclosureSOE.vue` 的 `RESPONSE_KEY`），
`remark` 是一个 JSON 对象：``{version: 2, tables: {tableId: rows}, texts: {},
entitySlots: {slot: names}, previouslySyncedTables: {}}``。

本 pilot 只消费其中两块：`tables[:data:`RENDER_MATRIX_TABLE_ID`]`（10 个 metric 行，
行 id 形如 ``minority-fs-1``，由 `metricRows()` 按**metric 序**而不是数组下标生成，第 i
个 id 恒对应源第 i 个 metric）与 `entitySlots[:data:`RENDER_SLOT`]`（实体名列表，
审计师可增删改名）。⇒ 改名只动 `entityName`，`{slot}_{seq}` 不变（Property 22）。

🔴 **实测：真实库里这一条 item 今天不存在**（由
`test_task43_g7_two_level_dynamic_pilot_pg.py` 从库里重新观测并冻结）。因此 merge oracle
跑在**按契约常量派生的合成载荷**上；结构性判据（identity 保留 / 公式范围 / 未管理区域 /
动态列绑定）一律跑在**真实权威模板 + 真实注入产物**上，不手搓最小 xlsx。

═══ 七、顺序与登记的上游缺口 ═══

`template → instrumentation → contract → bundle → representation` 的顺序由 Task 12 的
`DefinitionPublisher` 强制，payload 由 Task 17 的 builder 生成 —— 本模块**不**自己拼
payload、不自己算 digest、不自己校验 bundle slot（复制一份的后果不是"更安全"，而是任一侧
被短路都不改变行为 ⇒ 变异检验判 GREEN）。

磁盘契约 ``backend/data/workpaper_sync_contracts/g7.soe_subsidiary_disclosure.json`` 与本
模块现算 payload **双向锁死**（:func:`assert_contract_file_matches_source`），且两个生产
入口（:func:`publish_pilot_definitions` / :func:`attach_pilot_adapters`）**都**必须经这把锁。

登记的上游缺口见模块末尾各条常量；每条都有对应的可打红实测判据与「上游修好即抛错提醒
撤销登记」的反向自检。原「缺 published representation artifact →
`FrozenEntryDefinitions` 公共观测器」那一条已于 Task 75 结清（观测器落在
:mod:`app.services.workpaper_sync.published_identity_observer`），常量已删除。
"""

from __future__ import annotations

import hashlib
import json
import re
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
    DYNAMIC_COLUMN_IDENTITY_TEMPLATE,
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
from app.services.workpaper_sync.excel_entry_gate import (
    DynamicColumnIdentityError,
    dynamic_column_stable_keys,
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
    "AUTHORITY_MODEL",
    "COLUMN_SOURCE_FACTS_RELATIVE_PATH",
    "DYNAMIC_FIRST_COLUMN",
    "FOOTER_MARKER",
    "GROUP_HEADER_ROW",
    "LEAF_HEADER_ROW",
    "MANAGED_LAST_COL",
    "MANAGED_SHEET",
    "MATRIX_HEADER_ROW_COUNT",
    "MATRIX_METRICS",
    "MATRIX_TABLE_KEY",
    "MATRIX_TERMINATOR_ROW",
    "METRIC_FIRST_ROW",
    "PILOT_ADAPTER_ID",
    "PILOT_CLASS",
    "PILOT_ENTRY_ID",
    "PILOT_WP_CODES",
    "PILOT_WP_CODE_FAMILY",
    "RECORD_COLUMNS",
    "RECORD_FIRST_ROW",
    "RECORD_FOOTER_ROW",
    "RECORD_FORMULA_MASK",
    "RECORD_FORMULA_TEMPLATE",
    "RECORD_HEADER_ROW",
    "RECORD_LAST_ROW",
    "RECORD_TABLE_KEY",
    "LEGACY_COLUMN_KEY_PATTERN",
    "RENDER_MATRIX_TABLE_ID",
    "RENDER_METRIC_ID_PREFIX",
    "RENDER_MODEL_RELATIVE_PATH",
    "RENDER_RECORD_ROW_ID_PREFIX",
    "RENDER_RECORD_TABLE_ID",
    "RENDER_SLOT",
    "RENDER_SLOT_COLUMNS_RELATIVE_PATH",
    "RENDER_SUB_COLUMNS",
    "RENDER_TAB_RELATIVE_PATH",
    "SHEET_KEY",
    "SIBLING_G7_CANDIDATES",
    "STORE_ITEM_ID",
    "TABLE_NAME",
    "TEMPLATE_ID",
    "TEMPLATE_RELATIVE_PATH",
    "TEMPLATE_SHA256",
    "TEMPLATE_SLOT_GROUP_MERGES",
    "UNMANAGED_NEIGHBOUR_CELLS",
    "UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY",
    "UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED",
    "UPSTREAM_DEBT_RENDER_ROW_IDS_ARE_POSITIONAL",
    "UPSTREAM_DEBT_SLOT_SUBCOLUMN_KEY_SPACE_SPLIT",
    "UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_PER_COLUMN",
    "UUID_COL",
    "WP_CODE_EXTRACTION_PATTERN",
    "PilotDefinitions",
    "PilotSelectionError",
    "StorePayloadError",
    "TemplateResolutionFacts",
    "assert_contract_file_matches_source",
    "assert_dynamic_family_is_unreachable_for_xlsx_entries",
    "assert_managed_tables_are_not_exempted",
    "assert_manifest_capability_enabled",
    "assert_matcher_domain_is_exclusive",
    "assert_no_implicit_template_fallback",
    "assert_pilot_entry_selectable",
    "assert_wp_code_pattern_is_a_name_extraction_artifact",
    "attach_pilot_adapters",
    "authoritative_template_path",
    "authority_model_payload",
    "build_contract_payload",
    "build_pilot_matcher",
    "build_pilot_registration",
    "build_store_projection",
    "contract_file_path",
    "dynamic_column_binding_for",
    "dynamic_column_keys_for_entities",
    "excel_carrier_gate",
    "instrumentation_definition_payload",
    "instrumentation_spec",
    "iter_store_entities",
    "iter_store_metric_rows",
    "load_pilot_contract",
    "manifest_capability_enabled",
    "matrix_column_letter_for_seq",
    "metric_row_for",
    "publish_pilot_definitions",
    "read_authoritative_template",
    "register_pilot_adapter",
    "render_column_key_for_seq",
    "render_layer_two_level_facts",
    "render_schema_template_paths",
    "resolve_published_frozen_definitions",
    "source_facts_for_managed_tables",
    "stable_key_for_metric_cell",
    "stable_key_for_record_column",
    "template_definition_payload",
]


class PilotSelectionError(SyncDomainError):
    """冻结的 pilot entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_pilot_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法（非对象 / 缺 metric 行 / 重复行身份 / 非法 JSON）。

    刻意与 :class:`PilotSelectionError` 分型：「选型漂移」与「载荷坏了」是两类完全不同的
    故障，合并成一个错误码会让较早的分支永久不可达（本 spec 已实测 3 次的形态）。
    """

    error_code = "sync_pilot_store_payload_invalid"


class RenderLayerError(SyncDomainError):
    """渲染层（第四边）没有真正把两级表头渲染出来 —— 数据层全绿也必须打红。

    归档 spec `g7-column-alignment-and-extraction-closure` 实测过：模型声明 `column.group`
    而任何 `.vue` 零引用 ⇒ 两级表头 0/38 张从未渲染，三向数据守卫 39 例全绿。故第四边
    必须有自己的异常类型，不能并进 :class:`PilotSelectionError`。
    """

    error_code = "sync_pilot_render_layer_not_two_level"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的身份常量
# ═══════════════════════════════════════════════════════════════════════════

#: 本 pilot 覆盖的 AC 12.2 四类之一（与 `pilot_harness.PilotClass` 同域）。
PILOT_CLASS: Final[str] = "g7_two_level_dynamic"

#: 从 source-backed manifest 冻结的 entry（`assess_pilot_classes()` 三个 G7 候选里
#: matcher 域独占的那一个，见模块 docstring §一第 2 条）。
PILOT_ENTRY_ID: Final[str] = "xlsx/gt-g7-long-term-equity-main"

#: adapter_id == contract_id == 契约文件名（registry RG-4 双向锁死）。
PILOT_ADAPTER_ID: Final[str] = "g7.soe_subsidiary_disclosure"

#: matcher 的 wp_code 集合 —— 取自本 entry 的 `wp_match.wp_code_patterns`。
#:
#: 🔴 `G7L` 不是真 wp_code，是 manifest 生成器从宿主文件名 `GtG7LongTermEquityMain.vue`
#: 抽出来的名字提取产物（见模块 docstring §一）。它照实进 matcher 域（matcher 必须覆盖
#: 该 entry 的全部 wp_code、不得多也不得少），而模板解析走下面的**码族**。
PILOT_WP_CODES: Final[frozenset[str]] = frozenset({"G7L"})

#: 本 entry 真正的 wp_code 族（`_index.json` 里精确唯一的那个码）。
PILOT_WP_CODE_FAMILY: Final[str] = "G7"

#: 同类的另外两个候选，以及它们**共用**的 matcher 码。
#:
#: `G7E` 被两个 entry 共用 ⇒ 以它为 `EntryMatcher.wp_codes` 的 adapter 触发 registry
#: RG-3（`MatcherOverlapError`）/ `AmbiguousAdapterError`。这一条是把三个候选收敛到一个的
#: 决定性事实，由 :func:`assert_matcher_domain_is_exclusive` 在真实 manifest 上现推。
SIBLING_G7_CANDIDATES: Final[Mapping[str, str]] = {
    "xlsx/gt-g7-equity-method": "G7E",
    "xlsx/gt-g7-equity-subsidiary": "G7E",
}

#: `backend/wp_templates/` 下的权威模板。
TEMPLATE_RELATIVE_PATH: Final[str] = "G/G7 长期股权投资.xlsx"

#: 权威模板字节哨兵（Requirement 9.9：`backend/wp_templates/` 运行时只读）。
TEMPLATE_SHA256: Final[str] = (
    "6bf9e2ebcdf50a1c4a32f8733353dd1de994e7dc483232ad43680043577c3335"
)

#: 声明权威模板的**配置真源**（同一工作簿的两个子码各自独立声明同一份文件）。
#:
#: 两份都读、都比：只读一份时那一份被改到别的工作簿仍会被另一份"救"回来的假象不存在，
#: 但两份同时被改到别处才算真漂移 —— 因此判据是「**每一份**都必须指向权威模板」。
RENDER_SCHEMA_RELATIVE_PATHS: Final[tuple[str, ...]] = (
    "backend/data/ledger_adapters/wp_render_schema/G7-1.yaml",
    "backend/data/ledger_adapters/wp_render_schema/G7A.yaml",
)

#: 四边真源第 2 边（seed / 派生投影）的登记文件。
COLUMN_SOURCE_FACTS_RELATIVE_PATH: Final[str] = "backend/data/g7_column_source_facts.json"

#: 四边真源第 4 边（渲染层）的三个文件。
RENDER_MODEL_RELATIVE_PATH: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/"
    "disclosure/g7SoeDisclosureModel.ts"
)
RENDER_SLOT_COLUMNS_RELATIVE_PATH: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/composables/g7SlotColumns.ts"
)
RENDER_TAB_RELATIVE_PATH: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/"
    "disclosure/G7TabDisclosureSOE.vue"
)
RENDER_HEADER_BLOCKS_RELATIVE_PATH: Final[str] = (
    "audit-platform/frontend/src/components/workpaper/g7-long-term-equity-main/"
    "disclosure/g7DisclosureHeaderBlocks.ts"
)

#: 受管 sheet 的真实 tab 名（构建期选择器；运行时定位一律走 identity 锚点）。
MANAGED_SHEET: Final[str] = "附注披露信息（国企）"

#: instrumentation 的模板短码（进 row UUID 前缀与 `GT_*` defined names）。
TEMPLATE_ID: Final[str] = "G7N"

#: 契约 sheet_key —— 必须与 `build_instrumentation_payload` 产出的
#: `managed_sheets[0].sheet_key`（`f"{template_id.lower()}-managed"`）一致。
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"

#: 静态块（两级表头 + 动态列矩阵）的表键 —— 同时是动态列 `{slot}` 的取值。
MATRIX_TABLE_KEY: Final[str] = "minority_financials"

#: 动态行表（记录型）的表键 —— `ExcelIdentityBinding.table_key` 绑它。
RECORD_TABLE_KEY: Final[str] = "former_subsidiary_basic"

# ── 表 1：两级表头 + 动态列矩阵（源「2、主要财务信息」）────────────────────────

#: 组标题行（源模板留空的横向合并 = 动态列占位）。
GROUP_HEADER_ROW: Final[int] = 62
#: 叶子表头行（`期末数/本期发生额` / `期初数/上期发生额` 交替）。
LEAF_HEADER_ROW: Final[int] = 63
#: `header_rows = 2` —— Requirement 6.3 的「两级表头」本体。
MATRIX_HEADER_ROW_COUNT: Final[int] = LEAF_HEADER_ROW - GROUP_HEADER_ROW + 1

#: 第一个 metric 行。
METRIC_FIRST_ROW: Final[int] = 64

#: 10 个 metric：`(渲染层行 id, 源标签)`。**顺序即源行序**（`A64` → `A73`）。
#:
#: 渲染层行 id 由 `g7SoeDisclosureModel.metricRows('minority-fs', minorityFsLabels, …)`
#: 生成（`${prefix}-${index+1}`）—— 第 i 个 id 恒对应源第 i 个 metric，是**语义序号**
#: 而不是数组下标持久化身份（下标身份的风险另见
#: :data:`UPSTREAM_DEBT_RENDER_ROW_IDS_ARE_POSITIONAL`）。
#: （行 id 的前缀是 :data:`RENDER_METRIC_ID_PREFIX`，与 store 表键 **不是**同一个串。）
MATRIX_METRICS: Final[tuple[tuple[str, str], ...]] = (
    ("minority-fs-1", "流动资产"),
    ("minority-fs-2", "非流动资产"),
    ("minority-fs-3", "资产合计"),
    ("minority-fs-4", "流动负债"),
    ("minority-fs-5", "非流动负债"),
    ("minority-fs-6", "负债合计"),
    ("minority-fs-7", "营业收入"),
    ("minority-fs-8", "净利润"),
    ("minority-fs-9", "综合收益总额"),
    ("minority-fs-10", "经营活动现金流量"),
)

#: 矩阵下方第一条真内容所在行（未管理区域的上界，也是矩阵的终止标记）。
MATRIX_TERMINATOR_ROW: Final[int] = METRIC_FIRST_ROW + len(MATRIX_METRICS)

#: 标签列在源模板里跨 A:B 两列（facts 的 `label_xlsx_span = 2`）。
MATRIX_LABEL_COLUMNS: Final[tuple[str, str]] = ("A", "B")

#: 标签列表头文本（源 `A62`，**双空格**，逐字不得简写）。
MATRIX_LABEL_HEADER: Final[str] = "项  目"

#: 动态列区的第一列。
DYNAMIC_FIRST_COLUMN: Final[str] = "C"

#: 渲染层的槽位标识与子列定义（`g7SoeDisclosureModel.MINORITY_FS_SLOT` /
#: `MINORITY_FS_SUB`，逐字）。子列 label 就是源 `C63` / `D63` 的文本。
RENDER_SLOT: Final[str] = "minority-fs-company"
RENDER_SUB_COLUMNS: Final[tuple[tuple[str, str], ...]] = (
    ("current", "期末数/本期发生额"),
    ("prior", "期初数/上期发生额"),
)

#: store `tables` 里承载矩阵的键 = 渲染模型里那张表的 `id`（**不是** metric 前缀）。
#:
#: 🔴 两者不同，实测过一次：`metricRows('minority-fs', …)` 的第一个参数只决定**行 id 前缀**
#: （`minority-fs-1`..`-10`），而 store 的键是表定义里的 `id: 'minority-financials'`。
#: 真实库里三条载荷的 `tables` 键实测就是 `minority-financials`。
RENDER_MATRIX_TABLE_ID: Final[str] = "minority-financials"
#: metric 行 id 的前缀（`metricRows()` 的第一个参数）。
RENDER_METRIC_ID_PREFIX: Final[str] = "minority-fs"
#: 渲染层记录表的 id（store 键与行 id 前缀在这张表上**也不同**：id 是
#: `former-subsidiary-basic`、行 id 是 `former-sub-{n}`）。
RENDER_RECORD_TABLE_ID: Final[str] = "former-subsidiary-basic"
RENDER_RECORD_ROW_ID_PREFIX: Final[str] = "former-sub"

#: 🔴 **改造前的历史列键**（真实库实测）：`c{n}Current` / `c{n}Prior`。
#: 见 :data:`UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED`。
LEGACY_COLUMN_KEY_PATTERN: Final[str] = r"^c([1-9][0-9]*)(Current|Prior)$"

#: 源模板行 62 的 **5 个空白横向合并** = 源自己的动态列占位（逐格实测）。
#: `(合并区, 锚列, facts 里的占位名)`。
TEMPLATE_SLOT_GROUP_MERGES: Final[tuple[tuple[str, str, str], ...]] = (
    (f"C{GROUP_HEADER_ROW}:D{GROUP_HEADER_ROW}", "C", "<DYNAMIC:c3>"),
    (f"E{GROUP_HEADER_ROW}:F{GROUP_HEADER_ROW}", "E", "<DYNAMIC:c5>"),
    (f"G{GROUP_HEADER_ROW}:H{GROUP_HEADER_ROW}", "G", "<DYNAMIC:c7>"),
    (f"I{GROUP_HEADER_ROW}:J{GROUP_HEADER_ROW}", "I", "<DYNAMIC:c9>"),
    (f"K{GROUP_HEADER_ROW}:L{GROUP_HEADER_ROW}", "K", "<DYNAMIC:c11>"),
)

#: 渲染层默认实体名（`MINORITY_FS_SLOT_DEFAULT_NAMES`）—— **只是默认值**，审计师可改名/
#: 增删。它进契约的 `review` 说明而**不**进任何 key（Property 22）。
RENDER_SLOT_DEFAULT_NAMES: Final[tuple[str, ...]] = (
    "公司1",
    "公司2",
    "公司3",
    "公司4",
    "公司5",
)

# ── 表 2：动态行记录表（源「（1）原子公司的基本情况」）────────────────────────

#: 单级表头行。
RECORD_HEADER_ROW: Final[int] = 78
#: 骨架行区间。
RECORD_FIRST_ROW: Final[int] = 79
RECORD_LAST_ROW: Final[int] = 83
#: footer 标记所在行（`A84` 是空行，`A85` 才是下一小节标题）。
RECORD_FOOTER_ROW: Final[int] = 85
#: footer 标记文本（源 `A85` 逐字）。
FOOTER_MARKER: Final[str] = "（2）本期出售的子公司出售日的财务状况"

#: `column_key → (列标, mode, value_type, 渲染层列键, 源表头文本)`。
#:
#: 🔴 `A 序号` 是**标签列**（渲染层 `labelHeader: '序号'`），没有对应的渲染列键 ⇒
#: 渲染层列键为空串；它在源模板里是字面量 `1..5` ⇒ `mode=auto_source`（服务端值）。
#: `B..G` 六列逐格是跨 sheet 公式 ⇒ `mode=formula`。
RECORD_COLUMNS: Final[tuple[tuple[str, str, str, str, str, str], ...]] = (
    ("seq", "A", "auto_source", "integer", "", "序号"),
    ("name", "B", "formula", "text", "name", "企业名称"),
    ("registered_place", "C", "formula", "text", "registeredPlace", "注册地"),
    ("business_nature", "D", "formula", "text", "businessNature", "业务性质"),
    ("holding_ratio", "E", "formula", "ratio", "holdingRatio", "持股比例（%）"),
    ("voting_rights", "F", "formula", "ratio", "votingRights", "表决权比例（%）"),
    ("reason", "G", "formula", "text", "reason", "本期不再成为子公司的原因"),
)

#: 记录表数据格的公式模板（逐格实测；`{col}` 是本表列标、`{src}` 是源表行号）。
RECORD_FORMULA_TEMPLATE: Final[str] = (
    "='处置子公司测试表（不包含一揽子交易）G7-11'!{col}{src}"
)
#: 公式源表的首行（本表第 79 行 ↔ 源表第 9 行）。
RECORD_FORMULA_SOURCE_FIRST_ROW: Final[int] = 9

#: 受保护只读区域（六个公式列 × 5 行，逐格实测）。
RECORD_FORMULA_MASK: Final[tuple[str, ...]] = (
    f"B{RECORD_FIRST_ROW}:G{RECORD_LAST_ROW}",
)

# ── 受管区域几何 ─────────────────────────────────────────────────────────────

#: 最后一列受管业务列。矩阵最右列是 `L`，而 UUID 列必须严格在它右侧；`M` 列有 13 格
#: 内容（`M9..M19` 等）不能隐藏，故取 `M` 作 `managed_last_col`、`N` 作 UUID 列。
MANAGED_LAST_COL: Final[str] = "M"

#: 隐藏 row UUID 列。`N..Q` 四列在本 sheet 上**一格内容都没有**（逐列实测），`N` 是最左的
#: 安全列；隐藏 `M` 会藏掉可见业务格（Requirement 6.13）。
UUID_COL: Final[str] = "N"

#: 注入的 Excel Table displayName（OOXML 要求字母/下划线开头、无空格）。
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"

#: 本 pilot 是 projection-based ⇒ 三个 typed child 全部必须是 approved definition。
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: 受管区域**邻域**的真实内容（未管理区域；插删行必须不动它们）。
#: `(单元格, 期望内容)` —— 守卫用 openpyxl 逐格比对。
UNMANAGED_NEIGHBOUR_CELLS: Final[tuple[tuple[str, str], ...]] = (
    (
        f"A{MATRIX_TERMINATOR_ROW}",
        "【提示：上述财务数据以合并日子公司可辨认资产和负债的公允价值为基础进行调整；"
        "被划分为持有待售资产的，不需要披露该子公司的上述财务信息。】",
    ),
    ("A75", "（五）子公司与母公司会计期间不一致的，母公司编制合并财务报表的处理方法"),
    ("A76", "（六）本期不再纳入合并范围的原子公司"),
    ("A77", "（1）原子公司的基本情况"),
    (f"A{RECORD_FOOTER_ROW}", FOOTER_MARKER),
    (f"A{RECORD_FOOTER_ROW + 1}", "（说明出售日的确定方法）"),
)

#: HTML store 里承载整个国企披露 Tab 的那一条 item（`G7TabDisclosureSOE.RESPONSE_KEY`）。
STORE_ITEM_ID: Final[str] = "G7-main-disclosure-soe-v2"

#: store `remark` 的 schema 版本（`applySavedState` 里 `if (saved.version !== 2) return`）。
STORE_STATE_VERSION: Final[int] = 2

#: manifest 生成器抽 wp_code 的那条正则（`generate_workpaper_sync_manifest._source_match`）。
#: 复现它是「`G7L` 是名字提取产物」这一判据的核心 —— 不是断言常量等于常量。
WP_CODE_EXTRACTION_PATTERN: Final[str] = r"[A-Z][0-9]+(?:-[0-9]+)*(?:[A-Z])?"


def _col_index(letters: str) -> int:
    """A1 列标 → 1-based 列序号（`Z` → 26、`AB` → 28）。"""
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index


def _col_letter(index: int) -> str:
    """1-based 列序号 → A1 列标。"""
    out = ""
    while index:
        index, rest = divmod(index - 1, 26)
        out = chr(65 + rest) + out
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 2. 动态列策略（唯一决定「有几列」的地方；平台铁律：禁写死列数）
# ═══════════════════════════════════════════════════════════════════════════


def dynamic_column_keys_for_entities(entity_names: Sequence[str]) -> tuple[str, ...]:
    """实体名列表 → 稳定动态列键元组（``{slot}_{seq}``，seq 按 **Excel 列序**）。

    **本模块唯一**决定动态列数量的地方：``len(entity_names) * len(RENDER_SUB_COLUMNS)``。
    既不写死 5，也不写死 10 —— 5 是源模板当前的占位槽数（
    :data:`TEMPLATE_SLOT_GROUP_MERGES` 实测），运行时由 store 的 `entitySlots` 决定。

    键的生成**委派** Task 36 的
    :func:`~app.services.workpaper_sync.excel_entry_gate.dynamic_column_stable_keys`
    （两参 `(slot, count)`，签名里根本拿不到 label ⇒ 「改名改了 key」在构造上不可能）。
    在这里重写一遍 ``f"{slot}_{seq}"`` 的后果不是"更安全"，而是上游把模板改成别的形状时
    两处各说一套（变异检验判 GREEN）。

    :param entity_names: 被投资单位/公司名列表（**只用来数个数**，不进任何 key）
    """
    count = len(tuple(entity_names)) * len(RENDER_SUB_COLUMNS)
    return dynamic_column_stable_keys(slot=MATRIX_TABLE_KEY, count=count)


def matrix_column_letter_for_seq(seq: int) -> str:
    """动态列序号（1-based，Excel 列序）→ 源模板列标。

    seq 1 → `C`、2 → `D`、3 → `E` …… 即 :data:`DYNAMIC_FIRST_COLUMN` 起连续排布。
    这是**模板时刻**的几何，只作 `source_ref` 与 `cell.column` 的声明值；运行时定位一律
    走 :func:`dynamic_column_binding_for` 的**实测**绑定（Task 37 的
    `_resolve_field_column` 在声明了 `dynamic_columns` 时忽略 `cell.column`）。
    """
    if seq < 1:
        raise DynamicColumnIdentityError(f"动态列序号必须 >= 1，实得 {seq}")
    return _col_letter(_col_index(DYNAMIC_FIRST_COLUMN) + seq - 1)


def render_column_key_for_seq(seq: int) -> str:
    """动态列序号 → **渲染层**列键 ``{slot}_{entity_seq}_{subKey}``。

    🔴 两套键空间的**唯一**换算处（见 :data:`UPSTREAM_DEBT_SLOT_SUBCOLUMN_KEY_SPACE_SPLIT`）：

    * Excel 侧（契约） —— 一列一键，`{slot}_{seq}`，`slot` = 契约 `table_key`；
    * 渲染层 —— 一实体两子列，`{slot}_{entity_seq}_{subKey}`，`slot` = 渲染层槽位名。

    换算规则由 `g7SlotColumns.buildG7SlotColumns` 的真实实现决定（实体按 `names` 顺序、
    每个实体内按 `sub` 顺序展开）⇒ ``entity_seq = (seq - 1) // len(sub) + 1``、
    ``subKey = sub[(seq - 1) % len(sub)].key``。守卫用那个 `.ts` 文件的真实规则反向核对。
    """
    if seq < 1:
        raise DynamicColumnIdentityError(f"动态列序号必须 >= 1，实得 {seq}")
    width = len(RENDER_SUB_COLUMNS)
    entity_seq = (seq - 1) // width + 1
    sub_key = RENDER_SUB_COLUMNS[(seq - 1) % width][0]
    return f"{RENDER_SLOT}_{entity_seq}_{sub_key}"


def dynamic_column_binding_for(entity_names: Sequence[str]) -> dict[str, str]:
    """``{slot}_{seq}`` → Excel 列标 的**实测绑定**（喂给 engine 的那一份）。

    这是 Task 37/38 登记给 Tasks 40–57 的「把实测绑定写进 representation 身份」那一段：
    Task 40/41/42 三个 entry 都没有动态列，本 pilot 是第一个真正产出它的。

    键与列**成对**产生（`zip` 同一个 seq），因此不可能出现「键数与列数不等」或「两个键
    绑同一列」；后者由 `excel_materialize.assert_dynamic_column_binding_usable` 独立复核。
    """
    keys = dynamic_column_keys_for_entities(entity_names)
    return {key: matrix_column_letter_for_seq(seq) for seq, key in enumerate(keys, start=1)}


def observed_dynamic_columns_for(entity_names: Sequence[str]) -> dict[str, list[tuple[str, str]]]:
    """Task 36 `ExcelEntryDefinitionLoader.load()` 要的 `(label, key)` 实测对。

    label 取「实体名 + 子列 label」的真实展示串 —— 它是**可改的**，正因如此它出现在
    `observed` 里而不出现在 key 生成路径上：
    :func:`~app.services.workpaper_sync.excel_entry_gate.assert_dynamic_columns_label_independent`
    会把它与「与 label 无关的派生键」逐项比对（Property 22）。
    """
    names = tuple(entity_names)
    keys = dynamic_column_keys_for_entities(names)
    width = len(RENDER_SUB_COLUMNS)
    pairs: list[tuple[str, str]] = []
    for seq, key in enumerate(keys, start=1):
        entity = names[(seq - 1) // width]
        sub_label = RENDER_SUB_COLUMNS[(seq - 1) % width][1]
        pairs.append((f"{entity} {sub_label}", key))
    return {MATRIX_TABLE_KEY: pairs}


# ═══════════════════════════════════════════════════════════════════════════
# 3. 权威模板
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
    静默继续会让后面每个 digest 都对着一份"新模板"算出来。
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


def render_schema_template_paths(
    *, payloads: Mapping[str, Mapping[str, Any]] | None = None
) -> dict[str, str]:
    """两份渲染 schema 各自声明的 `template_path`（配置真源，本模块不复制字面量判定）。

    这两条读取存在的意义是让「权威模板由配置唯一声明」成为**运行时可打红的事实**：任一
    YAML 改指到另一份工作簿，:func:`assert_pilot_entry_selectable` 立刻失败。

    🔴 判据是「声明的码属于本 entry 的**码族**」而不是 Task 41 的
    `wp_code in PILOT_WP_CODES`：两份 YAML 的 `wp_code` 分别是 `G7-1`（子码形）与
    `G7A`（后缀字母形），而本 pilot 的 matcher 域是 `{"G7L"}`（名字提取产物），三者本就
    不该相等。抄 Task 41 的判据会让这条永远失败，进而逼人把判据关掉。

    :param payloads: 已解析的 schema（`相对路径 → payload`）。默认现读磁盘 —— 这个参数
        只为让「配置的 wp_code 跳出本 entry 码族」这一分支可测（否则它对真实数据结构性
        不可达，永久 GREEN）。
    """
    import yaml

    out: dict[str, str] = {}
    for relative in RENDER_SCHEMA_RELATIVE_PATHS:
        path = _REPO_ROOT / relative
        payload = (payloads or {}).get(relative)
        if payload is None:
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except OSError as exc:
                raise PilotSelectionError(f"渲染 schema 不可读: {path}: {exc}") from exc
        declared_code = str(payload.get("wp_code") or "")
        if not re.fullmatch(rf"{re.escape(PILOT_WP_CODE_FAMILY)}(-\d+)?[A-Z]?", declared_code):
            raise PilotSelectionError(
                f"{relative} 的 wp_code={declared_code!r} 不属于本 pilot 的码族 "
                f"{PILOT_WP_CODE_FAMILY!r}（形如 `G7` / `G7-<n>` / `G7<字母>`）—— "
                "配置真源与 entry 脱钩，它声明的 template_path 不能再当本 entry 的权威模板"
            )
        out[relative] = str(payload.get("template_path") or "")
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 4. 选型必要条件（在真实 manifest / 真实 resolver 上重新推导，不抄结论）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TemplateResolutionFacts:
    """`wp_template_finder` 的**实测**解析结果，由调用方提供。

    🔴 为什么不在本模块直接调 `find_template_file*`：Task 19 的 AST 清册把
    `find_template_file` / `find_template_file_any` 列为 **non-canonical resolver 符号**
    （`generate_workpaper_writer_inventory._RESOLVER_SYMBOLS`），生产模块里出现它们会给
    Task 20 的收口门增一条 `unadjudicated_resolver` + 一条 `non_canonical_resolver_only`
    欠账（清册生成器只扫 `backend/app`，脚本不在其内）。Task 40/41/42 已为同类形态各付过
    一次代价，正解是让那一行从清册里**整行消失**。

    这里需要的是「解析结果」这一**事实**，不是「谁去解析」：调用方（契约生成器与守卫）
    用真实 finder 取事实，本模块只做判定。判定被短路时守卫立刻打红。

    :param by_wp_code: `wp_code → 三个 finder 入口解析出的路径`（本 pilot 要求**全空**）
    :param index_wp_codes: `_index.json` 里全部 `wp_code` 值（用于「G7L 不是真码」判据）
    :param index_filenames: `_index.json` 里全部 `filename` 值（同上）
    :param family_code: 真正的码族（`G7`）
    :param family_resolved_paths: 码族在三个 finder 入口上的解析结果（要求全部 == 权威模板）
    :param family_index_rows: `_index.json` 里 `wp_code == family_code` 的行（要求恰 1 行）
    :param host_stem: 宿主组件文件名主干（`GtG7LongTermEquityMain`），用于复现名字提取
    """

    by_wp_code: Mapping[str, Sequence[Any]]
    index_wp_codes: Sequence[str]
    index_filenames: Sequence[str]
    family_code: str
    family_resolved_paths: Sequence[Any]
    family_index_rows: Sequence[Mapping[str, Any]]
    host_stem: str


def assert_wp_code_pattern_is_a_name_extraction_artifact(
    resolution: TemplateResolutionFacts,
) -> frozenset[str]:
    """证明 `G7L` 是从宿主文件名抽出来的产物，而不是一个真 wp_code。

    三条同时成立才放行（任一不成立 ⇒ `G7L` 可能真是个码，那本 pilot 的「零回退」判据
    就必须换成「精确唯一」形态，不能继续按提取产物处置）：

    1. 它不在 `_index.json` 的 `wp_code` 值域里；
    2. 它不是任何 `filename` 的前缀（`find_template_file_any` 的前缀回退分支进不去）；
    3. 把生成器那条正则重跑在宿主文件名主干上**能逐字复现**它。

    返回复现出的码集合（守卫据此断言 `G7L` 真在里面）。
    """
    extracted = frozenset(
        match.upper()
        for match in re.findall(WP_CODE_EXTRACTION_PATTERN, resolution.host_stem, re.I)
    )
    for code in sorted(PILOT_WP_CODES):
        if code in set(resolution.index_wp_codes):
            raise PilotSelectionError(
                f"{code!r} 出现在 wp_templates/_index.json 的 wp_code 值域里 —— "
                "它是一个真 wp_code，不能再按「名字提取产物」处置；本 pilot 的模板解析"
                f"判据必须改成对 {code!r} 自身的精确唯一性判定"
            )
        if any(str(name).startswith(code) for name in resolution.index_filenames):
            raise PilotSelectionError(
                f"存在以 {code!r} 开头的模板文件名 —— `find_template_file_any` 的前缀回退"
                "分支变得可达，「零回退」不再是「根本没有回退」"
            )
        if code not in extracted:
            raise PilotSelectionError(
                f"用生成器正则 {WP_CODE_EXTRACTION_PATTERN!r} 在宿主文件名主干 "
                f"{resolution.host_stem!r} 上复现不出 {code!r}（实得 {sorted(extracted)}）"
                " —— 那它就不是名字提取产物，本 pilot 的选型推导前提失效"
            )
    return extracted


def assert_no_implicit_template_fallback(
    resolution: TemplateResolutionFacts, *, wp_codes: frozenset[str]
) -> None:
    """matcher 域的每个码在 finder 上都必须解析不到任何文件；码族必须精确唯一落在权威模板。"""
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
            "本 pilot 的零回退判据要求它们**全部**解析不到任何文件，否则契约的 source_ref "
            "可能指向另一份底稿的单元格（本 spec 已付两次学费的形态）"
        )

    if resolution.family_code != PILOT_WP_CODE_FAMILY:
        raise PilotSelectionError(
            f"码族实测为 {resolution.family_code!r}，本 pilot 冻结的是 "
            f"{PILOT_WP_CODE_FAMILY!r} —— 换了码族就等于换了底稿"
        )
    rows = list(resolution.family_index_rows)
    if len(rows) != 1:
        raise PilotSelectionError(
            f"wp_templates/_index.json 里 wp_code == {PILOT_WP_CODE_FAMILY!r} 的行有 "
            f"{len(rows)} 条（要求恰 1 条）—— 码族不再精确唯一，`find_template_file` 会在"
            "多份工作簿之间挑一份，契约的 source_ref 失去唯一归属"
        )
    declared_relative = "/".join(str(rows[0].get("relative_path") or "").split("\\"))
    if declared_relative != TEMPLATE_RELATIVE_PATH:
        raise PilotSelectionError(
            f"索引里 {PILOT_WP_CODE_FAMILY!r} 的 relative_path={declared_relative!r} 与冻结的 "
            f"{TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
        )

    expected = authoritative_template_path().resolve()
    if not resolution.family_resolved_paths:
        raise PilotSelectionError(
            f"缺少码族 {PILOT_WP_CODE_FAMILY!r} 的 finder 实测结果 —— "
            "「精确唯一落在权威模板」不得对未观测的入口放行"
        )
    for resolved in resolution.family_resolved_paths:
        if resolved is None or Path(str(resolved)).resolve() != expected:
            raise PilotSelectionError(
                f"码族 {PILOT_WP_CODE_FAMILY!r} 的某个 finder 入口落在 {resolved} —— "
                f"与冻结的权威模板 {TEMPLATE_RELATIVE_PATH!r} 不是同一份文件"
            )


def assert_matcher_domain_is_exclusive(
    *, manifest: Mapping[str, Any] | None = None
) -> Mapping[str, tuple[str, ...]]:
    """本 entry 的 matcher 码必须**只属它自己**；同类另外两个候选必须共用一个码。

    这是把三个 G7 候选收敛到一个的决定性判据（模块 docstring §一第 2 条第四点）。两侧都要
    断言，缺任一侧都会让判据退化：

    * 只断言「`G7L` 独占」 ⇒ 万一将来 `G7E` 也变独占，「为什么当初没选它」就无从复核；
    * 只断言「`G7E` 被共用」 ⇒ 万一 `G7L` 也被别的 entry 用上，本 pilot 的 matcher
      会在 registry RG-3 上撞车而这里却放行。

    返回 `wp_code → 使用它的 entry_id 元组`（只含 G7 类的码）。
    """
    payload = manifest if manifest is not None else load_entry_manifest()
    entries = manifest_entries_by_id(payload)
    by_code: dict[str, list[str]] = {}
    for entry_id, entry in sorted(entries.items()):
        for code in (entry.get("wp_match") or {}).get("wp_code_patterns") or ():
            by_code.setdefault(str(code), []).append(entry_id)

    for code in sorted(PILOT_WP_CODES):
        owners = tuple(by_code.get(code, ()))
        if owners != (PILOT_ENTRY_ID,):
            raise PilotSelectionError(
                f"matcher 码 {code!r} 的使用者实测为 {list(owners)}，要求恰为 "
                f"[{PILOT_ENTRY_ID!r}] —— `EntryMatcher.wp_codes` 被两个 entry 共用时，"
                "registry RG-3 会以 MatcherOverlapError 拒绝第二个 adapter，"
                "`resolve()` 也会抛 AmbiguousAdapterError；共用码的 entry 不能当 pilot"
            )
    for sibling, shared_code in sorted(SIBLING_G7_CANDIDATES.items()):
        owners = tuple(by_code.get(shared_code, ()))
        if sibling not in owners:
            raise PilotSelectionError(
                f"同类候选 {sibling!r} 不再使用 {shared_code!r}（实测使用者 {list(owners)}）"
                " —— 「三个候选里只有本 entry 的 matcher 域独占」这一推导前提已失效，"
                "必须重新走选型"
            )
        if len(owners) < 2:
            raise PilotSelectionError(
                f"{shared_code!r} 实测只被 {list(owners)} 使用 —— 它已不再是共用码，"
                f"当初排除 {sorted(SIBLING_G7_CANDIDATES)} 的理由（matcher 重叠）不再成立，"
                "选型必须重做而不是继续沿用结论"
            )
    return {code: tuple(owners) for code, owners in sorted(by_code.items())}


def source_facts_for_managed_tables(
    *, facts: Mapping[str, Any] | None = None
) -> dict[str, Mapping[str, Any]]:
    """四边真源第 2 边（seed / 派生投影）：取本契约两张表在 facts 里的登记项。

    :data:`COLUMN_SOURCE_FACTS_RELATIVE_PATH` 是归档 spec
    `g7-column-alignment-and-extraction-closure` 的产物，`_meta.note` 明写「派生投影，非
    真源；禁止手改」，并由 `backend/tests/four_table/test_g7_column_source_facts.py` 钉死
    「与实时 openpyxl 读取逐字相等」。本函数只负责**定位**那两项并校验它仍描述同一份工作
    簿；逐字比对在守卫里做（期望值从源侧 openpyxl 推导，不用 facts 当期望）。
    """
    path = _REPO_ROOT / COLUMN_SOURCE_FACTS_RELATIVE_PATH
    payload = facts
    if payload is None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PilotSelectionError(f"G7 列真源 facts 不可读: {path}: {exc}") from exc
    meta = payload.get("_meta") or {}
    if str(meta.get("source_sha256") or "") != TEMPLATE_SHA256:
        raise PilotSelectionError(
            f"{COLUMN_SOURCE_FACTS_RELATIVE_PATH} 的 _meta.source_sha256="
            f"{meta.get('source_sha256')!r} 与本 pilot 冻结的权威模板 sha256 不符 —— "
            "seed 侧描述的是另一份工作簿，四边真源第 2 边失效"
        )
    if MANAGED_SHEET not in tuple(meta.get("sheet_names") or ()):
        raise PilotSelectionError(
            f"受管 sheet {MANAGED_SHEET!r} 不在 facts 的 _meta.sheet_names "
            f"{list(meta.get('sheet_names') or ())} 里 —— 四边真源第 2 边覆盖不到本 sheet"
        )
    soe = payload.get("soe") or {}
    wanted = {
        MATRIX_TABLE_KEY: ("七、重要非全资子公司", "主要财务信息"),
        RECORD_TABLE_KEY: ("七、本期不再纳入合并", "原子公司的基本情况"),
    }
    out: dict[str, Mapping[str, Any]] = {}
    for table_key, (section, table_name) in wanted.items():
        table = (soe.get(section) or {}).get(table_name)
        if table is None:
            raise PilotSelectionError(
                f"facts 里找不到 soe[{section!r}][{table_name!r}] —— 本契约的表 "
                f"{table_key!r} 在 seed 侧没有登记项，四边比对无从进行"
            )
        out[table_key] = table
    return out


def assert_managed_tables_are_not_exempted(
    *, facts: Mapping[str, Any] | None = None
) -> tuple[int, int, int]:
    """本契约的两张表都不在 `single_slot_exemption` 登记里；顺带现推「应渲染两级」的期望。

    🔴 `is_two_level` 是**源侧物理结构**字段，不能直接当期望值：它把「父行为空的占位合并」
    也算两级。真期望 = `is_two_level 计数 - single_slot_exemption 计数`（归档 spec 实测
    24 → 20）。任何 `_exemption` / `_adjudicated` 登记表都必须参与期望值推导。

    返回 `(两级计数, 豁免计数, 应渲染两级的期望计数)`。
    """
    path = _REPO_ROOT / COLUMN_SOURCE_FACTS_RELATIVE_PATH
    payload = facts
    if payload is None:
        payload = json.loads(path.read_text(encoding="utf-8"))
    two_level = 0
    exempt = 0
    for variant in ("listed", "soe"):
        for _section, tables in (payload.get(variant) or {}).items():
            for _name, table in tables.items():
                if table.get("is_two_level"):
                    two_level += 1
                if "single_slot_exemption" in table:
                    exempt += 1
    mine = source_facts_for_managed_tables(facts=payload)
    for table_key, table in mine.items():
        if "single_slot_exemption" in table:
            raise PilotSelectionError(
                f"本契约的表 {table_key!r} 在 seed 侧带 single_slot_exemption 登记 —— "
                "已裁决为「单槽 flat、不声明 group」的表不得当两级动态表 pilot；"
                "选型必须重做"
            )
    return two_level, exempt, two_level - exempt


def render_layer_two_level_facts(*, sources: Mapping[str, str] | None = None) -> dict[str, Any]:
    """四边真源第 4 边（**渲染层**）：从三个前端文件取「两级表头真的被渲染」的事实。

    🔴 这一边不能只比数据层，也不能只 grep 符号名。归档 spec 的教训是「模型声明
    `column.group`、三向守卫 39 例全绿，而任何 `.vue` 零引用 ⇒ 0/38 张从未渲染」。故本函数
    产出的是**模板形态判据的三要素**，缺一即由调用方判红：

    1. `iterates_groups` —— Tab 模板里存在对「两级表头块」的遍历（外层 `v-for`）；
    2. `outer_gate` —— 该遍历被「本表是两级」这一条件门控（`v-if` / 三元），而不是无条件
       画一行父表头；
    3. `inner_nesting` —— 遍历体内部还有一层子列渲染（内层 `v-for`），即父 → 子两层。

    另外返回 `slot_key_rule`（`g7SlotColumns.buildG7SlotColumns` 的真实键拼接源码行）与
    `declares_slot_config`（渲染模型是否给本表声明了 `slotConfig`），供守卫反向核对
    :func:`render_column_key_for_seq` 的换算规则。

    :param sources: `相对路径 → 源码`。默认现读磁盘 —— 这个参数只为让「渲染层退回一级
        表头」这一分支可测（否则它对真实数据结构性不可达，永久 GREEN）。
    """

    def _read(relative: str) -> str:
        if sources is not None and relative in sources:
            return sources[relative]
        path = _REPO_ROOT / relative
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RenderLayerError(f"渲染层文件不可读: {path}: {exc}") from exc

    tab = _read(RENDER_TAB_RELATIVE_PATH)
    blocks = _read(RENDER_HEADER_BLOCKS_RELATIVE_PATH)
    model = _read(RENDER_MODEL_RELATIVE_PATH)
    slot_columns = _read(RENDER_SLOT_COLUMNS_RELATIVE_PATH)

    header_block_symbols = tuple(
        sorted(set(re.findall(r"export (?:function|const) (\w+)", blocks)))
    )
    used_symbols = tuple(symbol for symbol in header_block_symbols if symbol in tab)
    # 外层遍历：`v-for="(<var>, …) in <两级表头渲染源>(…)"`。渲染源既可能是导入的符号
    # 本身，也可能是 Tab 里包了一层的本地函数（实测就是后者：`headerBlocks(table)` →
    # `buildG7HeaderBlocks(effectiveColumns(table))`）。⇒ 先把包装链解出来，再要求 v-for
    # 的遍历目标落在这条链上 —— 松匹配（任何叫 group/block 的循环都算）会在「模型里有
    # group、模板里另有一个同名循环」时误判成已渲染。
    renderers: set[str] = set(used_symbols)
    for symbol in used_symbols:
        for match in re.finditer(
            r"function\s+(\w+)\s*\([^)]*\)[^{]*\{[^}]*\b" + re.escape(symbol) + r"\s*\(",
            tab,
            re.S,
        ):
            renderers.add(match.group(1))
    group_loops: list[str] = []
    loop_vars: set[str] = set()
    for symbol in sorted(renderers):
        for match in re.finditer(
            r'v-for="\(?\s*(\w+)[^"]*\bin\s+' + re.escape(symbol) + r'\s*\([^"]*"', tab
        ):
            group_loops.append(match.group(0))
            loop_vars.add(match.group(1))
    # 内层嵌套与外层门控都必须落在同一个循环变量上（父 → 子两层，而不是两处无关代码）。
    inner_loops = [
        match.group(0)
        for var in sorted(loop_vars)
        for match in re.finditer(r'v-for="[^"]*\bin\s+' + re.escape(var) + r'\.\w+[^"]*"', tab)
    ]
    gates = [
        match.group(0)
        for var in sorted(loop_vars)
        for match in re.finditer(r'v-if="[^"]*\b' + re.escape(var) + r'\.\w+[^"]*"', tab)
    ]
    slot_key_rule = tuple(
        line.strip()
        for line in slot_columns.splitlines()
        if "${slot}_${seq}" in line
    )
    return {
        "header_block_symbols": header_block_symbols,
        "header_block_symbols_used_by_tab": used_symbols,
        "iterates_groups": tuple(group_loops),
        "inner_nesting": tuple(inner_loops),
        "outer_gate": tuple(gates),
        "slot_key_rule": slot_key_rule,
        "declares_slot_config": f"slot: {RENDER_SLOT.upper().replace('-', '_')}" in model
        or f"'{RENDER_SLOT}'" in model,
        "render_slot_default_names_declared": all(
            name in model for name in RENDER_SLOT_DEFAULT_NAMES
        ),
    }


def assert_render_layer_renders_two_level(
    *, sources: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """三要素缺一即抛 :class:`RenderLayerError`（第四边的 fail-closed 形态）。"""
    facts = render_layer_two_level_facts(sources=sources)
    if not facts["header_block_symbols_used_by_tab"]:
        raise RenderLayerError(
            f"{RENDER_HEADER_BLOCKS_RELATIVE_PATH} 导出的两级表头符号 "
            f"{list(facts['header_block_symbols'])} 在 {RENDER_TAB_RELATIVE_PATH} 里"
            "一个都没被引用 —— 这正是归档 spec 实测过的「声明了 group 但零渲染」形态"
        )
    for key, what in (
        ("iterates_groups", "父表头遍历（外层 v-for）"),
        ("outer_gate", "两级门控（v-if）"),
        ("inner_nesting", "子列遍历（内层 v-for）"),
    ):
        if not facts[key]:
            raise RenderLayerError(
                f"{RENDER_TAB_RELATIVE_PATH} 缺{what} —— 两级表头的模板形态三要素"
                "（遍历 + 外层门控 + 内层嵌套）缺一即判未渲染，"
                "不得只凭模型里有 `group` 字段就算生效"
            )
    if not facts["slot_key_rule"]:
        raise RenderLayerError(
            f"{RENDER_SLOT_COLUMNS_RELATIVE_PATH} 里找不到 `${{slot}}_${{seq}}` 的键拼接 —— "
            "渲染层的动态列键规则已变，本模块的换算（render_column_key_for_seq）失去依据"
        )
    return facts


def assert_pilot_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
    declared_template_paths: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    """在**真实** manifest / 真实 resolver 事实上重新推导必要条件；任一不成立即抛。

    :param resolution: 见 :class:`TemplateResolutionFacts`。**必填**（没有默认值 ⇒
        不可能出现「没给就跳过」的 fail-open）。
    :param declared_template_paths: 两份渲染 schema 声明的 `template_path`。默认现读配置
        —— 这个参数只为让「配置指到别的工作簿」这一分支可测。
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

    assessment = assess_pilot_classes(manifest=payload)[PilotClass.g7_two_level_dynamic]
    if PILOT_ENTRY_ID not in assessment.candidate_entry_ids:
        raise PilotSelectionError(
            f"{PILOT_ENTRY_ID!r} 不在 assess_pilot_classes() 的 g7_two_level_dynamic 候选里"
            f"（当前 {len(assessment.candidate_entry_ids)} 个候选）—— Property 49 的类边界"
            "由 harness 判定，不由本模块声明"
        )
    for sibling in sorted(SIBLING_G7_CANDIDATES):
        if sibling not in assessment.candidate_entry_ids:
            raise PilotSelectionError(
                f"同类候选 {sibling!r} 已不在 g7_two_level_dynamic 候选里 —— 「三个候选」"
                "这一推导前提已变，matcher 独占性的排除理由必须重新现推"
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

    # ── ②-a 冻结的码是名字提取产物（不是真 wp_code）────────────────────────
    assert_wp_code_pattern_is_a_name_extraction_artifact(resolution)
    # ── ②-b 运行时**没有**任何隐式回退；码族精确唯一落在权威模板 ──────────────
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))
    # ── ②-c matcher 域必须独占（把三个候选收敛到一个的那一条）───────────────
    assert_matcher_domain_is_exclusive(manifest=payload)

    # ── ②-d 权威模板由配置真源唯一声明（两份 YAML 各自都要指向它）────────────
    declared = (
        declared_template_paths
        if declared_template_paths is not None
        else render_schema_template_paths()
    )
    expected = f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}"
    for relative in RENDER_SCHEMA_RELATIVE_PATHS:
        if relative not in declared:
            raise PilotSelectionError(
                f"缺少 {relative} 的 template_path 实测值 —— 配置真源判据不得对未观测的"
                "声明放行"
            )
        if "/".join(str(declared[relative]).split("\\")) != expected:
            raise PilotSelectionError(
                f"{relative} 声明的 template_path={declared[relative]!r} 与本 pilot 冻结的"
                f"权威模板 {expected!r} 不一致 —— 契约的每个 source_ref 都指向后者的具体"
                "单元格，配置指到别处即为「据另一份底稿建契约」"
            )
    return entry


def assert_dynamic_family_is_unreachable_for_xlsx_entries(
    *, manifest: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    """把 :data:`UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY` 变成实测事实。

    返回 `{"xlsx_dynamic": (...), "dynamic": (...), "total": N}`。判据是**结构性的**：
    `evidence.derive_for_manifest_entry` 只按 `scenario_profile.mount_cardinality ==
    "dynamic"` 追加 `DYNAMIC_SCENARIOS`，所以只要 xlsx 侧该取值为空集，AC 6.4 自己的那条
    场景（`dynamic_column_stable_keys`）就对全部 xlsx entry 不可达。

    🔴 对**本 pilot** 这条缺口最刺眼：`dynamic_column_stable_keys` 正是 Requirement 6.4 的
    主场景，而本 entry 是四类 pilot 里**唯一**真有动态列的那个，却仍进不了分母。

    🔴 这条**不是**「断言缺口存在所以别管了」：它是欠账的可打红形态 —— 上游哪天把门改成
    按 contract 的 `dynamic_columns` 判定（或给本 entry 的 profile 打上 dynamic），
    `xlsx_dynamic` 就不再是空集，本函数抛错，欠账登记必须同步撤销。

    与 Task 41/42 的同名函数**刻意各自一份**：三个 pilot 的欠账文案、撤销条件与落点
    Property 都不同，复用一个函数会让其中一条的撤销条件无处可查（AC 12.12 禁跨 entry 复用）。
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
            f"{xlsx_dynamic} —— `dynamic_column_stable_keys` 不再对 xlsx 侧结构性不可达，"
            f"{UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY!r} 这条欠账必须撤销，"
            "并把 Property 22 的落点改到那条场景上"
        )
    return {"dynamic": tuple(dynamic), "xlsx_dynamic": (), "total": len(entries)}


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation spec 与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    """本 entry 的 Task 17 instrumentation 声明。

    受管行区间是**记录表**的骨架行 79..83（矩阵是静态块，不需要行身份）；`footer_row` 取
    `A85` 的真实标记行。`managed_last_col='M'` / `uuid_col='N'` 的推导见模块 docstring §三。
    """
    return ExcelInstrumentationSpec(
        entry_id=PILOT_ENTRY_ID,
        template_id=TEMPLATE_ID,
        template_relative_path=TEMPLATE_RELATIVE_PATH,
        managed_sheet=MANAGED_SHEET,
        first_data_row=RECORD_FIRST_ROW,
        last_data_row=RECORD_LAST_ROW,
        footer_row=RECORD_FOOTER_ROW,
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
    """authoritative model definition 的 canonical payload（**本 entry 独立批准**）。

    `projection_contract` ⇒ 三个 typed child 全部必须是 approved definition；AC 12.12
    的「字段级两场景替换」只对 `custom_authoritative_ooxml` / `opaque_single_onlyoffice`
    开放，本 pilot 因此**不会**触发替换，Property 25/26 必跑。

    🔴 `entry_id` + `pilot_class` 进 payload ⇒ 本 entry 的 authority model digest 与
    Task 40/41/42 的**必然不同**，不可能出现「借用别的 pilot 的 definition identity」
    （任务正文明令；守卫 `test_pilot_does_not_reuse_another_pilot_definition_identity`
    逐项比对不相等）。
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
# 6. per-entry contract
# ═══════════════════════════════════════════════════════════════════════════


def _src(cell: str) -> str:
    """`source_ref` 的统一形态：权威源 xlsx 的 `sheet!单元格`。"""
    return f"源xlsx!{MANAGED_SHEET}!{cell}"


def stable_key_for_metric_cell(metric_key: str, column_key: str) -> str:
    """矩阵格的 stable key = ``{table}/{metric}/{column_key}``（唯一拼装处）。

    🔴 **Property 22**：键里只有 `column_key`（``{slot}_{seq}``），**没有** label。本表 10
    列只有 2 个不同 label（各重复 5 次），label 一旦进键就会撞键（平台 H7 已付学费）。
    行侧同理只用 metric 的语义 id（``minority-fs-3``），不用中文标签。
    """
    return f"{MATRIX_TABLE_KEY}/{metric_key}/{column_key}"


def stable_key_for_record_column(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """记录表格的 stable key = ``{table}/{row_uuid}/{column_key}``（唯一拼装处）。"""
    return f"{RECORD_TABLE_KEY}/{row_identity}/{column_key}"


def metric_row_for(metric_key: str) -> int:
    """metric id → 源模板行号。未登记 id 即抛（不按位置猜）。"""
    for index, (key, _label) in enumerate(MATRIX_METRICS):
        if key == metric_key:
            return METRIC_FIRST_ROW + index
    raise PilotSelectionError(
        f"metric {metric_key!r} 不在本 pilot 的受管 metric 里 —— metric 集合由 "
        "MATRIX_METRICS 单一声明"
    )


def _matrix_table_payload() -> dict[str, Any]:
    """静态块：`10 metric × N 动态列`。

    列数由 :func:`dynamic_column_keys_for_entities` 从**源模板占位槽数**推出（不写死）。
    """
    entity_names = tuple(name for _range, _anchor, name in TEMPLATE_SLOT_GROUP_MERGES)
    keys = dynamic_column_keys_for_entities(entity_names)
    fields: list[dict[str, Any]] = []
    for metric_key, metric_label in MATRIX_METRICS:
        row = metric_row_for(metric_key)
        for seq, column_key in enumerate(keys, start=1):
            column = matrix_column_letter_for_seq(seq)
            render_key = render_column_key_for_seq(seq)
            sub_key, sub_label = RENDER_SUB_COLUMNS[(seq - 1) % len(RENDER_SUB_COLUMNS)]
            slot_range, slot_anchor, slot_placeholder = TEMPLATE_SLOT_GROUP_MERGES[
                (seq - 1) // len(RENDER_SUB_COLUMNS)
            ]
            fields.append(
                {
                    "stable_field_key": stable_key_for_metric_cell(metric_key, column_key),
                    "json_pointer": (
                        f"/tables/{RENDER_MATRIX_TABLE_ID}/{metric_key}/values/{render_key}"
                    ),
                    "column_key": column_key,
                    "cell": {"column": column, "row_from": row},
                    "mode": "editable",
                    "value_type": "amount",
                    "source_ref": _src(f"{column}{row}"),
                    "header_source_ref": _src(f"{column}{LEAF_HEADER_ROW}"),
                    "header_text": sub_label,
                    "group_source_ref": _src(slot_range),
                    "group_placeholder": slot_placeholder,
                    "group_anchor_column": slot_anchor,
                    "row_label_source_ref": _src(
                        f"{MATRIX_LABEL_COLUMNS[0]}{row}:{MATRIX_LABEL_COLUMNS[1]}{row}"
                    ),
                    "row_label_text": metric_label,
                    "render_column_key": render_key,
                    "render_sub_key": sub_key,
                    "store_item_id": STORE_ITEM_ID,
                }
            )
    return {
        "table_key": MATRIX_TABLE_KEY,
        "anchor": f"{MATRIX_LABEL_COLUMNS[0]}{GROUP_HEADER_ROW}",
        "header_rows": MATRIX_HEADER_ROW_COUNT,
        "dynamic_columns": {
            "identity": DYNAMIC_COLUMN_IDENTITY_TEMPLATE,
            "source_ref": _src(
                f"{DYNAMIC_FIRST_COLUMN}{GROUP_HEADER_ROW}:"
                f"{matrix_column_letter_for_seq(len(keys))}{GROUP_HEADER_ROW}"
            ),
        },
        "fields": fields,
    }


def _record_table_payload() -> dict[str, Any]:
    """动态行表：5 行骨架 × 7 列（`A` auto_source + `B..G` formula）。"""
    fields: list[dict[str, Any]] = []
    for column_key, column, mode, value_type, render_key, header_text in RECORD_COLUMNS:
        spec: dict[str, Any] = {
            "stable_field_key": stable_key_for_record_column(column_key),
            "json_pointer": (
                f"/tables/{RENDER_RECORD_TABLE_ID}/{{row_uuid}}/values/{render_key}"
                if render_key
                else f"/tables/{RENDER_RECORD_TABLE_ID}/{{row_uuid}}/ordinal"
            ),
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(f"{column}{RECORD_FIRST_ROW}"),
            "header_source_ref": _src(f"{column}{RECORD_HEADER_ROW}"),
            "header_text": header_text,
            "store_item_id": STORE_ITEM_ID,
        }
        if render_key:
            spec["render_column_key"] = render_key
        else:
            spec["render_label_column"] = True
        if mode == "formula":
            spec["formula_source_ref"] = RECORD_FORMULA_TEMPLATE.format(
                col=column, src=RECORD_FORMULA_SOURCE_FIRST_ROW
            )
        fields.append(spec)
    return {
        "table_key": RECORD_TABLE_KEY,
        "anchor": f"A{RECORD_HEADER_ROW}",
        "header_rows": 1,
        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
        "delete_policy": "tombstone",
        "footer_anchor": {"marker": FOOTER_MARKER, "search_column": "A"},
        "formula_mask": list(RECORD_FORMULA_MASK),
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
    entity_names = tuple(name for _range, _anchor, name in TEMPLATE_SLOT_GROUP_MERGES)
    keys = dynamic_column_keys_for_entities(entity_names)
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
                "tables": [_matrix_table_payload(), _record_table_payload()],
            }
        ],
        "review": {
            "entry_id": PILOT_ENTRY_ID,
            "pilot_class": PILOT_CLASS,
            "authority_root": "backend/wp_templates",
            "html_store": {
                "table": "checklist_responses",
                "item_id": STORE_ITEM_ID,
                "state_version": STORE_STATE_VERSION,
                "shape": "json_object_with_tables_and_entity_slots",
                "matrix_table_id": RENDER_MATRIX_TABLE_ID,
                "record_table_id": RENDER_RECORD_TABLE_ID,
                "entity_slot": RENDER_SLOT,
                "note": (
                    "整个国企披露 Tab 存成这一条 item 的 remark（一个 JSON 对象）；本 pilot "
                    "只消费 tables['minority-fs']（10 个 metric 行，行 id 按 metric 序而非"
                    "数组下标）与 entitySlots['minority-fs-company']（实体名列表，可改名）。"
                    "改名只动 entityName，{slot}_{seq} 不变（Requirement 6.4 / Property 22）"
                ),
                "observed_absent_in_reference_database": True,
            },
            "two_level_header": {
                "group_row": GROUP_HEADER_ROW,
                "leaf_row": LEAF_HEADER_ROW,
                "label_header": MATRIX_LABEL_HEADER,
                "label_columns": list(MATRIX_LABEL_COLUMNS),
                "label_xlsx_span": len(MATRIX_LABEL_COLUMNS),
                "source_slot_group_merges": [
                    {"range": rng, "anchor_column": anchor, "placeholder": name}
                    for rng, anchor, name in TEMPLATE_SLOT_GROUP_MERGES
                ],
                "duplicate_leaf_labels": {
                    label: len(keys) // len(RENDER_SUB_COLUMNS)
                    for _key, label in RENDER_SUB_COLUMNS
                },
                "note": (
                    "行 62 的 5 个横向合并**值全空** —— 那是源模板自己的动态列占位（facts 的 "
                    "dynamic_group_rule：值为空的横向合并 = 动态列占位）。10 个数据列只有 2 "
                    "个不同叶子 label、各重复 5 次，故 identity 只能是 {slot}_{seq}"
                ),
            },
            "dynamic_columns": {
                "identity": DYNAMIC_COLUMN_IDENTITY_TEMPLATE,
                "slot": MATRIX_TABLE_KEY,
                "template_slot_count": len(TEMPLATE_SLOT_GROUP_MERGES),
                "sub_columns": [
                    {"key": key, "label": label} for key, label in RENDER_SUB_COLUMNS
                ],
                "column_keys": list(keys),
                "template_column_letters": [
                    matrix_column_letter_for_seq(seq) for seq in range(1, len(keys) + 1)
                ],
                "render_column_keys": [
                    render_column_key_for_seq(seq) for seq in range(1, len(keys) + 1)
                ],
                "render_slot": RENDER_SLOT,
                "render_slot_default_names": list(RENDER_SLOT_DEFAULT_NAMES),
                "note": (
                    "列数由 dynamic_column_keys_for_entities(entity_names) 决定 = "
                    "len(实体名) × len(子列)，不写死。契约里列出的 10 个键对应源模板当前的 5 "
                    "个占位槽；运行时列数由 store 的 entitySlots 决定，键→列的**实测绑定**由 "
                    "dynamic_column_binding_for() 产出并写进 representation 身份，"
                    "Task 37/38 两侧在缺绑定时 fail closed（不按声明列右移猜）"
                ),
            },
            "formula_region": {
                "table_key": RECORD_TABLE_KEY,
                "mask": list(RECORD_FORMULA_MASK),
                "formula_template": RECORD_FORMULA_TEMPLATE,
                "source_first_row": RECORD_FORMULA_SOURCE_FIRST_ROW,
                "cell_count": 6 * (RECORD_LAST_ROW - RECORD_FIRST_ROW + 1),
                "note": (
                    "记录表 B..G 六列逐格是跨 sheet 公式（30 格逐格实测）⇒ mode=formula + "
                    "formula_mask；A 列是字面量 1..5 ⇒ mode=auto_source。矩阵那张表源侧 "
                    "0 公式（资产合计/负债合计在源模板里是空格）⇒ 不给它造 mask"
                    "（Requirement 6.1 禁止无来源自造字段）"
                ),
            },
            "footer_anchor": {
                "marker": FOOTER_MARKER,
                "search_column": "A",
                "row_at_instrumentation": RECORD_FOOTER_ROW,
                "carries_total_formula": False,
                "note": (
                    "披露 sheet 的受管区域没有「合计」行：A84 是空行、A85 是下一小节标题，"
                    "也就是「受管区域到此为止、插行时必须跟着下移」的可见标记。"
                    "assert_footer_formula_covers_managed_rows() 因此返回空元组 —— "
                    "这是源侧事实，不是判据空转"
                ),
            },
            "unmanaged_neighbours": [
                {"cell": cell, "content": content}
                for cell, content in UNMANAGED_NEIGHBOUR_CELLS
            ],
            "four_edge_sources": {
                "source_xlsx": f"backend/wp_templates/{TEMPLATE_RELATIVE_PATH}",
                "seed": COLUMN_SOURCE_FACTS_RELATIVE_PATH,
                "runtime": (
                    "app.services.workpaper_sync.excel_extract.extract_projection "
                    "on the instrumented artifact"
                ),
                "render_layer": [
                    RENDER_MODEL_RELATIVE_PATH,
                    RENDER_SLOT_COLUMNS_RELATIVE_PATH,
                    RENDER_TAB_RELATIVE_PATH,
                    RENDER_HEADER_BLOCKS_RELATIVE_PATH,
                ],
            },
            "reviewed_basis": (
                "openpyxl 逐 sheet 直读权威模板 G/G7 长期股权投资.xlsx 的 22 张 sheet，"
                "只取受管 sheet 附注披露信息（国企）的两张表："
                "① 主要财务信息（源 A61:L73）—— 两级表头 62/63 行（A62:B63 纵向合并「项  目」"
                "双空格 + 行 62 的 5 个**空白**横向合并 C62:D62/E62:F62/G62:H62/I62:J62/K62:L62 "
                "= 源自己的动态列占位 + 行 63 的 10 个叶子交替「期末数/本期发生额」「期初数/"
                "上期发生额」）、10 个 metric 行 64..73（标签在 A{r}:B{r} 合并格）、"
                "C64:L73 共 100 格逐格实测**全空** ⇒ 全部 editable；"
                "② 原子公司的基本情况（源 A77:G83）—— 单级表头 78 行 7 列（两个百分号括号全角）、"
                "5 行骨架 79..83、A 列字面量 1..5 ⇒ auto_source、B..G 逐格跨 sheet 公式 "
                "⇒ formula + formula_mask B79:G83、footer 取 A85 真实文本。"
                "UUID 列取 N（M 列有 13 格内容不能隐藏；N..Q 四列全空）。"
                "上市侧同构的 5 张动态列矩阵因数据格在源模板里**全是公式** ⇒ 零 editable 字段、"
                "merge 家族两条 required scenario 结构性不可满足，故未选用；"
                "登记为 UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_PER_COLUMN"
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
            "请用 `py -3 backend/scripts/gen/generate_pilot_g7_two_level_dynamic_contract.py "
            f"--apply` 重生成 {contract_file_path().name}，并复核 diff"
        )
    # 现算 payload 自己也必须过强校验（磁盘对得上但两边都非法时仍要打红）。
    parse_contract(expected, adapter_id=PILOT_ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 7. store 载荷拆分（stable field + 动态列，流式）
# ═══════════════════════════════════════════════════════════════════════════


def _store_state(payload: str | bytes | Mapping[str, Any]) -> Mapping[str, Any]:
    """把 `checklist_responses.remark` 的三种真实形态归一成 state 对象。"""
    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            state: Any = json.loads(text)
        except ValueError as exc:
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 的 remark 不是合法 JSON: {exc}"
            ) from exc
    else:
        state = payload
    if not isinstance(state, Mapping):
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 的载荷必须是对象，实得 {type(state).__name__} —— "
            "整个 Tab 被存成别的形态时必须 fail closed，不得静默当成零行"
        )
    version = state.get("version")
    if version != STORE_STATE_VERSION:
        raise StorePayloadError(
            f"{STORE_ITEM_ID} 的 state version={version!r}，本 pilot 冻结的是 "
            f"{STORE_STATE_VERSION} —— 前端 `applySavedState` 对不匹配版本直接 return，"
            "拆分侧也必须 fail closed 而不是按旧结构猜"
        )
    return state


def iter_store_entities(payload: str | bytes | Mapping[str, Any]) -> tuple[str, ...]:
    """取 store 里本表的实体名列表（`entitySlots[RENDER_SLOT]`）。

    空列表即抛：动态列数量必须由**实测的**实体列表决定，退回默认名会让「审计师删到 0 家」
    这一状态被静默补成 5 列（写死列数的另一种形态）。
    """
    state = _store_state(payload)
    slots = state.get("entitySlots") or {}
    if not isinstance(slots, Mapping):
        raise StorePayloadError(
            f"{STORE_ITEM_ID}.entitySlots 必须是对象，实得 {type(slots).__name__}"
        )
    names = slots.get(RENDER_SLOT)
    if not isinstance(names, (list, tuple)) or not names:
        raise StorePayloadError(
            f"{STORE_ITEM_ID}.entitySlots[{RENDER_SLOT!r}] 缺失或为空（实得 {names!r}）—— "
            "动态列数量只能由实测实体列表决定，不得回退到模板默认名"
        )
    out: list[str] = []
    for ordinal, name in enumerate(names):
        if not isinstance(name, str) or not name.strip():
            raise StorePayloadError(
                f"{STORE_ITEM_ID}.entitySlots[{RENDER_SLOT!r}] 第 {ordinal} 项不是非空字符串"
                f"（实得 {name!r}）"
            )
        out.append(name.strip())
    return tuple(out)


def iter_store_metric_rows(
    payload: str | bytes | Mapping[str, Any],
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """流式 yield `(metric_key, values)`；未登记 / 重复 metric 即抛。"""
    state = _store_state(payload)
    tables = state.get("tables") or {}
    if not isinstance(tables, Mapping):
        raise StorePayloadError(
            f"{STORE_ITEM_ID}.tables 必须是对象，实得 {type(tables).__name__}"
        )
    rows = tables.get(RENDER_MATRIX_TABLE_ID)
    if not isinstance(rows, (list, tuple)):
        raise StorePayloadError(
            f"{STORE_ITEM_ID}.tables[{RENDER_MATRIX_TABLE_ID!r}] 必须是行数组，"
            f"实得 {type(rows).__name__}"
        )
    known = {key for key, _label in MATRIX_METRICS}
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise StorePayloadError(
                f"{STORE_ITEM_ID}.tables[{RENDER_MATRIX_TABLE_ID!r}] 第 {ordinal} 项不是对象，"
                f"实得 {type(row).__name__}"
            )
        metric_key = row.get("id")
        if not isinstance(metric_key, str) or metric_key not in known:
            raise StorePayloadError(
                f"{STORE_ITEM_ID}.tables[{RENDER_MATRIX_TABLE_ID!r}] 第 {ordinal} 项的 "
                f"id={metric_key!r} 不在受管 metric 集合里（{sorted(known)}）—— "
                "不得按数组下标推 metric（Requirement 6.5）"
            )
        if metric_key in seen:
            raise StorePayloadError(
                f"{STORE_ITEM_ID} 出现重复 metric id {metric_key!r}（第 {ordinal} 项）—— "
                "复制行产生的重复身份默认是结构冲突，不得静默合并成一行（Requirement 6.15）"
            )
        seen.add(metric_key)
        values = row.get("values")
        if not isinstance(values, Mapping):
            raise StorePayloadError(
                f"{STORE_ITEM_ID} metric {metric_key!r} 的 values 必须是对象，"
                f"实得 {type(values).__name__}"
            )
        yield metric_key, values


def build_store_projection(
    payload: str | bytes | Mapping[str, Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """把 HTML store 载荷拆成按 stable field key 索引的 :class:`Projection`。

    行/field 预算由 Task 37 的 :class:`StreamingProjectionBudget` **边读边判**
    （本函数不含任何阈值数字）；越界即 `BudgetExceededError`，不截断、不静默丢行。

    🔴 契约的动态列键集合由**契约**给出，而 store 的实体数可能更多/更少：多出来的列在
    契约里没有对应字段 ⇒ `field_by_stable_key` 直接抛（而不是静默丢），少的列则不产生键
    （Task 14 用键缺失表达 MISSING）。这条不能"宽容"：静默丢一列就是把某家公司的披露数据
    整列扔掉。
    """
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    entity_names = iter_store_entities(payload)
    keys = dynamic_column_keys_for_entities(entity_names)
    values: dict[str, FieldValue] = {}
    for metric_key, cells in iter_store_metric_rows(payload):
        budget.add_row(MATRIX_TABLE_KEY)
        matched = 0
        for seq, column_key in enumerate(keys, start=1):
            render_key = render_column_key_for_seq(seq)
            if render_key not in cells:
                continue
            matched += 1
            stable_key = stable_key_for_metric_cell(metric_key, column_key)
            spec = contract.field_by_stable_key(stable_key)
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=cells[render_key],
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=None,
            )
        if matched == 0 and cells:
            # 🔴 一整行有值却**一个键都对不上** ⇒ fail closed，不得静默丢整行。
            #    真实库里实测存在这种载荷：改造前的行用 `c{n}Current` / `c{n}Prior` 当列键
            #    （见 UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED），当前渲染层已读不到它们。
            #    静默跳过 = 把那家公司的整列披露数据扔掉（本 spec 最贵的 fail-open 形态）。
            legacy = sorted(
                key for key in cells if re.match(LEGACY_COLUMN_KEY_PATTERN, str(key))
            )
            raise StorePayloadError(
                f"{STORE_ITEM_ID} metric {metric_key!r} 的 values 键 {sorted(cells)[:4]} "
                f"与契约声明的动态列键（{keys[:2]}…）一个都对不上"
                + (f"；其中 {legacy[:4]} 是改造前的历史键" if legacy else "")
                + " —— 不得静默丢整行，历史键需要显式迁移（Requirement 6.4）"
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={},
    )


# ═══════════════════════════════════════════════════════════════════════════
# 8. 发布（顺序由 Task 12 的 publisher 强制）
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
# 9. adapter 注册与宿主接线
# ═══════════════════════════════════════════════════════════════════════════


def build_pilot_matcher() -> EntryMatcher:
    """本 entry 的匹配域（精确 wp_code 集合，不用 glob）。

    🔴 `G7L` 独占是选型硬条件（:func:`assert_matcher_domain_is_exclusive`）：换成 `G7E`
    会与另一个 G7 entry 在 registry RG-3 上撞车。
    """
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


#: 🔴 **登记的上游缺口 ②**（Task 41 首登、42 复现，**本 entry 上最刺眼**）：
#: AC 6.4 自己的场景 `dynamic_column_stable_keys` 对 xlsx entry 结构性不可达。
#:
#: 由 :func:`assert_dynamic_family_is_unreachable_for_xlsx_entries` 把它变成可打红的
#: 实测事实；缺口一旦被上游修掉，那个函数会抛错，提醒撤销本条登记。
UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY: Final[str] = (
    "Task 43 欠账（Task 41 首次登记、Task 42 复现，本 entry 上最刺眼）："
    "`evidence.derive_for_manifest_entry` 只在 "
    '`scenario_profile.mount_cardinality == "dynamic"` 时追加 DYNAMIC_SCENARIOS，而该'
    "字段量的是**前端宿主挂载基数**（v-for 挂几个 OO 编辑器），不是「受管表有没有动态"
    "行/动态列」。实测全 manifest 186 条里只有 1 条为 dynamic 且是 docx ⇒ "
    "`dynamic_column_stable_keys`（AC 6.4）与 `dynamic_row_add_delete_reorder_copy`"
    "（AC 6.9）对**任何 xlsx entry** 都进不了 required set —— 包括本 G7 pilot，而它是四类 "
    "pilot 里**唯一**真有 `{slot}_{seq}` 动态列的那个（10 列共用 2 个重复 label）。"
    "修法需要把 contract 的 dynamic_columns / row_identity 声明喂进 required-set 推导"
    "（会改动 B60/D2/H1/G7 四个 required digest），属设计级变更。"
    "owner 建议归 evidence 推导侧（Task 39 后续）；在此之前 Property 22 落在 required set "
    "里真实存在的 merge 家族场景上，并在**真实契约形态**上跑 oracle（真实 10 列绑定 + "
    "真实重复 label），而不是为了让它进分母去改 profile"
)

#: 🔴 **登记的上游缺口 ③（本任务新发现）**：契约的 `mode` 是**按字段（=按列）**声明的，
#: 而「实体作列头」的两级动态矩阵，其公式/可编辑性在源模板里是**按行**分布的。
#:
#: 三段可打红的实测链条（见守卫 `TestTwoLevelMatrixModeIsPerColumn`）：
#:
#: 1. 上市侧 `重要联营企业主要财务信息`（源 `A169:G187`）与本 pilot 选中的国企侧
#:    `主要财务信息` 同构（都是 `{实体} × {期末/期初}` 两级矩阵），但它的 **6 列 × 17 行
#:    共 102 格逐格都是公式**，其中 `B173:G173`（资产合计）/ `B176:G176`（负债合计）是
#:    `=SUM(...)`、其余是跨 sheet 引用；
#: 2. `contracts._parse_table` 把 `mode` 放在 field 上，而行域字段的 `cell.row_from` 只能是
#:    `row_identity` ⇒ 一列一个 mode，行级差异表达不了；
#: 3. `excel_extract.verify_formula_regions` 的 `declared_protected_keys` 取
#:    `contract.protected_field_keys()`（按 field），`excel_materialize._emit` 也按
#:    `spec.mode` 判 ⇒ 把矩阵当动态行表时，行级受保护语义在读写两侧同时丢失。
#:
#: 本 pilot 的规避办法是**把矩阵声明成静态块**（字段 = `(metric, column)` 逐格，mode 精确到
#: 格），代价是它不再享有 `row_identity` 的插删重排语义 —— 对「metric 行是固定披露项」的表
#: 恰好无损，但对「实体作列头 + 行也可增删」的表就无解。
#: 修法在 schema 侧：允许 `row_identity` 表按行声明 mode 覆盖（例如 `row_mode_overrides`），
#: 属设计级变更（Requirement 6.6 / design §Contract schema 都要一起改）。
#: owner 建议归 contract schema 侧（Task 13 后续）。
UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_PER_COLUMN: Final[str] = (
    "Task 43 欠账：per-entry contract 的 `mode` 是按 field（=按列）声明的，而「实体作列头」"
    "的两级动态矩阵其公式/可编辑性在源模板里按**行**分布 ⇒ 把矩阵当动态行表时行级受保护"
    "语义在读写两侧同时丢失。实证：上市侧同构表 `重要联营企业主要财务信息`（源 A169:G187）"
    "6 列 × 17 行共 102 格全是公式，其中 B173:G173 / B176:G176 是 =SUM(...)、其余是跨 sheet "
    "引用；把它写成动态行表只能给 6 个列字段各一个 mode。本 pilot 因此把矩阵声明成**静态块**"
    "（字段 = (metric, column) 逐格，mode 精确到格），并选国企侧 100 格全空、全 editable 的"
    "那张表，使 merge 家族两条 required scenario 可满足。"
    "修法：schema 侧允许 row_identity 表按行覆盖 mode（如 row_mode_overrides），"
    "并同步 Requirement 6.6 / design §Contract schema 的措辞。"
    "owner 建议归 contract schema 侧（Task 13 后续）"
)

#: 🔴 **登记的上游缺口 ④（本任务新发现）**：Excel 侧与渲染层的动态列**键空间不同**。
#:
#: * 契约（Excel 侧）：一列一键 ``{slot}_{seq}``，`slot` = 契约 `table_key`
#:   （`DYNAMIC_COLUMN_IDENTITY_TEMPLATE` 硬编在 `contracts._parse_dynamic_columns`，
#:   `identity != "{slot}_{seq}"` 直接拒）；
#: * 渲染层：一实体两子列 ``{slot}_{seq}_{subKey}``，`slot` = 渲染层槽位名
#:   （`g7SlotColumns.buildG7SlotColumns` 实测）。
#:
#: 两者**都符合各自的规则**，但换算必须有人做。今天它由本模块的
#: :func:`render_column_key_for_seq` 承担（唯一换算处 + 守卫用 `.ts` 真实规则反向核对）。
#: 风险：任何**别的** entry 再遇到「实体 × 子列」矩阵时，如果各自写一份换算，就会出现
#: 第二真源。修法在 schema 侧：让 `dynamic_columns` 能声明 `sub_columns`，由校验器统一派生
#: 两套键并把双射固定进契约（而不是留给每个 pilot 各写一遍）。
UPSTREAM_DEBT_SLOT_SUBCOLUMN_KEY_SPACE_SPLIT: Final[str] = (
    "Task 43 欠账：Excel 侧与渲染层的动态列键空间不同 —— 契约只能用 "
    '`{slot}_{seq}`（`contracts._parse_dynamic_columns` 对 identity != "{slot}_{seq}" 直接'
    "拒，且 `excel_materialize` 的绑定形态是「一键一列」)，而渲染层 "
    "`g7SlotColumns.buildG7SlotColumns` 对带子列的表产出 `{slot}_{seq}_{subKey}`"
    "（一实体两子列）。两者各自正确，但双射今天由每个 pilot 自己写"
    "（本 pilot 的 render_column_key_for_seq 是唯一换算处）。"
    "风险：下一个「实体 × 子列」矩阵 entry 会写第二份换算 ⇒ 第二真源。"
    "修法：`dynamic_columns` 增加 `sub_columns` 声明，由契约校验器统一派生两套键并把双射"
    "固定进 canonical payload。owner 建议归 contract schema 侧（Task 13 后续）"
)

#: 🔴 **登记的上游缺口 ⑤（本任务新发现）**：渲染层的披露行 id 是**位置派生**的。
#:
#: `g7SoeDisclosureModel.blankRows()` / `metricRows()` 都用 ``${prefix}-${index + 1}``
#: 生成行 id。对本 pilot 的**矩阵**无害（10 个 metric 是固定披露项，第 i 个 id 恒对应源第
#: i 个 metric，是**语义序号**），但对同一模型里**真正可增删的**表（如
#: `former-subsidiary-basic` / `lte-movement`）就是 AC 6.5 明禁的「数组下标作持久化身份」：
#: 删掉第 2 行再新增一行会得到同一个 `-2` id，历史值会串到新行。
#:
#: 本 pilot 因此**不**把渲染层行 id 用作记录表的行身份：`former_subsidiary_basic` 的
#: `row_identity` 指向注入的 `rowUuid`（`GTROW-G7N-0079` 一类字面量），
#: 而它的 6 个数据列全是 formula ⇒ HTML 侧不写这张表，位置派生 id 不进任何持久化身份。
UPSTREAM_DEBT_RENDER_ROW_IDS_ARE_POSITIONAL: Final[str] = (
    "Task 43 欠账：`g7SoeDisclosureModel` 的 `blankRows()` / `metricRows()` 用 "
    "`${prefix}-${index + 1}` 生成披露行 id ⇒ 对**可增删**的披露表（former-subsidiary-basic "
    "/ lte-movement 等）等于用数组下标作持久化身份（AC 6.5 明禁）：删第 2 行再新增会复用 "
    "`-2`，历史值串到新行。对本 pilot 的 10 个固定 metric 行无害（语义序号），故本契约的"
    "矩阵按 metric id 寻址、记录表的 row_identity 走注入的 rowUuid 而不是渲染层 id。"
    "修法：渲染层可增删表改用一次性随机 rowId（H1 的 `disp-mrgi0qg1-fwwm` 范式）并在 store "
    "里持久化。owner 建议归 G7 披露底稿 owner；engine 侧不做兼容层"
)


#: 🔴 **登记的上游缺口 ⑥（本任务新发现，真实库实证）**：改造前持久化的矩阵列键
#: （``c1Current`` … ``c5Prior``）**没有迁移**，当前渲染层读不到它们。
#:
#: 真实库实测（`test_task43_g7_two_level_dynamic_pilot_pg.py` 冻结）：`checklist_responses`
#: 里 `item_id = 'G7-main-disclosure-soe-v2'` 共 **3** 条，其中
#:
#: * 2 条用改造后的 ``{slot}_{seq}_{subKey}``（`minority-fs-company_1_current` …）；
#: * **1 条**（字节数最大的那一条）仍用改造前的 ``c{n}Current`` / ``c{n}Prior``。
#:
#: 归档 spec `g7-four-table-extraction-and-disclosure-alignment` Task 5.6 把写死列数改成
#: `buildG7SlotColumns` 时，只换了**生成端**，没有为存量载荷写 upgrader；`applySavedState`
#: 按键名回填，于是老键的值在 UI 上直接消失（不是显示为 0，而是那一列变空）。
#:
#: 本 pilot **不**自造 `c1Current → minority-fs-company_1_current` 的映射
#: （Requirement 6.1 禁止无来源自造字段；而且 `c{n}` 的 n 与实体序号的对应关系没有留下
#: 任何可验证的来源）。:func:`build_store_projection` 对「一整行有值却一个键都对不上」
#: **fail closed** 并点名历史键，让它成为可见故障而不是静默丢数据。
UPSTREAM_DEBT_LEGACY_COLUMN_KEYS_STRANDED: Final[str] = (
    "Task 43 欠账（真实库实证）：改造前持久化的矩阵列键 `c{n}Current` / `c{n}Prior` 没有"
    "迁移。真实库里 `G7-main-disclosure-soe-v2` 共 3 条，2 条用改造后的 "
    "`{slot}_{seq}_{subKey}`、1 条（字节最大的那条）仍是历史键 ⇒ 该底稿的重要非全资子公司"
    "主要财务信息在当前 UI 上整块读不出来。归档 spec "
    "g7-four-table-extraction-and-disclosure-alignment Task 5.6 只改了生成端、没写存量 "
    "upgrader。本 pilot 不自造 `c1Current → minority-fs-company_1_current` 的映射"
    "（Requirement 6.1；且 `c{n}` 与实体序号的对应关系无可验证来源），"
    "`build_store_projection` 对这类载荷 fail closed 并点名历史键。"
    "修法：写一次性 store upgrader（按 entitySlots 顺序重键）并留迁移记录。"
    "owner 建议归 G7 披露底稿 owner；engine 侧不做兼容层"
)


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """从已 published representation **现读** :class:`FrozenEntryDefinitions`。

    ═══ Task 75 交付：原先这里 `raise` ═══

    Task 43 交付时这里按「缺公共观测器」的欠账登记 fail closed —— 缺的是
    「published representation artifact → FrozenEntryDefinitions」的公共观测器
    （`ExcelEntryDefinitionLoader.load()` 的四个运行时实测入参当时只有 finalize 时刻的
    candidate evidence 一个来源）。Task 75 把那个观测器建成了
    :mod:`app.services.workpaper_sync.published_identity_observer`，本函数改为**调它**，
    那条欠账登记随之删除（本模块现在一个字都不再提它）。

    本 entry 是四类 pilot 里唯一真有 ``{slot}_{seq}`` 动态列的那个 ⇒
    ``observed_dynamic_columns`` 必须非空，由观测器的 ``observe_dynamic_columns()`` 从
    工作簿的**物理**列跨度 + merge 铺开后的 label 现读（label 只进 observed 侧，key 一律走
    ``dynamic_column_stable_keys(slot, count)``，签名里拿不到 label）。

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
       这不是吞异常，而是"这个 entry 今天还不是双向 pilot"这一事实的忠实表达。
       **今天恒走这一条**。
    2. `entry_state` 必须已有 **published** representation（Task 36 finalize 之后才有）。
    3. representation 必须绑定 approved bundle。
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
        #    Task 41 实测过 raise 的后果：它一抛就让 `_registration` / `_apply_durable_incoming`
        #    对**所有** entry 都 500 —— 一个尚未启用的 pilot 把整条 sync 路由拖下水
        #    （Task 28 的路由守卫 8 例打红）。
        #
        #    判据没有被放宽：`assert_manifest_capability_enabled()` 仍是顺序门（守卫直接调
        #    它、变异仍打红），本 entry 在 registry 里依旧没有 adapter ⇒ `_registration`
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

    🔴 **今天必然抛**：任务正文的顺序是「经 Task 36 反读四边真源并 finalize 其 candidate
    为 published representation 后**才**启用」。finalize 被
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


def _unused_instrumentation_error_guard() -> tuple[type[InstrumentationError], type[FieldSpec]]:
    """保留 `InstrumentationError` / `FieldSpec` 的显式引用（本模块 payload 构建的类型）。"""
    return InstrumentationError, FieldSpec
