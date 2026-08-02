# Requirements Document

## Introduction

H 类循环（H1 固定资产 / H2 在建工程 / H3 投资性房地产 / H4 工程物资 / H5 油气资产 / H6 固定资产清理 / H7 生产性生物资产 / H8 使用权资产 / H9 租赁负债 / H10 资产处置损益）的**披露表与附注模板结构**已由 7 个归档 spec 收口（15 个主章节列元数据与 guidance 100% 覆盖）。本 spec 收口尚未处理的一侧：**四表库入库后的科目映射 → 底稿取数 → 审定表预填 → 公式预设**，并修掉披露/附注侧遗留的双真源与动态区写死。

### 🔴 与并发 spec 的范围划分（开工前 grep 消费方发现）

并发 spec `g-cycle-extraction-mapping-and-disclosure-alignment` 已建成通用共享件 `four_table/semantic_account_resolver.py`（**按科目名逐项目定位** + 多级回退 + `report_config` 错码冲突检测 + 旧准则科目提示），并已用它改造完 **H3**（`h3_account_scope.py` + `_h3_investment_property.py` + `test_h3_account_scope.py`）—— H3 是它解决 G4 `1504 债权投资` 撞码时的溢出产物。

故本 spec：
- **复用**该共享件，不另造 H 类专用件（原计划的 `h_asset_layers.py` 已撤销，理由见 design §Overview 的对比表）
- **后端范围 = H1/H2/H4/H5/H6/H7/H8/H9/H10 共 9 个循环**，H3 后端完全不碰
- 前端 `h{n}AccountScope.ts` 含 H3（前端 scope 归本 spec，以便 10 个循环形态一致、守卫可参数化）
- 不修改 `semantic_account_resolver.py` / `report_line_accounts.py` / `leaf_aggregation.py` / `h3_account_scope.py` / `_h3_investment_property.py`

### 调查已坐实的事实（DB 只读 + openpyxl + 源码，全部有据）

**报表映射真源（`report_config`，四准则实证）**

| 循环 | 报表行 | soe_standalone 公式 | 备抵独立行 |
|---|---|---|---|
| H1 固定资产 | `BS-028` | `TB('1601')-TB('1602')+TB('1606')` | `IMP-011`=`TB('1603')` |
| H2 在建工程 | `BS-029` | `TB('1604')` | `IMP-012` formula=NULL |
| H3 投资性房地产 | `BS-027` | `TB('1521')-TB('1525')`（listed 另减 `1526`） | `IMP-010`=`TB('1527')` |
| H4 工程物资 | 无独立行（含于 `BS-029`） | — | — |
| H5 油气资产 | 无 BS 行（`CFSS-005` 提折耗） | 兜底 `1631`/`1632` | `IMP-014` formula=NULL |
| H6 固定资产清理 | 含于 `BS-028`（`+TB('1606')`） | — | — |
| H7 生产性生物资产 | `BS-030` | `TB('1621')` | `IMP-013` formula=NULL |
| H8 使用权资产 | `BS-031` | `TB('1641')-TB('1642')-TB('1643')` | `IMP-015`=`TB('1643')` |
| H9 租赁负债 | `BS-063` | `TB('2601')-TB('2602')` | — |
| H10 资产处置损益 | `IS-018` | `TB('6115','本期发生额')` | — |

**🔴 三个「取错整个科目族」级 P0（`account_chart` + 活体 `tb_balance` 双证）**

1. `_h3_investment_property._H3_ACCOUNT_PREFIXES = {"1503","1504"}` —— `1503` 实为**可供出售金融资产**、`1504` 实为**债权投资**（G4 循环的科目）。活体 active 数据集下 `1503`/`1504` **零行** → H3「四表入库后刷新取数」**恒空**；真实投资性房地产 `1521` 有 21 行 / 7 项目 / 期末合计 59,823,786.84。
2. `_h8_right_of_use_assets._H8_ACCOUNT_PREFIXES = {"1901","190101"}` —— `1901` 实为**待处理财产损溢**（且平台 `BS-014 其他流动资产` 亦引用 `1901`，与 K2 撞科目）。`190101` 是无点号平铺形态且非真实科目。
3. `_h9_lease_liabilities._H9_ACCOUNT_PREFIXES = {"2205"}` —— `2205` 实为**合同负债**（D7 循环的科目，`BS-047`=`TB('2205')`）。租赁负债真值 `2601`，未确认融资费用 `2602`。

