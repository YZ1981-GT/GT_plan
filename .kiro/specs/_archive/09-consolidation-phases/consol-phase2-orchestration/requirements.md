# 需求文档：consol-phase2-orchestration（合并模块 Phase 2 编排 + 接线 + 报表穿透）

> 关联设计：#[[file:.kiro/specs/consol-phase2-orchestration/design.md]]
> 前置依赖：consol-phase0（B1/B2/breakdown）+ consol-phase1（统一引擎/抵销 APPROVED/事件重算）
> 工作流：Design-First。EARS 风格，关联设计 §六 属性 S1~S8。

## 引言（Introduction）

Phase 2 补"编排与接线"：①A6/C2 统一编排者 cascade_refresh（重建被删的 orchestrator）②一键级联刷新 + SSE 进度 ③V2 附注 feature flag 接线（接通孤儿 generate_full_consol_notes）④B3 自动抵销生成（接通孤立 elimination_rules，只产 draft）⑤衔接4 报表穿透后端（低垂果实，UI 留 Phase 3）⑥国企↔上市 cross_template 孤儿接线 ⑦公式管理联动（合并公式纳入管理中心）⑧P2 签字冻结 ConsolSnapshot 落实 ⑨F3 前端补 V2/refresh-all 路径。

**范围内**：cascade_refresh / refresh-all + SSE / V2 附注接线 / B3 自动抵销 draft / 报表穿透后端端点 / cross_template 接线 / 公式管理联动 / P2 签字冻结 / F3 前端路径补全。
**范围外**：报表·附注穿透 UI / 双向导航 / 自动建树 / 附注穿透 provenance / 真实数据 UAT（留 Phase 3/4）。

**全程铁律**：编排单一入口 DAG / A5 走 worker+SSE 不占连接 / feature flag 灰度 / router_registry 必查 / 改动后必 Playwright 实测。

---

## 需求 1：统一编排者 cascade_refresh（A6/C2）

**用户故事**：作为合并执行人，我希望有一个统一入口按正确依赖顺序跑完整条合并链路，而不是手动按顺序点 4 个刷新按钮，以确保 notes/report/trial/worksheet 依赖顺序正确。

### 验收标准
1. THE 系统 SHALL 新建 `consol_cascade_refresh_service.refresh_all(db, parent_project_id, year)`，作为合并链路唯一编排入口（重建被删的 orchestrator，C2）。
2. THE 编排顺序 SHALL 严格 DAG 自底向上：build_tree → recalc_full(worksheet) → recalculate_trial(含 B1) → reconcile(观测) → generate_consol_reports → generate_full_consol_notes，顺序恒定（关联属性 **S1**）。
3. WHEN 某步失败 THEN 系统 SHALL 记 `errors[{step,node,error}]`；关键步（worksheet/trial）失败中断，下游步（notes）失败标部分成功继续（关联属性 **S2**、错误场景 **EH1**）。
4. WHEN 同 project/year 连续两次 refresh_all THEN 结果数值 SHALL 一致（幂等，关联属性 **S6**）。
5. THE 编排者 SHALL 复用既有 service（不重写），既有单步 recalc 端点保留作细粒度入口（关联风险 **R3**）。

---

## 需求 2：一键级联刷新 + SSE 进度（A5）

**用户故事**：作为合并执行人，我希望点一个"一键刷新全部"按钮就能更新整棵树的报表和附注，并看到进度，以便高效完成合并数据更新。

### 验收标准
1. THE 系统 SHALL 提供 `POST /api/consolidation/{project_id}/{year}/refresh-all`，返回 `job_id`，走后台 worker（不在请求线程跑全量重算，关联风险 **R1**）。
2. THE 系统 SHALL 提供 SSE 进度端点，推送 `{step, total, current_node, status}` 进度事件。
3. THE 一键刷新 SHALL 不占用 asyncpg 请求连接（SSE 用独立连接/Redis pub-sub），job 状态可经 GET 兜底查询（关联风险 **R5**、错误场景 **EH6**）。
4. IF worker 异常 THEN job 状态置 failed + SSE 推 error，不影响其他请求（关联错误场景 **EH2**）。

---

## 需求 3：V2 附注接线（feature flag 灰度）

