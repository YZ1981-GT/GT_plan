// broadcast_raw 事件不在 typed `audit:events` replay 流里。
//
// 本清单与 backend/app/services/event_bus.py::RAW_EVENT_REPLAY_DEGRADED 同名，契约测试逐值对拍。
// 项目事件流完成 typed replay barrier 后会发 `transport.recovered`，并调用各订阅者的 onReconnect：
// * 能安全整页/整域重拉的消费者在 onReconnect 全量刷新；
// * 进度类消费者已有状态轮询兜底；
// * 没有安全自动覆盖路径（例如用户正在编辑的 formula.pushed）只提示/按页面重新进入恢复。
//
// 清单存在的目的不是把 raw 事件冒充成可重放事件，而是让新增 raw 事件必须显式登记降级。
export const RAW_EVENT_REPLAY_DEGRADED = [
  'ANNOTATION_CREATED',
  'ANNOTATION_UPDATED',
  'PROCEDURE_REVIEW_MESSAGE',
  'REVIEW_MESSAGE',
  'a13_summary_updated',
  'acnr:invalidate',
  'adjustment:review-changed',
  'adjustment:sync-arrived',
  'aging-config:changed',
  'attachment.uploaded',
  'consol.note_mapping_confirmed',
  'consol.note_stale',
  'consol.scope_changed',
  'consol.pushed',
  'consol.push_failed',
  'consol.push_stale',
  'consol.refresh.progress',
  'consol.refresh.completed',
  'consol.refresh.error',
  'cross_module_conflict.enqueued',
  'cross_ref.updated',
  'deliverable.package.complete',
  'deliverable.package.progress',
  'disclosure:note-text-updated',
  'editing_lock.force_acquired',
  'export.complete',
  'export.failed',
  'export.progress',
  'formula.pushed',
  'note.synced',
  'procedure_task.event',
  'report.stale',
  'review_message.created',
  'review_submitted',
  'signing_progress_updated',
  'sync.completed',
  'workpaper.assigned',
] as const

export const RAW_EVENT_REPLAY_DEGRADED_PREFIXES = ['formula_runtime.'] as const
export const PROJECT_TRANSPORT_RECOVERED_EVENT = 'transport.recovered'

export interface ProjectTransportRecovered {
  event_type: typeof PROJECT_TRANSPORT_RECOVERED_EVENT
  project_id: string
  /** typed replay 已完成（可能没有 anchor，见 replay_attempted）。 */
  typed_replay_complete: true
  replay_attempted: boolean
  replay_failed: boolean
  replay_truncated: boolean
  /** raw 事件没有同一 replay 流，相关消费者必须全量刷新或靠状态轮询。 */
  raw_full_refresh_required: true
  raw_events_without_replay: readonly string[]
}

/** 当前前端实际消费的 raw 事件族及恢复机制。新增消费方必须登记，不得默认声称 replay。 */
export const RAW_CONSUMER_RECOVERY = {
  'acnr:invalidate': 'on_reconnect_cache_clear',
  'adjustment:review-changed': 'on_reconnect_full_refresh',
  'adjustment:sync-arrived': 'on_reconnect_full_refresh',
  'attachment.uploaded': 'on_reconnect_full_refresh',
  'consol.pushed': 'on_reconnect_full_refresh',
  'consol.push_failed': 'on_reconnect_full_refresh',
  'consol.push_stale': 'on_reconnect_full_refresh',
  'consol.refresh.*': 'status_poll',
  'formula.pushed': 'manual_dirty_safe_reload',
  'LINKAGE_STALE_CHANGED': 'on_reconnect_full_refresh',
  'workpaper.content.updated': 'typed_replay',
} as const
