# 任务清单：consol-phase0-core-pipeline（合并模块 Phase 0 核心管线 + 基础设施修复）

> 关联设计：#[[file:.kiro/specs/consol-phase0-core-pipeline/design.md]]
> 关联需求：#[[file:.kiro/specs/consol-phase0-core-pipeline/requirements.md]]
> 工作流：Design-First。范围 = 止血（B1/B2/C1/C3/A4/P1/P5/P3/F2 + 数据流主干 ADR）。~3 人天。
>
> 任务约定：`[ ]` 未开始 / `[x]` 完成 / `[ ]*` 可选（外部依赖或非阻塞 PBT）。
> 每个任务标注【需求引用】+【属性引用】+【铁律】。实施顺序按依赖拓扑：基线 → schema → B1 → B2 → A4 → P1 → P5 → 锁定闭环 → P3 → PBT → 集成 → UAT。
> 铁律：金额 Decimal / 三层一致校验 / D6 唯一入口 + 幂等 / 彻底解决不绕开 / 改动后必验 / 触类旁通 grep。

---

## 阶段 0：基线与现状核实（动手前实证，防伪绿）

- [x] 0. 实证核实现状基线
  - [x] 0.1 grep 确认 `consol_lock|consolidation_breakdown` 在 `backend/migrations/*.sql`、`backend/app/models/core.py`、`consolidation_models.py` 的命中情况，落档"动手前基线"
  - [x] 0.2 grep 全部 consol 路由清单（`router_registry/system.py` §6 的 14 个 router + report_trace.py），列出每个端点当前的 `Depends` 链（确认仅挂 `get_current_user`），作为 P5 覆盖清单
  - [x] 0.3 readCode 确认 `consol_worksheet_engine._get_audited_amount` 取数口径（`audited_amount` + `is_deleted==false` + `standard_account_code`），作为 B1 取数口径锚点
  - [x] 0.4 readCode 确认 `ExternalReportImportService.import_external_report` 死代码缺陷 + grep 其真实业务调用方（判定需求 6 修复 vs 下线，关联 R5）
  - [x] 0.5 确认现有最大迁移编号（预期 V026），锁定本 spec 用 V027
  - _需求：全部（基线）_ _铁律：彻底解决不绕开（先实证再动手）/ 触类旁通 grep_

---

## 阶段 1：schema 基线迁移 + ORM 三层一致（C1 / C3 / C2）

- [x] 1. V034 合并 schema 基线迁移 + ORM 同步（原 V027，因与 work 分支迁移撞号重编号为 V034）
  - [x] 1.1 编写 `backend/migrations/V034__consol_schema_baseline.sql`：①`projects` 加 `consol_lock BOOLEAN NOT NULL DEFAULT false` / `consol_lock_by UUID` / `consol_lock_at TIMESTAMPTZ`（`ADD COLUMN IF NOT EXISTS`）②`consol_trial` 加 `consolidation_breakdown JSONB`（`ADD COLUMN IF NOT EXISTS`）③合并核心表 `CREATE TABLE IF NOT EXISTS` 基线固化（与 ORM 一致）④GIN 索引 `idx_consol_trial_breakdown ... WHERE is_deleted=false`
  - [x] 1.2 编写配套 `backend/migrations/R034__consol_schema_baseline_rollback.sql`（DROP COLUMN / DROP INDEX 配对回滚）
  - [x] 1.3 `Project` ORM（`core.py`）新增 `consol_lock: Mapped[bool]` + `consol_lock_by: Mapped[UUID|None]` + `consol_lock_at: Mapped[datetime|None]`（紧邻 `consol_level`）
  - [x] 1.4 `ConsolTrial` ORM（`consolidation_models.py`）新增 `consolidation_breakdown: Mapped[dict|None] = mapped_column(JSONB)`
  - [x] 1.5 本地 PG + 全新库双路径实测 V034 幂等重跑（重复执行全 no-op，不抛 DuplicateColumn/DuplicateTable）
  - [x] 1.6 确认 `schema_drift_detector` 对 `consol_lock` 三列 0 漂移（进 ORM 后启动期 drift 检查通过）
  - [x] 1.7 C2：grep 确认无 live import `consolidation_orchestrator` 后删除 stale `.pyc` + 确认 `__pycache__` 已 `.gitignore`
  - _需求：4（C1）/ 5.1·5.7（C3 三层一致）_ _铁律：D6 唯一入口 + IF NOT EXISTS 幂等 / 三层一致校验 / DB 迁移幂等_
  - 注：母分合并 `consolidation_type`=V035（原 V028）/ consol_trial `is_stale`=V036（原 V029），均因 work 分支撞号重编号

