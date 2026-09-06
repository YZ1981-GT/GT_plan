# -*- coding: utf-8 -*-
"""H1 分组/动态结构 Excel pilot —— **冻结的那一个 H1 entry** 自己的身份、契约与骨架策略。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 42
Requirements: 6.3, 6.4, 6.5, 6.9, 6.16, 12.1, 12.2, 12.10, 14.1
Properties: **P22 / P23 / P27 / P49 / P66 / P69**

本模块**不借用** Task 40（`b60.hour_budget`）或 Task 41（`d2.receivable_detail`）的任何
definition identity：authority model / template / instrumentation / contract / bundle 全部
是本 entry 自己发布的（任务正文明令）。

═══ 一、为什么冻结的是 `xlsx/gt-h1-fixed-assets` ═══

Task 39 的 :func:`~app.services.workpaper_sync.pilot_harness.assess_pilot_classes` 用正则
``(^|[^a-z0-9])h1([^0-9]|$)`` 划出 `h1_grouped_dynamic` 类，在真实 manifest（186 条 entry）
上实测**只有 1 个**候选、`bidirectional` **0 个** —— 没有可选空间，本模块只把它固定下来，
并由守卫在 `assess_pilot_classes()` 的真实输出上重新推导。

必要条件逐条现推（**不抄** Task 40/41 的结论；第 2 条实测是**第三种形态**）：

1. `independent_entry = true`（AC 12.1「每个**独立** entry」）。实测 true、
   `parent_entry_id = None`。
2. **权威模板必须唯一可解且不是「静默回退到别的底稿」**。本 entry 的
   `wp_match.wp_code_patterns == ["H1F"]`，而 `H1F` **根本不是一个 wp_code** ——
   它是 manifest 生成器把宿主文件名当输入抽出来的**名字提取产物**：
   `generate_workpaper_sync_manifest._source_match()` 对
   ``Path("GtH1FixedAssets.vue").stem`` 跑正则 ``[A-Z][0-9]+(?:-[0-9]+)*(?:[A-Z])?``，
   ``GtH1FixedAssets`` 里的 ``H1F`` 恰好命中。故本条不是 Task 40 的「wp_code 与
   `_index.json` 精确相等」，也不是 Task 41 的「三个 finder 入口全空 + YAML 声明同码」，
   而是**四条实测事实**（:func:`assert_pilot_entry_selectable` 把每条写成一个可打红判据）：

   * **零回退的最强形态是"根本没有回退"**：`find_template_file("H1F")` /
     `find_template_file_any("H1F")` / `find_all_template_files("H1F")` 实测分别是
     `None` / `None` / `[]` —— `H1F` 既不精确命中索引、`wp_templates/H` 下没有以 `H1F`
     开头的文件、``"-" not in "H1F"`` 所以连子码回退分支都进不去。
   * `H1F` 可证是**提取产物而非真码**：它不在 `_index.json` 的 `wp_code` 值域里（0 行）、
     不在任何 `filename` 前缀里（0 个），而把生成器那条正则重跑在宿主文件名上**能逐字
     复现**它。⇒ 本 entry 真正的码族是 `H1`。
   * `H1` 在 `_index.json` 里**精确唯一**（恰 1 行，`wp_code == "H1"`、`relative_path`
     就是 :data:`TEMPLATE_RELATIVE_PATH`），且 `find_template_file("H1")` 实测落在同一份
     文件 —— 这一条与 Task 40 同形态。
   * **配置真源**独立声明同一份工作簿：
     `backend/data/ledger_adapters/wp_render_schema/H1-1.yaml`（`wp_code: H1-1`，同一
     工作簿的审定表子码）的 `template_path` 恰是
     ``backend/wp_templates/H/H1 固定资产.xlsx``。
     🔴 这里**不能**照抄 Task 41 的 `payload["wp_code"] in PILOT_WP_CODES` 判据 ——
     该 YAML 的 `wp_code` 是 `H1-1` 而本 pilot 的 matcher 域是 `{"H1F"}`，两者本就不该
     相等；正确的判据是「声明的码属于本 entry 的**码族** `H1`」（见
     :func:`render_schema_template_path`）。

   四条合起来 ⇒ 契约里每个 `source_ref` 指向的单元格确实属于 H1 固定资产自己的工作簿。
3. `scenario_profile.profile_id = xlsx.editable.shared.single.room_service_wired.v1`
   ⇒ required scenario set 是 shared+editable 的标准 **24** 条，不走 authority-model
   替换分支，Property 25/26 必跑。实测本 entry 的 `required_scenario_set_digest` =
   ``319d10b4…``，与 B60 的 ``984681c2…``、D2 的 ``76d49456…`` **都不同** ——
   evidence 按本 bundle 自己的 digest 记录（任务正文要求）。

═══ 二、权威模板只认 `backend/wp_templates/` ═══

:data:`TEMPLATE_RELATIVE_PATH` 指向 ``H/H1 固定资产.xlsx``，:data:`TEMPLATE_SHA256` 是它
的字节哨兵。`基础数据/致同通用审计程序及底稿模板（2025年修订）/` 下**没有**这份文件的
参考副本（实测 `rglob` 0 命中），本模块一次都不读那棵树。
:func:`read_authoritative_template` 每次读都比对哨兵，改一个字节就抛（Requirement 9.9）。

工作簿共 **26** 张 sheet。逐 sheet 审核（openpyxl 直读全部 26 张，见守卫
`TestAuthoritativeTemplate::test_managed_sheet_is_the_only_declared_one` 与本任务
evidence 的 `sheet_audit.json`）后本契约**只**声明 `减少检查表H1-8` ——
`excel_extract.managed_tables_of()` 对「受管 sheet 之外还声明了表」显式 fail closed，
一次 extract 只覆盖一张 sheet。

🔴 **为什么不是 `明细表H1-2`**（工作簿里分组结构最深、且真实库里有 9,026 字节载荷的那张）：
它的表头是**四行**（9/10/11/12，例如 E 列的路径是
`固定资产原值 > 未审数 > 本期增加 > 金额`），而 per-entry contract 的 `header_rows` 值域
被 `contracts._parse_table` 硬限为 **1..3**，并且 Task 13 的守卫
`test_task13_contract_registry.py` 用 ``@pytest.mark.parametrize("header_rows", [0, 4, "2", True])``
把「4 必须被拒」显式锁死。⇒ 今天的契约 schema **表达不了**四级表头；把 anchor 下移到行 10
会丢掉最外层分组（`固定资产原值 / 累计折旧 / 减值准备`），那正是「分组表头」本身。
故 H1-2 登记为 :data:`UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE`，本 pilot 选
schema 域内分组最深的 `减少检查表H1-8`（三级、`header_rows = 3` 取到上界）。

═══ 三、逐格审核 `减少检查表H1-8`（人工审核依据）═══

真实网格（openpyxl 直读，dims `A1:AA43`，**32 处 merge**，3 处横向组合并 + 1 处四列组）：

* **行 10/11/12 是三级表头**（`header_rows = 3`）。行 10 给出 8 个纵向合并的单列
  （`A10:A12 序号` … `H10:H12 对方科目`）+ **4 个横向组**
  （`I10:O10 减少情况` 跨 7 列 / `P10:Q10 审批单` / `R10:T10 合同/协议/订单` /
  `U10:W10 发票`）+ 3 个纵向单列（`X10:X12 ……` / `Y10:Y12 索引号` / `Z10:Z12 是否异常`）。
  行 11 在 `减少情况` 组内再分两级（`I11:L11 转入清理的固定资产` / `M11:N11 清理净收入` /
  `O11:O12 清理净损益`），行 12 才是叶子（`I12 原值 / J12 累计折旧 / K12 减值准备 /
  L12 净值` 与 `M12 清理费用 / N12 清理收入`）。
* 🔴 **Property 22 在本表上有真实（非合成）oracle**：三个证据组的叶子 label **逐字重复** ——
  `日期/编号` 出现在 `P11` / `R11` / `U11`（**3 次**）、`对手方名称` 出现在 `S11` / `V11`
  （2 次）、`金额` 出现在 `T11` / `W11`（2 次）。**7 列共用 3 个 label**。identity 若用
  label 就会撞键（平台 H7 已付过学费）；本契约的 `column_key` / `stable_field_key` 与
  label 完全解耦，7 个键互不相同。
* **行 13..27 是动态数据区**（`A13..A26` 是模板字面量 1..14、`A27` 是占位 `……`），
  **15 行物理骨架**。
* **`L` 与 `O` 两列在数据行里逐行有真公式**：``=I{r}-J{r}-K{r}`` / ``=N{r}-M{r}-L{r}``
  ⇒ 契约里 `mode=formula` + `formula_mask` 两段区域。其余 23 列在模板里**没有**公式
  （逐格实测），故判 `editable` / `auto_source`。
* **`A28 合计` 是 footer**（`I28..O28` 全是 `SUM(x13:x27)`）⇒
  `footer_anchor = {marker: 合计, search_column: A}`，不写死行号。
* **受管区域之下还有真内容**（未管理区域，插删行必须不动它们）：
  `A29 本期减少固定资产合计` = ``='明细表H1-2'!O33``（**跨 sheet 引用**）、
  `A30 检查比例` = ``=IF(I28=0,0,I28/$I$29)``、`A31/A36/A40..A42` 是说明与提示，
  `AA11` 是一条列外注解（`检查的关键证据和要素根据被审计单位具体情况修改`）。
* **样式源**（`managed_sheet_structure` aspect 覆盖）：**2 条数据验证** ——
  `B13:B27` list ``房屋及建筑物,机器设备,运输设备,办公设备,其他设备``、
  `E13:E27` list ``处置,其他减少``；条件格式 0 条；`sheetProtection` 关；`cols` 17 条。

`X` 列（`X10:X12` 值恰为 `……`）是模板的**扩展占位列**，没有业务语义、也没有对应前端
字段 —— 按 Requirement 6.1「禁止无来源自造字段」**不声明**为受管字段。故受管字段是
**25** 个（A..Z 的 26 列减去 X）。

隐藏 row UUID 列取 `AB`：`managed_last_col = Z`（col 26），而 `AA` 列**有内容**
（`AA11` 注解），把 UUID 写在 `AA` 并隐藏该列会藏掉一条可见注解
（Requirement 6.13「不得改变业务公式/标签」）⇒ 必须再右移一列。

═══ 四、骨架行数取 `max(seed, 1)`（平台铁律：动态区骨架行数禁写死）═══

:func:`skeleton_row_count` 是本模块**唯一**决定动态区行数的地方，实现恰为
``max(int(seed), 1)``：

* `seed = 0` ⇒ **1**（不是 3/5/10/15）。预置多余空占位行会被下游推成占位披露行；
* `seed = 1` ⇒ 1；`seed = 15` ⇒ 15；`seed = 1260` ⇒ 1260 —— 上限由
  `limits.SyncLimits` 的行预算在**运行时边读边判**（本模块不含任何阈值数字）。

:data:`TEMPLATE_SKELETON_ROWS` 是**模板事实**（15，由守卫用 openpyxl 从
`A13..A27` 与 footer `A28` 反推），**不是**骨架策略：`instrumentation_spec()` 的行区间
也经 :func:`skeleton_row_count` 计算，只是把模板自己的骨架行数当 seed 传进去 ——
所以「15」来自源侧推导而不是写死的常量算术。守卫
`TestSkeletonRowPolicy` 断言 `skeleton_row_count(0) == 1 != TEMPLATE_SKELETON_ROWS`，
并做源码级判据「模块里没有第二处行数算术」。

═══ 五、HTML store 与三源锁死 ═══

H1 宿主 `GtH1FixedAssets.vue` 的 H1-8 面板是 `H1TabDisposalCheck.vue`，store 是
`checklist_responses`（`item_id → remark`）。整张表落在 :data:`STORE_ITEM_ID`
（``H1-8-rows``，来自 `useH1DisposalCheck.ts` 的 ```${ITEM_PREFIX}-rows`​``）这一条
`remark` 里，形态是行对象 JSON 数组，行身份是载荷自带的 `rowId`
（形如 ``disp-mrgi0qg1-fwwm``）。数组下标**永不**进入任何 key
（Requirement 6.5 / Property 23）。

🔴 **实测：真实库里这一条 item 今天是空的** —— 5 个有 `H1-*` item 的底稿里
`H1-8-rows` 一条都没有（全库 0 行），而 `H1-2-rows` 有 9,026 字节。因此本 pilot 的
merge / delete-update oracle 跑在**按契约常量派生的合成行**上，并由 pg 侧守卫把
「今天为空」这一事实冻结成可打红的判据（真实数据一旦出现且形态不符即打红）。
结构性判据（identity 保留 / 公式范围 / 未管理区域）一律跑在**真实权威模板 + 真实注入
产物**上，不手搓最小 xlsx —— 手搓的工作簿上「未管理区域」是空集恒真。

三源锁死（本模块不是第二个真源，也不自造字段）：

1. **源 xlsx** 行 10/11/12 的真实表头文本与 `B/E` 两列的 DV 值域 —— 每个字段的
   `header_source_ref` / `mid_source_ref` / `group_source_ref` 指向具体单元格，
   守卫用 openpyxl 直读比对；
2. **前端行形态真源** `useH1DisposalCheck.ts` 的 `DisposalRow` 接口 + `addRow()`
   初始化键集合 —— 守卫解析该文件比对 25 个 json 路径逐个存在；
3. **前端类别真源** `useH1Detail.ts` 的 `H1_2_CATEGORY_OPTIONS` —— 守卫比对它与
   `B13:B27` 的 DV 五个取值**逐字同序相等**。

═══ 六、顺序与登记的上游缺口 ═══

`template → instrumentation → contract → bundle → representation` 的顺序由 Task 12 的
`DefinitionPublisher` 强制，payload 由 Task 17 的 builder 生成 —— 本模块**不**自己拼
payload、不自己算 digest、不自己校验 bundle slot（复制一份的后果不是"更安全"，
而是任一侧被短路都不改变行为 ⇒ 变异检验判 GREEN）。

磁盘契约 ``backend/data/workpaper_sync_contracts/h1.disposal_check.json`` 与本模块现算
payload **双向锁死**（:func:`assert_contract_file_matches_source`），且两个生产入口
（:func:`publish_pilot_definitions` / :func:`attach_pilot_adapters`）**都**必须经这把锁 ——
Task 40 实测过「守卫自己调锁、从不检查生产路径」会让整组变异判 GREEN。

四条缺口按 Task 40/41 的处置办：**fail closed 抛可分辨异常，绝不返回 `None`**，
adapter 不注册、capability 不启用、manifest digest 不变，「契约孤儿」进
`registry.build_report().contract_files_without_adapter` 当可见欠账。

【已于 Task 75 结清】原第一条缺口「缺 published representation artifact →
`FrozenEntryDefinitions` 的公共观测器」已由
:mod:`app.services.workpaper_sync.published_identity_observer` 交付，登记常量已删除。
今天挡住 finalize 的是**供给**：approved bundle / published representation 两表实测
0 行，生产侧 provisioner 是 Task 76 的交付。
* :data:`UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY` —— Task 41 发现、
  **本 entry 同样命中**：`evidence.derive_for_manifest_entry` 只在
  `scenario_profile.mount_cardinality == "dynamic"` 时追加 `DYNAMIC_SCENARIOS`，而该字段
  量的是**前端宿主挂载基数**。实测全 manifest 186 条里 `dynamic` 只 1 条且是 docx ⇒
  `dynamic_row_add_delete_reorder_copy`（AC 6.9）与 `dynamic_column_stable_keys`（AC 6.4）
  对**任何 xlsx entry** 结构性不可达，包括本 pilot。⇒ Property 22/23/27 **不能**落在那两条
  场景上，改落 required set 里真实存在的 merge 家族两条，并在真实契约形态上跑 oracle。
* :data:`UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE` —— **本任务新发现**：契约
  `header_rows` 值域 1..3 表达不了 `明细表H1-2` 的四级表头（见 §二）。
* :data:`UPSTREAM_DEBT_DISPOSAL_METHOD_ENUM_DOMAIN_SPLIT` —— **本任务新发现**：
  `E 减少方式` 的模板 DV 值域是 ``处置 / 其他减少``（会计科目口径），而前端
  `H1TabDisposalCheck.vue` 的下拉是 ``出售 / 报废 / 损毁 / 捐赠 / 盘亏 / 其他``
  （业务口径），两者互不为子集。本 pilot **不**为绕开它自造映射
  （Requirement 6.1 禁止无来源自造字段），照实登记。
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
    "AUTHORITY_MODEL",
    "CATEGORY_DV_CELL_RANGE",
    "CATEGORY_DV_VALUES",
    "DISPOSAL_METHOD_DV_CELL_RANGE",
    "DISPOSAL_METHOD_DV_VALUES",
    "FIRST_DATA_ROW",
    "FOOTER_MARKER",
    "FOOTER_ROW",
    "FORMULA_MASK",
    "FORMULA_TEMPLATES",
    "GROUP_HEADER_ROW",
    "HEADER_LEAF_ROW",
    "HEADER_MID_ROW",
    "HEADER_ROW_COUNT",
    "LAST_DATA_ROW",
    "MANAGED_FIELD_SPECS",
    "MANAGED_LAST_COL",
    "MANAGED_SHEET",
    "PILOT_ADAPTER_ID",
    "PILOT_CLASS",
    "PILOT_ENTRY_ID",
    "PILOT_WP_CODES",
    "PILOT_WP_CODE_FAMILY",
    "PLACEHOLDER_COLUMN",
    "RENDER_SCHEMA_RELATIVE_PATH",
    "ROWS_TABLE_KEY",
    "ROW_IDENTITY_STORE_KEY",
    "SHEET_KEY",
    "STORE_ITEM_ID",
    "TABLE_NAME",
    "TEMPLATE_ID",
    "TEMPLATE_RELATIVE_PATH",
    "TEMPLATE_SHA256",
    "TEMPLATE_BUSINESS_SKELETON_ROWS",
    "TEMPLATE_PHYSICAL_LAST_ROW",
    "TEMPLATE_SKELETON_ROWS",
    "TEMPLATE_TYPOGRAPHY_TAIL_ROWS",
    "UNMANAGED_BELOW_FOOTER_CELLS",
    "UPSTREAM_DEBT_DISPOSAL_METHOD_ENUM_DOMAIN_SPLIT",
    "UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY",
    "UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE",
    "UUID_COL",
    "PilotDefinitions",
    "PilotSelectionError",
    "StorePayloadError",
    "TemplateResolutionFacts",
    "assert_contract_file_matches_source",
    "assert_dynamic_family_is_unreachable_for_xlsx_entries",
    "assert_manifest_capability_enabled",
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
    "excel_carrier_gate",
    "group_header_cell_of",
    "instrumentation_definition_payload",
    "instrumentation_spec",
    "iter_store_rows",
    "leaf_header_cell_of",
    "load_pilot_contract",
    "manifest_capability_enabled",
    "mid_header_cell_of",
    "publish_pilot_definitions",
    "read_authoritative_template",
    "register_pilot_adapter",
    "render_schema_template_path",
    "resolve_published_frozen_definitions",
    "skeleton_row_count",
    "split_store_row",
    "stable_key_for",
    "store_row_identity",
    "template_definition_payload",
]


class PilotSelectionError(SyncDomainError):
    """冻结的 pilot entry 不再满足选型必要条件（manifest / 模板真源漂移即打红）。"""

    error_code = "sync_pilot_selection_invalid"


class StorePayloadError(SyncDomainError):
    """HTML store 载荷形态不合法（非数组 / 缺行身份 / 重复行身份 / 非法 JSON）。

    刻意与 :class:`PilotSelectionError` 分型：「选型漂移」与「载荷坏了」是两类完全不同的
    故障，合并成一个错误码会让较早的分支永久不可达（本 spec 已实测 3 次的形态）。
    """

    error_code = "sync_pilot_store_payload_invalid"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 冻结的身份常量
# ═══════════════════════════════════════════════════════════════════════════

#: 本 pilot 覆盖的 AC 12.2 四类之一（与 `pilot_harness.PilotClass` 同域）。
PILOT_CLASS: Final[str] = "h1_grouped_dynamic"

#: 从 source-backed manifest 冻结的 entry（`assess_pilot_classes()` 的唯一 H1 候选）。
PILOT_ENTRY_ID: Final[str] = "xlsx/gt-h1-fixed-assets"

#: adapter_id == contract_id == 契约文件名（registry RG-4 双向锁死）。
PILOT_ADAPTER_ID: Final[str] = "h1.disposal_check"

#: matcher 的 wp_code 集合 —— 取自本 entry 的 `wp_match.wp_code_patterns`。
#:
#: 🔴 `H1F` 不是真 wp_code，是 manifest 生成器从宿主文件名 `GtH1FixedAssets.vue` 抽出来的
#: 名字提取产物（见模块 docstring §一）。它照实进 matcher 域（matcher 必须覆盖该 entry 的
#: 全部 wp_code、不得多也不得少），而模板解析走下面的**码族**。
PILOT_WP_CODES: Final[frozenset[str]] = frozenset({"H1F"})

#: 本 entry 真正的 wp_code 族（`_index.json` 里精确唯一的那个码）。
PILOT_WP_CODE_FAMILY: Final[str] = "H1"

#: `backend/wp_templates/` 下的权威模板。
TEMPLATE_RELATIVE_PATH: Final[str] = "H/H1 固定资产.xlsx"

#: 权威模板字节哨兵（Requirement 9.9：`backend/wp_templates/` 运行时只读）。
TEMPLATE_SHA256: Final[str] = (
    "344f83216b9024e3c3fde7c1ed545eb0026a6cf088a0b0dfd0916e47b64fdc87"
)

#: 声明权威模板的**配置真源**（`wp_code: H1-1` 是同一工作簿的审定表子码）。
RENDER_SCHEMA_RELATIVE_PATH: Final[str] = (
    "backend/data/ledger_adapters/wp_render_schema/H1-1.yaml"
)

#: 受管 sheet 的真实 tab 名（构建期选择器；运行时定位一律走 identity 锚点）。
MANAGED_SHEET: Final[str] = "减少检查表H1-8"

#: instrumentation 的模板短码（进 row UUID 前缀与 `GT_*` defined names）。
TEMPLATE_ID: Final[str] = "H18"

#: 契约 sheet_key —— 必须与 `build_instrumentation_payload` 产出的
#: `managed_sheets[0].sheet_key`（`f"{template_id.lower()}-managed"`）一致。
SHEET_KEY: Final[str] = f"{TEMPLATE_ID.lower()}-managed"

ROWS_TABLE_KEY: Final[str] = "disposal_check_rows"

#: 三级表头的三行：组标题 10、中层 11、叶子 12（`header_rows = 3`，取到 schema 上界）。
GROUP_HEADER_ROW: Final[int] = 10
HEADER_MID_ROW: Final[int] = 11
HEADER_LEAF_ROW: Final[int] = 12
HEADER_ROW_COUNT: Final[int] = HEADER_LEAF_ROW - GROUP_HEADER_ROW + 1

#: 动态数据区起始行（模板事实）。
FIRST_DATA_ROW: Final[int] = 13

#: 权威模板里**物理骨架行数**（`A13..A26` 字面量 1..14 + `A27` 占位 `……`）。
#:
#: 🔴 这是**模板事实**，不是骨架策略：骨架策略是 :func:`skeleton_row_count`
#: （``max(seed, 1)``）。守卫用 openpyxl 从 `A13..A27` 与 footer `A28` 反推这个数，
#: 并断言 `skeleton_row_count(0) == 1 != TEMPLATE_SKELETON_ROWS`。
TEMPLATE_SKELETON_ROWS: Final[int] = 15

#: 物理骨架行里属于**排版占位**的尾部行数（`A27` 的 `……`，1 行）。
#:
#: 🔴 BP-21：中文审计模板在数据区末尾放一行续行省略号，它是排版符号不是业务行。
#: 把它算进受管行区间会让 `materialize` 试图把 `……` 按 `integer` 写回 `seq` 字段 ——
#: 首版发布实测就卡在这里（`EditableCellWriteError`，受管格 `A27`）。
#:
#: 这个数**不是**本模块自己判的：`excel_instrumentation` 在注入期调
#: :func:`app.services.workpaper_sync.excel_typography_rows.assert_last_data_row_is_not_typography_placeholder`
#: 现读模板字节，声明的 `last_data_row` 落在占位行上即 fail closed 并给出应声明的值。
#: 于是本常量是「被生产门验证过的模板事实」，不是一处可以写错而无人发现的数字。
#: 全库同形态实测 170 处 / 37 份模板 / 35 个 wp_code。
TEMPLATE_TYPOGRAPHY_TAIL_ROWS: Final[int] = 1

#: 真实**业务**骨架行数 = 物理骨架 − 尾部排版占位行（14 行，`A13..A26`）。
TEMPLATE_BUSINESS_SKELETON_ROWS: Final[int] = (
    TEMPLATE_SKELETON_ROWS - TEMPLATE_TYPOGRAPHY_TAIL_ROWS
)


def skeleton_row_count(seed: int) -> int:
    """动态区骨架行数 = ``max(seed, 1)``。**本模块唯一**决定行数的地方。

    平台铁律「动态区骨架行数禁写死」：`blankRows(p, 3|5|10)` 那种预置空占位会被下游推成
    占位披露行。这里既不写 3/5/10，也不把模板自己的 :data:`TEMPLATE_SKELETON_ROWS` 当
    默认值 —— seed 为 0 时得到 **1** 行。

    上限不在这里判：行/字段预算由 `limits.SyncLimits` 在 extract/split 时**边读边判**
    （本模块不含任何阈值数字）。

    :param seed: 已有业务行数（HTML store 里的行数）。
    """
    return max(int(seed), 1)


#: **受管**行区间末行 = 起始行 + 业务骨架行数 - 1。经 :func:`skeleton_row_count` 计算，
#: seed 取权威模板自己的**业务**骨架行数 ⇒ 这个数来自源侧推导而非写死的行数算术。
#:
#: 🔴 BP-21 起 seed 用 :data:`TEMPLATE_BUSINESS_SKELETON_ROWS`（14）而不是
#: :data:`TEMPLATE_SKELETON_ROWS`（15）：末行 `A27` 是排版占位 `……`，不是业务行。
LAST_DATA_ROW: Final[int] = (
    FIRST_DATA_ROW + skeleton_row_count(TEMPLATE_BUSINESS_SKELETON_ROWS) - 1
)

#: **物理**骨架末行（含尾部排版占位行）= 27。
#:
#: 🔴 它与 :data:`LAST_DATA_ROW`（26）是**两件事**，混用是 BP-21 落地时踩过的坑：
#:
#: * :data:`LAST_DATA_ROW` = 受管业务行区间末行 ⇒ Table ref、row UUID、projection、
#:   `formula_mask`（受管的只读区）都按它算；
#: * 本常量 = 模板**物理**结构的末行 ⇒ 模板自带的那些覆盖整个骨架的事实按它算：
#:   两个数据验证区（`B13:B27` / `E13:E27`）、footer 的合计区间（`SUM(x13:x27)`）、
#:   以及 `L`/`O` 两列**逐行**公式（占位行上也有）。
#:
#: 首版实测：把 DV 区间也跟着受管区收缩成 `B13:B26` 后，`enum_source_ref` 指向一个模板里
#: **不存在**的区间 ⇒ 守卫 `KeyError: 'B13:B26'`、枚举值域读成空集。
#: 合计区间同理：模板里是 `SUM(I13:I27)`，它对受管区末行 26 属**超集**（
#: `assert_footer_formula_covers_managed_rows` 的判据是 `last >= effective_last_row`）
#: ⇒ 收缩受管区不会让合计判据打红，但把它写成 `SUM(I13:I26)` 就与模板不符了。
TEMPLATE_PHYSICAL_LAST_ROW: Final[int] = FIRST_DATA_ROW + TEMPLATE_SKELETON_ROWS - 1

#: footer 所在行（`A28 合计`）—— 紧跟**物理**骨架末行。
#:
#: 🔴 它与 :data:`LAST_DATA_ROW` 之间隔着那 :data:`TEMPLATE_TYPOGRAPHY_TAIL_ROWS` 行占位行
#: —— BP-21 之前二者相邻，那只是因为占位行被误算成了业务行。footer 的物理位置（`A28`）
#: 没有变，守卫仍用 openpyxl 断言 `A{FOOTER_ROW}` 的文本恰为 `合计`。
FOOTER_ROW: Final[int] = TEMPLATE_PHYSICAL_LAST_ROW + 1

#: 最后一列受管业务列（`Z 是否异常`）。
MANAGED_LAST_COL: Final[str] = "Z"

#: 隐藏 row UUID 列。
#:
#: 🔴 不是 `AA`：`AA11` 里有一条可见注解（`检查的关键证据和要素根据被审计单位具体情况修改`），
#: 把 UUID 写进 `AA` 并隐藏该列会藏掉它（Requirement 6.13「不得改变业务公式/标签」）。
UUID_COL: Final[str] = "AB"

#: 注入的 Excel Table displayName（OOXML 要求字母/下划线开头、无空格）。
TABLE_NAME: Final[str] = f"GT_{TEMPLATE_ID}_ROWS"

#: 本 pilot 是 projection-based ⇒ 三个 typed child 全部必须是 approved definition。
AUTHORITY_MODEL: Final[AuthorityModel] = AuthorityModel.projection_contract

#: 模板的**扩展占位列**（`X10:X12` 值恰为 `……`）。没有业务语义、没有前端字段 ⇒
#: 按 Requirement 6.1「禁止无来源自造字段」**不**声明为受管字段。
PLACEHOLDER_COLUMN: Final[str] = "X"

#: 公式列 → 数据行公式模板（`{r}` 为行号）。守卫逐行与权威模板比对。
FORMULA_TEMPLATES: Final[Mapping[str, str]] = {
    "L": "=I{r}-J{r}-K{r}",
    "O": "=N{r}-M{r}-L{r}",
}

#: 两个公式列的只读区域（逐格实测 `=I-J-K` / `=N-M-L`）。
FORMULA_MASK: Final[tuple[str, ...]] = tuple(
    f"{column}{FIRST_DATA_ROW}:{column}{LAST_DATA_ROW}"
    for column in sorted(FORMULA_TEMPLATES)
)

#: footer 定位标记（`A28` 的真实文本）。
FOOTER_MARKER: Final[str] = "合计"

#: HTML store 里承载整张表的那一条 item（`useH1DisposalCheck.ts` 的 `${ITEM_PREFIX}-rows`）。
STORE_ITEM_ID: Final[str] = "H1-8-rows"

#: 「审计师还没录任何一行」时的 store 载荷。
#:
#: 🔴 由 **provider 自己**声明，而不是让调用方拿一个通用常量喂所有 pilot。
#:    起因（2026-09-05 实测）：宿主 `fix_projection_first_publication.py` 曾用单一
#:    `_EMPTY_STORE_PAYLOAD = "[]"` 喂全部四个 pilot，而 G7 的载荷根形态是 **对象**
#:    不是数组 ⇒ 它必然 `StorePayloadError`。「空载荷长什么样」是每个 pilot 的
#:    store schema 决定的，只有 provider 自己知道，放在调用方就是猜。
#:
#: 本 pilot 的根形态是行数组，因此空行集就是 `[]` —— `build_store_projection` 对它
#: 产出 `values` 与 `row_keys` 皆空的 Projection（实测 values=0），下游无额外约束。
EMPTY_STORE_PAYLOAD: Final[str] = "[]"

#: 载荷里每行自带的稳定行身份键（形如 `disp-mrgi0qg1-fwwm`）。
ROW_IDENTITY_STORE_KEY: Final[str] = "rowId"

#: `B13:B27` 的数据验证值域（**样式源**；与前端 `H1_2_CATEGORY_OPTIONS` 逐字同序相等）。
#:
#: 🔴 区间用 :data:`TEMPLATE_PHYSICAL_LAST_ROW`（27）而不是 :data:`LAST_DATA_ROW`（26）：
#: 这是 `enum_source_ref` 指向的**模板实际 DV 区间**，模板里它覆盖整个物理骨架（含占位行）。
#: 跟着受管区收缩会让 source_ref 指向一个不存在的区间（实测 `KeyError: 'B13:B26'`）。
CATEGORY_DV_CELL_RANGE: Final[str] = f"B{FIRST_DATA_ROW}:B{TEMPLATE_PHYSICAL_LAST_ROW}"
CATEGORY_DV_VALUES: Final[tuple[str, ...]] = (
    "房屋及建筑物",
    "机器设备",
    "运输设备",
    "办公设备",
    "其他设备",
)

#: `E13:E27` 的数据验证值域（**会计科目口径**；与前端业务口径下拉互不为子集，
#: 见 :data:`UPSTREAM_DEBT_DISPOSAL_METHOD_ENUM_DOMAIN_SPLIT`）。
#: 🔴 同 :data:`CATEGORY_DV_CELL_RANGE`：DV 区间是物理模板事实，用物理末行。
DISPOSAL_METHOD_DV_CELL_RANGE: Final[str] = (
    f"E{FIRST_DATA_ROW}:E{TEMPLATE_PHYSICAL_LAST_ROW}"
)
DISPOSAL_METHOD_DV_VALUES: Final[tuple[str, ...]] = ("处置", "其他减少")

#: 受管区域**之下**的真实内容（未管理区域；插删行必须不动它们）。
#: `(单元格, 期望内容)` —— 守卫用 openpyxl 逐格比对。
UNMANAGED_BELOW_FOOTER_CELLS: Final[tuple[tuple[str, str], ...]] = (
    (f"A{FOOTER_ROW + 1}", "本期减少固定资产合计"),
    (f"I{FOOTER_ROW + 1}", "='明细表H1-2'!O33"),
    (f"A{FOOTER_ROW + 2}", "检查比例"),
    (f"I{FOOTER_ROW + 2}", f"=IF(I{FOOTER_ROW}=0,0,I{FOOTER_ROW}/$I${FOOTER_ROW + 1})"),
    ("AA11", "检查的关键证据和要素根据被审计单位具体情况修改"),
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 三级表头的分组声明（逐格 openpyxl 实测得来）
# ═══════════════════════════════════════════════════════════════════════════

#: 行 10 的**横向组**：`(组标题单元格, 覆盖列元组, 组标题文本)`。
#:
#: 逐格实测的 merge：`I10:O10` / `P10:Q10` / `R10:T10` / `U10:W10`。
#: 其余列在行 10 是 `X10:X12` 形态的纵向合并（单列、无组），不进本表。
GROUP_HEADERS: Final[tuple[tuple[str, tuple[str, ...], str], ...]] = (
    (f"I{GROUP_HEADER_ROW}", ("I", "J", "K", "L", "M", "N", "O"), "减少情况"),
    (f"P{GROUP_HEADER_ROW}", ("P", "Q"), "审批单"),
    (f"R{GROUP_HEADER_ROW}", ("R", "S", "T"), "合同/协议/订单"),
    (f"U{GROUP_HEADER_ROW}", ("U", "V", "W"), "发票"),
)

#: 行 11 的**中层**（只在 `减少情况` 组内存在）：`(中层单元格, 覆盖列元组, 文本)`。
#:
#: 逐格实测：`I11:L11 转入清理的固定资产` / `M11:N11 清理净收入` /
#: `O11:O12 清理净损益`（后者是纵向合并到叶子行，故它同时是中层与叶子）。
MID_HEADERS: Final[tuple[tuple[str, tuple[str, ...], str], ...]] = (
    (f"I{HEADER_MID_ROW}", ("I", "J", "K", "L"), "转入清理的固定资产"),
    (f"M{HEADER_MID_ROW}", ("M", "N"), "清理净收入"),
    (f"O{HEADER_MID_ROW}", ("O",), "清理净损益"),
)

#: `column_key → (列标, mode, value_type, json 路径, 叶子表头单元格, 叶子表头文本)`。
#:
#: 🔴 **顺序即 Excel 列序**（A → Z，跳过 :data:`PLACEHOLDER_COLUMN`）。
#: `json 路径`是 store 行对象里的键名（camelCase，来自
#: `useH1DisposalCheck.DisposalRow`），`column_key` 是契约侧的小写稳定键。
#:
#: 🔴 **叶子表头单元格是逐格实测的 merge 左上角**，不是「列标 + 叶子行号」：
#: 8 个纵向合并单列（A..H）与 3 个（X/Y/Z）的锚点在**行 10**，`O` 的锚点在**行 11**，
#: 只有 `减少情况` 组内的 6 列（I/J/K/L/M/N）锚点真在行 12。用位置猜会把 label 取空。
MANAGED_FIELD_SPECS: Final[tuple[tuple[str, str, str, str, str, str, str], ...]] = (
    ("seq", "A", "auto_source", "integer", "seq", f"A{GROUP_HEADER_ROW}", "序号"),
    ("category", "B", "editable", "enum", "category", f"B{GROUP_HEADER_ROW}", "固定资产类别"),
    ("asset_no", "C", "editable", "text", "assetNo", f"C{GROUP_HEADER_ROW}", "固定资产编号"),
    ("asset_name", "D", "editable", "text", "name", f"D{GROUP_HEADER_ROW}", "固定资产名称"),
    (
        "disposal_method", "E", "editable", "enum", "disposalMethod",
        f"E{GROUP_HEADER_ROW}", "减少方式",
    ),
    (
        "disposal_date", "F", "editable", "date", "disposalDate",
        f"F{GROUP_HEADER_ROW}", "减少日期",
    ),
    ("voucher_no", "G", "editable", "text", "voucherNo", f"G{GROUP_HEADER_ROW}", "凭证号"),
    (
        "counterpart_account", "H", "editable", "text", "counterpartAccount",
        f"H{GROUP_HEADER_ROW}", "对方科目",
    ),
    (
        "original_cost", "I", "editable", "amount", "originalCost",
        f"I{HEADER_LEAF_ROW}", "原值",
    ),
    ("acc_dep", "J", "editable", "amount", "accDep", f"J{HEADER_LEAF_ROW}", "累计折旧"),
    (
        "impairment", "K", "editable", "amount", "impairment",
        f"K{HEADER_LEAF_ROW}", "减值准备",
    ),
    ("net_value", "L", "formula", "amount", "netValue", f"L{HEADER_LEAF_ROW}", "净值"),
    (
        "disposal_cost", "M", "editable", "amount", "disposalCost",
        f"M{HEADER_LEAF_ROW}", "清理费用",
    ),
    (
        "disposal_income", "N", "editable", "amount", "disposalIncome",
        f"N{HEADER_LEAF_ROW}", "清理收入",
    ),
    (
        "disposal_gain_loss", "O", "formula", "amount", "disposalGainLoss",
        f"O{HEADER_MID_ROW}", "清理净损益",
    ),
    (
        "application_ref", "P", "editable", "text", "applicationRef",
        f"P{HEADER_MID_ROW}", "日期/编号",
    ),
    (
        "is_approved", "Q", "editable", "enum", "isApproved",
        f"Q{HEADER_MID_ROW}", "是否经过恰当审批",
    ),
    (
        "contract_ref", "R", "editable", "text", "contractRef",
        f"R{HEADER_MID_ROW}", "日期/编号",
    ),
    (
        "contract_party", "S", "editable", "text", "contractParty",
        f"S{HEADER_MID_ROW}", "对手方名称",
    ),
    (
        "contract_amount", "T", "editable", "amount", "contractAmount",
        f"T{HEADER_MID_ROW}", "金额",
    ),
    (
        "invoice_ref", "U", "editable", "text", "invoiceRef",
        f"U{HEADER_MID_ROW}", "日期/编号",
    ),
    (
        "invoice_party", "V", "editable", "text", "invoiceParty",
        f"V{HEADER_MID_ROW}", "对手方名称",
    ),
    (
        "invoice_amount", "W", "editable", "amount", "invoiceAmount",
        f"W{HEADER_MID_ROW}", "金额",
    ),
    ("index_ref", "Y", "editable", "text", "indexRef", f"Y{GROUP_HEADER_ROW}", "索引号"),
    (
        "is_abnormal", "Z", "editable", "enum", "isAbnormal",
        f"Z{GROUP_HEADER_ROW}", "是否异常",
    ),
)


def _col_index(letters: str) -> int:
    """A1 列标 → 1-based 列序号（`Z` → 26、`AB` → 28）。"""
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index


def group_header_cell_of(column: str) -> str:
    """某列的**组标题单元格**（行 10 的横向组锚点）；不在任何组内则返回空串。"""
    for cell, columns, _label in GROUP_HEADERS:
        if column in columns:
            return cell
    return ""


def mid_header_cell_of(column: str) -> str:
    """某列的**中层表头单元格**（行 11 锚点）；无中层则返回空串。

    只有 `减少情况` 组内的列有中层；且 `O` 列的中层锚点与叶子锚点是同一格
    （`O11:O12` 纵向合并）—— 这种形态下**不**重复声明中层，避免同一格既是 leaf 又是 mid
    造成「三级」名义上成立而实际只有两级的假象。
    """
    for cell, columns, _label in MID_HEADERS:
        if column not in columns:
            continue
        leaf = leaf_header_cell_of(column)
        return "" if cell == leaf else cell
    return ""


def leaf_header_cell_of(column: str) -> str:
    """某列的**叶子表头单元格**（实测 merge 左上角）。未登记列即抛。"""
    for _key, col, _mode, _vt, _path, leaf_cell, _label in MANAGED_FIELD_SPECS:
        if col == column:
            return leaf_cell
    raise PilotSelectionError(
        f"列 {column!r} 不在本 pilot 的受管字段里 —— 受管列集合由 "
        "MANAGED_FIELD_SPECS 单一声明（占位列 "
        f"{PLACEHOLDER_COLUMN!r} 按 Requirement 6.1 刻意不声明）"
    )


#: `column_key → 组标题文本`（守卫与源 xlsx 比对）。
GROUP_HEADER_LABELS: Final[Mapping[str, str]] = {
    column_key: label
    for column_key, column, *_rest in MANAGED_FIELD_SPECS
    for cell, columns, label in GROUP_HEADERS
    if column in columns
}

#: `column_key → 中层表头文本`（只有有中层的列在表内）。
MID_HEADER_LABELS: Final[Mapping[str, str]] = {
    column_key: label
    for column_key, column, *_rest in MANAGED_FIELD_SPECS
    for cell, columns, label in MID_HEADERS
    if column in columns and cell != leaf_header_cell_of(column)
}


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


def render_schema_template_path(*, payload: Mapping[str, Any] | None = None) -> str:
    """`H1-1.yaml` 里声明的 `template_path`（配置真源，不在本模块复制字面量判定）。

    这条读取存在的意义是让「权威模板由配置唯一声明」成为**运行时可打红的事实**：
    YAML 改指到另一份工作簿，:func:`assert_pilot_entry_selectable` 立刻失败。

    🔴 判据是「声明的码属于本 entry 的**码族**」而**不是** Task 41 的
    `wp_code in PILOT_WP_CODES`：该 YAML 的 `wp_code` 是 `H1-1`（同一工作簿的审定表子码），
    而本 pilot 的 matcher 域是 `{"H1F"}`（名字提取产物），两者本就不该相等。抄 Task 41 的
    判据会让这条永远失败，进而逼人把判据关掉。

    :param payload: 已解析的 schema。默认现读磁盘 —— 这个参数只为让「配置的 wp_code 跳出
        本 entry 码族」这一分支可测（否则它对真实数据结构性不可达，永久 GREEN）。
    """
    import yaml

    path = _REPO_ROOT / RENDER_SCHEMA_RELATIVE_PATH
    if payload is None:
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except OSError as exc:
            raise PilotSelectionError(f"H1-1 渲染 schema 不可读: {path}: {exc}") from exc
    declared_code = str(payload.get("wp_code") or "")
    if not re.fullmatch(rf"{re.escape(PILOT_WP_CODE_FAMILY)}(-\d+)?", declared_code):
        raise PilotSelectionError(
            f"{RENDER_SCHEMA_RELATIVE_PATH} 的 wp_code={declared_code!r} 不属于本 pilot 的 "
            f"码族 {PILOT_WP_CODE_FAMILY!r}（形如 `H1` 或 `H1-<n>`）—— "
            "配置真源与 entry 脱钩，它声明的 template_path 不能再当本 entry 的权威模板"
        )
    return str(payload.get("template_path") or "")


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
    欠账（清册生成器只扫 `backend/app`，脚本不在其内）。Task 40/41 已为同类形态各付过
    一次代价，正解是让那一行从清册里**整行消失**。

    这里需要的是「解析结果」这一**事实**，不是「谁去解析」：调用方（契约生成器与守卫）
    用真实 finder 取事实，本模块只做判定。判定被短路时守卫立刻打红。

    :param by_wp_code: `wp_code → 三个 finder 入口解析出的路径`（本 pilot 要求**全空**）
    :param index_wp_codes: `_index.json` 里全部 `wp_code` 值（用于「H1F 不是真码」判据）
    :param index_filenames: `_index.json` 里全部 `filename` 值（同上）
    :param family_code: 真正的码族（`H1`）
    :param family_resolved_paths: 码族在三个 finder 入口上的解析结果（要求全部 == 权威模板）
    :param family_index_rows: `_index.json` 里 `wp_code == family_code` 的行（要求恰 1 行）
    :param host_stem: 宿主组件文件名主干（`GtH1FixedAssets`），用于复现名字提取
    """

    by_wp_code: Mapping[str, Sequence[Any]]
    index_wp_codes: Sequence[str]
    index_filenames: Sequence[str]
    family_code: str
    family_resolved_paths: Sequence[Any]
    family_index_rows: Sequence[Mapping[str, Any]]
    host_stem: str


