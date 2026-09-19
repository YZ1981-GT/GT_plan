/**
 * G10-4 分类检查 ↔ G10-2 / G10-3 跨表辅助
 */
import type { G10ClassificationRow, G10Yn } from './g10ClassificationModel'
import { hasClassificationBasis } from './g10ClassificationModel'
import { G10_ACCOUNT_CODE } from './g10Constants'
import { inferG10AdjudicationRowKey } from './g10AccountMatch'
import type { G10AdjustmentRow } from './useG10Adjustment'
import { parseNum } from './useG10FormulaEngine'

export const G10_RECLASS_COUNTER_ACCOUNT = { code: '2501', name: '其他流动负债' } as const

/** 识别由 G10-4 分类检查推送的重分类 RJE 草稿 */
export function isG10ClassificationAdjDraft(row: {
  summary?: string
  remark?: string
  indexRef?: string
}): boolean {
  const summary = String(row.summary || '')
  const remark = String(row.remark || '')
  const indexRef = String(row.indexRef || '')
  if (indexRef === 'G10-4' || indexRef.includes('G10-4')) return true
  if (/G10-4\s*重分类/.test(summary)) return true
  if (/由 G10-4 分类检查生成/.test(remark)) return true
  return false
}

export function countG10ClassificationAdjDrafts(
  rows: Array<{ summary?: string; remark?: string; indexRef?: string }>,
): number {
  return rows.filter(isG10ClassificationAdjDraft).length
}

/** 按摘要前缀统计 G10-4 重分类项目数（每组 2 行分录） */
export function countG10ClassificationDraftProjects(
  rows: Array<{ summary?: string; remark?: string; indexRef?: string }>,
): number {
  const summaries = new Set(
    rows.filter(isG10ClassificationAdjDraft).map((r) => String(r.summary || '').trim()).filter(Boolean),
  )
  return summaries.size
}

export const G10_REVIEW_CLASSIFICATION_ADJ_KEY = 'g10:review-classification-adj'

export type G10ReclassDraftStatus = 'none' | 'pending' | 'confirmed'
export type G10DraftReviewStatus = 'pending' | 'confirmed'

export function buildClassificationDraftSummary(issue: G10ClassificationIssue): string {
  return `G10-4 重分类—${issue.liabilityName}：${issue.reason}`
}

export function extractClassificationSourceId(row: {
  classificationSourceId?: string
}): string | undefined {
  const id = String(row.classificationSourceId || '').trim()
  return id || undefined
}

/** 待复核的 G10-4 草稿（已确认的不高亮） */
export function isPendingG10ClassificationAdjDraft(row: {
  summary?: string
  remark?: string
  indexRef?: string
  draftReviewStatus?: string
}): boolean {
  return isG10ClassificationAdjDraft(row) && row.draftReviewStatus !== 'confirmed'
}

export function countPendingG10ClassificationAdjDrafts(
  rows: Array<{ summary?: string; remark?: string; indexRef?: string; draftReviewStatus?: string }>,
): number {
  return rows.filter(isPendingG10ClassificationAdjDraft).length
}

export function countPendingG10ClassificationDraftProjects(
  rows: Array<{ summary?: string; remark?: string; indexRef?: string; draftReviewStatus?: string }>,
): number {
  const summaries = new Set(
    rows.filter(isPendingG10ClassificationAdjDraft).map((r) => String(r.summary || '').trim()).filter(Boolean),
  )
  return summaries.size
}

/** G10-4 行 id → 重分类草稿状态 */
export function buildReclassStatusMap(
  adjRows: Array<{
    classificationSourceId?: string
    summary?: string
    remark?: string
    indexRef?: string
    draftReviewStatus?: string
  }>,
): Map<string, G10ReclassDraftStatus> {
  const map = new Map<string, G10ReclassDraftStatus>()
  for (const row of adjRows) {
    if (!isG10ClassificationAdjDraft(row)) continue
    const sourceId = extractClassificationSourceId(row)
    if (!sourceId) continue
    const next: G10ReclassDraftStatus = row.draftReviewStatus === 'confirmed' ? 'confirmed' : 'pending'
    const prev = map.get(sourceId)
    if (!prev || prev === 'none') {
      map.set(sourceId, next)
      continue
    }
    if (prev === 'confirmed' && next === 'pending') map.set(sourceId, 'pending')
  }
  return map
}

