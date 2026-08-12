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

- [x] 1. Wave 1 守卫先打红：B50 三字段解析与完成度口径
  - 新建 `backend/tests/procedure_trim/test_b50_reader_extension.py`
  - **类 A（现在应全绿）**：`checklist_responses` 中 `B50-T3-balance-*` 的独立计数查询可执行；`_parse_matrix_item_id` 对 `B50-T3-balance-*` / `-category-*` / `-estimate-*` / `-cscope-*` 一律返回 `None`；冻结 `load_b50_accounts` 对既有 cycle/plan/matrix 三类键的输出快照（作 Task 2 的零回归基线）
  - **类 B（现在应全红）**：返回项含 `balance` / `category` / `is_estimate` 三键；未录入时为 `None` 而非 `0`/空串
  - **反向自检**：移除 `body == item_id` 守卫后，`B50-T3-balance-货币资金` 必须被误判成矩阵格（证明该守卫是防误判的唯一保障）；无该样本时 `pytest.skip` 并在 reason 写明「暂不可验证，⚠️ 不等于可省掉该守卫」
  - 全库 `B50-T3-*` 为 0 行 → 类 A 的存在性断言须按「查询可执行且返回 0」而非「必须有数据」
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 14.6_

- [x] 2. `load_b50_accounts()` additive 补三字段
  - `backend/app/services/b50_risk_reader.py`：新增解析 `B50-T3-balance-{account}`（取 `remark` 转 float，失败为 `None`）/ `-category-{account}` / `-estimate-{account}`，填入返回项 `balance` / `category` / `is_estimate`
  - 既有 cycle / plan / matrix 三个分支**逐字不动**；`_parse_matrix_item_id` 的 `body == item_id` 守卫**保留**
  - `load_b50_risks()` 不受影响（它只消费 `cells`）
  - 跑 Task 1 守卫：类 B 转绿、类 A 保持绿、既有输出快照零差异
  - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6_

- [x] 3. B50 填写完成度纯函数与面板
  - 新建 `audit-platform/frontend/src/components/workpaper/composables/b50Completeness.ts`：`resolveB50Completeness({accounts})` → `{state: 'not_started' | 'partial' | 'completed', importedCount, assessedCount, unassessedAccounts}`；三态判据 = 导入数为 0 → `not_started`；每个导入科目至少一个认定有 RMM → `completed`；其余 `partial`
  - `GtB50RiskAssessment.vue` 加完成度面板（加法式）：三态徽标 + 已导入/已评估计数 + 未评估科目清单（点击定位到该行）+ 零科目时提示「可从试算表一键导入」并给出既有 `applyScopeAccounts` 入口
  - **不改任何录入逻辑**，不碰该组件既有的 `pm`/`te`/`sat` 命名
  - 新建 `composables/__tests__/b50Completeness.spec.ts`：三态边界 + 未评估清单准确性 + 纯函数无 Vue 依赖
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.7_

- [x] 4. 裁剪页 B50 状态徽标与跳转
  - `ProcedureTrimming.vue`：展示 B50 填写状态徽标（复用 Task 3 同一纯函数，禁另算一份），非 `completed` 时提供跳转 B50-3 的入口
  - 徽标 tooltip 说明「风险联动依赖 B50 认定层次风险矩阵」，使审计师理解未填的后果而非只看到一个状态词
  - 守卫：徽标取值与 B50 面板同源（源码级断言两处引用同一函数）
  - _Requirements: 2.5, 2.6, 2.7_

- [x] 5. Wave 2 守卫先打红：决策内核 / 完整性豁免 / 汇总闸
  - 新建 `composables/__tests__/procedureTrimDecision.spec.ts`、`completenessExemption.spec.ts`、`trimAggregateGate.spec.ts`
  - **类 A（现在应全绿）**：`materiality` 表列存在性与三个字段可读；`scope-accounts` 端点确实返回 `amount` 字段（读源码断言）；现状智能裁剪**丢弃 `amount`**（源码级断言 `confirmSmartTrim` 未引用 `amount`，作改造前基线）；`TrimReasonCode` 现有取值域快照
  - **类 B（现在应全红）**：三个纯函数模块存在且导出约定接口
  - **反向自检**：`overall_materiality` 不得出现在决策输入类型中；扫描面非空自检（防正则失效导致断言空转）
  - _Requirements: 3.1, 3.11, 7.7, 14.4_

