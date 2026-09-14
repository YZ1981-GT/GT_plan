/**
 * useD2Cutoff — 截止测试核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 16.1
 *
 * 职责：
 * - CutoffSample 类型定义（seq, invoiceNo, revenueDate, receivableDate, amount, isCutoff, conclusion, remark）
 * - samples reactive
 * - 自动截止判定 via determineCutoff(revenueDate, bsDate)
 * - cutoffCount / cutoffTotalAmount / hasCutoffIssue computed
 * - addSample / removeSample / updateCell
 *
 * Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { parseNum, determineCutoff } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CutoffSample {
  rowId: string
  seq: number                  // 序号
  invoiceNo: string            // 发票号
  revenueDate: string          // 收入确认日期
  receivableDate: string       // 应收确认日期
  amount: number               // 金额
  isCutoff: boolean            // 是否跨期（自动判定）
  conclusion: string           // 结论
  remark: string               // 备注
  source?: '自动提取' | '手动添加'  // 数据来源标记
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D2-cutoff-samples'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `ct-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptySample(seq: number): CutoffSample {
  return {
    rowId: generateRowId(),
    seq,
    invoiceNo: '',
    revenueDate: '',
    receivableDate: '',
    amount: 0,
    isCutoff: false,
    conclusion: '',
    remark: '',
    source: '手动添加',
  }
}

function parseSamples(jsonStr: string | null | undefined): CutoffSample[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, idx: number) => ({
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? (idx + 1),
      invoiceNo: raw.invoiceNo || '',
      revenueDate: raw.revenueDate || '',
      receivableDate: raw.receivableDate || '',
      amount: parseNum(raw.amount),
      isCutoff: raw.isCutoff === true,
      conclusion: raw.conclusion || '',
      remark: raw.remark || '',
      source: raw.source || undefined,
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Cutoff(options: UseD2BaseOptions) {
  const { allResponses, isReadonly, bsDate } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const samples = ref<CutoffSample[]>([])
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    samples.value = parseSamples(resp?.remark)
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      if (samples.value.length === 0) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Computed ──────────────────────────────────────────────────────────

  /** 跨期样本数量 */
  const cutoffCount: ComputedRef<number> = computed(() => {
    return samples.value.filter(s => s.isCutoff).length
  })

  /** 跨期样本金额合计 */
  const cutoffTotalAmount: ComputedRef<number> = computed(() => {
    return samples.value.filter(s => s.isCutoff).reduce((sum, s) => sum + s.amount, 0)
  })

  /** 是否存在跨期问题 */
  const hasCutoffIssue: ComputedRef<boolean> = computed(() => {
    return cutoffCount.value > 0
  })

  // ─── Auto Cutoff Judgment ──────────────────────────────────────────────

  /**
   * 自动判定截止：revenueDate > bsDate → isCutoff = true
   */
  function autoJudgeCutoff(row: CutoffSample): void {
    const bsDateStr = bsDate?.value || ''
    if (!bsDateStr || !row.revenueDate) {
      row.isCutoff = false
      return
    }
    row.isCutoff = determineCutoff(row.revenueDate, bsDateStr)
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

    const key = field as keyof CutoffSample
    if (key === 'rowId' || key === 'seq') return

    if (key === 'amount') {
      row.amount = parseNum(value)
    } else if (key === 'isCutoff') {
      row.isCutoff = value === true || value === 'true'
    } else {
      ;(row as any)[key] = String(value)
    }

    // Auto judge cutoff when revenueDate changes
    if (key === 'revenueDate') {
      autoJudgeCutoff(row)
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
    const json = JSON.stringify(samples.value)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    dispatchSaveEvent(json)
  }

  function dispatchSaveEvent(json: string): void {
    try {
      const items = [{ item_id: STORAGE_KEY, conclusion: null, remark: json }]
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
    samples,
    cutoffCount,
    cutoffTotalAmount,
    hasCutoffIssue,
    addSample,
    removeSample,
    updateCell,
    debounceSave,
  }
}

export default useD2Cutoff
