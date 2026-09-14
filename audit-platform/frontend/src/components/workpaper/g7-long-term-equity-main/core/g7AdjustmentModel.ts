/**
 * G7-3 调整分录 — 纯函数（normalize / 汇总 / 按被投资单位回写）
 */
import {
  G7_ADJUSTMENT_ACCOUNT_OPTIONS,
  G7_GROSS_FALLBACK_STANDARD,
  g7CodeMatchesPrefix,
  isG7ProvisionCode,
} from '../../composables/g7AccountScope'
import type { TbSourceCodes } from '../../composables/shared/tbSourceCodes'
import { parseNum } from '../../composables/useG7FormulaEngine'

export const G7_ADJUSTMENT_PUSHED_EVENT = 'g7:adjustment-pushed'
export const G714_SUGGESTED_KIND = 'g7-14-suggested'
export const G713_BARGAIN_KIND = 'g7-13-bargain-suggested'

export type G73SourceKind = typeof G714_SUGGESTED_KIND | typeof G713_BARGAIN_KIND | string

export interface G73EntryLike {
  id: string
  seq: number
  description: string
  category: '账项调整' | '报表调整' | '其他'
  reportItem: string
  noteItem: string
  indexRef: string
  sourceGroupId?: string
  sourceKind?: string
  investeeName?: string
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

export interface AccountTotals {
  ajeTotal: number
  rjeTotal: number
}

export interface InvesteeAccountTotals extends AccountTotals {
  investeeName: string
}

/**
 * 调整分录可选科目 —— 与 `G7TabAdjustment.vue` 共用同一份声明
 * （`composables/g7AccountScope.G7_ADJUSTMENT_ACCOUNT_OPTIONS`）。
 * 改造前两处各写一份 4 条列表，改一处必漏另一处。
 */
const ACCOUNT_DEFAULTS = [
  ...G7_ADJUSTMENT_ACCOUNT_OPTIONS,
  // 以下为本模块归一化时额外识别的对方科目（不进 Tab 的下拉选项）
  { code: '6301', name: '营业外收入' },
  { code: '1012', name: '银行存款' },
  { code: '1122', name: '应收账款' },
  { code: '2241', name: '其他应付款' },
]

export function sourceKindLabel(kind: string | undefined | null): string {
  const k = String(kind || '').trim()
  if (k === G714_SUGGESTED_KIND) return 'G7-14建议'
  if (k === G713_BARGAIN_KIND) return 'G7-13廉价购买'
  if (!k) return ''
  return k
}

export function isSuggestedDraft(row: { sourceKind?: string; remark?: string }): boolean {
  const sk = String(row.sourceKind || '').trim()
  if (sk === G714_SUGGESTED_KIND || sk === G713_BARGAIN_KIND) return true
  const remark = String(row.remark || '')
  return remark.includes(`sourceKind=${G714_SUGGESTED_KIND}`)
    || remark.includes(`sourceKind=${G713_BARGAIN_KIND}`)
}

/**
 * 采纳建议草稿：去掉 sourceKind，清洗 remark 中的 sourceKind= 标记，变为可推集中模块的手工行。
 */
export function adoptSuggestedDraft<T extends {
  sourceKind?: string
  remark?: string
}>(row: T): T {
  if (!isSuggestedDraft(row)) return row
  const next = { ...row, sourceKind: undefined as string | undefined }
  const remark = String(row.remark || '')
    .replace(/;?\s*sourceKind=g7-14-suggested/g, '')
    .replace(/;?\s*sourceKind=g7-13-bargain-suggested/g, '')
    .replace(/^来源：/, '')
    .trim()
  const stamp = '【已采纳建议】'
  next.remark = remark.includes(stamp)
    ? remark
    : (remark ? `${stamp} ${remark}` : stamp)
  return next
}

export function adoptAllSuggestedDrafts<T extends {
  sourceKind?: string
  remark?: string
}>(rows: T[]): T[] {
  return rows.map((row) => (isSuggestedDraft(row) ? adoptSuggestedDraft(row) : row))
}

/** 可推入集中调整模块：非建议草稿、无模块组 ID、有金额 */
export function isPushableToModule(row: {
  sourceKind?: string
  remark?: string
  sourceGroupId?: string
  debitAmount?: number
  creditAmount?: number
}): boolean {
  if (isSuggestedDraft(row)) return false
  if (row.sourceGroupId) return false
  return parseNum(row.debitAmount) !== 0 || parseNum(row.creditAmount) !== 0
}

/** 从 sourceKind 字段或 remark 兜底推断 */
export function inferSourceKind(raw: Record<string, any> | null | undefined): string | undefined {
  if (!raw) return undefined
  const direct = String(raw.sourceKind || '').trim()
  if (direct) return direct
  const remark = String(raw.remark || '')
  for (const k of [G714_SUGGESTED_KIND, G713_BARGAIN_KIND]) {
    if (remark.includes(`sourceKind=${k}`)) return k
  }
  return undefined
}

export function normalizeG73Entry(
  raw: any,
  index: number,
  opts?: { generateId?: () => string },
): G73EntryLike {
  const generateId = opts?.generateId
    || (() => `g7adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`)
  const category = (raw?.category
    || (raw?.entryType === 'RJE' ? '报表调整' : '账项调整')) as G73EntryLike['category']
  const knownByName = ACCOUNT_DEFAULTS.find((item) =>
    String(raw?.accountName || '').includes(item.name),
  )
  const accountCode = String(raw?.accountCode || knownByName?.code || G7_GROSS_FALLBACK_STANDARD)
  const known = ACCOUNT_DEFAULTS.find((item) => item.code === accountCode)
  const description = String(raw?.description || raw?.summary || '')
  const sourceKind = inferSourceKind(raw)
  const investeeName = String(raw?.investeeName || raw?.investee_name || '').trim() || undefined
  return {
    id: String(raw?.id || raw?.rowId || generateId()),
    seq: index + 1,
    description,
    category: (['账项调整', '报表调整', '其他'].includes(category) ? category : '账项调整') as G73EntryLike['category'],
    reportItem: String(raw?.reportItem || '长期股权投资'),
    noteItem: String(raw?.noteItem || ''),
    indexRef: String(raw?.indexRef || 'G7-3'),
    sourceGroupId: raw?.sourceGroupId ? String(raw.sourceGroupId) : undefined,
    sourceKind,
    investeeName,
    entryType: category === '报表调整' ? 'RJE' : 'AJE',
    date: String(raw?.date || ''),
    summary: description,
    accountCode,
    accountName: String(raw?.accountName || known?.name || ''),
    debitAmount: parseNum(raw?.debitAmount ?? raw?.debit),
    creditAmount: parseNum(raw?.creditAmount ?? raw?.credit),
    preparedBy: String(raw?.preparedBy || ''),
    remark: String(raw?.remark || ''),
  }
}

export function aggregateAccount(
  entries: Array<{
    accountCode?: string
    debitAmount?: number
    creditAmount?: number
    category?: string
  }>,
  codePrefix: string,
  tbSource?: TbSourceCodes | null,
): AccountTotals {
  let ajeTotal = 0
  let rjeTotal = 0
  for (const entry of entries) {
    if (!g7CodeMatchesPrefix(entry.accountCode, codePrefix)) continue
    const debitMinusCredit = parseNum(entry.debitAmount) - parseNum(entry.creditAmount)
    const amount = isG7ProvisionCode(codePrefix, tbSource) ? -debitMinusCredit : debitMinusCredit
    if (entry.category === '报表调整') rjeTotal += amount
    else ajeTotal += amount
  }
  return {
    ajeTotal: Math.round(ajeTotal * 100) / 100,
    rjeTotal: Math.round(rjeTotal * 100) / 100,
  }
}

/** 按被投资单位拆分 1511/1512 回写金额；无名称的归入「（未指定）」 */
export function aggregateByInvestee(
  entries: Array<{
    accountCode?: string
    debitAmount?: number
    creditAmount?: number
    category?: string
    investeeName?: string
    description?: string
  }>,
  codePrefix: string,
  tbSource?: TbSourceCodes | null,
): InvesteeAccountTotals[] {
  const map = new Map<string, AccountTotals>()
  for (const entry of entries) {
    if (!g7CodeMatchesPrefix(entry.accountCode, codePrefix)) continue
    const name = String(entry.investeeName || '').trim()
      || extractInvesteeFromDescription(String(entry.description || ''))
      || '（未指定）'
    const debitMinusCredit = parseNum(entry.debitAmount) - parseNum(entry.creditAmount)
    const amount = isG7ProvisionCode(codePrefix, tbSource) ? -debitMinusCredit : debitMinusCredit
    const cur = map.get(name) || { ajeTotal: 0, rjeTotal: 0 }
    if (entry.category === '报表调整') cur.rjeTotal += amount
    else cur.ajeTotal += amount
    map.set(name, cur)
  }
  return [...map.entries()].map(([investeeName, totals]) => ({
    investeeName,
    ajeTotal: Math.round(totals.ajeTotal * 100) / 100,
    rjeTotal: Math.round(totals.rjeTotal * 100) / 100,
  }))
}

/** 从说明中粗提取「××公司/联营/合营」等名称片段（兜底） */
export function extractInvesteeFromDescription(description: string): string {
  const text = String(description || '').trim()
  if (!text) return ''
  const m = text.match(/([\u4e00-\u9fa5A-Za-z0-9（）()·\-_]{2,40}?(?:公司|联营|合营|企业|中心))/)
  return m?.[1]?.trim() || ''
}

/**
 * 将按被投资单位的 AJE/RJE 写入 G7-1 groups.rows。
 * 优先按 row.item / investeeName 精确匹配；未匹配部分汇总落到第一行（兼容旧行为）。
 */
export function applyInvesteeWritebackToGroups(
  groups: Array<{ id?: string; groupType?: string; rows?: any[] }> | null | undefined,
  byInvestee: InvesteeAccountTotals[],
  codePrefix: string,
  tbSource?: TbSourceCodes | null,
): boolean {
  if (!groups?.length || !byInvestee.length) return false
  const targetGroups = isG7ProvisionCode(codePrefix, tbSource)
    ? groups.filter(g => g.id === 'impairment' || g.groupType === 'impairment')
    : groups.filter(g => !['impairment', 'total'].includes(String(g.id || g.groupType || '')))

  const allRows = targetGroups.flatMap(g => (Array.isArray(g.rows) ? g.rows : []))
  if (!allRows.length) return false

  for (const row of allRows) {
    row.closingAJE = 0
    row.closingRJE = 0
    row.closingAdjusted = parseNum(row.closingUnadjusted)
  }

  let applied = 0
  let unmatchedAje = 0
  let unmatchedRje = 0
  for (const part of byInvestee) {
    const name = String(part.investeeName || '').trim()
    const hit = allRows.find((row) => {
      const item = String(row.item || row.investeeName || '').trim()
      return item && name && (item === name || item.includes(name) || name.includes(item))
    })
    if (hit) {
      hit.closingAJE = parseNum(hit.closingAJE) + part.ajeTotal
      hit.closingRJE = parseNum(hit.closingRJE) + part.rjeTotal
      hit.closingAdjusted = parseNum(hit.closingUnadjusted)
        + parseNum(hit.closingAJE) + parseNum(hit.closingRJE)
      applied++
    } else {
      unmatchedAje += part.ajeTotal
      unmatchedRje += part.rjeTotal
    }
  }
  if (Math.abs(unmatchedAje) > 0.005 || Math.abs(unmatchedRje) > 0.005) {
    const fallback = allRows[0]
    fallback.closingAJE = parseNum(fallback.closingAJE) + unmatchedAje
    fallback.closingRJE = parseNum(fallback.closingRJE) + unmatchedRje
    fallback.closingAdjusted = parseNum(fallback.closingUnadjusted)
      + parseNum(fallback.closingAJE) + parseNum(fallback.closingRJE)
    applied++
  }
  return applied > 0
}
