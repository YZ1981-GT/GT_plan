# Implementation Plan: H 类取数、公式与披露收口

## Overview

H1~H10 十个循环的「四表入库 → 底稿取数 → 公式管理 → 披露表 → 附注」全链收口。**后端语义定位骨架已完整（10 个 `h{n}_account_scope.py` 全部接线），本 spec 只补缺口、不重建范式**。

分 6 波 / 26 任务：

| Wave | 内容 | 阻塞关系 |
|---|---|---|
| 1 | 判据守卫（**必须先对当前状态打红**） | 无 |
| 2 | 双族并取 + 列别名 + 预设纠偏 | 依赖 W1 |
| 3 | 四循环 `adjudication_prefill` + 溯源面板 | 依赖 W2 |
| 4 | `WP()` 底稿间联动 | 依赖 W2 |
| 5 | 附注会计政策章 + 披露结构 | 依赖 W1 |
| 6 | 金额控件 + 库龄点选 + CI + 真实库验收 | 依赖 W2~W5 |

两个已关闭的裁决门（本 spec 的设计前提，下个会话不得推翻）：

- **裁决 1 = 双族 additive 并取，零改码**。实证 `1641/1651`、`2601/2651` 在同一项目内**互斥**（9 项目逐个核，唯一并存的 `0ec33ac9` 双方均为 0.00）⇒ `TB(a)+TB(b)` 零双算风险；而改码会重演 V138 那次「改对码反而暴雷」。
- **裁决 2 = H 类不引入账龄枚举**。长期资产无账龄维度，H4「库龄」与应收账龄不同构，改为守卫钉死禁引用 + 库龄改点选。

