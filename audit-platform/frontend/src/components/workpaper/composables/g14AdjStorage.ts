/**
 * G14-3 调整分录 — 纯函数（类别判定 / 6702 净额 / 按明细行分项回写）
 * 对齐 Excel「信用减值损失调整分录汇总表 G14-3」
 */
import { G14_ACCOUNT_CODE, G14_LINE_ITEMS } from './g14Constants'
import { parseNum } from './useG14FormulaEngine'

export const G14_CATEGORY_OPTIONS = ['账项调整', '报表调整', '其他'] as const
export type G14AdjCategory = (typeof G14_CATEGORY_OPTIONS)[number]

/** 调整分录常见相关科目（含对方科目：坏账准备/减值准备/预计负债/OCI） */
export const G14_ADJ_ACCOUNT_OPTIONS = [
  { code: '6702', name: '信用减值损失' },
  { code: '1231', name: '坏账准备' },
  { code: '1142', name: '合同资产减值准备' },
  { code: '1505', name: '债权投资减值准备' },
  { code: '1502', name: '持有至到期投资减值准备' },
  { code: '2801', name: '预计负债' },
  { code: '4104', name: '其他综合收益' },
  { code: '1002', name: '银行存款' },
] as const

/** 中央调整分录模块同步时识别的相关科目前缀 */
export const G14_RELATED_ACCOUNT_PREFIXES = [
  '6702', '1231', '1142', '1505', '1502', '2801', '4104',
] as const

export const G14_WRITEBACK_OPTIONS = [
  ...G14_LINE_ITEMS.map((d) => ({ value: d.rowKey, label: d.label })),
] as const

export function isG14RelatedAccount(code: string): boolean {
  const c = String(code || '').trim()
  return G14_RELATED_ACCOUNT_PREFIXES.some((p) => c === p || c.startsWith(p))
}

export function isG14AccountCode(code: string | undefined): boolean {
  const c = String(code || '').trim()
  return c === G14_ACCOUNT_CODE || c.startsWith('6702')
}

export function categoryFromModule(t: string | undefined): string {
  const x = String(t || '').toLowerCase()
  if (x.includes('rje') || x.includes('报表') || x.includes('重分类')) return '报表调整'
  if (x.includes('其他')) return '其他'
  return '账项调整'
}

export function categoryFromLegacy(raw: { category?: string; entryType?: string }): string {
  const cat = String(raw.category || '').trim()
  if ((G14_CATEGORY_OPTIONS as readonly string[]).includes(cat)) return cat
  if (cat === '重分类调整') return '报表调整'
  if (raw.entryType === 'RJE') return '报表调整'
  if (raw.entryType === 'AJE') return '账项调整'
  return '账项调整'
}

export interface G14AdjustmentEntryLike {
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
  adjudicationRowKey?: string
}

export type G14AdjustmentWritebackMap = Record<string, number>

export interface G14AdjustmentSummary {
  rowCount: number
  ajeCount: number
  rjeCount: number
  totalDebits: number
  totalCredits: number
  balanceDiff: number
  /** 6702 账项调整净额（借−贷，费用增加为正） */
  netAje6702: number
  /** 6702 报表调整净额（不回写审定） */
  netRje6702: number
}

export function isG14ReportReclass(row: G14AdjustmentEntryLike): boolean {
  if (row.category === '报表调整') return true
  if (row.entryType === 'RJE') return true
  return false
}

/**
 * 按摘要/附注推断 G14-2 明细回写行。
 * 显式 adjudicationRowKey 优先；未匹配落入 other。
 */
export function inferG14AdjudicationRowKey(row: G14AdjustmentEntryLike): string {
  const explicit = String(row.adjudicationRowKey || '').trim()
  if (explicit && G14_LINE_ITEMS.some((d) => d.rowKey === explicit)) return explicit

  const text = [
    row.description, row.summary, row.noteItem, row.remark, row.accountName,
  ].map((x) => String(x || '')).join(' ')

  if (/合同资产/.test(text)) return 'ca'
  if (/应收票据|票据坏账/.test(text)) return 'notes'
  if (/其他应收/.test(text)) return 'othar'
  if (/应收款项融资/.test(text)) return 'rfin'
  if (/长期应收/.test(text)) return 'ltar'
  if (/其他债权投资|FVOCI|其他综合收益.*信用/.test(text)) return 'othdebt'
  if (/债权投资|持有至到期/.test(text)) return 'debt'
  if (/财务担保|贷款承诺|预计负债/.test(text)) return 'guarantee'
  if (/应收账款/.test(text)) return 'ar'
  return 'other'
}

/** 6702 借方科目：单行净额 = 借方 − 贷方（费用/损失增加为正） */
export function calcG14AdjustmentNet(rows: G14AdjustmentEntryLike[]): number {
  return rows
    .filter((r) => isG14AccountCode(r.accountCode) || String(r.accountName ?? '').includes('信用减值'))
    .filter((r) => !isG14ReportReclass(r))
    .reduce((s, r) => s + parseNum(r.debitAmount) - parseNum(r.creditAmount), 0)
}

/**
 * 按 G14-2 明细行汇总 6702 账项调整净额。
 * 「报表调整」不计入；非 6702 行跳过。
 */
export function aggregateG14AdjustmentByRow(
  rows: G14AdjustmentEntryLike[],
): G14AdjustmentWritebackMap {
  const byRow: G14AdjustmentWritebackMap = {}
  for (const def of G14_LINE_ITEMS) byRow[def.rowKey] = 0

  for (const r of rows) {
    if (isG14ReportReclass(r)) continue
    const code = String(r.accountCode ?? '')
    if (
      !isG14AccountCode(code)
      && !String(r.accountName ?? '').includes('信用减值')
    ) {
      continue
    }
    const key = inferG14AdjudicationRowKey(r)
    const net = parseNum(r.debitAmount) - parseNum(r.creditAmount)
    byRow[key] = (byRow[key] ?? 0) + net
  }
  return byRow
}

export function summarizeG14Adjustment(rows: G14AdjustmentEntryLike[]): G14AdjustmentSummary {
  let ajeCount = 0
  let rjeCount = 0
  let totalDebits = 0
  let totalCredits = 0
  let netAje6702 = 0
  let netRje6702 = 0

  for (const r of rows) {
    totalDebits += parseNum(r.debitAmount)
    totalCredits += parseNum(r.creditAmount)
    const isRje = isG14ReportReclass(r)
    if (isRje) rjeCount += 1
    else ajeCount += 1

    const is6702 = isG14AccountCode(r.accountCode) || String(r.accountName ?? '').includes('信用减值')
    if (!is6702) continue
    const net = parseNum(r.debitAmount) - parseNum(r.creditAmount)
    if (isRje) netRje6702 += net
    else netAje6702 += net
  }

  return {
    rowCount: rows.length,
    ajeCount,
    rjeCount,
    totalDebits,
    totalCredits,
    balanceDiff: totalDebits - totalCredits,
    netAje6702,
    netRje6702,
  }
}
