# Requirements — 可编辑金额控件迁移与列类型判据

## Introduction

平台铁律已定：可编辑金额输入**只能用** `components/workpaper/shared/WpAmountInput.vue`
（失焦千分符 / 聚焦原始值 / 粘贴带逗号可解析 / 非法输入回退不写 NaN），
因为 `el-input-number` 的 `:formatter` prop 在 Element Plus **2.13.6 根本不存在**
（双证：`node_modules/element-plus/es/components/input-number/**` 全文无该 prop；
浏览器实测 `:formatter` 下输 `1234567.5` 显示 `1234567.50` 无千分符）。

### 存量实测（2026-08-15 全量扫 `src/components/workpaper/**/*.vue`）

| 指标 | 实测 |
|---|---|
| `el-input-number` 总量 | **4260 处 / 798 文件** |
| 其中带 `:formatter`（确定空操作） | **80 处 / 13 文件** |
| `WpAmountInput` 已覆盖 | 682 处 / 118 文件 |
| 疑似「金额语义列用了 `el-input-number`」 | **1064 处**（粗判候选，非确认违规数） |

`:formatter` 空操作集中在：K1 披露两版（21 + 15）· E1 多个 Tab（11/9/5/5/4/3/2/1/1）·
`K1StageEclTable`（2）—— 与 memory 记载的「K1TabDisclosureListed·Soe / K1StageEclTable /
E1TabCashCount / E1TabCreditReport」一致，但**实测 80 处而非「40+」**。

### 🔴 本 spec 的立项直因：旧探针的判据盲区

I 循环 Task 18 做过一轮金额控件收口，当时结论是「I 循环 `el-input-number :formatter`
**命中 0 处**、`WpAmountInput` 已覆盖 18 文件 / 112 处」，据此判为合规。

但 2026-08-15 浏览器实测 I1-10 摊销测算表发现：

| 列 | 控件 | 输入 `1234567.5` 后显示 | 判定 |
|---|---|---|---|
| 原值（可编辑） | `el-input-number` + `:precision="2"` | `1234567.50` | ❌ 金额无千分符 |
| 残值（可编辑） | 同上 | `50000.00` | ❌ 同上 |
| 期初净值 F（只读派生） | 文本 + `fmtAmount` | `1,184,567.50` | ✓ |
| 月摊销额 K（只读派生） | 同上 | `9,871.40` | ✓ |

⇒ **同一行内并排显示两种格式**（`50000.00` 与 `9,871.40`），比单纯没千分符更容易误读。

源码核实：`I1TabAmortizationNoImpair.vue` / `I1TabAmortizationWithImpair.vue` 用
`el-input-number` + `:precision="2"`、**并无 `:formatter`**
⇒ 不在「`:formatter` 空操作」名单里，Task 18 的探针（按「找 `:formatter`」）**必然漏掉**。

这是**假绿第②源**（grep 式守卫只查字符串存在）的又一实例：
判据应是「金额语义列是否用了非 `WpAmountInput` 的控件」，而不是「有没有写 `:formatter`」。

### 🔴 第二个立项直因：反向边界现在是「碰巧成立」

同一次实测：「使用期限(年)」列输 `1000` 显示 `1000.00`、输 `10` 显示 `10.00`
—— **不带千分符，符合铁律**。但成因是 `el-input-number` 对**所有**列都不做千分符，
而非正确区分了列类型。

⇒ 一旦按铁律把金额列换成 `WpAmountInput`，若不同时**显式排除**年限/月数/比率列，
「使用期限 1000 年」会被渲染成 `1,000.00`。

现有反向边界断言（I 循环 Task 18 的 Property 30）验的是「非金额列未被误换成
`WpAmountInput`」—— 在**尚未迁移**的代码上它恒真，**没有区分能力**。
必须在迁移前把列类型判据建起来，否则迁移本身就是引入缺陷的过程。

---

## Requirements

### Requirement 1: 列类型单一真源

**User Story:** 作为迁移执行者，我需要一个权威的「这一列是不是金额」的判定依据，
而不是每个文件靠人眼判断。

#### Acceptance Criteria

1.1 WHEN 判定某列是否为金额列 THEN 必须依据一份声明式真源（列 label 模式 + 显式豁免清单），
    不得在各文件里各写一套关键词

1.2 WHEN 真源声明非金额语义 THEN 必须覆盖至少：比率 / 利率 / 汇率 / 占比 / 比例 / 年限 /
    期限 / 月份 / 月数 / 天数 / 笔数 / 数量 / 股数 / 份数 / 年度 / 折现率 / 增长率 /
    毛利率 / 税率

1.3 WHEN 某列 label 同时命中金额与非金额模式 THEN 判为**歧义**并进入人工裁决清单，
    不得由脚本静默二选一（实测存在 5 处此类 label）

1.4 WHEN 真源新增/修改条目 THEN 必须写明「源模板依据或实测证据」，禁止凭常识添加

1.5 WHEN 判定「只读展示金额」THEN 一律走 `displayPrefs.fmtAmount()`
    （setup 顶层 `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`），
    与可编辑列的迁移分开处理

### Requirement 2: 探针能力 —— 覆盖「无 formatter」的漏网形态

**User Story:** 作为守卫作者，我需要探针抓的是「金额列用了非 WpAmountInput 控件」，
而不是「有没有写 `:formatter`」。

#### Acceptance Criteria

