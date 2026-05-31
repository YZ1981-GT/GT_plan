# 需求文档：consol-phase0-core-pipeline（合并模块 Phase 0 核心管线 + 基础设施修复）

> 关联设计：#[[file:.kiro/specs/consol-phase0-core-pipeline/design.md]]
> 关联调研：#[[file:docs/proposals/consolidation-module-status-and-proposal.md]]
> 工作流：Design-First（需求从设计反推）。本文档采用 EARS 风格验收标准，并关联设计 §六 正确性属性 P1~P7。

## 引言（Introduction）

合并模块当前"骨架健全、核心管线断裂、关键操作无留痕、无项目级权限"。本 Phase 0 不做新高端功能，目标是**止血**：让合并数逻辑成立（B1/B2）、修复基础设施（C1/C3/A4）、补合规留痕与权限（P1/P5）、防误用标记（P3）、锁定真闭环（F2），并通过数据流主干 ADR（W1/W4）锁定后续演进方向。

**范围内**：B1 子公司汇总 / B2 单一事实源对账 / C1 schema 基线迁移 / C3+F2 consol_lock 三层一致 / A4 死代码修复 / P1 审计留痕 / P5 项目级权限 / P3 防误用标记 / 数据流主干 ADR。
**范围外**（留后续 Phase）：15 张致同底稿喂引擎 / 报表级·附注级穿透 UI / 公式引擎统一（A1）/ 同一控制企业合并（B8）/ 真实集团数据端到端 UAT（卡外部数据）。

**全程铁律**：金额 Decimal / 三层一致校验（DB 迁移 + ORM `Mapped[]` + service）/ D6 唯一迁移入口 + IF NOT EXISTS 幂等 / 彻底解决不绕开 / 改动后必验。

---

## 需求 1：子公司本体自动汇总（B1）

**用户故事**：作为集团审计的合并执行人，我希望系统在合并重算时自动把各子公司同科目的审定数加总到 `individual_sum`，以便合并报表真正包含子公司本体数据，而不是只剩抵销额。

### 验收标准

1. WHEN 对合并母项目调用 `recalculate_trial(project_id, year)` THEN 系统 SHALL 先遍历企业树，按 `standard_account_code` 把各子公司 `trial_balance.audited_amount` 加总写入对应 `consol_trial.individual_sum`。
2. WHERE 某科目跨多个子公司存在 THE 系统 SHALL 令 `individual_sum[code] == Σ 各子公司 audited_amount[code]`（关联属性 **P3**）。
3. IF 某子公司无 `trial_balance` 数据 THEN 系统 SHALL 视其对所有科目贡献 0 并继续汇总，不抛错（关联错误场景 **E1**）。
4. WHEN 汇总完成 THEN 系统 SHALL 对每个被汇总的 trial 行写入 `consolidation_breakdown` provenance，且 `consolidation_breakdown.individual_sum == Σ by_company[*].amount`（关联属性 **P2**）。
5. WHERE 某科目尚无对应 `consol_trial` 行 THE 系统 SHALL 自动建行（account_name 从 TB 带入），不丢失该科目。
6. THE 汇总取数口径 SHALL 与 `consol_worksheet_engine._get_audited_amount` 完全一致（读 `audited_amount`、`is_deleted == false`、按 `standard_account_code`），否则 B2 对账失败。
7. THE 全链路金额 SHALL 使用 `Decimal`，provenance JSON 中金额以 `str(Decimal)` 序列化，无 `float` 中转（关联属性 **P7**）。
8. THE Phase 0 的 individual_sum 汇总 SHALL **假定单层合并**（母项目 + 直接子公司）：仅对企业树叶子节点取 `audited_amount`。WHERE 存在多级合并树（如 A 合并 B+C、B 又合并 D+E）且中间节点 B 自身持有 TB THE 中间节点本体的汇总 SHALL 留待后续 Phase 处理（由 `_calc_node` 后序遍历覆盖），Phase 0 不保证多级中间节点本体被纳入 individual_sum（关联设计 §5.2 边界说明）。

---

## 需求 2：合并恒等式成立（B1）

**用户故事**：作为签字合伙人，我希望合并试算表每一行都满足"合并数 = 本体加总 + 调整 + 抵销"，以便我能信任产出的合并数在结构上成立。

