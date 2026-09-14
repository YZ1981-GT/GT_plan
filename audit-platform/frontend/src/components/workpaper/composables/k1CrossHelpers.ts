/**
 * K1 跨表取数辅助 — K1-2 明细 → K1-10 长期未收回；K1-10 ↔ K1-7/K1-8 勾稽
 */
import { parseNum } from './useG2IntRecFormulaEngine'
import { parseK18Payload } from './useK1BadDebtCalcSheet'

export const K1_DETAIL_STORAGE_KEY = 'K1-2-detail-rows'

export interface K1DetailPartial {
  id: string
  counterparty: string
  nature: string
  beginBalance: number
  endBalance: number
  badDebtProvision: number
  stage: number
  relatedParty: string
  agingPrior: Record<string, number>
  agingAudited: Record<string, number>
  remark: string
}

export interface K1LongTermImportRow {
  debtorName: string
  sourceRowId: string
  openingBalance: number
  closingBalance: number
  aging: string
  businessDesc: string
  unrecoveredReason: string
  provision: number
  auditedBalance: number
  stage: number
}

function sumAgingBucket(bucket: Record<string, number> | undefined): number {
  if (!bucket || typeof bucket !== 'object') return 0
  return Object.values(bucket).reduce((s, v) => s + parseNum(v), 0)
}

function isWithin1Key(key: string): boolean {
  return key === 'within1' || /^within\s*1$/i.test(key)
}

const AGING_LABEL_MAP: Record<string, string> = {
  y1to2: '1-2年',
  y2to3: '2-3年',
  y3to4: '3-4年',
  y4to5: '4-5年',
  over3: '3年以上',
  over5: '5年以上',
}

/** 从 allResponses 解析 K1-2 明细行 */
export function loadK1DetailPartials(map: Map<string, any>): K1DetailPartial[] {
  const raw = map.get(K1_DETAIL_STORAGE_KEY)?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any) => ({
      id: String(r.id || ''),
      counterparty: String(r.counterparty || ''),
      nature: String(r.nature || ''),
      beginBalance: parseNum(r.beginBalance),
      endBalance: parseNum(r.endBalance),
      badDebtProvision: parseNum(r.badDebtProvision),
      stage: Number(r.stage) || 1,
      relatedParty: String(r.relatedParty || '否'),
      agingPrior: (r.agingPrior && typeof r.agingPrior === 'object') ? r.agingPrior : {},
      agingAudited: (r.agingAudited && typeof r.agingAudited === 'object') ? r.agingAudited : {},
      remark: String(r.remark || ''),
    }))
  } catch {
    return []
  }
}

/** K1-2 → K1-10：账龄超过 1 年的明细 */
export function filterLongTermFromK1Detail(details: K1DetailPartial[]): K1LongTermImportRow[] {
  const out: K1LongTermImportRow[] = []
  for (const d of details) {
    const audited = d.agingAudited || {}
    let longSum = 0
    let topLabel = ''
    let topAmt = 0
    for (const [key, val] of Object.entries(audited)) {
      const amt = parseNum(val)
      if (amt <= 0) continue
      if (isWithin1Key(key)) continue
      longSum += amt
      if (amt > topAmt) {
        topAmt = amt
        topLabel = key
      }
    }
    if (longSum <= 0.005) continue
    const closing = longSum || d.endBalance
    const net = Math.max(0, closing - d.badDebtProvision)
    out.push({
      debtorName: d.counterparty || '未命名',
      sourceRowId: d.id,
      openingBalance: d.beginBalance || sumAgingBucket(d.agingPrior),
      closingBalance: closing,
      aging: AGING_LABEL_MAP[topLabel] || topLabel || '1年以上',
      businessDesc: d.nature || '',
      unrecoveredReason: d.remark || '',
      provision: d.badDebtProvision,
      auditedBalance: net || closing,
      stage: d.stage,
    })
  }
  return out
}

/** 从账龄审定分布取金额最大段的展示标签 */
export function dominantAgingLabel(agingAudited: Record<string, number> | undefined): string {
  if (!agingAudited || typeof agingAudited !== 'object') return ''
  let topKey = ''
  let topAmt = 0
  for (const [key, val] of Object.entries(agingAudited)) {
    const amt = parseNum(val)
    if (amt > topAmt) {
      topAmt = amt
      topKey = key
    }
  }
  if (!topKey) return ''
  return AGING_LABEL_MAP[topKey] || topKey
}

export interface K1TopLargeImportRow {
  debtorName: string
  sourceRowId: string
  openingBalance: number
  closingBalance: number
  periodDebit: number
  periodCredit: number
  provision: number
  aging: string
  businessDesc: string
  isRelated: boolean
}

