/**
 * G10 附注披露跨表勾稽：G10-1 审定、G10-2 Level3、G10-5、G10-6
 */
import { parseNum, calcSubtotal } from './useG10FormulaEngine'
import { G10_CROSS_TOLERANCE } from './g10DisclosureFromAdj'
import type { G10DiscMovementPair } from './g10DisclosureFromAdj'
import { G10_LISTED_MOVEMENT_ROWS } from './g10SchemaRows'
import { G10_DETAIL_ROWS_KEY } from './g10CrossHelpers'
import { G10_FV_KEY } from './g10FvCrossHelpers'
import type { ChecklistResponse } from './useF1FormData'

export const G10_L3_KEY = 'G10-l3-rows'

export type G10DiscCrossCheckCode =
  | 'disclosure-l3-hint'
  | 'disclosure-fv5-vs-l6'
  | 'disclosure-detail-l3-vs-l6'
  | 'disclosure-movement-balance'

export interface G10DiscCrossCheck {
  code: G10DiscCrossCheckCode
  level: 'info' | 'warning'
  message: string
  left?: number
  right?: number
  diff?: number
}

function parseJsonArray(raw: string | null | undefined): Record<string, unknown>[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

function fmt(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function isG10Level3(level: unknown): boolean {
  const s = String(level ?? '').trim().toLowerCase()
  return s === 'level3' || s === 'l3' || s === '3' || s === '第三层次'
}

export function sumG10Level3FvAudited(responses: Map<string, ChecklistResponse>): number {
  return calcSubtotal(
    parseJsonArray(responses.get(G10_FV_KEY)?.remark)
      .filter((r) => isG10Level3(r.fairValueLevel))
      .map((r) => parseNum(r.closingAuditedFV)),
  )
}

export function sumG10L3ReportedClosing(responses: Map<string, ChecklistResponse>): number {
  return calcSubtotal(
    parseJsonArray(responses.get(G10_L3_KEY)?.remark).map((r) => parseNum(r.reportedClosing)),
  )
}

export function sumG10DetailLevel3Closing(responses: Map<string, ChecklistResponse>): number {
  return calcSubtotal(
    parseJsonArray(responses.get(G10_DETAIL_ROWS_KEY)?.remark)
      .filter((r) => isG10Level3(r.fairValueLevel))
      .map((r) => parseNum(r.closingAdjusted ?? r.closingFairValue ?? r.closingBalance)),
  )
}

function mkWarn(
  code: G10DiscCrossCheckCode,
  left: number,
  right: number,
  message: string,
): G10DiscCrossCheck | null {
  const diff = left - right
  if (Math.abs(diff) <= G10_CROSS_TOLERANCE) return null
  return { code, level: 'warning', message, left, right, diff }
}

/** 附注页展示的 Level3 / G10-5 / G10-6 勾稽提示 */
export function buildG10DisclosureCrossChecks(
  responses: Map<string, ChecklistResponse>,
): G10DiscCrossCheck[] {
  const checks: G10DiscCrossCheck[] = []

  const fv5L3 = sumG10Level3FvAudited(responses)
  const l6Reported = sumG10L3ReportedClosing(responses)
  const detailL3 = sumG10DetailLevel3Closing(responses)
  const hasFv5L3 = fv5L3 !== 0
    || parseJsonArray(responses.get(G10_FV_KEY)?.remark).some((r) => isG10Level3(r.fairValueLevel))
  const hasL6 = parseJsonArray(responses.get(G10_L3_KEY)?.remark).length > 0
  const hasL3Balance = Math.abs(fv5L3) > G10_CROSS_TOLERANCE
    || Math.abs(detailL3) > G10_CROSS_TOLERANCE
    || Math.abs(l6Reported) > G10_CROSS_TOLERANCE

  if (hasL3Balance && !hasFv5L3 && !hasL6) {
    checks.push({
      code: 'disclosure-l3-hint',
      level: 'info',
      message: '存在 Level3 相关余额，请在 G10-5 完成公允价值测试并在 G10-6 编制第三层次调节表，附注中说明层次与调节过程。',
    })
  } else if (hasL3Balance && (hasFv5L3 || hasL6)) {
    checks.push({
      code: 'disclosure-l3-hint',
      level: 'info',
      message: `Level3 余额：G10-5 审定 ${fmt(fv5L3)}；G10-6 企业期末 ${fmt(l6Reported)}；G10-2 明细 ${fmt(detailL3)}。附注应披露公允价值层次及调节过程（见 G10-5/G10-6）。`,
    })
  }

  if (hasFv5L3 && hasL6) {
    const c = mkWarn(
      'disclosure-fv5-vs-l6',
      fv5L3,
      l6Reported,
      `G10-5 Level3 审定合计 ${fmt(fv5L3)} 与 G10-6 企业报告期末 ${fmt(l6Reported)} 差异 ${fmt(fv5L3 - l6Reported)}`,
    )
    if (c) checks.push(c)
  }

  if (Math.abs(detailL3) > G10_CROSS_TOLERANCE && hasL6) {
    const c = mkWarn(
      'disclosure-detail-l3-vs-l6',
      detailL3,
      l6Reported,
      `G10-2 Level3 期末合计 ${fmt(detailL3)} 与 G10-6 企业报告期末 ${fmt(l6Reported)} 差异 ${fmt(detailL3 - l6Reported)}`,
    )
    if (c) checks.push(c)
  }

  return checks
}

/** 上市变动表：期初 + 增加 − 减少 = 期末 */
export function buildG10MovementCrossChecks(
  movement: Record<string, G10DiscMovementPair>,
): G10DiscCrossCheck[] {
  const checks: G10DiscCrossCheck[] = []
  const leafKeys = G10_LISTED_MOVEMENT_ROWS.filter((r) => !r.isParent).map((r) => r.rowKey)
  for (const key of leafKeys) {
    const row = movement[key]
    if (!row) continue
    const hasData = Math.abs(row.openingAmount) > 0.005
      || Math.abs(row.increaseAmount) > 0.005
      || Math.abs(row.decreaseAmount) > 0.005
      || Math.abs(row.closingAmount) > 0.005
    if (!hasData) continue
    const expected = row.openingAmount + row.increaseAmount - row.decreaseAmount
    const diff = expected - row.closingAmount
    if (Math.abs(diff) <= G10_CROSS_TOLERANCE) continue
    const label = G10_LISTED_MOVEMENT_ROWS.find((r) => r.rowKey === key)?.label?.trim() ?? key
    checks.push({
      code: 'disclosure-movement-balance',
      level: 'warning',
      message: `变动表「${label}」期初+增加−减少≠期末，差异 ${fmt(diff)}`,
      left: expected,
      right: row.closingAmount,
      diff,
    })
  }
  return checks
}
