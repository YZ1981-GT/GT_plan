/**
 * Entry capability 现算（前端）—— 只读 source-backed manifest，禁止宿主内联字面量。
 *
 * HOST-CONSUMES-UNIFIED-PATH 谓词 8：能力开关来自服务端/裁决产物现算，
 * 不得像 legacy `d2_sync_status.bidirectional: True` 那样在宿主硬编码。
 */
import {
  WORKPAPER_SYNC_MANIFEST,
  type WorkpaperSyncCapability,
} from './workpaperSyncManifest.generated'

const BY_ID: ReadonlyMap<string, WorkpaperSyncCapability | null> = new Map(
  WORKPAPER_SYNC_MANIFEST.map((e) => [e.entryId, e.capability]),
)

/**
 * @returns manifest 登记的终态 capability；entry 未登记或仍待裁决时 fail-closed 为
 *          `unreachable`（与后端「pending 不得进入双向动作」同口径）。
 */
export function capabilityForEntry(entryId: string): WorkpaperSyncCapability {
  const found = BY_ID.get(String(entryId))
  if (found == null) return 'unreachable'
  return found
}
