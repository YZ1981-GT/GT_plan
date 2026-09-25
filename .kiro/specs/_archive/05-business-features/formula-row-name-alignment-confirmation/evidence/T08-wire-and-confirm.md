# Task 8 — 批量确认事务 + 刷新链返回 match_state

产物：
- wire 编排 `backend/app/services/row_name_alignment_wire.py`
- 端点扩展 `backend/app/routers/wp_render_config.py`（追加两个底稿级端点）
- 守卫 `backend/tests/four_table/test_row_name_alignment_wire.py`（4 passed）

## 扩展既有链，不新建平行刷新端点

既有底稿级刷新 = `POST /{wp_id}/audit-sheet-refresh`（`refresh_audit_sheet_from_ledger`，编辑权门禁）。
本 spec 在**同一 router**（`wp_render_config.py`，已注册 + 走 dedicated_wp_gate）补两个端点，
是刷新链在「名称维度」的可见化 + 裁决入口，非平行刷新端点（不产报表、不改取数口径）：

1. `POST /{wp_id}/row-name-alignment`（只读）：逐行 match_state + 候选 + 映射来源
2. `POST /{wp_id}/row-name-mapping/confirm`（写，单事务）：批量确认

## 固定 wire 字段（design §后端 3）

`build_alignment_wire` 逐行返回固定 11 字段，守卫 `_WIRE_FIELDS` 断言字段集完全一致：
```
row_key / match_state / candidates[] / target_identity / amount /
similarity / source_kind / confirmed_by / confirmed_at / mapping_version / stale_reason
```
顶层还返回 `unmatched_count` + `has_pending`（前端据此决定是否弹窗）。

## 确认端点事务语义（Requirement 3.6）

- router 层 commit / rollback（service 只 flush，工程铁律）
- 版本冲突 → `MappingConflictError` → HTTP **409** + `{row_key, expected_base_version, current_active_version}`
- 空目标 → `ValueError` → HTTP **422**
- 幂等：`idempotency_key` 重复 → service 层短路返回第一次结果
- 全回滚：service 先全校验再全写，任一行冲突即抛 → 无部分写

## Property 5（确认映射复用不弹窗，Requirement 3.3）

守卫 `test_wire_user_confirmed_not_pending`：已确认且候选身份仍在 → `user_confirmed`，
`has_pending=false`（不触发弹窗），且 amount = 目标身份金额之和。
`test_wire_stale_mapping_falls_back_unmatched`：dataset 变 → stale ⇒ unmatched + stale_reason，计入 pending。

## 🔴 additive 反模式自查（待 Task 9/10 闭合）

新增 wire 字段的**唯一前端消费方** = `GtRowNameAlignmentDialog.vue`（Task 9）+ 行内标识（Task 10）。
本 Task 完成时前端尚未接线 ⇒ 字段状态为「已定义待接线」，**Task 9/10 完成后即闭合**（非永久死代码）。
两个端点亦待 Task 11 的刷新入口触发。此依赖已登记，收口（Task 15）核验消费方存在。

## 守卫覆盖（4 passed）

- 零候选 → unmatched + wire 字段集完全一致
- 唯一精确 → auto_matched 携带金额 + source_kind=auto
- 已确认未失效 → user_confirmed 不 pending + 映射来源（version/confirmed_by/target_identity）
- stale → unmatched + stale_reason + amount None
