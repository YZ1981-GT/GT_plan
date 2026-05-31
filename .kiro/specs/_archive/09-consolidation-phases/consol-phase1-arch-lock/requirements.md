# 需求文档：consol-phase1-arch-lock（合并模块 Phase 1 架构修复 + 锁定闭环）

> 关联设计：#[[file:.kiro/specs/consol-phase1-arch-lock/design.md]]
> 前置依赖：consol-phase0-core-pipeline（consol_lock 三层一致 + B1 trial 已通 + 审计留痕基线）
> 工作流：Design-First。EARS 风格验收，关联设计 §六 属性 Q1~Q7。

## 引言（Introduction）

Phase 0 止血后，Phase 1 做架构理顺，消除腐化地基：①A1/A2 合并报表复用 report_engine 安全公式引擎（删除重复裸 eval）②衔接2 抵销口径统一为 APPROVED + 事件驱动重算 ③F2/F4 锁定全端点覆盖 + 前端 banner + 423 拦截 ④B6 负商誉 CAS 20 修正 + B7 少数股东持股比例语义统一 + A3 consol_report_service sync/async 统一（会计正确性 + 工程债，搭车 A1/A2 重构）。**不加新高端功能。**

**范围内**：A1 公式引擎统一 / A2 AmountResolver 注入 / 衔接2 抵销口径 / F2 锁定全端点 / F4 前端 banner+423 / B6 负商誉 CAS 20 修正 / B7 少数股东持股比例语义统一 / A3 sync-async 统一。
**范围外**：cascade_refresh 编排者 / 一键刷新 / V2 附注接线 / B3 自动抵销生成 / 报表·附注穿透 UI（留 Phase 2/3）；**B8 同一控制企业合并（整类计算路径缺失，独立大模块，需审计专业 + 大工作量，本批 4 Phase 均不含，单独立项）** / **B4 MI·商誉在 verify_balance 的处理（需深入核实合并恒等式口径，留审计专业）** / **B5 跨年合并上年数结转（留 Phase 4 连续审计场景）**。

**全程铁律**：彻底解决不绕开（删裸 eval 复用 ast）/ 金额 Decimal / 改动后必 Playwright 实测 / 触类旁通 grep。

---

## 需求 1：合并报表复用统一公式引擎（A1/A2）

**用户故事**：作为签字合伙人，我希望同一张报表的单体版和合并版公式行为完全一致（都支持 ABS/IF/比较），以便合并报表的计算口径可信、不因引擎不同而出错。

### 验收标准
1. THE 系统 SHALL 抽象 `AmountResolver` 接口（`resolve_tb` / `resolve_sum`），`report_engine` 公式求值接受 resolver 注入。
2. THE 单体报表 SHALL 注入 `TrialBalanceResolver`（读 `trial_balance.audited_amount`），合并报表 SHALL 注入 `ConsolTrialResolver`（读 `consol_trial.consol_amount`）。
3. THE 系统 SHALL 删除 `consol_report_service._execute_formula` / `_resolve_consol_tb` / `_resolve_sum_consol` / `_extract_account_codes`，改委托 `report_engine`（消除重复裸 eval）。
4. WHEN 对同一 formula 字符串分别注入两个 resolver THEN 解析与求值路径 SHALL 完全相同，仅取数值不同（关联属性 **Q1**）。
5. THE 公式求值 SHALL 不使用 `eval`，非法/注入表达式返回 `Decimal("0")` 不抛（关联属性 **Q2**、错误场景 **EH1**）。
6. WHEN A1 改造完成 THEN 单体报表既有测试 SHALL 全绿（复用引擎不破坏单体行为，关联风险 **R1**）。
7. THE 取数全程 SHALL `Decimal`，无 `float` 中转（关联属性 **Q6**）。

---

## 需求 2：抵销口径统一为 APPROVED + 事件驱动重算（衔接2）

**用户故事**：作为合并执行人，我希望 worksheet 和 trial 消费的抵销分录口径一致（都只认已审批的），且审批抵销后自动重算，以便两条计算路径不再因口径不同而对不上。

