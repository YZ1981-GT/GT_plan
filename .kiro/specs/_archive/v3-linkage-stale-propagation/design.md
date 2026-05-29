# Spec A — Design

**版本**：v1.0
**关联**：requirements.md / tasks.md

## 变更记录

| 版本 | 日期 | 摘要 |
|------|------|------|
| v1.0 | 2026-05-16 | 初稿 |

---

## 架构决策（ADR）

### D1 — useStaleStatus 单一真源

**决策**：不为每个视图新建 stale composable，全部复用现有 `useStaleStatus(projectId)`。

**理由**：
- 现有 5 视图已稳定使用 ~3 个月
- composable 内部已订阅 `workpaper:saved` + `year:changed`
- R1 6 个新视图只需 import + onMounted 调用 `check()`

**反方案**（已否决）：每个视图各自维护 stale state——多 6 倍订阅，N+1 查询。

### D2 — stale-summary/full 端点设计为聚合 SQL

**决策**：`/stale-summary/full` 内部用 4 条聚合 SQL（每张目标表一条），不调 4 个 service。

**SQL 模板**：
```sql
-- workpapers
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE prefill_stale = true) AS stale,
  COUNT(*) FILTER (WHERE consistency_status = 'inconsistent') AS inconsistent
FROM working_paper
WHERE project_id = $1 AND is_deleted = false;

-- reports（is_stale 列已在 round8-deep-closure 加）
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE is_stale = true) AS stale
FROM financial_report
WHERE project_id = $1 AND year = $2 AND is_deleted = false;

-- notes
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE is_stale = true) AS stale
FROM disclosure_notes
WHERE project_id = $1 AND year = $2 AND is_deleted = false;

-- misstatements
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE materiality_recheck_needed = true) AS recheck_needed
FROM unadjusted_misstatements
WHERE project_id = $1 AND year = $2 AND is_deleted = false;
```

**性能预估**：4 项目 × 4 SQL ≈ 16 次查询，单次请求 < 200ms（PG 索引齐全）。

**N+1 防退化**：CI 集成测试加 `assert_query_count(<= 6)` 装饰器（4 SQL + 1 user auth + 1 dataset filter）。

### D3 — `materiality_recheck_needed` 字段已存在性核验

**决策**：先 grep 核验 `unadjusted_misstatements` 表是否已有 `materiality_recheck_needed` 列；如无，本 spec 不新建迁移，直接用 `last_evaluated_at < materiality.updated_at` 派生计算（性能可接受）。

**核验任务**：Sprint 1 Task 1.0 必做。

### D4 — PartnerSignDecision 摘要区块的位置

**决策**：摘要区块插在中栏"报告 HTML 预览"的**上方**（不是底栏），高度 ~80px，对合伙人最显眼。

**布局**：
```
左栏（GateReadinessPanel）              中栏（HTML 预览）              右栏（风险摘要）
                                       ┌──────────────────────┐
                                       │ ⚠️ 项目状态摘要         │
                                       │ [底稿3] [报表1] [附注12]│
                                       │ [错报0] [一致性4/5]   │
                                       ├──────────────────────┤
                                       │  HTML 预览内容...     │
                                       └──────────────────────┘
```

### D5 — AJE→错报转换的幂等键

**决策**：以 `adjustment.id` 为幂等键。

```
POST /api/projects/{pid}/misstatements/from-rejected-aje?adjustment_id={id}

服务端逻辑：
1. SELECT existing FROM unadjusted_misstatements WHERE source_adjustment_id = $1
2. 如果 existing：返回 409 + {error_code: "ALREADY_CONVERTED", misstatement_id: ...}
3. 否则创建并返回 201 + 新错报对象
```

**前端**：
- 收到 409 时不弹错误，转为 toast "该 AJE 已转换为错报，跳转查看？"
- 点击跳转到 Misstatements 并 setCurrentRow

### D6 — eventBus 订阅 + 防抖

**实现**：
```ts
// useStaleStatus.ts 内部
import { debounce } from 'lodash-es'  // 已是依赖

const debouncedCheck = debounce(() => check(), 500)

eventBus.on('workpaper:saved', debouncedCheck)
eventBus.on('adjustment:created', debouncedCheck)
eventBus.on('adjustment:updated', debouncedCheck)
eventBus.on('adjustment:deleted', debouncedCheck)
eventBus.on('materiality:changed', debouncedCheck)
eventBus.on('year:changed', () => { check() })  // 年度切换不防抖
eventBus.on('dataset:activated', debouncedCheck)
```

**注意**：`year:changed` 不防抖（用户切年立即看新年数据）。

### D7 — 不动现有 stale_summary 端点（向后兼容）

**决策**：现有 `/api/projects/{pid}/stale-summary`（仅底稿粒度）保留，不废弃；新建 `/stale-summary/full`（聚合多模块）。

**理由**：5 个老视图已用旧端点，改动会触碰大量代码；新视图直接接对新端点即可。

---

## 数据流图

```
User → Adjustments.vue (修改 AJE)
  ↓
POST /api/projects/{pid}/adjustments
  ↓
event_bus.publish(ADJUSTMENT_UPDATED)
  ↓
event_handler._mark_reports_stale_on_adjustment
  → UPDATE financial_report SET is_stale=true
  → UPDATE disclosure_notes SET is_stale=true
  ↓
SSE 推送 sse:sync-event → 前端
  ↓
useStaleStatus.debouncedCheck() （500ms 防抖）
  ↓
GET /api/projects/{pid}/stale-summary/full
  ↓
WorkpaperList / Misstatements / PartnerSignDecision 等 6 视图同步刷新
```

---

## 实施记录（实施完成后回填）

待实施。