#: manifest 生成器抽 wp_code 的那条正则（`generate_workpaper_sync_manifest._source_match`）。
#: 复现它是「`H1F` 是名字提取产物」这一判据的核心 —— 不是断言常量等于常量。
WP_CODE_EXTRACTION_PATTERN: Final[str] = r"[A-Z][0-9]+(?:-[0-9]+)*(?:[A-Z])?"


def assert_wp_code_pattern_is_a_name_extraction_artifact(
    resolution: TemplateResolutionFacts,
) -> frozenset[str]:
    """证明 `H1F` 是从宿主文件名抽出来的产物，而不是一个真 wp_code。

    三条同时成立才放行（任一不成立 ⇒ `H1F` 可能真是个码，那本 pilot 的「零回退」判据
    就必须换成「精确唯一」形态，不能继续按提取产物处置）：

    1. 它不在 `_index.json` 的 `wp_code` 值域里；
    2. 它不是任何 `filename` 的前缀（`find_template_file_any` 的前缀回退分支进不去）；
    3. 把生成器那条正则重跑在宿主文件名主干上**能逐字复现**它。

    返回复现出的码集合（守卫据此断言 `H1F` 真在里面）。
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


def assert_pilot_entry_selectable(
    *,
    resolution: TemplateResolutionFacts,
    manifest: Mapping[str, Any] | None = None,
    declared_template_path: str | None = None,
) -> Mapping[str, Any]:
    """在**真实** manifest / 真实 resolver 事实上重新推导三条必要条件；任一不成立即抛。

    :param resolution: 见 :class:`TemplateResolutionFacts`。**必填**（没有默认值 ⇒
        不可能出现「没给就跳过」的 fail-open）。
    :param declared_template_path: `H1-1.yaml` 声明的 `template_path`。默认现读配置 ——
        这个参数只为让「配置指到别的工作簿」这一分支可测。
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

    assessment = assess_pilot_classes(manifest=payload)[PilotClass.h1_grouped_dynamic]
    if PILOT_ENTRY_ID not in assessment.candidate_entry_ids:
        raise PilotSelectionError(
            f"{PILOT_ENTRY_ID!r} 不在 assess_pilot_classes() 的 h1_grouped_dynamic 候选里"
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

    # ── ②-a 冻结的码是名字提取产物（不是真 wp_code）────────────────────────
    assert_wp_code_pattern_is_a_name_extraction_artifact(resolution)
    # ── ②-b 运行时**没有**任何隐式回退；码族精确唯一落在权威模板 ──────────────
    assert_no_implicit_template_fallback(resolution, wp_codes=frozenset(codes))

    # ── ②-c 权威模板由配置真源唯一声明 ──────────────────────────────────────
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

    返回 `{"xlsx_dynamic": (...), "dynamic": (...), "total": N}`。判据是**结构性的**：
    `evidence.derive_for_manifest_entry` 只按 `scenario_profile.mount_cardinality ==
    "dynamic"` 追加 `DYNAMIC_SCENARIOS`，所以只要 xlsx 侧该取值为空集，AC 6.4 / 6.9 自己的
    两条场景就对全部 xlsx entry 不可达。

    🔴 这条**不是**「断言缺口存在所以别管了」：它是欠账的可打红形态 —— 上游哪天把门改成
    按 contract 的 `row_identity` / `dynamic_columns` 判定（或给本 entry 的 profile 打上
    dynamic），`xlsx_dynamic` 就不再是空集，本函数抛错，欠账登记必须同步撤销。

    与 Task 41 的同名函数**刻意各自一份**：两个 pilot 的欠账文案、撤销条件与落点
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
            f"{xlsx_dynamic} —— `dynamic_row_add_delete_reorder_copy` 与 "
            "`dynamic_column_stable_keys` 不再对 xlsx 侧结构性不可达，"
            f"{UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY!r} 这条欠账必须撤销，"
            "并把 Property 22/23/27 的落点改到那两条场景上"
        )
    return {"dynamic": tuple(dynamic), "xlsx_dynamic": (), "total": len(entries)}


