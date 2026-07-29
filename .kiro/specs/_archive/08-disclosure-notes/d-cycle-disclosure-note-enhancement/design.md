# Design Document

## Overview

本 spec 在 D 循环披露表↔附注模块已全链打通（结构化推送 / 正反向跳转 / 定向刷新 / 保存自动同步 `useDisclosureAutoSync`）的基础上，补两类系统性增强：

1. **审定↔披露一致性可见（Req1/Req2）**：把 D1/D2 已验证的「审定合计 vs 披露合计 差异告警 + 从审定表一键刷新」范式扩到 D3/D5/D6/D7（当前仅 D1/D2 有）。
2. **项目级批量同步入口（Req4）**：审计收尾阶段一键把全项目已映射科目的披露数据落到附注，减少逐科目手动。

设计基调：**复用已验证范式，不新建能力；additive 零回归；无 DB 迁移**。

## Architecture

### 数据流现状（实测确认）

```
底稿披露 tab（D3/D5/D6/D7 TabDisclosure*.vue）
  ├─ 编辑保存 → useDisclosureAutoSync.scheduleAutoSync(syncToDisclosureNotes)  [已有，~90 tab 已铺]
  │                        │
  │                        └─ buildXSyncPayload（前端构建 sub_table_data+columns+_note_texts）
  │                                  │  POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper
  │                                  ▼
  │                        wp_disclosure_sync_service.sync_from_workpaper → disclosure_notes 落库
  ├─ checkNoteConsistency（只读校对：披露表合计 vs 附注模块合计）              [D1/D2 已有 → 本 spec 不涉及]
  └─ 【本 spec 新增】审定合计（跨sheet键）vs 披露合计 → 差异告警 + 从审定表刷新  [Req1/Req2]
```

**关键约束（Req4 设计依据）**：`sync_from_workpaper` 恒需前端构建的 `sub_table_data`/`columns`（各科目 `buildXSyncPayload` 逻辑在前端，依赖各 tab composable 内存态）。后端**没有** payload builder，无法为任意科目代建结构化推送载荷。已有的 `sync-batch-from-workpaper` 端点是「单底稿 wp_id + 多 section items」批量（G7 跨章节编排器用），**不是「全部底稿」批量**。

### 各需求落点

| 需求 | 落点 | 复用/新增 |
|---|---|---|
| Req1 审定↔披露差异告警 | D3/D5/D6/D7 TabDisclosure（listed+soe） | 新增薄共享 composable + 各 tab wiring；复用 D1/D2 范式 |
| Req2 从审定表刷新 | 同上 | 各 tab `refreshFromAdjudication`；复用 D1 `fillPortfolioAgingBands`/D2 `importFromXxx` 覆盖范式 |
| Req3 D1/D2 零回归 | D1TabDisclosure / D2DisclosureNoteBody | 不改动，仅新增 D3-D7 独立实现 |
| Req4 项目级批量同步 | DisclosureEditor「🔁 全部刷新」（已存在） | 复用，不重复建（决策 2） |
| Req5 权限门控 | 前端按钮 disabled + 后端 `require_project_access("edit")` | 复用现有权限依赖 |
| Req6 零回归 | 全部 | additive；无迁移；不改 sync_from_workpaper 签名 |

## 设计决策

### 决策 1：Req1/Req2 用「薄共享 composable + 各 tab 自备 getter」，不强共享也不四份拷贝

D1/D2 是 per-tab bespoke（Req3 要求 D3-D7「对齐 D1/D2 范式但独立实现」）。四个科目（D3/D5/D6/D7）的审定合计跨 sheet 键与披露合计取法各不相同，但告警计算/横幅渲染/刷新交互完全同构。

**方案**：新建薄共享 composable `useDisclosureAdjudicationReconcile`（纯计算，不含科目特定键）：

