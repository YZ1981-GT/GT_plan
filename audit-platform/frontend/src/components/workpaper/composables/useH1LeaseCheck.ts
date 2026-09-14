/**
 * useH1LeaseCheck — H1-18~20 关联/租赁检查 composable
 *
 * RelatedPartyRow（致同 H1-18：合并范围外购入表 + 出售表 + 公允性增强）
 * + OperatingLeaseRow（致同 H1-19）+ FinanceLeaseRow
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.16
 * Requirements: 15.1-15.10
 *
 * H1-18 Excel 核心：
 *   出售时净值 H = 原值E − 累计折旧F − 减值准备G
 *   数字底稿增强：价格差异率 = (交易价 − 公允/评估价) ÷ 公允价 × 100%，|率|>10% 标红
 *
 * H1-19 Excel 核心公式（致同模板）：
 *   月折旧额 N = 原值J×(1-残值率M)/折旧年限L/12
 *   本期应计折旧 O = 本年月份I×月折旧N；差异 Q = O−账面P
 *   本期应计租金 S = 本年月份I×月租金R；差异 U = S−账面T
 *
 * H1-20 Excel 核心公式：
 *   应收融资租赁款 = 最低租赁收款额 + 初始直接费用
 *   未确认融资收益 = 最低租赁收款额 − 租赁投资净额
 *   ③融资收入 = 期初净投资×内含利率；④减少额 = 租金−③；⑤期末 = 期初−④
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import {
  calcSubtotal,
  calcFinanceLeaseReceivable,
  calcUnearnedFinanceIncome,
  calcPvToFvRatio,
  buildFinanceLeaseAmortization,
  solveLeaseImplicitRatePct,
  type FinanceLeaseAmortPeriod,
} from './useH1FormulaEngine'
import type { H1FinanceLeaseG5Seed } from './h1FinanceLeaseG5Pull'

export type { FinanceLeaseAmortPeriod }

// ─── Types ───────────────────────────────────────────────────────────────────

/** 关联交易行 — 对齐致同 H1-18 购入/出售/无偿调拨 + 公允性/勾稽增强 */
export interface RelatedPartyRow {
  rowId: string
  seq: number
  /** 购入 | 出售 | 无偿调拨 */
  transType: string
  counterparty: string            // 关联单位名称
  relationship: string            // 关联方关系
  assetCategory: string           // 资产类别
  name: string                    // 固定资产名称
  /** 交易价格：购入=购买价款；出售=销售价格(不含税)；无偿调拨通常为 0 */
  transAmount: number
  /** 购入/调拨：固定资产入账价值 */
  bookValue: number
  /** 入账差异（公式 = 入账价值 − 购买价款；购入/调拨） */
  entryDiff: number
  /** 购入：折旧年限 */
  depYears: number
  /** 出售：出售时原值 / 累计折旧 / 减值准备 */
  originalCost: number
  accumDep: number
  impairment: number
  /** 出售时净值（公式 = 原值−累计折旧−减值） */
  netValue: number
  /** 处置损益（增强公式 = 售价−净值，仅出售有意义） */
  disposalGain: number
  /** H10 勾稽：对应处置损益；差异 = 本表处置损益 − H10 */
  h10Gain: number | null
  h10Diff: number | null
  transDate: string               // 购入/出售时间
  /** 同类交易总额（手填或「按本表重算」写入；用于占比） */
  categoryTotal: number | null
  /** 占同类交易金额的比例%（公式 = 交易价÷同类总额×100） */
  similarRatio: number | null
  pricingPolicy: string           // 定价政策（Excel）
  pricingBasis: string            // 兼容旧字段，与 pricingPolicy 同步
  hasAnomaly: string              // 关联交易是否存在异常
  appraisedValue: number          // 公允/评估价值（数字底稿增强）
  priceDiffRate: number           // 价格差异率(%)（公式）
  isFair: string                  // 是否公允
  approvalDoc: string             // 审批文件
  conclusion: string              // 结论
  remark: string                  // 备注
  indexRef: string                // 索引号
  /** 来源底稿 H1-7 / H1-8 */
  sourceWp: string
  sourceRowId: string
  /** 带入时源行指纹，用于漂移检测 */
  sourceFingerprint: string
  /** 资产编号（H10 / H1-7·8 匹配） */
  assetNo: string
}

export const DEFAULT_PRICE_DIFF_THRESHOLD = 10
/** 入账差异强制备注：相对价款的比例阈值（与价差阈值共用默认值时可覆盖） */
export const DEFAULT_ENTRY_DIFF_THRESHOLD = 10

/** 合并范围内常见关联关系（带入/选择时提示确认） */
export const IN_SCOPE_RELATIONSHIP_KEYWORDS = [
  '子公司', '孙公司', '全资子公司', '控股子公司', '同一控制下企业',
]

export interface H1RelatedPartySettings {
  priceDiffThreshold: number
  entryDiffThreshold: number
  noTransaction: boolean
}

export function defaultRelatedPartySettings(): H1RelatedPartySettings {
  return {
    priceDiffThreshold: DEFAULT_PRICE_DIFF_THRESHOLD,
    entryDiffThreshold: DEFAULT_ENTRY_DIFF_THRESHOLD,
    noTransaction: false,
  }
}

/** 重算关联交易行公式：入账差异、出售净值、处置损益、占比、价格差异率 */
export function recalcRelatedPartyRow(row: RelatedPartyRow): void {
  row.netValue = Math.max(0, (row.originalCost || 0) - (row.accumDep || 0) - (row.impairment || 0))
  if (row.transType === '出售') {
    row.disposalGain = (row.transAmount || 0) - row.netValue
    row.entryDiff = 0
  } else {
    row.disposalGain = 0
    row.entryDiff = (row.bookValue || 0) - (row.transAmount || 0)
  }
  if (row.categoryTotal != null && row.categoryTotal > 0) {
    row.similarRatio = (row.transAmount || 0) / row.categoryTotal * 100
  }
  if (row.pricingPolicy && !row.pricingBasis) row.pricingBasis = row.pricingPolicy
  if (row.pricingBasis && !row.pricingPolicy) row.pricingPolicy = row.pricingBasis
  row.priceDiffRate = row.appraisedValue > 0
    ? ((row.transAmount - row.appraisedValue) / row.appraisedValue * 100)
    : 0
  if (row.h10Gain != null) {
    row.h10Diff = row.disposalGain - row.h10Gain
  } else {
    row.h10Diff = null
  }
}

