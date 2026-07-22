/**
 * G10-8 衍生工具核查 ↔ G10-2 衍生负债明细 / G10-3 调整联动
 */
import { matchG10LiabilityKey, inferG10AdjudicationRowKey } from './g10AccountMatch'
import {
  aggregateG10AdjustmentAjeRjeByRow,
} from './g10AdjStorage'
import { G10_DETAIL_ROWS_KEY, commitG10AdjustmentWritebackFromRows, parseG10DetailRows } from './g10CrossHelpers'
import { G10_ACCOUNT_CODE } from './g10Constants'
import { G10_ADJ_KEY } from './g10FvCrossHelpers'
import type { G10DetailRow } from './useG10Detail'
import type { ChecklistResponse } from './useF1FormData'
import type { G10DerivativeRow } from './useG10DerivativeCheck'

export const G10_DERIVATIVE_DETAIL_LINKS_KEY = 'G10-derivative-detail-links'

export interface G10DerivativeDetailLink {
  detailRowId: string
  liabilityName: string
}

export function isG10DerivativeDetailRow(row: Pick<G10DetailRow, 'isDerivative' | 'liabilityType' | 'liabilityName'>): boolean {
  if (row.isDerivative) return true
  const type = String(row.liabilityType ?? '')
  if (type.includes('衍生')) return true
  return /衍生|期权|互换|期货|远期/.test(String(row.liabilityName ?? ''))
}

export function filterG10DerivativeDetailRows(rows: G10DetailRow[]): G10DetailRow[] {
  return rows.filter(isG10DerivativeDetailRow)
}

