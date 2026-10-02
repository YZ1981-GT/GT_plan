/**
 * useB22CSyncMode — B22C 设计有效性评价的在线编辑接桥。
 *
 * spec: b-class-shared-base-carrier-lanes · Task 2
 * 复用 useB22BSyncMode 结构（entryId/sheetKey 不同）。
 */
import { useB22BSyncMode, type UseB22BSyncModeOptions } from './useB22BSyncMode'
import type { Ref } from 'vue'
import type { WorkpaperSyncFlushResult } from '../sync/useWorkpaperSyncBridge'

export const B22C_ENTRY_ID = 'xlsx/gt-b22-c-design-effectiveness'
export const B22C_SHEET_KEY = 'b22c-managed'

export function useB22CSyncMode(options: {
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly isReadonly: Ref<boolean>
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
}) {
  return useB22BSyncMode({
    entryId: B22C_ENTRY_ID,
    sheetKey: B22C_SHEET_KEY,
    ...options,
  })
}
