/** G12-2 ↔ G12-5 净头寸双向同步匹配 */
import type { G12HedgeDetailRow } from './useG12HedgeDetail'
import type { G12NetExposureRow } from './useG12NetExposure'

function normKey(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, '')
}

export function buildG12PositionMatchKey(row: {
  item?: string
  hedgingInstrument?: string
  indexRef?: string
}): string {
  const item = normKey(row.item ?? '')
  const tool = normKey(row.hedgingInstrument ?? '')
  if (item && tool) return `${item}::${tool}`
  if (item) return item
  if (tool) return tool
  const ref = normKey(row.indexRef ?? '')
  return ref || `__empty_${Math.random().toString(36).slice(2, 6)}`
}

export function findG12NetExposureMatch(
  detailRow: Pick<G12HedgeDetailRow, 'item' | 'hedgingInstrument' | 'indexRef' | 'rowKind'>,
  neRows: G12NetExposureRow[],
): G12NetExposureRow | undefined {
  if (detailRow.rowKind !== 'fv_allocation') return undefined
  const key = buildG12PositionMatchKey(detailRow)
  return neRows.find((r) => buildG12PositionMatchKey(r) === key)
    ?? neRows.find((r) => normKey(r.hedgingInstrument) === normKey(detailRow.hedgingInstrument) && detailRow.hedgingInstrument.trim())
    ?? neRows.find((r) => normKey(r.item) === normKey(detailRow.item) && detailRow.item.trim())
}

export interface G12PositionSyncResult {
  detailUpdates: Array<{ rowId: string; netPosition: string }>
  neUpdates: Array<{ rowId: string; netPosition: string; netPositionManual: boolean }>
  syncedCount: number
}

/** 以 source 为准，将净头寸同步至 target 侧 */
export function planG12NetPositionSync(
  source: 'g12-2' | 'g12-5',
  detailRows: G12HedgeDetailRow[],
  neRows: G12NetExposureRow[],
): G12PositionSyncResult {
  const detailUpdates: G12PositionSyncResult['detailUpdates'] = []
  const neUpdates: G12PositionSyncResult['neUpdates'] = []
  let syncedCount = 0

  if (source === 'g12-5') {
    for (const ne of neRows) {
      if (!ne.netPosition.trim()) continue
      const match = detailRows.find(
        (d) => d.rowKind === 'fv_allocation' && findG12NetExposureMatch(d, [ne]),
      )
      if (!match || match.netPosition === ne.netPosition) continue
      detailUpdates.push({ rowId: match.rowId, netPosition: ne.netPosition })
      syncedCount += 1
    }
    return { detailUpdates, neUpdates, syncedCount }
  }

  for (const d of detailRows) {
    if (d.rowKind !== 'fv_allocation' || !d.netPosition.trim()) continue
    const match = findG12NetExposureMatch(d, neRows)
    if (!match || match.netPosition === d.netPosition) continue
    neUpdates.push({ rowId: match.rowId, netPosition: d.netPosition, netPositionManual: true })
    syncedCount += 1
  }
  return { detailUpdates, neUpdates, syncedCount }
}

export interface G12AmortizationCandidate {
  source: 'G12-4' | 'G12-6'
  label: string
  amount: number
  indexRef: string
  hedgingInstrument: string
}

const AMORT_RE = /摊销|套期调整|无效部分|hedge.*adj/i

/** 从 G12-4 无效部分（|工具FV−项目FV|）提取摊销候选 */
export function extractAmortizationFromFvTest(
  fvRows: Array<{
    hedgeRelationId?: string
    instrumentName?: string
    instrumentFVChange?: number
    itemFVChange?: number
  }>,
): G12AmortizationCandidate[] {
  const out: G12AmortizationCandidate[] = []
  for (const r of fvRows) {
    const inst = Number(r.instrumentFVChange ?? 0)
    const item = Number(r.itemFVChange ?? 0)
    const ineffectiveness = Math.abs(inst - item)
    if (ineffectiveness < 0.01) continue
    const id = r.hedgeRelationId || r.instrumentName || ''
    out.push({
      source: 'G12-4',
      label: id ? `套期无效部分摊销（${id}）` : '套期无效部分摊销',
      amount: -ineffectiveness,
      indexRef: id ? `G12-4/${id}` : 'G12-4',
      hedgingInstrument: r.instrumentName ?? '',
    })
  }
  return out
}

/** 从 G12-6 凭证中提取 6103/摊销相关分录 */
export function extractAmortizationFromVouchers(
  voucherRows: Array<{
    businessContent?: string
    counterAccount?: string
    debitAmount?: number
    creditAmount?: number
    voucherNo?: string
    hedgeRelationId?: string
  }>,
): G12AmortizationCandidate[] {
  const out: G12AmortizationCandidate[] = []
  for (const r of voucherRows) {
    const content = `${r.businessContent ?? ''} ${r.counterAccount ?? ''}`
    const hits6103 = /6103|净敞口套期/.test(content)
    const hitsAmort = AMORT_RE.test(content)
    if (!hits6103 && !hitsAmort) continue
    const net = Number(r.debitAmount ?? 0) - Number(r.creditAmount ?? 0)
    if (Math.abs(net) < 0.01) continue
    const ref = r.voucherNo || r.hedgeRelationId || ''
    out.push({
      source: 'G12-6',
      label: hitsAmort ? `套期调整摊销（${ref || '凭证'}）` : `6103 相关调整（${ref || '凭证'}）`,
      amount: net,
      indexRef: ref ? `G12-6/${ref}` : 'G12-6',
      hedgingInstrument: '',
    })
  }
  return out
}
