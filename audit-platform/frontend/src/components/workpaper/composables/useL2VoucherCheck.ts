/**
 * useL2VoucherCheck — L2-4 应付利息检查表（凭证级）核心逻辑 composable
 *
 * 对齐致同源模板「应付利息检查表L2-4」结构（2026-07 复盘重建）：
 * - 测试原因（大额/关联方/大额交易频繁/异常/其他）
 * - 记账凭证级检查行：日期/凭证编号/业务内容/对方科目/对方明细科目/借方/贷方
 *   + 支持性文件 + 核对内容①~⑤ + 索引号/是否异常/备注
 * - 检查比例：检查合计(借/贷) / 本期发生额(借=明细已付合计, 贷=明细计提合计) / 检查比例
 * - 审计说明 + 审计结论
 *
 * 本期发生额来自 L2-2 明细表（L2-L2-2-rows）：贷方=Σ本期计提(accrued)，借方=Σ本期支付(paid)
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistResponse } from './useL2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface VoucherCheckRow {
  rowId: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterSubAccount: string
  debitAmount: number
  creditAmount: number
  supportingDoc: string
  /** 核对内容①~⑤（true=已核对相符） */
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
  indexNo: string
  abnormal: boolean
  remark: string
}

/** 测试原因 */
export interface TestReasons {
  large: boolean
  relatedParty: boolean
  frequent: boolean
  abnormal: boolean
  other: boolean
  otherText: string
}

export interface UseL2VoucherCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ROWS = 'L2-L2-4-voucher-rows'
const ITEM_CRITERIA = 'L2-L2-4-criteria'
const ITEM_NOTE = 'L2-L2-4-note'
const ITEM_CONCLUSION = 'L2-L2-4-conclusion'
const ITEM_DETAIL_ROWS = 'L2-L2-2-rows'

/** 核对内容标签（对齐源模板测试内容说明） */
export const CHECK_LABELS = [
  '①原始凭证齐全',
  '②经授权批准',
  '③会计处理正确',
  '④记账凭证与原始凭证金额核对相符',
  '⑤会计期间归属正确',
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genRowId(): string {
  return `vc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function normalizeRow(raw: any): VoucherCheckRow {
  return {
    rowId: raw.rowId || genRowId(),
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterSubAccount: raw.counterSubAccount || '',
    debitAmount: parseNum(raw.debitAmount),
    creditAmount: parseNum(raw.creditAmount),
    supportingDoc: raw.supportingDoc || '',
    check1: Boolean(raw.check1),
    check2: Boolean(raw.check2),
    check3: Boolean(raw.check3),
    check4: Boolean(raw.check4),
    check5: Boolean(raw.check5),
    indexNo: raw.indexNo || '',
    abnormal: Boolean(raw.abnormal),
    remark: raw.remark || '',
  }
}

function createEmptyRow(): VoucherCheckRow {
  return normalizeRow({})
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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL2VoucherCheck(options: UseL2VoucherCheckOptions) {
  const { allResponses, saveField, debouncedSave } = options

  // ─── 凭证检查行 ────────────────────────────────────────────────────────

  const rows = ref<VoucherCheckRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  function persistRows(): void {
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function addRow(): void {
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateRow(rowId: string, field: string, value: any): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    if (field === 'debitAmount' || field === 'creditAmount') {
      ;(row as any)[field] = parseNum(value)
    } else if (field.startsWith('check') || field === 'abnormal') {
      ;(row as any)[field] = Boolean(value)
    } else {
      ;(row as any)[field] = value
    }
    const next = [...rows.value]
    next[idx] = row
    rows.value = next
    persistRows()
  }

  // ─── 测试原因 ──────────────────────────────────────────────────────────

  const testReasons = ref<TestReasons>({
    large: false, relatedParty: false, frequent: false, abnormal: false, other: false, otherText: '',
  })

  watch(
    () => allResponses.value.get(ITEM_CRITERIA)?.remark,
    (jsonStr) => {
      if (!jsonStr) return
      try {
        const p = JSON.parse(jsonStr)
        testReasons.value = {
          large: Boolean(p.large),
          relatedParty: Boolean(p.relatedParty),
          frequent: Boolean(p.frequent),
          abnormal: Boolean(p.abnormal),
          other: Boolean(p.other),
          otherText: p.otherText || '',
        }
      } catch { /* ignore */ }
    },
    { immediate: true },
  )

  function updateTestReasons(): void {
    debouncedSave(ITEM_CRITERIA, { remark: JSON.stringify(testReasons.value) })
  }

  // ─── 合计 & 检查比例 ───────────────────────────────────────────────────

  const checkedDebitTotal = computed(() => rows.value.reduce((s, r) => s + r.debitAmount, 0))
  const checkedCreditTotal = computed(() => rows.value.reduce((s, r) => s + r.creditAmount, 0))

  /** 本期发生额（来自 L2-2 明细）：借方=Σ本期支付(paid)，贷方=Σ本期计提(accrued) */
  const periodDebitOccurrence = computed(() => {
    const detail = safeParseDetail()
    return detail.reduce((s, r) => s + parseNum(r.paid), 0)
  })
  const periodCreditOccurrence = computed(() => {
    const detail = safeParseDetail()
    return detail.reduce((s, r) => s + parseNum(r.accrued), 0)
  })

  function safeParseDetail(): any[] {
    const raw = allResponses.value.get(ITEM_DETAIL_ROWS)?.remark
    if (!raw) return []
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }

  const debitCheckRatio = computed(() => {
    const base = periodDebitOccurrence.value
    return base === 0 ? 0 : checkedDebitTotal.value / base
  })
  const creditCheckRatio = computed(() => {
    const base = periodCreditOccurrence.value
    return base === 0 ? 0 : checkedCreditTotal.value / base
  })

  /** 异常行数 */
  const abnormalCount = computed(() => rows.value.filter(r => r.abnormal).length)

  /** 未完成核对的行（存在数据但核对内容未全勾） */
  const incompleteRows = computed(() =>
    rows.value.filter(r =>
      (r.debitAmount > 0 || r.creditAmount > 0)
      && !(r.check1 && r.check2 && r.check3 && r.check4 && r.check5),
    ),
  )

  // ─── 审计说明 / 结论 ────────────────────────────────────────────────────

  const auditNote = computed(() => allResponses.value.get(ITEM_NOTE)?.remark ?? '')
  const auditConclusion = computed(() => allResponses.value.get(ITEM_CONCLUSION)?.remark ?? '')

  function updateNote(field: 'note' | 'conclusion', value: string): void {
    const itemId = field === 'note' ? ITEM_NOTE : ITEM_CONCLUSION
    debouncedSave(itemId, { remark: value })
  }

  return {
    rows,
    testReasons,
    updateTestReasons,
    addRow,
    removeRow,
    updateRow,
    checkedDebitTotal,
    checkedCreditTotal,
    periodDebitOccurrence,
    periodCreditOccurrence,
    debitCheckRatio,
    creditCheckRatio,
    abnormalCount,
    incompleteRows,
    auditNote,
    auditConclusion,
    updateNote,
    CHECK_LABELS,
  }
}

export default useL2VoucherCheck
