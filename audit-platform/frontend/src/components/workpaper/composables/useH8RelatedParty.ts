/**
 * useH8RelatedParty — H8-14 关联交易检查表 composable
 *
 * 对齐 Excel「关联交易检查表（使用权资产、租赁负债）」双表结构：
 *   1. 使用权资产（15列 + 年租金/市场租金/价差率数字化增强）
 *   2. 租赁负债（12列 + 价差率增强）
 *
 * 核心公式：
 *   净值 = 原值期末 − 累计折旧期末 − 减值准备期末
 *   价差率 = (年租金 − 市场租金) / 市场租金 × 100%
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Requirements 9.1
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Constants ───────────────────────────────────────────────────────────────

export const RELATED_PARTY_RELATIONSHIPS = [
  '母公司',
  '实际控制人',
  '控股股东',
  '控股股东、实际控制人的附属企业',
  '持有公司5%以上股份的法人或其他组织及其一致行动人',
  '联营企业',
  '合营企业',
  '董监高等关键管理人员',
  '其他关联方',
] as const

export type RelatedPartyRelationship = (typeof RELATED_PARTY_RELATIONSHIPS)[number]

export const ASSET_TYPE_OPTIONS = ['房屋建筑物', '机器设备', '运输工具', '土地使用权', '其他'] as const

export const ABNORMAL_OPTIONS = ['否', '是', '待核实'] as const

const DIFF_WARN_THRESHOLD = 10
const ROU_ROWS_KEY = 'H8-14-rows'
const LIAB_ROWS_KEY = 'H8-14-liability-rows'
const AUDIT_NOTE_KEY = 'H8-related-party-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-related-party-audit-conclusion'
const H8_2_ROWS_KEY = 'H8-2-rows'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 使用权资产关联交易行（Excel 15列 + 公允性增强） */
export interface H8RelatedPartyRouRow {
  rowId: string
  seq: number
  /** 关联单位名称 */
  relatedPartyName: string
  /** 关联方关系 */
  relationship: string
  /** 租赁项目 */
  leaseItem: string
  /** 租赁资产种类 */
  assetType: string
  /** 租赁发生时间及到期日 */
  leasePeriod: string
  /** 使用权资产原值期末审定数 */
  costEnding: number
  /** 使用权资产累计折旧期末审定数 */
  accumDepEnding: number
  /** 使用权资产减值准备期末审定数 */
  impairmentEnding: number
  /** 使用权资产净值（公式） */
  netValue: number
  /** 本期新增使用权资产金额（原值） */
  additionsCost: number
  /** 使用权资产本期折旧金额 */
  periodDep: number
  /** 定价政策 */
  pricingPolicy: string
  /** 年租金（数字化：用于价差率） */
  annualRent: number
  /** 市场租金参考（数字化） */
  marketRent: number
  /** 价差率%（公式） */
  priceDiffRate: number
  /** 关联交易是否存在异常 */
  isAbnormal: string
  /** 备注 */
  remark: string
  /** 索引号 / 合同号 */
  indexNo: string
  /** 来源 H8-2 rowId（带入时写入） */
  sourceRowId?: string
}

/** 租赁负债关联交易行（Excel 12列 + 公允性增强） */
export interface H8RelatedPartyLiabRow {
  rowId: string
  seq: number
  relatedPartyName: string
  relationship: string
  leaseItem: string
  assetType: string
  leasePeriod: string
  /** 租赁负债期末审定数 */
  liabilityEnding: number
  /** 本期应支付的租赁款项 */
  periodPayments: number
  /** 本期承担的租赁负债利息支出 */
  periodInterest: number
  pricingPolicy: string
  annualRent: number
  marketRent: number
  priceDiffRate: number
  isAbnormal: string
  remark: string
  indexNo: string
  /** 配对使用权资产行 rowId */
  pairedRouRowId?: string
}