/** K1-2 → K1-5：按期末余额降序取前 N 名（默认排除合并范围内关联方） */
export function extractTopLargeFromK1Detail(
  details: K1DetailPartial[],
  opts: { limit?: number; excludeRelated?: boolean } = {},
): K1TopLargeImportRow[] {
  const limit = opts.limit ?? 10
  const excludeRelated = opts.excludeRelated !== false
  const filtered = details.filter((d) => {
    if (!d.counterparty.trim()) return false
    if (Math.abs(d.endBalance) < 0.005) return false
    if (excludeRelated && d.relatedParty === '是') return false
    return true
  })
  filtered.sort((a, b) => b.endBalance - a.endBalance)
  return filtered.slice(0, limit).map((d) => {
    const opening = d.beginBalance
    const closing = d.endBalance
    return {
      debtorName: d.counterparty,
      sourceRowId: d.id,
      openingBalance: opening,
      closingBalance: closing,
      periodDebit: Math.max(0, closing - opening),
      periodCredit: Math.max(0, opening - closing),
      provision: d.badDebtProvision,
      aging: dominantAgingLabel(d.agingAudited),
      businessDesc: d.nature || '',
      isRelated: d.relatedParty === '是',
    }
  })
}

export const K18_STORAGE_KEY = 'K1-8-bad-debt-calc'
export const K18_PROVISION_TOTAL_KEY = 'K1-8-calc-provision-total'

export interface K110ProvisionRowMismatch {
  debtorName: string
  k110Provision: number
  k18BookProvision: number
  k18ExpectedProvision: number
  diffVsBook: number
}

export interface K110ProvisionReconciliation {
  k110ProvisionTotal: number
  k18ExpectedTotal: number
  k18BookTotal: number
  diffVsExpected: number
  diffVsBook: number
  isBookMatch: boolean
  hasK18Data: boolean
  rowMismatches: K110ProvisionRowMismatch[]
}

function sumK18Totals(payload: ReturnType<typeof parseK18Payload>) {
  const sum = (rows: Array<{ expectedProvision?: number; bookProvision?: number; archived?: boolean }>) => {
    let expected = 0
    let book = 0
    for (const r of rows) {
      if (r.archived) continue
      expected += parseNum(r.expectedProvision)
      book += parseNum(r.bookProvision)
    }
    return { expected, book }
  }
  const single = sum(payload.singleRows)
  const credit = sum(payload.creditGroups.flatMap((g) => g.rows))
  const aging = sum(payload.agingGroups.flatMap((g) => g.rows))
  return {
    expected: single.expected + credit.expected + aging.expected,
    book: single.book + credit.book + aging.book,
  }
}

export function stageLabelToNumber(stage: string): 1 | 2 | 3 | null {
  if (stage === 'Stage3') return 3
  if (stage === 'Stage2') return 2
  if (stage === 'Stage1') return 1
  return null
}

/** K1-10 坏账准备 vs K1-8 测算勾稽 */
export function computeK110ProvisionReconciliation(
  map: Map<string, any>,
  overdueRows: Array<{ debtorName: string; provision: number }>,
): K110ProvisionReconciliation {
  const k110ProvisionTotal = overdueRows.reduce((s, r) => s + parseNum(r.provision), 0)

  const k18Raw = map.get(K18_STORAGE_KEY)?.remark ?? map.get(K18_STORAGE_KEY)?.value
  const cachedExpected = parseNum(map.get(K18_PROVISION_TOTAL_KEY)?.remark)

  let k18ExpectedTotal = cachedExpected
  let k18BookTotal = 0
  let hasK18Data = false
  const singleByName = new Map<string, { bookProvision: number; expectedProvision: number }>()

  if (k18Raw) {
    hasK18Data = true
    const payload = parseK18Payload(k18Raw)
    const totals = sumK18Totals(payload)
    if (!cachedExpected) k18ExpectedTotal = totals.expected
    k18BookTotal = totals.book
    for (const r of payload.singleRows) {
      if (r.archived) continue
      const name = String(r.label || '').trim()
      if (name) {
        singleByName.set(name, {
          bookProvision: parseNum(r.bookProvision),
          expectedProvision: parseNum(r.expectedProvision),
        })
      }
    }
  }

  const rowMismatches: K110ProvisionRowMismatch[] = []
  for (const r of overdueRows) {
    const name = r.debtorName.trim()
    if (!name || parseNum(r.provision) <= 0) continue
    const hit = singleByName.get(name)
    if (!hit) continue
    const diffVsBook = parseNum(r.provision) - hit.bookProvision
    if (Math.abs(diffVsBook) >= 0.01) {
      rowMismatches.push({
        debtorName: name,
        k110Provision: parseNum(r.provision),
        k18BookProvision: hit.bookProvision,
        k18ExpectedProvision: hit.expectedProvision,
        diffVsBook,
      })
    }
  }

  const diffVsExpected = k110ProvisionTotal - k18ExpectedTotal
  const diffVsBook = k110ProvisionTotal - k18BookTotal

  return {
    k110ProvisionTotal,
    k18ExpectedTotal,
    k18BookTotal,
    diffVsExpected,
    diffVsBook,
    isBookMatch: hasK18Data && Math.abs(diffVsBook) < 0.01,
    hasK18Data,
    rowMismatches,
  }
}
