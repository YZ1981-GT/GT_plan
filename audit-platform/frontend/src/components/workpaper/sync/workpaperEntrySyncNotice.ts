/**
 * 同步提示的兼容纯函数入口。
 *
 * 只消费后端 readiness，不再从静态 `capability=bidirectional` 推断 adapter 已注册。
 */
import type { EntrySyncReadiness } from './workpaperSyncApi'
import {
  deriveEntrySyncPresentation,
  type EntrySyncLoadState,
} from './entrySyncPresentation'

export type EntrySyncNoticeLevel = 'info' | 'not_synchronized' | 'unavailable'

export interface EntrySyncNotice {
  level: EntrySyncNoticeLevel
  label: string
  summary: string
  reason: string
}

export const ENTRY_SYNC_NOTICE_LABEL = '两侧数据未互通'
export const ENTRY_SYNC_NOTICE_SUMMARY = '结构化视图与在线编辑尚未形成已验收的双向链路'

export function entrySyncNotice(
  readiness: EntrySyncReadiness | null,
  loadState: EntrySyncLoadState = 'ready',
): EntrySyncNotice | null {
  const view = deriveEntrySyncPresentation(readiness, loadState)
  if (view.noticeKind === 'none') return null
  return {
    level: view.noticeKind === 'danger'
      ? 'unavailable'
      : view.noticeKind === 'warning'
        ? 'not_synchronized'
        : 'info',
    label: view.noticeLabel,
    summary: view.noticeSummary,
    reason: view.noticeReason,
  }
}

export default entrySyncNotice
