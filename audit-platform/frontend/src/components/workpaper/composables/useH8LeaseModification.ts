/**
 * useH8LeaseModification — H8-7 租赁变更 composable
 *
 * 判定树 → 变更日账面（H8-2/H8-6 带入）→ 折现表/年金重计量 → 回写 H8-2
 * CAS21第28-30条 | Spec Task 3.4 | Requirements 4.3, 4.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import {
  calcRemeasurement,
  calcLiabilityAdjustment,
  calcAnnuityPV,
  calcAnnuityDuePV,
  calcScopeReduction,
  buildEqualPaymentSchedule,
  buildCustomPaymentSchedule,
  deriveModificationType,
  isSeparateLease,
  suggestAccountingTreatment,
  estimateLiabilityAtDate,
  type H8YesNo,
  type H8ModificationTypeDerived,
  type H8PaymentPVRow,
} from './useH8CAS21Engine'
import { calcSubtotal } from './useH8FormulaEngine'
import {
  mapH82ToSeeds,
  yearsBetween,
  validateModificationRow,
  buildH82ModificationPatch,
  buildSeparateLeaseH82Draft,
  appendRemark,
  type H82ContractSeed,
  type H8ModValidationIssue,
} from './h8LeaseModificationModel'

export type H8ModificationType = H8ModificationTypeDerived
export type H8PaymentTiming = '期初' | '期末'

export interface H8CustomPayment {
  amount: number
  periods: number
}

export interface H8LeaseModificationRow {
  rowId: string
  contractNo: string
  modificationDate: string
  assetName: string
  expandsScope: H8YesNo
  standalonePrice: H8YesNo
  scopeReduction: H8YesNo
  modificationDesc: string
  modificationType: H8ModificationType
  typeManualOverride: boolean
  originalTerms: string
  newTerms: string
  carryingLiability: number
  carryingROU: number
  revisedDiscountRate: number
  remainingAnnualPayment: number
  remainingPeriods: number
  /** 期初/期末付款 */
  paymentTiming: H8PaymentTiming
  /** 自定义逐期付款（优先于等额） */
  customPayments: H8CustomPayment[]
  /** 是否使用自定义付款流 */
  useCustomPayments: boolean
  newLiabilityPV: number
  autoCalcNewPV: boolean
  /** 范围减少比例 0–1 */
  reductionRatio: number
  /** 范围减少终止损益（负债终止−ROU终止） */
  scopeGainLoss: number
  /** ROU 摊销剩余年数（校验用） */
  rouAmortYears: number
  originalROUAmount: number
  adjustmentAmount: number
  adjustmentManualOverride: boolean
  remeasuredROUAmount: number
  accountingTreatment: string
  treatmentManualOverride: boolean
  conclusion: '是' | '否' | '不适用' | ''
  remark: string
  /** UI：卡片是否展开 */
  expanded: boolean
  /** 来源标记 */
  sourceTag: string
}

const ROWS_KEY = 'H8-7-rows'
const H82_ROWS_KEY = 'H8-2-rows'
const H86_PARAMS_KEY = 'H8-6-params'

function _round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

function _emptyRow(partial: Partial<H8LeaseModificationRow> = {}): H8LeaseModificationRow {
  return {
    rowId: partial.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    contractNo: partial.contractNo ?? '',
    modificationDate: partial.modificationDate ?? '',
    assetName: partial.assetName ?? '',
    expandsScope: (partial.expandsScope as H8YesNo) ?? '',
    standalonePrice: (partial.standalonePrice as H8YesNo) ?? '',
    scopeReduction: (partial.scopeReduction as H8YesNo) ?? '',
    modificationDesc: partial.modificationDesc ?? '',
    modificationType: (partial.modificationType as H8ModificationType) ?? '',
    typeManualOverride: Boolean(partial.typeManualOverride),
    originalTerms: partial.originalTerms ?? '',
    newTerms: partial.newTerms ?? '',
    carryingLiability: Number(partial.carryingLiability) || 0,
    carryingROU: Number(partial.carryingROU ?? partial.originalROUAmount) || 0,
    revisedDiscountRate: Number(partial.revisedDiscountRate) || 0,
    remainingAnnualPayment: Number(partial.remainingAnnualPayment) || 0,
    remainingPeriods: Number(partial.remainingPeriods) || 0,
    paymentTiming: partial.paymentTiming === '期初' ? '期初' : '期末',
    customPayments: Array.isArray(partial.customPayments) ? partial.customPayments.map(p => ({
      amount: Number(p.amount) || 0,
      periods: Number(p.periods) || 0,
    })) : [],
    useCustomPayments: Boolean(partial.useCustomPayments),
    newLiabilityPV: Number(partial.newLiabilityPV) || 0,
    autoCalcNewPV: partial.autoCalcNewPV === true || partial.autoCalcNewPV === 'true',
    reductionRatio: Number(partial.reductionRatio) || 0,
    scopeGainLoss: Number(partial.scopeGainLoss) || 0,
    rouAmortYears: Number(partial.rouAmortYears) || 0,
    originalROUAmount: Number(partial.originalROUAmount ?? partial.carryingROU) || 0,
    adjustmentAmount: Number(partial.adjustmentAmount) || 0,
    adjustmentManualOverride: Boolean(partial.adjustmentManualOverride),
    remeasuredROUAmount: 0,
    accountingTreatment: partial.accountingTreatment ?? '',
    treatmentManualOverride: Boolean(partial.treatmentManualOverride),
    conclusion: (partial.conclusion as H8LeaseModificationRow['conclusion']) ?? '',
    remark: partial.remark ?? '',
    expanded: partial.expanded !== false,
    sourceTag: partial.sourceTag ?? '',
  }
}

