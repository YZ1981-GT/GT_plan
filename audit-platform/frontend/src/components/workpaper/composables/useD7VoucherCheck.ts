/**
 * useD7VoucherCheck — D7-7 凭证检查（双区块：本期增减变动 + 期后结转）
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 12.1
 * Requirements: 12.1-12.9, 18.5, 24.1-24.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface VoucherCheckRow {
  rowId: string
  customerName: string     // 客户名称
  date: string             // 日期
  voucherNo: string        // 凭证号
  businessContent: string  // 业务内容
  counterAccount: string   // 对方科目
  counterDetail: string    // 对方明细
  debitAmount?: number     // 借方金额（仅本期变动区块）
  creditAmount: number     // 贷方金额
  supportDocs: string      // 支持文件
  checkItems: boolean[]    // 核对内容(1-5)
  indexRef: string         // 索引号
  isAbnormal: boolean      // 是否异常
  remark: string           // 备注
}

export interface SamplingParams {
  totalPopulation: number     // 总体笔数
  specificSamples: number     // 特定项目样本
  samplingPopulation: number  // 抽样总体笔数
  targetSampleSize: number    // 目标样本量
  samplingMethod: string      // 抽样方法
  samplingProcess: string     // 抽样过程说明
}

export interface UseD7VoucherCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_SAMPLING_PARAMS = 'D7-7-sampling-params'
const ITEM_PERIOD_ROWS = 'D7-7-period-rows'
const ITEM_POST_ROWS = 'D7-7-post-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `vc-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseArray(jsonStr: string | null | undefined): any[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function normalizeVoucherRow(raw: any, hasDebit: boolean): VoucherCheckRow {
  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterDetail: raw.counterDetail || '',
    debitAmount: hasDebit ? parseNum(raw.debitAmount) : undefined,
    creditAmount: parseNum(raw.creditAmount),
    supportDocs: raw.supportDocs || '',
    checkItems: Array.isArray(raw.checkItems) ? raw.checkItems : [false, false, false, false, false],
    indexRef: raw.indexRef || '',
    isAbnormal: raw.isAbnormal === true,
    remark: raw.remark || '',
  }
}

function createEmptyRow(hasDebit: boolean): VoucherCheckRow {
  return {
    rowId: generateRowId(),
    customerName: '', date: '', voucherNo: '',
    businessContent: '', counterAccount: '', counterDetail: '',
    debitAmount: hasDebit ? 0 : undefined,
    creditAmount: 0, supportDocs: '',
    checkItems: [false, false, false, false, false],
    indexRef: '', isAbnormal: false, remark: '',
  }
}

function defaultSamplingParams(): SamplingParams {
  return {
    totalPopulation: 0,
    specificSamples: 0,
    samplingPopulation: 0,
    targetSampleSize: 0,
    samplingMethod: '',
    samplingProcess: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD7VoucherCheck(options: UseD7VoucherCheckOptions) {
  const { allResponses, debouncedSave } = options

  // ─── Sampling Params ─────────────────────────────────────────────────

  const samplingParams = ref<SamplingParams>(defaultSamplingParams())

  watch(
    () => allResponses.value.get(ITEM_SAMPLING_PARAMS)?.remark,
    (jsonStr) => {
      if (!jsonStr) return
      try {
        const parsed = JSON.parse(jsonStr)
        samplingParams.value = { ...defaultSamplingParams(), ...parsed }
      } catch { /* keep defaults */ }
    },
    { immediate: true },
  )

  watch(samplingParams, (params) => {
    debouncedSave(ITEM_SAMPLING_PARAMS, { remark: JSON.stringify(params) })
  }, { deep: true })

  // ─── Period Change Rows (本期增减变动) ───────────────────────────────

  const periodChangeRows = ref<VoucherCheckRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_PERIOD_ROWS)?.remark,
    (jsonStr) => {
      periodChangeRows.value = safeParseArray(jsonStr).map((r: any) => normalizeVoucherRow(r, true))
    },
    { immediate: true },
  )

  function persistPeriodRows(): void {
    debouncedSave(ITEM_PERIOD_ROWS, { remark: JSON.stringify(periodChangeRows.value) })
  }

  // ─── Post Transfer Rows (期后结转, 无借方金额列) ─────────────────────

  const postTransferRows = ref<VoucherCheckRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_POST_ROWS)?.remark,
    (jsonStr) => {
      postTransferRows.value = safeParseArray(jsonStr).map((r: any) => normalizeVoucherRow(r, false))
    },
    { immediate: true },
  )

  function persistPostRows(): void {
    debouncedSave(ITEM_POST_ROWS, { remark: JSON.stringify(postTransferRows.value) })
  }

  // ─── Computed Summaries ──────────────────────────────────────────────

  const checkedCount: ComputedRef<number> = computed(() =>
    periodChangeRows.value.length + postTransferRows.value.length,
  )

  const abnormalCount: ComputedRef<number> = computed(() => {
    const periodAbn = periodChangeRows.value.filter(r => r.isAbnormal).length
    const postAbn = postTransferRows.value.filter(r => r.isAbnormal).length
    return periodAbn + postAbn
  })

  const abnormalRate: ComputedRef<number> = computed(() => {
    if (checkedCount.value === 0) return 0
    return abnormalCount.value / checkedCount.value
  })

  /** 期后结转贷方合计 → 供crossSheet联动D7-2 */
  const postTransferCreditTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(postTransferRows.value.map(r => r.creditAmount)),
  )

  // ─── Add/Remove/Update ───────────────────────────────────────────────

  function addSample(block: 'period' | 'post'): void {
    if (block === 'period') {
      periodChangeRows.value = [...periodChangeRows.value, createEmptyRow(true)]
      persistPeriodRows()
    } else {
      postTransferRows.value = [...postTransferRows.value, createEmptyRow(false)]
      persistPostRows()
    }
  }

  function removeSample(block: 'period' | 'post', rowId: string): void {
    if (block === 'period') {
      periodChangeRows.value = periodChangeRows.value.filter(r => r.rowId !== rowId)
      persistPeriodRows()
    } else {
      postTransferRows.value = postTransferRows.value.filter(r => r.rowId !== rowId)
      persistPostRows()
    }
  }

  function updateCell(block: 'period' | 'post', rowId: string, field: string, value: any): void {
    const updateFn = (r: VoucherCheckRow): VoucherCheckRow => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (field === 'debitAmount' || field === 'creditAmount') {
        ;(updated as any)[field] = parseNum(value)
      } else if (field === 'isAbnormal') {
        updated.isAbnormal = value === true
      } else if (field === 'checkItems') {
        updated.checkItems = Array.isArray(value) ? value : updated.checkItems
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    }

    if (block === 'period') {
      periodChangeRows.value = periodChangeRows.value.map(updateFn)
      persistPeriodRows()
    } else {
      postTransferRows.value = postTransferRows.value.map(updateFn)
      persistPostRows()
    }
  }

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(allResponses, (map) => {
    auditNotes.value.explanation = map.get('D7-7-note-explanation')?.remark || ''
    auditNotes.value.conclusion = map.get('D7-7-note-conclusion')?.remark || ''
  }, { immediate: true })

  watch(() => auditNotes.value.explanation, (v) => debouncedSave('D7-7-note-explanation', { remark: v }))
  watch(() => auditNotes.value.conclusion, (v) => debouncedSave('D7-7-note-conclusion', { remark: v }))

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    samplingParams,
    periodChangeRows,
    postTransferRows,
    checkedCount,
    abnormalCount,
    abnormalRate,
    postTransferCreditTotal,
    addSample,
    removeSample,
    updateCell,
    auditNotes,
  }
}

export default useD7VoucherCheck
