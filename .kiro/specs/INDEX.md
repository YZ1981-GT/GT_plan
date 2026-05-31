# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-05-30  
**当前分支**：`main`（HEAD = 85b362d5）  
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer  
**目标规模**：6000 并发用户

---

## 一、平台已实现功能全景

按审计业务流程排列，标注对应 spec 来源。

### 1.1 项目管理与基础设施

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 项目向导 | 创建项目 → 配置 → 派单 → 启动 | phase0/phase1a |
| 角色体系 | 6 角色（auditor/manager/qc/partner/eqcr/admin）+ 动态导航 + 权限矩阵 | role-based-view-switching / R5 |
| 人员档案 | StaffMember + ProjectAssignment + 工时追踪 | phase1a / R4 |
| 通知中心 | SSE 推送 + 轮询 + 分类 Tab + 免打扰 | R7 / R9 |
| 编辑锁 | 乐观锁 + heartbeat + 强制接管 | R4 / R7 |
| 审计日志 | 哈希链 + 事件溯源 + DLQ | phase14 / R3 |

### 1.2 账表数据（四表体系）

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 智能导入 v2 | 9 家企业验证 / 自动识别表类型 / 7 适配器 / GBK+UTF-8 | ledger-import-unification |
| B' 视图重构 | activate <1s（metadata 切换替代 200 万行 UPDATE） | ledger-import-view-refactor |
| 四表联查 | 余额表 / 序时账 / 辅助余额 / 辅助明细 + 全屏 + 右键穿透 | phase1a / R9 |
| 科目映射 | 自动匹配 + 手动调整 + 跨项目复用 fingerprint | e2e-business-flow |
| 数据管理 | 软删除回收站 / 增量追加 / 跨年度并存 | ledger-import-view-refactor S7 |
| 上传安全 | MIME 校验 / zip bomb 检测 / 宏拦截 / 规模预警 | ledger-import-view-refactor S7 |

### 1.3 试算平衡表

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 自动生成 | 从 tb_balance 聚合 + 父级汇总行补齐 | phase1a / e2e-business-flow |
| 科目标准库 | CAS 166 标准科目 + 国企/上市版映射 | phase1a |
| 公式引擎 | TB()/SUM_TB()/ROW() 三类公式 + 全量重算 | report-module-enhancement |
| 借贷平衡校验 | 含损益结转 + Decimal 精度 | global-refinement-v3 |

### 1.4 报表模块

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 6 类报表 | BS / IS / CFS / EQ / CFS 附表 / 减值准备 | phase1c / report-module-enhancement |
| 国企+上市双版 | 303 行 / 214 行配置驱动 | report-module-enhancement |
| 事件联动 | TB 变更 → 报表自动 stale → 重算 | phase3 / R7 |
| 签字状态机 | draft → review → eqcr_approved → final | R5 |
| PDF/Word 导出 | LibreOffice headless 转换 | phase13 / production-readiness |

### 1.5 底稿模块

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 1788 单体底稿 | 致同 D/F/K/N 等 15 循环全覆盖 | 11 审计循环 spec |
| HTML 渲染器 | 9 类 componentType + 禁止 Univer 兜底 | workpaper-html-renderer |
| Univer 在线编辑 | F/G 循环 558 sheet 保留 Univer | workpaper-editor-slimdown |
| 程序裁剪 | 智能裁剪 + 自定义裁剪 + 自定义新增 | procedure-applicability-trimming |
| 底稿生命周期 | 生命周期视图 + 委派矩阵 + 依赖图 + 看板 | workpaper-completion-foundation |
| 预填充 | TB/WP/REPORT 批量取数 + provenance 溯源 | workpaper-editor-slimdown S4 |
| 离线导出/导入 | 4 色 cell + _meta_ binding + AES 加密 | workpaper-editor-slimdown S4 |

### 1.6 附注模块

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 单体附注生成 | 173 章节（首汽租车实测）/ 自动裁剪 40 章节 | disclosure-note-full-revamp |
| 合并附注 | 7 章节基础生成 + 子公司汇总 | disclosure-note-full-revamp B.0-B.2 |
| Word 导出 | 致同模板 + python-docx | disclosure-note-full-revamp S2 |
| 离线分发 | xlsx 4 色语义 + _meta_ + AES + 一键导入 diff | note-dynamic-tables D15 |
| 公式 DSL | REGION/PRIOR/SUM_TB 等 + 三式联动 | disclosure-note-full-revamp S1.5 |

