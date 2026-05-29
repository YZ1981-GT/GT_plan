# Spec A — Tasks

**版本**：v1.0
**总工时预估**：3 天（Day 6-8 of v3 第一周）
**关联**：requirements.md / design.md

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-16 | 初稿 |

---

## Sprint 0 — 现状核验（强制前置，1 小时）

- [x] 0.1 grep 核验 `working_paper.prefill_stale` / `financial_report.is_stale` / `disclosure_notes.is_stale` / `unadjusted_misstatements.materiality_recheck_needed` 4 个字段真实存在
  - 输出 `snapshot.json` 含 4 字段命中情况
  - 任一字段缺失 → 立刻退出 spec，转 P0-13 之前先补迁移
- [x] 0.2 实测 `/api/projects/{pid}/stale-summary` 4 项目响应（确认现状不影响）
- [x] 0.3 grep 当前 `useStaleStatus` 5 视图实际使用方式（避免覆盖率重复 fix）

---

## Sprint 1 — 后端聚合端点（0.5 天）

- [x] 1.1 新建 `backend/app/services/stale_summary_aggregate.py`
  - 函数 `async def get_full_summary(db, project_id, year) -> dict`
  - 内部 4 条聚合 SQL（design.md D2 给定模板）
  - 返回 `{workpapers, reports, notes, misstatements, last_event_at}`

- [x] 1.2 `backend/app/routers/stale_summary.py` 新增 `/full` 端点
  - 路由 `GET /api/projects/{pid}/stale-summary/full?year={year}`
  - 调用 `get_full_summary` 并返回

- [x] 1.3 集成测试 `backend/tests/test_stale_summary_full.py`
  - 4 项目均 200，字段齐全
  - `assert_query_count(<= 6)` 防 N+1
  - 跨年度隔离：year=2024 修改不影响 year=2025 stale

---

## Sprint 2 — 前端 useStaleStatus 推到 6 视图（1.5 天）

### 2.A WorkpaperList + WorkpaperWorkbench（0.5 天）

- [x] 2.A.1 `WorkpaperList.vue`：
  - 表格新增"新鲜度"列（width 100px）
  - 用 `useStaleStatus(projectId)` 获取 staleItems
  - 每行 `<el-tag>` 根据状态显示 ✓/🟡 stale/🔴 inconsistent

- [x] 2.A.2 `WorkpaperWorkbench.vue`：
  - 编制卡片右上角 `v-if="isWpStale"` 显示 🟡 角标
  - 点击角标显示 stale_reason tooltip

### 2.B Misstatements + Adjustments（0.5 天）

- [x] 2.B.1 `Misstatements.vue`：
  - 列表行级 `v-if="row.materiality_recheck_needed"` 显示"⚠️ 重要性已变更"标志
  - 订阅 `materiality:changed` 事件触发 debouncedCheck

- [x] 2.B.2 `Adjustments.vue`：
  - "已转错报"列右侧 stale 标志（条件：错报阈值变化时）

### 2.C PartnerSignDecision 摘要区块（0.4 天）

- [x] 2.C.1 `PartnerSignDecision.vue`：
  - 中栏头部下方插入"项目状态摘要"区块（design.md D4 布局）
  - 5 个指标卡片：底稿stale / 报表stale / 附注stale / 错报待评估 / 一致性通过数
  - 数据源：`/api/projects/{pid}/stale-summary/full` + `/workflow/consistency-check`
  - 任一指标 > 0 → 卡片橙色边框；全 0 → 显示"✅ 项目状态健康"

- [x] 2.C.2 卡片可点击跳转：
  - 底稿 → WorkpaperList?filter=stale
  - 报表 → ReportView
  - 附注 → DisclosureEditor
  - 错报 → Misstatements
  - 一致性 → 弹窗显示 5 项详情

### 2.D EqcrProjectView Tab badge（0.1 天）

- [x] 2.D.1 `EqcrProjectView.vue`：
  - 各 Tab 标题加 badge（哪些 Tab 数据 stale）
  - 利用现有 `useStaleStatus` 的 staleItems 按 Tab 类型分组

---

## Sprint 3 — useStaleStatus composable 升级 + AJE→错报（0.7 天）

### 3.A composable 订阅扩展 + 防抖（0.2 天）

- [x] 3.A.1 `useStaleStatus.ts`：
  - 新增订阅事件：`adjustment:created` / `adjustment:updated` / `adjustment:deleted` / `dataset:activated`
  - 用 `lodash-es.debounce(check, 500)` 包装
  - `year:changed` 不防抖（立即刷新）

- [x] 3.A.2 实测：1s 内连发 10 个事件，API 调用次数 ≤ 2

### 3.B AJE→错报转换前端入口（依赖 P0-1 F6）（0.5 天）

