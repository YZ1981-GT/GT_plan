/**
 * 汇总 F2-29~32 四表截止测试完成度（同 wp allResponses）
 */
import { assessCutoffRow } from './f2CutoffJudgment'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import { F2_CUTOFF_CONFIGS } from '../f2/inspection/f2CutoffSheetConfigs'

export interface F2CutoffSheetOverview {
  sheetCode: string
  title: string
  total: number
  rawCount: number
  finishedCount: number
  uncategorizedCount: number
  crossCount: number
  errorCount: number
  errorAmount: number
  earlyCount: number
  lateCount: number
  missingDocCount: number
  missingBookCount: number
  hasConclusion: boolean
  categoryOk: boolean
}

export interface F2CutoffBundleOverview {
  sheets: F2CutoffSheetOverview[]
  totalSamples: number
  totalCross: number
  totalErrors: number
  allHaveSamples: boolean
  allCategorized: boolean
  allHaveConclusions: boolean
}

function loadRows(map: Map<string, ChecklistResponse>, sheetCode: string): Array<Record<string, unknown>> {
  const raw = readRowJson(map.get(`${sheetCode}-rows`))
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function loadMeta(map: Map<string, ChecklistResponse>, sheetCode: string): Record<string, string> {
  const raw = map.get(`${sheetCode}-meta`)?.remark
  if (!raw) return {}
  try {
    return JSON.parse(raw) as Record<string, string>
  } catch {
    return {}
  }
}

export function buildF2CutoffBundleOverview(
  allResponses: Map<string, ChecklistResponse>,
  fallbackCutoff = '',
): F2CutoffBundleOverview {
  const sheets: F2CutoffSheetOverview[] = []

  for (const code of ['F2-29', 'F2-30', 'F2-31', 'F2-32'] as const) {
    const cfg = F2_CUTOFF_CONFIGS[code]
    const rows = loadRows(allResponses, code)
    const meta = loadMeta(allResponses, code)
    const pe = meta.cutoffDate || fallbackCutoff
    let crossCount = 0
    let errorCount = 0
    let errorAmount = 0
    let earlyCount = 0
    let lateCount = 0
    let missingDocCount = 0
    let missingBookCount = 0
    let rawCount = 0
    let finishedCount = 0
    let uncategorizedCount = 0

    for (const r of rows) {
      const invCategory = String(r.invCategory || '')
      if (invCategory === 'raw') rawCount += 1
      else if (invCategory === 'finished') finishedCount += 1
      else uncategorizedCount += 1

      const docDate = String(r.docDate || '')
      const bookDate = String(r.bookDate || '')
      const amount = Number(r.amount || 0) || 0
      const judge = assessCutoffRow({
        docDate,
        bookDate,
        periodEnd: pe,
        voucherNo: String(r.voucherNo || ''),
        docNo: String(r.docNo || ''),
        amount,
        docAmount: r.docAmount != null ? Number(r.docAmount) : undefined,
        overrideCorrect: (r.isCorrectOverride as boolean | null) ?? null,
      })
      if (judge.isCrossPeriod) {
        crossCount += 1
      }
      if (!judge.isCorrect) {
        errorCount += 1
        errorAmount += amount
      }
      if (judge.timing === 'early_book') earlyCount += 1
      if (judge.timing === 'late_book') lateCount += 1
      if (judge.evidenceGap === 'missing_doc') missingDocCount += 1
      if (judge.evidenceGap === 'missing_book') missingBookCount += 1
    }

    const conclusion =
      (allResponses.get(`${code}-conclusion`)?.remark || '').trim()
      || (allResponses.get(`${code}-audit-conclusion`)?.remark || '').trim()

    sheets.push({
      sheetCode: code,
      title: cfg?.title || code,
      total: rows.length,
      rawCount,
      finishedCount,
      uncategorizedCount,
      crossCount,
      errorCount,
      errorAmount,
      earlyCount,
      lateCount,
      missingDocCount,
      missingBookCount,
      hasConclusion: !!conclusion,
      categoryOk: rows.length === 0 || uncategorizedCount === 0,
    })
  }

  return {
    sheets,
    totalSamples: sheets.reduce((s, x) => s + x.total, 0),
    totalCross: sheets.reduce((s, x) => s + x.crossCount, 0),
    totalErrors: sheets.reduce((s, x) => s + x.errorCount, 0),
    allHaveSamples: sheets.every((s) => s.total > 0),
    allCategorized: sheets.every((s) => s.categoryOk),
    allHaveConclusions: sheets.every((s) => s.hasConclusion || s.total === 0),
  }
}
