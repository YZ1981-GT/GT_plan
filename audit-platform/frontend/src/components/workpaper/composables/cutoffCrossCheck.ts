/**
 * 截止测试双表交叉核对
 */
import type { CutoffRow } from './useCycleCutoff'

export interface CutoffCrossMatchItem {
  voucherNo: string
  amount: number
  forwardConclusion: string
  backwardConclusion: string
  forwardCross: boolean
  backwardCross: boolean
  status: 'consistent' | 'mismatch' | 'forward-only' | 'backward-only'
}

export interface CutoffCrossCheckSummary {
  matchedCount: number
  consistentCount: number
  mismatchCount: number
  forwardOnlyCount: number
  backwardOnlyCount: number
  items: CutoffCrossMatchItem[]
}

function _normVoucher(v: string): string {
  return String(v ?? '').trim().replace(/\s+/g, '').toLowerCase()
}

function _approxAmount(a: number, b: number): boolean {
  return Math.abs(a - b) < 0.02
}

export function buildCutoffCrossCheck(
  forwardRows: CutoffRow[],
  backwardRows: CutoffRow[],
): CutoffCrossCheckSummary {
  const forwardMap = new Map<string, CutoffRow>()
  const backwardMap = new Map<string, CutoffRow>()

  for (const row of forwardRows) {
    const key = _normVoucher(row.voucherNo)
    if (key) forwardMap.set(key, row)
  }
  for (const row of backwardRows) {
    const key = _normVoucher(row.voucherNo)
    if (key) backwardMap.set(key, row)
  }

  const allKeys = new Set([...forwardMap.keys(), ...backwardMap.keys()])
  const items: CutoffCrossMatchItem[] = []

  for (const key of allKeys) {
    const f = forwardMap.get(key)
    const b = backwardMap.get(key)
    if (f && b) {
      const fCross = f.isCrossPeriod
      const bCross = b.isCrossPeriod
      const consistent = fCross === bCross
      items.push({
        voucherNo: f.voucherNo || b.voucherNo || key,
        amount: f.amount || b.amount || 0,
        forwardConclusion: f.conclusion || '正常',
        backwardConclusion: b.conclusion || '正常',
        forwardCross: fCross,
        backwardCross: bCross,
        status: consistent ? 'consistent' : 'mismatch',
      })
    } else if (f) {
      items.push({
        voucherNo: f.voucherNo,
        amount: f.amount,
        forwardConclusion: f.conclusion || '正常',
        backwardConclusion: '—',
        forwardCross: f.isCrossPeriod,
        backwardCross: false,
        status: 'forward-only',
      })
    } else if (b) {
      items.push({
        voucherNo: b.voucherNo,
        amount: b.amount,
        forwardConclusion: '—',
        backwardConclusion: b.conclusion || '正常',
        forwardCross: false,
        backwardCross: b.isCrossPeriod,
        status: 'backward-only',
      })
    }
  }

  return {
    matchedCount: items.filter((i) => i.status === 'consistent' || i.status === 'mismatch').length,
    consistentCount: items.filter((i) => i.status === 'consistent').length,
    mismatchCount: items.filter((i) => i.status === 'mismatch').length,
    forwardOnlyCount: items.filter((i) => i.status === 'forward-only').length,
    backwardOnlyCount: items.filter((i) => i.status === 'backward-only').length,
    items: items.sort((a, b) => {
      if (a.status === 'mismatch' && b.status !== 'mismatch') return -1
      if (b.status === 'mismatch' && a.status !== 'mismatch') return 1
      return 0
    }),
  }
}
