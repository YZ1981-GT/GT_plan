# Requirements Document

## Introduction

函证模块的「函证覆盖率」是审计证据充分性的**结论性指标**。当前实现存在口径错误与单一真源缺失两类问题（三次复盘核实）：

1. **口径错误（P0）**：`ConfirmationDashboard` 的真实数据源 `useConfirmationData.coverageMetrics` 计算
   `confirmation_coverage = 已确认金额 / Σ(函证行金额)`——分母是「已函证金额之和」而非**科目审定总额（TB population）**。
   但 Dashboard tooltip 与 `GtConfirmationSummary` 公式面板均声明「函证覆盖率 = 发函总额 / 科目账面余额 × 100%」。
   即：指标算的是「已确认/已函证」比率，**根本没度量科目被函证的覆盖比例**，会误导「证据是否充分」的判断。
   `reply_coverage = 已回函笔数 / 总笔数`（按笔数），但 tooltip 声明「已回函金额 / 函证发出总金额」（按金额），标签与计算不一致。

2. **单一真源缺失（P1）**：后端 `GET /projects/{pid}/confirmations/stats`（返回 `reply_rate`/`confirmation_coverage`/`warn_level`）
   全前端**无消费者**（死端点），且字段名与前端 composable（`reply_coverage`）对不上；两套覆盖率并行计算，口径可能发散。

本 spec 目标：以**科目审定总额（TB population）**为分母修正三项覆盖率口径，收敛为单一真源，并让 tooltip/标签与计算严格一致。
遵循审计铁律「Skip-on-missing 优于误报」——当科目总体金额无法解析时，覆盖率显示为「不可用」而非误导性数字。

不在本 spec 范围：替代程序（alternative-*）composable、Hub 台账投影、舞弊信号落库、覆盖率阈值与 B15 重要性联动。

## Glossary

- **科目审定总额 / TB population**：函证底稿所对应科目在试算平衡表（trial_balance）的审定金额合计（负债类取绝对值），作为覆盖率分母。
- **函证覆盖率 (confirmation coverage)**：发函总额 / 科目审定总额 × 100%。度量该科目余额被纳入函证程序的比例。
- **确认覆盖率 (confirmed coverage)**：（回函确认金额 + 替代确认金额）/ 科目审定总额 × 100%。度量已取得确认证据占科目余额的比例。
- **回函覆盖率 (reply coverage)**：已回函笔数 / 已发函笔数 × 100%（笔数口径，与公式面板一致）。
- **可确认金额 (computeConfirmedAmount)**：现有 composable 逻辑（相符→函证金额；不符→回函金额；未回函→替代确认金额）。
- **population 可解析性 (population resolvable)**：后端能从 TB 解析出该函证底稿科目审定总额且 > 0。
- **单一真源 (single source)**：覆盖率口径只有一处权威定义，前后端不各算一套。

## Requirements

### Requirement 1: 函证覆盖率以科目审定总额为分母

**User Story:** 作为审计师，我希望「函证覆盖率」真实反映该科目被函证的比例，以便判断函证证据是否充分。

#### Acceptance Criteria

1. WHEN 科目审定总额（population）可解析且 > 0 THEN 系统 SHALL 计算 `confirmation_coverage = 发函总额(Σ函证行金额) / population × 100%`。
2. WHEN 科目审定总额不可解析或 ≤ 0 THEN 系统 SHALL 将 `confirmation_coverage` 标记为不可用（null），并且 UI SHALL 显示「需科目总体金额」占位而非误导性百分比。
3. WHEN 计算 `confirmed_coverage` THEN 系统 SHALL 使用分子 =（相符/不符回函确认 + 替代确认）金额、分母 = population。
4. THE 分母 population 对负债类科目 SHALL 取审定金额绝对值（借正贷负口径归一为正）。

### Requirement 2: 回函覆盖率口径与标签一致

**User Story:** 作为审计师，我希望回函覆盖率的显示口径与其标签/tooltip 严格一致，避免误读。