---

## 阶段 2：B1 子公司本体汇总 + 合并恒等式

- [x] 2. consol_individual_sum_service（B1 新建）
  - [x] 2.1 新建 `backend/app/services/consol_individual_sum_service.py`，实现 `aggregate_individual_sum(db, project_id, year) -> AggregationResult`（遍历企业树叶子 → 按 `standard_account_code` 加总 `audited_amount` → 写 `individual_sum`）
  - [x] 2.2 实现 `_load_audited_amounts`，**强制复用** `_get_audited_amount` 同口径（`audited_amount` + `is_deleted==false` + `standard_account_code`），保证 B2 对账口径一致（关联 R4）
  - [x] 2.3 构建 `consolidation_breakdown` provenance（`by_company` 列表，amount==0 子公司不写入），落库时金额 `str(Decimal)` 序列化
  - [x] 2.4 无对应 `consol_trial` 行的科目自动 `upsert_trial_row` 建行（account_name 从 TB 带入）
  - [x] 2.5 `AggregationResult` 数据类（accounts_aggregated / companies_traversed / total_individual_sum）
  - _需求：1（1.1~1.7）_ _属性：P3 汇总正确 / P2 provenance 自洽 / P7 Decimal_ _铁律：金额 Decimal / 取数口径一致_

- [x] 3. recalculate_trial 改造（B1 接入）
  - [x] 3.1 `consol_trial_service.recalculate_trial` 改造：先调 `aggregate_individual_sum`（之前完全缺失），再叠加 adjustment/elimination
  - [x] 3.2 抵销额仅取 `review_status == APPROVED` 的 `EliminationEntry`（与 worksheet 口径统一）
  - [x] 3.3 落实合并恒等式 `consol_amount == individual_sum + consol_adjustment + consol_elimination`（全程 Decimal）
  - _需求：2（2.1~2.4）_ _属性：P1 合并恒等式 / P7 Decimal_ _铁律：金额 Decimal / 彻底解决不绕开_

---

## 阶段 3：B2 单一事实源对账

- [x] 4. consol_reconciliation_service（B2 新建）
  - [x] 4.1 新建 `backend/app/services/consol_reconciliation_service.py`，实现 `reconcile_worksheet_vs_trial(db, project_id, year, tolerance=Decimal("0.01")) -> ReconciliationResult`
  - [x] 4.2 逐科目对比 worksheet 根节点 `consolidated_amount` vs `consol_trial.consol_amount`，构建 `diffs` + `max_abs_diff`
  - [x] 4.3 `max_abs_diff > tolerance` 时记 warning 日志并返回 `is_reconciled=false` + diffs，**不阻断**（接口仍 200，关联 E5）
  - [x] 4.4 `ReconciliationResult` 数据类（is_reconciled / tolerance / diffs / max_abs_diff）
  - _需求：3（3.1~3.5）_ _属性：P4 对账等价 / P7 Decimal_ _铁律：金额 Decimal / 单一事实源（ADR-CONSOL-001）_

---

## 阶段 4：A4 死代码修复

- [ ] 5. ExternalReportImportService 修复（A4）
  - [x] 5.1 依据 0.4 判定：若有真实调用价值则修复签名（`self.db`→`db` 参数；`kwargs/year/company_code`→显式参数）；若实证为纯死代码则改"下线路由 + 删方法"（关联 R5）
  - [x] 5.2 修复路径下：金额入口 `float(row[1])` → `Decimal(str(row[1] or 0))`
  - [x] 5.3 `file_content` 缺失/解析失败返回 `{"imported": False, "message": 中文原因}` 不抛 500；坏行逐行跳过计 `skipped`（关联 E2）
  - [x] 5.4 导入成功走 `ON CONFLICT` upsert 写 `trial_balance`，返回 `imported_count`
  - [x] 5.5 **同步更新调用方**：A4 签名由 `(self, db, project_id, data)` 改为 `(self, db, project_id, year, company_code, file_content=None)` 是破坏性变更，grep 全部调用处（`report_trace.py` 路由等）同步改传参（呼应「触类旁通 grep 铁律」）；若 5.1 判定下线则删调用处
  - _需求：6（6.1~6.5）_ _属性：P7 Decimal_ _铁律：金额 Decimal / 彻底解决不绕开（修根因不吞异常）/ 触类旁通 grep_

---

