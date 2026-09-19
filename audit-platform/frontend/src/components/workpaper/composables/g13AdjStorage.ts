/**
 * G13-3 调整分录 — 纯函数（类别判定 / 6101 净额 / 按所属科目分项回写）
 * 对齐 Excel「公允价值变动收益调整分录汇总表 G13-3」
 */
import { G13_ACCOUNT_CODE, G13_BELONG_ACCOUNTS, mapBelongToAdjRow } from './g13Constants'
import { parseNum } from './useG13FormulaEngine'

export const G13_CATEGORY_OPTIONS = ['账项调整', '报表调整', '其他'] as const
export type G13AdjCategory = (typeof G13_CATEGORY_OPTIONS)[number]

/** 调整分录常见相关科目（含对方科目） */
export const G13_ADJ_ACCOUNT_OPTIONS = [
  { code: '6101', name: '公允价值变动收益' },
  { code: '1501', name: '交易性金融资产' },
  { code: '2101', name: '交易性金融负债' },
  { code: '1504', name: '其他非流动金融资产' },
  { code: '1503', name: '其他权益工具投资' },
  { code: '1521', name: '投资性房地产' },
  { code: '2221', name: '应交税费' },
  { code: '1002', name: '银行存款' },
] as const

/** 中央调整分录模块同步时识别的相关科目前缀 */
export const G13_RELATED_ACCOUNT_PREFIXES = [
  '6101', '1501', '2101', '1504', '1503', '1521', '6111',
] as const

export function isG13RelatedAccount(code: string): boolean {
  const c = String(code || '').trim()
  return G13_RELATED_ACCOUNT_PREFIXES.some((p) => c === p || c.startsWith(p))
}

export function categoryFromModule(t: string | undefined): string {
  const x = String(t || '').toLowerCase()
  if (x.includes('rje') || x.includes('报表') || x.includes('重分类')) return '报表调整'
  if (x.includes('其他')) return '其他'
  return '账项调整'
}

export interface G13AdjustmentEntryLike {
  category?: string
  entryType?: string
  accountCode?: string
  accountName?: string
  debitAmount?: number
  creditAmount?: number
  description?: string
  summary?: string
  noteItem?: string
  remark?: string
  belongAccount?: string
  adjudicationRowKey?: string
}

export type G13AdjustmentWritebackMap = Record<string, number>

/** G13-3 账项调整 → G13-1 分项调整数 overlay（按审定表 rowKey） */
export const G13_AJE_ADJ_OVERLAY_ID = 'G13-aje-adj-overlay'

export interface G13AdjustmentSummary {
  rowCount: number
  ajeCount: number
  rjeCount: number
  totalDebits: number
  totalCredits: number
  balanceDiff: number
  /** 6101 账项调整净额（贷−借，收益增加为正） */
  netAje6101: number
  /** 6101 报表调整净额（不回写审定） */
  netRje6101: number
}

export function isG13ReportReclass(row: G13AdjustmentEntryLike): boolean {
  if (row.category === '报表调整') return true
  if (row.entryType === 'RJE') return true
  return false
}

export function isG13AccountCode(code: string | undefined): boolean {
  const c = String(code || '').trim()
  return c === G13_ACCOUNT_CODE || c.startsWith('6101')
}

/** 6101 贷方科目：单行净额 = 贷方 − 借方（收益增加为正） */
export function calcG13AdjustmentNet(rows: G13AdjustmentEntryLike[]): number {
  return rows
    .filter((r) => isG13AccountCode(r.accountCode) || String(r.accountName ?? '').includes('公允价值变动'))
    .filter((r) => !isG13ReportReclass(r))
    .reduce((s, r) => s + parseNum(r.creditAmount) - parseNum(r.debitAmount), 0)
}

export function inferG13BelongAccount(row: G13AdjustmentEntryLike): string {
  const explicit = String(row.belongAccount || '').trim()
  if (explicit && (G13_BELONG_ACCOUNTS as readonly string[]).includes(explicit)) return explicit
  if (explicit === 'other') return 'other'

  const text = [
    row.description, row.summary, row.noteItem, row.remark, row.accountName,
  ].map((x) => String(x || '')).join(' ')

  if (/交易性金融负债|G10|2101/.test(text)) return 'G10'
  if (/衍生|G9/.test(text)) return 'G9'
  if (/其他非流动|G8|1504/.test(text)) return 'G8'
  if (/投资性房地产|H3|1521/.test(text)) return 'H3'
  if (/交易性金融资产|G1|1501/.test(text)) return 'G1'
  return 'other'
}

