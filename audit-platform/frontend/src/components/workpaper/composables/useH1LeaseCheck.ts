/**
 * useH1LeaseCheck — H1-18~20 关联/租赁检查 composable
 *
 * RelatedPartyRow 15列 + OperatingLeaseRow 25列(23公式) + FinanceLeaseRow 22列
 * 价格差异率 + 租赁净收益 + 收益率
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.16
 * Requirements: 15.1-15.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 关联交易行 (H1-18, 15列) */
export interface RelatedPartyRow {
  rowId: string
  seq: number
  name: string                    // 资产名称
  counterparty: string            // 交易对方
  relationship: string            // 关联关系
  transType: string               // 交易类型(购入/出售/租赁)
  transDate: string               // 交易日期
  transAmount: number             // 交易金额
  bookValue: number               // 账面价值
  appraisedValue: number          // 评估价值
  pricingBasis: string            // 定价依据
  priceDiffRate: number           // 价格差异率(%)（公式）
  isFair: string                  // 是否公允(Y/N)
  approvalDoc: string             // 审批文件
  conclusion: string              // 结论
  remark: string                  // 备注
}

/** 经营租出行 (H1-19, 25列, 23公式) */
export interface OperatingLeaseRow {
  rowId: string
  seq: number
  lessee: string                  // 承租方
  assetName: string               // 资产名称
  originalCost: number            // 原值
  netValue: number                // 净值
  leaseStart: string              // 租赁起始日
  leaseEnd: string                // 租赁终止日
  leaseTerm: number               // 租赁期限(月)
  annualRent: number              // 年租金
  monthlyRent: number             // 月租金（公式）
  totalRentIncome: number         // 总租金收入（公式）
  depAlloc: number                // 折旧分摊
  maintenanceCost: number         // 维修费用
  netIncome: number               // 租赁净收益（公式）
  returnRate: number              // 收益率(%)（公式）
  marketRent: number              // 市场租金参考
  rentDiff: number                // 租金差异（公式）
  contractNo: string              // 合同编号
  deposit: number                 // 押金
  expiryDate: string              // 到期日
  renewalTerms: string            // 续租条款
  earlyTermination: string        // 提前终止条款
  isRelatedParty: string          // 是否关联(Y/N)
  hasChanged: string              // 是否变更(Y/N)
  accountTreatment: string        // 会计处理
  conclusion: string              // 结论
  remark: string                  // 备注
}