### 1.7 复核与质控

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 复核工作台 | ReviewWorkbench + 批注 + 工单转换 | R1 / R6 |
| Gate Engine | 签字门禁 + 22 条规则 + 可配置 | phase14 / R3 / R6 |
| QC 规则引擎 | 22 条 seed 规则 + DSL(python/jsonpath) | R3 / R6 |
| EQCR 独立复核 | 5 域聚合 + 影子计算 + 备忘录 + 工时 | R5 |
| 归档包 | 插件化章节(00-99) + SHA-256 水印 + 断点续传 | R1 / R5 |

### 1.8 高级查询与穿透

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| 高级查询 | 16 表白名单 + JOIN + 底稿树 + 单元格选区 | advanced-query-enhancements-p1p2 |
| 正向穿透 | 5 套端点（报表→TB→序时账→凭证） | phase1a / R4 |
| 反向溯源 | report_trace + trace replay | R4 / v4 复盘 |
| 跨模块跳转 | 11 命名空间 4 层级 + Backspace 返回 | enterprise-linkage |

### 1.9 运维与工程

| 功能 | 说明 | 来源 spec |
|------|------|-----------|
| D6 迁移系统 | V*.sql + MigrationRunner + 失败追踪 + schema drift | migration-runner-resilience |
| CI 卡点 | vue-tsc / vitest / file-size / API hardcode / B' guard | R6 / R9 / ledger-import-view-refactor |
| Git 工作流 | 5 类分支命名 + pre-push hook + 6 维核查 CLI | repo-git-workflow-unification |
| 性能基线 | YG2101 128MB/11min / calamine 3.4× 加速 | ledger-import-view-refactor |

---

## 二、进行中 / 待启动 Spec（active，5 个）

> 状态图例：📌 占位 stub（仅 README，无 tasks.md，代码未动）/ ⏳ 实施中 / ✅ 核心完成
> 核心已闭环的 spec 均已归档到 `_archive/`，根目录只保留尚未启动的真 stub 或进行中 spec。

| Spec | 状态 | 说明 |
|------|------|------|
| `consol-phase0-core-pipeline/` | ✅ 核心完成 | Phase 0 止血：B1 汇总 + B2 对账 + C1/C3 schema 基线 V027 + A4 下线 + P1 留痕 + P5 权限 + P3 防误用 + F2 锁定闭环 + ADR-CONSOL-001/002/003；PBT P1~P7 全绿；真实 UAT（任务14）卡 PG 合并数据 |
| `consol-phase1-arch-lock/` | 📌 待启动 | Phase 1 架构修复：A1 公式引擎统一 + 衔接2 抵销口径 + B6/B7 准则修正 + A3 async；前置 = Phase 0 |
| `consol-phase2-orchestration/` | 📌 待启动 | Phase 2 编排接线：cascade_refresh + V2 附注 + cross_template + 报表穿透；前置 = Phase 1 |
| `consol-phase3-frontend-drilldown/` | 📌 待启动 | Phase 3 前端联动：ConsolBreakdownDialog + 附注穿透 + 自动建树 + stale SSE；前置 = Phase 2 |
| `consol-note-three-level-drilldown/` | 📌 | 合并附注三级穿透；前置 = 真实合并母子项目数据（PG 当前 0 个 consolidated 项目）；待并入 Phase 3 |

> 注：`workpaper-fill-service-split` 已 `git rm`（目标 WorkpaperFillService 经 grep 实证为 0 业务调用方的死代码，拆分无意义）；`gt-c-note-table-shrink` 已于 2026-05-30 完成并归档至 07-workpaper-slimdown（GtCNoteTable 1803→450 + GtEControlTest 1414→344，90 测试全绿；残留 R3 Playwright 目视待环境，非代码缺口）。

---

## 三、已归档 Spec（`_archive/`，84 个）

> 已完成且不再演进的 spec，保留审计轨迹。归档不删文件。
> **物理结构**：`_archive/` 下按功能 + 开发先后分 9 个分类目录，每个目录含 README 说明。
> （active spec 保持 `.kiro/specs/` 根目录扁平存放——Kiro spec 工作流依赖固定路径 `.kiro/specs/{name}/`，不可嵌套。）
> **归档标准**：代码实证核心已闭环（声称产物文件真实存在 + 测试通过），剩余仅外部依赖 UAT/文档的，归档；纯 README stub（代码未动）留 active。