```ts
// audit-platform/frontend/src/components/workpaper/composables/useDisclosureAdjudicationReconcile.ts
export function useDisclosureAdjudicationReconcile(opts: {
  auditedTotal: () => number      // 审定表 X-1 各分类行期末审定数之和（各 tab 从跨 sheet 键聚合传入）
  disclosureTotal: () => number   // 披露表主表合计行期末金额（各 tab 从本地 computed 传入）
  hasAudited?: () => boolean       // 审定合计是否有值（无值不误报，仅提示未取到）
  tolerance?: number               // 默认 1 元
}): {
  diff: ComputedRef<number>
  level: ComputedRef<'ok' | 'warn' | 'no-data'>
  message: ComputedRef<string>
}
```

各 tab 提供 `auditedTotal`（复用各科目 `useXCrossSheet` / `useXDisclosure` 已暴露的审定聚合，或从 allResponses 的审定表跨 sheet 键读取）+ `disclosureTotal`（主表合计行期末）。告警横幅、刷新按钮、只读态由各 tab 模板渲染（对齐 D1/D2 的 el-alert 范式）。

**理由**：纯计算收敛为单一真源（防 4 份拷贝的告警口径漂移），科目特定的键留在各 tab（尊重差异，避免过度抽象）。

### 决策 2：Req4「项目级批量同步」— 🔴 复盘确认**已由现有「🔁 全部刷新」满足，本 spec 不重复建**

**复盘实证（2026-07-28）**：`DisclosureEditor.vue` 已存在项目级批量入口：
- 工具栏「🔁 全部刷新」按钮（tooltip：**「从底稿披露表起，刷新全部附注主要项目下的科目数据」**）→ `onRefreshAll`（`useNoteRefresh`）→ `refreshDisclosureFromWorkpapers(projectId, year)` → 后端 `POST P_dn.refreshFromWorkpapers`（项目级 `refill_sections` 全量取数刷新，与决策原 Option B 完全同源）；
- 返回 `RefreshFromWorkpapersResult`（`refreshed / total_notes / sections_recomputed / ...` = 已有 counts）；
- 已带权限门控 `v-if="!isEqcrRole"`（EQCR 只读隐藏）；
- 已有 sync-hint 引导「检测到底稿已编制审定/披露数据 → 立即全部刷新」。

**约束**：后端不能为任意科目代建结构化 payload（builder 在前端）。项目级"结构化推送"无法 backend-driven；backend-native 的"从底稿刷新"就是 `refill_sections`——而这**正是现有「全部刷新」所做的**。

**结论**：Req4 的可行且非重复实现 = 现有「🔁 全部刷新」。**本 spec 不新建 `batch-refresh-from-workpapers` 端点/按钮**（重复建违反"需要存在吗"）。Req4 验收改为**确认现有能力覆盖**：① 覆盖 registry 全部映射 section（`refill_sections` 无 section 参 = 全量）② 权限门控在（`!isEqcrRole`）③ 结果 counts + 进度反馈在（`RefreshFromWorkpapersResult` + `refreshAllLoading`）。若发现覆盖不全（如未含某映射 section），仅在现有 `onRefreshAll`/`refreshFromWorkpapers` 内补 registry-scoping，不另起端点。

> 若用户后续明确要"结构化批量推送（buildXSyncPayload 逐科目）"而非"取数刷新"，因后端无 payload builder，须走前端编排（各底稿运行时在场逐一 build+POST，工作量大）——那是独立 feature，应另立 spec，不在本轻量增强内。

## Components and Interfaces

### 前端

1. **`composables/useDisclosureAdjudicationReconcile.ts`（新增）**：纯计算，接口见决策 1。
2. **D3TabDisclosureListed/Soe、D5/D6/D7TabDisclosure（改）**：
   - 引入 reconcile composable，提供 `auditedTotal`/`disclosureTotal` getter。
   - 模板顶部渲染差异横幅（warn>1元黄 / ≤1元绿 / no-data 灰提示），只读态同样渲染。
   - 非只读态提供「从审定表刷新」按钮 → `refreshFromAdjudication()`：`ElMessageBox.confirm` 后按名称匹配用审定表各分类行期末审定数覆盖披露表主表对应行期末金额（仅期末列；期初/说明/动态行不动；未匹配行不动）；刷新后横幅自动重算。