上述 3 处同时污染 `build_d_adjudication_prefill(account_prefix=...)`（H8 传 `1901`、H9 传 `2205`）。

**🔴 公式预设整片贴错标签（`prefill_formula_mapping.json`）**

| 块 | 现状 | 判定 |
|---|---|---|
| H3 审定表 | `wp_name='使用权资产审定表'` + `TB_SUM('1641~1643')` | 整块是 H8 的内容 |
| H3 明细表（成本模式） | `1522`/`1523` | **两码在标准科目表中不存在** |
| H5 审定表 | `1611` | `1611` = 融资租赁资产 |
| H8 审定表 | `1631` | `1631` = 油气资产 |
| H8 明细表 | `1621`/`1622` | 生产性生物资产（H7 的科目） |
| H9 审定表 / 明细 / 未确认融资费用 | `2802`/`2803` | **两码在标准科目表中不存在** |
| H2 明细表 | `AUX('1604','项目名称','B510003',…)` ×4 | 硬编码某项目的具体工程编码 |
| H1 分析程序 | `TB_SUM('1601~1604','期末余额')` | 病态区间，把在建工程/工程物资混进固定资产 |
| H10 审定表 / 明细 | `TB('6115','期初余额')` / `TB('6115','期末余额')` | 损益类无期初/期末余额口径 |

**取数实现层缺陷**

- H2~H10 **9 个循环全部硬编码科目前缀**，不走 `app/services/four_table/` 共享件；仅 H1 直调 `resolve_report_line_account_codes`（未走共享件）。
- `_h3` 的 `_is_leaf` 用 `c.startswith(code)` **缺点号边界**（`1521` 会误命中 `15210`）；`_h3` 的 `trial_balance` 查询走裸 SQL 绕过 `get_active_filter`（数据集版本泄漏）。
- `_h8` 的 `is_contra = len(code) > 4 and code.startswith("1901")` —— 把**任何子科目**都当累计折旧。
- 共享件 `split_gross_provision` 的 `_PROVISION_NAME_HINTS` 只有「坏账准备/减值准备/信用减值」，**不含「累计折旧/累计摊销/累计折耗」** → H 类的折旧类备抵会被归入原值。且 `1525`/`1526` 在 `account_chart` 里 `direction='debit'`（异常标注）→ 方向判定不可靠。
- H 类是**三层结构**（原值 / 累计折旧·摊销·折耗 / 减值准备），共享件 `ReportLineAccounts` 只有 `gross`/`provision` 两槽。
- `tb_source_codes` 仅 H1 输出，且前端 grep **0 消费** = dead output。
- H2/H3/H4 无 `adjudication_prefill`（H5~H10 有但喂错科目）。

**披露/附注侧遗留（结构本身已对齐，问题在双真源与写死）**

- `fix_note_h2_construction_structure.py:195` 目标 `report_row_code="BS-015"`，模板现值 `BS-029`（正确）→ 任何人跑 `--apply` 即回退；`--check` 不比对 rows 内容故 0 欠账掩盖。
- `fix_note_h8_right_of_use_structure.py` 目标 guidance 含 `**`（576 字），模板现值 572 字已剥离 → 与平台级 `fix_note_bold_markers.py` 互相打架，两者 `--check` 各自都绿。
- `fix_h1_note_section_alignment.py` **无 argparse / 无 check / 无 dry-run**，`main()` 无条件写两个 JSON，且与 `fix_note_h1_fixed_assets_structure.py` 对同一批表各持一份 guidance 真源。
- `h5NoteSectionMap.spec.ts` **7 例全红**（陈旧 API：传 `summaryRows`，现签名要 `layerTotals`），且 `buildH5SoeRows(totals)` 无空值保护；CI job `note-h5-structure` 无前端步骤。
- H9 两版动态区写死：上市源模板 `A8:A10` 是三行**空白自由列示区**，前端 `H9_LISTED_DEFAULT_ROWS` 固定 4 行仅可改名；国企 `A11` 是 `……` 可续扣减行，前端 `H9_SOE_DEFAULT_ROWS` 硬编码 3 行 → 模板 seed 的 `……` 行永远收不到数据。
- 平台守卫 `disclosureAutoSyncCoverage.spec.ts` 的 `/<template>([\s\S]*?)<\/template>/` 非贪婪正则在嵌套 `<template #slot>` 处截断 → H 类 22 个宿主使用点中 **12 个未被检查**（当前全部合规，是**未来**的盲区）。

