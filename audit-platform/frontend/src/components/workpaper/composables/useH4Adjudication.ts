/**
 * useH4Adjudication — H4-1 审定表 composable
 *
 * 审定表结构（三段：原值/减值/净值，每段5个分类行+合计）：
 * 项目 | 期初余额 | 本期借方发生(增加) | 本期贷方发生(减少) | 期末余额 | 未审数 | AJE | RJE | 审定数
 *
 * 功能：
 * - 三段结构（原值5行+小计 / 减值5行+小计 / 净值合计）
 * - 公式：审定=未审+AJE+RJE；期末=期初+借方-贷方（资产类1605）
 * - 合计行自动SUM（不可编辑）
 * - TB取数（科目1605） + TB回写
 * - 跨sheet发布 adjudicatedTotal / debitTotal / creditTotal
 * - Saves to allResponses with prefix "H4-1-"
 *
 * Spec: .kiro/specs/h4-engineering-materials/
 * Task: 3.4
 * Requirements: 2.1-2.10
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcAuditedAmount, calcAssetEndBalance, calcSubtotal } from './useH4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4-1 审定表行 */
export interface H4AdjudicationRow {
  rowId: string
  /** 物资分类名称 */
  name: string
  /** 段标记：original=原值 / impairment=减值 / net=净值 */
  section: 'original' | 'impairment' | 'net'
  /** 期初余额 */
  beginBalance: number
  /** 本期借方发生（增加） */
  debitAmount: number
  /** 本期贷方发生（减少） */
  creditAmount: number
  /** 期末余额（公式：=期初+借方-贷方） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式：=未审+AJE+RJE） */
  audited: number
  /** 是否小计行 */
  isSubtotal?: boolean
  /** 是否合计行 */
  isTotal?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H4-1-rows'
const NOTE_KEY = 'H4-1-audit-note'
const CONCLUSION_KEY = 'H4-1-audit-conclusion'
const ADJUDICATED_TOTAL_KEY = 'H4-1-adjudicated-total'
const DEBIT_TOTAL_KEY = 'H4-1-debit-total'
const CREDIT_TOTAL_KEY = 'H4-1-credit-total'
const BEGIN_TOTAL_KEY = 'H4-1-begin-total'
const END_TOTAL_KEY = 'H4-1-end-total'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  tbData?: Ref<{ unadjusted1605: number; audited1605: number }>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (auditedAmount: number) => Promise<void>
}) {
  const { allResponses, onSave, onWritebackTB, tbData } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H4AdjudicationRow[]>([])
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

  /** 规范化行（从 JSON 加载后重算公式列） */
  function _normalizeRow(raw: any): H4AdjudicationRow {
    const begin = Number(raw.beginBalance) || 0
    const debit = Number(raw.debitAmount) || 0
    const credit = Number(raw.creditAmount) || 0
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: raw.name ?? '',
      section: raw.section ?? 'original',
      beginBalance: begin,
      debitAmount: debit,
      creditAmount: credit,
      endBalance: calcAssetEndBalance(begin, debit, credit),
      unadjusted: unadj,
      aje,
      rje,
      audited: calcAuditedAmount(unadj, aje, rje),
      isSubtotal: raw.isSubtotal ?? false,
      isTotal: raw.isTotal ?? false,
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

  // ─── Computed: 明细行（按段） ──────────────────────────────────────────────

  const originalRows = computed(() => rows.value.filter(r => r.section === 'original' && !r.isSubtotal && !r.isTotal))
  const impairmentRows = computed(() => rows.value.filter(r => r.section === 'impairment' && !r.isSubtotal && !r.isTotal))

  // ─── Computed: 各段小计 ────────────────────────────────────────────────────

  const originalSubtotal = computed(() => ({
    beginBalance: calcSubtotal(originalRows.value.map(r => r.beginBalance)),
    debitAmount: calcSubtotal(originalRows.value.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(originalRows.value.map(r => r.creditAmount)),
    endBalance: calcSubtotal(originalRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(originalRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(originalRows.value.map(r => r.aje)),
    rje: calcSubtotal(originalRows.value.map(r => r.rje)),
    audited: calcSubtotal(originalRows.value.map(r => r.audited)),
  }))

  const impairmentSubtotal = computed(() => ({
    beginBalance: calcSubtotal(impairmentRows.value.map(r => r.beginBalance)),
    debitAmount: calcSubtotal(impairmentRows.value.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(impairmentRows.value.map(r => r.creditAmount)),
    endBalance: calcSubtotal(impairmentRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(impairmentRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(impairmentRows.value.map(r => r.aje)),
    rje: calcSubtotal(impairmentRows.value.map(r => r.rje)),
    audited: calcSubtotal(impairmentRows.value.map(r => r.audited)),
  }))

  // ─── Computed: 净值合计 = 原值 - 减值 ─────────────────────────────────────

  const netTotal = computed(() => ({
    beginBalance: originalSubtotal.value.beginBalance - impairmentSubtotal.value.beginBalance,
    debitAmount: originalSubtotal.value.debitAmount - impairmentSubtotal.value.debitAmount,
    creditAmount: originalSubtotal.value.creditAmount - impairmentSubtotal.value.creditAmount,
    endBalance: originalSubtotal.value.endBalance - impairmentSubtotal.value.endBalance,
    unadjusted: originalSubtotal.value.unadjusted - impairmentSubtotal.value.unadjusted,
    aje: originalSubtotal.value.aje - impairmentSubtotal.value.aje,
    rje: originalSubtotal.value.rje - impairmentSubtotal.value.rje,
    audited: originalSubtotal.value.audited - impairmentSubtotal.value.audited,
  }))

  // ─── CrossSheet 发布值 ─────────────────────────────────────────────────────

  /** 审定数合计（供CrossSheet使用） */
  const adjudicatedTotal: ComputedRef<number> = computed(() => netTotal.value.audited)
  /** 借方发生合计 */
  const debitTotal: ComputedRef<number> = computed(() => originalSubtotal.value.debitAmount)
  /** 贷方发生合计 */
  const creditTotal: ComputedRef<number> = computed(() => originalSubtotal.value.creditAmount)

  // ─── TB取数行 ──────────────────────────────────────────────────────────────

  const tbUnadjusted = computed(() => tbData?.value?.unadjusted1605 ?? 0)
  const tbAudited = computed(() => tbData?.value?.audited1605 ?? 0)
  const tbDiff = computed(() => adjudicatedTotal.value - tbAudited.value)
  const isTbMatch = computed(() => Math.abs(tbDiff.value) < 0.01)

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || row.isSubtotal || row.isTotal) return

    const numVal = Number(value) || 0

    switch (field) {
      case 'name': row.name = String(value ?? ''); break
      case 'beginBalance': row.beginBalance = numVal; break
      case 'debitAmount': row.debitAmount = numVal; break
      case 'creditAmount': row.creditAmount = numVal; break
      case 'unadjusted': row.unadjusted = numVal; break
      case 'aje': row.aje = numVal; break
      case 'rje': row.rje = numVal; break
      default: return
    }

    // 重算公式列
    row.endBalance = calcAssetEndBalance(row.beginBalance, row.debitAmount, row.creditAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    _persist()
  }

  function addRow(name: string, section: 'original' | 'impairment' = 'original'): void {
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim(), section }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const row = rows.value[idx]
    if (row.isSubtotal || row.isTotal) return
    rows.value.splice(idx, 1)
    _persist()
  }

  /** 审定数回写TB + EventBus */
  async function publishAdjudicated(): Promise<void> {
    if (onWritebackTB) {
      await onWritebackTB(adjudicatedTotal.value)
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value
      .filter(r => !r.isSubtotal && !r.isTotal)
      .map(r => ({
        rowId: r.rowId,
        name: r.name,
        section: r.section,
        beginBalance: r.beginBalance,
        debitAmount: r.debitAmount,
        creditAmount: r.creditAmount,
        unadjusted: r.unadjusted,
        aje: r.aje,
        rje: r.rje,
      }))
    onSave(ROWS_KEY, toPersist)

    // 同步写入汇总值（供CrossSheet读取）
    onSave(ADJUDICATED_TOTAL_KEY, adjudicatedTotal.value)
    onSave(DEBIT_TOTAL_KEY, debitTotal.value)
    onSave(CREDIT_TOTAL_KEY, creditTotal.value)
    onSave(BEGIN_TOTAL_KEY, netTotal.value.beginBalance)
    onSave(END_TOTAL_KEY, netTotal.value.endBalance)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    auditNote,
    auditConclusion,
    // Computed — 分段
    originalRows,
    impairmentRows,
    originalSubtotal,
    impairmentSubtotal,
    netTotal,
    // Computed — CrossSheet
    adjudicatedTotal,
    debitTotal,
    creditTotal,
    // Computed — TB
    tbUnadjusted,
    tbAudited,
    tbDiff,
    isTbMatch,
    // Actions
    updateCell,
    addRow,
    deleteRow,
    save,
    load,
    publishAdjudicated,
    saveNote,
    saveConclusion,
  }
}

export default useH4Adjudication