function _recomputeRow(row: H8LeaseModificationRow): void {
  if (!row.typeManualOverride) {
    if (isSeparateLease(row.expandsScope, row.standalonePrice)) {
      row.modificationType = '单独租赁'
      if (row.scopeReduction === '是') row.scopeReduction = ''
    } else {
      row.modificationType = deriveModificationType(
        row.expandsScope,
        row.standalonePrice,
        row.scopeReduction,
      )
    }
  }

  // 折现 / 年金 → 新负债 PV
  if (row.autoCalcNewPV && row.modificationType !== '单独租赁') {
    if (row.useCustomPayments && row.customPayments.length > 0) {
      const { totalPV } = buildCustomPaymentSchedule(row.customPayments, row.revisedDiscountRate)
      row.newLiabilityPV = _round2(totalPV)
    } else if (row.remainingPeriods > 0 && row.remainingAnnualPayment !== 0) {
      const pv = row.paymentTiming === '期初'
        ? calcAnnuityDuePV(row.remainingAnnualPayment, row.revisedDiscountRate, row.remainingPeriods)
        : calcAnnuityPV(row.remainingAnnualPayment, row.revisedDiscountRate, row.remainingPeriods)
      row.newLiabilityPV = _round2(pv)
    }
  }

  const oldROU = row.carryingROU || row.originalROUAmount
  row.originalROUAmount = oldROU

  if (row.modificationType === '单独租赁') {
    if (!row.adjustmentManualOverride) row.adjustmentAmount = 0
    row.scopeGainLoss = 0
    row.remeasuredROUAmount = calcRemeasurement(oldROU, 0)
  } else if (row.modificationType === '范围减少') {
    const sr = calcScopeReduction(row.carryingLiability, oldROU, row.reductionRatio)
    row.scopeGainLoss = _round2(sr.gainLoss)
    if (!row.adjustmentManualOverride) row.adjustmentAmount = _round2(sr.rouAdjustment)
    row.remeasuredROUAmount = _round2(sr.remainingROU)
  } else if (row.modificationType === '其他变更') {
    row.scopeGainLoss = 0
    if (!row.adjustmentManualOverride) {
      row.adjustmentAmount = _round2(
        calcLiabilityAdjustment(row.newLiabilityPV, row.carryingLiability),
      )
    }
    row.remeasuredROUAmount = _round2(calcRemeasurement(oldROU, row.adjustmentAmount))
  } else {
    row.remeasuredROUAmount = _round2(calcRemeasurement(oldROU, row.adjustmentAmount))
  }

  if (!row.treatmentManualOverride) {
    let text = suggestAccountingTreatment(row.modificationType)
    if (row.modificationType === '范围减少' && row.reductionRatio > 0) {
      text += `；终止比例 ${(row.reductionRatio * 100).toFixed(1)}%，终止损益 ${row.scopeGainLoss.toFixed(2)}（负债−ROU）`
    }
    row.accountingTreatment = text
  }
}

