# Spec 总索引

**最后更新**：2026-05-17（v2.6 — workpaper-e1-cash-optimization 大改 v2：基于真实 4 文件 33 sheet 完整提取核验，修正 v1 共 15 处偏差，含双总控台 + 25+11 项程序拆解 + E1-1 193 公式拓扑 + 6 大优化方向）

> 此索引追踪所有 spec 的状态、关联文档、commit。
> **审计原则**：spec 不删，但标"演进/被取代/已合并"避免重复阅读。
> **实测铁律**：每行的"完成度/日期/commit"列必须有 grep 证据，凭印象写视为漏审。

> 数据生成方式：`python backend/scripts/_audit_specs.py` 一键重算（用完即删，需要时重跑）。

---

## §1 当前活跃区（聚焦最近 3 周 + 占位待办，14 个）

### 1.1 占位待办（未启动）

| Spec | 档次 | 完成度 | 优先级 | 说明 |
|------|------|-------|-------|------|
| `consol-note-three-level-drilldown/` | 档 3 | no-tasks | P1 | 合并附注→单体附注→单体底稿三级穿透；前置=真实合并母子项目数据；预估 3-4 天 |
| `workpaper-e1-cash-optimization/` | 档 2 | no-tasks | P1 | E1 货币资金底稿审计助理视角优化（v2 大改完整核验版）；6 大方向（双总控台裁剪/prefill 链路扩展到明细表/25+11 项程序完成状态联动/历史遗留清理/跨底稿超链接/CFS 勾稽+附件管理）；前置=Foundation+Cycle-D+global-linkage-bus 全完成；预估 12.5 天 |
| `workpaper-d-sales-cycle/` | 档 3 | **三件套 v1.0** | P1 | D 销售循环底稿优化（225+266+202=693 行三件套 vs E1 910 行 0.76×，复用 E1 9 组件 + 4 上游 spec 基础设施）；README v1.3 A+ 9.4/10（1213+318=1531 行 / 96KB / 17 章节 + 4 审定表 620 公式 + 9 总控台 133 项程序 + §6.4 schema/API/code 骨架）；38 任务 / 13 天 / 4 Sprint / 5 PBT / 19 UAT；P0 quickfix 2 天单独立项；启动条件待 E1 UAT 通过 |

### 1.2 实施中 / 部分完成（tasks.md 真实 [x] 比例）

| Spec | 完成度 | last commit | 真实状态（grep tasks.md） |
|------|-------|------------|---------------------------|
| `audit-chain-generation/` | 92/101 (91%) | 2026-05-16 (6b621f3) | 9 task 未标 [x]（多为 UAT 真人验收类）|
| `template-library-coordination/` | 63/64 (98%) **+ 9/10 UAT ✓** | 2026-05-17 | 编码任务 1 未标（6.3 枚举字典 DB-backed 升级 P0 缺口）；UAT 10 项 milestone 已达（8 ✓ + 1 ⚠ + 1 ○ 真人筛选器）|
| `e2e-business-flow/` | 50/58 (86%) | 2026-05-13 (4cea1f1) | 8 task 未标（含 UAT 类）|
| `enterprise-linkage/` | 46/56 (82%) | 2026-05-15 (2052290) | 10 task 未标 |
| `refinement-round9-global-deep-review/` | 83/91 (91%) | 2026-05-12 (a68eb18) | 8 task 未标 |
| `ledger-import-view-refactor/` | 239/243 (98%) | 2026-05-11 (007939e) | 4 task 未标 |
| `ledger-import-unification/` | **86/138 (62%)** ⚠ | 2026-05-08 (d8ac536) | 大部分被 view-refactor 取代但 tasks.md 未关闭 |

### 1.3 近期完成（≥ 95% 视为完成）

| Spec | 完成度 | last commit | 完成日期 |
|------|-------|------------|---------|
| `workpaper-completion-foundation/` | 38/38 (100%) | 2026-05-17 | 2026-05-17 |
| `workpaper-cycle-d-revenue/` | 31/31 (100%) | 2026-05-17 | 2026-05-17 |
| `table-unification-el-table/` | 26/26 (100%) | 2026-05-17 | 2026-05-17 |
| `global-linkage-bus/` | 52/52 (100%) | 2026-05-17 (9cac0d3) | 2026-05-17 |
| `note-account-mapping-seed/` | no-tasks (README only) | 2026-05-17 | 2026-05-17 |
| `v3-r10-linkage-and-tokens/` | 68/68 (100%) | 2026-05-16 (16c88a8) | 2026-05-16 |
| `v3-r10-editor-resilience/` | 48/48 (100%) | 2026-05-16 (16c88a8) | 2026-05-16 |
| `v3-linkage-stale-propagation/` | 23/23 (100%) | 2026-05-16 (b4cda44) | 2026-05-16 |
| `workpaper-deep-optimization/` | 119/120 (99%) | 2026-05-15 (71ca5f2) | 2026-05-15 |
| `production-readiness/` | 143/144 (99%) | 2026-05-05 (73204cf) | 2026-05-05 |

