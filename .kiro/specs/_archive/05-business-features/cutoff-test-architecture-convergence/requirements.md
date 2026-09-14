# Requirements Document

截止性测试架构收敛（cutoff-test-architecture-convergence）

## Introduction

截止性测试功能在长期演进中形成多处**并行实现**，此前已完成 P0（证据治理）与 P1（任意截止日端到端、跨期→A13 联动）确定性 bug 修复。本 spec 处理剩余的**架构收敛**——把散落的端点、判定函数、证据模型与统计口径收敛为单一真源，消除漂移与假绿风险。

本 spec 是 **strangler / 行为保持式重构**：核心约束是**零回归**——此前 P0/P1 已落地的确定性行为必须逐条保持，既有测试必须持续全绿，禁止用放宽断言/跳过用例绕过。

### 收敛前的真实现状（本仓实测）

**两套后端截止端点**：
- `POST /sampling/cutoff-test`（`CutoffTestService.run_cutoff_test`）——简单引擎：仅 account_codes/year/days/threshold/cutoff_date；返回全部 entries 一次性（无分页、无截断透明、无全量统计、无 exclude_extracted、无 direction/keyword）。K8/K9/useCycleCutoff（I2/I6）当前调它。
- `POST /sampling/cutoff-extract`（`LedgerSamplingService` + `CutoffExtractRequest`）——富引擎：cutoff_date/前缀匹配/direction/voucher_type/keyword/exclude_extracted/分页/`StatsResult`（含全量 `amount_total`/`truncated`）。useCutoffAutoSampling 调它。

**五套跨期/窗口判定函数**：
- `cutoffJudgment.ts::determineCutoffStatus`（单日期 + direction post/pre/window → '可能跨期'/'待检查'/'正常'）
- `cutoffJudgment.ts::computeDateRange`（窗口计算）
- `useI2FormulaEngine.ts::isCutoffPeriodCrossing`（双日期任一侧跨截止日 → boolean）
- `useCutoffAutoSampling.ts::markCutoffCrossPeriod`（双日期 + 单日期降级 → boolean）
- `useCutoffAutoSampling.ts::filterByCutoffWindow`（窗口过滤）
- `useK8CutoffEngine.ts` / `useK9CutoffEngine.ts::isCrossPeriod`（双日期变体）

**三套 CutoffRow 证据模型**：`useCycleCutoff`（recordDate/amount/documentDate/documentAmount）、`useK8Cutoff`（bookDate/amount/sourceDate/sourceAmount）、`useK9Cutoff`（bookDate/amount/sourceDate，无 sourceAmount）——字段命名与结论口径各异。

**结论口径不统一**：useCycleCutoff 用 '证据不完整'/'跨期'/'正常'；K8/K9 用 '证据不完整'/'跨期'/'正常'；useCutoffAutoSampling 用 '可能跨期'/'待检查'/'正常'。无统一状态机。

## Glossary

- **截止基准日（cutoff_date）**：资产负债表日（审计期末），非固定 12-31。
- **记账侧证据**：记账凭证日期 + 账面金额 + 凭证号。
- **原始单据侧证据**：原始单据/支出凭单日期 + 单据金额 + 单据号。
- **双侧独立证据**：记账侧与原始单据侧两份**各自独立取得**的证据；截止结论必须同时具备两侧。
- **全量抽样框**：从 DB 层对满足条件的**全部**凭证做 COUNT/SUM 聚合得到的总体，不受返回分页/截断影响。
- **canonical 判定**：收敛后的单一跨期判定真源。

---

## Requirements

### Requirement 1: 唯一截止取数端点

**User Story:** 作为维护者，我要所有截止自动取数走单一后端端点，以消除简单引擎/富引擎双轨漂移与能力缺口。

#### Acceptance Criteria

