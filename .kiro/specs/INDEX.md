# Spec 总索引

**最后更新**：2026-05-29（merge `feature/global-refinement-v3-closure` 后统一基线：active 收敛至 11 个 + archived 71，含报表/编辑器瘦身 phase2/全平台 V3 收尾）

> 此索引追踪所有 spec 状态、关联文档、commit。
> **审计原则**：spec 不删，但归档已完成且不再演进的；新启动 spec 默认在 active。
> **实测铁律**：每行的"完成度/日期/commit"列必须有 grep 证据，凭印象写视为漏审。

## 迁移系统（D6 唯一入口）

- **当前迁移系统** = `backend/migrations/V*.sql` + `R*.sql`(D6 版本化 SQL 脚本，启动时 MigrationRunner 自动执行)
- **alembic 已废弃**(2026-05-29 删除，`backend/alembic/` + `alembic.ini` + `requirements.txt` 中 `alembic` 依赖全部移除)
- **新加迁移**：写 `V0XX__xxx.sql` + `R0XX__rollback_xxx.sql` 配对，必须 `IF NOT EXISTS` 幂等
- **失败追踪**：`schema_migration_failures` 表 + `/api/health` 暴露 `migration.failures`
- **schema 漂移**：启动 self-check `SchemaDriftDetector` 检测 ORM↔DB 4 类漂移，写 `schema_drift_log` 表

---

## §1 Active Spec（11 个，待打磨/进行中/外部依赖未完）

| Spec | 状态 | 完成度 | 关键阻塞/下一步 |
|------|------|-------|----------------|
| `migration-runner-resilience/` | 🚧 进行中 | 17/21 | Sprint 5 UAT 实测（Playwright health degraded 截图 + 故意 drift 复测）+ ADR-024/025 |
| `disclosure-note-full-revamp/` | ⚠ 外部依赖 | 44/47 | F-1 真项目 UAT / F-2 dev-history / F-3 文档（外部审计师协作） |
| `note-dynamic-tables-and-template-inheritance/` | 📋 待启动 | 0/151 v0.6.2 | Phase 1 单体附注修复（17 人天，含 D1-D7+D9+D13+D14）；待用户决策启动节奏 |
| `consol-note-three-level-drilldown/` | 📋 占位 | 0 | 前置 = 真实合并母子项目数据 |
| `workpaper-editor-slimdown/` | 🚧 部分完成 | 59/59 任务 / 1200 行目标未达成 | WorkpaperEditor 仍 2167 行，剩余 useUniverEditor composable 待抽（被 workpaper-editor-shrink-phase2 接续） |
| `workpaper-html-renderer/` | ✅ 完成（保留为打磨基础） | 40/40 | 已闭环，作为 1788 单体真底稿渲染基线保留在 active 供后续 view 打磨参考 |
| `global-refinement-v3/` | ⚠ 外部依赖 | 143/145 | 2026-05-28 完成核心（Sprint 0-4 + 13 Property PBT + vue-tsc 0 + vitest 2094 passed + CI 双卡点）；剩 14.4 真合伙人 UAT；gaps.md 反向记录 GtAmountCell 17%/80% + WorkpaperEditor 2555/1000 等技术债 |
| `workpaper-editor-shrink-phase2/` | 🚧 进行中 | 部分完成 | WorkpaperEditor 减 686 行（2748→1481）+ 8 子 SFC + 2 composable + 42 tests + CI 防退化；merge 进基线后继续 |
| `pytest-residual-failures-cleanup/` | ✅ 已闭环 | 全部执行完毕 | 2026-05-28 commit 7a90c3e9 |
| `report-module-enhancement/` | 📝 待执行 | 0/10 | 2026-05-29 commit 612c8a79 三件套就绪：7 需求 / 11 PBT / 5 大领域（种子公式补全 + 路由注册 + 覆盖验证 + CFS 规则扩展 + API 测试基础设施） |
| `workpaper-list-shrink/` | 📝 待执行 | 0/13 | 2026-05-28 三件套就绪（10 stories/61 ACs/1 PBT + 5 ADR）；目标 = WorkpaperList.vue 3463→≤1000 拆 5 子 SFC + 1 shell；已有 4 子组件可复用（kanban/lifecycle/graph/matrix），仅需新建 Workbench |

---

## §2 模块打磨待办（结构调整建议落地）

按 ROI 排序：

