# Requirements Document

## Introduction

程序裁剪的重要性判据（`procedure-trimming-and-delegation-intelligence` 的档 7/8）需要知道「这条程序对应的科目余额是多少」。当前的定位方式是**科目名单向子串匹配**：拿程序名去 `trial_balance` 的 `account_name` 里找包含关系。这个方式在真实数据上大面积失效，因为**程序按报表项目组织，而 `trial_balance` 存的是明细科目名** —— 两者是层级关系，不是命名关系。

本 spec 把裁剪判据的科目定位改为走**报表行映射**：程序 → 报表行 `row_code` → `report_config.formula` → 科目金额。三段映射的**每一段都已有生产真源**，本 spec 不新建任何映射知识，只补一层索引与接线。

### 实证基线（2026-08-12，只读 + 浏览器实测）

以下全部来自 `procedure-trimming-and-delegation-intelligence` Task 26 的浏览器实测与 postgres 只读交叉核实（实测项目 `2aa00f57-1df4-4fe8-9840-2d65d0fd8749` 重庆和平药房_2025 / soe）：

1. **E 循环 5 条程序的重要性判据整体空转**。程序名一律「货币资金 …」（`E0 货币资金 - 函证`、`E1-1至E1-11 货币资金- 审定表明细表` 等），而 `trial_balance` 中**没有名为「货币资金」的行**，只有明细「其他货币资金」（`1012`，8,280,881.84）与「银行存款」（`1002`，327,095.20）⇒ `resolveAccountName` 返回 `null` ⇒ `accountAmount` 为 `null` ⇒ 决策内核档 7/8 跳过 ⇒ 档 9 默认保留。
2. **`resolveAccountName` 的 docstring 承诺了两个匹配方向，实现只有一个**。注释写「程序名包含科目名（最长优先）→ 科目名包含程序名」，而函数体只有前者的循环。即便补上后者也救不了本例：程序名「货币资金 - 函证（Leap应对措施-函证）」不被「其他货币资金」包含。
3. **`report_config` 恰好有这条映射**：`BS-002 货币资金 = TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')`，四个 `applicable_standard` 变体一致。
4. **判据读的表是 `trial_balance` 而非 `tb_balance`**。该项目 `trial_balance` 58 行 / 54 个非零科目；`tb_balance` 1176 行。此前会话记录的「481 个非零科目里 370 个低于实际执行重要性」是 `tb_balance` 口径，**与决策内核实际入参不同源**，不能用来推断建议应有多少条。
5. **D 循环 17 条程序的重要性判据不可达，但成因不同且是设计使然**：`COMPLETENESS_CYCLE_RULES` 的 D `sensitiveByDefault = true`，而档 5 完整性豁免排在档 7/8 之前 ⇒ 全部保留。本 spec **不改这个顺序**（完整性方向的漏记与账面金额无关，用金额豁免它方向就是反的）。
6. **档 4 数据存在性判据本身是有效的**：同一轮实测中 D5 应收款项融资 / D7 合同负债被判 `no_data` 并自动裁剪（真实库历史上第一次产生裁剪结果）。故问题**只在重要性维度的金额定位**，不在整条判据链。
7. **改判 D 循环为完整性不敏感后，重要性档立即产出正确建议**：D3 预收账款 13,656,018.02 < 实际执行重要性 26,104,487.00 ⇒ `below_materiality`，落库 `suggestion_state.reason_code` 与含判据数值的 `skip_reason` 并列。⇒ 档 7/8 的**逻辑是对的，缺的只是金额**。

### 已有生产真源（本 spec 一律复用，禁止重造）

