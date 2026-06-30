/**
 * useD3VoucherCheck — D3-7 预收账款检查表核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 13.1
 *
 * 职责：
 * - 定义 VoucherCheckRow/SamplingParams 类型
 * - samplingParams reactive
 * - currentChangeRows（本期增减17列）+ postPeriodRows（期后结转16列）
 * - totalChecked/anomalyCount/anomalyRate computed
 * - addSample/removeSample/updateCell
 * - autoMarkCrossPeriod（日期<收入确认日→标"跨期疑点"）
 *
 * Requirements: 11.1-11.9
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcAnomalyRate } from './useD3FormulaEngine'
import type { ChecklistResponse } from './useD3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface VoucherCheckRow {
  rowId: string
  customerName: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetailAccount: string
  debitAmount?: number       // 仅(1)本期增减有此列
  creditAmount: number
  supportingDoc: string
  checkItems: [boolean, boolean, boolean, boolean, boolean]
  indexRef: string
  isAbnormal: string         // 是否异常
  remark: string
}

export interface SamplingParams {
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingMethod: string
  samplingProcess: string
  targetSampleSize: number
  currentSampleSize: number
}

export interface UseD3VoucherCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_PARAMS = 'D3-vc-params'
const ITEM_ID_CURRENT_ROWS = 'D3-vc-current-rows'
const ITEM_ID_POST_ROWS = 'D3-vc-post-rows'

// ─── Pure Helpers (exported for PBT testability) ─────────────────────────────

/**
 * 计算异常率（纯函数，方便 PBT 测试）
 *
 * anomalyRate = 非空 isAbnormal 行数 / 总行数 × 100
 */
export function computeAnomalyRate(rows: { isAbnormal: string }[]): number {
  if (rows.length === 0) return 0
  const anomalyCount = rows.filter(r => r.isAbnormal !== '' && r.isAbnormal !== null && r.isAbnormal !== undefined).length
  return calcAnomalyRate(anomalyCount, rows.length)
}

/**
 * 判断是否应标记跨期疑点（纯函数，方便 PBT 测试）
 *
 * 当凭证日期早于收入确认日期时，返回 true。
 */
export function shouldMarkCrossPeriod(voucherDate: Date, revenueDate: Date): boolean {
  return voucherDate < revenueDate
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseRows(jsonStr: string | null | undefined): VoucherCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): VoucherCheckRow {
  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterDetailAccount: raw.counterDetailAccount || '',
    debitAmount: raw.debitAmount !== undefined ? parseNum(raw.debitAmount) : undefined,
    creditAmount: parseNum(raw.creditAmount),
    supportingDoc: raw.supportingDoc || '',
    checkItems: Array.isArray(raw.checkItems) && raw.checkItems.length === 5
      ? raw.checkItems as [boolean, boolean, boolean, boolean, boolean]
      : [false, false, false, false, false],
    indexRef: raw.indexRef || '',
    isAbnormal: raw.isAbnormal || '',
    remark: raw.remark || '',
  }
}

function createEmptyRow(section: 'current' | 'postPeriod'): VoucherCheckRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetailAccount: '',
    debitAmount: section === 'current' ? 0 : undefined,
    creditAmount: 0,
    supportingDoc: '',
    checkItems: [false, false, false, false, false],
    indexRef: '',
    isAbnormal: '',
    remark: '',
  }
}