### 1.4 ⚠ 真实数据 vs memory 不一致清单（必须立即修正）

| 项 | memory 声称 | tasks.md 实测 | 处置 |
|----|-------------|---------------|------|
| ~~`workpaper-completion-foundation`~~ ✅ 已修正 | "23 task 全部完成" | 38/38 (100%) | **2026-05-17 实施完成** — 跑全 35 task + 9 PBT + 5 E2E 全绿 |
| ~~`workpaper-cycle-d-revenue`~~ ✅ 已修正 | "27 task 全部完成" | 31/31 (100%) | **2026-05-17 实施完成** — 4 JSON 数据文件齐全（21 validation rules / 18 cross-refs / 23 D-cycle PFM / 8 procedures）+ 26 PBT/集成测试全绿 |
| ~~`table-unification-el-table`~~ ✅ 已修正 | "21/21 完成" | 26/26 (100%) | **2026-05-17 UAT 完成** — 5 UAT 任务（vue-tsc 零错误 + 4 Playwright UAT 全绿，含试算汇总/权益变动/合并矩阵/字号联动）|
| `ledger-import-unification` | "全部完成" | 86/138 (62%) | 大部分被 ledger-import-view-refactor 取代但 tasks.md 没关闭；需补 [x] 或标"已 superseded by view-refactor" |
| `enterprise-linkage` | "5 Sprint / 41 必做完成" | 46/56 (82%) | 10 task 未标 |
| `refinement-round1` | "全部完成" | 33/45 (73%) | 12 task 未标 |
| `refinement-round2` | "全部完成" | 24/27 (89%) | 3 task 未标 |
| `post-enhancement-bugfix` | "已完成" | 134/149 (90%) | 15 task 未标 |
| `phase8` | "已完成" | 189/209 (90%) | 20 task 未标 |
| `global-platform-enhancement` | "已完成" | 199/206 (97%) | 7 task 未标 |

**整体诊断**：约 1/3 的 spec memory 标的"完成"实为"95%+ 接近完成"或"代码已交付 UAT 未跑"；workpaper Foundation + Cycle-D + table-unification 三个 100% 完成不一致项已于 2026-05-17 全部修正消除。剩余不一致项多为"UAT 真人验收未跑" + "被取代未关闭"两类。

---

## §2 重叠/演进路线分析（实施前必读）

### 群组 1：底稿优化（5 spec）

```
phase1b-workpaper (110/110 ✅)
  → phase12-workpaper-deep (172/172 ✅)
    → workpaper-deep-optimization (119/120 ✅)
      → workpaper-completion-foundation (38/38 ✅ 2026-05-17)
      → workpaper-cycle-d-revenue (31/31 ✅ 2026-05-17)
```
- ✅ 当前主线全部完成：deep-optimization + Foundation（基础设施 UI 机制）+ Cycle-D（数据填充）
- 📌 Foundation 含 35 task + 9 PBT + 5 Playwright E2E 全绿
- 📌 Cycle-D 含 4 JSON 数据文件 + 26 PBT/集成测试全绿（21 validation rules / 18 cross-refs / 23 D-cycle PFM / 8 procedures）

### 群组 2：联动 stale（5 spec）

```
phase15-task-tree-and-event-orchestration (119/119 ✅，event_bus 基础)
  → enterprise-linkage (46/56 82% ⚠)
    → v3-linkage-stale-propagation (23/23 ✅)
      → global-linkage-bus (52/52 ✅，URI 标准 + 6 模块图谱)
        → note-account-mapping-seed (README ✅，单体 280 条)
          → consol-note-three-level-drilldown (待办，三级穿透)
```
- ✅ 当前主线：global-linkage-bus（URI 标准 6 模块图谱）+ note-mapping
- 📌 下一步：consol-note-three-level-drilldown（启动条件 = 真实合并母子项目数据）
- ⚠ enterprise-linkage 还有 10 task 未关，但功能已被后续 spec 累加增强，**不必回填**仅保留 ADR

### 群组 3：账表导入（3 spec）

```
phase0-infrastructure (78/78 ✅)
  → ledger-import-unification (86/138 62% ⚠)
    → ledger-import-view-refactor (239/243 ✅，B' 视图，activate 127s→0.01s)
```
- ✅ 当前主线：view-refactor（已含 unification 大部分内容）
- ⚠ unification 完成度 62% 是因为大量任务被 view-refactor 取代未关闭；建议在 tasks.md 顶部加"已被 view-refactor 取代"标注

### 群组 4：全局打磨/Refinement（11 spec）

