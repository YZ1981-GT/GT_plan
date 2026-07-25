/**
 * useL3VoucherCheck — L3-9 长期借款检查表（凭证级）核心逻辑 composable
 *
 * 对齐致同源模板「长期借款针对性测试底稿 L3-9」结构（2026-07 复盘重建）：
 * - 测试原因（大额/关联方/大额交易频繁/异常/其他）
 * - 记账凭证级检查行：日期/凭证编号/业务内容/对方科目/对方明细科目/借方/贷方
 *   + 支持性文件 + 核对内容①~⑤ + 索引号/是否异常/备注
 * - 检查比例：检查合计(借/贷) / 本期发生额(借=明细本期偿还合计, 贷=明细本期借入合计) / 检查比例
 * - 审计说明 + 审计结论
 *
 * 本期发生额来自 L3-2 明细表（L3-L3-2-rows）：贷方=Σ本期借入(borrowed)，借方=Σ本期归还(repaid)
 *
 * 科目：2501 长期借款（贷方/负债类）
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistResponse } from './useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface L3VoucherCheckRow {
  rowId: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterSubAccount: string
  debitAmount: number
  creditAmount: number
  supportingDoc: string
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
  indexNo: string
  abnormal: boolean
  remark: string
}

export interface L3TestReasons {
  large: boolean
  relatedParty: boolean
  frequent: boolean
  abnormal: boolean
  other: boolean
  otherText: string
}

export interface UseL3VoucherCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ROWS = 'L3-L3-9-voucher-rows'
const ITEM_CRITERIA = 'L3-L3-9-criteria'
const ITEM_NOTE = 'L3-L3-9-note'
const ITEM_CONCLUSION = 'L3-L3-9-conclusion'
const ITEM_DETAIL_ROWS = 'L3-L3-2-rows'

export const L3_CHECK_LABELS = [
  '①原始凭证齐全',
  '②记账凭证与原始凭证相符',
  '③账务处理正确',
  '④会计期间归属正确',
  '⑤其他核对事项',
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function genRowId(): string {
  return `l3vc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function normalizeRow(raw: any): L3VoucherCheckRow {
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

function createEmptyRow(): L3VoucherCheckRow {
  return normalizeRow({})
}

function safeParseRows(jsonStr: string | null | undefined): L3VoucherCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRow) : []
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL3VoucherCheck(options: UseL3VoucherCheckOptions) {
  const { allResponses, debouncedSave } = options

  // ─── 凭证检查行 ────────────────────────────────────────────────────────

  const rows = ref<L3VoucherCheckRow[]>([])

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

  const testReasons = ref<L3TestReasons>({
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

  function safeParseDetail(): any[] {
    const raw = allResponses.value.get(ITEM_DETAIL_ROWS)?.remark
    if (!raw) return []
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }

  /** 本期发生额：借方=Σ本期归还(repaid)，贷方=Σ本期借入(borrowed) */
  const periodDebitOccurrence = computed(() =>
    safeParseDetail().reduce((s, r) => s + parseNum(r.repaid), 0),
  )
  const periodCreditOccurrence = computed(() =>
    safeParseDetail().reduce((s, r) => s + parseNum(r.borrowed), 0),
  )

  const debitCheckRatio = computed(() => {
    const base = periodDebitOccurrence.value
    return base === 0 ? 0 : checkedDebitTotal.value / base
  })
  const creditCheckRatio = computed(() => {
    const base = periodCreditOccurrence.value
    return base === 0 ? 0 : checkedCreditTotal.value / base
  })

  const abnormalCount = computed(() => rows.value.filter(r => r.abnormal).length)

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
    debouncedSave(field === 'note' ? ITEM_NOTE : ITEM_CONCLUSION, { remark: value })
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
    L3_CHECK_LABELS,
  }
}

export default useL3VoucherCheck
