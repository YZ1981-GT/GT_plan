/**
 * useH9Detail — H9-2 租赁负债明细表 composable（22列，按合同动态行）
 *
 * 按合同列示租赁负债变动：
 * A出租方 | B期初 | C本期偿还(借方减少) | D本期利息(贷方增加) | E期末=B-C+D
 * F~H审定调整(期初AJE/偿还AJE/利息AJE)
 * I~L审定后(I=B+F, J=C+G, K=D+H, L=I-J+K)
 * M重分类 | N最终=L-M
 * O~R其他列(合同号/承租资产/利率IBR/租赁期)
 * S关联方(是/否) | T发函(是/否)
 *
 * ⚠️ 负债贷方科目：E=B-C+D（期末=期初-偿还+利息）
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.4
 * Requirements: 3.1-3.3, 3.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { calcLiabilityEndBalance, calcSubtotal } from './useH9FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9-2 租赁负债明细表行 */
export interface H9DetailRow {
  rowId: string
  /** A: 出租方名称 */
  lessor: string
  /** O: 合同号 */
  contractNo: string
  /** P: 承租资产描述 */
  assetDesc: string
  /** Q: 增量借款利率IBR */
  ibrRate: number
  /** R: 租赁期(月) */
  leaseTerm: number
  /** B: 期初余额 */
  beginBalance: number
  /** C: 本期偿还(借方减少) */
  repayment: number
  /** D: 本期利息(贷方增加) */
  interestAccrued: number
  /** E: 期末余额 = B - C + D（负债贷方！） */
  endBalance: number
  /** F: 期初AJE */
  beginAje: number
  /** G: 偿还AJE */
  repayAje: number
  /** H: 利息AJE */
  interestAje: number
  /** I: 审定期初 = B + F */
  auditedBegin: number
  /** J: 审定偿还 = C + G */
  auditedRepay: number
  /** K: 审定利息 = D + H */
  auditedInterest: number
  /** L: 审定期末 = I - J + K */
  auditedEnd: number
  /** M: 重分类 */
  reclassification: number
  /** N: 最终审定 = L - M */
  finalAudited: number
  /** S: 关联方（是/否） */
  isRelatedParty: string
  /** T: 发函（是/否） */
  isConfirmed: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H9-2-rows'
const TOTAL_END_KEY = 'H9-2-total-end'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9Detail(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H9DetailRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H9DetailRow {
    const begin = Number(raw.beginBalance) || 0
    const repay = Number(raw.repayment) || 0
    const interest = Number(raw.interestAccrued) || 0
    const beginAje = Number(raw.beginAje) || 0
    const repayAje = Number(raw.repayAje) || 0
    const interestAje = Number(raw.interestAje) || 0
    const reclassification = Number(raw.reclassification) || 0

    // 公式：负债贷方 E=B-C+D (期末=期初-偿还+利息)
    const endBalance = calcLiabilityEndBalance(begin, interest, repay)
    // I=B+F, J=C+G, K=D+H
    const auditedBegin = begin + beginAje
    const auditedRepay = repay + repayAje
    const auditedInterest = interest + interestAje
    // L=I-J+K (审定期末=审定期初-审定偿还+审定利息)
    const auditedEnd = calcLiabilityEndBalance(auditedBegin, auditedInterest, auditedRepay)
    // N=L-M
    const finalAudited = auditedEnd - reclassification

    return {
      rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      lessor: raw.lessor ?? '',
      contractNo: raw.contractNo ?? '',
      assetDesc: raw.assetDesc ?? '',
      ibrRate: Number(raw.ibrRate) || 0,
      leaseTerm: Number(raw.leaseTerm) || 0,
      beginBalance: begin,
      repayment: repay,
      interestAccrued: interest,
      endBalance,
      beginAje,
      repayAje,
      interestAje,
      auditedBegin,
      auditedRepay,
      auditedInterest,
      auditedEnd,
      reclassification,
      finalAudited,
      isRelatedParty: raw.isRelatedParty ?? '否',
      isConfirmed: raw.isConfirmed ?? '否',
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
    repayment: calcSubtotal(rows.value.map(r => r.repayment)),
    interestAccrued: calcSubtotal(rows.value.map(r => r.interestAccrued)),
    endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    auditedBegin: calcSubtotal(rows.value.map(r => r.auditedBegin)),
    auditedRepay: calcSubtotal(rows.value.map(r => r.auditedRepay)),
    auditedInterest: calcSubtotal(rows.value.map(r => r.auditedInterest)),
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

    const textFields = ['lessor', 'contractNo', 'assetDesc', 'isRelatedParty', 'isConfirmed']
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persist()
      return
    }

    const numVal = Number(value) || 0
    switch (field) {
      case 'ibrRate': row.ibrRate = numVal; break
      case 'leaseTerm': row.leaseTerm = numVal; break
      case 'beginBalance': row.beginBalance = numVal; break
      case 'repayment': row.repayment = numVal; break
      case 'interestAccrued': row.interestAccrued = numVal; break
      case 'beginAje': row.beginAje = numVal; break
      case 'repayAje': row.repayAje = numVal; break
      case 'interestAje': row.interestAje = numVal; break
      case 'reclassification': row.reclassification = numVal; break
      default: return
    }

    // 重算所有公式列
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.interestAccrued, row.repayment)
    row.auditedBegin = row.beginBalance + row.beginAje
    row.auditedRepay = row.repayment + row.repayAje
    row.auditedInterest = row.interestAccrued + row.interestAje
    row.auditedEnd = calcLiabilityEndBalance(row.auditedBegin, row.auditedInterest, row.auditedRepay)
    row.finalAudited = row.auditedEnd - row.reclassification
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId, lessor: r.lessor, contractNo: r.contractNo, assetDesc: r.assetDesc,
      ibrRate: r.ibrRate, leaseTerm: r.leaseTerm,
      beginBalance: r.beginBalance, repayment: r.repayment, interestAccrued: r.interestAccrued,
      beginAje: r.beginAje, repayAje: r.repayAje, interestAje: r.interestAje,
      reclassification: r.reclassification,
      isRelatedParty: r.isRelatedParty, isConfirmed: r.isConfirmed,
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

export default useH9Detail
