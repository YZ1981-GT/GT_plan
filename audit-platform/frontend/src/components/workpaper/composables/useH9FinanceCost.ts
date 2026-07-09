/**
 * useH9FinanceCost — H9-3 未确认融资费用明细表 composable（21列，联动H9-2）
 *
 * 未确认融资费用是负债备抵科目（借方余额）：
 * A出租方(readonly,联动H9-2) | B期初 | C本期增加(借方) | D本期确认(贷方,转为利息费用)
 * E期末=B+C-D (借方备抵！)
 * F~I审定调整 | J~M审定后(J=B, K=C+F+H, L=D+G+I, M=J+K-L)
 * N重分类 | O最终=M-N
 * P~S其他列(合同号/对应利息期/备注)
 * T关联方(是/否)
 *
 * ⚠️ 借方备抵科目：E=B+C-D（期末=期初+借方增加-贷方减少）
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.4
 * Requirements: 3.4-3.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcContraLiabilityEndBalance, calcSubtotal } from './useH9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9-3 未确认融资费用明细行 */
export interface H9FinanceCostRow {
  rowId: string
  /** A: 出租方（联动H9-2，只读） */
  lessor: string
  /** P: 合同号 */
  contractNo: string
  /** B: 期初余额 */
  beginBalance: number
  /** C: 本期增加(借方，新租赁) */
  debitIncrease: number
  /** D: 本期确认(贷方，摊销转利息) */
  creditDecrease: number
  /** E: 期末=B+C-D (借方备抵!) */
  endBalance: number
  /** F: 期初AJE */
  beginAje: number
  /** G: 确认AJE */
  confirmAje: number
  /** H: 增加AJE */
  increaseAje: number
  /** I: 其他AJE */
  otherAje: number
  /** J: 审定期初=B (无调整) */
  auditedBegin: number
  /** K: 审定增加=C+F+H */
  auditedIncrease: number
  /** L: 审定确认=D+G+I */
  auditedDecrease: number
  /** M: 审定期末=J+K-L */
  auditedEnd: number
  /** N: 重分类 */
  reclassification: number
  /** O: 最终审定=M-N */
  finalAudited: number
  /** Q: 对应利息期 */
  interestPeriod: string
  /** R: 备注 */
  remark: string
  /** T: 关联方(是/否) */
  isRelatedParty: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H9-3-rows'
const TOTAL_END_KEY = 'H9-3-total-end'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9FinanceCost(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H9FinanceCostRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H9FinanceCostRow {
    const begin = Number(raw.beginBalance) || 0
    const debitInc = Number(raw.debitIncrease) || 0
    const creditDec = Number(raw.creditDecrease) || 0
    const beginAje = Number(raw.beginAje) || 0
    const confirmAje = Number(raw.confirmAje) || 0
    const increaseAje = Number(raw.increaseAje) || 0
    const otherAje = Number(raw.otherAje) || 0
    const reclassification = Number(raw.reclassification) || 0

    // E=B+C-D (借方备抵：期初+借-贷)
    const endBalance = calcContraLiabilityEndBalance(begin, debitInc, creditDec)
    // J=B, K=C+F+H, L=D+G+I, M=J+K-L
    const auditedBegin = begin
    const auditedIncrease = debitInc + beginAje + increaseAje
    const auditedDecrease = creditDec + confirmAje + otherAje
    const auditedEnd = calcContraLiabilityEndBalance(auditedBegin, auditedIncrease, auditedDecrease)
    const finalAudited = auditedEnd - reclassification

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      lessor: raw.lessor ?? '',
      contractNo: raw.contractNo ?? '',
      beginBalance: begin,
      debitIncrease: debitInc,
      creditDecrease: creditDec,
      endBalance,
      beginAje,
      confirmAje,
      increaseAje,
      otherAje,
      auditedBegin,
      auditedIncrease,
      auditedDecrease,
      auditedEnd,
      reclassification,
      finalAudited,
      interestPeriod: raw.interestPeriod ?? '',
      remark: raw.remark ?? '',
      isRelatedParty: raw.isRelatedParty ?? '否',
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
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const totalRow = computed(() => ({
    beginBalance: calcSubtotal(rows.value.map(r => r.beginBalance)),
    debitIncrease: calcSubtotal(rows.value.map(r => r.debitIncrease)),
    creditDecrease: calcSubtotal(rows.value.map(r => r.creditDecrease)),
    endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    auditedBegin: calcSubtotal(rows.value.map(r => r.auditedBegin)),
    auditedIncrease: calcSubtotal(rows.value.map(r => r.auditedIncrease)),
    auditedDecrease: calcSubtotal(rows.value.map(r => r.auditedDecrease)),
    auditedEnd: calcSubtotal(rows.value.map(r => r.auditedEnd)),
    finalAudited: calcSubtotal(rows.value.map(r => r.finalAudited)),
  }))

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(lessor: string): void {
    if (!lessor?.trim()) return
    rows.value.push(_normalizeRow({ lessor: lessor.trim() }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const textFields = ['lessor', 'contractNo', 'interestPeriod', 'remark', 'isRelatedParty']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'beginBalance': row.beginBalance = numVal; break
      case 'debitIncrease': row.debitIncrease = numVal; break
      case 'creditDecrease': row.creditDecrease = numVal; break
      case 'beginAje': row.beginAje = numVal; break
      case 'confirmAje': row.confirmAje = numVal; break
      case 'increaseAje': row.increaseAje = numVal; break
      case 'otherAje': row.otherAje = numVal; break
      case 'reclassification': row.reclassification = numVal; break
      default: return
    }

    // 重算公式列
    row.endBalance = calcContraLiabilityEndBalance(row.beginBalance, row.debitIncrease, row.creditDecrease)
    row.auditedBegin = row.beginBalance
    row.auditedIncrease = row.debitIncrease + row.beginAje + row.increaseAje
    row.auditedDecrease = row.creditDecrease + row.confirmAje + row.otherAje
    row.auditedEnd = calcContraLiabilityEndBalance(row.auditedBegin, row.auditedIncrease, row.auditedDecrease)
    row.finalAudited = row.auditedEnd - row.reclassification
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId, lessor: r.lessor, contractNo: r.contractNo,
      beginBalance: r.beginBalance, debitIncrease: r.debitIncrease, creditDecrease: r.creditDecrease,
      beginAje: r.beginAje, confirmAje: r.confirmAje, increaseAje: r.increaseAje, otherAje: r.otherAje,
      reclassification: r.reclassification,
      interestPeriod: r.interestPeriod, remark: r.remark, isRelatedParty: r.isRelatedParty,
    }))
    onSave(ROWS_KEY, toPersist)
    onSave(TOTAL_END_KEY, totalRow.value.auditedEnd)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, totalRow,
    addRow, deleteRow, updateCell, save, load,
  }
}

export default useH9FinanceCost
