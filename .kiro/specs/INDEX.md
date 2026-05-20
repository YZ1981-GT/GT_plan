# Spec 总索引

**最后更新**：2026-05-20（v3.0 — 全部 11 审计循环 spec 100% 完成 548/548 tasks + B/C 联动补充 CW-382~400）

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

**汇总**：548/548 tasks / 400 CWR / 1035 prefill cells / 53 VR rules / 全循环 PBT / 全循环 IPO 占位

---

## §2 其他活跃 Spec

### 2.1 实施中（未 100%）

| Spec | 完成度 | 说明 |
|------|-------|------|
| `e2e-business-flow/` | 50/58 (86%) | 8 task 未标（含 UAT 真人验收类）|
| `template-library-coordination/` | 63/64 (98%) | 剩 1 task（6.3 枚举字典 DB-backed）|
| `audit-chain-generation/` | 92/101 (91%) | 9 task（UAT 真人验收类）|
| `enterprise-linkage/` | 46/56 (82%) | 功能已被后续 spec 增强，保留 ADR |
| `ledger-import-view-refactor/` | 239/243 (98%) | 4 task（运维/手动验证）|
| `k-admin-cycle-post-review-fix/` | 18/18 ✅ | 2026-05-20 完成 |

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

## §5 当前程序规模（2026-05-20 实测）

| 维度 | 值 |
|------|---|
| 后端 routers | 215+ |
| 后端 services | 330+ |
| 后端 models | 56 |
| 前端 views | 96 |
| 前端 components | 283 |
| 前端 composables | 52 |
| 前端 stores | 9 |
| PG 表数 | 188 |
| 底稿模板 | 473 |
| cross_wp_references | 400 条 |
| prefill_formula_mapping | 1035 cells |
| validation_rules | 53 条（D×25 + F×4 + G×4 + H×4 + I×3 + J×3 + K×3 + L×3 + M×2 + N×2）|
| 测试文件 | 300+ |
| Alembic 迁移 | 59 版本 |
| git 分支 | feature/e2e-business-flow (HEAD) |

---

## §6 索引规约

1. 新建 spec 时必须更新此表
2. 完成 spec 时填完成日期
3. 废弃 spec 时标"已被取代" + 记录取代者
4. 每月一审重算完成度
5. 凭印象禁令：完成度/日期必须 grep 证据
