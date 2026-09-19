# Implementation Plan: E1 货币资金四表取数与披露/附注对齐

## Overview

> **状态：20/20 全部完成**（Task 13 按用户裁决选项 A 收口 —— 外币章节只补列元数据不接推送，
> 理由与三个备选方案见 Notes §外币落点裁决；行级合并能力建议另立平台级 spec）。
> 真实 DB 直跑 + 浏览器实测均通过，测试数据已复原（一处 AI 占位文本无快照不可逐字复原，已记录）。
> 实测另修掉 **2 个平台级 P0**（多槽规格被报表公式兜底污染 → 合计虚增一倍）
> 与 **2 个前端缺陷**（溯源面板读错路径 / 国企侧假勾稽差异），详见 Notes。

7 个 wave、20 个任务（含 Task 3.5）。Wave 1 的 Task 1 是**崩溃级 P0**（披露 Tab 因 TDZ 完全无法挂载），可独立先合。
Wave 2~6 按「后端取数 → 公式预设 → 前端真源 → 附注模板 → 外币章节 → 铁律收口」推进，Wave 7 实测收口。
Task 19（上市侧②表）**用户已裁决为「补」**，并追加 Requirement 11「受限资金动态取数」——候选集由 `BS-002` 映射规则驱动、按叶子名分类、未命中落 `unclassified` 供点选归类，适配各项目科目命名差异。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "P0 止血 + 后端取数收敛 + 受限动态取数",
      "tasks": ["1", "2", "3", "3.5", "4"],
      "parallel": false,
      "rationale": "Task 1 是崩溃级修复，独立可先合；Task 2~4 同改一个后端文件，串行；3.5 依赖 2/3 的叶子聚合结果"
    },
    {
      "wave": 2,
      "name": "公式预设纠偏",
      "tasks": ["5", "6"],
      "parallel": true,
      "rationale": "改 prefill_formula_mapping.json + 守卫，与前端互不触碰"
    },
    {
      "wave": 3,
      "name": "前端单一真源 + 消费点",
      "tasks": ["7", "8", "9", "10"],
      "parallel": false,
      "rationale": "scope 模块是 8/9/10 的依赖；均触碰 E1TabDisclosure.vue，串行避免并发覆盖"
    },
    {
      "wave": 4,
      "name": "附注模板结构修订",
      "tasks": ["11", "12"],
      "parallel": false,
      "rationale": "幂等脚本 + 守卫，须在 Task 9 的载荷列键定稿后做（模板 key 镜像载荷）"
    },
    {
      "wave": 5,
      "name": "外币章节打通 + 勾稽",
      "tasks": ["13", "14"],
      "parallel": true,
      "rationale": "外币映射与勾稽引擎互不依赖"
    },
    {
      "wave": 6,
      "name": "平台铁律收口 + CI",
      "tasks": ["15", "16"],
      "parallel": true,
      "rationale": "控件替换与 CI job 登记互不依赖"
    },
    {
      "wave": 7,
      "name": "实测与收口",
      "tasks": ["17", "18"],
      "parallel": false,
      "rationale": "真实 DB 直跑 → 浏览器实测 → 数据复原 → 复盘"
    }
  ]
}
```

## Wave 1 — P0 止血 + 后端取数收敛

- [x] 1. 修复 `E1TabDisclosure.vue` 的 TDZ 崩溃（P0，可独立合并）
  - 将第 62 行的 `watch([disclosureRows, restrictedRows, noteText, variant], …)` 下移到 `syncToDisclosureNotes` 声明之后
  - 删除第 81 行本地 `type DisclosureVariant`（与第 27 行 import 重复）
  - 新建守卫 `e1SetupOrder.spec.ts`：断言每个 `watch(` 引用的顶层 `const` 声明行号 < watch 行号；含反向自检（把 watch 移前必须红）
  - 用 `curl.exe http://localhost:3030/src/.../E1TabDisclosure.vue` 确认 transform 200（`get_diagnostics` 查不出此类）
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. `_e1_monetary_fund.py` 取数改委托共享件
  - **改用 `semantic_account_resolver`（比原计划的 `report_line_accounts` 更适合）**：新建
    `four_table/e_cycle_specs.py` 的 `E1_MONETARY_FUND_SPEC`（5 个语义槽按**科目名**逐项目定位）
  - 取数走 `fetch_tb_subtree` + `select_leaves` + `filter_by_prefixes` + `aggregate_leaves` + `parent_totals`
  - **已删除** `_CASH_PREFIX` / `_BANK_PREFIX` / `_OTHER_PREFIX` / `_fetch_leaf_accounts` / `_is_leaf`
  - `get_active_filter` 全签名 4 参 + `await`（币种映射查询亦然）
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. 补 `adjudication_prefill` + 修零余额账户过滤 + 平台标准 `tb_source_codes`
  - 纯函数 `build_e1_slot_leaves` / `build_e1_detail_rows` / `build_e1_account_list`（**不过滤零余额**）/
    `build_e1_tb_values` / `build_e1_adjudication_prefill` / `build_e1_parent_check`
  - `tb_source_codes` = `SemanticAccountResult.as_dict()` + `parent_check`（含 conflicts / unmapped_candidates）
  - `tb_amount` / `tb_amount_opening` 改取 tb_balance **叶子**合计（不用 trial_balance，该表有父子双算陈旧数据）
  - _Requirements: 2.4, 2.6, 2.7_

- [x] 3.5 受限资金动态取数（新建共享件 + render 输出）
  - 新建 `four_table/e1_restricted_buckets.py`：`E1RestrictedBucket` dataclass × 6 桶（5 桶逐字取源 xlsx R17~R21 + 「其他受限资金」），每桶带 `keywords`/`exclude_keywords`/`source_ref`；**顺序即优先级**（`信用证` 先于 `银行承兑`、`担保` 先于泛 `定期存款`、`结构性` 为 `pledged_deposit` 的否决词）
  - `classify_e1_restricted_leaf(name)` 名称优先 + 否决词 + **未命中返 `None`**；`bucket_defs_payload()` 下发前端
  - render 输出 `restricted_prefill{buckets, unclassified, source}`：候选集**由 `BS-002` 解析 → `account_mapping` 反解 → `select_leaves` 得来，不跨出货币资金族**
  - 守卫：Property 10（活体 12 个叶子名全 `None`）、Property 15（顺序优先级 + 两条打乱后必红的反向自检）、Property 16（桶和 + unclassified 和 == 三族叶子合计，不重不漏）
  - **实现中追加两处语义修正**：①`require_any_of` 共现要求 —— 源模板 R21 是「放在境外**且资金汇回受到限制**」，光凭「境外」二字归类会把香港子公司基本户误判成受限款项（会改变披露结论）②「境外」桶排序**必须先于**「质押」桶，否则 `境外冻结存款` 被「冻结」抢走；③`pledged_deposit` 去掉裸「保证」（`投标保证金` 不是定期/通知存款，应落兜底桶）
  - **全零叶子不进「待归类」面板**（活体 50+ 空账户会淹没面板；金额为 0 不破坏 Property 16 的求和恒等式）
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.11_

- [x] 4. 后端守卫 `test_e1_account_scope.py`
  - Property 1（叶子和 == 父额，用活体三项目数值）、Property 2（点号边界，构造 `1002.1`+`1002.11`，**旧实现必红**）、Property 3（零余额账户保留）、Property 4（字面量只许出现在 spec 与 slots 两处）
  - 反向自检：故意把 `select_leaves` 换回 `startswith` 实现，Property 2 必须失败
  - 诚实修正既有测试中钉死 `_is_leaf`/硬编码前缀语义的断言
  - _Requirements: 2.1, 2.5, 2.6_

## Wave 2 — 公式预设纠偏

- [x] 5. `fix_e1_prefill_presets.py`（幂等，`--dry-run`/`--check`/`--apply`）
  - **P0**：「数字货币明细表」块 `account_codes=['1502']` + `TB('1502',…)` → `1502` 实为**持有至到期投资减值准备**；改 `PLACEHOLDER` + 描述写明「数字货币按准则解释15号在货币资金项下二级列报，无独立标准科目，需项目级映射」，**不臆造科目码**
  - 「货币资金分析程序」块 `PREV('E1','分析程序E1-3','审定数')` → 源 xlsx 无该 tab，改真实 tab「货币资金分析表E1-14」
  - `TB_SUM('1001~1012',…)` → 显式 `TB('1001')+TB('1002')+TB('1012')`
  - 新增两张披露 sheet 块（`附注披露信息(上市公司)` / `附注披露信息(国企)`，**半角括号**），公式按源 xlsx 逐格（主表 `B8=='货币资金审定表E1-1'!G7` 等）
  - E1-1 审定表块补 `WP('E1','现金明细表E1-2',…)` / `WP('E1','银行存款及其他货币资金明细表(人民币及外币)E1-3',…)` / `WP('E1','数字货币明细表E1-4',…)`；**明细块禁 `WP()` 防成环**
  - **实现中追加 4 处**：①`applies_when="tb_account_exists:1502"` 是**死字段**（全仓 grep 无 Python 消费方；`chain_orchestrator` 同名字段读的是 `project_flags` 的 flag 名，属 B60 机制，`notes` 声称的「无 1502 则隐藏整 sheet」从未实现）→ 删除并把 `notes` 改成实情 ②`审定表E1-1` → `货币资金审定表E1-1`（源 xlsx 无短名 tab，同 G7 已修过的分叉）③`PREV('E1','审定表E1-1',…)` 与 `PREV('E1','分析程序E1-3',…)` **公式实参内的 sheet 名也要改**（首版只改了 `block.sheet`，漏的那条靠守卫抓出）④补 `本期借方/贷方发生额`（供 E1-14 分析与 E1-23 收支检查）
  - **`page_key` 撞键已消除**：`上年审定数` 原在审定表块与分析表块之间撞（`page_key=workpaper:E1` 忽略 sheet，同名互相遮蔽）→ 分析表块条目加前缀；实测 `convert_prefill_presets()` 加载 **44 条、重复 0**
  - **校验器自身踩坑并已修**：首版对整块 `json.dumps` 做「不得出现 1502/TB_SUM」断言，而 `description`/`notes` 里如实写着被纠正的反例 → 误判。改为只扫**语义字段**（`formula`/`formula_type`/`account_codes`/`applies_when`）+ 反向自检，同 `stripComments()` 一类坑
  - 实测：16 项变更 → `--check` 0 欠账 → 重跑幂等（第二轮又抓出 1 项公式内 sheet 名）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 6. 后端守卫 `test_e1_formula_presets.py`
  - Property 11（`account_codes` ∈ 标准科目表 ∩ `BS-002` 引用集；`1502` 不复活，反向自检）
  - Property 12（`wp_name`/`sheet_name` ∈ 源 xlsx 四 workbook 的 tab 名集合；`分析程序E1-3` 不出现）
  - 防成环（明细块禁 `WP()`）；`validate_formula` 返回**错误列表**（空 = 合法）非 bool；`ADJ`/`TB_SUM`/`LEDGER`/`PREV`/`PLACEHOLDER` 按 prefill 词汇表豁免
  - _Requirements: 3.6_

## Wave 3 — 前端单一真源 + 消费点

- [x] 7. 新建 `e1CurrencyScope.ts` / `e1RestrictedScope.ts` / `e1DisclosureScope.ts`（前端单一真源）
  - 币种：`E1_DEFAULT_CURRENCIES`（人民币/美元/日元/澳元/欧元）+ `E1_FX_GROUPS`（源 xlsx R38/R44/R50/R56 四段）+ `e1CurrencyRowKey(groupSlot, currencyKey, seq)`（**禁用 label 作 key**）
  - 受限类别：镜像后端 `bucket_defs_payload()`（**中文标签只在后端一份**，前端只作兜底展示）+ 人工归类 map 读写 + `resolveRestrictedRows()`（人工归类 > 自动分类 > unclassified）
  - 守卫 `e1CurrencyScope.spec.ts`（59 例）：组件源码币种/主表行/分组字面量**全部归零**；稳定 key PBT 不撞键；Property 17（人工归类优先、新增叶子不改已有行、reason 保留）
  - **实现中追加 `e1DisclosureScope.ts`**（披露主表行真源，每行带 `sourceRef`）：原 `LISTED_ITEMS`/`SOE_ITEMS` 内联在组件里，且 overseas 行写缩写「其中：存放境外」与源模板/附注的「其中：存放在境外的款项总额」不一致 → 已按源 xlsx 逐字纠正；合计行改按 `isTotal`/`isMemo` 判定不再硬编码 key
  - **🔴 载荷表示由预聚合改扁平叶子清单**：首版后端下发 `buckets`（预聚合）+ `unclassified`，实现前端合并时发现**预聚合是有损表示** —— 审计师把叶子改归到别的类别后无法重算原桶余额。改为下发 `leaves:[{code,name,opening,closing,slot,autoBucket}]`，聚合全部在前端做，人工改归属时两侧余额都能精确重算
  - **🔴 跨 sheet 键不可改**：`E1-adj-total-1001/1002/1012` 是**跨 spec 数据契约**（归档 spec 明确「供报表/附注引用」，`wp_formula.py` 亦引用，既有项目已按此键持久化）→ 一度改成语义槽名，发现后改回并加守卫钉死形态 `^E1-adj-total-\d{4}$`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 11.5, 11.7, 11.8, 11.10_

- [x] 8. `E1TabDisclosure.vue` 结构对齐源 xlsx
  - 上市 3 表 + 4 段文本；国企 4 表 + 2 段括注（逐格依据见 design）
  - overseas 行 label 改源模板字面「其中：存放在境外的款项总额」
  - 主表 R16 是**勾稽校验行**不是披露行 → 不进载荷、只进勾稽面板
  - 外币两表接 `e1CurrencyScope`（动态增删币种/分组，`ElMessageBox.prompt` 先输名称）
  - **②表两版共用**（上市按裁决新建）：接 `e1RestrictedScope` + 「从四表库带入受限资金」按钮 + 新建 `E1RestrictedUnclassifiedPanel.vue`（`unclassified` 叶子点选归入某类 / 新建自定义类别 / 标记不受限）；动态插行须 prompt 先输名称，行 key `restricted_{bucketKey|custom}_{seq}`
  - 自动分类**不覆盖已有金额**（空值或用户确认才写入，`previewSeedFromPrefill` 范式）
  - 每个文本域配 AI + 复核（后端 `_SECTION_PROMPTS` 同步登记，≥20 字 + 「不得虚构」）
  - **已完成**：①主表行/列头改由 `e1DisclosureScope` 驱动（overseas 行改源模板全称、合计行按 `isTotal`/`isMemo` 判定）②外币两表常量改由 `e1CurrencyScope` 派生，组件币种/分组/行标签字面量**全部归零** ③**②表升级为两变体共用 + 四表动态取数**：四表命中行金额只读派生（带「四表」tag + 来源科目 tooltip）、纯手工行可编辑、`ElMessageBox.prompt` 先输名称再建自定义类别、四表命中行禁直删并引导用「标记不受限」④**新增「待归类科目」面板**（`el-select` 归类 / 「标记不受限」/ 撤销；已标不受限的单独列示并说明金额仍进 F1-5/F1-6 差额侧）⑤持久化拆两键：`-restricted`（只存手工侧：受限原因 + 纯手工行金额，派生值不落库）+ `-restricted-map`（人工归类）⑥旧结构兼容迁移（`item` → 自定义 `bucketKey`、`amount` → `endingAmount`）⑦金额控件用 `WpAmountInput`
  - **🔴 修掉宿主漏传 `:html-data`**（N2 同款）：宿主有 `props.htmlData` 但两个披露 Tab 使用点都没传 → `restricted_prefill` 恒 undefined、受限四表取数静默失效。已补传 + 新建守卫 `e1HostPropWiring.spec.ts`（两使用点必传 `:html-data`/`:project-id`、组件必声明 prop、必须读 snake_case）
  - ⑧**披露说明按源模板分段**（`E1_NOTE_TEXTS_LISTED/SOE`，各 2 段：上市 受限及境外款项/存款利息，国企 受限及境外款项/数字货币），每段带 `sourceRef` + 源模板指引原文（就地琥珀块展示，**指引不进附注正文**）+ 专属 AI prompt（≥20 字 + 「不得虚构」）+ 独立持久化键；**旧单一 `noteText` 内容迁移到首段**不丢字；`_note_texts` 逐段带中文 title 且空段过滤
  - ⑨②表接**条件表 + `_removed_table_keys`**；合计行字面按本章节实证取 `合计`（**不套**平台的 `合 计`）
  - **🔴 实现中修正一处真实语义缺陷**：`restrictedRows` 的 `undefined`（调用方**不管**这张表）与 `[]`（管但当前为空）必须区分 —— 首版一律进 `_removed_table_keys`，会**越权删掉别的底稿推的同名表**（K3 vs K7 铁律）。修正后既有 `e1NoteSectionMap.spec.ts` 两条断言无需改动即通过；`buildNoteTexts` 保留裸字符串旧签名兼容，公开 API 不破
  - 守卫 `e1NoteTextsAndPayload.spec.ts`（含 Property 13 同步幂等 + 文本域必须 `@input` 回写）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 6.2, 6.3, 8.4, 8.5, 8.6, 11.6, 11.8, 11.10_

- [x] 9. `e1NoteSectionMap.ts` 载荷补全
  - `columns` 标 `flat`（`is_label` 列标 flat 即为「显式单级」—— 后端 `_extract_column_groups`
    的判据是「任一列带 `flat`」；seed 与推送两处都已加）
  - ②表按**条件表**语义 + `_removed_table_keys`（`undefined` = 不管这张表 → 跳过且不删；
    `[]` = 管但为空 → 不推空表且删。K3 vs K7 铁律）
  - `_note_texts` 分段（各 2 段），每条带**中文 title** + 空段过滤
  - `E1_NOTE_TOTAL_LABEL = '合计'`（按本章节实证，**不套**平台的 `合 计`）
  - **修 `buildE1SyncPayload(…, null, …)`**：组件新增 `applicableStandards` prop + 接
    `useHostApplicableStandards`（explicit > `html_data.project_context` > runtime），
    宿主两个使用点补传 `:applicable-standards`；守卫 `e1HostPropWiring.spec.ts` 加 4 条
    （每个使用点必传 / 宿主必走平台单一入口 / 不得留 `runtime.applicableStandards` 死 fallback /
    **不得再给 payload 传 `null` 准则**）
  - **列定义提为零参导出** `buildE1ListedColumns()` / `buildE1SoeColumns()` + `E1_MAIN_TABLE`
    + `E1_{LISTED,SOE}_SUBTABLE`，载荷改**委托** builder（原先 payload 里另写一份 = 双真源）
  - **基线播种（R7.5）经实证不需要**：postgres 只读查全库 `五、1`/`八、1` 仅 2 条曾同步过，
    `sub_table_data` 键恰为 `['货币资金']` / `['货币资金','受限制的货币资金明细']`
    —— 与当前载荷表名逐字相同，**无历史孤儿表**，加播种只会增加误删风险
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_

- [x] 10. `E1TabAdjudication.vue` 接四表 + 溯源面板
  - **溯源面板不是「改薄壳委托 `WpFourTableSourcePanel`」** —— 实测两者口径不同：
    平台那份对应 `report_line_accounts`（原值/备抵二分，读 `gross`/`provision`/`extra`），
    而 E1 走 `semantic_account_resolver`（多语义槽并列、无备抵二分、带 `conflicts` /
    `unmapped_candidates` / `chart_available`）。→ **新建平台共用件**
    `composables/shared/semanticAccountSource.ts`（零 Vue 依赖纯函数视图模型）
    + `shared/WpSemanticAccountSourcePanel.vue`（G 循环同样走语义 resolver，可直接复用）
  - 面板消除 `tb_source_codes` dead output，并显式暴露四件事：命中科目码/名/来源
    （客户科目表 > 标准科目表 > 兜底）、`found=false` 显示「本项目无此科目」**不伪装成 0**、
    `exact=false`（包含匹配）打「需复核」、`report_config` 冲突与旧准则待映射科目橙色告警、
    「叶子和 ≠ 父额」两个口径都列出
  - **「从四表库带入未审数」**：纯函数 `e1AdjudicationPrefill.ts`
    （`planE1AdjudicationPrefill` / `resolveE1PrefillWrites` / `describeE1PrefillPlan`）
    + `useE1Adjudication.applyFourTablePrefill`。**🔴 关键发现**：审定表未审数列本就由
    E1-2/E1-3/E1-4 经**跨 sheet 聚合键**喂入（`cashUnaudited` 等 computed 读的是
    `E1-cash-detail-total-unaudited` 这类键），写 `E1-adj-*` 会**静默无效**；而
    `flushSave` 只收集 `E1-adj-` 前缀 → 这些键必须在 `applyFourTablePrefill` 内**显式提交**，
    否则只改内存刷新即丢。守卫从 composable 源码反查 `getVal('...')` 键集与绑定表交叉锁死
  - `found=false` 整槽跳过；已有值不同 → 弹「覆盖 / 仅补空值」二选一（默认仅补空值，
    **已录入数据永不被静默覆盖**）；金额相等则幂等不写
  - 宿主补传 `:html-data` 给 `E1TabAdjudication`（原未传 → 两个功能都拿不到数据）
  - 前端契约 `e1NoteSubtableContract.spec.ts`（共享 helper P1~P6 + E1 专属 9 条：
    两版列头必须不同 / 载荷委托 builder / ②表不推「受限原因」列 / 合计行字面 /
    sheet 名半角 / undefined vs [] 语义 / `current_standard` 随准则变 / `_note_texts` 中文 title）
  - **明细表空表自动 seed 已存在**（`e1FourTablePrefill.ts` 的
    `buildCashSeedRows`/`buildBankSeedRows`/`buildAccountListSeedRows`/`buildCrossSheetSeeds`
    由宿主 `selfLoad` 消费），本任务不重复实现
  - _Requirements: 2.4, 2.7, 9.3, 9.4_

## Wave 4 — 附注模板结构修订

- [x] 11. `fix_note_e1_monetary_fund_structure.py`（幂等，复用 `_note_structure_kit`）
  - 作用域 `五、1` + `八、1`：补全部表 `columns`（`flat`，key 镜像 Task 9 载荷）+ `guidance`（源 xlsx 红字/括注 + 准则解释15号，**纯文本禁 markdown 粗体**）
  - soe 主表首行「库存现金」→「**现金**」（源 xlsx R8）
  - soe 主表末行「其中：存放在境外的款项总额」**删除**（源 R13 是括注文字被当数据行 = 假行）
  - soe ②表：删「金融企业法定存款准备金或备付金」（源 xlsx 无）+ **补「合  计」行**（源 R23，校验预设 F1-4 要求）+ 不 seed `…` 占位行（源 R22 是动态插行标记）
  - 附注列头字面**不动**（按平台铁律，本仓库无 `附注模版/*.md` 可复核）
  - 改名走 `rule(aliases=)` 不进 `drops`
  - **上市侧②表按裁决 `insert=True` 补建**（校验预设 listed 侧 F1-4~F1-6 引用它）
  - **实测**：`--check` 7 项欠账 → `--dry-run` 14 处变更 / 0 问题 → 应用 → `--check` 0 欠账 → 重跑幂等空操作
  - **顺带修一处载荷孤儿列**：②表载荷原推 4 列（含 `reason`）而源模板/附注只有 3 列 → 「受限原因」不进附注，改按源 R13 括注要求写在**文字说明段**里；主表列同时补 `flat`（seed 与推送两处都加）
  - `text_sections` 用 `require_text_sections` **只补齐缺段**（不整表替换 —— 现有 10/3 段多为源模板提示原文，整表替换要手抄全部、抄错会写回模板）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.2, 6.3, 6.4_

- [x] 12. 后端守卫 `test_note_e1_structure.py`
  - Property 5（openpyxl 直读源 xlsx ↔ 模板 headers/rows ↔ 载荷 columns 三向；归一化小节编号/「其中：」/尾冒号/多空格）
  - Property 6（seed 与推送两侧都必须 `flat` 且不得声明 `group`）
  - guidance 禁 markdown 粗体（防与平台级 `fix_note_bold_markers.py` 互相打架）
  - 反向自检：`_norm` 不得把「库存现金」和「现金」归一成同一个；两个锚点必须真实存在
  - **30 例全绿**，含：上市主表 == 源 R8~R15 / 国企主表 == 源 R8~R12 / 国企 R13 确为括注（证明删假行有据）/ 上市 R15 确为真数据行（证明不是一刀切删）/ 源 R16 是勾稽校验行不进模板 / 源无「金融企业法定存款准备金或备付金」/ 源 R22 是 `…` 动态标记 / 两版②表共用行集 / 单级表必 flat 且无 `_column_groups` / guidance 禁 markdown 与 HTML / 模板列键逐字镜像载荷 / 合计行字面 `合计`
  - 广域回归：`backend/tests/four_table` 496 passed（唯一失败 `test_report_line_accounts` 属并发会话）；其它循环附注结构守卫 427 passed / 0 failed
  - _Requirements: 5.9_

## Wave 5 — 外币章节打通 + 勾稽

- [x] 13. 外币 → `五、73` / `八、92`（**已补列元数据 + 守卫；推送按裁决移交新 spec**）
  - **🔴 阻塞发现（实证）**：`wp_disclosure_sync_service` 的合并语义是**按子表名浅合并（表级）**，
    不是行级 —— 注释原文「同名 key 覆盖，未推送的 key 保留」。而「外币货币性项目」是**一张表**
    内按科目分段（货币资金 / 应收账款 / 短期借款 / 长期借款 / 应付债券），
    → **E1 推该表就会整表覆盖，把他循环的段落连同审计师在附注模块手填的数据一起清掉**。
  - 三个独立证据确认**目前无任何 pusher**：registry 无外币条目 / 无 `*NoteSectionMap.ts` 指向它 /
    代码两处注释记录过「五、73 实为外币货币性项目」的历史误映射修正。故这不是抢占，
    而是「E1 若接线就会成为唯一 pusher 并独占整表」。
  - **已完成（零风险部分）**：两版补 4 列 `flat` columns + guidance（`rows=None` **完全不动行集**，
    行数保持上市 16 / 国企 25，他循环段与「可无限量添加行」/「……」可扩行原样保留）；
    guidance 如实记录「尚未接自动推送」及其原因，避免下一个人误以为已打通；
    顺带纠正 `五、1` text_sections 的**陈旧交叉引用** `五、81` → `五、73`（`variant_matrix` 双向实证）
  - 守卫（`test_note_e1_structure.py` 43 例）：他循环段必须完整保留 / 行数不变 / 可扩行占位不得误删 /
    **全前端不得有 map 推向外币章节**（含 E1 自己）/ registry 不得出现该章节 / 陈旧章节号不复活
  - **✅ 用户裁决（2026-08-02）：选项 A 收口本 spec + 治本另立 spec** —— 推送部分移交
    `disclosure-note-row-level-merge`（平台级行级合并），其 Task 9/10 会新建 `e1FxNoteSectionMap.ts`
    并把本 spec 的守卫「全前端不得有 map 推向外币章节」改成
    「只允许经 `_row_scope` 声明的 map 推向该章节」+ 保留「不得整表覆盖」正向断言。
    本任务在 E1 spec 范围内**已完成**（列元数据 + guidance + 守卫 + 陈旧章节号纠正），
    不再是「阻塞待裁决」状态
  - **立新 spec 时补充实证（受益面远超外币一张表）**：扫两份 note_template 得全库 805 张表里
    **29 张是多段共享表**（listed 23 / soe 6），横跨 E/D/F/H/K/L/N；且模板段首行**已带**
    `report_row_code`（listed 95 行 / soe 26 行）→ 段归属已声明好，行级合并无需新造标识
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 14. 勾稽引擎 `e1DisclosureConsistency.ts` + 面板
  - 实现校验预设 F1-1~F1-6 全 6 条（两版各自），容差 0.01 元（复用平台共享原语 `shared/disclosureConsistency`）
  - 额外实现源 xlsx 自带两条：上市 `B16 = B14 − D62`（主表合计 vs 原币表人民币合计）；
    原币表**分组小计 = 该组币种叶子之和**（`D38=SUM(D39:D43)` 等，对应 `B29=B40+B46+B52+B58`）
  - 接 `WpDisclosureConsistencyPanel`（紧凑单行 bar + 折叠明细 + 规则 tooltip + `GtIndexChip` 追溯）
  - **F1-5/F1-6 的数据可得性处理**：「现金及现金等价物余额」在现金流量表补充资料③表，
    E1 披露表拿不到 → 传 `null` 走 `skip`（**不伪造、不塌成 0**），并在规则说明里给出
    **推算值**（货币资金合计 − 受限合计）供审计师与③表人工核对；调用方日后能提供时自动转真实比对
  - `buildE1MisstatementPayload`（只推 `error` 级且 `|diff| > 0.01`；`labels` 指定时仍只推真差异，
    防单行推送把 ok/skip 也推进错报汇总）+ 面板下方「推送差异到 A13 错报」按钮（仅有 error 时出现）
  - **`E1_ACCOUNT_CODE='1001'` 只作错报汇总的展示口径**（A13 按报表项目归集，`BS-002` 下
    `1001/1002/1012` 共用一行），**取数仍走 `semantic_account_resolver` 逐项目定位**，不是回退硬编码
  - 守卫 `e1DisclosureConsistency.spec.ts`（**27 例全绿**）：Property 14（`E1_COVERED_PRESET_IDS`
    ⊇ 真源 JSON 抽出的 F1-1~F1-6，两版各自）+ 反向自检（真源必须恰好 6 条、F1-1~3 挂①表 /
    F1-4~6 挂②表、两版逐字相同）+ 规则说明必标真源出处且 >15 字 + `refs` 只许平台索引形态
    且计数 >0（防断言空转）+ 数值语义（备注行不参与加总，**误当明细行必红**的反向自检）
    + A13 载荷经平台桥 `normalizeMisstatementPushPayload` 归一（形态 A）
  - _Requirements: 9.1, 9.2_

## Wave 6 — 平台铁律收口 + CI

- [x] 15. 控件与格式铁律
  - `E1TabCashCount.vue`（9 处）+ `E1TabCreditReport.vue`（2 处）的 `el-input-number :formatter`
    → `WpAmountInput`（EP **2.13.6 的 input-number 无 `formatter`/`parser` prop**，千分符从未生效）；
    两文件 `:formatter="amountFormatter"` **归零**，并清掉因此变成未使用的 import
  - `E1TabDisclosure.vue` 实测**本来就是 0 处**（其金额格用的是 `el-input` + formatter / `WpAmountInput`）；
    残留的 2 个 `el-input-number` 是**折算率**（`:precision="4"`），按反向边界**必须保留**
  - **反向边界守卫**：扫全 E1 目录，`endRate`/`openRate`/`fxRate`/`closingFxRate`/`annualRate`/
    `marketRate`/`denomination`（面值）/`quantity`（张数）不得套 `WpAmountInput`
  - 金额只读走 `displayPrefs.fmtAmount()`：修 `E1TabBankFlowReconcile.vue` 自造
    `toLocaleString('zh-CN', {minimumFractionDigits:2})`（绕过单位/showZero 平台偏好）
    → 改 inject 平台 store 并在 setup 顶层取（写进函数体会静默失效）
  - 守卫 `e1AmountControlIronLaw.spec.ts`（12 例）：三个 scoped 文件零残留 / 反向边界 /
    禁从 `@/stores/displayPrefs` 命名导入 `fmtAmount`（运行时崩整页）/ 禁自造金额
    `toLocaleString`（放行 `new Date(...)`）/ `useDisplayPrefsStore()` 缩进必须为 0
  - **E1 其余 17 个文件的 `el-input-number :formatter` 存量共 84 处**已冻结为
    `E1_LEGACY_FORMATTER_BUDGET` 预算表（**只允许变短**，新增即打红；未登记的新文件也打红）。
    平台级存量替换由单独 spec 收口（memory 已记「40+ 处待单独 spec」，实测 E1 一个循环就有 95 处
    → 平台总量远超原估，已作为发现上报）
  - 派生列读时推导：②表四表命中行金额只读派生、持久化只存手工侧（Task 8 已落地）；
    E1 无防抖累积器 / 无 `saveBatch` 调用点（扫描 0 命中，无需去重改造）；
    模板属性中文引号扫描：命中项全在**文本内容**里（`<p>`/`<div>` 文案），
    属性值内的 U+201C/201D（`E1TabReconciliation` 的 `title="…"`）与 U+0022 是不同码点、
    Vite transform 实测 200，**不构成铁律违规**
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 16. 守卫登记与 CI
  - 新导出的 `buildE1ListedColumns` / `buildE1SoeColumns` 登记 `disclosureColumnsCoverage.spec.ts`
    的 `P1_ROUTE`（**零入参可调** —— sweep 用空入参调用所有 `build*Columns`）
  - `E1_DISCLOSURE_SHEET_NAME` 保持**半角括号**（源 xlsx tab 名实证）；
    `note_workpaper_sync_registry.json` 实测已正确（`附注披露信息(上市公司)` / `(国企)`，
    章节 `五、1`/`八、1`）**无需重生成**；外币章节 `五、73`/`八、92` 实测**不在 registry**（符合 Task 13 判定）
  - `MISSING_SYNC_PATH`：E1 两个 Tab 均有同步链路，无需登记
  - CI 新增 3 个 job（`note-e1-structure` / `e1-four-table-extraction` / `e1-disclosure-frontend`），
    `yaml.safe_load` 校验通过（78 jobs），引用的 6 个脚本/测试路径全部存在
  - **两条平台守卫失败经查证均为预存在基线，非本 spec 引入**：
    `disclosureAutoSyncCoverage` 挂 `D2TabDisclosure.vue`（并发会话 D2 成品，本地无修改）、
    `disclosureColumnsCoverage` 挂 `buildJ2ListedColumns` + `buildJ2SoeColumns`
    （`git log` 显示由 commit `f7b28ff0` 引入，本地无修改）
  - _Requirements: 10.6, 10.7_

## Wave 7 — 实测与收口

- [x] 17. 真实 DB 直跑 render（绕过 HTTP）
  - 三项目实跑 `_build_four_table_extraction`：`df5b8403` / `0ec33ac9` / `2aa00f57`
  - **✅ 通过项**：`row_code=BS-002`、`chart_available=True`、公式解析出
    `['1001','1002','1012']`、`conflicts=[]`、`unmapped_candidates=[]`；
    三个基础槽 `resolved_from=account_chart_client` 且 `exact=True`；
    `parent_check.diff` **全 0**（`1002` 20,751,212.11 / `1012` 461,130.20 逐分相等）；
    `account_list` 保留零余额账户（`df5b8403` 67 条中 64 条零余额）；
    `restricted_prefill` 是**扁平叶子清单**（无 `buckets` 键），
    `leaves` 期末合计 == `tb_values.total_closing` 三项目全部分文不差
  - **🔴🔴 实测挖出两个平台级 P0（已修 + 已加守卫）** —— 见下方
    「实测发现的平台级 P0」小节。修前/修后对比：
    项目 `2aa00f57` `total_closing` **8,935,072.24 → 4,467,536.12**（虚增一倍已消除）；
    `finance_co_closing` / `digital_closing` **21,212,342.31 → 0.00**（不再等于货币资金全额）；
    `parent_check` 的 `slot` 标签 **全是 `digital` → 正确的 cash/bank/other**
  - 回归：`backend/tests/four_table` **517 passed / 1 failed**
    （唯一失败 `test_report_line_accounts::test_split_reverse_selfcheck_chart_actually_used`
    是并发会话改 `report_line_accounts.py` 造成的**预存在基线**，本地无修改）；
    resolver 的另外三个消费方（`test_g_cycle_specs` / `test_h3_account_scope` /
    `test_semantic_account_resolver`）全绿；four_table 外的 G/H 消费方 11 passed / 1 skipped
  - _Requirements: 2.5, 2.6, 2.7_

- [x] 18. 浏览器实测 + 数据复原 + 复盘
  - chrome-devtools MCP 驱动（`admin`/`admin123`；项目 `2aa00f57` / E1 底稿 `a5701bec`
    —— **刻意选这个项目**：它正是 P0-1 双算缺陷的现场）
  - **✅ render-config 活体校验**（uvicorn `--reload` 已加载修复）：`total_closing`
    **4,467,536.12**（修前 8,935,072.24）、`cash`/`finance_co`/`digital` 全 `found=false`
    且 `codes=[]`、`parent_check` 槽标签正确（`1002→bank` / `1012→other`）、`diff` 全 0、
    `restricted_prefill` 无 `buckets` 键、`applicable_standards`
    `["soe_standalone","soe","standalone"]` 顶层与逐 sheet 均已注入、
    sheet 名 `附注披露信息(上市公司)` / `(国企)` **半角括号**
  - **✅ 33 个 sheet 全部渲染**；审定表 Tab 挂载、**溯源面板**显示「命中 2/5 项 · 报表行 BS-002」，
    三个未命中项如实显示**「本项目无此科目」**（不是 0），报表公式原文可见
  - **✅「从四表库带入未审数」**：点击后提示
    「库存现金、存放财务公司款项、数字货币 本项目无此科目（已跳过）」——
    P0 的 skip 语义在活体生效；因宿主四表 seed 已把三个命中槽填成同值，
    计划为**幂等空操作**（DB 0 行写入），恰好交叉验证「两条独立取数路径产出同一组数字」
  - **✅ 披露 Tab 挂载**（Task 1 的 TDZ 修复生效）；`el-input-number` 计数 **0**；
    ②受限表 2 行 + 合计、「待归类科目 1 项待处理」面板（`1002 银行存款` + 归类下拉 + 标记按钮）、
    两段说明各带 AI 辅助 + 源模板琥珀指引块
  - **✅ 勾稽面板**：先开审定表再回披露 Tab → **一致 6 / 待补数 2 / 不一致 0**，
    F1-1~F1-4 逐条与四表数字相符（4,467,536.12 / 53,324,585.63 / 4,140,440.92 / 52,475,713.77），
    F1-5/F1-6 如设计走「待补数」并给推算值；未取数时 F1-1/F1-2 正确报「不一致」
    并出现「推送差异到 A13 错报」按钮（取数后按钮消失）
  - **✅ 自动同步（未点任何按钮）**：改一段说明文本 → 5s 内 `八、1`
    `last_sync_at` NULL→前移、`_source=workpaper`、`_last_sync_sheet=附注披露信息(国企)`（半角）、
    `_current_standard=soe_standalone`（**真实准则，不再是 `null` 退化**）、
    子表 0→**2 张**（含②受限表）、`text_content` 显示**【受限及境外款项说明】**（中文 title）
  - **✅ 读时投影**：两张表 `_column_groups` **均为 `[]`**（flat 生效、无凭空父表头），
    列头 `项目/期末余额/期初余额`，合计行带 `is_total`；②表**无 `reason` 列**（事由走说明段）
  - **🔴 实测挖出并修掉 2 个前端缺陷**（见下方「实测发现的前端缺陷」）
  - 外币章节按 Task 13 裁决**不推送**，故不涉及该项验证
  - **数据复原**：`table_data` 经 md5 **逐字节复原**
    （`f55e054f1b7d6bc8ad1a1a741baa484b` / 6065 字节）、`last_sync_at`/`last_sync_wp_id` 回 NULL、
    删掉本次写入的 1 条 `checklist_responses`。**唯一不可逆**：`text_content`
    实测前是 570 字的**附注模块 AI 填充占位文本**（`last_sync_at` NULL 证明不来自底稿同步，
    全文 `[请补充：具体金额]` 占位），全库无版本快照（`note_section_version_tree` 该项目 0 行）
    → 仅捕获到前 80 字，已按同项目 `五、1` 的常态置空串，需要时走附注模块 AI 填充重建
  - _Requirements: 1.5, 8.3, 10.2_

## 裁决已定（2026-08-01 用户裁决：补②表 + 动态取数）

- [x] 19. 上市侧「② 受限制的货币资金明细表」补建
  - **裁决依据**：源 xlsx 上市披露 sheet 无该表（仅 R18/R19 文字），但校验预设
    **listed 侧 F1-4/F1-5/F1-6 三条明确引用②表**（实证 `table_name` 均为
    「② 受限制的货币资金明细表」），F1-5/F1-6 是与现金流量表补充资料③表的跨科目勾稽
    → 按平台铁律「校验预设是列结构裁决者」**补**
  - 上市②表复用国企行集（6 行）与列结构（3 列 flat），列头 label 按 listed 变体
    `项目 / 期末余额 / 上年年末余额`（国企为 `期初余额`）；R18/R19 保留为 `_note_texts`
  - **条件表语义**：有受限行才推；无行不推空表**且进 `_removed_table_keys`**（K7 范式）；
    `undefined`（不管这张表）与 `[]`（管但为空）严格区分，防越权删他循环表
  - 两版共用同一套受限分类真源（后端 `e1_restricted_buckets` 6 桶）与取数逻辑；
    前端**不抄第二份中文标签**（扫描确认无 `保证金存款`/`担保存款`/`冻结存款` 字面量）
  - 实测：两版②表模板 `cols=3` / `rows=6` / `guidance` 268 字，浏览器国企侧
    渲染 2 行明细 + 合计并成功同步落库
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

## Notes

### 🔴🔴 实测发现的平台级 P0（Task 17，已修 + 已加守卫）

> **只有真实 DB 才能暴露** —— 改动前 `backend/tests/four_table` 509 例全绿、
> `--check` 全部 0 欠账、前端 272 例全绿。自造 fixture 与错误假设同构，测不出来。

#### P0-1：`report_config` 兜底层（层③）对多槽规格把整条报表行科目集分给未命中槽

`semantic_account_resolver.resolve_semantic_accounts` 的定位分层原为：
① 客户科目表按名 → ② 标准科目表按名 → ③ **报表公式给的码** → ④ 槽自有兜底码 →
⑤ 科目表不可用时裸兜底码。

层③给的是**整条报表行**的科目集（`BS-002 货币资金 = TB('1001')+TB('1002')+TB('1012')`）。
单槽规格下「该行就这些科目」成立，多槽规格下则把**整行金额**塞进某个子项槽：

| 现象 | 实测数据 |
|------|---------|
| `finance_co` / `digital` 各自拿到 `['1001','1002','1012']` | `finance_co_closing == digital_closing == total_closing == 21,212,342.31` |
| 项目 `2aa00f57` 无「库存现金」→ `cash` 拿到 `['1002','1012']` | `total = cash + bank + other` 把 1002/1012 算两遍：**8,935,072.24 vs 真值 4,467,536.12** |

后果链：①「从四表库带入未审数」会把货币资金全额填进「存放财务公司款项」与
「数字货币」两行；② E1-1 合计行 `summableKeys` 含 `digital` → 再加一遍；
③ 报表核对行凭空出现巨额差异。

**同款风险在 G/H 循环是潜伏态**（层③排在层④之前 → 槽自有兜底码用不上）：
- G1/G10 的 `derivative`（`fallback=()`）会拿到**原值**科目（1101 / 2101）
- G4/G7 的 `provision`、H3 的 `accum_dep`/`accum_amort`/`impairment`
  会拿到**原值科目码** → 备抵 == 原值

**修法**：层③加 `allow_report_config_tier = len(spec.slots) == 1` 门控。
多槽规格下槽要么按名命中、要么用自己声明的兜底码、否则 `found=False`
由调用方显示「本项目无此科目」（宁缺勿造）。

**守卫**：`test_semantic_account_resolver.py` 新增 4 条（多槽未命中槽必返空 /
多槽参与合计的槽科目码两两无交集 / 备抵槽绝不继承原值码 /
**反向自检：单槽规格下层③仍然生效**，防收窄过度让 G2/G5 等回退）；
`test_e1_account_scope.py::TestMultiSlotReportConfigFallback` 新增 4 条从 E1 侧钉死
后果面，含**反向自检**（复现旧行为必须产出虚增的 8,935,072.24）。

#### 实测发现的前端缺陷（Task 18，已修 + 已加守卫）

**F-1：溯源面板读错路径 → 又一个 dead output**

后端把溯源放在 **`html_data.project_context.tb_source_codes`**
（`_e1_monetary_fund` 里 `project_context["tb_source_codes"] = ...`，这样每个 sheet 都拿得到），
而组件读的是 `html_data.tb_source_codes`（顶层）→ 恒 `undefined` → 面板恒不渲染。
`get_diagnostics` / Vite / vitest 全绿，**只有浏览器打开才发现面板不见了**。
已改为「`project_context` 优先、顶层兼容」。
注意同一份 `html_data` 里 `adjudication_prefill` / `restricted_prefill` / `tb_values`
**确实在顶层** —— 同一个 render 的输出分两层放，逐个 key 都要核实位置。

**F-2：源模板 B16 勾稽在国企侧产出假「不一致」**

外币原币表只在源 xlsx「附注披露信息(上市公司)」（R38~R62），国企版没有这两张表。
组件却无条件传 `fxRows`，而 `foreignCurrencyRows` 在国企侧返回的是**未渲染的默认分组骨架**
（金额全 0）→ B16「主表合计 = 原币表人民币金额合计」拿 0 去比主表合计
→ 国企 Tab 报**不一致 4,467,536.12**。已改为 `variant === 'listed'` 才传；
守卫含**反向自检**（传骨架必产生 error，证明门控必要）+ 源码级断言门控存在。

#### P0-2：`build_e1_parent_check` 的 `slot` 标签被最后一个槽覆盖

原实现 `out[code] = {...}` 无条件赋值，而多个槽可能声明同一科目码
（P0-1 状态下五个槽都声明 1001/1002/1012）→ 三个码的 `slot` 全被标成 `digital`，
溯源面板显示的归属完全错误。改 `setdefault` 语义（保留**首个**声明者）。

### 调查阶段已实证的事实（不需重复验证）

| 事实 | 证据 |
|------|------|
| `BS-002 = TB('1001')+TB('1002')+TB('1012')`，四准则一致 | `report_config` 直查 8 行 |
| `100x/101x` 范围仅 `1001`/`1002`/`1012` | `account_chart` 正则查询 |
| `1502 = 持有至到期投资减值准备`（**不是**数字货币） | `account_chart` 直查 |
| `1012` 存在三层（`1012.014` + `.01/.02`），叶子和 == 父额 | `df5b8403` 逐行核对 |
| `1002` 叶子和 20,751,212.11 == 父额 | 同上 |
| 叶子名 = 银行户名/支付渠道名，**不含受限类别关键字** | 「金华招行基本户801」「金华支付宝」「聚合收款」「AFO」「小桔有车」 |
| 货币资金章节 = `五、1` / `八、1` | `note_template_variant_matrix.json` |
| 外币章节 = `五、73` / `八、92`，**跨循环共享** | 同上 + 模板 rows 含应收账款/借款/应付债券段 |
| 校验预设两版各 6 条 F1-1~F1-6 且完全相同 | `note_check_preset_formulas.json` |
| `tb_source_codes` 前端零消费 = dead output | grep 0 命中 |
| 披露 sheet tab 名是**半角括号** | openpyxl 直读 |
| `E1TabDisclosure.vue` watch(L62) 引用 L83/167/452/493 的 const | 行号精确定位 + `get_diagnostics` 零诊断 |

### 关键踩坑预防（本 spec 直接适用）

- **PowerShell `>` 重定向会把 UTF-8 中文腌成乱码**（本次调查已踩：`note_check_preset_formulas.json` 一度看起来是乱码，实为重定向所致）→ 诊断脚本一律用 Python 自己写盘
- `read_file` 对本会话已改/并发在改的文件返回**陈旧版本** → 判落盘真相用 `python -c "open(p,encoding='utf-8').read()"`
- `flat` 必须 **seed 与推送两处都加**（H8 踩过只加一侧）
- 幂等脚本改名走 `rule(aliases=)`，**不能进 `drops`**
- 外币章节 `rows=None`（跨循环共享，动行集会打断他循环）
- `get_active_filter` 必须传全签名并 `await`（N2/N5 单参调用被吞成 warning → 取数恒空）
- 守卫读源码先 `stripComments()` 并加反向自检
- `_removed_table_keys` 只删本底稿上次推过的键

### 范围外发现（记录，不在本 spec 处理）

- **E0 公式预设 `wp_name='银行询证函'` 与源 xlsx 无对应 tab**（E0 真实 tab 是「货币资金发函记录表E0-3」等）→ 疑似贴错标签，属 E0 函证模块（跨循环共享），另议
- **listed `五、1` text_sections 引用的「五、81」是陈旧章节号**（实为 `五、73`）→ 本 spec 只改 E 类这一条；`note_template` 的 `report_row_code` 全库陈旧属平台级 data-hygiene 待办
- **`TB_SUM('1001~1012')` 在当前标准科目表下等价 BS-002**（区间内无 `1003`/`1011`）→ 不是虚增，但脆弱，本 spec 顺手改显式三项相加
- `prefill_formula_mapping` 全部 E1 块 `sheet_name=None` → `page_key` 撞键（`convert_prefill_presets` 的 `page_key = f"workpaper:{wp_code}"` 忽略 sheet），属平台级待办

### 用户提问的直接回答

- **「用好枚举账龄模块（3年段/5年段/自定义）」在 E 类不适用** —— 货币资金无账龄维度。E 类对应的枚举维度是**币种**（人民币/美元/日元/澳元/欧元 + 自定义）与**受限类别**（5 类 + 自定义），本 spec 按同款「枚举驱动 + 动态插行 + 稳定 key」范式处理（Task 7）
- **动态插行区识别**：源 xlsx 明确的动态区有两处 —— 国企②表 R22 的 `…`（受限类别可继续加行）、外币原币表各分组下的币种行（源模板固定 5 币种但实务需增删）。上市主表与国企主表是**固定行集**（不可动态插行），只有「其中：存放财务公司款项」「数字货币」等按准则解释15号按需列示

### 外币落点裁决（阻塞 Task 13 的推送部分）

**问题**：附注同步的合并粒度是**表级**（按子表名浅合并），而「外币货币性项目」是一张表内按科目分段。
E1 推该表 → 整表覆盖 → 他循环段落及审计师在附注模块手填的数据被清空。

**✅ 用户已裁决（2026-08-02）：A 收口本 spec + B 另立平台级 spec `disclosure-note-row-level-merge`。**
以下三选项保留作决策留痕。

**选项 A：不推送（本 spec 采用）**
- 外币数据留在底稿，附注侧由审计师在「外币货币性项目」章节手工填列（现状即如此，无回退）
- 已补列元数据 + guidance，附注 TAB 有编制提示、seed 路径有列头
- 代价：底稿录的外币数据不会自动流到附注，需人工转录
- 后续可加「复制到剪贴板」或「跳转到该附注章节」按钮降低转录成本

**选项 B：平台级「行级合并」能力（治本，需独立 spec）**
- 给 `sync_from_workpaper` 增加按 `label`（或稳定行 key）合并行的模式，
  载荷声明「本次只负责这些行」，未声明的行保留
- 收益：外币章节可分段推送，D2/K/L 各循环日后都能接；这是跨循环共享表的通用解
- 代价：改动 `wp_disclosure_sync_service` 核心写路径 + 投影器，影响面覆盖全部已接线的
  90 个披露 Tab，必须独立 spec + 全量回归

**选项 C：按循环拆表（改交付物结构，不推荐）**
- E1 推一张自己的表（如「外币货币性项目（货币资金）」），表名不同故不冲突
- 代价：附注该章节出现两张表（模板骨架表 + E1 推的表），交付物结构冗余、与源模板不符

**裁决落地**：按 **A** 收口本 spec（功能完整性上只差自动转录，不影响正确性），
**B** 已立为独立平台级 spec `disclosure-note-row-level-merge`（5 wave / 14 任务）。
它的收益不止 E1 —— 全库实测 **29 张多段共享表**（listed 23 / soe 6），横跨 E/D/F/H/K/L/N；
且模板段首行**已带** `report_row_code`（listed 95 行 / soe 26 行），段归属已声明好，无需新造标识。
现存同类靠「恰好各推不同子表」绕过（H4→H2 工程物资、H6→H1 固定资产清理），
一旦出现「同一张表内分段」就无解。
