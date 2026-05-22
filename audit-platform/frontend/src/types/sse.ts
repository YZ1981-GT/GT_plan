/**
 * SSE 事件类型联合类型 — 镜像后端 EventType 枚举
 *
 * 后端真源：backend/app/models/audit_platform_schemas.py → class EventType(str, Enum)
 * 格式：domain.action
 *
 * 当后端新增 EventType 枚举值时，需同步更新此文件。
 * CI 中 vue-tsc 编译检查可确保前后端同步。
 */
export type SSEEventType =
  // 调整分录
  | 'adjustment.created'
  | 'adjustment.updated'
  | 'adjustment.deleted'
  // 科目映射
  | 'mapping.changed'
  // 数据导入
  | 'data.imported'
  | 'import.rolled_back'
  | 'import.progress'
  // 重要性水平
  | 'materiality.changed'
  // 试算平衡表
  | 'trial_balance.updated'
  // 报表
  | 'reports.updated'
  // 底稿
  | 'workpaper.saved'
  // 附注
  | 'note.updated'
  // 复核
  | 'review_record.created'
  // 总账导入（Phase 17 细化）
  | 'ledger.import_detected'
  | 'ledger.import_submitted'
  | 'ledger.import_failed'
  | 'ledger.dataset_validated'
  | 'ledger.dataset_activated'
  | 'ledger.dataset_rolled_back'
  // 事件链路失败（Phase 18）
  | 'sync.failed'
  // 底稿委派
  | 'workpaper.assigned'
  // Presence 事件（Enterprise Linkage）
  | 'presence.joined'
  | 'presence.left'
  | 'presence.editing_started'
  | 'presence.editing_stopped'
  // 批量提交 + 级联降级（Enterprise Linkage）
  | 'adjustment.batch_committed'
  | 'linkage.cascade_degraded'
  // 底稿深度优化事件（Sprint 10）
  | 'workpaper.audited_confirmed'
  | 'workpaper.procedure_completed'
  | 'workpaper.review_passed'
  | 'workpaper.stale_detected'
  | 'cross_check.failed'
  // Phase 7 F11: 复核进度实时通知
  | 'review.accepted'
  | 'review.completed'
