# Requirements Document

## Introduction

通用抽凭引擎（`GtVoucherSamplingEngine` / `useVoucherSampling` / `useSamplingAlgorithms` / 后端 `voucher_sampling.py` + `voucher_sampling_algorithms.py` + `LedgerSamplingService`）在长期演进中已具备五种抽样方法、B15 重要性联动、MUS 间隔、高值必选、随机种子、版本历史、覆盖率、错报推断、UML、抽样结论与底稿回填。此前已完成 **P0 第一批快修**（回填日志补 `filled_voucher_nos`、未检查样本不参与错报推断、结论确认门禁、传父底稿真实前态、后端 `amount_max`/离散月份生效、调用方 API/非法 phase 迁移、`summary_keyword` PBT 策略收敛）。

本 spec 处理剩余的 **第二批正确性改造** 与 **第三批架构收敛**：抽样框全量化（消除对总体前 N 条的选择偏差）、总体完整性独立数据源、分录/凭证抽样单位统一、回填与日志原子化、抽样批次状态机与完整性约束、后端方法学单一真源、多套抽样 API 收敛、服务端授权校验、真实操作者留痕、核心算法权威向量与属性测试，以及 `summary_keyword` 的 LIKE 元字符转义。

本 spec 是 **strangler / 行为保持式重构**：核心约束是**零回归**——P0 第一批快修与既有抽凭行为必须逐条保持，既有测试（后端 `test_voucher_sampling_integration` + 前端 `useVoucherSampling.spec` / `useSamplingAlgorithms.spec`）必须持续全绿，禁止用放宽断言 / 跳过用例 / 换参数绕过。

### 与截止性测试架构收敛 spec 的边界

`cutoff-test-architecture-convergence` spec 拥有**截止路径**（`cutoff-extract` / `cutoff-test` 端点、跨期判定、CutoffRow 证据模型、截止全量框）的收敛，本 spec **不重复**处理。二者共享 `LedgerSamplingService`：本 spec 对**抽样框全量化**的改造仅作用于抽凭路径（`voucher-extract` 的 `execute_sampling`），必须保持 `cutoff-extract` 既有行为零回归；本 spec 的**多套抽样 API 收敛**仅收敛 `voucher-extract` 与 `sampling-execute`（`WpSamplingEngine`），不触碰 `cutoff-extract` / `cutoff-test`（由截止 spec 负责）。

## Glossary

- **总体（population）**：满足抽样过滤条件的全部序时账记录集合。
- **抽样框（sampling frame）**：抽样算法实际据以抽取样本的候选集合；若被截断为总体的子集，则随机 / 分层 / 系统 / MUS 抽样均产生选择偏差。
- **全量抽样框**：抽样算法可从总体的**每一个抽样单位**中抽中，不因返回分页 / `max_total` 截断而使部分单位永不可抽。
- **抽样单位（sampling unit）**：抽样的最小对象，`ledger_line`（序时账分录行）或 `voucher`（整张凭证，按凭证号聚合）。
- **总体完整性核对（population reconciliation）**：将抽样总体金额与**独立于序时账的账面来源**（试算表科目余额 / 审定数 / 损益发生额）比对，证明从完整总体抽样；无独立来源时显示"未执行核对"，不得以序时账总体自身比对充数。
- **方法学单一真源**：MUS 抽样间隔、高值必选标识、建议样本量等由后端权威计算并返回，前端仅展示与即时预览，正式回填以后端复算为准。
- **抽样批次（sampling batch）**：一次抽凭执行 → 回填 → 记录日志构成的原子单元，具唯一 `batch_id` 与幂等键。
- **canonical 抽样端点**：收敛后的单一抽凭取数 / 抽样端点（以 `voucher-extract` 为真源）。
- **characterization test**：锁定既有实现当前行为的测试，作为等价迁移的安全网。

---

## Requirements

### Requirement 1: DB 级全量抽样框

**User Story:** 作为审计师，我要抽样从完整总体中抽取，以确保当总体超过内存上限时随机 / 分层 / 系统 / MUS 抽样不产生选择偏差。

#### Acceptance Criteria

