/**
 * useD2VoucherCheck — 凭证抽查D2-7核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 11.1
 *
 * 职责：
 * - SamplingParams 类型 + VoucherSampleRow 类型（17列）
 * - params reactive, samples reactive
 * - progress computed (current/target/ratio)
 * - abnormalCount / abnormalRate computed
 * - autoMarkCutoff (determineCutoff 自动标记跨期)
 * - addSample / removeSample / updateCell
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { parseNum, determineCutoff } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SamplingParams {
  method: string               // 抽样方法（随机/分层/特定项目）
  populationSize: number       // 总体规模
  sampleSize: number           // 样本量
  startDate: string            // 抽样期间起始
  endDate: string              // 抽样期间截止
  seed: string                 // 随机种子
}

export interface VoucherSampleRow {
  rowId: string
  seq: number                  // 序号
  voucherNo: string            // 凭证号
  voucherDate: string          // 凭证日期
  amount: number               // 金额
  counterparty: string         // 交易对手
  abstract: string             // 摘要
  accountName: string          // 科目
  attachmentCount: number      // 附件数量
  hasOriginal: string          // 有无原始凭证 (Y/N)
  amountConsistent: string     // 金额一致 (Y/N)
  dateConsistent: string       // 日期一致 (Y/N)
  revenueDate: string          // 收入确认日期
  isCutoff: boolean            // 是否跨期（自动判定）
  customerConfirm: string      // 客户确认
  agingVerify: string          // 账龄核实
  abnormalFlag: string         // 异常标记 (Y/N/'')
  conclusion: string           // 结论
  indexRef: string             // 索引号
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PARAMS_KEY = 'D2-voucher-params'
const SAMPLES_KEY = 'D2-voucher-samples'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `vc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createDefaultParams(): SamplingParams {
  return {
    method: '随机',
    populationSize: 0,
    sampleSize: 0,
    startDate: '',
    endDate: '',
    seed: '',
  }
}

function createEmptySample(seq: number): VoucherSampleRow {
  return {
    rowId: generateRowId(),
    seq,
    voucherNo: '',
    voucherDate: '',
    amount: 0,
    counterparty: '',
    abstract: '',
    accountName: '',
    attachmentCount: 0,
    hasOriginal: '',
    amountConsistent: '',
    dateConsistent: '',
    revenueDate: '',
    isCutoff: false,
    customerConfirm: '',
    agingVerify: '',
    abnormalFlag: '',
    conclusion: '',
    indexRef: '',
  }
}

function parseParams(jsonStr: string | null | undefined): SamplingParams {
  if (!jsonStr) return createDefaultParams()
  try {
    const parsed = JSON.parse(jsonStr)
    return {
      method: parsed.method || '随机',
      populationSize: parseNum(parsed.populationSize),
      sampleSize: parseNum(parsed.sampleSize),
      startDate: parsed.startDate || '',
      endDate: parsed.endDate || '',
      seed: parsed.seed || '',
    }
  } catch {
    return createDefaultParams()
  }
}

function parseSamples(jsonStr: string | null | undefined): VoucherSampleRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, idx: number) => ({
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? (idx + 1),
      voucherNo: raw.voucherNo || '',
      voucherDate: raw.voucherDate || '',
      amount: parseNum(raw.amount),
      counterparty: raw.counterparty || '',
      abstract: raw.abstract || '',
      accountName: raw.accountName || '',
      attachmentCount: parseNum(raw.attachmentCount),
      hasOriginal: raw.hasOriginal || '',
      amountConsistent: raw.amountConsistent || '',
      dateConsistent: raw.dateConsistent || '',
      revenueDate: raw.revenueDate || '',
      isCutoff: raw.isCutoff === true,
      customerConfirm: raw.customerConfirm || '',
      agingVerify: raw.agingVerify || '',
      abnormalFlag: raw.abnormalFlag || '',
      conclusion: raw.conclusion || '',
      indexRef: raw.indexRef || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2VoucherCheck(options: UseD2BaseOptions) {
  const { allResponses, isReadonly, bsDate } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const params = ref<SamplingParams>(createDefaultParams())
  const samples = ref<VoucherSampleRow[]>([])
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const paramsResp = allResponses.value.get(PARAMS_KEY)
    params.value = parseParams(paramsResp?.remark)

    const samplesResp = allResponses.value.get(SAMPLES_KEY)
    samples.value = parseSamples(samplesResp?.remark)
  }

  watch(
    () => [
      allResponses.value.get(PARAMS_KEY)?.remark,
      allResponses.value.get(SAMPLES_KEY)?.remark,
    ],
    () => {
      if (samples.value.length === 0) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Progress ──────────────────────────────────────────────────────────

  const progress: ComputedRef<{ current: number; target: number; ratio: number }> = computed(() => {
    const current = samples.value.length
    const target = params.value.sampleSize
    const ratio = target > 0 ? current / target : 0
    return { current, target, ratio }
  })

  // ─── Abnormal Count & Rate ─────────────────────────────────────────────

  const abnormalCount: ComputedRef<number> = computed(() => {
    return samples.value.filter(s => s.abnormalFlag === 'Y').length
  })

  const abnormalRate: ComputedRef<number> = computed(() => {
    const total = samples.value.length
    if (total === 0) return 0
    return abnormalCount.value / total
  })

  // ─── Auto Mark Cutoff ──────────────────────────────────────────────────

  /**
   * 自动标记跨期：凭证日期 vs 收入确认日期跨越资产负债表日
   */
  function autoMarkCutoff(rowId: string): void {
    if (isReadonly.value) return
    const row = samples.value.find(r => r.rowId === rowId)
    if (!row) return

    const bsDateStr = bsDate?.value || ''
    if (!bsDateStr || !row.revenueDate) return

    row.isCutoff = determineCutoff(row.revenueDate, bsDateStr)
    debounceSave()
  }

  /**
   * 批量自动判定所有样本的跨期标记
   */
  function autoMarkAllCutoff(): void {
    if (isReadonly.value) return
    const bsDateStr = bsDate?.value || ''
    if (!bsDateStr) return

    let changed = false
    for (const row of samples.value) {
      if (row.revenueDate) {
        const result = determineCutoff(row.revenueDate, bsDateStr)
        if (row.isCutoff !== result) {
          row.isCutoff = result
          changed = true
        }
      }
    }
    if (changed) {
      debounceSave()
    }
  }

  // ─── Row Management ────────────────────────────────────────────────────

  function addSample(): void {
    if (isReadonly.value) return
    const seq = samples.value.length + 1
    samples.value.push(createEmptySample(seq))
    debounceSave()
  }

  function removeSample(rowId: string): void {
    if (isReadonly.value) return
    const idx = samples.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    samples.value.splice(idx, 1)
    // Re-sequence
    samples.value.forEach((r, i) => { r.seq = i + 1 })
    debounceSave()
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const row = samples.value.find(r => r.rowId === rowId)
    if (!row) return

    const key = field as keyof VoucherSampleRow
    if (key === 'rowId' || key === 'seq') return

    if (key === 'amount' || key === 'attachmentCount') {
      ;(row as any)[key] = parseNum(value)
    } else if (key === 'isCutoff') {
      row.isCutoff = value === true || value === 'true'
    } else {
      ;(row as any)[key] = String(value)
    }

    // Auto-check cutoff when revenueDate changes
    if (key === 'revenueDate') {
      autoMarkCutoff(rowId)
    }

    debounceSave()
  }

  /**
   * 更新抽样参数
   */
  function updateParams(field: keyof SamplingParams, value: any): void {
    if (isReadonly.value) return

    if (field === 'populationSize' || field === 'sampleSize') {
      ;(params.value as any)[field] = parseNum(value)
    } else {
      ;(params.value as any)[field] = String(value)
    }
    debounceSave()
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items = [
      { item_id: PARAMS_KEY, conclusion: null, remark: JSON.stringify(params.value) },
      { item_id: SAMPLES_KEY, conclusion: null, remark: JSON.stringify(samples.value) },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    dispatchSaveEvent(items)
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    params,
    samples,
    progress,
    abnormalCount,
    abnormalRate,
    addSample,
    removeSample,
    updateCell,
    updateParams,
    autoMarkCutoff,
    autoMarkAllCutoff,
  }
}

export default useD2VoucherCheck
