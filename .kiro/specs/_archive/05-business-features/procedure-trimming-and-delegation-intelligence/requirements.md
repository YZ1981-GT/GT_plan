# Requirements Document

## Introduction

底稿**程序裁剪**与**人员委派**是项目核心环节：裁剪决定"这个项目要做哪些程序"，委派决定"谁来做"。当前两者的骨架已相当扎实，但**智能化程度停在单维判据**，与重要性水平、风险评估、底稿模块的联动几乎为零。

本 spec 的目标是把裁剪决策从「一维（科目有无余额）」升级为「三维（风险评估 → 重要性 → 数据存在性）」，把委派从「一次一个循环给一个人」升级为「按风险与负载给出建议分配表」，并补齐两者与 B50 风险评估、B15 重要性、底稿录入状态、附注模块的联动。

### 现状实证基线（2026-08-08 只读调查，落地前必读）

**已扎实、禁重造的部分：**

- **委派后端**：三粒度 selector（`cycle` / `workpaper` / `row`）、一次性 preview 凭证 + `lock_version` 校验 + `request_id` 幂等、默认整批原子 / 显式 `best_effort`、`assert_sod_distinct` 在 preview 与 apply **逐 task 双查**（不是只在前端）、同步前置 materialize、`delegation_batch_id` + delegation history + policy epoch + invalidation outbox。
- **裁剪与委派已联动**：`ProcedureDelegationService._trimmed_scopes()` 使被粗裁为 `skip`/`not_applicable` 的 scope 不会成为委派目标。
- **B50 录入侧已完整**（归档 spec `b50-risk-assessment`）：`GtB50RiskAssessment.vue`（2600+ 行、4 个 Tab）+ `useB50RiskMatrix.ts` + `useB50FormData.ts` + `useB50Approval.ts`；已实现从 `GET /api/b50/scope-accounts` 一键导入科目、逐认定 IR/CR/RMM/SR 录入、CAS 规则（收入确认舞弊推定 / 管理层凌驾控制不可变）、合伙人审批与只读、12 条 PBT + registry 契约测试。**本 spec 不重建任何 B50 录入 UI。**
- **B50 前后端 item_id 前缀一致**：前端写 `B50-T3-matrix-{account}-{assertion}-{suffix}` / `B50-T3-cycle-{name}` / `B50-T3-plan-{name}-{field}`，后端 `b50_risk_reader._parse_matrix_item_id` 与 `load_b50_accounts` 解析同款 ⇒ 全库 `B50-T3-*` 为 0 行是**真实业务状态（没人填过）**，不是接线缺陷。

**三个已备好却零引用的数据源（本 spec 的核心机会）：**

| 数据源 | 现状 | 被裁剪判据引用了吗 |
|---|---|---|
| `GET /api/b50/scope-accounts` 返回的逐科目 `amount` | 端点已聚合并返回 | ❌ 智能裁剪调了该端点，但只取 `cycle`，`amount` 整个丢弃 |
| `materiality` 表的 `performance_materiality` / `trivial_threshold` / `overall_materiality` | 表在（全库 2 个项目有数据） | ❌ 零引用。裁剪理由下拉已有「金额低于重要性水平（不重要）」但纯手工文本 |
| `b50_risk_reader.load_b50_accounts()` 的 `max_risk` / `has_special` / `approach` / `reliance` / `substantive_only` / 逐认定 `cells{assertion:{rmm,special}}` | 读取能力完整已实现 | ❌ 零引用 |

即：审计上程序裁剪的三个法定判据，平台只实现了最末位的「数据存在性」。

**真实库存量（决定"数据缺失"必须是一等状态）：**

`risk_assessments` 0 行 / `risk_matrix_records` 0 行 / `checklist_responses` 的 `B50-T3-*` **0 行** / `materiality` 仅 2 个项目有数据（而 14 个项目有 `procedure_instances`）/ `procedure_row_tasks` 仅 3 个项目 46 行（行级委派几乎未被使用）/ `procedure_trim_schemes` 5 行。

### 🔴 核心设计约束：不得天真实现"重要性联动"

「科目余额 < 实际执行重要性 ⇒ 裁掉该科目程序」在审计上**不成立**：