| 能力 | 生产真源 | 现状 |
|------|---------|------|
| wp_code → 报表行 `row_code` | `four_table/{d,f,g,i,l,m,n}_cycle_specs.spec_of()` · `k_cycle_specs.get_k_cycle_spec()` · `j_cycle_account_scope.j_semantic_spec_of()` · `e_cycle_specs.E1_REPORT_ROW_CODE` · `h{1,2,3,4,6,7,8,9}_account_scope.H*_ACCOUNT_SPEC` | 已覆盖 D/E/F/G/H/I/J/K/L/M/N，**缺跨循环统一入口** |
| 按项目准则选 row_code | `i_cycle_accounts.resolve_row_code(wp_code, standards)` · `j_cycle_account_scope.pick_spec(specs, standards)` · `k_cycle_specs.KCycleSpec.row_code_soe/row_code_listed` | 已有，各循环自行调用 |
| row_code → 科目码集 | `four_table/report_line_accounts.resolve_report_line_accounts()` | 已有 17 个调用方 |
| 报表公式 → 金额 | `report_engine.ReportFormulaParser.execute()` | 报表模块在用 |
| 公式 → 科目码 | `ReportFormulaParser.extract_account_codes()` | 已有 |
| 叶子聚合（防父子双算） | `four_table/leaf_aggregation.{select_leaves,filter_by_code_specs,aggregate_leaves}` | 已有 |

⇒ **本 spec 的净新增 = 一个跨循环索引 + 一个金额解析器 + 裁剪判据接线 + 溯源展示。**

## Glossary

| 术语 | 含义 |
|------|------|
| 报表行 / `row_code` | `report_config` 的行编码（`BS-002` 货币资金 / `IS-001` 营业收入 / `IMP-008` 债权投资减值准备） |
| 报表项目 | 报表行的行名（`row_name`）。审计程序与底稿按它组织 |
| 明细科目 | `trial_balance.account_name` 里的实际科目（「银行存款」「其他货币资金」），是报表项目的下级 |
| 标准码 | `trial_balance.standard_account_code`（`1002`/`1231-03`），平台统一编码，`-` 分级 |
| 原始码 | `tb_balance.account_code`，客户自己的编码，`.` 分级 |
| `applicable_standard` | 报表准则变体，4 个取值：`listed_consolidated` / `listed_standalone` / `soe_consolidated` / `soe_standalone` |
| 解析来源 | 某条程序的科目金额是怎么来的：报表行映射 / 科目名匹配 / 不可解析 |
| 决策内核 | `procedureTrimDecision.decideTrim()`，9 档短路的裁剪判据纯函数 |

## Requirements

### Requirement 1: 程序 → 报表行的跨循环索引，且不与既有 per-cycle 声明形成双真源

作为平台维护者，我需要一个能按 `wp_code` 查到报表行编码的统一入口，且它的映射知识**全部来自既有 per-cycle 声明**，这样将来某个循环改了报表行号，索引会自动跟随而不会漂移。

#### Acceptance Criteria

1.1 WHEN 传入任一 D/E/F/G/H/I/J/K/L/M/N 循环的 `wp_code` THEN 索引 SHALL 返回该底稿的报表行编码，取值 SHALL 来自对应 per-cycle 声明（`spec_of()` / `get_k_cycle_spec()` / `j_semantic_spec_of()` / `E1_REPORT_ROW_CODE` / `H*_ACCOUNT_SPEC`）而非索引自己的字面量

1.2 索引 SHALL NOT 声明任何 per-cycle 模块里不存在的 `row_code` 字面量；凡需要字面量的位置 SHALL 改为引用既有常量

1.3 WHEN 某 `wp_code` 在任何 per-cycle 声明里都没有报表行落点 THEN 索引 SHALL 返回显式的「无报表行落点」结果并带原因，SHALL NOT 返回空串或抛异常

1.4 A/B/C/S 四类循环（报表与调整 / 计划 / 控制 / 专项）SHALL 显式登记为「不按科目余额驱动」，与 `decideTrim` 的 `BALANCE_DRIVEN_CYCLES` 取值域一致

1.5 索引返回的每个 `row_code` SHALL 在 `report_config` 中真实存在（守卫按真实库断言）

1.6 索引与 per-cycle 声明的 `row_code` SHALL 逐字相等（守卫交叉锁死，一侧改动另一侧未跟进即打红）

1.7 索引 SHALL 支持形如 `D2-1至D2-4` / `E1-14至E1-15` 的**区间型 wp_code**（真实库 `procedure_instances.wp_code` 实际形态），按前缀归一到底稿主码