- [x] 6. 完整性豁免纯函数与默认清单
  - 新建 `composables/completenessExemption.ts`：`COMPLETENESS_CYCLE_RULES`（声明式真源，11 个科目余额驱动循环各带 `rationale`；默认开 L/J/N/K/**D**，默认关 E/F/G/H/I/M）+ `resolveCompletenessExemption()`
  - **认定级优先**：`completenessRmm` 非 null 或 `completenessSpecial` 为真时只按认定判定，完全不看循环级清单，`source = 'assertion'`
  - `usingPlatformDefault` 当且仅当 `source === 'cycle_default'`
  - 守卫：每条 `rationale` 长度 ≥ 20 且非占位；清单不含 A/B/C/S；认定级与循环级结论冲突时以认定级为准
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7, 5.8_

- [x] 7. 裁剪决策内核纯函数
  - 新建 `composables/procedureTrimDecision.ts`：`decideTrim(input): TrimDecision`，按 design 的 9 档顺序短路
  - 输出恒含 `verdict` / `reasonCode` / `narrative` / `evidence` / `hints`；`keep` 时 `reasonCode` 为 null，其余两态非 null
  - `evidence` 记录本次实际使用的判据数值与来源标识（科目余额、所用重要性口径及金额、B50 风险等级、完整性判据层级、`risk_unknown` 标记）
  - 零 IO、零 Vue 依赖；输入类型中**不存在** `overall_materiality`
  - 单测覆盖：9 档逐条 + 短路性（命中靠前判据时靠后判据取值变化不改变 verdict）+ 风险未知既不保护也不裁 + 驳回标记恒 keep + 底稿已录入恒 keep（含「程序待执行 + 底稿有录入」组合）+ 不信赖控制提示不改变 verdict
  - PBT（`max_examples` 20）：特别风险/高风险恒 keep、重要性类恒 `suggest_trim`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 4.3, 4.6, 6.4, 9.1, 9.2, 9.3, 9.6_

- [x] 8. 汇总闸纯函数
  - 新建 `composables/trimAggregateGate.ts`：`evaluateAggregateGate()` → `{applicable, distinctAccountCount, totalAmount, threshold, blocked, narrative}`
  - 三条易被"优化"掉的约束：只计入 `below_trivial` / `below_materiality`、按 `accountName` 去重、判据 `>=` 而非 `>`
  - `performanceMateriality === null` 时 `applicable = false` 且 `blocked = false`（无比较基准）
  - 单测 + PBT：去重正确性、阈值方向、重要性缺失路径
  - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7_

- [x] 9. 后端判据上下文装配
  - 新建 `backend/app/services/trim_decision_context.py`：`build_trim_decision_context(db, project_id, year, cycles)` 一次性装配 `accounts` / `materiality` / `risk` / `risk_dimension_available` / `completeness_override` / `workpaper_entry` / `degradations`
  - 任一维度取数失败 → 该维度置 `None` 并往 `degradations` 记一条，**不抛异常也不伪造默认值**
  - 试算表读取失败或零科目 → 保持现有阻断兜底语义（上下文使前端阻断裁剪，且区分「读取失败」与「未导入」两种成因）
  - `performance_materiality` 缺失但 `overall_materiality` 存在时**不推算**，按缺失处理
  - `completeness_override` 读 `checklist_responses` 的 `B50-T3-cscope-{cycle}`；读取失败退回平台默认并记 degradation
  - 新增端点或在既有裁剪相关端点上 additive 下发该上下文（不新建第二套取数路径）
  - 守卫：`backend/tests/procedure_trim/test_trim_decision_context.py` —— 三个维度各自的降级路径 + `degradations` 结构 + 不推算断言 + 试算表不可用阻断（含复现旧行为的替身必须打红）
  - _Requirements: 3.1, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.5, 5.6_

- [x] 10. 底稿已录入批量探测
  - 新建 `backend/app/services/workpaper_entry_probe.py`：`probe_workpaper_entries(db, project_id, wp_codes)` → `dict[str, bool]`
  - 判据 = 该底稿存在 `checklist_responses` 行（`conclusion` 或 `remark` 非空）或 `working_paper.parsed_data` 非空
  - **批量一次查询**，查询次数与 wp_code 数无关；查询失败 → 全部返回 `True`（保守保留）并记 WARNING
  - 写连库 SQL 前先查真实列名（`checklist_responses` 的底稿外键是 **`wp_id`** 不是 `workpaper_id`）
  - 守卫：批量化（源码级断言无按 wp_code 循环发查询的结构）+ 失败兜底 + 真实列名可执行性（真跑一次查询，异常即红，不只做源码断言）
  - _Requirements: 9.1, 9.2, 9.4, 9.5_

- [x] 11. 迁移：`procedure_instances.suggestion_state`
  - **落地前重查** `schema_version` 与 `backend/migrations/` 取当前最大迁移号 +1（design 写的 V145 只是示意，并发 spec 可能已占用；迁移号永不复用）
  - `ALTER TABLE procedure_instances ADD COLUMN IF NOT EXISTS suggestion_state JSONB;`（幂等）
  - **同步加 ORM `mapped_column`**（否则列存在而代码写不进去）
  - 结构：`{reason_code, rejected, rejected_by, rejected_at, evidence}`
  - 配套 rollback 脚本（按平台 `R1xx__` 命名约定）
  - 守卫：迁移幂等（二次应用零变更）+ ORM 与迁移列集精确相等（列清单由**扫全部 `V*.sql`** 派生，禁手写按迁移号分组的常量）
  - _Requirements: 6.4, 8.1_

- [x] 12. 理由码真源统一与交叉锁死
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

- [x] 13. 裁剪页接线：建议态、确认驳回、汇总闸、降级标注
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

- [x] 14. 完整性清单项目级覆盖入口
  - `ProcedureTrimming.vue` 或 B50-3 加逐循环开关面板，落 `checklist_responses` 键 `B50-T3-cscope-{cycle}`（`conclusion` = `Y`/`N`，`remark` = 覆盖理由）
  - 覆盖动作留痕操作人与时间（复用 `checklist_responses` 既有字段），理由必填
  - 未覆盖时使用平台默认，并在裁剪摘要标注「使用平台默认，未经本项目确认」
  - 守卫：`B50-T3-cscope-*` 行不改变 `load_b50_accounts()` 任何输出（既不产生科目项也不改既有字段）
  - _Requirements: 5.5, 5.6, 5.7_

- [x] 15. 委派向导展示后端已下发的负载与受影响底稿
  - `ProcedureTrimming.vue` 委派向导：展示 preview 已返回的 `membership_load.active_task_count`（执行人当前非终态任务数）与 `affected_workpapers`（受影响底稿清单，可展开）
  - 负载缺失时显示「负载未知」而非 `0`（0 会误导为"这个人很空闲"）
  - 保留前端执行人 ≠ 复核人的即时提示，但注释明确后端为权威（`assert_sod_distinct` 在 preview 与 apply 逐 task 双查）
  - **后端零改动**（这两个字段 preview 早已返回，现状前端 `membership_load` / `active_task_count` grep **0 命中** = dead output）
  - 🔴 `affected_workpapers` 是**同名不同源**字段：委派 preview 侧是 `{wp_index_ids, wp_ids}` 对象，而调整分录影响预览侧是 `string[]` 或 `ImpactWorkpaper[]` ⇒ **不得复用 `ImpactPreviewPanel` / `AdjustmentImpactPreview` 的渲染组件**
  - _Requirements: 10.1, 10.2, 10.6, 10.7_

- [x] 16. 负载口径统一
  - 删除 `ProcedureTrimming.vue` 的 `assigneeLoadMap` 前端自算实现（按"底稿张数"且仅在打开全项目概览后才有值，与后端"非终态任务数"口径不同 = 双真源）
  - 底稿主编下拉与委派向导的负载展示改读后端同一口径，进入委派界面即可用（不依赖先打开其他抽屉）
  - 新建 `composables/__tests__/delegationLoadSingleSource.spec.ts`：源码级断言前端不存在按底稿计数聚合负载的逻辑 + 缺失显示「负载未知」+ 两处展示同源
  - _Requirements: 10.3, 10.4, 10.5, 10.6_

- [x] 17. 建议分配算法纯函数
  - 新建 `composables/delegationSuggestion.ts`：`suggestDelegation(input)` → `{assignments, loadAfter, degraded, warnings}`
  - 算法：按风险降序 → 每张底稿选「资历满足该风险等级 且 加权负载最小」的成员 → 复核人取「资历不低于执行人 且 非执行人本人」中负载最小者 → 累加负载后继续
  - 权重 `1 + riskCoefficient + rowCount / 20`，`riskCoefficient` = `H:1.0 / M:0.5 / L:0.2 / null:0.3`
  - `riskDimensionAvailable === false` → 退化为纯负载均衡，`degraded = true` + warnings 含「未做风险匹配」
  - 单测 + PBT：每条 assignment 满足 `reviewerStaffId !== assigneeStaffId`、`loadAfter` 单调不减且总增量等于所分配权重之和、降级标注
  - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.9, 11.10_

- [x] 18. 建议分配表组件
  - 新建建议分配表组件：底稿粒度清单 + 每行执行人/复核人可改 + 移除行 + 每人分配后负载对比条
  - selector 用 `kind: 'workpaper'`（后端已支持，现状前端只用 `cycle`）
  - 展示每行 `rationale`（为何这样分），使审计师能判断是否接受
  - 应用前展示负载对比，使不均衡一眼可见
  - _Requirements: 11.1, 11.6, 11.8_

- [x] 19. 建议分配应用走既有委派路径
  - 应用复用既有 `previewProcedureDelegation` → `applyProcedureDelegation` 两阶段与 `request_id` 幂等
  - 多个执行人 → 按执行人分组多次 preview/apply（每组一个 `assignee_staff_id`），逐组结果汇总展示
  - 任一组 409（预览过期/版本变化/成员变更）→ 提示重新预览该组，不影响已成功组
  - 守卫：源码级断言本 spec 不新增任何直接写 `procedure_row_tasks` 分配字段的代码路径
  - _Requirements: 11.7, 14.1_

- [x] 20. 裁剪充分性复核视图
  - 新建只读复核视图组件：各循环保留/已裁/建议待确认/缺理由计数 + 理由码分布 + 因重要性原因裁剪的金额合计与重要性水平对比
  - 高亮异常组合：高风险或特别风险科目被裁、缺理由的裁剪、使用平台默认完整性清单未经确认
  - 支持从任一异常项跳转到对应循环并定位
  - 视图为**只读**（不含任何写入调用），统计数值由裁剪决策同一真源派生（相同输入下与裁剪页统计逐项相等）
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [x] 21. 附注反向联动
  - 某科目循环程序被整体裁剪 → 该科目对应附注章节可标注为本期不适用
  - **复用附注既有机制**：`disclosure_notes.is_empty` + `note_content_utils.note_has_data`（与 `NoteWordExporter._has_content` 收敛的共享 helper，归档 spec `disclosure-notes-selective-generation` Req2 已建）；`disclosure_engine` 已按 `is_empty` 产出 `status: "not_applicable"` ⇒ **不新建第二套不适用字段或判定逻辑**（新建即双真源，会让附注树标记与 Word 导出结果漂移）
  - 标注**不删除**章节或模板结构（保留可恢复性）；裁剪撤销时标注相应撤销
  - 该章节存在人工录入内容时**只提示不自动标注**
  - 联动为加法式，既有附注同步链路输出逐字节不变
  - 附注章节无法定位 → 跳过并记录，不阻断裁剪保存
  - 守卫：源码级断言不存在第二套不适用标注字段（只写 `is_empty`，判定只调既有共享 helper）
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

- [x] 22. 变异检验
  - 新建 `backend/scripts/check/mutate_trim_decision_guards.py`
  - 至少 12 个变异，逐个必须 RED：移除风险保护 · 移除认定级优先 · 汇总闸去掉去重 · 汇总闸纳入 `no_data` · `>=` 改 `>` · 移除 `body == item_id` 守卫 · 移除底稿已录入判据 · 移除驳回判据 · 让重要性类走自动裁 · 降级标注与执行不一致 · 移除 `overall_materiality` 禁用约束 · 前端另算负载
  - **判据按失败测试名集合求差集**（不看退出码 —— Wave 1 守卫基线本身可能有红），并区分三态：`new_fails` 非空 = RED 有效 / 空 = **守卫缺陷** / 某条基线红转绿 = 亦为有效信号
  - 锚点必须行级唯一且 `hits == 1`（多命中或零命中 = ANCHOR-MISS 脚本缺陷，不得当 GREEN 处理）
  - 备份落 `.bak` 并提供 `--restore`；`try/finally` 无条件写回；变异后以 md5 核验字节级还原
  - 锚点禁用跨行字面量（工作树多为 CRLF，含 `\n` 的锚点必 MISS）
  - 「降级标注与实际执行一致」这条须有独立守卫（双向断言：标注含 materiality ⟺ 结果集无重要性类 reason_code；标注含 risk ⟺ 无因风险保护而 keep 的项），且对应变异必须打红
  - _Requirements: 14.3, 14.4, 14.7_

- [x] 23. 零回归验证
  - `no_data` 自动裁集合与改造前逐条一致 —— ⚠️ **真实库 `procedure_instances.status` 436 行全为 `execute`、0 条已裁剪**，故该零回归只能用**构造输入的 characterization** 验证，报告中**不得声称已在真实库比对过**
  - canonical trim 未携带 `reason_code` 时 preview/apply 的请求 payload 与基线逐字节相同
  - 委派 preview / apply 对外契约字段逐字段不变（新增字段为 additive）
  - `load_b50_accounts` 既有三类键解析结果与扩展前逐字节相同（复用 Task 1 冻结的快照）
  - 既有附注同步链路输出逐字节不变
  - **零回归判据用「施加改动前 vs 施加改动后」前后对照**，禁用「把改动文件换成 `git show HEAD:` 版跑同一组」（本仓库并发度高，HEAD 侧可能含他人未提交成果，且被 Ctrl+C 打断时 HEAD 版会留在工作树）
  - _Requirements: 14.1, 14.2, 14.6_

- [x] 24. CI job
  - `.github/workflows/governance-checks.yml` 新增两个 job：`procedure-trim-intelligence`（后端守卫 + 变异脚本 + 迁移幂等）与 `procedure-trim-intelligence-frontend`（前端纯函数守卫 + 交叉锁死）
  - 加挂前用 `yaml.safe_load` 验证可解析并核对 job 名无重名（平台曾出现同名 job 被静默去重、前一个从未运行）
  - 引用的测试文件必须全部已存在（否则 CI 红）
  - _Requirements: 14.4, 14.5_

- [x] 25. 真实库验收
  - 新建 `backend/scripts/diagnose/verify_trim_decision_live.py`（默认只读）
  - 覆盖三种项目状态并如实报告：有重要性无 B50 / 无重要性无 B50 / 有试算表数据
  - 逐项目输出：三维可用性、`degradations`、各 verdict 计数、汇总闸结果、完整性豁免命中数与判据层级分布
  - 某状态在库中不存在时输出 `UNVERIFIABLE` 而非用 fixture 冒充通过
  - 连库时用**专用一次性 engine**（`poolclass=NullPool`）并在同一 loop 内 `dispose()`，不借用共享连接池（避免 `Event loop is closed` 双向污染）
  - 中文输出前设 `PYTHONIOENCODING=utf-8`，或直接写盘不 print（GBK 控制台会在写库前崩）
  - _Requirements: 14.8_

- [x] 26. 浏览器实测与数据复原
  - 实测六项：建议态展示 · 逐条确认 · 批量确认 · 汇总闸阻断 · 委派建议分配表 · 负载对比
  - 实测前抓完整基线：目标行的 `suggestion_state` / `skip_reason` / `checklist_responses` 行数 / 相关 md5 与 `updated_at`
  - 实测后复原，并以**独立查询**核实（不看操作脚本自身输出）：`suggestion_state` 回 null、`skip_reason` 与基线逐字相等、`checklist_responses` 行数回到基线
  - 复原脚本写在 `engine.begin()` 事务内；JSONB 列赋值直接传 dict（传 `json.dumps` 会写成 JSON 字符串标量，`jsonb_typeof` 变 `string` 而下游全失效）
  - 实测中若发现只有浏览器能暴露的缺陷（如传了不存在的 prop、宿主漏传参数、命名导出缺失），一并修复并补守卫
  - 🔴 **阻塞原因（2026-08-11 登记并当日修正，有意驻留而非被中断）**：⚠️ 先前登记的「无 Playwright 工具」**是错的,已作废** —— Playwright 作为项目 CLI 依赖可用（`@playwright/test ^1.52.0` 已装、`playwright.config.ts` 在位、289 个既有 e2e 用例、`webServer` 配置会自动起前端 3030 且 `reuseExistingServer`）⇒ **不是工具阻塞**。真实阻塞三条：①真实库 `procedure_instances` **0 条已裁剪**、`checklist_responses` 的 `B50-T3-*` **0 行**（Task 25 连库实证）⇒ 清单 13 项里过半必须先造数据；②平台 e2e 既定约定是用 `backend/scripts/e2e/seed_fix_projects.py --fix` 造**专用 FIX 项目**（`globalSetup` 已在跑它），**不应改真实业务项目** —— 落地前须先确认 FIX 项目是否具备 `procedure_instances` / `materiality` / `tb_balance` 三者，否则裁剪页无判据可算；③实测要写库（建议态→确认→canonical apply / B50 认定录入 / 逐循环覆盖），须按基线复原并以**独立查询**核实，且 `procedure_row_task_history` 是 append-only（DELETE 会被触发器拒），复原方案须按此设计 ⇒ 需人在场执行。
  - ✅ **已完成的前置（2026-08-11，全程零写库）**：①**实测目标已定** = e2e 指定项目 `2aa00f57-1df4-4fe8-9840-2d65d0fd8749`（重庆和平药房连锁有限责任公司_2025），只读实证它具备裁剪页三样前置：`procedure_instances` 61 条（0 已裁剪）/ `materiality` 1 行 / `tb_balance` 1176 行 / `wp_index` 324 / `procedure_row_tasks` 3 ⇒ **不必碰真实客户项目**。②**基线工具已建并双向验证** = `backend/scripts/e2e/trim_e2e_baseline.py`（`--capture` / `--verify` 只读，`--restore` 是唯一写库开关，单事务）：基线覆盖 `procedure_instances`(status/skip_reason/suggestion_state) · `checklist_responses` 的 `B50-T3-*` · `procedure_row_tasks`(执行人/复核人/两个 workflow 状态) · `disclosure_notes`(is_empty/template_lineage) · 两张 history 表行数。**负控制**（篡改基线副本）逐项捕获 3 个可复原字段 + 4 个不可复原项；**正控制**（真实基线）0 差异。③**三条不可复原项已在脚本内钉死**：`lock_version` / `assignment_version` 是单调计数器（只报差值不回写，回写会破坏乐观锁语义）、`procedure_row_task_history` 与 `workpaper_delegation_history` 是 append-only（只报新增行数）⇒ 复原后**不得声称字节级一致**。④JSONB 回写一律 `CAST(:v AS jsonb)`，`--restore` 后有一条 `jsonb_typeof(suggestion_state) <> 'object'` 计数断言专钉「写成 JSON 字符串标量」这个坑。
  - ⬜ **剩余（需人在场）**：写 Playwright 用例覆盖六项（建议态展示 · 逐条确认 · 批量确认 · 汇总闸阻断 · 委派建议分配表 · 负载对比）并真跑。`playwright.config.ts` 的 `webServer` 会自动起 3030（`reuseExistingServer`），`globalSetup` 已在跑 `seed_fix_projects.py --fix`；但该 seed **不造** `procedure_instances` / `materiality` / `tb_balance`（三词 0 命中），故 B50 认定仍需另行录入才能覆盖依赖 B50 的项（清单第 9 项）。流程：`--capture` → 跑 e2e → `--verify` 看漂移 → `--restore` → 再 `--verify` 独立复核。
  - 🟢 **Playwright 用例已写并跑到全绿（2026-08-11，六轮迭代，全程零写库）**：新建 `audit-platform/frontend/e2e/procedure-trim-intelligence.spec.ts`（**8 个 test**；写库项 26.6/26.7 由 `TRIM_E2E_WRITE=1` 门控、默认 skip）。跑法 `SKIP_E2E_SEED=1 npx playwright test e2e/procedure-trim-intelligence.spec.ts --workers=1`（`globalSetup` 的 `seed_fix_projects.py --fix` 会写库，本轮不需要 FIX 夹具故跳过）。**终轮 rc=0：5 passed / 3 skipped / 0 failed。**✅ **26.1 = 整个 spec 第一次在浏览器里被证实**：裁剪页挂载**零致命错误**（`pageerror` + console error 全收，ReferenceError/TypeError 一律不过滤）且八列齐（含 Task 13 新增的「裁剪建议」列）⇒ Task 13 那 5 个零声明标识符的修复真的生效。✅ **26.2**：「逐循环设置 →」面板本体真渲染、五列齐 ⇒ Task 14 的渲染宿主在位。✅ **26.3a**：`GET /procedure-delegations/member-loads` 返 200 且 `loads` 为**数字**映射 ⇒ Task 16 收敛出的负载单一真源出口可用（值若为 null/字符串会让前端三态判断失效）。✅ **26.4**：附注联动面板三态可区分（未知 / 显式空 `el-empty` / 有表格），并补了**第四态**（有 degradations 时 `el-empty` 被隐藏而分桶表也不渲染）—— 该态只坚持底线：面板不得空白且须说明原因。✅ **26.5**：走「仅当前循环」点通 `confirmSmartTrim` 全链（该分支是**内存应用**，须再点「💾 保存粗裁」才落库 ⇒ 真跑决策内核而仍零写库）；**同源判据**（建议态条 ⟺ 建议列 cell）与 `.gt-proc-degrade-bar` 降级标注块**双双满足**。⚪ **26.3b 按结构化原因 skip（此项不算通过）**：只读实证本 e2e 项目 **`project_users = 0`** ⇒ 执行人下拉为空 ⇒ 委派预览与「执行人当前负载」**结构上不可达**（另：3 条行任务已全部分配、仅覆盖 1 张底稿）。判据显式 skip 并写明成因，**不拿不可达当合格**，也不误报成 Task 15 的 dead output 未修复。
  - 🔴 **拆 26.3a/26.3b 是因为判据的可见性也是判据质量**：两者同处一个 test 时，`test.skip` 会把**已经跑过并通过**的端点断言一起显示成 skipped —— 一次真实验证被报成「未验证」。拆开后端点验证以 pass 形式可见。
  - 🔴 **四轮迭代里全部 4 条失败都是「我方判据缺陷」，无一条产品缺陷**（值得作平台经验）：①`getByRole(columnheader, 平台默认)` 未加 `exact` 被「平台默认依据 / 覆盖理由」二次命中触发 strict mode violation，以「列缺失」形态**假红**而面板其实渲染成功；②降级标注按 tasks.md 的**描述**猜文案写成 `/未做风险联动/`，而后端真实文案是「B50 无已评估认定（未填写重大错报风险等级）或读取失败」⇒ 改为按结构锚 `.gt-proc-degrade-bar` + 真实 label 断言；③智能裁剪确认按钮按 `/确定|开始|执行|应用/` 猜，真实文案是「确认一键裁剪」⇒ 一次都没点中，于是 `loadTrimContext` 从未被调用、降级标注块自然不存在（顺带定性：该函数有 7 个调用点但 **`onMounted` 里没有**，首屏 `trimContext` 为 null 是设计使然 —— 标注文案是「**本次**裁剪判据的维度可用性」，语义绑在一次裁剪运行上 ⇒ **不是 R4.4 回归**）；④`执行人当前负载` 受 `v-if="delegateWizard.preview"` 门控，只开向导不点「预览」永远不渲染。⇒ 再次实证「判据的扫描面与它声称覆盖的输入空间不一致时，红和绿都不可信」。
  - 🟢 **基线工具已扩收 `project_users`，并被一次真实写入端到端验证过（2026-08-11）**：`trim_e2e_baseline.py` 新增 `project_users` 域（唯一索引是 `(project_id, user_id) WHERE is_deleted = false` ⇒ 按 `user_id` 判；**只支持「新增成员 → 删除」这一对**，`role` / `permission_level` 是 enum，改动一律落 NOTE 不自动回写 —— 盲目 CAST 到未知枚举类型会在事务里炸掉，把「复原」变成「更坏的写入」）。端到端实证链：插入 1 行成员 → `--verify` **精确报 1 条 `<DELETE>`、零误报** → `--restore` → **独立查询**（postgres 只读，不看脚本自身输出）核实 `project_users = 0`、插入行已消失、裁剪侧 `status/suggestion_state` 零漂移、`B50-T3-*` 仍 0 行。⇒ 复原路径不再是纸面设计。
  - 🔴 **26.3b 的真前置不是 `project_users`（我先猜错并写了一行，已复原）**：`loadTeamMembers()` 调的是 `listAssignments(projectId)` 并按 `a.staff_id` 过滤 ⇒ 执行人下拉喂的是**项目派工**（带 staff_id 的 assignment 行），不是项目成员表。加 `project_users` 行对下拉毫无作用（实测:加完 26.3b 仍 skip）。⇒ 要验 26.3b 必须先造带 `staff_id` 的派工行，且**基线工具需先扩收该表**才能可靠复原（顺序反了就会「改了库但复原不了」）。教训与平台已登记的同族：**前置条件也要实证，不能按名字猜**（`project_users` 听起来就是「项目成员」，而喂下拉的是另一条链）。
  - 🟢 **基线工具已扩到六个域并经两次真实写入→复原端到端验证（2026-08-11）**：`trim_e2e_baseline.py` 现收 `procedure_instances` · `checklist_b50` · `row_tasks` · `disclosure_notes` · **`project_users`** · **`project_assignments`**（后者是真源，前者是 `save_assignments` 顺带 upsert 的**派生**结果 —— 实测造 2 条派工即自动生成 2 条成员行）。第二次验证链：经**既有写入服务** `AssignmentService.save_assignments` 造 2 条派工（不裸 INSERT）→ `--verify` **精确报 4 条 `<DELETE>`（2 真源 + 2 派生），零误报零漏报** → `--restore` 单事务删 4 行 → 脚本内**复原后独立重读**报残留 0 项、`jsonb_typeof(suggestion_state) <> object` 行数 0 → 再用 **postgres 只读**交叉核实：`project_assignments` 0 · `project_users` 0 · 裁剪侧 `status/suggestion_state` 漂移 0 · `B50-T3-*` 0 行 · 行任务仍 3。
  - ✅ **26.3b 已通过（2026-08-11 终验，2.6s）**：造 2 条派工后向导预览产出、「执行人当前负载」渲染，判据「在办 N 项 / 负载未知，**绝不显示 0**」成立 ⇒ Task 15 的 dead output 修复与 Task 16 的负载单一真源在真实浏览器下双双生效。**根因确认为我探针的时序**：EP 下拉是 teleport 到 body 的**异步** popper，click 后立即 `count()` 恒得 0 ⇒ 把「未渲染」误当成「无可选执行人」而假 skip；改为显式 `waitFor({state:"visible"})` 后转绿。两条「像产品缺陷」的假设此前已静态排除并记档：①`list_assignments` 返回 dict **确实含** `staff_id`（JOIN 无额外过滤）②`utils/http.ts` 响应拦截器**已统一解包**信封（`if ("code" in d && "data" in d) response.data = d.data`）⇒ `listAssignments` 不会恒返空。**Playwright 终态：rc=0，6 passed / 2 skipped（仅剩写库项）/ 0 failed。**
  - 🔴 **实测暴露一条不可逆副作用（本 spec 此前未登记，直接影响写库项方案）**：**委派预览会同步物化行任务** —— 26.3b 跑完 `procedure_row_tasks` 从 **3 → 27**（+24 行，`assignee_staff_id` 仍为空），与 Task 19 实录「`materialization_pending` 已是死分支、改同步物化」互相印证。⇒ ①**「预览」不是只读操作**，任何含预览的实测都会永久增加行任务；②基线工具**如实把 24 行报成 `[NOTE] row_tasks 新增行（基线里没有，不自动删）`**（不静默忽略、不谎报「已完整复原」），但**不会自动清除** —— 删它们有风险：`procedure_row_task_history` 是 append-only（触发器拒 DELETE），删任务会留下孤儿历史行。⇒ 写库项 26.6/26.7 落地前必须先决定这 24 行的处置口径（保留并接受漂移 / 扩基线工具做级联清理 + 想清楚孤儿历史）。本轮**保留未删**，并已在此登记漂移事实。
  - 🔴 **写库项 26.6/26.7 仍 skip；「默认循环是 A」这条假设已被实测推翻**：已在 `openTrimPage` 里加了 `switchToDataDrivenCycle()`（按 Tab 文本首字母取 D~N，取不到即打红并把现有 Tab 清单写进报错），切换成功后**仍然 0 建议** ⇒ 成因不是激活循环。数据侧已排除：`performance_materiality = 26,104,487` / `trivial_threshold = 2,610,448.70`，481 个非零科目里 **370 个低于 PM**，`below_materiality` 类本该大量产出。**下一轮的两条待查线索**：①**科目名解析**——`resolveAccountName(p, ctx)` 解析不到时 `accountAmount` 为 null，重要性档直接跳过（Task 20 实录已登记「金额无法定位」这一态）；②**重要性未进上下文**——`_load_materiality` 按 `(project_id, year)` 取，若 e2e 项目的 `audit_year` 与 `materiality` 行的年度不一致，则上下文里 materiality 为 None（库里有行 ≠ 上下文取到）。
  - 🔴 **顺带暴露我自己判据的一处不足（已登记，下轮先补）**：26.5 对降级标注只断言 `.gt-proc-degrade-bar` 存在且 `.el-tag` 数 > 0，**没断言是哪个维度** ⇒ 无法区分「风险降级」（预期，B50 全库 0 行）与「重要性降级」（若真如此，正好解释 0 建议）。⇒ 判据应改为**断言维度集合**（如恰含 `risk`、且在有 materiality 行的项目上**不得**含 `materiality`），否则它只能证明「有降级」而不能证明「降级的是该降的那个」。同族于本 spec 反复登记的：判据只覆盖到「有没有」而没覆盖到「是不是对的那个」时，绿也不可信。
  - ⬜ **剩余（仅写库项）**：按上两条先取证（落 `trimContext.degradations` 的真实内容 + 某条程序的 `resolveAccountName` 结果）→ 让建议态真产出 → 再跑 26.6/26.7。流程 `--capture` → `TRIM_E2E_WRITE=1` → `--verify` → `--restore` → 再 `--verify`；⚠️ 落地前先定那 24 行物化行任务的处置口径。当前基线：`procedure_instances` 61 · `checklist_b50` 0 · `row_tasks` 27 · `disclosure_notes` 213 · `project_users` 0 · `project_assignments` 0。**Playwright 现态 rc=0，5 passed / 3 skipped / 0 failed**（26.3b 因复原后无派工而 skip，属预期；有派工时已实测通过）。
  - ⬜ **剩余（仅写库项）**：①先按上条切数据驱动循环让建议态产出，再跑 26.6（逐条确认 → `suggestion_state.reason_code` 真落库，独立 API 复核）与 26.7（汇总闸 blocked 阻断批量但允许逐条）；②流程 `--capture` → `TRIM_E2E_WRITE=1` → `--verify` → `--restore` → 再 `--verify`；③⚠️ 落地前先定那 24 行物化行任务的处置口径（见上条不可逆副作用）。基线现状（已把物化漂移固化为新基线）：`procedure_instances` 61 · `checklist_b50` 0 · `row_tasks` **27** · `disclosure_notes` 213 · `project_users` 0 · `project_assignments` 0。复原路径已**三次**实证（篡改副本反向自检 · project_users · project_assignments，均经 postgres 只读交叉核实）。
  - ⬜ **剩余**：①26.3b 按上条先取证再定判据；②写库项 26.6/26.7 走 `--capture` → `TRIM_E2E_WRITE=1` → `--verify` → `--restore` → 再 `--verify`（复原路径现已双次实证，可放心用）；③依赖 B50 的项须先录入认定（全库 `B50-T3-*` 至今 0 行），实测后须让行数回到 0。⚠️ 顺带登记一个基线脚本的小缺陷：`--out` 指定路径时偶发不落盘（`--capture` 与首次 `--restore` 各出现一次，退出码仍 0）⇒ 判成败别只看 `--out` 文件是否存在，要查 `backend/data/trim_e2e_baseline.json` 或直接连库核。
  - ✅ **写库项四条全通过，Task 26 收口（2026-08-12）**。终态 Playwright：只读部分 **5 passed / 5 skipped / 0 failed**；写库项按两轮跑法各 **2 passed**。回归：后端 `backend/tests/procedure_trim/` **328 passed / 1 skipped**、前端三个 `ProcedureTrimming.vue` 守卫 **167 passed**。
  - 🟢 **「0 建议」的两个成因已取证，都不是缺陷（此前两条待查线索一并结案）**：拦 `trim-decision-context` 响应实测 `materiality={"pm":26104487,"tt":2610448.7}` 且 `degradations` **只含 `risk`** ⇒ **线索②（重要性未进上下文）排除**。真成因是：①**D 循环 17 条** —— `COMPLETENESS_CYCLE_RULES` 的 D `sensitiveByDefault=true`，而 `decideTrim` 的**档 5 完整性豁免排在档 7/8 重要性之前** ⇒ 全部 keep（9 档设计使然：完整性方向的漏记与账面金额无关，用金额豁免它方向就是反的）；②**E 循环 5 条** —— 程序名一律「货币资金 …」而 `trial_balance` 里没有名为「货币资金」的行、只有明细「其他货币资金」/「银行存款」⇒ `resolveAccountName` 的「程序名 includes 科目名」单向子串规则匹配不上 ⇒ `accountAmount` 为 null ⇒ 档 7/8 跳过（「宁缺勿造」的正确行为）。**顺带实证档 4 真生效**：D5 应收款项融资 / D7 合同负债被判 `no_data` 自动裁 ⇒ 真实库历史上第一次产生裁剪结果。
  - 🔴 **顺带纠正一条此前登记的错口径**：`_load_accounts` 读的是 **`trial_balance`（本项目 58 行 / 54 个非零科目）**，不是 `tb_balance`（1176 行）⇒ 前几轮写的「481 个非零科目里 370 个低于 PM」是 `tb_balance` 口径，**与决策内核实际入参不同源**，不能用来推断建议应有多少条。D 循环经 `cycle_for_account` 过滤后 `accounts` 实为 4 个：应收账款 151,273,548 / 营业收入 1,044,179,479 / 预收账款 13,656,018 / 坏账准备-应收账款 406,014。
  - 🔴 **发现并修复一个真产品缺陷：Task 14 的写入端点在真实库上恒 500（112 例守卫 + 14/14 变异全绿而功能是死的）**。`PUT /api/projects/{pid}/procedure-trim/completeness-scope` 返回 500，根因 `CAST(:ts AS timestamptz)` 配 `now.isoformat()` → `asyncpg DataError: expected a datetime.date or datetime.datetime instance, got 'str'`。**UUID 与 timestamptz 的正确写法方向相反**：UUID 是 `CAST + str(uuid)`（不 CAST 则 `operator does not exist: uuid = character varying`），timestamptz 是 `CAST + datetime 对象`（写了 CAST 后 asyncpg 即把该参数推断为 timestamptz，遂要求 datetime）—— 「CAST 了就该传字符串」这个直觉对 UUID 成立、对时间戳恰好相反，而生产代码注释里那句"传 datetime 给未声明类型的参数同样会 DataError"把方向记反了。**为什么 56 后端 + 56 前端 + 14 变异全绿**：写入行为的 9 例全走 `_WriteSession` **替身**，替身不做参数编码；源码级断言只看到「CAST 写了、参数传了」；变异脚本的 14 条也都在这两层内 ⇒ **「替身单测 + 源码级断言」对参数编码类缺陷结构性无效**。修 2 处（INSERT / UPDATE 的 `ts`）；全平台同族排查 `AS timestamptz)` **仅此一处**，`now_iso` / `rejected_at` 等都是写进 JSONB 的 ISO 串（正确）。
  - 🟢 **为该缺陷补了 3 条守卫并做变异检验**（`test_completeness_scope_override.py` 56 → **59**）：①`test_live_write_roundtrip_insert_update_list_delete` —— 真实库上真跑 INSERT/UPDATE/list 读回/DELETE 四条路径，动态找一个有 B50 底稿的项目、用哨兵 cycle `ZZLIVETEST`、**末尾无条件 rollback（零写库）**；rollback 不削弱判据强度，因为 asyncpg 的参数编码发生在 `execute` 时刻。②反向自检 —— 钉死「`CAST($n AS timestamptz)` 传字符串必被拒」这条**驱动行为事实**，驱动哪天放宽了它会打红，提醒后人「那条连库守卫已不再针对原缺陷」。③源码级 —— `"ts": now` 形态断言（与前两条互补：连库那条在库不可达时会 skip，源码这条不依赖库；但源码这条单独不够，换成 `str(now)` 同样会炸而它看不出）。**变异检验 RED 有效**：改回 `isoformat()` 后连库判据 + 源码级判据**双双打红**，反向自检按设计保持绿（三态判定正确，不是守卫缺陷）。端到端复验：PUT 200 `created:true` / GET 读回含理由与留痕（updated_by_name=admin）/ DELETE 200 `deleted:1` / GET-final 空；postgres 只读核实哨兵行 0 残留。
  - 🟢 **让 26.6/26.7 从「结构不可达」变为可达 —— 不造假数据，而是用 Task 14 的生产功能改判**：把 D 循环经覆盖面板设为**完整性不敏感**（面板 alert 本就明文写着「项目组可结合客户舞弊动机方向关闭」，这是审计师的判断权），档 5 短路随之解除 ⇒ D3 预收账款 13,656,018 < `performance_materiality` 26,104,487 ⇒ 档 8 产出 `below_materiality`。**这条路径比原计划更强**：它顺带端到端实证了「Task 14 的覆盖开关真的改变裁剪判据」（`setCompletenessScope` 成功后重刷 `loadTrimContext`），而不只是"面板能点开"。写库落点全在基线工具覆盖域内。
  - ✅ **26.6a**（覆盖生效 → 建议态产出）：当前生效值 敏感 → **不敏感**、覆盖理由回显；重跑智能裁剪后建议态条与逐行建议列同时出现，理由码标签实测为「**金额低于实际执行重要性**」（断言其必属重要性类，证明走的是档 7/8 而非别的档碰巧产出）。
  - ✅ **26.7**（汇总闸）：实测 `blocked=false`，闸门叙述**真写出了判据数值** —— 「本次建议裁剪科目 1 个（已按科目去重），金额合计 13,656,018.02 元，低于实际执行重要性 26,104,487.00 元，汇总错报敞口在可容忍范围内，可批量确认。」⇒ Task 8 的去重、阈值方向、不误阻断三条约束在真实数据上首次验证。**blocked 分支结构不可达**（D 循环唯一可解析且低于 PM 的科目只有预收账款一个，单条合计永远达不到 26,104,487）—— 如实登记，**不为凑分支造数据**。
  - ✅ **26.6b**（逐条确认 → 落库）：独立 API 复核 + postgres 只读双查，D3 落库为 `status=not_applicable` · `suggestion_state={'reason_code':'below_materiality'}` · `jsonb_typeof=object`（**没踩「写成 JSON 字符串标量」那个坑**）· `skip_reason` 与理由码**并列同事务**且含判据数值（「本期科目余额 13,656,018.02 元低于实际执行重要性 26,104,487.00 元…」）⇒ **Task 12 的 `reason_code` 扩展在真实库首次落库**，整条核心链路（三维判据 → 建议态 → 确认 → 理由码落库）第一次完整跑通。
  - ✅ **26.9**（收尾撤销）：撤销后当前生效退回平台默认「敏感」、覆盖理由不再回显 ⇒ 后端确实**删行**而非写空值（R5.5）。这也让跑完后的 `checklist_b50` 漂移为 0（无需靠 `--restore` 兜底），本身即 26.9 有效的旁证。
  - 🟢 **26.5 判据已从「有没有降级」升级到「降的是不是该降的那个」**（上一轮自我登记的不足已补）：新增 `captureTrimContext()` 拦 `trim-decision-context` 响应取**结构化** `degradations[].dimension` —— DOM 上 `el-tag` 只渲染 `d.text`（中文措辞），**拿不到维度**，而「有降级」在「重要性维度也降级」时同样为真，那恰是 0 建议的另一种成因且结论相反。三条新断言：**DOM tag 数 == API degradations 数**（跨层同源，防悄悄吞掉一个法定维度的降级告知）· **必须含 `risk`**（B50 全库 0 行是真实状态；若 `risk_dimension_available` 为 true 则可用性判据失真）· **不得含 `materiality`**（库里确有本年度行，含它即判据断链）。另加一条「整轮未拦到 context 响应即打红」防判据空转。
  - 🔴 **本轮 5 条失败又全部是「我方判据缺陷」，无一条产品缺陷（与前四轮同族，累计 9 条）**：①**按钮文案又猜错**——`setCompletenessScope` 的真实 `confirmButtonText` 是「**保存覆盖**」、`revertCompletenessScope` 是「**撤销覆盖**」，我按 `/确定|确认/` 匹配 ⇒ 一次没点中而以「保存未生效」形态假红（本 spec **第 5 次**同族，此后一律照抄源码 confirmButtonText）；②**`.el-message--success` 不区分来源**——被**前置步骤自己**（智能裁剪的「已自动裁剪 N 个…」）满足，断言通过而库里零变化 ⇒ 改用**网络请求**（`/procedure-trim/(preview|apply)` 的 POST）作硬判据，它是 `confirmSuggestion` 唯一的写库出口；③**复核端点漏 cycle 段**——真实是 `/api/projects/{pid}/procedures/{cycle}`，我写成 `/procedures` 得 404，会以「理由码未落库」形态假红；④**`locator.click()` 恒报 `intercepts pointer events`**——遮挡者是带 `.gt-fade-in` 的根容器，而按钮 rect (652,606) 在视口内、祖先链全 `pointer-events:auto`、滚动容器未裁切、注入 `animation:none` 后现象不变 ⇒ 改用 `page.mouse.click(x,y)`（**浏览器真实输入事件**，走 Chromium 自己的 hit-testing）；并配一条 `dispatchEvent` **定性诊断**把「产品缺陷（handler 没绑上）」与「命中层假阳性」分开 —— 这一步是关键，否则用 dispatchEvent 直接绕过就等于掩盖缺陷；⑤**交叉核实查询漏 `is_deleted` 过滤**——`disclosure_notes` 全表 215 vs 基线口径 213，那 2 行是 11 天前的软删遗留，差点被我误报成本轮漂移 ⇒ **交叉核实查询必须与基线工具同口径，否则交叉核实自己会造假漂移**。
  - 🟢 **顺序依赖用「两轮跑法」解决，不改文件声明顺序**：26.6b 一确认就把唯一建议行转成 `not_applicable`，此后 26.7 会以「当前无建议态」skip（执行顺序造成的不可达，不是真实结论）。故 `--restore` → `--grep "26\.6a|26\.7"` → `--grep "26\.6b|26\.9"`。文件里 26.7 排在 26.6b 之后，注释已写明这条跑法与理由。
  - 🟢 **复原与独立核实（三段式，全部通过）**：跑完 `--verify` **精确报 3 项**（D3 的 status / skip_reason / suggestion_state；`checklist_b50` 因 26.9 已在 UI 撤销故 0 漂移）→ `--restore` 单事务回写 → 脚本内复原后独立重读**残留 0 项**且 `jsonb_typeof(suggestion_state) <> object` 行数 **0** → 再 `--verify` **0 差异** → **postgres 只读交叉核实**（不看脚本输出）：`procedure_instances` 61 / 已裁剪 **0** / 带 suggestion_state **0** / 带 skip_reason **0** · `checklist_responses` 的 `B50-T3-*` **0 行** · `procedure_row_tasks` **27**（本轮无委派预览，未新增物化）· `project_assignments` 0 · `project_users` 0 · `disclosure_notes`(is_deleted=false) **213** ⇒ 全部回到基线。
  - ⬜ **遗留（非本任务范围，建议另立 spec）**：**`resolveAccountName` 覆盖不了「报表项目 ↔ 明细科目」的层级差异**。程序按报表项目组织（E1「货币资金」、D2「应收账款」），而 `trial_balance` 存的是明细科目名（「其他货币资金」/「银行存款」）⇒ 单向子串匹配在 E 循环 5 条程序上全部落空、重要性维度**整体空转**。这不是 bug（宁缺勿造是正确的），但意味着**重要性判据在很多项目上会大面积不可用**。平台已有「报表项目 → 科目码」映射真源（`report_config` DB 表），可据此改造；改造会动 Task 7/13/20 的判据行为，须重跑变异检验与零回归 ⇒ 不在 Task 26 里顺手改。另：26.7 的 `blocked` 分支与 26.3b 的委派预览需要造数据才可达，已各自登记结构化原因。
  - _Requirements: 14.9, 14.10_

## Notes

### 与并发 spec 的边界

- **`h-cycle-extraction-formula-and-disclosure-completion`**（Task 18 为有意驻留的浏览器实测）：无文件交集。
- **`e-cycle-extraction-formula-and-disclosure-completion`** / **`soe-listed-note-conversion-correctness`** / **`note-template-columns-and-legacy-snapshot-closure`**：均在附注侧，与本 spec 唯一潜在交集是 Task 21（附注反向联动）。Task 21 为加法式且不改附注同步链路输出，若届时这三个 spec 仍在活跃，Task 21 应最后做并在做前重查它们对附注模板 JSON 的改动状态。
- **`sampling-compliance-closure`**：抽样侧，无交集。
- **`custom-workpaper-dual-mode-formula-and-batch`**：自定义底稿侧，无交集。

### 已知不做（避免后续会话重复提议）

- **不重建 B50 录入 UI 与 B50×B15 联动面板**：均已完整（含 `suggestedTeRatio` 风险×重要性建议 TE 比例）。
- **不改 `GtB50RiskAssessment.vue` 内既有的 `pm`/`te`/`sat` 命名**：动它会波及该组件 12 条 PB；只约束新代码。
- **不改 `risk_assessments` / `risk_matrix_records` 两张表**：全库 0 行且 B50 数据实际落在 `checkTlist_responses`；这两张表的定性属另一个议题。
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

## Progress Log

### Wave 3 已交付（Task 15 + 16，2026-08-08）

**产出**

- 后端 `ProcedureDelegationService.member_workloads(project_id) -> dict[str, int]`：GROUP BY 一次查完全项目执行人非终态任务数，与既有 `_assignee_workload` **同口径**（docstring 写明口径一致性要求，两者一改必须同改）。
- 后端 `GET /api/projects/{pid}/procedure-delegations/member-loads`（只读，挂 `require_project_delegator_pid`，返回 `{"loads": {...}}`）。
- 前端 `apiPaths/workpaper.ts` 新增 `delegationMemberLoads`（挂在已被 barrel re-export 的 `procedureRowTasks` 对象内 ⇒ 无需改 `apiPaths/index.ts` 的具名 re-export 清单）+ `commonApi.fetchDelegationMemberLoads()`。
- `ProcedureTrimming.vue`：删 `assigneeLoadMap` / `assigneeLoadLoaded` 前端自算实现；新增 `memberLoads`（三态，null=未知）/ `loadMemberLoads()` / `memberLoadOf()` / `memberLoadLabel()`（未知显示「负载未知」，绝不显示 0）；`onMounted` 即加载（不依赖先打开全项目概览）；新增 `previewSummary` / `previewAssigneeLoad` / `affectedWorkpapers` 三个 computed；预览统计改读嵌套 `summary` 真实键并新增「将新分配 / 将转派 / 无需变更 / 执行人当前负载」；新增受影响底稿折叠清单（wp_ids → wp_code 映射，映射不到时如实显示「N 张（编号待解析）」）；SOD 即时提示补注「后端为权威」注释。

**顺带修掉一个 spec 未记的真缺陷**：预览统计原读 `preview.target_count ?? preview.targets` / `conflict_count` / `assigned_count` —— **后端三个字段名都不存在**（真实值在嵌套 `summary` 下）⇒ 目标数与已分配恒显示「—」、冲突数恒 0，而这正是审计师判断委派影响面的唯一依据。apply 侧顶层字段读法本来是对的，只有 preview 侧读错层。修法为只读 `summary` 真实键、读不到显示「—」，**不做跨字段名 fallback**（fallback 会让「读错层」以显示错数的形式被掩盖）。

**守卫**

- `backend/tests/procedure_trim/test_member_workloads.py`（**15 passed**）：含 `_code_lines()` / `_func_code()` / `_raw_func()` 剥注释 helper（tokenize 剥 `#` + AST 剥 docstring）+ 两条剥注释反向自检。
- `audit-platform/frontend/src/views/__tests__/delegationLoadSingleSource.spec.ts`（**21 passed**）：stripComments 状态机 + 双哨兵 repoRoot + 跨前后端交叉锁死（端点路径比对 + `summary` 键名比对）+ 3 条反向自检。
- 变异检验 **10/10 全 RED**（脚本支持函数内定向替换）。过程中修掉 4 个自身问题：M6/M8 首轮 GREEN = 守卫未剥注释被自己的说明文字骗过；M5/M7 ANCHOR-MISS = 锚点缩进错 + 跨行锚点（CRLF）。

**零回归（前后对照，未用 HEAD-swap）**

`-k "delegation or procedure_trim or trimming"` 得 **25 failed / 694 passed**。用「移除新端点 → 跑 → 装回 → 跑」的前后对照法逐条判定：**AFTER 与 BEFORE 失败集合逐条相同（7 条），新增 0 / 消失 0，还原字节相等** ⇒ 25 个失败全部预存在。成因分四类：

1. **sqlite 缺表**（`test_procedure_delegation_characterization` 等）：wp_gate 在 sqlite 下查 `project_users` / `staff_members` / `wp_visibility_policy_epoch` 全部 `no such table` → 分类失败 → 统一 404。
2. **DB append-only 触发器**（14 条 PG 连库用例）：测试 fixture 执行 `DELETE FROM procedure_row_task_history` 撞 `procedure_row_task_history is append-only` 保护。
3. **ledger 长期漂移**（`test_task16_coverage_guard` 3 条）：`missing_in_ledger=178` / `stale=2` / `fake_pass=1`；实测 ledger 里连既有的 `procedure-delegations/preview|apply` 都是 **0 命中** ⇒ 该 spec 的端点从来不在 ledger 覆盖范围内。
4. **常量过期**：`NEXT_MIGRATION_FILENAME` 期望 `V105__procedure_row_tasks.sql` 而实际已到 `V112__procedure_current_revision_registry.sql`（2 条）。

**另定性一条平台级预存在缺陷**：`test_task9_dedicated_route_gate::test_all_dedicated_routes_have_gate_dependency` 失败（`496 == 497`），缺 gate 的那条是 **`b60_chapters.get_chapter_definitions`** —— 该 router 在 `router_registry/system.py` L212 与 `router_registry/workpaper.py` 的加 gate 循环里**被 include 了两次**，产生一条无 gate 的重复路由。本 spec 新增端点所在模块 `app.routers.procedure_delegations` **不在** `DEDICATED_COMPONENT_ROUTER_MODULES` 名单内且其 router 无 `{wp_id}` 路由，故不受该守卫约束（既有 preview/apply 的 `route.dependencies` 同样为空）。

**验证汇总**：后端 15 passed / 前端 21 passed / 三个改动前端文件 Vite transform 全 200 / barrel 完整性已核 / 变异 10/10 RED。

**未做（按 spec 分工留给后续任务）**：浏览器实测归 Task 26 统一做（本轮改动为纯展示层 + 只读端点，无写库路径）。

---

## Wave 1 交付实录（Task 1~4，2026-08-08）

### 产出

| 文件 | 性质 |
|---|---|
| `backend/tests/procedure_trim/test_b50_reader_extension.py` | 新建守卫 23 例（类 A 15 / 类 B 8） |
| `backend/app/services/b50_risk_reader.py` | additive 补三字段解析 |
| `audit-platform/frontend/src/components/workpaper/composables/b50Completeness.ts` | 新建纯函数（三态 + 两侧归一） |
| `.../composables/__tests__/b50Completeness.spec.ts` | 新建守卫 21 例 |
| `.../workpaper/GtB50RiskAssessment.vue` | 加法式完成度面板 |
| `audit-platform/frontend/src/views/ProcedureTrimming.vue` | B50 状态徽标 + 跳转 |
| `.../views/__tests__/b50BadgeSingleSource.spec.ts` | 新建守卫 22 例 |
| `services/apiPaths/system.ts` + `services/commonApi.ts` | 登记既有端点访问器 + 取数函数 |

### 验证

- 后端 `tests/procedure_trim/` **38 passed**；前端 B50 域 6 文件 **111 passed**（含既有 12 条 PBT 零回归）
- 6 个前端文件 Vite transform 全 **200**；无重复顶层导出
- **变异检验 10/10 全 RED**，`.bak` 零残留、字节级还原核验通过
- 零回归前后对照（禁 HEAD-swap）：`-k "b50 or b60 or risk_reader"` 两侧失败集合**逐条相同**，新增 0

### 落地时修正的 spec 描述（照 tasks.md 原文会做错）

1. **Task 1 的反向自检样本证明不了它要证明的东西**。原文写「移除 `body == item_id` 守卫后 `B50-T3-balance-货币资金` 必须被误判成矩阵格」，而 `_parse_matrix_item_id` 有**三道互相独立**的闸（前缀锚定 / suffix 白名单 / assertion 白名单）；该样本末段是 `货币资金`，移除闸 1 后会被**闸 2** 挡住 ⇒ 证明不了闸 1 承重。改用能穿透闸 2/3 的构造样本 `B50-T3-otherprefix-货币资金-existence-RMM`，并**额外留一条断言**把「spec 原样本被闸 2 挡住」这个事实钉死，防后续会话按原文改回去（改回去会得到「移除闸 1 仍返回 None」的假绿结论，进而误判闸 1 可删）。

2. **Task 4 不需要新建后端端点**。既有 `GET /api/b60/b50-risk-rows`（`b60_data_pull.py`，本为 B60 六/七章一键带入而建）直接返回 `load_b50_accounts()` 输出 ⇒ 裁剪页取 B50 完成度**零后端改动**。已在 commonApi 的 docstring 里写明「不要为此新建 `/api/b50/risk-rows`」—— 否则同一份 B50 认定层次数据会有两个读取口径。

3. **`riskAssessments` 已在 apiPaths barrel 内**，新增访问器无需改 `index.ts`（该 barrel 用具名 re-export，只有新增顶层对象才要改三处清单）。

### 平台级事实（新增实证，后续会话可直接引用）

- **前端写 B50-3 三列的值列不同**：`B50-T3-balance-*` 值在 **`remark`**（数值字符串），`-category-*` / `-estimate-*` 值在 **`conclusion`**。照抄同一列会让其中两个恒空。取值域：`category ∈ {scot, amount_only, other}`、`estimate ∈ {Y, N}`。
- **`useB50RiskMatrix.incompleteAccounts` 与本 spec 完成度口径不同且都要保留**：前者「六认定全填」（矩阵是否编完），后者「至少一个认定有 RMM」（风险数据能否用于裁剪判据）。同一份数据下两者结论可以相反，`b50Completeness.spec.ts` 有一条断言把该差异钉死 —— 统一到严格口径会让「只填了关键认定」的项目在裁剪页恒显示「B50 未填」。
- **完成度判据取最原始的 `cells[*].rmm` 而非派生的 `max_risk`**：读派生值会让「后端派生逻辑变了」与「数据变了」不可区分。

### 本轮踩到并已修的守卫缺陷（3 个，均由变异检验暴露）

1. `expect(src).toContain('resolveB50Completeness')` 在 computed 被整体换成写死值后**仍然通过** —— 标识符还在 import 行里。⇒ 改断言 **computed 实参区**内真的调用了纯函数（新增 `computedArg` 圆括号配对 helper，同时支持表达式体箭头与花括号体两形态）。
2. 「加载失败保持未知」原只断言 **ref 声明**形态，抓不住 `catch` 里把 `null` 改成 `[]`（那会谎报"未开始"）。⇒ 补断言 catch 块内容 + 「未知态早退」存在。
3. `fnBody` 若按「声明后第一个 `{`」定位会命中**内联返回类型注解**（`Promise<{ fs_risks... }>`），截出来的"函数体"是那段类型 ⇒ 断言在无关文本上求值、把正确实现打红。已改花括号配对 + 语句特征筛选，并配自检。

### 变异脚本的两条经验

- **锚点含 `\n` 在 CRLF 工作树必 MISS**（首轮 10 条里 5 条 ANCHOR-MISS 全是此因）⇒ 一律**行级定位**（`splitlines()` + 锚点行号 + 相对偏移），与行尾无关。
- **ANCHOR-MISS 是第三种结果**，既不是 RED 也不是 GREEN：变异根本没施加，此时「测试仍绿」不能作为任何结论。脚本必须显式区分三态并断言命中数为 1。

### Wave 2 可直接复用的资产

- `test_b50_reader_extension.py` 里的 `_FakeSession`（按 SQL 文本分流 wp_index / checklist_responses 两条查询）
- `b50BadgeSingleSource.spec.ts` 里的 `stripComments`（带字符串状态，不被 `accept="image/*"` 骗）/ `fnBody` / `computedArg` / 双哨兵 `repoRoot`
- `b50Completeness.ts` 的 `normalizeFromReader`（Wave 2 的风险判据同样要从 `load_b50_accounts` 形态取 `cells`）
---

## Task 13 交付实录（2026-08-09）

### 一句话结论

tasks.md 把 Task 13 写成「接线」，**实证是整条建议态链从未跑通过** —— 5 个标识符全文零声明（运行即 `ReferenceError`）、5 个行字段零赋值点、`loadTrimContext` 零调用点。性质是**修 bug**，不是补功能。这也解释了为何真实库 `procedure_instances` 436 行 0 条已裁剪：粗裁之外的智能裁剪路径一执行就抛异常。

### 产出

| 文件 | 性质 |
|---|---|
| `audit-platform/frontend/src/views/ProcedureTrimming.vue` | 接线修复 + 概览侧 additive 统计 + 导出双列注释修正 |
| `.../src/views/__tests__/trimDecisionWiring.spec.ts` | 新建守卫 **42 例 / 8 suites**（756 行） |
| `backend/scripts/check/mutate_task13_wiring_guards.py` | 新建变异脚本 5 条，**5/5 全 RED** |

### 改了什么

**（1）5 个零声明标识符**（Volar / vitest / `get_diagnostics` / HEAD-swap **四层全绿**，只有浏览器挂载才暴露 —— SFC 模板表达式不参与 TS 类型检查，脚本里对 `any` 行对象赋任意字段也不报错）：

| 标识符 | 原状 | 修法 |
|---|---|---|
| `suggestions` | 赋值给一个从未声明的 ref | 删除（设计改为建议态挂程序行字段） |
| `TrimSuggestion` | 类型标注，**全仓不存在该类型** | 删除 |
| `suggestionOf` | 模板「裁剪建议」列调用 ×3，无声明 | 新增函数 + `clearRowSuggestion(row)` |
| `decisionContext` | 写 + `aggregateGate` 读，无声明 | 改模块级 `trimContext` |
| `loadDecisionContext` | 3 处 `await`，无声明 | 改 `loadTrimContext` |

**（2）3 条死路径**（符号名都在源码里出现过 —— 在注释、在读取侧、在 import 行，故任何「grep 到标识符即视为已接线」的判据都会静默通过）：

- `loadTrimContext` **原零调用点**（死代码）⇒ `trimContext` 永不被写 ⇒ `degradationNotes` 恒空 ⇒ **降级标注（R4.4）从未渲染过**。现 4 个调用点。而 tasks.md 已把降级标注列为完成项。
- `confirmSmartTrim` 内联了第二份 `fetchTrimDecisionContext` + `data-availability` 取数，其中两个同名局部 `const subjectWithData` / `subjectNoData` **遮蔽**模块级 ref，使模块 ref 恒空。已删内联取数，统一经 `loadTrimContext`。
- `resolveAccountName(p)` **缺第二参 `ctx`** ⇒ 修为 `resolveAccountName(p, ctx as TrimDecisionContext)`。

**（3）5 个行字段零赋值点**（只有读取侧）：`_suggest` / `_suggestReasonCode` / `_suggestNarrative` / `_decisionAccountName` / `_decisionEvidence` ⇒ 建议条计数恒 0、汇总闸恒空。现 `suggest_trim` 分支写入五字段 + `clearRowSuggestion` 逐行清理防重跑残留（漏清会让「已改判保留」的行继续算进建议数与汇总闸）。

**（4）概览侧建议态统计（additive）**：`overviewRows` **两处 return** 均加 `suggestConfirmed` / `suggestRejected`（早退分支返 0 —— 返 undefined 会让 `overviewTotals` 的 reduce 得 NaN）；`overviewTotals` 加两项 reduce；概览抽屉表格加 2 列 + 合计条加 2 项（`v-if > 0`）。后端 `procedure_service._to_dict` 已确认下发 `suggestion_state`，非死代码。

**（5）导出双列**：`exportScheme()` 表头 8 列 `['循环','编号','程序名称','适用性','裁剪理由','理由码','底稿主编','来源']`，行第 6 位 `applicable ? '' : (p.suggestion_state?.reason_code || '')`，`ws['!cols']` 8 项。注释里的机器理由码曾误写大写，已改为真源小写 snake（`no_data` / `below_trivial` / `below_materiality`）。

### 偏离 tasks.md 描述之处（5 处，均为落地实证与计划不符）

1. **「接线」实为「修 bug」**：见上。tasks.md 隐含前提是各部件已存在只需连起来，实证是 5 标识符零声明 / 5 行字段零赋值 / `loadTrimContext` 零调用 —— 整条链从未执行成功过。
2. **导出侧实现位置**：tasks.md 未指明，实证 `exportScheme()` 是**纯前端** `await import('xlsx')` + `XLSX.writeFile`，**无后端端点、无 Blob、无 csv 路径**。落地前若按「找后端导出端点」去改会全程找不到目标。
3. **建议态统计已存在**：预期命名 `suggestedCount` / `confirmedCount` / `rejectedCount`，实证已有 `suggestionStats`（含 `suggested` / `confirmed` / `rejected` 三键）⇒ 核实后**复用而非新建**，避免双真源。
4. **概览侧「待确认」口径不可派生，明确不做**：概览侧消费 `getProcedures` 的**原始行**（无 `_suggest` / `_applicable` —— 那两个字段是本页 `loadProcedures` 经 `decideTrim` 派生后才写回的）；跨循环重跑 `decideTrim` 需 per-cycle 三维判据上下文而概览侧拿不到，另造一套判据即第二真源。故概览侧只统计**已落地事实**：已确认 = `status ∈ {not_applicable, skip}` 且 `isMachineReasonCode(suggestion_state.reason_code)`；已驳回 = `suggestion_state.rejected === true`。守卫有一条断言钉死「概览侧不得读原始行上不存在的 `_suggest`」。
5. **降级标注（R4.4）此前从未渲染过**：tasks.md 已将其列为 Task 13 的完成项之一，实证因 `trimContext` 恒空而恒不显示。本轮一并修复，并加守卫断言其唯一来源是后端 `degradations`（前端不自行判断）。

### 守卫（42 例 / 8 suites，全绿）

| 组 | 例数 | 判据 |
|---|---|---|
| helper 五件套自检 | 6 | `fnBody` 跳过内联返回类型注解 / `stripComments` 不被 `accept="image/*"` 骗 |
| 判据 A | 9 | `suggest_trim` 分支只挂建议态、不写 `_applicable` / `status` / `skip_reason`（R6.2 红线）；`loadTrimContext` 有真实调用点；无内联第二份取数 |
| 判据 B | 9 | 重要性类恒建议永不自动裁；`auto_trim` 恰 1 次且必为 `no_data`；汇总闸只计两码；批量过闸而逐条不过闸 |
| 判据 C | 5 | 导出理由码与理由文本并列相邻两列；`!cols` 项数与表头相等 |
| 判据 D | 9 | 模板自由调用必在 `script setup` 有声明；未声明集合**冻结**为恰 `['calc','var']` |
| R6.6 | 4 | 建议态统计裁剪页与概览双侧可见 + 真的渲染 |

🔴 判据全部落到**结构**（哪个函数体的哪个分支里有什么赋值）而非「字符是否存在」—— 修复时刻意在注释里保留了 `decisionContext` / `TrimSuggestion` / `loadDecisionContext` 等字样以记录缺陷成因，故「全文不含 X」类判据必须先 `stripComments`，否则会误红（那是守卫缺陷不是代码缺陷）。

### 变异检验 5/5 全 RED（`RED(assertion)`，无 collection-error / GREEN / ANCHOR-MISS / WRONG-TEST）

| 编号 | 变异 | 锚点命中 | 判定 | 打红的测试 |
|---|---|---|---|---|
| M1 | 删导出表头 `'理由码', ` | 1 | RED(assertion) | 判据 C「表头同时含…并列相邻」+「`!cols` 项数相等」+「反向自检」共 3 条 |
| M2 | `below_materiality` 的 `verdict` → `'auto_trim'` | 1 | RED(assertion) | 判据 B「`below_materiality` 必为 `suggest_trim`」+「`auto_trim` 恰 1 次且为 `no_data`」共 2 条 |
| M3 | `suggest_trim` 分支插 `p._applicable = false` | 1 | RED(assertion) | 判据 A「不写 `_applicable` / `status` / `skip_reason`（R6.2 红线）」1 条 |
| M4 | 删概览 `suggestConfirmed` const + 两处 return 引用 | 1,1,1 | RED(assertion) | R6.6「概览侧统计已确认/已驳回」+「未初始化循环计数为 0」共 2 条 |
| M5 | 模板 `suggestionOf(row)` → `suggestionOfX(row)` | 1,1,1 | RED(assertion) | 判据 D「模板无未声明自由调用」+「反向自检 M5」共 2 条 |

基线 `total=42 passed=42 failed=0 suites=8`；md5 双文件 before == after（`82f7360a…` / `0769d052…`），`.bak` 零残留。

脚本要点：锚点**行级唯一**（`splitlines()` + needle 行内匹配 + `hits == 1` + 相对 `offset`，禁含 `\n` 的跨行字面量 —— 本工作树 CRLF，跨行锚点必 MISS）；`verdict: 'suggest_trim'` 全文 2 命中不能直接当锚点，改用其下一行唯一的 `reasonCode` + `offset=-1` 定位；`suggestionOf(row)` 全文 **4 命中**（模板 3 + 注释 1），M5 必须逐行钉而非按裸子串算唯一；变异后断言**字节确实变了**（未变则「测试仍绿」无意义）；判定读 vitest JSON 不读 stdout，跑前删旧 JSON 防解析陈旧结果；`npm exec` 传 flag 必须加 `--` 分隔符（不加时 npm 把 `--reporter` 当自己的 cli config 并 warn `Unknown cli config`，**JSON 根本不生成而退出码仍 0**）。

### 零回归（前后对照，未用 HEAD-swap）

cwd `audit-platform/frontend`，`npm exec vitest run src/views`：

- BEFORE `total=681 passed=648 failed=33`
- AFTER  `total=681 passed=649 failed=32`
- **仅在 AFTER（新增失败）= 空集**；仅在 BEFORE = 1 条 `ProcedureTrimming.twoLayer.spec.ts::程序委派向导（行层）单独设置执行人/操作复核人，走 ProcedureRowTask 真源`（**被顺带修好**）

因果已确认：该测试 mount `ProcedureTrimming.vue`，其 `ElTableColumnStub` 对每行调 `slots.default({ row })` ⇒ 必然执行模板 `suggestionOf(row)` ⇒ 修复前抛 `ReferenceError` 打红、修复后转绿。**这是接线修复生效的行为级独立证据**（不是源码级断言，也不是我自己写的守卫）。

Vite transform 已验：`curl.exe -s -o NUL -w "%{http_code}" http://localhost:3030/src/views/ProcedureTrimming.vue` → 200。

### 守卫自身缺陷三处（这是「变异检验与反向自检为何不可省」的实证）

1. **反向自检哨兵进不了提取域**：哨兵名 `__nonexistentHelper__` 双下划线起头，而 `freeCalls` 提取正则要求首字符 `[a-z]` ⇒ 哨兵**永远进不了集合**，那条断言实际在测「哨兵长什么样」而非「判据是否承重」，并以 `expected ['calc','var'] to include …` 的形态**假红**。修法两侧同时收口：提取域扩到 `[a-z_$]` 起头（顺带覆盖 `$emit` 这类真实写法）、哨兵改小写起头、补一条提取域自检。左边界还须用**负向后顾**而非 `\b` —— `\b` 在 `$emit(` 前不成立，会把 `$` 起头的标识符整类漏掉。
2. **模板切分取「第一个 `</template>`」只得 ~4% 模板**：本 SFC 有 20+ 个嵌套 `<template #default>` 插槽，第一个闭合标签在 L175 左右 ⇒ 判据 D 会在绝大部分模板上**空转恒绿**。改取「`<script setup` 之前的**最后一个** `</template>`」+ 配切分自检（断言正确切法比朴素切法多拿 2 倍以上）。
3. **`calc` / `var` 是 CSS 函数不是 JS 标识符**：来自 `max-height="calc(100vh - 340px)"` 与 `style="color: var(--gt-color-primary)"`。已冻结**最小**豁免清单（恰 2 个）+ 双向自检（清单里的名字不得同时是脚本声明、且必须真的在模板中出现）。清单每多一个名字就多一个真实标识符藏身的缺口。

三处的共同点：**守卫红/绿两种结果都不可信** —— 判据的扫描面与它声称覆盖的输入空间不一致时，缺陷既可能表现为假红（1）也可能表现为假绿（2）。故「写完守卫必做变异检验，没打红 = 守卫有缺陷不是代码没问题」这条铁律在本轮又收到两类新证据。

### 平台级事实（后续会话可直接引用）

- **`suggestionOf(row)` 这类模板消费的零声明标识符，四层检查（Volar / vitest / `get_diagnostics` / HEAD-swap）全绿**，只有浏览器挂载或 **mount 型测试**才暴露。本轮的独立证据来自 `ProcedureTrimming.twoLayer.spec.ts` 的 `ElTableColumnStub` 会真调插槽 —— 说明「模板里出现的自由调用是否有声明」值得作为平台级源码守卫推广（`views/` 下的大 SFC 尤其）。
- **`npm exec vitest --reporter=json` 经 `subprocess.run` 数组形式必须加 `--` 分隔符**，否则 JSON 不生成而退出码仍 0（会让「解析到陈旧 JSON」以「功能未修好」的形态误导判断）。跑前删旧 JSON + 断言新 JSON 存在是唯一保证。
- **本环境 python 脚本 stdout 会被 `\ode (vitest N)\` 转义符污染吞掉** ⇒ 诊断/变异报告一律落盘再 `read_file`。

### 未做（留给后续任务）

浏览器实测归 **Task 26** 统一做（含「裁掉某底稿后它不再出现在委派目标里」—— `ProcedureDelegationService._trimmed_scopes()` 恒返空集的死链条，本 spec 落地后才第一次真正有数据流经过）。Task 22 的完整 12 条变异在本轮 5 条基础上扩充。

---

## Task 18 交付实录（2026-08-10）

### 一句话结论

组件本身按计划落地（纯展示 + 本地编辑 + `emit`，不发请求不写库），但本轮真正的收获在**上游**：零回归对照时 Task 17 的 PBT 偶发打红，逼出一个「属性侧要求去重、实现侧没去重」的口径不对称缺陷；同时确认平台**没有资历真源**、`getProcedures` 下发的 `wp_id` 与 selector 要的 `wp_index_id` **不是同一个 ID**，两条都属于「不报错但结果为空」的静默失效类。

### 产出

| 文件 | 性质 |
|---|---|
| `.../components/workpaper/delegation/GtDelegationSuggestionTable.vue` | 新建，建议分配表组件（纯展示 + 本地编辑 + `emit`，不发请求不写库） |
| `.../components/workpaper/composables/delegationSeniority.ts` | 新建，`role → seniority` 折算的单一真源 |
| `.../components/workpaper/composables/__tests__/delegationSeniority.spec.ts` | 新建守卫 |
| `.../components/workpaper/delegation/__tests__/delegationSuggestionTable.spec.ts` | 新建守卫 |
| `.../components/workpaper/composables/delegationSuggestion.ts` | **修缺陷**：targets 按 `wpIndexId` 去重 |
| `.../components/workpaper/composables/__tests__/delegationSuggestion.spec.ts` | 补 3 条确定性回归用例 |
| `.../views/ProcedureTrimming.vue` | 接线（`suggestDelegation` 4 处 / `listWorkpapers` 3 处 / `roleSeniority` 3 处），2327 → 2621 行 |
| `backend/scripts/check/mutate_task18_suggestion_guards.py` | 新建变异脚本，7 条变异 |

### 本轮修掉的 Task 17 真实缺陷（口径不对称）

**发现路径**：做零回归全量对照时，`delegationSuggestion.spec.ts` 的 PBT「已分配 + 未分配 == 有效目标数（不丢不重）」**偶发**打红 —— 单独连跑 4 次全绿，只在全量套件里命中。

**确定性反例**：`seed: -986847725`，`members: []` 且两条目标 `{wpIndexId:'v', wpCode:' ', cycle:'D', risk:'H', rowCount:0}`。

**根因**：属性侧用 `new Set(...).size` 计「有效目标数」并断言输出的 `wpIndexId` 唯一 ⇒ 属性实际要求的是**按 `wpIndexId` 去重**；实现侧却只 `.filter()` 掉空 `wpIndexId`、**从未去重**。而同一文件里的 `members` 是去重的（`seen` + `duplicateCount` + warning）—— 两个入参集合口径不对称，是缺陷的直接来源。复算吻合：`ids.size = 1` 而 `unassignedTargets.length = 2`，`0 + 2 !== 1`。

**为何判「改实现、不改属性」**：同一张底稿在入参里出现两次，若不去重则 ①会对同一 `wp_index_id` 重复下发委派 ②Task 18 的建议分配表以 `wpIndexId` 作 `el-table` 行键，重复键会让某一行的编辑串到另一行。两条都是真实业务错误，故属性是对的、实现是错的。

**修法与两个必须的顺序/一致性约束**：

- 在 targets 规范化处按 `wpIndexId` 去重，**首次出现胜出**，重复条数计入 `warnings`。
- **去重必须发生在排序之前**：排序键含 `wpIndexId`，若先排后去重，「首次出现胜出」的语义会随排序结果漂移，输出不可复算。
- **去重键与对外产出的 `wpIndexId` 值必须逐字一致**：若去重时对键做了任何规整而产出值不同，两条不同键的记录仍可能产出同一个 `wpIndexId`，`el-table` 行键碰撞照旧存在。

**回归用例（3 条，均不依赖随机种子）**：反例逐字复现；有成员时同一 `wpIndexId` 只产出一条 assignment；去重先于排序（首次出现胜出）。

**经验**：PBT 偶发打红本身就说明「单次全绿不构成证据」。故修完后连跑 5 次确认，每次单独 `outputFile` 且跑前删旧 JSON（防解析到陈旧结果）。

### 偏离 tasks.md / design.md 之处

**1）入参形态与 design.md 不一致（有意偏离）**

design.md L256 的入参写作 `members: { staffId; role; currentWeightedLoad }`（按 `role`），而 Task 17 实际落地为 `seniority: number`。二者不一致，本任务新增 `delegationSeniority.ts` 作映射层桥接。

**2）平台无资历真源，映射表是本 spec 自建口径**

`staff_members.role_level`（`partner` / `manager` / `senior` / `auditor` / `intern`）在模型里存在，但**全部 router grep 0 命中 = 后端不下发**；`list_assignments` 只 select `role` / `staff_title`（← `StaffMember.title`）/ `employee_no`。故 `delegationSeniority.ts` 的映射表是本 spec 自建口径。将来后端下发 `role_level` 后，应改读该字段并删掉本映射层。

🔴 **不得挪用 `ProcedureTrimming.vue` 既有的 `ROLE_PRIORITY`**（`auditor:1 … signing_partner:6`，兜底 `?? 90`）：它是底稿主编下拉的**排序优先级**，数值越小越靠前，**语义方向与资历相反**；把兜底 90 挪到资历尺子上会变成「未登记角色资历最高」，即不认识的角色反而被允许承担高风险底稿。

**3）`wp_index_ids` 取数改走 `listWorkpapers`（ID 不同源）**

`getProcedures` 只下发 `wp_id`（= `working_paper.id`；`procedure_service._resolve_wp_ids` 是 JOIN 后取 `WorkingPaper.id`），与 selector 需要的 `wp_index.id` **不是同一个 ID**。混用后端 `ProcedureRowTask.wp_index_id.in_(...)` 匹配不到任何目标**且不报错**，表现为「建议表生成了但应用后 0 变更」—— 属最难归因的一类静默失效。故改走 `listWorkpapers(projectId, { audit_cycle })` 的 `VisibilityWpItem.wp_index_id`。本任务**后端零改动**。

### 守卫

| 项 | 结果 |
|---|---|
| 变异脚本基线 | `total=144 passed=144 failed=0 suites=32`（覆盖 `src/components/workpaper/delegation` + `delegationSeniority.spec.ts` + `delegationSuggestion.spec.ts`） |
| `delegationSuggestion.spec.ts` 单文件 | 62 例（原 59 + 新增 3 条确定性用例），**连跑 5 次全绿** |
| 五守卫合并跑（含 `trimDecisionWiring.spec.ts` 42 例与 `delegationLoadSingleSource.spec.ts`） | **204 例全绿** |

### 变异检验 7/7 全 RED

判定态均为 `RED`，无 GREEN / ANCHOR-MISS / WRONG-TEST；三个被变异文件 md5 字节级还原全部一致，`.bak` 零残留。

| 编号 | 变异 | 打红条数 |
|---|---|---|
| M1 | `buildSuggestionTargets` 取 `wp_id` 代替 `wp_index_id` | 3 |
| M2 | `loadBoard` 把负载未知的成员补成 0 基线 | 2 |
| M3 | 未登记 role 兜底改成最高档（与 `ROLE_PRIORITY` 的 `?? 90` 同向） | 4 |
| M4 | `reviewerOptions` 不再排除执行人本人（破 SOD 硬约束） | 1 |
| M5 | `emitApply` 改为组件自行调用 `applyProcedureDelegation` | 2 |
| M6 | 删掉 `unassignedTargets` 独立区块的渲染条件 | 1 |
| M7 | `suggestDelegation` 去掉 targets 的 `wpIndexId` 去重判断 | 3 |

### 零回归（前后对照，未用 HEAD-swap）

- **全量**：BEFORE `total=12439 passed=12242 failed=197` → AFTER（未修 PBT 前）`total=12481 passed=12283 failed=198`。唯一新增失败即上述那条 PBT；去重修好后该条转为确定性通过。
- **`src/views` 定向复核**（Task 18 改动最大的 `ProcedureTrimming.vue` 所在面）：`total=723 passed=691 failed=32`。失败名集合与 Task 13 收口基线**逐条相同**（PartnerProjectDashboard 15 / ReportView.filesize-invariant 2 / b50BadgeSingleSource 1 / useNoteTree.indexRef 1 / useReportColumns 3 / useReportCrossCheck.p32 2 / useReportCrossCheck 2 / useReportExport 1 / line-budget(editor) 1 / line-budget(workpaper-list) 1 / WorkpaperListShell 3 = 32），**新增 0**；`ProcedureTrimming.twoLayer.spec.ts` 不在失败列表 = 保持绿。
- ⚠️ **如实标注全量基线的局限**：全量套件存在 197 条**预存在**失败与 13 个 unhandled error（后者会让 vitest 退出码非 0 且 JSON reporter 不落盘，须改用 `--reporter=basic` 抓摘要）；期间**并发会话**在改 i/e 循环附注文件（`i1SoeDisclosureModel.ts` / `i2DisclosureModel.ts` / `e1RestrictedScope.ts` / `useI2Disclosure.ts` 等，14:00~15:40 多次改动），故全量基线已不可重复比对，**零回归结论以定向面为准**。

### Vite transform

`ProcedureTrimming.vue` / `GtDelegationSuggestionTable.vue` / `delegationSeniority.ts` 均 200。

### Task 13 成果未被破坏（逐项核实在位）

`suggestionOf` / `clearRowSuggestion` 各 1 处声明、`loadTrimContext` 5 个调用点、`p._suggest = true` 1 处、概览 `suggestConfirmed` 9 处、导出「理由码」9 处。

---

## 交付实录 · Task 14 完整性清单项目级覆盖入口（2026-08-10，恢复 16:42 中断的实现）

### 一句话结论

后端三方法 + 三端点、`apiPaths`、`commonApi`、以及 `.vue` **脚本侧 14 个绑定全部已在位**，唯独模板里**没有面板本体** —— 六个标识符模板 0 引用，点「逐循环设置 →」只把一个没人读的 ref 置真。这是平台已登记的「additive 注入即死代码」的**对偶形态**（那次是新取数没有消费方，这次是新交互没有渲染宿主），四层检查（Volar / vitest / `get_diagnostics` / HEAD-swap）对它全绿。

### 磁盘真相盘点（写码前，按 tasks.md 逐条）

用 `python -c "open(p,encoding='utf-8').read()"` 直读（`read_file` 对刚写过的文件返回陈旧内容）。

| bullet | 判定 | 实证 |
|---|---|---|
| ①「加逐循环开关面板，落 `B50-T3-cscope-{cycle}`（`conclusion`=Y/N，`remark`=理由）」 | **PARTIAL** | 见下表逐项 |
| ②「留痕操作人与时间，理由必填」 | **后端 SATISFIED / 前端不可达** | INSERT/UPDATE 均写 `updated_by`+`updated_at`；空白理由 400。前端三道校验齐备但**无入口可达** |
| ③「未覆盖用平台默认 + 标注『使用平台默认，未经本项目确认』」 | **SATISFIED** | 状态条 L92-124，开关取 `resolveCompletenessExemption` 的 `usingPlatformDefault` |
| ④「守卫：cscope 行不改变 `load_b50_accounts()` 任何输出」 | **PARTIAL，关键半边 ABSENT** | 见「tasks.md 与代码接触后不成立之处」第 2 条 |

bullet ① 逐项：

| 部件 | 状态 |
|---|---|
| `procedure_trim_service.set_/clear_/list_completeness_scope_overrides`（L232-424） | ✓ 在位（含 asyncpg 显式 CAST、`_require_b50_wp_id` 409、Y/N 双向表态、DELETE 删行不写空串） |
| router `GET/PUT/DELETE /procedure-trim/completeness-scope`（L255-322） | ✓ 在位（三者均挂 `require_project_delegator_pid`，写端点 commit + rollback + 重抛） |
| `apiPaths.procedureRowTasks.trimCompletenessScope` / `…Item`（L239-241） | ✓ 在位 |
| `commonApi.fetch/save/clearCompletenessScopeOverride` + `CompletenessScopeOverride`（L457-539） | ✓ 在位（读取**不吞**请求级错误，注释已写明理由） |
| `.vue` script setup 14 个绑定（L1223-1418） | ✓ 在位 |
| **`.vue` 模板：面板本体** | **✗ 缺失** —— `completenessPanelVisible` / `completenessScopeRows` / `setCompletenessScope` / `revertCompletenessScope` / `completenessSourceLabel` / `completenessSaving` 模板命中 **0** |
| **`<style scoped>`：`.gt-proc-cscope-*` 六个类** | **✗ 缺失** —— 状态条已在模板引用它们，样式一个都没有 |
| 守卫（后端 py / 前端 spec / 变异脚本） | **✗ 全缺**；且源码注释**已引用两个尚不存在的文件名**（router L110 引 `test_completeness_scope_override.py::TestRouterServiceKwargAgreement`、`.vue` L1157 引 `completenessScopeOverride.spec.ts`） |

### 产出

| 文件 | 性质 |
|---|---|
| `audit-platform/frontend/src/views/ProcedureTrimming.vue` | 补面板渲染宿主（`el-dialog` + 逐循环 `el-table`：平台默认 / 当前生效 / 判据来源 / 依据与理由 / 最后修改 / 三个点选动作）+ 六条 `.gt-proc-cscope-*` CSS；2890 → **3046**（+156 行） |
| `backend/tests/procedure_trim/test_completeness_scope_override.py` | 新建守卫 **56 例** |
| `.../frontend/src/views/__tests__/completenessScopeOverride.spec.ts` | 新建守卫 **56 例 / 7 suites** |
| `backend/scripts/check/mutate_task14_cscope_guards.py` | 新建变异脚本 **14 条，14/14 RED** |
| `.../frontend/src/views/__tests__/b50BadgeSingleSource.spec.ts` | **修 Task 4 守卫假红**（见下） |

面板交互按底稿铁律做点选：「设为敏感 / 设为不敏感」双向按钮 + 「撤销」，每个按钮受 `canManage` 与当前态双重 `:disabled`（已是该态时不可重复点），`completenessSaving` 做逐行 loading（不整表禁用）。未知态（读取失败）单独渲染红色 alert + 「重新加载」，绝不显示成「全部平台默认」。

### tasks.md 与代码接触后不成立之处（5 处）

1. **「加面板」实为「补宿主」**。照原文从零做会重复实现已在位的 14 个绑定与三条取数链；反过来若因「脚本侧齐备」判定已完成，功能就永远不存在。真实缺口只有两处：模板里的 `el-dialog` 与 `<style>` 里的六个类。

2. **守卫判据 tasks.md 只写到一半就已被当成整条**。原文要求「既不产生科目项**也不改既有字段**」，而 Task 1 留下的 `test_cscope_key_is_silently_skipped_by_all_branches` 只断言 `names == {"货币资金"}` —— 仅覆盖前半。后半（cscope 行是否污染既有科目的 `cells` / `max_risk` / `has_special`）此前**无人验证**。本轮按 Task 1 冻结的 `_LEGACY_ROWS` / `_LEGACY_EXPECTED` 做**全量深比对**补齐（importlib 按路径加载兄弟守卫模块复用快照与 `_FakeSession`，不抄第二份 —— 抄了「快照被改」与「实现回归」就不可区分，两边各自全绿），并配一条反向自检「注入一条矩阵行必须让该比对察觉差异」：没有它，深比对退化成只比科目名集合时会静默恒绿。

3. **cscope 前缀不是单一真源，是「一份常量 + 一份内联 SQL 字面量」**。写入侧 `procedure_trim_service` 从读取侧 import `COMPLETENESS_SCOPE_ITEM_PREFIX`，而读取侧 `trim_decision_context._load_completeness_override` 把 `'B50-T3-cscope-%'` **内联在 SQL 文本里**（L381）。常量一改就「写得进读不出」，而两侧各自的替身单测都用自己的前缀构造样本 ⇒ 都不会红。tasks.md 未提这条风险，本轮加了交叉锁死断言（读取侧 LIKE 字面量必须 == 常量 + `'%'`），变异 M9 验证承重。

4. **CSS 缺失是「模板引用了不存在的类」，属只有浏览器能暴露的一类**。scoped CSS 缺类不报错、不影响渲染，`get_diagnostics` 与 vitest 全查不出，表现为状态条与面板完全没有视觉分层（三态同一个样子）。16:42 那轮写了状态条模板却没写样式。

5. **`checklist_responses` 只有「当前值 + 最后一次留痕」，没有变更历史**。原文「覆盖动作留痕操作人与时间（复用既有字段）」易被读成有审计轨迹；实为 `updated_by` / `updated_at` 单值覆盖式。R5.5 只要求最后一次的 who/when/why，`commonApi` 的类型注释已如实写明，避免后续会话按「有历史」去做复核视图。

### 守卫（112 例，全绿）

**后端 56 例**（`test_completeness_scope_override.py`）：helper 三条自检 · 前缀单一真源与读写交叉锁死 4 · **cscope 零污染 5**（含全量深比对 + 反向自检 + 11 循环参数化 + 一条能穿透 suffix/assertion 两道白名单的构造样本）· 真实库连库 2（专用 `NullPool` engine，同 loop 内 dispose）· 写入行为 9 · 读回行为 5 · `TestRouterServiceKwargAgreement` 4 · `TestCompletenessScopeEndpoints` 6。

**前端 56 例 / 7 suites**（`completenessScopeOverride.spec.ts`）：helper 自检 4 · **判据 A 渲染宿主 15**（10 个绑定逐个「有声明 × 被模板消费」+ dialog 形态 + Y/N 双向触发点 + 留痕可见 + `canManage` 门控 + 两条反向自检）· 判据 B 单一真源 7 · 判据 C 未知态 5 · 判据 D 理由必填与双刷新 6 · 判据 E 跨前后端交叉锁死 6。

判据全部落在**结构**（哪个函数体 / 哪个 computed 实参区 / 哪一段模板里有什么）而非「字符是否存在」。修复时刻意在模板注释里保留了那六个标识符以记录缺陷成因，故所有「名字是否出现」类判据必须先 `stripComments` —— 并配了一条反向自检断言「raw 侧命中数 > clean 侧」，防剥注释哪天失效后判据被自己的说明文字骗绿。

**真实库事实**（连库真跑，非推断）：`checklist_responses` 共 **1,034,515** 行，其中 `B50-T3-cscope-%` **0** 行、`B50-T3-%` **0** 行 ⇒ 存在性断言按「查询可执行且返回 0」而非「必须有数据」；同时真跑 `information_schema` 确认列名是 `wp_id` 而非 `workpaper_id`。

### 变异检验 14/14 全 RED

`.bak` 备份 + `try/finally` 无条件写回 + **md5 五文件字节级还原核验全部 OK**、`.bak` 零残留。判定按**失败测试名集合求差集**（不看退出码），显式区分 RED / WRONG-TEST / GREEN(守卫缺陷) / ANCHOR-MISS 四态。基线：后端 79 passed / 0 failed、前端 56 passed / 0 failed。

| 编号 | 变异 | 打红 |
|---|---|---|
| M1 | 面板 `el-dialog` 的 `v-model` 改绑别的 ref | 1 |
| M2 | 面板表格不再遍历 `completenessScopeRows` | 2 |
| M3 | 只给「设为敏感」一个方向（Y/N 退化成半个功能） | 1 |
| M4 | 读取失败退化成空数组（技术故障谎报成「全部平台默认」） | 1 |
| M5 | `usingPlatformDefault` 改为视图自算（第二份判据真源） | 1 |
| M6 | 写入后只刷面板不刷判据上下文 | 1 |
| M7 | 去掉发请求前的独立空理由判断 | 1 |
| M8 | 写入侧另写一份前缀字面量（不再 import 读取侧常量） | 1 |
| M9 | 读取侧 LIKE 模式与常量漂移（写得进读不出） | 1 |
| M10 | 空理由不再拒绝（无理由的覆盖直接落库） | 4 |
| M11 | 撤销改成写空 `conclusion` 而不是删行 | 1 |
| M12 | reader 把 cscope 行也当科目建项（污染 `load_b50_accounts`） | 3 |
| M13 | PUT 端点摘掉项目级 Delegator 守卫（越权写入口） | 1 |
| M14 | router 用不存在的形参名调 service（运行时 TypeError → 500） | 2 |

### 变异检验暴露的**我自己守卫的三个缺陷**

1. **`computedArg` 的泛型正则在真实写法上直接失配**。首版用 `computed\s*(?:<[^>]*>)?\s*\(`，遇到 `computed<Record<string, boolean> | null>(` 时 `[^>]*` 停在 `Record<string, boolean>` 的内层 `>` ⇒ 整条正则不匹配 ⇒ 返回空串 ⇒ 断言以 `expected '' to contain 'resolveIt'` 的形态**假红**。改为只锚 `const NAME = computed` 再取其后第一个 `(`（泛型里不会有圆括号）。
2. **`_func_src` 自检样本两个 `def` 缩进不一致**（`async def f` 顶格 + `def g` 缩进 4）⇒ 「缩进 ≤ def 缩进即结束」永不触发、`def g` 被截进函数体 ⇒ 以「越界截到了下一个函数」**假红**。那是**样本缺陷不是 helper 缺陷**；已改成同缩进并补一条顶格形态的正样本。
3. **守卫自己犯了它要防的那类错配**。`_load_completeness_override` 真实签名是**两个位置参数、返 `(override, degradations)` 二元组**，首版按 `(db, pid, degradations)` 三参调用得 TypeError。这与 `TestRouterServiceKwargAgreement` 在生产代码上要钉死的是同一类问题 —— 写守卫的人先踩了一次，可作该守卫必要性的旁证。

### 变异脚本的两条经验（锚点唯一性）

- **三条变异都不能拿"看起来独特"的语句当锚点**：`await loadTrimContext([activeCycle.value])` 全文 **6 处**命中（Task 13 接线留下的调用点）、`_guard: DelegatorContext = Depends(require_project_delegator_pid),` 全文 **9 处完全相同**、`reason=body.reason,` **4 处**。三者改锚唯一行（写入调用行 / `body:` 标注行 / `svc.set_completeness_scope_override(` 起始行）+ 相对 `offset`。
- **首版 M13/M14 用 `nth` 计数定位** —— 会随端点增删而错位（且错位后仍可能"打红"，成 WRONG-TEST 而非 RED）。改成唯一锚 + offset 后与端点顺序无关。
- **M8 首版变异体不是合法 Python**：会以 collection error 而非断言失败打红 —— 那是**第五种结果**，既不能算 RED 也不能算 GREEN（整文件零断言执行）。改成「保留一个真实 import + 自造字面量」的合法形态后才是有效变异。

### 零回归（前后对照，未用 HEAD-swap）

把本轮对 `.vue` 的两处插入（面板 + CSS，共 156 行）摘掉 → 跑 `src/views` → 装回 → 再跑：

- BEFORE `total=779 passed=734 failed=45`
- AFTER  `total=779 passed=747 failed=32`
- **仅在 AFTER（新增失败）= 0**；仅在 BEFORE = **13 条，全部是新守卫的判据 A**

那 13 条是**行为级证据**：面板不在时守卫必红、装回即绿 —— 判据承重不靠自证。32 条共有失败与 Task 18 收口基线**逐条相同**（PartnerProjectDashboard 15 / ReportView.filesize-invariant 2 / WorkpaperListShell 3 / line-budget 2 / useNoteTree.indexRef 1 / useReportColumns 3 / useReportCrossCheck.p32 2 / useReportCrossCheck 2 / useReportExport 1 / b50BadgeSingleSource 1 = 32），全为预存在。还原后 md5 字节相等。

**后端零回归天然成立**：本轮后端**只新增测试文件，未改任何生产代码**（三方法与三端点是 16:42 那轮的产出）。

### 顺带修掉一条 Task 4 守卫假红

`b50BadgeSingleSource.spec.ts::非 completed 时提供跳转 B50 的入口` 断言 `/b50Completeness\.state\s*!==\s*['"]completed['"]/`，而模板写的是 `b50Completeness!.state`（TS 非空断言）⇒ **门控明明存在却匹配不到**，以「跳转入口未按状态门控」的形态假红（该条已在 Task 18 记录的 32 条基线里躺了两天）。已改 `b50Completeness!?\.state` 并补四条反向自检（两种写法都要进扫描面；换 `===` 或换字段不得命中）。这是判据缺陷不是代码缺陷 —— 同族于本轮那三条守卫自身缺陷：**扫描面与它声称覆盖的写法不一致时，红/绿两种结果都不可信**。

### 验证汇总

| 项 | 结果 |
|---|---|
| `backend/tests/procedure_trim/` 全目录 | **238 passed / 1 skipped**（skip 为 Task 10 预存在的连库样本缺失） |
| 前端 5 守卫合并（新建 + `trimDecisionWiring` + `b50BadgeSingleSource` + `twoLayer` + `delegationLoadSingleSource`） | **145 / 145** |
| 变异检验 | **14/14 RED**，md5 五文件还原 OK |
| 零回归 | 新增失败 **0** |
| `src/views` 最终 | `779 / 748 / 31`（32 预存在 − 1 修掉的假红） |
| Vite transform | `ProcedureTrimming.vue` / `completenessExemption.ts` / `commonApi.ts` 全 **200** |
| `get_diagnostics` | 5 个改动/新建文件全 0 |

### 平台级事实（后续会话可直接引用）

- **「模板渲染宿主缺失」是「additive 注入即死代码」的对偶形态**，同样四层全绿：SFC 模板表达式不参与 TS 类型检查，脚本里声明而不被消费的绑定也不是错误。判据 = 「脚本侧声明 × 模板消费方」二维交叉，且**必须先 `stripComments`**。建议作平台级守卫推广到 `views/` 下的大 SFC（与 Task 13 定性的「模板里的零声明自由调用」互为一对：那次是模板有、脚本无；这次是脚本有、模板无）。
- **`trim_decision_context._load_completeness_override` 的 LIKE 前缀是内联 SQL 字面量**，与写入侧 import 的常量构成潜在漂移点；已加交叉锁死守卫。同一模式值得在平台其它「一侧常量、一侧内联 SQL」的读写对上排查。
- **`checklist_responses` 1,034,515 行但 `B50-T3-%` 为 0 行** —— B50 从未被填写过这一事实在本轮再次实证（Task 25 的「有 B50」状态仍须输出 `UNVERIFIABLE`）。
- **交付实录的标题写法会影响 spec 机器校验**：`## Task N 交付实录…` 被 `get_diagnostics` 判成「任务必须用复选框格式」（本文件 Task 13 / Task 18 两份记录共留下 3 条此类**预存在**报错）。改写成 `## 交付实录 · Task N …` 即不触发，且仍可按「Task N」grep 到。后续会话写记录时用后者。

### 清理与一处需登记的操作失误

本轮 `tmp_*` 诊断产物已删（`tmp_t14_*` / `tmp_mutate_task14_report.txt` / `tmp_t14_zero_regression*` / `frontend/tmp_t14_fe.json`）。

🔴 **清理 glob 过宽误删了并非本轮产生的 `backend/app/routers/wp_template.py.bak`（32857 B）**。已定性并**按字节重建**：32857 恰为 HEAD 版 `wp_template.py`（31987 B，LF）的 **CRLF 副本**（`\n` → `\r\n` 后 31987 → 32857，逐字节可重算），故其中不含任何独有成果；重建后与工作树、与 HEAD 的逻辑内容均一致，且 `wp_template.py` 本身与 HEAD 字节相同、`git status` 干净 ⇒ 无残留变异体、无他人成果丢失。**教训：清理只能按本轮已知产出的确切路径删，禁按扩展名扫目录**（`*.bak` 是别的会话变异脚本的活体备份，删掉会让它的 `--restore` 失败并把变异体留在工作树）。

另：`tmp_task14_dump*.{py,txt}` / `tmp_task14_inventory.*`（mtime 17:05-17:09）是**另一会话**做同一盘点的产物（其脚本 docstring 自称「会话结束前删除」），结论与本轮一致且已被本记录取代 —— 但**不属本轮产出，故未删**，留给该会话自行清理。

### 未做（留给后续任务）

浏览器实测归 **Task 26** 统一做。本轮新增的三个写端点（PUT / DELETE）**在浏览器上一次都没跑过** —— 替身单测覆盖了参数编码与分支，但 asyncpg 的真实 CAST 行为、`(wp_id, item_id)` 唯一约束下的 INSERT/UPDATE 分流、以及「写入后判据上下文真的重算」这条跨层联动仍待实测。Task 26 的实测清单应加两项：**逐循环覆盖写入 → 撤销 → 复原**，以及**覆盖某循环后该循环的「金额低于重要性」建议是否真的消失**。

---

## 交付实录 · Task 19 建议分配应用走既有委派路径（2026-08-10）

### 一句话结论

按计划把应用编排落在宿主并复用既有两阶段，**但 Task 18 留下的 emit → 宿主接线是断的**：宿主 handler 的形参类型写成 `{ assigneeStaffId; wpIndexIds }`，而组件 emit 的是含 `selector.wp_index_ids` 的 `DelegationApplyGroup` —— `g.wpIndexIds` 字段不存在，`.length` 运行时抛 TypeError。点「应用建议分配」在浏览器上从来只会报错。本轮同时定性一条更要紧的平台级事实：**`get_diagnostics` 在 `ProcedureTrimming.vue` 上是全盲的**（塞 `const x: number = '字符串'` 也返回 0 条），此前多份交付记录把它当作「四层全绿」的一层，在本文件上不构成任何证据。

### 产出

| 文件 | 性质 |
|---|---|
| `audit-platform/frontend/src/views/ProcedureTrimming.vue` | 逐组 preview→apply 编排 + 409 三分类 + `no_target` 独立态 + 单组重试 + 模板渲染宿主 + CSS；3046 → **3430**（+384 行） |
| `.../src/views/__tests__/delegationSuggestionApply.spec.ts` | 新建守卫 **55 例 / 9 suites**（源码级 48 + **mount 行为级 7**） |
| `backend/scripts/check/mutate_task19_apply_guards.py` | 新建变异脚本 **12 条，12/12 RED** |

**后端零改动**（preview / apply / member-loads 三个端点与 `ProcedureDelegationService` 一字未动）。

### 改了什么

**（1）宿主类型改用组件导出的单一真源**。`import GtDelegationSuggestionTable, { type DelegationApplyGroup } from '...vue'`，`pendingApplyGroups` 与 handler 形参一并换掉镜像类型。`<script setup>` 的 type-only export **确实可被别的模块 import**（见下「类型面怎么核的」）。

**（2）逐组编排**（`onSuggestionApplyRequest` → `applySuggestionGroup` → `retrySuggestionGroup`）：

- 每组一次 `previewProcedureDelegation` → 一次 `applyProcedureDelegation`，selector 用 `kind: 'workpaper'` + `wp_index_ids`（取 `g.selector.wp_index_ids`）。
- **同一个 body 对象**喂两阶段：后端 apply 侧 `canonical_request_hash(request_payload)` 重算比对，两侧任一字段不同即 409「预览请求已被篡改」。守卫断言 `suggestionGroupBody(` 在组函数内**恰调用 1 次**。
- 每组自己的 `request_id`（`newRequestId()` 在组内取，落 `state.requestId`）。
- **顺序**执行不并行：后端 apply 用 `resolve_targets(..., for_update=True)` 行锁复取并比对 `target_versions`，并行提交时先落库那组顶掉 `lock_version` ⇒ 其余组全部 409「目标任务版本已变化」，表现为「随机几组失败」。
- 组函数**自吞异常**、循环体无 `break`/`throw` ⇒ 一组失败不中断后续组。
- 用户取消确认框时一个请求都不发（`ElMessageBox.confirm` 在建 group 状态之前）。

**（3）409 三分类**（`classifyDelegationConflict`）—— 这是 tasks.md 没写而实证必须做的：后端 409 有三个来源、指向三种完全不同的处置。

| 来源 | 态 | 处置 |
|---|---|---|
| `consume_and_apply` 的 TTL / 一次消费 / 防篡改 / 成员快照 + `apply_fn` 的 `target_versions` 复核 | `stale` | 重新预览该组即可 |
| `DelegationConflictError`（`detail.error === 'delegation_conflict'`） | `assigned_conflict` | 目标已被他人分配，需改冲突策略 |
| `assert_sod_distinct`（**也是 409**，`procedure_authorization.py`） | `sod` | **重新预览无效**，必须改复核人 |

塌成一句「请重新预览」会让审计师对 SOD 冲突反复做无用功，最后把问题归因成「系统不稳定」。

**（4）`no_target` 独立态**（`summary.targets === 0` 时**不调 apply**）：apply 在零目标下也会 200 且返回 `applied: 0`，屏幕上就是「已应用」。说明文案写明三种成因（行任务未物化 / 已被粗裁为不适用 / applicability 非 execute）。目标数读**嵌套 `summary.targets`**（后端真键；顶层 `target_count` 不存在，读它恒得 undefined）。

**（5）逐组结果面板**（`suggestApply` / `suggestApplyTotals` / 两个 label 函数 / `retrySuggestionGroup` 的唯一渲染宿主）：汇总条把**成功 / 需重新预览 / 无目标 / 受阻**分开计（合成一个数就看不出该做什么）；`retryable > 0` 时 alert 明示「失效组零写入、已成功的组不受影响、只重试标记组」；逐行「重新应用」只动该组，**不重建 `groups` 数组**（重建会把已成功组的 `applied` 抹成 0，屏幕上像「上次全白做了」⇒ 审计师会对已落库的组再委派一遍）。

**（6）顺带消一处命名隐患**：`suggestionGroupBody` 的形参由 `g` 改名 `state`。`g` 此后只指组件 emit 的 `DelegationApplyGroup`（snake_case selector），`state` 只指本页 `SuggestionApplyGroupState`（camelCase）—— 两种形状共用一个变量名正是 Task 18 那处字段名写错的温床。

### 偏离 tasks.md / 上游描述之处（4 处）

1. **「应用复用既有两阶段」的前提是断的**。tasks.md 隐含 emit → 宿主这条线已通（Task 18 记录称「emit 出口已通，Task 19 只需替换本函数体」），实证宿主形参类型与 emit 载荷结构不兼容、字段名不存在。性质是**接线修复 + 新功能**，不是纯新增。

2. **409 不是单一含义**，tasks.md 只写「任一组 409（预览过期/版本变化/成员变更）→ 提示重新预览该组」。漏了 SOD 与 conflict 两类同样是 409 而处置完全不同。已按三分类实现并配守卫 + 变异 M6。

3. **`materialization_pending` 已经不会出现**。`procedure-mainline-convergence` Task 4.1 把物化改成同步（`procedure_delegation_service.preview` 内注释明写「不再返回 materialization_pending，直接同步完成物化并继续构建 ready preview」）。故「命中 materialize 前置」在 UI 上**不表现为 pending 态**，而表现为 `summary.targets === 0`（同步物化后仍无可委派目标）。任务书说的「多数项目会先触发 materialize 前置」在当前后端下等价于本轮的 `no_target` 态 —— 这也是为什么它必须与成功态分开。防御性保留了 `preview_id` 为空即 `failed` 的分支。

4. **真实库数字已过期**（本轮只读实测，2026-08-10）：`procedure_row_tasks` 是 **157 行 / 3 个项目**（tasks.md 写 46 行）、`procedure_instances` 覆盖 **34 个项目**（写 14 个）、已分配 65 行。`procedure_instances` 已裁剪仍是 **0 行** ⇒ `_trimmed_scopes()` 恒返空集这条判断不变。

### 类型面怎么核的（`get_diagnostics` 在本文件上全盲）

| 探针 | `get_diagnostics` | 隔离 vue-tsc |
|---|---|---|
| `import { type __ProbeNonexistentType__ } from '...vue'`（不存在的导出） | **0 条** | TS2614 ✔ |
| `const x: number = 'definitely-not-a-number'` | **0 条** | TS2322 ✔ |
| `DelegationApplyGroup` + `selector.wp_index_ids` 字面量 | 0 条 | 静默通过 ✔ |

即：负控制两条都能被隔离 vue-tsc 打红、正控制静默 ⇒ 类型 import 是真的、字段名与组件导出逐字段吻合。**全项目 `vue-tsc --noEmit` 跑不动**（4 GB 与 8 GB 堆均 `Ineffective mark-compacts near heap limit`），故做法是：临时 tsconfig 只 `include` 一个 probe.ts（它只 import 那个组件，传递依赖很小）→ 秒级出结果。这条路子后续核 SFC 类型面可直接复用。

### 守卫（55 例 / 9 suites，全绿）

| 组 | 例数 | 判据 |
|---|---|---|
| helper 自检 | 7 | `stripComments`（JS/HTML/python 三形态）· `fnBody` 跳过内联返回类型注解 · **`pyClassBlock` 按缩进切 python 类体** · 五个被测函数体非空 · 扫描面非空 |
| A 写入路径唯一 | 7 | 两阶段调用同处一体且 apply 在 preview 之后 · 自有 13 个文件零直写 `procedure_row_tasks` 分配字段 · 不借 `assignProcedures` / `transitionProcedureRowTask` · 组件仍零 IO · **两条反向自检** |
| B 分组与 selector | 7 | `workpaper` 粒度 + snake_case · **接收者判据**（见下）· 跨文件锁死组件导出类型 · 同 body 两阶段 · 每组 `request_id` · 顺序不并行 · 空组不发请求 |
| C 逐组隔离与 409 | 6 | 组内 catch / 循环无 break·throw · 三分类齐备 · SOD 分支不得说「重新预览」· 重试不重建数组 · 模板逐组展示 + 重试入口 + 明示 · 汇总四态分开计 |
| D 无目标不报成功 | 5 | 读 `summary.targets` 非 `target_count` · 零目标**在 apply 之前**短路（下标比较）· 三成因文案 · 标签与配色都不是成功 · 成功文案由真实 `applied` 派生 |
| E 绑定 × 宿主双向 | 9 | 6 个 UI 绑定逐个「有声明 × 被模板消费」· 哨兵反向自检 · 注释剥离反向自检 · **模板用到的 scoped 类必须真有样式** |
| F 前后端交叉锁死 | 6 | 后端 `DelegationSelector.wp_index_ids` · `summary.targets` 真键 · apply 三个计数键 · 空列表 422 · **SOD 是 409 而非 422** · 版本/过期/篡改/成员变化四条 409 文案 |
| G **行为级（mount 真跑）** | 7 | 三组中间 409 → 另两组照旧落库且计数不被抹 · 两阶段 body **深相等** · 零目标不调 apply · SOD/conflict 分类正确且不计入 retryable · 单组重试只动该组 · 取消确认零请求 · 不调 `assignProcedures` |

🔴 **源码级与行为级缺一不可**：Task 13 那类「模板调了个零声明标识符」只有 mount 能抓；而「一组 409 不中断其余组」这种时序性质只有真跑一遍才算证明。本轮 G 组 7 条正是靠 mount 才在 M2/M5 上把缺陷抓出来的。

### 变异检验 12/12 全 RED

判定按**失败测试名集合差集**（不看退出码），显式区分 RED / GREEN(守卫缺陷) / ANCHOR-MISS / WRONG-TEST 四态，并额外把「整文件 collection error」（零断言执行的第五态）单独收进失败名集合。基线 `total=55 passed=55 failed=0 suites=9`；两个被变异文件 md5 字节级还原一致（`3812a95157c6` / `6bf789f70cf2`），`.bak` 零残留。

| 编号 | 变异 | 打红 |
|---|---|---|
| M1 | selector 退回 `cycle` 粒度 | 2 |
| M2 | 从组件 group 读不存在的 `wpIndexIds`（Task 18 原缺陷） | 7 |
| M3 | apply 侧另构造一份 body（防篡改 hash 会不一致） | 1 |
| M4 | `targets === 0` 不再短路（`applied:0` 冒充成功） | 3 |
| M5 | 一组非 applied 即 `break`（放弃其余组） | 4 |
| M6 | SOD 类 409 也提示「重新预览」（三分类塌成一类） | 2 |
| M7 | `retrySuggestionGroup` 重建 `groups` 数组 | 2 |
| M8 | 改调 `assignProcedures`（底稿主编层另一真源） | 2 |
| M9 | 模板去掉单组「重新应用」按钮 | 3 |
| M10 | 逐组改 `Promise.all` 并行提交 | 1 |
| M11 | 组件导出类型把 `wp_index_ids` 改 camelCase | 1 |
| M12 | `no_target` 标签改成「已应用成功」 | 2 |

### 变异检验暴露的**我自己守卫的一个洞**（首轮 M2 = WRONG-TEST）

首版判据写成 `expect(SEG.script).not.toMatch(/\bg\.wpIndexIds\b/)` —— 变异体 `[...(g as any).wpIndexIds]` **一个类型断言就绕过**（`g` 与 `.` 之间多了 `as any)`）。当时 7 条新增失败全来自行为级 G 组，源码级那条纹丝不动 ⇒ 判定 WRONG-TEST。

改法从「禁某个固定标识符」换成**按接收者判**：提取脚本里所有 `.wpIndexIds` 的接收者（`([A-Za-z_$][\w$]*|\))\s*\.wpIndexIds`），断言每一个都必须是 `state`（本页 `SuggestionApplyGroupState`）；括号收尾即任意表达式/强转，一律不合格。并补一条反向自检：构造 `(g as any).wpIndexIds` 必须被提取出接收者 `)`，而 `state.wpIndexIds.length` 必须只提取出 `state`。改完 M2 转 RED（7 → 8 条，含预期项）。

**这是「禁字符串出现」类判据为何不可靠的又一实证**：绕过它不需要改语义，只要改写法。判据必须落在结构关系（谁点谁）上。

### 另一个守卫自身缺陷（写作期即打红，未进变异脚本）

拿花括号配对的 `braceBlockAfter` 去截 python 的 `class DelegationSelector` —— python 类没有花括号，命中的是类体内 `to_payload` 的 `return {...}` 字典字面量，于是断言在无关文本上求值，并以「后端未声明 `wp_index_ids`」的形态**假红**。已加 `pyClassBlock`（缩进边界 + 越界自检），并保留一条对照断言「花括号法在 python 上必然截错」，防后续会话把两个 helper「统一」成一个。

### 零回归（前后对照，未用 HEAD-swap）

`src/views` 全面，判据用失败名集合差集（该面有 31 条预存在失败，看计数会把「修一条 + 新增一条」误判成无变化）：

- BEFORE（本轮改动前、同会话实测）`total=779 passed=748 failed=31 suites=233`
- AFTER `total=834 passed=803 failed=31 suites=242`
- **仅在 AFTER（新增失败）= 0；仅在 BEFORE（被修掉）= 0；共有失败 31 条逐条相同**

31 条与 Task 14 收口基线完全一致（PartnerProjectDashboard 15 / ReportView.filesize-invariant 2 / WorkpaperListShell 3 / line-budget 2 / useNoteTree.indexRef 1 / useReportColumns 3 / useReportCrossCheck.p32 2 / useReportCrossCheck 2 / useReportExport 1 = 31），全为预存在。`ProcedureTrimming.twoLayer.spec.ts` 不在失败列表 ⇒ 保持绿。

**后端零回归天然成立**：后端一字未改（仅被守卫**读取**）。

### 验证汇总

| 项 | 结果 |
|---|---|
| 新守卫单跑 | **55 / 55**（9 suites） |
| 8 个必查 spec 合并跑 | **317 / 317**（63 suites） |
| `backend/tests/procedure_trim/` | **238 passed / 1 skipped**（与基线一致，skip 为 Task 10 预存在的连库样本缺失） |
| 变异检验 | **12/12 RED**，md5 双文件还原一致，`.bak` 零残留 |
| 零回归 | 新增失败 **0** |
| Vite transform | `ProcedureTrimming.vue` / `GtDelegationSuggestionTable.vue` / 新守卫 spec 全 **200** |
| 中文引号 / U+FFFD 扫描 | 两个改动文件 **0** 命中（模板属性里的中文弯引号会静默崩 Vite） |

### 平台级事实（后续会话可直接引用）

- 🔴 **`get_diagnostics` 在 `ProcedureTrimming.vue` 上返回恒 0**，连 `const x: number = '字符串'` 都不报。此前 Task 13 / 14 的记录把「`get_diagnostics` 全 0」列为四层证据之一 —— **在本文件上那一层是空的**。要核类型面只有一条路：临时 tsconfig 只 include 一个小 probe.ts（全项目 `vue-tsc` 4 GB / 8 GB 堆均 OOM），并且**必须带负控制**（不存在的导出 + 类型不匹配都要真打红），否则「静默通过」同样可能是没在检查。
- **`<script setup>` 里的 `export interface` 可被别处 `import type`**（隔离 vue-tsc 正负控制双证）⇒ 组件与宿主之间共享载荷类型不必再镜像一份。
- **委派 409 有三个语义**（stale / assigned_conflict / SOD），且 SOD 走的是 `assert_sod_distinct` 的 409 而不是 422。任何「409 → 请重新预览」的一刀切处置都会在 SOD 上把用户带进死循环。平台其它消费 409 的地方值得照此排查。
- **`materialization_pending` 已是死分支**（`procedure-mainline-convergence` Task 4.1 改同步物化）。「行任务未物化」现在的可观测形态是 `summary.targets === 0`，而 apply 在零目标下返回 200 + `applied: 0` ⇒ 任何不把零目标单列一态的实现都会稳定地把「一行未动」显示成「委派成功」。
- **真实库（2026-08-10 只读实测）**：`procedure_row_tasks` 157 行 / 3 个项目（已分配 65）；`procedure_instances` 34 个项目、已裁剪 **0** 行。唯一有实测价值的项目是 **重药控股安徽有限公司_2025**（`0ec33ac9-…`，13 个 wp_index，cycle I 5 张 / A 9 张 / B 3 张 / G 3 张 / D 9 张 / K 1 张，execute 任务 127）。其余 31 个有 `procedure_instances` 的项目在建议分配表上会命中 `no_target`。

### 未做（留给 Task 26 的浏览器实测清单）

本轮**没有任何一次真实 HTTP 请求打到后端** —— 逐组编排全部由 mount + mock 覆盖。以下只有浏览器能确认，请并入 Task 26：

1. **逐组 apply 真落库**：在 `重药控股安徽有限公司_2025` 的 I 或 D 循环生成建议 → 改成 2~3 个执行人 → 应用 → 独立查询核 `procedure_row_tasks.assignee_staff_id` / `assignment_version` / `delegation_batch_id`（每组一个 batch）/ `workpaper_delegation_history` 行数。
2. **一组 409 不影响其他组**：应用前用另一会话改动其中一组的目标任务（顶掉 `lock_version`），确认该组标「需重新预览」而其余组照旧落库；再点该组「重新应用」转绿。
3. **SOD 409 的真实文案**：把某组复核人设成执行人本人（需绕开组件下拉的构造性约束，例如直接调 `vm.onSuggestionApplyRequest`），确认后端 409 文案含「职责分离」且被归到 `sod` 而非 `stale`。
4. **`no_target` 真形态**：在一个只有 `procedure_instances` 而无 `procedure_row_tasks` 的项目上应用，确认同步物化后仍为 0 目标、UI 显示「无可委派目标」而**不是**「已应用」。
5. **裁剪 → 委派联动第一次真有数据流**：裁掉某底稿后确认它不再出现在建议分配目标里（`_trimmed_scopes()` 至今恒返空集，本 spec 落地后才第一次生效）。
6. Task 14 遗留两项（逐循环覆盖写入 → 撤销 → 复原；覆盖某循环后该循环的「金额低于重要性」建议是否真的消失）。

实测前抓基线（目标行的 `assignee_staff_id` / `reviewer_staff_id` / `lock_version` / `assignment_version` / `procedure_row_task_history` 行数），实测后复原并以**独立查询**核实 —— 注意 `procedure_row_task_history` 是 **append-only**（有触发器保护，`DELETE` 会被拒），复原方案需按此设计。

---

## 交付实录 · Task 20 裁剪充分性复核视图（2026-08-10）

### 一句话结论

只读复核视图按计划落地，**但任务书的第三条 bullet（「因重要性原因裁剪的金额合计与重要性水平对比」）在当前后端下无法从已落地事实算出** —— `suggestion_state` 实际只写 `reason_code` 与 `rejected` 三兄弟，`evidence` **从未被写过**（design.md 与 `_write_suggestion_reason_code` 的 docstring 都提到它）。故已确认裁剪的科目余额只能由宿主用**同一个** `resolveAccountName` 当场重解析，解析不到就必须单独报「金额无法定位 N 项」而不是当 0 计入合计 —— 后者会让复核者看到一个偏低的汇总额并据此认为敞口可接受。

### 产出

| 文件 | 性质 |
|---|---|
| `.../components/workpaper/composables/trimAdequacyReview.ts` | 新建，统计派生纯函数（零 IO / 零 Vue / 零 async） |
| `.../components/workpaper/trim/GtTrimAdequacyReview.vue` | 新建，只读复核组件（**不 import 任何 api/http**） |
| `.../views/ProcedureTrimming.vue` | 宿主接线 + 单一真源收敛；3430 → **3660**（+230 行） |
| `.../views/__tests__/trimAdequacyReview.spec.ts` | 新建守卫 **67 例 / 7 suites**（源码级 51 + mount 行为级 16） |
| `.../views/__tests__/trimDecisionWiring.spec.ts` | **修 Task 13 守卫的 helper 缺陷** + 判据跟随新真源 + 1 条自检 |
| `backend/scripts/check/mutate_task20_review_guards.py` | 新建变异脚本 **14 条，14/14 RED** |

**后端零改动**（`procedure_trim_service` / `trim_decision_context` / 三个端点一字未动，仅被守卫读取）。

### 做了什么

**（1）纯函数 `buildTrimAdequacyReview`** —— 各循环保留/已裁/建议待确认/缺理由/系统判据裁/人工判据裁/已驳回/异常数、理由码分布（machine / manual / legacy_text / missing 四桶）、重要性对比面板、异常清单。

🔴 **金额汇总一行都不自己写**：两道闸（待确认那批、已确认那批）**都**走 `evaluateAggregateGate`，由它承担「只计重要性类理由码 / 按科目去重 / `>=` 而非 `>`」三条约束。自己写一遍求和就是第二份去重与阈值口径，两边分叉时无从裁决谁对。守卫断言 `buildMaterialityPanel` 内 `evaluateAggregateGate(` 恰 2 次且**不出现 `Math.abs`**（变异 M2 验证承重）。

**（2）宿主侧把汇总闸输入收敛成两个具名 computed**：`suggestedGateItems`（唯一 map 点）与 `performanceMateriality`（唯一读取点），`aggregateGate` 与复核视图**共用**它们。这不是省字：R12.7 的「相同输入下逐项相等」只有一种可靠落法 = 两处调同一个函数吃同一份输入。守卫既有源码级断言（`suggestedRows.value.map` 全文恰 1 处 / `materiality?.performance_materiality` 恰 1 处），也有 mount 行为级断言 `vm.trimAdequacyReview.materiality.suggestedGate` **deepEqual** `vm.aggregateGate`。

**（3）三个未知态一律不退化为 0**（各配变异）：

| 未知 | 表现 | 退化成 0 的后果 |
|---|---|---|
| 循环未加载 | `loaded=false` + `suggested=null`，计数不进合计 | 合计虚低，复核者以为该循环没裁过东西 |
| 待确认不可派生 | `suggested=null`，列显示「需打开该循环」 | 读成「该循环没有待确认建议」 |
| 重要性水平未确定 | `materialityAvailable=false`，该格显示「未确定」 | 「合计 0.00 元 < 重要性」= 谎报已做汇总评估 |
| 完整性覆盖读取失败 | `completenessOverrideUnknown=true`，**不产出**任何平台默认异常 | 把技术故障说成「本项目 11 个循环全未确认」 |

**（4）异常三类，detail 必须写清判据与后果**（不是只给行上色）：高风险/特别风险科目被裁（severity high，detail 带出科目名 + 风险词 + 现有理由 + 准则要求）· 缺理由的裁剪（high）· 完整性判据取平台默认未经确认（medium，detail **带出平台默认的审计依据原文**）。守卫断言每条 `detail.length >= 40`，并有一条 mount 断言那段依据原文真的渲染出来了。

**（5）定位是真定位**：`onReviewLocate` 复用既有 `jumpToCycleFromOverview`（含脏检查）切循环 → 把 `searchText` 设为 wp_code 过滤到那一条 → `locatedWpCode` + 主表 `:row-class-name="procedureRowClass"` 行高亮 → 工具栏出现可关闭的「已定位 X」提示（否则复核者会以为该循环只剩一个程序）。循环级异常没有具体程序，改为打开完整性敏感清单面板。mount 断言 `filteredProcedures.length === 1`。

**（6）只读是承重属性，用「没有能力」而不是「约定不做」保证**：组件**不 import 任何 `services/` 或 `utils/http`**（没导入就调不到）。守卫三层：import 源扫描（主判据）+ 写入函数名剥注释后缺席 + `.(post|put|delete|patch)(` 结构缺席；再加 mount 级 `expectNoWrites`（8 个写 mock + `http.post` 全未被调用）。反向自检断言这些名字在**宿主**里确实存在，证明前一条不是恒真。

### 任务书与代码接触后不成立之处（4 处）

1. **「因重要性原因裁剪的金额合计」的判据数值未持久化**（见上）。`_write_suggestion_reason_code` 只写 `{**existing, "reason_code": reason_code}`；driver 的 docstring 与 `/reject` 分支的注释都提到 `evidence`，design.md 的 `suggestion_state` 结构也列了它 —— 但**代码从未写它**。这属于平台已登记的「注释/设计承诺了而实现没做」，且因为 `evidence` 只被读侧期待、无人断言，四层检查全绿。本轮**不补写**（那要动 canonical entry 载荷，会破 Task 12 的「未携带 `reason_code` 时逐字节不变」保证），改为如实分报「可解析合计」与「无法定位条数」。

2. **「各循环…建议待确认计数」对非当前循环不可派生**。Task 13 已定性并留了守卫（概览侧不得读原始行上不存在的 `_suggest`）。本轮遵守该边界：`suggested` 是 `number | null` 三态，只有当前循环取 `suggestionStats.value.suggested`（同真源），其余传 `null`；一个循环都不可派生时 `totals.suggested` 亦为 `null`。守卫有一条断言 `reviewCycleInputs` 实参区**不含** `_suggest`。

3. **跨循环解析科目会张冠李戴 —— 任务书没提，而它比解析不出更坏**。后端 `_load_accounts` 按 `cycles` 过滤，而 `resolveAccountName` 是对上下文里**全部**科目名做最长匹配。拿 D 循环的 accounts 去解析 E 循环的程序，会得出**另一个循环科目的金额**：数字看起来合理、来源完全错。故新增 `trimContextCycles`（与 `trimContext` 同一次更新，避免「上下文是 D 的、覆盖面标着 E」的中间态），未覆盖循环一律按「金额未知」。变异 M13 验证该门控承重。

4. **「缺理由」口径刻意与概览逐字一致（已裁剪且理由文本为空），不是「无理由码」**。后者会把只有自由文本的存量裁剪误判成缺理由（R8.4），进而让复核视图的「缺理由」计数虚高 —— 而这个数是复核者决定是否退回项目组的依据。存量记录单独进「仅自由文本」桶。变异 M10 一次打红 4 条。

### 变异检验暴露的**我自己守卫的三个缺陷**

1. **`expect(w.text()).not.toContain('0.00 元')` 被 `1,000.00 元` 里的子串命中**（首轮 67 例里唯一那条红）。判据想说的是「重要性未确定时那一格不得渲染金额」，写成整组件文本的禁止子串后，被**另一格**的合计金额打红 —— 假红。改为 `matCellValue(w, '实际执行重要性') === '未确定'`（按标签定位到那一格），并补一条反向自检：重要性已设时同一格必须是 `500,000.00 元`（否则前一条可能恒真）。**又一次证明「禁某个字符串出现」类判据不可靠**：这次是误命中导致假红，Task 19 那次是类型断言绕过导致假绿。

2. **`toContain('<GtTrimAdequacyReview')` 会被改名后的 `<GtTrimAdequacyReviewXX` 以子串形态骗过**（设计 M12 时发现）。改为 `/<GtTrimAdequacyReview[\s/>]/` 带定界符，M12 随即转 RED。这条判据管的正是 Task 14 那类「import 了却没有渲染宿主」的缺陷，若被子串骗过则整个复核视图打不开而守卫全绿。

3. **Task 13 的 `computedArg` 对带类型参数的 `computed<T>(` 直接失配**。它写的是 `computed\s*\(`，遇到 `computed<number | null>(` 返回空串 ⇒ 以「未找到该 computed」的形态**假红**。已改成 Task 14 定过的形态（只锚 `const NAME = computed`，再取其后第一个 `(` —— 泛型里不会有圆括号），并在该文件的 helper 自检组补一条覆盖四形态（无泛型 / 简单泛型 / 嵌套泛型 / 不存在的名字）。注意也**不能**写 `computed\s*(?:<[^>]*>)?\s*\(`：`computed<Record<string, boolean> | null>(` 里 `[^>]*` 会停在内层 `>`（Task 14 的原始成因）。

第四个（不在变异脚本内，是零回归脚本自身的缺陷，一并记以免重犯）：**inverse-patch 的块结束锚给了 `')'`，而 `() =>` 里的 ASCII `)` 更早出现** ⇒ 块被截短、文件残留一个孤立 `)` ⇒ Vite 500。是脚本里「删完先过 Vite transform 再跑测试」这道自检拦住的；没有它，BEFORE 侧会整文件 collection error，而我会拿一堆垃圾去做差集。

### 变异检验 14/14 全 RED

判定按**失败测试名集合差集**（不看退出码），显式区分 RED / GREEN(守卫缺陷) / ANCHOR-MISS / WRONG-TEST / NO-JSON 五态。基线 `total=111 passed=111 failed=0 suites=2`；三个被变异文件 md5 **字节级还原一致**，`.bak` 零残留。锚点全部行级唯一（`hits == 1`，禁含 `\n`），且变异后断言字节确实变了。

| 编号 | 变异 | 打红 |
|---|---|---|
| M1 | 复核组件 import 并调用 `canonicalTrimApply`（破只读） | 3 |
| M2 | 已确认那道闸自己 `Math.abs` 求和（不走 `evaluateAggregateGate`） | 1 |
| M3 | 复核视图另构造一份建议项（第二真源） | 2 |
| M4 | 未加载循环的待确认数补成 0 | 1 |
| M5 | 非当前循环的待确认数补成 0 | 1 |
| M6 | 重要性未确定时仍给出「合计低于该水平」结论 | 1 |
| M7 | 金额无法定位的按 0 计入合计（汇总额偏低） | 1 |
| M8 | 覆盖表读取失败当成「全部平台默认」 | 1 |
| M9 | 移除 `riskKnown` 前置（把未评估当成高风险） | 2 |
| M10 | 缺理由判据改看理由码（存量自由文本被误判成缺理由） | 4 |
| M11 | 定位只切 Tab 不过滤到该条 | 2 |
| M12 | 复核组件标签改名（模板宿主实际不存在） | 1 |
| M13 | 去掉循环覆盖门控（跨循环解析科目） | 1 |
| M14 | 平台默认异常的 detail 塌成一句结论词（丢掉审计依据） | 3 |

### 类型面（`get_diagnostics` 在 `ProcedureTrimming.vue` 上仍是盲的）

沿用 Task 19 的隔离 tsconfig 法（全项目 `vue-tsc` 4G/8G 堆均 OOM），临时 tsconfig 只 include 一个 probe.ts：

| 探针 | 结果 |
|---|---|
| 正控制（真实用法：组件默认导入 + 5 个类型 + `buildTrimAdequacyReview` 调用） | **静默通过**（0 相关诊断） |
| 负控制 1：不存在的导出 | **TS2305** ✔ |
| 负控制 2：`number = review.materiality.narrative` | **TS2322** ✔ |
| 负控制 3：`review.__t20NoSuchField__` | **TS2339** ✔ |

三条负控制都能打红 ⇒ 正控制的静默是「真的检查过了」，不是「压根没在检查」。首轮探针 `extends: ./tsconfig.app.json` 失败（本项目只有一个 `tsconfig.json`，无 app/node 拆分）—— 那时四个 case 全 exit=2，若只看退出码会把「负控制打红」误判成有效。

### 零回归（真前后对照，未用 HEAD-swap）

BEFORE 的构造方式：脚本把本轮对 `.vue` 的 10 个块逐个 exact-substring 删除（每块 `count == 1` 断言 + 8 个标识符残留自检），并把**本轮新建/改过的 4 个 spec 一并移出收集面**（`trimDecisionWiring.spec.ts` 本轮改了两处，对 BEFORE 的 `.vue` 必然打红 —— 那是改动本身不是回归；它在 AFTER 侧已单独证明 44/44 全绿）。删完先过 Vite transform（200）再跑测试。

| | total | passed | failed |
|---|---|---|---|
| BEFORE | 792 | 761 | 31 |
| AFTER | 903 | 872 | 31 |

- **仅在 AFTER（新增失败）= 0；仅在 BEFORE（被修掉）= 0；共有失败 31 条逐条相同**
- 31 条与 Task 19 / Task 14 收口基线**文件对文件、条数对条数完全一致**（PartnerProjectDashboard 15 / ReportView.filesize-invariant 2 / WorkpaperListShell 3 / line-budget 2 / useNoteTree.indexRef 1 / useReportColumns 3 / useReportCrossCheck 2 / useReportCrossCheck.p32 2 / useReportExport 1 = 31），全为预存在
- 测试数增量 111 = 67（新守卫）+ 44（BEFORE 侧被移出的 `trimDecisionWiring`）**逐项对得上** ⇒ 没有任何既有测试消失
- 还原后两个文件 md5 与快照一致，`.aside` / `.t20snap` / 非受保护 `.bak` 零残留；`backend/app/routers/wp_template.py.bak`（32857 B）与 `backend/data/procedure_table_templates.json.bak`（449699 B）**未动**

**后端零回归天然成立**：后端一字未改。

### 验证汇总

| 项 | 结果 |
|---|---|
| 新守卫单跑 | **67 / 67**（7 suites） |
| 7 个必查 spec 合并跑 | **269 / 269** |
| `backend/tests/procedure_trim/` | **238 passed / 1 skipped**（与基线一致） |
| 变异检验 | **14/14 RED**，md5 三文件还原一致，`.bak` 零残留 |
| 零回归 | 新增失败 **0**，消失 **0** |
| Vite transform | 5 个改动/新建前端文件全 **200** |
| `get_diagnostics` | 6 个文件全 0（⚠️ 在 `ProcedureTrimming.vue` 上此项**不构成证据**） |
| 隔离 vue-tsc | 正控制静默 + 3 条负控制全 RED |
| 中文弯引号 / U+FFFD | 两个 `.vue` **0** 命中（守卫内亦有一条断言） |

### 真实库现状（本轮只读复核，未连库写入）

复核视图的每一个计数在真实数据上都是 **0**：`procedure_instances` 34 个项目 **0 条已裁剪** ⇒ 已裁/理由码分布/异常清单全空；`materiality` 仅 2/14 项目有数据 ⇒ 多数项目走「重要性水平未确定」分支；`checklist_responses` 1,034,515 行中 `B50-T3-*` 仍为 **0 行** ⇒ `riskKnown` 恒 false，「高风险科目被裁」这条异常**在真实数据上不可达**。故本轮全部证据来自**构造输入 + mount**，报告中不声称任何非零路径已在真实库验证过。

### 未做（并入 Task 26 的浏览器实测清单，第 7~10 项）

7. **复核视图抽屉真渲染 + 异常卡视觉分层**：scoped CSS 缺类不报错、渲染照旧，`get_diagnostics` 与 vitest 全查不出，只表现为三态同一个样子（Task 14 已在本文件踩过一次）。守卫只能断言「模板用到的类在 `<style>` 里存在」，看不出层次是否可读。
8. **定位真的滚到并高亮那一行**：`row-class-name` 在真实 `el-table` 上生效、`max-height` 滚动容器内可见。stub 下只能验 `procedureRowClass` 的返回值。
9. **「高风险科目被裁」异常的可达性**：需先在测试项目手填某科目 B50 `completeness` 认定为 `H`（或勾特别风险）→ 裁掉其程序 → 打开复核视图确认异常出现、detail 带出科目名与风险等级、点击能定位到该程序；**实测后复原**（`checklist_responses` 的 `B50-T3-*` 行数须回到 0）。
10. **跨循环覆盖面的诚实性**：只加载 D 循环判据上下文后打开复核视图，确认其它循环的已确认金额类裁剪被计入「金额无法定位」而不是 0，且 narrative 出现「实际汇总额高于此数」。

实测前抓基线（目标行 `status` / `skip_reason` / `suggestion_state` / `checklist_responses` 行数 / md5 与 `updated_at`），实测后复原并以**独立查询**核实。

---

## 交付实录 · Task 21 附注反向联动（2026-08-10，恢复 19:50 中断的验证阶段）

### 一句话结论

**实现侧本轮零改动** —— 19:50 那次中断发生在验证阶段，落盘的实现经五项盘点全部齐备（这是本 spec 迄今唯一一次「on disk 就是完整的」）。本轮的实质产出在**守卫**：变异检验 20 条首轮得 **16 RED / 4 GREEN**，四条 GREEN 全是我方守卫缺陷，其中两条暴露出一个更要紧的事实 —— `resolve_linkage_plan` 的两个合取项在**正常输入上互相蕴含**，「守卫样本命中了同一条 `if`」不等于「命中了那条 `if` 里的每个合取项」。修正后 20/20 RED。

### 一、模块归属勘查：谁拥有「不适用」决策，谁只是消费

平台有六个 `is_empty` 邻近模块，名字近而判的东西完全不同。逐个落定归属后才敢说 R13.7 的「不新建第二套」成立：

| 模块 / 字段 | 它判/存什么 | 与本任务的关系 |
|---|---|---|
| **`disclosure_notes.is_empty`（列）** | 「本期不适用 / 不导出」的**唯一持久化真源**。`disclosure_engine.get_notes_tree` 按它产 `status:"not_applicable"`；Word 导出按同一 helper 跳过 | 本联动**唯一写入**的字段 |
| **`note_content_utils.note_has_data`** | 「该章节有没有内容」——与 `NoteWordExporter._has_content` 收敛的**唯一**口径（归档 spec `disclosure-notes-selective-generation` Req2）。首句是 `if note.is_empty: return False` | 本联动**唯一调用**的判定 helper |
| `note_trim_service` | 附注侧章节裁剪向导，判据 = 试算表科目余额全 0。写三处：`NoteSectionInstance.status='not_applicable'`（另一张表的状态列）/ `DisclosureNote.is_deleted=True`（**删章节**，`auto_trim_v2` 段落级）/ `table_data['_render_as']='no_business_paragraph'`（改业务载荷）。**一次都不写 `is_empty`** | **零重叠**。三条路都与 R13.2「不删章节、保留可恢复性」直接冲突 ⇒ 不得复用。守卫 `test_a3` + 变异 M2 钉死。它在 `template_lineage` 写 `deletion_reason`/`deletion_at`（注释原话「无独立列，避免 schema 改动」）恰是本联动面包屑做法的平台先例 |
| `note_is_empty_calc.is_section_empty` / `is_table_data_empty` | 带数值阈值的 *material* 判空，专供 D5 `auto_trim_v2`（判「能不能删这一章」） | 不同概念（「值全 0」≠「本期不适用」）；守卫 `test_b2` 禁引用 |
| `note_empty_table_detector.is_empty_table` | **投影后单表**判空（跳合计/段标题/`expandable` 行，`_ZERO_EPS=0.005`），服务表级折叠与导出省略 | 表级 ≠ 章节级；同上禁引用 |
| `note_word_dynamic_styles.should_skip_empty_section` | Word 侧 skip 判定；其中把 `is_empty=True` 注释为「用户『不导出』标记」，且**自带第三个** `is_empty_table` | 只**消费** `is_empty`，不写 |

**结论**：决策归属唯一 —— 持久化真源 = `is_empty`，判定真源 = `note_has_data`；另外四个模块要么只消费、要么判的是另一个概念。本任务未与任何一个重叠，也未引入第六个判空口径。

🔴 **顺带勘出一条 tasks.md 未提而对 R13.3 决定性的事实：`is_empty` 已有三类写入方**（本联动是第四类）——`note_conversion_service` 新建「目标侧独有章节」时写 `is_empty=True`（空骨架）、审计师在附注侧手工标记、以及本联动。⇒ 撤销**必须**凭 provenance 判归属，否则会清掉前两类。守卫 `test_f5` / `test_f4b` + 变异 M10 钉死。

### 二、中断前已落盘 vs 本轮新增

**已落盘（md5 与交接时逐一相同，本轮未改一字）**

| 文件 | 规模 | 盘点结论 |
|---|---|---|
| `backend/app/services/procedure_trim_note_linkage.py` | 534 行 | 完整。只写 `is_empty` + 面包屑，判定只调共享 helper |
| `backend/app/routers/procedure_trim.py` | `GET /note-linkage?year=` + `POST /note-linkage/apply` + `NoteLinkageApplyRequest` + docstring 3 行 | 完整，两端点均挂 `require_project_delegator_pid` |
| `services/apiPaths/workpaper.ts` | `trimNoteLinkage` / `trimNoteLinkageApply` | 完整，且在 **`procedureRowTasks`** 对象内（barrel 具名 re-export 已含它 ⇒ 无需改 `index.ts`） |
| `services/commonApi.ts` | `NoteLinkageItem` / `NoteLinkageView` / `_normalizeNoteLinkage` / `fetchTrimNoteLinkage` / `applyTrimNoteLinkage` | 完整 |
| `views/ProcedureTrimming.vue` | 5 个块：常驻入口按钮 12L / 面板 `el-dialog` 106L / 脚本段 94L / `saveTrim` 钩子 4L / CSS 16L | 完整 |
| `backend/tests/procedure_trim/test_note_linkage_single_source.py` | 51 例 | 完整 |
| `views/__tests__/noteLinkageHost.spec.ts` | 46 例 | 完整（本轮 → 48） |
| `backend/scripts/check/mutate_task21_note_linkage_guards.py` | 20 条变异 | 完整 |

**五项盘点逐条结果**（用 `python -c "open(p,encoding='utf-8').read()"` 直读，不信 `read_file`）

1. **UI 可达性（双向）**：10 个绑定 `noteLinkagePanelVisible` / `noteLinkage` / `noteLinkageError` / `noteLinkageLoading` / `noteLinkageApplying` / `noteLinkageActionable` / `noteLinkageBuckets` / `applyNoteLinkage` / `loadNoteLinkage` / `openNoteLinkagePanel` **全部 decl=1 且剥注释后模板消费 ≥1**。既不是 Task 13 那种「模板有、脚本无」，也不是 Task 14 那种「脚本有、模板无」。旁证两条：`trimDecisionWiring.spec.ts` 判据 D 把整份模板的未声明自由调用集合**冻结**为恰 `['calc','var']`（CSS 函数），本轮仍绿 ⇒ 新模板没引入零声明标识符；`ProcedureTrimming.twoLayer.spec.ts` 会 mount 组件并真调插槽，亦绿。
2. **scoped 类**：模板用到 `.gt-proc-nlink__bar/__group/__title/__hint/__why` 五个，`<style>` 里**全部存在**。（另发现 7 个存量缺类，属别的任务，见第六节。）
3. **端点一致**：前端两条路径与 router 装饰器逐字相同，方法一致（GET 带 `params:{year}`、POST 体只有 `{ year }`）。
4. **服务不是死输出**：`preview_note_linkage` / `apply_note_linkage` 各有一个真实 router 调用点（不只符号出现）。
5. **文件完整**：`<template>`/`<script setup>`/`<style scoped>` 配对正常，Vite transform **200**（`commonApi.ts` / `apiPaths/workpaper.ts` / 新守卫 spec 亦 200）⇒ 中断没有截断写入。

**本轮新增 = 两个守卫文件的判据修正**（生产代码零改动）：`test_note_linkage_single_source.py` 的 `test_d1` / `test_d4` 各追加一组构造输入；`noteLinkageHost.spec.ts` 的两条判据换实现 + 加 2 条反向自检（46 → 48）。

### 三、任务书与代码接触后不成立之处（4 处）

1. **「跳过并记录」不是一种粒度，是两种**。tasks.md 只写「附注章节无法定位 → 跳过并记录」，实现必须分开：`unlocatable`（附注侧没有该 note 行）与 `skipped_no_scope`（owner 一条 `procedure_instances` 都没有）。合成一条会让「本年度还没生成这一节」与「这张底稿本项目压根没纳入范围」在界面上同形，而两者处置完全不同（前者去生成附注，后者去看裁剪范围）。
2. **「裁剪撤销时标注相应撤销」需要一条任务书未提的 provenance 面包屑**。`is_empty` 是共享字段（见第一节的三类既有写入方），无脑撤销会清掉审计师手工标注与 conversion 建的空骨架。实现落 `template_lineage.procedure_trim_not_applicable`（平台先例见上）⇒ **零迁移**。🔴 它不是第二套不适用字段，判据是结构性的：模块内任何「是否不适用」的判断都不读它，它只决定「本联动有没有权撤销这一条」；`test_c1`/`test_c2` 按 AST 钉死，变异 M9 验证承重。
3. **「复用既有共享 helper」不能把 note 直接传进去**。`note_has_data` 首句 `if note.is_empty: return False`（对附注树是正确行为，Req2.4）⇒ 直接传真实 note 会让**已被本联动标过**的章节恒判「无内容」，于是「标注之后审计师又录了内容」这一情形**永远发现不了**，下一轮联动继续把它压在导出之外。实现传一个 `is_empty=False` 的投影再调同一 helper（判定逻辑仍是唯一那份，只把「我上一轮自己的标注」从输入里剔除）。变异 M3 钉死。
4. **R13.1 的「某科目循环」在 registry 上不是一循环一章节**。实测有跨循环共有章节（`五、42 → [K3, M1]`、`五、8 → [G2, G3, K1]`，共 8 个多 owner 章节）⇒ 判定取两个合取项、取更保守一侧。但这两条在正常输入上互相蕴含 —— 见下节，这一点是变异检验逼出来的，任务书与 design 都没有。

### 四、变异检验暴露的**我方守卫四个缺陷**（首轮 16 RED / 4 GREEN）

#### （A）判据的输入空间没覆盖到被测约束真正承重的那一类（M5 / M7）

- **M5**（去掉 `all_owners_trimmed` 合取项）原判据 `test_d1` 构造 K3 已裁 + M1 在做 —— 此时 `all_cycles_fully_trimmed` 本来就是 False（M 循环没整体裁剪）⇒ 去掉第一条不改变结论，测试纹丝不动。
  根因：**第二合取项在正常输入上蕴含第一条**。「这些循环都整体裁剪」⟹ 该循环内每条 `procedure_instances` 都已裁 ⟹ 其中的 owner 必然已裁。第一条唯一真正承重的输入类 = **owner 行的 `audit_cycle` 为空**：`_load_scopes` 把 NULL 显式转成 `""`（`str(r[0] or "").strip()`），空 cycle 不进 `cycle_rows` ⇒ 该 owner 完全不被循环级判据覆盖。已在 `test_d1` 追加该组（K3 已裁 + cycle 为空的 M1 在做 ⇒ 必须**不**标注）。
- **M7**（同一 wp_code 多条程序改 OR 合并）原判据 `test_d4` 两条都在 J 循环 ⇒ 只要有一条 `execute`，J 就不算整体裁剪，第二合取项已挡住，合并方向无关。承重输入类 = 同一 wp_code **跨循环**重复：J1 在 J 已裁（J 只有它 → J 整体裁剪），J1 在 X 仍需执行；AND 合并取未裁那条 → `cycles=[X]` → 不标注 ✓，OR 合并取已裁那条 → `cycles=[J]` → **误标** ✗。已在 `test_d4` 追加。

  🔴 两类输入在真实库都是 0 行（只读实测：`procedure_instances` 456 行，空 `audit_cycle` 0、空 `wp_code` 0、wp_code 跨循环 0、`(project_id, wp_code)` 重复 0），但 schema 都允许（`(project_id, wp_code)` **无唯一约束**，仅 `id` 主键 + `idx_proc_project_cycle` 普通索引；`audit_cycle` 由代码显式处理 NULL）⇒ 这两个合取项是**对未来数据的防御性冗余**，只能由构造输入钉死。
  **可直接引用的平台经验**：「守卫样本命中了同一条 `if`」不等于「命中了那条 `if` 里的每个合取项」。合取式条件的每个合取项都要各有一组**只有它能挡住**的输入，否则移除任一冗余合取项的变异恒绿。

#### （B）判据落在「字符是否出现」上，改写法即绕过（M17 / M20）

- **M17**（五个桶塌成一个）：把 `items: v.to_mark,` 改成 `items: [...v.to_mark, ...v.conflicts, ...v.unlocatable],` 后，五个 `v.<key>` 依然全在、`key:` 依然 5 个 ⇒ 原判据 GREEN，而界面上「已有内容所以没标」「附注侧没这一节」已混进「将标注」那张表 —— **没标的看起来像已标**。改为断言桶与后端数组 **1:1**（每个桶必须恰是 `items: v.<key>,`；禁数组字面量 `items:[`；禁 `.concat(`；`items:` 出现次数 == 桶数 5）+ 一条反向自检（构造合并形态必须被判不合格、构造合格形态必须通过，防判据过严或恒真）。
- **M20**（删/改一个 scoped CSS 类）：`SEG.style.includes('.gt-proc-nlink__hint')` 在类名被改成 `.gt-proc-nlink__hintX` 后**仍为真**（前者是后者子串）⇒ GREEN，而那一组实际已无样式。改为带右定界符 `new RegExp('\\.' + cls + '(?![\\w-])')` + 反向自检（`.foo__bar {` 通过；`.foo__barX` / `.foo__bar-lite` 必须不通过）。
  **同族于 Task 20 的 `toContain('<GtTrimAdequacyReview')` 被 `<GtTrimAdequacyReviewXX` 骗过**；本轮我自己在盘点脚本里也踩了一次（`.gt-proc-nlink` 被 `.gt-proc-nlink__bar` 命中而误报"有样式"）。⇒ 一切「类名/标签名/标识符是否存在」的判据必须带定界符。

**修正后重跑：20/20 RED**，每条打红的都恰是预期那条测试（无 WRONG-TEST / ANCHOR-MISS / COLLECT-ERR）；`procedure_trim_note_linkage.py` / `procedure_trim.py` / `ProcedureTrimming.vue` 三文件 md5 **字节级还原一致**，`.bak` 零残留。判定按失败测试名集合差集，不看退出码。

| 编号 | 变异 | 判定 | 打红 |
|---|---|---|---|
| M1 | **新增第二套不适用字段**（`note.trim_not_applicable = True`）—— 主判据 | RED | 2（`test_a1` 冻结被赋值属性集合 / `test_a2` 冻结 note 上的赋值） |
| M2 | 改走删章节路径（`note.is_deleted = True`） | RED | 6 |
| M3 | 内容判定不再绕开 `is_empty` 短路 | RED | 3 |
| M4 | 内容判定自己遍历 `table_data` | RED | 4 |
| M5 | 去掉 all-owners 合取项 | RED（修守卫后） | 1 |
| M6 | 去掉 cycle-fully-trimmed 合取项 | RED | 1 |
| M7 | 同一 wp_code 按 OR 合并 | RED（修守卫后） | 1 |
| M8 | 已裁取值域少一个（`skip` 不算已裁） | RED | 2 |
| M9 | 把 provenance 变成不适用判据 | RED | 2 |
| M10 | 撤销不检查归属（清掉人工标注） | RED | 2 |
| M11 | 有内容仍自动标注 | RED | 2 |
| M12 | 定位不到章节时抛异常（阻断裁剪保存） | RED | 7 |
| M13 | 自读 registry JSON | RED | 12 |
| M14 | GET 端点摘掉项目级 Delegator 守卫 | RED | 1 |
| M15 | apply 请求体让前端传章节清单 | RED | 1 |
| M16 | 面板 `v-model` 改绑别的 ref | RED | 4 |
| M17 | 五个桶塌成一个 | RED（修守卫后） | 1 |
| M18 | 加载失败退化成空对象 | RED | 1 |
| M19 | 裁剪保存后不再触发联动（服务变死代码） | RED | 1 |
| M20 | 删掉一个 scoped CSS 类 | RED（修守卫后） | 1 |

### 五、验证汇总

| 项 | 结果 |
|---|---|
| `backend/tests/procedure_trim/`（全目录） | **289 passed / 1 skipped** —— Task 21 前基线 238/1，**+51 恰为新守卫的 51 例**，零回归 |
| `noteLinkageHost.spec.ts` 单跑 | **48 / 48** |
| 8 个 `ProcedureTrimming.vue` 守卫合并跑 | **317 / 317**（`noteLinkageHost` · `trimAdequacyReview` · `trimDecisionWiring` · `delegationSuggestionApply` · `completenessScopeOverride` · `ProcedureTrimming.twoLayer` · `delegationLoadSingleSource` · `b50BadgeSingleSource`） |
| **附注后端测试面**（227 文件：文件名含 `note`/`disclosure`） | BEFORE `103 failed / 6146 passed / 47 skipped` → AFTER `103 / 6197 / 47`；**新增失败 0、消失 0、103 条逐条相同**；passed +51 恰为新守卫 |
| 前端 `src/views` | BEFORE `903 / 871 / 32` → AFTER `949 / 918 / 31`；**新增失败 0**，消失 1（见下）；总数 +46 恰为新守卫（含两个 `it.each` 展开的 19 例） |
| 变异检验 | **20/20 RED**，md5 三文件还原一致，`.bak` 零残留 |
| Vite transform | `ProcedureTrimming.vue` / `commonApi.ts` / `apiPaths/workpaper.ts` / 新守卫 spec 全 **200** |
| `get_diagnostics` | 6 个文件全 0（⚠️ 在 `ProcedureTrimming.vue` 上此项**不构成证据**，Task 19 已实测它返回恒 0） |
| 中文弯引号 / U+FFFD | 我改过的两个文件 **0** 命中 |
| **附注模板 JSON** | `note_template_listed.json` **14:31:24** / `note_template_soe.json` **14:50:24** —— 与交接时逐秒相同、md5 未变；本轮全程未碰附注模板 JSON 与任何 `i*`/`e*`/`g7*`/`k*` 循环文件 |
| 他人 `.bak` | `wp_template.py.bak`(32857 B) / `procedure_table_templates.json.bak`(449699 B) **未动**，仓库内 `.bak` 仅此两个 |

#### 零回归两处必须如实标注的环境影响

1. **首轮 AFTER 多出 8 条「新增失败」，实为后端 dev server 起落所致，不是回归**。`test_disclosure_table_e2e.py::TestDisclosureTableSyncE2E` 的 8 条按 `/api/health`（`localhost:9980`）可达性决定 skip：我第一次跑 AFTER 时服务器在跑（耗时 506s，含真实 HTTP，8 条运行并失败），跑 BEFORE 时已停（224s，8 条 skip）。定性两条独立依据：①那 8 条只打 `/auth/login`、`/projects/{pid}`、`/disclosure-notes/...`、`/notes/export-word`，**一条都不碰 `procedure-trim`** ②在服务器同样停止的条件下把 AFTER 重跑两次（AFTER2 / final），失败名集合与 BEFORE **逐条相同**。⇒ 结论取同环境那一组；本轮**没有**在服务器起着的条件下比对过那 8 条，故不对它们作任何结论。
2. **`src/views` 消失的那 1 条是无固定种子的 fast-check PBT**：`guidanceBar Property 5 renders bar iff guidance non-empty after trim`（`fc.property(fc.string(), …)`，与本任务零交集）。单独连跑 2 次全绿 ⇒ 偶发命中反例。方向无害（只在 BEFORE 红），零回归结论不变。同 Task 18 的经验：**PBT 单次全绿不构成证据**。

#### 零回归构造方法（真前后对照，未用 HEAD-swap）

BEFORE 由**逆向摘除本任务自己的新增**构造 —— 禁 `git show HEAD:` 换文件（本工作树并发度高，HEAD 侧可能含他人未提交成果，且被中断时 HEAD 版会留在工作树）：`.vue` 5 块 + router 3 块按**行级唯一锚点对**删除（两端 `hits == 1`、禁含 `\n`、块间重叠检查），另 3 个整体新增文件（service + 两个守卫）改名 `.aside`。
🔴 保留了 Task 20 那道救命的门：**删完先过语法/transform 门再跑测试**（Task 20 的块尾锚点 `')'` 命中了 `() =>` 里的 `)`，块被截短留下孤立 `)` → Vite 500，全靠这道门拦住）。本轮两道门：router `ast.parse` + `ProcedureTrimming.vue` Vite transform 200；另加**残留标识符自检**（摘除后 6 个前端标识符 + 3 个后端符号必须全部 0 命中，否则块集不完整即中止）。快照后缀用 **`.t21snap` 而不是 `.bak`** —— 变异脚本发现 owned 文件存在 `.bak` 会拒绝启动，而别的会话的 `*.bak` 是活体备份。还原后 5 个文件 md5 与快照逐一相同，`.aside` / `.t21snap` 零残留。

### 六、范围外发现（如实上报，本轮未改）

**`ProcedureTrimming.vue` 模板引用了 7 个 `<style>` 里不存在的 scoped 类，全部是存量、与 Task 21 无关**：`gt-proc-b50-unknown`（Task 4 的 B50 未知态）、`gt-proc-suggest-bar` / `__head` / `__stat` / `__gate` / `__degrade` 与 `gt-proc-suggest-cell`（Task 13 的建议态条与建议列）。后果与 Task 14 踩过的同款：**不报错、不影响渲染、`get_diagnostics` 与 vitest 全查不出**，只表现为建议态条与 B50 未知态没有视觉分层。未改的理由是它属已完成任务的面、且改它会动本轮零回归的对照面；修法就是本轮 M20 定下的带定界符判据 + 补样式。建议并入 Task 26 或单独收口。

**另一条已知既有缺口（服务 docstring 已记，本 spec 不修）**：`note_readiness_service.section_workpaper_map()` 只读 registry 的 `listed` / `soe` 两个**单数**键，而 G1 / G10 另有 `listed_sections` / `soe_sections` **复数**键（衍生工具章节 五、3 / 五、35）；`disclosure_stale_marker.sections_for_wp_code` 有同一缺口。扩它会改变 stale 标记的既有行为面 ⇒ 非加法式，另议。本联动因此对那两个章节不产生联动（表现为「不在计划里」而非报错）。

### 七、真实库现状（只读，未写入）

联动在真实数据上**一次都没有数据流经过**：`procedure_instances` 456 行 / 34 个项目、**0 条已裁剪**（`status` 全为 `execute`）⇒ `resolve_linkage_plan` 在真实输入上恒返全 `applicable`、`to_mark` 恒空。故本轮**全部证据来自构造输入 + 替身 session**，不声称任何非零路径已在真实库验证过。`disclosure_notes` 的 `is_empty` / `template_lineage` 两列均已存在（本任务零迁移）。

### 八、并入 Task 26 的浏览器实测清单（第 11~13 项；该清单原有 10 项）

11. **联动面板真渲染 + 五组视觉分层**：守卫只能断言「模板用到的类在 `<style>` 里存在」，看不出五组是否可读区分（tag 配色 + hint 文案），也看不出 `append-to-body` 的 dialog 在裁剪页滚动容器内定位是否正常。
12. **裁剪保存 → 联动自动弹一次**的真实时序：`saveTrim` 里 `void loadNoteLinkage()` 在 canonical apply commit 之后自吞异常执行。要确认 ①保存成功后面板真弹（`noteLinkageActionable > 0` 时）②联动读取失败时**裁剪保存仍显示成功**（R13.6 不阻断）③失败时面板显示「附注联动状态未知…这不等于『没有需要标注的章节』」而不是空态。
13. **`apply` 真落库 + 幂等 + 撤销归属**（本轮由替身全覆盖，**一次真实 HTTP 都没打过**）：在有已裁剪底稿的项目上点「应用到附注」→ 用**独立查询**核 `disclosure_notes.is_empty` 与 `template_lineage->'procedure_trim_not_applicable'` 四键（`at`/`by`/`cycles`/`wp_codes`）；再点一次确认 `marked=0 revoked=0`（幂等零写入）；把裁剪恢复成 `execute` → 再 apply → 确认标注被撤销且 `template_lineage` **只**少了那一个键（别的键原样）；最后在附注侧手工标一节「不适用」（无面包屑）→ apply → 确认它进 `skipped_foreign_mark` 而**没有**被撤销。
    ⚠️ 前置：真实库 0 条已裁剪 ⇒ 必须先造一条裁剪（Task 26 清单第 1~5 项本来就要造）。实测后连同 `disclosure_notes.is_empty` / `template_lineage` 一起复原，并以独立查询交叉核实；实测前抓基线（目标 note 行的 `is_empty` / `template_lineage` / `updated_at` + `procedure_instances` 的 `status` / `skip_reason` / `suggestion_state`）。

### 九、清理

本轮 `tmp_t21_*` 诊断产物（含 19:50 那次中断遗留的同前缀文件）已**按确切路径**逐个删除，未按扩展名扫目录（平台已登记过一次 `*.bak` 误删事故）。工作树中 `_wip_*` / `tmp_g7_*` / `tmp_ie_*` / `tmp_t18_*` / `tmp_hc_*` 等属并发会话，未动。

---

## 交付实录 · Task 22 变异检验（2026-08-11）

### 一句话结论

12 条变异 **12/12 全 RED**，每条打红的都正是预期那条守卫，字节级还原逐文件一致。但本轮真正的收获在两处 tasks.md 未写的事实：①目标脚本 08-09 就已存在且装着 Task 10 的 16 条变异 ⇒ 落地为**加法式扩容而非新建**；②12 条变异**跨前后端**，判定必须把 pytest 与 vitest 两侧的失败测试名归一到同一个集合求差集 —— 只跑一侧会让另一侧的 6 条恒显 GREEN 而被误判成守卫缺陷。另顺带修掉一个只有 mount 能抓的真缺陷：**降级标注的门控与它的内容互斥**。

### 产出

| 文件 | 性质 |
|---|---|
| `backend/scripts/check/mutate_trim_decision_guards.py` | 加法式扩 `T22-1`…`T22-12`；11916 → **36395 B**；`T10-1`…`T10-16` 逐条保留，`--only` 可分别单跑 |
| `.../frontend/src/views/__tests__/trimDegradationConsistency.spec.ts` | 新建 **21 例 / 5 组**（helper 自检 5 · [A] 渲染宿主独立 5 · [B] 重要性双向等价 4 · [C] 风险双向等价 4 · [D] 非恒真自检 3） |
| `.../frontend/src/views/ProcedureTrimming.vue` | 修缺陷：降级标注独立出宿主（见下） |
### 判定结果（基线 py `289 passed / 0 failed` · ts `589 total / 7 预存在红`）

`命中预期 M/N` 读法：该变异使失败集合新增 N 条，其中 M 条命中预期特征。

| 编号 | 变异 | 判定 | 命中预期 | 期望打红的性质 |
|---|---|---|---|---|
| T22-1 | 移除档 1 风险保护 | RED | 6/9 | 特别风险与高 RMM 不因金额被裁（CAS 1231） |
| T22-2 | 移除认定级优先 | RED | 6/6 | Property 6：完整性认定级优先且短路于循环级清单 |
| T22-3 | 汇总闸去掉按 `accountName` 去重 | RED | 2/2 | Property 10：同一科目多条只计一次 |
| T22-4 | 汇总闸纳入 `no_data` | RED | 1/1 | Property 10：非重要性类理由码不得计入汇总 |
| T22-5 | 阈值 `>=` 改 `>` | RED | 2/4 | Property 11：恰好等于实际执行重要性必须阻断 |
| T22-6 | 移除 `body == item_id` 前缀锚定闸 | RED | 2/3 | 移除后非 matrix 前缀键被误判成矩阵格并污染 `cells` |
| T22-7 | 移除底稿已录入判据 | RED | 2/3 | Property 15：待执行 + 底稿已录入必须保留 |
| T22-8 | 移除驳回判据 | RED | 2/2 | Property 32：已驳回建议恒 keep |
| T22-9 | 让重要性类走 `auto_trim` | RED | 6/8 | Property 2 双向锁死：`auto_trim` 只允许 `no_data` 一种成因 |
| T22-10 | 降级标注重新嵌回「有建议」宿主 | RED | 3/3 | 标注门控不得与它的内容互斥 |
| T22-11 | 移除 `overall_materiality` 禁用约束 | RED | 2/3 | 返回结构任何层级不得出现 `overall_materiality` |
| T22-12 | 前端另算负载 | RED | 3/3 | 负载单一真源（口径与后端「非终态任务数」不同） |

无 GREEN / ANCHOR-MISS / WRONG-TEST / COLLECT-ERROR。`字节级还原核验: OK 全部一致`，`.bak` 零残留；仓库内两个他人活体备份（`wp_template.py.bak` 32857 B / `procedure_table_templates.json.bak` 449699 B）未动。
### 与 tasks.md 描述不符之处（3 处）

1. **「新建」实为「加法式扩容」**。目标脚本 `mutate_trim_decision_guards.py` 08-09 14:05 就已存在（11916 B），内含 Task 10 的 `T10-1`…`T10-16`（打 `workpaper_entry_probe.py` / `trim_decision_context.py` / `test_trim_decision_context.py`），与本任务 12 条**零重叠**。照原文「新建」会覆盖掉 Task 10 的交付资产。落地为保留 `T10-*` 并新增独立前缀 `T22-*`，两族可分别 `--only` 单跑。

2. **三态判定不够，实际实现为五态**。tasks.md 只写 RED / GREEN / ANCHOR-MISS。历史六轮已把另两态钉死并在本轮沿用：**WRONG-TEST**（打红了但不是预期那条 = 污染残留或锚点错行；Task 19 的 M2 首轮就是此态被误判成 RED）与 **COLLECT-ERROR·NO-JSON**（变异体非法语法致整文件零断言执行，或 vitest JSON 未生成；Task 14 的 M8 首版踩过）。故每条变异都声明了期望打红的测试名特征，并断言实际新增失败**包含**它 —— 这也是上表「命中预期 M/N」这一列存在的原因。

3. 🔴 **12 条变异跨前后端，判定必须合并两侧失败名集合**。T22-6 / T22-11 打后端 pytest（`b50_risk_reader.py` 的前缀锚定闸、`trim_decision_context.py` 的不推算约束），其余 10 条打前端 vitest（`procedureTrimDecision.ts` / `completenessExemption.ts` / `trimAggregateGate.ts` / `ProcedureTrimming.vue`）。tasks.md 未提这条 —— 只跑单侧会让另一侧的变异恒显失败集合不变，从而把**有效变异误判成守卫缺陷**。判定统一按 `py::` / `ts::` 前缀归一测试名后求差集，不看退出码。

### 本轮顺带修掉的真缺陷：降级标注的门控与内容互斥

降级标注（R4.4）原先嵌在 `suggestionStats.suggested > 0` 的渲染宿主内。而降级的含义恰恰是**判据维度不可用、算不出建议** ⇒ 该标注在唯一该出现的场景里恒不显示。性质上比 Task 13 那次更隐蔽：Task 13 是 `trimContext` 恒空导致标注恒不渲染（整条链没跑通），本轮是链已跑通、标注也算对了，**但门控条件恰好排除了内容出现的唯一场景**。

源码级断言抓不住这类缺陷（宿主在、标注在、`degradationNotes` 也在），只有 mount 行为级能抓 —— 新守卫 [A] 组第 2 条即断言「标注块不得嵌在建议态条宿主内」，[D] 组第 3 条断言「两个 arm 的 DOM 文本必须不同」（防标注恒显或恒隐）。修复时刻意在模板注释里留了「条件与内容互斥」字样以记录成因，守卫 helper 自检有一条依赖它，**后续会话不要删那段注释**。
### 🔴 前端 7 条基线红的定性：到期未回收的冻结基线，不是回归（移交 Task 23）

基线 `ts 589 total / 7 failed` 里那 7 条**全部**是 Task 5 埋的「类 A 改造前基线」快照，断言文本自己就写着落地后应转红：

| 基线断言 | 自述的到期条件 |
|---|---|
| `TrimReasonCode 现有取值域快照 当前恰为这 4 值` | 「Task 12 落地后本条应改为 ⊇ 并登记新增值」 |
| `canonical scope entry 现状无 reason_code` | 「Task 12 需 additive 扩它」 |
| `改造前基线：现状智能裁剪丢弃 amount — 函数体只读 a.cycle，从不读 a.amount` | 「Task 13 落地后本条应转红」 |
| 同上组的「扫描面非空自检：截到 `confirmSmartTrim` 函数体」 | 随上条一并转红 |
| `粗裁现状无结构化理由码 — 裁剪页现状只有自由文本 skip_reason` | 「Task 12/13 落地后本条应转红」 |
| 两条「内存内变异：判据施加于真实源码后必须能打红」（M3 / M4） | 同族的改造前口径 |

Task 12 与 Task 13 均已落地 ⇒ 这 7 条**是设计使然的到期红，不是任何任务引入的回归**。按它们自身注释应改写为「⊇ 并登记新增值」或转为已落地口径。

**本轮不改**：改它会动 Task 23 零回归的对照面（Task 23 要做的正是「施加改动前 vs 施加改动后」的前后对照，基线一动对照就失去意义）。🔴 **明确移交 Task 23 处置**；后续会话看到这 7 条红不要当成 Task 22 的产物，也不要当成待修 bug。

### 零回归

- 后端 `backend/tests/procedure_trim/` = **289 passed / 0 failed**，与 Task 21 收口基线一致（Task 21 记录的 `289 passed / 1 skipped` 中那 1 skip 为 Task 10 预存在的连库样本缺失，本轮变异脚本的基线取样不含它）。
- 前端 16 个守卫文件 = **589 total / 7 failed**，7 条全部为上节所述的到期冻结基线，**新增失败 0**。
- 12 条变异逐条跑完后，三个被变异文件 md5 **字节级还原全部一致**。

### 证据来源与本条实录的写入方式（如实标注）

12 条判定结果与两侧基线数字**均转写自 08-11 08:19 落盘的变异报告**（`tmp_mutate_trim_report.txt` 全文 + `tmp_t22_full.log`），转写完成后按确切路径删除该两文件。执行变异扫描的子代理在写交付实录前被 abort，本条实录由编排器据报告补记 —— **本次补记过程未重跑变异扫描，亦未重跑任何测试**，故上列数字的时点是 08-11 08:19 那一轮，此后若有并发会话改动被测文件则需重跑确认。

### 未做（留给后续任务）

- 那 7 条到期冻结基线的回收 → **Task 23**（见上）。
- 浏览器实测统一归 **Task 26**（清单已累积 13 项：Task 19 留 6 项 · Task 14 留 2 项 · Task 20 留 4 项 · Task 21 留 3 项，含「裁掉某底稿后它不再出现在委派目标里」这条至今无数据流经过的死链条）。
- 变异脚本尚未加挂 CI → **Task 24**（`governance-checks.yml` 现有 139 个 job，`procedure-trim-intelligence` 与 `procedure-trim-intelligence-frontend` 均 0 命中；该文件在工作树里为已修改状态，加挂前需重查并用 `yaml.safe_load` 核对无重名）。
---

## 交付实录 · Task 23 零回归验证（2026-08-11）

### 一句话结论

五条零回归判据全部验证通过，Task 22 移交的 7 条到期冻结基线以**真实前后对照**被证明确实转绿（BEFORE 7 failed → AFTER 0 failed，新增失败 0）。但本轮最有价值的两处都不在计划里：①变异检验抓出**我方守卫的一处假绿**（T23-6 首轮 GREEN —— `toContain('COMMON_SKIP_REASONS')` 被模板消费点骗过），改成声明级带定界符判据后转 RED；②定性一条平台级传输缺陷 —— **PowerShell 5.1 的 `$OutputEncoding` 默认是 ASCII**，中文经管道送子进程被静默换成 `?`，而 `U+FFFD` 检查抓不到它。

### 执行方式的偏离（如实登记，影响可复现性）

实现主体不是本轮产出：13:11–14:56 有会话（被中断的子代理或并发会话）已把四个文件落盘，**但没跑验证、也没写实录**，tasks.md 停在 12:16。本轮 = 磁盘盘点 + 全量验证 + 修一处守卫缺陷 + 补实录 + 收口复选框。

`invoke_sub_agent` 本会话 **5/5 失败**（4× `aborted` + 1× `Improperly formed request`，连最短纯 ASCII 提示亦然）⇒ 由编排器**在主线程直接执行**，这是对编排器模式的明确偏离。期间普通 shell 调用亦多次被 `^C` 打断，长命令改为**后台运行 + 轮询落盘文件**才稳定；诊断结论一律落盘再读（本环境 python stdout 会被转义符污染吞掉）。

### 产出

| 文件 | 性质 | 本轮角色 |
|---|---|---|
| `backend/tests/procedure_trim/test_task23_zero_regression.py`（31 KB / 36 例） | 零回归守卫：五条判据各有承重类 + 反向自检 | 14:47 落盘，本轮首次验证 |
| `.../composables/__tests__/trimNoDataZeroRegression.spec.ts`（29 KB / 30 例） | `no_data` 集合等价 characterization（Property 31） | 14:51 落盘，本轮首次验证 |
| `backend/scripts/check/mutate_task23_baseline_guards.py`（23 KB / 12 条变异） | 变异检验：五态判定 + `.t23bak` + md5 还原核验 | 14:56 落盘，本轮首次执行 |
| `.../composables/__tests__/procedureTrimDecision.spec.ts` | 7 条到期基线回收 | 13:11 落盘；**本轮修 T23-6 假绿**（38612 → 39208 字符） |

🔴 **生产代码零改动**：四个产出全是测试/脚本文件；12:00 后全仓 mtime 扫描（`backend/app` · `backend/data` · `backend/migrations` · `backend/tests` · `backend/scripts` · `frontend/src`）只有它们 + 自动生成的 `auto-imports.d.ts` ⇒ 生产面零回归**结构上**成立，不靠推断。

### 五条判据的落法与承重类

| 判据 | 承重守卫 | 口径 |
|---|---|---|
| (a) `no_data` 自动裁集合与改造前逐条一致 | `trimNoDataZeroRegression.spec.ts`（30 例，含 Property 31）+ `TestMandatoryDivergenceUnreachable` | 唯一分歧输入类是 `is_mandatory=true`，而 ORM 无该列且 `_to_dict` 不下发 ⇒ 分歧**不可达**；等价性用构造输入 + 冻结谓词证明 |
| (b) canonical trim 不带 `reason_code` 时 payload 逐字节相同 | `TestZeroRegressionEvidenceAnchors::test_criterion_b_independent_recompute` + 兄弟 `test_trim_reason_code_contract.py::TestAdditiveZeroRegression` | 独立复算：不传时归一键集恰为扩展前五键 + canonical key；`reason_code` 必须**条件写入**，出现在返回 dict 字面量里即红 |
| (c) 委派 preview / apply 对外契约字段逐字段不变 | `TestDelegationContractFrozen`（8 例） | AST 抽 `preview` / `apply` 的 return dict 键集与冻结基线**精确相等**；另有 HEAD 侧同抽取器比对 + 一条「比对非空转」反向自检 |
| (d) `load_b50_accounts` 三类键解析逐字节相同 | `test_criterion_d_independent_recompute_with_frozen_snapshot` | 按路径 import 兄弟守卫模块，复用 **Task 1 冻结的** `_LEGACY_ROWS` / `_LEGACY_EXPECTED`（不抄第二份，抄了「快照被改」与「实现回归」就不可区分）+ 注入矩阵行必须被察觉的反向自检 |
| (e) 既有附注同步链路输出逐字节不变 | `TestNoteChainUnchanged`（参数化 ≥8 个文件） | 联动模块在 HEAD 里**不存在** ⇒ 结构上不可能改变既有链路输出；另逐文件字节比对 |

### 与 tasks.md 描述不符之处（4 处，均为落地实证）

1. **「零回归判据用前后对照、禁 HEAD 版换文件」这条在 (c)(e) 上被合理放宽，须写清区别**。禁的是「把改动文件换成 HEAD 版**跑同一组测试**」（HEAD 侧可能含他人未提交成果）。而 (c)(e) 用 HEAD 只做**未被本 spec 触碰的文件**的键集/字节比对，不跑测试、不换工作树。⚠️ 但它有一条脆弱性必须登记：若并发会话改了那 8+ 个附注链路文件中任一，该条会**以本 spec 的名义假红**。

2. **Task 22 记录的「前端 16 个守卫文件 589 total / 7 failed」与本轮数字不可直接比对**。Task 22 未列举那 16 个文件；本轮复原的清单与它不同（至少缺 `trimReasonCodes.spec.ts` 与 `procedureTrimDecision.behavior.spec.ts` —— 两者都在变异脚本的 `VITEST_TARGETS` 里）。故**只有那 7 条失败测试名可比**，且逐条吻合；总数（589 / 587 / 614 / 617）跨轮不构成同一基线，本轮结论一律以**同一文件集的自比**为准。

3. **回收前的文件版本 git 里取不到**：`procedureTrimDecision.spec.ts` 未被 HEAD 跟踪（`fatal: exists on disk, but not in HEAD`），13:11 那个会话也没留快照。前后对照改用 **Kiro local history** 取真实旧文件（`History/3573d0c9/J7PG.ts`，08-09 01:06:31，41630 B）—— 这是「禁 HEAD-swap」前提下唯一可用的真前后对照来源，值得作平台经验推广。

4. **变异脚本被 `^C` 打断时，shell 外壳退出但 python 仍在跑**并完成了 `finally` 还原与删备份。中断后**必须独立核残留**、不能看退出码：本轮核了三项 —— `.t23bak` 已消失、`RENAMED_SKIP_REASONS` 只出现在守卫自检断言里（生产文件 0 命中）、`const COMMON_SKIP_REASONS = [` 已回到 `ProcedureTrimming.vue` L1198。另注意 `Select-String` 对该文件两个 pattern 同时零命中（结果不可信），字节级判定一律走 python。

### 本轮修的那一处：T23-6 首轮 GREEN = 守卫缺陷

**现象**：12 条变异首轮 **11 RED / 1 GREEN**。T23-6「把 `COMMON_SKIP_REASONS` 声明改名（破 R8.4 存量自由文本可读）」→ `ts failed=0`。

**机制**：`COMMON_SKIP_REASONS` 在 `ProcedureTrimming.vue` 出现 **2 次** —— 声明 L1198 + 模板消费点 L345（`v-for` 绑定）。变异只改声明行，而判据写的是 `expect(src).toContain('COMMON_SKIP_REASONS')` ⇒ 被模板那处继续命中 ⇒ 恒真。同族于平台已登记的「Task 20 的 `toContain('<GtTrimAdequacyReview')` 被 `<GtTrimAdequacyReviewXX` 骗过」与「Task 21 的 `.gt-proc-nlink__hint` 被 `__hintX` 骗过」。

**修法**（判据从「名字是否出现」升级为**结构关系**，四条）：①声明级带定界符 `toMatch(/const\s+COMMON_SKIP_REASONS\s*=\s*\[/)`；②声明体内必须真有 ≥3 条自由文本项（清空数组同样让存量理由无从选择）；③必须真被模板消费（`v-for` 绑定正则，防「声明在而下拉里选不到」的死代码形态）；④定界符反向自检（把 `RENAMED_SKIP_REASONS` 形态喂给同一正则必须为 false，防判据退回恒真）。

**重跑 T23-6 = RED**，打红的正是预期那条 `裁剪页既有结构化理由码，也保留自由文本理由（R8.4）`；基线仍 `py 325/0` `ts 203/0`，字节级还原 OK，`.t23bak` 无残留。ESLint 该文件 `No issues found`。

### 变异检验 12/12 RED（五态判定，判据按失败测试名集合求差集、不看退出码）

跨前后端，测试名归一 `py::` / `ts::` 前缀到同一集合 —— 只跑单侧会让另一侧的变异恒显失败集合不变，从而把**有效变异误判成守卫缺陷**。

| 编号 | 变异 | 判定 | 打红 |
|---|---|---|---|
| T23-1 | 删掉 Task 12 新增的 `BELOW_MATERIALITY` 取值 | RED | 44（py+ts） |
| T23-2 | 删掉既有取值 `NO_RELATED_BUSINESS`（additive 偷偷删存量） | RED | 10 |
| T23-3 | `reason_code` 无条件写进 `normalized` dict 字面量（破 R8.9） | RED | 5 |
| T23-4 | `buildAndDecide` 退回「丢弃 amount」形态 | RED | 3 |
| T23-5 | 改名 `buildAndDecide`（扫描面失锚必须显式报错而非空转） | RED | 7 |
| T23-6 | 删掉自由文本理由常量 `COMMON_SKIP_REASONS` | **首轮 GREEN → 修守卫后 RED** | 1 |
| T23-7 | `confirmSmartTrim` 内联第二份金额取数（第二判据真源） | RED | 1 |
| T23-8 | 把取金额那行伪装成类型字面量（复现过滤过宽吞掉真实取值行） | RED | 3 |
| T23-9 | 决策内核档 4 去掉循环级兜底（漏裁） | RED | 4 |
| T23-10 | `subjectNoData` 排到 `subjectWithData` 之前（矛盾输入下多裁） | RED | 1 |
| T23-11 | 委派 `preview.summary` 删掉 `already_assigned`（破 R14.1） | RED | 2 |
| T23-12 | `_to_dict` 下发 `is_mandatory`（让「唯一分歧不可达」前提失效） | RED | 1 |

无 ANCHOR-MISS / WRONG-TEST / COLLECT-ERROR。三个被变异生产文件 md5 **字节级还原全部一致**；他人两个活体备份（`wp_template.py.bak` 32857 B / `procedure_table_templates.json.bak` 449699 B）未动。

### 零回归前后对照（真前后对照，BEFORE 取自 Kiro local history 的真实旧文件）

同一 17 个守卫文件集，BEFORE 侧仅把 `procedureTrimDecision.spec.ts` 换成回收前版本（md5 `9dbb3a5b…`，41630 B），`try/finally` 无条件写回后 md5 核验一致。

| | files | total | passed | failed |
|---|---|---|---|---|
| BEFORE（回收前） | 17 | 614 | 607 | **7** |
| AFTER（回收后 + 本轮修 T23-6） | 17 | 617 | 617 | **0** |

- **仅在 AFTER（新增失败）= 0**；共有失败 = 0
- **仅在 BEFORE（被修掉）= 7**，逐条正是 Task 22 点名的那 7 条到期冻结基线：`TrimReasonCode 当前恰为这 4 值` · `归一后的 entry 不含 reason_code` · `函数体只读 a.cycle，从不读 a.amount` · 同组「扫描面非空自检：截到 confirmSmartTrim 函数体」· `裁剪页现状只有自由文本 skip_reason` · 内存内变异 `M3` · 内存内变异 `M4`
- 用例数核算逐项吻合：该文件 `it` 42 → 45（+3），集合总数 614 → 617（+3）
- 还原后 md5 与快照一致

**后端零回归天然成立**：后端生产代码一字未改（仅被守卫读取）。

### 验证汇总

| 项 | 结果 |
|---|---|
| `backend/tests/procedure_trim/`（全目录） | **325 passed / 1 skipped / 0 failed**（Task 21/22 基线 289 + 1 skip ⇒ **+36 恰为新建零回归守卫**；skip 为 Task 10 预存在的连库样本缺失） |
| 前端 17 个守卫文件 | **617 total / 617 passed / 0 failed** |
| 变异检验 | **12/12 RED**（T23-6 修守卫后），md5 三文件还原一致，`.t23bak` 零残留 |
| 零回归 | 新增失败 **0**，被修掉 **7**（= 移交的 7 条到期基线） |
| ESLint（改动文件） | `No issues found` |
| Task 22 移交项收口 | 7 条到期冻结基线**全部回收并转绿**，每条承重方向保留（`⊇` + 新增四值登记 + 前后端交叉锁死 + `reason_code` 条件写入而非恒写） |

### 真实库现状（只读，未写入；不可达路径如实标注）

- `procedure_instances` **0 条已裁剪**（`status` 全为 `execute`）⇒ 判据 (a) 的 `no_data` 集合在真实库**无数据可比**，全部证据来自**构造输入 + 冻结谓词**。🔴 本记录**不声称**已在真实库比对过任何一条。
- `checklist_responses` 的 `B50-T3-*` 仍为 **0 行** ⇒ 风险维度在真实数据上恒 unknown。
- 上述两条与 Task 20 / 21 / 22 的实测一致，本轮未新连库写入。

### 未做（移交）

- **Task 24 CI 加挂**：`mutate_task23_baseline_guards.py` 与 `test_task23_zero_regression.py` / `trimNoDataZeroRegression.spec.ts` 均**未进 CI**。加挂前需 `yaml.safe_load` 验证可解析并核对 job 名无重名（`governance-checks.yml` 现有 139 个 job，两个目标 job 名 0 命中；该文件在工作树里为已修改状态）。
- **Task 25 真实库验收** / **Task 26 浏览器实测（清单已 13 项）**：两者都需后端 9980 + 前端 3030 起着，且因真实库 0 条已裁剪 / `B50-T3-*` 0 行，**清单里过半项必须先手工造数据**才可达 —— 无论谁执行都要人在场。
- 判据 (c)(e) 的 HEAD 比对脆弱性（并发会话改附注链路文件会让本 spec 假红）**未加防护**；若后续频繁误红，改法是把 HEAD 比对降为 warning，并以「本 spec 未触碰该文件」的白名单断言承重。

### 平台级新事实（后续会话可直接引用）

- 🔴 **PowerShell 5.1 的 `$OutputEncoding` 默认是 `ASCIIEncoding`**：任何中文经管道送子进程 stdin 都被**静默换成 `?`**。本轮直接后果是第一次打补丁时 `re.compile` 报 `multiple repeat`（连续两个 `?` 构成非法量词）。**`U+FFFD` 检查抓不到它**（腌成的是 `?`）；正确哨兵 = 对**纯 CJK 字符串**查是否含 `?`。修法：把 `$OutputEncoding` 设成不带 BOM 的 UTF8，或把中文全写成 ASCII 转义。⚠️ 短探针只查长度会漏（长度不变），必须查内容。
- **`Path.read_text(newline=...)` 是 Python 3.13+**，本环境 3.12 ⇒ 要保 CRLF 一律用 `open(p, 'r', encoding='utf-8', newline='')`。
- **Kiro local history 可作「禁 HEAD-swap」下的 BEFORE 来源**：对未被 git 跟踪的新文件，它是唯一能取到改动前版本的地方（本轮据此把「用例数 -2 无从交代」变成了逐项吻合的 +3）。
- **长命令被 `^C` 打断后 python 子进程可能仍在跑**：`.bak` 消失与生产文件还原都可能发生在打断之后。判残留一律独立复查，且 `Select-String` 在大 SFC 上出现过多 pattern 同时零命中的不可信结果，字节级判定走 python。

### 清理

本轮 `tmp_*` 诊断产物按**确切路径**逐个删除，未按扩展名扫目录（平台已登记一次活体备份误删事故）。工作树中 `_wip_*` / `tmp_g7_*` / `tmp_ie_*` / `tmp_hc_*` 等属并发会话，未动。
---

## 交付实录 · Task 24 CI job（2026-08-11）

### 一句话结论

两个 job 已加挂（139 → **141**，YAML 可解析、无重名、无 tab），四个步骤的命令**全部本地实跑验证过**。但本轮真正的发现是一条 tasks.md 未提、会让 CI 首跑必红的前置问题：**本 spec 的 5 个变异脚本全是 Windows 专用** —— 两个写死 `["cmd", "/c", "npm", ...]`（`ubuntu-latest` 无 `cmd`），另三个用 `shell=True` + 列表参数（POSIX 上只执行 `npm`/`npx` 本身、不带任何参数 ⇒ JSON 不生成 ⇒ NO-JSON ⇒ 基线 fatal ⇒ 脚本 exit 2）。Task 24 要挂的两个已改为按 `os.name` 分支并在 Windows 上回归验证；另三个未动，如实登记为已知缺口。

### 产出

| 文件 | 改动 |
|---|---|
| `.github/workflows/governance-checks.yml` | 新增 `procedure-trim-intelligence`（9 步）与 `procedure-trim-intelligence-frontend`（4 步，引用 18 个 spec）；job 数 139 → 141 |
| `backend/scripts/check/mutate_trim_decision_guards.py` | 跨平台：`cmd /c npm` → `_npm = ["cmd","/c","npm"] if os.name == "nt" else ["npm"]` |
| `backend/scripts/check/mutate_task23_baseline_guards.py` | 同上 |

### 与 tasks.md 描述不符之处（4 处）

1. **「引用的测试文件必须全部已存在（否则 CI 红）」只覆盖了一半风险**。18 个前端 spec + 9 个后端测试文件确实全部存在（逐个 `exists()` 核过），但**被引用的脚本能否在 runner 上跑**同样决定 CI 红绿 —— 而两个变异脚本在 `ubuntu-latest` 上必然失败。这条不修，Task 24 交付即是假绿。

2. **「后端 job 跑后端守卫、前端 job 跑前端守卫」的分工在变异脚本上不成立**。两个脚本**跨前后端**（T22-6 / T22-11 打后端 `b50_risk_reader.py` 与 `trim_decision_context.py`，其余 10 条打前端 composables 与 `ProcedureTrimming.vue`；T23 的 12 条同理），缺 vitest 即 NO-JSON。故 `procedure-trim-intelligence` **同时装 python 与 node**（`pip install` + `npm ci`），这是有意偏离而非疏漏。

3. **迁移幂等守卫本就在 `backend/tests/procedure_trim/` 目录内**（`test_suggestion_state_migration.py`，26 例）。单列一步不是新增覆盖面，只为在 CI 日志里可见（目录整跑那步已包含它）。tasks.md 把它列为独立项，易被读成需要另建守卫。

4. **CI 无 DB ⇒ 连库判据静默 skip**。三个守卫（`test_b50_reader_extension` / `test_completeness_scope_override` / `test_workpaper_entry_probe`）的真实库断言按 `pytest.skip('真实库不可达')` 降级，**不是 fail** ⇒ 目录整跑在 CI 上不会因缺 PG 变红，但 ⚠️ **job 绿也不代表连库判据被执行过**。已写进 job 注释，真实验收归 Task 25。

### 加挂前的三道闸（按 tasks.md 要求）

| 闸 | 结果 |
|---|---|
| `yaml.safe_load` 可解析 | ✅ 加挂前 139 jobs、加挂后 141 jobs |
| job 名无重名 | ✅ 按行首锚定正则抽 2 空格缩进顶层键，`dupes=[]`（🔴 `safe_load` 会**静默去重**同名 job，只看它查不出 —— 平台曾出现同名 job 被去重、前一个从未运行） |
| 目标 job 名此前不存在 | ✅ `procedure-trim-intelligence` / `procedure-trim-intelligence-frontend` 加挂前 0 命中 |
| 引用文件全部存在 | ✅ 18 个前端 spec 逐个 `exists()`；9 个后端测试文件在目录内 |
| 无 tab 缩进 | ✅ |

### 四个步骤的本地实跑验证（不是「写完就算」）

| CI 步骤 | 本地实跑结果 |
|---|---|
| `python -m pytest backend/tests/procedure_trim/ -q` | **325 passed / 1 skipped / 0 failed** |
| `python -m pytest .../test_suggestion_state_migration.py -q` | **26 passed** |
| `python backend/scripts/check/mutate_trim_decision_guards.py` | 跨平台补丁后单条 `--only T22-6` **rc=0**；全量 12 条 RED 见 Task 22 实录 |
| `python backend/scripts/check/mutate_task23_baseline_guards.py` | 跨平台补丁后单条 `--only T23-6` **RED / rc=0 / 字节级还原 OK / `.t23bak` 无残留**；全量 12/12 RED 见 Task 23 实录 |
| 前端 job 的 `npx vitest run <18 specs>`（逐字照 job 里的命令跑） | **18 files / 702 total / 702 passed / 0 failed** |

### 运行时与触发面（需要团队知情的成本）

本 workflow 触发条件是 `push` + `pull_request`。后端 job 合计 **40 条变异**（T10 16 + T22 12 + T23 12），每条各跑一轮 pytest 与一轮 vitest，本机单条约 25–40 s ⇒ 该 job 预计 **20–27 min**（另加 `pip install` 与 `npm ci`）。若需缩短，两脚本均支持 `--only` / `--only-prefix`（如 `--only-prefix T22` 只跑本 spec 那 12 条），已写进 job 注释作为明示的调节杆。**本轮未擅自裁剪**：裁掉 T10 那 16 条等于让 Task 10 的守卫家族失去 CI 闸。

### 未做（如实登记的缺口）

- **另三个变异脚本仍是 Windows 专用**，未加挂也未修：`mutate_task14_cscope_guards.py` / `mutate_task20_review_guards.py` / `mutate_task21_note_linkage_guards.py`（均为 `shell=True` + 列表参数，POSIX 上只会执行 `npx`/`npm` 本身）。它们对应 Task 14/20/21 的守卫家族，目前只有本地闸。修法与本轮相同（按 `os.name` 分支或改 `shell=False` + 显式 `npm.cmd`）。
- **全量变异 sweep 未在跨平台补丁后重跑**：只验了每个脚本各一条（T22-6 / T23-6）。补丁只改 npm 调用路径、不触判据，但严格说全量结论的时点仍是 Task 22 / Task 23 那两轮。
- **两个 job 未在真实 GitHub runner 上跑过**：本轮全部验证在 Windows 本机完成，`ubuntu-latest` 上 `npm ci` 与 `pip install -r backend/requirements.txt` 的可解析性、以及跨平台补丁在 Linux 上的实际行为，需第一次 push 后看 CI 结果确认。
- Task 25（真实库验收）/ Task 26（浏览器实测，清单 13 项）仍需人在场：真实库 0 条已裁剪、`B50-T3-*` 0 行，过半实测项须先手工造数据。

### 清理

本轮 `tmp_t24_*` 诊断产物按确切路径删除；他人两个 `.bak` 活体备份未动。
### 追加（同日,用户要求后补）：paths 门控 + 另三个变异脚本跨平台

**一处事实纠正**：GitHub Actions **没有 per-job 的 `paths` 过滤器**。`paths` 只能挂在 workflow 级的 `on.push` / `on.pull_request` 上，加上去会波及本文件其余 139 个 job。故落法改为**无第三方依赖的 `git diff` 门控**（仓库内 `paths` 与 `dorny/paths-filter` 均 0 命中，无先例可循；引入第三方 action 还要额外承担版本钉死与供应链风险）：

- 两个 job 各加一个 `id: scope` 步骤，`actions/checkout@v4` 带 `fetch-depth: 0`，按 `github.event_name` 取 base（PR 取 `pull_request.base.sha`，push 取 `github.event.before`），`git diff --name-only` 后用一条 `grep -E` 匹配本 spec 的取数面/守卫面/脚本面（含 `backend/app/services/procedure_*`、`b50_risk_reader` / `trim_decision_context` / `workpaper_entry_probe` / `note_content_utils`、`routers/procedure_*`、`models/`、`migrations/`、`tests/procedure_trim/`、`scripts/check/mutate_*`、`ProcedureTrimming.vue`、`views/__tests__/`、`workpaper/{composables,delegation,trim}/`、`GtB50RiskAssessment.vue`、`services/`，以及 workflow 自身）。
- 其余步骤全部挂 `if: steps.scope.outputs.run == 'true'`（后端 10 步中 8 步、前端 5 步中 3 步；checkout 与 scope 本身不挂）。
- 🔴 **方向必须 fail-open-toward-running**：base 取不到（首次 push / force-push 的全零 SHA）或 `git diff` 失败时 `run=true`。反向（默认跳过）会让门控一坏就静默关闸 —— 那是假绿，且比不加门控更坏。
- 前端 job **不再用 `defaults.run.working-directory`**：scope 步骤必须在仓库根跑 `git diff`，故 npm 步骤逐个显式 `working-directory`（同 `h-cycle-frontend` 的写法）。

**另三个变异脚本已改跨平台**（`mutate_task14_cscope_guards.py` / `mutate_task20_review_guards.py` / `mutate_task21_note_linkage_guards.py`）：三者原为 `shell=True` + 列表参数 —— 在 Windows 上能跑，在 POSIX 上只会执行 `npx`/`npm` 本身、不带任何参数 ⇒ JSON 不生成 ⇒ NO-JSON。均改为 `_npx = ["cmd","/c","npx"] if os.name == "nt" else ["npx"]`（`task20` 同理用 `_npm`）并去掉 `shell=True`；`mutate_task21` 原文无 `import os`，已在首个 `import sys` 前补上。

**Windows 回归**：三者各跑一条 `--only M1`，**全部 `rc=0`**；跑后核残留 —— 仓库内 `.bak` 仍只有他人两个活体备份（`wp_template.py.bak` 32857 B / `procedure_table_templates.json.bak` 449699 B），无 `.t23bak` / `.t21snap` / `.aside` 残留，`ProcedureTrimming.vue` 的 `RENAMED_SKIP_REASONS` 与 `procedure_trim_note_linkage.py` 的 `trim_not_applicable = True` 均 0 命中 ⇒ 无变异体留在工作树。

**加挂后复核**：`yaml.safe_load` 可解析、jobs 仍 **141**、`dupes=[]`、无 tab、前端命令仍引用 18 个 spec。⚠️ 门控逻辑本身**未在真实 runner 上验证过**（`github.event.before` 在不同事件下的取值、`grep -E` 在 runner 的 shell 下的行为），首次 push 后需看 CI 日志里 `scope: run=...` 那行确认。
---

## 交付实录 · Task 25 真实库验收（2026-08-11）

### 一句话结论

`verify_trim_decision_live.py` 新建并**在真实库上真跑通过**（只读，PG 5432 可达）：三维判据上下文确实能在真实数据上装配出来（重药控股安徽 48 个科目 / `performance_materiality=19411.48` / 331 个 wp_code 中 57 个已录入），`degradations` 也真的产出了。但本任务最要紧的判断是**拒绝了 tasks.md 的一项要求**：它要脚本输出「各 verdict 计数 / 汇总闸结果 / 完整性豁免命中数与判据层级分布」，而这三项的真源按 design.md 的架构决定**全在前端 TS**，在 Python 里重算一遍就是第二真源 ⇒ 一律输出 `UNVERIFIABLE(kernel is frontend-only by design)` 并写明真源文件。

### 产出

| 文件 | 性质 |
|---|---|
| `backend/scripts/diagnose/verify_trim_decision_live.py`（8.5 KB） | 新建，默认只读；专用 `NullPool` engine + 同一 loop 内 `dispose()`；一次 `asyncio.run` 取完全部快照；中文报告**落盘不 print**（GBK 控制台会在写完前 `UnicodeEncodeError`，那时退出码非零而数据已取到） |

### 与 tasks.md 描述不符之处（3 处，均为落地实证）

1. 🔴 **三项要求的产物无法由后端诚实产出**。tasks.md 要「各 verdict 计数、汇总闸结果、完整性豁免命中数与判据层级分布」，但 `decideTrim` 的 9 档内核在 `procedureTrimDecision.ts`、汇总闸在 `trimAggregateGate.ts`、豁免清单在 `completenessExemption.ts` 的 `COMPLETENESS_CYCLE_RULES` —— 全是前端 TS，且 design.md 的「已知不做」明确写了**不把决策内核搬到后端**（裁剪是交互式决策）。Python 里重算即第二真源，两侧一旦分叉无从裁决谁对。故三项标 `UNVERIFIABLE` 并各自指向真源文件，验它们只能走 Task 26 浏览器实测。**这不是偷懒，是拒绝制造双真源。**

2. **真实库项目数三个数字互不相同，实测为 23**。tasks.md 写「14 个项目有 `procedure_instances`」、Task 19 实录写「34 个」、本轮实测 **23 个** —— 差异来自 `projects.is_deleted` 过滤（前两个数字未过滤软删）。本轮 SQL 显式加 `p.is_deleted = false`。

3. **`projects` 表没有 `fiscal_year` 列**，真实列名是 **`audit_year`**。首版 SQL 据此报 `asyncpg.exceptions.UndefinedColumnError: column p.fiscal_year does not exist`，改正后通过。（平台铁律「写连库 SQL 前先查真实列名」又一次生效；本轮用 postgres MCP 只读查 `projects` 全列名核实，未再猜。）

### 真实库实测结果（只读，2026-08-11）

| 状态 | 命中项目数 | 代表项目 |
|---|---|---|
| 有重要性无 B50 | **2** | 重药控股安徽有限公司_2025 |
| 无重要性无 B50 | **21** | 重庆医药集团宜宾医药有限公司新健康大药房临港店_2025 |
| 有试算表数据 | **3** | 重药控股安徽有限公司_2025 |
| 有 B50 | **0** | **UNVERIFIABLE** —— 库中不存在该状态，未用 fixture 冒充 |

- **有 `procedure_instances` 的项目 23 个，已裁剪（`status IN (not_applicable, skip)`）合计 0** ⇒ 与 Task 20/21/22/23 的实测一致：粗裁功能上线以来真实未产生任何裁剪结果，`ProcedureDelegationService._trimmed_scopes()` 至今恒返空集。
- **三维可用性（重药控股安徽，FY2025）**：`accounts` 48 个科目 · `materiality` performance=19411.48 / trivial=1941.15 · `risk` 0 个科目且 `risk_dimension_available=False` · `completeness_override` 0 个循环有项目级覆盖 · `workpaper_entry` 331 个 wp_code 中 57 个已录入。
- **`degradations` 真实产出**（这是前端降级标注的唯一来源，Task 13 曾实证它「从未渲染过」）：所有项目恒有 `[risk] B50 无已评估认定…本次不使用风险维度`；无重要性项目额外产出 `[materiality] 本项目本年度未设置重要性水平…`。⇒ 风险维度在真实数据上**恒降级**，「高风险科目被裁」这条异常至今不可达。

### 一处如实上报的可疑点（未深挖，不作结论）

两个不同 `project_id` 的 `tb_balance` 行数**完全相同（均 2436）**。可能成因：同一份试算表被导入到多个项目（业务上合理），或 `tb_balance` 的项目维度过滤/数据集版本有问题。本轮为只读验收，未展开核查。若后续要查，建议先按 `(project_id, dataset_id)` 分组比对 `account_code` 集合是否逐条相同。

### 验证

| 项 | 结果 |
|---|---|
| 脚本语法 | `ast.parse` OK |
| 真实库真跑 | `EXIT=0`，报告落盘完整（23 个项目 + 3 个状态代表的上下文快照） |
| 只读性 | 全部语句为 SELECT；无 `--apply` 之类开关；未产生任何写入 |
| 连库形态 | 专用 `NullPool` engine + 同 loop `dispose()`（不借共享池，避免 `Event loop is closed` 双向污染） |
| 异常处理 | 上下文装配失败按 **ERROR 态**如实记录并打印成因，不 fail-open 吞成「本项目无此数据」 |

### 未做（移交 Task 26）

- verdict 计数 / 汇总闸 / 豁免判据层级分布 —— 前端 TS 独占，须浏览器实测。
- 「有 B50」状态在库中不存在 ⇒ 要覆盖它必须先在测试项目手工填几个科目的 B50 认定（实测后复原，`checklist_responses` 的 `B50-T3-*` 行数须回到 0）。
- Task 26 前置未就绪：**前端 3030 未启动**（后端 9980 与 PG 5432 均通）。