export interface H8RelatedPartySummary {
  rouCount: number
  liabCount: number
  rouNetTotal: number
  liabEndingTotal: number
  abnormalCount: number
  highDiffCount: number
}

// ─── Pure helpers（可单测） ───────────────────────────────────────────────────

export function calcRouNetValue(cost: number, accumDep: number, impairment: number): number {
  return (Number(cost) || 0) - (Number(accumDep) || 0) - (Number(impairment) || 0)
}

export function calcPriceDiffRate(annualRent: number, marketRent: number): number {
  const m = Number(marketRent) || 0
  if (m === 0) return 0
  return (((Number(annualRent) || 0) - m) / m) * 100
}

export function suggestIsAbnormal(priceDiffRate: number, marketRent: number): string {
  if (!marketRent) return ''
  if (Math.abs(priceDiffRate) > DIFF_WARN_THRESHOLD) return '是'
  if (Math.abs(priceDiffRate) > 5) return '待核实'
  return '否'
}

function _newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

export function emptyRouRow(seq = 1): H8RelatedPartyRouRow {
  return {
    rowId: _newId('rou'),
    seq,
    relatedPartyName: '',
    relationship: '',
    leaseItem: '',
    assetType: '',
    leasePeriod: '',
    costEnding: 0,
    accumDepEnding: 0,
    impairmentEnding: 0,
    netValue: 0,
    additionsCost: 0,
    periodDep: 0,
    pricingPolicy: '',
    annualRent: 0,
    marketRent: 0,
    priceDiffRate: 0,
    isAbnormal: '',
    remark: '',
    indexNo: '',
  }
}

export function emptyLiabRow(seq = 1): H8RelatedPartyLiabRow {
  return {
    rowId: _newId('liab'),
    seq,
    relatedPartyName: '',
    relationship: '',
    leaseItem: '',
    assetType: '',
    leasePeriod: '',
    liabilityEnding: 0,
    periodPayments: 0,
    periodInterest: 0,
    pricingPolicy: '',
    annualRent: 0,
    marketRent: 0,
    priceDiffRate: 0,
    isAbnormal: '',
    remark: '',
    indexNo: '',
  }
}

export function recalcRouRow(row: H8RelatedPartyRouRow): void {
  row.costEnding = Number(row.costEnding) || 0
  row.accumDepEnding = Number(row.accumDepEnding) || 0
  row.impairmentEnding = Number(row.impairmentEnding) || 0
  row.additionsCost = Number(row.additionsCost) || 0
  row.periodDep = Number(row.periodDep) || 0
  row.annualRent = Number(row.annualRent) || 0
  row.marketRent = Number(row.marketRent) || 0
  row.netValue = calcRouNetValue(row.costEnding, row.accumDepEnding, row.impairmentEnding)
  row.priceDiffRate = calcPriceDiffRate(row.annualRent, row.marketRent)
}

export function recalcLiabRow(row: H8RelatedPartyLiabRow): void {
  row.liabilityEnding = Number(row.liabilityEnding) || 0
  row.periodPayments = Number(row.periodPayments) || 0
  row.periodInterest = Number(row.periodInterest) || 0
  row.annualRent = Number(row.annualRent) || 0
  row.marketRent = Number(row.marketRent) || 0
  row.priceDiffRate = calcPriceDiffRate(row.annualRent, row.marketRent)
}