### Requirement 2: 报表行 → 科目金额走既有取数引擎，与报表页同口径

作为审计师，我需要裁剪建议里的科目金额与报表页显示的金额一致，否则我无法判断该不该接受建议。

#### Acceptance Criteria

2.1 金额解析 SHALL 复用 `ReportFormulaParser`（报表模块的取数引擎），SHALL NOT 新写公式求值或科目聚合逻辑

2.2 WHEN 报表公式含 `TB()` 的科目码 THEN 金额 SHALL 按「该科目及其全部子科目」前缀聚合（沿用 `_get_tb_rows_prefix` 口径），SHALL NOT 只取精确码

2.3 WHEN 报表公式含 `SUM_TB('lo~hi')` 区间 THEN 金额 SHALL 按区间语义聚合

2.4 WHEN 报表公式含减项（如 `TB('1122') - TB('1231')`）THEN 金额 SHALL 按公式符号运算，SHALL NOT 只把各项相加

2.5 金额 SHALL NOT 按 `SemanticAccountSpec` 的槽（slot）拆分后再合计 —— 实证多槽规格下报表公式兜底会把整行金额分配给某个槽，E1 曾因此把 `1002`/`1012` 算两遍（8,935,072.24 vs 真值 4,467,536.12，虚增一倍）

2.6 WHEN 报表公式含 `ROW()` 引用（依赖其它报表行的计算结果）THEN 金额 SHALL 标注为不可独立解析，SHALL NOT 用 0 或部分结果代替

### Requirement 3: 按项目实际准则选取报表行与公式

作为审计师，国企项目与上市项目的同一底稿对应的报表行号不同（如 J1 应付职工薪酬 `listed=BS-051` / `soe=BS-069`），金额必须按本项目的准则取。

#### Acceptance Criteria

3.1 WHEN 解析某项目的报表行金额 THEN 系统 SHALL 按该项目的 `applicable_standard` 取对应 `report_config` 行

3.2 WHEN 某底稿的报表行号按准则变体不同 THEN 系统 SHALL 复用既有的准则选择件（`resolve_row_code` / `pick_spec` / `KCycleSpec.row_code_soe|row_code_listed`），SHALL NOT 另写一套准则判断

3.3 WHEN 项目未设置适用准则 THEN 系统 SHALL 标注为不可解析，SHALL NOT 默认取某一个变体

3.4 同一 `row_code` 在不同变体下公式不同的情形（实证 `BS-006 应收账款`：`listed_consolidated = TB('1122')` 而 `listed_standalone = TB('1122') - TB('1231')`）SHALL 按变体取到各自的科目集与金额

### Requirement 4: 解析结果三态可区分，一律不兜造金额

作为审计师，我必须能区分「这个科目余额是 0」与「平台算不出这个科目的余额」—— 前者可能是裁剪依据，后者只意味着该判据本次不可用。

#### Acceptance Criteria

4.1 解析结果 SHALL 恒含来源标识，取值域 SHALL 为「报表行映射解析成功 / 无报表行落点 / 报表公式缺失或不可解析 / 项目准则未设置」四态之一

4.2 WHEN 解析未成功 THEN 结果 SHALL NOT 含金额字段或金额 SHALL 为 `null`，SHALL NOT 为 `0`

4.3 每一态 SHALL 有独立的中文说明文案，使审计师在界面上看到的原因与实际成因一致

4.4 WHEN 取数过程抛异常 THEN 系统 SHALL 记 ERROR 级日志并按不可解析处理，SHALL NOT 静默返回 0 或空

4.5 解析失败 SHALL NOT 阻断裁剪页其余功能（其它维度判据照常工作）

### Requirement 5: 裁剪判据接线为加法式，未命中时行为逐字不变

作为平台维护者，我需要这次改造不破坏已收口的裁剪判据 —— `procedure-trimming-and-delegation-intelligence` 的 26 个任务已全部完成并有变异检验护住。

#### Acceptance Criteria

