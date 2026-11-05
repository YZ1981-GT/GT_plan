import { isK1BackendOwnedKey } from './k1BackendOwnedKeys'
/**
 * K1 宿主收到 SSE `formula.pushed` 后的纯函数处理。
 *
 * 只对当前底稿、真实运行、源值阶段且实际改到 K1 后端独占键的事件显示提示。
 * 派生键同样列入 changed_items，便于用户一次载入完整的 K1 系统值集合。
 *
 * spec: chain-closure-phase3-push-rollout · design §六 · 需求 6.3
 */
export interface K1FormulaPushedEvent {
  project_id?: string
  year?: number
  run_id?: string | null
  dry_run?: boolean
  wp_ids?: string[]
  changed_items?: string[]
  stages?: string[]
  written_count?: number
  trigger?: string
}

export interface K1PushNotice {
  runId: string
  count: number
  itemIds: string[]
}

export interface ChecklistRow {
  item_id: string
  conclusion?: string | null
  remark?: string | null
}

export function k1PushNotice(event: unknown, wpId: string): K1PushNotice | null {
  const e = (event && typeof event === 'object' ? event : {}) as K1FormulaPushedEvent
  if (!wpId || e.dry_run) return null
  if (!Array.isArray(e.wp_ids) || !e.wp_ids.includes(wpId)) return null
  if (!Array.isArray(e.stages) || !e.stages.includes('source')) return null
  const itemIds = (Array.isArray(e.changed_items) ? e.changed_items : []).filter(
    (id): id is string => typeof id === 'string' && isK1BackendOwnedKey(id),
  )
  if (!itemIds.length) return null
  return { runId: String(e.run_id ?? ''), count: itemIds.length, itemIds }
}

/** 只挑出服务端返回的、被本次推送改过的行。 */
export function k1PushedRows(
  rows: readonly ChecklistRow[],
  itemIds: readonly string[],
): ChecklistRow[] {
  const wanted = new Set(itemIds)
  return rows.filter((row) => wanted.has(row.item_id))
}

/**
 * 交给共享持久化层 `reloadItems` 的 key 清单（去重、去空）。
 *
 * 🔴 读路径收口后宿主不再自己发请求，所以「只要这几条」这件事要在交给持久化层之前表达清楚：
 * 这个函数就是 `k1PushedRows` 的对偶 —— 前者过滤服务端返回的行，后者过滤要问服务端的 key。
 */
export function k1PushedItemIds(itemIds: readonly string[]): string[] {
  return [...new Set(itemIds.filter((id) => typeof id === 'string' && id))]
}
