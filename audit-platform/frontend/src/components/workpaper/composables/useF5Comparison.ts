/**
 * useF5Comparison — F5-5 主营业务成本与上年度比较分析表
 *
 * 源表逻辑（A–O）：
 *  产品 × (本期数量/平均单位成本/总成本 + 上期同结构 + 变动额 + 变动率 + 变动原因/索引号)
 *  总成本 = 数量 × 平均单位成本
 *  变动额 = 本期 − 上期；变动率 = 变动额 / 上期（上期=0 → N/A，避免 #DIV/0）
 *  合计行：仅汇总总成本及总成本变动额/率（数量、单价列不汇总）
 */
import { computed, ref, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcChangeAmount } from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5ComparisonOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface ComparisonRow {
  id: string
  product: string
  currentQty: number
  currentUnitCost: number
  currentTotalCost: number
  priorQty: number
  priorUnitCost: number
  priorTotalCost: number
  qtyChange: number
  unitCostChange: number
  totalCostChange: number
  qtyChangeRate: number | 'N/A'
  unitCostChangeRate: number | 'N/A'
  totalCostChangeRate: number | 'N/A'
  changeReason: string
  indexRef: string
}

interface StoredComparisonRow {
  id: string
  product: string
  currentQty: number
  currentUnitCost: number
  priorQty: number
  priorUnitCost: number
  changeReason: string
  indexRef: string
}

export interface ComparisonTotalRow {
  currentTotalCost: number
  priorTotalCost: number
  totalCostChange: number
  totalCostChangeRate: number | 'N/A'
}

const STORAGE_KEY = 'F5-5-comparison-rows'
const LEGACY_STORAGE_KEY = 'F5-5-rows'
const NOTE_KEY = 'F5-5-audit-note'
const CONCLUSION_KEY = 'F5-5-audit-conclusion'
const LEGACY_CONCLUSION_KEY = 'F5-5-conclusion'

/** 源表默认空白产品行数 */
export const F5_COMPARISON_DEFAULT_ROWS = 6
/** 总成本变动率绝对值超过此阈值标黄 */
export const F5_COMPARISON_CHANGE_RATE_THRESHOLD = 30

/** 变动率 = 变动额/上期；上期=0 → N/A（对应 Excel #DIV/0） */
export function calcF5ComparisonChangeRate(
  change: number,
  prior: number,
): number | 'N/A' {
  if (prior === 0) return 'N/A'
  return (change / prior) * 100
}