export function useH8LeaseModification(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params
  const rows = ref<H8LeaseModificationRow[]>([])

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _normalizeRow(raw: any): H8LeaseModificationRow {
    const row = _emptyRow(raw)
    _recomputeRow(row)
    return row
  }

  function load(): void {
    const data = _getJson(ROWS_KEY)
    rows.value = Array.isArray(data) && data.length > 0 ? data.map(_normalizeRow) : []
  }

  watch(allResponses, () => load(), { immediate: true })

  const totalAdjustment = computed(() =>
    calcSubtotal(rows.value.map(r => r.adjustmentAmount)),
  )

  const typeStats = computed(() => ({
    separateLease: rows.value.filter(r => r.modificationType === '单独租赁').length,
    scopeReduction: rows.value.filter(r => r.modificationType === '范围减少').length,
    otherModification: rows.value.filter(r => r.modificationType === '其他变更').length,
  }))

  const h82Contracts = computed<H82ContractSeed[]>(() =>
    mapH82ToSeeds(_getJson(H82_ROWS_KEY) || []),
  )

  const rowValidations = computed(() => {
    const endByContract = new Map(h82Contracts.value.map(c => [c.contractNo, c.endDate]))
    const map = new Map<string, H8ModValidationIssue[]>()
    for (const r of rows.value) {
      map.set(r.rowId, validateModificationRow(r, endByContract.get(r.contractNo)))
    }
    return map
  })

  function getPaymentSchedule(rowId: string): { rows: H8PaymentPVRow[]; totalPV: number } {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return { rows: [], totalPV: 0 }
    if (row.useCustomPayments && row.customPayments.length > 0) {
      return buildCustomPaymentSchedule(row.customPayments, row.revisedDiscountRate)
    }
    if (row.remainingPeriods > 0 && row.remainingAnnualPayment !== 0) {
      return buildEqualPaymentSchedule(
        row.remainingAnnualPayment,
        row.revisedDiscountRate,
        row.remainingPeriods,
        row.paymentTiming,
      )
    }
    return { rows: [], totalPV: row.newLiabilityPV || 0 }
  }

  function addRow(contractNo: string): void {
    if (!contractNo?.trim()) return
    rows.value.push(_normalizeRow({ contractNo: contractNo.trim(), expanded: true }))
    _persist()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persist()
  }

  function setExpanded(rowId: string, expanded: boolean): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    row.expanded = expanded
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const textFields = [
      'contractNo', 'modificationDate', 'assetName', 'modificationDesc',
      'originalTerms', 'newTerms', 'accountingTreatment', 'conclusion', 'remark',
      'expandsScope', 'standalonePrice', 'scopeReduction', 'modificationType',
      'paymentTiming', 'sourceTag',
    ]
    const numFields = [
      'carryingLiability', 'carryingROU', 'originalROUAmount',
      'revisedDiscountRate', 'remainingAnnualPayment', 'remainingPeriods',
      'newLiabilityPV', 'adjustmentAmount', 'reductionRatio', 'rouAmortYears',
    ]
    const boolFields = [
      'typeManualOverride', 'autoCalcNewPV', 'adjustmentManualOverride',
      'treatmentManualOverride', 'useCustomPayments', 'expanded',
    ]

    if (field === 'customPayments' && Array.isArray(value)) {
      row.customPayments = value.map((p: any) => ({
        amount: Number(p.amount) || 0,
        periods: Number(p.periods) || 0,
      }))
      row.useCustomPayments = true
      row.autoCalcNewPV = true
    } else if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      if (field === 'modificationType') row.typeManualOverride = true
      if (field === 'accountingTreatment') row.treatmentManualOverride = true
      if (['expandsScope', 'standalonePrice', 'scopeReduction'].includes(field)) {
        row.typeManualOverride = false
        row.treatmentManualOverride = false
      }
      if (field === 'paymentTiming' && row.remainingPeriods > 0 && row.remainingAnnualPayment !== 0) {
        row.autoCalcNewPV = true
      }
    } else if (numFields.includes(field)) {
      let numVal = Number(value) || 0
      if (field === 'reductionRatio') {
        // UI 可传 0–100 或 0–1
        if (numVal > 1) numVal = numVal / 100
        numVal = Math.min(1, Math.max(0, numVal))
      }
      ;(row as any)[field] = numVal
      if (field === 'adjustmentAmount') row.adjustmentManualOverride = true
      if (field === 'newLiabilityPV') row.autoCalcNewPV = false
      if (field === 'carryingROU') row.originalROUAmount = numVal
      if (field === 'originalROUAmount') row.carryingROU = numVal
      if (['remainingAnnualPayment', 'remainingPeriods', 'revisedDiscountRate', 'paymentTiming'].includes(field)
        || field === 'reductionRatio') {
        if (row.remainingPeriods > 0 && row.remainingAnnualPayment !== 0) {
          row.autoCalcNewPV = true
        }
      }
    } else if (boolFields.includes(field)) {
      ;(row as any)[field] = Boolean(value)
      if (field === 'typeManualOverride' && !value) row.treatmentManualOverride = false
      if (field === 'useCustomPayments' && value) row.autoCalcNewPV = true
    } else {
      return
    }

    _recomputeRow(row)
    _persist()
  }

  /** 从 H8-2 选合同带入基础信息 + 净值作 ROU 账面 */
  function pullFromH82(rowId: string, contractNo: string): { ok: boolean; message: string } {
    const seed = h82Contracts.value.find(c => c.contractNo === contractNo)
    if (!seed) return { ok: false, message: `H8-2 未找到合同 ${contractNo}` }
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return { ok: false, message: '行不存在' }

    row.contractNo = seed.contractNo
    if (seed.assetName) row.assetName = seed.assetName
    row.carryingROU = seed.netValue || seed.initialAmount || 0
    row.originalROUAmount = row.carryingROU
    if (!row.originalTerms) {
      row.originalTerms = [
        seed.startDate && `起租${seed.startDate}`,
        seed.endDate && `到期${seed.endDate}`,
        seed.initialAmount && `入账${seed.initialAmount}`,
      ].filter(Boolean).join('；')
    }
    row.sourceTag = 'H8-2'

    // 若有 H8-6 参数，估算变更日负债
    const p = _getJson(H86_PARAMS_KEY)
    if (p && typeof p === 'object' && row.modificationDate && seed.startDate) {
      const years = yearsBetween(seed.startDate, row.modificationDate)
      const est = estimateLiabilityAtDate({
        leaseLiabilityInitial: Number(p.leaseLiabilityInitial) || seed.h9InitialAmount || 0,
        discountRatePct: Number(p.discountRate) || 0,
        rentalPerPeriod: Number(p.rentalPerPeriod) || 0,
        leaseTermMonths: Number(p.leaseTermMonths) || 0,
        yearsElapsed: years,
        paymentTiming: p.paymentTiming === '期初' ? '期初' : '期末',
      })
      if (est > 0) row.carryingLiability = _round2(est)
      if (Number(p.discountRate) > 0 && !(row.revisedDiscountRate > 0)) {
        row.revisedDiscountRate = Number(p.discountRate) / 100
      }
    } else if (!(row.carryingLiability > 0) && seed.h9InitialAmount > 0) {
      // 无 H8-6 时退化为 H9 初始（提示用户复核）
      row.carryingLiability = seed.h9InitialAmount
    }

    _recomputeRow(row)
    _persist()
    return { ok: true, message: `已从 H8-2 带入 ${contractNo}` }
  }

  /** 仅用 H8-6 参数刷新当前行负债估算（需已有变更日与合同起租信息） */
  function estimateLiabilityFromH86(rowId: string, startDate?: string): { ok: boolean; message: string } {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return { ok: false, message: '行不存在' }
    const p = _getJson(H86_PARAMS_KEY)
    if (!p || typeof p !== 'object') return { ok: false, message: 'H8-6 计量参数为空' }
    const start = startDate
      || h82Contracts.value.find(c => c.contractNo === row.contractNo)?.startDate
      || ''
    if (!row.modificationDate || !start) {
      return { ok: false, message: '需要变更日期与起租日（可先从 H8-2 带入）' }
    }
    const years = yearsBetween(start, row.modificationDate)
    const est = estimateLiabilityAtDate({
      leaseLiabilityInitial: Number(p.leaseLiabilityInitial) || 0,
      discountRatePct: Number(p.discountRate) || 0,
      rentalPerPeriod: Number(p.rentalPerPeriod) || 0,
      leaseTermMonths: Number(p.leaseTermMonths) || 0,
      yearsElapsed: years,
      paymentTiming: p.paymentTiming === '期初' ? '期初' : '期末',
    })
    row.carryingLiability = _round2(est)
    row.sourceTag = appendRemark(row.sourceTag, 'H8-6估算')
    _recomputeRow(row)
    _persist()
    return { ok: true, message: `已按 H8-6 估算变更日负债 ${est.toFixed(2)}（已过约 ${years.toFixed(1)} 年）` }
  }

  /** 回写调整额到 H8-2 变更区段 */
  function syncAdjustmentsToH82(): { updated: number; message: string } {
    const raw = _getJson(H82_ROWS_KEY)
    if (!Array.isArray(raw) || raw.length === 0) {
      return { updated: 0, message: 'H8-2 无明细行可回写' }
    }
    const patches = buildH82ModificationPatch(rows.value, raw)
    if (patches.length === 0) return { updated: 0, message: '无匹配合同可回写' }

    const next = raw.map((r: any) => {
      const k = String(r.contractNo ?? '').trim()
      const patch = patches.find(p => p.contractNo === k)
      if (!patch) return r
      return {
        ...r,
        modificationAmount: patch.modificationAmount,
        remark: appendRemark(String(r.remark ?? ''), patch.remarkAppend),
      }
    })
    onSave?.(H82_ROWS_KEY, next)
    return { updated: patches.length, message: `已回写 ${patches.length} 份合同的变更调整额至 H8-2` }
  }

  /** 单独租赁：在 H8-2 新增独立合同行 */
  function createSeparateLeaseOnH82(rowId: string): { ok: boolean; message: string; contractNo?: string } {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return { ok: false, message: '行不存在' }
    const draft = buildSeparateLeaseH82Draft(row)
    if (!draft) return { ok: false, message: '仅「单独租赁」可生成新合同行' }

    const raw = _getJson(H82_ROWS_KEY)
    const list = Array.isArray(raw) ? [...raw] : []
    if (list.some((r: any) => String(r.contractNo).trim() === draft.contractNo)) {
      return { ok: false, message: `H8-2 已存在 ${draft.contractNo}` }
    }
    list.push({
      rowId: `row-${Date.now().toString(36)}`,
      ...draft,
      lessor: '',
      leaseType: '',
      accDepBegin: 0,
      depCurrentPeriod: 0,
      terminationDate: '',
    })
    onSave?.(H82_ROWS_KEY, list)
    return {
      ok: true,
      message: `已在 H8-2 新增单独租赁合同 ${draft.contractNo}，请继续完善 H8-6 计量`,
      contractNo: draft.contractNo,
    }
  }

  function addCustomPayment(rowId: string): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    const nextPeriod = row.customPayments.length === 0
      ? (row.paymentTiming === '期初' ? 0 : 1)
      : Math.max(...row.customPayments.map(p => p.periods)) + 1
    row.customPayments.push({
      amount: row.remainingAnnualPayment || 0,
      periods: nextPeriod,
    })
    row.useCustomPayments = true
    row.autoCalcNewPV = true
    _recomputeRow(row)
    _persist()
  }

  function removeCustomPayment(rowId: string, index: number): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || index < 0 || index >= row.customPayments.length) return
    row.customPayments.splice(index, 1)
    row.autoCalcNewPV = true
    _recomputeRow(row)
    _persist()
  }

  function save(): void { _persist() }

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId,
      contractNo: r.contractNo,
      modificationDate: r.modificationDate,
      assetName: r.assetName,
      expandsScope: r.expandsScope,
      standalonePrice: r.standalonePrice,
      scopeReduction: r.scopeReduction,
      modificationDesc: r.modificationDesc,
      modificationType: r.modificationType,
      typeManualOverride: r.typeManualOverride,
      originalTerms: r.originalTerms,
      newTerms: r.newTerms,
      carryingLiability: r.carryingLiability,
      carryingROU: r.carryingROU,
      revisedDiscountRate: r.revisedDiscountRate,
      remainingAnnualPayment: r.remainingAnnualPayment,
      remainingPeriods: r.remainingPeriods,
      paymentTiming: r.paymentTiming,
      customPayments: r.customPayments,
      useCustomPayments: r.useCustomPayments,
      newLiabilityPV: r.newLiabilityPV,
      autoCalcNewPV: r.autoCalcNewPV,
      reductionRatio: r.reductionRatio,
      scopeGainLoss: r.scopeGainLoss,
      rouAmortYears: r.rouAmortYears,
      originalROUAmount: r.originalROUAmount,
      adjustmentAmount: r.adjustmentAmount,
      adjustmentManualOverride: r.adjustmentManualOverride,
      accountingTreatment: r.accountingTreatment,
      treatmentManualOverride: r.treatmentManualOverride,
      conclusion: r.conclusion,
      remark: r.remark,
      expanded: r.expanded,
      sourceTag: r.sourceTag,
    })))
  }

  return {
    rows, totalAdjustment, typeStats, h82Contracts, rowValidations,
    addRow, deleteRow, updateCell, setExpanded,
    getPaymentSchedule, pullFromH82, estimateLiabilityFromH86,
    syncAdjustmentsToH82, createSeparateLeaseOnH82,
    addCustomPayment, removeCustomPayment,
    save, load,
  }
}

export default useH8LeaseModification