/** 融资租出行 (H1-20, 22列) */
export interface FinanceLeaseRow {
  rowId: string
  seq: number
  lessee: string                  // 承租方
  assetName: string               // 资产名称
  originalCost: number            // 原值
  classificationBasis: string     // 租赁分类依据(5项判断)
  classResult1: string            // 判断1: 转移所有权
  classResult2: string            // 判断2: 购买选择权
  classResult3: string            // 判断3: 占大部分使用年限
  classResult4: string            // 判断4: 现值≈公允
  classResult5: string            // 判断5: 性质特殊
  minLeasePayment: number         // 最低租赁付款额
  presentValue: number            // 现值
  unrecognizedFinIncome: number   // 未确认融资收益
  allocRate: number               // 分摊利率(%)
  periodInterest: number          // 各期利息收入
  principalRecovery: number       // 本金回收
  endBalance: number              // 期末余额
  isRelatedParty: string          // 是否关联(Y/N)
  conclusion: string              // 结论
  remark: string                  // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_18 = 'H1-18'
const ITEM_PREFIX_19 = 'H1-19'
const ITEM_PREFIX_20 = 'H1-20'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1LeaseCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const relatedRows = ref<RelatedPartyRow[]>([])
  const operatingRows = ref<OperatingLeaseRow[]>([])
  const financeRows = ref<FinanceLeaseRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    _loadArray(ITEM_PREFIX_18, relatedRows, _normalizeRelatedRow)
    _loadArray(ITEM_PREFIX_19, operatingRows, _normalizeOperatingRow)
    _loadArray(ITEM_PREFIX_20, financeRows, _normalizeFinanceRow)
    auditNote.value = _getString(`${ITEM_PREFIX_18}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX_18}-audit-conclusion`)
  }

  function _loadArray<T>(prefix: string, target: Ref<T[]>, normalize: (raw: any, idx: number) => T): void {
    const item = allResponses.value.get(`${prefix}-rows`)
    if (item?.remark) {
      try {
        const parsed = JSON.parse(item.remark)
        target.value = Array.isArray(parsed) ? parsed.map(normalize) : []
      } catch { target.value = [] }
    } else { target.value = [] }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRelatedRow(raw: any, idx: number): RelatedPartyRow {
    const transAmt = Number(raw.transAmount) || 0
    const appraised = Number(raw.appraisedValue) || 0
    const diffRate = appraised > 0 ? ((transAmt - appraised) / appraised * 100) : 0
    return {
      rowId: raw.rowId ?? `rp-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      counterparty: raw.counterparty ?? '',
      relationship: raw.relationship ?? '',
      transType: raw.transType ?? '',
      transDate: raw.transDate ?? '',
      transAmount: transAmt,
      bookValue: Number(raw.bookValue) || 0,
      appraisedValue: appraised,
      pricingBasis: raw.pricingBasis ?? '',
      priceDiffRate: diffRate,
      isFair: raw.isFair ?? '',
      approvalDoc: raw.approvalDoc ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeOperatingRow(raw: any, idx: number): OperatingLeaseRow {
    const annualRent = Number(raw.annualRent) || 0
    const leaseTerm = Number(raw.leaseTerm) || 0
    const monthlyRent = annualRent / 12
    const totalRent = monthlyRent * leaseTerm
    const dep = Number(raw.depAlloc) || 0
    const maint = Number(raw.maintenanceCost) || 0
    const netIncome = totalRent - dep - maint
    const origCost = Number(raw.originalCost) || 0
    const returnRate = origCost > 0 ? (netIncome / origCost * 100) : 0
    const marketRent = Number(raw.marketRent) || 0
    return {
      rowId: raw.rowId ?? `ol-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      lessee: raw.lessee ?? '',
      assetName: raw.assetName ?? '',
      originalCost: origCost,
      netValue: Number(raw.netValue) || 0,
      leaseStart: raw.leaseStart ?? '',
      leaseEnd: raw.leaseEnd ?? '',
      leaseTerm,
      annualRent,
      monthlyRent,
      totalRentIncome: totalRent,
      depAlloc: dep,
      maintenanceCost: maint,
      netIncome,
      returnRate,
      marketRent,
      rentDiff: annualRent - marketRent,
      contractNo: raw.contractNo ?? '',
      deposit: Number(raw.deposit) || 0,
      expiryDate: raw.expiryDate ?? '',
      renewalTerms: raw.renewalTerms ?? '',
      earlyTermination: raw.earlyTermination ?? '',
      isRelatedParty: raw.isRelatedParty ?? 'N',
      hasChanged: raw.hasChanged ?? 'N',
      accountTreatment: raw.accountTreatment ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeFinanceRow(raw: any, idx: number): FinanceLeaseRow {
    return {
      rowId: raw.rowId ?? `fl-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      lessee: raw.lessee ?? '',
      assetName: raw.assetName ?? '',
      originalCost: Number(raw.originalCost) || 0,
      classificationBasis: raw.classificationBasis ?? '',
      classResult1: raw.classResult1 ?? '',
      classResult2: raw.classResult2 ?? '',
      classResult3: raw.classResult3 ?? '',
      classResult4: raw.classResult4 ?? '',
      classResult5: raw.classResult5 ?? '',
      minLeasePayment: Number(raw.minLeasePayment) || 0,
      presentValue: Number(raw.presentValue) || 0,
      unrecognizedFinIncome: Number(raw.unrecognizedFinIncome) || 0,
      allocRate: Number(raw.allocRate) || 0,
      periodInterest: Number(raw.periodInterest) || 0,
      principalRecovery: Number(raw.principalRecovery) || 0,
      endBalance: Number(raw.endBalance) || 0,
      isRelatedParty: raw.isRelatedParty ?? 'N',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  /** 关联交易中价格差异率>10%的行 */
  const unfairPricingRows = computed(() =>
    relatedRows.value.filter((r) => Math.abs(r.priceDiffRate) > 10),
  )

  /** 经营租出汇总 */
  const operatingSummary = computed(() => ({
    count: operatingRows.value.length,
    totalRent: calcSubtotal(operatingRows.value.map((r) => r.totalRentIncome)),
    totalNetIncome: calcSubtotal(operatingRows.value.map((r) => r.netIncome)),
    avgReturnRate: operatingRows.value.length > 0
      ? calcSubtotal(operatingRows.value.map((r) => r.returnRate)) / operatingRows.value.length
      : 0,
  }))

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRelatedRow(): void {
    const newRow: RelatedPartyRow = {
      rowId: `rp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: relatedRows.value.length + 1,
      name: '', counterparty: '', relationship: '', transType: '',
      transDate: '', transAmount: 0, bookValue: 0, appraisedValue: 0,
      pricingBasis: '', priceDiffRate: 0, isFair: '', approvalDoc: '',
      conclusion: '', remark: '',
    }
    relatedRows.value.push(newRow)
    _persistRelated()
  }

  function addOperatingRow(): void {
    const newRow: OperatingLeaseRow = {
      rowId: `ol-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: operatingRows.value.length + 1,
      lessee: '', assetName: '', originalCost: 0, netValue: 0,
      leaseStart: '', leaseEnd: '', leaseTerm: 0, annualRent: 0,
      monthlyRent: 0, totalRentIncome: 0, depAlloc: 0, maintenanceCost: 0,
      netIncome: 0, returnRate: 0, marketRent: 0, rentDiff: 0,
      contractNo: '', deposit: 0, expiryDate: '',
      renewalTerms: '', earlyTermination: '',
      isRelatedParty: 'N', hasChanged: 'N', accountTreatment: '',
      conclusion: '', remark: '',
    }
    operatingRows.value.push(newRow)
    _persistOperating()
  }

  function addFinanceRow(): void {
    const newRow: FinanceLeaseRow = {
      rowId: `fl-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: financeRows.value.length + 1,
      lessee: '', assetName: '', originalCost: 0,
      classificationBasis: '',
      classResult1: '', classResult2: '', classResult3: '', classResult4: '', classResult5: '',
      minLeasePayment: 0, presentValue: 0, unrecognizedFinIncome: 0,
      allocRate: 0, periodInterest: 0, principalRecovery: 0, endBalance: 0,
      isRelatedParty: 'N', conclusion: '', remark: '',
    }
    financeRows.value.push(newRow)
    _persistFinance()
  }

  function removeRow(sheet: '18' | '19' | '20', rowId: string): void {
    if (sheet === '18') {
      const idx = relatedRows.value.findIndex((r) => r.rowId === rowId)
      if (idx >= 0) { relatedRows.value.splice(idx, 1); relatedRows.value.forEach((r, i) => { r.seq = i + 1 }); _persistRelated() }
    } else if (sheet === '19') {
      const idx = operatingRows.value.findIndex((r) => r.rowId === rowId)
      if (idx >= 0) { operatingRows.value.splice(idx, 1); operatingRows.value.forEach((r, i) => { r.seq = i + 1 }); _persistOperating() }
    } else {
      const idx = financeRows.value.findIndex((r) => r.rowId === rowId)
      if (idx >= 0) { financeRows.value.splice(idx, 1); financeRows.value.forEach((r, i) => { r.seq = i + 1 }); _persistFinance() }
    }
  }

  function updateRelatedCell(rowId: string, field: keyof RelatedPartyRow, value: any): void {
    const row = relatedRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 重算价格差异率
    row.priceDiffRate = row.appraisedValue > 0
      ? ((row.transAmount - row.appraisedValue) / row.appraisedValue * 100) : 0
    _persistRelated()
  }

  function updateOperatingCell(rowId: string, field: keyof OperatingLeaseRow, value: any): void {
    const row = operatingRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 重算公式列
    row.monthlyRent = row.annualRent / 12
    row.totalRentIncome = row.monthlyRent * row.leaseTerm
    row.netIncome = row.totalRentIncome - row.depAlloc - row.maintenanceCost
    row.returnRate = row.originalCost > 0 ? (row.netIncome / row.originalCost * 100) : 0
    row.rentDiff = row.annualRent - row.marketRent
    _persistOperating()
  }

  function updateFinanceCell(rowId: string, field: keyof FinanceLeaseRow, value: any): void {
    const row = financeRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistFinance()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistRelated(): void { options?.onSave?.(`${ITEM_PREFIX_18}-rows`, relatedRows.value) }
  function _persistOperating(): void { options?.onSave?.(`${ITEM_PREFIX_19}-rows`, operatingRows.value) }
  function _persistFinance(): void { options?.onSave?.(`${ITEM_PREFIX_20}-rows`, financeRows.value) }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX_18}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX_18}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    relatedRows,
    operatingRows,
    financeRows,
    auditNote,
    auditConclusion,
    // Computed
    unfairPricingRows,
    operatingSummary,
    // CRUD
    addRelatedRow,
    addOperatingRow,
    addFinanceRow,
    removeRow,
    updateRelatedCell,
    updateOperatingCell,
    updateFinanceCell,
    // Save
    saveNote,
    saveConclusion,
  }
}

export default useH1LeaseCheck
