/**
 * useH1DisposalCheck — H1-8 固定资产减少检查表 composable
 *
 * 对齐致同模板「固定资产减少检查表」编制逻辑：
 * 目标（发生/完整/计价）→ 测试原因 → 抽样 → 样本明细
 * （转入清理金额勾稽 + 清理净损益 + 关键证据）→ 检查比例 → 说明/结论 → 联动 H10
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Requirements: 9.1-9.11
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal, calcNetValue, calcDisposalGainLoss } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisposalRow {
  rowId: string
  seq: number
  /** 固定资产类别 */
  category: string
  name: string
  assetNo: string
  /** 减少方式：出售/报废/损毁/捐赠/盘亏/其他 */
  disposalMethod: string
  disposalDate: string
  /** 凭证号 */
  voucherNo: string
  /** 对方科目 */
  counterpartAccount: string
  // ── 转入清理的固定资产 ──
  originalCost: number
  accDep: number
  impairment: number
  netValue: number
  // ── 清理净收入 / 净损益 ──
  disposalCost: number
  disposalIncome: number
  disposalGainLoss: number
  // ── 关键证据：申报单 ──
  applicationRef: string
  /** 是否经过恰当审批 Y/N */
  isApproved: string
  // ── 关键证据：合同/协议/订单 ──
  contractRef: string
  contractParty: string
  contractAmount: number
  // ── 关键证据：发票 ──
  invoiceRef: string
  invoiceParty: string
  invoiceAmount: number
  // ── 其他检查列 ──
  approvalDoc: string
  evaluationReport: string
  paymentVoucher: string
  isRelatedParty: string
  relatedPartyName: string
  pricingBasis: string
  taxTreatment: string
  accountEntry: string
  /** 检查结果 OK / ERR */
  checkResult: string
  /** 是否异常 Y/N（模板 Z 列） */
  isAbnormal: string
  conclusion: string
  remark: string
  indexRef: string
  voucherSampleId: string
  attachmentUrl: string
}

/** 测试原因（模板勾选） */
export type DisposalTestReason =
  | 'largeAmount'
  | 'relatedParty'
  | 'frequentLarge'
  | 'abnormal'
  | 'other'

export interface DisposalSamplingParams {
  /** 本期减少固定资产合计（总体） */
  totalPopulation: number
  samplingMethod: string
  sampleSize: number
  coverageRate: number
}

export interface DisposalSummary {
  checkedCount: number
  /** 样本原值合计 */
  disposalAmountTotal: number
  /** 样本净值合计 */
  netValueTotal: number
  /** 处置收入合计 */
  incomeTotal: number
  /** 处置损益合计 */
  gainLossTotal: number
  /** 检查比例(%) = 样本原值 / 本期减少合计 */
  coverageRate: number
  anomalyCount: number
  /** 报废无收入且净值>0 的笔数 */
  scrapNoIncomeCount: number
}

/** H1-1/H1-2 联动的本期减少合计 */
export interface LinkedDecreaseTotal {
  amount: number
  /** H1-2 优先；无则回退 H1-1 原值贷方 */
  source: 'H1-2' | 'H1-1' | ''
  h2Amount: number
  h1Amount: number
}

const ITEM_PREFIX = 'H1-8'

const DEFAULT_TEST_REASONS: DisposalTestReason[] = []

function _safeParseArr(raw: string | null | undefined): any[] {
  if (!raw) return []
  try {
    const p = JSON.parse(raw)
    return Array.isArray(p) ? p : []
  } catch {
    return []
  }
}