**期限分段口径澄清**

逐格扫 H1~H10 共 20 个披露 sheet（判据 `期限/到期/账龄/年以内/年以上/个月/折现/剩余/1至2/2至3/分段/区间`）：**H 类没有任何按期限分段的披露结构**，仅 H9 有单行重分类（上市 `A12`「减：一年内到期的租赁负债」、国企 `A10`「重分类至一年内到期的非流动负债」）。故平台账龄枚举模块 `disclosureAgingLabels.ts` / `useAgingConfig` 在 H 类**不适用**，前端 0 命中是正确状态，本 spec 只对该结论加反向守卫防日后误接。

**测试基线（HEAD 预存在，`git status` 对相关文件全干净）**

- 后端 `-k "h1 or … or h10"`：65 failed / 1247 passed / 8 skipped / 4 errors。其中 49 例在 `test_h_cycle_export_import_verification.py`（锁「H 循环还没专属组件」的旧状态），4 errors 全在 playwright 收集期。
- 前端 `vitest run h1 … h10`：2070 passed / 8 failed（`h5NoteSectionMap.spec.ts` 7 + `useH4DualMode.spec.ts` 1）。

## Requirements

### Requirement 1: 科目定位由报表映射规则驱动，禁止硬编码前缀

**User Story:** 作为审计助理，我希望四表库入库后各 H 类底稿能自动取到**正确科目**的数据，而不是取到别的循环的科目或恒空。

#### Acceptance Criteria

1.1 H1~H10 各循环的 render 策略 SHALL 通过报表行编码（`BS-027`/`BS-028`/`BS-029`/`BS-030`/`BS-031`/`BS-063`/`IS-018`）解析科目码，不得在取数路径上出现科目码字面量作为唯一真源。
1.2 解析 SHALL 复用 `app/services/four_table/` 共享件（`resolve_report_line_accounts` + `select_leaves`/`aggregate_leaves`），不得在 H 类内重写科目定位或叶子聚合逻辑。
1.3 解析 SHALL 传入该项目的 `applicable_standards`，因为 `BS-027` 在 `listed_standalone` 下多减 `TB('1526')`、`BS-028` 在 `soe_standalone` 下多加 `TB('1606')`。
1.4 `_h3_investment_property` 的 `1503`/`1504` SHALL 纠正为由 `BS-027` 解析（兜底 `1521`/`1525`/`1526`），且减值走 `IMP-010` 兜底 `1527`。
1.5 `_h8_right_of_use_assets` 的 `1901`/`190101` SHALL 纠正为由 `BS-031` 解析（兜底 `1641`/`1642`/`1643`），减值走 `IMP-015` 兜底 `1643`。
1.6 `_h9_lease_liabilities` 的 `2205` SHALL 纠正为由 `BS-063` 解析（兜底 `2601`/`2602`）。
1.7 `build_d_adjudication_prefill(account_prefix=...)` 的调用方（H5/H6/H7/H8/H9/H10）SHALL 改传解析结果，不得再传字面量。
1.8 任一解析环节失败（无 `report_config` 行 / 无 `account_chart` / 无 `account_mapping` / DB 异常）SHALL fail-open 回退到声明的兜底码并在 `resolved_from` 标注来源，不得阻断 render。

### Requirement 2: H 类三层资产结构（原值 / 累计折旧摊销折耗 / 减值准备）

**User Story:** 作为审计助理，我希望审定表的原值段、累计折旧段、减值准备段各自取到对应科目，不要把折旧混进原值。

#### Acceptance Criteria

