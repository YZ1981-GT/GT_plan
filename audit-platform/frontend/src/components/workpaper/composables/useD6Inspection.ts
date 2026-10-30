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
 * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：抽凭进区块(1)，
 * 挂凭导入按凭证日期分区，按分录指纹去重，行元数据 `_gt` 随行 JSON 落库
 * （spec voucher-identity-writeback-and-audit-phase 任务 10）。
 *
 * Spec: .kiro/specs/d6-contract-assets/
 * Task: 12.1
 * Requirements: 11.1-11.9, 25.1-25.3
 */
import { ref, computed, watch, toValue, type Ref, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import { parseNum, calcSubtotal } from './useD6FormulaEngine'
import type { ChecklistResponse } from './useD6FormData'
import { metaOf, useVoucherCheckFill, withRowMeta, type PreparedItem } from './shared/voucherCheckFill'
import { partyNameForColumn } from './shared/samplingPartyTarget'

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
  /** 只读（回填 / 挂凭导入 / 撤销都不做） */
  isReadonly?: MaybeRefOrGetter<boolean>
  /** 资产负债表日（挂凭导入按凭证日期分区：晚于它的进区块(2)）；缺省全进区块(1) */
  bsDate?: MaybeRefOrGetter<string | null | undefined>
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
  return withRowMeta<InspectionSampleRow>({
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
  }, raw)
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

/**
 * 共享回填函数的待写入项 → 检查行（spec voucher-identity-writeback-and-audit-phase 任务 10）：对方科目取后端配对
 * 结果（配不上写「多科目」），对方明细写对方科目名称，金额落在样本自己的借贷栏（原宿主按对方分录展开、
 * 把金额翻到对方栏的推断已删除）。
 */
export function mapPreparedToInspectionRow(item: PreparedItem): InspectionSampleRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null }
  return {
    ...createEmptySample(1),
    customerName: partyNameForColumn(s as never, 'customer'),
    date: String(s.voucherDate ?? ''),
    voucherNo: String(s.voucherNo ?? ''),
    businessContent: String(s.summary ?? ''),
    counterAccount: item.counterpartAccount,
    counterDetail: item.counterpartAccountName === item.counterpartAccount ? '' : item.counterpartAccountName,
    debitAmount: parseNum(item.debitAmount),
    creditAmount: parseNum(item.creditAmount),
  }
}

/** 行上是否已填核对结果 / 文件 / 备注（替换 / 撤销前先确认） */
export function hasInspectionContent(r: InspectionSampleRow): boolean {
  return [r.check1, r.check2, r.check3, r.check4, r.check5, r.supportDoc, r.indexRef, r.remark]
    .some(v => String(v ?? '').trim() !== '') || r.isAbnormal === '是'
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

  /** 已在某区块的分录（按指纹）：再次回填 / 挂凭导入仍进那一区块 */
  function blockHolding(lfp: string | null): 'block1' | 'block2' | null {
    if (!lfp) return null
    if (block1Rows.value.some(r => metaOf(r)?.lfp === lfp)) return 'block1'
    if (block2Rows.value.some(r => metaOf(r)?.lfp === lfp)) return 'block2'
    return null
  }

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（抽凭进区块(1)，挂凭导入按凭证日期分区）
  const voucherFill = useVoucherCheckFill<InspectionSampleRow>({
    projectId: options.projectId,
    tables: { block1: block1Rows, block2: block2Rows },
    tableOf: (item) => {
      const held = blockHolding(item.meta.lfp)
      if (held || !item.meta.src.includes('attach')) return held
      const bs = toValue(options.bsDate) || ''
      const date = String(item.sample.voucherDate ?? '')
      return date && bs && date > bs ? 'block2' : 'block1'
    },
    mapSampleToRow: item => mapPreparedToInspectionRow(item),
    persist: () => Promise.all([
      options.saveImmediate(ITEM_ID_BLOCK1_ROWS, { remark: blockJson(1) }),
      options.saveImmediate(ITEM_ID_BLOCK2_ROWS, { remark: blockJson(2) }),
    ]),
    hasUserContent: hasInspectionContent,
    readonly: () => !!toValue(options.isReadonly),
  })

  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedRow(block: 1 | 2, rowId: string): boolean {
    const row = (block === 1 ? block1Rows.value : block2Rows.value).find(r => r.rowId === rowId)
    return !!row && voucherFill.isRowLocked(row)
  }

  /** 一区块的行 JSON（年审阶段预审行按读入版本写回，防绕过） */
  function blockJson(block: 1 | 2): string {
    return block === 1
      ? JSON.stringify(voucherFill.guardPersist(block1Rows.value, 'block1'))
      : JSON.stringify(voucherFill.guardPersist(block2Rows.value, 'block2'))
  }

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
      voucherFill.markLoaded()
    },
    { immediate: true },
  )

  // Load block2 rows
  watch(
    () => allResponses.value.get(ITEM_ID_BLOCK2_ROWS)?.remark,
    (jsonStr) => {
      block2Rows.value = safeParseRows(jsonStr)
      voucherFill.markLoaded()
    },
    { immediate: true },
  )

  // ─── Persist ─────────────────────────────────────────────────────────

  function persistSamplingParams(): void {
    debouncedSave(ITEM_ID_SAMPLING_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  function persistBlock1(): void {
    debouncedSave(ITEM_ID_BLOCK1_ROWS, { remark: blockJson(1) })
  }

  function persistBlock2(): void {
    debouncedSave(ITEM_ID_BLOCK2_ROWS, { remark: blockJson(2) })
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
    if (lockedRow(block, rowId)) return
    if (block === 1) {
      block1Rows.value = block1Rows.value.filter(r => r.rowId !== rowId)
      persistBlock1()
    } else {
      block2Rows.value = block2Rows.value.filter(r => r.rowId !== rowId)
      persistBlock2()
    }
  }

  function updateSampleCell(block: 1 | 2, rowId: string, field: string, value: any): void {
    if (lockedRow(block, rowId)) return
    const NUMERIC_FIELDS = ['debitAmount', 'creditAmount']
    const mapRow = (r: InspectionSampleRow): InspectionSampleRow => {
      if (r.rowId !== rowId) return r
      const updated = { ...r }
      if (NUMERIC_FIELDS.includes(field)) {
        ;(updated as any)[field] = parseNum(value)
      } else {
        ;(updated as any)[field] = value
      }
      return updated
    }
    if (block === 1) {
      block1Rows.value = block1Rows.value.map(mapRow)
      persistBlock1()
    } else {
      block2Rows.value = block2Rows.value.map(mapRow)
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
    updateSampleCell,
    checkRatioSummary,
    auditNotes,
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled: voucherFill.onEngineFilled,
    onAttachImported: voucherFill.onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}

export default useD6Inspection
