/**
 * 调整分录组定位（spec wp-deeplink-locate-residual-closure 需求 1.2）。
 *
 * 调整分录页「底稿 X」跳来源底稿带 `?sheet=@adjustment&highlight=<source_ref>`，source_ref 形如 `{wp_id}:{item_id}`
 * （后端 `AdjustmentSyncService.build_source_ref`）。item_id 是来源页签分录组的幂等键：81 个循环调整分录页签都经
 * `useAdjustmentCentralSync` 汇聚，页签挂载时在这里登记、卸载时注销；渲染器切到调整分录表后按 item_id 问一遍，
 * 认领的页签自己切到对应类型（AJE / RJE）并高亮分录表。
 */

/** 认领：item_id 是本页签的分录组则定位并返回 true */
export type AdjustmentEntryGroupLocator = (itemId: string) => boolean

interface Registration {
  wpId: () => string
  locate: AdjustmentEntryGroupLocator
}

const registrations = new Set<Registration>()

/** 页签挂载时登记（wpId 取值函数：页签换底稿时按当时的值认）；返回注销函数 */
export function registerAdjustmentEntryGroup(wpId: () => string, locate: AdjustmentEntryGroupLocator): () => void {
  const entry: Registration = { wpId, locate }
  registrations.add(entry)
  return () => { registrations.delete(entry) }
}

/** 依次问本底稿已登记的页签，有一个认领即 true（同一 item_id 只会有一个页签认领） */
export function locateAdjustmentEntryGroup(wpId: string, itemId: string): boolean {
  if (!wpId || !itemId) return false
  for (const entry of [...registrations]) {
    if (entry.wpId() !== wpId) continue
    if (entry.locate(itemId)) return true
  }
  return false
}

/**
 * 从 `?highlight=` 取本底稿的分录组 item_id：按第一个冒号拆 source_ref，wp_id 等于当前底稿才返回，
 * 否则 null（别的页面带来的 highlight 不误用）。
 */
export function entryGroupOfHighlight(highlight: unknown, wpId: string): string | null {
  const raw = Array.isArray(highlight) ? highlight[0] : highlight
  if (typeof raw !== 'string' || !wpId) return null
  const cut = raw.indexOf(':')
  if (cut <= 0) return null
  const itemId = raw.slice(cut + 1).trim()
  return raw.slice(0, cut).trim() === wpId && itemId ? itemId : null
}

/** 已登记的页签数（测试用） */
export function adjustmentEntryGroupRegistrationCount(): number {
  return registrations.size
}
