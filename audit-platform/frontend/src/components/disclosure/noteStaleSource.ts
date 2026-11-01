/**
 * 附注过期来源的中文展示口径。
 *
 * 存储编码与后端 ``app.services.stale_state.StaleSource`` 同源；
 * ``noteStaleSource.spec.ts`` 逐成员对拍，任一侧新增/改名未同步都会打红。
 */
export const NOTE_STALE_SOURCE_LABELS = {
  workpaper_saved: '底稿已保存',
  report: '报表已变化',
  report_fallback: '报表变化（未定位具体行）',
  disclosure_refresh_no_data: '附注刷新时缺少数据',
  consol_child_changed: '合并子企业附注已变化',
  rollback: '账套已回滚',
  adjustment: '调整分录已变化',
  adjustment_review_revoked: '调整分录复核已撤回',
  adjustment_batch_committed: '调整分录批量提交',
  ledger_activated: '账套已激活',
  workpaper_reviewed: '底稿复核已通过',
  formula_settings: '公式设置已变化',
  trial_balance: '试算表已变化',
  formula_push: '公式推送已完成',
  workpaper_sync: '底稿数据已同步',
  linkage_propagation: '依赖链数据已变化',
} as const satisfies Record<string, string>

export type NoteStaleSource = keyof typeof NOTE_STALE_SOURCE_LABELS

export function noteStaleSourceLabel(source: string | null | undefined): string {
  const normalized = String(source ?? '').trim()
  if (!normalized) return '来源未记录'
  return NOTE_STALE_SOURCE_LABELS[normalized as NoteStaleSource] ?? '其他数据变化'
}

export function noteStaleSourceTip(source: string | null | undefined): string {
  const label = noteStaleSourceLabel(source)
  if (!String(source ?? '').trim()) return `过期（${label}）`
  if (source === 'report') return '报表中与本章节存在关联关系的行次发生变更，建议刷新本章节'
  if (source === 'report_fallback') return '报表发生变更（本项目暂无逐章节关联关系，故整体提示）'
  return `${label}，建议刷新本章节`
}