## 阶段 5：P1 审计留痕（CAS 1131 合规红线）

- [ ] 6. consol_audit_helper + event_type 扩展
  - [x] 6.1 `audit_log_helper.EVENT_TYPE_SCHEMAS` 新增 `consol_lifecycle`（必需字段 `sub_action/before/after`）+ `EventType` Literal 增补 `"consol_lifecycle"`
  - [x] 6.2 新建 `backend/app/services/consol_audit_helper.py`，实现 `log_consol_action(...)` 包装既有哈希链 `append_audit_log`
  - [x] 6.3 留痕装配到关键写操作：lock / unlock / 抵销审批（→APPROVED）/ recalc / scope 变更（grep 全覆盖，逐一挂上 before/after）
  - [x] 6.4 留痕与主操作**同事务**：留痕失败回滚主操作（合规优先，关联 E9），不静默吞
  - _需求：7（7.1~7.5）_ _属性：P6 哈希链连续性_ _铁律：触类旁通 grep（关键写操作全覆盖）_

---

## 阶段 6：P5 项目级权限（CAS 1101 数据隔离红线）

- [ ] 7. consol 路由补 require_project_access
  - [x] 7.1 依据 0.2 清单，给全部 consol 路由加 `require_project_access`（工厂依赖，project_id 从路径注入）
  - [x] 7.2 只读类端点（lock-status / snapshots list / pivot / drilldown / report 查看）→ `require_project_access("readonly")`
  - [x] 7.3 写类端点（lock / unlock / recalc / 抵销审批 / scope 变更 / external import）→ `require_project_access("edit")`
  - [x] 7.4 无权访问返回 HTTP 403（关联 E4）；逐一核对清单无遗漏（关联 R7）
  - _需求：8（8.1~8.5）_ _铁律：触类旁通 grep（全路由覆盖）_

---

## 阶段 7：F2 锁定真闭环 + P3 防误用标记

- [ ] 8. consol_lock 去静默 pass + 锁定状态机
  - [x] 8.1 `deps.py:check_consol_lock` 移除"列不存在静默 pass"的 try/except，改 `select(Project.consol_lock)`，锁定态抛 HTTP 423（关联 E8）
  - [x] 8.2 `ConsolLockService.lock/unlock/check_lock` 改用 ORM/`select(Project.consol_lock)`（禁裸 SQL），保证状态机不变量（三字段联合，无半填态）
  - [x] 8.3 锁定覆盖扩展到子公司写端点（底稿/附注/序时账/报表写端点 grep 全挂 `check_consol_lock`，不止 trial+adjustments 5 端点）
  - _需求：5（5.2~5.6）_ _属性：P5 锁状态机不变量_ _铁律：service 禁裸 SQL 操作 ORM 未声明列（ADR-CONSOL-002）_

- [ ] 9. P3 防误用标记
  - [x] 9.1 新增配置开关 `CONSOL_MODULE_DEV_MODE`（默认 `True`）
  - [x] 9.2 新增端点 `GET /api/consolidation/{project_id}/module-status` 返回 `{dev_mode, warning}`；**优先挂到现有 consolidation router**（避免新建文件漏注册 404）；若新建 router 文件则必须在 `router_registry/system.py` §6 登记并跑 `_verify_note_routers.py` 式验证（呼应「router_registry 必查铁律」）
  - [x] 9.3 前端合并模块页面在 `dev_mode==true` 时展示警告 banner「开发中，不可用于正式合并报告」
  - _需求：9（9.1~9.3）_ _铁律：改动后必验（前端 banner 需 Playwright 目视）_

---

## 阶段 8：正确性属性测试（PBT，hypothesis）

- [ ] 10. 核心管线 PBT（P1~P4，B1/B2 守护）
  - [x] 10.1 P1 合并恒等式：随机 N 子公司×M 科目 audited_amount + 随机 APPROVED 抵销 → 断言每行 `consol_amount == individual_sum + adj + elim`
  - [x] 10.2 P2 provenance 自洽：断言 `breakdown.individual_sum == Σ by_company[*].amount` + amount==0 不写溯源行
  - [x] 10.3 P3 汇总正确：随机母子树（含"子公司无 TB""负数科目""跨多子公司同科目"分支），独立字典重算比对（**单层合成树**——多级中间节点本体不在 Phase 0 守护范围，见 §5.2/R8）
  - [x] 10.4 P4 对账等价：随机 worksheet/trial 金额 + 随机 tolerance → 断言 `is_reconciled == (max_abs_diff <= tolerance)` 且 diffs 集合正确（**只验对账逻辑自洽，不验两路径数值必相等**——抵销归集维度差异是已知设计性不一致，见 §5.4/R9）
  - _需求：1/2/3_ _属性：P1/P2/P3/P4_ _铁律：hypothesis 调速（max_examples 10~15）_