3. **`views/DisclosureEditor.vue`（Req4：不改，仅确认）**：项目级批量入口已存在（「🔁 全部刷新」→ `onRefreshAll` → `refreshDisclosureFromWorkpapers`），已带权限门控 + 结果 counts + sync-hint 引导。本 spec **不新增按钮/端点**；仅在验收阶段确认其覆盖 registry 全部映射 section。

### 后端

**无新增端点**（Req4 复用现有 `refreshFromWorkpapers` 项目级刷新，见决策 2）。本 spec 后端零改动，不触碰 `sync_from_workpaper` / `sync_batch_from_workpaper` / `refill_sections` 签名（Req6）。

## Data Models

无新表、无 DB 迁移、无既有表结构变更（Req6）。仅新增：
- 前端 composable（纯计算）；
- 后端批量刷新端点响应模型（Pydantic，仅 API 层）。

## Correctness Properties

### Property 1: 差异告警计算正确
`level` = `no-data`（无审定合计）/ `warn`（|审定−披露|>tolerance）/ `ok`（≤tolerance）；message 含双方合计与差额。
**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: 只读态显示但不可操作
只读态横幅照常渲染（供复核人查看），「从审定表刷新」按钮 disabled。
**Validates: Requirements 1.6, 2.1, 5.2**

### Property 3: 从审定表刷新只覆盖期末列 + 未匹配不动
`refreshFromAdjudication` 仅按名称匹配覆盖主表期末金额；期初金额/说明文本/动态行不变；审定表无同名行的披露行保持原值。
**Validates: Requirements 2.3, 2.5**

### Property 4: 刷新后差异重算归零
刷新（全部匹配情况下）后 `diff` → 0，横幅转 `ok`。
**Validates: Requirements 2.4**

### Property 5: D1/D2 零回归
D1TabDisclosure / D2DisclosureNoteBody 的既有差异告警与「从审定表带入」逻辑不改动；新增仅在 D3-D7。
**Validates: Requirements 3.1, 3.2, 6.1**

### Property 6: Req4 由现有「全部刷新」满足（不重复建）
项目级批量刷新入口已存在（`onRefreshAll` → `refreshDisclosureFromWorkpapers` → 后端 `refill_sections` 全量），本 spec 不新增端点/按钮；验收确认其覆盖 registry 全部映射 section + 权限门控 + counts 返回。
**Validates: Requirements 4.1, 4.2, 4.4, 4.5, 5.1**

### Property 9: additive 零回归
无 DB 迁移、无新表；`sync_from_workpaper` 签名不变；各科目手动「同步到附注」与 `useDisclosureAutoSync` 行为不变；`refill_sections` 逻辑不变。
**Validates: Requirements 6.2, 6.3, 6.4, 6.5**

## Error Handling

- **审定合计取不到**：`level='no-data'`，横幅灰色提示"未取到审定表合计"，不误报差异（Property 1）。
- **刷新按名称匹配失败**：未匹配行静默保留原值 + ElMessage 告知匹配了几行（Property 3）。
- **批量刷新单节失败**：fail-open 记入 failures，继续（Property 6）；整体端点异常 → rollback + 500（不留半状态）。
- **附注尚未生成**：批量刷新对无 disclosure_notes 记录的 section 跳过（skipped），不报错。

## Testing Strategy

- **前端 vitest**：`useDisclosureAdjudicationReconcile.spec.ts`（Property 1/4：告警分级、刷新后归零）；各 tab `refreshFromAdjudication` 纯逻辑（Property 3：只覆盖期末+未匹配不动）。
- **后端**：无新增端点（Req4 复用现有 `refreshFromWorkpapers`），无新增后端测试；仅验收确认现有「全部刷新」覆盖 registry 映射 section（Property 6）。
- **零回归门**：D1/D2 disclosure 相关 vitest 全绿（Property 5）；`sync_from_workpaper` / `refill_sections` 契约与签名不变（Property 9）。
- **Playwright（可选\*）**：D3/D5/D6/D7 披露 tab 差异横幅渲染 + 从审定表刷新 round-trip；DisclosureEditor 批量刷新进度弹窗（需实例化项目+SSE 稳定环境，flaky 则留待，由 vitest+pytest 覆盖）。