1. WHEN 总体记录数超过内存抽样上限（当前 `max_total=10000`） THEN 系统 SHALL 使抽样算法仍可从总体的**每一个抽样单位**中抽中，不得仅从按 `(voucher_date, voucher_no)` 排序后的前 N 条中抽取。
2. WHEN 执行随机 / 系统 / MUS 抽样且总体超上限 THEN 系统 SHALL 通过 DB 级抽样或"两阶段定位（先按算法确定命中的抽样单位标识，再按标识取回样本）"实现，使选择概率覆盖全总体。
3. WHEN 执行 MUS 抽样 THEN 高值必选项（单笔金额 ≥ 抽样间隔）SHALL 从**全量总体**中识别并 100% 纳入，不受抽样框截断影响。
4. WHEN 总体未超上限 THEN 系统 SHALL 保持与现状**逐字节等价**的抽样结果（相同种子 / 参数 / 总体下样本集合不变），确保零回归。
5. WHEN 抽样框因实现限制仍存在上限 THEN 系统 SHALL 显式返回该限制并使其可被前端如实提示，不得静默截断且不得声称覆盖全总体。
6. WHERE 相同随机种子 THE 全量抽样框实现 SHALL 保持结果可复现（同种子 + 同总体 + 同参数 → 同样本）。

### Requirement 2: 总体完整性独立数据源

**User Story:** 作为审计师，我要总体完整性核对使用独立于序时账的账面来源，以避免"总体与自身比对"的假绿。

#### Acceptance Criteria

1. WHEN 展示总体完整性核对 THEN 系统 SHALL 优先使用独立数据源作为账面金额：资产负债表类科目用试算表期末余额 / 审定数；损益类科目用权威发生额。
2. IF 无可用独立数据源 THEN 系统 SHALL 显示"未执行总体完整性核对"，SHALL NOT 以序时账总体金额自身作为账面金额产生"一致"结论。
3. WHEN 抽样总体金额与独立账面金额差异超过可容忍阈值 THEN 系统 SHALL 提示"总体可能不完整，抽样结论受限"。
4. WHEN 审计师手工录入账面金额 THEN 系统 SHALL 以手工值为准执行核对，并留存该手工值来源标记。
5. WHERE 独立数据源取数失败或缺失 THE 系统 SHALL 允许审计师手工录入，不阻断抽样流程。

### Requirement 3: 抽样单位显式化

**User Story:** 作为审计师，我要显式选择按分录行还是按整张凭证抽样，以避免同一凭证多行或跨科目导致的重复抽取与整张误排除。

#### Acceptance Criteria

1. WHEN 配置抽样 THEN 系统 SHALL 支持显式抽样单位：`ledger_line`（分录行）或 `voucher`（整张凭证）。
2. WHEN 抽样单位为 `voucher` THEN 系统 SHALL 按凭证号聚合总体金额与统计，并在抽中一张凭证时带出其完整借贷分录。
3. WHEN 排除已抽 / 预审转年审排重 / 版本比较 THEN 系统 SHALL 使用与当前抽样单位一致的稳定键，避免按凭证号整张排除却按分录行抽样导致的跨科目误排除。
4. WHEN 未显式指定抽样单位 THEN 系统 SHALL 采用与现状等价的默认单位（当前为分录行），保持零回归。
5. WHERE 抽样单位为 `voucher` THE 覆盖率与 MUS 间隔的分母 SHALL 与所选单位口径一致（按凭证聚合的总体金额 / 笔数）。

### Requirement 4: 回填与日志原子化

**User Story:** 作为审计师，我要回填底稿与记录抽样日志作为一个原子操作，以避免部分成功导致底稿与日志不一致或 before_data 失真。

#### Acceptance Criteria

1. WHEN 确认回填 THEN 系统 SHALL 使"底稿数据变更 + 抽样日志写入（含 before_data 快照与 filled_voucher_nos）"在同一逻辑事务内成功或整体失败。
2. IF 日志写入失败 THEN 系统 SHALL NOT 使底稿保留已回填状态而日志缺失（不得产生无法撤销的孤儿回填）。
3. WHEN 回填成功 THEN before_data SHALL 反映回填前底稿的真实前态（基于父底稿传入的 existingSamples，保持 P0 修复）。
4. WHEN 回填的样本集合非空 THEN 日志 SHALL 记录本次实际回填的凭证号清单（filled_voucher_nos，保持 P0 修复）。

### Requirement 5: 抽样批次状态机与完整性约束

**User Story:** 作为维护者，我要抽样日志具备幂等批次、状态机、乐观锁与撤销唯一约束，以保证并发与重放下的一致性与可追溯。

#### Acceptance Criteria

