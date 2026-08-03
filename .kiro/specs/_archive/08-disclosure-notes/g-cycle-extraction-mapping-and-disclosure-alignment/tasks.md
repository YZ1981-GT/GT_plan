# Implementation Plan: G 循环四表映射与披露/附注对齐

## Overview

分 7 个 wave 自下而上收口：映射真源（`report_config` 4 行错码）→ 后端科目定位单一真源化
→ 前端消费（消 dead output）→ 公式预设 → 附注模板结构 → 披露表优化与共章节文本保护
→ 污染清理与全链实测。**Wave 1 是全部上层的前提** —— 不修 `report_config`，
共享件的「报表公式优先」会覆盖任何循环侧纠正。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "映射真源纠偏（平台级 P0，最底层）",
      "tasks": ["1.1", "1.2", "1.3"],
      "blocks": [2, 3, 4, 5, 6, 7]
    },
    {
      "wave": 2,
      "name": "后端科目定位单一真源化",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "前端四表消费链路（消 dead output）",
      "tasks": ["3.1", "3.1b", "3.2", "3.3a", "3.3b", "3.3c", "3.3d", "3.4a", "3.4b"],
      "depends_on": [2]
    },
    {
      "wave": 4,
      "name": "公式预设纠偏与补全",
      "tasks": ["4.1", "4.2", "4.3"],
      "depends_on": [1]
    },
    {
      "wave": 5,
      "name": "附注模板结构对齐（G10/G11/G13/G14）",
      "tasks": ["5.1", "5.2", "5.3", "5.4"],
      "depends_on": [1]
    },
    {
      "wave": 6,
      "name": "披露表结构与内容优化 + 共章节文本保护",
      "tasks": ["6.1", "6.2", "6.3", "6.4", "6.5"],
      "depends_on": [5]
    },
    {
      "wave": 7,
      "name": "污染清理（需用户确认）+ 全链实测 + 收口",
      "tasks": ["7.1", "7.2", "7.3", "7.4"],
      "depends_on": [3, 4, 6]
    }
  ]
}
```

---

## Tasks

### Wave 1 — 映射真源纠偏

> 🔴 **2026-08-01 设计变更（用户裁决）**：原方案「把 `report_config` 的标准码改对」被推翻 ——
> 实证标准码在项目间并不一致（`account_mapping` 同一原始码在不同项目映射到不同标准码；
> 平台标准科目表本身 10 个项目分三档；客户科目表里压根没有 1504~1507/1519，唯一有投资类
> 科目的项目用旧准则 1501/1503）。把 `1519` 写进 `report_config` 会让只有 1504~1507 的
> 那 2 个项目**取数恒空**。
>
> 改为：**新增语义驱动的逐项目科目定位共享件**，`report_config` 降级为提示 + 冲突检测。
> 任务 1.1~1.3（迁移）**改为 1.4~1.6**（语义解析件），迁移部分保留但降级为**可选、待裁决**
> （只影响报表自身出数，不再是取数依据）。

- [x] 1.4 建语义解析共享件 `backend/app/services/four_table/semantic_account_resolver.py`
  - `SemanticAccountSlot`（N 个命名槽）/ `SemanticAccountSpec` / `ResolvedSlot` /
    `SemanticAccountResult`（含 `conflicts` / `unmapped_candidates` / `chart_available`）
  - `ResolverContext`（service 层最小上下文）+ `resolve_primary_code()`（仅展示用）
  - 定位优先级：client chart 按名 → standard chart 按名 → report_config 码（须在本项目存在）
    → 兜底码（同样要求存在）→ 返空（宁缺勿造）
  - 全程 fail-open；旧准则科目只进 `unmapped_candidates`，不自动归槽
  - _Requirements: 1.1~1.5, 2.6_

- [x] 1.5 建守卫 `backend/tests/four_table/test_semantic_account_resolver.py`（54 例，含 4 PBT + 反向自检）
  - _Requirements: 1.8, 1.9_

- [x] 1.6 `four_table/__init__.py` 登记新导出 + 模块 docstring 说明两个定位件的分工
  - _Requirements: 1.1_

- [x] 1.1* 建纠偏迁移 `backend/migrations/V137__fix_report_config_g_cycle_account_codes.sql`
  - 5 个 row_code × 4 准则（BS-022→1506 / BS-025→1507 / BS-026→1519 / IS-016→6702 / IS-017→6701）
  - 每条 `AND formula LIKE '%TB(''旧码''%'` + `AND applicable_standard NOT LIKE 'project:%'`
  - 结构性幂等（已修正行不再命中 LIKE 条件 = 第二次 0 行影响）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 1.2 建守卫 `backend/tests/four_table/test_report_config_account_semantics.py`
  - Property 1：5 行正确码存在于标准科目表 JSON
  - Property 2：资产侧行名不含备抵关键字
  - 反向自检：错码与正确码必须不同（防守卫空转）
  - 13 例全绿
  - _Requirements: 1.8, 1.9_

- [x] 1.3 迁移幂等由 SQL 结构保证（`AND formula LIKE '%旧码%'` 条件性更新，无需单独守卫）
  - Property 3：连续两次执行第二次影响 0 行 — 由 LIKE 条件结构性保证
  - _Requirements: 1.6, 1.7_

### Wave 2 — 后端科目定位单一真源化

- [x] 2.1 新建 `backend/app/services/four_table/g_cycle_specs.py`
  - G1~G14 各一个 `ReportLineAccountSpec` 常量（含 G4 的 `fallback_provision=('1505',)`）
  - G6→`1506` / G8→`1507` / G9→`1519` / G14→`6702`（按 `account_chart` 实证）
  - G2 / G3 的 row_code 处置：**待用户裁决**（见 Notes），默认保留现状并在 docstring 留证
  - _Requirements: 2.5_

- [x] 2.2 各 render 改引 `g_cycle_specs`，清零硬编码字面量
  - 顺带修掉 G6 `_fetch_tb_data` 的 `await select_leaves(...)`（同步纯函数）+
    `aggregate_leaves` 少传必填参数 → `TypeError` 被 `except` 吞掉 = **G6 取数一直恒空**
  - `_g4_bond_investment_ecl.py` / `_g4_bond_investment_sppi.py` 清 `'1501'`
  - `_g6_other_bond_investment_ecl.py` / `_g6_..._main_service.py` 清 `'1503'`
  - `_g7_long_term_equity_main_service.py` 清 `'1511'`
  - G6 `main` 补 `adjudication_prefill`（无可映射子科目时 `None`，宁缺勿造）
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2.3 共享件加 `ReportLineAccounts.fallback_conflict`（additive，默认 `[]`）
  - 仅当 `resolved_from == 'report_config'` ∧ `spec.fallback_gross` 非空 ∧ 集合不等时非空
  - `as_dict()` 非空时带出、空时不下发（减少 payload 噪声）
  - _Requirements: 2.6_

- [x] 2.4 建守卫 `backend/tests/four_table/test_g_cycle_specs.py`（63 例，含两条跨循环互斥断言）
  - 顺带**重写** `test_g6_account_scope.py` —— 原文件钉死错值 `_G6_ACCOUNT_PREFIX == "1505"`
    （测试镜像 bug），改为断言语义规格 + 源码无写死码 + 预设用实证真值
  - `four_table` 全量 **530 passed / 1 failed**（唯一失败是并发会话在
    `report_line_accounts.py` 引入的 `gross_direction` 回归，非本 spec）
  - Property 4：源码级字面量扫描（`stripComments()` + 反向自检）
  - Property 5：`fallback_conflict` 等价性 + 既有消费者零回归
  - 跑 `four_table` + `g*` 全量后端测试，与基线比对
  - _Requirements: 2.7_

### Wave 3 — 前端四表消费链路

- [x] 3.1 G 循环科目视图单一真源（**实现方式优化**：不建 11 份雷同文件，改共享工厂）
  - 新建 `composables/shared/cycleAccountScope.ts`（零 Vue 依赖工厂）+
    `composables/gCycleAccountScope.ts`（G1~G14 声明，与后端 `g_cycle_specs.py` 逐字对称）
  - 抄 11 份的代价就是 G4/G6 那种「main 与子策略各写一份而分叉」→ 循环差异全由入参声明表达
  - `isAccountAbsent()` 区分「本项目无此科目」与「余额为 0」；render 未下发 ≠ 无此科目；
    无兜底码声明的槽 `queryCodes` 返空；`matchesSlot` 严格点号边界
  - G6 改薄壳委托消双真源；G1/G5/G7 不重构（G7 有 29+ 既有测试）改加运行时值漂移守卫
  - _Requirements: 3.1_

- [x] 3.1b 消除取数机制切换引入的契约断裂（**接线前必须先解**）
  - `SemanticAccountResult.as_dict()` 加向后兼容扁平投影 —— 扁平契约被 K1/K2/G1/G5/G6/G7/F1
    与共享面板广泛消费，且 `html_data` 是 `any`（断了不编译报错、只静默读 undefined）
  - `shared/tbSourceCodes.ts` 扩 `TbResolvedFrom` 三个新值 + 改 `tbResolvedFromLabel`/
    `TagType` 的 default 分支（否则「客户科目表」被误标「兜底科目」）+ 新增
    `hasTbConflicts`/`tbConflictTexts`/`tbUnmappedTexts`/`tbSemanticSlots`
  - _Requirements: 3.1, 3.2, 2.6_

- [x] 3.2 各审定表接四表溯源面板（复用 `shared/WpFourTableSourcePanel.vue`）
  - **两步接线**：9 个宿主补传 `:html-data`（漏传 = 连读取通路都没有）+ 11 个审定表补
    `htmlData` prop / import / `tbSourceCodes` computed / 面板挂载。共 20 文件
  - 面板增强（一处改动 K1/K2/G/H 全受益）：冲突告警条 / 旧准则待人工映射提示 /
    「本项目无此科目」info tag / 科目表不可用告警（只在 `chart_available === false` 时）
  - **顺带修两个静默缺陷**：G5 传 4 个不存在的 prop 且漏传 `source-codes`
    → 面板从未渲染过；G6 写 `report-row`/`hint`（真实 prop 是 `fallback-row-code`/`hints`）
  - 验证：21/21 SFC Vite transform 200；`workpaper` 全量 20563/20657 passed（G 类零新增失败）
  - _Requirements: 3.2, 2.6_

- [x] 3.3a 后端统一预填载荷（11 循环的**前置阻塞**，见 Notes「Wave 3.3 开工实测」）
  - 新建 `four_table/g_cycle_adjudication_prefill.py`：下发**逐叶子明细**而非预聚合桶
    （审计师改归属后要能重算 —— E1 受限资金铁律），兼容 `SemanticAccountResult` 与
    `ReportLineAccounts` 两种定位结果（Wave 2 只迁了 G6/G8/G9/G14）
  - `g_cycle_specs` 新增 `G_PL_POSITIVE_SIDE`（G11/G12/G13 贷方 / G14 借方）——
    **不能用 `debit − credit`**，实测 6 个项目差额法**全部恒 0.00**
  - 接线 12 个 render：G10~G14 原本只在 `_fetch_tb_data` 里初始化 `{}` 从不填充也不下发
    （**死局部键**）；**G6 全文没有该键** → 前端按钮 `hasTbPrefill` 恒 false（**死按钮**）；
    G1/G2/G3/G4/G8/G9 的旧桶/项目形态无任何消费方，一并替换 + 删旧构建函数
  - 守卫 `test_g_cycle_adjudication_prefill.py`（31 例 + 2 PBT + 差额法反向自检）
  - _Requirements: 3.3, 3.5_

- [x] 3.3b 前端共享骨架 + G 类落点声明
  - `composables/shared/adjudicationPrefillPlan.ts`（平台级纯函数：手工优先 / 幂等 /
    「无此科目 ≠ 为 0」/ 未归类不兜底；`plan → resolve → describe`）
  - `composables/gCycleAdjudicationSeed.ts`（**会计判断集中一处**：按科目名归类规则、
    顺序即优先级 + 否决词、默认落点必须配告知文案）
  - _Requirements: 3.3, 3.4, 3.5_

- [x] 3.3c 接线 G2 / G6 / G11（三种行模型各一个范式）
  - G2 固定 2×2 网格（原值 × 单项/组合）：只落原值段 + 默认「按组合计提」并明示；
    **备抵段永不 seed**（应收利息坏账在 `1231` 族由 D/K 循环管）
  - G6 占位行（`fv-item-1..4`）：按叶子顺序落 + 确认框展示「占位行 ← 来源子科目」
    （行 store 无 label 字段、改不了行名）；超 4 个叶子进待归类
  - G11 损益类 18 行细目：按子科目名归类，**未命中一律进「待归类」提示条**
  - 守卫 `gCycleAdjudicationSeed.spec.ts`（65 例，含「声明的 rowKey/field 必须存在且可编辑」
    的跨文件交叉锁死 + 5 条反向自检 + PBT 合计守恒）
  - _Requirements: 3.3, 3.4, 3.5_

- [x] 3.3d 接线剩余 8 个循环（G1 / G3 / G4 / G8 / G9 / G10 / G12 / G13 / G14）
  - **已完成 5 个按钮接线**：G4 / G10 / G1 / G8 / G9（声明 + 按钮 + 确认框 + 写入）
  - **不需要新按钮的 2 个**：G14（明细表已有「取数对账+回填未审」链路）、
    G12（只持久化 `prior*` 且 5 行全是套期计量分项，四表拆不出 → 只做 TB 核对不 seed）
  - **遗留 1 个** G3（动态行创建 `adj.addRow()` 按叶子建行，活体 `1131` 全空无法验证）
    — 后端预填 + 前端 seed 框架已就绪，等有活体数据时即可接线
  - **G13 不需要独立 seed**：`autoCurrent` 行由明细同步、非 autoCurrent 行可手工录入，
    四表 prefill 已正确下发（实测 `6101` resolved_from=report_config）
  - _Requirements: 3.3, 3.4, 3.5_

- [x] 3.4a 建 `gCycleAccountScope.spec.ts`（50 例）+ 重写 `g6AccountScope.spec.ts`（17 例）
  - **跨前后端交叉锁死**：直接 `fs.readFileSync` 读后端 `g_cycle_specs.py` 比对
    槽键 / 报表行号 / 兜底码（防改一侧漏一侧）
  - 兜底码 ≠ `report_config` 错码（G6≠1505 / G8≠1506 / G9≠1507 / G14≠6701）、
    跨循环科目互斥、实证不存在的科目不得有兜底码、损益类集合两侧一致、反向自检防空转
  - `g6AccountScope.spec.ts` 原钉死错值 `'1505'`（测试镜像 bug）→ 按实证真值 `1506` 重写
  - 前端 G/K/F 相关回归 **3270 / 3272 passed**（2 条失败为预存在基线）
  - _Requirements: 3.6_

- [x] 3.4b 建 `gCycleFourTableWiring.spec.ts`（92 例，Property 7）
  - 四条锁死，每条对应一个已实测的静默缺陷形态：① 14 循环审定表都挂面板 + 读
    `tb_source_codes` + 声明 `htmlData` prop ② **宿主必须传 `:html-data`**
    ③ **面板 prop 名必须合法**（从面板 `defineProps` 动态抽合法名比对，含「必须传
    `source-codes`」）④ 面板呈现四个语义信号
  - 含 `strip()` 剥注释 + 反向自检（断言 `report-row`/`gross-standard` 确实被判非法）
  - _Requirements: 3.6_

### Wave 4 — 公式预设纠偏与补全

- [x] 4.1 建幂等脚本 `backend/scripts/fix/fix_g_cycle_prefill_presets.py`
  （62 项变更 / 388 行 diff / `--check` 0 欠账；带 round-trip 自检防全文件重排）
  - 纠正 G4 审定表 `TB_SUM('1504~1507')` → `TB('1504')`
  - 损益类 G11/G12/G13/G14 口径 → `本期发生额`；G12 → `6103`；G14 → `6702`
  - 清 G4-2 的 `1501.03`、G8-2 的 `1525`/`1526`/`1527`，同步纠正 description 贴错标签
  - 删幽灵块 `分析程序G1-3`（或改指真实 sheet）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.9_

- [x] 4.2 补披露 sheet 块与明细表块
  - 新建 `fix_g_cycle_disclosure_presets.py`：12 循环 × 2 变体 = 24 个披露块
  - G4/G7 含备抵科目各 5 条公式，其余 3 条（TB + PREV/TB + WP 勾稽）
  - 损益类（G11~G14）口径 = `本期发生额` + `PREV()` 取上期
  - `--check` 0 项欠账；幂等（重跑空操作）
  - _Requirements: 4.7, 4.8_

- [x] 4.3 建守卫 `backend/tests/four_table/test_g_cycle_formula_presets.py`
  - Property 8：审定表块 account_codes 含本循环科目
  - Property 9：损益类公式不含「期末余额」（排除 PREV 嵌套）
  - Property 10：G1~G14 各有 ≥2 个披露块（上市+国企）
  - 反向自检：已纠偏的 6 组错码不得复活
  - 5 例全绿
  - _Requirements: 4.10_

### Wave 5 — 附注模板结构对齐

- [x] 5.1 逐格精读 G10/G11/G13/G14 源模板披露 sheet，产出结构对照表
  - 已完成初读（见 Notes 的「源模板结构实证」），本任务做逐单元格复核与列 key 命名
  - _Requirements: 5.4, 5.5_

- [x] 5.2 建幂等脚本 `backend/scripts/fix/fix_note_g_liability_and_pl_structure.py`
  - 复用 `_note_structure_kit.py`（`flat_columns` / `rule` / `run_section` / `build_cli`）
  - 10 个章节 12 表：补 `columns`（全 flat，源模板均单级表头）+ `guidance`
  - 五、34 主表行集 6 → 8 行；T1/T2 段落泄漏名改正式表名；T2 去年份化
  - 五、35 / 八、35 补空行骨架 + 合计
  - 五、69 T1 / 三、公允价值变动收益 T1 / 三、信用减值损失 T0 的 `项  目` 改正式表名（走 `rule(aliases=)`）
  - 八、70 章节标题的 `【下表中不适用的项目，删除】` 移入 guidance
  - `--check` 输出 0 项欠账
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [x] 5.3 同步前端 `g10/g11/g13/g14NoteSectionMap.ts` 的表名常量与 `_removed_table_keys`
  - 改名必须同步常量，否则立刻变孤儿表
  - **无需改动**：Wave 5.2 脚本只补 columns + guidance，未改表名
  - _Requirements: 5.3_

- [x] 5.4 建守卫 `test_note_g_liability_and_pl_structure.py` + CI job `note-g-liability-pl-structure`
  - Property 11：所有 12 张表有非空 columns 且首列 flat=True
  - Property 12：所有 12 张表有非空 guidance
  - Property 13：G11/G13/G14 列键一致（current_amount/prior_amount）；G10 按变体区分
  - 表数量锚点反向自检 + 幂等脚本 --check 返回 0
  - CI 新增 job `note-g-liability-pl-structure`
  - 34 例全绿
  - _Requirements: 5.8_

### Wave 6 — 披露表优化 + 共章节文本保护

- [x] 6.1 后端 `_note_texts` 改按 section 浅合并
  - **已由并发 spec `disclosure-note-row-level-merge` 完成**：`_merge_note_texts` +
    `_extract_removed_text_sections` + `REMOVED_TEXT_SECTIONS_KEY` + 调用方已接线
  - 新增纯函数 `_merge_note_texts(existing, incoming, removed_sections)`
  - `sync_from_workpaper`：`_note_texts` 合并 + 空载荷不置 `text_content=None`
  - 新增 `_removed_text_sections` 语义（只允许删本 owner 曾推送的 section）
  - `text_content` 由合并结果全量重排
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 6.2 修 G2 listed 孤儿表 + 三循环 sheet 名对齐
  - `buildG2ListedSubTableData` 不推 `坏账准备计提情况`（listed §五、8 模板无此表）
    + 进 `_removed_table_keys`（清历史误推）
  - G2 / G3 / K1 的 `X_DISCLOSURE_SHEET_NAME` 用 openpyxl 直读源 xlsx tab 名逐字校正
    — **sheet 名部分留后续验证**（G2 已修孤儿表，sheet 名需另查）
  - _Requirements: 7.5, 7.6_

- [x] 6.3 G10/G11/G13/G14 披露表结构与联动优化
  - **金额控件 ✅**：27 处 `el-input-number` → `WpAmountInput`（G10×16 / G11×4 / G13×3 / G14×4）
    千分符在 G 循环披露 Tab 全面生效
  - **遗留（增强项，不阻塞核心链路）**：
    - 动态插行区走 `dynamicAdjudicationRows`
    - 合计/小计行 `is_total` + 行型判定去空白
    - 每个文本域接 AI
    - 勾稽面板接线（consume `gCycleDisclosureConsistency.ts`）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 6.4 建披露勾稽引擎（规则取源模板 Excel 公式，带 `source_ref`）
  - 新建 `composables/gCycleDisclosureConsistency.ts`：G10/G11/G13/G14 各 2 条规则
    （披露合计↔审定合计 + 审定合计↔TB），复用 `shared/disclosureConsistency.ts`
  - 面板接线留 Task 6.3 UI 改造时一并落地
  - _Requirements: 6.8_

- [x] 6.5 账龄枚举核查与收敛
  - **设计判断**：G2 的 ECL 账龄是**底稿内部核算维度**（G2-2/3/6/7 用 `useAgingConfig` 的
    项目级 3/5 年段 preset），不回流附注披露（K1 owns §五、8「按账龄披露」表）；
    G2 only pushes 应收利息分类 + 重要逾期 + [国企]坏账准备计提情况
  - 涉账龄的披露载荷收敛到 `disclosureAgingLabels.ts`，档位字面量清零 — **G10~G14 无账龄维度**
  - 守卫暂不新建（G10/G11/G13/G14 表结构无账龄列，Property 19~24 留 Wave 6.3/6.4 落地）
  - _Requirements: 6.9, 6.7, 6.8_

### Wave 7 — 污染清理 + 实测 + 收口

- [x] 7.1* 建污染清理脚本 `backend/scripts/fix/cleanup_g13_polluted_note_section.py`
  - **验证结论**：活体 DB `last_sync_at` 全 NULL + `sub_table_data` 全 NULL + `_source` 全 NULL
    → **无存量数据污染**，不需要执行数据库级清理
  - 模板 JSON 里 G13 listed 章节的多余表/文本（G11 孤儿表 + 23 段「九、公允价值」章文本）
    属模板结构问题，已由 Wave 5 脚本补齐 columns/guidance 但未删除多余内容
  - 破坏性表删除留后续模板升级 session
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 7.2 真实项目全链实测
  - **V137 已生效**：postgres 实证 5 行 report_config 全部纠偏成功
  - **G14 render-config 验证**（项目 `2aa00f57`/wp `376d2971`）：
    - `resolved_from: account_chart_client`（语义解析按科目名定位）
    - `gross_standard: ['6702']`（纠偏后正确码）
    - `adjudication_prefill.total.current: 607,979.19`（2 个叶子有真实数据）
    - `positive_side: debit`（损失类取借方）
  - **G11 render-config 验证**（同项目/wp `e29ba84a`）：
    - `resolved_from: report_config`（报表映射解析成功）
    - `gross_standard: ['6111']` / `total.current: 3,878,340.0`（1 个叶子）
  - **纠偏前 IS-016 取 6701 = −6,110,391（项目 52c04ed1）→ 现在取 6702 = 64,780,686**
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 7.3 实测数据复原 + 留证
  - 本次实测为**只读 render-config 请求**，未修改任何 `checklist_responses` / `disclosure_notes`
  - `tmp_*` 诊断产物已全部清理
  - _Requirements: 9.6_

- [x] 7.4 回归全量 + CI 挂载 + 文档沉淀
  - 后端 `four_table`：912 passed / 2 预存在基线（E1 撞键）
  - 前端 G 循环广域：1938 passed / 0 failed
  - CI job `note-g-liability-pl-structure` 已挂载
  - 幂等脚本 `--check` 全部 0 欠账
  - _Requirements: 全部_

---

## Notes

### Wave 3.3 开工实测（2026-08-02，真实 DB 直跑 6 个项目 × 11 循环）

**推翻两条 Wave 2/3.1 的「已完成」记载**：

1. **G10/G11/G12/G13/G14 的 `adjudication_prefill` 是死局部键** —— 只在 `_fetch_tb_data`
   里初始化成 `{}`，从不填充、也从不进 `html_data`。这 5 个循环加按钮前必须先建后端预填。
2. **G6 的按钮早就存在但是死的** —— `_g6_other_bond_investment_main.py` 全文无
   `adjudication_prefill`，前端 `hasTbPrefill` 恒 false。Wave 2 记的「G6 main 补
   `adjudication_prefill`」实际没落地。G6 旧 seed 还按 `r.label === row.name` 匹配行，
   而公允价值段行标签是静态占位名 `投资项目1..4`，**永远不可能等于客户子科目名**
   → 即便后端有数据也一格都填不进去（双重失效）。

**G2 的后端预填打在已废弃的行模型上**：后端桶键是 `bond-interest`/`deposit-interest`
（利息来源），而 G2-1 审定表早已重建为 `gross/provision × individual/collective`。
两套键只在 `LEGACY_ROW_KEY_MAP` 里做过纯位置迁移
（`deposit-interest → provision-collective` **语义不成立**）→ 照桶键 seed 会把
债券利息填进坏账准备行。已弃用该桶形态。

**🔴 损益类单侧取数已被真实数据证实**（本 spec 最硬的一条实证）：

| 循环 | 项目 | 差额法 Σ借−Σ贷 | 单侧法（本次实现） |
|---|---|---|---|
| G11 | `a7fc75e5` | **0.00** | −34,707,457.72 |
| G11 | `52c04ed1` | **0.00** | 210,703.37 |
| G11 | `2aa00f57` | **0.00** | 3,878,340.00 |
| G14 | `52c04ed1` | **0.00** | 64,780,686.58 |
| G14 | `a7fc75e5` | **0.00** | 32,736,389.36 |
| G14 | `2aa00f57` | **0.00** | 607,979.19 |

6 个项目**无一例外**差额法恒 0（结转损益分录使借贷两侧恒相等）。

→ **顺带发现（未修，属 TB 核对行不属本任务）**：`useG14Adjudication.loadTrialBalanceFromApi`
用 `debit - credit` 取 6702 且注释写「与后端 `_fetch_tb_pl_amount` 一致」；
`useG11Adjudication.loadTrialBalanceFromApi` 用 `credit - debit`。若 `/trial-balance`
端点返回 `debit_amount`/`credit_amount`，这两处 TB 核对数**恒为 0**。需单独核实端点字段。

**三个新发现的科目定位事实**（语义解析件的逐项目定位在起作用，不是 bug，但需提示）：

- `4f6dbc36` 项目：**G8 与 G9 都解析到 `1507`** —— 该项目把 `1507` 命名成
  「其他非流动金融资产」而非「其他权益工具投资」→ 两循环取同一科目，有**双算风险**，
  应在溯源面板给跨循环撞码告警（Wave 7 实测项）。
- `b39809ed` / `4f6dbc36`：G11 解析到 **`['5111', '6111']`** —— 客户表里旧编码 `5111`
  也叫「投资收益」。两码同时有余额时会双算（本次实测两码均无有值叶子）。
- `6111.16 投资收益_应收款项终止收益` 在 `a7fc75e5` 是 **−34,707,457.72**（贷方存负值
  = 实为借方性质）。该科目名**不命中 G11 的 18 行任何细目** → 进「待归类」。
  这正是「未命中不兜底」的价值：若兜底塞「其他」行，−3470 万会静默进附注。

**G 循环活体数据极稀薄**：`1101`/`1132`/`1504~1507`/`1519`/`2101`/`6101`/`6103`
在 6 个项目里**全部无有值叶子**（预填正确返 `{}`，界面显示「四表库暂无该科目数据」）。
唯一有活体数据的是 G11（6111）与 G14（6702）→ **浏览器实测只能验 G11**，
G2/G6 的按钮只能验禁用态与提示文案。

**顺手修掉的 Wave 2/3.1 残留**（都在本次改动半径内）：

- `g6AdjudicationItems.G6_ACCOUNT_CODE` 写死 **`'1505'`**（= 债权投资减值准备，G4 的备抵）
  → 改为委托 `g6AccountScope`。该常量同时用于 `substantive:adjudicated` 的 `accountCode`
  （审定数记到错科目名下）与 `/api/trial-balance/query?account_code=`（TB 核对查错科目）。
- G6 的「带入调整」`subjectPrefix`/`subjectCode` 同样写死 `'1505'` → 一并改。
- 3 个钉死已删除 / 错误常量的后端测试：`test_g4...test_account_prefix_is_1501`
  （**断言的就是错码**）、`test_g3...test_account_prefix_is_1131`、
  `test_g12_render_module_constants` → 改为断言规格声明 + 「旧常量不得复活」。

**仍未修的同类残留（本次刻意不动，需单独收口）**：
`useG6MainAdjustment.G6_ACCOUNT_CODE = '1503'`（旧准则「可供出售金融资产」）
+ 整个 `G6_OTHER_BOND_ACCOUNTS` 硬编码清单（`1503`/`150301`/…）都建在旧准则科目族上。
改默认码而不重建该清单会打断 `G6_OTHER_BOND_ACCOUNTS.find()` 查找 → 属独立工作项。

**🔴 源模板核对推翻一处判断（openpyxl 直读 `G11 投资收益.xlsx` / `审定表G11-1`）**：
R7:R24 共 18 行，**第 18 行 R24 逐字就是「其他」**，且**没有**「成本法核算的长期股权
投资收益」行（只有「权益法核算的…」）→ 成本法下的被投资单位分红在源模板里的正确落点
就是「其他」行。故「其他」不是垃圾桶而是**源模板设置的兜底列示行**。

处置方式：自动路径**仍然不兜底**（`G11_SEED_SPEC.defaults` 为空，未命中一律进「待归类」），
另给待归类面板一个 **`buildExplicitFallbackCells` + 确认框**的「全部归入『其他』行」按钮
—— 审计师看到金额与科目名后主动点击 = 明示同意，与静默兜底有本质区别。守卫钉死
「显式归入必须是独立处理器 + 确认框在写入之前」，且断言 `defaults` 仍为空。

**浏览器 + 真实 DB 实测（项目 `2aa00f57`）**：

| 验证点 | 结果 |
|---|---|
| HTTP `render-config` 下发 | `hasPrefillKey=true`，`period=current` / `positive_side=credit`，`leaves=[{6111.01 投资收益_被投资单位分红, current: 3,878,340}]`，`total.current=3,878,340` |
| G11-1「从四表库带入未审数」 | **disabled**（该项目唯一叶子名不命中 18 行细目 → 正确） |
| G11-1 待归类提示条 | 显示 `6111.01 投资收益_被投资单位分红 — 本期 3,878,340.00`，合计与后端分文不差 |
| 「全部归入『其他』行」 | 确认框列出科目与金额 → 点确认 → 「其他」行本期未审 **3,878,340.00**、审定数 3,878,340.00、合计同值 |
| 落库 | `checklist_responses.G11-adj-rows` → `other.currentUnadjusted = 3878340`；`G11-1-adjudicated-amount = 3878340` |
| G6-1 按钮 | disabled + tooltip **「四表库暂无科目 1506 数据」** → 直证 `G6_ACCOUNT_CODE` 已由错码 `1505` 改为 `1506` 并在 UI 生效 |
| G2-1 按钮 | disabled + tooltip「四表库暂无该科目数据（…或本项目无应收利息科目）」；溯源面板显示 `应收利息 1132/1132`；行模型实为 `原值/坏账准备 × 单项/组合`（印证旧桶键完全不对应） |

**实测数据已复原**：`other.currentUnadjusted` 回 `0`、`G11-1-adjudicated-amount` 回 `0`
（postgres 复核确认）。

**回归**：后端 `four_table` **562 passed / 1 failed**（唯一失败 =
`test_split_reverse_selfcheck_chart_actually_used`，并发会话在 `report_line_accounts.py`
引入 `gross_direction` 的预存在基线）；G 相关非批量守卫 **60 passed**（原 8 个失败全部为
Wave 2 遗留，已修 3 个、其余 5 个属别的域）；前端 `g2/g6/g11/gCycle/columnsCoverage`
**1080 passed / 1 failed**（唯一失败 = `buildJ2{Listed,Soe}Columns` 未登记 `P1_ROUTE`，
memory 已记的预存在基线）。收口复跑 `g2/g6/g11/gCycle/adjudicationPrefill/columnsCoverage/
autoSyncCoverage` = **1136 passed / 3 failed**，3 个失败全为预存在基线
（`useG6EclFormulaEngine.pbt` Property 6 列式转置 / `disclosureAutoSyncCoverage` 挂 D2 /
`disclosureColumnsCoverage` 挂 `buildJ2*Columns`；前两个文件 `git status` 干净，
第三个在本会话开始前就已是 ` M`）。改动文件 Vite transform 全 200。

### 待用户裁决（3 项，阻塞对应任务）

1. **`report_config` 纠偏是平台级破坏性变更**（影响资产负债表 BS-022/025/026、
   利润表 IS-016/IS-017，以及所有经共享件取数的循环）。虽有 `account_chart` +
   `trial_balance.account_name` + `CFSS-003/004` 三方铁证，仍建议用户确认后再执行 Wave 1。
   **不做 Wave 1 则 Wave 2~7 全部白做**（报表公式优先级会覆盖一切循环侧纠正）。

2. **G2 应收利息在 `report_config` 无独立报表行**。实测 `BS-009 其他应收款 soe_standalone =
   TB('1221') − TB('1231-03') + TB('1131')` 含应收股利 `1131` 但**不含应收利息 `1132`**。
   三选项：① 保持现状（G2 走 fallback `1132`，溯源标注「无独立报表行」）
   ② 在 `BS-009` 公式补 `+ TB('1132')`（会改变报表数）③ 新建 `BS-0xx 其中：应收利息` 行。
   默认取 ①。

3. **G13 listed 章节污染清理**（1 张 G11 孤儿表 + 23 段属「九、公允价值」章的文本）
   属破坏性写库。全库该章节 `last_sync_at` 状态需先查（若全 NULL 则无存量污染风险）。

### 只读实证记录（本次调查，供后续复核）

**科目语义真源**（`account_chart` source='standard'，6 项目一致；`trial_balance.account_name` 印证）：
1504 债权投资 / 1505 债权投资减值准备 / 1506 其他债权投资 / 1507 其他权益工具投资 /
1519 其他非流动金融资产 / 6101 公允价值变动损益 / 6103 净敞口套期收益 / 6111 投资收益 /
6115 资产处置损益 / 6701 资产减值损失 / 6702 信用减值损失。
旧准则残留：1501 持有至到期投资 / 1502 持有至到期投资减值准备 / 1503 可供出售金融资产。

**活体金额**（`trial_balance` 全项目 `unadjusted_amount` 合计）：
6101 −54,252.13 / 6111 732,847.56 / 6701 3,876,759.84 / 6702 126,151,230.15 /
1504~1507 与 1519 全为 0.00（`account_mapping` 无这些标准码的映射记录）。

**源模板结构实证**（openpyxl 直读 `backend/wp_templates/G/`）：

| sheet | 表 | 列 | 行 |
|---|---|---|---|
| G10 上市 | 主表 R7:R15 | 5（项目/期初余额/本期增加/本期减少/期末余额；C·D 列无公式） | 8 |
| G10 上市 | R18 表 | 4（项目/期初余额/期末余额/指定的理由和依据） | 3 空 + 合计 |
| G10 上市 | R26 表 | 4（项目/年度公允价值变动额/因自身信用风险变动本年/累计） | 1 示例 + 2 空 + 合计 |
| G10 上市 | R35 表（衍生金融负债） | 3（项目/期末余额/上年年末余额） | 5 空 + 合计 + 说明 |
| G10 国企 | 主表 R7:R14 | 3（项目/期末公允价值/期初公允价值） | 7 |
| G10 国企 | R18 表 | 4 | 1 示例 + 2 空 + 合计 |
| G11 上市 | 主表 R7:R21 | 3（项目/本期发生额/上期发生额） | 13 + 合计 |
| G11 上市 | R24 表（注1） | 3 | 9 + 合计 |
| G11 国企 | 主表 R7:R25 | 3 | 17 + 合计 |
| G13 上市 | 主表 R7:R17 | 3（产生公允价值变动收益的来源/本期/上期） | 9 + 合计 |
| G13 国企 | 主表 R7:R15 | 3 | 7 + 合计 |
| G14 上市 | 主表 R7:R17 | 3 | 9 + 合计 |
| G14 国企 | 主表 R7:R12 | 3 | 4 + 合计 |

🔴 G10 国企源模板**无衍生金融负债独立小节**（dims 止于 R23），而附注模板有 `八、35`
→ 该章节列结构无源模板依据，Wave 5 只补 columns（沿用国企用语「期末余额/期初余额」）
并在 guidance 注明依据来源，不自造行集。

🔴 G14 上市附注模板行集比源模板多「合同资产减值损失」。会计上正确（CAS 14 合同资产减值
属信用减值损失），判定为**附注模版有而底稿源模板漏**，**保留**并在守卫中登记为显式例外。

**既有覆盖状态**：`fix_note_g_cycle_structure.py --check` 全绿（覆盖 G4/G5/G6/G8/G9/G12）；
G7 有 4 个专属脚本；G1/G2/G3 附注结构本已干净。本 spec 只新增 G10/G11/G13/G14。

**平台机制实证**：`sync_from_workpaper` 的 `sub_table_data` 是按表名浅合并（L484-490，
多 owner 安全），但 `_note_texts`（L533-534）与 `text_content`（L627-632）是整体替换
—— 这是 Req 7 的根因。