function safeParseParams(jsonStr: string | null | undefined): SamplingParams {
  const defaults: SamplingParams = {
    testPopulation: '',
    specificSamples: '',
    samplingPopulation: '',
    samplingMethod: '',
    samplingProcess: '',
    targetSampleSize: 0,
    currentSampleSize: 0,
  }
  if (!jsonStr) return defaults
  try {
    const parsed = JSON.parse(jsonStr)
    return { ...defaults, ...parsed }
  } catch {
    return defaults
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3VoucherCheck(options: UseD3VoucherCheckOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  // ─── Sampling Params ─────────────────────────────────────────────────

  const samplingParams = ref<SamplingParams>(safeParseParams(null))

  watch(
    () => allResponses.value.get(ITEM_ID_PARAMS)?.remark,
    (jsonStr) => { samplingParams.value = safeParseParams(jsonStr) },
    { immediate: true },
  )

  function updateSamplingParams(field: string, value: any): void {
    if (isReadonly.value) return
    ;(samplingParams.value as any)[field] = value
    debouncedSave(ITEM_ID_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  // ─── Current Change Rows (1)本期增减 ─────────────────────────────────

  const currentChangeRows = ref<VoucherCheckRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_CURRENT_ROWS)?.remark,
    (jsonStr) => { currentChangeRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Post Period Rows (2)期后结转 ────────────────────────────────────

  const postPeriodRows = ref<VoucherCheckRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_POST_ROWS)?.remark,
    (jsonStr) => { postPeriodRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistCurrentRows(): void {
    debouncedSave(ITEM_ID_CURRENT_ROWS, { remark: JSON.stringify(currentChangeRows.value) })
  }

  function persistPostRows(): void {
    debouncedSave(ITEM_ID_POST_ROWS, { remark: JSON.stringify(postPeriodRows.value) })
  }

  // ─── Computed: totals ────────────────────────────────────────────────

  const totalChecked: ComputedRef<number> = computed(() => {
    return currentChangeRows.value.length + postPeriodRows.value.length
  })

  const anomalyCount: ComputedRef<number> = computed(() => {
    const allRows = [...currentChangeRows.value, ...postPeriodRows.value]
    return allRows.filter(r => r.isAbnormal !== '').length
  })

  const anomalyRate: ComputedRef<number> = computed(() => {
    return computeAnomalyRate([...currentChangeRows.value, ...postPeriodRows.value])
  })

  // ─── addSample / removeSample / updateCell ───────────────────────────

  function addSample(section: 'current' | 'postPeriod'): void {
    if (isReadonly.value) return
    const newRow = createEmptyRow(section)
    if (section === 'current') {
      currentChangeRows.value = [...currentChangeRows.value, newRow]
      persistCurrentRows()
    } else {
      postPeriodRows.value = [...postPeriodRows.value, newRow]
      persistPostRows()
    }
  }

  function removeSample(section: 'current' | 'postPeriod', rowId: string): void {
    if (isReadonly.value) return
    if (section === 'current') {
      currentChangeRows.value = currentChangeRows.value.filter(r => r.rowId !== rowId)
      persistCurrentRows()
    } else {
      postPeriodRows.value = postPeriodRows.value.filter(r => r.rowId !== rowId)
      persistPostRows()
    }
  }

  function updateCell(section: 'current' | 'postPeriod', rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    const rows = section === 'current' ? currentChangeRows.value : postPeriodRows.value
    const idx = rows.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = parseNum(value)
    } else if (field.startsWith('checkItems.')) {
      const checkIdx = parseInt(field.replace('checkItems.', ''), 10)
      if (checkIdx >= 0 && checkIdx < 5) {
        row.checkItems = [...row.checkItems] as [boolean, boolean, boolean, boolean, boolean]
        row.checkItems[checkIdx] = Boolean(value)
      }
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...rows]
    newRows[idx] = row

    if (section === 'current') {
      currentChangeRows.value = newRows
      persistCurrentRows()
    } else {
      postPeriodRows.value = newRows
      persistPostRows()
    }
  }

  // ─── autoMarkCrossPeriod ─────────────────────────────────────────────

  /**
   * 自动标记跨期疑点：当凭证日期早于收入确认日期时，
   * 标记 isAbnormal 为"跨期疑点"。
   *
   * @param revenueRecognitionDate 收入确认日期字符串（如"2025-12-31"）
   */
  function autoMarkCrossPeriod(revenueRecognitionDate: string): void {
    if (isReadonly.value) return
    if (!revenueRecognitionDate) return

    const revenueDate = new Date(revenueRecognitionDate)
    if (isNaN(revenueDate.getTime())) return

    let changed = false
    const newRows = postPeriodRows.value.map(row => {
      if (!row.date) return row
      const voucherDate = new Date(row.date)
      if (isNaN(voucherDate.getTime())) return row

      if (shouldMarkCrossPeriod(voucherDate, revenueDate) && row.isAbnormal !== '跨期疑点') {
        changed = true
        return { ...row, isAbnormal: '跨期疑点' }
      }
      return row
    })

    if (changed) {
      postPeriodRows.value = newRows
      persistPostRows()
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    samplingParams,
    currentChangeRows,
    postPeriodRows,
    totalChecked,
    anomalyCount,
    anomalyRate,
    addSample,
    removeSample,
    updateCell,
    updateSamplingParams,
    autoMarkCrossPeriod,
  }
}

export default useD3VoucherCheck
