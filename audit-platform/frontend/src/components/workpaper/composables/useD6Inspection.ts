/**
 * useD6Inspection — D6-6 检查表（双区块+抽样参数19公式）
 *
 * 结构：
 *   - 抽样参数区（samplingParams）
 *   - (1) 本期增减变动检查（block1Rows，含debitAmount+creditAmount）
 *   - (2) 期后贴现/背书/调整检查（block2Rows，仅creditAmount无debitAmount）
 *
 * 功能：
 *   - addSample(block) / removeSample(block, rowId)
 *   - checkRatioSummary computed（检查比例=检查金额/账面金额）
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 12.1
 * Requirements: 11.1-11.9, 25.1-25.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface InspectionSampleRow {
  rowId: string
  customerName: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetail: string
  debitAmount?: number       // 仅区块(1)有
  creditAmount: number
  supportDoc: string
  check1: string
  check2: string
  check3: string
  check4: string
  check5: string
  indexRef: string
  isAbnormal: string         // 是否异常
  remark: string
}

export interface SamplingParams {
  testPopulation: string     // 测试总体
  specificSample: string     // 特定样本
  samplingPopulation: string // 抽样总体
  targetSampleSize: number   // 目标样本量
  samplingMethod: string     // 抽样方法
  samplingProcess: string    // 抽样过程
}

export interface UseD6InspectionOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId: Ref<string>
  projectId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_SAMPLING_PARAMS = 'D6-6-sampling-params'
const ITEM_ID_BLOCK1_ROWS = 'D6-6-block1-rows'
const ITEM_ID_BLOCK2_ROWS = 'D6-6-block2-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): InspectionSampleRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

function normalizeRow(raw: any): InspectionSampleRow {
  return {
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterDetail: raw.counterDetail || '',
    debitAmount: raw.debitAmount != null ? parseNum(raw.debitAmount) : undefined,
    creditAmount: parseNum(raw.creditAmount),
    supportDoc: raw.supportDoc || '',
    check1: raw.check1 || '',
    check2: raw.check2 || '',
    check3: raw.check3 || '',
    check4: raw.check4 || '',
    check5: raw.check5 || '',
    indexRef: raw.indexRef || '',
    isAbnormal: raw.isAbnormal || '否',
    remark: raw.remark || '',
  }
}

function safeParseSamplingParams(jsonStr: string | null | undefined): SamplingParams {
  const defaults: SamplingParams = {
    testPopulation: '',
    specificSample: '',
    samplingPopulation: '',
    targetSampleSize: 0,
    samplingMethod: '',
    samplingProcess: '',
  }
  if (!jsonStr) return defaults
  try {
    const parsed = JSON.parse(jsonStr)
    return {
      testPopulation: parsed.testPopulation || '',
      specificSample: parsed.specificSample || '',
      samplingPopulation: parsed.samplingPopulation || '',
      targetSampleSize: parseNum(parsed.targetSampleSize),
      samplingMethod: parsed.samplingMethod || '',
      samplingProcess: parsed.samplingProcess || '',
    }
  } catch {
    return defaults
  }
}

function createEmptySample(block: 1 | 2): InspectionSampleRow {
  return {
    rowId: generateRowId(),
    customerName: '',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetail: '',
    debitAmount: block === 1 ? 0 : undefined,
    creditAmount: 0,
    supportDoc: '',
    check1: '', check2: '', check3: '', check4: '', check5: '',
    indexRef: '',
    isAbnormal: '否',
    remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD6Inspection(options: UseD6InspectionOptions) {
  const { allResponses, debouncedSave } = options

  // ─── Reactive data ───────────────────────────────────────────────────

  const samplingParams = ref<SamplingParams>({
    testPopulation: '',
    specificSample: '',
    samplingPopulation: '',
    targetSampleSize: 0,
    samplingMethod: '',
    samplingProcess: '',
  })

  const block1Rows = ref<InspectionSampleRow[]>([])
  const block2Rows = ref<InspectionSampleRow[]>([])

  // Load sampling params
  watch(
    () => allResponses.value.get(ITEM_ID_SAMPLING_PARAMS)?.remark,
    (jsonStr) => {
      samplingParams.value = safeParseSamplingParams(jsonStr)
    },
    { immediate: true },
  )

  // Load block1 rows
  watch(
    () => allResponses.value.get(ITEM_ID_BLOCK1_ROWS)?.remark,
    (jsonStr) => {
      block1Rows.value = safeParseRows(jsonStr)
    },
    { immediate: true },
  )

  // Load block2 rows
  watch(
    () => allResponses.value.get(ITEM_ID_BLOCK2_ROWS)?.remark,
    (jsonStr) => {
      block2Rows.value = safeParseRows(jsonStr)
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistSamplingParams(): void {
    debouncedSave(ITEM_ID_SAMPLING_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  function persistBlock1(): void {
    debouncedSave(ITEM_ID_BLOCK1_ROWS, { remark: JSON.stringify(block1Rows.value) })
  }

  function persistBlock2(): void {
    debouncedSave(ITEM_ID_BLOCK2_ROWS, { remark: JSON.stringify(block2Rows.value) })
  }

  // Watch samplingParams changes for auto-save
  watch(samplingParams, () => persistSamplingParams(), { deep: true })

  // ─── Add/Remove ──────────────────────────────────────────────────────

  function addSample(block: 1 | 2): void {
    const newRow = createEmptySample(block)
    if (block === 1) {
      block1Rows.value = [...block1Rows.value, newRow]
      persistBlock1()
    } else {
      block2Rows.value = [...block2Rows.value, newRow]
      persistBlock2()
    }
  }

  function removeSample(block: 1 | 2, rowId: string): void {
    if (block === 1) {
      block1Rows.value = block1Rows.value.filter(r => r.rowId !== rowId)
      persistBlock1()
    } else {
      block2Rows.value = block2Rows.value.filter(r => r.rowId !== rowId)
      persistBlock2()
    }
  }

  // ─── Check Ratio Summary ─────────────────────────────────────────────

  /**
   * 检查比例 = 检查金额 / 账面金额
   * 从D6-2总行取账面金额合计
   */
  const checkRatioSummary: ComputedRef<Array<{
    direction: string
    bookAmount: number
    checkAmount: number
    ratio: number
  }>> = computed(() => {
    // 从D6-2取期末审定合计作为账面金额
    let bookAmount = 0
    try {
      const d6DetailJson = allResponses.value.get('D6-2-rows')?.remark
      if (d6DetailJson) {
        const detailRows = JSON.parse(d6DetailJson)
        if (Array.isArray(detailRows)) {
          bookAmount = calcSubtotal(detailRows.map((r: any) => parseNum(r.endAudited)))
        }
      }
    } catch { /* ignore */ }

    const block1Debit = calcSubtotal(block1Rows.value.map(r => parseNum(r.debitAmount)))
    const block1Credit = calcSubtotal(block1Rows.value.map(r => r.creditAmount))
    const block2Credit = calcSubtotal(block2Rows.value.map(r => r.creditAmount))

    const results = [
      {
        direction: '本期借方',
        bookAmount,
        checkAmount: block1Debit,
        ratio: bookAmount > 0 ? block1Debit / bookAmount : 0,
      },
      {
        direction: '本期贷方',
        bookAmount,
        checkAmount: block1Credit,
        ratio: bookAmount > 0 ? block1Credit / bookAmount : 0,
      },
      {
        direction: '期后结转',
        bookAmount,
        checkAmount: block2Credit,
        ratio: bookAmount > 0 ? block2Credit / bookAmount : 0,
      },
    ]

    return results
  })

  // ─── Audit Notes ─────────────────────────────────────────────────────

  const auditNotes = ref<{ explanation: string; conclusion: string }>({
    explanation: '',
    conclusion: '',
  })

  watch(
    () => allResponses.value.get('D6-6-note-explanation')?.remark,
    (v) => { if (v) auditNotes.value.explanation = v },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('D6-6-note-conclusion')?.remark,
    (v) => { if (v) auditNotes.value.conclusion = v },
    { immediate: true },
  )
  watch(
    () => auditNotes.value.explanation,
    (v) => debouncedSave('D6-6-note-explanation', { remark: v }),
  )
  watch(
    () => auditNotes.value.conclusion,
    (v) => debouncedSave('D6-6-note-conclusion', { remark: v }),
  )

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    samplingParams,
    block1Rows,
    block2Rows,
    addSample,
    removeSample,
    checkRatioSummary,
    auditNotes,
  }
}

export default useD6Inspection