1. WHEN 系统需要按截止条件从序时账取数 THEN 系统 SHALL 仅通过单一 canonical 截止取数端点（以 `cutoff-extract` 富引擎为真源）完成。
2. WHERE `cutoff-test` 端点仍被外部调用 THE 系统 SHALL 将其保留为对 canonical 引擎的**薄委托**（同签名、同响应形状），或在所有调用方迁移后按序废弃；两种路径均不得改变既有响应契约。
3. WHEN K8-6/K8-7、K9-6/K9-7、useCycleCutoff（I2/I6）触发自动取数 THEN 系统 SHALL 经 canonical 端点获得与迁移前**相同窗口的凭证集合**（相同 cutoff_date/days/account/threshold 输入下集合等价）。
4. WHEN 通过 canonical 端点取数 THEN 调用方 SHALL 获得富引擎能力：科目前缀匹配、exclude_extracted 去重、全量统计、截断透明；缺省参数下行为与迁移前一致。
5. IF canonical 端点接收非法或缺省参数 THEN 系统 SHALL 保持既有回退语义（cutoff_date 缺省回退 year-12-31；account_codes 为空返回空集合而非全表）。

### Requirement 2: 统一双侧证据模型

**User Story:** 作为审计师，我要截止样本的记账侧与原始单据侧证据在统一模型下表达与校验，以避免各底稿字段口径不一导致的误判。

#### Acceptance Criteria

1. WHEN 表达一条截止样本 THEN 系统 SHALL 使用单一 canonical 样本模型，显式区分记账侧（日期/金额/凭证号）与原始单据侧（日期/金额/单据号）两组独立证据字段。
2. WHEN 任一侧的日期证据缺失 THEN 系统 SHALL NOT 将该样本结论判为"正常"或纳入完成；SHALL 判为"证据不完整"。
3. WHEN 更新账面金额 THEN 系统 SHALL NOT 自动复制账面金额为原始单据金额（保持 P0 修复）。
4. WHEN 从自动取数导入样本（仅得记账侧） THEN 系统 SHALL 将原始单据侧证据留空并使样本进入"证据不完整"，由审计师补录。
5. WHERE 现有 useCycleCutoff/useK8Cutoff/useK9Cutoff 三处 CutoffRow 结构存在 THE 系统 SHALL 提供从各自结构到 canonical 模型的等价适配（字段别名映射），迁移不丢已保存数据。

### Requirement 3: 统一跨期判定

**User Story:** 作为维护者，我要单一跨期判定真源，以消除五套判定函数各自演进导致的语义漂移。

#### Acceptance Criteria

1. WHEN 判定一条样本是否跨期 THEN 系统 SHALL 调用单一 canonical 判定模块；`determineCutoffStatus`/`isCutoffPeriodCrossing`/`markCutoffCrossPeriod`/`isCrossPeriod`/`filterByCutoffWindow` 的调用方 SHALL 迁移至该模块或其薄封装。
2. WHEN 记账侧日期与原始单据侧日期分处截止基准日两侧 THEN canonical 判定 SHALL 返回"跨期"。
3. WHEN 仅具备单侧日期（另一侧缺失） THEN canonical 判定 SHALL 按既有单日期降级语义返回"跨期疑点/待检查"而非直接"正常"或"跨期"，与迁移前 `markCutoffCrossPeriod` 单日期降级行为等价。
4. WHEN 计算日期窗口 [cutoff_date − daysBefore, cutoff_date + daysAfter] THEN canonical 窗口函数 SHALL 与既有 `computeDateRange`/`filterByCutoffWindow` 边界（含端点闭区间）逐日等价。
5. WHERE direction 概念（post_cutoff/pre_cutoff/window，或 forward/backward）在不同调用方语义不同 THE canonical 模块 SHALL 显式文档化并保留各语义的等价映射，不得静默改变任一调用方结论。

### Requirement 4: 统一结论状态机

**User Story:** 作为复核人，我要所有截止底稿用同一套结论状态与完成门禁，以便一致地审阅与追踪。

#### Acceptance Criteria

1. WHEN 为截止样本下结论 THEN 系统 SHALL 使用统一状态集合：待追查、证据不完整、正常、跨期、需调整、已调整；每条样本 SHALL 恰好映射到其中之一（互斥完备）。
2. WHEN 审计师已手工录入结论 THEN 系统 SHALL 保留手工结论，canonical 默认派生仅作缺省回退。
3. WHEN 判定底稿完成度 THEN 系统 SHALL 在存在"证据不完整"或未决"跨期"样本时使完成标记 ok=false（保持 P0 完成门禁）。
4. WHERE 各底稿现有中文结论字面量（'可能跨期'/'待检查' 等）存在 THE 系统 SHALL 提供到统一状态集合的等价映射，迁移不改变现有已保存结论的语义归类。