2.1 系统 SHALL 提供 H 类专用共享件，把报表行公式解析出的科目码分派到 `gross` / `depreciation` / `impairment` 三层。
2.2 分层判定 SHALL 以**科目名称**为主（含「减值准备」→ impairment；含「累计折旧」「累计摊销」「累计折耗」→ depreciation），因为 `1525`/`1526` 在 `account_chart` 里方向标注为 `debit` 不可靠。
2.3 名称判定 SHALL 有明确优先级并加否决词校验，防止「投资性房地产减值准备」被「投资性房地产」误吞。
2.4 公式中带**负号**的科目码 SHALL 不得被归入 `gross`（负号即备抵语义）；名称与符号冲突时以名称为准并记录告警。
2.5 该共享件 SHALL 为**纯增量**：不得修改 `report_line_accounts.py` 的 `_PROVISION_NAME_HINTS` 或 `split_gross_provision` 的既有语义（D1/K1/K2/F1/G7 消费者须逐字零回归）。
2.6 备抵科目的聚合结果 SHALL 取绝对值输出（`tb_balance` 存在「无符号 + 方向列」与「已带符号」两种约定并存）。
2.7 备抵科目的「增加」SHALL 取 `credit_amount`、「减少」取 `debit_amount`（与原值侧相反）。

### Requirement 3: 叶子聚合与勾稽自检

**User Story:** 作为现场经理，我希望底稿取的数与试算平衡表能勾稽得上，差异能被系统自己发现并显示出来。

#### Acceptance Criteria

3.1 聚合 SHALL 只汇总**叶子**科目（无 `code + '.'` 前缀的兄弟行），不得取「最深层级」。
3.2 前缀匹配 SHALL 要求点号边界（`code == p` 或 `code.startswith(p + '.')`），`_h3` 现有的无边界 `startswith` 须删除。
3.3 所有 `tb_balance` / `trial_balance` 查询 SHALL 经 `get_active_filter`，`_h3` 的裸 SQL 须改造。
3.4 render SHALL 输出 `parent_check`（叶子和 vs 父科目行金额及其差额），供守卫与前端溯源自检。

### Requirement 4: 取数溯源可见（消灭 dead output）

**User Story:** 作为质量控制复核合伙人，我需要在底稿上直接看到「这个数取自哪个科目、依据哪条报表映射规则」，否则无法复核取数的正确性。

#### Acceptance Criteria

4.1 H1~H10 的 render SHALL 输出 `tb_source_codes`（含 `gross`/`depreciation`/`impairment` 的标准码与原始码、`resolved_from`、命中的报表公式原文、报表行编码）。
4.2 前端 SHALL 通过共用件 `shared/WpFourTableSourcePanel.vue` + `composables/shared/tbSourceCodes.ts` 消费它，H1 现有的 dead output 须接入。
4.3 溯源面板 SHALL 展示报表行编码与公式原文，使审计人员可追溯「这个数为什么是这个科目」。

### Requirement 5: 审定表未审数四表预填

**User Story:** 作为审计助理，我希望四表入库后点一下就能把未审数带进审定表，不用手工抄一遍，同时我已经填过的内容不会被覆盖。

#### Acceptance Criteria

5.1 H1~H10 的审定表 SHALL 支持「从四表库带入未审数」，数据来自解析后的科目叶子聚合。
5.2 预填 SHALL **宁缺勿造**：科目解析为空或该科目在活体数据集无数据时输出空，不得用 0 冒充已知值。
5.3 预填 SHALL 手工优先：已有持久化值不被覆盖；带入时若与现值不同须给出确认。
5.4 H10 属损益类，其取数 SHALL 用**本期发生额**口径（`trial_balance` 优先，兜底 `tb_balance.debit_amount`/`credit_amount` 按方向），不得用「Σ借−Σ贷」（含年末结转损益的全年账上结构性恒为 0）。

### Requirement 6: 前端科目单一真源

**User Story:** 作为平台维护者，我希望科目码只在一处声明，改一次全循环生效，且不会因为前端写死而把审定数回写到别的循环的科目上。

#### Acceptance Criteria

6.1 每个 H 循环 SHALL 有 `composables/h{n}AccountScope.ts` 作为科目单一真源（范式 `k2AccountScope.ts`/`g1AccountScope.ts`）。
6.2 运行态 SHALL 取 render 下发的 `tb_source_codes`，常量只作兜底与展示。
6.3 前端源码 SHALL 不出现 H 类科目码字面量作为请求参数、事件载荷或 TB 回写目标。
6.4 特别地，`writebackTB` SHALL 写解析后的科目码 —— 现状 H8 会往 `1901`（其他流动资产 / 待处理财产损溢）写审定数，H9 会往 `2205`（合同负债）写，均会污染 K2/D7 的口径。