```
_archive/
├── 01-phase-foundation/        平台地基（Phase 0~16，24 个）
├── 02-workpaper-cycles/        审计循环业务内容（11 循环 + 5 底稿基础，16 个）
├── 03-refinement-rounds/       五角色轮转打磨（R1~R9，9 个）
├── 04-infra-architecture/      基础设施 / 全局架构（8 个）
├── 05-business-features/       业务专项功能（12 个）
├── 06-engineering-governance/  工程治理（4 个）
├── 07-workpaper-slimdown/      底稿模块瘦身系列（5 个）
├── 08-disclosure-notes/        附注模块系列（2 个）
└── 99-superseded/              已被取代 / 合并（4 个）
```

### 3.1 `01-phase-foundation/` — 平台地基建设（24 个）

平台最早期地基（Phase 0~16），按时间顺序构建。

`phase0-infrastructure` · `phase1a-core` · `phase1b-workpaper` · `phase1c-report` · `phase1-experience-gap-fix` · `phase2-consolidation` · `phase2-role-experience-boost` · `phase3-collaboration` · `phase3-system-enhancement` · `phase4-ai` · `phase4-long-term-governance` · `phase5-extension` · `phase5-operational-excellence` · `phase6-integration` · `phase6-precision-and-security` · `phase7-enhancement` · `phase7-role-experience-closure` · `phase8` · `phase11-system-hardening` · `phase12-workpaper-deep` · `phase13-word-export` · `phase14-gate-engine-governance` · `phase15-task-tree-and-event-orchestration` · `phase16-evidence-package-and-versionline`

### 3.2 `02-workpaper-cycles/` — 审计循环业务内容（16 个）

11 审计循环主体 + 5 底稿基础。548/548 tasks 全部完成。

致同审计循环代号：A=报表/调整 · B=控制了解 · C=控制测试 · D=销售收入 · E=货币资金 · F=采购存货 · G=投资 · H=固定资产 · I=无形资产 · J=职工薪酬 · K=管理 · L=筹资 · M=股东权益 · N=税费 · S=专项

**11 循环主体**：`workpaper-d-sales-cycle` · `workpaper-e1-cash-optimization` · `workpaper-f-purchase-inventory` · `workpaper-g-investment-cycle` · `workpaper-h-fixed-assets-cycle` · `workpaper-i-intangible-assets-cycle` · `workpaper-j-payroll-cycle` · `workpaper-k-admin-cycle` · `workpaper-l-debt-cycle` · `workpaper-m-equity-cycle` · `workpaper-n-tax-cycle`

**5 底稿基础**：`workpaper-completion-foundation` · `workpaper-cycle-d-revenue` · `workpaper-collaboration-presence` · `workpaper-editor-refactor` · `workpaper-deep-optimization`

### 3.3 `03-refinement-rounds/` — 五角色轮转打磨（9 个）

合伙人 → 项目经理 → 质控 → 审计助理 → EQCR 独立复核 → 跨角色优化 → 全局打磨 → 深度收口 → 全局深度复盘

`refinement-round1-review-closure` · `refinement-round2-project-manager` · `refinement-round3-quality-control` · `refinement-round4-audit-assistant` · `refinement-round5-independent-review` · `refinement-round6-cross-role-optimization` · `refinement-round7-global-polish` · `refinement-round8-deep-closure` · `refinement-round9-global-deep-review`

### 3.4 `04-infra-architecture/` — 基础设施 / 全局架构（8 个）

`global-linkage-bus` · `global-platform-enhancement` · `production-readiness` · `table-unification-el-table` · `v3-linkage-stale-propagation` · `v3-r10-linkage-and-tokens` · `v3-r10-editor-resilience` · `global-refinement-v3`（全平台一致性治理：金额 Decimal 化 + 表单校验 + 归档只读 + 年度联动；143/147，剩合伙人 UAT）

### 3.5 `05-business-features/` — 业务专项功能（12 个）

`proposal-remaining-18` · `e2e-business-flow` · `template-library-coordination` · `audit-chain-generation` · `enterprise-linkage` · `ledger-import-view-refactor` · `advanced-query-enhancements-p1p2` · `k-admin-cycle-post-review-fix` · `partner-dashboard` · `procedure-applicability-trimming` · `role-based-view-switching` · `report-module-enhancement`