> **前置依赖**：v3-quickfixes Q1 (F6) 必须先完成，否则 R4 验收时点击"转为错报"会触发 F6 的 500。

- [x] 3.B.1 `Adjustments.vue` 表格新增条件操作：
  - `v-if="row.status === 'rejected' && !row.converted_to_misstatement_id"` 显示"📝 转为错报"按钮
  - 点击调 `POST /api/projects/{pid}/misstatements/from-rejected-aje?adjustment_id={id}`

- [x] 3.B.2 错误处理：
  - 201 → toast "已转为错报记录" + 行内标记 ✅ converted
  - 409（ALREADY_CONVERTED）→ toast "已转换过，跳转查看" + 跳转
  - 500 → handleApiError 统一处理

- [x] 3.B.3 跳转：成功后调 `router.push('/projects/{pid}/misstatements')` 并通过 `?highlight={id}` 让 Misstatements 自动 setCurrentRow

- [x] 3.B.4 后端 `misstatement_service.create_from_rejected_aje` 加幂等检查（design.md D5）：
  - 先 SELECT existing WHERE source_adjustment_id
  - 存在 → 抛 409 而非创建重复

---

## Sprint 4 — 集成测试 + 验收（0.3 天）

- [x] 4.1 `backend/tests/test_aje_to_misstatement_idempotent.py`
  - admin 角色 POST 同一 AJE 两次：第二次 409 + ALREADY_CONVERTED
  - 派生（不开启 F6）：mock svc.create_entry 返回成功后再调 from-rejected-aje

- [x] 4.2 `backend/tests/test_stale_summary_aggregate.py`
  - 修 1 张底稿 → stale_summary/full workpapers.stale = 1
  - 改重要性 → misstatements.recheck_needed = N
  - 跨年度隔离测试

- [x] 4.3 前端 vitest 单测（如已有 vitest 基建）：
  - `useStaleStatus` 防抖测试（vi.advanceTimersByTime）
  - PartnerSignDecision 摘要区块条件渲染

- [x] 4.4 全项目 E2E 验收：
  - 跑 v3 §4 实测脚本（重新写一份）
  - 4 项目 stale_summary/full 都 200
  - PartnerSignDecision 4 项目都能展示摘要

---

## UAT 验收清单（手动）

| # | 验收项 | Tester | Date | Status |
|---|--------|--------|------|--------|
| 1 | 修一张底稿 → WorkpaperList 该行立即变 🟡 stale | partner | | ○ pending |
| 2 | 修重要性 → Misstatements 出现"⚠️ 重要性已变更" | manager | | ○ pending |
| 3 | PartnerSignDecision 摘要区块全 0 时显示"✅ 项目状态健康" | partner | | ○ pending |
| 4 | 任一摘要指标 > 0 时卡片橙边 + 可点击跳转 | partner | | ○ pending |
| 5 | 拒绝 AJE → "转为错报"按钮出现 | manager | | ○ pending |
| 6 | 转换成功后跳转 Misstatements 自动定位新行 | manager | | ○ pending |
| 7 | 重复转换同一 AJE → 提示 409 而非重复创建 | auto | 2026-05-16 | ✓ pass |
| 8 | EqcrProjectView 各 Tab 标题 badge 显示正确 | eqcr | | ○ pending |
| 9 | 4 项目 `/stale-summary/full?year=2025` 全 200 + 字段完整 | auto | 2026-05-16 | ✓ pass |
| 10 | F6 修复后 AJE 创建 200（之前 500） | auto | 2026-05-16 | ✓ pass |

---

## 已知缺口与技术债

| # | 缺口 | 优先级 | 后续 spec |
|---|------|-------|-----------|
| TD-1 | useStaleStatus 5 老视图未升级到 debouncedCheck（保留兼容） | P3 | R11 评估 |
| TD-2 | stale-summary/full 没含 Adjustments 模块（adjustment.is_stale 字段未必存在） | P2 | 确认字段后补 |
| TD-3 | EqcrProjectView Tab badge 数据源粒度可能不够（只有项目级而非 Tab 级） | P2 | EQCR 独立 Sprint |

---

## 风险与依赖

| # | 风险 | 缓解 |
|---|------|------|
| RR1 | F6 不修复 → R4 整章 (3.B) 无法验收 | 先完成 v3-quickfixes Q1 才进入本 spec |
| RR2 | `materiality_recheck_needed` 字段不存在 | Sprint 0 核验，如缺则降级为派生计算 |
| RR3 | useStaleStatus 防抖 500ms 在某些 UI 场景偏慢 | 提供 `force=true` 参数可绕过 |
| RR4 | 4 条聚合 SQL 在大项目（10000+ 底稿）性能慢 | 加 PG partial index `WHERE prefill_stale=true` |
