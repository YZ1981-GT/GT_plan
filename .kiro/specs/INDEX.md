# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-06-27  
**当前分支**：`work/2026-05-30-wp-specs`  
**Spec 总数**：**195**（active 13 + archived 182）+ 全局交叉索引 1  
**当前 active = 13**（3 全局治理 + 1 A1-11 + 6 A17子底稿 + 3 新增A类底稿）  
**最高迁移**：V093  
**测试总数**：~17100+（含 PBT 30+ properties）  
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

## 二、已归档 Spec（155 个，10 分类）

**当前 active = 13**（3 全局治理 + 1 A1-11 + 6 A17子底稿 + 3 新增A类底稿）。新建 spec 放 `.kiro/specs/{name}/`。

### Active Specs

| Spec | 状态 | 迁移 | 说明 |
|------|------|------|------|
| `display-format-single-source` | 🔵 未启动 | 无 | 金额/时间/百分比格式化收口到 displayPrefs 统一出口 + CI 守卫（43处formatAmount+70+处裸toLocaleString）|
| `cycle-palette-single-source` | 🔵 未启动 | 无 | 循环色板单一真源（cyclePalette.ts + --gt-cycle-* CSS 变量），4 处分裂收口 |
| `stale-propagation-cleanup-doc` | 🔵 未启动 | 无 | 删死代码 stale_incremental_propagation.py + stale 分层文档 |
| `a1-11-signing-control-form` | 🔵 进行中 | 无 | A1-11签发流转表（Task 1-4 done，5 PBT进行中）|
| `a17-1-audit-summary` | 🔵 未启动 | 无 | A17-1重大事项概要汇总专属组件(16章折叠卡片+签字表+左侧导航+B50/A13/A1-15联动) |
| `a17-2-1-kam` | 🔵 未启动 | 无 | A17-2-1关键审计事项(KAM)动态增删卡片+候选表+适用性开关+A17-1联动 |
| `a17-3-consultation-record` | 🔵 未启动 | 无 | A17-3业务咨询记录(元信息+4章+文件tag+AI准则查询预留) |
| `a17-3-1-consultation-execution` | 🔵 未启动 | 无 | A17-3-1业务咨询结果执行情况(极简5区块+A17-3引用联动) |
| `a17-4-disagreement-record` | 🔵 未启动 | 无 | A17-4重大专业分歧事项(人员动态表+6章textarea+签字区) |
| `a17-6-closing-meeting` | 🔵 未启动 | 无 | A17-6总结会会议纪要(最简组件,6字段卡片) |
| `a17-7-independence-declaration` | 🔵 未启动 | 无 | A17-7/A17-7A独立性声明书(variant双变体,签字表+威胁记录+期间承诺,~400行) |
| `a10-1-governance-communication` | 🔵 未启动 | 无 | A10-1与治理层沟通函(16章折叠卡片+左侧导航+服务费表格+签发,~600行) |
| `a12-1-legal-confirmation` | 🔵 未启动 | 无 | A12-1法律事务确认函(发函3问询+回函确认+诉讼动态列表+A5-3联动,~450行) |
| `a27-1-it-audit-memo` | 🔵 未启动 | 无 | A27-1 IT审计总结备忘录(IT团队表+7章卡片+三选一radio+条件展开+4个GtIndexChip,~500行) |

