/**
 * useH4RelatedParty — H4-9 关联交易检查表 composable
 *
 * 对齐致同 Excel「关联交易检查表H4-9」：
 *   (1) 向合并范围外关联方采购工程物资
 *   (2) 向合并范围外关联方出售工程物资
 * 增强（对齐 H2-17 实务）：
 *   - 公允/评估价值 + 价差率阈值高亮
 *   - 购入入账差异（入账价值−购买价款）
 *   - 出售净值/处置损益公式
 *   - 占同类% 自动计算
 *   - 从 H4-4/H4-5 带入（需源表标记关联方）
 *   - 「本期无此类交易」+ 异常摘要
 * 兼容旧版单表字段（name/marketPrice/pricingBasis…）自动迁移为购入行
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal, calcPriceDiffRate } from './useH4FormulaEngine'
import { H49_AJE_MARKER, pushDraftPairsToH43 } from './h4AdjustmentDraftPush'

// ─── Types ───────────────────────────────────────────────────────────────────

export type H4RpTransType = '购入' | '出售'

export interface H4RelatedPartyRow {
  rowId: string
  seq: number
  /** 购入 | 出售 */
  transType: H4RpTransType
  /** 关联单位名称 */
  counterparty: string
  /** 关联方关系 */
  relationship: string
  /** 资产类别 */
  assetCategory: string
  /** 工程物资名称 */
  name: string
  /**
   * 交易金额：
   * 购入=购买价款；出售=销售价格(不含税)
   */
  transAmount: number
  /** 购入：工程物资入账价值 */
  bookValue: number
  /** 入账差异（公式 = 入账价值 − 购买价款） */
  entryDiff: number
  /** 出售：出售时工程物资原值 */
  originalCost: number
  /** 出售：出售时减值准备 */
  impairment: number
  /** 出售时净值（公式 = 原值 − 减值） */
  netValue: number
  /** 处置损益（公式 = 售价 − 净值） */
  disposalGain: number
  /** 购入/出售时间 */
  transDate: string
  /** 同类交易总额（手填或按本表重算；用于占比） */
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
  /** 行级检查结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 索引号 */
  indexRef: string
  /** 来源底稿 H4-4 / H4-5 */
  sourceWp: string
  sourceRowId: string
  sourceFingerprint: string
}

export interface H4RelatedPartySettings {
  priceDiffThreshold: number
  entryDiffThreshold: number
  noTransaction: boolean
}

export interface H4RelatedPartySummary {
  purchaseCount: number
  purchaseTotal: number
  saleCount: number
  saleTotal: number
  count: number
  abnormalCount: number
  entryDiffCount: number
  entryRemarkMissingCount: number
  sourceDriftCount: number
  noTransaction: boolean
  priceDiffThreshold: number
  entryDiffThreshold: number
}

/** @deprecated 兼容旧单表类型别名 */
export type H4RelatedPartyStats = Pick<H4RelatedPartySummary, 'count' | 'abnormalCount'> & {
  transCount: number
  totalAmount: number
}

export const DEFAULT_PRICE_DIFF_THRESHOLD = 10
export const DEFAULT_ENTRY_DIFF_THRESHOLD = 10

export const H4_RELATIONSHIP_OPTIONS = [
  '实际控制人',
  '控股股东',
  '控股股东、实际控制人的附属企业',
  '持有5%以上股份的法人或其他组织',
  '联营企业',
  '合营企业',
  '董高监等关键管理人员',
  '其他关联方',
] as const

export const IN_SCOPE_RELATIONSHIP_KEYWORDS = [
  '子公司', '孙公司', '全资子公司', '控股子公司', '同一控制下企业',
]

const ROWS_KEY = 'H4-9-rows'
const SETTINGS_KEY = 'H4-9-settings'
const NOTE_KEY = 'H4-9-note'
const CONCLUSION_KEY = 'H4-9-conclusion'

// ─── Pure helpers ────────────────────────────────────────────────────────────

