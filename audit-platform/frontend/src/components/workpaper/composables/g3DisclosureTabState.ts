/**
 * G3 应收股利披露 Tab 的表格行 + 审计说明状态（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1）。
 *
 * 由 `G3TabDisclosureListed` / `G3TabDisclosureSOE` 原样抽出：表格存在 `G3-disclosure-{variant}-table` 的 conclusion（JSON），
 * 审计说明存在 `G3-disclosure-{variant}-text` 的 remark；首屏读一次，响应变化时重读。保存、事件、从 G3-1 带入与提示仍在 Tab。
 */
import { ref, watch, type Ref } from 'vue'
import type { ChecklistResponse } from './useF1FormData'

export type G3DisclosureTabVariant = 'listed' | 'soe'

export const G3_DISCLOSURE_ITEM_KEYS = {
  listed: { text: 'G3-disclosure-listed-text', table: 'G3-disclosure-listed-table' },
  soe: { text: 'G3-disclosure-soe-text', table: 'G3-disclosure-soe-table' },
} as const satisfies Record<G3DisclosureTabVariant, { text: string; table: string }>

/** 上市：被投资方 | 上年年末 | 本期增加 | 本期减少 | 期末 */
export interface G3ListedDisclosureRow {
  id: string
  investeeName: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
  remark: string
}

/** 国企：被投资方 | 期初 | 本期变动 | 期末 */
export interface G3SoeDisclosureRow {
  id: string
  investeeName: string
  openingBalance: number
  currentChange: number
  remark: string
}

function generateListedId(): string {
  return `dl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function generateSoeId(): string {
  return `ds-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function emptyG3ListedDisclosureRow(): G3ListedDisclosureRow {
  return { id: generateListedId(), investeeName: '', openingBalance: 0, currentIncrease: 0, currentDecrease: 0, remark: '' }
}

export function emptyG3SoeDisclosureRow(): G3SoeDisclosureRow {
  return { id: generateSoeId(), investeeName: '', openingBalance: 0, currentChange: 0, remark: '' }
}

/** 表格行：没有已存表格或解析失败 ⇒ 一行空占位（与 Tab 原 `loadTableRows` 相同） */
export function loadG3ListedDisclosureRows(raw: string | null | undefined): G3ListedDisclosureRow[] {
  if (!raw) return [emptyG3ListedDisclosureRow()]
  try {
    const parsed = JSON.parse(raw) as Partial<G3ListedDisclosureRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyG3ListedDisclosureRow()]
    return parsed.map((p) => ({ ...emptyG3ListedDisclosureRow(), ...p, id: p.id ?? generateListedId() }))
  } catch { return [emptyG3ListedDisclosureRow()] }
}

export function loadG3SoeDisclosureRows(raw: string | null | undefined): G3SoeDisclosureRow[] {
  if (!raw) return [emptyG3SoeDisclosureRow()]
  try {
    const parsed = JSON.parse(raw) as Partial<G3SoeDisclosureRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyG3SoeDisclosureRow()]
    return parsed.map((p) => ({ ...emptyG3SoeDisclosureRow(), ...p, id: p.id ?? generateSoeId() }))
  } catch { return [emptyG3SoeDisclosureRow()] }
}

type RowOf<V extends G3DisclosureTabVariant> = V extends 'listed' ? G3ListedDisclosureRow : G3SoeDisclosureRow

export interface G3DisclosureTabState<V extends G3DisclosureTabVariant> {
  noteText: Ref<string>
  tableRows: Ref<RowOf<V>[]>
}

/**
 * 审计说明：响应里有值且与当前不同才写入（立即执行一次）；表格：首屏读一次，之后已存表格变化时重读。
 * 两个 watch 与 Tab 原实现逐行相同（Tab 自己的保存 / 事件 watch 建在这之后）。
 */
export function useG3DisclosureState<V extends G3DisclosureTabVariant>(
  variant: V,
  allResponses: Ref<Map<string, ChecklistResponse>>,
): G3DisclosureTabState<V> {
  const keys = G3_DISCLOSURE_ITEM_KEYS[variant]
  const load = (variant === 'listed' ? loadG3ListedDisclosureRows : loadG3SoeDisclosureRows) as
    (raw: string | null | undefined) => RowOf<V>[]

  const noteText = ref('')
  watch(() => allResponses.value.get(keys.text)?.remark, (v) => {
    if (v && v !== noteText.value) noteText.value = v
  }, { immediate: true })

  const tableRows = ref(load(allResponses.value.get(keys.table)?.conclusion)) as Ref<RowOf<V>[]>
  watch(() => allResponses.value.get(keys.table)?.conclusion, (raw) => {
    if (raw) tableRows.value = load(raw)
  }, { immediate: false })

  return { noteText, tableRows }
}