/** 无 sourceId 的旧草稿：按项目名称在摘要中匹配 */
export function resolveReclassStatusForClassificationRow(
  row: Pick<G10ClassificationRow, 'id' | 'liabilityName'>,
  adjRows: Array<{
    classificationSourceId?: string
    summary?: string
    remark?: string
    indexRef?: string
    draftReviewStatus?: string
  }>,
): G10ReclassDraftStatus {
  const map = buildReclassStatusMap(adjRows)
  const direct = map.get(row.id)
  if (direct) return direct
  const name = String(row.liabilityName || '').trim()
  if (!name) return 'none'
  const hit = adjRows.find(
    (r) => isG10ClassificationAdjDraft(r) && String(r.summary || '').includes(name),
  )
  if (!hit) return 'none'
  return hit.draftReviewStatus === 'confirmed' ? 'confirmed' : 'pending'
}

export function reclassStatusLabel(status: G10ReclassDraftStatus): string {
  if (status === 'pending') return '待复核'
  if (status === 'confirmed') return '已确认'
  return '—'
}

/** 标记 G10-4 草稿为已复核 */
export function markClassificationDraftsConfirmed<T extends {
  summary?: string
  remark?: string
  indexRef?: string
  classificationSourceId?: string
  draftReviewStatus?: string
}>(
  rows: T[],
  options?: { sourceIds?: string[]; summaries?: string[]; allPending?: boolean },
): T[] {
  const sourceSet = options?.sourceIds?.length ? new Set(options.sourceIds) : null
  const summarySet = options?.summaries?.length ? new Set(options.summaries) : null
  const allPending = options?.allPending ?? (!sourceSet && !summarySet)
  return rows.map((r) => {
    if (!isG10ClassificationAdjDraft(r)) return r
    if (r.draftReviewStatus === 'confirmed') return r
    const hitById = sourceSet && r.classificationSourceId && sourceSet.has(r.classificationSourceId)
    const hitBySummary = summarySet && summarySet.has(String(r.summary || '').trim())
    if (allPending || hitById || hitBySummary) {
      return { ...r, draftReviewStatus: 'confirmed' as const }
    }
    return r
  })
}

export const G10_CLASSIFICATION_DRAFT_REVIEWED_EVENT = 'g10:classification-draft-reviewed'

export function hasTradingBasis(row: Pick<G10ClassificationRow, 'tradingNearTermSale' | 'tradingPortfolioShortTerm' | 'tradingDerivative'>): boolean {
  return row.tradingNearTermSale === 'yes' || row.tradingPortfolioShortTerm === 'yes' || row.tradingDerivative === 'yes'
}

export function hasDesignatedBasis(row: Pick<G10ClassificationRow, 'designatedMismatch' | 'designatedFvManagement'>): boolean {
  return row.designatedMismatch === 'yes' || row.designatedFvManagement === 'yes'
}

/** G10-2 类别与 G10-4 勾选是否一致 */
export function getCategoryMismatchReason(
  row: G10ClassificationRow,
  liabilityCategory: string,
): string | null {
  if (!liabilityCategory?.trim()) return null
  if (!row.liabilityName?.trim() && !row.closingBookValue) return null
  const trading = hasTradingBasis(row)
  const designated = hasDesignatedBasis(row)
  if (liabilityCategory === '指定类') {
    if (!designated && !hasClassificationBasis(row)) return 'G10-2为指定类但未勾选初始指定依据'
    if (!designated && trading) return 'G10-2为指定类但仅勾选交易性依据，请复核'
  }
  if (liabilityCategory === '交易类') {
    if (!trading && !hasClassificationBasis(row)) return 'G10-2为交易类但未勾选交易性依据'
    if (!trading && designated) return 'G10-2为交易类但仅勾选初始指定依据，请复核'
  }
  return null
}

export interface G10ClassificationIssue {
  rowId: string
  liabilityName: string
  closingBookValue: number
  reason: string
  liabilityType: string
  liabilityCategory: string
}

/** 需提请重分类/调整的项目 */
export function collectClassificationIssues(
  rows: G10ClassificationRow[],
  detailById: Map<string, { liabilityType: string; liabilityCategory: string }>,
): G10ClassificationIssue[] {
  const issues: G10ClassificationIssue[] = []
  for (const row of rows) {
    if (!row.liabilityName?.trim() && !row.closingBookValue) continue
    const detail = row.detailRowId ? detailById.get(row.detailRowId) : undefined
    const category = row.liabilityCategory || detail?.liabilityCategory || ''
    const mismatch = getCategoryMismatchReason(row, category)
    if (!hasClassificationBasis(row)) {
      issues.push({
        rowId: row.id,
        liabilityName: row.liabilityName || `第${row.seq}行`,
        closingBookValue: row.closingBookValue,
        reason: mismatch || '未勾选任一 FVTPL 分类依据',
        liabilityType: detail?.liabilityType || '',
        liabilityCategory: category,
      })
      continue
    }
    if (mismatch) {
      issues.push({
        rowId: row.id,
        liabilityName: row.liabilityName || `第${row.seq}行`,
        closingBookValue: row.closingBookValue,
        reason: mismatch,
        liabilityType: detail?.liabilityType || '',
        liabilityCategory: category,
      })
    }
  }
  return issues
}

