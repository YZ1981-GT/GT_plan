/**
 * useD7VoucherCheck — D7-7 凭证检查（双区块：本期增减变动 + 期后结转）
 *
 * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：抽凭进本期增减变动，
 * 挂凭导入按凭证日期分区，按分录指纹去重，行元数据 `_gt` 随行 JSON 落库
 * （spec voucher-identity-writeback-and-audit-phase 任务 10）。
 *
 * Spec: .kiro/specs/d7-contract-liabilities/
 * Task: 12.1
 * Requirements: 12.1-12.9, 18.5, 24.1-24.3
 */
import { ref, computed, watch, toValue, type Ref, type ComputedRef, type MaybeRefOrGetter } from 'vue'
import { parseNum, calcSubtotal } from './useD7FormulaEngine'
import type { ChecklistResponse } from './useD7FormData'
import { metaOf, useVoucherCheckFill, withRowMeta, type PreparedItem } from './shared/voucherCheckFill'
import { partyNameForColumn } from './shared/samplingPartyTarget'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface VoucherCheckRow {
  rowId: string
  customerName: string     // 客户名称
  date: string             // 日期
  voucherNo: string        // 凭证号
  businessContent: string  // 业务内容
  counterAccount: string   // 对方科目
  counterDetail: string    // 对方明细
  debitAmount?: number     // 借方金额（两区都有：模板区② G34 只有「借方金额」——合同负债期后结转是借方）
  creditAmount?: number    // 贷方金额（仅本期变动区块）
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
  /** 只读（回填 / 挂凭导入 / 撤销都不做） */
  isReadonly?: MaybeRefOrGetter<boolean>
  /** 资产负债表日（挂凭导入按凭证日期分区：晚于它的进期后结转）；缺省全进本期增减变动 */
  bsDate?: MaybeRefOrGetter<string | null | undefined>
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

/**
 * 期后结转区一行的金额。区② 原按贷方存 `creditAmount`，spec oo-writeback-template-parity-closure R3 批 B2 起
 * 按模板改存 `debitAmount`；没重新保存过的旧行仍只有 `creditAmount` ⇒ 跨表消费方一律经本函数读。
 */
export function postTransferAmount(raw: any): number {
  return parseNum(raw?.debitAmount ?? raw?.creditAmount)
}

function normalizeVoucherRow(raw: any, isPeriod: boolean): VoucherCheckRow {
  return withRowMeta<VoucherCheckRow>({
    rowId: raw.rowId || generateRowId(),
    customerName: raw.customerName || '',
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterDetail: raw.counterDetail || '',
    debitAmount: isPeriod ? parseNum(raw.debitAmount) : postTransferAmount(raw),
    creditAmount: isPeriod ? parseNum(raw.creditAmount) : undefined,
    supportDocs: raw.supportDocs || '',
    checkItems: Array.isArray(raw.checkItems) ? raw.checkItems : [false, false, false, false, false],
    indexRef: raw.indexRef || '',
    isAbnormal: raw.isAbnormal === true,
    remark: raw.remark || '',
  }, raw)
}

function createEmptyRow(isPeriod: boolean): VoucherCheckRow {
  return {
    rowId: generateRowId(),
    customerName: '', date: '', voucherNo: '',
    businessContent: '', counterAccount: '', counterDetail: '',
    debitAmount: 0,
    creditAmount: isPeriod ? 0 : undefined, supportDocs: '',
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

/**
 * 共享回填函数的待写入项 → 凭证检查行（spec voucher-identity-writeback-and-audit-phase 任务 10）：
 * 客户名称取辅助明细账往来单位（经语义门控，匹配不到留空），对方科目取后端配对结果（配不上写「多科目」），
 * 对方明细写对方科目名称，金额落在样本自己的借贷栏。原宿主把对方科目写进客户名称、按对方分录展开并翻转金额，已删除。
 */
export function mapPreparedToD7Row(item: PreparedItem, isPost = false): VoucherCheckRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null }
  return {
    ...createEmptyRow(!isPost),
    customerName: partyNameForColumn(s as never, 'customer'),
    date: String(s.voucherDate ?? ''),
    voucherNo: String(s.voucherNo ?? ''),
    businessContent: String(s.summary ?? ''),
    counterAccount: item.counterpartAccount,
    counterDetail: item.counterpartAccountName === item.counterpartAccount ? '' : item.counterpartAccountName,
    debitAmount: parseNum(item.debitAmount),
    // 期后结转区只有借方金额（上游 oo-writeback-template-parity-closure R3 批 B2），没有贷方栏
    creditAmount: isPost ? undefined : parseNum(item.creditAmount),
  }
}

/** 行上是否已填核对结果 / 文件 / 备注 / 异常（替换 / 撤销前先确认） */
export function hasD7RowContent(r: VoucherCheckRow): boolean {
  return (r.checkItems ?? []).some(Boolean) || r.isAbnormal
    || [r.supportDocs, r.indexRef, r.remark].some(v => String(v ?? '').trim() !== '')
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

  // ─── Rows：本期增减变动 / 期后结转（期后结转区只有借方金额，旧行的贷方金额经 postTransferAmount 读） ───

  const periodChangeRows = ref<VoucherCheckRow[]>([])
  const postTransferRows = ref<VoucherCheckRow[]>([])

  /** 已在某区块的分录（按指纹）：再次回填 / 挂凭导入仍进那一区块 */
  function blockHolding(lfp: string | null): 'period' | 'post' | null {
    if (!lfp) return null
    if (periodChangeRows.value.some(r => metaOf(r)?.lfp === lfp)) return 'period'
    if (postTransferRows.value.some(r => metaOf(r)?.lfp === lfp)) return 'post'
    return null
  }

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（抽凭进本期增减变动，挂凭导入按凭证日期分区）
  const voucherFill = useVoucherCheckFill<VoucherCheckRow>({
    projectId: options.projectId,
    tables: { period: periodChangeRows, post: postTransferRows },
    tableOf: (item) => {
      const held = blockHolding(item.meta.lfp)
      if (held || !item.meta.src.includes('attach')) return held
      const bs = toValue(options.bsDate) || ''
      const date = String(item.sample.voucherDate ?? '')
      // 期后结转区只有借方金额（模板 R33-R34）：期后的贷方分录不是结转，留在本期增减变动区，金额照记不丢
      return date && bs && date > bs && parseNum(item.debitAmount) !== 0 ? 'post' : 'period'
    },
    mapSampleToRow: (item, key) => mapPreparedToD7Row(item, key === 'post'),
    persist: () => Promise.all([
      options.saveImmediate(ITEM_PERIOD_ROWS, { remark: rowsJson('period') }),
      options.saveImmediate(ITEM_POST_ROWS, { remark: rowsJson('post') }),
    ]),
    hasUserContent: hasD7RowContent,
    readonly: () => !!toValue(options.isReadonly),
  })

  /** 一区块的行 JSON（年审阶段预审行按读入版本写回，防绕过） */
  function rowsJson(block: 'period' | 'post'): string {
    return block === 'period'
      ? JSON.stringify(voucherFill.guardPersist(periodChangeRows.value, 'period'))
      : JSON.stringify(voucherFill.guardPersist(postTransferRows.value, 'post'))
  }

  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedRow(block: 'period' | 'post', rowId: string): boolean {
    const row = (block === 'period' ? periodChangeRows.value : postTransferRows.value).find(r => r.rowId === rowId)
    return !!row && voucherFill.isRowLocked(row)
  }

  watch(
    () => allResponses.value.get(ITEM_PERIOD_ROWS)?.remark,
    (jsonStr) => {
      periodChangeRows.value = safeParseArray(jsonStr).map((r: any) => normalizeVoucherRow(r, true))
      voucherFill.markLoaded()
    },
    { immediate: true },
  )

  function persistPeriodRows(): void {
    debouncedSave(ITEM_PERIOD_ROWS, { remark: rowsJson('period') })
  }

  watch(
    () => allResponses.value.get(ITEM_POST_ROWS)?.remark,
    (jsonStr) => {
      postTransferRows.value = safeParseArray(jsonStr).map((r: any) => normalizeVoucherRow(r, false))
      voucherFill.markLoaded()
    },
    { immediate: true },
  )

  function persistPostRows(): void {
    debouncedSave(ITEM_POST_ROWS, { remark: rowsJson('post') })
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

  /** 期后结转借方合计 → 供crossSheet联动D7-2 */
  const postTransferDebitTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(postTransferRows.value.map(r => postTransferAmount(r))),
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
    if (lockedRow(block, rowId)) return
    if (block === 'period') {
      periodChangeRows.value = periodChangeRows.value.filter(r => r.rowId !== rowId)
      persistPeriodRows()
    } else {
      postTransferRows.value = postTransferRows.value.filter(r => r.rowId !== rowId)
      persistPostRows()
    }
  }

  function updateCell(block: 'period' | 'post', rowId: string, field: string, value: any): void {
    if (lockedRow(block, rowId)) return
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
    postTransferDebitTotal,
    addSample,
    removeSample,
    updateCell,
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

export default useD7VoucherCheck
