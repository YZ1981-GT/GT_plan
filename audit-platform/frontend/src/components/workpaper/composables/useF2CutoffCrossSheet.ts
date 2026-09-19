/**
 * F2-29~32 跨表：监盘种子 / 单号软勾稽 / 收入截止 D4-17/18 对照
 */
import { readStocktakeMetaSeed, extractDateToken } from './useF2StocktakeCrossSheet'
import type { ChecklistResponse } from './useF2FormData'
import type { F2CutoffRow } from './useF2CutoffSheet'
import http from '@/utils/http'
import { useAcnr } from '@/services/acnr/useAcnr'

export interface F2CutoffCrossHints {
  entityName: string
  cutoffDate: string
  countDate: string
  stocktakeSource: string
  /** 监盘叙述中命中的本表单号（可能冲突需人工核） */
  stocktakeDocHits: string[]
  /** 本表有、监盘叙述未提及的单号（提示未交叉核对） */
  uncheckedDocNos: string[]
  stocktakeNote: string
}

function collectNarrative(map: Map<string, ChecklistResponse>): string {
  const keys = [
    'F2-22-fields',
    'F2-23-fields',
    'F2-24-fields',
    'F2-24-note',
    'F2-24-count-note',
    'F2-25-fields',
    'F2-25-note',
    'F2-26-fields',
    'F2-26-note',
  ]
  const chunks: string[] = []
  for (const k of keys) {
    const raw = map.get(k)?.remark
    if (!raw) continue
    chunks.push(raw)
    try {
      const obj = JSON.parse(raw) as Record<string, unknown>
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        chunks.push(...Object.values(obj).map((v) => String(v ?? '')))
      }
    } catch { /* plain text */ }
  }
  return chunks.join('\n')
}

/** 从监盘叙述中软匹配本表单据号 */
export function matchDocsAgainstStocktakeNarrative(
  rows: F2CutoffRow[],
  allResponses: Map<string, ChecklistResponse>,
): { hits: string[]; unchecked: string[]; narrativeLen: number } {
  const narrative = collectNarrative(allResponses)
  const docNos = [...new Set(
    rows.map((r) => (r.docNo || '').trim()).filter((d) => d.length >= 2),
  )]
  if (!docNos.length) {
    return { hits: [], unchecked: [], narrativeLen: narrative.length }
  }
  const hits: string[] = []
  const unchecked: string[] = []
  for (const no of docNos) {
    if (narrative.includes(no)) hits.push(no)
    else unchecked.push(no)
  }
  return { hits, unchecked, narrativeLen: narrative.length }
}

export function buildCutoffCrossHints(
  rows: F2CutoffRow[],
  allResponses: Map<string, ChecklistResponse>,
): F2CutoffCrossHints {
  const seed = readStocktakeMetaSeed(allResponses)
  const match = matchDocsAgainstStocktakeNarrative(rows, allResponses)
  let note = ''
  if (seed.countDate) {
    note = `监盘日 ${seed.countDate}（来自 ${seed.source || '监盘底稿'}）`
  }
  if (match.narrativeLen > 20 && match.hits.length) {
    note += (note ? '；' : '') + `监盘叙述命中单号 ${match.hits.length} 个`
  }
  if (match.unchecked.length && match.narrativeLen > 40) {
    note += (note ? '；' : '') + `${match.unchecked.length} 个单号未在监盘叙述中出现，请人工交叉核对`
  }
  return {
    entityName: seed.entityName,
    cutoffDate: seed.bsDate,
    countDate: seed.countDate,
    stocktakeSource: seed.source,
    stocktakeDocHits: match.hits,
    uncheckedDocNos: match.unchecked.slice(0, 20),
    stocktakeNote: note,
  }
}

export interface D4CutoffMatchRow {
  sheet: 'D4-17' | 'D4-18'
  deliveryNo: string
  deliveryDate: string
  voucherNo: string
  voucherDate: string
  amount: number
  product: string
  isCutoff: boolean | null
}

export interface D4CutoffMatchResult {
  loaded: boolean
  message: string
  matches: Array<{
    f2DocNo: string
    f2Amount: number
    d4: D4CutoffMatchRow
    amountDiff: boolean
  }>
}

function parseD4Rows(raw: string | undefined, sheet: 'D4-17' | 'D4-18'): D4CutoffMatchRow[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw) as Array<Record<string, unknown>>
    if (!Array.isArray(arr)) return []
    return arr.map((r) => ({
      sheet,
      deliveryNo: String(r.deliveryNo || ''),
      deliveryDate: String(r.deliveryDate || ''),
      voucherNo: String(r.voucherNo || ''),
      voucherDate: String(r.voucherDate || ''),
      amount: Number(r.deliveryAmount || r.voucherAmount || 0) || 0,
      product: String(r.deliveryProduct || r.voucherProduct || ''),
      isCutoff: (r.isCutoff as boolean | null) ?? null,
    }))
  } catch {
    return []
  }
}

/** 拉取同项目 D4-17/18 行并与 F2 出库单号勾稽（产成品出库用） */
export async function fetchD4CutoffMatches(
  projectId: string,
  f2Rows: F2CutoffRow[],
): Promise<D4CutoffMatchResult> {
  if (!projectId) {
    return { loaded: false, message: '无项目上下文，无法加载收入截止底稿', matches: [] }
  }
  const { resolveInstance } = useAcnr()
  const docSet = new Map(
    f2Rows
      .filter((r) => (r.docNo || '').trim())
      .map((r) => [(r.docNo || '').trim(), r]),
  )
  if (!docSet.size) {
    return { loaded: true, message: '本表尚无出库单号可对照', matches: [] }
  }

  const allD4: D4CutoffMatchRow[] = []
  for (const code of ['D4-17', 'D4-18'] as const) {
    try {
      const inst = await resolveInstance(projectId, 'D4', code)
      const wpId = inst?.found ? inst.wp_id : undefined
      if (!wpId) continue
      const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`)
      const list = Array.isArray(data) ? data : (data?.items || data?.responses || [])
      const map = new Map<string, ChecklistResponse>()
      for (const it of list as ChecklistResponse[]) {
        if (it?.item_id) map.set(it.item_id, it)
      }
      allD4.push(...parseD4Rows(map.get(`${code}-rows`)?.remark, code))
    } catch {
      /* 无 D4 底稿或权限不足 */
    }
  }

  if (!allD4.length) {
    return {
      loaded: true,
      message: '未找到 D4-17/18 样本行（请确认项目已生成营业收入截止底稿）',
      matches: [],
    }
  }

  const matches: D4CutoffMatchResult['matches'] = []
  for (const d4 of allD4) {
    const no = (d4.deliveryNo || '').trim()
    if (!no) continue
    const f2 = docSet.get(no)
    if (!f2) continue
    matches.push({
      f2DocNo: no,
      f2Amount: f2.amount,
      d4,
      amountDiff: f2.amount > 0 && d4.amount > 0 && Math.abs(f2.amount - d4.amount) > 0.01,
    })
  }

  return {
    loaded: true,
    message: matches.length
      ? `与收入截止勾稽命中 ${matches.length} 笔`
      : `已加载 D4 样本 ${allD4.length} 行，与本表出库单号无交集`,
    matches,
  }
}

export { extractDateToken, readStocktakeMetaSeed }
