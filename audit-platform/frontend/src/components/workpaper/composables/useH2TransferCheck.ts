/**
 * useH2TransferCheck — H2-5 转固时点检查 composable
 *
 * 对齐致同模板双向检查逻辑：
 * - 表一（CIP挂账）：重大在建工程是否已达预定可使用状态仍未转固
 * - 表二（已转固）：本期重大转固时点是否与验收/投产实质一致（CAS4五条件）
 *
 * 保留：延迟天数、异常高亮、与 H2-2/H1 交叉验证与联动
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Requirements: 6.1-6.10
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import http from '@/utils/http'
import { calcTransferCondition, calcOverdueDays, calcSubtotal, calcCompletionRate } from './useH2FormulaEngine'
import { calcStraightLine, calcMonthsDepreciated } from './useH1DepreciationEngine'
import {
  pullH1CipAdditionsForH2,
  matchH1AmountByName,
  buildH2H1TransferReconcile,
  type H1CipAddition,
  type H2H1TransferReconcile,
} from './h2H1TransferPull'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 表一：期末仍挂列在建工程的重大项目（防延迟转固） */
export interface H2CipPendingRow {
  rowId: string
  /** 工程项目名称及设备 */
  name: string
  /** 在建工程期末原值 */
  cipOriginal: number
  /** 其中：累计利息资本化 */
  capitalizedInterest: number
  /** 减值准备 */
  impairment: number
  /** 净值（公式） */
  cipNet: number
  /** 总预算 */
  budget: number
  /** 累计投入占预算比例%（公式） */
  budgetRatio: number | null
  /** 合同规定/预计完工到货时间 */
  plannedReadyDate: string
  /** 开工/供货时间 */
  startDate: string
  /** 达到预定可使用状态的判断标准 */
  readyCriteria: string
  /** 是否已达预定可使用状态或在用 */
  readyForUse: boolean | null
  /** 达到预定可使用状态的时间 */
  readyDate: string
  /** 未转固原因 */
  notTransferReason: string
  /** 拟转固比例% */
  proposedTransferPct: number | null
  /** 期后转固情况（可自动拉取凭证摘要） */
  postPeriodTransfer: string
  /** 期后凭证号（分号分隔，便于追溯） */
  postPeriodVoucherNos: string
  /** 预计使用年限（年），用于少计折旧测算 */
  usefulLifeYears: number
  /** 残值率%（如 5 表示 5%） */
  salvageRatePct: number
  /** 少计折旧月数（公式） */
  missedDepMonths: number
  /** 少计折旧金额（公式） */
  missedDepAmount: number
  /** 是否存在异常（公式倾向） */
  isAbnormal: boolean
  remark: string
}

/** 表二：本期已转固重大项目（时点合理性） */
export interface H2TransferRow {
  rowId: string
  name: string
  /** 固定资产期末原值 */
  faOriginal: number
  /** 累计折旧 */
  faAccumDep: number
  /** 减值准备 */
  faImpairment: number
  /** 净值（公式） */
  faNet: number
  /** 转固日期 */
  transferDate: string
  /** 转固金额 */
  transferAmount: number
  /** 转入资产类别 */
  assetCategory: string
  /** 竣工验收日期 */
  acceptanceDate: string
  /** 决算/验收金额 */
  acceptanceAmount: number
  /** 达到预定可使用状态的自评价标准 */
  readyCriteria: string
  /** 试生产日期 */
  trialProductionDate: string
  /** 正式投产日期 */
  officialProductionDate: string
  /** 达到可用状态日（用于延迟计算，优先正式投产/试生产/验收） */
  conditionsMetDate: string
  /** CAS4 五条件 */
  condition1: boolean
  condition2: boolean
  condition3: boolean
  condition4: boolean
  condition5: boolean
  allConditionsMet: boolean
  timelyTransfer: boolean | null
  delayDays: number
  /** 对应 H1 资产 */
  h1Asset: string
  /** H1 入账金额 */
  h1Amount: number
  /** 差异（公式：转固金额 - H1入账） */
  difference: number
  /** 预计使用年限（年） */
  usefulLifeYears: number
  /** 残值率% */
  salvageRatePct: number
  /** 少计折旧月数（公式） */
  missedDepMonths: number
  /** 少计折旧金额（公式） */
  missedDepAmount: number
  /** 是否存在异常 */
  isAbnormal: boolean | null
  remark: string
}

/** 期后凭证命中（供匹配/单测） */
export interface H2PostPeriodVoucherHit {
  voucherDate: string
  voucherNo: string
  summary: string
  amount: number
  accountCode: string
}

export interface H2MissedDepResult {
  monthly: number
  months: number
  amount: number
}

export type TransferHighlight =
  | 'red-not-transferred'
  | 'yellow-delay'
  | 'red-amount-diff'
  | 'red-cip-ready'
  | null

// ─── Constants ───────────────────────────────────────────────────────────────