### Requirement 7: 公式预设纠正

**User Story:** 作为审计助理，我在底稿当页的公式管理里看到的预设应该是本循环的科目和公式，而不是别的循环的内容或取不到数的死公式。

#### Acceptance Criteria

7.1 系统 SHALL 提供幂等脚本（`--dry-run`/`--check`/`--apply`）纠正 H 类公式预设，范式对齐 `fix_f2_prefill_presets.py`。
7.2 脚本 SHALL 纠正 Introduction 表列出的全部贴错标签块（H3/H5/H8/H9 的错科目、H3/H9 的不存在科目码、H2 的硬编码工程编码、H1 的病态区间、H10 的损益口径）。
7.3 预设中的科目码 SHALL 与该循环报表行引用的科目集一致；无法干净映射的条目须删除而非保留错值。
7.4 底稿间联动 SHALL 用 `WP()`：审定表可引明细表，**明细表禁引审定表**（防成环）。
7.5 每个循环的两个披露 sheet SHALL 在公式管理页有对应块（现状全部空白）。

### Requirement 8: 披露/附注侧双真源与打架修复

**User Story:** 作为平台维护者，我希望同一处附注结构只有一个真源，不会因为跑了另一个脚本就把已修正的内容回退。

#### Acceptance Criteria

8.1 `fix_note_h2_construction_structure.py` 的 `report_row_code` SHALL 由 `BS-015` 纠正为 `BS-029`，并加守卫钉死。
8.2 `fix_note_h8_right_of_use_structure.py` 的 guidance SHALL 剥离 `**`（guidance 一律纯文本），消除与平台级 `fix_note_bold_markers.py` 的互相翻转。
8.3 `fix_h1_note_section_alignment.py` SHALL 与 `fix_note_h1_fixed_assets_structure.py` 收敛为单一真源（保留走共享 kit 的那个，另一个删除或改为薄壳委托），不得两处各持一份 guidance。
8.4 `h5NoteSectionMap.spec.ts` 的 7 例 SHALL 改为现签名并转绿；`buildH5SoeRows` SHALL 对 `undefined` 入参有保护。
8.5 CI job `note-h5-structure` SHALL 补前端步骤（对齐 `note-h7-frontend`/`note-h8-frontend`）。

### Requirement 9: 动态插行区域

**User Story:** 作为审计助理，客户实际有几类租赁我就录几行，不该被界面写死的行数限制，也不该在附注里出现一堆空行。

#### Acceptance Criteria

9.1 H9 上市披露表的租赁类别区 SHALL 改为动态增删行（源模板 `A8:A10` 是空白自由列示区），行数由实际数据决定，`max(seed 行数, 1)`，不得写死 4 行。
9.2 H9 国企披露表 SHALL 支持在「重分类至一年内到期的非流动负债」之后续加扣减项（源模板 `A11` = `……`），并让模板 seed 的该行能收到数据。
9.3 新增行 SHALL 先 `ElMessageBox.prompt` 输入名称再创建，撞名须拒绝。
9.4 动态行的稳定 key SHALL 不使用 label（改名会丢数据 / 同名会撞键）。
9.5 H10 两版披露表源模板均写「不适用的项目删除」，SHALL 提供删行能力或在推送侧对全空行输出 `null` 并由附注侧折叠 —— 二者择一并写明依据。
9.6 删除行 SHALL 清理对应持久化键，且推送时把移除的表/行纳入 `_removed_table_keys` 求差集处理。

### Requirement 10: 期限分段口径澄清

**User Story:** 作为平台维护者，我需要把「H 类不适用账龄枚举」这个调查结论固化下来，避免下一个人又花时间去接一个源模板里不存在的分段表。

#### Acceptance Criteria

10.1 系统 SHALL 以守卫固化「H 类披露表无按期限分段结构」这一结论，防止日后误接账龄枚举模块。
10.2 该守卫 SHALL 用 openpyxl 直读源模板反向自检（判据词在 H 类 20 个披露 sheet 中的命中集必须等于已登记的白名单：H9 两处单行重分类 + H2 工程进度列）。
10.3 H9 的「一年内到期」SHALL 保持为**单行重分类**语义（小计 − 该行 = 合计），不得改造成多档到期分析（源模板无此表）。