export function defaultRelatedPartySettings(): H4RelatedPartySettings {
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

export function recalcRelatedPartyRow(row: H4RelatedPartyRow): void {
  if (row.transType === '出售') {
    row.netValue = Math.max(0, (row.originalCost || 0) - (row.impairment || 0))
    row.disposalGain = (row.transAmount || 0) - row.netValue
    row.entryDiff = 0
  } else {
    row.netValue = 0
    row.disposalGain = 0
    row.entryDiff = (row.bookValue || 0) - (row.transAmount || 0)
  }

  if (row.categoryTotal != null && row.categoryTotal > 0) {
    row.similarRatio = ((row.transAmount || 0) / row.categoryTotal) * 100
  } else {
    row.similarRatio = null
  }

  row.priceDiffRate = row.appraisedValue > 0
    ? calcPriceDiffRate(row.transAmount, row.appraisedValue)
    : 0
}

export function needsEntryDiffRemark(
  row: H4RelatedPartyRow,
  entryTh: number = DEFAULT_ENTRY_DIFF_THRESHOLD,
): boolean {
  if (row.transType !== '购入') return false
  if (Math.abs(row.entryDiff) <= 0.01) return false
  const base = Math.abs(row.transAmount) || Math.abs(row.bookValue) || 1
  const rate = Math.abs(row.entryDiff) / base * 100
  return rate > entryTh && !(row.remark || '').trim()
}

export function emptyRelatedPartyRow(seq: number, transType: H4RpTransType = '购入'): H4RelatedPartyRow {
  return {
    rowId: `h4rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
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
    transDate: '',
    categoryTotal: null,
    similarRatio: null,
    pricingPolicy: '',
    hasAnomaly: '',
    appraisedValue: 0,
    priceDiffRate: 0,
    approvalDoc: '',
    conclusion: '',
    remark: '',
    indexRef: '',
    sourceWp: '',
    sourceRowId: '',
    sourceFingerprint: '',
  }
}

export function isMarkedRelatedParty(src: any): boolean {
  const flag = String(src?.isRelatedParty ?? '').trim()
  if (flag === '是' || flag === 'Y' || flag === 'y' || flag === 'true') return true
  return Boolean(String(src?.relatedPartyName ?? '').trim())
}

export function buildH44SourceFingerprint(src: any): string {
  return JSON.stringify({
    name: src?.name ?? '',
    amount: Number(src?.amount) || 0,
    supplier: src?.supplier ?? '',
    relatedPartyName: src?.relatedPartyName ?? '',
    inboundDate: src?.inboundDate ?? src?.voucherDate ?? '',
    contractNo: src?.contractNo ?? '',
  })
}

export function buildH45SourceFingerprint(src: any): string {
  return JSON.stringify({
    name: src?.name ?? '',
    amount: Number(src?.originalCost ?? src?.amount) || 0,
    reason: src?.disposalMethod ?? src?.reason ?? '',
    relatedPartyName: src?.relatedPartyName ?? '',
    disposalDate: src?.disposalDate ?? '',
  })
}

export function applyH44SourceToRow(row: H4RelatedPartyRow, src: any): void {
  row.transType = '购入'
  row.name = src.name ?? row.name
  row.counterparty = src.relatedPartyName || src.supplier || row.counterparty
  row.relationship = src.relationship ?? row.relationship
  row.transAmount = Number(src.amount) || 0
  row.bookValue = Number(src.amount) || 0
  row.transDate = src.inboundDate || src.voucherDate || ''
  row.pricingPolicy = src.contractNo
    ? `合同:${src.contractNo}`
    : (src.voucherNo ? `凭证:${src.voucherNo}` : (row.pricingPolicy || ''))
  row.indexRef = src.indexRef || src.refIndex || row.indexRef || 'H4-4'
  row.sourceWp = 'H4-4'
  row.sourceRowId = src.rowId ?? row.sourceRowId
  row.sourceFingerprint = buildH44SourceFingerprint(src)
  recalcRelatedPartyRow(row)
}

export function applyH45SourceToRow(row: H4RelatedPartyRow, src: any): void {
  row.transType = '出售'
  row.name = src.name ?? row.name
  row.counterparty = src.relatedPartyName || row.counterparty
  row.relationship = src.relationship ?? row.relationship
  row.originalCost = Number(src.originalCost ?? src.amount) || 0
  row.impairment = Number(src.impairment) || 0
  row.transAmount = Number(src.disposalIncome ?? src.originalCost ?? src.amount) || 0
  row.transDate = src.disposalDate ?? ''
  const method = src.disposalMethod || src.reason
  row.pricingPolicy = method ? `减少方式:${method}` : (row.pricingPolicy || '')
  row.indexRef = src.indexRef || src.refIndex || row.indexRef || 'H4-5'
  row.sourceWp = 'H4-5'
  row.sourceRowId = src.rowId ?? row.sourceRowId
  row.sourceFingerprint = buildH45SourceFingerprint(src)
  recalcRelatedPartyRow(row)
}

/** 兼容旧版单表（无 transType） */
function _migrateLegacyRow(raw: any, idx: number): H4RelatedPartyRow {
  const hasLegacySingle =
    raw.transType == null
    && (raw.marketPrice != null || raw.pricingBasis != null || raw.isFair != null || raw.contractDate != null)

  if (!hasLegacySingle && raw.transType) {
    return _fromRaw(raw, idx)
  }

  const row = emptyRelatedPartyRow(raw.seq ?? idx + 1, '购入')
  row.rowId = raw.rowId ?? row.rowId
  row.name = raw.name ?? ''
  row.counterparty = raw.counterparty ?? ''
  row.relationship = raw.relationship ?? ''
  row.transAmount = Number(raw.transAmount) || 0
  row.bookValue = Number(raw.bookValue ?? raw.transAmount) || 0
  row.appraisedValue = Number(raw.appraisedValue ?? raw.marketPrice) || 0
  row.transDate = raw.transDate ?? raw.contractDate ?? ''
  row.pricingPolicy = raw.pricingPolicy ?? raw.pricingBasis ?? ''
  row.hasAnomaly = raw.hasAnomaly
    ?? (raw.isFair === '否' ? '是' : raw.isFair === '是' ? '否' : raw.isFair === '待定' ? '待定' : '')
  row.approvalDoc = raw.approvalDoc ?? raw.approvalProcess ?? ''
  row.conclusion = raw.conclusion ?? ''
  row.remark = raw.remark ?? ''
  row.indexRef = raw.indexRef ?? raw.contractNo ?? ''
  row.assetCategory = raw.assetCategory ?? ''
  row.originalCost = Number(raw.originalCost) || 0
  row.impairment = Number(raw.impairment) || 0
  if (raw.transType === '出售') row.transType = '出售'
  recalcRelatedPartyRow(row)
  return row
}

function _fromRaw(raw: any, idx: number): H4RelatedPartyRow {
  const tt: H4RpTransType = raw.transType === '出售' ? '出售' : '购入'
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
    transDate: raw.transDate ?? '',
    categoryTotal: raw.categoryTotal != null ? Number(raw.categoryTotal) : null,
    pricingPolicy: raw.pricingPolicy ?? '',
    hasAnomaly: raw.hasAnomaly ?? '',
    appraisedValue: Number(raw.appraisedValue ?? raw.marketPrice) || 0,
    approvalDoc: raw.approvalDoc ?? '',
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

function _persistable(row: H4RelatedPartyRow) {
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
    transDate: row.transDate,
    categoryTotal: row.categoryTotal,
    pricingPolicy: row.pricingPolicy,
    hasAnomaly: row.hasAnomaly,
    appraisedValue: row.appraisedValue,
    approvalDoc: row.approvalDoc,
    conclusion: row.conclusion,
    remark: row.remark,
    indexRef: row.indexRef,
    sourceWp: row.sourceWp,
    sourceRowId: row.sourceRowId,
    sourceFingerprint: row.sourceFingerprint,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4RelatedParty(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>> | ComputedRef<Map<string, any>>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const rows = ref<H4RelatedPartyRow[]>([])
  const settings = ref<H4RelatedPartySettings>(defaultRelatedPartySettings())
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isReadonly = params.isReadonly ?? ref(false)

  function _getJson(itemId: string): any {
    const item = params.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return typeof raw === 'object' ? raw : null }
  }

  function _getString(itemId: string): string {
    const item = params.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function load(): void {
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

  watch(params.allResponses, () => load(), { immediate: true })

  const purchaseRows = computed(() => rows.value.filter(r => r.transType === '购入'))
  const saleRows = computed(() => rows.value.filter(r => r.transType === '出售'))

  function _readSourceRows(itemId: string): any[] {
    const data = _getJson(itemId)
    return Array.isArray(data) ? data : []
  }

  function _findDrifted(): H4RelatedPartyRow[] {
    const h44 = new Map(_readSourceRows('H4-4-rows').map((r: any) => [r.rowId, r]))
    const h45 = new Map(_readSourceRows('H4-5-rows').map((r: any) => [r.rowId, r]))
    const drifted: H4RelatedPartyRow[] = []
    for (const row of rows.value) {
      if (!row.sourceWp || !row.sourceRowId) continue
      if (row.sourceWp === 'H4-4') {
        const src = h44.get(row.sourceRowId)
        if (!src || buildH44SourceFingerprint(src) !== (row.sourceFingerprint || '')) drifted.push(row)
      } else if (row.sourceWp === 'H4-5') {
        const src = h45.get(row.sourceRowId)
        if (!src || buildH45SourceFingerprint(src) !== (row.sourceFingerprint || '')) drifted.push(row)
      }
    }
    return drifted
  }

  const summary: ComputedRef<H4RelatedPartySummary> = computed(() => {
    const th = settings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
    const entryTh = settings.value.entryDiffThreshold || DEFAULT_ENTRY_DIFF_THRESHOLD
    const purchases = purchaseRows.value
    const sales = saleRows.value
    const all = rows.value
    return {
      purchaseCount: purchases.length,
      purchaseTotal: calcSubtotal(purchases.map(r => r.transAmount)),
      saleCount: sales.length,
      saleTotal: calcSubtotal(sales.map(r => r.transAmount)),
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

  /** 兼容旧组件 stats 字段 */
  const stats: ComputedRef<H4RelatedPartyStats> = computed(() => ({
    transCount: summary.value.count,
    totalAmount: summary.value.purchaseTotal + summary.value.saleTotal,
    abnormalCount: summary.value.abnormalCount,
    count: summary.value.count,
  }))

  function _persistRows(): void {
    if (!params.onSave) return
    params.onSave(ROWS_KEY, rows.value.map(_persistable))
  }

  function _persistSettings(): void {
    if (!params.onSave) return
    params.onSave(SETTINGS_KEY, { ...settings.value })
  }

  function addRow(nameOrType?: string | H4RpTransType): H4RelatedPartyRow | null {
    if (isReadonly.value) return null
    settings.value.noTransaction = false
    _persistSettings()
    let transType: H4RpTransType = '购入'
    let name = ''
    if (nameOrType === '购入' || nameOrType === '出售') {
      transType = nameOrType
    } else if (typeof nameOrType === 'string' && nameOrType.trim()) {
      name = nameOrType.trim()
    }
    const row = emptyRelatedPartyRow(rows.value.length + 1, transType)
    if (name) row.name = name
    rows.value.push(row)
    _persistRows()
    return row
  }

  function deleteRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persistRows()
  }

  const removeRow = deleteRow

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const formulaFields = ['entryDiff', 'netValue', 'disposalGain', 'similarRatio', 'priceDiffRate']
    if (formulaFields.includes(field)) return

    const numFields = [
      'transAmount', 'bookValue', 'originalCost', 'impairment', 'appraisedValue', 'categoryTotal',
    ]
    if (numFields.includes(field)) {
      if (field === 'categoryTotal') {
        row.categoryTotal = value == null || value === '' ? null : (Number(value) || 0)
      } else {
        ;(row as any)[field] = Number(value) || 0
      }
    } else if (field === 'transType') {
      row.transType = value === '出售' ? '出售' : '购入'
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    recalcRelatedPartyRow(row)
    _persistRows()
  }

  function recalcSimilarRatios(): void {
    if (isReadonly.value) return
    const totals: Record<H4RpTransType, number> = {
      购入: calcSubtotal(purchaseRows.value.map(r => r.transAmount)),
      出售: calcSubtotal(saleRows.value.map(r => r.transAmount)),
    }
    for (const row of rows.value) {
      row.categoryTotal = totals[row.transType] || null
      recalcRelatedPartyRow(row)
    }
    _persistRows()
  }

  function applyNoTransaction(): void {
    if (isReadonly.value) return
    rows.value = []
    settings.value.noTransaction = true
    _persistRows()
    _persistSettings()
    const note = '经核查，本期被审计单位未发生向合并范围外关联方采购或出售工程物资的交易。'
    auditNote.value = note
    auditConclusion.value = '本期无合并范围外关联方工程物资购销交易，本检查表不适用；相关披露无此类事项。'
    params.onSave?.(NOTE_KEY, note)
    params.onSave?.(CONCLUSION_KEY, auditConclusion.value)
  }

  function updateSettings(partial: Partial<H4RelatedPartySettings>): void {
    if (isReadonly.value) return
    Object.assign(settings.value, partial)
    _persistSettings()
  }

  function buildNoteDraft(): string {
    const s = summary.value
    const lines: string[] = []
    lines.push('【H4-9 关联交易检查摘要】')
    if (s.noTransaction && s.count === 0) {
      lines.push('本期无合并范围外关联方工程物资购销交易。')
      return lines.join('\n')
    }
    lines.push(
      `购入 ${s.purchaseCount} 笔，价款合计 ${s.purchaseTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}；`
      + `出售 ${s.saleCount} 笔，售价合计 ${s.saleTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}。`,
    )
    if (s.abnormalCount > 0) {
      lines.push(`价差超阈(>${s.priceDiffThreshold}%)或标记异常共 ${s.abnormalCount} 笔，需说明公允性依据（评估/招投标/市场报价）。`)
    }
    if (s.entryRemarkMissingCount > 0) {
      lines.push(`购入入账差异超 ${s.entryDiffThreshold}% 且未备注 ${s.entryRemarkMissingCount} 笔，请说明运杂/税费/折扣等构成。`)
    }
    const inScope = rows.value.filter(r => isLikelyInConsolidationScope(r.relationship))
    if (inScope.length > 0) {
      lines.push(`提示：有 ${inScope.length} 笔关系疑似合并范围内（如子公司），请确认是否确属「合并范围外」关联方交易。`)
    }
    lines.push('已核对定价政策、审批文件及披露完整性（CAS36）；详见各行索引号。可与 H4-4/H4-5、附注关联交易交叉验证。')
    return lines.join('\n')
  }

  function saveNote(note: string): void {
    auditNote.value = note
    params.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    params.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function isUnfair(row: H4RelatedPartyRow): boolean {
    const th = settings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
    return row.appraisedValue > 0 && Math.abs(row.priceDiffRate) > th
  }

  function importFromH4H5(): {
    added: number
    skipped: number
    inScopeCandidates: H4RelatedPartyRow[]
    message: string
  } {
    if (isReadonly.value) {
      return { added: 0, skipped: 0, inScopeCandidates: [], message: '只读模式不可带入' }
    }
    const h44All = _readSourceRows('H4-4-rows')
    const h45All = _readSourceRows('H4-5-rows')
    if (h44All.length === 0 && h45All.length === 0) {
      return {
        added: 0,
        skipped: 0,
        inScopeCandidates: [],
        message: 'H4-4/H4-5 尚无数据。请先完成增减检查；在增减表标记「关联方=是」后可带入。',
      }
    }

    const existingKeys = new Set(
      rows.value.filter(r => r.sourceWp && r.sourceRowId).map(r => `${r.sourceWp}:${r.sourceRowId}`),
    )
    let added = 0
    let skipped = 0
    const inScopeCandidates: H4RelatedPartyRow[] = []

    for (const src of h44All) {
      if (!isMarkedRelatedParty(src)) continue
      const key = `H4-4:${src.rowId}`
      if (!src.rowId || existingKeys.has(key)) { skipped++; continue }
      const row = emptyRelatedPartyRow(rows.value.length + 1, '购入')
      applyH44SourceToRow(row, src)
      rows.value.push(row)
      existingKeys.add(key)
      added++
      if (isLikelyInConsolidationScope(row.relationship)) inScopeCandidates.push(row)
    }
    for (const src of h45All) {
      if (!isMarkedRelatedParty(src)) continue
      // 领用出库通常不是对外出售，默认仅带入退货/其他等出售类
      const reason = String(src.disposalMethod ?? src.reason ?? '')
      if (reason === '领用出库') continue
      const key = `H4-5:${src.rowId}`
      if (!src.rowId || existingKeys.has(key)) { skipped++; continue }
      const row = emptyRelatedPartyRow(rows.value.length + 1, '出售')
      applyH45SourceToRow(row, src)
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

    const markedCount = h44All.filter(isMarkedRelatedParty).length
      + h45All.filter(r => isMarkedRelatedParty(r) && String(r.disposalMethod ?? r.reason ?? '') !== '领用出库').length
    let message = ''
    if (added === 0 && markedCount === 0) {
      message = `H4-4 共 ${h44All.length} 行、H4-5 共 ${h45All.length} 行，但尚未标记关联方。可在增减检查表勾选「关联方=是」后重试。`
    } else if (added === 0) {
      message = `候选 ${markedCount} 笔均已带入或缺少行ID，本次新增 0 笔。`
    } else {
      message = `已带入 ${added} 笔（跳过 ${skipped}）；H4-4→购入、H4-5→出售（不含领用出库）。`
    }
    return { added, skipped, inScopeCandidates, message }
  }

  function refreshDriftedFromSource(): number {
    if (isReadonly.value) return 0
    const h44 = new Map(_readSourceRows('H4-4-rows').map((r: any) => [r.rowId, r]))
    const h45 = new Map(_readSourceRows('H4-5-rows').map((r: any) => [r.rowId, r]))
    let n = 0
    for (const row of _findDrifted()) {
      if (row.sourceWp === 'H4-4') {
        const src = h44.get(row.sourceRowId)
        if (src) { applyH44SourceToRow(row, src); n++ }
      } else if (row.sourceWp === 'H4-5') {
        const src = h45.get(row.sourceRowId)
        if (src) { applyH45SourceToRow(row, src); n++ }
      }
    }
    if (n > 0) _persistRows()
    return n
  }

  function save(): void { _persistRows() }

  /**
   * 价差超阈或标记异常 → H4-3 草稿：
   * 购入偏高：借管理费用 / 贷工程物资（按 |entryDiff| 或价差估算）
   * 出售偏低：借营业外支出 / 贷（已在减少侧，此处按净值差简化为借支出贷收入对冲提示，仍落 1605 相关）
   */
  function pushAjeDraftToH43(): { ok: boolean; added: number; amount: number; message: string } {
    if (isReadonly.value) {
      return { ok: false, added: 0, amount: 0, message: '只读模式' }
    }
    const th = settings.value.priceDiffThreshold
    const targets = rows.value.filter((r) => {
      if (r.hasAnomaly === '是') return true
      return r.appraisedValue > 0 && Math.abs(r.priceDiffRate) > th
    })
    if (!targets.length) {
      return { ok: false, added: 0, amount: 0, message: '无价差超阈或标记异常行可推送' }
    }
    const pairs = targets.map((r) => {
      const name = (r.name || r.counterparty || '关联交易').trim()
      if (r.transType === '购入') {
        const amt = Math.abs(r.entryDiff) > 0.01
          ? Math.abs(r.entryDiff)
          : Math.abs(r.transAmount - r.appraisedValue)
        return {
          description: `关联购入公允性拟调整-${name}`,
          amount: amt,
          debitCode: '6602',
          debitName: '管理费用',
          creditCode: '1605',
          creditName: '工程物资',
          reportItemDebit: '管理费用',
          reportItemCredit: '工程物资',
          indexRef: 'H4-9',
          marker: H49_AJE_MARKER,
        }
      }
      const amt = Math.abs(r.appraisedValue) > 0
        ? Math.abs(r.transAmount - r.appraisedValue)
        : Math.abs(r.disposalGain) || Math.abs(r.transAmount)
      return {
        description: `关联出售公允性拟调整-${name}`,
        amount: amt,
        debitCode: '5301',
        debitName: '营业外支出',
        creditCode: '6301',
        creditName: '营业外收入',
        reportItemDebit: '营业外支出',
        reportItemCredit: '营业外收入',
        indexRef: 'H4-9',
        marker: H49_AJE_MARKER,
      }
    }).filter((p) => p.amount >= 0.005)
    return pushDraftPairsToH43({
      allResponses: params.allResponses.value,
      marker: H49_AJE_MARKER,
      pairs,
      onSave: params.onSave,
    })
  }

  return {
    rows,
    settings,
    auditNote,
    auditConclusion,
    purchaseRows,
    saleRows,
    summary,
    stats,
    addRow,
    deleteRow,
    removeRow,
    updateCell,
    recalcSimilarRatios,
    applyNoTransaction,
    updateSettings,
    buildNoteDraft,
    saveNote,
    saveConclusion,
    isUnfair,
    needsEntryDiffRemark: (row: H4RelatedPartyRow) =>
      needsEntryDiffRemark(row, settings.value.entryDiffThreshold),
    isLikelyInConsolidationScope,
    importFromH4H5,
    refreshDriftedFromSource,
    pushAjeDraftToH43,
    save,
    load,
    initFromAllResponses: load,
  }
}

export default useH4RelatedParty