1. **低估风险方向反了**。重要性用于评价错报与确定样本量，不是"科目小就不查"。账面小恰恰可能是**完整性认定**出了问题（少记负债、少记收入），而完整性风险与账面金额无关 —— 这正是要查它的理由。
2. **汇总效应**。若干各自低于实际执行重要性的科目，汇总错报可能远超重要性水平；准则要求汇总考虑。
3. **特别风险与高风险不受金额豁免**。对特别风险必须实施实质性程序，金额小也必须做。

因此本 spec 中「低于重要性」只产生**建议**、必须人工确认，且配汇总闸与完整性豁免。

### 已由用户拍板的三条口径

- **口径 A**：「低于重要性」只建议不自动裁；`no_data`（科目在试算表无数据）保持现有自动裁行为。
- **口径 B**：先补 B50 填写引导，再做风险联动（避免给一条永远走不到的分支写代码，也避免把"未填"与"低风险"混为一谈）。
- **口径 C**：完整性敏感范围交给用户决定 —— 优先读审计师自己在 B50 做的**完整性认定**评估（科目级），未填时退回**循环级默认清单**（平台建议值 + 项目级可覆盖 + 留痕）。`D 收入`循环按「默认开 + 项目组可关」立项。

## Requirements

### Requirement 1: B50 认定层次数据可读性补齐

**User Story:** 作为现场经理，我希望审计师在 B50-3 录入的科目余额、审计范围类别、会计估计标识能被下游读取，这样裁剪与委派决策才能用上这些审计判断。

#### Acceptance Criteria

1.1 WHEN 前端已落库 `B50-T3-balance-{account}`（remark 存余额数值）THEN `load_b50_accounts()` 返回的科目项 SHALL 包含 `balance` 字段（数值或 `None`）
1.2 WHEN 前端已落库 `B50-T3-category-{account}` / `B50-T3-estimate-{account}` THEN 返回的科目项 SHALL 分别包含 `category` / `is_estimate` 字段
1.3 WHEN 某科目未录入上述三个键 THEN 对应字段 SHALL 为 `None`，而不是 `0` 或空串（"未录入"与"录入为 0"必须可区分）
1.4 `_parse_matrix_item_id()` SHALL 保持对 `B50-T3-balance-*` / `-category-*` / `-estimate-*` 返回 `None`（现有 `body == item_id` 守卫不得移除，避免非矩阵键被误判成矩阵单元格）
1.5 补齐后 `load_b50_accounts()` 对**既有** cycle / plan / matrix 三类键的解析结果 SHALL 逐字节不变（additive 扩展，零回归）
1.6 `load_b50_risks()` 的返回结构 SHALL 不受本需求影响（它只消费 `cells`）

### Requirement 2: B50 填写引导与完成度提示

**User Story:** 作为审计助理，我希望平台告诉我 B50-3 该填什么、填到什么程度算够，以及在裁剪页能直接跳去填，这样风险评估才不会因为"不知道要填"而空着。

#### Acceptance Criteria

2.1 B50-3 界面 SHALL 展示填写完成度：已导入科目数 / 已评估科目数（至少一个认定有 RMM）/ 未评估科目清单
2.2 完成度 SHALL 区分三态：`未开始`（0 科目）/ `部分完成`（有科目但存在未评估科目）/ `已完成`（全部导入科目至少一个认定有 RMM）
2.3 WHEN 科目已导入但六个认定全无 RMM THEN 该科目 SHALL 在未评估清单中列出，并支持点击定位到该行
2.4 WHEN 项目尚未导入任何科目 THEN 界面 SHALL 提示「可从试算表一键导入」并给出该操作入口（复用既有 `applyScopeAccounts`，不新建导入逻辑）
2.5 程序裁剪页 SHALL 展示 B50 填写状态徽标（三态同口径），并在非"已完成"时提供跳转 B50-3 的入口
2.6 该徽标 SHALL 说明"风险联动依赖 B50"，使审计师理解未填的后果，而不是只显示一个状态词
2.7 B50 完成度判定 SHALL 是纯函数且前后端同口径（避免两侧各算一份而漂移）

### Requirement 3: 裁剪判据三维化