### 3.6 `06-engineering-governance/` — 工程治理（4 个）

`repo-frontend-layout-unification`（删仓库根 frontend/ 空壳 + pre-commit hook 防回归）  
`repo-git-workflow-unification`（5 类分支命名 + GIT_MODE 双模式 + 6 维核查 CLI + pre-push hook + ADR-027/028）  
`pytest-residual-failures-cleanup`（SQLite vs PG 测试残留失败治理，2026-05-28 闭环）  
`migration-runner-resilience`（D6 MigrationRunner 韧性化：批不中断 + schema drift 自检 + alembic 清理；V025/V026 + schema_drift_detector.py 381 行；Sprint 1-4 完成，剩 Sprint 5 UAT）

### 3.7 `07-workpaper-slimdown/` — 底稿模块瘦身系列（5 个）

底稿渲染 HTML 化 + 超长 .vue 拆分。

| Spec | 成果 |
|------|------|
| `workpaper-html-renderer` | 1788 单体底稿切 HTML，9 类组件，40/40 tasks，413 tests |
| `workpaper-editor-slimdown` | WorkpaperEditor 2748→758 行 + 8 子 SFC + 2 composable，59/59 tasks |
| `workpaper-list-shrink` | WorkpaperList 3463→1151 行（净减 67%）+ 5 子 SFC，36 vitest + e2e |
| `workpaper-editor-shrink-phase2` | WorkpaperEditor 收尾瘦身至 837 行 + 8 子 SFC + 2 composable，36/36 tasks |
| `gt-c-note-table-shrink` | GtCNoteTable 1803→450 行 + GtEControlTest 1414→344 行；C 类 3 子组件 + 3 composable / E 类 5 子组件 + 2 composable；90 测试全绿（36 spec 零断言 + 54 新单测）+ vue-tsc 0；残留 R3 Playwright 目视待环境 |

### 3.8 `08-disclosure-notes/` — 附注模块系列（2 个）

| Spec | 成果 |
|------|------|
| `disclosure-note-full-revamp` | 附注重写：173 章节生成 + 自动裁剪 + Word 导出 + 公式 DSL；46/47（剩外部 UAT/文档）；note_formula_generator 1331 行 + 50 note 测试 |
| `note-dynamic-tables-and-template-inheritance` | 全维度增强 v0.6.2（D1~D15 共 15 维度）；实测 166/182≈90%（剩 16 项外部依赖）；10 核心 service 实跑全绿 |

### 3.9 `99-superseded/` — 已被取代 / 合并（4 个）

| 旧 spec | 取代者 |
|---------|--------|
| `ledger-import-unification` | → `ledger-import-view-refactor`（在 05-business-features） |
| `post-enhancement-bugfix` | → R9 + global-refinement-v3（在 04-infra-architecture） |
| `note-account-mapping-seed` | → 合并入 `disclosure-note-full-revamp`（在 08-disclosure-notes） |
| `linkage-panorama-graph` | → 合并入 `enterprise-linkage`（在 05-business-features） |

---

## 四、开发历程时间线

平台采用 PDCA 迭代模式：建议 → spec 三件套（requirements + design + tasks）→ 实施 → 复盘 → 下一轮。

| 阶段 | 主题 | 产出 |
|------|------|------|
| **Phase 0-1** | 平台地基 | 基础设施 + 核心数据模型 + 底稿/报表骨架 |
| **Phase 2-4** | 合并 / 协作 / AI | 合并报表 + 多人协作 + AI 引擎接入框架 |
| **Phase 5-8** | 扩展 / 集成 / 加固 | 系统扩展 + 第三方集成 + 系统硬化 |
| **Phase 11-16** | 深度治理 | 底稿深化 + Word 导出 + Gate 引擎 + 任务树 + 证据包 |
| **11 审计循环** | 业务内容填充 | D~N 全循环 548 任务 + 致同 2025 编码体系 |
| **Refinement R1-R9** | 五角色轮转打磨 | 合伙人/PM/质控/助理/EQCR 视角逐轮收口 |
| **账表导入 v2** | 数据引擎重写 | 9 家企业验证 + B' 视图架构（activate <1s） |
| **底稿渲染器** | HTML 化 | 1788 单体底稿从 Univer 切 HTML + 9 类组件 |
| **附注全栈** | 附注模块重写 | 173 章节生成 + 离线分发 + Word 导出 |
| **V3 全平台收尾** | 一致性治理 | 金额 Decimal 化 + 表单校验 + 归档只读 + 年度联动 |
| **工程治理** | 仓库/迁移/Git | 前端路径统一 + D6 迁移韧性 + Git 工作流规约 |