/** 兼容旧版单表（合同号/关联租金/公允性评价） */
function _migrateLegacyRou(raw: any, idx: number): H8RelatedPartyRouRow {
  const row = emptyRouRow(raw.seq ?? idx + 1)
  row.rowId = raw.rowId ?? row.rowId
  row.relatedPartyName = raw.relatedPartyName ?? raw.relatedParty ?? ''
  row.relationship = raw.relationship ?? ''
  row.leaseItem = raw.leaseItem ?? raw.assetName ?? ''
  row.assetType = raw.assetType ?? ''
  row.leasePeriod = raw.leasePeriod ?? ''
  row.costEnding = Number(raw.costEnding) || 0
  row.accumDepEnding = Number(raw.accumDepEnding) || 0
  row.impairmentEnding = Number(raw.impairmentEnding) || 0
  row.additionsCost = Number(raw.additionsCost) || 0
  row.periodDep = Number(raw.periodDep) || 0
  row.pricingPolicy = raw.pricingPolicy ?? raw.pricingBasis ?? ''
  row.annualRent = Number(raw.annualRent ?? raw.relatedRental) || 0
  row.marketRent = Number(raw.marketRent ?? raw.marketRental ?? raw.marketRentRef) || 0
  row.remark = raw.remark ?? ''
  row.indexNo = raw.indexNo ?? raw.contractNo ?? ''
  row.sourceRowId = raw.sourceRowId

  // 旧公允性评价 → 是否异常
  if (raw.isAbnormal) {
    row.isAbnormal = String(raw.isAbnormal)
  } else if (raw.fairnessAssessment === '存在异常') {
    row.isAbnormal = '是'
  } else if (raw.fairnessAssessment === '公允' || raw.fairnessAssessment === '基本公允') {
    row.isAbnormal = '否'
  } else if (raw.fairnessAssessment === '待核实') {
    row.isAbnormal = '待核实'
  } else if (raw.needsAdjustment === true || raw.needsAdjustment === '是') {
    row.isAbnormal = '是'
  }

  recalcRouRow(row)
  return row
}

function _fromRouRaw(raw: any, idx: number): H8RelatedPartyRouRow {
  return _migrateLegacyRou(raw, idx)
}

function _fromLiabRaw(raw: any, idx: number): H8RelatedPartyLiabRow {
  const row = emptyLiabRow(raw.seq ?? idx + 1)
  row.rowId = raw.rowId ?? row.rowId
  row.relatedPartyName = raw.relatedPartyName ?? raw.relatedParty ?? ''
  row.relationship = raw.relationship ?? ''
  row.leaseItem = raw.leaseItem ?? raw.assetName ?? ''
  row.assetType = raw.assetType ?? ''
  row.leasePeriod = raw.leasePeriod ?? ''
  row.liabilityEnding = Number(raw.liabilityEnding) || 0
  row.periodPayments = Number(raw.periodPayments) || 0
  row.periodInterest = Number(raw.periodInterest) || 0
  row.pricingPolicy = raw.pricingPolicy ?? ''
  row.annualRent = Number(raw.annualRent ?? raw.relatedRental) || 0
  row.marketRent = Number(raw.marketRent ?? raw.marketRental) || 0
  row.isAbnormal = raw.isAbnormal ?? ''
  row.remark = raw.remark ?? ''
  row.indexNo = raw.indexNo ?? raw.contractNo ?? ''
  row.pairedRouRowId = raw.pairedRouRowId
  recalcLiabRow(row)
  return row
}

function _persistableRou(row: H8RelatedPartyRouRow) {
  return {
    rowId: row.rowId,
    seq: row.seq,
    relatedPartyName: row.relatedPartyName,
    relationship: row.relationship,
    leaseItem: row.leaseItem,
    assetType: row.assetType,
    leasePeriod: row.leasePeriod,
    costEnding: row.costEnding,
    accumDepEnding: row.accumDepEnding,
    impairmentEnding: row.impairmentEnding,
    additionsCost: row.additionsCost,
    periodDep: row.periodDep,
    pricingPolicy: row.pricingPolicy,
    annualRent: row.annualRent,
    marketRent: row.marketRent,
    isAbnormal: row.isAbnormal,
    remark: row.remark,
    indexNo: row.indexNo,
    sourceRowId: row.sourceRowId,
    // 兼容旧导入导出字段名
    contractNo: row.indexNo,
    relatedParty: row.relatedPartyName,
    assetName: row.leaseItem,
    relatedRental: row.annualRent,
    marketRental: row.marketRent,
    fairnessAssessment: row.isAbnormal === '是' ? '存在异常' : row.isAbnormal === '否' ? '公允' : row.isAbnormal,
  }
}

