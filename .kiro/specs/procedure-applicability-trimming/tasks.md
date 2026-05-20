# Implementation Plan: 程序适用性裁剪 UI

## Overview

基于 requirements.md 和 design.md，将程序适用性裁剪功能拆分为 2 个 Sprint：Sprint 1 后端（router + service + RBAC + audit）、Sprint 2 前端（组件 + composable + eventBus 联动 + 集成测试）。后端使用 Python（FastAPI + hypothesis PBT），前端使用 TypeScript（Vue 3 + vitest + fast-check PBT）。

## Tasks

- [x] 1. Sprint 1 — 后端核心实现
  - [x] 1.1 创建 ProcedureTrimEngine 服务
    - 创建 `backend/app/services/procedure_trim_engine.py`
    - 实现 `ProcedureTrimEngine` 类：`trim()` / `revert()` / `get_summary()` / `get_history()` 方法
    - `trim()`: 更新 `parsed_data.procedure_status[sheet_key].{Rxx}.status = 'not_applicable'` + 写入 `parsed_data.trimming_metadata[sheet_key].{Rxx}` 元数据
    - `revert()`: 恢复 status 为 `pending` + 清除 trimming_metadata 对应条目
    - `get_summary()`: 按循环/按理由分组统计 + 裁剪率 > 50% 警告
    - `get_history()`: 从审计日志读取裁剪操作历史，支持按操作人/理由/时间范围筛选
    - 实现 `TrimReasonCode` 枚举 + `ProcedureTrimRequest` / `ProcedureTrimResponse` / `TrimSummaryResponse` / `TrimHistoryEntry` Pydantic schema
    - 幂等处理：trim 时跳过已 N/A 行，revert 时跳过非 N/A 行
    - _Requirements: 2.4, 3.3, 3.5, 4.1, 7.1, 7.2_

  - [x] 1.2 创建 wp_procedure_trim.py 路由
    - 创建 `backend/app/routers/wp_procedure_trim.py`
    - `PATCH /api/projects/{project_id}/workpapers/{wp_id}/procedure-trim` — 单行/批量裁剪 + 恢复
    - `GET /api/projects/{project_id}/workpapers/{wp_id}/procedure-trim/summary` — 裁剪汇总
    - `GET /api/projects/{project_id}/workpapers/{wp_id}/procedure-trim/history` — 操作历史
    - 使用 `Depends(require_role(["admin", "partner", "manager"]))` 守卫 PATCH 端点
    - summary 和 history 端点对所有角色可见（仅需 `get_current_user`）
    - 注册路由到 `router_registry.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.4, 4.1, 4.4, 6.3, 6.4, 8.1, 8.3_

  - [x] 1.3 集成 WpAuditTrailService 审计日志
    - 在 `ProcedureTrimEngine.trim()` 和 `revert()` 中调用 `WpAuditTrailService.log_procedure_trim`
    - 扩展 details 字段：`action_type`（trim/revert）/ `row_ids` / `reason_code` / `reason_text` / `batch_id` / `user_id` / `timestamp`
    - 确保 revert 操作不删除历史 trim 日志条目（仅追加新 revert 条目）
    - _Requirements: 4.2, 4.3, 6.1, 6.2_

  - [x] 1.4 编写后端单元测试
    - 创建 `backend/tests/test_procedure_trimming.py`
    - 测试 PATCH trim happy path（单行 + 批量）
    - 测试 PATCH revert happy path
    - 测试 RBAC 403（assistant/auditor 角色）
    - 测试 422 校验（缺 reason_code / "其他"理由 < 5 字符）
    - 测试 400（不存在的 row_id）
    - 测试幂等（重复 trim 已 N/A 行 → skipped）
    - 测试 GET summary 响应结构 + 裁剪率计算
    - 测试 GET history 响应结构 + 时间倒序
    - 测试审计日志写入完整性
    - _Requirements: 2.3, 2.4, 2.5, 3.3, 3.4, 3.5, 4.1, 4.2, 6.1, 8.1, 8.3_

  - [x] 1.5 创建 ProcedureTrimEngine 服务单元测试
    - 创建 `backend/tests/test_procedure_trim_engine.py`
    - 测试 trim 方法：状态变更 + trimming_metadata 写入
    - 测试 revert 方法：状态恢复 + metadata 清除
    - 测试 get_summary：按循环/按理由分组 + 警告阈值
    - 测试 get_history：筛选条件 + 排序
    - 测试边界条件：空 row_ids / reason_text 恰好 5 字符 / 裁剪率恰好 50%
    - _Requirements: 2.4, 3.3, 4.1, 7.1, 7.2_

- [ ] 2. Sprint 1 — 后端 PBT 属性测试
  - [ ]* 2.1 Write property test: trim-revert round trip (P1)
    - **Property 1: Trim-revert round trip**
    - 使用 hypothesis 生成任意 pending 状态程序行，执行 trim → revert，验证状态恢复为 pending 且 trimming_metadata 无残留
    - 创建 `backend/tests/test_procedure_trim_pbt.py`
    - **Validates: Requirements 2.4, 4.1**

  - [ ]* 2.2 Write property test: batch trim idempotence (P2)
    - **Property 2: Batch trim idempotence**
    - 生成混合状态行集合（部分已 N/A），执行批量 trim 两次，验证第二次全部 skipped + 零状态变更
    - **Validates: Requirements 3.3, 3.5**

  - [ ]* 2.3 Write property test: count invariant (P3)
    - **Property 3: Count invariant — trimmed + active = total**
    - 生成 N 行程序，执行任意序列 trim/revert 操作，验证 `count(not_applicable) + count(non-not_applicable) == N`
    - **Validates: Requirements 1.4, 7.1**

  - [ ]* 2.4 Write property test: batch result count conservation (P4)
    - **Property 4: Batch result count conservation**
    - 生成 K 个 row_ids 的请求，验证 `len(succeeded) + len(skipped) + len(failed) == K` 且三列表无交集无遗漏
    - **Validates: Requirements 3.4**

  - [ ]* 2.5 Write property test: audit log completeness (P6)
    - **Property 6: Audit log completeness and immutability**
    - 执行 trim 后验证审计日志新增条目含完整字段；执行 revert 后验证原 trim 日志不变 + 新增 revert 条目
    - **Validates: Requirements 4.2, 4.3, 6.1, 6.2**

  - [ ]* 2.6 Write property test: RBAC enforcement (P7)
    - **Property 7: RBAC enforcement**
    - 生成非授权角色（assistant/auditor）调用 → 403；生成授权角色（admin/partner/manager）调用 → 非 403
    - **Validates: Requirements 8.1, 8.3**

  - [ ]* 2.7 Write property test: custom reason text validation (P8)
    - **Property 8: Custom reason text validation**
    - 生成 reason_code="other" + reason_text 长度 0~100，验证 < 5 字符 → 422，≥ 5 字符 → 接受
    - **Validates: Requirements 2.3, 2.5**

  - [ ]* 2.8 Write property test: trim rate warning threshold (P9)
    - **Property 9: Trim rate warning threshold**
    - 生成各循环裁剪率 0%~100%，验证 > 50% 出现在 warnings，≤ 50% 不出现
    - **Validates: Requirements 7.2**

  - [ ]* 2.9 Write property test: history ordering (P10)
    - **Property 10: History ordering**
    - 生成多条审计日志条目，验证 history 端点返回按 created_at 降序排列
    - **Validates: Requirements 6.3**

- [ ] 3. Checkpoint — 后端测试全绿
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Sprint 2 — 前端 composable + 组件实现
  - [x] 4.1 创建 useProcedureTrimming composable
    - 创建 `audit-platform/frontend/src/composables/useProcedureTrimming.ts`
    - 实现 `useProcedureTrimming(projectId, wpId, sheetKey)` 返回 `rows` / `stats` / `loading` / `trimHistory`
    - 实现 `trimRows(rowIds, reason)` → PATCH /procedure-trim action=trim
    - 实现 `revertRows(rowIds)` → PATCH /procedure-trim action=revert
    - 实现 `fetchSummary()` → GET /procedure-trim/summary
    - 实现 `fetchHistory(filters)` → GET /procedure-trim/history
    - 操作成功后 `eventBus.emit('procedure-status:changed')` 触发 sheet 导航刷新
    - _Requirements: 2.4, 3.3, 4.1, 5.1, 5.2_

  - [x] 4.2 创建 TrimReasonDialog.vue 组件
    - 创建 `audit-platform/frontend/src/components/workpaper/TrimReasonDialog.vue`
    - 预设理由选项：无相关业务 / 风险评估为低 / 控制测试有效 / 其他
    - "其他"选项时显示文本输入框，实时校验 ≥ 5 字符
    - 未选择理由时禁用确认按钮 + 提示"请选择裁剪理由"
    - emit `confirm({ reason_code, reason_text })` / `cancel`
    - _Requirements: 2.1, 2.2, 2.3, 2.5_

  - [x] 4.3 创建 BatchTrimSelector.vue 组件
    - 创建 `audit-platform/frontend/src/components/workpaper/BatchTrimSelector.vue`
    - 三种筛选维度：按循环 / 按认定 / 按风险等级
    - 实时预览匹配程序行列表及数量
    - 选择后触发 TrimReasonDialog → 确认后调用 composable.trimRows
    - _Requirements: 3.1, 3.2_

  - [x] 4.4 创建 ProcedureTrimmingPanel.vue 主面板
    - 创建 `audit-platform/frontend/src/components/workpaper/ProcedureTrimmingPanel.vue`
    - 作为 WorkpaperAuditNav 新 tab "程序适用性"
    - 顶部统计摘要（总程序数 / 已裁剪数 / 裁剪率）
    - 程序行列表：行号 + 程序描述 + 当前状态 + N/A 标记
    - 已裁剪行：灰色背景 + "N/A" 标签 + 裁剪理由摘要
    - "标记 N/A" 按钮（manager+ 可见）→ 弹出 TrimReasonDialog
    - "恢复" 按钮（manager+ 可见）→ 直接调用 revertRows
    - RBAC：assistant/auditor 角色隐藏操作按钮（只读模式）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 4.1, 8.2_

  - [x] 4.5 创建 TrimmingSummaryPanel.vue 汇总面板
    - 创建 `audit-platform/frontend/src/components/workpaper/TrimmingSummaryPanel.vue`
    - 按循环分组裁剪数 / 按理由分组裁剪数 / 裁剪率
    - 裁剪率 > 50% 循环标记黄色警告
    - 展开查看每个被裁剪程序的详细理由和操作人
    - 操作历史列表（时间倒序）+ 筛选（按操作人/理由/时间范围）
    - 所有角色可见（只读）
    - _Requirements: 6.3, 6.4, 7.1, 7.2, 7.3, 8.4_

  - [x] 4.6 集成到 WorkpaperAuditNav + eventBus 联动
    - 在 WorkpaperAuditNav.vue 中注册"程序适用性"tab → 渲染 ProcedureTrimmingPanel
    - 确认 `eventBus.emit('procedure-status:changed')` 触发 useProcedureStatus 自动 refresh
    - 确认 sheet 导航灰显逻辑：所有关联程序行均 N/A → sheet 整体灰显；撤销后立即移除灰显
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 5. Sprint 2 — 前端测试
  - [x] 5.1 编写 useProcedureTrimming composable 测试
    - 创建 `audit-platform/frontend/src/composables/__tests__/useProcedureTrimming.spec.ts`
    - 测试 trimRows 调用 API + 更新 rows 状态 + emit eventBus
    - 测试 revertRows 调用 API + 恢复状态 + emit eventBus
    - 测试 fetchSummary / fetchHistory 响应解析
    - 测试批量操作结果摘要（succeeded/skipped/failed）
    - _Requirements: 2.4, 3.4, 5.2_

  - [x] 5.2 编写 ProcedureTrimmingPanel 组件测试
    - 创建 `audit-platform/frontend/src/components/workpaper/__tests__/ProcedureTrimmingPanel.spec.ts`
    - 测试面板渲染：统计摘要 + 程序行列表 + N/A 行灰色样式
    - 测试 RBAC 按钮显隐：manager 可见 / assistant 隐藏
    - 测试"标记 N/A"按钮点击 → 弹出 TrimReasonDialog
    - 测试"恢复"按钮点击 → 调用 revertRows
    - _Requirements: 1.1, 1.2, 1.3, 8.2_

  - [x] 5.3 编写 TrimReasonDialog 组件测试
    - 创建 `audit-platform/frontend/src/components/workpaper/__tests__/TrimReasonDialog.spec.ts`
    - 测试理由选项渲染（4 个预设选项）
    - 测试"其他"选项 → 文本输入框显示 + < 5 字符禁用确认
    - 测试未选择理由 → 确认按钮禁用
    - 测试确认 emit 正确 payload
    - _Requirements: 2.2, 2.3, 2.5_

  - [ ]* 5.4 Write property test: sheet graying iff all rows N/A (P5)
    - **Property 5: Sheet graying iff all associated rows N/A**
    - 创建 `audit-platform/frontend/src/components/workpaper/__tests__/ProcedureTrimming.pbt.spec.ts`
    - 使用 fast-check 生成 sheet 关联程序行状态组合，验证：全部 N/A → 灰显；至少一行非 N/A → 不灰显
    - **Validates: Requirements 5.1, 5.3, 5.4**

  - [ ]* 5.5 Write property test: trim rate warning threshold — frontend (P9)
    - **Property 9: Trim rate warning threshold (frontend)**
    - 在 `ProcedureTrimming.pbt.spec.ts` 中追加
    - 使用 fast-check 生成各循环裁剪率，验证 > 50% 显示黄色警告 / ≤ 50% 不显示
    - **Validates: Requirements 7.2**

- [ ] 6. Checkpoint — 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 回归验证 + 现有 procedure_status 兼容性
  - [x] 7.1 验证现有 useProcedureStatus 兼容性
    - 确认 `useProcedureStatus.markStatus` 方法与裁剪操作不冲突
    - 确认 `procedure-status:changed` 事件触发后 useProcedureStatus 正确 refresh
    - 确认已有 11 个循环的 sheet 分组逻辑不受影响
    - 运行现有 `backend/tests/test_procedure_status*.py` + `frontend/src/composables/__tests__/useProcedureStatus.spec.ts` 确认零回归
    - _Requirements: 5.2, 非功能需求-兼容性_

  - [x] 7.2 验证审计日志哈希链完整性
    - 确认裁剪/恢复操作写入 `audit_log_entries` 表后哈希链不断裂
    - 确认 `WpAuditTrailService.log_procedure_trim` 调用参数完整
    - _Requirements: 6.1, 非功能需求-可观测性_

- [x] 8. Final checkpoint — 全部测试通过 + 回归零失败
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Sprint 1（后端）预计 1 天，Sprint 2（前端+集成）预计 1 天
- 后端 PBT 使用 hypothesis（≥ 100 iterations），前端 PBT 使用 fast-check（≥ 100 iterations）
- 数据存储在 `parsed_data.trimming_metadata`（JSONB 扩展），不新增 PG 表，不需要 Alembic 迁移
- eventBus 复用现有 `procedure-status:changed` 事件，不新增事件类型
- RBAC 复用现有 `require_role` 依赖注入模式