### Requirement 5: DB 级全量抽样框

**User Story:** 作为审计师，我要总体统计、覆盖率与 MUS 抽样间隔基于全量总体，以避免因返回截断导致的统计失真与假绿。

#### Acceptance Criteria

1. WHEN 通过 canonical 端点取数 THEN 系统 SHALL 在 DB 层对满足条件的**全部**凭证聚合总体统计（总笔数、借方合计、贷方合计、全量代表金额），不受返回分页/截断影响。
2. WHEN 返回的样本框被分页或截断 THEN 系统 SHALL 显式返回 `truncated=true` 且总体统计仍为全量口径。
3. WHEN 计算覆盖率或 MUS 抽样间隔 THEN 系统 SHALL 以全量总体统计为分母/基数，不得用截断后的样本框重算。
4. IF `cutoff-test` 简单引擎在收敛前被调用 THEN 迁移后的 canonical 路径 SHALL 为其补齐全量统计与截断透明（简单引擎当前缺失此能力）。
5. WHEN 全量总体为空 THEN 系统 SHALL 返回明确的空结果与零统计，不得静默失败或返回误导性非零值。

### Requirement 6: 下游联动一致

**User Story:** 作为审计师，我要所有截止底稿的跨期发现一致地既生成调整分录草稿又推送 A13 错报汇总。

#### Acceptance Criteria

1. WHEN 任一截止底稿发现跨期样本并生成 AJE 草稿 THEN 系统 SHALL 同时发布 `a13:push-misstatement`（crossWpEventBridge 白名单事件），保持 P1 已实现的联动。
2. WHEN 推送 A13 THEN payload SHALL 包含 wpCode、accountCode、projectId、source、items（voucherNo/amount/description/indexRef）、timestamp，与既有 K9-6/7 范式一致。
3. WHERE useCycleCutoff（I2/I6）与 K8/K9 各自的跨期→A13 路径存在 THE 系统 SHALL 使二者行为一致（同样的触发条件与 payload 结构）。

### Requirement 7: 零回归与增量可回退

**User Story:** 作为维护者，我要收敛过程可分步、可回退、零回归，以在大范围重构下不破坏已上线行为。

#### Acceptance Criteria

1. WHILE 执行收敛 THE 系统 SHALL 在每一步保持既有截止相关测试全绿（前端 cutoff PBT/I2/I6/K8-pbt-cutoff + 后端 cutoff sampling 集成/PBT）。
2. WHEN 收敛完成 THEN 以下 P0/P1 已修确定性行为 SHALL 全部保持：cutoff_date 任意截止日、科目前缀匹配、双侧证据门禁、禁止金额自动复制、undo 必传 wp_id、confirmFill 提交 filled_voucher_nos、历史/撤销/排除限定 extraction_type='cutoff'、单份版本快照、跨期→A13 联动。
3. WHEN 迁移某个调用方失败或断言不符 THEN 系统 SHALL 停在该步（可回退），不得放宽断言或跳过用例以求通过。
4. WHERE 存在并发会话可能编辑同一文件 THE 实施 SHALL 在每步动手前重新读取最新源码，避免 last-write-wins 覆盖。

### Requirement 8: 契约守卫与差异文档

**User Story:** 作为维护者，我要收敛前先建立行为安全网并产出差异矩阵，以证明等价、防止未来再次漂移。

#### Acceptance Criteria

1. WHEN 收敛任一并行实现前 THEN 系统 SHALL 先补 characterization 测试锁定各实现的当前行为，作为等价迁移安全网。
2. WHEN 收敛完成 THEN 系统 SHALL 产出差异矩阵文档，列出各原实现 → canonical 的映射、语义差异与保留决策。
3. WHEN 新增绕过 canonical 的并行截止判定/端点 THEN 契约守卫 SHALL 使其可被检测（测试或扫描），防止回退到多轨状态。
