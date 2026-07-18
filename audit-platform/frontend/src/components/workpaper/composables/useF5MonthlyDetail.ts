/**
 * useF5MonthlyDetail — F5-2 主营业务成本月度明细表
 *
 * 源表逻辑：
 *  品种动态行 × (1~12月 + 本期未审/调整/审定 + 上期未审/调整/审定 + 未审/审定变动比例 + 备注)
 *  本期未审 = SUM(1~12月)；本期审定 = 未审 + 账项调整 + 重分类
 *  上期审定 = 上期未审 + 账项调整 + 重分类
 *  合计行纵向 SUM；比例行 = 各月合计 / 本期未审合计
 *  与 F5-1 联动：品种全年未审/上期未审可供审定表引用
 */
import { computed, ref, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcAdjustedAmount,
  calcChangeRate,
} from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5MonthlyDetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface MonthlyDetailRow {
  id: string
  product: string
  months: number[]
  /** 本期未审数 = Σ月度 */
  currentUnaudited: number
  currentAje: number
  currentRje: number
  /** 本期审定 = 未审 + AJE + RJE */
  currentAudited: number
  priorUnaudited: number
  priorAje: number
  priorRje: number
  priorAudited: number
  /** 未审变动比例% */
  unauditedChangeRate: number | 'N/A'
  /** 审定变动比例% */
  auditedChangeRate: number | 'N/A'
  remark: string
}

interface StoredMonthlyRow {
  id: string
  product: string
  months: number[]
  currentAje: number
  currentRje: number
  priorUnaudited: number
  priorAje: number
  priorRje: number
  remark: string
}

export interface MonthlyTotalRow {
  months: number[]
  currentUnaudited: number
  currentAje: number
  currentRje: number
  currentAudited: number
  priorUnaudited: number
  priorAje: number
  priorRje: number
  priorAudited: number
  unauditedChangeRate: number | 'N/A'
  auditedChangeRate: number | 'N/A'
}

/** 各月占本期未审合计的比例（源表「比例」行） */
export interface MonthlyRatioRow {
  months: Array<number | 'N/A'>
  currentUnaudited: number | 'N/A'
}

const STORAGE_KEY = 'F5-2-monthly-rows'
const LEGACY_STORAGE_KEY = 'F5-2-rows'
const NOTE_KEY = 'F5-2-audit-note'
const CONCLUSION_KEY = 'F5-2-audit-conclusion'
/** 变动比例绝对值超过此阈值标黄（与审定表口径一致） */
export const F5_MONTHLY_CHANGE_RATE_THRESHOLD = 30

const MONTH_LABELS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'] as const
export { MONTH_LABELS }

function emptyMonths(): number[] {
  return new Array(12).fill(0)
}

function normalizeMonths(raw: unknown): number[] {
  if (Array.isArray(raw)) {
    return [...raw.map(parseNum), ...emptyMonths()].slice(0, 12)
  }
  // 旧宽表 m1..m12
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>
    return Array.from({ length: 12 }, (_, i) => parseNum(obj[`m${i + 1}`] ?? obj[`month${i + 1}`]))
  }
  return emptyMonths()
}

