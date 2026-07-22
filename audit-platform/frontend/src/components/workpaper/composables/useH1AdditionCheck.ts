/**
 * useH1AdditionCheck — H1-7 固定资产增加检查表 composable
 *
 * 对齐致同模板编制逻辑：
 * 目标 → 样本选取 → 账→证抽查（vouching）+ 证→账追查（tracing）
 * → 按增加方式专项清单 → 暂估/折旧起算联动 H1-12 → 检查比例 → 说明/结论
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal, calcNetValue } from './useH1FormulaEngine'
import {
  getMethodChecklist,
  calcChecklistProgress,
} from './h1AdditionMethodChecklist'
import { readH12BranchRows, saveH12BranchRows } from './h1H12BranchKeys'

export { getMethodChecklist, calcChecklistProgress, METHOD_CHECKLISTS } from './h1AdditionMethodChecklist'
export type { MethodChecklistItem } from './h1AdditionMethodChecklist'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdditionRow {
  rowId: string
  seq: number
  category: string
  name: string
  assetNo: string
  acquisitionDate: string
  additionMethod: string
  voucherNo: string
  counterpartAccount: string
  originalCost: number
  accDep: number
  impairment: number
  netValue: number
  acceptanceRef: string
  acceptanceDate: string
  contractRef: string
  contractParty: string
  contractAmount: number
  invoiceRef: string
  invoiceParty: string
  invoiceAmount: number
  paymentRef: string
  paymentAmount: number
  capitalizationBasis: string
  expenseOrCapital: string
  accountCode: string
  depStartDate: string
  /** 是否暂估入账 Y/N */
  isProvisional: string
  /** 按增加方式的专项勾选 { checklistKey: Y|N|NA|'' } */
  methodChecks: Record<string, string>
  attachmentUrl: string
  ocrResult: string
  isRelatedParty: string
  relatedPartyName: string
  isAbnormal: string
  checkResult: string
  conclusion: string
  remark: string
  indexRef: string
  voucherSampleId: string
}

/**
 * 证→账追查行（完整性）：从外部/内部源文件追查至账面是否入账
 */
export interface TraceRow {
  rowId: string
  seq: number
  /** 源文件类型：验收单/合同/发票/发运单/其他 */
  sourceType: string
  sourceRef: string
  sourceDate: string
  sourceParty: string
  sourceAmount: number
  /** 是否已入账 Y/N */
  recordedInBooks: string
  bookVoucherNo: string
  bookAssetNo: string
  bookAssetName: string
  bookAmount: number
  /** 差额 = 源金额 − 账面金额（公式） */
  amountDiff: number
  checkResult: string
  remark: string
  indexRef: string
}

export type AdditionTestReason =
  | 'largeAmount'
  | 'relatedParty'
  | 'abnormal'
  | 'newCategory'
  | 'other'

export interface SamplingParams {
  totalPopulation: number
  samplingMethod: string
  sampleSize: number
  coverageRate: number
}

export interface AdditionSummary {
  checkedCount: number
  checkedAmount: number
  netValueTotal: number
  coverageRate: number
  anomalyCount: number
  amountMismatchCount: number
  cipNoAcceptanceCount: number
  /** 暂估但缺折旧起算日 */
  provisionalNoDepStartCount: number
  /** 专项清单未完成笔数 */
  checklistIncompleteCount: number
  /** 证→账追查笔数 */
  traceCount: number
  /** 追查未入账笔数 */
  traceUnrecordedCount: number
}

export interface LinkedIncreaseTotal {
  amount: number
  source: 'H1-2' | 'H1-1' | ''
  h2Amount: number
  h1Amount: number
}

export interface H12DepLinkResult {
  linked: number
  notes: string[]
}

const ITEM_PREFIX = 'H1-7'
const DEFAULT_TEST_REASONS: AdditionTestReason[] = []
const AMOUNT_TOLERANCE = 1

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

export function isCipTransferMethod(method: string): boolean {
  const m = (method || '').trim()
  return m === '在建工程转入' || m === 'cip' || m === '在建转入' || m.includes('在建')
}

/** 解析应推送至 H1-12 的折旧起算日 */
export function resolveDepStartDate(row: Pick<AdditionRow, 'depStartDate' | 'acceptanceDate' | 'acquisitionDate'>): string {
  return String(row.depStartDate || row.acceptanceDate || row.acquisitionDate || '').trim()
}