function _persistableLiab(row: H8RelatedPartyLiabRow) {
  return {
    rowId: row.rowId,
    seq: row.seq,
    relatedPartyName: row.relatedPartyName,
    relationship: row.relationship,
    leaseItem: row.leaseItem,
    assetType: row.assetType,
    leasePeriod: row.leasePeriod,
    liabilityEnding: row.liabilityEnding,
    periodPayments: row.periodPayments,
    periodInterest: row.periodInterest,
    pricingPolicy: row.pricingPolicy,
    annualRent: row.annualRent,
    marketRent: row.marketRent,
    isAbnormal: row.isAbnormal,
    remark: row.remark,
    indexNo: row.indexNo,
    pairedRouRowId: row.pairedRouRowId,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8RelatedParty(params: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  const rouRows = ref<H8RelatedPartyRouRow[]>([])
  const liabRows = ref<H8RelatedPartyLiabRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getText(itemId: string): string {
    const item = allResponses.value.get(itemId)
    if (!item) return ''
    return item.remark ?? item.conclusion ?? ''
  }

  function load(): void {
    const rouRaw = _getJson(ROU_ROWS_KEY)
    rouRows.value = Array.isArray(rouRaw) ? rouRaw.map(_fromRouRaw) : []

    const liabRaw = _getJson(LIAB_ROWS_KEY)
    liabRows.value = Array.isArray(liabRaw) ? liabRaw.map(_fromLiabRaw) : []

    auditNote.value = _getText(AUDIT_NOTE_KEY)
    auditConclusion.value = _getText(AUDIT_CONCLUSION_KEY)
  }

  function _persistRou(): void {
    onSave?.(ROU_ROWS_KEY, rouRows.value.map(_persistableRou))
  }

  function _persistLiab(): void {
    onSave?.(LIAB_ROWS_KEY, liabRows.value.map(_persistableLiab))
  }

  function _renumber(rows: { seq: number }[]): void {
    rows.forEach((r, i) => { r.seq = i + 1 })
  }

  // ── ROU CRUD ───────────────────────────────────────────────────────────────

  function addRouRow(): H8RelatedPartyRouRow {
    const row = emptyRouRow(rouRows.value.length + 1)
    rouRows.value.push(row)
    _persistRou()
    return row
  }

  function removeRouRow(rowId: string): void {
    const idx = rouRows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rouRows.value.splice(idx, 1)
    _renumber(rouRows.value)
    // 解除负债配对
    liabRows.value.forEach(l => {
      if (l.pairedRouRowId === rowId) l.pairedRouRowId = undefined
    })
    _persistRou()
    _persistLiab()
  }

  function updateRouCell(rowId: string, field: keyof H8RelatedPartyRouRow, value: any): void {
    const row = rouRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    recalcRouRow(row)
    if (
      (field === 'annualRent' || field === 'marketRent') &&
      !row.isAbnormal &&
      row.marketRent > 0
    ) {
      const suggested = suggestIsAbnormal(row.priceDiffRate, row.marketRent)
      if (suggested) row.isAbnormal = suggested
    }
    _persistRou()
  }

  /** 从使用权资产行一键生成配对租赁负债行（复制关联方/项目/期间） */
  function pairLiabilityFromRou(rouRowId: string): H8RelatedPartyLiabRow | null {
    const rou = rouRows.value.find(r => r.rowId === rouRowId)
    if (!rou) return null
    const existing = liabRows.value.find(l => l.pairedRouRowId === rouRowId)
    if (existing) return existing

    const liab = emptyLiabRow(liabRows.value.length + 1)
    liab.relatedPartyName = rou.relatedPartyName
    liab.relationship = rou.relationship
    liab.leaseItem = rou.leaseItem
    liab.assetType = rou.assetType
    liab.leasePeriod = rou.leasePeriod
    liab.pricingPolicy = rou.pricingPolicy
    liab.annualRent = rou.annualRent
    liab.marketRent = rou.marketRent
    liab.isAbnormal = rou.isAbnormal
    liab.indexNo = rou.indexNo
    liab.pairedRouRowId = rou.rowId
    recalcLiabRow(liab)
    liabRows.value.push(liab)
    _persistLiab()
    return liab
  }

  // ── Liability CRUD ─────────────────────────────────────────────────────────

  function addLiabRow(): H8RelatedPartyLiabRow {
    const row = emptyLiabRow(liabRows.value.length + 1)
    liabRows.value.push(row)
    _persistLiab()
    return row
  }

  function removeLiabRow(rowId: string): void {
    const idx = liabRows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    liabRows.value.splice(idx, 1)
    _renumber(liabRows.value)
    _persistLiab()
  }

  function updateLiabCell(rowId: string, field: keyof H8RelatedPartyLiabRow, value: any): void {
    const row = liabRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    recalcLiabRow(row)
    if (
      (field === 'annualRent' || field === 'marketRent') &&
      !row.isAbnormal &&
      row.marketRent > 0
    ) {
      const suggested = suggestIsAbnormal(row.priceDiffRate, row.marketRent)
      if (suggested) row.isAbnormal = suggested
    }
    _persistLiab()
  }

  // ── H8-2 带入 ──────────────────────────────────────────────────────────────

  function _readH82Rows(): any[] {
    const raw = _getJson(H8_2_ROWS_KEY)
    return Array.isArray(raw) ? raw : []
  }

  /** 从 H8-2 明细带入候选（按合同号去重，已存在则跳过） */
  function importFromH82(selectedContractNos?: string[]): {
    added: number
    skipped: number
    total: number
  } {
    const sources = _readH82Rows()
    const existingKeys = new Set(
      rouRows.value.map(r => (r.sourceRowId || r.indexNo || '').trim()).filter(Boolean),
    )
    let added = 0
    let skipped = 0

    for (const src of sources) {
      const contractNo = String(src.contractNo ?? '').trim()
      if (!contractNo) continue
      if (selectedContractNos && !selectedContractNos.includes(contractNo)) continue

      const sourceKey = String(src.rowId ?? contractNo)
      if (existingKeys.has(sourceKey) || existingKeys.has(contractNo)) {
        skipped++
        continue
      }

      const row = emptyRouRow(rouRows.value.length + 1)
      row.relatedPartyName = String(src.lessor ?? '')
      row.leaseItem = String(src.assetName ?? '')
      row.assetType = String(src.leaseType ?? '')
      const start = String(src.startDate ?? '')
      const end = String(src.endDate ?? '')
      row.leasePeriod = [start, end].filter(Boolean).join(' ~ ')
      row.costEnding = Number(src.initialAmount) || 0
      row.accumDepEnding = Number(src.accDepEnd) || 0
      row.periodDep = Number(src.depCurrentPeriod) || 0
      row.additionsCost = Number(src.initialAmount) || 0
      row.indexNo = contractNo
      row.sourceRowId = String(src.rowId ?? '')
      row.remark = '自 H8-2 带入，请确认是否关联方并补全关联关系/定价政策'
      recalcRouRow(row)
      rouRows.value.push(row)
      existingKeys.add(sourceKey)
      existingKeys.add(contractNo)
      added++
    }

    if (added > 0) _persistRou()
    return { added, skipped, total: sources.length }
  }

  // ── 审计说明 / 结论 ────────────────────────────────────────────────────────

  function saveAuditNote(val: string): void {
    auditNote.value = val
    onSave?.(AUDIT_NOTE_KEY, val)
  }

  function saveAuditConclusion(val: string): void {
    auditConclusion.value = val
    onSave?.(AUDIT_CONCLUSION_KEY, val)
  }

  function draftAuditNote(): string {
    const lines: string[] = []
    lines.push('一、关联方租赁识别与范围')
    lines.push(
      `本期共登记关联方使用权资产 ${rouRows.value.length} 笔（净值合计 ${summary.value.rouNetTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元），` +
      `关联方租赁负债 ${liabRows.value.length} 笔（期末审定合计 ${summary.value.liabEndingTotal.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元）。`,
    )
    lines.push('')
    lines.push('二、定价公允性核查')
    const highDiff = [
      ...rouRows.value.filter(r => Math.abs(r.priceDiffRate) > DIFF_WARN_THRESHOLD && r.marketRent > 0),
      ...liabRows.value.filter(r => Math.abs(r.priceDiffRate) > DIFF_WARN_THRESHOLD && r.marketRent > 0),
    ]
    if (highDiff.length) {
      lines.push(`价差率绝对值超过 ${DIFF_WARN_THRESHOLD}% 的租赁 ${highDiff.length} 笔，需重点关注定价合理性及是否存在利益输送：`)
      highDiff.forEach((r: any) => {
        lines.push(
          `  - ${r.relatedPartyName || '（未填关联方）'} / ${r.leaseItem || '-'}：年租金 ${r.annualRent}，市场租金 ${r.marketRent}，价差率 ${r.priceDiffRate.toFixed(1)}%`,
        )
      })
    } else {
      lines.push('经与市场租金参考比对，未发现价差率超过10%的关联租赁；或尚未获取市场租金参考。')
    }
    lines.push('')
    lines.push('三、程序执行')
    lines.push('已核对关联方租赁合同、定价政策及决策审批文件，核查使用权资产/租赁负债期末审定数与 H8-2/H9 勾稽，并评估关联交易披露完整性（CAS36）。')
    const abnormal = [
      ...rouRows.value.filter(r => r.isAbnormal === '是'),
      ...liabRows.value.filter(r => r.isAbnormal === '是'),
    ]
    if (abnormal.length) {
      lines.push('')
      lines.push(`四、异常事项（${abnormal.length} 笔标记存在异常）`)
      abnormal.forEach((r: any) => {
        lines.push(`  - ${r.relatedPartyName}：${r.remark || '详见备注/索引'}`)
      })
    }
    return lines.join('\n')
  }

  // ── Summary ────────────────────────────────────────────────────────────────

  const summary: ComputedRef<H8RelatedPartySummary> = computed(() => {
    const abnormalCount =
      rouRows.value.filter(r => r.isAbnormal === '是').length +
      liabRows.value.filter(r => r.isAbnormal === '是').length
    const highDiffCount =
      rouRows.value.filter(r => r.marketRent > 0 && Math.abs(r.priceDiffRate) > DIFF_WARN_THRESHOLD).length +
      liabRows.value.filter(r => r.marketRent > 0 && Math.abs(r.priceDiffRate) > DIFF_WARN_THRESHOLD).length
    return {
      rouCount: rouRows.value.length,
      liabCount: liabRows.value.length,
      rouNetTotal: rouRows.value.reduce((s, r) => s + (r.netValue || 0), 0),
      liabEndingTotal: liabRows.value.reduce((s, r) => s + (r.liabilityEnding || 0), 0),
      abnormalCount,
      highDiffCount,
    }
  })

  watch(allResponses, () => load(), { immediate: true })

  return {
    rouRows,
    liabRows,
    auditNote,
    auditConclusion,
    summary,
    addRouRow,
    removeRouRow,
    updateRouCell,
    pairLiabilityFromRou,
    addLiabRow,
    removeLiabRow,
    updateLiabCell,
    importFromH82,
    saveAuditNote,
    saveAuditConclusion,
    draftAuditNote,
    load,
    ROU_ROWS_KEY,
    LIAB_ROWS_KEY,
    DIFF_WARN_THRESHOLD,
  }
}

export default useH8RelatedParty