```
phase11-system-hardening (131/131 ✅，12 个 P0-P2)
  → global-platform-enhancement (199/206 96% ✅)
    → post-enhancement-bugfix (134/149 89% ⚠)
      → R1 (33/45 73% ⚠) → R2 (24/27 88% ⚠) → R3-R6 (✅)
        → R7 (no-tasks README only)
          → R8 (no-tasks README only) → R9 (83/91 91%)
            → v3-linkage-stale-propagation
              → v3-r10-linkage-and-tokens (68/68 ✅)
              → v3-r10-editor-resilience (48/48 ✅)
```
- ✅ 当前主线：R10 两个 spec（已完成 + UAT 待真人）
- ⚠ R1/R2/post-enhancement-bugfix 完成度 73-89%，部分被 R7-R10 整合，建议在 tasks.md 标"已转 R7-R10"
- ❌ R7/R8 没 tasks.md 仅 README，按规约不算正式 spec（但 README 价值保留）

### 群组 5：审计链路 + 报表导出（3 spec）

```
phase1c-report (118/118 ✅)
  → phase13-word-export (119/119 ✅)
    → audit-chain-generation (92/101 91% ⚠)
```
- ✅ 当前主线：audit-chain-generation
- ⚠ 9 task 多是 UAT 真人验收类，标 [x] 取决于真人测过

### 群组 6：模板库 + 治理（2 spec）

```
phase14-gate-engine-governance (134/134 ✅)
  → template-library-coordination (63/64 98% ⚠ 剩 1 项 6.3)
```
- ✅ 当前主线：template-library
- 📌 剩 1 task = 6.3 枚举字典 DB-backed 升级（独立 Sprint 处理）

### 群组 7：表格统一化（独立链）

```
table-unification-el-table (26/26 ✅ 2026-05-17)
```
- ✅ 21 编码 task + 5 UAT 已通过（vue-tsc 零错误 + 4 Playwright UAT 全绿）

---

## §3 已沉淀历史区（旧 phase + 已完成 R 系列，21 个，折叠阅读）

> 这些 spec 已 100% 完成或被后续 spec 整合替代，**新需求不要再改这批**。
> 列在此处仅供 ADR 阅读追溯。

| Spec | 完成度 | last commit | 完成日期 |
|------|-------|------------|---------|
| `phase0-infrastructure/` | 78/78 (100%) | 78457fc | 2026-04-18 |
| `phase1a-core/` | 137/137 (100%) | 78457fc | 2026-04-18 |
| `phase1b-workpaper/` | 110/110 (100%) | 78457fc | 2026-04-18 |
| `phase1c-report/` | 118/118 (100%) | 78457fc | 2026-04-18 |
| `phase2-consolidation/` | 103/103 (100%) | 4cef051 | 2026-04-13 |
| `phase3-collaboration/` | 141/141 (100%) | 78457fc | 2026-04-18 |
| `phase4-ai/` | 90/90 (100%) | 8811649 | 2026-04-13 |
| `phase5-extension/` | 214/214 (100%) | 28dcbce | 2026-04-19 |
| `phase6-integration/` | 356/356 (100%) | 28dcbce | 2026-04-19 |
| `phase7-enhancement/` | 209/209 (100%) | 28dcbce | 2026-04-19 |
| `phase11-system-hardening/` | 131/131 (100%) | d50680c | 2026-04-26 |
| `phase12-workpaper-deep/` | 172/172 (100%) | 4fdae2f | 2026-04-27 |
| `phase13-word-export/` | 119/119 (100%) | 4fdae2f | 2026-04-27 |
| `phase14-gate-engine-governance/` | 134/134 (100%) | b78ad0b | 2026-04-29 |
| `phase15-task-tree-and-event-orchestration/` | 119/119 (100%) | b78ad0b | 2026-04-29 |
| `phase16-evidence-package-and-versionline/` | 126/126 (100%) | b78ad0b | 2026-04-29 |
| `refinement-round3-quality-control/` | 29/29 (100%) | 4194e88 | 2026-05-06 |
| `refinement-round4-audit-assistant/` | 26/26 (100%) | 2a0358f | 2026-05-06 |
| `refinement-round5-independent-review/` | 27/27 (100%) | f9bd1fa | 2026-05-06 |
| `refinement-round6-cross-role-optimization/` | 18/18 (100%) | 4194e88 | 2026-05-06 |
| `refinement-round7-global-polish/` | README only | 2e72884 | 2026-05-07 |
| `refinement-round8-deep-closure/` | README only | 1224eba | 2026-05-07 |

> **§3 注**：`refinement-round1-review-closure/` (33/45 73%) 和 `refinement-round2-project-manager/` (24/27 88%) 完成度未到 95%，但功能已被 R7-R10 整合取代，归类为"已被取代但保留 ADR"，不再回填 [x]；详见 §1.4 不一致清单。