### 验收标准
1. THE `consol_worksheet_engine._get_elimination_map` SHALL 加 `review_status == APPROVED` 过滤（对齐 trial，当前仅 `is_deleted` 过滤）。
2. WHEN worksheet 与 trial 重算 THEN 两者消费的抵销集合 SHALL 相同（均 APPROVED，关联属性 **Q3**）。
3. WHEN 抵销分录审批（→APPROVED）THEN 系统 SHALL 发 `ELIMINATION_APPROVED` 事件并触发 worksheet + trial 重算。
4. WHEN 同一笔抵销审批重复触发事件 THEN 重算结果 SHALL 幂等（关联属性 **Q4**）。
5. IF 触发重算失败 THEN 系统 SHALL 记 error 日志但不阻断审批本身（审批已落库，关联错误场景 **EH3**）。
6. THE 口径变更 SHALL 标注并通知用户（draft 不再进合并数是预期修正，关联风险 **R3**）。

---

## 需求 3：锁定全端点覆盖（F2，CAS 数据完整性）

**用户故事**：作为合并执行人，我希望母项目锁定后，子公司的底稿/附注/序时账/报表等所有写操作都被拦截，而不是只拦试算表和调整分录，以确保锁定真正锁住全部数据修改入口。

### 验收标准
1. THE 系统 SHALL grep 全部子公司维度写端点，逐一挂 `check_consol_lock`（当前仅 trial_balance + adjustments 5 端点，关联风险 **R5**）。
2. THE 覆盖范围 SHALL 含底稿（working_paper）/ 附注（disclosure）/ 序时账（ledger）/ 报表（report）写端点。
3. WHEN 母项目处于锁定态 AND 调用任一子公司写端点 THEN 系统 SHALL 返回 **HTTP 423**（关联属性 **Q5**）。
4. WHERE 端点仅含资源 id（wp_id/note_id 等）无 project_id THE `check_consol_lock` SHALL 先反查所属 project_id 再判锁。
5. IF 资源 id 反查所属项目失败 THEN 系统 SHALL 放行不误拦 + 记 warning（关联错误场景 **EH4**）。

---

## 需求 4：前端锁定 banner + 423 统一拦截（F2/F4）

**用户故事**：作为子公司审计人员，我希望在项目被合并锁定时看到明确的横幅提示并禁用编辑，且任何被拦截的操作都有友好提示，以避免"以为能改实际改不了"的困惑。

### 验收标准
1. THE 系统 SHALL 新建 `ConsolLockedBanner.vue`（`components/common/`，仿 `ArchivedBanner`，无 props 内部读锁定态）。
2. WHERE 项目 `consol_lock == true` THE 前端 SHALL 显示锁定横幅「本项目已被合并项目锁定，暂不可编辑」+ 编辑按钮 disabled。
3. WHEN 后端返回 HTTP 423 THEN 前端 http 拦截器 SHALL 统一 `ElMessage` 提示「项目已被合并锁定，无法修改」+ 刷新锁定态（关联错误场景 **EH5**）。
4. WHEN 前后端联调 THEN 系统 SHALL 形成真闭环：后端锁 → 前端点 → 真改子公司被拦 423 → 前端 banner + ElMessage（关联风险 **R1**，须 Playwright 实测）。

---

## 需求 5：负商誉处理符合 CAS 20（B6，会计准则硬错误修正）

**用户故事**：作为签字合伙人，我希望系统对负商誉的处理符合现行《企业会计准则第 20 号——企业合并》，而不是套用已废止的"递延收益摊销"逻辑，以免我采信错误的会计处理建议。

### 验收标准
1. THE `goodwill_service.calculate_goodwill` SHALL 删除 `treatment = "计入损益" if abs(goodwill) < acquisition_cost * 0.25 else "递延收益摊销"` 这段**编造的 25% 阈值 + 递延摊销分支**。
2. WHERE 合并成本 < 享有可辨认净资产公允价值份额（负商誉）THE 系统 SHALL 统一判定为"全额计入当期损益（营业外收入）"（CAS 20 现行规定）。
3. THE 系统 SHALL 提示审计师"需复核合并成本与可辨认净资产公允价值的计量"（负商誉前的准则要求复核步骤）。
4. THE 商誉计算公式本身（成本 − 可辨认净资产 FV × 母持股比例）SHALL 保持不变（原公式正确，仅修负商誉后续处理分支）。
5. THE 修正 SHALL 标注 `[ ]* 待审计专业确认`，由懂 CAS 20 的审计专业人员复核准则符合性后方可标完成（关联风险 **R7**）。

