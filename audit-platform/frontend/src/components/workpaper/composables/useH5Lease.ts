/**
 * useH5Lease — H5-18/19 租赁 composable
 *
 * 经营租出收益率 + 融资租出本金摊销
 * H5-18 经营租出17列 + H5-19 融资租出20列
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 8.5-8.6, 11.1-11.3
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcLeaseReturnRate, calcSubtotal } from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface OperatingLeaseRow {
  rowId: string
  seq: number
  assetName: string
  oilField: string
  lessee: string                // 承租方
  leaseStartDate: string
  leaseEndDate: string
  leaseTerm: number             // 租期(月)
  annualRent: number            // 年租金
  netValue: number              // 资产净值
  returnRate: number            // 收益率(%) - 公式
  paymentMethod: string         // 支付方式
  contractNo: string
  approvalDoc: string
  conclusion: string
  remark: string
}

export interface FinanceLeaseRow {
  rowId: string
  seq: number
  assetName: string
  oilField: string
  lessee: string
  leaseStartDate: string
  leaseEndDate: string
  leaseTerm: number
  principal: number             // 本金(应收融资租赁款)
  unrecognizedFinanceIncome: number  // 未确认融资收益
  netInvestment: number         // 净投资(本金-未确认收益)
  currentInterest: number       // 本期确认利息
  residualValue: number         // 担保余值
  interestRate: number          // 内含利率(%)
  amortizedPrincipal: number    // 已摊销本金
  remainingPrincipal: number    // 剩余本金
  contractNo: string
  conclusion: string
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const OP_PREFIX = 'H5-18'
const FIN_PREFIX = 'H5-19'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Lease(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const operatingRows = ref<OperatingLeaseRow[]>([])
  const financeRows = ref<FinanceLeaseRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const rawOp = allResponses.value.get(`${OP_PREFIX}-rows`)?.remark
    if (rawOp) {
      try { operatingRows.value = (JSON.parse(rawOp) ?? []).map(_normalizeOp) } catch { operatingRows.value = [] }
    } else { operatingRows.value = [] }

    const rawFin = allResponses.value.get(`${FIN_PREFIX}-rows`)?.remark
    if (rawFin) {
      try { financeRows.value = (JSON.parse(rawFin) ?? []).map(_normalizeFin) } catch { financeRows.value = [] }
    } else { financeRows.value = [] }

    auditNote.value = (allResponses.value.get(`${OP_PREFIX}-audit-note`)?.remark ?? '') as string
    auditConclusion.value = (allResponses.value.get(`${OP_PREFIX}-audit-conclusion`)?.remark ?? '') as string
  }

  function _normalizeOp(raw: any): OperatingLeaseRow {
    const annualRent = Number(raw.annualRent) || 0
    const netValue = Number(raw.netValue) || 0
    return {
      rowId: raw.rowId ?? `op-${Math.random().toString(36).slice(2, 10)}`,
      seq: Number(raw.seq) || 0,
      assetName: raw.assetName ?? '',
      oilField: raw.oilField ?? '',
      lessee: raw.lessee ?? '',
      leaseStartDate: raw.leaseStartDate ?? '',
      leaseEndDate: raw.leaseEndDate ?? '',
      leaseTerm: Number(raw.leaseTerm) || 0,
      annualRent,
      netValue,
      returnRate: calcLeaseReturnRate(annualRent, netValue),
      paymentMethod: raw.paymentMethod ?? '',
      contractNo: raw.contractNo ?? '',
      approvalDoc: raw.approvalDoc ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeFin(raw: any): FinanceLeaseRow {
    const principal = Number(raw.principal) || 0
    const unrecognized = Number(raw.unrecognizedFinanceIncome) || 0
    return {
      rowId: raw.rowId ?? `fin-${Math.random().toString(36).slice(2, 10)}`,
      seq: Number(raw.seq) || 0,
      assetName: raw.assetName ?? '',
      oilField: raw.oilField ?? '',
      lessee: raw.lessee ?? '',
      leaseStartDate: raw.leaseStartDate ?? '',
      leaseEndDate: raw.leaseEndDate ?? '',
      leaseTerm: Number(raw.leaseTerm) || 0,
      principal,
      unrecognizedFinanceIncome: unrecognized,
      netInvestment: principal - unrecognized,
      currentInterest: Number(raw.currentInterest) || 0,
      residualValue: Number(raw.residualValue) || 0,
      interestRate: Number(raw.interestRate) || 0,
      amortizedPrincipal: Number(raw.amortizedPrincipal) || 0,
      remainingPrincipal: Number(raw.remainingPrincipal) || 0,
      contractNo: raw.contractNo ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalAnnualRent = computed(() => calcSubtotal(operatingRows.value.map((r) => r.annualRent)))
  const avgReturnRate = computed(() => {
    if (operatingRows.value.length === 0) return 0
    return calcSubtotal(operatingRows.value.map((r) => r.returnRate)) / operatingRows.value.length
  })
  const totalFinancePrincipal = computed(() => calcSubtotal(financeRows.value.map((r) => r.principal)))
  const totalCurrentInterest = computed(() => calcSubtotal(financeRows.value.map((r) => r.currentInterest)))

  // ─── Actions: 经营租出 ─────────────────────────────────────────────────────

  function addOperatingRow(assetName: string): void {
    operatingRows.value.push({
      rowId: `op-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: operatingRows.value.length + 1, assetName,
      oilField: '', lessee: '', leaseStartDate: '', leaseEndDate: '',
      leaseTerm: 0, annualRent: 0, netValue: 0, returnRate: 0,
      paymentMethod: '', contractNo: '', approvalDoc: '', conclusion: '', remark: '',
    })
    _persistOp()
  }

  function removeOperatingRow(rowId: string): void {
    const idx = operatingRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { operatingRows.value.splice(idx, 1); _persistOp() }
  }

  function updateOperatingCell(rowId: string, field: keyof OperatingLeaseRow, value: any): void {
    const row = operatingRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'annualRent' || field === 'netValue') {
      row.returnRate = calcLeaseReturnRate(row.annualRent, row.netValue)
    }
    _persistOp()
  }

  // ─── Actions: 融资租出 ─────────────────────────────────────────────────────

  function addFinanceRow(assetName: string): void {
    financeRows.value.push({
      rowId: `fin-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: financeRows.value.length + 1, assetName,
      oilField: '', lessee: '', leaseStartDate: '', leaseEndDate: '',
      leaseTerm: 0, principal: 0, unrecognizedFinanceIncome: 0,
      netInvestment: 0, currentInterest: 0, residualValue: 0,
      interestRate: 0, amortizedPrincipal: 0, remainingPrincipal: 0,
      contractNo: '', conclusion: '', remark: '',
    })
    _persistFin()
  }

  function removeFinanceRow(rowId: string): void {
    const idx = financeRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) { financeRows.value.splice(idx, 1); _persistFin() }
  }

  function updateFinanceCell(rowId: string, field: keyof FinanceLeaseRow, value: any): void {
    const row = financeRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'principal' || field === 'unrecognizedFinanceIncome') {
      row.netInvestment = row.principal - row.unrecognizedFinanceIncome
    }
    _persistFin()
  }

  function _persistOp(): void { onSave?.(`${OP_PREFIX}-rows`, operatingRows.value) }
  function _persistFin(): void { onSave?.(`${FIN_PREFIX}-rows`, financeRows.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${OP_PREFIX}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${OP_PREFIX}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    operatingRows, financeRows, auditNote, auditConclusion,
    totalAnnualRent, avgReturnRate, totalFinancePrincipal, totalCurrentInterest,
    addOperatingRow, removeOperatingRow, updateOperatingCell,
    addFinanceRow, removeFinanceRow, updateFinanceCell,
    saveNote, saveConclusion,
  }
}