| 优先级 | 模块 | 当前规模 | 目标 | 依赖 |
|--------|------|---------|------|------|
| P0 | WorkpaperEditor.vue 瘦身收尾 | 2167 行 | ≤1200 行 | workpaper-editor-slimdown 已闭环，剩抽 useUniverEditor |
| P1 | WorkpaperList.vue 拆分 | 3241 行 | ≤1500 行 | 需新建 spec / 抽 useStandardTable 复用 6 view |
| P1 | TrialBalance.vue 拆分 | 2494 行 | ≤1500 行 | 同上 |
| P2 | DisclosureEditor.vue 拆分 | 2468 行 | ≤1500 行 | C.3 前端组件已加，编辑器主体未拆 |
| P2 | LedgerPenetration.vue 拆分 | 3175 行 | ≤1500 行 | 需新建 spec |
| P3 | ReportView.vue 拆分 | 2317 行 | ≤1500 行 | 需新建 spec |
| P0 | service ≤800 行卡点 | smart_import 2786 / consistency_gate 2141 等 8 个 | pre-commit hook + whitelist | 新加 pre-commit 规则 |
| P1 | 仓库前端路径消歧 | `frontend/` 5 文件空壳 + `audit-platform/frontend/` 真前端 | 单一来源 | 需新 spec（高侵入） |
| P2 | 6000 并发压测 | UAT-5（外部依赖） | 真实环境验证 | 需 PG 大数据量 + Locust |
| P3 | LLM 真实接入 | 6 stub 引擎 H/I/G/K/J/N | 一键切换真服务 | `WP_AI_SERVICE_ENABLED` 已就位，等环境 |

---

## §3 已归档区（71 个 spec）

详见 `.kiro/specs/_archive/`，分类如下：

### 3.1 11 审计循环（D~N，548/548 tasks）

`workpaper-d-sales-cycle` / `workpaper-e1-cash-optimization` / `workpaper-f-purchase-inventory` / `workpaper-g-investment-cycle` / `workpaper-h-fixed-assets-cycle` / `workpaper-i-intangible-assets-cycle` / `workpaper-j-payroll-cycle` / `workpaper-k-admin-cycle` / `workpaper-l-debt-cycle` / `workpaper-m-equity-cycle` / `workpaper-n-tax-cycle`

### 3.2 phase 系列（17 个）

`phase0-infrastructure` / `phase1a-core` / `phase1b-workpaper` / `phase1c-report` / `phase1-experience-gap-fix` / `phase2-consolidation` / `phase2-role-experience-boost` / `phase3-collaboration` / `phase3-system-enhancement` / `phase4-ai` / `phase4-long-term-governance` / `phase5-extension` / `phase5-operational-excellence` / `phase6-integration` / `phase6-precision-and-security` / `phase7-enhancement` / `phase7-role-experience-closure` / `phase8` / `phase11-system-hardening` / `phase12-workpaper-deep` / `phase13-word-export` / `phase14-gate-engine-governance` / `phase15-task-tree-and-event-orchestration` / `phase16-evidence-package-and-versionline`

### 3.3 refinement 系列（9 round）

`refinement-round1-review-closure` ~ `refinement-round9-global-deep-review`

### 3.4 v3 / global / production / table 基础设施（7 个）

`v3-r10-linkage-and-tokens` / `v3-r10-editor-resilience` / `v3-linkage-stale-propagation` / `global-linkage-bus` / `global-platform-enhancement` / `production-readiness` / `table-unification-el-table`

### 3.5 workpaper 基础（5 个）

`workpaper-completion-foundation` / `workpaper-cycle-d-revenue` / `workpaper-collaboration-presence` / `workpaper-editor-refactor` / `workpaper-deep-optimization`

### 3.6 业务专项已完成（11 个）

`proposal-remaining-18` / `e2e-business-flow` / `template-library-coordination` / `audit-chain-generation` / `enterprise-linkage` / `ledger-import-view-refactor` / `advanced-query-enhancements-p1p2` / `k-admin-cycle-post-review-fix` / `partner-dashboard` / `procedure-applicability-trimming` / `role-based-view-switching`

### 3.7 已被取代/合并（4 个）

`ledger-import-unification` → `ledger-import-view-refactor` / `post-enhancement-bugfix` → R9+v3 / `note-account-mapping-seed`（合并入 disclosure-note-full-revamp） / `linkage-panorama-graph`（合并入 enterprise-linkage）

### 3.8 全局结构治理（1 个）

`repo-frontend-layout-unification`（2026-05-29 完成，9/9 tasks，删仓库根 frontend/ 空壳 + 加 pre-commit hook 防回归）

### 3.9 README stub（待启动）

| Spec | 说明 |
|------|------|
| `workpaper-fill-service-split/` | README stub（2026-05-28）：workpaper_fill_service 1587 行拆 4 service；prefill 扩展时启动 |
| `gt-c-note-table-shrink/` | README stub（2026-05-28）：GtCNoteTable 1608 / GtEControlTest 1125 拆子组件；触碰时启动 |

---

## §4 程序规模快照（2026-05-29 实测）

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
| D6 SQL 迁移 | V001-V026（24 历史 + V025/V026 spec 新增） |
| Spec 总数 | 77（active 6 + archived 71） |
| git 当前分支 | feature/disclosure-note-full-revamp |

---

## §5 索引规约

1. 新建 spec 默认放 `.kiro/specs/`（active），完成后审议是否归档
2. 完成 spec 时填完成日期 + 关键 commit
3. 归档时直接 `git mv` 到 `_archive/`，不删文件保留审计轨迹
4. 废弃 spec 标"已被取代" + 记录取代者，仍归档
5. 凭印象禁令：完成度/日期必须 grep 证据
