# Implementation Plan: 程序裁剪与人员委派智能化

## Overview

把裁剪决策从「单维（科目有无余额）」升级为「三维（风险评估 → 重要性 → 数据存在性）」，把委派从「一次一个循环给一个人」升级为「按风险与负载给出建议分配表」。

**总体取向是加法式接线，不重建既有能力。** 三个判据数据源的读取能力全部已存在（`scope-accounts` 的 `amount`、`materiality` 表、`b50_risk_reader`），B50 录入 UI 与 B50×B15 重要性联动面板亦已完整。本计划新增的是一层纯函数决策内核 + 把内核结论接到既有裁剪/委派写入路径。

### 落地前必读的四条约束

1. **禁用 PM / TE / SAT 缩写**。`GtB50RiskAssessment.vue` 把 `overall_materiality` 命名为 `pm`、`performance_materiality` 命名为 `te`，与审计通用含义相反。新代码一律用 DB 字段名；该组件内既有命名不改，但守卫扫描面要排除它。
2. **`overall_materiality` 不作为裁剪判据**。主口径 `performance_materiality`，更强口径 `trivial_threshold`。
3. **不得重建 B50 录入 UI**。`GtB50RiskAssessment.vue`（2600+ 行 / 4 Tab）+ 3 个 composable + 一键导入 + CAS 规则 + 审批只读 + 12 条 PBT 均已完成。本计划对它只做加法式的完成度面板。
4. **迁移号落地时重查**。design 写 V145 只是示意；`schema_version` 与 `backend/migrations/` 必须现查现用，迁移号永不复用；新增列必须同步加 ORM `mapped_column`，否则列在表里存在而代码写不进去。

### Wave 1 守卫的断言分两类（防「全红分不清是功能未做还是守卫写坏」）

- **类 A = 独立口径判据**（守卫自己算出的事实：数据存在性、冻结基线、与另一数据源勾稽、反向自检）—— **现在就应全绿**，绿了才证明判据基础设施有效而非空转。
- **类 B = 被测实现**（API 齐备性 + 实现产出与类 A 口径一致）—— **现在应全红**，失败消息须写明「尚未实现（Wave N Task M）。本条红是预期的 Wave 1 打红结果」。
- 禁在模块顶层 import 生产模块（顶层 import 失败会让整个文件 collection error、零断言执行，那时"全红"既可能是功能没做也可能是守卫写坏）；改为测试内 try-import 后 `pytest.fail`（不是 skip）。

## Task Dependency Graph

