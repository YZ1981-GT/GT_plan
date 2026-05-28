# Spec 总索引

**最后更新**：2026-05-28（v3.8 — `global-refinement-v3` Sprint 0-4 全完成 143/145 tasks，vue-tsc 0 / vitest 0 failed / 2094 passed；CI 双卡点已上线；剩 14.4 真合伙人 UAT）

> 此索引追踪所有 spec 的状态、关联文档、commit。
> **审计原则**：spec 不删，但标"演进/被取代/已合并"避免重复阅读。
> **实测铁律**：每行的"完成度/日期/commit"列必须有 grep 证据，凭印象写视为漏审。

---

## §1 审计循环 Spec（11 个，全部 100% 完成）

| Spec | Tasks | 完成日期 | 关键产出 |
|------|-------|---------|---------|
| `workpaper-d-sales-cycle/` | 53/53 ✅ | 2026-05-19 | D4 VR×4 / CWR 175 / prefill 93 cells / 12 IPO codes |
| `workpaper-e1-cash-optimization/` | 91/91 ✅ | 2026-05-18 | E1 双总控台 / 25+11 程序联动 / 193 公式拓扑 |
| `workpaper-f-purchase-inventory/` | 58/58 ✅ | 2026-05-19 | F2 两级 prefill 链路 / CWR 176~210 / 107 cells / 12 IPO |
| `workpaper-g-investment-cycle/` | 55/55 ✅ | 2026-05-19 | 3 router(fair_value/ecl/classification) / VR×4 / 134 cells / 12 类 sheet |
| `workpaper-h-fixed-assets-cycle/` | 59/59 ✅ | 2026-05-19 | 4 方法折旧引擎 / DCF 减值 stub / H9→H8 反向回填 / 148 cells |
| `workpaper-i-intangible-assets-cycle/` | 62/62 ✅ | 2026-05-19 | 摊销引擎(复用 H) / 商誉 CGU / VR×3 / 90 cells / term 参数 |
| `workpaper-j-payroll-cycle/` | 38/38 ✅ | 2026-05-19 | 薪酬计提 12 月序列 / Black-Scholes / VR×3 / 59 cells |
| `workpaper-k-admin-cycle/` | 38/38 ✅ | 2026-05-19 | 费用 YoY 分析 / 跨循环减值汇总 / 10 类 sheet / 139 cells |
| `workpaper-l-debt-cycle/` | 39/39 ✅ | 2026-05-20 | 利息计算 3×3 / 实际利率法摊余成本 / VR×3 / 90 cells |
| `workpaper-m-equity-cycle/` | 28/28 ✅ | 2026-05-20 | 权益变动 6 列汇总 / VR×2 / 87 cells / 8 类 sheet |
| `workpaper-n-tax-cycle/` | 27/27 ✅ | 2026-05-20 | 所得税引擎 stub / VR×2 / 64 cells / 8 类 sheet / C12 前置 |

**汇总**：548/548 tasks / 400 CWR / 1035 prefill cells / 114 VR rules / 全循环 PBT / 全循环 IPO 占位

---

## §2 其他活跃 Spec

### 2.1 实施中（未 100%）

