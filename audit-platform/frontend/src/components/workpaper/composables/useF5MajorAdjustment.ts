/**
 * useF5MajorAdjustment — F5-8 主营业务成本账户中重大调整事项核查表
 *
 * 源表编制逻辑：
 *  本表是 F5-1 销售成本审定表的附表，核查营业成本账户中重大调整事项的理由是否充分。
 *  列：日期 | 凭证号 | 重大调整事项内容 | 借方 | 贷方 | 调整理由 | 理由是否充分
 *  提示：检查现金返利、实物返利是否冲减或调整存货/购货当期主营业务成本。
 *  与 F5-1 审定、F5-4 调整分录相互印证。
 */
import { computed, ref, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF5CosOfFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface UseF5MajorAdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  materiality?: Ref<number>
}

export interface MajorAdjustmentRow {
  id: string
  date: string
  voucherNo: string
  itemContent: string
  debitAmount: number
  creditAmount: number
  /** 借方 − 贷方（展示/重要性判断） */
  netAmount: number
  adjustmentReason: string
  reasonAdequate: string
}

interface StoredMajorAdjustmentRow {
  id: string
  date: string
  voucherNo: string
  itemContent: string
  debitAmount: number
  creditAmount: number
  adjustmentReason: string
  reasonAdequate: string
}

const STORAGE_KEY = 'F5-8-rows'
const NOTE_KEY = 'F5-8-audit-note'
const CONCLUSION_KEY = 'F5-8-audit-conclusion'
const LEGACY_CONCLUSION_KEY = 'F5-8-conclusion'

/** 源表默认空白行数（R14–R29） */
export const F5_MAJOR_ADJ_DEFAULT_ROWS = 16

export const F5_MAJOR_ADJ_ADEQUACY_OPTIONS = ['充分', '不充分', '待补充', '不适用'] as const

