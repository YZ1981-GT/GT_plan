/**
 * useH2RelatedParty — H2-17 关联交易检查 composable
 *
 * 对齐致同 Excel「关联交易检查表H2-17」：
 *   (1) 向合并范围外关联方采购在建工程
 *   (2) 向合并范围外关联方出售在建工程
 * 增强（对齐 H1-18 实务）：
 *   - 公允/评估价值 + 价差率阈值高亮
 *   - 购入入账差异（入账价值−购买价款）
 *   - 出售净值/处置损益公式
 *   - 占同类% 自动计算
 *   - (3) 关联方工程服务（施工/供材/设计/监理）— CIP 特有高频场景
 *   - 「本期无此类交易」+ 异常摘要
 *
 * Spec: .kiro/specs/h2-construction-in-progress/ Requirement 13（结构已按源模板校正）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useH2FormulaEngine'
import { reconcileA7Disclosure, type A7ReconcileResult } from './useH1LeaseCheck'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 交易类型：购入/出售对齐源模板；工程服务为 CIP 实务增强 */
export type H2RpTransType = '购入' | '出售' | '工程服务'

export interface H2RelatedPartyRow {
  rowId: string
  seq: number
  /** 购入 | 出售 | 工程服务 */
  transType: H2RpTransType
  /** 关联单位名称 */
  counterparty: string
  /** 关联方关系 */
  relationship: string
  /** 资产类别 / 服务类别 */
  assetCategory: string
  /** 在建工程名称 / 工程服务内容 */
  name: string
  /**
   * 交易金额：
   * 购入=购买价款；出售=销售价格(不含税)；工程服务=合同金额
   */
  transAmount: number
  /** 购入：在建工程入账价值 */
  bookValue: number
  /** 入账差异（公式 = 入账价值 − 购买价款） */
  entryDiff: number
  /** 出售：出售时在建工程原值 */
  originalCost: number
  /** 出售：出售时减值准备 */
  impairment: number
  /** 出售时净值（公式 = 原值 − 减值） */
  netValue: number
  /** 处置损益（公式 = 售价 − 净值） */
  disposalGain: number
  /** 工程服务：本期发生额 */
  currentAmount: number
  /** 工程服务：累计发生额 */
  cumulativeAmount: number
  /** 购入/出售/服务时间 */
  transDate: string
  /** 同类交易总额（手填；用于占比） */
  categoryTotal: number | null
  /** 占同类交易金额的比例% */
  similarRatio: number | null
  /** 定价政策 */
  pricingPolicy: string
  /** 关联交易是否存在异常：是/否/待定 */
  hasAnomaly: string
  /** 公允/评估价值（或市场价参考） */
  appraisedValue: number
  /** 价格差异率(%) = (交易价−公允)/公允×100 */
  priceDiffRate: number
  /** 审批文件 */
  approvalDoc: string
  /** 独立董事意见 */
  independentDirectorOpinion: string
  /** 行级检查结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 索引号 */
  indexRef: string
  /** 来源底稿 H2-8 / H2-9（预埋带入；源表未齐时允许为空） */
  sourceWp: string
  sourceRowId: string
  /** 带入时源行指纹，用于漂移检测 */
  sourceFingerprint: string
}

export interface H2RelatedPartySettings {
  priceDiffThreshold: number
  entryDiffThreshold: number
  noTransaction: boolean
}

export interface H2RelatedPartySummary {
  purchaseCount: number
  purchaseTotal: number
  saleCount: number
  saleTotal: number
  serviceCount: number
  serviceTotal: number
  count: number
  abnormalCount: number
  entryDiffCount: number
  entryRemarkMissingCount: number
  sourceDriftCount: number
  noTransaction: boolean
  priceDiffThreshold: number
  entryDiffThreshold: number
}

export const DEFAULT_PRICE_DIFF_THRESHOLD = 10
export const DEFAULT_ENTRY_DIFF_THRESHOLD = 10

export const IN_SCOPE_RELATIONSHIP_KEYWORDS = [
  '子公司', '孙公司', '全资子公司', '控股子公司', '同一控制下企业',
]

const ROWS_KEY = 'H2-17-rows'
const SETTINGS_KEY = 'H2-17-settings'
const NOTE_KEY = 'H2-17-audit-note'
const CONCLUSION_KEY = 'H2-17-audit-conclusion'