### 验收标准

1. WHEN `recalculate_trial` 返回结果 THEN 系统 SHALL 令每一行满足 `consol_amount == individual_sum + consol_adjustment + consol_elimination`（关联属性 **P1**）。
2. THE 抵销额来源 SHALL 仅取 `review_status == APPROVED` 的 `EliminationEntry`（与 worksheet 口径统一）。
3. IF `individual_sum` 因任何原因未被写入 THEN 恒等式 SHALL 失败并被属性测试 P1 捕获（杜绝回归到"consol_amount = 0 + 0 + 抵销"的旧 bug）。
4. THE 恒等式计算 SHALL 全程 `Decimal`，结果按 2 位量化后精确相等（关联属性 **P7**）。

---

## 需求 3：worksheet ↔ trial 单一事实源对账（B2）

**用户故事**：作为合并执行人，我希望系统能对比差额表引擎（worksheet）算出的合并数与报表数据源（trial）的合并数，以便我能及时发现两条计算路径的不一致。

### 验收标准

1. WHEN 调用 `reconcile_worksheet_vs_trial(project_id, year, tolerance)` THEN 系统 SHALL 逐科目对比 `ConsolWorksheet`（根节点）的 `consolidated_amount` 与 `consol_trial.consol_amount`。
2. THE 返回结果 SHALL 满足 `is_reconciled == (max_abs_diff <= tolerance)`，且 `diffs` 恰为超容差科目集合（关联属性 **P4**）。
3. IF `max_abs_diff > tolerance` THEN 系统 SHALL 记 warning 日志并返回 `is_reconciled=false` + `diffs` 清单，但 **不阻断**接口（仍返 200，关联错误场景 **E5**）。
4. THE 对账金额比较 SHALL 全程 `Decimal`，默认容差 `Decimal("0.01")`。
5. THE 设计 SHALL 确立 worksheet 为单一事实源（关联 **ADR-CONSOL-001**），对账为 Phase 0 观测手段，不强制两路径数值一致。
6. WHERE worksheet 与 trial 因**抵销分录归集维度不同**而产生 diff（`recalculate_trial` 按 `EliminationEntry.lines[].account_code` 聚合 / `_calc_node` 按 `EliminationEntry.debit_amount/credit_amount` 按公司节点聚合）THE 此类 diff SHALL 视为**已知设计性不一致**而非缺陷，统一口径留待后续 Phase 衔接2 处理；Phase 0 对账 diff ≠ Phase 0 bug（关联设计 §5.4、风险 **R4**）。

---

## 需求 4：合并 schema 基线迁移纳入 D6 治理（C1）

**用户故事**：作为平台维护者，我希望合并模块的所有表与字段都纳入 D6 迁移系统，以便老库能正确演进 schema，不再依赖 `create_all()` 兜底。

### 验收标准

1. THE 系统 SHALL 新增 `V027__consol_schema_baseline.sql` 与配套 `R027__consol_schema_baseline_rollback.sql`（取现有最大 V026 的下一编号）。
2. THE V027 SHALL 把合并模块 ORM 现状固化为 `CREATE TABLE IF NOT EXISTS` 幂等 SQL，对已 `create_all` 的老库 no-op、对全新库补建。
3. THE V027 SHALL 为 `projects` 表新增 `consol_lock BOOLEAN NOT NULL DEFAULT false`、`consol_lock_by UUID`、`consol_lock_at TIMESTAMPTZ` 三列（均 `ADD COLUMN IF NOT EXISTS`）。
4. THE V027 SHALL 为 `consol_trial` 新增 `consolidation_breakdown JSONB` 列 + GIN 索引 `idx_consol_trial_breakdown ... WHERE is_deleted=false`。
5. WHEN V027 在已部署库或全新库重复执行 THEN 系统 SHALL 全部 no-op，不抛 `DuplicateColumn/DuplicateTable`，不中断 D6 管线（关联错误场景 **E6**、风险 **R1**）。
6. THE 系统 SHALL 在 grep 确认无 live import 后清理 `consolidation_orchestrator` 的 stale `.pyc`（C2），并确保 `__pycache__` 已 `.gitignore`。
7. THE 全部新增 PG-only SQL（GIN / JSONB）SHALL 在 SQLite 测试方言下有兜底，不污染单测（关联错误场景 **E7**）。

