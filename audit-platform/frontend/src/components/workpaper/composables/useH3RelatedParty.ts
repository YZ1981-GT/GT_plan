/**
 * useH3RelatedParty — H3-13 关联交易 composable
 *
 * RelatedPartyRow 11列 + 差异率 + 高亮规则
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.17
 * Requirements: 13.1-13.5
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPartyRow {
  rowId: string
  seq: number
  relatedParty: string        // 关联方
  relationship: string        // 关联关系
  transType: string           // 交易类型(出租/购入/处置/转换)
  amount: number              // 金额
  pricingMethod: string       // 定价方式
  marketRef: number           // 市场价参考
  diffRate: number            // 差异率（公式）
  approvalDoc: string         // 审批文件
  conclusion: string          // 审计结论
  remark: string
}

const ITEM_ID = 'H3-13-rp-rows'

export function useH3RelatedParty(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params
  const rows = ref<RelatedPartyRow[]>([])

  function loadRows(): void {
    const raw = getValue(ITEM_ID)
    rows.value = Array.isArray(raw) ? raw.map(_normalize) : []
  }

  function _normalize(raw: any, idx?: number): RelatedPartyRow {
    const amount = Number(raw.amount) || 0
    const market = Number(raw.marketRef) || 0
    const diffRate = market !== 0 ? ((amount - market) / market) * 100 : 0
    return {
      rowId: raw.rowId ?? `rp-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      relatedParty: raw.relatedParty ?? '',
      relationship: raw.relationship ?? '',
      transType: raw.transType ?? '',
      amount,
      pricingMethod: raw.pricingMethod ?? '',
      marketRef: market,
      diffRate,
      approvalDoc: raw.approvalDoc ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  /** 差异率>10%高亮行 */
  const highDiffRows = computed(() => rows.value.filter((r) => Math.abs(r.diffRate) > 10))

  function addRow(): void {
    rows.value.push(_normalize({ seq: rows.value.length + 1 }))
    _persist()
  }

  function removeRow(index: number): void {
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persist()
  }

  function updateCell(index: number, field: keyof RelatedPartyRow, value: any): void {
    const row = rows.value[index]
    if (!row) return
    ;(row as any)[field] = value
    // 重算差异率
    if (field === 'amount' || field === 'marketRef') {
      const amt = Number(row.amount) || 0
      const mkt = Number(row.marketRef) || 0
      row.diffRate = mkt !== 0 ? ((amt - mkt) / mkt) * 100 : 0
    }
    _persist()
  }

  function _persist(): void { setValue(ITEM_ID, rows.value) }
  watch(allResponses, () => loadRows(), { immediate: true })

  return { rows, highDiffRows, addRow, removeRow, updateCell, loadRows }
}

export default useH3RelatedParty