| Spec | 完成度 | 说明 |
|------|-------|------|
| `phase1-experience-gap-fix/` | 19/19 ✅ | 2026-05-21 上线（全局搜索+字号统一+面包屑+compact+版本锁，UAT 10/10）|
| `phase2-role-experience-boost/` | 22/22 ✅ | 2026-05-21 上线（签字 Gate+QC 热力图+批量+prefill diff+优先级，UAT 12/12）|
| `phase3-system-enhancement/` | 30/30 ✅ ⚠ | 2026-05-21 上线（双向穿透+LLM+压测+暗色+Storybook）；UAT-3/UAT-5 待外部环境（vLLM 真实接入 + 6000 并发实测）|
| `phase4-long-term-governance/` | 23/23 ✅ | 2026-05-21 上线（PG RLS+多年度对比+EQCR 快照+迁移回滚+Redis HA，UAT 9/10）|
| `phase5-operational-excellence/` | 63/63 ✅ | 2026-05-22 上线（router_registry 拆分+SSE 32 类型+SLA 预警+批量复核，UAT 10/10）|
| `phase6-precision-and-security/` | 32/32 ✅ | 2026-05-22 上线（Decimal.js+ESLint 防护+项目级权限+二次密码+复核层级，UAT 14/14）|
| `phase7-role-experience-closure/` | 50/50 ✅ | 2026-05-22 上线（EQCR 三件套+QC 三件套+工时四件套+复核通知+紧急度，UAT 14/14）|
| `phase8/` | 116/116 ✅ | 2026-05-22 完成（116 tests，含性能 23 + 冒烟 16）|
| `proposal-remaining-18/` | 30/30 ✅ ⚠ | 2026-05-22 上线（27 项剩余功能 + 6 项伪绿真补：D-1 lazy load / L-4 公式引擎 / K-4 reasoning chain / M-5 / L-2 / L-3 / C-3 SSE / AT-2 LibreOffice / MT-8 cleanup worker）|
| `e2e-business-flow/` | 58/58 ✅ | 2026-05-23 完成（程序化 UAT 验收 4 项目 Layer 1-4 全 PASS）|
| `template-library-coordination/` | 64/64 ✅ | 2026-05-23 完成（Property 2 PBT 就位）|
| `audit-chain-generation/` | 101/101 ✅ | 2026-05-23 完成（综合 PBT 9 项 / 22 tests）|
| `enterprise-linkage/` | 56/56 ✅ | 2026-05-23 完成（10 项 PBT + 集成 + 性能基线 / 22 tests）|
| `ledger-import-view-refactor/` | 243/243 ✅ | 2026-05-23 完成（9.10 Day 30 索引清理：72.82MB DROP + 38MB REINDEX 共 110MB 回收）|
| `advanced-query-enhancements-p1p2/` | 16 Tasks ✅ | 2026-05-24 完成（15 Req / 5 Phase / 212 tests：29 PBT + 单测 + e2e；wp_template_registry + GIN + 单源化 + 审计节流 + LO 池化 + 跨模块 cell + 模板联动 + 批量查询 + 写回 + 追溯 + 4 体验组件）|
| `k-admin-cycle-post-review-fix/` | 18/18 ✅ | 2026-05-20 完成 |
| `disclosure-note-full-revamp/` | 44/47 ✅ ⚠ | 2026-05-27 完成核心（Sprint 0~4 / 47 tasks 中 4 任务待外部，剩 F-1 UAT 真项目 / F-2 dev-history / F-3 文档；commits 6b6731c+65fc11a+3c5067c+e1477b2+1729c38f+58cff337+736cf1d4+551835b6；pytest 430/430 全绿；致同 21 排版+11 视觉断言+ADR-007/008/009/010；4101 binding cells / 25 列语义 / PRESET_TO_RULE 11 枚举 / NoteFormatConfig 21 字段 frozen / NOTE↔TB 双向边）|
| `global-refinement-v3/` | 143/145 ✅ ⚠ | 2026-05-28 完成核心（Sprint 0~4 + 回归 / 13 Req / 13 Property PBT 全绿；后端 145 / 前端 vue-tsc 0 + vitest 2094 passed / 0 failed / 7 skipped；CI 双卡点已上线（vue-tsc 0 errors + vitest 0 failed + GtAmountCell 66 only-increase + el-form :rules 70 only-increase + WorkpaperEditor 2555 only-decrease + no-console strict 0）；剩 14.4 真合伙人 UAT；gaps.md 已建反向记录 GtAmountCell 17%/80% + WorkpaperEditor 2555/1000 等技术债，下一个 spec `gt-amount-cell-rollout` 推进）|

### 2.2 已被取代（保留 ADR）

| Spec | 完成度 | 取代者 |
|------|-------|--------|
| `ledger-import-unification/` | 86/138 (62%) | → `ledger-import-view-refactor` |
| `refinement-round1-review-closure/` | 33/45 (73%) | → R7~R10 整合 |
| `refinement-round2-project-manager/` | 24/27 (88%) | → R7~R10 整合 |
| `post-enhancement-bugfix/` | 134/149 (90%) | → R9 + v3 系列 |

### 2.3 占位待办