function genAdjId(): string {
  return `g10cl-adj-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 4)}`
}

/** 为单个问题项目生成平衡 RJE 草稿（借 2101 / 贷 2501） */
export function buildReclassificationDraftPair(issue: G10ClassificationIssue, seq: number): G10AdjustmentRow[] {
  const amount = Math.abs(parseNum(issue.closingBookValue))
  if (amount < 0.005) return []
  const summary = buildClassificationDraftSummary(issue)
  const adjudicationRowKey = inferG10AdjudicationRowKey({
    liabilityType: issue.liabilityType,
    liabilityName: issue.liabilityName,
    summary,
  })
  const base = {
    entryType: 'RJE' as const,
    date: new Date().toISOString().slice(0, 10),
    summary,
    preparedBy: '',
    remark: `由 G10-4 分类检查生成；请复核对方科目及金额后确认。类别：${issue.liabilityCategory || '—'}`,
    indexRef: 'G10-4',
    liabilityType: issue.liabilityType,
    adjudicationRowKey,
    classificationSourceId: issue.rowId,
    draftReviewStatus: 'pending' as const,
  }
  return [
    {
      rowId: genAdjId(),
      seq,
      ...base,
      accountCode: G10_ACCOUNT_CODE,
      accountName: '交易性金融负债',
      debitAmount: amount,
      creditAmount: 0,
    },
    {
      rowId: genAdjId(),
      seq: seq + 1,
      ...base,
      accountCode: G10_RECLASS_COUNTER_ACCOUNT.code,
      accountName: G10_RECLASS_COUNTER_ACCOUNT.name,
      debitAmount: 0,
      creditAmount: amount,
    },
  ]
}

export function buildAllReclassificationDrafts(issues: G10ClassificationIssue[]): G10AdjustmentRow[] {
  const drafts: G10AdjustmentRow[] = []
  let seq = 1
  for (const issue of issues) {
    const pair = buildReclassificationDraftPair(issue, seq)
    drafts.push(...pair)
    seq += pair.length
  }
  return drafts
}

/** 合并至 G10-3，跳过已存在同摘要的草稿 */
export function mergeReclassificationDraftsIntoAdj(
  existingJson: string | null | undefined,
  drafts: G10AdjustmentRow[],
): { merged: string; added: number } {
  let existing: G10AdjustmentRow[] = []
  try {
    const parsed = existingJson ? JSON.parse(existingJson) : []
    existing = Array.isArray(parsed) ? parsed : []
  } catch {
    existing = []
  }
  const summaries = new Set(existing.map((r) => String(r.summary || '').trim()).filter(Boolean))
  const toAdd = drafts.filter((d) => !summaries.has(String(d.summary || '').trim()))
  if (!toAdd.length) return { merged: existingJson || '[]', added: 0 }
  const next = [...existing, ...toAdd].map((r, i) => ({ ...r, seq: i + 1 }))
  return { merged: JSON.stringify(next), added: toAdd.length }
}

/** 按 G10-2 类别 + 负债类型预填分类依据 */
export function prefillBasisFromDetail(
  liabilityType: string,
  isDerivative: boolean,
  liabilityCategory?: string,
): Partial<Pick<G10ClassificationRow,
  'tradingNearTermSale' | 'tradingPortfolioShortTerm' | 'tradingDerivative' | 'designatedMismatch' | 'designatedFvManagement'
>> {
  const patch: Partial<Pick<G10ClassificationRow,
    'tradingNearTermSale' | 'tradingPortfolioShortTerm' | 'tradingDerivative' | 'designatedMismatch' | 'designatedFvManagement'
  >> = {}

  if (liabilityCategory === '指定类') {
    patch.designatedMismatch = 'yes'
    return patch
  }

  if (isDerivative || liabilityType === '衍生金融负债') {
    patch.tradingDerivative = 'yes'
    return patch
  }
  if (liabilityType === '卖出回购' || liabilityType === '融券负债') {
    patch.tradingNearTermSale = 'yes'
    return patch
  }
  if (liabilityType === '交易性债券' || liabilityType === '结构化产品') {
    patch.tradingPortfolioShortTerm = 'yes'
    return patch
  }
  if (liabilityCategory === '交易类') {
    patch.tradingNearTermSale = 'yes'
  }
  return patch
}

export function ynFromBool(v: boolean | null | undefined): G10Yn {
  if (v === true) return 'yes'
  if (v === false) return 'no'
  return ''
}
