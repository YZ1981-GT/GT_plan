/**
 * useH3AdditionCheck — H3-5 增减检查表 composable
 *
 * 双版本（成本21列/公允20列）+ 抽凭 + OCR + 汇总统计
 *
 * Spec: .kiro/specs/h3-investment-property/
 * Task: 3.10
 * Requirements: 6.1-6.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal } from './useH3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdditionCostRow {
  rowId: string
  seq: number
  assetName: string
  date: string
  changeType: string        // 购入/自建转入/自用转入/处置/转出
  originalCost: number
  accDep: number
  netValue: number
  contract: string
  invoice: string
  appraisal: string
  titleCert: string
  approvalDoc: string
  debitAccount: string
  creditAccount: string
  plImpact: number
  attachment: string        // 📎
  conclusion: string
  remark: string
}

export interface AdditionFairRow {
  rowId: string
  seq: number
  assetName: string
  date: string
  changeType: string
  fairValue: number
  appraisalBasis: string
  contract: string
  invoice: string
  appraisal: string
  titleCert: string
  fairValueChange: number
  plImpact: number
  attachment: string
  conclusion: string
  remark: string
}

const ITEM_COST = 'H3-5-cost-rows'
const ITEM_FAIR = 'H3-5-fair-rows'

export function useH3AdditionCheck(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
  measurementModel: Ref<string>
}) {
  const { allResponses, getValue, setValue, measurementModel } = params
  const costRows = ref<AdditionCostRow[]>([])
  const fairRows = ref<AdditionFairRow[]>([])

  function loadRows(): void {
    const rawCost = getValue(ITEM_COST)
    costRows.value = Array.isArray(rawCost) ? rawCost.map(_normCost) : []
    const rawFair = getValue(ITEM_FAIR)
    fairRows.value = Array.isArray(rawFair) ? rawFair.map(_normFair) : []
  }

  function _normCost(raw: any, idx?: number): AdditionCostRow {
    return {
      rowId: raw.rowId ?? `ac-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      date: raw.date ?? '',
      changeType: raw.changeType ?? '',
      originalCost: Number(raw.originalCost) || 0,
      accDep: Number(raw.accDep) || 0,
      netValue: Number(raw.netValue) || 0,
      contract: raw.contract ?? '',
      invoice: raw.invoice ?? '',
      appraisal: raw.appraisal ?? '',
      titleCert: raw.titleCert ?? '',
      approvalDoc: raw.approvalDoc ?? '',
      debitAccount: raw.debitAccount ?? '',
      creditAccount: raw.creditAccount ?? '',
      plImpact: Number(raw.plImpact) || 0,
      attachment: raw.attachment ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normFair(raw: any, idx?: number): AdditionFairRow {
    return {
      rowId: raw.rowId ?? `af-${Math.random().toString(36).slice(2, 8)}`,
      seq: raw.seq ?? (idx != null ? idx + 1 : 1),
      assetName: raw.assetName ?? '',
      date: raw.date ?? '',
      changeType: raw.changeType ?? '',
      fairValue: Number(raw.fairValue) || 0,
      appraisalBasis: raw.appraisalBasis ?? '',
      contract: raw.contract ?? '',
      invoice: raw.invoice ?? '',
      appraisal: raw.appraisal ?? '',
      titleCert: raw.titleCert ?? '',
      fairValueChange: Number(raw.fairValueChange) || 0,
      plImpact: Number(raw.plImpact) || 0,
      attachment: raw.attachment ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  /** 当前模式下的活跃行 */
  const activeRows = computed(() => measurementModel.value === 'cost' ? costRows.value : fairRows.value)

  const summary = computed(() => ({
    totalCount: activeRows.value.length,
    totalAmount: measurementModel.value === 'cost'
      ? calcSubtotal(costRows.value.map((r) => r.originalCost))
      : calcSubtotal(fairRows.value.map((r) => r.fairValue)),
    plImpactTotal: calcSubtotal(activeRows.value.map((r: any) => r.plImpact)),
  }))

  function addRow(): void {
    if (measurementModel.value === 'cost') {
      costRows.value.push(_normCost({ seq: costRows.value.length + 1 }))
      setValue(ITEM_COST, costRows.value)
    } else {
      fairRows.value.push(_normFair({ seq: fairRows.value.length + 1 }))
      setValue(ITEM_FAIR, fairRows.value)
    }
  }

  function removeRow(index: number): void {
    if (measurementModel.value === 'cost') {
      costRows.value.splice(index, 1)
      costRows.value.forEach((r, i) => { r.seq = i + 1 })
      setValue(ITEM_COST, costRows.value)
    } else {
      fairRows.value.splice(index, 1)
      fairRows.value.forEach((r, i) => { r.seq = i + 1 })
      setValue(ITEM_FAIR, fairRows.value)
    }
  }

  function updateCell(index: number, field: string, value: any): void {
    if (measurementModel.value === 'cost') {
      const row = costRows.value[index]
      if (row) { (row as any)[field] = value; setValue(ITEM_COST, costRows.value) }
    } else {
      const row = fairRows.value[index]
      if (row) { (row as any)[field] = value; setValue(ITEM_FAIR, fairRows.value) }
    }
  }

  watch(allResponses, () => loadRows(), { immediate: true })

  return { costRows, fairRows, activeRows, summary, addRow, removeRow, updateCell, loadRows }
}

export default useH3AdditionCheck
