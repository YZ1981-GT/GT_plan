# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-06-10  
**当前分支**：`work/2026-05-30-wp-specs`  
**Spec 总数**：**139**（active 2 + archived 137）  
**最高迁移**：V068  
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

**快速查找**：
1. 知道关键词 → 查 §二 分类表格定位 spec 名
2. 知道 spec 名 → 直接读 `_archive/{分类}/{name}/tasks.md`
3. 验证完成度 → tasks.md 产物路径 + `codegraph_search` / `grepSearch` 实证

**防伪绿铁律**：`[x]` 必须有「产物文件真实存在 + 测试通过」双重实证。详见 `docs/spec-audit-2026-05-30.md`。

---

## 一、平台模块概览

| 模块 | 核心能力 |
|------|----------|
| 项目管理 | 向导创建 / 6 角色权限 / 人员派单 / 通知 / 编辑锁 / 审计日志 |
| 账表数据 | 智能导入 v2（9 企业）/ B' 视图 / 四表联查 / 科目映射 / 符号约定+方向推导 |
| 试算平衡 | 自动聚合 / CAS 标准库 / 公式引擎 / 借贷平衡诊断 |
| 报表 | 6 类报表 / 国企+上市双版 / 事件联动 / 签字状态机 / PDF+Word 导出 |
| 底稿 | 1788 单体 / HTML 渲染器 / Univer 编辑 / 程序裁剪 / 预填充 / 离线导入导出 / 科目工作包 / AI 结论 |
| 附注 | 173 章节生成 / 自动裁剪 / Word 导出 / 离线分发 / 公式 DSL / 语义契约 |
| 复核质控 | 复核工作台 / Gate 门禁 / QC 规则 / EQCR 独立复核 / 归档包 |
| 穿透查询 | 高级查询 / 正向穿透 / 反向溯源 / 跨模块跳转 |
| 合并报表 | 4 Phase（止血→锁定→编排→穿透）/ 147 测试 / 16 ADR |
| 运维工程 | D6 迁移 / CI 卡点 / Git 工作流 / 性能基线 |

---

## 二、已归档 Spec（137 个，10 分类）

**当前 active = 2**（其余已归档）。新建 spec 放 `.kiro/specs/{name}/`。

### Active Specs（实施中）

| Spec | 状态 | 迁移 | 说明 |
|------|------|------|------|
| audit-report-template-integration | implementing | V066 | 审计报告模板集成（171/184，剩 13 项非代码阻塞/人工验收） |
| deliverable-lineage-and-writeback | completed | V067 | 出品物溯源与回填（92/92 全部完成，待端到端联调） |

```
_archive/
├── 01-phase-foundation/         24   平台地基（Phase 0~16）
├── 02-workpaper-cycles/         16   审计循环（11循环+5基础，548 tasks）
├── 03-refinement-rounds/         9   五角色轮转（R1~R9）
├── 04-infra-architecture/       27   基础设施/全局架构
├── 05-business-features/        34   业务专项（含ledger/wp系列）
├── 06-engineering-governance/    6   工程治理
├── 07-workpaper-slimdown/        9   底稿瘦身
├── 08-disclosure-notes/          4   附注模块
├── 09-consolidation-phases/      4   合并模块
└── 99-superseded/                4   已被取代
```


### 2.1 `01-phase-foundation/`（24）

`phase0-infrastructure` · `phase1a-core` · `phase1b-workpaper` · `phase1c-report` · `phase1-experience-gap-fix` · `phase2-consolidation` · `phase2-role-experience-boost` · `phase3-collaboration` · `phase3-system-enhancement` · `phase4-ai` · `phase4-long-term-governance` · `phase5-extension` · `phase5-operational-excellence` · `phase6-integration` · `phase6-precision-and-security` · `phase7-enhancement` · `phase7-role-experience-closure` · `phase8` · `phase11-system-hardening` · `phase12-workpaper-deep` · `phase13-word-export` · `phase14-gate-engine-governance` · `phase15-task-tree-and-event-orchestration` · `phase16-evidence-package-and-versionline`

### 2.2 `02-workpaper-cycles/`（16）

**11 循环**：`workpaper-d-sales-cycle` · `workpaper-e1-cash-optimization` · `workpaper-f-purchase-inventory` · `workpaper-g-investment-cycle` · `workpaper-h-fixed-assets-cycle` · `workpaper-i-intangible-assets-cycle` · `workpaper-j-payroll-cycle` · `workpaper-k-admin-cycle` · `workpaper-l-debt-cycle` · `workpaper-m-equity-cycle` · `workpaper-n-tax-cycle`

**5 基础**：`workpaper-completion-foundation` · `workpaper-cycle-d-revenue` · `workpaper-collaboration-presence` · `workpaper-editor-refactor` · `workpaper-deep-optimization`

### 2.3 `03-refinement-rounds/`（9）

`refinement-round1-review-closure` · `refinement-round2-project-manager` · `refinement-round3-quality-control` · `refinement-round4-audit-assistant` · `refinement-round5-independent-review` · `refinement-round6-cross-role-optimization` · `refinement-round7-global-polish` · `refinement-round8-deep-closure` · `refinement-round9-global-deep-review`