export function emptyF5ComparisonRow(product = ''): StoredComparisonRow {
  return {
    id: `cmp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    product,
    currentQty: 0,
    currentUnitCost: 0,
    priorQty: 0,
    priorUnitCost: 0,
    changeReason: '',
    indexRef: '',
  }
}

export function defaultF5ComparisonRows(): StoredComparisonRow[] {
  return Array.from({ length: F5_COMPARISON_DEFAULT_ROWS }, () => emptyF5ComparisonRow())
}

export function migrateF5ComparisonRows(jsonStr: string | null | undefined): StoredComparisonRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => {
      const product = String(r?.product ?? r?.variety ?? r?.label ?? '')
      let currentQty = parseNum(r?.currentQty ?? r?.qty)
      let currentUnitCost = parseNum(r?.currentUnitCost ?? r?.unitCost ?? r?.avgUnitCost)
      let priorQty = parseNum(r?.priorQty)
      let priorUnitCost = parseNum(r?.priorUnitCost)

      // 旧毛利模型：仅有成本金额 → 数量=1、单价=成本，使总成本=原成本
      if (
        currentQty === 0 && currentUnitCost === 0
        && (r?.currentCost != null || r?.currentTotalCost != null)
      ) {
        const cost = parseNum(r?.currentTotalCost ?? r?.currentCost)
        if (cost !== 0) {
          currentQty = 1
          currentUnitCost = cost
        }
      }
      if (
        priorQty === 0 && priorUnitCost === 0
        && (r?.priorCost != null || r?.priorTotalCost != null)
      ) {
        const cost = parseNum(r?.priorTotalCost ?? r?.priorCost)
        if (cost !== 0) {
          priorQty = 1
          priorUnitCost = cost
        }
      }

      return {
        id: String(r?.id ?? r?.rowId ?? `cmp-migrated-${i}`),
        product,
        currentQty,
        currentUnitCost,
        priorQty,
        priorUnitCost,
        changeReason: String(r?.changeReason ?? r?.auditEvaluation ?? ''),
        indexRef: String(r?.indexRef ?? r?.remark ?? ''),
      }
    })
  } catch {
    return []
  }
}

export function computeF5ComparisonRow(stored: StoredComparisonRow): ComparisonRow {
  const currentTotalCost = stored.currentQty * stored.currentUnitCost
  const priorTotalCost = stored.priorQty * stored.priorUnitCost
  const qtyChange = calcChangeAmount(stored.currentQty, stored.priorQty)
  const unitCostChange = calcChangeAmount(stored.currentUnitCost, stored.priorUnitCost)
  const totalCostChange = calcChangeAmount(currentTotalCost, priorTotalCost)
  return {
    id: stored.id,
    product: stored.product,
    currentQty: stored.currentQty,
    currentUnitCost: stored.currentUnitCost,
    currentTotalCost,
    priorQty: stored.priorQty,
    priorUnitCost: stored.priorUnitCost,
    priorTotalCost,
    qtyChange,
    unitCostChange,
    totalCostChange,
    qtyChangeRate: calcF5ComparisonChangeRate(qtyChange, stored.priorQty),
    unitCostChangeRate: calcF5ComparisonChangeRate(unitCostChange, stored.priorUnitCost),
    totalCostChangeRate: calcF5ComparisonChangeRate(totalCostChange, priorTotalCost),
    changeReason: stored.changeReason,
    indexRef: stored.indexRef,
  }
}

export function buildF5ComparisonTotal(rows: ComparisonRow[]): ComparisonTotalRow {
  let currentTotalCost = 0
  let priorTotalCost = 0
  for (const row of rows) {
    currentTotalCost += row.currentTotalCost
    priorTotalCost += row.priorTotalCost
  }
  const totalCostChange = calcChangeAmount(currentTotalCost, priorTotalCost)
  return {
    currentTotalCost,
    priorTotalCost,
    totalCostChange,
    totalCostChangeRate: calcF5ComparisonChangeRate(totalCostChange, priorTotalCost),
  }
}

export function useF5Comparison(options: UseF5ComparisonOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedRows = ref<StoredComparisonRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawJson(): string | null | undefined {
    return allResponses.value.get(STORAGE_KEY)?.remark
      ?? allResponses.value.get(LEGACY_STORAGE_KEY)?.remark
  }

  function loadRows(): void {
    const migrated = migrateF5ComparisonRows(rawJson())
    storedRows.value = migrated.length ? migrated : defaultF5ComparisonRows()
  }

  watch(() => rawJson(), (raw) => {
    if (raw && (raw === lastPersisted || raw === JSON.stringify(storedRows.value))) return
    loadRows()
  }, { immediate: true })

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark
        ?? allResponses.value.get(LEGACY_CONCLUSION_KEY)?.remark,
    ],
    ([note, conclusion]) => {
      auditNote.value = typeof note === 'string' ? note : ''
      auditConclusion.value = typeof conclusion === 'string' ? conclusion : ''
    },
    { immediate: true },
  )

  const rows: ComputedRef<ComparisonRow[]> = computed(() =>
    storedRows.value.map(computeF5ComparisonRow),
  )
  const totalRow = computed(() => buildF5ComparisonTotal(rows.value))

  const significantChanges = computed(() =>
    rows.value.filter((row) => {
      if (!row.product.trim() && row.currentTotalCost === 0 && row.priorTotalCost === 0) return false
      return typeof row.totalCostChangeRate === 'number'
        && Math.abs(row.totalCostChangeRate) >= F5_COMPARISON_CHANGE_RATE_THRESHOLD
    }),
  )

  function persist(): void {
    const json = JSON.stringify(storedRows.value)
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
    if (key === 'product' || key === 'changeReason' || key === 'indexRef') {
      ;(row as any)[key] = String(value ?? '')
    } else if (['currentQty', 'currentUnitCost', 'priorQty', 'priorUnitCost'].includes(key)) {
      ;(row as any)[key] = parseNum(value)
    }
    persist()
  }

  function addRow(product = ''): void {
    if (readonly.value) return
    storedRows.value.push(emptyF5ComparisonRow(product))
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const next = storedRows.value.filter((r) => r.id !== id)
    storedRows.value = next.length ? next : defaultF5ComparisonRows()
    persist()
  }

  function isRowHighlighted(row: ComparisonRow): boolean {
    return typeof row.totalCostChangeRate === 'number'
      && Math.abs(row.totalCostChangeRate) >= F5_COMPARISON_CHANGE_RATE_THRESHOLD
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
    significantChanges,
    auditNote,
    auditConclusion,
    updateCell,
    addRow,
    removeRow,
    isRowHighlighted,
    saveAuditNote,
    saveAuditConclusion,
    loadRows,
  }
}

export default useF5Comparison