1. WHEN 记录一次抽样批次 THEN 系统 SHALL 为其分配 `batch_id` 与幂等键（idempotency_key），相同幂等键的重复提交 SHALL NOT 产生重复日志。
2. WHEN 抽样批次生命周期演进 THEN 系统 SHALL 以明确状态集合表达：draft → confirmed → filled → undone；状态转移 SHALL 受约束（不可从终态非法回退）。
3. WHEN 撤销一次批次 THEN 数据库约束 SHALL 保证同一批次至多成功撤销一次（撤销唯一性），并保持"仅可撤销最近一次非撤销记录"的既有语义。
4. WHEN 写入抽样日志 THEN 数据库 SHALL 对 `fill_mode`、`extraction_type` 施加 CHECK 约束（仅允许合法枚举值），并使 `user_id` 关联真实用户表。
5. WHEN 并发提交同一底稿的抽样批次 THEN 系统 SHALL 通过乐观版本或等价机制检测冲突，不得静默互相覆盖。
6. WHERE 迁移新增约束 THE 迁移 SHALL 幂等（`IF NOT EXISTS` / information_schema 守护）且向后兼容既有日志行（历史行缺 `batch_id` 时不破坏读取）。

### Requirement 6: 后端方法学单一真源

**User Story:** 作为维护者，我要 MUS 抽样间隔与高值必选由后端权威计算，前端只展示，以消除前后端双算的算法漂移。

#### Acceptance Criteria

1. WHEN 后端执行抽样 THEN 系统 SHALL 权威计算并返回抽样间隔、高值必选标识与建议样本量（方法学快照）。
2. WHEN 前端展示方法学结果 THEN 前端 SHALL 消费后端返回值作为权威口径；前端可保留即时预览计算，但正式回填 SHALL 以后端复算 / 返回值为准。
3. WHEN 回填时 THEN 系统 SHALL 记录方法学快照的算法版本标识，以支持未来审计追溯与漂移检测。
4. WHERE 前端与后端方法学计算存在差异 THE 系统 SHALL 以后端为准，并使差异可被契约测试检测。

### Requirement 7: 抽样 API 收敛

**User Story:** 作为维护者，我要抽凭取数走单一 canonical 端点，以消除 `voucher-extract` 与 `sampling-execute` 双轨实现的能力漂移与重复算法。

#### Acceptance Criteria

1. WHEN 系统需要执行抽凭抽样 THEN 系统 SHALL 仅通过单一 canonical 抽样端点（以 `voucher-extract` 为真源）完成。
2. WHERE `sampling-execute`（`WpSamplingEngine`）仍被调用 THE 系统 SHALL 将其保留为对 canonical 引擎的**薄委托**（同签名、同响应形状），或在所有调用方迁移后按序废弃；两种路径均不得改变既有响应契约。
3. WHEN 两套抽样算法实现（`voucher_sampling_algorithms` 与 `WpSamplingEngine`）并存 THEN 系统 SHALL 收敛为单一算法真源，消除重复实现。
4. WHEN 收敛完成 THEN 所有既有 `voucher-extract` 调用方 SHALL 获得相同输入下等价的样本与统计。
5. WHERE 本 spec 收敛抽凭抽样端点 THE 系统 SHALL NOT 触碰 `cutoff-extract` / `cutoff-test`（归属截止 spec）。

### Requirement 8: 服务端授权校验

**User Story:** 作为安全负责人，我要抽凭端点在服务端校验底稿归属、年度与编辑权限，以防止越权与错误年度取数。

#### Acceptance Criteria

1. WHEN 调用抽凭端点 THEN 系统 SHALL 校验 `workpaper_id` 属于 URL 中的项目；不属于时 SHALL 拒绝（不得跨项目取数）。
2. WHEN 调用抽凭端点 THEN 系统 SHALL 校验请求年度属于该项目的审计期；非法年度 SHALL 被拒绝或明确报错，不得静默按错误年度取数。
3. WHEN 调用抽凭端点 THEN 系统 SHALL 校验当前用户对该底稿 / sheet 具备编辑权限；无权限时 SHALL 拒绝。
4. WHERE 校验失败 THE 系统 SHALL 返回明确的授权错误，且 SHALL NOT 依赖前端不展示按钮作为唯一防线。

### Requirement 9: 真实操作者留痕

**User Story:** 作为复核人，我要 edit_trail 与实际错报录入记录真实操作者，以保证审计追溯的可信。

#### Acceptance Criteria

1. WHEN 记录 edit_trail 或实际错报 THEN 系统 SHALL 使用真实认证用户身份，SHALL NOT 使用硬编码占位符 `current_user`。
2. WHERE 操作者身份应由服务端确定 THE 系统 SHALL 由后端认证上下文记录 actor，前端不得自行声明可信身份。
3. WHEN 展示或导出 edit_trail THEN 系统 SHALL 呈现真实操作者标识。

### Requirement 10: 核心方法学正确性

**User Story:** 作为维护者，我要核心抽样算法有固定权威向量与属性测试，以防 CAS 1314 泊松表 / MUS 间隔 / UML / 结论判定被无意破坏。

#### Acceptance Criteria