2.1 WHEN 探针扫描 THEN 判据必须是「金额语义列 ∧ 控件 ≠ `WpAmountInput`」，
    **不得**以 `:formatter` 是否存在作为必要条件

2.2 WHEN 探针跑在 I1-10 / I1-11（`I1TabAmortizationNoImpair.vue` /
    `I1TabAmortizationWithImpair.vue`）上 THEN 必须报出「原值 / 残值 / 累计摊销期初 /
    账面累计摊销期末 / 账面本期摊销 / 账面月摊销额 / 减值准备」等金额列违规
    —— 这是探针能力的定向验收点（旧探针在此报 0）

2.3 WHEN 探针跑在同两文件的「使用期限(年)」列上 THEN 必须**不**报违规（它本就该是
    `el-input-number`）

2.4 WHEN 探针输出 THEN 必须区分三类：`confirmed_violation`（金额列 + 非 WpAmountInput）/
    `ambiguous`（label 歧义待裁决）/ `ok`，并给出文件 + 行号 + 列 label

2.5 WHEN 探针做反向自检 THEN 必须验证：喂一个已迁移的金额列（`WpAmountInput`）不报违规；
    喂一个 `el-input-number` 的年限列不报违规；喂一个 `el-input-number` 的金额列必报违规

2.6 IF 探针命中数与人工复核结果不一致 THEN 以人工复核为准并修探针
    （I 循环 Task 18 首版探针曾报 22 处，逐标签复核发现全是 `style="width:100%"` 的 `%`
    落进 400 字符窗口造成的误报 ⇒ 窗口式匹配不可靠，必须按 `el-table-column` 块配对扫描）

### Requirement 3: 反向边界判据必须具备区分能力

**User Story:** 作为复核者，我需要「非金额列没被误换」这条断言在迁移后仍然有意义。

#### Acceptance Criteria

3.1 WHEN 迁移完成一批 THEN 反向边界断言必须能在「把年限列误换成 `WpAmountInput`」时打红
    —— 用变异检验证明，不接受「在未迁移代码上恒真」的断言

3.2 WHEN 建立反向边界判据 THEN 必须至少覆盖一个**已迁移**文件里的真实非金额列作为锚点，
    使断言的扫描面非空

3.3 WHEN `WpAmountInput` 被用在非金额列 THEN 断言失败消息必须给出文件 + 列 label +
    「该列属哪类非金额语义」

### Requirement 4: 分批迁移与批次内闭环

**User Story:** 作为项目维护者，我不接受一个跨 798 个文件的大爆炸式改动。

#### Acceptance Criteria

4.1 WHEN 规划批次 THEN 必须按「先确定性最高、影响最大」排序：
    批 1 = 80 处 `:formatter` 空操作（确定错、语义明确）；
    批 2 = I 循环摊销测算表等本次实测确认的漏网点；
    批 3+ = 按循环分批处理 `confirmed_violation` 剩余项

4.2 WHEN 完成一个批次 THEN 该批次必须自带守卫 + 变异检验 + 浏览器实测，不得攒到最后

4.3 WHEN 浏览器实测 THEN 判据是「输 `1234567.5` → 失焦显示 `1,234,567.50`」
    且**同一行内的只读派生列格式一致**（本次实测暴露的正是同行两种格式）

4.4 WHEN 迁移涉及 `:precision` THEN 必须逐列确认业务粒度，不得机械套用
    （`使用期限(年)` 现为 `:precision="2"` 显示 `10.00`，年限是否允许小数需业务确认，
    改 `:precision="0"` 会禁掉 `2.5 年` 这类录入 ⇒ 本 spec 只登记不擅改）

4.5 WHEN 某批次的文件正被其它 active spec 修改 THEN 必须先 `git status` 归因，
    跳过并登记，不得覆盖他人在途改动

### Requirement 5: 迁移正确性（不改变数值语义）

#### Acceptance Criteria

5.1 WHEN 把 `el-input-number` 换成 `WpAmountInput` THEN 绑定的 `v-model` 字段、
    `@change` 回调、`:min` / `:max` / `:disabled` 语义必须逐项等价保留

5.2 WHEN 原控件有 `:controls="false"` THEN 迁移后不得出现步进按钮

5.3 WHEN 原控件允许负数（如备抵/调整列）THEN 迁移后必须仍允许

5.4 WHEN 用户输入非法值 THEN 不得写入 `NaN`（`WpAmountInput` 的既有行为，须在守卫中锁死）

5.5 WHEN 迁移后 THEN 该列的持久化值类型必须仍是 number（不得变成带逗号的字符串落库）

### Requirement 6: 验收与入库

#### Acceptance Criteria

6.1 WHEN 每批次完成 THEN 按引用关系反查辐射面串行跑测试（`--no-file-parallelism`），
    禁止跑前端全量（实测 1999 files 并发跑会产出大量资源竞争型 flaky）

6.2 WHEN 浏览器实测 THEN 写库数据必须在验收后复原，并以 `--diff` 输出「无漂移」为证

6.3 WHEN 批次收口 THEN `git status --porcelain -- <产物清单>` 必须无 `??`

6.4 WHEN 探针与守卫入 CI THEN 必须是 blocking job，且 job 内跑的文件清单显式列出

6.5 WHEN 本 spec 全部完成 THEN `el-input-number` 用于金额列的 `confirmed_violation` 必须为 0，
    且该结论由探针脚本 `--check` 可复现
