/**
 * G7-5 被投资单位财务信息 — 纯函数模型
 * 变动额/率、分组 hydrate、异常变动与关键项目完整性校验。
 */
import { useDecimalCalc } from '@/composables/useDecimalCalc'

const moneyCalc = useDecimalCalc({ dp: 2 })
const rateCalc = useDecimalCalc({ dp: 4 })

export type G7FinancialAuditStatus = '已审' | '未审' | '待确认' | ''

export interface G7FinancialInfoRow {
  id: string
  seq: number
  investeeName: string
  reportItem: string
  priorAmount: number
  currentAmount: number
  changeAmount: number
  changeRate: number | null
  analysisNote: string
  dataSource: string
  auditStatus: G7FinancialAuditStatus
  remark: string
}

export interface G7FinancialInfoGroup {
  investeeName: string
  investeeId?: string
  rows: G7FinancialInfoRow[]
}

export interface G7FinancialInfoIssue {
  severity: 'error' | 'warning'
  rowId?: string
  message: string
}

/** 新建分组默认报表项目（资产/负债/净资产/损益） */
export const DEFAULT_FINANCIAL_REPORT_ITEMS = [
  '总资产', '流动资产', '非流动资产',
  '总负债', '流动负债', '非流动负债',
  '所有者权益（净资产）',
  '营业收入', '营业成本', '净利润',
] as const