W1（B50 数据与引导）与 W3（委派向导信息补全）**无依赖关系，可并行** —— W3 纯前端、零后端改动，不应被 B50 引导挡住。W2 依赖 W1 的风险数据可读性；W4 依赖 W3 的负载口径；W5 依赖 W2 的决策真源。

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "B50 认定层次数据与填写引导",
      "depends_on": [],
      "tasks": ["1", "2", "3", "4"]
    },
    {
      "wave": 2,
      "name": "裁剪三维判据与建议态",
      "depends_on": [1],
      "tasks": ["5", "6", "7", "8", "9", "10", "11", "12", "13", "14"]
    },
    {
      "wave": 3,
      "name": "委派向导信息补全（可与 wave 1 并行）",
      "depends_on": [],
      "tasks": ["15", "16"]
    },
    {
      "wave": 4,
      "name": "一键智能委派",
      "depends_on": [3],
      "tasks": ["17", "18", "19"]
    },
    {
      "wave": 5,
      "name": "复核视图与附注联动",
      "depends_on": [2],
      "tasks": ["20", "21"]
    },
    {
      "wave": 6,
      "name": "守卫收口与验收",
      "depends_on": [2, 4, 5],
      "tasks": ["22", "23", "24", "25", "26"]
    }
  ]
}
```

## Tasks

- [ ] 1. Wave 1 守卫先打红：B50 三字段解析与完成度口径
  - 新建 `backend/tests/procedure_trim/test_b50_reader_extension.py`
  - **类 A（现在应全绿）**：`checklist_responses` 中 `B50-T3-balance-*` 的独立计数查询可执行；`_parse_matrix_item_id` 对 `B50-T3-balance-*` / `-category-*` / `-estimate-*` / `-cscope-*` 一律返回 `None`；冻结 `load_b50_accounts` 对既有 cycle/plan/matrix 三类键的输出快照（作 Task 2 的零回归基线）
  - **类 B（现在应全红）**：返回项含 `balance` / `category` / `is_estimate` 三键；未录入时为 `None` 而非 `0`/空串
  - **反向自检**：移除 `body == item_id` 守卫后，`B50-T3-balance-货币资金` 必须被误判成矩阵格（证明该守卫是防误判的唯一保障）；无该样本时 `pytest.skip` 并在 reason 写明「暂不可验证，⚠️ 不等于可省掉该守卫」
  - 全库 `B50-T3-*` 为 0 行 → 类 A 的存在性断言须按「查询可执行且返回 0」而非「必须有数据」
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 14.6_

- [ ] 2. `load_b50_accounts()` additive 补三字段
  - `backend/app/services/b50_risk_reader.py`：新增解析 `B50-T3-balance-{account}`（取 `remark` 转 float，失败为 `None`）/ `-category-{account}` / `-estimate-{account}`，填入返回项 `balance` / `category` / `is_estimate`
  - 既有 cycle / plan / matrix 三个分支**逐字不动**；`_parse_matrix_item_id` 的 `body == item_id` 守卫**保留**
  - `load_b50_risks()` 不受影响（它只消费 `cells`）
  - 跑 Task 1 守卫：类 B 转绿、类 A 保持绿、既有输出快照零差异
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

- [ ] 3. B50 填写完成度纯函数与面板
  - 新建 `audit-platform/frontend/src/components/workpaper/composables/b50Completeness.ts`：`resolveB50Completeness({accounts})` → `{state: 'not_started' | 'partial' | 'completed', importedCount, assessedCount, unassessedAccounts}`；三态判据 = 导入数为 0 → `not_started`；每个导入科目至少一个认定有 RMM → `completed`；其余 `partial`
  - `GtB50RiskAssessment.vue` 加完成度面板（加法式）：三态徽标 + 已导入/已评估计数 + 未评估科目清单（点击定位到该行）+ 零科目时提示「可从试算表一键导入」并给出既有 `applyScopeAccounts` 入口
  - **不改任何录入逻辑**，不碰该组件既有的 `pm`/`te`/`sat` 命名
  - 新建 `composables/__tests__/b50Completeness.spec.ts`：三态边界 + 未评估清单准确性 + 纯函数无 Vue 依赖
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.7_

- [ ] 4. 裁剪页 B50 状态徽标与跳转
  - `ProcedureTrimming.vue`：展示 B50 填写状态徽标（复用 Task 3 同一纯函数，禁另算一份），非 `completed` 时提供跳转 B50-3 的入口
  - 徽标 tooltip 说明「风险联动依赖 B50 认定层次风险矩阵」，使审计师理解未填的后果而非只看到一个状态词
  - 守卫：徽标取值与 B50 面板同源（源码级断言两处引用同一函数）
  - _Requirements: 2.5, 2.6, 2.7_

- [ ] 5. Wave 2 守卫先打红：决策内核 / 完整性豁免 / 汇总闸
  - 新建 `composables/__tests__/procedureTrimDecision.spec.ts`、`completenessExemption.spec.ts`、`trimAggregateGate.spec.ts`
  - **类 A（现在应全绿）**：`materiality` 表列存在性与三个字段可读；`scope-accounts` 端点确实返回 `amount` 字段（读源码断言）；现状智能裁剪**丢弃 `amount`**（源码级断言 `confirmSmartTrim` 未引用 `amount`，作改造前基线）；`TrimReasonCode` 现有取值域快照
  - **类 B（现在应全红）**：三个纯函数模块存在且导出约定接口
  - **反向自检**：`overall_materiality` 不得出现在决策输入类型中；扫描面非空自检（防正则失效导致断言空转）
  - _Requirements: 3.1, 3.11, 7.7, 14.4_

- [ ] 6. 完整性豁免纯函数与默认清单
  - 新建 `composables/completenessExemption.ts`：`COMPLETENESS_CYCLE_RULES`（声明式真源，11 个科目余额驱动循环各带 `rationale`；默认开 L/J/N/K/**D**，默认关 E/F/G/H/I/M）+ `resolveCompletenessExemption()`
  - **认定级优先**：`completenessRmm` 非 null 或 `completenessSpecial` 为真时只按认定判定，完全不看循环级清单，`source = 'assertion'`
  - `usingPlatformDefault` 当且仅当 `source === 'cycle_default'`
  - 守卫：每条 `rationale` 长度 ≥ 20 且非占位；清单不含 A/B/C/S；认定级与循环级结论冲突时以认定级为准
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7, 5.8_

- [ ] 7. 裁剪决策内核纯函数
  - 新建 `composables/procedureTrimDecision.ts`：`decideTrim(input): TrimDecision`，按 design 的 9 档顺序短路
  - 输出恒含 `verdict` / `reasonCode` / `narrative` / `evidence` / `hints`；`keep` 时 `reasonCode` 为 null，其余两态非 null
  - `evidence` 记录本次实际使用的判据数值与来源标识（科目余额、所用重要性口径及金额、B50 风险等级、完整性判据层级、`risk_unknown` 标记）
  - 零 IO、零 Vue 依赖；输入类型中**不存在** `overall_materiality`
  - 单测覆盖：9 档逐条 + 短路性（命中靠前判据时靠后判据取值变化不改变 verdict）+ 风险未知既不保护也不裁 + 驳回标记恒 keep + 底稿已录入恒 keep（含「程序待执行 + 底稿有录入」组合）+ 不信赖控制提示不改变 verdict
  - PBT（`max_examples` 20）：特别风险/高风险恒 keep、重要性类恒 `suggest_trim`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 4.3, 4.6, 6.4, 9.1, 9.2, 9.3, 9.6_

- [ ] 8. 汇总闸纯函数
  - 新建 `composables/trimAggregateGate.ts`：`evaluateAggregateGate()` → `{applicable, distinctAccountCount, totalAmount, threshold, blocked, narrative}`
  - 三条易被"优化"掉的约束：只计入 `below_trivial` / `below_materiality`、按 `accountName` 去重、判据 `>=` 而非 `>`
  - `performanceMateriality === null` 时 `applicable = false` 且 `blocked = false`（无比较基准）
  - 单测 + PBT：去重正确性、阈值方向、重要性缺失路径
  - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7_

- [ ] 9. 后端判据上下文装配
  - 新建 `backend/app/services/trim_decision_context.py`：`build_trim_decision_context(db, project_id, year, cycles)` 一次性装配 `accounts` / `materiality` / `risk` / `risk_dimension_available` / `completeness_override` / `workpaper_entry` / `degradations`
  - 任一维度取数失败 → 该维度置 `None` 并往 `degradations` 记一条，**不抛异常也不伪造默认值**
  - 试算表读取失败或零科目 → 保持现有阻断兜底语义（上下文使前端阻断裁剪，且区分「读取失败」与「未导入」两种成因）
  - `performance_materiality` 缺失但 `overall_materiality` 存在时**不推算**，按缺失处理
  - `completeness_override` 读 `checklist_responses` 的 `B50-T3-cscope-{cycle}`；读取失败退回平台默认并记 degradation
  - 新增端点或在既有裁剪相关端点上 additive 下发该上下文（不新建第二套取数路径）
  - 守卫：`backend/tests/procedure_trim/test_trim_decision_context.py` —— 三个维度各自的降级路径 + `degradations` 结构 + 不推算断言 + 试算表不可用阻断（含复现旧行为的替身必须打红）
  - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.5, 5.6_

- [ ] 10. 底稿已录入批量探测
  - 新建 `backend/app/services/workpaper_entry_probe.py`：`probe_workpaper_entries(db, project_id, wp_codes)` → `dict[str, bool]`
  - 判据 = 该底稿存在 `checklist_responses` 行（`conclusion` 或 `remark` 非空）或 `working_paper.parsed_data` 非空
  - **批量一次查询**，查询次数与 wp_code 数无关；查询失败 → 全部返回 `True`（保守保留）并记 WARNING
  - 写连库 SQL 前先查真实列名（`checklist_responses` 的底稿外键是 **`wp_id`** 不是 `workpaper_id`）
  - 守卫：批量化（源码级断言无按 wp_code 循环发查询的结构）+ 失败兜底 + 真实列名可执行性（真跑一次查询，异常即红，不只做源码断言）
  - _Requirements: 9.1, 9.2, 9.4, 9.5_

- [ ] 11. 迁移：`procedure_instances.suggestion_state`
  - **落地前重查** `schema_version` 与 `backend/migrations/` 取当前最大迁移号 +1（design 写的 V145 只是示意，并发 spec 可能已占用；迁移号永不复用）
  - `ALTER TABLE procedure_instances ADD COLUMN IF NOT EXISTS suggestion_state JSONB;`（幂等）
  - **同步加 ORM `mapped_column`**（否则列存在而代码写不进去）
  - 结构：`{reason_code, rejected, rejected_by, rejected_at, evidence}`
  - 配套 rollback 脚本（按平台 `R1xx__` 命名约定）
  - 守卫：迁移幂等（二次应用零变更）+ ORM 与迁移列集精确相等（列清单由**扫全部 `V*.sql`** 派生，禁手写按迁移号分组的常量）
  - _Requirements: 6.4, 8.1_

- [ ] 12. 理由码真源统一与交叉锁死
  - `backend/app/services/procedure_trim_engine.py`：`TrimReasonCode` additive 扩展 `NO_DATA` / `BELOW_TRIVIAL` / `BELOW_MATERIALITY` / `COVERED_ELSEWHERE`
  - 粗裁改为共用同一枚举（现状粗裁只有自由文本 `skip_reason`）
  - **canonical trim scope entry additive 扩 `reason_code?`** —— 现状 entry 只有 `{kind, cycle, wp_index_code, target_status, skip_reason}`（前端 `commonApi.canonicalTrimPreview/Apply` 与后端契约双侧），理由码**无处可落**；必须与 `target_status` 同一次请求提交，禁「先 apply 状态再补写理由码」的两次写入，禁把理由码编码进 `skip_reason` 文本
  - `reason_code` 须参与 preview → apply 的 **request payload 归一**（否则两侧 payload 不一致会触发防篡改校验失败）
  - 后端落库时写 `suggestion_state.reason_code`，与 `skip_reason` 并列同事务
  - **未携带 `reason_code` 时请求 payload 与写入行为逐字节不变**（存量调用方与既有测试零影响，这是本扩展可安全落地的结构性保证）
  - 新建前端 `composables/trimReasonCodes.ts` 镜像该枚举 + 中文标签
  - 存量仅有 `skip_reason` 自由文本的记录保持可读，不显示为空或"未知理由"
  - 守卫：前端读后端 py 源码抽枚举比对（逐值相等，一侧新增另一侧未跟进即红）+ 存量兼容 + 每个取值都有中文标签 + additive 零回归（不传 `reason_code` 的 payload 与基线逐字节相同）+ 源码级断言无第二次写入调用
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.7, 8.8, 8.9, 14.5_

- [ ] 13. 裁剪页接线：建议态、确认驳回、汇总闸、降级标注
  - `ProcedureTrimming.vue`：`confirmSmartTrim` 改为消费 Task 9 的上下文 + 调用 Task 7 决策内核（**不再自行判断**）
  - 建议态列与视觉状态（区别于"已裁剪"）+ 显示建议理由与判据数值
  - 逐条确认 / 批量确认 / 逐条驳回；确认走既有 canonical trim preview → apply（不新建写入路径，理由码经 Task 12 扩展的 `reason_code?` 字段随同一请求提交）；驳回写 `suggestion_state.rejected`
  - 确认后理由自动填入含判据数值的规范文本，保留用户补充说明能力
  - 汇总闸：批量确认前调用 Task 8，`blocked` 时阻断批量但允许逐条，逐条后重新计算并持续提示
  - 摘要区展示 `degradations` 标注（「未做重要性联动：本项目未确定重要性水平」/「未做风险联动：B50 未填写」），**标注与实际执行必须一致**
  - 建议态统计（建议数 / 已确认数 / 已驳回数）在裁剪页与全项目概览可见
  - 裁剪方案导出同时含理由码列与理由文本列
  - 守卫：建议态产生路径不含适用性写入调用（源码级）+ 重要性类 reason_code 不走自动裁路径 + 导出双列
  - _Requirements: 3.1, 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 7.3, 8.6, 4.5_

- [ ] 14. 完整性清单项目级覆盖入口
  - `ProcedureTrimming.vue` 或 B50-3 加逐循环开关面板，落 `checklist_responses` 键 `B50-T3-cscope-{cycle}`（`conclusion` = `Y`/`N`，`remark` = 覆盖理由）
  - 覆盖动作留痕操作人与时间（复用 `checklist_responses` 既有字段），理由必填
  - 未覆盖时使用平台默认，并在裁剪摘要标注「使用平台默认，未经本项目确认」
  - 守卫：`B50-T3-cscope-*` 行不改变 `load_b50_accounts()` 任何输出（既不产生科目项也不改既有字段）
  - _Requirements: 5.5, 5.6, 5.7_

- [ ] 15. 委派向导展示后端已下发的负载与受影响底稿
  - `ProcedureTrimming.vue` 委派向导：展示 preview 已返回的 `membership_load.active_task_count`（执行人当前非终态任务数）与 `affected_workpapers`（受影响底稿清单，可展开）
  - 负载缺失时显示「负载未知」而非 `0`（0 会误导为"这个人很空闲"）
  - 保留前端执行人 ≠ 复核人的即时提示，但注释明确后端为权威（`assert_sod_distinct` 在 preview 与 apply 逐 task 双查）
  - **后端零改动**（这两个字段 preview 早已返回，现状前端 `membership_load` / `active_task_count` grep **0 命中** = dead output）
  - 🔴 `affected_workpapers` 是**同名不同源**字段：委派 preview 侧是 `{wp_index_ids, wp_ids}` 对象，而调整分录影响预览侧是 `string[]` 或 `ImpactWorkpaper[]` ⇒ **不得复用 `ImpactPreviewPanel` / `AdjustmentImpactPreview` 的渲染组件**
  - _Requirements: 10.1, 10.2, 10.6, 10.7_

- [ ] 16. 负载口径统一
  - 删除 `ProcedureTrimming.vue` 的 `assigneeLoadMap` 前端自算实现（按"底稿张数"且仅在打开全项目概览后才有值，与后端"非终态任务数"口径不同 = 双真源）
  - 底稿主编下拉与委派向导的负载展示改读后端同一口径，进入委派界面即可用（不依赖先打开其他抽屉）
  - 新建 `composables/__tests__/delegationLoadSingleSource.spec.ts`：源码级断言前端不存在按底稿计数聚合负载的逻辑 + 缺失显示「负载未知」+ 两处展示同源
  - _Requirements: 10.3, 10.4, 10.5, 10.6_

- [ ] 17. 建议分配算法纯函数
  - 新建 `composables/delegationSuggestion.ts`：`suggestDelegation(input)` → `{assignments, loadAfter, degraded, warnings}`
  - 算法：按风险降序 → 每张底稿选「资历满足该风险等级 且 加权负载最小」的成员 → 复核人取「资历不低于执行人 且 非执行人本人」中负载最小者 → 累加负载后继续
  - 权重 `1 + riskCoefficient + rowCount / 20`，`riskCoefficient` = `H:1.0 / M:0.5 / L:0.2 / null:0.3`
  - `riskDimensionAvailable === false` → 退化为纯负载均衡，`degraded = true` + warnings 含「未做风险匹配」
  - 单测 + PBT：每条 assignment 满足 `reviewerStaffId !== assigneeStaffId`、`loadAfter` 单调不减且总增量等于所分配权重之和、降级标注
  - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.9, 11.10_

- [ ] 18. 建议分配表组件
  - 新建建议分配表组件：底稿粒度清单 + 每行执行人/复核人可改 + 移除行 + 每人分配后负载对比条
  - selector 用 `kind: 'workpaper'`（后端已支持，现状前端只用 `cycle`）
  - 展示每行 `rationale`（为何这样分），使审计师能判断是否接受
  - 应用前展示负载对比，使不均衡一眼可见
  - _Requirements: 11.1, 11.6, 11.8_

- [ ] 19. 建议分配应用走既有委派路径
  - 应用复用既有 `previewProcedureDelegation` → `applyProcedureDelegation` 两阶段与 `request_id` 幂等
  - 多个执行人 → 按执行人分组多次 preview/apply（每组一个 `assignee_staff_id`），逐组结果汇总展示
  - 任一组 409（预览过期/版本变化/成员变更）→ 提示重新预览该组，不影响已成功组
  - 守卫：源码级断言本 spec 不新增任何直接写 `procedure_row_tasks` 分配字段的代码路径
  - _Requirements: 11.7, 14.1_

- [ ] 20. 裁剪充分性复核视图
  - 新建只读复核视图组件：各循环保留/已裁/建议待确认/缺理由计数 + 理由码分布 + 因重要性原因裁剪的金额合计与重要性水平对比
  - 高亮异常组合：高风险或特别风险科目被裁、缺理由的裁剪、使用平台默认完整性清单未经确认
  - 支持从任一异常项跳转到对应循环并定位
  - 视图为**只读**（不含任何写入调用），统计数值由裁剪决策同一真源派生（相同输入下与裁剪页统计逐项相等）
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 21. 附注反向联动
  - 某科目循环程序被整体裁剪 → 该科目对应附注章节可标注为本期不适用
  - **复用附注既有机制**：`disclosure_notes.is_empty` + `note_content_utils.note_has_data`（与 `NoteWordExporter._has_content` 收敛的共享 helper，归档 spec `disclosure-notes-selective-generation` Req2 已建）；`disclosure_engine` 已按 `is_empty` 产出 `status: "not_applicable"` ⇒ **不新建第二套不适用字段或判定逻辑**（新建即双真源，会让附注树标记与 Word 导出结果漂移）
  - 标注**不删除**章节或模板结构（保留可恢复性）；裁剪撤销时标注相应撤销
  - 该章节存在人工录入内容时**只提示不自动标注**
  - 联动为加法式，既有附注同步链路输出逐字节不变
  - 附注章节无法定位 → 跳过并记录，不阻断裁剪保存
  - 守卫：源码级断言不存在第二套不适用标注字段（只写 `is_empty`，判定只调既有共享 helper）
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

- [ ] 22. 变异检验
  - 新建 `backend/scripts/check/mutate_trim_decision_guards.py`
  - 至少 12 个变异，逐个必须 RED：移除风险保护 · 移除认定级优先 · 汇总闸去掉去重 · 汇总闸纳入 `no_data` · `>=` 改 `>` · 移除 `body == item_id` 守卫 · 移除底稿已录入判据 · 移除驳回判据 · 让重要性类走自动裁 · 降级标注与执行不一致 · 移除 `overall_materiality` 禁用约束 · 前端另算负载
  - **判据按失败测试名集合求差集**（不看退出码 —— Wave 1 守卫基线本身可能有红），并区分三态：`new_fails` 非空 = RED 有效 / 空 = **守卫缺陷** / 某条基线红转绿 = 亦为有效信号
  - 锚点必须行级唯一且 `hits == 1`（多命中或零命中 = ANCHOR-MISS 脚本缺陷，不得当 GREEN 处理）
  - 备份落 `.bak` 并提供 `--restore`；`try/finally` 无条件写回；变异后以 md5 核验字节级还原
  - 锚点禁用跨行字面量（工作树多为 CRLF，含 `\n` 的锚点必 MISS）
  - 「降级标注与实际执行一致」这条须有独立守卫（双向断言：标注含 materiality ⟺ 结果集无重要性类 reason_code；标注含 risk ⟺ 无因风险保护而 keep 的项），且对应变异必须打红
  - _Requirements: 14.3, 14.4, 14.7_

- [ ] 23. 零回归验证
  - `no_data` 自动裁集合与改造前逐条一致 —— ⚠️ **真实库 `procedure_instances.status` 436 行全为 `execute`、0 条已裁剪**，故该零回归只能用**构造输入的 characterization** 验证，报告中**不得声称已在真实库比对过**
  - canonical trim 未携带 `reason_code` 时 preview/apply 的请求 payload 与基线逐字节相同
  - 委派 preview / apply 对外契约字段逐字段不变（新增字段为 additive）
  - `load_b50_accounts` 既有三类键解析结果与扩展前逐字节相同（复用 Task 1 冻结的快照）
  - 既有附注同步链路输出逐字节不变
  - **零回归判据用「施加改动前 vs 施加改动后」前后对照**，禁用「把改动文件换成 `git show HEAD:` 版跑同一组」（本仓库并发度高，HEAD 侧可能含他人未提交成果，且被 Ctrl+C 打断时 HEAD 版会留在工作树）
  - _Requirements: 14.1, 14.2, 14.6_

- [ ] 24. CI job
  - `.github/workflows/governance-checks.yml` 新增两个 job：`procedure-trim-intelligence`（后端守卫 + 变异脚本 + 迁移幂等）与 `procedure-trim-intelligence-frontend`（前端纯函数守卫 + 交叉锁死）
  - 加挂前用 `yaml.safe_load` 验证可解析并核对 job 名无重名（平台曾出现同名 job 被静默去重、前一个从未运行）
  - 引用的测试文件必须全部已存在（否则 CI 红）
  - _Requirements: 14.4, 14.5_

- [ ] 25. 真实库验收
  - 新建 `backend/scripts/diagnose/verify_trim_decision_live.py`（默认只读）
  - 覆盖三种项目状态并如实报告：有重要性无 B50 / 无重要性无 B50 / 有试算表数据
  - 逐项目输出：三维可用性、`degradations`、各 verdict 计数、汇总闸结果、完整性豁免命中数与判据层级分布
  - 某状态在库中不存在时输出 `UNVERIFIABLE` 而非用 fixture 冒充通过
  - 连库时用**专用一次性 engine**（`poolclass=NullPool`）并在同一 loop 内 `dispose()`，不借用共享连接池（避免 `Event loop is closed` 双向污染）
  - 中文输出前设 `PYTHONIOENCODING=utf-8`，或直接写盘不 print（GBK 控制台会在写库前崩）
  - _Requirements: 14.8_

- [ ] 26. 浏览器实测与数据复原
  - 实测六项：建议态展示 · 逐条确认 · 批量确认 · 汇总闸阻断 · 委派建议分配表 · 负载对比
  - 实测前抓完整基线：目标行的 `suggestion_state` / `skip_reason` / `checklist_responses` 行数 / 相关 md5 与 `updated_at`
  - 实测后复原，并以**独立查询**核实（不看操作脚本自身输出）：`suggestion_state` 回 null、`skip_reason` 与基线逐字相等、`checklist_responses` 行数回到基线
  - 复原脚本写在 `engine.begin()` 事务内；JSONB 列赋值直接传 dict（传 `json.dumps` 会写成 JSON 字符串标量，`jsonb_typeof` 变 `string` 而下游全失效）
  - 实测中若发现只有浏览器能暴露的缺陷（如传了不存在的 prop、宿主漏传参数、命名导出缺失），一并修复并补守卫
  - _Requirements: 14.9, 14.10_

## Notes

### 与并发 spec 的边界

- **`h-cycle-extraction-formula-and-disclosure-completion`**（Task 18 为有意驻留的浏览器实测）：无文件交集。
- **`e-cycle-extraction-formula-and-disclosure-completion`** / **`soe-listed-note-conversion-correctness`** / **`note-template-columns-and-legacy-snapshot-closure`**：均在附注侧，与本 spec 唯一潜在交集是 Task 21（附注反向联动）。Task 21 为加法式且不改附注同步链路输出，若届时这三个 spec 仍在活跃，Task 21 应最后做并在做前重查它们对附注模板 JSON 的改动状态。
- **`sampling-compliance-closure`**：抽样侧，无交集。
- **`custom-workpaper-dual-mode-formula-and-batch`**：自定义底稿侧，无交集。

### 已知不做（避免后续会话重复提议）

- **不重建 B50 录入 UI 与 B50×B15 联动面板**：均已完整（含 `suggestedTeRatio` 风险×重要性建议 TE 比例）。
- **不改 `GtB50RiskAssessment.vue` 内既有的 `pm`/`te`/`sat` 命名**：动它会波及该组件 12 条 PBT；只约束新代码。
- **不改 `risk_assessments` / `risk_matrix_records` 两张表**：全库 0 行且 B50 数据实际落在 `checklist_responses`；这两张表的定性属另一个议题。
- **不把决策内核搬到后端**：裁剪是交互式决策，见 design 的架构理由。
- **不用 `overall_materiality` 推算 `performance_materiality`**：缺失即缺失（R4.6）。
- **不新建第二套委派写入路径**：一律走 `ProcedureDelegationService`。

### 真实库现状事实（影响验收判据，落地前必读）

- **`procedure_instances.status` 436 行全为 `execute`，0 条 `not_applicable` / `skip`** ⇒ ①粗裁功能上线以来实际未产生任何裁剪结果 ②Task 23 的 `no_data` 零回归在真实库**无数据可比**，只能用构造输入 ③`ProcedureDelegationService._trimmed_scopes()` 恒返空集 ⇒ **「裁剪→委派联动」逻辑正确但从未有数据流经过**（同族于平台已登记的「链条上游合格、整条链仍是死的」），本 spec 落地后它才第一次真正生效 —— Task 26 浏览器实测应顺带验证「裁掉某底稿后它不再出现在委派目标里」
- **`checklist_responses` 全库 `B50-T3-*` 0 行** ⇒ B50 从未被填写过；Task 25 的「有 B50」状态须输出 `UNVERIFIABLE`
- **`materiality` 仅 2 个项目有数据**（而 14 个项目有 `procedure_instances`）
- **`procedure_row_tasks` 仅 3 个项目 46 行** ⇒ 行级委派几乎未被使用，Task 17/18 的建议分配表在多数项目上会先触发 materialize 前置

### 实测目标候选

真实库 14 个项目有 `procedure_instances`，其中 2 个有 `materiality` 数据、0 个有 B50 数据。故：

- 「有重要性无 B50」→ 用那 2 个有 materiality 的项目
- 「无重要性无 B50」→ 其余 12 个任一
- 「有 B50」→ 当前**无此状态**，Task 25 须输出 `UNVERIFIABLE`；若要覆盖，需先在测试项目上手工填几个科目的 B50 认定（实测后复原）