```
_archive/
├── 01-phase-foundation/         24   平台地基（Phase 0~16）
├── 02-workpaper-cycles/         16   审计循环（11循环+5基础，548 tasks）
├── 03-refinement-rounds/         9   五角色轮转（R1~R9）
├── 04-infra-architecture/       29   基础设施/全局架构
├── 05-business-features/        39   业务专项（含ledger/wp系列）
├── 06-engineering-governance/    6   工程治理
├── 07-workpaper-slimdown/       15   底稿瘦身 + 模块治理
├── 08-disclosure-notes/          5   附注模块
├── 09-consolidation-phases/      4   合并模块
├── 10-A~S-workpaper-all-cycles-complete/ 13  A~S全循环底稿（568任务，2026-06-19完成）
├── 11-confirmation-d0-module/   10   D0函证模块（283任务，2026-06-22完成）
├── 12-2026-06-23-batch/         12   架构加固+A类深化+分发持久化（2026-06-23完成）
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

### 2.5 `05-business-features/`（36）

**账表导入（5）**：`ledger-import-view-refactor` · `ledger-import-header-adapter-contract` · `ledger-import-sign-convention-migration` · `ledger-balance-diagnostics-report-line-coverage` · `ledger-sign-convention-unify`

**底稿专项（17）**：`wp-evidence-collection` · `wp-frontend-ux-polish` · `wp-functional-actions` · `wp-generation-pipeline` · `wp-locate-foundation` · `wp-performance-virtualization` · `wp-template-migration` · `wp-traceability-panel` · `wp-tsj-llm-review` · `wp-ai-review-ux-fix` · `workpaper-guardrail-cleanup` · `workpaper-account-package-d1-d2-pilot` · `workpaper-ai-conclusion-copilot` · `workpaper-content-semantic-contract` · `workpaper-bad-debt-nested-structure` · `workpaper-unified-import-export` · `word-template-dual-mode`

**报表/查询/角色（5）**：`advanced-query-enhancements-p1p2` · `partner-dashboard` · `procedure-applicability-trimming` · `role-based-view-switching` · `report-module-enhancement`

**核心流程（7）**：`proposal-remaining-18` · `e2e-business-flow` · `template-library-coordination` · `audit-chain-generation` · `enterprise-linkage` · `multi-standard-unification` · `schema-drift-full-sync`

**其他（3）**：`k-admin-cycle-post-review-fix` · `project-creation-enhancement` · `audit-report-deliverable-center`

### 2.6 `06-engineering-governance/`（6）

`repo-frontend-layout-unification` · `repo-git-workflow-unification` · `pytest-residual-failures-cleanup` · `migration-runner-resilience` · `frontend-consistency-m1` · `dev-tooling-modernization`

### 2.7 `07-workpaper-slimdown/`（15）

**底稿瘦身（9）**：`workpaper-html-renderer` · `workpaper-editor-slimdown` · `workpaper-list-shrink` · `workpaper-editor-shrink-phase2` · `gt-c-note-table-shrink` · `gtdform-test-and-shrink` · `custom-workpaper-formula-binding` · `audit-sheet-editable` · `report-view-slimdown`

**模块治理（6，2026-06-21 归档）**：`workpaper-render-config-refactor`（策略拆分，render_config 1474→747）· `workpaper-module-health-pass2`（9 项 P1/P2 治理）· `workpaper-silent-exception-cleanup`（70 处宽异常补留痕）· `workpaper-module-large-file-split`（pass3，3 文件拆 ≤800）· `workpaper-module-large-file-split-pass4`（3 服务文件拆 ≤800）· `workpaper-frontend-large-component-split`（前端 Top3 抽 composable）

### 2.8 `08-disclosure-notes/`（5）

`disclosure-note-full-revamp` · `note-dynamic-tables-and-template-inheritance` · `disclosure-note-linkage-and-slimdown` · `disclosure-note-semantic-structure-and-presentation` · `four-panel-note-linkage`

### 2.9 `09-consolidation-phases/`（4）

`consol-phase0-core-pipeline` · `consol-phase1-arch-lock` · `consol-phase2-orchestration` · `consol-phase3-frontend-drilldown`

### 2.10 `99-superseded/`（4）

| 旧 spec | 取代者 |
|---------|--------|
| `ledger-import-unification` | → `ledger-import-view-refactor` |
| `post-enhancement-bugfix` | → R9 + `global-refinement-v3` |
| `note-account-mapping-seed` | → `disclosure-note-full-revamp` |
| `linkage-panorama-graph` | → `enterprise-linkage` |

### 2.11 `12-2026-06-23-batch/`（12）

| Spec | 类型 | 摘要 |
|------|------|------|
| `a17-summary-enhancement` | Feature | 富文本RTE+一致性校验+LLM跨章polish+KAM集成+子文档导航+Word导出增强 |
| `a-cycle-docx-online` | Feature | A循环 docx 在线化（13必做+14 PBT） |
| `a-review-checklist-rbac` | Feature | 五级复核表RBAC+Sequential Gate+Sign-Lock+Unlock+Dashboard |
| `a13-misstatement-aggregation` | Feature | 事件驱动聚合+三色预警+上年结转+沟通函+ref_chip+SSE |
| `cross-workpaper-dispatch-persistence` | Feature | D0分发持久化 V093+DispatchService+EventBus+前端composable |
| `authorization-enforcement-baseline` | Feature | require_operation工厂+CI lint+7高风险端点接入 |
| `custom-query-authorization-hardening` | Bugfix | IDOR read+cross-project write修复 |
| `qc-python-rule-load-hardening` | Bugfix | _ALLOWED_RULE_PREFIXES白名单+admin-only python规则 |
| `report-cache-year-isolation` | Bugfix | _cache_key加year维度+SCAN通配符 |
| `single-source-cleanup` | Refactor | 6项去重收口（枚举合并+lru_cache+formula_grammar单源） |
| `multi-worker-readiness` | Feature | Redis分布式导入锁+地址坐标库single-flight+OCR服务化 |
| `workpaper-save-orchestrator` | Refactor | 统一after_save编排器+孤立EventBus删除 |

### 2.12 `05-business-features/` 补充

| Spec | 类型 | 摘要 |
|------|------|------|
| `word-template-dual-mode` | Feature | 25个word-template底稿统一双模式框架：el-segmented(结构化视图/在线编辑)+python-docx解析器+占位符提取+checklist_responses持久化+AI预填disabled+导出Word/导出模板/导入数据。33/33任务，~120测试 |

---

## 三、实质性程序循环 Spec（D~N + S，全部完成 ✅）

> 🔗 **全局交叉索引**：`.kiro/specs/_archive/10-A~S-workpaper-all-cycles-complete/CYCLE-CROSS-REFERENCE.md`

| Spec | 循环 | 任务 | wp_code | 测试 | 状态 |
|------|------|------|---------|------|------|
| c-cycle-workpapers | C 控制测试 | 42/42 | 95 | 304+286 | ✅ |
| d-cycle-workpapers | D 销售收入 | 38/38 | 49 | 342 | ✅ |
| e-cycle-workpapers | E 货币资金 | 39/39 | 33 | 129+50 | ✅ |
| f-cycle-workpapers | F 采购存货 | 58/58 | 93 | ~800 | ✅ |
| g-cycle-workpapers | G 投资 | 50/50 | 89 | 172 | ✅ |
| h-cycle-workpapers | H 固定资产 | 46/46 | 68 | 144 | ✅ |
| i-cycle-workpapers | I 无形资产 | 38/38 | 42 | 107 | ✅ |
| j-cycle-workpapers | J 职工薪酬 | 32/32 | 26 | 126 | ✅ |
| k-cycle-workpapers | K 管理 | 49/49 | 81 | 262 | ✅ |
| l-cycle-workpapers | L 筹资 | 43/43 | 56 | 110 | ✅ |
| m-cycle-workpapers | M 股东权益 | 46/46 | 58 | 114 | ✅ |
| n-cycle-workpapers | N 税费 | 40/40 | 35 | 87 | ✅ |
| s-cycle-workpapers | S 专项 | 47/47 | 90 | 72 | ✅ |
| **合计** | **13 循环** | **568/568** | **~815** | **~2457** | **全绿** |

全部归档到 `_archive/10-A~S-workpaper-all-cycles-complete/`。

---

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
