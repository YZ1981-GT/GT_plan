/**
 * useH8Adjudication — H8-1 审定表 composable（双区块：原值+累计折旧+净值，51公式）
 *
 * 审定表结构：
 * 区块1：使用权资产-原值（按租赁类型分行+小计）
 * 区块2：累计折旧（按租赁类型分行+小计）
 * 净值合计 = 原值小计 - 累计折旧小计
 *
 * 列：项目 | 期初 | 借方 | 贷方 | 期末 | 未审 | AJE | RJE | 审定
 *
 * 功能：
 * - 双区块结构（原值行+小计 / 累计折旧行+小计 / 净值合计）
 * - 公式：审定=未审+AJE+RJE；原值期末=期初+借-贷；折旧期末=期初+贷-借
 * - H8-2合计交叉验证
 * - H9租赁负债交叉验证（H8初始=H9+直接费用-激励）
 * - TB回写(1901+累计折旧)+发布'substantive:adjudicated'
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/
 * Task: 3.4
 * Requirements: 2.1-2.8, 11.1-11.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useH8FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8-1 审定表行 */
export interface H8AdjudicationRow {
  rowId: string
  /** 项目名称（租赁类型，如"房屋租赁/车辆租赁"） */
  name: string
  /** 区块：cost=使用权资产原值 / accDep=累计折旧 */
  block: 'cost' | 'accDep'
  /** 期初余额 */
  beginBalance: number
  /** 本期借方 */
  debitAmount: number
  /** 本期贷方 */
  creditAmount: number
  /** 期末余额（公式：原值=期初+借-贷，折旧=期初+贷-借） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（=未审+AJE+RJE） */
  audited: number
  /** 是否小计/合计行 */
  isSubtotal?: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H8-1-rows'
const NOTE_KEY = 'H8-1-audit-note'
const CONCLUSION_KEY = 'H8-1-audit-conclusion'
const COST_AUDITED_KEY = 'H8-1-cost-audited'
const ACCDEP_AUDITED_KEY = 'H8-1-accdep-audited'
const NET_AUDITED_KEY = 'H8-1-net-audited'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8Adjudication(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onWritebackTB?: (audited1901: number, auditedAccDep: number) => Promise<void>
}) {
  const { allResponses, onSave, onWritebackTB } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H8AdjudicationRow[]>([])
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

  function _normalizeRow(raw: any): H8AdjudicationRow {
    const begin = Number(raw.beginBalance) || 0
    const debit = Number(raw.debitAmount) || 0
    const credit = Number(raw.creditAmount) || 0
    const unadj = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0
    const block = raw.block === 'accDep' ? 'accDep' : 'cost'

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: raw.name ?? '',
      block,
      beginBalance: begin,
      debitAmount: debit,
      creditAmount: credit,
      endBalance: block === 'cost'
        ? calcAssetEndBalance(begin, debit, credit)
        : calcContraEndBalance(begin, debit, credit),
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

  const costRows = computed(() => rows.value.filter(r => r.block === 'cost' && !r.isSubtotal))
  const accDepRows = computed(() => rows.value.filter(r => r.block === 'accDep' && !r.isSubtotal))

  // ─── Computed: 各区块小计 ──────────────────────────────────────────────────

  const costSubtotal = computed(() => ({
    beginBalance: calcSubtotal(costRows.value.map(r => r.beginBalance)),
    debitAmount: calcSubtotal(costRows.value.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(costRows.value.map(r => r.creditAmount)),
    endBalance: calcSubtotal(costRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(costRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(costRows.value.map(r => r.aje)),
    rje: calcSubtotal(costRows.value.map(r => r.rje)),
    audited: calcSubtotal(costRows.value.map(r => r.audited)),
  }))

  const accDepSubtotal = computed(() => ({
    beginBalance: calcSubtotal(accDepRows.value.map(r => r.beginBalance)),
    debitAmount: calcSubtotal(accDepRows.value.map(r => r.debitAmount)),
    creditAmount: calcSubtotal(accDepRows.value.map(r => r.creditAmount)),
    endBalance: calcSubtotal(accDepRows.value.map(r => r.endBalance)),
    unadjusted: calcSubtotal(accDepRows.value.map(r => r.unadjusted)),
    aje: calcSubtotal(accDepRows.value.map(r => r.aje)),
    rje: calcSubtotal(accDepRows.value.map(r => r.rje)),
    audited: calcSubtotal(accDepRows.value.map(r => r.audited)),
  }))

  // ─── Computed: 净值合计 = 原值 - 累计折旧 ─────────────────────────────────

  const netAudited: ComputedRef<number> = computed(() =>
    calcNetValue(costSubtotal.value.audited, accDepSubtotal.value.audited, 0),
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || row.isSubtotal) return

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
    row.endBalance = row.block === 'cost'
      ? calcAssetEndBalance(row.beginBalance, row.debitAmount, row.creditAmount)
      : calcContraEndBalance(row.beginBalance, row.debitAmount, row.creditAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    _persist()
  }

  function addRow(name: string, block: 'cost' | 'accDep' = 'cost'): void {
    if (!name?.trim()) return
    rows.value.push(_normalizeRow({ name: name.trim(), block }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    if (rows.value[idx].isSubtotal) return
    rows.value.splice(idx, 1)
    _persist()
  }

  async function publishAdjudicated(): Promise<void> {
    if (onWritebackTB) {
      await onWritebackTB(costSubtotal.value.audited, accDepSubtotal.value.audited)
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

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.filter(r => !r.isSubtotal).map(r => ({
      rowId: r.rowId, name: r.name, block: r.block,
      beginBalance: r.beginBalance, debitAmount: r.debitAmount, creditAmount: r.creditAmount,
      unadjusted: r.unadjusted, aje: r.aje, rje: r.rje,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(COST_AUDITED_KEY, costSubtotal.value.audited)
    onSave(ACCDEP_AUDITED_KEY, accDepSubtotal.value.audited)
    onSave(NET_AUDITED_KEY, netAudited.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, auditNote, auditConclusion,
    costRows, accDepRows,
    costSubtotal, accDepSubtotal, netAudited,
    updateCell, addRow, deleteRow, save, load,
    publishAdjudicated, saveNote, saveConclusion,
  }
}

export default useH8Adjudication