### Requirement 11: 守卫与 CI

**User Story:** 作为平台维护者，我希望「科目码写错」这类缺陷以后能被 CI 直接拦住，而不是靠人逐个循环去核。

#### Acceptance Criteria

11.1 SHALL 新增后端守卫：H 类三层分派共享件单测（含反向自检：打乱名称判定优先级则「减值准备」被误吞）。
11.2 SHALL 新增平台级守卫 `test_h_cycle_account_codes.py`：① 取数路径与预设中的每个科目码 ∈ 标准科目表 ② 每个码 ∈ 该循环报表行引用的科目集（第 ② 条才能抓住「码是真科目但属别的循环」）。
11.3 SHALL 新增公式预设守卫（科目码正确性 + 防成环 + 语法合法性 + 损益口径）。
11.4 SHALL 新增前端守卫：每个循环的 `h{n}AccountScope.spec.ts`（含「源码不得出现旧错误科目码」的反向自检）+ 跨循环接线守卫。
11.5 SHALL 修复 `disclosureAutoSyncCoverage.spec.ts` 的 `<template>` 正则截断盲区（12/22 个 H 使用点未被检查），并加反向自检。
11.6 读源码型守卫 SHALL 先 `stripComments()` 并加反向自检（防守卫注释里的反例被数成真实调用，且防断言空转）。
11.7 SHALL 新增 CI job 覆盖上述守卫。

### Requirement 12: 实测验证

**User Story:** 作为业务合伙人，我要求改动经过真实数据验证，任务标记不能假绿。

#### Acceptance Criteria

12.1 SHALL 对真实 DB 直跑各循环 render，核对 `tb_source_codes.resolved_from`、三层科目码、`parent_check.diff`。
12.2 SHALL 验证「叶子和 == 父科目行金额」在有活体数据的循环（H1 `1601`/`1602`、H2 `1604`、H3 `1521`/`1525`/`1526`、H6 `1606`、H10 `6115`）上成立。
12.3 对无活体数据的循环（H5 `1631`、H7 `1621`、H8 `1641`、H9 `2601`）SHALL 明确记录「科目解析正确但该资产类别在在册项目中不存在」，并说明验证手段限于 render 直跑 + 单测，不得把「空」当成通过。
12.4 SHALL 用浏览器实测披露表改动（H9 动态行增删改名 + 撞名拒绝 + 推送到附注 + `_removed_table_keys` 生效），并在测后把测试数据复原。
12.5 SHALL 记录改动前后的测试基线对比，区分「本次引入的失败」与「HEAD 预存在的 65 后端 / 8 前端失败」。

## Glossary

| 术语 | 含义 |
|---|---|
| 四表库 | `tb_balance`（余额表，客户原始码）/ `trial_balance`（试算平衡表，标准码）/ `tb_ledger`（序时账）/ `tb_aux_balance`（辅助余额表） |
| 原始码 | 客户科目表里的编码，点号分级（`1521.01`） |
| 标准码 | 平台标准科目编码，横杠分级（`1231-03`） |
| 报表行 | `report_config` 表的一行，含 `row_code`（`BS-027`）与按准则的 `formula` |
| 三层结构 | H 类资产的 原值 / 累计折旧·摊销·折耗 / 减值准备 三段 |
| 备抵科目 | 与资产原值方向相反的抵减科目（累计折旧、减值准备） |
| 叶子科目 | 不存在以 `本码 + '.'` 开头的同数据集兄弟行的最明细科目 |
| `parent_check` | 「叶子和 vs 父科目行金额」的自检结果 |
| `tb_source_codes` | render 下发的取数溯源信息（科目码 + 报表行 + 公式原文 + 来源标注） |
| fail-open | 解析失败时回退兜底值并标注来源，不阻断渲染 |
| 贴错标签 | 公式预设块的 `wp_name`/科目码属于另一个循环 |
| dead output | 后端已输出但前端零消费的字段 |
| `_removed_table_keys` | 同步载荷里声明「本次应从附注删除的子表键」 |