| Spec | 说明 |
|------|------|
| `consol-note-three-level-drilldown/` | 合并附注三级穿透；前置=真实合并母子项目数据 |
| `workpaper-list-shrink/` | README stub（2026-05-28）：WorkpaperList 3238 行拆 5 SFC + shell；触碰时启动完整三件套 |
| `workpaper-fill-service-split/` | README stub（2026-05-28）：workpaper_fill_service 1587 行拆 4 service；prefill 扩展时启动 |
| `gt-c-note-table-shrink/` | README stub（2026-05-28）：GtCNoteTable 1608 / GtEControlTest 1125 拆子组件；触碰时启动 |

---

## §3 基础设施完成区（全部 100%）

| Spec | Tasks | 完成日期 |
|------|-------|---------|
| `workpaper-completion-foundation/` | 38/38 | 2026-05-17 |
| `workpaper-cycle-d-revenue/` | 31/31 | 2026-05-17 |
| `table-unification-el-table/` | 26/26 | 2026-05-17 |
| `global-linkage-bus/` | 52/52 | 2026-05-17 |
| `v3-r10-linkage-and-tokens/` | 68/68 | 2026-05-16 |
| `v3-r10-editor-resilience/` | 48/48 | 2026-05-16 |
| `v3-linkage-stale-propagation/` | 23/23 | 2026-05-16 |
| `workpaper-deep-optimization/` | 119/120 | 2026-05-15 |
| `production-readiness/` | 143/144 | 2026-05-05 |
| `refinement-round9-global-deep-review/` | 83/91 | 2026-05-12 |
| `global-platform-enhancement/` | 199/206 | 2026-05-10 |
| `phase8/` | 189/209 | 2026-05-09 |

---

## §4 已沉淀历史区（phase 0~16 + R3~R6，全部 100%）

| Spec | Tasks | 完成日期 |
|------|-------|---------|
| `phase0-infrastructure/` | 78/78 | 2026-04-18 |
| `phase1a-core/` | 137/137 | 2026-04-18 |
| `phase1b-workpaper/` | 110/110 | 2026-04-18 |
| `phase1c-report/` | 118/118 | 2026-04-18 |
| `phase2-consolidation/` | 103/103 | 2026-04-13 |
| `phase3-collaboration/` | 141/141 | 2026-04-18 |
| `phase4-ai/` | 90/90 | 2026-04-13 |
| `phase5-extension/` | 214/214 | 2026-04-19 |
| `phase6-integration/` | 356/356 | 2026-04-19 |
| `phase7-enhancement/` | 209/209 | 2026-04-19 |
| `phase11-system-hardening/` | 131/131 | 2026-04-26 |
| `phase12-workpaper-deep/` | 172/172 | 2026-04-27 |
| `phase13-word-export/` | 119/119 | 2026-04-27 |
| `phase14-gate-engine-governance/` | 134/134 | 2026-04-29 |
| `phase15-task-tree-and-event-orchestration/` | 119/119 | 2026-04-29 |
| `phase16-evidence-package-and-versionline/` | 126/126 | 2026-04-29 |
| `refinement-round3~6/` | 100/100 | 2026-05-06 |

---

## §5 当前程序规模（2026-05-22 实测）

| 维度 | 值 |
|------|---|
| 后端 routers | 271 |
| 后端 services | 345 |
| 后端 models | 58 |
| 后端 workers | 12 |
| 后端 tests | 464 |
| 前端 views | 99 |
| 前端 components | 353 |
| 前端 composables | 81 |
| 前端 stores | 9 |
| 前端 services | 37 |
| 前端 utils | 39 |
| PG 表数 | 188 |
| 底稿模板 | 456 |
| cross_wp_references | 400 条 |
| prefill_formula_mapping | 1035 cells |
| validation_rules | 114 条（bcas×25 / d×25 / efghijklmn×36 / f×4 / g×4 / h×4 / i×3 / j×3 / k×3 / l×3 / m×2 / n×2）|
| Alembic 迁移 | 61 版本 + 28 SQL（migrations/）|
| Spec 总数 | 70 |
| git 分支 | feature/e2e-business-flow (HEAD) |

---

## §6 索引规约

1. 新建 spec 时必须更新此表
2. 完成 spec 时填完成日期
3. 废弃 spec 时标"已被取代" + 记录取代者
4. 每月一审重算完成度
5. 凭印象禁令：完成度/日期必须 grep 证据