> 判据真源：`backend/wp_templates/H/*.xlsx`（openpyxl 直读）· `report_config` DB · `account_chart`/`account_mapping`/`tb_balance`/`trial_balance` 真实库 · `docs/模版/` 两份附注源 docx。
>
> **🔴 Wave 1 的守卫必须先对当前状态打红**，再进 Wave 2 修数据/代码。先改后写无法区分「守卫有效」与「空转」。
>
> **🔴 本 spec 零 `report_config` 改码**：只做 additive 加和（裁决 1）。不得把 `1641`→`1651`。
>
> **🔴 H 类禁引用账龄枚举**（裁决 2）：`disclosureAgingLabels` / `useAgingConfig` 在 `components/workpaper/**/[Hh]*` 下必须零命中。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "name": "判据先行（必须先打红）", "tasks": ["1", "2", "3"], "parallel": true },
    { "wave": 2, "name": "后端取数补齐", "tasks": ["4", "5", "6"], "depends_on": [1, 2] },
    { "wave": 3, "name": "公式预设与报表行", "tasks": ["7", "8", "9"], "depends_on": [1, 2] },
    { "wave": 4, "name": "前端消费与溯源", "tasks": ["10", "11", "12"], "depends_on": [2] },
    { "wave": 5, "name": "附注模板结构", "tasks": ["13", "14"], "depends_on": [] },
    { "wave": 6, "name": "守卫、CI 与验收", "tasks": ["15", "16", "17", "18"], "depends_on": [2, 3, 4, 5] }
  ],
  "notes": [
    "Task 1/2/3 三个守卫互不依赖，可并行；但都必须在 Wave 2 之前完成并打红。",
    "Task 7（预设脚本）依赖 Task 1 的双族真源常量与 Task 3 的 H3 错块判据。",
    "Task 8（V145 迁移）与 Task 7 无先后，但都要在 Task 16 回归之前。",
    "Wave 5 只碰 note_template JSON 与幂等脚本，与 Wave 2~4 无文件重叠，可提前做。",
    "Task 18 浏览器实测是最后一步，须在 Task 16/17 全绿后。"
  ]
}
```

## Tasks

- [x] 1. 双族并取单一真源 + 守卫（先打红）
  - 新建 `backend/app/services/four_table/dual_family_codes.py`：`DualFamilyGroup` dataclass（`slot_key` / `primary` / `alternate` / `source_ref` / `evidence`）+ `ROU_LEASE_DUAL_FAMILIES` 三组（`1641|1651` / `1642|1652` / `2601|2651`）+ `tb_sum_expression(codes, column)` 生成 `TB('a','col')+TB('b','col')` 字面量
  - 每组 `evidence` 写明实证：`1641` 全库 5 项目 `unadj=160,078.75` vs `1651` 5 项目 `386,272,594.21`（0.04%）；`2601` 98,176.48 vs `2651` 146,970,513.03
  - 新建 `backend/tests/four_table/test_dual_family_codes.py`：连库断言「两族在同一项目内互斥」（每 project 至多一族有非 NULL 值）+「唯一两族并存的项目双方均为 0.00」→ 证明加和零双算；另断言当前 `report_config` 的 `BS-031`/`BS-063` **只含 primary 码**（此条现在必红）
  - 反向自检：把 `alternate` 置空后「互斥断言」仍通过但「加和覆盖率」断言必红
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. 公式列别名缺口守卫（先打红）
  - 新建 `backend/tests/test_formula_column_alias_coverage.py`：扫 `prefill_formula_mapping.json` 全部 `TB(...)`/`SUM_TB(...)` 第二实参，断言每个列名都在 `formula_engine.COLUMN_ALIASES` 里
  - 当前必红并点名 72 处（H 类 16 处：H1 明细 4 / H2 明细 2 / H3 明细 2 / H8 明细 2 / H9 明细 4 / H10 明细 2）
  - 另断言 `_handle_tb` 源码**不含**静默回退（`account_data.get(resolved_col, account_data.get("期末余额"` 形态），此条现在必红
  - 反向自检：构造一个 `COLUMN_ALIASES` 替身缺 `本期发生额`，断言守卫能点名
  - _Requirements: 3.1, 3.3, 3.5_

- [x] 3. 公式预设科目自洽守卫（先打红）
  - 新建 `backend/tests/test_h_cycle_preset_account_coherence.py`：对每个 H 块断言「公式里出现的科目码 ⊆ 该块 `accounts` 声明 ∪ 双族 alternate ∪ `PLACEHOLDER`」
  - 当前必红并点名 H3 `审定表（成本模式）H3-1`（声明 `1521/1525/1526/1527`，公式全为 `1641~1643`）
  - 另三条断言（当前均必红）：H10 `审定表H10-1` 的 `期初余额` 与 `未审数` 公式不得逐字相同 · H2 `明细表H2-2` 不得含项目号字面量（`B510003`/`B510006`）· H1-1/H2-1/H8-1/H9-1 至少各有一条 `WP()`
  - 反向自检：替身块「公式码与声明一致」必须绿
  - _Requirements: 2.2, 2.5, 2.6, 2.7, 10.3, 10.4_

- [x] 4. 扩 `COLUMN_ALIASES` 并补发生额键
  - `formula_engine.COLUMN_ALIASES` additive 增 `本期借方`/`本期借方发生额`→`本期借方`、`本期贷方`/`本期贷方发生额`→`本期贷方`（既有 8 键逐字不动）
  - `_handle_tb` 改三态：列名在 `COLUMN_ALIASES` 但 `tb_data` 无该键 → 抛/记 WARNING 并返 `Decimal(0)`，**不回退期末余额**；列名完全未注册 → 保持既有行为
  - 两个 `tb_data` 构造点补键：`wp_template_files._get_tb_data_for_prefill` 从 `tb_balance` 取 `debit_amount`/`credit_amount`（按 `closing_direction` 带符号）；`adjudication_writeback._build_context` 同款
  - Task 2 守卫转绿；反向自检「回退分支复现旧行为必红」
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 5. H1/H2/H3/H4 审定表预填补齐
  - 四个 render 各加 `_build_adjudication_prefill`，复用 `four_table/leaf_aggregation.resolve_leaf_totals` + 各自 `h{n}_account_scope` 槽定位，形态镜像 H5/H7（已验证范式）
  - H1 按 `h1CategoryClassify` 的五类资产类别分桶；H2 按项目维度；H3 按四槽（原值/累计折旧/累计摊销/减值）；H4 单槽
  - 槽 `found=False` 时该行**不产出键**（宁缺勿造，不得填 0）
  - 新建 `backend/tests/four_table/test_h1234_adjudication_prefill.py`（含「无科目不产键」与「叶子和==父额」两条反向自检）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 6. H8/H9 语义定位接双族（**2026-08-06 Task 17 变异检验时发现是假绿，已补做**）
  - `h8_account_scope`/`h9_account_scope` 的槽 `fallback_standard_codes` 由单码改为双族元组（`("1641","1651")` 等），来源引 Task 1 常量不写字面量
  - `semantic_account_resolver` 侧确认多兜底码已支持（若只取首个则改为全取并去重）
  - 断言 H8/H9 是多槽 spec ⇒ `allow_report_config_tier=False` ⇒ Task 8 改 `report_config` 对语义定位零影响
  - 真实库直跑 9 项目，断言使用权资产/租赁负债金额与 `tb_balance` 叶子聚合逐分相等
  - _Requirements: 1.1, 1.5, 6.4_

- [x] 7. 公式预设幂等脚本（六类修正）
  - 新建 `backend/scripts/fix/fix_h_cycle_prefill_presets_phase2.py`（`--dry-run` / `--apply` / `--check`，带 round-trip 自检：`json.dumps` 不能逐字复现原文即 exit 2）
  - ① H3 审定表整块重写为投资性房地产口径（`TB('1521',…)` − 三备抵，`ADJ('1521',…)`）② H8/H9 六张表改双族加和 ③ H10 审定表 `期初余额` 改 `PREV('H10','审定表H10-1','审定数')` ④ 删 H2 明细表 4 条项目号硬编码 `AUX` ⑤ 补 `WP()` 联动（H1-1←H1-2/H1-12、H2-1←H2-2、H8-1←H8-2、H9-1←H9-2/H9-3；**明细表禁写 `WP()` 防成环**）⑥ 发生额列名统一为 Task 4 注册的别名
  - 控制台输出禁 emoji（GBK 崩点在写盘之后）；`--check` 必须归零
  - Task 3 守卫转绿
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 8. `report_config` 双族加和迁移 V145
  - 新建 `backend/migrations/V145__report_config_dual_family_rou_lease.sql`：`BS-031` 四变体改 `TB('1641')+TB('1651')-TB('1642')-TB('1652')-TB('1643')`、`BS-063` 四变体改 `TB('2601')+TB('2651')-TB('2602')`；全部 `IF EXISTS` 幂等 + 配 `R145` 回滚
  - **迁移号先 `migration_status` 实测**（V139~V144 已占用，号永不复用）
  - 同步 `ReportFormulaService` 的 `_BS_SPECIAL`/`_NAME_TO_ACCOUNT`（第二写入路径，只改迁移等于白做）+ `fill_report_formulas.py` 薄壳确认已委托 service
  - 新建守卫断言两条路径公式一致 + `FORMULA_FILLER_MIRRORED_CORRECTIONS` 登记
  - 应用后连库断言 `BS-031`/`BS-063` 八条 formula 均含两族码；Task 1 的「只含 primary」断言转为「必须含双族」
  - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6_

- [x] 9. 报表侧零回归 characterization
  - 对 9 个真实项目跑 `BS-031`/`BS-063` 改造前后取值比对：8 个单族项目值**必须逐分不变**，`0ec33ac9`（两族并存且均 0）仍为 0
  - 断言「加和后不产生双算」：任一项目两族同时非零且非 0.00 即红（当前实证为空集，此断言是未来防线）
  - _Requirements: 1.3, 1.4, 6.4_

- [x] 10. H3 溯源面板接线守卫（**接线已由并发会话交付，本任务只补守卫**）
  - **接手实证（2026-08-06）：接线已完成，四项全部满足** —— 两个 Tab 各 1 处 `<WpFourTableSourcePanel>`、`htmlData` 在 `defineProps` 内、宿主 `GtH3InvestmentProperty.vue` L63 是 `<template v-else-if="currentSheet === 'H3-1'">` 包住两个 Tab 且传 `:html-data`（计数 7）、5 个属性（`source-codes`/`gross-label`/`extra-slot-keys`/`fallback-row-code`/`hints`）**逐个存在于面板 `defineProps` 的 8 键中**
  - 故本任务收窄为：新建 `h3SourcePanelWiring.spec.ts` 把上述四项钉死，防被回退
  - 判据：从 `WpFourTableSourcePanel.vue` 的 `defineProps<{...}>` **动态抽**合法 prop 名（转 kebab-case）比对两个 Tab 的调用点属性；必填 prop（无 `?` 的 `grossLabel`）必须已传；`sourceCodes` 缺失即面板 `visible` 恒 false 故也必须传
  - 断言宿主分发链未被打断：`currentSheet === 'H3-1'` 那一支必须是 `<template v-else-if`，且其后仍存在 `v-else-if`（裸 `v-if` 插进链中间会让后续全成死分支，H 类已踩过 11 个宿主）
  - 反向自检：把标签名改成 `<WpFourTableSourcePanelREMOVED` 必红（**标签断言必须带边界** `<Foo(?=[\s/>])`，`toContain('<Foo')` 会被骗过）；构造「传不存在的 prop」替身必红
  - **并入原 10b（R5.3/R5.4 复核）**：只读核实面板是否已实现「本项目无此科目」三态与 conflicts 中文完整句（memory 记平台已建 `isAccountAbsent()`）→ 已实现则在同一守卫里补正向断言钉死，未实现则补齐后同样加断言；**不得**在 H3 侧另写一份判定（面板是 K1/K2/F1/E1 共享件，双真源会漂移）
  - _Requirements: 4.6, 5.1, 5.2, 5.3, 5.4_

- [x] 11. H5 上市披露 Tab 改「本版不适用」（**修正立项判据：源 sheet 有内容**）
  - **🔴 立项写的「同 N4 国企侧范式」只对了一半** —— N4 的 soe sheet 内容逐字是 `附注披露信息：`/`无`，而 **H5 的 `附注披露信息（上市公司）` sheet 是 visible 且有完整 38 行四层表**（`A7:G7` 表头 = 项目/探明矿区权益/未探明矿区权益/井及相关设施/…/…/合计，`A8` 一、账面原值 → `A38` 2.期初账面价值）。文案必须如实区分「源模板无内容」与「源模板有表但准则无落点」（R12.3），照抄 N4 措辞即造假
  - 不适用的真实依据三条并列：`variant_matrix.you_qi_zi_chan` 的 `listed_standalone`/`listed_consolidated` **均为 `null`** · `h5NoteSectionMap.H5_NOTE_SECTION` **只有 `soe` 键**（无 `listed`）· `note_template_listed.json` 含「油气」的章节数**实测 0**
  - **🔴 本任务的真缺陷 = 编造章节号**：`H5TabDisclosureListed.vue` 现写 `noteSectionId: H5_NOTE_SECTION.listed ?? '五、油气资产'` —— `H5_NOTE_SECTION` 无 `listed` 键（TS 上是 `undefined`）⇒ **恒取兜底字面量 `'五、油气资产'`**，而该章节在 listed 模板里不存在 ⇒ AI 提示与复核入口挂在一个虚构章节上（R12.5）
  - 改造：整页替换为不适用说明页（保留 `emit('navigate')` 返回目录 + 跳国企版按钮 + `GtReviewTrigger`），删掉两张自造附注表（`costNoteRows`/`depletionNoteRows` 与其 EventBus 订阅）、删 `WpNoteTextArea` 与 `useHCycleDisclosureAi` 接线、删 `H5-disc-listed-text` 持久化（**该键需先查库确认无存量数据**，有则保留只读展示不删数据）
  - `h5NoteSectionMap` 增 `H5_LISTED_NOT_APPLICABLE_REASON` 常量（判据文字单一真源，供组件与守卫共读）；`buildH5SyncPayload` 已只接 soe 形态，确认无 listed 分支可走
  - 守卫 `h5ListedNotApplicable.spec.ts`：①组件零 `useDisclosureAutoSync`/`scheduleAutoSync`/`sync-from-workpaper` ②**源码不得出现 `?? '五、` 形态的章节号兜底**（反向自检：注入该兜底必红）③`H5_NOTE_SECTION` 无 `listed` 键 ④判据文案含源 sheet 名与「有表格但无附注落点」语义（反向自检：文案写成「源模板无内容」必红）⑤`buildH5SyncPayload` 类型层不接受 `'listed'`
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

- [x] 12. H 类金额控件替换（收窄范围）
  - 只替换**披露 Tab 与审定表** 的金额 `el-input-number`（H1TabAdjudication 18 / H2TabDisclosureListed 21 / H2TabDisclosureSoe 18 / H1TabDisclosureListed 13 / H1TabDisclosureSoe 12 / H9TabAdjudication 16 / H5TabAdjudication 15 / H7 两审定表 18）→ `WpAmountInput`
  - **绝不替换**利率/折旧率/残值率/使用年限/比例/笔数/月份（H1TabPolicyCheck 的年折旧率、H2 利息资本化率等）
  - 检查/测算类 Tab（Recoverable/Impairment/Depreciation）本轮不动，登记进 Notes 留后续
  - 新建 `hCycleAmountControl.spec.ts`：披露/审定表内金额列 `el-input-number` 计数必须为 0 + 非金额列必须保持 `el-input-number`（双向锁死）
  - _Requirements: 10.1, 10.2_

- [x] 13. 会计政策章 H 类表处置（幂等脚本）
  - 新建 `backend/scripts/fix/fix_note_h_policy_chapter_structure.py`（`--dry-run`/`--check`）
  - **保留并补 columns**：listed `三、固定资产` 折旧年限表（4 列 类别/使用年限/残值率%/年折旧率%，`flat`）+ guidance 取源模板红字
  - **表名正名**：listed `三、工程物资【不适用` 的 `项  目` → 正式表名（表头首格泄漏）
  - **处置重复表**：listed `三、使用权资产` 的 39 行变动表与 `五、25` 同构 → 移除该表并 `_removed_table_keys`；`……` 占位列头按 H8 已定口径展开为 `其他`
  - soe `四、投资性房地产`/`四、固定资产`/`四、在建工程`/`四、油气资产`/`四、使用权资产` 五章 `tables=0` → 依源 docx 判定是否应有政策表，无则只补 `text_sections`，**不凭空造表**
  - 新建 `test_note_h_policy_chapter_structure.py`：以源 docx 为裁决者（`paragraph.style.name == 'Heading N'` 定位章，**不用 `^N、` 正则**）+ 反向自检「重复表复活必红」
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 14. 八、26 使用权资产 `text_sections` 核对
  - 按 soe 源 docx 判定该章是否真无说明段（listed 侧有 3 段）；有则补齐，确无则在守卫里显式登记「源模板无说明段」并加反向自检
  - `_note_texts` 一律带中文 `title`（缺 title 会渲染成 `【soe-note-xxx】`）
  - _Requirements: 7.1, 8.2_

- [x] 15. 动态插行与账龄双向守卫
  - 新建 `test_h_cycle_expandable_rows.py`：逐 H 循环披露 sheet openpyxl 直读，断言六种可扩标记（`……`/`…`/`......`/`预留`/`可改名`/`可无限量添加行`）识别结果与前端 `h{n}*DisclosureModel` 的 `blankRows`/`addRow` 位置一致
  - 断言前端**不得**写死骨架行数（`blankRows(p, 3|5|10)` 形态即红），改 `max(seed 行数, 1)`
  - 新建 `hCycleNoAgingEnum.spec.ts`：`components/workpaper/**/[Hh]*` 下 `disclosureAgingLabels`/`useAgingConfig`/`AGING_BANDS` **零命中**（裁决 2）；反向自检「注入一处引用必红」
  - H4/H6 的「库龄」字段改 `el-select` 点选（区间选项来自源模板字面），**不接项目账龄配置**
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4_

- [x] 16. 零回归回归与 CI
  - 跑 `backend/tests/four_table`（**从仓库根，不从 `backend/`** —— 相对路径会让 16 个测试假红）+ `-k "h1 or h2 or h3 or h4 or h5 or h6 or h7 or h8 or h9 or h10 or formula_engine or report_config"`
  - 前端跑 `npx vitest run h1 h2 h3 h4 h5 h6 h7 h8 h9 h10 --reporter=json --outputFile=<abs>.json`
  - 判「失败是否本轮造成」：用 `git show HEAD:<path>` 换回原版跑同一组求差集；**先核对两侧执行用例数量级相当**（波次间有依赖时 HEAD 侧可能收集崩）
  - `governance-checks.yml` 新增两 job：`h-cycle-extraction-formula`（后端）+ `h-cycle-frontend`（前端），补 npm 缓存步骤
  - _Requirements: 11.1, 11.4, 11.7_

- [x] 17. 变异检验（逐条打红）
  - 对 Task 1/2/3/5/6/9/13/15 的每个新守卫各做一次变异：改一字看是否变红
  - 变异脚本必须：备份落磁盘 `.bak` + `try/finally` 无条件写回 + 一个脚本只做一个变异 + 锚点行级唯一（`hits == 1`，三态区分 RED/GREEN/ANCHOR-MISS）
  - **共享热点文件**（`formula_engine.py` / `prefill_formula_mapping.json` / 两个 note_template JSON）改用「替身字符串」在测试内验证，不做磁盘变异
  - 每条变异结果如实记入 tasks.md Notes：GREEN 说明守卫有缺陷，必须修守卫
  - _Requirements: 11.2, 11.3_

- [x] 18. 真实库验收与浏览器实测（**真实库 80 组合验收 + 浏览器实测 5/5 均已通过，2026-08-10**）
  - 新建 `backend/scripts/diagnose/verify_h_cycle_extraction_live.py`（默认 dry-run，只读）：9 项目 × 10 循环逐个跑 render，输出 `tb_source_codes.resolved_from` / 槽命中 / `parent_check.diff` / `adjudication_prefill` 行数；判据违规数为 0 才算通过
  - 浏览器实测（chrome-devtools）：H8 审定表看到 `1651` 族真实金额（`2aa00f57` 期望 352,406,145.74）· H3 审定表溯源面板渲染四槽 · H1 审定表「从四表库带入未审数」出数 · 披露表推送后附注 `last_sync_at` 前移且子表非空 · 金额输 `1234567.5` 显示 `1,234,567.50`
  - **实测三件套**：录真实数据 → 看目标区域真出数 → postgres 查 `checklist_responses`/`disclosure_notes` 落库；缺一不算实测
  - 实测后按快照**逐字节复原**（`parsed_data` / `last_sync_at` / `checklist_responses` 三项），并二次核实
  - 会话结束前清掉本轮 `tmp_*` 诊断产物
  - _Requirements: 10.5, 11.5, 11.6_

## Notes

### 两个裁决（2026-08-06，据真实库实证定案）

**裁决 1 = 双族加法式并取，零改码。** `tb_balance` 与 `trial_balance` 双证：`1641/1651`、`1642/1652`、`2601/2651` 在**同一项目内互斥**（9 项目逐个查，每项目只出现一族、另一族为 NULL），唯一两族都有记录的 `0ec33ac9` 双方均为 `0.00` ⇒ `TB(a)+TB(b)` **零双算**。故不改任何现有码（避免 V138 那类「改对码反而把潜伏错误变成活错」），只做 additive 加和。H8/H9 是多槽 spec ⇒ `allow_report_config_tier=False` ⇒ 改 `report_config` 对语义定位零影响。

**裁决 2 = H 类不引入账龄枚举。** 长期资产无账龄维度；H4「库龄」/H6「挂账时长」与应收账龄不同构（同 J2「到期分析」定论）。改为守卫钉死禁引用 + 库龄字段点选化。H 类真实分类维度是**资产类别**（H1/H7/H8 已按此做动态列）。

### 实证基线（2026-08-06）

- 源模板 11 个 xlsx / 209 sheet，H1 最重（27 sheet）；H0 无披露 sheet（函证循环，正常）
- 后端 10 个 `h{n}_account_scope.py` + `h_cycle_specs.py` 齐全，H1~H10 全部 render 已调 `resolve_semantic_accounts`
- `report_config` H 类映射四准则**逐条正确**（BS-027/028/029/031/063、IMP-010/011、IS-018）
- 双族金额：`1651`=872,197,195.23(9 项目) vs `1641`=0.00(1 项目)；`2651`=−134,149,603.09 vs `2601`=0.00（`tb_balance` 口径）
- `trial_balance` 口径：`1641`=160,078.75 vs `1651`=386,272,594.21 ⇒ 旧码**只取到 0.04%**，比恒空更隐蔽
- 未注册列名 `本期借方`/`本期贷方` 全库 72 处（H 类 16 处）
- 附注主章节 15 个已带 `_aligned_by`；会计政策章 10 处 `columns=0`
- H 类 `el-input-number` 密集（最高 H8TabRecoverable 24），`WpAmountInput` 仅 H7 两个表格组件

### 范围外（登记不做）

- H 类检查/测算类 Tab 的金额控件替换（Recoverable/Impairment/Depreciation 共 20+ 文件）→ 与存量 40+ 处 `el-input-number :formatter` 一并另立 spec
- `trial_balance` 父子双算（H2/H8 实证正好 2 倍）→ 属 recalc 平台级缺陷
- 单 sheet 遗留 wp_code render 出 `html_data=null` → 平台级
- `note_template` 的 `report_row_code` 全库陈旧（inert）→ 平台级 data-hygiene
- 母公司章任何字段 → `parent-company-note-chapter-and-sourcing`
- 国企↔上市转换链路 → `soe-listed-note-conversion-correctness`

### 接手实证：三个 `[x]` 任务被并发会话回退（2026-08-06 本会话开工核实）

按 memory 铁律「凡记『某幂等脚本 --check 已归零』的，接手时都要重跑一次 --check」逐项复核，
发现 Wave 2/3 的**数据与生产侧改动已被回退**，而 tasks.md 仍标 `[x]`（假绿）：

| 任务 | 声称 | 实证 | 处置 |
|---|---|---|---|
| 7 公式预设 | `--check` 归零 | `--check` **exit 1 / 45 项欠账**（`1651`/`1652`/`2651` 各只 1 次命中、`B510003` 仍 6 处） | 重跑 `--apply`，45 处写入，`--check` 归零 |
| 8 双族迁移 | 含第二写入路径 | `report_formula_service._BS_SPECIAL` 里 `1651`/`1652`/`2651` **计数全为 0** | 按真源 `DUAL_FAMILY_ROW_FORMULAS` 重新同步两条（隐式拼接多行串形态） |
| 4 列别名 | 已注册 + tb_data 产出 | `COLUMN_ALIASES` 14 键在、两个构造点接线也在（首轮那条失败是陈旧态，复跑即绿） | 无需改动，已复验 |

**Task 5 判定 = 已交付**（与 memory 记的「接线全错的假交付」不同，磁盘现状已修好）：
共享件 `four_table/h_cycle_adjudication_prefill.py` 全关键字签名 +
H1~H4 四个 render 调用点**逐个核实绑定正确**（`(ctx, payload, cycle=…, accounts=…, slot_key_prefix=…)`），
守卫存在但文件名是 `test_h_cycle_adjudication_prefill.py`（非 tasks.md 写的 `test_h1234_…`）。

本轮改动守卫一处：`SEGMENT_PREFILL_KNOWN_CONSUMERS` 由 **0 → 3** 并新增
`SEGMENT_PREFILL_EXPECTED_CONSUMERS` 逐个登记（只断言数量会被「删一个+加一个」绕过）。
三个消费方 = 共享件本体 + `H2TabAdjudication.vue` + `H4TabAdjudication.vue`；
**H1 走既有 `adjudication_category_prefill` 通路**（守卫 `test_h1_category_prefill_is_the_wired_path` 钉住），
**H3 两个审定表 Tab 连 `htmlData` prop 都没有** ⇒ 归 Task 10 一并接。

### Wave 4 实录（Task 10 / 11，2026-08-06 本会话）

**Task 10 = 只补守卫**（接线已由并发会话交付，四项逐个实证通过）：
`h3SourcePanelWiring.spec.ts` **21 例全绿**，3 个变异逐条打红并还原
（M1 传不存在的 prop → 2 红 · M2 标签改名 `<XxxREMOVED` → 4 红 · M3 裸 `v-if` 打断分发链 → 1 红）。
落地时修掉守卫自身两处**判据字面量写错**（本可造成假红）：
面板文案实为「本项目无「…」科目」（不是「本项目无此科目」）、
`conflicts` 的变量名是 `conflictTexts`/`tbConflictTexts`（源码里没有小写复数 `conflicts` 单词）。
→ **守卫首次运行打红时先分三态判**：实现缺陷 / 判据字面量错 / 解析器缺陷。

**Task 11 实证推翻两处并连修一个活缺陷**：

| 项 | 立项写的 | 实证 | 处置 |
|---|---|---|---|
| 源 sheet 内容 | 同 N4 国企侧「内容为无」 | H5 `附注披露信息（上市公司）` **visible 且有 38 行四层表**（`A7:G7` 表头 + `A8` 一、账面原值 → `A38` 2.期初账面价值） | 文案改为「源模板有表格，但附注侧无落点」；守卫反向锁死禁照抄 N4 措辞 |
| `H5-disc-listed-text` 存量 | 需先查库 | 全库 `checklist_responses` **0 行** | 直接删该持久化键，零数据丢失 |
| 活缺陷 | — | `noteSectionId: H5_NOTE_SECTION.listed ?? '五、油气资产'` 而该常量**连 `listed` 键都没有** ⇒ `??` 恒取右值 ⇒ 向 AI/复核下发**虚构章节号** | 删 `useHCycleDisclosureAi` 接线 + 守卫禁 `?? '五、` 形态兜底 |

不适用的三条并列判据（全部落点侧，写进 `H5_LISTED_NOT_APPLICABLE_REASON` 单一真源）：
`variant_matrix.you_qi_zi_chan` 的 `listed_standalone`/`listed_consolidated` 均 `null` ·
`note_template_listed.json` 共 **204** 章节、含「油气」**0** 个 · `H5_NOTE_SECTION` 只有 `soe` 键。

**诚实修正两个既有守卫**（它们锁定的正是本任务要撤掉的旧行为，不是回归）：
`hDisclosureAiWiring.spec.ts` 的「应有 13 个 Tab 接入 helper」→ **12**（H5 listed 移出）+
「H5 两版补上文本持久化」→ 只对 soe 断言，上市侧改为**反向锁死**
（不得出现 `H5-disc-listed-text`/`saveResponse`/`WpNoteTextArea`/`useHCycleDisclosureAi`）。
`MISSING_SYNC_PATH` 里 H5 listed 的登记理由由「后续改为不适用页」更新为「已落地」。

`h5ListedNotApplicable.spec.ts` **28 例全绿**，4 个变异逐条打红并还原
（M1 注入 `?? '五、` 兜底 → 3 红 · M2 重接自动同步 → 2 红 ·
M3 给 `H5_NOTE_SECTION` 加 `listed` 键 → 1 红 · M4 文案照抄 N4「内容为无」 → 1 红）。
回归 `h5` 相关 **79 例 / 78 passed**，唯一失败 = `D2TabDisclosure.vue` 预存在基线
（薄壳非标委托，`resolveDelegate` 识别不了，属 D2 spec）。

**一条可复用的组件写法**：判据常量做成对象（`{sourceSheet, summary, evidence[]}`）时，
模板里**不能** `{{ CONST }}` 直接插值（渲染成 `[object Object]`，`get_diagnostics` 零诊断）→
必须逐字段渲染 `{{ CONST.summary }}` + `v-for` 遍历 `CONST.evidence`；守卫要断言这两处形态。

### Task 12 实录（金额控件，2026-08-06）

**实测口径修正**：tasks 原估「H1 18 / H2L 21 / H2S 18 / H1L 13 / H1S 12 / H9 16 / H5 15 / H7 两表 18」
= 131 处，逐个标签按 `v-model` 字段名分类后 **127 金额 + 4 非金额**（H2 两版各 2 处比率列）。
9 个目标文件的 131 个 `el-input-number` **全是自闭合**（属性感知扫描实证，`closes=0`）
⇒ 替换是纯标签重写，无需处理闭合标签。

产出三件：
- 判据真源 `composables/hCycleAmountControlRegistry.ts`
  （`H_AMOUNT_TARGET_FILES` 9 条 + `H_NON_AMOUNT_FIELDS` 4 条逐条带理由 +
  `isHNonAmountField()` **只查登记表不做名称推断** + `H_NON_AMOUNT_NAME_HINTS` 仅供守卫兜底）
- 幂等脚本 `backend/scripts/fix/fix_h_cycle_amount_controls.py`（`--dry-run`/`--apply`/`--check`）
  已 apply **127 处 + 9 个 import**，`--check` 归零
- 守卫 `__tests__/hCycleAmountControl.spec.ts` **37 例全绿**，双向锁死：
  正向「金额列必须 `WpAmountInput` + 已显式 import + 无 `:controls`/`:precision` 残留」·
  反向「4 个登记的比率列必须仍是 `el-input-number` 且不得出现在 `WpAmountInput` 上」

**5 个变异逐条打红并还原**（M1 金额列回退 `el-input-number` → 1 红 · M2 比率列误换 → **3 红** ·
M3 删 import → 1 红 · M4 登记表塞空理由 → **4 红** · M5 残留 `:controls` → 1 红），
`RESTORED same_as_baseline=True`。H 类前端回归 **1338 例 / 0 failed**。

**三条踩坑（本轮实测）**：

1. **🔴 用「正则匹配位置 + `src.index('[')`」截数组字面量会命中类型注解里的 `string[]`** ——
   `export const X: readonly string[] = [` 从 `m.start()` 找第一个 `[` 得到的是 `string[]` 的，
   depth 立刻回零、body 截成**空串** ⇒ 脚本报「目标清单为空」但 **exit 0 看起来正常**。
   正解 = 用正则末尾 `m.end() - 1`（正则里的 `\[` 就是目标开括号）。
   同族已登记：固定字符窗口截函数体 / `blockOf` 命中内联返回类型注解。
2. **守卫 import 的符号名必须与真源导出名逐字一致** —— 真源导出 `isHNonAmountField`
   而守卫写 `isNonAmountField` → `TypeError: (0 , isNonAmountField) is not a function`，
   4 条断言以**运行时错误**形式失败（不是断言失败），容易误判成实现有问题。
3. **`isHNonAmountField` 有意不做名称推断** —— 若名称启发式进入生产判据，
   `interestCapAccum`（利息资本化累计**金额**）会因前缀与 `interestCapRate` 相同而被误豁免。
   故判据 = 逐条登记（key 含**文件路径**，同名字段在不同文件各自裁决），
   `H_NON_AMOUNT_NAME_HINTS` 只在守卫侧作第二道防线。我第一版把这条自检的期望写反了，
   实为**守卫期望错**而非实现缺陷。

### Task 13 实录（会计政策章，2026-08-06）—— **源 docx 推翻 tasks 两处处置**

产出：幂等脚本 `backend/scripts/fix/fix_note_h_policy_chapter_structure.py`
（`--dry-run`/`--apply`/`--check`，**round-trip 硬闸**：`json.dumps(indent=2)+"\n"` 必须逐字
复现原文否则 exit 2，实测两份模板均满足 —— listed 1,026,449 B / soe 680,717 B）
+ 守卫 `backend/tests/test_note_h_policy_chapter_structure.py` **21 例全绿**
（源 docx 为裁决者，`--check` 归零也作一条断言）。**6 个变异逐条打红并还原**
（M1 重复表塞回 → 3 红 · M2 表名退回红字泄漏 → 2 红 · M3 标签列去 `flat` → 2 红 ·
M4 soe 行标签漂移 → 3 红 · M5 删 `……` 可扩位 → 3 红 · M6 无表章节凭空造表 → 2 红），
`RESTORED same_as_baseline=True`。

**两处 tasks 原处置被源 docx 推翻**：

| 项 | tasks 写的 | 源 docx 实证 | 实际处置 |
|---|---|---|---|
| listed `三、工程物资【不适用` | 「表名正名（表头首格泄漏）」 | 该章 `tables_between=0`，**源 docx 根本没有表**；JSON 那张表与项目注释章 `五、23` 的 t[5]「工程物资」行标签同构（专用材料/专用设备/工器具/工程物资减值准备/合计） | **移除**（重复表），不是正名 |
| soe 五章 `tables=0` | 「判定是否应有政策表」 | 只有 **`四、固定资产`** 应有 1 表（`Heading 4 固定资产分类及折旧政策`，8 行×4 列）；**`四、投资性房地产`/`四、在建工程`/`四、油气资产`/`四、使用权资产` 及其全部 `Heading 4` 子节 `tables_between` 全 0** | 补 1 表；其余四章 `tables=0` **是正确的**，守卫显式登记 + 反向自检 |

**另两处按 tasks 执行且证据充分**：
- listed `三、使用权资产` 表 = `五、25` 的**逐行同构副本**（39 行，5 处差异只是「4. 期末余额」多一个空格的 md 空白差异；headers 亦同构且还残留 `……` 占位列头）→ **移除**。因整表移除，tasks 说的「`……` 展开为 `其他`」不再需要
- listed `三、固定资产` / `三、生物资产【不适用` 的**表名是整段红字说明文本泄漏**（不是表头首格）→ 正名为源 docx 的 heading 标题（`各类固定资产的折旧方法` / `生产性生物资产`），红字移入 `guidance`，补 4 列 `flat` columns

**移除重复表的安全性（三条并列）**：`note_workpaper_sync_registry.json` 里这些政策章**全部不在册** ·
80 个 `*NoteSectionMap.ts` 对政策章号的 grep 命中经逐条核实**全是别的语义**
（`h1` 只在注释里 / `h3`·`h5` 命中的是**行标签**「四、投资性房地产减值准备累计金额合计」
「四、油气资产账面价值合计」/ `h8` 的 `isH8RouNoteSection` 只判章节号且**只有测试消费方**）·
守卫另加反向锁死「被移除的表必须仍存在于项目注释章」（`五、25` 仍是 39 行 + `五、23` 仍含「工程物资」表）
⇒ 是去重不是删数据。

**三条踩坑**：

1. **🔴 `git diff --numstat` 报 4289/2101 不等于自己改了这么多** —— 逐 section 比对 HEAD 后
   实为「我的 6 个目标章节 + 并发会话的 14 个母公司章（listed `十六、*` / soe `十二、*`，
   属 spec `parent-company-note-chapter-and-sourcing`）」。判改动范围要**按 section 做结构化 diff**，
   不能看行数。
2. **🔴 两份源 docx 的 Heading 层级不同构** —— listed `Heading 2`=节，
   **soe `Heading 3`=节 / `Heading 4`=子节 / 局部到 `Heading 5`**；且政策表往往挂在**子节**下
   （listed 的折旧表在 `Heading 3 各类固定资产的折旧方法`，soe 在 `Heading 4 固定资产分类及折旧政策`，
   生物资产折旧表更深到 `Heading 5 生产性生物资产`）⇒ 只按「节级 heading 的 tables_between」判会全部得 0。
3. **同名 heading 在两个章里各出现一次**（会计政策章 + 项目注释章都有「固定资产」「使用权资产」
   「在建工程」「投资性房地产」）⇒ 建索引必须 `setdefault` 取**首次**（会计政策章在前），
   否则政策章的「无表」判据会被项目注释章的表覆盖成「有表」。

### Task 14 实录（八、26 text_sections，2026-08-06）—— **零数据改动**

按源 docx 核对结果：**现状全部正确，无需补齐**。

| 项 | 实证 | 处置 |
|---|---|---|
| soe `八、26` `text_sections=0` | 国企附注源 docx 的「使用权资产」项目注释章（`Heading 3` 第 2 次出现）**只有 1 张 26×5 表、零段落** | 正确，不补（宁缺勿造） |
| listed `五、25` 3 段说明 | 与源 docx **逐字一致**（33 / 214 / 57 字符逐字符相等） | 无需改 |
| `_note_texts` 中文 title | 前序 spec 已落地 `H8_NOTE_TEXT_TITLES` + `buildH8NoteTexts()`（过滤空白 + 补 title） | 已满足，补断言钉死 |

**一处自我更正**：首轮我据探针输出判「listed 第 2 段被 md 重建截断」，逐字符 diff 后
`identical=True len=214` —— 那是**探针自己 `[:220]` 显示截断**造成的假象，不是数据缺陷。
→ 判「文本是否被截断」必须做逐字符比对并打印 `common_prefix` 与两侧 tail，
不能看被截断显示的探针输出。

**增量 = 给既有守卫补按源 docx 的交叉判据**（不新建文件，同一不变式择一实现）：
`test_note_h8_right_of_use_structure.py` 原有的 `test_soe_has_no_text_sections`
判据是**底稿源 xlsx**，而 `text_sections` 属**附注模板**、真源是 `docs/模版/` 的 docx ——
两者不是同一份文件（listed 侧正是「xlsx 有表 + 附注 docx 另有 3 段」），
故「xlsx 无说明段」**不蕴含**「附注不该有说明段」。新增 4 例：
`test_soe_no_text_sections_confirmed_by_source_docx` ·
`test_listed_text_sections_match_source_docx`（逐字） ·
`test_note_texts_carry_chinese_titles` · `test_reverse_self_check_docx_heading_lookup`。
**4 个变异逐条打红并还原**（M1 soe 凭空补段 · M2 段落截断 · M3 删一段 ·
M4 title 换英文键），该文件 **21 例全绿**。

**🔴 heading 定位必须取「第 2 次出现」** —— 「使用权资产」在两份 docx 里都出现两次
（会计政策章 + 项目注释章）；取第 1 次会拿到会计政策章（**零段落零表**）
⇒ 得出「listed 也无说明段」的错误结论。反向自检已把这个差别钉死
（`first == []` 且 `len(second) == 3` 且 `first != second`）。

### Task 15 实录（可扩行与账龄，2026-08-06）—— **tasks 判断被实证修正两处**

产出两个守卫 + 一处改名，**7 个变异逐条打红并还原**：
- 前端 `__tests__/hCycleNoAgingEnum.spec.ts` **18 例全绿**（3 变异全红）
- 后端 `backend/tests/test_h_cycle_expandable_rows.py` **39 passed / 2 skipped**（4 变异全红）
  （2 skipped = H5-listed 与 H10 两侧无附注落点）

**修正一：H4 库龄「已经是点选」，且已自造区间。** tasks 写「H4/H6 的库龄字段改
`el-select` 点选（区间选项来自源模板字面）」，实证 `H4TabDetail.vue` **早已是
`el-select` + `AGING_OPTS = ['1年以内','1-2年','2-3年','3年以上']`**；而源模板
`明细表H4-2!AV8` **只有「库龄」列头、无 DV 无区间字面量**（AV 列全列仅 3 个值：
索引号/页次/库龄）⇒ tasks 说的「区间来自源模板字面」**不存在**。

处置（三条实证支撑「保留但改名」）：库龄**不进披露载荷** ——
`h4NoteSectionMap.ts` / `h4DisclosureSyncPayload.ts` / `H4TabDisclosureListed.vue` /
`H4TabDisclosureSoe.vue` 对「库龄」与 `aging` 的命中数**全为 0** ⇒ 不污染附注 ⇒
点选是合法的录入辅助（符合「交互点选优先」）。但**常量名 `AGING_OPTS` 会诱导后来者
统一到平台账龄枚举**（正是裁决 2 要防的）⇒ 改名 **`STOCK_AGE_OPTS`** + 注释写明
语义边界；**持久化键 `row.aging` 保留不动**（历史键，改名会让既有项目已录数据读不回来）。
守卫判据随之从「禁自造区间」（过宽，会误伤合法录入辅助）改为三条精确判据：
①分段常量名不得含 `AGING` ②必须就地声明 + 注释含「与账龄无关」与源模板实证
③**库龄不得进披露载荷**（真红线）。

**修正二：H6 不是库龄，是「挂账关注」。** `{ label: '挂账关注', value: 'aging' }`
是**区段切换器的 value**，判据是 `isRowOverOneYear`（转入清理超 1 年），
与账龄分段无关 ⇒ 「H4/H6 库龄改点选」对 H6 不成立，改为把该语义**登记进守卫**防误改。

**行级 `……` 的处置必须逐循环声明，不能一刀切**（后端守卫 `ELLIPSIS_ROW_POLICY`）：

| 循环-变体 | 源 sheet 行级 `……` | 附注 JSON | 策略 |
|---|---|---|---|
| H1-listed / H7-listed / H8-listed / H9-soe | 6 / 5 / 6 / 1 | 6 / 5 / 6 / 1 | `keep`（真实可扩行、参与小计求和） |
| **H7-soe** | **8** | **0** | `dynamic-rows`（**有意不 seed**：已改动态类别行模型，预置空行会被推成占位披露行） |

**列头级 `……` 全部已展开**（H1-listed `E13` · H5-listed `E7`/`F7` · H7-listed 8 处 ·
H8-listed `E6` → JSON headers/columns 里零残留）；
**纯占位词零 seed**（H3-listed 7 处「可无限量添加行」+ H1-listed 2 处 → JSON 0 处）。

**两条踩坑**：

1. **🔴 `\(([^)]*)\)` 取实参会把嵌套调用截断，让合法写法被误判** ——
   `blankRows(p, Math.max(seed.length, 1))` 被截成 `p, Math.max(seed.length, 1`，
   尾部恰是 `, 1` ⇒ 判成「写死骨架行数」。正解 = **按圆括号配对**取实参
   + 按**顶层逗号**切分（`callArgs` / `lastArgIsLiteralNumber`），
   并配「派生形态不得命中」的对照自检。同族已登记：固定字符窗口截函数体 /
   `src.index('[')` 命中类型注解里的 `string[]`。
2. **「当前已是 0 命中」的守卫必须配扫描面非空自检** —— 账龄与骨架行数两条实证
   命中数都已是 0（裁决 2 当前就是绿的），若不断言「H 类文件数 > 200 且 h1~h10
   每个目录都被扫到 且 已知内容锚点存在」，路径写错/glob 失效都会让 0 命中变成假绿。

### Task 16 实录（回归与 CI，2026-08-06）

**回归结果**（全部从**仓库根**跑）：

| 范围 | 结果 |
|---|---|
| `backend/tests/four_table` | **1560 passed / 22 failed / 17 skipped** —— 22 个失败全在 `test_report_formula_filler_mirror.py`（本文件已登记的预存在红，属 `report-config-account-code-integrity` spec 被回退） |
| H 类后端守卫聚焦清单（13 个文件） | **236 passed / 3 skipped / 1 failed → 复跑 81 passed / 0 failed** |
| 前端 `h1..h10 + hCycle` | **2269 / 2269 全绿** |

**CI 新增两 job**（`governance-checks.yml` 124 → **126**，diff 424 行纯新增 0 删除）：
`h-cycle-extraction-formula`（12 步：列别名 / 预设自洽 / H1~H4 预填 / 会计政策章 /
使用权资产结构 / 可扩标记 / 两个幂等脚本 `--check` / 双族连库烟测）+
`h-cycle-frontend`（8 步：H3 溯源接线 / H5 不适用 / 金额控件 / 账龄与骨架 / AI 接线）。

**三条踩坑**：

1. **🔴 唯一那条失败是并发写入的瞬时中间态，不是回归** ——
   `test_fix_script_check_is_clean` 报 round-trip `rc=2`，而立刻复跑 `--check` 归零、
   守卫也转绿。实测两份 note_template JSON 的 **mtime 距当下 0.9 / 1.3 分钟且文件大小
   已变**（listed 1,026,449 → 1,014,914 · soe 680,717 → 683,832）⇒ 并发会话
   （母公司章 spec）正在高频改同一批文件。→ 判「守卫红了是不是自己造成的」时，
   若判据文件 mtime 在分钟级内且不是自己改的，**先复跑一次**再下结论。
2. **`-k "h1 or h2 or ..."` 宽匹配在本机不可用** —— 它按测试名子串匹配，
   `h1` 会命中上万个无关测试；叠加实测 **40 个并发后台进程**（多数属其他会话）后
   跑了 4 分钟仍在 91%。改用**显式文件清单**，19 秒完成且失败可逐条判归属。
3. **YAML step 名里的 `: ` 会被当映射分隔符** —— `name: H cycle amount controls
   (two-way lock: amount vs rate columns)` 让 `yaml.safe_load` 抛
   `mapping values are not allowed here`，而 `governance-checks.yml` 有 3500+ 行、
   报错位置指向文件中部难定位。→ 新增 job 后**必须 `yaml.safe_load` 验证一次**；
   含 `: ` 的 step 名一律加引号。

### 范围外的预存在红（不属本 spec，未动）

`backend/tests/four_table/test_report_formula_filler_mirror.py` **22 failed** ——
全部是 `report-config-account-code-integrity` spec 的成果被回退：
`report_formula_service.py` 里 V138 的镜像改码（专项储备 4103→4301 / 库存股 4003→4201 /
开发支出 1703→1704）、派生行拦截门 `DERIVED_ROW_NAMES_WITHOUT_ACCOUNT`、
6701/6702 互换修正**全部不在磁盘上**。本会话只负责 H 类，故只在此登记不修。

### Task 18 实录（浏览器实测，2026-08-10）—— 5 条全过 + 3 处 tasks 原文被实测修正

实测项目 `2aa00f57-1df4-4fe8-9840-2d65d0fd8749`（重庆和平药房连锁有限责任公司_2025，
`audit_year=2025` / `template_type=soe`）。三个底稿：
H1 `c71b7c54-…` / H3 `899bf861-…` / H8 `34bbc627-…`。

开工先重跑 `verify_h_cycle_extraction_live.py` → `rc=0`，确认 Task 1~17 成果未被
并发会话回退（本 spec 有过三个 `[x]` 被回退的先例，见上文）。

#### 通路变更：MCP 浏览器工具不可用 → 本地 Playwright CLI

本会话工具列表里**没有 chrome-devtools / playwright MCP**（与 tasks 原文写的
「浏览器实测（chrome-devtools）」不符），改走本地 CLI：`npx playwright --version`
= **1.60.0**，chromium 二进制 `Chrome for Testing 148.0.7778.96 (playwright chromium v1223)`
已装（`npm exec playwright install chromium --dry-run` rc=0 探测，不实际下载）。

用主 `playwright.config.ts`（`reuseExistingServer: !CI` 会复用已在跑的 3030），
但**必须带 `SKIP_E2E_SEED=1`** —— 其 `globalSetup` 会
`execSync('python scripts/e2e/seed_fix_projects.py --fix')` 写库。
临时 spec `e2e/tmp-h-cycle-task18.spec.ts`（收口已删）。

#### 五条实测结果

| # | 判据 | 结果 |
|---|---|---|
| 1 | H8 审定表见 `1651` 族真实金额 | ✅ 「与试算平衡表核对」块出 `352,406,145.74` |
| 2 | H3 审定表溯源面板四槽 | ✅ 四行全渲染 |
| 3 | H1 审定表从四表库出数 | ✅ 溯源面板 3 行 + 预填按钮 enabled |
| 4 | 披露推送后附注 `last_sync_at` 前移且子表非空 | ✅ 八、26 NULL → `2026-08-10 04:20:54` |
| 5 | 金额输 `1234567.5` 显 `1,234,567.50` | ✅ H1-1（`WpAmountInput` 宿主） |

第 1 条 TB 核对块四行（本表未审 / 试算平衡表 / 差异）：

```
使用权资产原值(1651) | 179,000.00 | 352,406,145.74 | -352,227,145.74
累计折旧(1652)      |  30,000.00 | 219,627,999.70 | -219,597,999.70
减值准备(1643)      |     500.00 | —              |         500.00
净额                | 148,500.00 | 132,778,146.04 | -132,629,646.04
```

第 2 条 H3 面板（`.wp-four-table-source`，bar 文案「四表库取数口径 报表行 BS-027」）：

```
投资性房地产原值        | 1521 | 1521
累计折旧（客户科目表）  | 1525 | 1525
累计摊销（客户科目表）  | 1526 | 1526
减值准备（本项目无此科目）| —   | —
```

第 3 条 H1 面板（`.wp-sem-source`）：`固定资产原值 1601 客户科目表` /
`累计折旧 1602 客户科目表` / `减值准备 本项目无此科目 未命中`。

第 4 条推送：`POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper`
→ `200 {success:true, section_id:"八、26", rows_synced:25, created:false, texts_synced:0}`。
落库核实 `sub_table_data['使用权资产']` = **25 行 array**，列结构同构
（`label/layer/begin/increase/decrease/end/is_total`）**未被压扁**；金额全 0 是
国企披露侧本身未录数所致，非同步丢数。

#### 三处 tasks 原文被实测修正

1. **H1 按钮文案不是「从四表库带入未审数」**，实为 **「从TB子科目预填」**
   （`H1TabAdjudication.vue`）。平台上「从四表库带入未审数」这一文案的宿主是
   N1/N3/N4/N5 / K1/K2 / J1/J2 / G8/G9 / H2/H4，**H1 不在其列**。
   → 用文案做 e2e 断言前必须先 grep 真实宿主。
2. **H3 与 H1 用的不是同一个溯源面板组件**：H1/H2/H4/E1 用
   `WpSemanticAccountSourcePanel`（`.wp-sem-source`，`<details>`+`summary`），
   H3 用 `WpFourTableSourcePanel`（`.wp-four-table-source`，`.src-bar` + `el-collapse-transition`）。
   两者 DOM 结构与展开方式都不同。
3. **立项预设「三个底稿是空底稿」被推翻**：实为已有 **37 行 `checklist_responses`**
   （H8 28 / H3 5 / H1 4，其中 `H8-1-rows` remark 3656 字节）。故复原**只能删本轮
   新增 item_id + 改回被覆盖值**，禁整表清空。

#### 第 5 条的对照实证：H8-1 千分符确实不生效（存量缺陷，未修）

同一测试里做了 A/B 对照：

- H1-1 `.wp-amount-input input`（90 个）→ 输 `1234567.5` 失焦显 **`1,234,567.50`** ✅
- H8-1 `.adj-table .el-input-number input`（60 个）→ 输 `1234567.5` 失焦显 **`1234567.5`** ❌

原因即 memory 已记的铁律：`H8TabAdjudication.vue` 的四个金额列用**裸
`el-input-number` 且未传 `formatter`**，而 EP 2.13.6 根本无该 prop。
→ **Task 18 第 5 条按「金额控件（`WpAmountInput`）千分符生效」判过**；
H8-1 等存量 `el-input-number` 的替换属 memory 已登记的「存量替换待单独 spec 收口」，
本 spec 范围外，此处仅留实测证据。

#### 附带发现（未修，登记）：`syncToNotes` 的 toast 假报失败

T18-4 的 toast 序列是
`已同步 25 行到附注「八、26」 | 同步附注失败，请稍后重试 | 已同步 25 行… | 同步附注失败…`，
但 4 次 HTTP **全 200 且 `success:true`**。`H8TabDisclosureSoe.vue` 的
`syncToNotes()` 用裸 `catch {}` 把成功路径后段的异常（`eventBus.emit` 之后的
`checkNoteConsistency` 自动校对链）也吞成「同步附注失败」，属 fail-open 掩盖 +
误报。属 H8 披露 UX 问题，不影响本 spec 判据，登记不修。

#### 复原与双重核实

工具 `backend/scripts/diagnose/tmp_task18_snapshot.py`（`--mode snapshot|verify|restore`，
收口已删）。诊断目录实测**无任何现成 `tmp_*_restore.py`**，故自建。

- `verify` 先做**自检**：刚建基线即跑 → `diff_count=0`（否则说明脚本比对逻辑有缺陷）
- 实测后 `verify` → `diff_count=22`（4 新增 + 9 覆盖 + 附注 6 项），**同时构成 verify 的变异检验**（0→22 证明不是假绿）
- `restore --apply` → 14 项（4 DELETE + 9 RESET + 1 附注回滚）
- **独立 SQL 直查二次核实**（不复用脚本逻辑）：checklist 37 行 / `H8-soe-*` 残留 0 /
  `H8-1-rows` 3656 / `H1-1-cost-rows` 1047 / 八、26 md5 `38d737af009b5c243c63897a23601cb9` /
  `td_len` 40662 / `last_sync_at` NULL / `updated_at` 2026-08-01 12:56:42 /
  三底稿 `parsed_data` 非 NULL 数 = 0 —— **逐项与基线吻合**

`working_paper.parsed_data` 三者全程保持 NULL，印证 memory 铁律「宿主类页面完整表格
视图编辑永不落库」，底稿数据实际走 `checklist_responses`。

#### 两个新踩坑（已并入本会话认知，建议进 `#conventions`）

1. **asyncpg 的 timestamptz 参数不接受字符串，`CAST(:ts AS timestamptz)` 救不了** ——
   报 `invalid input for query argument $3: '2026-07-22 03:39:49.677234+00'
   (expected a datetime.date or datetime.datetime instance, got 'str')`，
   **与 uuid 行为不同**（uuid 传字符串 + CAST 可用）。绑参阶段就炸，SQL 层 cast 来不及。
   → 从 JSON 基线读回的时间戳必须先 `datetime.fromisoformat()`。
   因整个 restore 在 `engine.begin()` 里，首次失败**已整体回滚**（独立 SQL 核实
   `cl_total` 仍 41、md5 未变），未留半写状态。
2. **Playwright 等待不能只等 `.gt-loading-overlay` detached** —— 该 overlay 在 H 循环
   HTML 渲染器路径下**从不出现**（`count=0`），`waitFor({state:'detached'})` 立即
   resolve，随后固定 2500ms 不足以等到 sheet 挂载 → 页面文本仅 148 字符、
   断言假红。正解：等 `.el-tabs` + `.el-table` visible 再 +3500ms（实测需 ~6s）。
   另：**PowerShell 控制台把 Playwright 的中文 stdout 腌成乱码**（`底稿目录`→`搴曠鐩綍`），
   故本轮所有实测结果一律 `fs.writeFileSync(..., 'utf-8')` 写 `tmp_task18_result_*.json`
   再用 python 以 UTF-8 读回，不靠 console.log 判读。
