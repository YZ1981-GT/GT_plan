/**
 * 公式推送 SSE 通知的统一纯函数（按 wp_code 通用）。
 *
 * E1 / K1 的 `e1PushNotice` / `k1PushNotice` 改为薄转发。
 * 新接入的底稿只需调用本函数，无需复制提示条逻辑。
 *
 * spec: formula-push-all-subjects-rollout · Task 13 · 需求 4.8
 */
import { isOwnedKey } from '@/generated/formulaPushOwnedKeys'

export interface FormulaPushedEvent {
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

export interface PushNotice {
  runId: string
  count: number
  itemIds: string[]
}

export interface ChecklistRow {
  item_id: string
  conclusion?: string | null
  remark?: string | null
}

/**
 * 通用推送提示条：按 wpCode 前缀过滤 changed_items 中属于该底稿的条目。
 * 只有源值阶段（source）有写入才提示。
 */
export function pushNotice(
  event: unknown,
  wpId: string,
  wpCode: string,
): PushNotice | null {
  const e = (event && typeof event === 'object' ? event : {}) as FormulaPushedEvent
  if (!wpId || e.dry_run) return null
  if (!Array.isArray(e.wp_ids) || !e.wp_ids.includes(wpId)) return null
  if (!Array.isArray(e.stages) || !e.stages.includes('source')) return null
  const prefix = `${wpCode}-`
  const itemIds = (Array.isArray(e.changed_items) ? e.changed_items : []).filter(
    (id): id is string => typeof id === 'string' && id.startsWith(prefix),
  )
  if (!itemIds.length) return null
  return { runId: String(e.run_id ?? ''), count: itemIds.length, itemIds }
}

/** 从服务端最新条目中挑出被推送改过的那些（按 item_id），供宿主替换内存。 */
export function pushedRows(
  rows: readonly ChecklistRow[],
  itemIds: readonly string[],
): ChecklistRow[] {
  const wanted = new Set(itemIds)
  return rows.filter((r) => wanted.has(r.item_id))
}