// ─── Pure helpers ────────────────────────────────────────────────────────────

export function defaultRelatedPartySettings(): H2RelatedPartySettings {
  return {
    priceDiffThreshold: DEFAULT_PRICE_DIFF_THRESHOLD,
    entryDiffThreshold: DEFAULT_ENTRY_DIFF_THRESHOLD,
    noTransaction: false,
  }
}

export function isLikelyInConsolidationScope(relationship: string): boolean {
  const r = (relationship || '').trim()
  return IN_SCOPE_RELATIONSHIP_KEYWORDS.some(k => r.includes(k))
}

export function recalcRelatedPartyRow(row: H2RelatedPartyRow): void {
  if (row.transType === '出售') {
    row.netValue = Math.max(0, (row.originalCost || 0) - (row.impairment || 0))
    row.disposalGain = (row.transAmount || 0) - row.netValue
    row.entryDiff = 0
  } else if (row.transType === '购入') {
    row.netValue = 0
    row.disposalGain = 0
    row.entryDiff = (row.bookValue || 0) - (row.transAmount || 0)
  } else {
    // 工程服务
    row.netValue = 0
    row.disposalGain = 0
    row.entryDiff = 0
  }

  const baseForRatio = row.transType === '工程服务'
    ? (row.currentAmount || row.transAmount || 0)
    : (row.transAmount || 0)
  if (row.categoryTotal != null && row.categoryTotal > 0) {
    row.similarRatio = (baseForRatio / row.categoryTotal) * 100
  } else {
    row.similarRatio = null
  }

  row.priceDiffRate = row.appraisedValue > 0
    ? ((row.transAmount - row.appraisedValue) / row.appraisedValue) * 100
    : 0
}

export function needsEntryDiffRemark(
  row: H2RelatedPartyRow,
  entryTh: number = DEFAULT_ENTRY_DIFF_THRESHOLD,
): boolean {
  if (row.transType !== '购入') return false
  if (Math.abs(row.entryDiff) <= 0.01) return false
  const base = Math.abs(row.transAmount) || Math.abs(row.bookValue) || 1
  const rate = Math.abs(row.entryDiff) / base * 100
  return rate > entryTh && !(row.remark || '').trim()
}