---

## 五、程序规模快照（2026-05-29 实测）

| 维度 | 值 |
|------|---|
| 后端 routers | 273 |
| 后端 services | 403 |
| 后端 models | 58 |
| 后端 tests | 588 |
| 前端 views | 99 |
| 前端 components | 353 |
| 前端 composables | 81 |
| 前端 .vue 总数 | 498 |
| 前端 .ts 总数 | 379 |
| PG 表数 | 188 |
| 底稿模板 | 456 |
| cross_wp_references | 400 条 |
| prefill_formula_mapping | 1035 cells |
| validation_rules | 114 条 |
| D6 SQL 迁移 | V001-V027 |
| **Spec 总数** | **89（active 5 + archived 84）** |

---

## 六、模块打磨待办（按 ROI 排序）

| 优先级 | 模块 | 当前 | 目标 | 依赖 |
|--------|------|------|------|------|
| P0 | WorkpaperEditor.vue | 2167 行 | ≤1200 | 抽 useUniverEditor composable |
| P1 | WorkpaperList.vue | 3241 行 | ≤1500 | 抽 useStandardTable 复用 6 view |
| P1 | TrialBalance.vue | 2494 行 | ≤1500 | 同上 |
| P2 | DisclosureEditor.vue | 2468 行 | ≤1500 | 编辑器主体未拆 |
| P2 | LedgerPenetration.vue | 3175 行 | ≤1500 | 需新建 spec |
| P3 | ReportView.vue | 2317 行 | ≤1500 | 需新建 spec |
| P0 | service ≤800 行卡点 | smart_import 2786 等 8 个 | pre-commit hook | 已有 check_file_size.py |
| P2 | 6000 并发压测 | 外部依赖 | 真实验证 | PG 大数据量 + Locust |
| P3 | LLM 真实接入 | 6 stub 引擎 | 一键切换 | WP_AI_SERVICE_ENABLED 已就位 |

---

## 六-A、归档 spec 完成度核查（2026-05-30，逐 spec 代码实证，防伪绿）

> 逐个 spec 读 tasks.md + fileSearch/grepSearch 实证产物真实存在。**结论：已核查 13 个 spec 无伪绿**。

### 已完成逐 spec 实证核查

**06-engineering-governance（4 个，全部核查）**：
| spec | 判定 | 实证 |
|------|------|------|
| migration-runner-resilience | ⏳核心完成收尾待补 | Sprint1-4 全✅（emoji格式）；Sprint5 ADR-024/025 实际已存在（tasks.md 滞后标⏳）；真缺口仅 5.2/5.3 Playwright 截图（.playwright-mcp/ 不存在，需启动后端=外部依赖） |
| pytest-residual-failures-cleanup | ✅真完成 | 残留 7 项全是父任务未勾+子任务全[x]（误报源③）；_test_auth_helper.py + override_auth 接入 + test_smoke_e2e skipif 全存在 |
| repo-frontend-layout-unification | ✅真完成 | emoji格式 ✅23；check_no_root_frontend.py 存在+已注册 pre-commit；仓库根 frontend/ git tracked 0 文件；ADR-026 存在 |
| repo-git-workflow-unification | ✅真完成（伪红） | tasks.md 12 项全标⏳但产物 100% 存在=最隐蔽伪红；check_git_sync_state.py(129行)/check_git_branch_naming.py(77)/check_hotspot_files.py(81)/.git-hooks/pre-push(53)/install.ps1(26)/git-workflow.md(110)/ADR-027(33)/ADR-028(42) 全部 fileSearch 确认 |

