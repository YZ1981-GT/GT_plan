# ADR-CONSOL-303: 自动建树用 EventBus 解耦 + 手动刷新兜底

## 状态
已接受 (2026-05-31)

## 背景

`consol_scope` 增删子公司后，合并模块企业树应自动更新；但强耦合"增删即同步重建"会拖慢 scope 操作，且无法覆盖 wizard 配置合并范围这一新入口。

## 决策

- 新增 `EventType.CONSOL_SCOPE_CHANGED = "consol.scope_changed"`。
- `consol_scope_service` 在 create/update/delete/batch 后调 `_emit_scope_changed(project_id, year)` → `event_bus.broadcast_raw("consol.scope_changed", {...})`（轻量 SSE，无 event loop 时静默回退 logger，不阻断业务）。
- wizard `report_scope=consolidated` 完成弹"配置合并范围"步骤（`ConsolScopeConfigDialog`），选已有单体项目挂子公司 → `POST /api/projects/{id}/attach-subsidiaries`（设 `parent_project_id` + `consol_level`）→ 同样广播 `CONSOL_SCOPE_CHANGED`。
- 前端 `ConsolidationIndex` 经 `useProjectEvents().onAnyEvent` 监听 → 自动 `refreshGroupTree()`。
- **手动"🔄 刷新树"按钮兜底**（EH4）：事件丢失时用户可手动触发，树不会永久过期。

## 后果

- 正向：解耦 + scope 操作不被重建拖慢 + 多入口（scope CRUD / wizard attach）统一触发；wizard 改动仅影响 `report_scope=consolidated`，非合并项目流程不变（R3）。
- 代价：最终一致（事件异步）+ 需手动刷新兜底按钮。
- 守护：T4 事件发射单测（4 测试）验证 broadcast_raw 调用 + 异常静默回退。