function newId(): string {
  return `f5ma-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyF5MajorAdjRow(): StoredMajorAdjustmentRow {
  return {
    id: newId(),
    date: '',
    voucherNo: '',
    itemContent: '',
    debitAmount: 0,
    creditAmount: 0,
    adjustmentReason: '',
    reasonAdequate: '',
  }
}

export function defaultF5MajorAdjRows(): StoredMajorAdjustmentRow[] {
  return Array.from({ length: F5_MAJOR_ADJ_DEFAULT_ROWS }, () => emptyF5MajorAdjRow())
}

export function migrateF5MajorAdjRows(jsonStr: string | null | undefined): StoredMajorAdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => {
      let debit = parseNum(r?.debitAmount ?? r?.debit)
      let credit = parseNum(r?.creditAmount ?? r?.credit)
      // 旧单金额模型 → 正数记借方，负数记贷方
      const single = r?.adjustmentAmount ?? r?.adjustAmount
      if (debit === 0 && credit === 0 && single != null) {
        const amt = parseNum(single)
        if (amt >= 0) debit = amt
        else credit = Math.abs(amt)
      }
      const reasonParts = [
        String(r?.adjustmentReason ?? r?.adjustReason ?? ''),
        String(r?.approvalBasis ?? ''),
      ].filter((s) => s.trim())
      return {
        id: String(r?.id ?? r?.rowId ?? `f5ma-migrated-${i}`),
        date: String(r?.date ?? r?.adjustmentDate ?? r?.adjustDate ?? ''),
        voucherNo: String(r?.voucherNo ?? ''),
        itemContent: String(
          r?.itemContent ?? r?.adjustmentItem ?? r?.adjustItem ?? r?.content ?? '',
        ),
        debitAmount: debit,
        creditAmount: credit,
        adjustmentReason: reasonParts.join('；') || String(r?.adjustmentReason ?? ''),
        reasonAdequate: String(
          r?.reasonAdequate ?? r?.auditEvaluation ?? r?.adequate ?? '',
        ),
      }
    })
  } catch {
    return []
  }
}

export function computeF5MajorAdjRow(stored: StoredMajorAdjustmentRow): MajorAdjustmentRow {
  return {
    ...stored,
    netAmount: stored.debitAmount - stored.creditAmount,
  }
}

export function useF5MajorAdjustment(options: UseF5MajorAdjustmentOptions) {
  const { allResponses, isReadonly, materiality } = options
  const readonly = isReadonly ?? ref(false)
  const materialityRef = materiality ?? ref(0)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedRows = ref<StoredMajorAdjustmentRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawJson(): string | null | undefined {
    return allResponses.value.get(STORAGE_KEY)?.remark
  }

  function loadRows(): void {
    const migrated = migrateF5MajorAdjRows(rawJson())
    storedRows.value = migrated.length ? migrated : defaultF5MajorAdjRows()
  }

  watch(() => rawJson(), (raw) => {
    if (raw && raw === lastPersisted) return
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

  const rows: ComputedRef<MajorAdjustmentRow[]> = computed(() =>
    storedRows.value.map(computeF5MajorAdjRow),
  )

  const totalDebit = computed(() => calcSubtotal(storedRows.value.map((r) => r.debitAmount)))
  const totalCredit = computed(() => calcSubtotal(storedRows.value.map((r) => r.creditAmount)))
  const filledCount = computed(() =>
    storedRows.value.filter((r) =>
      r.itemContent.trim() || r.voucherNo.trim() || r.debitAmount || r.creditAmount,
    ).length,
  )

  const inadequateCount = computed(() =>
    rows.value.filter((r) => {
      if (!r.itemContent.trim() && !r.debitAmount && !r.creditAmount) return false
      const a = r.reasonAdequate.trim()
      return !a || a === '不充分' || a === '待补充'
    }).length,
  )

  function exceedsMateriality(row: MajorAdjustmentRow): boolean {
    const m = materialityRef.value
    if (m <= 0) return false
    return Math.abs(row.netAmount) > m || Math.max(row.debitAmount, row.creditAmount) > m
  }

  const exceedCount = computed(() => rows.value.filter(exceedsMateriality).length)

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
    if (key === 'debitAmount' || key === 'creditAmount') {
      ;(row as any)[key] = parseNum(value)
    } else if ([
      'date', 'voucherNo', 'itemContent', 'adjustmentReason', 'reasonAdequate',
    ].includes(key)) {
      ;(row as any)[key] = String(value ?? '')
    }
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    storedRows.value.push(emptyF5MajorAdjRow())
    persist()
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const next = storedRows.value.filter((r) => r.id !== id)
    storedRows.value = next.length ? next : defaultF5MajorAdjRows()
    persist()
  }

  /** 抽凭样本填入（借方/贷方按样本金额拆分） */
  function mergeSamplingRows(samples: Array<Record<string, any>>): number {
    if (readonly.value || !samples.length) return 0
    const mapped = samples.map((s) => {
      const debit = parseNum(s.debit_amount ?? s.debitAmount)
      const credit = parseNum(s.credit_amount ?? s.creditAmount)
      let d = debit
      let c = credit
      if (d === 0 && c === 0) {
        const amt = parseNum(s.amount)
        if (amt >= 0) d = amt
        else c = Math.abs(amt)
      }
      return {
        ...emptyF5MajorAdjRow(),
        date: String(s.voucher_date ?? s.date ?? ''),
        voucherNo: String(s.voucher_no ?? s.voucherNo ?? ''),
        itemContent: String(s.summary ?? s.abstract ?? '重大成本调整'),
        debitAmount: d,
        creditAmount: c,
      }
    })
    const emptyOnly = storedRows.value.every(
      (r) => !r.itemContent.trim() && !r.voucherNo.trim() && !r.debitAmount && !r.creditAmount,
    )
    storedRows.value = emptyOnly ? mapped : [...storedRows.value, ...mapped]
    persist()
    return mapped.length
  }

  function isRowHighlighted(row: MajorAdjustmentRow): boolean {
    if (exceedsMateriality(row)) return true
    const a = row.reasonAdequate.trim()
    if ((row.itemContent.trim() || row.debitAmount || row.creditAmount)
      && (!a || a === '不充分' || a === '待补充')) {
      return true
    }
    return false
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
    totalDebit,
    totalCredit,
    filledCount,
    inadequateCount,
    exceedCount,
    auditNote,
    auditConclusion,
    updateCell,
    addRow,
    removeRow,
    mergeSamplingRows,
    exceedsMateriality,
    isRowHighlighted,
    saveAuditNote,
    saveAuditConclusion,
    loadRows,
  }
}

export default useF5MajorAdjustment