export function emptyRelatedPartyRow(seq: number, transType: string = '购入'): RelatedPartyRow {
  return {
    rowId: `rp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    transType,
    counterparty: '', relationship: '', assetCategory: '', name: '',
    transAmount: 0, bookValue: 0, entryDiff: 0, depYears: 0,
    originalCost: 0, accumDep: 0, impairment: 0, netValue: 0, disposalGain: 0,
    h10Gain: null, h10Diff: null,
    transDate: '', categoryTotal: null, similarRatio: null,
    pricingPolicy: '', pricingBasis: '', hasAnomaly: '',
    appraisedValue: 0, priceDiffRate: 0, isFair: '',
    approvalDoc: '', conclusion: '', remark: '', indexRef: '',
    sourceWp: '', sourceRowId: '', sourceFingerprint: '', assetNo: '',
  }
}

export function _safeParseRows(remark: string | null | undefined): any[] {
  if (!remark) return []
  try {
    const parsed = JSON.parse(remark)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function buildH7SourceFingerprint(src: any): string {
  return JSON.stringify({
    name: src?.name ?? '',
    assetNo: src?.assetNo ?? '',
    originalCost: Number(src?.originalCost) || 0,
    contractAmount: Number(src?.contractAmount) || 0,
    relatedPartyName: src?.relatedPartyName ?? '',
    acquisitionDate: src?.acquisitionDate ?? '',
  })
}

export function buildH8SourceFingerprint(src: any): string {
  return JSON.stringify({
    name: src?.name ?? '',
    assetNo: src?.assetNo ?? '',
    originalCost: Number(src?.originalCost) || 0,
    accDep: Number(src?.accDep) || 0,
    impairment: Number(src?.impairment) || 0,
    disposalIncome: Number(src?.disposalIncome) || 0,
    relatedPartyName: src?.relatedPartyName ?? '',
    disposalDate: src?.disposalDate ?? '',
  })
}

export function applyH7SourceToRow(row: RelatedPartyRow, src: any): void {
  row.transType = '购入'
  row.name = src.name ?? row.name
  row.assetNo = src.assetNo ?? row.assetNo
  row.transAmount = Number(src.contractAmount || src.originalCost) || 0
  row.bookValue = Number(src.originalCost) || 0
  row.transDate = src.acquisitionDate ?? ''
  row.counterparty = src.relatedPartyName ?? row.counterparty
  row.relationship = src.relationship ?? row.relationship
  row.pricingPolicy = src.contractRef ? `合同:${src.contractRef}` : (row.pricingPolicy || '')
  row.indexRef = src.indexRef || row.indexRef || 'H1-7'
  row.sourceWp = 'H1-7'
  row.sourceRowId = src.rowId ?? row.sourceRowId
  row.sourceFingerprint = buildH7SourceFingerprint(src)
  recalcRelatedPartyRow(row)
}

export function applyH8SourceToRow(row: RelatedPartyRow, src: any): void {
  row.transType = '出售'
  row.name = src.name ?? row.name
  row.assetNo = src.assetNo ?? row.assetNo
  row.counterparty = src.relatedPartyName ?? row.counterparty
  row.relationship = src.relationship ?? row.relationship
  row.originalCost = Number(src.originalCost) || 0
  row.accumDep = Number(src.accDep) || 0
  row.impairment = Number(src.impairment) || 0
  row.transAmount = Number(src.disposalIncome) || 0
  row.transDate = src.disposalDate ?? ''
  row.pricingPolicy = src.pricingBasis ?? row.pricingPolicy
  row.approvalDoc = src.approvalDoc ?? row.approvalDoc
  row.indexRef = src.indexRef || row.indexRef || 'H1-8'
  row.sourceWp = 'H1-8'
  row.sourceRowId = src.rowId ?? row.sourceRowId
  row.sourceFingerprint = buildH8SourceFingerprint(src)
  recalcRelatedPartyRow(row)
}

/** 检测已带入行相对 H1-7/H1-8 源是否漂移（含源行被删除） */
export function detectSourceDrift(
  relatedRows: RelatedPartyRow[],
  h7Rows: any[],
  h8Rows: any[],
): RelatedPartyRow[] {
  const drifted: RelatedPartyRow[] = []
  for (const row of relatedRows) {
    if (!row.sourceRowId || !row.sourceWp) continue
    if (row.sourceWp === 'H1-7') {
      const src = h7Rows.find((r) => r.rowId === row.sourceRowId)
      if (!src || buildH7SourceFingerprint(src) !== (row.sourceFingerprint || '')) drifted.push(row)
    } else if (row.sourceWp === 'H1-8') {
      const src = h8Rows.find((r) => r.rowId === row.sourceRowId)
      if (!src || buildH8SourceFingerprint(src) !== (row.sourceFingerprint || '')) drifted.push(row)
    }
  }
  return drifted
}

/** 从 H1-2 明细按资产类别汇总本期增加/减少，作为同类交易总额 */
export function aggregateH12CategoryTotals(
  detailRows: any[],
  direction: '购入' | '出售',
): Map<string, number> {
  const map = new Map<string, number>()
  for (const r of detailRows) {
    const cat = String(r.category || '未分类').trim() || '未分类'
    const amt = direction === '出售'
      ? Number(r.originalCostDecrease) || 0
      : Number(r.originalCostIncrease) || 0
    if (!(amt > 0)) continue
    map.set(cat, (map.get(cat) || 0) + amt)
  }
  return map
}

export function fillCategoryTotalsFromDetail(
  relatedRows: RelatedPartyRow[],
  detailRows: any[],
): number {
  const purchaseMap = aggregateH12CategoryTotals(detailRows, '购入')
  const saleMap = aggregateH12CategoryTotals(detailRows, '出售')
  let n = 0
  for (const row of relatedRows) {
    const cat = String(row.assetCategory || '').trim()
    if (!cat) continue
    const map = row.transType === '出售' ? saleMap : purchaseMap
    if (!map.has(cat)) continue
    row.categoryTotal = map.get(cat)!
    recalcRelatedPartyRow(row)
    n++
  }
  return n
}

/** H10 匹配：sourceRowRef/linkageId → assetNo → 唯一资产名称 */
export function matchH10Detail(row: RelatedPartyRow, h10Rows: any[]): any | null {
  if (!h10Rows.length) return null
  const byRef = h10Rows.find((h) => {
    const ref = String(h.sourceRowRef || h.linkageId || '')
    if (!ref) return false
    return ref === row.sourceRowId || ref === row.rowId || ref === row.assetNo
  })
  if (byRef) return byRef
  if (row.assetNo) {
    const byNo = h10Rows.find((h) =>
      h.assetNo === row.assetNo || h.assetCode === row.assetNo,
    )
    if (byNo) return byNo
  }
  if (!row.name) return null
  const nameHits = h10Rows.filter((h) => (h.assetName || h.name) === row.name)
  if (nameHits.length === 1) return nameHits[0]
  return null
}

export function isLikelyInConsolidationScope(relationship: string): boolean {
  const s = String(relationship || '')
  return IN_SCOPE_RELATIONSHIP_KEYWORDS.some((k) => s.includes(k))
}

/** 入账差异超阈值且未填备注 → 需强制说明 */
export function needsEntryDiffRemark(
  row: RelatedPartyRow,
  thresholdPct: number = DEFAULT_ENTRY_DIFF_THRESHOLD,
): boolean {
  if (row.transType === '出售') return false
  const base = Math.abs(row.transAmount) || Math.abs(row.bookValue) || 0
  if (base <= 0) return Math.abs(row.entryDiff) > 0.01 && !(row.remark || '').trim()
  const rate = Math.abs(row.entryDiff) / base * 100
  return rate > thresholdPct && !(row.remark || '').trim()
}

export function buildAdjustmentSuggestionDraft(
  rows: RelatedPartyRow[],
  priceTh: number = DEFAULT_PRICE_DIFF_THRESHOLD,
  entryTh: number = DEFAULT_ENTRY_DIFF_THRESHOLD,
): string {
  const lines: string[] = [
    '【H1-18 异常调整建议草稿】（推送 A13 / 披露附注前请复核）',
    '',
  ]
  const unfair = rows.filter((r) => Math.abs(r.priceDiffRate) > priceTh)
  const entryMiss = rows.filter((r) => needsEntryDiffRemark(r, entryTh))
  const h10m = rows.filter((r) => r.h10Diff != null && Math.abs(r.h10Diff) > 0.01)
  if (!unfair.length && !entryMiss.length && !h10m.length) {
    lines.push('未见需调整的价差/入账差异/H10勾稽异常。')
    return lines.join('\n')
  }
  if (unfair.length) {
    lines.push(`一、定价差异率超过 ${priceTh}%（建议评估是否调整入账价值或补充披露）：`)
    for (const r of unfair) {
      const adj = r.appraisedValue > 0 ? (r.appraisedValue - r.transAmount) : 0
      lines.push(
        `  · [${r.transType}] ${r.counterparty}/${r.name}：交易价 ${r.transAmount.toFixed(2)}，公允 ${r.appraisedValue.toFixed(2)}，差异率 ${r.priceDiffRate.toFixed(1)}%` +
        (adj ? `；建议关注调整额约 ${adj.toFixed(2)}` : ''),
      )
    }
    lines.push('  建议分录方向：若应以公允价入账，借记/贷记固定资产，差额计入资本公积或当期损益（视交易性质）。')
    lines.push('')
  }
  if (entryMiss.length) {
    lines.push(`二、入账价值与价款差异超过 ${entryTh}% 且未说明（请补备注或核查税费构成）：`)
    for (const r of entryMiss) {
      lines.push(`  · ${r.counterparty}/${r.name}：价款 ${r.transAmount.toFixed(2)}，入账 ${r.bookValue.toFixed(2)}，差异 ${r.entryDiff.toFixed(2)}`)
    }
    lines.push('')
  }
  if (h10m.length) {
    lines.push('三、与 H10 处置损益不一致（建议核对处置费用/税费后调整 H10 或本表）：')
    for (const r of h10m) {
      lines.push(`  · ${r.name}：本表损益 ${r.disposalGain.toFixed(2)}，H10 ${r.h10Gain?.toFixed(2)}，差异 ${r.h10Diff?.toFixed(2)}`)
    }
    lines.push('')
  }
  lines.push('披露：以上重大关联方固定资产交易应在 A7-1 / 附注按 CAS36 充分披露交易方、金额、定价政策及未结算余额。')
  return lines.join('\n')
}

export interface A7ReconcileResult {
  h118Total: number
  a7Total: number | null
  diff: number | null
  status: 'ok' | 'mismatch' | 'no-a7' | 'empty'
  note: string
}

/** 本表交易合计 vs A7-1 披露关联交易合计（口径可能更宽，仅交叉提示） */
export function reconcileA7Disclosure(
  h118Total: number,
  a7Total: number | null | undefined,
  tolerance = 0.01,
): A7ReconcileResult {
  if (!(h118Total > 0) && !(a7Total != null && a7Total > 0)) {
    return { h118Total: 0, a7Total: a7Total ?? null, diff: null, status: 'empty', note: '双方均无金额' }
  }
  if (a7Total == null) {
    return {
      h118Total,
      a7Total: null,
      diff: null,
      status: 'no-a7',
      note: '未取得 A7-1 合计，请打开关联方汇总或手工核对附注',
    }
  }
  const diff = h118Total - a7Total
  if (Math.abs(diff) <= tolerance) {
    return { h118Total, a7Total, diff, status: 'ok', note: '本表合计与 A7-1 合计一致（若 A7 含非固定资产交易则属巧合，请仍核对附注明细）' }
  }
  return {
    h118Total,
    a7Total,
    diff,
    status: 'mismatch',
    note: `本表合计 ${h118Total.toFixed(2)} 与 A7-1 合计 ${a7Total.toFixed(2)} 差异 ${diff.toFixed(2)}（A7 通常含全部关联交易，请核对附注中固定资产相关分项）`,
  }
}

/** 经营租出行 (H1-19，对齐致同检查表 + 收益率分析) */
export interface OperatingLeaseRow {
  rowId: string
  seq: number
  // ── 基础识别 ──
  assetName: string               // 固定资产名称
  assetCategory: string           // 资产类别
  specModel: string               // 规格型号
  lessee: string                  // 承租单位名称
  leaseStart: string              // 租赁开始日
  leaseEnd: string                // 租赁到期日
  contractAmount: number          // 租赁合同总金额
  monthsThisYear: number          // 本年应计提月份数
  // ── 资产计价参数 ──
  originalCost: number            // 固定资产原值
  accumDep: number                // 累计折旧
  depYears: number                // 折旧年限
  residualRate: number            // 残值率(%)，如 5 表示 5%
  netValue: number                // 净值（原值−累计折旧，可手改）
  // ── 折旧费用核对（公式）──
  monthlyDep: number              // 月折旧额 = 原值×(1−残值率)/年限/12
  expectedDep: number             // 本期应计入其他业务支出的折旧额
  bookedDep: number               // 账面计入其他业务支出的折旧额
  depDiff: number                 // 折旧差异 = 应计−账面
  // ── 租金收入核对（公式）──
  monthlyRent: number             // 月租金收入
  expectedRent: number            // 本期应计租金收入
  bookedRent: number              // 账面计入其他业务收入的租金额
  incomeDiff: number              // 租金差异 = 应计−账面
  // ── 合同索引 / 条款 ──
  contractIndex: string           // 租赁合同索引号
  contractNo: string              // 合同编号
  deposit: number                 // 押金
  renewalTerms: string            // 续租条款
  earlyTermination: string        // 提前终止条款
  isRelatedParty: string          // 是否关联(Y/N)
  hasChanged: string              // 是否变更(Y/N)
  accountTreatment: string        // 会计处理
  // ── 收益率分析（数字底稿增强）──
  leaseTerm: number               // 租赁期限(月)，可由起止日推算
  annualRent: number              // 年租金（=月租金×12）
  totalRentIncome: number         // 总租金收入（合同期，供附注联动）
  depAlloc: number                // 年折旧分摊（=月折旧×12，供收益率）
  maintenanceCost: number         // 维修费用
  netIncome: number               // 租赁净收益 = 年租金−年折旧−维修
  returnRate: number              // 收益率(%) = 净收益/原值×100
  marketRent: number              // 市场年租金参考
  rentDiff: number                // 与市场租金差额 = 年租金−市场年租
  conclusion: string
  remark: string
}

/** 融资租出行 (H1-20，对齐 Excel：分类判断 → 初始计量 → 收益分配) */
export interface FinanceLeaseRow {
  rowId: string
  seq: number
  assetCode: string               // 固定资产编号
  assetName: string               // 资产名称
  lessee: string                  // 承租单位名称
  leaseStart: string              // 租赁开始日
  contractIndex: string           // 租赁合同索引号
  originalCost: number            // 资产原值
  fairValue: number               // 租赁开始日公允价值
  classificationBasis: string     // 租赁分类依据说明
  classResult1: string            // ①所有权转移
  classResult2: string            // ②优惠购买选择权
  classResult3: string            // ③租期≥寿命大部分(≥75%)
  classResult4: string            // ④最低收款额现值≥公允几乎全部(≥90%)
  classResult5: string            // ⑤专用性资产
  /** 最低租赁收款额（出租人口径；字段名 minLeasePayment 兼容旧数据） */
  minLeasePayment: number
  initialDirectCosts: number      // 初始直接费用
  unguaranteedResidual: number    // 未担保余值
  leaseReceivable: number         // 应收融资租赁款（公式）
  presentValue: number            // 租赁投资净额/现值
  unrecognizedFinIncome: number   // 未确认融资收益（公式）
  pvFvRatio: number | null        // 现值/公允价值%（公式）
  allocRate: number               // 租赁内含利率(%)
  rateSolved: boolean             // 利率是否由 IRR 求解
  annualRent: number              // 各期租金（用于分配表）
  periodCount: number             // 分配期数
  periodInterest: number          // 本期确认融资收入
  principalRecovery: number       // 本期净投资减少额
  endBalance: number              // 期末租赁投资净额
  amortSchedule: FinanceLeaseAmortPeriod[]
  g5ProjectName: string           // 勾稽 G5 项目名
  g5BookNetInvestment: number     // G5 账面净投资（对照）
  g5BookUnearned: number          // G5 账面未确认收益（对照）
  isRelatedParty: string
  conclusion: string
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_18 = 'H1-18'
const ITEM_PREFIX_19 = 'H1-19'
const ITEM_PREFIX_20 = 'H1-20'

// ─── Formula helpers (exported for tests / UI tooltips) ──────────────────────

function toYmd(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 两日期间完整月数（按日历月近似，至少 0） */
export function calcLeaseMonths(start: string, end: string): number {
  if (!start || !end) return 0
  const s = new Date(start)
  const e = new Date(end)
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime()) || e < s) return 0
  return Math.max(0, (e.getFullYear() - s.getFullYear()) * 12 + (e.getMonth() - s.getMonth()) + 1)
}

/**
 * 租赁期间与指定会计年度的重叠月数（本年应计提月份数）。
 * 例：租期 2024-06-01~2026-05-31、年度 2025 → 12；年度 2024 → 7。
 */
export function calcMonthsInFiscalYear(start: string, end: string, year: number): number {
  if (!start || !end || !year) return 0
  const s = new Date(start)
  const e = new Date(end)
  if (Number.isNaN(s.getTime()) || Number.isNaN(e.getTime()) || e < s) return 0
  const yearStart = new Date(year, 0, 1)
  const yearEnd = new Date(year, 11, 31)
  const overlapStart = s > yearStart ? s : yearStart
  const overlapEnd = e < yearEnd ? e : yearEnd
  if (overlapEnd < overlapStart) return 0
  return Math.min(12, calcLeaseMonths(toYmd(overlapStart), toYmd(overlapEnd)))
}

/** 残值率统一为小数：5 → 0.05；已是 0~1 则原样 */
function toResidualDecimal(rate: number): number {
  if (!rate || rate <= 0) return 0
  return rate > 1 ? rate / 100 : rate
}

/**
 * 重算经营租出一行全部公式列。
 * 对齐致同 Excel：N/O/Q、S/U；并维护收益率分析列。
 */
export function recalcOperatingRow(row: OperatingLeaseRow, opts?: { fiscalYear?: number; fillMonthsIfEmpty?: boolean }): void {
  // 起止日 → 租赁期限
  const termFromDates = calcLeaseMonths(row.leaseStart, row.leaseEnd)
  if (termFromDates > 0) row.leaseTerm = termFromDates

  // 本年月份为空时，按租期与会计年度重叠推算
  if (opts?.fillMonthsIfEmpty && !(row.monthsThisYear > 0) && row.leaseStart && row.leaseEnd) {
    const y = opts.fiscalYear ?? new Date().getFullYear()
    const m = calcMonthsInFiscalYear(row.leaseStart, row.leaseEnd, y)
    if (m > 0) row.monthsThisYear = m
  }

  // 月折旧（防除零，对齐 Excel #DIV/0! 防护）
  const residual = toResidualDecimal(row.residualRate)
  row.monthlyDep = row.depYears > 0
    ? (row.originalCost * (1 - residual)) / row.depYears / 12
    : 0
  row.expectedDep = (row.monthsThisYear || 0) * row.monthlyDep
  row.depDiff = row.expectedDep - (row.bookedDep || 0)

  // 月租金：优先 合同总额÷期限；否则沿用已有月租金；再否则 年租金÷12
  if (row.contractAmount > 0 && row.leaseTerm > 0) {
    row.monthlyRent = row.contractAmount / row.leaseTerm
  } else if (!(row.monthlyRent > 0) && row.annualRent > 0) {
    row.monthlyRent = row.annualRent / 12
  }
  row.expectedRent = (row.monthsThisYear || 0) * (row.monthlyRent || 0)
  row.incomeDiff = row.expectedRent - (row.bookedRent || 0)

  // 年租金 / 总租金 / 年折旧分摊（收益率与附注联动）
  row.annualRent = (row.monthlyRent || 0) * 12
  row.totalRentIncome = row.contractAmount > 0
    ? row.contractAmount
    : (row.monthlyRent || 0) * (row.leaseTerm || 0)
  row.depAlloc = (row.monthlyDep || 0) * 12
  row.netIncome = row.annualRent - row.depAlloc - (row.maintenanceCost || 0)
  row.returnRate = row.originalCost > 0 ? (row.netIncome / row.originalCost) * 100 : 0
  row.rentDiff = row.annualRent - (row.marketRent || 0)
}

/** 将 H1-19 行映射为附注「经营租出」动态行 */
export function mapOperatingToDisclosureRows(rows: OperatingLeaseRow[]) {
  return rows.map((r, i) => ({
    rowId: `disc-ol-${r.rowId}`,
    name: r.assetName || `经营租出-${i + 1}`,
    amount: r.netValue > 0 ? r.netValue : Math.max(0, (r.originalCost || 0) - (r.accumDep || 0)),
    description: [
      r.lessee ? `承租方:${r.lessee}` : '',
      r.leaseStart && r.leaseEnd ? `租期:${r.leaseStart}~${r.leaseEnd}` : '',
      r.annualRent ? `年租金:${r.annualRent.toLocaleString('zh-CN')}` : '',
      r.contractIndex ? `索引:${r.contractIndex}` : '',
    ].filter(Boolean).join('；'),
    remark: '来源:H1-19',
  }))
}

/** 根据差异行生成审计说明草稿 */
export function buildOperatingLeaseNoteDraft(rows: OperatingLeaseRow[], fiscalYear?: number): string {
  const year = fiscalYear ?? new Date().getFullYear()
  const lines: string[] = [
    `检查范围：截至${year}年12月31日，经营租出固定资产共 ${rows.length} 项。`,
    '程序：获取租赁合同/协议，核对重要条款及经营租赁分类；按合同重算本期应计折旧（其他业务支出）与应计租金（其他业务收入），并与账面核对。',
  ]
  const depAbn = rows.filter((r) => Math.abs(r.depDiff) > 0.01)
  const rentAbn = rows.filter((r) => Math.abs(r.incomeDiff) > 0.01)
  const mktAbn = rows.filter((r) => {
    if (!(r.marketRent > 0)) return false
    return Math.abs((r.annualRent - r.marketRent) / r.marketRent * 100) > 20
  })
  if (depAbn.length === 0 && rentAbn.length === 0) {
    lines.push('本期应计折旧、应计租金与账面核对未见重大差异。')
  } else {
    if (depAbn.length) {
      lines.push(`折旧差异 ${depAbn.length} 项：`)
      for (const r of depAbn) {
        lines.push(`  · ${r.assetName || r.rowId}：应计 ${r.expectedDep.toFixed(2)}，账面 ${r.bookedDep.toFixed(2)}，差异 ${r.depDiff.toFixed(2)}`)
      }
    }
    if (rentAbn.length) {
      lines.push(`租金差异 ${rentAbn.length} 项：`)
      for (const r of rentAbn) {
        lines.push(`  · ${r.assetName || r.rowId}：应计 ${r.expectedRent.toFixed(2)}，账面 ${r.bookedRent.toFixed(2)}，差异 ${r.incomeDiff.toFixed(2)}`)
      }
    }
  }
  if (mktAbn.length) {
    lines.push(`市场租金偏离>20% 共 ${mktAbn.length} 项，已要求管理层说明定价依据。`)
  }
  const related = rows.filter((r) => r.isRelatedParty === 'Y')
  if (related.length) {
    lines.push(`其中关联方租赁 ${related.length} 项，已结合 H1-18 评价定价公允性。`)
  }
  lines.push('合同复印件索引见各行「合同索引号」。')
  return lines.join('\n')
}

function emptyOperatingRow(seq: number): OperatingLeaseRow {
  return {
    rowId: `ol-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    seq,
    assetName: '', assetCategory: '', specModel: '', lessee: '',
    leaseStart: '', leaseEnd: '', contractAmount: 0, monthsThisYear: 0,
    originalCost: 0, accumDep: 0, depYears: 0, residualRate: 0, netValue: 0,
    monthlyDep: 0, expectedDep: 0, bookedDep: 0, depDiff: 0,
    monthlyRent: 0, expectedRent: 0, bookedRent: 0, incomeDiff: 0,
    contractIndex: '', contractNo: '', deposit: 0,
    renewalTerms: '', earlyTermination: '',
    isRelatedParty: 'N', hasChanged: 'N', accountTreatment: '',
    leaseTerm: 0, annualRent: 0, totalRentIncome: 0, depAlloc: 0,
    maintenanceCost: 0, netIncome: 0, returnRate: 0, marketRent: 0, rentDiff: 0,
    conclusion: '', remark: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1LeaseCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  const relatedRows = ref<RelatedPartyRow[]>([])
  const operatingRows = ref<OperatingLeaseRow[]>([])
  const financeRows = ref<FinanceLeaseRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const relatedSettings = ref<H1RelatedPartySettings>(defaultRelatedPartySettings())

  function _loadData(): void {
    _loadArray(ITEM_PREFIX_18, relatedRows, _normalizeRelatedRow)
    _loadArray(ITEM_PREFIX_19, operatingRows, _normalizeOperatingRow)
    _loadArray(ITEM_PREFIX_20, financeRows, _normalizeFinanceRow)
    auditNote.value = _getString(`${ITEM_PREFIX_18}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX_18}-audit-conclusion`)
    const settingsRaw = allResponses.value.get(`${ITEM_PREFIX_18}-settings`)?.remark
    if (settingsRaw) {
      try {
        const p = JSON.parse(settingsRaw)
        relatedSettings.value = {
          priceDiffThreshold: Number(p.priceDiffThreshold) > 0
            ? Number(p.priceDiffThreshold)
            : DEFAULT_PRICE_DIFF_THRESHOLD,
          entryDiffThreshold: Number(p.entryDiffThreshold) > 0
            ? Number(p.entryDiffThreshold)
            : DEFAULT_ENTRY_DIFF_THRESHOLD,
          noTransaction: Boolean(p.noTransaction),
        }
      } catch { relatedSettings.value = defaultRelatedPartySettings() }
    } else {
      relatedSettings.value = defaultRelatedPartySettings()
    }
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
    const row = emptyRelatedPartyRow(raw.seq ?? idx + 1, raw.transType ?? '购入')
    row.rowId = raw.rowId ?? row.rowId
    row.counterparty = raw.counterparty ?? ''
    row.relationship = raw.relationship ?? ''
    row.assetCategory = raw.assetCategory ?? ''
    row.name = raw.name ?? ''
    row.transType = raw.transType ?? '购入'
    row.transAmount = Number(raw.transAmount ?? raw.purchasePrice ?? raw.salePrice) || 0
    row.bookValue = Number(raw.bookValue ?? raw.bookedValue) || 0
    row.depYears = Number(raw.depYears) || 0
    row.originalCost = Number(raw.originalCost) || 0
    row.accumDep = Number(raw.accumDep) || 0
    row.impairment = Number(raw.impairment) || 0
    row.transDate = raw.transDate ?? raw.purchaseDate ?? raw.saleDate ?? ''
    row.categoryTotal = raw.categoryTotal != null && raw.categoryTotal !== ''
      ? Number(raw.categoryTotal)
      : null
    row.similarRatio = raw.similarRatio != null && raw.similarRatio !== ''
      ? Number(raw.similarRatio)
      : null
    row.pricingPolicy = raw.pricingPolicy ?? raw.pricingBasis ?? ''
    row.pricingBasis = raw.pricingBasis ?? row.pricingPolicy
    row.hasAnomaly = raw.hasAnomaly ?? ''
    row.appraisedValue = Number(raw.appraisedValue) || 0
    row.isFair = raw.isFair ?? ''
    row.approvalDoc = raw.approvalDoc ?? ''
    row.conclusion = raw.conclusion ?? ''
    row.remark = raw.remark ?? ''
    row.indexRef = raw.indexRef ?? ''
    row.sourceWp = raw.sourceWp ?? ''
    row.sourceRowId = raw.sourceRowId ?? ''
    row.sourceFingerprint = raw.sourceFingerprint ?? ''
    row.assetNo = raw.assetNo ?? ''
    row.h10Gain = raw.h10Gain != null && raw.h10Gain !== '' ? Number(raw.h10Gain) : null
    if (row.transType === '出售' && !row.originalCost && row.bookValue > 0 && !row.accumDep && !row.impairment) {
      row.originalCost = row.bookValue
    }
    recalcRelatedPartyRow(row)
    return row
  }

  function _normalizeOperatingRow(raw: any, idx: number): OperatingLeaseRow {
    const row = emptyOperatingRow(raw.seq ?? idx + 1)
    row.rowId = raw.rowId ?? row.rowId
    row.assetName = raw.assetName ?? ''
    row.assetCategory = raw.assetCategory ?? ''
    row.specModel = raw.specModel ?? ''
    row.lessee = raw.lessee ?? ''
    row.leaseStart = raw.leaseStart ?? ''
    row.leaseEnd = raw.leaseEnd ?? ''
    row.contractAmount = Number(raw.contractAmount) || 0
    row.monthsThisYear = Number(raw.monthsThisYear) || 0
    row.originalCost = Number(raw.originalCost) || 0
    row.accumDep = Number(raw.accumDep) || 0
    row.depYears = Number(raw.depYears) || 0
    row.residualRate = Number(raw.residualRate) || 0
    row.netValue = Number(raw.netValue) || 0
    row.bookedDep = Number(raw.bookedDep) || 0
    row.bookedRent = Number(raw.bookedRent) || 0
    row.monthlyRent = Number(raw.monthlyRent) || 0
    row.contractIndex = raw.contractIndex ?? ''
    row.contractNo = raw.contractNo ?? ''
    row.deposit = Number(raw.deposit) || 0
    row.renewalTerms = raw.renewalTerms ?? ''
    row.earlyTermination = raw.earlyTermination ?? ''
    row.isRelatedParty = raw.isRelatedParty ?? 'N'
    row.hasChanged = raw.hasChanged ?? 'N'
    row.accountTreatment = raw.accountTreatment ?? ''
    row.leaseTerm = Number(raw.leaseTerm) || 0
    row.annualRent = Number(raw.annualRent) || 0
    row.maintenanceCost = Number(raw.maintenanceCost) || 0
    row.marketRent = Number(raw.marketRent) || 0
    row.conclusion = raw.conclusion ?? ''
    row.remark = raw.remark ?? ''
    // 兼容旧数据：仅有年租金时回填月租金
    if (!(row.monthlyRent > 0) && row.annualRent > 0) row.monthlyRent = row.annualRent / 12
    // 兼容旧数据：depAlloc 曾作手填折旧，映射为 bookedDep（若未填账面折旧）
    if (!(row.bookedDep > 0) && Number(raw.depAlloc) > 0 && raw.expectedDep == null && raw.bookedDep == null) {
      row.bookedDep = Number(raw.depAlloc) || 0
    }
    if (!(row.netValue > 0) && row.originalCost > 0) {
      row.netValue = Math.max(0, row.originalCost - row.accumDep)
    }
    recalcOperatingRow(row, { fillMonthsIfEmpty: true })
    return row
  }

  function _normalizeFinanceRow(raw: any, idx: number): FinanceLeaseRow {
    const minLease = Number(raw.minLeasePayment ?? raw.minLeaseReceipt) || 0
    const idc = Number(raw.initialDirectCosts) || 0
    const ug = Number(raw.unguaranteedResidual) || 0
    const pv = Number(raw.presentValue) || 0
    const fv = Number(raw.fairValue) || Number(raw.originalCost) || 0
    const rate = Number(raw.allocRate) || 0
    const annualRent = Number(raw.annualRent) || 0
    const periodCount = Number(raw.periodCount) || 0
    const leaseStart = String(raw.leaseStart ?? '')
    const startYear = leaseStart ? Number(leaseStart.slice(0, 4)) || undefined : undefined
    const schedule = Array.isArray(raw.amortSchedule) && raw.amortSchedule.length > 0
      ? raw.amortSchedule as FinanceLeaseAmortPeriod[]
      : (periodCount > 0 && (pv > 0 || annualRent > 0)
        ? buildFinanceLeaseAmortization({
          openingNetInvestment: pv,
          annualRent,
          implicitRatePct: rate,
          periodCount,
          startYear,
          unguaranteedResidual: ug,
        })
        : [])
    const first = schedule[0]
    return {
      rowId: raw.rowId ?? `fl-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      assetCode: raw.assetCode ?? '',
      assetName: raw.assetName ?? '',
      lessee: raw.lessee ?? '',
      leaseStart,
      contractIndex: raw.contractIndex ?? '',
      originalCost: Number(raw.originalCost) || 0,
      fairValue: fv,
      classificationBasis: raw.classificationBasis ?? '',
      classResult1: raw.classResult1 ?? '',
      classResult2: raw.classResult2 ?? '',
      classResult3: raw.classResult3 ?? '',
      classResult4: raw.classResult4 ?? '',
      classResult5: raw.classResult5 ?? '',
      minLeasePayment: minLease,
      initialDirectCosts: idc,
      unguaranteedResidual: ug,
      leaseReceivable: calcFinanceLeaseReceivable(minLease, idc),
      presentValue: pv,
      unrecognizedFinIncome: calcUnearnedFinanceIncome(minLease, pv, ug),
      pvFvRatio: calcPvToFvRatio(pv, fv),
      allocRate: rate,
      rateSolved: Boolean(raw.rateSolved),
      annualRent,
      periodCount,
      periodInterest: first?.financeIncome ?? (Number(raw.periodInterest) || 0),
      principalRecovery: first?.netDecrease ?? (Number(raw.principalRecovery) || 0),
      endBalance: schedule.length
        ? schedule[schedule.length - 1].netBalance
        : (Number(raw.endBalance) || 0),
      amortSchedule: schedule,
      g5ProjectName: raw.g5ProjectName ?? '',
      g5BookNetInvestment: Number(raw.g5BookNetInvestment) || 0,
      g5BookUnearned: Number(raw.g5BookUnearned) || 0,
      isRelatedParty: raw.isRelatedParty ?? 'N',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  /** 按实际利率法重算未确认融资收益分配表及相关衍生字段 */
  function _recalcFinanceDerived(row: FinanceLeaseRow): void {
    row.leaseReceivable = calcFinanceLeaseReceivable(row.minLeasePayment, row.initialDirectCosts)
    row.unrecognizedFinIncome = calcUnearnedFinanceIncome(
      row.minLeasePayment,
      row.presentValue,
      row.unguaranteedResidual,
    )
    row.pvFvRatio = calcPvToFvRatio(row.presentValue, row.fairValue || row.originalCost)
    const startYear = row.leaseStart ? Number(row.leaseStart.slice(0, 4)) || undefined : undefined
    if (row.periodCount > 0 && (row.presentValue > 0 || row.annualRent > 0)) {
      row.amortSchedule = buildFinanceLeaseAmortization({
        openingNetInvestment: row.presentValue,
        annualRent: row.annualRent,
        implicitRatePct: row.allocRate,
        periodCount: row.periodCount,
        startYear,
        unguaranteedResidual: row.unguaranteedResidual,
      })
      const first = row.amortSchedule[0]
      const last = row.amortSchedule[row.amortSchedule.length - 1]
      row.periodInterest = first?.financeIncome ?? 0
      row.principalRecovery = first?.netDecrease ?? 0
      row.endBalance = last?.netBalance ?? 0
    } else {
      row.amortSchedule = []
      row.periodInterest = Math.round(row.presentValue * (row.allocRate / 100) * 100) / 100
      row.principalRecovery = Math.round((row.annualRent - row.periodInterest) * 100) / 100
      row.endBalance = Math.round((row.presentValue - row.principalRecovery) * 100) / 100
    }
  }

  const unfairPricingRows = computed(() => {
    const th = relatedSettings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
    return relatedRows.value.filter((r) => Math.abs(r.priceDiffRate) > th)
  })

  /** 购入表（不含无偿调拨） */
  const purchaseRows = computed(() =>
    relatedRows.value.filter((r) => r.transType !== '出售' && r.transType !== '无偿调拨'),
  )

  /** 无偿调拨表 */
  const transferRows = computed(() =>
    relatedRows.value.filter((r) => r.transType === '无偿调拨'),
  )

  /** 出售表 */
  const saleRows = computed(() =>
    relatedRows.value.filter((r) => r.transType === '出售'),
  )

  const relatedSummary = computed(() => {
    const th = relatedSettings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
    const entryTh = relatedSettings.value.entryDiffThreshold || DEFAULT_ENTRY_DIFF_THRESHOLD
    const entryDiffRows = relatedRows.value.filter((r) =>
      (r.transType === '购入' || r.transType === '无偿调拨') && Math.abs(r.entryDiff) > 0.01,
    )
    const entryRemarkMissing = relatedRows.value.filter((r) => needsEntryDiffRemark(r, entryTh))
    const h10Mismatch = saleRows.value.filter((r) => r.h10Diff != null && Math.abs(r.h10Diff) > 0.01)
    const h7 = _safeParseRows(allResponses.value.get('H1-7-rows')?.remark)
    const h8 = _safeParseRows(allResponses.value.get('H1-8-rows')?.remark)
    const drifted = detectSourceDrift(relatedRows.value, h7, h8)
    const transTotal = calcSubtotal(relatedRows.value.map((r) => r.transAmount))
    return {
      count: relatedRows.value.length,
      purchaseCount: purchaseRows.value.length,
      transferCount: transferRows.value.length,
      saleCount: saleRows.value.length,
      purchaseTotal: calcSubtotal(purchaseRows.value.map((r) => r.transAmount)),
      saleTotal: calcSubtotal(saleRows.value.map((r) => r.transAmount)),
      transTotal,
      abnormalCount: unfairPricingRows.value.length,
      entryDiffCount: entryDiffRows.length,
      entryRemarkMissingCount: entryRemarkMissing.length,
      h10MismatchCount: h10Mismatch.length,
      sourceDriftCount: drifted.length,
      anomalyFlagCount: relatedRows.value.filter((r) =>
        r.hasAnomaly === '是' || r.hasAnomaly === 'Y' || r.hasAnomaly === '异常',
      ).length,
      priceDiffThreshold: th,
      entryDiffThreshold: entryTh,
      noTransaction: relatedSettings.value.noTransaction,
    }
  })

  const driftedSourceRows = computed(() => {
    const h7 = _safeParseRows(allResponses.value.get('H1-7-rows')?.remark)
    const h8 = _safeParseRows(allResponses.value.get('H1-8-rows')?.remark)
    return detectSourceDrift(relatedRows.value, h7, h8)
  })

  /** 经营租出汇总：核对差异 + 收益率 */
  const operatingSummary = computed(() => {
    const rows = operatingRows.value
    const n = rows.length
    return {
      count: n,
      totalContractAmount: calcSubtotal(rows.map((r) => r.contractAmount)),
      totalExpectedDep: calcSubtotal(rows.map((r) => r.expectedDep)),
      totalBookedDep: calcSubtotal(rows.map((r) => r.bookedDep)),
      totalDepDiff: calcSubtotal(rows.map((r) => r.depDiff)),
      totalExpectedRent: calcSubtotal(rows.map((r) => r.expectedRent)),
      totalBookedRent: calcSubtotal(rows.map((r) => r.bookedRent)),
      totalIncomeDiff: calcSubtotal(rows.map((r) => r.incomeDiff)),
      totalRent: calcSubtotal(rows.map((r) => r.totalRentIncome)),
      totalNetIncome: calcSubtotal(rows.map((r) => r.netIncome)),
      avgReturnRate: n > 0 ? calcSubtotal(rows.map((r) => r.returnRate)) / n : 0,
      abnormalDepCount: rows.filter((r) => Math.abs(r.depDiff) > 0.01).length,
      abnormalIncomeCount: rows.filter((r) => Math.abs(r.incomeDiff) > 0.01).length,
      marketDeviationCount: rows.filter((r) => {
        if (!(r.marketRent > 0)) return false
        return Math.abs((r.annualRent - r.marketRent) / r.marketRent * 100) > 20
      }).length,
    }
  })

  /** 融资租出汇总 */
  const financeSummary = computed(() => ({
    count: financeRows.value.length,
    financeCount: financeRows.value.filter((r) =>
      [r.classResult1, r.classResult2, r.classResult3, r.classResult4, r.classResult5].some((v) => v === 'Y'),
    ).length,
    totalMinLease: calcSubtotal(financeRows.value.map((r) => r.minLeasePayment)),
    totalReceivable: calcSubtotal(financeRows.value.map((r) => r.leaseReceivable)),
    totalUnearned: calcSubtotal(financeRows.value.map((r) => r.unrecognizedFinIncome)),
    totalNetInvestment: calcSubtotal(financeRows.value.map((r) => r.presentValue)),
    totalPeriodInterest: calcSubtotal(financeRows.value.map((r) => r.periodInterest)),
  }))

  function classifyFinanceLease(row: FinanceLeaseRow): '融资' | '经营' {
    const anyYes = [row.classResult1, row.classResult2, row.classResult3, row.classResult4, row.classResult5]
      .some((v) => v === 'Y')
    return anyYes ? '融资' : '经营'
  }

  function addRelatedRow(transType: string = '购入'): void {
    const newRow = emptyRelatedPartyRow(relatedRows.value.length + 1, transType)
    relatedRows.value.push(newRow)
    _persistRelated()
  }

  function addOperatingRow(): void {
    const newRow = emptyOperatingRow(operatingRows.value.length + 1)
    operatingRows.value.push(newRow)
    _persistOperating()
  }

  function addFinanceRow(): void {
    const newRow: FinanceLeaseRow = {
      rowId: `fl-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: financeRows.value.length + 1,
      assetCode: '', assetName: '', lessee: '', leaseStart: '', contractIndex: '',
      originalCost: 0, fairValue: 0, classificationBasis: '',
      classResult1: '', classResult2: '', classResult3: '', classResult4: '', classResult5: '',
      minLeasePayment: 0, initialDirectCosts: 0, unguaranteedResidual: 0, leaseReceivable: 0,
      presentValue: 0, unrecognizedFinIncome: 0, pvFvRatio: null,
      allocRate: 0, rateSolved: false, annualRent: 0, periodCount: 0,
      periodInterest: 0, principalRecovery: 0, endBalance: 0,
      amortSchedule: [],
      g5ProjectName: '', g5BookNetInvestment: 0, g5BookUnearned: 0,
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
    if (field === 'pricingPolicy') row.pricingBasis = String(value ?? '')
    if (field === 'pricingBasis') row.pricingPolicy = String(value ?? '')
    recalcRelatedPartyRow(row)
    _persistRelated()
  }

  function updateOperatingCell(rowId: string, field: keyof OperatingLeaseRow, value: any): void {
    const row = operatingRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 手改原值/累计折旧时同步净值（除非用户正在改净值本身）
    if (field === 'originalCost' || field === 'accumDep') {
      row.netValue = Math.max(0, (row.originalCost || 0) - (row.accumDep || 0))
    }
    // 起止日变更时按会计年度重叠重算本年月份
    if (field === 'leaseStart' || field === 'leaseEnd') {
      const y = new Date().getFullYear()
      const m = calcMonthsInFiscalYear(row.leaseStart, row.leaseEnd, y)
      if (m > 0) row.monthsThisYear = m
    }
    recalcOperatingRow(row)
    _persistOperating()
  }

  function updateFinanceCell(rowId: string, field: keyof FinanceLeaseRow, value: any): void {
    const row = financeRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'allocRate') row.rateSolved = false
    if ((field === 'fairValue' || field === 'initialDirectCosts') && !(row.presentValue > 0)) {
      row.presentValue = (row.fairValue || 0) + (row.initialDirectCosts || 0)
    }
    _recalcFinanceDerived(row)
    if ((field === 'presentValue' || field === 'fairValue' || field === 'originalCost')
      && row.pvFvRatio != null && row.pvFvRatio >= 90 && !row.classResult4) {
      row.classResult4 = 'Y'
    }
    _persistFinance()
  }

  /** 按合同参数重建分配表（期数/租金/利率/净投资变更后调用） */
  function rebuildAmortSchedule(rowId: string): void {
    const row = financeRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    _recalcFinanceDerived(row)
    _persistFinance()
  }

  // ─── 行级合同 OCR 回填（复用 /d4/contract-ocr 通用字段，仅填空）──────────────
  // 通用字段：counterparty/contractNo/signDate/serviceContent/contractAmount

  function _fillStr(row: any, field: string, val: any, filled: string[], overwrite: boolean): void {
    if (val == null || String(val).trim() === '') return
    if (!overwrite && String(row[field] || '').trim()) return
    row[field] = String(val).trim()
    filled.push(field)
  }

  function _fillNum(row: any, field: string, val: any, filled: string[], overwrite: boolean): void {
    const n = Number(val)
    if (!Number.isFinite(n) || n <= 0) return
    if (!overwrite && Number(row[field]) > 0) return
    row[field] = n
    filled.push(field)
  }

  /** H1-18 关联交易合同 OCR 回填 */
  function applyRelatedPartyOcr(rowId: string, ocr: Record<string, any>, opts?: { overwrite?: boolean }): string[] {
    const row = relatedRows.value.find((r) => r.rowId === rowId)
    if (!row) return []
    const ow = opts?.overwrite === true
    const filled: string[] = []
    _fillStr(row, 'counterparty', ocr.counterparty, filled, ow)
    _fillStr(row, 'name', ocr.serviceContent, filled, ow)
    _fillStr(row, 'transDate', ocr.signDate, filled, ow)
    _fillStr(row, 'indexRef', ocr.contractNo, filled, ow)
    _fillNum(row, 'transAmount', ocr.contractAmount, filled, ow)
    if (ocr.attachment_id && !(row.remark || '').includes('OCR:')) {
      row.remark = [row.remark, `OCR:${String(ocr.attachment_id).slice(0, 8)}`].filter(Boolean).join('；')
      filled.push('remark')
    }
    if (filled.length) { recalcRelatedPartyRow(row); _persistRelated() }
    return filled
  }

  /** H1-19 经营租出合同 OCR 回填 */
  function applyOperatingLeaseOcr(rowId: string, ocr: Record<string, any>, opts?: { overwrite?: boolean }): string[] {
    const row = operatingRows.value.find((r) => r.rowId === rowId)
    if (!row) return []
    const ow = opts?.overwrite === true
    const filled: string[] = []
    _fillStr(row, 'lessee', ocr.counterparty, filled, ow)
    _fillStr(row, 'assetName', ocr.serviceContent, filled, ow)
    _fillStr(row, 'leaseStart', ocr.signDate, filled, ow)
    _fillStr(row, 'contractNo', ocr.contractNo, filled, ow)
    _fillNum(row, 'contractAmount', ocr.contractAmount, filled, ow)
    if (ocr.attachment_id && !(row.contractIndex || '').trim()) {
      row.contractIndex = `OCR:${String(ocr.attachment_id).slice(0, 8)}`
      filled.push('contractIndex')
    }
    if (filled.length) { recalcOperatingRow(row); _persistOperating() }
    return filled
  }

  /** H1-20 融资租出合同 OCR 回填 */
  function applyFinanceLeaseOcr(rowId: string, ocr: Record<string, any>, opts?: { overwrite?: boolean }): string[] {
    const row = financeRows.value.find((r) => r.rowId === rowId)
    if (!row) return []
    const ow = opts?.overwrite === true
    const filled: string[] = []
    _fillStr(row, 'lessee', ocr.counterparty, filled, ow)
    _fillStr(row, 'assetName', ocr.serviceContent, filled, ow)
    _fillStr(row, 'leaseStart', ocr.signDate, filled, ow)
    _fillStr(row, 'contractIndex', ocr.contractNo, filled, ow)
    if (filled.length) { _recalcFinanceDerived(row); _persistFinance() }
    return filled
  }

  /**
   * IRR 求解内含利率并回填。
   * 净投资优先取 presentValue；若为空则用 fairValue+initialDirectCosts。
   */
  function solveImplicitRate(rowId: string): number | null {
    const row = financeRows.value.find((r) => r.rowId === rowId)
    if (!row) return null
    const net = row.presentValue > 0
      ? row.presentValue
      : (row.fairValue || 0) + (row.initialDirectCosts || 0)
    if (net > 0 && !(row.presentValue > 0)) row.presentValue = net
    const rate = solveLeaseImplicitRatePct({
      netInvestment: net,
      annualRent: row.annualRent,
      periodCount: row.periodCount,
      unguaranteedResidual: row.unguaranteedResidual,
    })
    if (rate == null) return null
    row.allocRate = rate
    row.rateSolved = true
    _recalcFinanceDerived(row)
    _persistFinance()
    return rate
  }

  /** 从 G5 种子带入（同名+承租人已存在则跳过） */
  function importFromG5Seeds(seeds: H1FinanceLeaseG5Seed[]): number {
    if (!seeds.length) return 0
    const existing = new Set(
      financeRows.value.map((r) => `${r.lessee.trim()}|${(r.g5ProjectName || r.assetName).trim()}`.toLowerCase()),
    )
    let added = 0
    for (const s of seeds) {
      const key = `${s.lessee.trim()}|${s.g5ProjectName.trim()}`.toLowerCase()
      if (existing.has(key)) continue
      const row: FinanceLeaseRow = {
        rowId: `fl-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        seq: financeRows.value.length + 1,
        assetCode: '',
        assetName: s.assetName,
        lessee: s.lessee,
        leaseStart: s.leaseStart,
        contractIndex: '',
        originalCost: s.fairValue,
        fairValue: s.fairValue,
        classificationBasis: '',
        classResult1: '', classResult2: '', classResult3: '', classResult4: '', classResult5: '',
        minLeasePayment: s.minLeasePayment,
        initialDirectCosts: s.initialDirectCosts,
        unguaranteedResidual: s.unguaranteedResidual,
        leaseReceivable: 0,
        presentValue: s.presentValue,
        unrecognizedFinIncome: 0,
        pvFvRatio: null,
        allocRate: s.allocRate,
        rateSolved: false,
        annualRent: s.annualRent,
        periodCount: s.periodCount,
        periodInterest: 0,
        principalRecovery: 0,
        endBalance: 0,
        amortSchedule: [],
        g5ProjectName: s.g5ProjectName,
        g5BookNetInvestment: s.g5BookNetInvestment,
        g5BookUnearned: s.g5BookUnearned,
        isRelatedParty: 'N',
        conclusion: '',
        remark: s.remark,
      }
      if (s.presentValue > 0 && s.fairValue > 0 && s.presentValue / s.fairValue >= 0.9) {
        row.classResult4 = 'Y'
      }
      _recalcFinanceDerived(row)
      financeRows.value.push(row)
      existing.add(key)
      added += 1
    }
    if (added) _persistFinance()
    return added
  }

  /** 按租期与会计年度重叠，批量重算「本年月份」并刷新公式 */
  function fillMonthsThisYear(fiscalYear?: number): number {
    const y = fiscalYear ?? new Date().getFullYear()
    let updated = 0
    for (const row of operatingRows.value) {
      const m = calcMonthsInFiscalYear(row.leaseStart, row.leaseEnd, y)
      if (m > 0) {
        row.monthsThisYear = m
        recalcOperatingRow(row)
        updated++
      }
    }
    if (updated) _persistOperating()
    return updated
  }

  /** 将经营租出清单同步至上市附注「经营租出」子节（只写新键；旧键仅 hydrate 读取） */
  function syncOperatingToDisclosure(): number {
    const discRows = mapOperatingToDisclosureRows(operatingRows.value)
    options?.onSave?.(
      'H1-listed-lease-rows',
      discRows.map((r) => ({
        rowId: r.rowId,
        name: r.name,
        bookValue: r.amount,
        isPreset: false,
      })),
    )
    return discRows.length
  }

  function _persistRelatedSettings(): void {
    options?.onSave?.(`${ITEM_PREFIX_18}-settings`, relatedSettings.value)
  }

  function updateRelatedSettings(patch: Partial<H1RelatedPartySettings>): void {
    relatedSettings.value = { ...relatedSettings.value, ...patch }
    if (!(relatedSettings.value.priceDiffThreshold > 0)) {
      relatedSettings.value.priceDiffThreshold = DEFAULT_PRICE_DIFF_THRESHOLD
    }
    if (!(relatedSettings.value.entryDiffThreshold > 0)) {
      relatedSettings.value.entryDiffThreshold = DEFAULT_ENTRY_DIFF_THRESHOLD
    }
    _persistRelatedSettings()
  }

  /** 从 H1-7/H1-8 带入；返回合并范围内关系候选供 UI 确认 */
  function importFromH7H8(): {
    added: number
    skipped: number
    inScopeCandidates: RelatedPartyRow[]
  } {
    const existing = new Set(
      relatedRows.value.filter((r) => r.sourceRowId).map((r) => `${r.sourceWp}:${r.sourceRowId}`),
    )
    let added = 0
    let skipped = 0
    const inScopeCandidates: RelatedPartyRow[] = []

    const add7 = _safeParseRows(allResponses.value.get('H1-7-rows')?.remark)
      .filter((r) => r.isRelatedParty === 'Y' || r.isRelatedParty === '是')
    for (const src of add7) {
      const key = `H1-7:${src.rowId}`
      if (existing.has(key)) { skipped++; continue }
      const row = emptyRelatedPartyRow(relatedRows.value.length + 1, '购入')
      applyH7SourceToRow(row, src)
      relatedRows.value.push(row)
      existing.add(key)
      added++
      if (isLikelyInConsolidationScope(row.relationship)) inScopeCandidates.push(row)
    }

    const add8 = _safeParseRows(allResponses.value.get('H1-8-rows')?.remark)
      .filter((r) => r.isRelatedParty === 'Y' || r.isRelatedParty === '是')
    for (const src of add8) {
      const key = `H1-8:${src.rowId}`
      if (existing.has(key)) { skipped++; continue }
      const row = emptyRelatedPartyRow(relatedRows.value.length + 1, '出售')
      applyH8SourceToRow(row, src)
      relatedRows.value.push(row)
      existing.add(key)
      added++
      if (isLikelyInConsolidationScope(row.relationship)) inScopeCandidates.push(row)
    }

    if (added) {
      relatedRows.value.forEach((r, i) => { r.seq = i + 1 })
      relatedSettings.value.noTransaction = false
      _persistRelatedSettings()
      _persistRelated()
    }
    return { added, skipped, inScopeCandidates }
  }

  /** 按源指纹刷新已漂移行；不传 rowIds 则刷新全部漂移行 */
  function refreshDriftedFromSource(rowIds?: string[]): { refreshed: number; missing: number } {
    const h7 = _safeParseRows(allResponses.value.get('H1-7-rows')?.remark)
    const h8 = _safeParseRows(allResponses.value.get('H1-8-rows')?.remark)
    const targets = rowIds?.length
      ? relatedRows.value.filter((r) => rowIds.includes(r.rowId))
      : detectSourceDrift(relatedRows.value, h7, h8)
    let refreshed = 0
    let missing = 0
    for (const row of targets) {
      if (row.sourceWp === 'H1-7') {
        const src = h7.find((r) => r.rowId === row.sourceRowId)
        if (!src) { missing++; continue }
        applyH7SourceToRow(row, src)
        refreshed++
      } else if (row.sourceWp === 'H1-8') {
        const src = h8.find((r) => r.rowId === row.sourceRowId)
        if (!src) { missing++; continue }
        applyH8SourceToRow(row, src)
        refreshed++
      }
    }
    if (refreshed) _persistRelated()
    return { refreshed, missing }
  }

  /** 按本表同方向+同资产类别合计重算「同类总额」与占比 */
  function recalcSimilarRatios(): number {
    const groups = new Map<string, number>()
    for (const r of relatedRows.value) {
      const key = `${r.transType}|${r.assetCategory || '未分类'}`
      groups.set(key, (groups.get(key) || 0) + (r.transAmount || 0))
    }
    let n = 0
    for (const r of relatedRows.value) {
      const key = `${r.transType}|${r.assetCategory || '未分类'}`
      const total = groups.get(key) || 0
      r.categoryTotal = total > 0 ? total : null
      recalcRelatedPartyRow(r)
      n++
    }
    if (n) _persistRelated()
    return n
  }

  /** 从 H1-2 明细按类别取本期购入/处置总额填入 categoryTotal */
  function fillCategoryTotalsFromH12(): number {
    const details = _safeParseRows(allResponses.value.get('H1-2-rows')?.remark)
    const n = fillCategoryTotalsFromDetail(relatedRows.value, details)
    if (n) _persistRelated()
    return n
  }

  /** 与 H10 处置损益勾稽（sourceRowRef / assetNo / 唯一名称）
   * @param externalH10Rows 跨 WP 拉取的 H10 明细；缺省时回退读本底稿 Map（通常为空）
   */
  function syncH10CrossCheck(externalH10Rows?: any[]): { matched: number; mismatch: number; unmatched: number } {
    const fromMap = _safeParseRows(allResponses.value.get('H10-detail-rows')?.remark)
    const source = Array.isArray(externalH10Rows) && externalH10Rows.length
      ? externalH10Rows
      : fromMap
    const h10 = source.filter(
      (r: any) => !r.sourceWp || r.sourceWp === 'H1' || String(r.sourceIndex || '').includes('H1'),
    )
    let matched = 0
    let mismatch = 0
    let unmatched = 0
    for (const row of relatedRows.value) {
      if (row.transType !== '出售') {
        row.h10Gain = null
        row.h10Diff = null
        continue
      }
      const hit = matchH10Detail(row, h10)
      if (hit) {
        row.h10Gain = Number(hit.disposalGainLoss) || 0
        matched++
      } else {
        row.h10Gain = null
        unmatched++
      }
      recalcRelatedPartyRow(row)
      if (row.h10Diff != null && Math.abs(row.h10Diff) > 0.01) mismatch++
    }
    _persistRelated()
    return { matched, mismatch, unmatched }
  }

  function buildAdjSuggestionAndPersist(): string {
    const draft = buildAdjustmentSuggestionDraft(
      relatedRows.value,
      relatedSettings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD,
      relatedSettings.value.entryDiffThreshold || DEFAULT_ENTRY_DIFF_THRESHOLD,
    )
    options?.onSave?.(`${ITEM_PREFIX_18}-adj-draft`, draft)
    return draft
  }

  function getA7Reconcile(a7Total: number | null | undefined): A7ReconcileResult {
    const total = calcSubtotal(relatedRows.value.map((r) => r.transAmount))
    return reconcileA7Disclosure(total, a7Total)
  }

  /** 一键「本期无合并范围外关联方固定资产购销」 */
  function applyNoTransaction(): { note: string; conclusion: string } {
    relatedSettings.value.noTransaction = true
    _persistRelatedSettings()
    const note = '经核查关联方清单、固定资产增减明细及合并范围，本期不存在与合并范围外关联方的固定资产购入、出售或无偿调拨交易。'
    const conclusion = '本期无合并范围外关联方固定资产购销交易，相关认定检查不适用；关联方披露范围已交叉核对，未见漏报迹象。'
    saveNote(note)
    saveConclusion(conclusion)
    return { note, conclusion }
  }

  /** 异常行审计说明草稿（可交 AI 事件二次润色） */
  function buildRelatedPartyNoteDraft(): string {
    const th = relatedSettings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
    if (relatedSettings.value.noTransaction && relatedRows.value.length === 0) {
      return '经核查，本期无合并范围外关联方固定资产购销交易。'
    }
    const lines: string[] = [
      `检查范围：合并范围外关联方固定资产交易共 ${relatedRows.value.length} 笔（购入 ${purchaseRows.value.length} / 无偿调拨 ${transferRows.value.length} / 出售 ${saleRows.value.length}）。`,
      `程序：核对合同/发票/审批；评价定价政策；以公允/评估价值测算差异率（阈值 ${th}%）；出售净值=原值−累计折旧−减值，并与 H10 处置损益勾稽。`,
    ]
    const unfair = unfairPricingRows.value
    if (unfair.length) {
      lines.push(`价格差异率超过 ${th}% 共 ${unfair.length} 笔：`)
      for (const r of unfair.slice(0, 8)) {
        lines.push(`  · [${r.transType}] ${r.counterparty || '-'} / ${r.name || '-'}：差异率 ${r.priceDiffRate.toFixed(1)}%，定价：${r.pricingPolicy || r.pricingBasis || '-'}`)
      }
    } else {
      lines.push(`未见价格差异率超过 ${th}% 的交易。`)
    }
    const entryAbn = relatedRows.value.filter((r) => Math.abs(r.entryDiff) > 0.01)
    if (entryAbn.length) {
      lines.push(`购入/调拨入账价值与价款差异 ${entryAbn.length} 笔，已核对税费/运杂费等构成。`)
    }
    const h10m = saleRows.value.filter((r) => r.h10Diff != null && Math.abs(r.h10Diff) > 0.01)
    if (h10m.length) {
      lines.push(`与 H10 处置损益不一致 ${h10m.length} 笔，需进一步核对处置费用/税费。`)
    }
    return lines.join('\n')
  }

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

  watch(allResponses, () => _loadData(), { immediate: true })

  return {
    relatedRows,
    operatingRows,
    financeRows,
    auditNote,
    auditConclusion,
    relatedSettings,
    unfairPricingRows,
    purchaseRows,
    transferRows,
    saleRows,
    relatedSummary,
    operatingSummary,
    financeSummary,
    addRelatedRow,
    addOperatingRow,
    addFinanceRow,
    removeRow,
    updateRelatedCell,
    updateOperatingCell,
    updateFinanceCell,
    applyRelatedPartyOcr,
    applyOperatingLeaseOcr,
    applyFinanceLeaseOcr,
    rebuildAmortSchedule,
    solveImplicitRate,
    importFromG5Seeds,
    classifyFinanceLease,
    fillMonthsThisYear,
    syncOperatingToDisclosure,
    importFromH7H8,
    refreshDriftedFromSource,
    recalcSimilarRatios,
    fillCategoryTotalsFromH12,
    syncH10CrossCheck,
    applyNoTransaction,
    buildRelatedPartyNoteDraft,
    buildAdjSuggestionAndPersist,
    getA7Reconcile,
    updateRelatedSettings,
    driftedSourceRows,
    saveNote,
    saveConclusion,
  }
}

export default useH1LeaseCheck
