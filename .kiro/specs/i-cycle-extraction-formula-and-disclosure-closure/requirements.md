# Requirements Document

## Introduction

I 循环（I1 无形资产 / I2 开发支出 / I3 商誉 / I4 长期待摊费用 / I5 其他非流动资产 / I6 研发费用）的
「四表入库 → 底稿取数 → 披露表 → 附注模块」全链收口。

本 spec 基于 2026-08-09 的只读实证（6 个 `_wip_*` 探针 + 真实库 8 项目直跑 + openpyxl 逐格精读
6 份源 workbook），**不重建既有骨架** —— `four_table/i_cycle_{accounts,extraction,prefill}.py`
与 6 份 `iXNoteSectionMap.ts` 均已在位且机制正确（真实库 `parent_check` 全部 `diff=0.0`）。

### 科目映射真源（`report_config` DB 实证，四准则一致）

| 循环 | 报表行 | 公式 | 备抵行 | 兜底标准码 |
|---|---|---|---|---|
| I1 无形资产 | `BS-032` | `TB('1701')-TB('1702')` | `IMP-016`=`TB('1703')`（仅 soe_standalone 有公式） | 1701 / 1702 / 1703 |
| I2 开发支出 | `BS-033` | `TB('1704')` | — | 1704 |
| I3 商誉 | `BS-034` | `TB('1711')` | `IMP-017`（四准则 formula 全 NULL） | 1711 / 无 |
| I4 长期待摊费用 | `BS-035` | `TB('1801')` | — | 1801 |
| I5 其他非流动资产 | `BS-037` | `TB('1911')` | — | **空**（`1911` 全库两张科目表都不存在） |
| I6 研发费用 | `IS-006` | `TB('6604','本期发生额')` | — | **不给兜底**（`6604` 在 1 个项目 client 侧叫「勘探费用」） |

### 已实证成立、本 spec 不动的部分