**User Story:** 作为项目经理，我希望智能裁剪按"风险评估 → 重要性 → 数据存在性"三维给出结论，而不是只看科目有没有余额，这样裁剪结论才符合准则的风险导向要求。

#### Acceptance Criteria

3.1 智能裁剪 SHALL 对每个程序产出一个决策结果，包含：`verdict`（`keep` / `auto_trim` / `suggest_trim`）、`reason_code`、`evidence`（判据数值与来源）
3.2 决策顺序 SHALL 为（前者命中即短路）：特别风险或高风险保护 → 强制保留项 → 数据存在性 → 微小临界值 → 重要性 → 默认保留
3.3 WHEN 该科目在 B50 的任一认定 `special = true` 或 `max_risk = 'H'` THEN verdict SHALL 为 `keep`，且**不得**因金额低于任何重要性口径而改变
3.4 WHEN 程序为 `is_mandatory` / 属 A 或 S 循环 / `execution_status` 属 `in_progress|completed|reviewed` / 已手动填写裁剪理由 THEN verdict SHALL 为 `keep`（保持现有行为）
3.5 WHEN 程序所属循环不在科目余额驱动集合（B/C 等）THEN verdict SHALL 为 `keep`（保持现有行为）
3.6 WHEN 该科目在试算表无数据 THEN verdict SHALL 为 `auto_trim`，`reason_code = no_data`（保持现有行为）
3.7 WHEN 科目余额绝对值 < `trivial_threshold` 且未被 3.3 保护且未被完整性豁免 THEN verdict SHALL 为 `suggest_trim`，`reason_code = below_trivial`
3.8 WHEN 科目余额绝对值 < `performance_materiality` 且不满足 3.7 且未被 3.3 保护且未被完整性豁免 THEN verdict SHALL 为 `suggest_trim`，`reason_code = below_materiality`
3.9 WHEN B50 该科目 `approach = substantive` 且 `reliance` 为不信赖 THEN verdict SHALL 为 `keep` 并附提示「拟不信赖内部控制，实质性程序需加强」
3.10 `evidence` SHALL 记录本次判定实际使用的数值（科目余额、所用重要性口径及其金额、B50 风险等级、数据来源标识），供理由留痕与复核追溯
3.11 决策逻辑 SHALL 是零 IO 纯函数（输入为已取好的科目余额 / 重要性 / B50 结论 / 程序属性），便于单测与变异检验

### Requirement 4: 数据缺失时的降级与诚实告知

**User Story:** 作为业务合伙人，我希望在重要性或风险数据缺失时，平台明确告诉我"本次没有做这一维联动"，而不是假装做了，这样我才能判断裁剪结论可不可信。

#### Acceptance Criteria

4.1 WHEN 项目无 `materiality` 记录 THEN 重要性维度 SHALL 整体跳过（不产生 `below_trivial` / `below_materiality` 建议），并在结果摘要中标注「未做重要性联动：本项目未确定重要性水平」
4.2 WHEN 项目 B50 无任何已评估科目 THEN 风险维度 SHALL 整体跳过，并标注「未做风险联动：B50 认定层次风险矩阵未填写」
4.3 WHEN 某科目在 B50 中不存在（其余科目已评估）THEN 该科目 SHALL 按"风险未知"处理：不享受 3.3 保护，也不因风险而被裁，仅在 evidence 标注 `risk_unknown`
4.4 WHEN 试算表读取失败或无任何科目 THEN SHALL 保持现有安全兜底（阻断裁剪并提示），不得把"读不到"当成"无数据"而全裁
4.5 摘要中的降级标注 SHALL 与实际执行一致（不得出现"已做风险联动"而实际跳过的情况），并由守卫钉死
4.6 `performance_materiality` 缺失但 `overall_materiality` 存在时 SHALL 不自行推算实际执行重要性，按 4.1 跳过重要性维度

### Requirement 5: 完整性认定豁免

**User Story:** 作为质量控制复核合伙人，我希望"金额小就不做"这个逻辑对完整性风险高的科目自动失效，且失效范围由项目组自己确认，这样才不会因为账面金额小而漏查少记负债。

#### Acceptance Criteria