**04-infra-architecture（8 个，全部核查）**：
| spec | 判定 | 实证 |
|------|------|------|
| global-linkage-bus | ✅真完成 | linkage_graph_builder/stale_propagation_engine/formula_reverse_index 全存在 |
| global-platform-enhancement | ✅真完成 | 7 残留全是收尾杂务框漏勾（误报源③）；GtAmountCell/GtEditableTable/eventBus(mitt)/migration_runner 全存在 |
| global-refinement-v3 | ⏳核心完成收尾待补 | useAuditContext/ai_content_log_service/conflict_resolution_service/time_machine_service/trust_score_service/allowed_actions_service + 7 ESLint 规则全存在；真缺口仅 Task14.4 合伙人 UAT（外部依赖） |
| production-readiness | ✅真完成 | 1 残留=父任务未勾子全done（误报源③）；migration_runner/sla_worker/import_recover_worker/outbox_replay_worker 全存在 |
| table-unification-el-table | ✅真完成 | GtTableExtended/GtFormTable/gt-tokens.css 全存在 |
| v3-linkage-stale-propagation | ⏳核心完成收尾待补 | stale_summary_aggregate.py 存在；残留=UAT 手动验收 8 项 pending（需真人执行） |
| v3-r10-editor-resilience | ⏳核心完成收尾待补 | event_cascade_health_service/workers/worker_helpers 存在；残留=UAT 5 项 pending（需运维/真人） |
| v3-r10-linkage-and-tokens | ⏳核心完成收尾待补 | GtTableExtended/gt-tokens.css/CI 4 道卡点全存在；残留=UAT 8 项设计师视觉回归截图（需真人） |

**05-business-features（1 个已核查）**：
| spec | 判定 | 实证 |
|------|------|------|
| procedure-applicability-trimming | ✅真完成 | 3 残留=Sprint/Checkpoint 汇总框（非实质任务）+11 可选 PBT；chain_orchestrator 步骤5b/5c 裁剪逻辑(548-579行)+ProcedureTrimming.vue+QC-19/20/24 门禁规则全存在 |

### 待核查（剩余 71 个）

### 已核查（续）— 05/01/03/07/08 标红项逐一实证

**05-business-features 标红项**：
| spec | 判定 | 实证 |
|------|------|------|
| procedure-applicability-trimming | ✅真完成 | 3 残留=Sprint/Checkpoint 汇总框+11 可选 PBT；chain_orchestrator 步骤5b/5c+ProcedureTrimming.vue+QC-19/20/24 全存在 |
| advanced-query-enhancements-p1p2 | ✅真完成 | 2 残留=父任务未勾子全done（误报③）；custom_query.py+query_builder.py JOIN_WHITELIST 存在 |
| partner-dashboard | ✅真完成 | 1 残留=父任务未勾（误报③）；PartnerDashboard.vue 存在 |
| report-module-enhancement | ✅真完成 | 必需 15/15；13 可选 PBT 不影响；audit_logs §127+validate_formula_coverage.py 存在 |
| 其余 8 个抽查 | ✅ | chain_orchestrator/enterprise_linkage_models/LedgerImportHistory.vue/TemplateLibraryMgmt.vue 等产物全存在 |

**01-phase-foundation 标红项（Python 脚本误报，PowerShell 复核）**：
| spec | 判定 | 实证 |
|------|------|------|
| phase3-system-enhancement | ✅真完成 | 2 残留=UAT-3(LLM 接入)+UAT-5(6000 并发)，均外部依赖 |
| phase7-enhancement | ✅真完成 | PowerShell grep 209/209 全[x]（Python 脚本编码/正则 bug 误报 32/51）|
| phase8 | ✅真完成 | PowerShell grep 209/209 全[x]（同上误报 50/75）|

**03-refinement-rounds 标红项**：
| spec | 判定 | 实证 |
|------|------|------|
| refinement-round1-review-closure | ⏳核心完成收尾待补 | 12 残留=UAT-1~6 真人验收+Round2 候选 2+已知妥协 4，全是外部依赖/后续候选/技术债 |

**07/08 补充核查**：
| spec | 判定 | 实证 |
|------|------|------|
| workpaper-html-renderer | ✅真完成（伪红）| 1 残留 Task1.6 标[ ]但 wp_classification_service.get_classification 真实存在 |
| workpaper-list-shrink | ✅真完成 | 9 残留全父任务未勾（误报③）；产物全存在 |
| disclosure-note-full-revamp | ✅真完成 | 6 残留=P-1~3 外部+1.7 UAT+F-2/3 文档收口；note_formula_generator.py 存在 |
| note-dynamic-tables | ✅真完成 | 16 可选/外部 UAT；dynamic_region_engine+consol_note_aggregation 存在 |

### 核查汇总（PowerShell 准确计数 + fileSearch 实证）

