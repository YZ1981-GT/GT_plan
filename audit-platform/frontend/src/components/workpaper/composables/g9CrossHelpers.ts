/**
 * G9 跨表勾稽纯函数：G9-1 审定 ↔ 附注；G9-4 Level3 ↔ G9-5；G9-2 Level3 ↔ G9-5
 * 以及 G9-2 辅助核算取数 / 分类合计回写 G9-1
 */
import { parseNum, calcSubtotal, calcAdjustedAmount } from './useG9FormulaEngine'
import {
  G9_DETAIL_KEY,
  G9_FV_KEY,
  G9_L3_KEY,
  matchG9AssetKey,
} from './g9VoucherCross'
import { G9_ACCOUNT_CODE } from './g9Constants'
import { parseG9AdjStore, patchG9AdjRow } from './g9AdjStorage'
import type { ChecklistResponse } from './useF1FormData'

export const G9_CROSS_TOLERANCE = 0.01
export const G9_ADJUDICATED_KEY = 'G9-1-adjudicated-amount'

export type G9CrossCheckCode =
  | 'disclosure-sum-vs-adj'
  | 'fv4-l3-total-vs-g95-reported'
  | 'detail-l3-vs-g95-reported'
  | 'l3-disclosure-note-missing'
  | 'fv4-vs-g95-asset'

export interface G9CrossCheck {
  code: G9CrossCheckCode
  level: 'info' | 'warning'
  message: string
  left: number
  right: number
  diff: number
}

