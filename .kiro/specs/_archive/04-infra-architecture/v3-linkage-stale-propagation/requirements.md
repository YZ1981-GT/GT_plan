# Spec A — Linkage Stale Propagation（联动 stale 推广）

**编制人**：合伙人
**日期**：2026-05-16
**关联**：v3 §6 P0-12 + P0-13 / v3 §7
**前置依赖**：v3 P0-1 (F6 修复) 必须先完成，否则 P0-13 AJE→错报转换无法验收

## 变更记录

| 版本 | 日期 | 摘要 | 触发原因 |
|------|------|------|---------|
| v1.0 | 2026-05-16 | 初稿 | v3 文档 P0-12+P0-13 落地 |

---

## 业务诉求

### 当前痛点（合伙人视角）

合伙人在 PartnerSignDecision 决策面板看不到"全项目当前 stale 状态"——不知道：
- 多少底稿因 TB 重算后未刷新（stale）
- 多少报表行因调整分录后未重算（stale）
- 多少附注节因报表变化后未刷新（stale）
- 多少错报因重要性变更后未重新评估（recheck_needed）

只能进每个模块单独查，签字时心里不踏实。

### 实测背景（v3 §7.2 实测）

`useStaleStatus` 当前只在 5 个视图接入（TrialBalance / ReportView / DisclosureEditor / AuditReportEditor / ProjectDashboard）。

**断点 6 个视图**（合伙人最敏感）：
1. WorkpaperList — 看不到"哪些底稿已 stale"
2. WorkpaperWorkbench — 编制卡片无 stale 标志
3. Misstatements — 重要性变更后无视觉提示
4. Adjustments — 错报阈值变化后无 stale 标志
5. **PartnerSignDecision** — 没有"项目状态摘要"区块（最痛）
6. EqcrProjectView — 各 Tab 无 stale badge

### AJE→错报转换前端入口缺失（v3 §7.5）

- 后端 `misstatement_service.create_from_rejected_aje` 已通
- 但 `Adjustments.vue` "已拒绝"行**没有"一键转错报"按钮**
- 合伙人 / 项目经理无法从前端走完整闭环

---

## 需求清单

### R1 — useStaleStatus 推到 6 个新视图

**优先级**：🔴 P0

**验收标准**（实测口径）：
1. WorkpaperList 表格新增"新鲜度"列：每行显示 ✓ / 🟡 stale / 🔴 inconsistent
2. WorkpaperWorkbench 编制卡片右上角显示 stale 角标
3. Misstatements 列表行级显示"重要性已变更"标志（条件：materiality.updated_at > misstatement.last_evaluated_at）
4. Adjustments "已转错报"列右侧显示 stale 标志（错报阈值变化时）
5. PartnerSignDecision 中栏新增"项目状态摘要"区块（见 R2）
6. EqcrProjectView 各 Tab 标题显示 badge（哪些 Tab 有 stale 数据）

**实测验证**：
```
1. 启动前后端
2. 修改任一底稿 → 等 1s
3. 进入 PartnerSignDecision，应看到"workpapers.stale=1"
4. 进入 WorkpaperList，对应行应显示 🟡 stale
5. 调 chain 刷新 → 各视图 stale 归 0
```

### R2 — 后端补齐 stale-summary/full 聚合端点

**优先级**：🔴 P0

**端点契约**：
```
GET /api/projects/{pid}/stale-summary/full?year=2025

Response 200:
{
  "workpapers": { "total": 92, "stale": 3, "inconsistent": 0, "items": [...] },
  "reports":    { "total": 6,  "stale": 1, "items": [...] },
  "notes":      { "total": 173, "stale": 12, "items": [...] },
  "misstatements": { "total": 0, "recheck_needed": 0, "items": [...] },
  "last_event_at": "2026-05-16T14:23:00Z"
}
```

**验收**：
- 4 项目实测响应 < 500ms
- 所有 N+1 查询用聚合 SQL 替代（CI 加 `assert_query_count` 装饰器）
- 字段命名与 v3 §7.4 一致

### R3 — PartnerSignDecision stale 摘要区块

**优先级**：🔴 P0

**UI 规约**：
- 中栏头部下方新增"项目状态摘要"区块（约 80px 高）
- 5 个指标卡片横排：底稿stale / 报表stale / 附注stale / 错报待评估 / 一致性5项中通过数
- 每个卡片可点击跳转对应模块
- 任一指标 > 0 时卡片显示橙色边框；全部 0 时绿色

**验收**：
- 实测 4 项目，PartnerSignDecision 顶部能正确展示摘要
- 点击"底稿 stale: 3" 跳到 WorkpaperList 并自动筛选 stale 行
- 全部 stale 归 0 时显示"✅ 项目状态健康，可进入签字流程"

### R4 — AJE→错报转换前端入口（依赖 P0-1 F6 修复）

**优先级**：🟡 P1（依赖 F6）

**UI 规约**：
- `Adjustments.vue` 表格新增条件操作：当 `row.status === 'rejected' && !row.converted_to_misstatement_id` 时，操作列显示"📝 转为错报"按钮
- 点击调 `POST /api/projects/{pid}/misstatements/from-rejected-aje?adjustment_id={id}`
- 成功后：
  - toast "已转为错报记录"
  - 行内标记 ✅ converted
  - 提供"查看错报详情"按钮跳转 Misstatements

**验收**：
- 创建一笔 AJE → 项目经理拒绝 → 列表行出现"📝 转为错报"按钮
- 点击转换 → 成功 → Misstatements 列表新增对应行
- 同一笔 AJE 不能重复转（按钮 disabled）

### R5 — eventBus 订阅链补全

**优先级**：🟡 P1

**改动**：
- `useStaleStatus` composable 自动订阅 6 个事件（`workpaper:saved` / `materiality:changed` / `year:changed` / `adjustment:created` / `report:regenerated` / `dataset:activated`）
- 6 个新视图 `onMounted` 时不需要重复订阅，由 `useStaleStatus` 内部处理
- 防抖 500ms（避免连续 5 个事件触发 5 次 API）

---

## Property（属性测试）

| # | Property | 覆盖测试 |
|---|----------|---------|
| P1 | useStaleStatus 在 6 视图都能正确反映 stale 状态 | E2E：修改底稿 → 6 视图 stale 都更新 |
| P2 | stale-summary/full 端点 N+1 查询数 ≤ 4 | pytest + assert_query_count |
| P3 | AJE→错报转换的幂等性 | 重复 POST 同一 AJE 应 409 而非创建重复错报 |
| P4 | event 防抖正确性 | 1s 内连发 10 次事件，API 调用次数 ≤ 2 |
| P5 | 跨年度隔离 | year=2024 改动不污染 year=2025 stale 状态 |

---

## 不做清单

- ❌ 不在 stale-summary/full 加细节展开（点击跳转到对应模块即可）
- ❌ 不实现 stale 状态推送（保持轮询/事件驱动模式）
- ❌ 不动 useStaleStatus 已有的 5 视图（向后兼容）