5.1 报表行映射 SHALL 作为科目金额的**优先**来源；现有科目名匹配 SHALL 保留为兜底

5.2 WHEN 报表行映射解析成功 AND 科目名匹配也命中 AND 两者金额不同 THEN 系统 SHALL 采用报表行映射结果并记录两者差异供溯源

5.3 WHEN 报表行映射未命中 THEN 决策内核的输入与输出 SHALL 与改造前逐字相同（零回归 characterization）

5.4 决策内核（`decideTrim`）的 9 档顺序与短路语义 SHALL 不变；本 spec SHALL NOT 新增或调整档位

5.5 判据上下文的新增字段 SHALL 为 additive；未消费该字段的调用方 SHALL 不受影响

5.6 完整性豁免（档 5）与风险保护（档 1）的优先级 SHALL 不变 —— 本 spec 只补金额，不改「谁先判」

### Requirement 6: 金额来源可追溯到报表行与科目码

作为质量控制复核合伙人，我需要能追查某条裁剪建议的金额是怎么算出来的，否则无法评价该裁剪的适当性。

#### Acceptance Criteria

6.1 裁剪建议的判据证据 SHALL 含报表行编码、报表行名、命中的公式原文、参与计算的标准码集

6.2 裁剪页与裁剪充分性复核视图 SHALL 从同一解析结果派生金额与来源，相同输入下两处 SHALL 逐项相等

6.3 WHEN 金额来自科目名匹配兜底 THEN 界面 SHALL 显式标注为兜底来源，使复核者知道该金额的可靠性低于报表行映射

6.4 溯源信息 SHALL 复用既有溯源展示机制，SHALL NOT 新建第二套溯源字段

### Requirement 7: 守卫、变异检验、真实库验收与浏览器实测

作为平台维护者，我需要这次改造的判据强度足以挡住本平台已反复出现的假绿模式（替身掩盖参数编码、源码级断言只查字符存在、判据扫描面与声称覆盖面不一致）。

#### Acceptance Criteria

7.1 守卫 SHALL 分「独立口径判据（现在应全绿）」与「被测实现（现在应全红）」两类，类 B 的失败消息 SHALL 写明「尚未实现（Task N）」

7.2 变异检验 SHALL 至少 8 条且逐条必须 RED，判据 SHALL 按失败测试名集合求差集而非退出码

7.3 真实库验收 SHALL 覆盖多个准则变体与多个循环，某状态在库中不存在时 SHALL 输出 `UNVERIFIABLE` 而非用构造数据冒充通过

7.4 浏览器实测 SHALL 证实 E 循环（本 spec 的立项缺陷现场）在改造后能产出重要性类建议，且金额与 `report_config` 公式独立计算结果一致

7.5 CI SHALL 新增 job 覆盖本 spec 的后端与前端守卫

7.6 涉及真实库写入的实测 SHALL 按基线复原并以独立查询核实

## 范围外

- **不改 `decideTrim` 的 9 档顺序**（R5.4/R5.6）。D 循环因完整性豁免不产生金额类建议是设计使然，不是本 spec 要修的。
- **不改 `COMPLETENESS_CYCLE_RULES` 的默认清单**。改判某循环是否完整性敏感是审计师的项目级判断，入口已由 `procedure-trimming-and-delegation-intelligence` Task 14 交付。
- **不改 `report_config` 的数据**。若发现某报表行公式错码，登记为独立议题（平台已有 `report-config-account-code-integrity` 的守卫与修法范式）。
- **不改 `trial_balance` / `tb_balance` 的取数口径**，也不改 `_load_accounts` 现有的科目名聚合输出（它仍供数据存在性判据与循环级判定使用）。
- **不做「报表项目 → 明细科目」的反向展开**（把报表行拆回明细科目列表供 UI 逐条展示）。裁剪判据只需要行级合计。
- **不扩展到委派侧**。委派的风险匹配走 B50 科目名，与本 spec 无关。
- **不为现金流量表 / 权益变动表补 TB 公式**（实证这两类 `report_config` 行无 `TB()` 引用，且它们不是科目余额驱动循环的对象）。