5.1 WHEN B50 中该科目存在 `completeness` 认定评估 THEN 完整性豁免 SHALL 以该认定为判据：`rmm = 'H'` 或 `special = true` 时该科目不享受任何"低于重要性"建议
5.2 WHEN B50 中该科目无 `completeness` 认定评估 THEN 完整性豁免 SHALL 退回循环级清单判据
5.3 循环级默认清单 SHALL 为声明式真源，默认开启 `L 债务` / `J 职工薪酬` / `N 税金` / `K 管理` / `D 收入`，默认关闭 `E 货币资金` / `F 存货` / `G 投资` / `H 固定资产` / `I 无形资产` / `M 权益`
5.4 清单每一条 SHALL 附审计依据文字（说明为何该循环的完整性风险高或低），不得只有布尔值
5.5 项目组 SHALL 能按项目覆盖该清单（逐循环开关），覆盖动作 SHALL 记录**最后一次**修改的操作人、时间与理由（承载表只保留当前值，不保留多次覆盖的历史；如需完整历史属另一议题，本 spec 不做）
5.6 WHEN 某项目未做过覆盖 THEN SHALL 使用默认清单，且在裁剪摘要与复核视图中标注「使用平台默认，未经本项目确认」
5.7 完整性豁免命中时 evidence SHALL 记录判据层级（`assertion` 或 `cycle_default` 或 `cycle_override`），使复核者能区分"审计师判断"与"平台默认"
5.8 豁免判定 SHALL 是纯函数，且认定级判据 SHALL 优先于循环级（同一科目两者结论冲突时以认定级为准）

### Requirement 6: 建议态与人工确认

**User Story:** 作为审计助理，我希望"建议裁剪"和"已裁剪"在界面上可区分，且建议必须我确认后才生效，这样我不会在不知情的情况下漏做程序。

#### Acceptance Criteria

6.1 `suggest_trim` 的程序 SHALL 以区别于"已裁剪"的视觉状态展示（建议态），并显示建议理由与判据数值
6.2 `suggest_trim` SHALL NOT 直接改变程序的适用性状态；只有用户确认后才转为不适用
6.3 用户 SHALL 能逐条确认、批量确认、以及逐条驳回建议
6.4 WHEN 用户驳回建议 THEN 该程序 SHALL 保持执行状态，且驳回 SHALL 不被下一次智能裁剪重新建议（记录驳回标记）
6.5 WHEN 用户确认建议 THEN 裁剪理由 SHALL 自动填入含判据数值的规范文本，并保留用户补充说明的能力
6.6 建议态统计 SHALL 在裁剪页与全项目概览中可见（建议数 / 已确认数 / 已驳回数）
6.7 `auto_trim` 与 `suggest_trim` 的处理路径 SHALL 在代码上可区分，且守卫 SHALL 钉死"重要性类 reason_code 不得走自动裁路径"

### Requirement 7: 汇总闸

**User Story:** 作为业务合伙人，我希望平台阻止"一堆各自不重要的科目被一起裁掉、汇总起来却超过重要性"这种情况，因为准则要求汇总考虑。

#### Acceptance Criteria

7.1 系统 SHALL 计算本次"建议裁剪 + 已确认裁剪"的科目余额绝对值合计
7.2 WHEN 该合计 ≥ `performance_materiality` THEN 批量确认 SHALL 被阻断，并提示合计金额与重要性金额的对比
7.3 阻断时 SHALL 仍允许逐条确认（审计师可自行判断个别项），但每次逐条确认后 SHALL 重新计算并持续提示
7.4 汇总计算 SHALL 只计入因重要性原因（`below_trivial` / `below_materiality`）裁剪的科目，不计入 `no_data` 类（后者本身无金额）
7.5 同一科目被多个程序引用时 SHALL 只计一次金额（按科目去重，避免重复累计）
7.6 WHEN 重要性数据缺失 THEN 汇总闸 SHALL 不生效（因为无比较基准），且不得静默放行而不告知
7.7 汇总闸计算 SHALL 是纯函数并覆盖变异检验（去掉去重、改用求和不取绝对值、改成 `>` 而非 `≥` 等变异必须被打红）

### Requirement 8: 裁剪理由码统一

**User Story:** 作为质量控制复核合伙人，我希望能按理由统计全项目的裁剪情况，这样才能判断裁剪是否过度或理由是否牵强。