**用户故事**：作为合并执行人，我希望"生成合并附注"能真正消费各子公司的单体附注汇总，而不是只给 7 个空骨架章节，同时保留老版作为兜底。

### 验收标准
1. THE 系统 SHALL 提供开关 `CONSOL_NOTES_V2_ENABLED`（默认 `False` 老版兼容）。
2. WHERE `CONSOL_NOTES_V2_ENABLED == true` THE consol_notes 路由 SHALL 调 `generate_full_consol_notes`（V2 消费子公司单体附注）；否则调 `generate_consol_notes_sync`（老版 7 骨架章节）。
3. THE V2 与老版返回结构契约 SHALL 一致（章节列表 schema 相同，仅内容来源不同，关联属性 **S4**）。
4. IF V2 生成失败 THEN 系统 SHALL 回退老版兼容 + warning 日志（不破坏既有可用性，关联错误场景 **EH3**、风险 **R2**）。

---

## 需求 4：B3 自动抵销生成（只产 draft）

**用户故事**：作为合并执行人，我希望系统能根据子公司内部交易自动生成抵销分录草稿，省去上百笔手工录入，但仍需我审批后才生效。

### 验收标准
1. THE `auto_generate_eliminations` 端点 SHALL 接通 `consol_elimination_rules.calculate_elimination_amount`（4 类：internal_ar/revenue/inventory/dividend）。
2. WHEN 自动生成 THEN 所有 EliminationEntry SHALL `review_status == DRAFT`，不触发重算（关联属性 **S3**、ADR **CONSOL-203**）。
3. WHEN 草稿被审计师审批（→APPROVED）THEN SHALL 经 Phase 1 `ELIMINATION_APPROVED` 事件触发 worksheet+trial 重算。
4. IF 某规则无匹配内部交易数据 THEN 系统 SHALL 返回 0 不生成 entry、不报错（关联错误场景 **EH4**）。

---

## 需求 5：报表穿透后端（衔接4，低垂果实）

**用户故事**：作为合并执行人，我希望能查看合并报表某行对应科目在各子公司的金额明细和抵销额，以便核查合并数来源（UI 留 Phase 3，后端先就位）。

### 验收标准
1. THE 系统 SHALL 提供 `GET /api/consolidation/report/{project_id}/{year}/{account_code}/consol-breakdown`，返回各子公司金额 + 抵销 + 占比 + 合并数。
2. THE 穿透数据 SHALL 复用 Phase 0 写入的 `consol_trial.consolidation_breakdown` + worksheet `node_company_code` 明细（不额外重算）。
3. THE `Σ by_company[*].amount` SHALL == `individual_sum`（provenance 自洽，复用 Phase 0 P2，关联属性 **S5**）。
4. IF trial 行无 `consolidation_breakdown`（未跑 B1）THEN 系统 SHALL 返回空 by_company + 提示"请先刷新合并数"（关联错误场景 **EH5**）。

---

## 需求 6：国企↔上市 cross_template 孤儿接线

**用户故事**：作为合并执行人，我希望集团内国企版子公司和上市版母公司的附注章节能跨模板正确翻译汇总，而不是让已写好的转换逻辑闲置不被调用。

### 验收标准
1. THE 系统 SHALL 把 `consol_cross_template_service`（3 个 API，当前 0 router 引用仅文件内部互调）接入 V2 附注汇总路径（reaggregate / generate_full_consol_notes）。
2. WHEN 子公司与母公司 template_type 不同（国企↔上市）THEN 系统 SHALL 调 `translate_child_section` 做章节翻译后再汇总。
3. THE 接线 SHALL feature flag 受控（随 CONSOL_NOTES_V2_ENABLED 或独立开关），避免影响老版路径。
4. IF cross_template 翻译无匹配映射 THEN 系统 SHALL 降级为原样汇总 + warning，不丢章节（关联错误场景 **EH7**）。

---

## 需求 7：公式管理联动（合并公式纳入管理中心）

**用户故事**：作为合并执行人，我希望合并的差额表/抵销/报表公式也能在公式管理中心可见、可留痕，而不是散落在代码里管不到。