- [ ] 11. 锁定/留痕/精度 PBT（P5~P7）
  - [x] 11.1 P5 锁状态机：随机 lock/unlock 操作序列（含重复/交替）→ 每步断言三字段联合不变量 + check_lock 一致
  - [x] 11.2 P6 哈希链连续性：随机 K 个合并操作写入 → 断言链 `prev_hash→entry_hash` 连续 + 篡改中间 payload 使后续校验失败
  - [x] 11.3 P7 Decimal 无精度丢失：生成易触发 float 误差金额 → 断言服务链路结果与纯 Decimal 参照逐位相等
  - [ ] 11.4* 静态守门：`_check_no_float_amount.py` 对合并相关文件（B1/B2/A4 路径）基线不增
  - _需求：5/7/1·2·6_ _属性：P5/P6/P7_ _铁律：金额 Decimal / hypothesis 调速_

---

## 阶段 9：集成测试 + 真实 UAT（边界清晰，不伪绿）

- [ ] 12. 合成母子数据集成测试
  - [x] 12.1 构造 1 母 N 子合成数据集（含"子公司无 TB""负数科目""未审批抵销"分支）
  - [x] 12.2 端到端 `recalculate_trial → reconcile` 全链路断言（恒等式 + provenance + 对账）
  - [x] 12.3 锁定前后端契约：后端锁 → 子公司写端点返 423 → 解锁后可写
  - [x] 12.4 权限：`require_project_access` 命中放行 / 无权返 403
  - [x] 12.5 审计留痕：关键操作后 `audit_log` +1 且哈希链连续
  - [x] 12.6 PG-only SQL（GIN/JSONB）在 SQLite 测试库加 `bind.dialect.name=="sqlite"` 兜底（关联 E7）
  - _需求：1/2/3/5/7/8_ _铁律：任务标记不能假绿（链路通才算完成）_

- [ ] 13. F2 锁定前后端联调 Playwright 实测
  - [x] 13.1 真闭环：补列 → 后端锁 → 前端点锁定 → 真改子公司被拦 423 → 前端显示锁定态 banner（关联 R2，须 Playwright 证据）
  - [x] 13.2 P3 dev_mode banner 前端目视确认
  - _需求：5.6 / 9.3_ _铁律：改动后必 Playwright 实测（getDiagnostics 通过 ≠ 运行时无错）_

- [ ] 14.* 真实集团母子数据端到端 UAT（外部依赖，待数据）
  - [ ] 14.1* 真实集团母子项目 + 审计师确认科目映射 + 端到端合并报告产出 + worksheet/trial/report 三者一致性专业复核
  - [ ] 14.2* 通过后人工置 `CONSOL_MODULE_DEV_MODE=False` 解除防误用标记
  - _需求：NFR-1.3_ _阻塞：PG `consolidated` 项目数为 0，无真实合并母子数据；**显式标"待数据"不用合成数据冒充**_

---

## 阶段 10：收尾

- [ ] 15. 文档与沉淀
  - [x] 15.1 ADR-CONSOL-001/002/003 落地 `docs/adr/`（注册前查 `Get-ChildItem docs/adr/ADR-CONSOL-*` 防编号冲突）
  - [x] 15.2 规约沉淀：service 层禁止裸 SQL 操作 ORM 未声明列（写入 conventions / memory）
  - [x] 15.3 更新 INDEX.md 合并模块 Phase 进展 + memory Phase 0 完成记录
  - [x] 15.4 单 commit 提交全部变更（commit 前 `git status` 确认无其他 staged 改动，防混入）
  - _铁律：历史档案不回填 / 单 commit / ADR 编号防冲突_

---

## 完成度判定口径

- **本 Phase 必需完成** = 任务 0~13 + 15（无星号项）全绿。
- **可选/外部依赖** = 任务 14（真实 UAT，卡 PG 合并数据）+ 11.4（静态守门，非阻塞）。
- **判定铁律**：标 completed 必须有实际代码 + 测试通过证据；真实 UAT 未做就显式标"待数据"，绝不用合成数据冒充；PBT P1~P7 全绿 + schema drift 0 + 集成链路通 + Playwright 锁定闭环实测，缺一不算 Phase 0 完成。
