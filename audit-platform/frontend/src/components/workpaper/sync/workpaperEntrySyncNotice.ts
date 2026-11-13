/**
 * 同步提示的兼容纯函数入口。
 *
 * 只消费后端 readiness，不再从静态 `capability=bidirectional` 推断 adapter 已注册。
 *
 * 🔴 现状（`eaa655686` 之后）：**生产侧 0 个调用方**。活路径是
 * `GtEntrySyncCapabilityNotice.vue` → `useEntrySyncReadiness` →
 * `deriveEntrySyncPresentation`；本文件只剩兼容面，由自己的 spec 覆盖。
 * 文件保留是因为 `workpaper_sync_abcs_cycle_deletion_plan.json` 的 `must_not_delete`
 * 把它列为「AC 1.4 文案的单一真源」⇒ 冻结计划明令不得删除。
 * 但文案**声明点**已随活路径搬到 `entrySyncPresentation.ts`，这里只做再导出 ——
 * 兼容面与用户真正看到的文案由同一个绑定保证，不会各自漂移。
 */
import type { EntrySyncReadiness } from './workpaperSyncApi'
import {
  deriveEntrySyncPresentation,
  type EntrySyncLoadState,
} from './entrySyncPresentation'

export {
  ENTRY_SYNC_NOTICE_LABEL,
  ENTRY_SYNC_NOTICE_SUMMARY,
} from './entrySyncPresentation'

export type EntrySyncNoticeLevel = 'info' | 'not_synchronized' | 'unavailable'

export interface EntrySyncNotice {
  level: EntrySyncNoticeLevel
  label: string
  summary: string
  reason: string
}

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