/** 从调整行文本推断 instrumentType，供 mapBelongToAdjRow 区分衍生负债 */
export function inferG13InstrumentTypeHint(row: G13AdjustmentEntryLike): string {
  const text = [
    row.description, row.summary, row.noteItem, row.remark, row.accountName,
    row.adjudicationRowKey,
  ].map((x) => String(x || '')).join(' ')
  if (/衍生金融负债|衍生.*负债|负债.*衍生|衍生工具负债/.test(text)) return '衍生工具负债'
  if (/指定/.test(text)) return '指定FVTPL'
  if (/衍生/.test(text)) return '衍生工具'
  return ''
}

/**
 * 按所属科目（G1/G8/G9/G10/H3/other）汇总 6101 账项调整净额。
 * 「报表调整」不计入；非 6101 行跳过。
 */
export function aggregateG13AdjustmentByBelong(
  rows: G13AdjustmentEntryLike[],
): G13AdjustmentWritebackMap {
  const byBelong: G13AdjustmentWritebackMap = { other: 0 }
  for (const acct of G13_BELONG_ACCOUNTS) byBelong[acct] = 0

  for (const r of rows) {
    if (isG13ReportReclass(r)) continue
    if (!isG13AccountCode(r.accountCode) && !String(r.accountName ?? '').includes('公允价值变动')) {
      continue
    }
    const key = inferG13BelongAccount(r)
    const net = parseNum(r.creditAmount) - parseNum(r.debitAmount)
    byBelong[key] = (byBelong[key] ?? 0) + net
  }
  return byBelong
}

/**
 * 所属科目 → 审定表 rowKey 分项净额（与 mapBelongToAdjRow 一致，支持衍生负债）
 * 优先用行上显式 adjudicationRowKey。
 */
export function aggregateG13AdjustmentByAdjRow(
  rows: G13AdjustmentEntryLike[],
): G13AdjustmentWritebackMap {
  const byAdj: G13AdjustmentWritebackMap = {}
  for (const r of rows) {
    if (isG13ReportReclass(r)) continue
    if (!isG13AccountCode(r.accountCode) && !String(r.accountName ?? '').includes('公允价值变动')) {
      continue
    }
    const explicit = String(r.adjudicationRowKey || '').trim()
    const belong = inferG13BelongAccount(r)
    const adjKey = explicit
      || (belong === 'other' ? 'other' : mapBelongToAdjRow(belong, inferG13InstrumentTypeHint(r)))
    const net = parseNum(r.creditAmount) - parseNum(r.debitAmount)
    byAdj[adjKey] = (byAdj[adjKey] ?? 0) + net
  }
  return byAdj
}

export function summarizeG13Adjustment(rows: G13AdjustmentEntryLike[]): G13AdjustmentSummary {
  let ajeCount = 0
  let rjeCount = 0
  let totalDebits = 0
  let totalCredits = 0
  let netAje6101 = 0
  let netRje6101 = 0

  for (const r of rows) {
    totalDebits += parseNum(r.debitAmount)
    totalCredits += parseNum(r.creditAmount)
    const isRje = isG13ReportReclass(r)
    if (isRje) rjeCount += 1
    else ajeCount += 1

    if (!isG13AccountCode(r.accountCode) && !String(r.accountName ?? '').includes('公允价值变动')) {
      continue
    }
    const net = parseNum(r.creditAmount) - parseNum(r.debitAmount)
    if (isRje) netRje6101 += net
    else netAje6101 += net
  }

  return {
    rowCount: rows.length,
    ajeCount,
    rjeCount,
    totalDebits,
    totalCredits,
    balanceDiff: totalDebits - totalCredits,
    netAje6101,
    netRje6101,
  }
}

export function categoryFromLegacy(raw: { category?: string; entryType?: string }): G13AdjCategory {
  if (raw.category && (G13_CATEGORY_OPTIONS as readonly string[]).includes(raw.category)) {
    return raw.category as G13AdjCategory
  }
  if (raw.entryType === 'RJE') return '报表调整'
  return '账项调整'
}
