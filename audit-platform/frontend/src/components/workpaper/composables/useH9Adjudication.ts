/**
 * useH9Adjudication — H9-1 审定表 composable（3段：原值+未确认融资费用+净值）
 *
 * 审定表结构：
 * 区块1：租赁负债-原值（贷方/负债类，按合同类型+小计）
 * 区块2：未确认融资费用（借方/负债备抵类）
 * 净值合计 = 原值小计 - 未确认融资费用小计
 *
 * 列：项目 | 期初 | 贷方(增加) | 借方(减少) | 期末 | 未审 | AJE | RJE | 审定
 *
 * ⚠️ CRITICAL: 负债类贷方科目 期末=期初+贷方-借方
 *              备抵类借方科目 期末=期初+借方-贷方
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.4
 * Requirements: 2.1-2.8
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcContraLiabilityEndBalance,
  calcNetLiability,
  calcSubtotal,
} from './useH9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9-1 审定表行 */
export interface H9AdjudicationRow {
  rowId: string
  /** 项目名称 */
  name: string
  /** 区块：liability=租赁负债原值(贷方) / unearned=未确认融资费用(借方备抵) */
  block: 'liability' | 'unearned'
  /** 期初余额 */
  beginBalance: number
  /** 贷方发生额(负债增加)/借方发生额(备抵增加) */
  creditAmount: number
  /** 借方发生额(负债减少)/贷方发生额(备抵减少=摊销确认) */
  debitAmount: number
  /** 期末余额（公式计算） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（=未审+AJE+RJE） */
  audited: number
  /** 是否小计行 */
  isSubtotal?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H9-1-rows'
const NOTE_KEY = 'H9-1-audit-note'
const CONCLUSION_KEY = 'H9-1-audit-conclusion'
const LIABILITY_AUDITED_KEY = 'H9-1-liability-audited'
const UNEARNED_AUDITED_KEY = 'H9-1-unearned-audited'
const NET_AUDITED_KEY = 'H9-1-net-audited'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedLiability: number, auditedUnearned: number) => Promise<void>
}) {
  const { allResponses, onSave, onWritebackTB } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H9AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): H9AdjudicationRow {
    const begin = Number(raw.beginBalance) || 0
    const credit = Number(raw.creditAmount) || 0
    const debit = Number(raw.debitAmount) || 0
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0
    const block = raw.block === 'unearned' ? 'unearned' : 'liability'

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: raw.name ?? '',
      block,
      beginBalance: begin,
      creditAmount: credit,
      debitAmount: debit,
      endBalance: block === 'liability'
        ? calcLiabilityEndBalance(begin, credit, debit)
        : calcContraLiabilityEndBalance(begin, debit, credit),
      unadjusted: unadj,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
      isSubtotal: raw.isSubtotal ?? false,
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function load(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 分区块行 ────────────────────────────────────────────────────

  const liabilityRows = computed(() => rows.value.filter(r => r.block === 'liability' && !r.isSubtotal))
  const unearnedRows = computed(() => rows.value.filter(r => r.block === 'unearned' && !r.isSubtotal))

  // ─── Computed: 各区块小计 ──────────────────────────────────────────────────

  const liabilitySubtotal = computed(() => ({
    beginBalance: calcSubtotal(liabilityRows.value.map(r => r.beginBalance)),
    creditAmount: calcSubtotal(liabilityRows.value.map(r => r.creditAmount)),
    debitAmount: calcSubtotal(liabilityRows.value.map(r => r.debitAmount)),
    endBalance: calcSubtotal(liabilityRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(liabilityRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(liabilityRows.value.map(r => r.aje)),
    rje: calcSubtotal(liabilityRows.value.map(r => r.rje)),
    audited: calcSubtotal(liabilityRows.value.map(r => r.audited)),
  }))

  const unearnedSubtotal = computed(() => ({
    beginBalance: calcSubtotal(unearnedRows.value.map(r => r.beginBalance)),
    creditAmount: calcSubtotal(unearnedRows.value.map(r => r.creditAmount)),
    debitAmount: calcSubtotal(unearnedRows.value.map(r => r.debitAmount)),
    endBalance: calcSubtotal(unearnedRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(unearnedRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(unearnedRows.value.map(r => r.aje)),
    rje: calcSubtotal(unearnedRows.value.map(r => r.rje)),
    audited: calcSubtotal(unearnedRows.value.map(r => r.audited)),
  }))

  // ─── Computed: 净值 = 原值 - 未确认融资费用 ────────────────────────────────

  const netAudited: ComputedRef<number> = computed(() =>
    calcNetLiability(liabilitySubtotal.value.audited, unearnedSubtotal.value.audited),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || row.isSubtotal) return

    const numVal = Number(value) || 0
    switch (field) {
      case 'name': row.name = String(value ?? ''); break
      case 'beginBalance': row.beginBalance = numVal; break
      case 'creditAmount': row.creditAmount = numVal; break
      case 'debitAmount': row.debitAmount = numVal; break
      case 'unadjusted': row.unadjusted = numVal; break
      case 'aje': row.aje = numVal; break
      case 'rje': row.rje = numVal; break
      default: return
    }
    row.endBalance = row.block === 'liability'
      ? calcLiabilityEndBalance(row.beginBalance, row.creditAmount, row.debitAmount)
      : calcContraLiabilityEndBalance(row.beginBalance, row.debitAmount, row.creditAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
  }

  function addRow(name: string, block: 'liability' | 'unearned' = 'liability'): void {
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim(), block }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1 || rows.value[idx].isSubtotal) return
    rows.value.splice(idx, 1)
    _persist()
  }

  async function publishAdjudicated(): Promise<void> {
    if (onWritebackTB) {
      await onWritebackTB(liabilitySubtotal.value.audited, unearnedSubtotal.value.audited)
    }
    // Dispatch EventBus 'substantive:adjudicated' to notify other workpapers (附注/H8/报表)
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'H9',
        accountCode: '2205',
        auditedAmount: liabilitySubtotal.value.audited,
        auditedAmountFinanceCost: unearnedSubtotal.value.audited,
      },
    }))
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(CONCLUSION_KEY, conclusion)
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.filter(r => !r.isSubtotal).map(r => ({
      rowId: r.rowId, name: r.name, block: r.block,
      beginBalance: r.beginBalance, creditAmount: r.creditAmount, debitAmount: r.debitAmount,
      unadjusted: r.unadjusted, aje: r.aje, rje: r.rje,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(LIABILITY_AUDITED_KEY, liabilitySubtotal.value.audited)
    onSave(UNEARNED_AUDITED_KEY, unearnedSubtotal.value.audited)
    onSave(NET_AUDITED_KEY, netAudited.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, auditNote, auditConclusion,
    liabilityRows, unearnedRows,
    liabilitySubtotal, unearnedSubtotal, netAudited,
    updateCell, addRow, deleteRow, save, load,
    publishAdjudicated, saveNote, saveConclusion,
  }
}

export default useH9Adjudication