- 取数三层链路（`report_config` → `account_mapping` 反解 → `tb_balance` 叶子聚合）机制正确
- 真实库 8 项目 × 6 循环 `parent_check` 全部 `diff=0.0`（父子双算已解决）
- `HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 已为 `True`（灰度已点亮）
- I2/I3/I5/I6 在现有 8 个项目取数恒空是**数据事实**（客户无该科目），非接线缺陷
- 6 份 `X_DISCLOSURE_SHEET_NAME` 与源模板 tab 名**逐字一致**（I1 带「信息」二字、I2~I6 不带，
  是源模板事实不得统一）
- 附注落点 listed `五、26/27/28/29/31/66`、soe `八、27/28/29/30/32/67` 全部存在

## Glossary

| 术语 | 本 spec 内的含义 |
|---|---|
| 段（segment） | `ISegmentSpec` 声明的一个取数段。I1 有三段（`cost` 原值 / `amortization` 累计摊销 / `impairment` 减值准备），I2/I4/I5 单段 `cost`，I3 两段（`cost`/`impairment`），I6 单段 `expense`（损益） |
| 行名闸 | `i_cycle_accounts.row_name_matches()` —— 拿 `report_config.row_name` 与本循环期望语义比对，不符即丢弃该公式。它是当前 6 个错 row_code 没造成错数的唯一原因 |
| 三态 | 「本项目无此科目」/「余额为 0」/「取数失败」三者必须可区分。判据 = `found` + 该段前缀在 `tb_balance` 的命中行数，不是看金额是否为 0 |
| 动态插行区 | 源模板 `……`/`…` 标记的可扩行位。作**行**时是真实可扩位必须保留；作**列头**时永远收不到数据必须展开或丢弃 |
| A/B 对照 | 改动前（A）与改动后（B）对同一真实项目跑同一函数，逐字段比对码集/金额/勾稽/prefill。本 spec 已完成一轮，实质差异 0 |
| 实质差异 | 码集（`standard`/`original`）、`tb_values`、`parent_check`、`adjudication_prefill` 四者任一不同。`resolved_from` 变化**不算**实质差异（它是溯源标签） |

## Glossary

| 术语 | 本 spec 内的含义 |
|---|---|
| **段（segment）** | I 类取数的最小单位。`cost` 原值 / `amortization` 累计摊销 / `impairment` 减值准备 / `expense` 损益发生额。I1 有三段、I3 有两段、I2/I4/I5 单段、I6 单段（损益）。由 `ISegmentSpec` 声明，每段独立认领科目、独立兜底、独立方向。 |
| **行名校验闸** | `i_cycle_accounts.row_name_matches()`。把 `report_config` 解析出的公式与本循环期望语义（`I_CYCLE_EXPECTED_NAMES`）比对，行名不符即丢弃该公式退回兜底码。它是现状 row_code 全错却没取到错数的唯一原因。 |
| **三态** | 「本项目无此科目」（`found=False`，码集为空）/「余额为 0」（有科目、金额为 0）/「未知」（取数失败）。三者必须可区分，禁把前两者都渲染成 `0.00`。 |
| **`resolved_from`** | 科目定位来源标记。`report_config` = 经报表行公式解析；`account_chart_client`/`account_chart_standard` = 按科目名在项目科目表定位；`fallback` = 用调用方声明的兜底码；`none` = 本项目无此科目。溯源面板据它显示中文标签。 |
| **动态插行区** | 源模板中以 `……` / `…` 标记的可扩行位。**同一符号有两种语义**：作**列头**时是永远收不到数据的占位（须展开为实际类别）；作**行**时是审计师可增行的真实位置（须保留并做成前端增行入口）。 |
| **cols=0** | 附注模板 `tables[].columns` 为空数组。后果是投影器退回 `_infer_groups_from_headers` 前缀推断，可能凭空造出父表头；或降级成 `_needs_columns` 只显示行名。 |
| **段落泄漏成表名** | md 重建脚本把附注 docx 的说明段落当成表名写进 `tables[].name`。本 spec 实测两处（listed 五、31 与 soe 八、32 的 `[披露与合同取得成本有关的资产…例如：`）。表名是 `sub_table_data` 的键，泄漏名会让底稿推送产出孤儿子表。 |

## Requirements

### Requirement 1: row_code 双真源收敛

**User Story:** 作为审计助理，我希望底稿取数的科目来源能如实显示「按报表规则映射」而不是「兜底科目」，
这样当客户科目表用了非标准编码时取数不会静默落空，我也能追溯这个数是怎么来的。

I 类报表行编码目前有两套并存声明，且被 6 个 render 消费的那一套 **6/6 全部指向错误报表行**。

#### Acceptance Criteria

1. `i_cycle_accounts.I_CYCLE_ROW_CODES` 的取值必须与 `report_config` 实证一致：
   I1=`BS-032` / I2=`BS-033` / I3=`BS-034` / I4=`BS-035` / I5=`BS-037` / I6=`IS-006`
   （🔴 改动前实测 **12 个取值里 11 个错**，仅 `I6.listed` 正确；listed 侧是
   `BS-033/035/037/038/040` = **整体错位一个循环**（`I1.listed=BS-033` 恰是 I2 的正确码、
   `I2.listed=BS-035` 恰是 I4 的正确码、`I4.listed=BS-038` 是「非流动资产合计」派生行、
   `I5.listed=BS-040` 是「流动负债：」节标题），soe 侧是负债段 `BS-045/046/047/048/050`
   与 `IS-024` 四、净利润）
2. listed 与 soe 两准则取值必须**相同**（实证四准则同码同名，无跨准则差异）
3. `four_table/i_cycle_specs.py` 当前**零 render 消费方**，必须收敛：删除该文件或改为从
   `i_cycle_accounts` 单向 re-export，不得两处各写一份 row_code。
   🔴 该文件的 row_code 六个全对（`BS-032/033/034/035/037`+`IS-006`）且逐条带 DB 实证注释
   —— **它是判据来源不是待删的垃圾**；但其 docstring 顶部那段映射表**自身有 4 处错**
   （写 `I2 BS-033=TB('1711')` 实为商誉、`I3 BS-034=TB('1721')` 而 1721 非商誉码、
   `I5 BS-039` 与正文 `row_code="BS-037"` 自相矛盾、`I1 备抵 IMP-011` 实为 `IMP-016`）
   ⇒ 迁移时只搬**正文常量**，docstring 按 `report_config` 重写，不得整段照搬
4. 改动后 8 个真实项目 × 6 循环的 `standard` / `original` 码集、`tb_values`、
   `parent_check`、`adjudication_prefill` 必须与改动前**逐字节相同**
5. 改动后 `resolved_from` 由 `fallback` 转为 `report_config`（34 处），溯源面板显示
   「报表规则映射」而非「兜底科目」
6. 行名校验闸（`row_name_matches`）必须保留，作为防回退护栏
7. 守卫必须钉死「每个 I 循环的 row_code 在 `report_config` 中的 `row_name` 命中本循环期望语义」，
   且该守卫在改动前必须打红（12 个取值里 11 个失败）
8. `backend/tests/four_table/test_i_cycle_accounts.py::TestResolveRowCode` 的 12 个参数化
   用例当前逐条断言**错值**（连 `test_empty_standards_returns_listed` 也断言 `BS-033`），
   必须诚实改写为正确值 —— 这是「守卫在保护错的那一侧」的实例，不得为了让它继续通过而回退真源

### Requirement 2: I5 兜底码缺失的三态如实表达

**User Story:** 作为审计助理，我希望「本项目没有这个科目」和「这个科目余额是 0」在界面上能分清，
这样我不会把「平台取不到数」误当成「客户确实没有余额」而漏做程序。

`BS-037 其他非流动资产 = TB('1911')`，而 `1911` 在 `account_chart` 两张表全库都不存在，
「其他非流动资产」这个科目名亦零命中 ⇒ I5 六个项目全部 `std=[] orig=[]`。

#### Acceptance Criteria

1. I5 的 `cost` 段兜底码保持**空 tuple**（宁缺勿造，禁按 CAS 猜码）
2. `tb_source_codes` 必须能区分「本项目无此科目」与「余额为 0」两态
3. 前端 I5 审定表与披露 Tab 在无科目时显示「本项目无标准科目映射，需手工编制」，
   不得显示 `0.00`
4. 守卫必须钉死「I5 兜底码为空」+ 反向自检「若将来 `1911` 或同名科目出现于某项目
   `account_chart`，解析应命中」

### Requirement 3: 公式预设两处真错修正

**User Story:** 作为审计助理，我希望公式管理页里 I 类的预设公式指向的 sheet 和科目都是真实存在的，
这样我按公式取的数就是这个科目的数，不会把管理费用当成研发费用。


#### Acceptance Criteria

1. I1 预设块 `sheet='审定表I1-1'` 必须改为源模板真实 tab 名 **`审定表I1`**（无 `-1`；
   I1 是六循环唯一例外，I2~I6 均为 `审定表IX-1`）
2. 同块内 `PREV('I1','审定表I1',…)` 的 sheet 实参已是正确值，改块名时不得连带改错
3. I2 明细表块的 `'研发费用_期末' <- TB('6602','期末余额')` 必须改为 `TB('6604',…)`
   （`6602` 是管理费用，归 K9）
4. 修正后同块 `account_codes` 必须与公式引用的科目码自洽（`['1704','6604']`）
5. 幂等脚本 `--check` 必须归零，二次 `--apply` 后 JSON md5 逐字节不变
6. 守卫必须钉死「I 类每个预设块的 `sheet` 名存在于对应源 workbook 的真实 tab 名集合」

### Requirement 4: 披露 sheet 零预设补齐

**User Story:** 作为审计助理，我希望在披露表页面也能看到公式预设（哪一格从哪来），
而不是打开公式管理页发现披露 sheet 一片空白、无法追溯披露数字的来源。


12 张 I 类披露 sheet 当前零公式预设。

#### Acceptance Criteria

1. 六循环各两张披露 sheet 必须显式登记预设块，或在幂等脚本中**显式登记为无预设**并写明理由
2. 有四表可取数的披露格（I1 三段期初/期末、I3 商誉原值与减值、I4 期初/本期摊销/期末）
   必须给出 `TB()` 公式；取数不可推导者写 `PLACEHOLDER` + description 写明真源
3. 禁止给动态类别行/项目行写死具体客户科目码（如 `AUX('1701','类别','xxx')`）
4. 明细表块禁引用本循环审定表（防成环）；审定表块可引用明细表

### Requirement 5: 附注模板列元数据补齐

**User Story:** 作为现场经理，我希望附注里的 I 类表格有正确的列头与编制提示，
而不是因为 `columns=0` 导致投影降级成「只显示行名」、或者表名是一段泄漏的段落文本。


4 张表 `columns=0` + 2 处段落文本泄漏成表名。

#### Acceptance Criteria

1. listed `五、26` 的 `无形资产情况`(38 行) 与 `确认为无形资产的数据资源`(27 行) 必须补 `columns`
2. soe `八、27` 的 `确认为无形资产的数据资源` 必须补 `columns`
3. listed `五、28` 的 `商誉减值测试关键假设` 必须补 `columns`
4. listed `五、31` / soe `八、32` 表名为段落文本泄漏
   （`[披露与合同取得成本有关的资产相关的信息…例如：`）者必须正名或移入 `text_sections`
5. 列定义真源 = 各循环源模板披露 sheet（openpyxl 直读），单级表必须显式标 `flat`，
   两级表必须声明 `group`
6. 单级表的 `flat` 必须在**模板 seed 与同步载荷两处都加**（seed 路径与推送路径都要正确）
7. 幂等脚本 `--check` 归零；守卫做「源 xlsx ↔ 模板 headers ↔ 同步 columns」三向比对

### Requirement 6: I1 上市披露主表列结构核验

**User Story:** 作为审计助理，我希望 I1 上市披露表的无形资产类别列与源模板一致，
类别可按本项目实际情况增删改名，而不是被写死成模板示例的那几类。


源模板 I1 上市披露主表为 13 列（10 个类别 + 数据资源 + 其他 + 合计），模板侧 `hdr=6`。

#### Acceptance Criteria

1. 必须逐列比对源模板 `附注披露信息（上市公司）!B10:M10` 与模板 `headers`，判定是否压扁
2. 若已压扁必须还原为源模板列集；若模板本就是另一种正确形态（如按类别动态列）必须留证说明
3. I1 上市披露主表的类别列真源 = 源模板 `底稿目录!A9:A19`（12 类）+ `A20` 的 `……` 可扩位，
   不得写死类别清单
4. 类别列 key 必须是稳定 key（`{slot}_{seq}`），**不得用中文 label 作 key**

### Requirement 7: 动态插行区识别与推送

**User Story:** 作为审计助理，我希望源模板留的可扩行位在底稿上真的能增行，且增的行能推到附注，这样客户实际科目类别多于模板预置时我不必手工改附注。

源模板动态标记实证：I1 上市 3 处 + I1 国企 4 处 + I2 上市 1 处；I3/I4/I5/I6 各 0 处。

#### Acceptance Criteria

1. I1 国企披露表四层（原价 / 累计摊销 / 减值准备 / 账面价值）末尾各一个 `……`，
   必须实现为真实可扩类别行，不得作为空数据行推送
2. I1 上市披露表三处 `……`（账面原值增加段 / 累计摊销增加段 / 减值准备增加段）同上
3. I2 上市「研发支出」表的 `……`（按费用性质）必须可扩
4. 骨架行数禁写死（禁 `blankRows(p,3|5|10)`），改 `max(seed 行数, 1)`
5. 动态行新增需命名者必须先 `ElMessageBox.prompt` 输入名称再建行
6. 动态行删除后必须走 `_removed_table_keys` 清理附注孤儿表；稳定 key 不得复用已删序号

### Requirement 8: 披露表 → 附注推送链路验证

**User Story:** 作为审计助理，我希望在披露表点「同步到附注」后附注真的有数据，而不是显示已同步但附注仍是空骨架。

#### Acceptance Criteria

1. 六循环 12 个披露 Tab 必须都已接 `useDisclosureAutoSync`（监听实际数据，非提示横幅）
2. 宿主必须向披露 Tab 传 `:project-id`（漏传即同步永久静默失败）
3. 推送载荷的子表名必须与附注模板 `tables[].name` 逐字一致
4. 推送载荷的 `columns` 必须与模板 `columns` 同构（列数、`flat`/`group` 表态一致）
5. `_note_texts` 必须带中文 `title`，空文本必须过滤
6. 推送后附注 `last_sync_at` 必须前移，`sub_table_data` 表数与推送表数一致

### Requirement 9: 前端消费与溯源面板

**User Story:** 作为质量控制复核合伙人，我希望在底稿上看到每个金额取自哪个科目、经哪条报表规则映射，这样我能独立追溯而不必去问编制人。

#### Acceptance Criteria

1. 六个审定表 Tab 必须挂 `WpFourTableSourcePanel`（或 `HiFourTableSourcePanel`）
2. 面板必须显示 `resolved_from` 中文标签、`parent_check` 三口径、`chart_conflict` 告警
3. 六个审定表必须有「从四表库带入未审数」按钮，走 `adjudicationPrefillPlan` 共享件
   （手工优先 / 幂等 / 「无此科目≠为 0」）
4. 宿主 sheet 分发链必须用 `<template v-else-if>` 包住「面板 + sheet 内容」，
   不得用裸 `v-if` 插进链中间（会让后续 `v-else-if` 全成死分支）
5. 金额列必须走 `WpAmountInput`（千分符），比率/年限/月份列不得套用

### Requirement 10: 源模板缺陷登记（按意图实现不照抄）

**User Story:** 作为业务合伙人，我希望平台按源模板的**意图**实现而不是照抄它的笔误，并且把每处偏离逐条留证，这样下个会话不会把它"改回去"。

#### Acceptance Criteria

1. I1 审定表 tab 名 `审定表I1`（缺 `-1`）必须如实登记，定位用 tab 名、展示用底稿目录索引号
2. I2 上市披露表 `A35:D39` 的 `=#REF!` 坏公式（15 格）必须登记，按意图实现（资本化情况续表）
3. I1 上市披露表 `D20:L20` 的 `IF(...="购置",...)` 应为「处置」（复制粘贴笔误）必须登记
4. I6 底稿目录第 7~14 项索引号指向 I2 底稿（`I2-4`~`I2-11`）是**有意跨 workbook 引用**
   （`E10` 有提示原文），不得当笔误修正
5. I5 底稿目录 `B4` 序号缺失（7 行内容只有 6 个序号）必须登记
6. I3 有 hidden sheet `市场平均收益率2017`，必须确认 `wp_code_overrides` 已 skip
7. 源模板缺陷一律「登记 + 守卫钉死」，不得反改源 xlsx

### Requirement 11: 守卫、CI 与验收

**User Story:** 作为 EQCR 技术复核人，我希望本次修好的每一处都有守卫钉死且经变异检验证明守卫真的有效，这样它不会在下一轮并发改动中被静默回退。

#### Acceptance Criteria

1. Wave 1 的守卫必须先对当前状态打红（row_code 6/6 红、预设 2 处红、列元数据 4 处红）
2. 守卫必须区分两类断言：类 A 独立口径判据（现在应全绿）、类 B 被测实现（现在应全红）
3. 必须做变异检验，每个新守卫至少 1 个有效变异并逐条 RED；变异脚本必须区分
   RED / GREEN / ANCHOR-MISS 三态，备份落 `.bak` 且提供 `--restore`
4. 必须新增 CI job，引用的每个文件路径必须存在
5. 零回归判据 = 「施加改动前 vs 施加改动后」前后对照（禁 `git stash`、禁 HEAD-swap
   —— 本 spec 改动文件混着并发会话未提交成果）
6. 必须做真实库验收（8 项目 × 6 循环）+ 浏览器实测（录数据 → 看目标区域出数 →
   postgres 查落库 → 数据复原）
7. 会话结束前必须清掉本 spec 的 `_wip_*` 临时产物