export function emptyF5MonthlyRow(product = ''): StoredMonthlyRow {
  return {
    id: `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    product,
    months: emptyMonths(),
    currentAje: 0,
    currentRje: 0,
    priorUnaudited: 0,
    priorAje: 0,
    priorRje: 0,
    remark: '',
  }
}

export function migrateF5MonthlyRows(jsonStr: string | null | undefined): StoredMonthlyRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => {
      let months = emptyMonths()
      if (Array.isArray(r?.months)) {
        months = normalizeMonths(r.months)
      } else {
        months = Array.from({ length: 12 }, (_, mi) =>
          parseNum(r?.[`m${mi + 1}`] ?? r?.[`month${mi + 1}`]),
        )
      }
      return {
        id: String(r?.id ?? r?.rowId ?? `m-${Date.now()}-${i}`),
        product: String(r?.product ?? r?.variety ?? r?.label ?? ''),
        months,
        currentAje: parseNum(r?.currentAje),
        currentRje: parseNum(r?.currentRje),
        priorUnaudited: parseNum(r?.priorUnaudited ?? r?.priorYearTotal ?? r?.priorTotal),
        priorAje: parseNum(r?.priorAje),
        priorRje: parseNum(r?.priorRje),
        remark: String(r?.remark ?? ''),
      }
    })
  } catch {
    return []
  }
}

export function computeF5MonthlyRow(stored: StoredMonthlyRow): MonthlyDetailRow {
  const months = normalizeMonths(stored.months)
  const currentUnaudited = calcSubtotal(months)
  const currentAudited = calcAdjustedAmount(currentUnaudited, stored.currentAje, stored.currentRje)
  const priorAudited = calcAdjustedAmount(stored.priorUnaudited, stored.priorAje, stored.priorRje)
  return {
    id: stored.id,
    product: stored.product,
    months,
    currentUnaudited,
    currentAje: stored.currentAje,
    currentRje: stored.currentRje,
    currentAudited,
    priorUnaudited: stored.priorUnaudited,
    priorAje: stored.priorAje,
    priorRje: stored.priorRje,
    priorAudited,
    unauditedChangeRate: calcChangeRate(currentUnaudited, stored.priorUnaudited),
    auditedChangeRate: calcChangeRate(currentAudited, priorAudited),
    remark: stored.remark,
  }
}

export function buildF5MonthlyTotal(rows: MonthlyDetailRow[]): MonthlyTotalRow {
  const months = emptyMonths()
  let currentAje = 0
  let currentRje = 0
  let priorUnaudited = 0
  let priorAje = 0
  let priorRje = 0
  for (const row of rows) {
    for (let i = 0; i < 12; i++) months[i] += row.months[i] || 0
    currentAje += row.currentAje
    currentRje += row.currentRje
    priorUnaudited += row.priorUnaudited
    priorAje += row.priorAje
    priorRje += row.priorRje
  }
  const currentUnaudited = calcSubtotal(months)
  const currentAudited = calcAdjustedAmount(currentUnaudited, currentAje, currentRje)
  const priorAudited = calcAdjustedAmount(priorUnaudited, priorAje, priorRje)
  return {
    months,
    currentUnaudited,
    currentAje,
    currentRje,
    currentAudited,
    priorUnaudited,
    priorAje,
    priorRje,
    priorAudited,
    unauditedChangeRate: calcChangeRate(currentUnaudited, priorUnaudited),
    auditedChangeRate: calcChangeRate(currentAudited, priorAudited),
  }
}

export function buildF5MonthlyRatioRow(total: MonthlyTotalRow): MonthlyRatioRow {
  const base = total.currentUnaudited
  return {
    months: total.months.map((m) => (base === 0 ? 'N/A' as const : (m / base) * 100)),
    currentUnaudited: base === 0 ? 'N/A' : 100,
  }
}

export function useF5MonthlyDetail(options: UseF5MonthlyDetailOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedRows = ref<StoredMonthlyRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawJson(): string | null | undefined {
    return allResponses.value.get(STORAGE_KEY)?.remark
      ?? allResponses.value.get(LEGACY_STORAGE_KEY)?.remark
  }

  function loadRows(): void {
    const migrated = migrateF5MonthlyRows(rawJson())
    storedRows.value = migrated.length
      ? migrated
      : [emptyF5MonthlyRow('品种1'), emptyF5MonthlyRow('品种2'), emptyF5MonthlyRow('品种3')]
  }

  watch(() => rawJson(), (raw) => {
    if (raw && (raw === lastPersisted || raw === JSON.stringify(storedRows.value))) return
    loadRows()
  }, { immediate: true })

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
    ],
    ([note, conclusion]) => {
      auditNote.value = typeof note === 'string' ? note : ''
      auditConclusion.value = typeof conclusion === 'string' ? conclusion : ''
    },
    { immediate: true },
  )

  const rows: ComputedRef<MonthlyDetailRow[]> = computed(() =>
    storedRows.value.map(computeF5MonthlyRow),
  )
  const totalRow = computed(() => buildF5MonthlyTotal(rows.value))
  const ratioRow = computed(() => buildF5MonthlyRatioRow(totalRow.value))

  const significantChanges = computed(() =>
    rows.value.filter((row) => {
      const rates = [row.unauditedChangeRate, row.auditedChangeRate]
      return rates.some((r) => typeof r === 'number' && Math.abs(r) >= F5_MONTHLY_CHANGE_RATE_THRESHOLD)
    }),
  )

  /** 持久化时附带 m1..m12，便于导入导出宽表与 months 数组互转 */
  function toPersistRows(): Array<StoredMonthlyRow & Record<string, number | string>> {
    return storedRows.value.map((r) => {
      const flat: StoredMonthlyRow & Record<string, number | string> = { ...r, months: [...r.months] }
      for (let i = 0; i < 12; i++) flat[`m${i + 1}`] = r.months[i] || 0
      return flat
    })
  }

  function persist(): void {
    const json = JSON.stringify(toPersistRows())
    lastPersisted = json
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f5:save-items', { detail: { items } }))
    }
  }

  function updateCell(id: string, key: string, value: number | string): void {
    if (readonly.value) return
    const row = storedRows.value.find((r) => r.id === id)
    if (!row) return
    const monthMatch = /^month(\d{1,2})$/.exec(key)
    if (monthMatch) {
      const idx = Number(monthMatch[1]) - 1
      if (idx >= 0 && idx < 12) row.months[idx] = parseNum(value)
    } else if (key === 'product' || key === 'remark') {
      ;(row as any)[key] = String(value ?? '')
    } else if (['currentAje', 'currentRje', 'priorUnaudited', 'priorAje', 'priorRje'].includes(key)) {
      ;(row as any)[key] = parseNum(value)
    } else if (key === 'priorYearTotal') {
      // 兼容旧字段名
      row.priorUnaudited = parseNum(value)
    }
    persist()
  }

  function updateMonth(id: string, monthIndex: number, value: number | string): void {
    if (monthIndex < 0 || monthIndex > 11) return
    updateCell(id, `month${monthIndex + 1}`, value)
  }

  function addRow(product = ''): void {
    if (readonly.value) return
    storedRows.value.push(emptyF5MonthlyRow(product || `品种${storedRows.value.length + 1}`))
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    if (storedRows.value.length <= 1) {
      storedRows.value = [emptyF5MonthlyRow('品种1')]
      persist()
      return
    }
    storedRows.value = storedRows.value.filter((r) => r.id !== id)
    persist()
  }

  function isRowHighlighted(row: MonthlyDetailRow): boolean {
    return [row.unauditedChangeRate, row.auditedChangeRate].some(
      (r) => typeof r === 'number' && Math.abs(r) >= F5_MONTHLY_CHANGE_RATE_THRESHOLD,
    )
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: value })
    debounceSave()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    totalRow,
    ratioRow,
    significantChanges,
    auditNote,
    auditConclusion,
    updateCell,
    updateMonth,
    addRow,
    removeRow,
    isRowHighlighted,
    saveAuditNote,
    saveAuditConclusion,
    loadRows: loadRows,
  }
}

export default useF5MonthlyDetail