#### Acceptance Criteria

8.1 粗裁 SHALL 支持结构化理由码 + 可选补充文本（现状仅自由文本 `skip_reason`）
8.2 理由码取值域 SHALL 与细裁侧 `TrimReasonCode` 收敛为同一真源（现状细裁已有枚举含 `LOW_RISK_ASSESSMENT`，粗裁无）
8.3 理由码 SHALL 覆盖：无相关业务 / 试算表无数据 / 低于微小临界值 / 低于实际执行重要性 / 风险评估为低 / 已由其他底稿覆盖 / 其他（其他必须填文本）
8.4 存量仅有自由文本的裁剪记录 SHALL 保持可读，不得因引入理由码而丢失或显示为空
8.5 系统生成的建议裁剪 SHALL 自动带上对应理由码，人工裁剪 SHALL 从点选列表选择
8.6 裁剪方案导出 SHALL 同时包含理由码与理由文本
8.7 理由码真源 SHALL 有前后端交叉锁死守卫（一侧新增取值而另一侧未跟进即打红）
8.8 理由码 SHALL 与适用性状态在**同一次写入**中落库（现状 canonical trim 的 scope entry 只含 `target_status` 与 `skip_reason` 两个字段，无理由码位置）；SHALL NOT 采用"先写状态再补一次理由码"的两次写入，也 SHALL NOT 把理由码编码进 `skip_reason` 文本
8.9 WHEN scope entry 未携带理由码 THEN 裁剪写入行为 SHALL 与改造前逐字节一致（additive 扩展，存量调用方零影响）

### Requirement 9: 底稿已录入保护

**User Story:** 作为审计助理，我希望我已经填过数据的底稿不会被智能裁剪判成"不适用"，因为那意味着我的工作白做了。

#### Acceptance Criteria

9.1 WHEN 某程序对应底稿已存在实质录入 THEN verdict SHALL 为 `keep`，且理由说明"底稿已有录入内容"
9.2 "实质录入"判定 SHALL 基于该底稿是否存在录入记录，而不仅依赖 `execution_status`（现状只看后者，程序状态仍为待执行而底稿已录数据的会被裁掉）
9.3 该判定 SHALL 与"程序有执行进度"判据并列生效（任一成立即保留）
9.4 判定 SHALL 批量取数（不得每个程序单独查库），避免裁剪页出现 N+1 查询
9.5 WHEN 底稿录入记录查询失败 THEN SHALL 按"可能有录入"处理（保守保留），并记录告警
9.6 守卫 SHALL 覆盖"程序状态为待执行 + 底稿有录入"这一组合必须判 `keep`

### Requirement 10: 委派向导信息补全

**User Story:** 作为项目经理，我希望在委派前看到"这个人当前背了多少任务"和"这次会委派哪些底稿"，这样我才能判断分配是否合理。

#### Acceptance Criteria

10.1 委派向导 SHALL 展示后端 preview 已返回的执行人当前负载（非终态任务数）
10.2 委派向导 SHALL 展示后端 preview 已返回的受影响底稿清单（可展开查看）
10.3 负载口径 SHALL 统一为后端口径，前端 SHALL NOT 另算一份（现状前端按"底稿张数"自算且仅在打开全项目概览后才有值，与后端"非终态任务数"口径不同）
10.4 底稿主编下拉的负载展示 SHALL 与委派向导同源同口径
10.5 负载数据 SHALL 在进入委派界面时即可用，不依赖用户先打开其他抽屉
10.6 WHEN 负载数据获取失败 THEN SHALL 显示"负载未知"而不是显示 0（0 会误导为"这个人很空闲"）
10.7 前端 SHALL 保留执行人与复核人不得同一人的即时提示，但 SHALL 明确后端为权威（现状后端 preview 与 apply 已逐 task 校验）

### Requirement 11: 一键智能委派

**User Story:** 作为项目经理，我希望系统按风险和负载给出一份建议分配表，我调整后一次性应用，而不是一个循环一个循环地手工指派。

#### Acceptance Criteria

