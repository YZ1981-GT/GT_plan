/**
 * useH2RelatedParty — H2-17 关联交易检查 composable
 *
 * RelatedPartyRow 15列 + 差异率计算 + 合计行
 * 高亮规则(差异率>10%红色)
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.15
 * Requirements: 13.1-13.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2RelatedPartyRow {
  rowId: string
  /** 序号 */
  seq: number
  /** 关联方名称 */
  partyName: string
  /** 关联关系 */
  relationship: string
  /** 交易类型 */
  transactionType: '施工' | '供材' | '设计' | '监理' | ''
  /** 合同金额 */
  contractAmount: number
  /** 本期发生额 */
  currentAmount: number
  /** 累计发生额 */
  cumulativeAmount: number
  /** 定价方式 */
  pricingMethod: string
  /** 市场价参考 */
  marketPrice: number
  /** 价格差异 (公式列: 合同金额 - 市场价参考) */
  priceDifference: number
  /** 差异率(%) (公式列: 差异/市场价×100) */
  differenceRate: number | null
  /** 审批文件(Y/N) */
  approvalDoc: string
  /** 独立董事意见 */
  independentDirectorOpinion: string
  /** 审计结论 */
  auditConclusion: string
  /** 备注 */
  remark: string
}

export type RelatedPartyHighlight = 'red-price-deviation' | null

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-17-rows'
const NOTE_KEY = 'H2-17-audit-note'
const CONCLUSION_KEY = 'H2-17-audit-conclusion'
const DIFFERENCE_THRESHOLD = 10  // 差异率>10%红色高亮

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2RelatedParty(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2RelatedPartyRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _recalcRow(row: H2RelatedPartyRow): void {
    row.priceDifference = row.contractAmount - row.marketPrice
    row.differenceRate = row.marketPrice > 0
      ? (row.priceDifference / row.marketPrice) * 100
      : null
  }

  function _normalizeRow(r: any, idx: number): H2RelatedPartyRow {
    const row: H2RelatedPartyRow = {
      rowId: r.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seq: r.seq ?? (idx + 1),
      partyName: r.partyName ?? '',
      relationship: r.relationship ?? '',
      transactionType: r.transactionType ?? '',
      contractAmount: Number(r.contractAmount) || 0,
      currentAmount: Number(r.currentAmount) || 0,
      cumulativeAmount: Number(r.cumulativeAmount) || 0,
      pricingMethod: r.pricingMethod ?? '',
      marketPrice: Number(r.marketPrice) || 0,
      priceDifference: 0,
      differenceRate: null,
      approvalDoc: r.approvalDoc ?? '',
      independentDirectorOpinion: r.independentDirectorOpinion ?? '',
      auditConclusion: r.auditConclusion ?? '',
      remark: r.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 合计行 */
  const totalRow = computed(() => ({
    contractAmount: calcSubtotal(rows.value.map(r => r.contractAmount)),
    currentAmount: calcSubtotal(rows.value.map(r => r.currentAmount)),
    cumulativeAmount: calcSubtotal(rows.value.map(r => r.cumulativeAmount)),
  }))

  /** 高亮规则: 差异率绝对值>10%红色 */
  const rowHighlights: ComputedRef<Map<string, RelatedPartyHighlight>> = computed(() => {
    const map = new Map<string, RelatedPartyHighlight>()
    for (const row of rows.value) {
      if (row.differenceRate != null && Math.abs(row.differenceRate) > DIFFERENCE_THRESHOLD) {
        map.set(row.rowId, 'red-price-deviation')
      } else {
        map.set(row.rowId, null)
      }
    }
    return map
  })

  /** 异常行数量 */
  const abnormalCount: ComputedRef<number> = computed(() =>
    rows.value.filter(r => r.differenceRate != null && Math.abs(r.differenceRate) > DIFFERENCE_THRESHOLD).length,
  )

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addRow(): void {
    if (options.isReadonly.value) return
    rows.value.push(_normalizeRow({}, rows.value.length))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persist()
    }
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const formulaFields = ['priceDifference', 'differenceRate']
    if (formulaFields.includes(field)) return

    const numFields = ['contractAmount', 'currentAmount', 'cumulativeAmount', 'marketPrice']
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _recalcRow(row)
    _persist()
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function _persist(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId, seq: r.seq, partyName: r.partyName,
      relationship: r.relationship, transactionType: r.transactionType,
      contractAmount: r.contractAmount, currentAmount: r.currentAmount,
      cumulativeAmount: r.cumulativeAmount, pricingMethod: r.pricingMethod,
      marketPrice: r.marketPrice, approvalDoc: r.approvalDoc,
      independentDirectorOpinion: r.independentDirectorOpinion,
      auditConclusion: r.auditConclusion, remark: r.remark,
    })))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows, auditNote, auditConclusion,
    totalRow, rowHighlights, abnormalCount,
    addRow, removeRow, updateCell,
    saveNote, saveConclusion, initFromAllResponses,
  }
}

export default useH2RelatedParty
