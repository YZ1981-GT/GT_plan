/**
 * H3-5 证→账追查 ↔ H3-12 产权核对 行级联动
 */
import type { H3TraceRow } from './h3AdditionCheckModel'
import type { TitleRow } from './h3TitleRowModel'
import { normName } from './h3TitleRowModel'
import { findBestTitleMatch } from './useH3TitleCrossSheet'

export interface TraceTitleLink {
  traceRowId: string
  titleRowId: string
  matchScore: number
  matchReason: string
}

const TITLE_CERT_SOURCE_TYPES = new Set(['产权证', '土地使用权证', '不动产权证书'])

export function isTitleCertTraceSource(trace: Pick<H3TraceRow, 'sourceType' | 'sourceRef'>): boolean {
  const t = String(trace.sourceType || '').trim()
  if (TITLE_CERT_SOURCE_TYPES.has(t)) return true
  return /产权|使用权|不动产/.test(t) || /产权|不动产|使用权/.test(String(trace.sourceRef || ''))
}

export function matchTraceToTitleRow(trace: H3TraceRow, titleRows: TitleRow[]): TitleRow | undefined {
  if (trace.linkedTitleRowId) {
    const linked = titleRows.find((r) => r.rowId === trace.linkedTitleRowId)
    if (linked) return linked
  }

  const certRef = String(trace.sourceRef || '').trim()
  if (isTitleCertTraceSource(trace) && certRef) {
    const byCert = titleRows.find((r) => normName(r.titleCertNo) === normName(certRef))
    if (byCert) return byCert
  }

  const name = String(trace.bookAssetName || trace.sourceParty || '').trim()
  if (!name) return undefined

  return findBestTitleMatch(titleRows, {
    assetName: name,
    bookArea: trace.bookAmount > 0 ? trace.bookAmount : undefined,
  })
}

export function findTraceRowsForTitle(title: TitleRow, traceRows: H3TraceRow[]): H3TraceRow[] {
  const linked = traceRows.filter((t) => t.linkedTitleRowId === title.rowId)
  if (linked.length) return linked

  const certNo = normName(title.titleCertNo)
  const assetKey = normName(title.assetName)

  return traceRows.filter((tr) => {
    if (tr.linkedTitleRowId === title.rowId) return true
    if (certNo && isTitleCertTraceSource(tr) && normName(tr.sourceRef) === certNo) return true
    const trName = normName(tr.bookAssetName || tr.sourceParty)
    if (assetKey && trName && (trName === assetKey || trName.includes(assetKey) || assetKey.includes(trName))) {
      return true
    }
    const hit = matchTraceToTitleRow(tr, [title])
    return hit?.rowId === title.rowId
  })
}

export function buildTraceTitleLinks(traceRows: H3TraceRow[], titleRows: TitleRow[]): TraceTitleLink[] {
  const links: TraceTitleLink[] = []
  const used = new Set<string>()

  for (const tr of traceRows) {
    const title = matchTraceToTitleRow(tr, titleRows)
    if (!title) continue
    const key = `${tr.rowId}:${title.rowId}`
    if (used.has(key)) continue
    used.add(key)
    links.push({
      traceRowId: tr.rowId,
      titleRowId: title.rowId,
      matchScore: tr.linkedTitleRowId === title.rowId ? 1 : 0.8,
      matchReason: tr.linkedTitleRowId === title.rowId
        ? '已关联'
        : isTitleCertTraceSource(tr) ? '产权证号' : '名称匹配',
    })
  }
  return links
}

export function parseTitleRows(raw: unknown): TitleRow[] {
  if (!Array.isArray(raw)) return []
  return raw as TitleRow[]
}

export function parseTraceRows(raw: unknown): H3TraceRow[] {
  if (!Array.isArray(raw)) return []
  return raw as H3TraceRow[]
}