---

## 需求 6：少数股东持股比例字段语义统一（B7，计算口径 bug）

**用户故事**：作为合并执行人，我希望 `minority_share_ratio` 字段在全系统语义一致，以免附注里的少数股东持股比例算反（如母 80% 子 20% 却显示 80%）。

### 验收标准
1. THE 系统 SHALL 明确 `minority_share_ratio` 字段语义为**少数股东持股比例**（与 `minority_interest_service.calculate_mi` 的用法一致）。
2. THE `consol_disclosure_service` 的 `minority_ratio = (1 - mi.minority_share_ratio or 1) * 100`（把同字段当母公司持股比例求补数）SHALL 修正为直接用少数股东比例，不再求补数。
3. THE 系统 SHALL 加单测锁定口径：给定母 80%/子 20%，附注展示的少数股东持股比例 == 20%（关联属性 **Q7**）。
4. THE 修正 SHALL 标注 `[ ]* 待审计专业确认` 字段语义最终口径（关联风险 **R7**）。

---

## 需求 7：consol_report_service sync/async 统一（A3）

**用户故事**：作为平台维护者，我希望合并报表服务统一为 async，避免在 async session 上调同步 Session API 触发 `MissingGreenlet`，以保证运行时稳定。

### 验收标准
1. THE `ConsolReportService` SHALL 把方法体内的同步 `self.db.query(...).filter(...).all()` 统一改为 async `await self.db.execute(select(...))`。
2. WHERE 确需同步上下文（如 worker）THE `*_sync` 包装 SHALL 用 `run_sync` 桥接，不在 async session 上直调同步 API。
3. WHEN A1/A2 重构（需求 1）触碰 `ConsolReportService` 时 THEN 系统 SHALL 一并完成 sync/async 统一（搭车重构，避免二次触碰，关联风险 **R8**）。
4. THE 改造后 SHALL 无 `MissingGreenlet` 风险路径（集成测试覆盖关键查询）。

---

## 非功能性需求

### NFR-1：测试与质量
1. THE 属性 Q1~Q7 SHALL 用 hypothesis 实现并 CI 全绿（Q5 用参数化集成测试）。
2. THE A1 改造 SHALL 有单体报表全量回归基线守门（不破坏既有行为）。
3. THE 锁定全端点 SHALL Playwright 实测 423 闭环，不伪绿。

### NFR-2：兼容与回归
1. THE A1/A2 重构 SHALL 先让 report_engine 注入版跑通合并用例，再删 consol 侧重复代码（R6）。
2. THE 抵销口径变更 SHALL 标注并通知用户（R3）。

---

## 正确性属性 → 需求映射表

| 属性 | 守护需求 | 验收锚点 |
|------|---------|---------|
| Q1 公式语义一致 | 需求 1 | 1.4 |
| Q2 求值安全 | 需求 1 | 1.5 |
| Q3 抵销口径一致 | 需求 2 | 2.2 |
| Q4 审批重算幂等 | 需求 2 | 2.4 |
| Q5 锁定全端点覆盖 | 需求 3 | 3.3 |
| Q6 Decimal 无精度丢失 | 需求 1 | 1.7 |
| Q7 少数股东比例语义正确 | 需求 6 | 6.3 |

## ADR → 需求映射表

| ADR | 落地需求 |
|-----|---------|
| ADR-CONSOL-101 复用 report_engine | 需求 1 |
| ADR-CONSOL-102 抵销 APPROVED + 事件重算 | 需求 2 |
| ADR-CONSOL-103 锁定全端点覆盖 | 需求 3 / 4 |
| ADR-CONSOL-104 负商誉按 CAS 20 计入当期损益 | 需求 5 |
| ADR-CONSOL-105 少数股东比例字段语义统一 | 需求 6 |
| ADR-CONSOL-106 consol_report_service 统一 async | 需求 7 |