function _num(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 是否报废类减少方式 */
export function isScrapMethod(method: string): boolean {
  const m = (method || '').trim()
  return m === '报废' || m === 'scrap' || m === '损毁' || m === 'damage'
}

export function useH1DisposalCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    totalDecreaseAmount?: Ref<number>
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  const rows = ref<DisposalRow[]>([])
  const samplingParams = ref<DisposalSamplingParams>({
    totalPopulation: 0,
    samplingMethod: '货币单元抽样',
    sampleSize: 0,
    coverageRate: 0,
  })
  /** 总体是否手工覆盖（手工改过则不再自动覆盖） */
  const populationManual = ref(false)
  const testReasons = ref<DisposalTestReason[]>([...DEFAULT_TEST_REASONS])
  const testReasonOther = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _loadData(): void {
    const rowItem = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (rowItem?.remark) {
      try {
        const parsed = JSON.parse(rowItem.remark)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
      } catch {
        rows.value = []
      }
    } else {
      rows.value = []
    }

    const paramItem = allResponses.value.get(`${ITEM_PREFIX}-sampling-params`)
    if (paramItem?.remark) {
      try {
        const p = JSON.parse(paramItem.remark)
        samplingParams.value = {
          totalPopulation: Number(p.totalPopulation) || 0,
          samplingMethod: p.samplingMethod ?? '货币单元抽样',
          sampleSize: Number(p.sampleSize) || 0,
          coverageRate: Number(p.coverageRate) || 0,
        }
        populationManual.value = Boolean(p.populationManual)
      } catch { /* keep defaults */ }
    }

    const reasonItem = allResponses.value.get(`${ITEM_PREFIX}-test-reasons`)
    if (reasonItem?.remark) {
      try {
        const r = JSON.parse(reasonItem.remark)
        testReasons.value = Array.isArray(r.reasons) ? r.reasons : []
        testReasonOther.value = r.otherText ?? ''
      } catch { /* keep defaults */ }
    }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)

    // 总体为空且非手工锁定时，自动从 H1-2/H1-1 带入（仅内存；持久化由后续编辑/手动带入触发）
    if (!populationManual.value && !(samplingParams.value.totalPopulation > 0)) {
      const linked = _calcLinkedDecrease()
      if (linked.amount > 0) {
        samplingParams.value.totalPopulation = linked.amount
        samplingParams.value.coverageRate =
          samplingParams.value.totalPopulation > 0
            ? (calcSubtotal(rows.value.map((r) => r.originalCost)) / samplingParams.value.totalPopulation) * 100
            : 0
      }
    }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  /** 从 H1-2 原值本期减少 / H1-1 原值贷方合计取数 */
  function _calcLinkedDecrease(): LinkedDecreaseTotal {
    const h2Rows = _safeParseArr(allResponses.value.get('H1-2-rows')?.remark)
    let h2Amount = 0
    for (const r of h2Rows) {
      h2Amount += _num(r.costDecUnadj ?? r.originalCostDecrease)
    }

    const h1Rows = _safeParseArr(allResponses.value.get('H1-1-cost-rows')?.remark)
    let h1Amount = 0
    for (const r of h1Rows) {
      if (r.isSubtotal) continue
      h1Amount += _num(r.credit)
    }

    if (h2Amount > 0) {
      return { amount: h2Amount, source: 'H1-2', h2Amount, h1Amount }
    }
    if (h1Amount > 0) {
      return { amount: h1Amount, source: 'H1-1', h2Amount, h1Amount }
    }
    return { amount: 0, source: '', h2Amount, h1Amount }
  }

  const linkedDecrease = computed<LinkedDecreaseTotal>(() => _calcLinkedDecrease())

  function _normalizeRow(raw: any, idx: number): DisposalRow {
    // 兼容旧字段名 disposalType / gainLoss
    const method = raw.disposalMethod ?? raw.disposalType ?? ''
    const row: DisposalRow = {
      rowId: raw.rowId ?? `disp-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      category: raw.category ?? '',
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      disposalMethod: method,
      disposalDate: raw.disposalDate ?? '',
      voucherNo: raw.voucherNo ?? '',
      counterpartAccount: raw.counterpartAccount ?? '',
      originalCost: Number(raw.originalCost) || 0,
      accDep: Number(raw.accDep) || 0,
      impairment: Number(raw.impairment) || 0,
      netValue: 0,
      disposalCost: Number(raw.disposalCost) || 0,
      disposalIncome: Number(raw.disposalIncome) || 0,
      disposalGainLoss: 0,
      applicationRef: raw.applicationRef ?? '',
      isApproved: raw.isApproved ?? '',
      contractRef: raw.contractRef ?? '',
      contractParty: raw.contractParty ?? '',
      contractAmount: Number(raw.contractAmount) || 0,
      invoiceRef: raw.invoiceRef ?? '',
      invoiceParty: raw.invoiceParty ?? '',
      invoiceAmount: Number(raw.invoiceAmount) || 0,
      approvalDoc: raw.approvalDoc ?? '',
      evaluationReport: raw.evaluationReport ?? '',
      paymentVoucher: raw.paymentVoucher ?? '',
      isRelatedParty: raw.isRelatedParty ?? 'N',
      relatedPartyName: raw.relatedPartyName ?? '',
      pricingBasis: raw.pricingBasis ?? '',
      taxTreatment: raw.taxTreatment ?? '',
      accountEntry: raw.accountEntry ?? '',
      checkResult: raw.checkResult ?? '',
      isAbnormal: raw.isAbnormal ?? (raw.checkResult === 'ERR' ? 'Y' : 'N'),
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      indexRef: raw.indexRef ?? '',
      voucherSampleId: raw.voucherSampleId ?? '',
      attachmentUrl: raw.attachmentUrl ?? '',
    }
    _recalcRow(row)
    return row
  }

  function _recalcRow(row: DisposalRow): void {
    row.netValue = calcNetValue(row.originalCost, row.accDep, row.impairment)
    row.disposalGainLoss = calcDisposalGainLoss(row.disposalIncome, row.netValue, row.disposalCost)
  }

  /** 出售且关联方但缺评估报告 → 需提示 */
  function needsEvalWarning(row: DisposalRow): boolean {
    const isSale = row.disposalMethod === '出售' || row.disposalMethod === 'sale'
    return isSale && row.isRelatedParty === 'Y' && !row.evaluationReport?.trim()
  }

  /**
   * 报废/损毁且清理收入为 0、账面净值>0 → 残值专项提示
   * （关注残值回收、废料变卖、保险赔款是否漏记）
   */
  function needsScrapResidualWarning(row: DisposalRow): boolean {
    if (!isScrapMethod(row.disposalMethod)) return false
    if ((Number(row.disposalIncome) || 0) > 0) return false
    return (Number(row.netValue) || 0) > 0
  }

  const summary = computed<DisposalSummary>(() => {
    const checkedCount = rows.value.length
    const disposalAmountTotal = calcSubtotal(rows.value.map((r) => r.originalCost))
    const netValueTotal = calcSubtotal(rows.value.map((r) => r.netValue))
    const incomeTotal = calcSubtotal(rows.value.map((r) => r.disposalIncome))
    const gainLossTotal = calcSubtotal(rows.value.map((r) => r.disposalGainLoss))
    const anomalyCount = rows.value.filter(
      (r) => r.isAbnormal === 'Y' || r.checkResult === 'ERR',
    ).length
    const scrapNoIncomeCount = rows.value.filter((r) => needsScrapResidualWarning(r)).length
    const totalDec =
      options?.totalDecreaseAmount?.value ?? samplingParams.value.totalPopulation
    const coverageRate = totalDec > 0 ? (disposalAmountTotal / totalDec) * 100 : 0
    return {
      checkedCount,
      disposalAmountTotal,
      netValueTotal,
      incomeTotal,
      gainLossTotal,
      coverageRate,
      anomalyCount,
      scrapNoIncomeCount,
    }
  })

  const incomeTotal = computed(() => summary.value.incomeTotal)
  const gainLossTotal = computed(() => summary.value.gainLossTotal)

  function addRow(name = ''): void {
    const newRow: DisposalRow = {
      rowId: `disp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      category: '',
      name,
      assetNo: '',
      disposalMethod: '',
      disposalDate: '',
      voucherNo: '',
      counterpartAccount: '',
      originalCost: 0,
      accDep: 0,
      impairment: 0,
      netValue: 0,
      disposalCost: 0,
      disposalIncome: 0,
      disposalGainLoss: 0,
      applicationRef: '',
      isApproved: '',
      contractRef: '',
      contractParty: '',
      contractAmount: 0,
      invoiceRef: '',
      invoiceParty: '',
      invoiceAmount: 0,
      approvalDoc: '',
      evaluationReport: '',
      paymentVoucher: '',
      isRelatedParty: 'N',
      relatedPartyName: '',
      pricingBasis: '',
      taxTreatment: '',
      accountEntry: '',
      checkResult: '',
      isAbnormal: 'N',
      conclusion: '',
      remark: '',
      indexRef: '',
      voucherSampleId: '',
      attachmentUrl: '',
    }
    rows.value.push(newRow)
    _syncSampleSize()
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => {
        r.seq = i + 1
      })
      _syncSampleSize()
      _persist()
    }
  }

  function updateCell(rowId: string, field: keyof DisposalRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'isAbnormal' && value === 'Y' && !row.checkResult) {
      row.checkResult = 'ERR'
    }
    if (field === 'isAbnormal' && value === 'N' && row.checkResult === 'ERR') {
      row.checkResult = 'OK'
    }
    if (field === 'checkResult') {
      row.isAbnormal = value === 'ERR' ? 'Y' : 'N'
    }
    _recalcRow(row)
    _persist()
  }

  /** 将 OCR 识别字段合并入行（仅填空或覆盖金额类） */
  function applyOcrFields(rowId: string, fields: Record<string, any>): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const f = fields || {}
    if (f.invoiceNo || f.invoice_no || f.invoiceRef) {
      row.invoiceRef = String(f.invoiceNo || f.invoice_no || f.invoiceRef)
    }
    if (f.invoiceParty || f.counterparty || f.buyer || f.seller) {
      row.invoiceParty = String(f.invoiceParty || f.counterparty || f.buyer || f.seller)
    }
    if (f.invoiceAmount != null || f.amount != null) {
      const amt = _num(f.invoiceAmount ?? f.amount)
      if (amt) {
        row.invoiceAmount = amt
        if (!row.disposalIncome) row.disposalIncome = amt
      }
    }
    if (f.contractNo || f.contract_no || f.contractRef) {
      row.contractRef = String(f.contractNo || f.contract_no || f.contractRef)
    }
    if (f.contractParty || f.supplier || f.counterparty) {
      row.contractParty = String(f.contractParty || f.supplier || f.counterparty)
    }
    if (f.contractAmount != null) {
      row.contractAmount = _num(f.contractAmount)
    }
    if (f.date || f.disposalDate || f.entryDate) {
      row.disposalDate = String(f.date || f.disposalDate || f.entryDate)
    }
    if (f.voucherNo || f.voucher_no) {
      row.voucherNo = String(f.voucherNo || f.voucher_no)
    }
    if (f.assetName || f.name) {
      if (!row.name) row.name = String(f.assetName || f.name)
    }
    if (f.originalCost != null) {
      row.originalCost = _num(f.originalCost)
    }
    _recalcRow(row)
    _persist()
  }

  function _syncSampleSize(): void {
    samplingParams.value.sampleSize = rows.value.length
    samplingParams.value.coverageRate = summary.value.coverageRate
  }

  function publishDisposalCompleted(): void {
    options?.onPublishEvent?.('h1:disposal-completed', {
      wp_code: 'H1',
      rows: rows.value.map((r) => ({
        rowId: r.rowId,
        name: r.name,
        assetNo: r.assetNo,
        disposalMethod: r.disposalMethod,
        disposalDate: r.disposalDate,
        originalCost: r.originalCost,
        accDep: r.accDep,
        impairment: r.impairment,
        netValue: r.netValue,
        disposalIncome: r.disposalIncome,
        disposalCost: r.disposalCost,
        disposalGainLoss: r.disposalGainLoss,
        isRelatedParty: r.isRelatedParty,
        relatedPartyName: r.relatedPartyName,
      })),
      totalGainLoss: summary.value.gainLossTotal,
    })
  }

  function updateSamplingParams(params: Partial<DisposalSamplingParams> & { populationManual?: boolean }): void {
    if (params.totalPopulation != null) {
      populationManual.value = params.populationManual !== false
    }
    if (params.populationManual != null) {
      populationManual.value = params.populationManual
    }
    const { populationManual: _pm, ...rest } = params
    Object.assign(samplingParams.value, rest)
    samplingParams.value.coverageRate = summary.value.coverageRate
    _persistSampling()
  }

  /** 从 H1-2（优先）或 H1-1 带入本期减少合计 */
  function syncPopulationFromLinked(force = true): { ok: boolean; amount: number; source: string } {
    const linked = _calcLinkedDecrease()
    if (!(linked.amount > 0)) {
      return { ok: false, amount: 0, source: '' }
    }
    if (!force && populationManual.value && samplingParams.value.totalPopulation > 0) {
      return { ok: false, amount: samplingParams.value.totalPopulation, source: 'manual' }
    }
    samplingParams.value.totalPopulation = linked.amount
    populationManual.value = false
    samplingParams.value.coverageRate = summary.value.coverageRate
    _persistSampling()
    return { ok: true, amount: linked.amount, source: linked.source }
  }

  function updateTestReasons(reasons: DisposalTestReason[], otherText = ''): void {
    testReasons.value = reasons
    testReasonOther.value = otherText
    options?.onSave?.(`${ITEM_PREFIX}-test-reasons`, {
      reasons,
      otherText,
    })
  }

  function _persistSampling(): void {
    options?.onSave?.(`${ITEM_PREFIX}-sampling-params`, {
      ...samplingParams.value,
      populationManual: populationManual.value,
    })
  }

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
    samplingParams.value.sampleSize = rows.value.length
    samplingParams.value.coverageRate = summary.value.coverageRate
    _persistSampling()
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  watch(allResponses, () => _loadData(), { immediate: true })

  return {
    rows,
    samplingParams,
    populationManual,
    linkedDecrease,
    testReasons,
    testReasonOther,
    auditNote,
    auditConclusion,
    summary,
    incomeTotal,
    gainLossTotal,
    addRow,
    removeRow,
    updateCell,
    applyOcrFields,
    needsEvalWarning,
    needsScrapResidualWarning,
    publishDisposalCompleted,
    updateSamplingParams,
    syncPopulationFromLinked,
    updateTestReasons,
    saveNote,
    saveConclusion,
  }
}

export default useH1DisposalCheck