11.1 系统 SHALL 支持按底稿粒度生成建议分配表（现状前端仅使用循环粒度，后端已支持底稿粒度）
11.2 建议分配 SHALL 综合考虑：底稿风险等级、成员角色资历、成员当前加权负载、成员可承担的循环范围
11.3 高风险与特别风险底稿 SHALL 优先建议资历较高的成员
11.4 负载均衡 SHALL 按加权工作量而非简单张数（权重至少含底稿数与风险系数）
11.5 系统 SHALL 建议操作复核人，且建议结果 SHALL 满足执行人与复核人不同一人
11.6 建议分配表 SHALL 可逐行调整（改执行人 / 改复核人 / 移除该行）
11.7 应用 SHALL 复用既有 preview → apply 两阶段与幂等机制，SHALL NOT 新建第二套委派写入路径
11.8 应用前 SHALL 展示每人分配后的负载对比，使不均衡一眼可见
11.9 WHEN 风险数据缺失 THEN SHALL 退化为仅按负载均衡建议，并标注「未做风险匹配」
11.10 建议算法 SHALL 是纯函数（输入底稿清单 + 成员清单 + 负载 + 风险，输出分配方案），不得内嵌 IO

### Requirement 12: 裁剪充分性复核视图

**User Story:** 作为 EQCR 技术复核人，我希望一屏看清这个项目裁掉了什么、为什么裁、有没有把高风险科目裁掉，这样我才能有效复核裁剪的适当性。

#### Acceptance Criteria

12.1 视图 SHALL 展示全项目维度：各循环保留 / 已裁 / 建议待确认 / 缺理由的数量
12.2 视图 SHALL 展示理由码分布（按理由码汇总裁剪数量）
12.3 视图 SHALL 高亮异常组合：高风险或特别风险科目被裁、缺理由的裁剪、使用平台默认完整性清单未经确认
12.4 视图 SHALL 展示因重要性原因裁剪的科目金额合计与重要性水平的对比
12.5 视图 SHALL 支持从任一异常项跳转到对应循环并定位
12.6 视图 SHALL 为只读（复核视图不承担修改职责）
12.7 视图数据 SHALL 复用裁剪决策的同一真源，不得另算一套统计口径

### Requirement 13: 附注反向联动

**User Story:** 作为审计助理，我希望某个科目循环整体被裁剪后，附注对应章节显示"本期无此项"而不是一张空表，这样交付件不会出现无意义的空白披露。

#### Acceptance Criteria

13.1 WHEN 某科目循环的程序被整体裁剪 THEN 该科目对应附注章节 SHALL 可被标注为本期不适用
13.2 该标注 SHALL NOT 删除附注章节或其模板结构（只改变呈现，保留可恢复性）
13.3 WHEN 裁剪被撤销 THEN 该标注 SHALL 相应撤销
13.4 该标注 SHALL 不覆盖审计师在附注模块的人工录入内容（有人工内容时只提示不自动标注）
13.5 联动 SHALL 为加法式，不改变既有附注同步链路的任何输出
13.6 WHEN 附注章节无法定位 THEN SHALL 跳过并记录，不得报错阻断裁剪保存
13.7 该标注 SHALL 复用附注模块既有的"本期无内容"机制（`disclosure_notes.is_empty` + 与 Word 导出收敛的共享判定 helper），SHALL NOT 新建第二套不适用标注字段或判定逻辑

### Requirement 14: 零回归与守卫

**User Story:** 作为开发者，我希望这轮改动不破坏既有裁剪与委派行为，并且新加的判据有守卫钉死，这样后续会话不会把关键约束"优化"掉。

#### Acceptance Criteria

14.1 既有委派 preview / apply 的对外契约 SHALL 逐字段不变（新增字段为 additive）
14.2 `no_data` 自动裁行为 SHALL 与改造前逐条一致（同一输入产出同一裁剪集合）；因真实库现无任何已裁剪记录（`procedure_instances.status` 全为 `execute`），该零回归 SHALL 以构造输入的 characterization 测试验证，SHALL NOT 声称已在真实库比对过
14.3 特别风险与高风险不受金额豁免 SHALL 有守卫，且移除该保护的变异 SHALL 被打红
14.4 汇总闸、完整性豁免、决策顺序 SHALL 各有守卫并通过变异检验
14.5 理由码前后端交叉锁死 SHALL 有守卫
14.6 B50 读取补齐 SHALL 有守卫证明既有三类键解析结果不变
14.7 数据缺失降级标注与实际执行的一致性 SHALL 有守卫
14.8 SHALL 在真实库上验证：至少覆盖"有重要性无 B50"、"无重要性无 B50"、"有试算表数据"三种项目状态
14.9 SHALL 有浏览器实测：建议态展示、逐条与批量确认、汇总闸阻断、委派建议分配表、负载对比
14.10 实测产生的数据 SHALL 在验收后复原，并以独立查询交叉核实复原结果

