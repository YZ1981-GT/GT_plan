/**
 * E1 宿主收到 SSE `formula.pushed` 后的处理（纯函数）。
 *
 * spec: chain-closure-phase2-formula-push-engine · 需求 4.7 · design §十二 风险 1
 *
 * - 只认本底稿：`wp_ids` 含当前 wpId，且 `dry_run` 为假；
 * - 只有**源值阶段**有写入（四表明细行 / 试算平衡表数 / 大厅已确认调整）才提示用户：
 *   派生值（汇总键 / 审定合计 / 语义槽）前端本就实时同式计算，静默更新不打扰；
 * - 「载入最新数据」只替换后台改过的条目（`changed_items`），SHALL NOT 静默替换用户未保存的编辑 ——
 *   由用户点按钮触发，按钮之前只显示提示条。
 */
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

export interface E1PushNotice {
  runId: string
  count: number
  itemIds: string[]
}

/** 本底稿需要提示的推送；不需要提示返回 null。 */
export function e1PushNotice(event: unknown, wpId: string): E1PushNotice | null {
  const e = (event && typeof event === 'object' ? event : {}) as FormulaPushedEvent
  if (!wpId || e.dry_run) return null
  if (!Array.isArray(e.wp_ids) || !e.wp_ids.includes(wpId)) return null
  if (!Array.isArray(e.stages) || !e.stages.includes('source')) return null
  const itemIds = (Array.isArray(e.changed_items) ? e.changed_items : []).filter(
    (id): id is string => typeof id === 'string' && id.startsWith('E1-'),
  )
  if (!itemIds.length) return null
  return { runId: String(e.run_id ?? ''), count: itemIds.length, itemIds }
}

export interface ChecklistRow {
  item_id: string
  conclusion?: string | null
  remark?: string | null
}

/** 从服务端最新条目中挑出被推送改过的那些（按 item_id），供宿主替换内存。 */
export function e1PushedRows(rows: readonly ChecklistRow[], itemIds: readonly string[]): ChecklistRow[] {
  const wanted = new Set(itemIds)
  return rows.filter((r) => wanted.has(r.item_id))
}