export function parseG10DerivativeDetailLinks(json: string | null | undefined): G10DerivativeDetailLink[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function buildG10DerivativeContractNoteFromDetails(rows: G10DetailRow[]): string {
  if (!rows.length) return ''
  return rows.map((r) => {
    const parts = [`【${r.liabilityName}】`]
    if (r.hostContractDesc?.trim()) parts.push(`主合同：${r.hostContractDesc.trim()}`)
    if (r.embeddedDerivativeJudgment?.trim()) parts.push(`嵌入衍生：${r.embeddedDerivativeJudgment.trim()}`)
    if (Math.abs(r.closingAdjusted) > 0.005) {
      parts.push(`期末审定 ${r.closingAdjusted.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`)
    }
    return parts.join('；')
  }).join('\n')
}

/** 从 G10-2 读取衍生行并写入链接清单 */
export function pullG10DerivativeLinksFromDetail(
  responses: Map<string, ChecklistResponse>,
): G10DerivativeDetailLink[] {
  const details = filterG10DerivativeDetailRows(
    parseG10DetailRows(responses.get(G10_DETAIL_ROWS_KEY)?.remark),
  )
  return details.map((d) => ({ detailRowId: d.rowId, liabilityName: d.liabilityName }))
}

/** 将 G10-8 结论/向导摘要回写 G10-2 衍生行 */
export function pushG10DerivativeCheckToDetail(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  input: {
    links: G10DerivativeDetailLink[]
    wizardConclusion?: string
    overallConclusion?: string
    indexRef?: string
  },
): number {
  const raw = responses.get(G10_DETAIL_ROWS_KEY)?.remark
  if (!raw || !input.links.length) return 0
  let details: Record<string, unknown>[]
  try {
    details = JSON.parse(raw)
    if (!Array.isArray(details)) return 0
  } catch {
    return 0
  }

  const linkById = new Map(input.links.map((l) => [l.detailRowId, l]))
  const linkByKey = new Map(input.links.map((l) => [matchG10LiabilityKey(l.liabilityName), l]))
  const judgmentParts = [input.wizardConclusion, input.overallConclusion].filter(Boolean)
  const judgmentSuffix = judgmentParts.length
    ? judgmentParts.join('；').slice(0, 500)
    : ''
  const indexRef = input.indexRef || 'G10-8'

  let n = 0
  const next = details.map((d, i) => {
    const rowId = String(d.rowId ?? d.id ?? '')
    const key = matchG10LiabilityKey(String(d.liabilityName ?? ''))
    const hit = linkById.get(rowId) || linkByKey.get(key)
    if (!hit) return d
    n += 1
    const prevJudgment = String(d.embeddedDerivativeJudgment ?? '')
    const mergedJudgment = judgmentSuffix
      ? (prevJudgment.includes('G10-8') ? prevJudgment : [prevJudgment, `[${indexRef}] ${judgmentSuffix}`].filter(Boolean).join('\n'))
      : prevJudgment
    return {
      ...d,
      isDerivative: true,
      liabilityType: d.liabilityType || '衍生金融负债',
      embeddedDerivativeJudgment: mergedJudgment,
      remark: String(d.remark ?? '').includes('G10-8')
        ? d.remark
        : [String(d.remark ?? '').trim(), indexRef].filter(Boolean).join(' · '),
    }
  })

  if (n) {
    debouncedSave(G10_DETAIL_ROWS_KEY, { remark: JSON.stringify(next) })
    try {
      window.dispatchEvent(new CustomEvent('g10:detail-updated', {
        detail: { source: 'G10-8→G10-2', timestamp: Date.now() },
      }))
    } catch { /* silent */ }
  }
  return n
}

export interface G10DerivativeIssue {
  rowId: string
  sectionNo: string
  sectionTitle: string
  checkItem: string
  riskLevel: string
  auditConclusion: string
}

/** 识别 G10-8 推送至 G10-3 的调整行 */
export function isFromG108(row: {
  summary?: string
  remark?: string
  indexRef?: string
}): boolean {
  const indexRef = String(row.indexRef || '')
  if (indexRef === 'G10-8' || indexRef.includes('G10-8')) return true
  const summary = String(row.summary || '')
  if (/^G10-8\s*衍生不合规/.test(summary)) return true
  if (/来自 G10-8/.test(String(row.remark || ''))) return true
  return false
}

/** 不合规问卷行（排除 N/A） */
export function collectG10DerivativeNonCompliantIssues(rows: G10DerivativeRow[]): G10DerivativeIssue[] {
  return rows
    .filter((r) => r.compliance === 'non_compliant')
    .map((r) => ({
      rowId: r.rowId,
      sectionNo: r.sectionNo,
      sectionTitle: r.sectionTitle,
      checkItem: r.checkItem,
      riskLevel: r.riskLevel || '',
      auditConclusion: r.auditConclusion || '',
    }))
}

function buildDerivativeIssueSummary(issue: G10DerivativeIssue): string {
  const label = issue.checkItem?.trim() || issue.sectionTitle || '未命名检查项'
  return `G10-8 衍生不合规：${issue.sectionNo} ${label}`.trim()
}

/** 不合规项 → G10-3 备忘 AJE（金额 0，待追查补录） */
export function pushG10DerivativeIssuesToAdjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  issues: G10DerivativeIssue[],
): { pushed: number; skipped: number } {
  if (!issues.length) return { pushed: 0, skipped: 0 }

  let existing: Record<string, unknown>[] = []
  const raw = responses.get(G10_ADJ_KEY)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch { /* ignore */ }
  }

  const summaries = new Set(
    existing.map((r) => String(r.summary || '').trim()).filter(Boolean),
  )
  const toPush = issues.filter((it) => !summaries.has(buildDerivativeIssueSummary(it)))
  const skipped = issues.length - toPush.length
  if (!toPush.length) return { pushed: 0, skipped }

  const added: Record<string, unknown>[] = []
  let seqBase = existing.length
  toPush.forEach((issue, i) => {
    const summary = buildDerivativeIssueSummary(issue)
    const rowKey = inferG10AdjudicationRowKey({
      liabilityType: '衍生金融负债',
      summary,
    })
    const base = {
      date: new Date().toISOString().slice(0, 10),
      entryType: 'AJE',
      preparedBy: '',
      indexRef: 'G10-8',
      liabilityType: '衍生金融负债',
      adjudicationRowKey: rowKey,
      remark: [
        '来自 G10-8 衍生工具核查；金额待追查补录',
        issue.riskLevel ? `风险：${issue.riskLevel}` : '',
        issue.auditConclusion ? `结论：${issue.auditConclusion}` : '',
      ].filter(Boolean).join('；'),
    }
    const idSuffix = `${Date.now().toString(36)}-${i}`
    added.push({
      ...base,
      rowId: `g10dr-adj-${idSuffix}a`,
      seq: seqBase + added.length + 1,
      summary,
      accountCode: G10_ACCOUNT_CODE,
      accountName: '交易性金融负债',
      debitAmount: 0,
      creditAmount: 0,
    })
    added.push({
      ...base,
      rowId: `g10dr-adj-${idSuffix}b`,
      seq: seqBase + added.length + 1,
      summary: `${summary}（对方科目待复核）`,
      accountCode: '2501',
      accountName: '其他流动负债',
      debitAmount: 0,
      creditAmount: 0,
    })
    seqBase = existing.length + added.length
  })

  const merged = [...existing, ...added]
  debouncedSave(G10_ADJ_KEY, { remark: JSON.stringify(merged) })

  commitG10AdjustmentWritebackFromRows(responses, debouncedSave, merged as Parameters<typeof aggregateG10AdjustmentAjeRjeByRow>[0], {
    source: 'G10-8',
    offerDisclosurePull: toPush.length > 0,
  })

  return { pushed: toPush.length, skipped }
}