---

## 需求 5：consol_lock 三层一致与锁定真闭环（C3 + F2）

**用户故事**：作为合并执行人，我希望对合并母项目锁定后，子公司数据真的不能被修改，且前端显示的锁定状态与后端真实状态一致，以避免"显示锁定成功实际没锁"的假闭环。

### 验收标准

1. THE `Project` ORM 模型 SHALL 新增 `consol_lock: Mapped[bool]`、`consol_lock_by`、`consol_lock_at` 三个 `Mapped[]` 字段（三层一致校验，关联 **ADR-CONSOL-002**）。
2. THE `ConsolLockService` SHALL 通过 ORM/`select(Project.consol_lock)` 操作锁定状态，禁止裸 SQL 操作该列。
3. THE `deps.py:check_consol_lock` SHALL 移除"列不存在静默 pass"的 try/except，列就位后真实锁定状态生效（关联错误场景 **E8**）。
4. WHEN 项目处于锁定态 AND 调用方对已挂 `check_consol_lock` 的子公司写端点操作 THEN 系统 SHALL 返回 **HTTP 423** `{detail: "项目已被合并锁定，无法修改"}`（关联错误场景 **E3**）。
5. THE 锁定状态 SHALL 始终满足不变量：`locked <=> (consol_lock==true ∧ lock_by≠None ∧ lock_at≠None)`，`unlocked <=> (consol_lock==false ∧ lock_by==None ∧ lock_at==None)`，无半填中间态（关联属性 **P5**）。
6. WHEN 前后端联调 THEN 系统 SHALL 形成真闭环：补列 → 后端锁 → 前端点 → 真改子公司被拦 423 → 前端显示锁定态（关联风险 **R2**，须 Playwright 实测）。
7. THE `consol_lock` 三列 SHALL 被 `schema_drift_detector` 纳入守护（进 ORM 后自动生效）。

---

## 需求 6：外部报表导入死代码修复（A4）

**用户故事**：作为合并执行人，我希望外部报表导入功能能真正工作而不是一调用就崩，以便能把子公司外部报表数据导入试算表。

### 验收标准

1. THE `ExternalReportImportService.import_external_report` SHALL 修复死代码缺陷：`self.db` → 传入的 `db` 参数；`kwargs/year/company_code` → 显式函数参数。
2. THE 金额入口 SHALL 由 `amount = float(row[1])` 改为 `Decimal(str(row[1] or 0))`（关联属性 **P7**、调研 **P6**）。
3. IF `file_content` 为空或 Excel 解析失败 THEN 系统 SHALL 返回 `{"imported": False, "message": 中文原因}`，不抛 500；坏行逐行跳过并计 `skipped`（关联错误场景 **E2**）。
4. WHEN 导入成功 THEN 系统 SHALL 通过 `ON CONFLICT` upsert 写入 `trial_balance`，返回 `imported_count`。
5. IF 实证该方法无任何真实业务调用方（仅路由注册） THEN 团队 SHALL 评估改为"下线路由 + 删方法"而非修复（关联风险 **R5**，避免给死代码美容）。

---

## 需求 7：合并关键操作审计留痕（P1，CAS 1131 合规红线）

**用户故事**：作为质控（QC/EQCR），我希望合并的锁定/解锁/抵销审批/重算/范围变更都有操作人、时间、前后值的审计记录，以便能复核合并过程、满足监管检查。

### 验收标准

1. THE 系统 SHALL 新增 `consol_audit_helper.log_consol_action(...)`，包装既有哈希链 `append_audit_log`。
2. WHEN 执行 lock / unlock / 抵销审批（→APPROVED）/ recalc / scope 变更 THEN 系统 SHALL 各写入一条 `audit_log`，含 `user_id`、`project_id`、`action`、`resource_type`、`resource_id`、`before`、`after`。
3. THE 审计日志链 SHALL 满足连续性：`∀ i>0: chain[i].prev_hash == chain[i-1].entry_hash` 且 `entry_hash == H(prev_hash ‖ payload)`（关联属性 **P6**）。
4. THE `audit_log_helper.EVENT_TYPE_SCHEMAS` SHALL 新增 `consol_lifecycle` 事件类型（必需字段 `sub_action/before/after`），`EventType` Literal 增补 `"consol_lifecycle"`。
5. IF 留痕写入失败 THEN 系统 SHALL 不静默吞，且因留痕与主操作同事务而回滚主操作（合规优先，关联错误场景 **E9**、风险 **R6**）。