1. WHEN 计算抽样间隔、建议样本量、推断错报、错报上限与抽样结论 THEN 系统 SHALL 有固定权威向量测试锁定已知输入 → 已知输出。
2. WHEN 错报增加 THEN 错报上限（UML）SHALL 不下降（单调性）。
3. WHEN 可容忍错报增加 THEN 建议样本量 SHALL 不增加（单调性）。
4. WHEN 错报上限计算 THEN SHALL 恒有 UML ≥ 推断错报 ≥ 0。
5. WHEN 高值项目金额 ≥ 抽样间隔 THEN SHALL 100% 被选中。
6. WHEN 相同种子 / 总体 / 参数 THEN 抽样结果 SHALL 稳定可复现。
7. WHEN 样本包含未检查项 THEN 未检查项 SHALL NOT 按零错报参与推断（保持 P0 修复）。
8. WHEN 后端与前端方法学计算同一输入 THEN 结果 SHALL 一致（间隔 / 高值识别 / 结论）。

### Requirement 11: 关键词搜索 LIKE 元字符转义

**User Story:** 作为审计师，我要按摘要关键词搜索时，`%`、`_`、`\` 等字符被当作字面量匹配，以避免误匹配或漏匹配。

#### Acceptance Criteria

1. WHEN `summary_keyword` 含 LIKE 元字符（`%` / `_` / `\`） THEN 系统 SHALL 转义这些字符使其按字面量匹配（ILIKE + ESCAPE 或等价预转义）。
2. WHEN `summary_keyword` 为普通文本（含 CJK / 字母数字） THEN 系统 SHALL 保持与现状等价的匹配行为。
3. WHERE 转义引入 THE 既有截止 / 抽凭查询过滤测试 SHALL 持续全绿。

### Requirement 12: 零回归与增量可回退

**User Story:** 作为维护者，我要收敛过程可分步、可回退、零回归，以在跨前后端大范围重构下不破坏已上线行为。

#### Acceptance Criteria

1. WHILE 执行改造 THE 系统 SHALL 在每一步保持既有抽凭相关测试全绿（后端 `test_voucher_sampling_integration` + `test_cutoff_sampling_pbt` / `integration` + 前端 `useVoucherSampling.spec` / `useSamplingAlgorithms.spec`）。
2. WHEN 改造完成 THEN 以下 P0 已修确定性行为 SHALL 全部保持：`filled_voucher_nos` 提交、未检查样本不参与推断、结论确认门禁、传父底稿真实前态、`amount_max` / 离散月份过滤、非法 phase 已迁移。
3. WHEN 迁移某个调用方或改造某处失败或断言不符 THEN 系统 SHALL 停在该步（可回退），SHALL NOT 放宽断言或跳过用例以求通过。
4. WHERE 存在并发会话可能编辑同一文件 THE 实施 SHALL 在每步动手前重新读取最新源码，避免 last-write-wins 覆盖。
5. WHEN 改造前 THEN 系统 SHALL 先补 characterization 测试锁定各并行实现的当前行为，作为等价迁移安全网。
6. WHEN 收敛完成 THEN 系统 SHALL 产出差异矩阵文档，列出各原实现 → canonical 的映射、语义差异与保留决策。

### Requirement 13: 属性抽样接入控制测试（可选）

**User Story:** 作为审计师，我要属性抽样能力接入 C 类控制测试，以按偏差率评价控制运行有效性。

#### Acceptance Criteria

1. WHEN C 类控制测试需要按属性（偏差率）抽样 THEN 系统 SHALL 复用既有 `computeAttributeSampleSize` / `evaluateDeviationRate` 能力提供样本量推导与偏差率评价。
2. WHEN 属性抽样接入 THEN SHALL NOT 改动既有金额法（MUS / 随机 / 系统 / 分层 / 特定项目）的任何函数与数据结构（纯附加）。
3. WHERE 本需求为可选 THE 未实现时 SHALL NOT 阻断本 spec 其余需求的完成。

### Requirement 14: 正式抽样备忘归档（可选）

**User Story:** 作为复核人，我要抽样备忘作为绑定批次与版本链的正式工件归档，以支持长期追溯。

#### Acceptance Criteria

1. WHEN 生成抽样备忘 THEN 系统 SHALL 使其绑定 `batch_id`、算法版本、随机种子并纳入版本链。
2. WHEN 归档抽样备忘 THEN 备忘内容 SHALL 反映该批次的真实数据（方法 / 参数 / 覆盖率 / 错报推断 / 结论）。
3. WHERE 本需求为可选 THE 未实现时 SHALL NOT 阻断本 spec 其余需求的完成。