/** 权益法下游常用关键项目（名称模糊匹配） */
export const KEY_FINANCIAL_REPORT_PATTERNS = [
  { key: 'netProfit', label: '净利润', patterns: [/净利润/, /净亏损/, /综合收益总额/] },
  { key: 'netAssets', label: '所有者权益/净资产', patterns: [/所有者权益/, /净资产/] },
] as const

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function parseFinancialAmount(value: unknown): number {
  if (value === '' || value == null) return 0
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

/** 变动额 = 本年 − 上年 */
export function calcFinancialChangeAmount(currentAmount: number, priorAmount: number): number {
  return Number(moneyCalc.sub(parseFinancialAmount(currentAmount), parseFinancialAmount(priorAmount)))
}

/**
 * 变动率 = 变动额 / 上年（小数，如 0.5=50%）
 * 上年为 0 时返回 null（避免除零）
 */
export function calcFinancialChangeRate(changeAmount: number, priorAmount: number): number | null {
  const prior = parseFinancialAmount(priorAmount)
  if (prior === 0) return null
  return Number(rateCalc.div(parseFinancialAmount(changeAmount), prior))
}

/** |变动率| > 50% → UI 橙色高亮 */
export function isFinancialRateWarning(rate: number | null | undefined): boolean {
  if (rate == null || !Number.isFinite(rate)) return false
  return Math.abs(rate) > 0.5
}

export function recalcFinancialInfoRow(row: G7FinancialInfoRow): G7FinancialInfoRow {
  row.changeAmount = calcFinancialChangeAmount(row.currentAmount, row.priorAmount)
  row.changeRate = calcFinancialChangeRate(row.changeAmount, row.priorAmount)
  return row
}

export function createFinancialInfoRow(
  investeeName: string,
  seq: number,
  reportItem = '',
): G7FinancialInfoRow {
  return recalcFinancialInfoRow({
    id: uid('g7-5'),
    seq,
    investeeName,
    reportItem,
    priorAmount: 0,
    currentAmount: 0,
    changeAmount: 0,
    changeRate: null,
    analysisNote: '',
    dataSource: '',
    auditStatus: '未审',
    remark: '',
  })
}

export function createDefaultFinancialGroup(
  investeeName: string,
  investeeId = '',
): G7FinancialInfoGroup {
  const rows = DEFAULT_FINANCIAL_REPORT_ITEMS.map((item, idx) =>
    createFinancialInfoRow(investeeName, idx + 1, item),
  )
  return {
    investeeName,
    investeeId: investeeId || undefined,
    rows,
  }
}

function asAuditStatus(value: unknown): G7FinancialAuditStatus {
  return value === '已审' || value === '未审' || value === '待确认' ? value : '未审'
}

export function mapRawFinancialInfoRow(
  raw: Record<string, any>,
  investeeName: string,
  index: number,
): G7FinancialInfoRow {
  const row = createFinancialInfoRow(
    investeeName,
    Number(raw.seq || index + 1),
    String(raw.reportItem ?? raw.report_item ?? ''),
  )
  Object.assign(row, {
    id: String(raw.id || row.id),
    priorAmount: parseFinancialAmount(raw.priorAmount ?? raw.prior_amount),
    currentAmount: parseFinancialAmount(raw.currentAmount ?? raw.current_amount),
    analysisNote: String(raw.analysisNote ?? raw.analysis_note ?? ''),
    dataSource: String(raw.dataSource ?? raw.data_source ?? ''),
    auditStatus: asAuditStatus(raw.auditStatus ?? raw.audit_status),
    remark: String(raw.remark ?? ''),
  })
  return recalcFinancialInfoRow(row)
}

/** 从 checklist conclusion / htmlData 解析分组 */
export function parseFinancialInfoGroups(payload: unknown): G7FinancialInfoGroup[] {
  let data = payload
  if (typeof data === 'string') {
    try { data = JSON.parse(data) } catch { return [] }
  }
  if (!data || typeof data !== 'object') return []

  const root = data as any
  const rawGroups = root.groups
  if (Array.isArray(rawGroups) && rawGroups.length > 0) {
    return rawGroups.map((g: any) => {
      const name = String(g.investeeName ?? g.investee_name ?? g.name ?? '未命名')
      const investeeId = String(g.investeeId ?? g.investee_id ?? '').trim()
      const rows = (Array.isArray(g.rows) ? g.rows : []).map((r: any, idx: number) =>
        mapRawFinancialInfoRow(r, name, idx),
      )
      return {
        investeeName: name,
        investeeId: investeeId || undefined,
        rows,
      }
    })
  }

  const rawRows = Array.isArray(root.rows)
    ? root.rows
    : (Array.isArray(root) ? root : [])
  if (!rawRows.length) return []

  const groupMap = new Map<string, G7FinancialInfoRow[]>()
  for (const r of rawRows) {
    const name = String(r.investeeName ?? r.investee_name ?? '未分组')
    if (!groupMap.has(name)) groupMap.set(name, [])
    const list = groupMap.get(name)!
    list.push(mapRawFinancialInfoRow(r, name, list.length))
  }
  return [...groupMap.entries()].map(([investeeName, rows]) => ({ investeeName, rows }))
}

export function flattenFinancialInfoGroups(groups: G7FinancialInfoGroup[]): G7FinancialInfoRow[] {
  return groups.flatMap(g => g.rows)
}

export function serializeFinancialInfoPayload(groups: G7FinancialInfoGroup[]): string {
  return JSON.stringify({
    rows: flattenFinancialInfoGroups(groups),
    groups: groups.map(g => ({
      investeeName: g.investeeName,
      investeeId: g.investeeId,
      rows: g.rows,
    })),
  })
}

function itemMatches(reportItem: string, patterns: readonly RegExp[]): boolean {
  const text = reportItem.trim()
  return patterns.some(p => p.test(text))
}

export function validateFinancialInfoGroups(
  groups: G7FinancialInfoGroup[],
): G7FinancialInfoIssue[] {
  const issues: G7FinancialInfoIssue[] = []

  for (const group of groups) {
    const name = group.investeeName.trim() || '未命名'
    if (!group.rows.length) {
      issues.push({ severity: 'warning', message: `「${name}」尚无财务信息行` })
      continue
    }

    for (const row of group.rows) {
      if (isFinancialRateWarning(row.changeRate) && !row.analysisNote.trim()) {
        const item = row.reportItem.trim() || `第${row.seq}行`
        issues.push({
          severity: 'warning',
          rowId: row.id,
          message: `「${name}」${item}：|变动率|超过50%，请在分析说明中补充原因`,
        })
      }
    }

    for (const key of KEY_FINANCIAL_REPORT_PATTERNS) {
      const hit = group.rows.some(r => itemMatches(r.reportItem, key.patterns))
      if (!hit) {
        issues.push({
          severity: 'warning',
          message: `「${name}」缺少「${key.label}」项目，将影响 G7-14/G7-13/G7-16 带入`,
        })
      }
    }
  }

  return issues
}

export interface G7FinancialUnauditedStats {
  unaudited: number
  pending: number
  total: number
}

/** 未审 / 待确认行数汇总 */
export function countUnauditedFinancialRows(groups: G7FinancialInfoGroup[]): G7FinancialUnauditedStats {
  let unaudited = 0
  let pending = 0
  for (const group of groups) {
    for (const row of group.rows) {
      if (row.auditStatus === '未审') unaudited += 1
      else if (row.auditStatus === '待确认') pending += 1
    }
  }
  return { unaudited, pending, total: unaudited + pending }
}

/**
 * 滚存：上年金额 ← 本年金额。
 * clearCurrent=true 时清空本年金额（新年度开账）；默认保留本年便于改数。
 */
export function rollForwardFinancialPriorAmounts(
  groups: G7FinancialInfoGroup[],
  opts: { clearCurrent?: boolean } = {},
): number {
  const clearCurrent = opts.clearCurrent === true
  let touched = 0
  for (const group of groups) {
    for (const row of group.rows) {
      row.priorAmount = parseFinancialAmount(row.currentAmount)
      if (clearCurrent) row.currentAmount = 0
      recalcFinancialInfoRow(row)
      touched += 1
    }
  }
  return touched
}

/** 分组块预估高度（外层虚拟列表 spacer） */
export const G7_FINANCIAL_GROUP_HEADER_H = 44
export const G7_FINANCIAL_ROW_H = 36
export const G7_FINANCIAL_TABLE_MAX_H = 400
/** 超过该分组数或总行数启用外层虚拟滚动 */
export const G7_FINANCIAL_VIRTUAL_GROUP_THRESHOLD = 6
export const G7_FINANCIAL_VIRTUAL_ROW_THRESHOLD = 40

export function estimateFinancialGroupHeight(
  group: G7FinancialInfoGroup,
  expanded: boolean,
): number {
  if (!expanded) return G7_FINANCIAL_GROUP_HEADER_H + 8
  const body = Math.min(
    group.rows.length * G7_FINANCIAL_ROW_H + 48,
    G7_FINANCIAL_TABLE_MAX_H + 48,
  )
  return G7_FINANCIAL_GROUP_HEADER_H + body + 8
}

export function shouldUseFinancialGroupVirtual(
  groupCount: number,
  rowCount: number,
): boolean {
  return groupCount >= G7_FINANCIAL_VIRTUAL_GROUP_THRESHOLD
    || rowCount > G7_FINANCIAL_VIRTUAL_ROW_THRESHOLD
}

export interface G7FinancialVirtualWindow {
  start: number
  end: number
  offsetY: number
  totalHeight: number
}

/** 根据 scrollTop 计算可见分组窗口（含 buffer） */
export function computeFinancialGroupVirtualWindow(
  heights: number[],
  scrollTop: number,
  viewportHeight: number,
  buffer = 2,
): G7FinancialVirtualWindow {
  const totalHeight = heights.reduce((s, h) => s + h, 0)
  if (!heights.length) {
    return { start: 0, end: 0, offsetY: 0, totalHeight: 0 }
  }
  let acc = 0
  let start = 0
  for (let i = 0; i < heights.length; i += 1) {
    if (acc + heights[i] > scrollTop) {
      start = i
      break
    }
    acc += heights[i]
    start = i
  }
  start = Math.max(0, start - buffer)
  let offsetY = 0
  for (let i = 0; i < start; i += 1) offsetY += heights[i]

  let end = start
  let visible = 0
  const limit = scrollTop + viewportHeight
  acc = offsetY
  while (end < heights.length && (acc < limit || end - start < buffer * 2 + 1)) {
    acc += heights[end]
    end += 1
    visible += 1
    if (visible > 30) break
  }
  end = Math.min(heights.length, end + buffer)
  return { start, end, offsetY, totalHeight }
}