---

## 需求 8：合并接口项目级权限（P5，CAS 1101 数据隔离红线）

**用户故事**：作为子公司审计团队成员，我希望只能访问自己有权的项目数据，不能通过合并接口看到无关子公司的数据，以满足数据隔离与独立性要求。

### 验收标准

1. THE 全部 consol 路由 SHALL 加 `require_project_access`（当前仅挂 `get_current_user`）。
2. WHERE 端点为只读类（lock-status / snapshots list / pivot / drilldown / report 查看）THE 系统 SHALL 用 `require_project_access("readonly")`。
3. WHERE 端点为写类（lock / unlock / recalc / 抵销审批 / scope 变更 / external import）THE 系统 SHALL 用 `require_project_access("edit")`。
4. IF 调用方无对应项目访问权 THEN 系统 SHALL 返回 **HTTP 403**（关联错误场景 **E4**）。
5. THE 改造 SHALL 先 grep 全部 consol 路由清单逐一覆盖，不遗漏（关联风险 **R7**，触类旁通铁律）。

---

## 需求 9：合并模块防误用标记（P3）

**用户故事**：作为团队成员，我希望系统明确标记合并模块"开发中，不可用于正式合并报告"，以避免在 Phase 0 端到端验证通过前误用错误的合并数出报告。

### 验收标准

1. THE 系统 SHALL 提供配置开关 `CONSOL_MODULE_DEV_MODE`（默认 `True`），Phase 0 端到端验证通过后由人工置 `False`。
2. WHEN 访问合并模块状态端点 `GET /api/consolidation/{project_id}/module-status` THEN 系统 SHALL 返回 `{"dev_mode": true, "warning": "开发中，不可用于正式合并报告"}`。
3. WHERE `dev_mode == true` THE 前端 SHALL 在合并模块页面展示警告 banner。

---

## 非功能性需求（Non-Functional Requirements）

### NFR-1：测试与质量
1. THE 正确性属性 P1~P7 SHALL 全部用 hypothesis 实现并在 CI 全绿。
2. THE 测试 SHALL 分三层边界：纯函数算法单测（PBT 主战场）/ 合成母子数据集成测试 / 真实 UAT（显式标"待数据"不伪绿）。
3. THE 真实集团母子数据端到端 UAT SHALL 因 PG `consolidated` 项目数为 0 而标记 `[ ]* 待数据`，不用合成数据冒充。

### NFR-2：迁移与兼容
1. THE V027 SHALL 在本地 PG 与全新库双路径实测幂等重跑。
2. THE 新增 PG-only SQL SHALL 加 `bind.dialect.name == "sqlite"` 兜底。

### NFR-3：合规与安全
1. THE 合并关键写操作 SHALL 全部留痕（CAS 1131）。
2. THE 合并接口 SHALL 全部有项目级权限（CAS 1101）。

---

## 正确性属性 → 需求映射表

| 属性 | 守护需求 | 验收标准锚点 |
|------|---------|-------------|
| P1 合并恒等式 | 需求 2 | 2.1 / 2.3 |
| P2 provenance 自洽 | 需求 1 | 1.4 |
| P3 汇总正确 | 需求 1 | 1.2 / 1.3 |
| P4 对账等价 | 需求 3 | 3.2 |
| P5 锁状态机不变量 | 需求 5 | 5.5 |
| P6 哈希链连续性 | 需求 7 | 7.3 |
| P7 Decimal 无精度丢失 | 需求 1/2/6 | 1.7 / 2.4 / 6.2 |

## ADR → 需求映射表

| ADR | 落地需求 |
|-----|---------|
| ADR-CONSOL-001 数据流主干裁定 | 需求 3（worksheet 单一事实源） |
| ADR-CONSOL-002 consol_lock 三层一致 | 需求 5 |
| ADR-CONSOL-003 V027 基线迁移纳入 D6 | 需求 4 |