export function emptyRelatedPartyRow(seq: number, transType: H2RpTransType = '购入'): H2RelatedPartyRow {
  return {
    rowId: `h2rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    transType,
    counterparty: '',
    relationship: '',
    assetCategory: '',
    name: '',
    transAmount: 0,
    bookValue: 0,
    entryDiff: 0,
    originalCost: 0,
    impairment: 0,
    netValue: 0,
    disposalGain: 0,
    currentAmount: 0,
    cumulativeAmount: 0,
    transDate: '',
    categoryTotal: null,
    similarRatio: null,
    pricingPolicy: '',
    hasAnomaly: '',
    appraisedValue: 0,
    priceDiffRate: 0,
    approvalDoc: '',
    independentDirectorOpinion: '',
    conclusion: '',
    remark: '',
    indexRef: '',
    sourceWp: '',
    sourceRowId: '',
    sourceFingerprint: '',
  }
}

/** 判定源行是否标记为关联方（兼容 Y/是/有名称） */
export function isMarkedRelatedParty(src: any): boolean {
  const flag = String(src?.isRelatedParty ?? '').trim()
  if (flag === '是' || flag === 'Y' || flag === 'y' || flag === 'true') return true
  return Boolean(String(src?.relatedPartyName ?? '').trim())
}

export function buildH28SourceFingerprint(src: any): string {
  return JSON.stringify({
    name: src?.name ?? '',
    amount: Number(src?.amount) || 0,
    supplier: src?.supplier ?? '',
    additionMethod: src?.additionMethod ?? '',
    relatedPartyName: src?.relatedPartyName ?? '',
    date: src?.date ?? '',
    contractNo: src?.contractNo ?? '',
    category: src?.category ?? '',
  })
}

export function buildH29SourceFingerprint(src: any): string {
  const decreaseAmt =
    (Number(src?.transferToFaAmount) || 0) + (Number(src?.otherDecreaseAmount) || 0)
      || Number(src?.originalValue)
      || 0
  return JSON.stringify({
    name: src?.name ?? '',
    originalValue: decreaseAmt,
    transferToFaAmount: Number(src?.transferToFaAmount) || 0,
    otherDecreaseAmount: Number(src?.otherDecreaseAmount) || 0,
    disposalIncome: Number(src?.disposalIncome) || 0,
    relatedPartyName: src?.relatedPartyName ?? '',
    decreaseDate: src?.decreaseDate ?? '',
    decreaseType: src?.decreaseType ?? src?.decreaseReason ?? '',
  })
}

export function applyH28SourceToRow(row: H2RelatedPartyRow, src: any): void {
  // 按增加方式推断交易类型：设备购置→购入；出包/自营→工程服务
  const method = String(src.additionMethod ?? '')
  if (method === '设备购置') {
    row.transType = '购入'
    row.assetCategory = src.category || row.assetCategory || '设备'
  } else {
    row.transType = '工程服务'
    row.assetCategory = src.category || method || row.assetCategory || '施工'
  }
  row.name = src.name ?? row.name
  row.counterparty = src.relatedPartyName || src.supplier || row.counterparty
  row.relationship = src.relationship ?? row.relationship
  row.transAmount = Number(src.amount) || 0
  row.currentAmount = Number(src.amount) || 0
  row.transDate = src.date ?? ''
  row.pricingPolicy = src.contractNo ? `合同:${src.contractNo}` : (row.pricingPolicy || '')
  row.approvalDoc = src.approvalDoc ?? row.approvalDoc
  row.indexRef = src.indexRef || row.indexRef || 'H2-8'
  row.sourceWp = 'H2-8'
  row.sourceRowId = src.rowId ?? row.sourceRowId
  row.sourceFingerprint = buildH28SourceFingerprint(src)
  recalcRelatedPartyRow(row)
}

export function applyH29SourceToRow(row: H2RelatedPartyRow, src: any): void {
  const decreaseAmt =
    (Number(src.transferToFaAmount) || 0) + (Number(src.otherDecreaseAmount) || 0)
      || Number(src.originalValue)
      || 0
  const dtype = String(src.decreaseType ?? src.decreaseReason ?? '')
  // H2-9 → H2-17 默认按「出售」带入（用户可改交易类型）；原值取减少合计
  row.transType = '出售'
  row.name = src.name ?? row.name
  row.counterparty = src.relatedPartyName || row.counterparty
  row.relationship = src.relationship ?? row.relationship
  row.originalCost = decreaseAmt
  row.impairment = 0
  row.transAmount = Number(src.disposalIncome) || Number(src.otherDecreaseAmount) || 0
  row.transDate = src.decreaseDate ?? ''
  row.pricingPolicy = dtype
    ? `减少类型:${dtype}`
    : (src.disposalMethod ? `处置方式:${src.disposalMethod}` : (row.pricingPolicy || ''))
  row.approvalDoc = src.approvalRef || src.approvalDoc || row.approvalDoc
  row.indexRef = src.indexRef || row.indexRef || 'H2-9'
  row.sourceWp = 'H2-9'
  row.sourceRowId = src.rowId ?? row.sourceRowId
  row.sourceFingerprint = buildH29SourceFingerprint(src)
  recalcRelatedPartyRow(row)
}

/** 兼容旧版单一「施工/供材」行结构 */
function _migrateLegacyRow(raw: any, idx: number): H2RelatedPartyRow {
  const hasLegacyType = ['施工', '供材', '设计', '监理'].includes(raw.transactionType)
  const hasLegacyParty = raw.partyName != null && raw.counterparty == null
  if (!hasLegacyType && !hasLegacyParty) {
    return _fromRaw(raw, idx)
  }
  const row = emptyRelatedPartyRow(raw.seq ?? idx + 1, '工程服务')
  row.rowId = raw.rowId ?? row.rowId
  row.counterparty = raw.partyName ?? raw.counterparty ?? ''
  row.relationship = raw.relationship ?? ''
  row.assetCategory = raw.transactionType ?? raw.assetCategory ?? ''
  row.name = raw.name ?? raw.projectName ?? ''
  row.transAmount = Number(raw.contractAmount ?? raw.transAmount) || 0
  row.currentAmount = Number(raw.currentAmount) || 0
  row.cumulativeAmount = Number(raw.cumulativeAmount) || 0
  row.pricingPolicy = raw.pricingMethod ?? raw.pricingPolicy ?? ''
  row.appraisedValue = Number(raw.marketPrice ?? raw.appraisedValue) || 0
  row.approvalDoc = raw.approvalDoc ?? ''
  row.independentDirectorOpinion = raw.independentDirectorOpinion ?? ''
  row.conclusion = raw.auditConclusion ?? raw.conclusion ?? ''
  row.remark = raw.remark ?? ''
  row.hasAnomaly = raw.hasAnomaly ?? ''
  recalcRelatedPartyRow(row)
  return row
}

function _fromRaw(raw: any, idx: number): H2RelatedPartyRow {
  const tt = (raw.transType as H2RpTransType) || '购入'
  const row = emptyRelatedPartyRow(raw.seq ?? idx + 1, tt)
  Object.assign(row, {
    rowId: raw.rowId ?? row.rowId,
    counterparty: raw.counterparty ?? '',
    relationship: raw.relationship ?? '',
    assetCategory: raw.assetCategory ?? '',
    name: raw.name ?? '',
    transAmount: Number(raw.transAmount) || 0,
    bookValue: Number(raw.bookValue) || 0,
    originalCost: Number(raw.originalCost) || 0,
    impairment: Number(raw.impairment) || 0,
    currentAmount: Number(raw.currentAmount) || 0,
    cumulativeAmount: Number(raw.cumulativeAmount) || 0,
    transDate: raw.transDate ?? '',
    categoryTotal: raw.categoryTotal != null ? Number(raw.categoryTotal) : null,
    pricingPolicy: raw.pricingPolicy ?? '',
    hasAnomaly: raw.hasAnomaly ?? '',
    appraisedValue: Number(raw.appraisedValue) || 0,
    approvalDoc: raw.approvalDoc ?? '',
    independentDirectorOpinion: raw.independentDirectorOpinion ?? '',
    conclusion: raw.conclusion ?? '',
    remark: raw.remark ?? '',
    indexRef: raw.indexRef ?? '',
  })
  row.sourceWp = raw.sourceWp ?? ''
  row.sourceRowId = raw.sourceRowId ?? ''
  row.sourceFingerprint = raw.sourceFingerprint ?? ''
  recalcRelatedPartyRow(row)
  return row
}

function _persistable(row: H2RelatedPartyRow) {
  return {
    rowId: row.rowId,
    seq: row.seq,
    transType: row.transType,
    counterparty: row.counterparty,
    relationship: row.relationship,
    assetCategory: row.assetCategory,
    name: row.name,
    transAmount: row.transAmount,
    bookValue: row.bookValue,
    originalCost: row.originalCost,
    impairment: row.impairment,
    currentAmount: row.currentAmount,
    cumulativeAmount: row.cumulativeAmount,
    transDate: row.transDate,
    categoryTotal: row.categoryTotal,
    pricingPolicy: row.pricingPolicy,
    hasAnomaly: row.hasAnomaly,
    appraisedValue: row.appraisedValue,
    approvalDoc: row.approvalDoc,
    independentDirectorOpinion: row.independentDirectorOpinion,
    conclusion: row.conclusion,
    remark: row.remark,
    indexRef: row.indexRef,
    sourceWp: row.sourceWp,
    sourceRowId: row.sourceRowId,
    sourceFingerprint: row.sourceFingerprint,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2RelatedParty(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>> | ComputedRef<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const rows = ref<H2RelatedPartyRow[]>([])
  const settings = ref<H2RelatedPartySettings>(defaultRelatedPartySettings())
  const auditNote = ref('')
  const auditConclusion = ref('')

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

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map((r, i) => _migrateLegacyRow(r, i))
    } else {
      rows.value = []
    }
    const s = _getJson(SETTINGS_KEY)
    if (s && typeof s === 'object') {
      settings.value = {
        ...defaultRelatedPartySettings(),
        ...s,
        priceDiffThreshold: Number(s.priceDiffThreshold) || DEFAULT_PRICE_DIFF_THRESHOLD,
        entryDiffThreshold: Number(s.entryDiffThreshold) || DEFAULT_ENTRY_DIFF_THRESHOLD,
      }
    } else {
      settings.value = defaultRelatedPartySettings()
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  const purchaseRows = computed(() => rows.value.filter(r => r.transType === '购入'))
  const saleRows = computed(() => rows.value.filter(r => r.transType === '出售'))
  const serviceRows = computed(() => rows.value.filter(r => r.transType === '工程服务'))

  function _readSourceRows(itemId: string): any[] {
    const data = _getJson(itemId)
    return Array.isArray(data) ? data : []
  }

  function _findDrifted(): H2RelatedPartyRow[] {
    const h28 = new Map(_readSourceRows('H2-8-rows').map((r: any) => [r.rowId, r]))
    const h29 = new Map(_readSourceRows('H2-9-rows').map((r: any) => [r.rowId, r]))
    const drifted: H2RelatedPartyRow[] = []
    for (const row of rows.value) {
      if (!row.sourceWp || !row.sourceRowId) continue
      if (row.sourceWp === 'H2-8') {
        const src = h28.get(row.sourceRowId)
        if (!src || buildH28SourceFingerprint(src) !== (row.sourceFingerprint || '')) drifted.push(row)
      } else if (row.sourceWp === 'H2-9') {
        const src = h29.get(row.sourceRowId)
        if (!src || buildH29SourceFingerprint(src) !== (row.sourceFingerprint || '')) drifted.push(row)
      }
    }
    return drifted
  }

  const summary: ComputedRef<H2RelatedPartySummary> = computed(() => {
    const th = settings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
    const entryTh = settings.value.entryDiffThreshold || DEFAULT_ENTRY_DIFF_THRESHOLD
    const purchases = purchaseRows.value
    const sales = saleRows.value
    const services = serviceRows.value
    const all = rows.value
    return {
      purchaseCount: purchases.length,
      purchaseTotal: calcSubtotal(purchases.map(r => r.transAmount)),
      saleCount: sales.length,
      saleTotal: calcSubtotal(sales.map(r => r.transAmount)),
      serviceCount: services.length,
      serviceTotal: calcSubtotal(services.map(r => r.transAmount || r.currentAmount)),
      count: all.length,
      abnormalCount: all.filter(r =>
        (r.appraisedValue > 0 && Math.abs(r.priceDiffRate) > th)
        || r.hasAnomaly === '是',
      ).length,
      entryDiffCount: purchases.filter(r => Math.abs(r.entryDiff) > 0.01).length,
      entryRemarkMissingCount: purchases.filter(r => needsEntryDiffRemark(r, entryTh)).length,
      sourceDriftCount: _findDrifted().length,
      noTransaction: settings.value.noTransaction,
      priceDiffThreshold: th,
      entryDiffThreshold: entryTh,
    }
  })

  function _persistRows(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(_persistable))
  }

  function _persistSettings(): void {
    if (!options.onSave) return
    options.onSave(SETTINGS_KEY, { ...settings.value })
  }

  function addRow(transType: H2RpTransType = '购入'): H2RelatedPartyRow | null {
    if (options.isReadonly.value) return null
    settings.value.noTransaction = false
    _persistSettings()
    const row = emptyRelatedPartyRow(rows.value.length + 1, transType)
    rows.value.push(row)
    _persistRows()
    return row
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const formulaFields = ['entryDiff', 'netValue', 'disposalGain', 'similarRatio', 'priceDiffRate']
    if (formulaFields.includes(field)) return

    const numFields = [
      'transAmount', 'bookValue', 'originalCost', 'impairment',
      'currentAmount', 'cumulativeAmount', 'appraisedValue', 'categoryTotal',
    ]
    if (numFields.includes(field)) {
      if (field === 'categoryTotal') {
        row.categoryTotal = value == null || value === '' ? null : (Number(value) || 0)
      } else {
        ;(row as any)[field] = Number(value) || 0
      }
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    recalcRelatedPartyRow(row)
    _persistRows()
  }

  /** 按交易类型，用本表同类型合计作为同类总额并重算占比 */
  function recalcSimilarRatios(): void {
    if (options.isReadonly.value) return
    const totals: Record<H2RpTransType, number> = {
      购入: calcSubtotal(purchaseRows.value.map(r => r.transAmount)),
      出售: calcSubtotal(saleRows.value.map(r => r.transAmount)),
      工程服务: calcSubtotal(serviceRows.value.map(r => r.transAmount || r.currentAmount)),
    }
    for (const row of rows.value) {
      row.categoryTotal = totals[row.transType] || null
      recalcRelatedPartyRow(row)
    }
    _persistRows()
  }

  function applyNoTransaction(): void {
    if (options.isReadonly.value) return
    rows.value = []
    settings.value.noTransaction = true
    _persistRows()
    _persistSettings()
    const note = '经核查，本期被审计单位未发生向合并范围外关联方购入/出售在建工程，亦未发生关联方工程服务交易。'
    auditNote.value = note
    auditConclusion.value = '本期无合并范围外关联方在建工程相关交易，本检查表不适用；相关披露无此类事项。'
    options.onSave?.(NOTE_KEY, note)
    options.onSave?.(CONCLUSION_KEY, auditConclusion.value)
  }

  function updateSettings(partial: Partial<H2RelatedPartySettings>): void {
    if (options.isReadonly.value) return
    Object.assign(settings.value, partial)
    _persistSettings()
  }

  function buildNoteDraft(): string {
    const s = summary.value
    const lines: string[] = []
    lines.push('【H2-17 关联交易检查摘要】')
    if (s.noTransaction && s.count === 0) {
      lines.push('本期无合并范围外关联方在建工程购销及工程服务交易。')
      return lines.join('\n')
    }
    lines.push(
      `购入 ${s.purchaseCount} 笔，价款合计 ${s.purchaseTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}；`
      + `出售 ${s.saleCount} 笔，售价合计 ${s.saleTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}；`
      + `工程服务 ${s.serviceCount} 笔，金额合计 ${s.serviceTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}。`,
    )
    if (s.abnormalCount > 0) {
      lines.push(`价差超阈(>${s.priceDiffThreshold}%)或标记异常共 ${s.abnormalCount} 笔，需说明公允性依据（评估/招投标/市场报价）。`)
    }
    if (s.entryRemarkMissingCount > 0) {
      lines.push(`购入入账差异超 ${s.entryDiffThreshold}% 且未备注 ${s.entryRemarkMissingCount} 笔，请说明税费/运杂/资本化利息等构成。`)
    }
    const inScope = rows.value.filter(r => isLikelyInConsolidationScope(r.relationship))
    if (inScope.length > 0) {
      lines.push(`提示：有 ${inScope.length} 笔关系疑似合并范围内（如子公司），请确认是否确属「合并范围外」关联方交易。`)
    }
    lines.push('已核对定价政策、审批文件及披露完整性；详见各行索引号。')
    return lines.join('\n')
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function isUnfair(row: H2RelatedPartyRow): boolean {
    const th = settings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
    return row.appraisedValue > 0 && Math.abs(row.priceDiffRate) > th
  }

  /**
   * 从 H2-8/H2-9 带入已标记关联方的行。
   * 容错：源表未齐 / 无关联方标记时返回空结果与提示，不抛错。
   * H2-8 → 工程服务；H2-9 → 出售（用户可改交易类型）。
   */
  function importFromH8H9(): {
    added: number
    skipped: number
    inScopeCandidates: H2RelatedPartyRow[]
    message: string
  } {
    if (options.isReadonly.value) {
      return { added: 0, skipped: 0, inScopeCandidates: [], message: '只读模式不可带入' }
    }
    const h28All = _readSourceRows('H2-8-rows')
    const h29All = _readSourceRows('H2-9-rows')
    if (h28All.length === 0 && h29All.length === 0) {
      return {
        added: 0,
        skipped: 0,
        inScopeCandidates: [],
        message: 'H2-8/H2-9 尚无数据。请先完成增减检查；关联方字段已预埋，修复后标记「是」即可带入。',
      }
    }

    const existingKeys = new Set(
      rows.value.filter(r => r.sourceWp && r.sourceRowId).map(r => `${r.sourceWp}:${r.sourceRowId}`),
    )
    let added = 0
    let skipped = 0
    const inScopeCandidates: H2RelatedPartyRow[] = []

    for (const src of h28All) {
      if (!isMarkedRelatedParty(src)) continue
      const key = `H2-8:${src.rowId}`
      if (!src.rowId || existingKeys.has(key)) { skipped++; continue }
      const row = emptyRelatedPartyRow(rows.value.length + 1, '工程服务')
      applyH28SourceToRow(row, src)
      rows.value.push(row)
      existingKeys.add(key)
      added++
      if (isLikelyInConsolidationScope(row.relationship)) inScopeCandidates.push(row)
    }
    for (const src of h29All) {
      if (!isMarkedRelatedParty(src)) continue
      const key = `H2-9:${src.rowId}`
      if (!src.rowId || existingKeys.has(key)) { skipped++; continue }
      const row = emptyRelatedPartyRow(rows.value.length + 1, '出售')
      applyH29SourceToRow(row, src)
      rows.value.push(row)
      existingKeys.add(key)
      added++
      if (isLikelyInConsolidationScope(row.relationship)) inScopeCandidates.push(row)
    }

    if (added > 0) {
      settings.value.noTransaction = false
      _persistSettings()
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persistRows()
    }

    const markedCount = h28All.filter(isMarkedRelatedParty).length + h29All.filter(isMarkedRelatedParty).length
    let message = ''
    if (added === 0 && markedCount === 0) {
      message = `H2-8 共 ${h28All.length} 行、H2-9 共 ${h29All.length} 行，但尚未标记关联方。可在增减检查表勾选「关联方=是」后重试。`
    } else if (added === 0) {
      message = `候选 ${markedCount} 笔均已带入或缺少行ID，本次新增 0 笔。`
    } else {
      message = `已带入 ${added} 笔（跳过 ${skipped}）；H2-8→工程服务、H2-9→出售，可按需改交易类型。`
    }
    return { added, skipped, inScopeCandidates, message }
  }

  /** 按指纹刷新已漂移行（源仍存在时覆盖金额等） */
  function refreshDriftedFromSource(): number {
    if (options.isReadonly.value) return 0
    const h28 = new Map(_readSourceRows('H2-8-rows').map((r: any) => [r.rowId, r]))
    const h29 = new Map(_readSourceRows('H2-9-rows').map((r: any) => [r.rowId, r]))
    let n = 0
    for (const row of _findDrifted()) {
      if (row.sourceWp === 'H2-8') {
        const src = h28.get(row.sourceRowId)
        if (src) { applyH28SourceToRow(row, src); n++ }
      } else if (row.sourceWp === 'H2-9') {
        const src = h29.get(row.sourceRowId)
        if (src) { applyH29SourceToRow(row, src); n++ }
      }
    }
    if (n > 0) _persistRows()
    return n
  }

  function getA7Reconcile(a7Total: number | null | undefined): A7ReconcileResult {
    const total = calcSubtotal(rows.value.map(r => r.transAmount || r.currentAmount || 0))
    const result = reconcileA7Disclosure(total, a7Total)
    // 文案改为在建工程口径
    if (result.status === 'mismatch') {
      result.note = `本表合计 ${result.h118Total.toFixed(2)} 与 A7-1 合计 ${Number(result.a7Total).toFixed(2)} 差异 ${Number(result.diff).toFixed(2)}（A7 通常含全部关联交易，请核对附注中在建工程/工程服务相关分项）`
    } else if (result.status === 'ok') {
      result.note = '本表合计与 A7-1 合计一致（若 A7 含非 CIP 交易则属巧合，请仍核对附注明细）'
    }
    return result
  }

  return {
    rows,
    settings,
    auditNote,
    auditConclusion,
    purchaseRows,
    saleRows,
    serviceRows,
    summary,
    addRow,
    removeRow,
    updateCell,
    recalcSimilarRatios,
    applyNoTransaction,
    updateSettings,
    buildNoteDraft,
    saveNote,
    saveConclusion,
    isUnfair,
    needsEntryDiffRemark: (row: H2RelatedPartyRow) =>
      needsEntryDiffRemark(row, settings.value.entryDiffThreshold),
    isLikelyInConsolidationScope,
    importFromH8H9,
    refreshDriftedFromSource,
    getA7Reconcile,
    initFromAllResponses,
  }
}

export default useH2RelatedParty