# ═══════════════════════════════════════════════════════════════════════════
# 5. instrumentation spec 与 definition payloads
# ═══════════════════════════════════════════════════════════════════════════


def instrumentation_spec() -> ExcelInstrumentationSpec:
    """本 entry 的 Task 17 instrumentation 声明。

    行区间的上界经 :func:`skeleton_row_count` 计算（见 :data:`LAST_DATA_ROW`），
    seed 取权威模板自己的物理骨架行数 —— **不是**在这里写 `27`。
    """
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
    """authoritative model definition 的 canonical payload（**本 entry 独立批准**）。

    `projection_contract` ⇒ 三个 typed child 全部必须是 approved definition；AC 12.12
    的「字段级两场景替换」只对 `custom_authoritative_ooxml` / `opaque_single_onlyoffice`
    开放，本 pilot 因此**不会**触发替换，Property 25/26 必跑。

    🔴 `entry_id` + `pilot_class` 进 payload ⇒ 本 entry 的 authority model digest 与
    Task 40/41 的**必然不同**，不可能出现「借用别的 pilot 的 definition identity」
    （任务正文明令；守卫 `test_pilot_does_not_reuse_other_pilot_identity` 逐项比对）。
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


def stable_key_for(column_key: str, row_identity: str = "{row_uuid}") -> str:
    """`disposal_check_rows/{row_uuid}/{column_key}` 的唯一拼装处。

    🔴 **Property 22**：键里只有 `column_key`（稳定小写键），**没有** label。本表有 3 个
    重复叶子 label（`日期/编号` ×3、`对手方名称` ×2、`金额` ×2 共 7 列），label 一旦进键
    就会撞键（平台 H7 已付学费）。
    """
    return f"{ROWS_TABLE_KEY}/{row_identity}/{column_key}"


def _rows_table_payload() -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for (
        column_key,
        column,
        mode,
        value_type,
        json_path,
        leaf_cell,
        leaf_label,
    ) in MANAGED_FIELD_SPECS:
        spec: dict[str, Any] = {
            "stable_field_key": stable_key_for(column_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_path}",
            "column_key": column_key,
            "cell": {"column": column, "row_from": "row_identity"},
            "mode": mode,
            "value_type": value_type,
            "source_ref": _src(f"{column}{FIRST_DATA_ROW}"),
            "header_source_ref": _src(leaf_cell),
            "store_item_id": STORE_ITEM_ID,
            "header_text": leaf_label,
        }
        mid_cell = mid_header_cell_of(column)
        if mid_cell:
            spec["mid_source_ref"] = _src(mid_cell)
            spec["mid_header_text"] = MID_HEADER_LABELS[column_key]
        group_cell = group_header_cell_of(column)
        if group_cell:
            spec["group_source_ref"] = _src(group_cell)
            spec["group_header_text"] = GROUP_HEADER_LABELS[column_key]
        if column_key == "category":
            spec["enum_source_ref"] = _src(CATEGORY_DV_CELL_RANGE)
            spec["enum_values"] = list(CATEGORY_DV_VALUES)
        if column_key == "disposal_method":
            spec["enum_source_ref"] = _src(DISPOSAL_METHOD_DV_CELL_RANGE)
            spec["enum_values"] = list(DISPOSAL_METHOD_DV_VALUES)
        fields.append(spec)
    return {
        "table_key": ROWS_TABLE_KEY,
        "anchor": f"A{GROUP_HEADER_ROW}",
        "header_rows": HEADER_ROW_COUNT,
        "row_identity": {"kind": "field", "json_pointer": f"/rows/*/{ROW_IDENTITY_STORE_KEY}"},
        "delete_policy": "tombstone",
        # 🔴 `carries_total_formula: True` 是**如实描述模板事实**，不是放宽：
        #    `I28..O28` 共 7 格逐格实测为 `SUM(x13:x27)`（见模块 docstring §二）。
        #    Spec: excel-structural-row-insertion-and-shift-aware-verification R5.1~5.4
        #
        #    不声明的后果（首版发布实测）：插行时
        #    `assert_footer_formula_covers_managed_rows` 判「合计区间覆盖不到位移后的末行」
        #    而引擎**无权**扩张它 ⇒ 结算 `blocked_total_formula_not_extendable`，
        #    即照插会产出一张合计漏算 N 行的审计底稿。声明为真才让引擎有权按
        #    **声明的**位移量扩张该区间（Requirement 4.4）；未扩张仍 fail closed。
        "footer_anchor": {
            "marker": FOOTER_MARKER,
            "search_column": "A",
            "carries_total_formula": True,
            "note": (
                "footer 行 A28 承载 7 条合计公式（I28..O28 = SUM(x13:x27)，逐格实测）。"
                "区间末行 27 是 BP-21 的排版占位行，合计公式覆盖它属超集 ⇒ 对受管区末行 "
                "26 仍然成立。声明为真使结构性插行有权按声明位移量扩张该区间"
            ),
        },
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
                    "整张表存成这一条 item 的 remark（一个 JSON 数组字符串），行身份是载荷"
                    "自带的 rowId。数组下标永不进入任何 key（Requirement 6.5 / Property 23）"
                ),
                "observed_empty_in_reference_database": True,
            },
            "grouped_header": {
                "group_row": GROUP_HEADER_ROW,
                "mid_row": HEADER_MID_ROW,
                "leaf_row": HEADER_LEAF_ROW,
                "groups": [
                    {"cell": cell, "columns": list(columns), "label": label}
                    for cell, columns, label in GROUP_HEADERS
                ],
                "mid_levels": [
                    {"cell": cell, "columns": list(columns), "label": label}
                    for cell, columns, label in MID_HEADERS
                ],
                "duplicate_leaf_labels": sorted(
                    {
                        label
                        for label in (row[6] for row in MANAGED_FIELD_SPECS)
                        if sum(1 for other in MANAGED_FIELD_SPECS if other[6] == label) > 1
                    }
                ),
            },
            "dynamic_rows": {
                "skeleton_row_policy": "max(seed,1)",
                "template_physical_skeleton_rows": TEMPLATE_SKELETON_ROWS,
                "note": (
                    "骨架行数由 pilot_h1_grouped_dynamic.skeleton_row_count(seed) 决定，"
                    "seed=0 时为 1 行。模板自带的 15 行是模板事实、不是骨架策略；"
                    "预置多余空占位会被下游推成占位披露行（平台铁律：动态区骨架行数禁写死）"
                ),
            },
            "style_sources": {
                "data_validations": [
                    {"sqref": CATEGORY_DV_CELL_RANGE, "values": list(CATEGORY_DV_VALUES)},
                    {
                        "sqref": DISPOSAL_METHOD_DV_CELL_RANGE,
                        "values": list(DISPOSAL_METHOD_DV_VALUES),
                    },
                ],
                "conditional_formatting_count": 0,
                "sheet_protection": False,
                "note": (
                    "样式源由 excel_extract.verify_unmanaged_regions 的 "
                    "managed_sheet_structure aspect 逐字节锁死"
                    "（mergeCells/cols/dataValidations/conditionalFormatting/sheetProtection）"
                ),
            },
            "unmanaged_below_footer": [
                {"cell": cell, "content": content}
                for cell, content in UNMANAGED_BELOW_FOOTER_CELLS
            ],
            "excluded_columns": [
                {
                    "column": PLACEHOLDER_COLUMN,
                    "header_source_ref": _src(f"{PLACEHOLDER_COLUMN}{GROUP_HEADER_ROW}"),
                    "reason": (
                        "模板的扩展占位列（表头文本恰为 `……`），没有业务语义也没有对应前端"
                        "字段 —— 按 Requirement 6.1「禁止无来源自造字段」不声明为受管字段"
                    ),
                }
            ],
            "reviewed_basis": (
                "openpyxl 逐 sheet 直读权威模板 H/H1 固定资产.xlsx 的 26 张 sheet，"
                "只取受管 sheet 减少检查表H1-8：三级表头 10/11/12 行（4 个横向组 "
                "I10:O10/P10:Q10/R10:T10/U10:W10 + 3 个中层 I11:L11/M11:N11/O11:O12 + "
                "6 个真叶子 I12..N12，其余 11 列为 X10:X12 形态的纵向合并）、"
                "动态区 13..27 行（15 行物理骨架，A13..A26 字面量 1..14 + A27 占位 ……）、"
                "L/O 两列逐行公式 =I-J-K / =N-M-L、A28 合计 footer（I28..O28 = SUM(x13:x27)）、"
                "B/E 两列共 2 条数据验证；25 个字段的 source_ref / header_source_ref / "
                "mid_source_ref / group_source_ref 均指向上述真实单元格。"
                "X 列是占位列故不声明；UUID 列取 AB 而非 AA（AA11 有可见注解）。"
                "明细表H1-2 因四级表头超出契约 header_rows 值域 1..3 而未选用，"
                "登记为 UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE"
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
            "请用 `py -3 backend/scripts/gen/generate_pilot_h1_grouped_dynamic_contract.py "
            f"--apply` 重生成 {contract_file_path().name}，并复核 diff"
        )
    # 现算 payload 自己也必须过强校验（磁盘对得上但两边都非法时仍要打红）。
    parse_contract(expected, adapter_id=PILOT_ADAPTER_ID)
    return on_disk


# ═══════════════════════════════════════════════════════════════════════════
# 7. store 载荷拆分（stable field + row UUID，流式）
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


def iter_store_rows(
    payload: str | bytes | Sequence[Any],
) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """流式 yield `(row_identity, row)`；重复身份即抛。

    接受三种输入形态（都是真实调用点）：`checklist_responses.remark` 的原始字符串、
    从库里以 bytes 读出的同一串、以及已解析好的数组。
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
            "整张表被存成别的形态时必须 fail closed，不得静默当成零行"
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


