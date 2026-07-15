// Feature: procedure-delegation-notification / Task 15
// 程序行任务通知类型 —— 前端镜像（后端权威见
// backend/app/services/procedure_notification_types.py 的 PROCEDURE_NOTIFICATION_TYPES）。
//
// CI guard check_procedure_delegation_architecture.py 的 notification-type-sync 检查会解析
// 本文件与后端清单，两侧集合必须完全一致，否则 CI 失败（需求 13.9 / 10.8）。
// 新增通知类型时必须同时改后端 procedure_notification_types.py 与本文件。

// 与后端 PROCEDURE_NOTIFICATION_TYPES 逐项对应（顺序无关，集合必须相等）。
export const PROCEDURE_NOTIFICATION_TYPES = [
  'assigned',
  'reassigned',
  'submitted',
  'changes_requested',
  'reviewed',
  'reviewer_missing',
  'comment',
  'reply',
  'delegation_batch_summary',
] as const

export type ProcedureNotificationType = (typeof PROCEDURE_NOTIFICATION_TYPES)[number]

// NotificationCenter 展示用中文标签（深链跳转由 metadata 驱动，不从中文 content 解析路由）。
export const PROCEDURE_NOTIFICATION_LABELS: Record<ProcedureNotificationType, string> = {
  assigned: '程序任务已分配给你',
  reassigned: '程序任务已转派给你',
  submitted: '有程序任务待你复核',
  changes_requested: '程序任务被退回，请修改',
  reviewed: '程序任务已通过一级复核',
  reviewer_missing: '程序任务缺少复核人，请指派',
  comment: '程序任务有新的复核意见',
  reply: '程序任务复核意见有新回复',
  delegation_batch_summary: '批量程序任务已委派',
}