#### Acceptance Criteria

1. THE `reply_coverage` SHALL 定义为「已回函笔数 / 已发函笔数 × 100%」（笔数口径，与公式面板一致）。
2. WHEN 已发函笔数为 0 THEN 系统 SHALL 返回 0 且不除零。
3. THE Dashboard 中回函覆盖率的 tooltip 文案 SHALL 与「笔数口径」一致（不再声明金额口径）。
4. THE 「已发函笔数」判定 SHALL 复用现有在途/已发函语义（`isConfirmationInFlight` 或等价 send 状态），不得用总笔数替代。

### Requirement 3: 科目审定总额由后端注入（population 单一真源）

**User Story:** 作为开发者，我希望科目总体金额从 TB 权威取数并随渲染注入，避免前端各自臆测分母。

#### Acceptance Criteria

1. WHEN 渲染 `confirmation-summary` 底稿 THEN 后端 SHALL 在 htmlData 的 `project_context` 中注入 `population_amount`（科目审定总额）。
2. THE population_amount 解析 SHALL 复用既有 TB 取数机制（`get_active_filter` + trial_balance audited_amount），并按科目编码聚合。
3. WHEN 无法确定函证底稿对应科目或 TB 无对应记录 THEN 后端 SHALL 注入 `population_amount = null`（不臆测、不返回 0 冒充）。
4. THE 注入 SHALL 为加法式（additive），不改变现有 confirmation-v1 htmlData 结构与既有字段。

### Requirement 4: 覆盖率单一真源收敛（后端 /stats 与前端一致或移除死端点）

**User Story:** 作为维护者，我希望覆盖率只有一处权威口径，消除死端点与双算发散。

#### Acceptance Criteria

1. THE 覆盖率口径（三项定义）SHALL 只有一处权威实现，前后端字段命名一致（`confirmation_coverage` / `confirmed_coverage` / `reply_coverage` / `warn_level`）。
2. IF 后端 `GET /confirmations/stats` 保留 THEN 它 SHALL 使用与前端一致的口径（含 population 分母），且字段名与前端 `ConfirmationCoverageMetrics` 对齐。
3. IF 后端 `/stats` 无任何消费者且不接 population THEN 系统 SHALL 移除该死端点，避免误导后续接入。
4. WHEN 决策保留或移除 `/stats` THEN 相关测试 SHALL 随之更新，不得残留断言死端点的假绿测试。

### Requirement 5: 预警等级基于修正后口径

**User Story:** 作为审计师，我希望覆盖率不足的预警基于真实口径，以便及时补充证据。

#### Acceptance Criteria

1. WHEN `reply_coverage < 80%` THEN `warn_level` SHALL 至少为 `danger`（回函不足优先级最高）。
2. WHEN `reply_coverage ≥ 80%` AND `confirmation_coverage` 可用 AND `confirmation_coverage < 50%` THEN `warn_level` SHALL 为 `warn`。
3. WHEN `confirmation_coverage` 不可用（population 缺失）THEN `warn_level` SHALL 仅由 `reply_coverage` 决定，且 UI SHALL 提示函证覆盖率因缺科目总体金额未参与预警。

### Requirement 6: 零回归与可测性

**User Story:** 作为维护者，我希望覆盖率修正不破坏现有函证编制/持久化/看板渲染，并有测试守卫审计口径。

#### Acceptance Criteria

1. THE 修正 SHALL 不改变 confirmation-v1 持久化 payload 结构、`computeConfirmedAmount` 业务规则、Hub 同步链路。
2. THE `coverageMetrics` 与后端 stats（若保留）SHALL 有单元测试锁定三项口径（含 population 缺失分支、除零分支）。
3. WHEN population 缺失 THEN 现有「录入更多后指标更有参考价值」等既有 UI 行为 SHALL 不受影响。
4. THE 改动文件 SHALL 通过 get_diagnostics 与 Vite transform（前端）/ AST 编译（后端）校验。