### 2.4 `04-infra-architecture/`（27）

`global-linkage-bus` · `global-platform-enhancement` · `production-readiness` · `table-unification-el-table` · `v3-linkage-stale-propagation` · `v3-r10-linkage-and-tokens` · `v3-r10-editor-resilience` · `global-refinement-v3` · `vllm-httpx-bugfix` · `retrieval-kernel-unification` · `doc-level-ai-chat` · `global-modules-cleanup` · `global-modules-p2-polish` · `formula-engine-unification` · `report-config-baseline` · `llm-structured-output` · `pg-pooling-and-load-test` · `xlsx-read-acceleration` · `endpoint-fuzz-and-tracing` · `global-refinement-v5-closure` · `platform-context-permission-foundation` · `platform-evidence-knowledge-ai-governance` · `platform-linkage-contract-stale` · `platform-maintenance-governance` · `platform-role-workbench-quality-loop` · `platform-ui-editing-consistency` · `zero-downtime-deployment`

### 2.5 `05-business-features/`（34）

**账表导入（5）**：`ledger-import-view-refactor` · `ledger-import-header-adapter-contract` · `ledger-import-sign-convention-migration` · `ledger-balance-diagnostics-report-line-coverage` · `ledger-sign-convention-unify`

**底稿专项（14）**：`wp-evidence-collection` · `wp-frontend-ux-polish` · `wp-functional-actions` · `wp-generation-pipeline` · `wp-locate-foundation` · `wp-performance-virtualization` · `wp-template-migration` · `wp-traceability-panel` · `wp-tsj-llm-review` · `wp-ai-review-ux-fix` · `workpaper-guardrail-cleanup` · `workpaper-account-package-d1-d2-pilot` · `workpaper-ai-conclusion-copilot` · `workpaper-content-semantic-contract`

**报表/查询/角色（5）**：`advanced-query-enhancements-p1p2` · `partner-dashboard` · `procedure-applicability-trimming` · `role-based-view-switching` · `report-module-enhancement`

**核心流程（7）**：`proposal-remaining-18` · `e2e-business-flow` · `template-library-coordination` · `audit-chain-generation` · `enterprise-linkage` · `multi-standard-unification` · `schema-drift-full-sync`

**其他（3）**：`k-admin-cycle-post-review-fix` · `project-creation-enhancement` · `audit-report-deliverable-center`

### 2.6 `06-engineering-governance/`（6）

`repo-frontend-layout-unification` · `repo-git-workflow-unification` · `pytest-residual-failures-cleanup` · `migration-runner-resilience` · `frontend-consistency-m1` · `dev-tooling-modernization`

### 2.7 `07-workpaper-slimdown/`（9）

`workpaper-html-renderer` · `workpaper-editor-slimdown` · `workpaper-list-shrink` · `workpaper-editor-shrink-phase2` · `gt-c-note-table-shrink` · `gtdform-test-and-shrink` · `custom-workpaper-formula-binding` · `audit-sheet-editable` · `report-view-slimdown`

### 2.8 `08-disclosure-notes/`（4）

`disclosure-note-full-revamp` · `note-dynamic-tables-and-template-inheritance` · `disclosure-note-linkage-and-slimdown` · `disclosure-note-semantic-structure-and-presentation`

### 2.9 `09-consolidation-phases/`（4）

`consol-phase0-core-pipeline` · `consol-phase1-arch-lock` · `consol-phase2-orchestration` · `consol-phase3-frontend-drilldown`

### 2.10 `99-superseded/`（4）

| 旧 spec | 取代者 |
|---------|--------|
| `ledger-import-unification` | → `ledger-import-view-refactor` |
| `post-enhancement-bugfix` | → R9 + `global-refinement-v3` |
| `note-account-mapping-seed` | → `disclosure-note-full-revamp` |
| `linkage-panorama-graph` | → `enterprise-linkage` |

---

## 三、待建 Spec

- `workpaper-unified-import-export`（底稿统一导入导出）
- D1-4 坏账嵌套结构（枚举+auto-SUM+辅助预填）
- `consol_disclosure_service` 瘦身（1736 行）
- `migration_runner` 瘦身（1026 行）
- `workpaper-content-semantic-system`（底稿内容平台化）

---

## 四、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| Schema drift | `python backend/scripts/check/check_schema_drift.py` |
| 最高迁移 | `ls backend/migrations/V*.sql \| sort \| tail -1` |
| Seed 覆盖率 | `python backend/scripts/check/check_account_to_report_line_seed_coverage.py` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 五、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 填日期 + commit，归档移到 `_archive/{分类}/`
3. 归档后同步更新 §〇 Spec 总数 + §二 分类计数
4. 分类（10 个）：01 地基 / 02 循环 / 03 打磨 / 04 架构 / 05 业务 / 06 工程 / 07 底稿瘦身 / 08 附注 / 09 合并 / 99 取代
5. 废弃 spec 移 `99-superseded/` + 记录取代者
6. **凭印象禁令**：完成度必须 grep 实证，不信文档自述
7. 迁移系统 = `backend/migrations/V*.sql`（D6 MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