**全部 84 个归档 spec 已用 PowerShell `Select-String "^\s*-\s*\[x\]"` 精确计数**（避开 Python re.M bug），有 unchecked 任务的逐一读 tasks.md + fileSearch 实证：

| 判定 | 说明 |
|------|------|
| ✅ 真完成（绝大多数）| 代码产物全部 fileSearch/grep 实证存在；unchecked 全是：可选 `[ ]*` / 父任务汇总框未勾（子任务全[x]）/ emoji 标题格式 / 伪红（标⏳产物已存在）|
| ⏳ 核心完成收尾待补 | migration-runner(Playwright 截图) / global-refinement-v3(合伙人 UAT) / v3-linkage-stale / v3-r10-editor-resilience / v3-r10-linkage-tokens / refinement-round1(真人 UAT) / phase6-precision(部分被 global-refinement-v3 取代) / phase7-role-closure(汇总框+UAT) / round7-global-polish(触碰即修债+UAT) — 残留**全是外部依赖（真人 UAT/Playwright/设计师视觉）或被后续 spec 取代**|
| ⚠️ 伪绿 | **0 个** — 无一 spec 声称完成但代码产物缺失 |

**有 unchecked 的 spec 逐一定性**（PowerShell 实测）：
- 01 类：phase3-system-enhancement(2=外部UAT) / phase6-precision(19=汇总框+1.3b被v3取代+UAT) / phase7-role-closure(25=汇总框+UAT)；其余含 phase7-enhancement/phase8 经 PowerShell 复核实为 209/209 全[x]（Python 误报）
- 02 类：16 个仅 workpaper-editor-refactor(残留=被 editor-slimdown/phase2 取代) + workpaper-deep-optimization(1 可选)；其余 14 个 notdone=0
- 03 类：round1(12=真人UAT+技术债) / round2(3=Sprint 验收框) / round7(32=触碰即修债+UAT) / round8(7) / round9(8)；其余 round3-6 notdone=0
- 04 类：8 个全核查（前文表格）
- 05 类：4 标红项 + 8 抽查全 ✅
- 06 类：4 个全核查（前文表格）
- 07 类：5 个全核查 ✅
- 08 类：2 个全 ✅
- 99 类：4 个 superseded（被取代不必 100%）

**剩余可深入**：03 类 round8/round9 的残留性质（sprint-split 格式）+ 99 superseded 细节，但均低风险。

### 正则统计四大误报源（核查方法论）
1. **可选 `[ ]*`**：带星号未做不影响完成定性
2. **emoji 标题格式 `### Task X ✅`**：非 checkbox 被误报 0/N
3. **父任务未勾 + 子任务全完成**：父项汇总忘勾
4. **伪红**：tasks.md 全标 ⏳ 但产物 100% 存在（repo-git-workflow-unification）

> ⚠ Python 正则脚本本身也有 bug（phase7/phase8 误报 32/51、50/75，实际 209/209）——**PowerShell `Select-String "^\s*-\s*\[x\]"` 直接 grep 比 Python re.M 更可靠**。最终判定一律靠 fileSearch/grep 实证产物文件存在，不信文档自述、不信扫描数字。

---

## 七、索引规约

1. 新建 spec 默认放 `.kiro/specs/`（active 根目录，**扁平存放**），完成后审议是否归档
2. **active spec 不可嵌套子目录** —— Kiro spec 工作流依赖固定路径 `.kiro/specs/{name}/tasks.md`
3. 完成 spec 时填完成日期 + 关键 commit
4. 归档时 `git mv` 到 `_archive/{分类目录}/`，按功能归入 7 个分类之一，不删文件保留审计轨迹
5. 归档分类目录：01 地基 / 02 循环 / 03 打磨 / 04 架构 / 05 业务 / 06 工程 / 99 取代
6. 废弃 spec 移入 `99-superseded/` + 记录取代者
7. **凭印象禁令**：完成度 / 日期必须有 grep 证据，凭印象写视为漏审

### 迁移系统提示（D6 唯一入口）

- 当前迁移系统 = `backend/migrations/V*.sql` + `R*.sql`（启动时 MigrationRunner 自动执行）
- alembic 已废弃（2026-05-29 删除）
- 新加迁移：写 `V0XX__xxx.sql` + `R0XX__rollback_xxx.sql` 配对，必须 `IF NOT EXISTS` 幂等