## Glossary

| 术语 | 含义 | 备注 |
|---|---|---|
| 粗裁（底稿范围裁剪） | 决定"这张底稿本项目做不做"，落 `procedure_instances.status` = `execute` / `not_applicable` | 入口 `ProcedureTrimming.vue`，走 canonical trim preview → apply |
| 细裁（程序行裁剪） | 决定"这张底稿里哪几条程序做不做"，落底稿内程序行 | 入口 `a-program-console`，服务 `procedure_trim_engine.py`，已有 `TrimReasonCode` 枚举 |
| `verdict` | 单个程序的裁剪判定结果：`keep` / `auto_trim` / `suggest_trim` | 本 spec 引入 |
| `auto_trim` | 自动裁剪，无需人工确认。**仅** `no_data` 使用 | 保持改造前行为 |
| `suggest_trim`（建议态） | 系统建议裁剪但不改变适用性状态，须人工确认 | 重要性类判据一律走这条 |
| PM（实际执行重要性） | `materiality.performance_materiality` | 用于"低于重要性"判据的主口径 |
| 微小临界值 | `materiality.trivial_threshold`（明显微小错报临界值） | 比 PM 更强的裁剪建议依据 |
| 完整性豁免 | 完整性风险高的科目不享受"低于重要性"建议 | 判据两级：认定级优先、循环级兜底 |
| 认定级判据 | 读 B50 该科目 `cells['completeness']` 的 `rmm` / `special` | 审计师自己的科目级判断，精度高于循环级 |
| 循环级清单 | 平台默认的完整性敏感循环开关表 + 项目级覆盖 | 仅在 B50 无该科目完整性评估时生效 |
| 汇总闸 | 因重要性原因裁剪的科目金额合计 ≥ PM 时阻断批量确认 | 对应准则的汇总考虑要求 |
| 特别风险 | B50 中标记 `special = true` 的认定单元格 | 永不受金额豁免 |
| 三粒度 selector | 委派目标选择：`cycle` / `workpaper` / `row` | **后端已支持**，前端目前只用 `cycle` |
| 加权负载 | 成员工作量 = 底稿数 × 风险系数（至少） | 区别于现状的"底稿张数" |
| `membership_load` | 委派 preview 已返回的执行人非终态任务数 | **后端已有**，前端未展示 |
| `affected_workpapers` | 委派 preview 已返回的受影响底稿清单 | **后端已有**，前端未展示 |

### 已存在、本 spec 不得重建的组件

| 组件 | 位置 | 说明 |
|---|---|---|
| B50 风险评估录入 UI | `GtB50RiskAssessment.vue` + `useB50RiskMatrix.ts` + `useB50FormData.ts` + `useB50Approval.ts` | 4 Tab、逐认定录入、CAS 规则、审批只读、12 条 PBT 均已完成 |
| B50 一键导入科目 | `useB50RiskMatrix` 内既有实现 | 消费 `GET /api/b50/scope-accounts` |
| B50 风险读取 | `b50_risk_reader.load_b50_accounts()` / `load_b50_risks()` | 本 spec 只做 additive 字段补齐 |
| 委派 preview / apply | `ProcedureDelegationService` + `DelegationTransactionService` + `procedure_delegations.py` | 幂等、原子、SOD、版本校验、history、epoch 均已完成 |
| 裁剪 → 委派联动 | `ProcedureDelegationService._trimmed_scopes()` | 被裁 scope 已不会成为委派目标 |
| 试算表科目聚合 | `GET /api/b50/scope-accounts` | 已返回 `{name, amount, cycle}`，`amount` 当前被裁剪逻辑丢弃 |