### 验收标准
1. THE 公式管理中心数据源树 SHALL 新增"合并工作底稿"/"合并报表"节点（当前只有试算平衡表/报表/附注）。
2. THE 合并公式审计 SHALL 纳入 `formula_audit_log`（module='consol'），与单体公式同源留痕。
3. THE 合并公式求值 SHALL 复用 Phase 1 的 report_engine 安全解析器（不再散在旧 eval），保证管理中心展示的公式与实际求值一致。
4. THE `FormulaManagerScope` 已含 `consol_note`，SHALL 补齐"合并底稿/报表" scope 使 5 大能力中"公式管理联动"真正闭环。

---

## 需求 8：P2 签字冻结落实（ConsolSnapshot 存真实数据）

**用户故事**：作为签字合伙人，我希望合并报告签字后有真实的数据快照冻结，以便日后能证明"签字时合并数是多少"，而不是只存一个空壳时间戳。

### 验收标准
1. THE `create_snapshot` SHALL 序列化并存储签字时刻的真实合并数据（consol_trial / worksheet / report / notes 全量结果 + 哈希），而非当前的 `{created_at}` 空壳。
2. WHEN 合并报告签字 THEN 系统 SHALL 锁定该 ConsolSnapshot 为只读版本。
3. WHERE 签字后子公司数据/抵销分录被改 THE 系统 SHALL 仍能从快照还原"签字时的合并数"（与当前实时数对比）。
4. THE 快照创建 SHALL 写审计留痕（复用 Phase 0 log_consol_action）。

---

## 需求 9：F3 前端补 V2/refresh-all 路径

**用户故事**：作为前端开发，我希望 apiPaths 里有 reaggregate/refresh-all 路径定义，以便后端接通的 V2/一键刷新功能前端能真正调到，不出现"后端接了前端调不到"。

### 验收标准
1. THE 前端 `consolidation.notes` apiPaths SHALL 补 `reaggregate` / `refresh-all` 路径定义（当前只有 list/save，F3）。
2. THE 前端 SHALL 提供"一键刷新全部"按钮（调 refresh-all）+ "重新汇总附注"入口（调 reaggregate / V2）。
3. THE 前端路径补全 SHALL 与 Phase 2 后端端点（需求 2/3）一一对应，不遗漏。

---

## 非功能性需求

### NFR-1：测试与质量
1. THE 属性 S1~S8 SHALL 用 hypothesis 实现（S4/S8 集成测试）并 CI 全绿。
2. THE 一键刷新 SSE 进度 + V2 附注前端表现 + F3 前端路径调通 SHALL Playwright 实测，不伪绿。
3. THE V2 附注 + cross_template 真实子公司数据正确性 SHALL 标"待数据"（卡 Phase 4）不伪绿。
4. THE 需求 7（公式管理联动）SHALL 用集成测试验证合并公式审计写入 formula_audit_log（module='consol'）+ 数据源树补节点；需求 9（F3）用前端路径契约核对。

### NFR-2：性能与兼容
1. THE 一键刷新 SHALL 走后台 worker + SSE，不占 asyncpg 请求连接（R1/R5）。
2. THE V2 接线 SHALL feature flag 灰度，老版兼容保留（R2）。

---

## 正确性属性 → 需求映射表

| 属性 | 守护需求 | 验收锚点 |
|------|---------|---------|
| S1 DAG 顺序不变 | 需求 1 | 1.2 |
| S2 失败隔离 | 需求 1 | 1.3 |
| S3 自动抵销仅 draft | 需求 4 | 4.2 |
| S4 V2 灰度结构等价 | 需求 3 | 3.3 |
| S5 穿透 provenance 自洽 | 需求 5 | 5.3 |
| S6 一键刷新幂等 | 需求 1 | 1.4 |
| S7 cross_template 降级不丢章节 | 需求 6 | 6.4 |
| S8 签字快照可还原 | 需求 8 | 8.3 |

## ADR → 需求映射表

| ADR | 落地需求 |
|-----|---------|
| ADR-CONSOL-201 cascade_refresh 编排者 | 需求 1 / 2 |
| ADR-CONSOL-202 V2 附注 feature flag | 需求 3 |
| ADR-CONSOL-203 自动抵销只产 draft | 需求 4 |
| ADR-CONSOL-204 cross_template 随 V2 接线（feature flag） | 需求 6 |
| ADR-CONSOL-205 合并公式纳入公式管理中心 + formula_audit_log | 需求 7 |
| ADR-CONSOL-206 ConsolSnapshot 存真实数据实现签字冻结 | 需求 8 |