---

## §4 当前程序状态（grep 实测，2026-05-17）

> **重要纠正**：以下数字是 `python -c "import glob; ..."` + `docker exec psql` 实测；之前 INDEX 写的"151/226/51/86/194/16"是 memory 旧快照已过时 30%+。

| 维度 | 实测值 | 实测命令 |
|------|--------|---------|
| 后端 routers | **211** | `glob('backend/app/routers/**/*.py')` |
| 后端 services | **325** | `glob('backend/app/services/**/*.py')` |
| 后端 models | **56** | `glob('backend/app/models/**/*.py')` |
| 前端 views | **96** | `glob('audit-platform/frontend/src/views/**/*.vue')` |
| 前端 components | **266** | `glob('audit-platform/frontend/src/components/**/*.vue')` |
| 前端 composables | **48** | `glob('audit-platform/frontend/src/composables/**/*.ts')` |
| 前端 stores | **9** | `glob('audit-platform/frontend/src/stores/**/*.ts')` |
| PG 表数 | **188** | `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public'` |
| 总 spec 数 | **47**（不计 v3-quickfixes 4 个已删；含新增 workpaper-e1-cash-optimization + workpaper-d-sales-cycle 2 个占位 spec）| `ls .kiro/specs/` |
| Alembic 末端 | linkage_audit_log_20260517 | grep `down_revision` 反向追溯 |

**memory 旧快照 vs 实测对比**（让下次更新有依据）：
- routers 151 → 211（+40%）
- services 226 → 325（+44%）
- views 86 → 96（+12%）
- components 194 → 266（+37%）
- composables 16 → 48（+200%）
- PG 表 152 → 188（+24%）

**结论**：memory 数字至少落后 1 个月，**月度 grep 重算规约** 必须落到自动化（`backend/scripts/_audit_specs.py` 已建用作此目的）。

---

## §5 索引规约（v2 升级版）

1. **新建 spec 时**必须更新此表 + 跑 `_audit_specs.py` 同步实测
2. **完成 spec 时**填 last commit hash + 完成日期（grep `git log --pretty=%cs|%h` 取真值）
3. **废弃 spec 时**改 status 为 ❌ + 记录废弃原因；**spec 不删**（保留作 ADR 阅读）
4. **每月一审**：跑 `_audit_specs.py` 重算所有完成度 + 程序实测数字
5. **重叠分析**：当主题群组超过 3 个 spec 时，必须画演进路线图避免重复阅读
6. **凭印象禁令**（v2 新增）：完成度 / 日期 / 演进关系 严禁凭印象写，必须 grep 证据
7. **memory 与 INDEX 双向核对**（v2 新增）：每月对照 §1.4 不一致清单，差异 ≥ 5% 强制纠正

---

## §6 工作流规范引用

详见 `.kiro/steering/conventions.md` 的 spec 工作流章节，本索引补充：

- **档 1 直接修**：单文件 ≤ 0.5 天，直接编辑，commit 时引用 v3 P0-N
- **档 2 小型 spec**：写 README.md（如 note-account-mapping-seed / consol-note-three-level-drilldown）
- **档 3 完整三件套**：requirements.md + design.md + tasks.md + 可选 snapshot.json

---

## §7 最近重大架构决策摘要（2026-05-17）

完整决策见 `.kiro/steering/architecture.md` 和 `memory.md`，本节摘录与 spec 演进相关：

1. **联动 URI 标准** `{module}:{code}:{sheet}:{label}`（6 模块）
2. **合并附注架构铁律**：合并版多家加总不映射底稿；单体版精确映射；右键三级穿透待 consol-note 实施
3. **跨项目稳定标识**：种子用业务名称替代机械编号；`disclosure_notes.section_title` 反查
4. **B' 视图架构**：`get_active_filter` + view 视图替代 metadata 切换；activate 0.01s
5. **stale_engine 单例 reload**：`GET /api/linkage-bus/graph?rebuild=true` 是后端常驻进程的唯一刷新方式
6. **subagent 工时压缩比 > 50× 触发独立验证**：4 项证据要求；UAT 必须 Playwright 真实跑
7. **凭印象禁令**（v2 新增）：metadata 工作（INDEX/审计/汇总）适用同等 grep 核验铁律

---

## §8 已沉淀短 spec（已删除目录）

| 项 | 当时档次 | 完成日期 | 沉淀位置 |
|----|---------|---------|---------|
| (直接修) PG ALTER TYPE / consistency-check / recheck-threshold / 端点核验 | 档 1 | 2026-05-16 | memory.md "v3 档 1 直接修 5 件已完成" |
| `v3-quickfixes/` Q1-Q4 | 档 2 | 2026-05-16 | memory.md + commit b4cda44 |