const CIP_ROWS_KEY = 'H2-5-cip-rows'
const ROWS_KEY = 'H2-5-rows'
const NOTE_KEY = 'H2-5-audit-note'
const CONCLUSION_KEY = 'H2-5-audit-conclusion'
const H23_ROWS_KEY = 'H2-3-rows'
const H213_ROWS_KEY = 'H2-13-rows'
export const H25_AJE_MARKER = 'H2-5-aje-auto'
const DELAY_THRESHOLD_DAYS = 30
const DEFAULT_USEFUL_LIFE_YEARS = 10
const DEFAULT_SALVAGE_RATE_PCT = 5
const POST_PERIOD_KEYWORDS = ['转固', '转入固定资产', '在建工程转', '竣工结转']

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _num(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function _normName(s: string): string {
  return String(s || '').replace(/\s+/g, '').toLowerCase()
}

function _nameMatch(a: string, b: string): boolean {
  const na = _normName(a)
  const nb = _normName(b)
  if (!na || !nb) return false
  return na === nb || na.includes(nb) || nb.includes(na)
}

/** 报表截止日默认：指定年 12-31；无年则当年 */
export function defaultPeriodEndDate(year?: number): string {
  const y = year && year > 1900 ? year : new Date().getFullYear()
  return `${y}-12-31`
}

/** 期后窗口：截止日次日起 N 个月 */
export function postPeriodDateRange(periodEnd: string, monthsAfter = 3): { dateFrom: string; dateTo: string; year: number } {
  const end = new Date(periodEnd)
  const from = new Date(end.getFullYear(), end.getMonth(), end.getDate() + 1)
  const to = new Date(from.getFullYear(), from.getMonth() + monthsAfter, from.getDate())
  const pad = (n: number) => String(n).padStart(2, '0')
  const fmt = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  return { dateFrom: fmt(from), dateTo: fmt(to), year: from.getFullYear() }
}

/** 按类别给出默认折旧政策 */
export function resolveDepPolicy(assetCategory?: string): { usefulLifeYears: number; salvageRatePct: number } {
  const cat = String(assetCategory || '')
  if (/房屋|建筑|构筑/.test(cat)) return { usefulLifeYears: 20, salvageRatePct: 5 }
  if (/运输|车辆|汽车/.test(cat)) return { usefulLifeYears: 5, salvageRatePct: 5 }
  if (/办公|电子|电脑/.test(cat)) return { usefulLifeYears: 5, salvageRatePct: 5 }
  if (/机器|设备|产线|装置/.test(cat)) return { usefulLifeYears: 10, salvageRatePct: 5 }
  return { usefulLifeYears: DEFAULT_USEFUL_LIFE_YEARS, salvageRatePct: DEFAULT_SALVAGE_RATE_PCT }
}

/**
 * 少计折旧测算：自达到预定可使用状态次月起，至 asOf 应提而未提的直线法折旧。
 * salvageRatePct 为百分比（5 = 5%）。
 */
export function calcMissedDepreciation(opts: {
  cost: number
  salvageRatePct: number
  usefulLifeYears: number
  readyDate: string
  asOfDate: string
}): H2MissedDepResult {
  const cost = _num(opts.cost)
  const life = _num(opts.usefulLifeYears)
  const salvage = _num(opts.salvageRatePct) / 100
  if (cost <= 0 || life <= 0 || !opts.readyDate || !opts.asOfDate) {
    return { monthly: 0, months: 0, amount: 0 }
  }
  const monthly = calcStraightLine(cost, salvage, life)
  const lifeMonths = Math.max(Math.round(life * 12), 0)
  const months = calcMonthsDepreciated(opts.readyDate, opts.asOfDate, lifeMonths)
  const amount = Math.round(monthly * months * 100) / 100
  return { monthly, months, amount }
}

/** 判断序时账分录是否与工程名称/转固关键词匹配 */
export function matchPostPeriodEntry(
  entry: { summary?: string; voucherNo?: string },
  projectName: string,
): boolean {
  const summary = String(entry.summary ?? '')
  if (!summary && !entry.voucherNo) return false
  if (projectName && _nameMatch(summary, projectName)) return true
  return POST_PERIOD_KEYWORDS.some(k => summary.includes(k))
}

export function formatPostPeriodHits(hits: H2PostPeriodVoucherHit[]): { text: string; voucherNos: string } {
  if (!hits.length) return { text: '', voucherNos: '' }
  const text = hits.map(h => {
    const amt = h.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    return `${h.voucherDate} ${h.voucherNo} ${h.summary || '转固'} ${amt}`.trim()
  }).join('；')
  const voucherNos = [...new Set(hits.map(h => h.voucherNo).filter(Boolean))].join(';')
  return { text, voucherNos }
}

/**
 * 将 H2-13 达可用行合并写入 CIP 挂账表（纯函数，供 H2-5 / H2-13 共用）。
 * readyForUse==='是' 的盘点行 → 更新已有挂账或新增。
 */
export function mergeH213ReadyIntoCipRows(
  cipRows: H2CipPendingRow[],
  h213Rows: any[],
): { rows: H2CipPendingRow[]; updated: number; added: number } {
  const ready = (h213Rows || []).filter((r: any) =>
    r.readyForUse === '是' || r.readyForUse === true || r.readyForUse === 'true',
  )
  if (!ready.length) return { rows: cipRows, updated: 0, added: 0 }

  const next: H2CipPendingRow[] = cipRows.map(r => ({
    ...r,
    postPeriodVoucherNos: r.postPeriodVoucherNos ?? '',
    usefulLifeYears: r.usefulLifeYears || DEFAULT_USEFUL_LIFE_YEARS,
    salvageRatePct: r.salvageRatePct || DEFAULT_SALVAGE_RATE_PCT,
    missedDepMonths: r.missedDepMonths ?? 0,
    missedDepAmount: r.missedDepAmount ?? 0,
  }))
  let updated = 0
  let added = 0

  for (const s of ready) {
    const name = String(s.projectName ?? s.name ?? '').trim()
    if (!name) continue
    const book = _num(s.bookAmount ?? s.bookValue ?? s.carryingAmount)
    const hit = next.find(r => _nameMatch(r.name, name))
    if (hit) {
      let changed = false
      if (hit.readyForUse !== true) {
        hit.readyForUse = true
        changed = true
      }
      if (!hit.readyCriteria) {
        hit.readyCriteria = 'H2-13 现场判断已达预定可使用状态'
        changed = true
      }
      if (!hit.remark?.includes('H2-13')) {
        hit.remark = [hit.remark, '来源:H2-13达可用'].filter(Boolean).join('；')
        changed = true
      }
      if (book > 0 && hit.cipOriginal <= 0) {
        hit.cipOriginal = book
        changed = true
      }
      const hasReason = !!(hit.notTransferReason?.trim() || hit.postPeriodTransfer?.trim())
      hit.cipNet = hit.cipOriginal - hit.impairment
      hit.budgetRatio = calcCompletionRate(hit.cipOriginal, hit.budget)
      hit.isAbnormal = hit.readyForUse === true && !hasReason
      if (changed) updated++
    } else {
      const row: H2CipPendingRow = {
        rowId: _newId('cip'),
        name,
        cipOriginal: book,
        capitalizedInterest: 0,
        impairment: 0,
        cipNet: book,
        budget: 0,
        budgetRatio: null,
        plannedReadyDate: '',
        startDate: '',
        readyCriteria: 'H2-13 现场判断已达预定可使用状态',
        readyForUse: true,
        readyDate: '',
        notTransferReason: '',
        proposedTransferPct: null,
        postPeriodTransfer: '',
        postPeriodVoucherNos: '',
        usefulLifeYears: DEFAULT_USEFUL_LIFE_YEARS,
        salvageRatePct: DEFAULT_SALVAGE_RATE_PCT,
        missedDepMonths: 0,
        missedDepAmount: 0,
        isAbnormal: true,
        remark: '来源:H2-13达可用',
      }
      next.push(row)
      added++
    }
  }
  return { rows: next, updated, added }
}

/** 延迟转固少计折旧 AJE：借费用 / 贷累计折旧 */
export function buildDelayDepAjePair(opts: {
  projectName: string
  amount: number
  seqStart: number
  months: number
  expenseAccount?: { code: string; name: string }
}): Array<{
  rowId: string
  seq: number
  description: string
  entryType: 'AJE'
  accountCode: string
  accountName: string
  summary: string
  debit: number
  credit: number
  indexRef: string
  remark: string
}> {
  const amt = Math.round(opts.amount * 100) / 100
  if (amt < 0.01) return []
  const name = opts.projectName.trim() || '在建工程'
  const exp = opts.expenseAccount ?? { code: '6602', name: '管理费用' }
  const desc = `补提延迟转固折旧-${name}（${opts.months}个月，${amt.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}）`
  const baseId = `h25-aje-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  return [
    {
      rowId: `${baseId}-dr`,
      seq: opts.seqStart,
      description: desc,
      entryType: 'AJE',
      accountCode: exp.code,
      accountName: exp.name,
      summary: desc,
      debit: amt,
      credit: 0,
      indexRef: 'H2-5',
      remark: H25_AJE_MARKER,
    },
    {
      rowId: `${baseId}-cr`,
      seq: opts.seqStart + 1,
      description: desc,
      entryType: 'AJE',
      accountCode: '1602',
      accountName: '累计折旧',
      summary: desc,
      debit: 0,
      credit: amt,
      indexRef: 'H2-5',
      remark: H25_AJE_MARKER,
    },
  ]
}

/** 实质可用日：正式投产 > 试生产 > 验收 > 手工达到可用状态日 */
function resolveReadyDate(row: Pick<H2TransferRow, 'officialProductionDate' | 'trialProductionDate' | 'acceptanceDate' | 'conditionsMetDate'>): string {
  return row.officialProductionDate
    || row.trialProductionDate
    || row.acceptanceDate
    || row.conditionsMetDate
    || ''
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2TransferCheck(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 审计年度（用于期后凭证年份与默认截止日） */
  year?: Ref<number | undefined>
  /** 报表截止日 YYYY-MM-DD，默认 year-12-31 */
  periodEndDate?: Ref<string | undefined>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const cipRows = ref<H2CipPendingRow[]>([])
  const rows = ref<H2TransferRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const postPeriodPulling = ref(false)
  /** H1 反向勾稽状态 */
  const h1Pulling = ref(false)
  /** 最近一次从 H1-7 拉取的入账原值合计（0 表示尚未拉取或无数据） */
  const h1RecordedTotal = ref(0)

  function _periodEnd(): string {
    return options.periodEndDate?.value?.trim()
      || defaultPeriodEndDate(options.year?.value)
  }

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

  function _recalcCipRow(row: H2CipPendingRow): void {
    row.cipNet = row.cipOriginal - row.impairment
    row.budgetRatio = calcCompletionRate(row.cipOriginal, row.budget)
    const hasReason = !!(row.notTransferReason?.trim() || row.postPeriodTransfer?.trim())
    row.isAbnormal = row.readyForUse === true && !hasReason

    // 已达可用仍挂账：测算至报表日的少计折旧
    if (row.readyForUse === true && row.readyDate) {
      const dep = calcMissedDepreciation({
        cost: row.cipNet > 0 ? row.cipNet : row.cipOriginal,
        salvageRatePct: row.salvageRatePct || DEFAULT_SALVAGE_RATE_PCT,
        usefulLifeYears: row.usefulLifeYears || DEFAULT_USEFUL_LIFE_YEARS,
        readyDate: row.readyDate,
        asOfDate: _periodEnd(),
      })
      row.missedDepMonths = dep.months
      row.missedDepAmount = dep.amount
    } else {
      row.missedDepMonths = 0
      row.missedDepAmount = 0
    }
  }

  function _recalcTransferRow(row: H2TransferRow): void {
    row.faNet = row.faOriginal - row.faAccumDep - row.faImpairment

    const conditions = [row.condition1, row.condition2, row.condition3, row.condition4, row.condition5]
    row.allConditionsMet = calcTransferCondition(conditions)

    const readyDate = resolveReadyDate(row)
    if (readyDate && !row.conditionsMetDate) {
      row.conditionsMetDate = readyDate
    }

    if (row.allConditionsMet && row.conditionsMetDate && row.transferDate) {
      row.delayDays = calcOverdueDays(row.transferDate, row.conditionsMetDate)
      row.timelyTransfer = row.delayDays <= DELAY_THRESHOLD_DAYS
    } else if (row.allConditionsMet && !row.transferDate) {
      row.delayDays = row.conditionsMetDate
        ? calcOverdueDays(new Date().toISOString().slice(0, 10), row.conditionsMetDate)
        : 0
      row.timelyTransfer = false
    } else if (row.conditionsMetDate && row.transferDate) {
      row.delayDays = calcOverdueDays(row.transferDate, row.conditionsMetDate)
      row.timelyTransfer = row.delayDays <= DELAY_THRESHOLD_DAYS
    } else {
      row.delayDays = 0
      row.timelyTransfer = null
    }

    row.difference = row.transferAmount - row.h1Amount

    // 少计折旧：实质可用日 → min(转固日, 报表日)
    const ready = row.conditionsMetDate || readyDate
    const periodEnd = _periodEnd()
    let asOf = periodEnd
    if (row.transferDate) {
      asOf = row.transferDate <= periodEnd ? row.transferDate : periodEnd
    }
    if (ready && (row.delayDays > 0 || (row.allConditionsMet && !row.transferDate))) {
      const cost = row.transferAmount > 0 ? row.transferAmount : row.faOriginal
      const policy = resolveDepPolicy(row.assetCategory)
      const life = row.usefulLifeYears > 0 ? row.usefulLifeYears : policy.usefulLifeYears
      const salvage = row.salvageRatePct > 0 ? row.salvageRatePct : policy.salvageRatePct
      const dep = calcMissedDepreciation({
        cost,
        salvageRatePct: salvage,
        usefulLifeYears: life,
        readyDate: ready,
        asOfDate: asOf,
      })
      row.missedDepMonths = dep.months
      row.missedDepAmount = dep.amount
      if (!row.usefulLifeYears) row.usefulLifeYears = life
      if (!row.salvageRatePct) row.salvageRatePct = salvage
    } else {
      row.missedDepMonths = 0
      row.missedDepAmount = 0
    }

    if (row.isAbnormal == null) {
      row.isAbnormal = row.delayDays > DELAY_THRESHOLD_DAYS
        || Math.abs(row.difference) > 0.01
        || row.missedDepAmount > 0.01
    }
  }

  function _emptyCipRow(name = ''): H2CipPendingRow {
    const row: H2CipPendingRow = {
      rowId: _newId('cip'),
      name,
      cipOriginal: 0,
      capitalizedInterest: 0,
      impairment: 0,
      cipNet: 0,
      budget: 0,
      budgetRatio: null,
      plannedReadyDate: '',
      startDate: '',
      readyCriteria: '',
      readyForUse: null,
      readyDate: '',
      notTransferReason: '',
      proposedTransferPct: null,
      postPeriodTransfer: '',
      postPeriodVoucherNos: '',
      usefulLifeYears: DEFAULT_USEFUL_LIFE_YEARS,
      salvageRatePct: DEFAULT_SALVAGE_RATE_PCT,
      missedDepMonths: 0,
      missedDepAmount: 0,
      isAbnormal: false,
      remark: '',
    }
    _recalcCipRow(row)
    return row
  }

  function _emptyTransferRow(name = ''): H2TransferRow {
    const row: H2TransferRow = {
      rowId: _newId('xfer'),
      name,
      faOriginal: 0,
      faAccumDep: 0,
      faImpairment: 0,
      faNet: 0,
      transferDate: '',
      transferAmount: 0,
      assetCategory: '',
      acceptanceDate: '',
      acceptanceAmount: 0,
      readyCriteria: '',
      trialProductionDate: '',
      officialProductionDate: '',
      conditionsMetDate: '',
      condition1: false,
      condition2: false,
      condition3: false,
      condition4: false,
      condition5: false,
      allConditionsMet: false,
      timelyTransfer: null,
      delayDays: 0,
      h1Asset: '',
      h1Amount: 0,
      difference: 0,
      usefulLifeYears: DEFAULT_USEFUL_LIFE_YEARS,
      salvageRatePct: DEFAULT_SALVAGE_RATE_PCT,
      missedDepMonths: 0,
      missedDepAmount: 0,
      isAbnormal: null,
      remark: '',
    }
    _recalcTransferRow(row)
    return row
  }

  function _mapCipFromRaw(r: any): H2CipPendingRow {
    const row: H2CipPendingRow = {
      rowId: r.rowId ?? _newId('cip'),
      name: r.name ?? '',
      cipOriginal: _num(r.cipOriginal),
      capitalizedInterest: _num(r.capitalizedInterest),
      impairment: _num(r.impairment),
      cipNet: 0,
      budget: _num(r.budget),
      budgetRatio: null,
      plannedReadyDate: r.plannedReadyDate ?? '',
      startDate: r.startDate ?? '',
      readyCriteria: r.readyCriteria ?? '',
      readyForUse: r.readyForUse === true ? true : r.readyForUse === false ? false : null,
      readyDate: r.readyDate ?? '',
      notTransferReason: r.notTransferReason ?? '',
      proposedTransferPct: r.proposedTransferPct == null || r.proposedTransferPct === ''
        ? null
        : _num(r.proposedTransferPct),
      postPeriodTransfer: r.postPeriodTransfer ?? '',
      postPeriodVoucherNos: r.postPeriodVoucherNos ?? '',
      usefulLifeYears: _num(r.usefulLifeYears) || DEFAULT_USEFUL_LIFE_YEARS,
      salvageRatePct: _num(r.salvageRatePct) || DEFAULT_SALVAGE_RATE_PCT,
      missedDepMonths: 0,
      missedDepAmount: 0,
      isAbnormal: false,
      remark: r.remark ?? '',
    }
    _recalcCipRow(row)
    return row
  }

  function _mapTransferFromRaw(r: any): H2TransferRow {
    const row: H2TransferRow = {
      rowId: r.rowId ?? _newId('xfer'),
      name: r.name ?? '',
      faOriginal: _num(r.faOriginal ?? r.transferAmount),
      faAccumDep: _num(r.faAccumDep),
      faImpairment: _num(r.faImpairment),
      faNet: 0,
      transferDate: r.transferDate ?? '',
      transferAmount: _num(r.transferAmount),
      assetCategory: r.assetCategory ?? r.h1Asset ?? '',
      acceptanceDate: r.acceptanceDate ?? '',
      acceptanceAmount: _num(r.acceptanceAmount),
      readyCriteria: r.readyCriteria ?? '',
      trialProductionDate: r.trialProductionDate ?? '',
      officialProductionDate: r.officialProductionDate ?? '',
      conditionsMetDate: r.conditionsMetDate ?? '',
      condition1: !!r.condition1 || !!r.cas4Cond1,
      condition2: !!r.condition2 || !!r.cas4Cond2,
      condition3: !!r.condition3 || !!r.cas4Cond3,
      condition4: !!r.condition4 || !!r.cas4Cond4,
      condition5: !!r.condition5 || !!r.cas4Cond5,
      allConditionsMet: false,
      timelyTransfer: null,
      delayDays: 0,
      h1Asset: r.h1Asset ?? r.assetCategory ?? '',
      h1Amount: _num(r.h1Amount),
      difference: 0,
      usefulLifeYears: _num(r.usefulLifeYears) || DEFAULT_USEFUL_LIFE_YEARS,
      salvageRatePct: _num(r.salvageRatePct) || DEFAULT_SALVAGE_RATE_PCT,
      missedDepMonths: 0,
      missedDepAmount: 0,
      isAbnormal: r.isAbnormal === true ? true : r.isAbnormal === false ? false : null,
      remark: r.remark ?? '',
    }
    _recalcTransferRow(row)
    return row
  }

  function initFromAllResponses(): void {
    const cipData = _getJson(CIP_ROWS_KEY)
    cipRows.value = Array.isArray(cipData) && cipData.length > 0
      ? cipData.map(_mapCipFromRaw)
      : []

    const data = _getJson(ROWS_KEY)
    rows.value = Array.isArray(data) && data.length > 0
      ? data.map(_mapTransferFromRaw)
      : []

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  const transferTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.transferAmount)),
  )

  const h1Total: ComputedRef<number> = computed(() =>
    calcSubtotal(rows.value.map(r => r.h1Amount)),
  )

  const totalDifference: ComputedRef<number> = computed(() =>
    transferTotal.value - h1Total.value,
  )

  const metCount: ComputedRef<number> = computed(() =>
    rows.value.filter(r => r.allConditionsMet).length,
  )

  const cipAbnormalCount: ComputedRef<number> = computed(() =>
    cipRows.value.filter(r => r.isAbnormal).length,
  )

  const transferAbnormalCount: ComputedRef<number> = computed(() =>
    rows.value.filter(r => r.isAbnormal === true || r.delayDays > DELAY_THRESHOLD_DAYS).length,
  )

  const cipNetTotal: ComputedRef<number> = computed(() =>
    calcSubtotal(cipRows.value.map(r => r.cipNet)),
  )

  const missedDepTotal: ComputedRef<number> = computed(() =>
    calcSubtotal([
      ...cipRows.value.map(r => r.missedDepAmount),
      ...rows.value.map(r => r.missedDepAmount),
    ]),
  )

  /** 可推送折旧 AJE 的行（金额>0） */
  const pushableDepItems: ComputedRef<Array<{ name: string; amount: number; months: number; source: 'cip' | 'transfer' }>> = computed(() => {
    const items: Array<{ name: string; amount: number; months: number; source: 'cip' | 'transfer' }> = []
    for (const r of cipRows.value) {
      if (r.missedDepAmount > 0.01) {
        items.push({ name: r.name, amount: r.missedDepAmount, months: r.missedDepMonths, source: 'cip' })
      }
    }
    for (const r of rows.value) {
      if (r.missedDepAmount > 0.01) {
        items.push({ name: r.name, amount: r.missedDepAmount, months: r.missedDepMonths, source: 'transfer' })
      }
    }
    return items
  })

  /** 与 H2-2 转固合计交叉验证 */
  const crossValidationH1: ComputedRef<{ diff: number; isMatch: boolean; h22Total: number }> = computed(() => {
    const resp = options.allResponses.value.get('H2-2-rows')
    const raw = resp?.remark ?? resp?.conclusion
    let h2_2_transferTotal = 0
    if (raw) {
      try {
        const h2Rows = JSON.parse(raw)
        if (Array.isArray(h2Rows)) {
          for (const r of h2Rows) {
            h2_2_transferTotal += _num(r.transferAmount)
          }
        }
      } catch { /* ignore */ }
    }
    const diff = transferTotal.value - h2_2_transferTotal
    return { diff, isMatch: Math.abs(diff) < 0.01, h22Total: h2_2_transferTotal }
  })

  /** 与 H1 入账合计勾稽（H1-7「在建工程转入」入账原值合计，须先执行「勾稽 H1 入账」拉取） */
  const h1TransferReconcile: ComputedRef<H2H1TransferReconcile> = computed(() =>
    buildH2H1TransferReconcile(transferTotal.value, h1RecordedTotal.value),
  )

  const rowHighlights: ComputedRef<Map<string, TransferHighlight>> = computed(() => {
    const map = new Map<string, TransferHighlight>()
    for (const row of cipRows.value) {
      map.set(row.rowId, row.isAbnormal ? 'red-cip-ready' : null)
    }
    for (const row of rows.value) {
      if (row.allConditionsMet && !row.transferDate) {
        map.set(row.rowId, 'red-not-transferred')
      } else if (row.delayDays > DELAY_THRESHOLD_DAYS) {
        map.set(row.rowId, 'yellow-delay')
      } else if (Math.abs(row.difference) > 0.01) {
        map.set(row.rowId, 'red-amount-diff')
      } else {
        map.set(row.rowId, null)
      }
    }
    return map
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistCip(): void {
    if (!options.onSave) return
    options.onSave(CIP_ROWS_KEY, cipRows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      cipOriginal: r.cipOriginal,
      capitalizedInterest: r.capitalizedInterest,
      impairment: r.impairment,
      budget: r.budget,
      plannedReadyDate: r.plannedReadyDate,
      startDate: r.startDate,
      readyCriteria: r.readyCriteria,
      readyForUse: r.readyForUse,
      readyDate: r.readyDate,
      notTransferReason: r.notTransferReason,
      proposedTransferPct: r.proposedTransferPct,
      postPeriodTransfer: r.postPeriodTransfer,
      postPeriodVoucherNos: r.postPeriodVoucherNos,
      usefulLifeYears: r.usefulLifeYears,
      salvageRatePct: r.salvageRatePct,
      remark: r.remark,
    })))
  }

  function _persistTransfer(): void {
    if (!options.onSave) return
    options.onSave(ROWS_KEY, rows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      faOriginal: r.faOriginal,
      faAccumDep: r.faAccumDep,
      faImpairment: r.faImpairment,
      transferDate: r.transferDate,
      transferAmount: r.transferAmount,
      assetCategory: r.assetCategory,
      acceptanceDate: r.acceptanceDate,
      acceptanceAmount: r.acceptanceAmount,
      readyCriteria: r.readyCriteria,
      trialProductionDate: r.trialProductionDate,
      officialProductionDate: r.officialProductionDate,
      conditionsMetDate: r.conditionsMetDate,
      condition1: r.condition1,
      condition2: r.condition2,
      condition3: r.condition3,
      condition4: r.condition4,
      condition5: r.condition5,
      h1Asset: r.h1Asset,
      h1Amount: r.h1Amount,
      usefulLifeYears: r.usefulLifeYears,
      salvageRatePct: r.salvageRatePct,
      isAbnormal: r.isAbnormal,
      remark: r.remark,
    })))
  }

  // ─── Actions ───────────────────────────────────────────────────────────────

  function addCipRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name?.trim()) return
    cipRows.value.push(_emptyCipRow(name.trim()))
    _persistCip()
  }

  function removeCipRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = cipRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      cipRows.value.splice(idx, 1)
      _persistCip()
    }
  }

  function updateCipCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = cipRows.value.find(r => r.rowId === rowId)
    if (!row) return

    const formulaFields = ['cipNet', 'budgetRatio', 'isAbnormal', 'missedDepMonths', 'missedDepAmount']
    if (formulaFields.includes(field)) return

    const numFields = [
      'cipOriginal', 'capitalizedInterest', 'impairment', 'budget',
      'proposedTransferPct', 'usefulLifeYears', 'salvageRatePct',
    ]
    if (field === 'readyForUse') {
      row.readyForUse = value === true || value === 'true' || value === '是'
        ? true
        : value === false || value === 'false' || value === '否'
          ? false
          : null
    } else if (numFields.includes(field)) {
      ;(row as any)[field] = value === '' || value == null ? (field === 'proposedTransferPct' ? null : 0) : _num(value)
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    _recalcCipRow(row)
    _persistCip()
  }

  function addRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name?.trim()) return
    rows.value.push(_emptyTransferRow(name.trim()))
    _persistTransfer()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      rows.value.splice(idx, 1)
      _persistTransfer()
    }
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    const boolFields = ['condition1', 'condition2', 'condition3', 'condition4', 'condition5', 'isAbnormal']
    const numFields = [
      'transferAmount', 'h1Amount', 'faOriginal', 'faAccumDep', 'faImpairment',
      'acceptanceAmount', 'usefulLifeYears', 'salvageRatePct',
    ]
    const formulaFields = [
      'allConditionsMet', 'timelyTransfer', 'delayDays', 'difference', 'faNet',
      'missedDepMonths', 'missedDepAmount',
    ]

    if (formulaFields.includes(field)) return

    if (field === 'isAbnormal' && (value === null || value === '')) {
      row.isAbnormal = null
    } else if (boolFields.includes(field)) {
      ;(row as any)[field] = value === true || value === 'true' || value === '是'
        ? true
        : value === false || value === 'false' || value === '否'
          ? false
          : !!value
    } else if (numFields.includes(field)) {
      ;(row as any)[field] = _num(value)
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    // 实质日期变更时同步 conditionsMetDate
    if (['officialProductionDate', 'trialProductionDate', 'acceptanceDate'].includes(field)) {
      const resolved = resolveReadyDate(row)
      if (resolved) row.conditionsMetDate = resolved
    }

    _recalcTransferRow(row)
    _persistTransfer()
  }

  /** 从 H2-2 带入：期末仍有余额 → 表一；本期有转固 → 表二 */
  function syncFromH2Detail(): { cipAdded: number; transferAdded: number } {
    if (options.isReadonly.value) return { cipAdded: 0, transferAdded: 0 }
    const resp = options.allResponses.value.get('H2-2-rows')
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return { cipAdded: 0, transferAdded: 0 }

    let detailRows: any[] = []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return { cipAdded: 0, transferAdded: 0 }
      detailRows = parsed
    } catch {
      return { cipAdded: 0, transferAdded: 0 }
    }

    const existingCip = new Set(cipRows.value.map(r => r.name.trim()).filter(Boolean))
    const existingXfer = new Set(rows.value.map(r => r.name.trim()).filter(Boolean))
    let cipAdded = 0
    let transferAdded = 0

    for (const d of detailRows) {
      const name = String(d.name || d.projectName || '').trim()
      if (!name) continue

      const cipEnd = _num(d.cipEnd ?? d.closingBalance)
      const transferAmount = _num(d.transferAmount ?? d.decreaseTransfer)
      const budget = _num(d.budget ?? d.budgetAmount)
      const interest = _num(d.increaseInterest ?? d.capitalizedInterest)
      const impairment = _num(d.impairmentEnd ?? d.impairment)

      if (cipEnd > 0.01 && !existingCip.has(name)) {
        const row = _emptyCipRow(name)
        row.cipOriginal = cipEnd + impairment
        row.capitalizedInterest = interest
        row.impairment = impairment
        row.budget = budget
        row.startDate = d.startDate ?? ''
        row.plannedReadyDate = d.plannedEndDate ?? d.actualEndDate ?? ''
        _recalcCipRow(row)
        cipRows.value.push(row)
        existingCip.add(name)
        cipAdded++
      }

      if (transferAmount > 0.01 && !existingXfer.has(name)) {
        const row = _emptyTransferRow(name)
        row.transferAmount = transferAmount
        row.faOriginal = transferAmount
        row.transferDate = d.transferDate ?? ''
        row.assetCategory = d.transferToH1 ?? d.targetAssetCategory ?? ''
        row.h1Asset = row.assetCategory
        row.h1Amount = transferAmount
        _recalcTransferRow(row)
        rows.value.push(row)
        existingXfer.add(name)
        transferAdded++
      }
    }

    if (cipAdded) _persistCip()
    if (transferAdded) _persistTransfer()
    return { cipAdded, transferAdded }
  }

  function publishTransferToH1(): void {
    if (!options.onPublishEvent) return
    options.onPublishEvent('h2:transfer-to-h1', {
      items: rows.value
        .filter(r => r.transferAmount > 0)
        .map(r => ({
          name: r.name,
          amount: r.transferAmount,
          date: r.transferDate,
          h1Asset: r.h1Asset || r.assetCategory,
          assetCategory: r.assetCategory,
        })),
      totalTransfer: transferTotal.value,
    })
  }

  /**
   * 表一：从序时账拉取期后（截止日次日起）1601/1604 转固相关凭证，回填 postPeriodTransfer。
   */
  async function pullPostPeriodTransfers(opts?: {
    monthsAfter?: number
    accountCodes?: string[]
  }): Promise<{ ok: boolean; matched: number; scanned: number; message: string }> {
    if (options.isReadonly.value) {
      return { ok: false, matched: 0, scanned: 0, message: '只读模式' }
    }
    if (!cipRows.value.length) {
      return { ok: false, matched: 0, scanned: 0, message: '表一无挂账工程，请先从 H2-2 带入或手工新增' }
    }

    const periodEnd = _periodEnd()
    const { dateFrom, dateTo, year } = postPeriodDateRange(periodEnd, opts?.monthsAfter ?? 3)
    const codes = opts?.accountCodes ?? ['1601', '1604']
    postPeriodPulling.value = true

    try {
      const hits: H2PostPeriodVoucherHit[] = []
      for (const code of codes) {
        let page = 1
        let hasMore = true
        while (hasMore && page <= 10) {
          const { data } = await http.get(
            `/api/projects/${options.projectId.value}/ledger/entries/${code}`,
            {
              params: { year, date_from: dateFrom, date_to: dateTo, page, page_size: 500 },
              _silent: true,
            } as any,
          )
          const items: any[] = data?.items ?? data?.data?.items ?? data?.rows ?? (Array.isArray(data) ? data : [])
          for (const it of items) {
            const voucherDate = String(it.voucher_date ?? it.voucherDate ?? '').slice(0, 10)
            if (voucherDate && voucherDate < dateFrom) continue
            hits.push({
              voucherDate,
              voucherNo: String(it.voucher_no ?? it.voucherNo ?? ''),
              summary: String(it.summary ?? it.description ?? ''),
              amount: Math.abs(_num(it.debit_amount ?? it.debitAmount) || _num(it.credit_amount ?? it.creditAmount)),
              accountCode: String(it.account_code ?? it.accountCode ?? code),
            })
          }
          hasMore = items.length >= 500
          page++
        }
      }

      let matched = 0
      for (const row of cipRows.value) {
        const name = row.name.trim()
        if (!name) continue
        const applied = hits.filter(h => {
          if (_nameMatch(h.summary, name)) return true
          // 摘要含转固关键词且金额接近挂账净值（±15%）
          if (POST_PERIOD_KEYWORDS.some(k => h.summary.includes(k))) {
            const net = row.cipNet || row.cipOriginal
            return net > 0 && Math.abs(h.amount - net) / net < 0.15
          }
          return false
        })
        if (!applied.length) continue
        const { text, voucherNos } = formatPostPeriodHits(applied.slice(0, 5))
        row.postPeriodTransfer = text
        row.postPeriodVoucherNos = voucherNos
        _recalcCipRow(row)
        matched++
      }

      if (matched > 0) _persistCip()
      return {
        ok: matched > 0,
        matched,
        scanned: hits.length,
        message: matched > 0
          ? `已回填 ${matched} 项期后转固（扫描 ${hits.length} 条，窗口 ${dateFrom}~${dateTo}）`
          : `期后窗口 ${dateFrom}~${dateTo} 扫描 ${hits.length} 条，未匹配到挂账工程`,
      }
    } catch (e: any) {
      return {
        ok: false,
        matched: 0,
        scanned: 0,
        message: `拉取失败：${e?.message || '网络或序时账不可用'}`,
      }
    } finally {
      postPeriodPulling.value = false
    }
  }

  /** H2-13 达可用 → 表一挂账回写 */
  function syncReadyFromH213(): { ok: boolean; updated: number; added: number; message: string } {
    if (options.isReadonly.value) {
      return { ok: false, updated: 0, added: 0, message: '只读模式' }
    }
    const raw = _getJson(H213_ROWS_KEY)
    if (!Array.isArray(raw) || !raw.length) {
      return { ok: false, updated: 0, added: 0, message: 'H2-13 暂无盘点行数据' }
    }
    const { rows: next, updated, added } = mergeH213ReadyIntoCipRows(cipRows.value, raw)
    if (updated + added === 0) {
      return { ok: false, updated: 0, added: 0, message: 'H2-13 无「达可用=是」的项目，或均已同步' }
    }
    cipRows.value = next.map(r => {
      _recalcCipRow(r)
      return r
    })
    _persistCip()
    return {
      ok: true,
      updated,
      added,
      message: `已从 H2-13 回写：更新 ${updated} 项、新增 ${added} 项挂账`,
    }
  }

  /** 少计折旧合计推送 H2-3（重复推送替换旧自动草稿） */
  function pushDelayDepAjeToH23(): {
    ok: boolean
    added: number
    amount: number
    message: string
  } {
    if (options.isReadonly.value) {
      return { ok: false, added: 0, amount: 0, message: '只读模式' }
    }
    // 推送前重算
    for (const r of cipRows.value) _recalcCipRow(r)
    for (const r of rows.value) _recalcTransferRow(r)

    const toPush = pushableDepItems.value
    if (!toPush.length) {
      return {
        ok: false,
        added: 0,
        amount: 0,
        message: '无可推送项：请确认达可用日/转固延迟，并填写原值与折旧政策（年限/残值率）',
      }
    }

    let existing: any[] = []
    const raw = _getJson(H23_ROWS_KEY)
    if (Array.isArray(raw)) existing = raw
    existing = existing.filter((r: any) => r?.remark !== H25_AJE_MARKER)

    let seq = existing.reduce((m: number, r: any) => Math.max(m, _num(r.seq)), 0) + 1
    const newRows: any[] = []
    for (const item of toPush) {
      const pair = buildDelayDepAjePair({
        projectName: item.name,
        amount: item.amount,
        seqStart: seq,
        months: item.months,
      })
      newRows.push(...pair)
      seq += pair.length
    }

    const merged = [...existing, ...newRows].map((r, i) => ({ ...r, seq: i + 1 }))
    options.onSave?.(H23_ROWS_KEY, merged)

    if (options.onPublishEvent) {
      options.onPublishEvent('adjustment:created', {
        source: 'H2-5',
        marker: H25_AJE_MARKER,
        count: newRows.length,
      })
    }

    const amount = toPush.reduce((s, r) => s + r.amount, 0)
    return {
      ok: true,
      added: newRows.length,
      amount,
      message: `已向 H2-3 推送 ${newRows.length} 条 AJE（少计折旧合计 ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}）`,
    }
  }

  /**
   * 反向勾稽：从 H1-7「在建工程转入」拉取实际入账原值，按工程名匹配回填
   * 表二各行的 h1Amount / h1Asset（差异列自动重算），闭合 H1↔H2 双向环。
   * 仅填空默认（fillEmpty）：已手工录入 h1Amount 的行不覆盖；overwrite 强制覆盖。
   */
  async function pullH1RecordedAmounts(
    mode: 'fillEmpty' | 'overwrite' = 'fillEmpty',
  ): Promise<{ ok: boolean; matched: number; unmatched: number; total: number; message: string }> {
    if (options.isReadonly.value) {
      return { ok: false, matched: 0, unmatched: 0, total: 0, message: '只读模式' }
    }
    if (!rows.value.length) {
      return { ok: false, matched: 0, unmatched: 0, total: 0, message: '表二暂无已转固工程，请先从 H2-2 带入或手工新增' }
    }
    h1Pulling.value = true
    try {
      const result = await pullH1CipAdditionsForH2(options.projectId.value)
      if (result.status !== 'ok') {
        h1RecordedTotal.value = result.recordedTotal
        return { ok: false, matched: 0, unmatched: rows.value.length, total: result.recordedTotal, message: result.message }
      }
      h1RecordedTotal.value = result.recordedTotal
      const h1Rows: H1CipAddition[] = result.rows
      let matched = 0
      let unmatched = 0
      for (const row of rows.value) {
        const hit = matchH1AmountByName(row.name, h1Rows)
        if (!hit) {
          unmatched++
          continue
        }
        const alreadyFilled = row.h1Amount > 0.01
        if (mode === 'fillEmpty' && alreadyFilled) {
          matched++
          continue
        }
        row.h1Amount = hit.recordedAmount
        if (!row.h1Asset && hit.assetCategory) row.h1Asset = hit.assetCategory
        _recalcTransferRow(row)
        matched++
      }
      if (matched > 0) _persistTransfer()
      return {
        ok: matched > 0,
        matched,
        unmatched,
        total: result.recordedTotal,
        message: matched > 0
          ? `已从 H1-7 回填 ${matched} 项入账金额（H1 入账合计 ${result.recordedTotal.toLocaleString('zh-CN')}），未匹配 ${unmatched} 项`
          : `H1-7 有 ${h1Rows.length} 项入账记录，但按工程名未匹配到表二任何行（未匹配 ${unmatched} 项，请核对工程/资产名称）`,
      }
    } catch (e: any) {
      return { ok: false, matched: 0, unmatched: 0, total: 0, message: `拉取失败：${e?.message || 'H1 底稿不可用'}` }
    } finally {
      h1Pulling.value = false
    }
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  return {
    cipRows,
    rows,
    auditNote,
    auditConclusion,
    transferTotal,
    totalTransfer: transferTotal,
    h1Total,
    totalDifference,
    metCount,
    cipAbnormalCount,
    transferAbnormalCount,
    cipNetTotal,
    missedDepTotal,
    pushableDepItems,
    crossValidationH1,
    h1TransferReconcile,
    h1RecordedTotal,
    h1Pulling,
    rowHighlights,
    postPeriodPulling,
    addCipRow,
    removeCipRow,
    updateCipCell,
    addRow,
    removeRow,
    updateCell,
    syncFromH2Detail,
    syncReadyFromH213,
    pullPostPeriodTransfers,
    pullH1RecordedAmounts,
    pushDelayDepAjeToH23,
    publishTransferToH1,
    saveNote,
    saveConclusion,
    initFromAllResponses,
  }
}

export default useH2TransferCheck