export interface G9AssetMismatch {
  assetName: string
  fv4Audited: number
  g95Reported: number
  diff: number
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

export function isG9Level3(level: unknown): boolean {
  const s = String(level ?? '').trim().toLowerCase()
  return s === 'level3' || s === 'l3' || s === '3' || s === '第三层次'
}

export function sumG9Level3FvAudited(responses: Map<string, ChecklistResponse>): number {
  return calcSubtotal(
    parseJsonArray(responses.get(G9_FV_KEY)?.remark)
      .filter((r) => isG9Level3(r.fairValueLevel))
      .map((r) => parseNum(r.closingAuditedFV)),
  )
}

export function sumG9L3ReportedClosing(responses: Map<string, ChecklistResponse>): number {
  return calcSubtotal(
    parseJsonArray(responses.get(G9_L3_KEY)?.remark).map((r) => parseNum(r.reportedClosing)),
  )
}

export function sumG9L3FormulaClosing(responses: Map<string, ChecklistResponse>): number {
  return calcSubtotal(
    parseJsonArray(responses.get(G9_L3_KEY)?.remark).map((r) => parseNum(r.closingFairValue)),
  )
}

export function sumG9DetailLevel3Closing(responses: Map<string, ChecklistResponse>): number {
  return calcSubtotal(
    parseJsonArray(responses.get(G9_DETAIL_KEY)?.remark)
      .filter((r) => isG9Level3(r.fairValueLevel))
      .map((r) => parseNum(r.closingAdjusted) || parseNum(r.closingBalance)),
  )
}

/** 按资产名比对 G9-4 Level3 审定 FV 与 G9-5 企业报告 */
export function listG9Fv4VsG95AssetMismatches(
  responses: Map<string, ChecklistResponse>,
): G9AssetMismatch[] {
  const fvMap = new Map<string, { name: string; audited: number }>()
  for (const r of parseJsonArray(responses.get(G9_FV_KEY)?.remark)) {
    if (!isG9Level3(r.fairValueLevel)) continue
    const name = String(r.assetName ?? '').trim()
    if (!name) continue
    fvMap.set(matchG9AssetKey(name), { name, audited: parseNum(r.closingAuditedFV) })
  }

  const out: G9AssetMismatch[] = []
  const seen = new Set<string>()
  for (const r of parseJsonArray(responses.get(G9_L3_KEY)?.remark)) {
    const name = String(r.assetName ?? '').trim()
    if (!name) continue
    const key = matchG9AssetKey(name)
    seen.add(key)
    const fv = fvMap.get(key)
    if (!fv) continue
    const reported = parseNum(r.reportedClosing)
    const diff = fv.audited - reported
    if (Math.abs(diff) > G9_CROSS_TOLERANCE) {
      out.push({
        assetName: name,
        fv4Audited: fv.audited,
        g95Reported: reported,
        diff,
      })
    }
  }

  // G9-4 有、G9-5 无的 Level3
  for (const [key, fv] of fvMap) {
    if (seen.has(key)) continue
    if (Math.abs(fv.audited) <= G9_CROSS_TOLERANCE) continue
    out.push({
      assetName: fv.name,
      fv4Audited: fv.audited,
      g95Reported: 0,
      diff: fv.audited,
    })
  }
  return out
}

function mkCheck(
  code: G9CrossCheckCode,
  left: number,
  right: number,
  message: string,
): G9CrossCheck | null {
  const diff = left - right
  if (Math.abs(diff) <= G9_CROSS_TOLERANCE) return null
  return { code, level: 'warning', message, left, right, diff }
}

/**
 * 汇总跨表勾稽项（仅返回有差异的项）。
 * disclosureSum / adjudicated 由调用方传入，避免本模块依赖附注 store 结构。
 */
export function buildG9CrossChecks(
  responses: Map<string, ChecklistResponse>,
  opts?: {
    disclosureCurrentSum?: number | null
    adjudicatedAmount?: number | null
    /** 附注汇总文本，用于 L3 披露软校验 */
    disclosureNoteText?: string | null
  },
): G9CrossCheck[] {
  const checks: G9CrossCheck[] = []

  const discSum = opts?.disclosureCurrentSum
  const adj = opts?.adjudicatedAmount
  if (discSum != null && adj != null) {
    const c = mkCheck(
      'disclosure-sum-vs-adj',
      discSum,
      adj,
      `附注本期合计 ${fmt(discSum)} 与 G9-1 审定数 ${fmt(adj)} 差异 ${fmt(discSum - adj)}`,
    )
    if (c) checks.push(c)
  }

  const fv4 = sumG9Level3FvAudited(responses)
  const g95Reported = sumG9L3ReportedClosing(responses)
  const hasFv4 = fv4 !== 0 || parseJsonArray(responses.get(G9_FV_KEY)?.remark).some((r) => isG9Level3(r.fairValueLevel))
  const hasG95 = parseJsonArray(responses.get(G9_L3_KEY)?.remark).length > 0
  if (hasFv4 && hasG95) {
    const c = mkCheck(
      'fv4-l3-total-vs-g95-reported',
      fv4,
      g95Reported,
      `G9-4 Level3 审定合计 ${fmt(fv4)} 与 G9-5 企业报告合计 ${fmt(g95Reported)} 差异 ${fmt(fv4 - g95Reported)}`,
    )
    if (c) checks.push(c)
  }

  const detailL3 = sumG9DetailLevel3Closing(responses)
  if (detailL3 !== 0 && hasG95) {
    const c = mkCheck(
      'detail-l3-vs-g95-reported',
      detailL3,
      g95Reported,
      `G9-2 Level3 审定合计 ${fmt(detailL3)} 与 G9-5 企业报告合计 ${fmt(g95Reported)} 差异 ${fmt(detailL3 - g95Reported)}`,
    )
    if (c) checks.push(c)
  }

  const assetMismatches = listG9Fv4VsG95AssetMismatches(responses)
  if (assetMismatches.length) {
    const names = assetMismatches.slice(0, 3).map((m) => m.assetName).join('、')
    const more = assetMismatches.length > 3 ? `等 ${assetMismatches.length} 项` : ''
    checks.push({
      code: 'fv4-vs-g95-asset',
      level: 'warning',
      message: `G9-4 与 G9-5 按资产勾稽不符：${names}${more}`,
      left: assetMismatches.reduce((s, m) => s + m.fv4Audited, 0),
      right: assetMismatches.reduce((s, m) => s + m.g95Reported, 0),
      diff: assetMismatches.reduce((s, m) => s + m.diff, 0),
    })
  }

  // Level3 有余额但附注汇总未提及层次/调节 — 软提醒
  const l3Balance = Math.max(Math.abs(detailL3), Math.abs(fv4), Math.abs(g95Reported))
  const noteText = String(opts?.disclosureNoteText ?? '').trim()
  const noteMentionsL3 = /第三层次|Level\s*3|L3|不可观察|层次调节/i.test(noteText)
  if (l3Balance > G9_CROSS_TOLERANCE && !noteMentionsL3) {
    checks.push({
      code: 'l3-disclosure-note-missing',
      level: 'info',
      message: `存在 Level3 余额 ${fmt(l3Balance)}，建议在附注汇总中补充公允价值层次及第三层次调节过程披露说明`,
      left: l3Balance,
      right: 0,
      diff: l3Balance,
    })
  }

  return checks
}

function fmt(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── G9-2 明细 ↔ 辅助核算 / G9-1 回写 ───────────────────────────────────────

export const G9_ADJ_ROWS_KEY = 'G9-adj-rows'

export interface G9AuxAssetSeed {
  assetName: string
  openingBalance: number
  closingBalance: number
  auxType: string
  auxCode: string
}

/** 分类 → G9-1 分组首行 rowKey */
export const G9_CLASSIFICATION_ROW_KEY: Record<string, string> = {
  FVTPL: 'fvtpl_1',
  FVOCI: 'fvoci_1',
  摊余成本: 'amort_1',
}

/** 拉取科目 1504 辅助核算余额，按辅助名称汇总为资产种子 */
export async function fetchG9AuxAssetSeeds(
  projectId: string,
  year?: number,
): Promise<{ seeds: G9AuxAssetSeed[]; dimType: string; error?: string }> {
  if (!projectId) return { seeds: [], dimType: '', error: '缺少项目 ID' }
  try {
    const http = (await import('@/utils/http')).default
    const { resolveAuditYearNumber } = await import('./workpaperAuditYear')
    const y = year
      ?? resolveAuditYearNumber(undefined, new Date().getFullYear() - 1)
      ?? (new Date().getFullYear() - 1)

    const { data } = await http.get(`/api/projects/${projectId}/ledger/aux-balance/${G9_ACCOUNT_CODE}`, {
      params: { year: y },
      _silent: true,
    } as any)

    const rows: any[] = Array.isArray(data)
      ? data
      : (data?.data ?? data?.items ?? data?.rows ?? [])

    if (!rows.length) {
      return { seeds: [], dimType: '', error: `科目 ${G9_ACCOUNT_CODE} 无辅助核算余额（年度 ${y}）` }
    }

    const byType = new Map<string, any[]>()
    for (const r of rows) {
      const t = String(r.aux_type ?? r.auxType ?? r.dim_type ?? '未分类').trim() || '未分类'
      if (!byType.has(t)) byType.set(t, [])
      byType.get(t)!.push(r)
    }
    let bestType = ''
    let bestRows: any[] = []
    for (const [t, list] of byType) {
      if (list.length > bestRows.length) {
        bestType = t
        bestRows = list
      }
    }

    const merged = new Map<string, G9AuxAssetSeed>()
    for (const r of bestRows) {
      const name = String(r.aux_name ?? r.auxName ?? r.name ?? '').trim()
      if (!name) continue
      const key = matchG9AssetKey(name)
      const opening = parseNum(r.opening_balance ?? r.openingBalance)
      const closing = parseNum(r.closing_balance ?? r.closingBalance ?? r.ending_balance)
      const prev = merged.get(key)
      if (prev) {
        prev.openingBalance = Math.round((prev.openingBalance + opening) * 100) / 100
        prev.closingBalance = Math.round((prev.closingBalance + closing) * 100) / 100
      } else {
        merged.set(key, {
          assetName: name,
          openingBalance: opening,
          closingBalance: closing,
          auxType: bestType,
          auxCode: String(r.aux_code ?? r.auxCode ?? ''),
        })
      }
    }

    const seeds = [...merged.values()].filter(
      (s) => Math.abs(s.openingBalance) > 0.01 || Math.abs(s.closingBalance) > 0.01,
    )
    if (!seeds.length) {
      return { seeds: [], dimType: bestType, error: `维度「${bestType}」无有效余额行` }
    }
    return { seeds, dimType: bestType }
  } catch (e: any) {
    return { seeds: [], dimType: '', error: e?.message || '辅助核算取数失败' }
  }
}

/**
 * 按分类将明细期初审定/期末未审合计回写 G9-1 各组首行（fvtpl_1 / fvoci_1 / amort_1），
 * 保留已有 AJE/RJE；并发布审定数合计。
 */
export function pushG9DetailGroupTotalsToAdjudication(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  groups: Array<{
    classification: string
    openingAdjusted: number
    closingBalance: number
    closingAdjusted: number
  }>,
): number {
  let store = parseG9AdjStore(responses.get(G9_ADJ_ROWS_KEY)?.remark)
  let n = 0
  let grandClosingAdj = 0

  for (const g of groups) {
    const rowKey = G9_CLASSIFICATION_ROW_KEY[g.classification]
    if (!rowKey) continue
    if (Math.abs(g.openingAdjusted) < 0.005 && Math.abs(g.closingBalance) < 0.005) continue
    store = patchG9AdjRow(store, rowKey, {
      openingUnadjusted: g.openingAdjusted,
      closingUnadjusted: g.closingBalance,
      indexRef: 'G9-2',
    })
    const row = store[rowKey] ?? {}
    grandClosingAdj += calcAdjustedAmount(
      parseNum(row.closingUnadjusted),
      parseNum(row.closingAJE),
      parseNum(row.closingRJE),
    )
    n += 1
  }

  if (!n) return 0

  debouncedSave(G9_ADJ_ROWS_KEY, { remark: JSON.stringify(store) })
  debouncedSave(G9_ADJUDICATED_KEY, { conclusion: String(grandClosingAdj) })
  try {
    window.dispatchEvent(
      new CustomEvent('g9:detail-to-adjudication', {
        detail: { closingAdjusted: grandClosingAdj, groups: n, timestamp: Date.now() },
      }),
    )
  } catch { /* silent */ }
  return n
}