export function useH1AdditionCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    totalAdditionAmount?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<AdditionRow[]>([])
  const traceRows = ref<TraceRow[]>([])
  const samplingParams = ref<SamplingParams>({
    totalPopulation: 0,
    samplingMethod: '货币单元抽样',
    sampleSize: 0,
    coverageRate: 0,
  })
  const populationManual = ref(false)
  const testReasons = ref<AdditionTestReason[]>([...DEFAULT_TEST_REASONS])
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

    const traceItem = allResponses.value.get(`${ITEM_PREFIX}-trace-rows`)
    if (traceItem?.remark) {
      try {
        const parsed = JSON.parse(traceItem.remark)
        traceRows.value = Array.isArray(parsed) ? parsed.map(_normalizeTraceRow) : []
      } catch {
        traceRows.value = []
      }
    } else {
      traceRows.value = []
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

    if (!populationManual.value && !(samplingParams.value.totalPopulation > 0)) {
      const linked = _calcLinkedIncrease()
      if (linked.amount > 0) {
        samplingParams.value.totalPopulation = linked.amount
      }
    }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _calcLinkedIncrease(): LinkedIncreaseTotal {
    const h2Rows = _safeParseArr(allResponses.value.get('H1-2-rows')?.remark)
    let h2Amount = 0
    for (const r of h2Rows) h2Amount += _num(r.costIncUnadj ?? r.originalCostIncrease)

    const h1Rows = _safeParseArr(allResponses.value.get('H1-1-cost-rows')?.remark)
    let h1Amount = 0
    for (const r of h1Rows) {
      if (r.isSubtotal) continue
      h1Amount += _num(r.debit)
    }

    if (h2Amount > 0) return { amount: h2Amount, source: 'H1-2', h2Amount, h1Amount }
    if (h1Amount > 0) return { amount: h1Amount, source: 'H1-1', h2Amount, h1Amount }
    return { amount: 0, source: '', h2Amount, h1Amount }
  }

  const linkedIncrease = computed<LinkedIncreaseTotal>(() => _calcLinkedIncrease())

  function _normalizeRow(raw: any, idx: number): AdditionRow {
    const cost = _num(raw.originalCost ?? raw.amount)
    const row: AdditionRow = {
      rowId: raw.rowId ?? `add-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      category: raw.category ?? '',
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      acquisitionDate: raw.acquisitionDate ?? raw.entryDate ?? '',
      additionMethod: raw.additionMethod ?? '',
      voucherNo: raw.voucherNo ?? '',
      counterpartAccount: raw.counterpartAccount ?? '',
      originalCost: cost,
      accDep: _num(raw.accDep),
      impairment: _num(raw.impairment),
      netValue: 0,
      acceptanceRef: raw.acceptanceRef ?? '',
      acceptanceDate: raw.acceptanceDate ?? '',
      contractRef: raw.contractRef ?? raw.contractNo ?? '',
      contractParty: raw.contractParty ?? raw.supplier ?? '',
      contractAmount: _num(raw.contractAmount),
      invoiceRef: raw.invoiceRef ?? raw.invoiceNo ?? '',
      invoiceParty: raw.invoiceParty ?? raw.supplier ?? '',
      invoiceAmount: _num(raw.invoiceAmount),
      paymentRef: raw.paymentRef ?? '',
      paymentAmount: _num(raw.paymentAmount),
      capitalizationBasis: raw.capitalizationBasis ?? '',
      expenseOrCapital: raw.expenseOrCapital ?? '资本化',
      accountCode: raw.accountCode ?? '',
      depStartDate: raw.depStartDate ?? '',
      isProvisional: raw.isProvisional ?? (String(raw.remark || '').includes('暂估') ? 'Y' : 'N'),
      methodChecks: (raw.methodChecks && typeof raw.methodChecks === 'object') ? { ...raw.methodChecks } : {},
      attachmentUrl: raw.attachmentUrl ?? '',
      ocrResult: raw.ocrResult ?? '',
      isRelatedParty: raw.isRelatedParty ?? 'N',
      relatedPartyName: raw.relatedPartyName ?? '',
      checkResult: raw.checkResult ?? '',
      isAbnormal: raw.isAbnormal ?? (raw.checkResult === 'ERR' || raw.checkResult === '异常' ? 'Y' : 'N'),
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      indexRef: raw.indexRef ?? '',
      voucherSampleId: raw.voucherSampleId ?? '',
    }
    if (row.checkResult === '异常' || row.checkResult === '有异常') row.checkResult = 'ERR'
    if (row.checkResult === '无异常') row.checkResult = 'OK'
    _recalcRow(row)
    return row
  }

  function _normalizeTraceRow(raw: any, idx: number): TraceRow {
    const row: TraceRow = {
      rowId: raw.rowId ?? `trc-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      sourceType: raw.sourceType ?? '',
      sourceRef: raw.sourceRef ?? '',
      sourceDate: raw.sourceDate ?? '',
      sourceParty: raw.sourceParty ?? '',
      sourceAmount: _num(raw.sourceAmount),
      recordedInBooks: raw.recordedInBooks ?? '',
      bookVoucherNo: raw.bookVoucherNo ?? '',
      bookAssetNo: raw.bookAssetNo ?? '',
      bookAssetName: raw.bookAssetName ?? '',
      bookAmount: _num(raw.bookAmount),
      amountDiff: 0,
      checkResult: raw.checkResult ?? '',
      remark: raw.remark ?? '',
      indexRef: raw.indexRef ?? '',
    }
    _recalcTrace(row)
    return row
  }

  function _recalcRow(row: AdditionRow): void {
    row.netValue = calcNetValue(row.originalCost, row.accDep, row.impairment)
  }

  function _recalcTrace(row: TraceRow): void {
    row.amountDiff = round2(_num(row.sourceAmount) - _num(row.bookAmount))
  }

  function needsAmountMismatchWarning(row: AdditionRow): boolean {
    const book = _num(row.originalCost)
    if (!(book > 0)) return false
    const inv = _num(row.invoiceAmount)
    if (inv > 0) return Math.abs(book - inv) > AMOUNT_TOLERANCE
    const ctr = _num(row.contractAmount)
    if (ctr > 0) return Math.abs(book - ctr) > AMOUNT_TOLERANCE
    return false
  }

  function needsCipAcceptanceWarning(row: AdditionRow): boolean {
    if (!isCipTransferMethod(row.additionMethod)) return false
    return !String(row.acceptanceRef || '').trim()
  }

  /** 暂估入账但缺折旧起算日 */
  function needsProvisionalDepWarning(row: AdditionRow): boolean {
    const isProv = row.isProvisional === 'Y' || String(row.remark || '').includes('暂估')
    if (!isProv) return false
    return !resolveDepStartDate(row)
  }

  function needsChecklistIncompleteWarning(row: AdditionRow): boolean {
    const items = getMethodChecklist(row.additionMethod)
    if (!items.length) return false
    return calcChecklistProgress(row.methodChecks, items).incomplete
  }

  /** 本期「在建工程转入」增加合计（供与 H2 转固勾稽） */
  const cipTransferInTotal = computed(() =>
    calcSubtotal(
      rows.value
        .filter((r) => isCipTransferMethod(r.additionMethod))
        .map((r) => r.originalCost),
    ),
  )

  /** 本期购建固定资产实际支付现金合计（供与现金流量表投资活动勾稽） */
  const cashPaidTotal = computed(() =>
    calcSubtotal(rows.value.map((r) => r.paymentAmount)),
  )

  const summary = computed<AdditionSummary>(() => {
    const checkedCount = rows.value.length
    const checkedAmount = calcSubtotal(rows.value.map((r) => r.originalCost))
    const netValueTotal = calcSubtotal(rows.value.map((r) => r.netValue))
    const anomalyCount = rows.value.filter(
      (r) => r.isAbnormal === 'Y' || r.checkResult === 'ERR',
    ).length
    const amountMismatchCount = rows.value.filter((r) => needsAmountMismatchWarning(r)).length
    const cipNoAcceptanceCount = rows.value.filter((r) => needsCipAcceptanceWarning(r)).length
    const provisionalNoDepStartCount = rows.value.filter((r) => needsProvisionalDepWarning(r)).length
    const checklistIncompleteCount = rows.value.filter((r) => needsChecklistIncompleteWarning(r)).length
    const traceCount = traceRows.value.length
    const traceUnrecordedCount = traceRows.value.filter(
      (r) => r.recordedInBooks === 'N' || r.checkResult === 'ERR',
    ).length
    const totalAdd =
      options?.totalAdditionAmount?.value ?? samplingParams.value.totalPopulation
    const coverageRate = totalAdd > 0 ? (checkedAmount / totalAdd) * 100 : 0
    return {
      checkedCount,
      checkedAmount,
      netValueTotal,
      coverageRate,
      anomalyCount,
      amountMismatchCount,
      cipNoAcceptanceCount,
      provisionalNoDepStartCount,
      checklistIncompleteCount,
      traceCount,
      traceUnrecordedCount,
    }
  })

  function _emptyRow(name = ''): AdditionRow {
    return {
      rowId: `add-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      category: '',
      name,
      assetNo: '',
      acquisitionDate: '',
      additionMethod: '',
      voucherNo: '',
      counterpartAccount: '',
      originalCost: 0,
      accDep: 0,
      impairment: 0,
      netValue: 0,
      acceptanceRef: '',
      acceptanceDate: '',
      contractRef: '',
      contractParty: '',
      contractAmount: 0,
      invoiceRef: '',
      invoiceParty: '',
      invoiceAmount: 0,
      paymentRef: '',
      paymentAmount: 0,
      capitalizationBasis: '',
      expenseOrCapital: '资本化',
      accountCode: '',
      depStartDate: '',
      isProvisional: 'N',
      methodChecks: {},
      attachmentUrl: '',
      ocrResult: '',
      isRelatedParty: 'N',
      relatedPartyName: '',
      checkResult: '',
      isAbnormal: 'N',
      conclusion: '',
      remark: '',
      indexRef: '',
      voucherSampleId: '',
    }
  }

  function addRow(name = ''): void {
    rows.value.push(_emptyRow(name))
    _syncSampleSize()
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _syncSampleSize()
      _persist()
    }
  }

  function updateCell(rowId: string, field: keyof AdditionRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'isAbnormal' && value === 'Y' && !row.checkResult) row.checkResult = 'ERR'
    if (field === 'isAbnormal' && value === 'N' && row.checkResult === 'ERR') row.checkResult = 'OK'
    if (field === 'checkResult') row.isAbnormal = value === 'ERR' ? 'Y' : 'N'
    if (field === 'additionMethod') {
      // 切换方式时保留已有同名 key，其余不强制清空
    }
    _recalcRow(row)
    _persist()
  }

  function updateMethodCheck(rowId: string, key: string, value: string): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    row.methodChecks = { ...row.methodChecks, [key]: value }
    _persist()
  }

  // ─── 证→账追查 ────────────────────────────────────────────────────────────

  function addTraceRow(sourceRef = ''): void {
    const row: TraceRow = {
      rowId: `trc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: traceRows.value.length + 1,
      sourceType: '发票',
      sourceRef,
      sourceDate: '',
      sourceParty: '',
      sourceAmount: 0,
      recordedInBooks: '',
      bookVoucherNo: '',
      bookAssetNo: '',
      bookAssetName: '',
      bookAmount: 0,
      amountDiff: 0,
      checkResult: '',
      remark: '',
      indexRef: '',
    }
    traceRows.value.push(row)
    _persistTrace()
  }

  function removeTraceRow(rowId: string): void {
    const idx = traceRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      traceRows.value.splice(idx, 1)
      traceRows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistTrace()
    }
  }

  function updateTraceCell(rowId: string, field: keyof TraceRow, value: any): void {
    const row = traceRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'recordedInBooks' && value === 'N' && !row.checkResult) {
      row.checkResult = 'ERR'
    }
    if (field === 'recordedInBooks' && value === 'Y' && row.checkResult === 'ERR') {
      row.checkResult = 'OK'
    }
    _recalcTrace(row)
    _persistTrace()
  }

  /** 从账→证样本生成证→账追查线索（已有发票/合同的行） */
  function seedTraceFromVouchRows(): number {
    let n = 0
    for (const r of rows.value) {
      const hasSrc = r.invoiceRef || r.contractRef || r.acceptanceRef
      if (!hasSrc) continue
      const already = traceRows.value.some(
        (t) =>
          (r.invoiceRef && t.sourceRef === r.invoiceRef)
          || (r.contractRef && t.sourceRef === r.contractRef)
          || (r.acceptanceRef && t.sourceRef === r.acceptanceRef),
      )
      if (already) continue
      const sourceType = r.invoiceRef ? '发票' : r.contractRef ? '合同' : '验收单'
      const sourceRef = r.invoiceRef || r.contractRef || r.acceptanceRef
      const sourceAmount = r.invoiceAmount || r.contractAmount || r.originalCost
      const tr: TraceRow = {
        rowId: `trc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}-${n}`,
        seq: traceRows.value.length + 1,
        sourceType,
        sourceRef,
        sourceDate: r.acceptanceDate || r.acquisitionDate || '',
        sourceParty: r.invoiceParty || r.contractParty || '',
        sourceAmount,
        recordedInBooks: (r.voucherNo || r.originalCost > 0) ? 'Y' : '',
        bookVoucherNo: r.voucherNo,
        bookAssetNo: r.assetNo,
        bookAssetName: r.name,
        bookAmount: r.originalCost,
        amountDiff: 0,
        checkResult: '',
        remark: `自账→证样本带入(${r.rowId})`,
        indexRef: r.indexRef || '',
      }
      _recalcTrace(tr)
      traceRows.value.push(tr)
      n++
    }
    if (n) _persistTrace()
    return n
  }

  // ─── OCR ───────────────────────────────────────────────────────────────────

  function mergeOcrResult(rowId: string, ocrData: Record<string, any>): void {
    applyOcrFields(rowId, ocrData)
  }

  function applyOcrFields(rowId: string, fields: Record<string, any>): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const f = fields || {}
    if (f.invoiceNo || f.invoice_no || f.invoiceRef) {
      row.invoiceRef = String(f.invoiceNo || f.invoice_no || f.invoiceRef)
    }
    if (f.invoiceParty || f.counterparty || f.seller || f.supplier) {
      row.invoiceParty = String(f.invoiceParty || f.counterparty || f.seller || f.supplier)
    }
    if (f.invoiceAmount != null || f.amount != null) {
      const amt = _num(f.invoiceAmount ?? f.amount)
      if (amt) {
        row.invoiceAmount = amt
        if (!row.originalCost) row.originalCost = amt
      }
    }
    if (f.contractNo || f.contract_no || f.contractRef) {
      row.contractRef = String(f.contractNo || f.contract_no || f.contractRef)
    }
    if (f.contractParty || f.supplier || f.counterparty) {
      if (!row.contractParty) {
        row.contractParty = String(f.contractParty || f.supplier || f.counterparty)
      }
    }
    if (f.contractAmount != null) row.contractAmount = _num(f.contractAmount)
    if (f.acceptanceRef || f.acceptance_no) {
      row.acceptanceRef = String(f.acceptanceRef || f.acceptance_no)
    }
    if (f.acceptanceDate) row.acceptanceDate = String(f.acceptanceDate)
    if (f.date || f.acquisitionDate || f.entryDate) {
      row.acquisitionDate = String(f.date || f.acquisitionDate || f.entryDate)
    }
    if (f.voucherNo || f.voucher_no) row.voucherNo = String(f.voucherNo || f.voucher_no)
    if ((f.assetName || f.name) && !row.name) row.name = String(f.assetName || f.name)
    if (f.originalCost != null) row.originalCost = _num(f.originalCost)
    if (f.depStartDate || f.startDate) {
      row.depStartDate = String(f.depStartDate || f.startDate)
    }
    row.ocrResult = JSON.stringify(f)
    _recalcRow(row)
    _persist()
  }

  // ─── H1-12 折旧起算联动 ────────────────────────────────────────────────────

  /**
   * 将 H1-7 样本的折旧起算日（暂估转固优先）推送至 H1-12：
   * 按资产编号/名称匹配，更新 startDate；无匹配则记 notes。
   */
  function pushDepStartToH12(): H12DepLinkResult {
    const { branch, rows: h12Raw } = readH12BranchRows(allResponses.value)
    if (!h12Raw.length) {
      return { linked: 0, notes: ['H1-12 尚无折旧测算行，请先导入台账或从 H1-2 带入'] }
    }
    const notes: string[] = []
    let linked = 0
    const candidates = rows.value.filter((r) => resolveDepStartDate(r) && (r.assetNo || r.name))
    if (!candidates.length) {
      return { linked: 0, notes: ['无可推送行：请填写折旧起算日（或验收日/增加日）及资产编号/名称'] }
    }

    for (const src of candidates) {
      const start = resolveDepStartDate(src)
      const hit = h12Raw.find((r: any) =>
        (src.assetNo && r.assetNo && src.assetNo === r.assetNo)
        || (src.name && (r.assetName === src.name || r.name === src.name)),
      )
      if (!hit) {
        notes.push(`未匹配 H1-12：「${src.name || src.assetNo}」`)
        continue
      }
      const prev = hit.startDate || ''
      hit.startDate = start
      hit.linkedFromH17 = true
      if (src.isProvisional === 'Y' && !String(hit.remark || '').includes('暂估')) {
        hit.remark = `${hit.remark ? hit.remark + '; ' : ''}H1-7暂估转固起算`
      } else if (!String(hit.remark || '').includes('H1-7')) {
        hit.remark = `${hit.remark ? hit.remark + '; ' : ''}来源勾稽:H1-7增加`
      }
      if (prev && prev !== start) {
        notes.push(`${src.name || src.assetNo}：起算日 ${prev} → ${start}`)
      }
      linked++
    }

    if (linked > 0) {
      saveH12BranchRows(options?.onSave, branch, h12Raw)
    }
    return { linked, notes }
  }

  /** 预览与 H1-12 的匹配情况（不写入） */
  function previewH12DepLink(): { matchable: number; missingStart: number; h12Count: number } {
    const { rows: h12Raw } = readH12BranchRows(allResponses.value)
    let matchable = 0
    let missingStart = 0
    for (const src of rows.value) {
      if (!(src.assetNo || src.name)) continue
      const hit = h12Raw.some((r: any) =>
        (src.assetNo && r.assetNo && src.assetNo === r.assetNo)
        || (src.name && (r.assetName === src.name || r.name === src.name)),
      )
      if (!hit) continue
      if (resolveDepStartDate(src)) matchable++
      else missingStart++
    }
    return { matchable, missingStart, h12Count: h12Raw.length }
  }

  // ─── Persist / sampling ────────────────────────────────────────────────────

  function _syncSampleSize(): void {
    samplingParams.value.sampleSize = rows.value.length
    samplingParams.value.coverageRate = summary.value.coverageRate
  }

  function updateSamplingParams(params: Partial<SamplingParams> & { populationManual?: boolean }): void {
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

  function syncPopulationFromLinked(force = true): { ok: boolean; amount: number; source: string } {
    const linked = _calcLinkedIncrease()
    if (!(linked.amount > 0)) return { ok: false, amount: 0, source: '' }
    if (!force && populationManual.value && samplingParams.value.totalPopulation > 0) {
      return { ok: false, amount: samplingParams.value.totalPopulation, source: 'manual' }
    }
    samplingParams.value.totalPopulation = linked.amount
    populationManual.value = false
    samplingParams.value.coverageRate = summary.value.coverageRate
    _persistSampling()
    return { ok: true, amount: linked.amount, source: linked.source }
  }

  function updateTestReasons(reasons: AdditionTestReason[], otherText = ''): void {
    testReasons.value = reasons
    testReasonOther.value = otherText
    options?.onSave?.(`${ITEM_PREFIX}-test-reasons`, { reasons, otherText })
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

  function _persistTrace(): void {
    options?.onSave?.(`${ITEM_PREFIX}-trace-rows`, traceRows.value)
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
    traceRows,
    samplingParams,
    populationManual,
    linkedIncrease,
    cipTransferInTotal,
    cashPaidTotal,
    testReasons,
    testReasonOther,
    auditNote,
    auditConclusion,
    summary,
    addRow,
    removeRow,
    updateCell,
    updateMethodCheck,
    addTraceRow,
    removeTraceRow,
    updateTraceCell,
    seedTraceFromVouchRows,
    mergeOcrResult,
    applyOcrFields,
    needsAmountMismatchWarning,
    needsCipAcceptanceWarning,
    needsProvisionalDepWarning,
    needsChecklistIncompleteWarning,
    pushDepStartToH12,
    previewH12DepLink,
    updateSamplingParams,
    syncPopulationFromLinked,
    updateTestReasons,
    saveNote,
    saveConclusion,
    getMethodChecklist,
    calcChecklistProgress,
  }
}

function round2(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100) / 100
}

export default useH1AdditionCheck