def split_store_row(
    row: Mapping[str, Any], *, row_identity: str, contract: SyncContract
) -> Iterator[tuple[str, Any, FieldSpec]]:
    """一行 → 25 条 `(stable_key, value, spec)`。

    `spec` 从 **contract** 取（`field_by_stable_key` 对未登记键直接抛），因此这里写错
    一个 column_key 会立刻炸，而不是静默产出一个契约里没有的字段。
    """
    for column_key, *_rest in MANAGED_FIELD_SPECS:
        json_path = next(
            spec[4] for spec in MANAGED_FIELD_SPECS if spec[0] == column_key
        )
        spec = contract.field_by_stable_key(stable_key_for(column_key))
        yield (
            stable_key_for(column_key, row_identity),
            row.get(json_path),
            spec,
        )


def build_store_projection(
    payload: str | bytes | Sequence[Any],
    *,
    contract: SyncContract,
    limits: Any | None = None,
) -> Any:
    """把 HTML store 载荷拆成按 stable field key 索引的 :class:`Projection`。

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


#: 🔴 **登记的上游缺口 ②**（Task 41 发现，本 entry 同样命中）：AC 6.4 / 6.9 自己的两条
#: 场景对 xlsx entry 结构性不可达。
#:
#: 由 :func:`assert_dynamic_family_is_unreachable_for_xlsx_entries` 把它变成可打红的
#: 实测事实；缺口一旦被上游修掉，那个函数会抛错，提醒撤销本条登记。
UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY: Final[str] = (
    "Task 42 欠账（Task 41 首次登记，本 entry 同样命中）："
    "`evidence.derive_for_manifest_entry` 只在 "
    '`scenario_profile.mount_cardinality == "dynamic"` 时追加 DYNAMIC_SCENARIOS，而该'
    "字段量的是**前端宿主挂载基数**（v-for 挂几个 OO 编辑器），不是「受管表有没有动态"
    "行/动态列」。实测全 manifest 186 条里只有 1 条为 dynamic 且是 docx ⇒ "
    "`dynamic_row_add_delete_reorder_copy`（AC 6.9）与 `dynamic_column_stable_keys`"
    "（AC 6.4）对**任何 xlsx entry** 都进不了 required set，包括本 H1 pilot —— 而本 pilot "
    "的契约恰恰声明了 row_identity + delete_policy，且源表有 7 列共用 3 个重复叶子 label。"
    "修法需要把 contract 的 row_identity / 列 identity 声明喂进 required-set 推导"
    "（会改动 B60/D2/G7 的 required digest），属设计级变更。owner 建议归 evidence 推导侧"
    "（Task 39 后续）；在此之前 Property 22/23/27 落在 merge 家族两条场景上，"
    "并在真实契约形态上跑 oracle"
)

#: 🔴 **登记的上游缺口 ③（本任务新发现）**：契约 `header_rows` 值域 1..3 表达不了
#: `明细表H1-2` 的**四级**表头，而那张 sheet 才是 H1 工作簿里分组最深、且真实库里唯一
#: 有载荷（9,026 字节 `H1-2-rows`）的那张。
#:
#: 三段可打红的实测链条（见守卫 `TestFourLevelHeaderIsAKnownSchemaLimit`）：
#:
#: 1. `明细表H1-2` 的表头物理上占 **4 行**（9/10/11/12）：例如 E 列的路径是
#:    `固定资产原值(D9:P9) > 未审数(D10:I10) > 本期增加(E11:F11) > 金额(E12)`；
#: 2. `contracts._parse_table` 对 `header_rows` 硬限 `1 <= header_rows <= 3`；
#: 3. Task 13 的 `test_task13_contract_registry.py` 用
#:    `@pytest.mark.parametrize("header_rows", [0, 4, "2", True])` 把「4 必须被拒」锁死。
#:
#: 把 anchor 下移到行 10 能让 `header_rows = 3` 通过，但会**丢掉最外层分组**
#: （`固定资产原值 / 累计折旧 / 减值准备`）—— 那正是「分组表头」本身，属于契约压扁列结构
#: （平台铁律：底稿→附注同步不得压扁列结构，同理适用于契约）。
#: 修法在 schema 侧：把 `header_rows` 值域扩到 1..4 并同步 Task 13 的边界参数化，
#: 属设计级变更（design §Contract schema 的示例与 Requirement 6.3 的「两级表头」措辞
#: 都要一起改）。owner 建议归 contract schema 侧（Task 13 后续）。
UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE: Final[str] = (
    "Task 42 欠账：per-entry contract 的 `header_rows` 值域被 "
    "`contracts._parse_table` 硬限为 1..3，且 Task 13 的 "
    'test_task13_contract_registry.py 用 parametrize([0, 4, "2", True]) 把 4 显式锁死为'
    "被拒 ⇒ H1 工作簿里分组最深的 `明细表H1-2`（表头物理占 4 行 9/10/11/12，"
    "例如 E 列路径 固定资产原值>未审数>本期增加>金额）**表达不了**。把 anchor 下移到行 10 "
    "可以凑到 3，但会丢掉最外层分组（固定资产原值/累计折旧/减值准备），即把列结构压扁。"
    "本 pilot 因此选 schema 域内分组最深的 `减少检查表H1-8`（三级，header_rows=3 取到上界），"
    "而真实库里唯一有载荷的 H1-2（9,026 字节 H1-2-rows）暂不进契约。"
    "修法：把 header_rows 值域扩到 1..4 并同步 Task 13 的边界参数化与 design "
    "§Contract schema / Requirement 6.3 的措辞。owner 建议归 contract schema 侧"
    "（Task 13 后续）"
)

#: 🔴 **登记的上游缺口 ④（本任务新发现）**：`E 减少方式` 的枚举值域在模板与前端之间**分叉**。
#:
#: * 源模板 `E13:E27` 的数据验证是 :data:`DISPOSAL_METHOD_DV_VALUES`
#:   （``处置 / 其他减少`` —— 会计科目变动口径，与 `明细表H1-2` 的 `H 减少方式` 同域）；
#: * 前端 `H1TabDisposalCheck.vue` 的下拉是 ``出售 / 报废 / 损毁 / 捐赠 / 盘亏 / 其他``
#:   （业务处置方式口径），`useH1DisposalCheck.needsScrapResidualWarning` 等联动逻辑按
#:   后者判断。
#:
#: 两者**互不为子集**。本 pilot 的 `value_type` 与 `enum_values` 一律以**源 xlsx** 为准
#: （契约的 source_ref 指向 DV 单元格区域），并**不**为绕开分叉自造映射 ——
#: 自造 `出售→处置` 一类映射就是无来源自造字段（Requirement 6.1 明令禁止），而且会让
#: OO 侧写回的值静默改变审计含义。
UPSTREAM_DEBT_DISPOSAL_METHOD_ENUM_DOMAIN_SPLIT: Final[str] = (
    "Task 42 欠账：`E 减少方式` 的枚举值域在权威模板与前端之间分叉 —— 模板 "
    "E13:E27 的数据验证是 `处置 / 其他减少`（会计科目变动口径），前端 "
    "H1TabDisposalCheck.vue 的下拉是 `出售 / 报废 / 损毁 / 捐赠 / 盘亏 / 其他`"
    "（业务处置方式口径），两者互不为子集。契约以源 xlsx 为准且不自造映射"
    "（Requirement 6.1 禁止无来源自造字段；自造 出售→处置 会让 OO 写回的值静默改变审计"
    "含义）。⇒ OO 侧按模板 DV 选值、HTML 侧按业务口径选值时，同一格会形成 enum 值域外"
    "的取值。修法二选一：把模板 DV 扩成业务口径的六项（须致同模板 owner 裁决），"
    "或在前端把业务口径收敛到模板两项并把细分方式挪到独立列。"
    "owner 建议归 H1 底稿 owner（模板/前端口径统一），engine 侧不做兼容层"
)


async def resolve_published_frozen_definitions(
    *, session: Any, representation: Any, contract: SyncContract
) -> Any:
    """从已 published representation **现读** :class:`FrozenEntryDefinitions`。

    ═══ Task 75 交付：原先这里 `raise` ═══

    Task 42 交付时这里按「缺公共观测器」的欠账登记 fail closed —— 缺的是
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

    🔴 **今天必然抛**：任务正文的顺序是「经 Task 36 校验动态 identity/visible equivalence
    并 finalize 其 candidate 为 published representation 后**才**启用」。finalize 被
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
