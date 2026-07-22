/**
 * H1-20 ↔ G5 长期应收款跨底稿带数 / 勾稽
 *
 * 优先读 G5-5（融资租赁未实现收益测算）groups；
 * 若无则回退 G5-2 中 businessType=lease 的余额行。
 */
import { api } from '@/services/apiProxy'
import { G5_ITEM_IDS, readCanonicalRaw } from './g5StorageContract'

export interface H1FinanceLeaseG5Seed {
  assetName: string
  lessee: string
  leaseStart: string
  minLeasePayment: number
  initialDirectCosts: number
  unguaranteedResidual: number
  fairValue: number
  presentValue: number
  unrecognizedFinIncome: number
  allocRate: number
  annualRent: number
  periodCount: number
  /** G5 账面净投资（勾稽对照） */
  g5BookNetInvestment: number
  /** G5 账面未实现融资收益（勾稽对照） */
  g5BookUnearned: number
  g5ProjectName: string
  source: 'G5-5' | 'G5-2'
  remark: string
}

export interface H1G5ReconcileRow {
  h1RowId: string
  h1AssetName: string
  h1Lessee: string
  g5ProjectName: string
  h1NetInvestment: number
  g5NetInvestment: number
  netVariance: number
  h1Unearned: number
  g5Unearned: number
  unearnedVariance: number
  h1Rate: number
  g5Rate: number
  matched: boolean
}

function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

async function resolveWpId(projectId: string, wpCode: string): Promise<string | null> {
  try {
    const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
      params: { project_id: projectId, wp_code: wpCode },
      _silent: true,
    } as any)
    return (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id ?? null
  } catch {
    return null
  }
}

async function loadChecklistItem(
  wpId: string,
  itemId: string,
): Promise<{ conclusion?: string | null; remark?: string | null } | null> {
  try {
    const res = await api.get(`/api/workpapers/${wpId}/checklist-responses`, { _silent: true } as any)
    const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
    return list.find((r) => r.item_id === itemId) ?? null
  } catch {
    return null
  }
}

function normalizeRatePct(raw: number): number {
  // G5 可能存 0.1（小数）或 10（百分数）
  if (!raw) return 0
  return Math.abs(raw) < 1 ? Math.round(raw * 10000) / 100 : raw
}

function mapG55Group(g: any): H1FinanceLeaseG5Seed | null {
  if (!g || typeof g !== 'object') return null
  const basic = g.basic || {}
  const name = String(g.projectName || basic.lessee || '').trim()
  if (!name) return null
  const periods = Array.isArray(g.periods) ? g.periods : []
  const first = periods[0]
  const mlp = parseNum(basic.minimumLeasePayment ?? basic.rentalInstallments)
  const idc = parseNum(basic.initialDirectCosts)
  const ug = parseNum(basic.unguaranteedResidual ?? basic.unguaranteedEnding)
  const fair = parseNum(basic.fairValue)
  const netFromPeriod = first
    ? parseNum(first.openingNetInvestment)
      || (parseNum(first.openingReceivable) - parseNum(first.openingUnrealized))
    : 0
  const bookNet = parseNum(basic.bookClosingNetInvestment) || netFromPeriod
  const bookUnr = parseNum(basic.bookClosingUnrealized)
    || (first ? parseNum(first.openingUnrealized) : 0)
  const presentValue = fair + idc > 0 ? fair + idc : (netFromPeriod || bookNet)
  const periodCount = periods.length || 0
  const annualRent = periodCount > 0
    ? parseNum(periods[0]?.periodCollection) || (mlp / periodCount)
    : 0

  return {
    assetName: name,
    lessee: String(basic.lessee || ''),
    leaseStart: String(basic.leaseStartDate || ''),
    minLeasePayment: mlp,
    initialDirectCosts: idc,
    unguaranteedResidual: ug,
    fairValue: fair,
    presentValue,
    unrecognizedFinIncome: mlp + ug - presentValue,
    allocRate: normalizeRatePct(parseNum(basic.implicitRate)),
    annualRent,
    periodCount,
    g5BookNetInvestment: bookNet,
    g5BookUnearned: bookUnr,
    g5ProjectName: name,
    source: 'G5-5',
    remark: '自 G5-5 融资租赁测算带入',
  }
}

function mapG52LeaseRow(r: any): H1FinanceLeaseG5Seed | null {
  if (!r || typeof r !== 'object') return null
  if (String(r.businessType || '') !== 'lease') return null
  const name = String(r.debtorName || r.contractNo || '').trim()
  if (!name) return null
  const closing = parseNum(r.closingBalance)
  const unrealized = parseNum(r.unrealizedIncome)
  const net = parseNum(r.netAmount) || (closing - unrealized)
  const contractAmt = parseNum(r.contractAmount) || closing
  return {
    assetName: name,
    lessee: String(r.debtorName || ''),
    leaseStart: String(r.startDate || ''),
    minLeasePayment: contractAmt,
    initialDirectCosts: 0,
    unguaranteedResidual: 0,
    fairValue: net,
    presentValue: net,
    unrecognizedFinIncome: unrealized || (contractAmt - net),
    allocRate: 0,
    annualRent: 0,
    periodCount: 0,
    g5BookNetInvestment: net,
    g5BookUnearned: unrealized,
    g5ProjectName: name,
    source: 'G5-2',
    remark: '自 G5-2 融资租赁余额行带入',
  }
}

/** 拉取同项目 G5 融资租赁数据，映射为 H1-20 种子 */
export async function fetchG5FinanceLeaseSeeds(projectId: string): Promise<{
  seeds: H1FinanceLeaseG5Seed[]
  missing: string[]
  source: 'G5-5' | 'G5-2' | null
}> {
  const missing: string[] = []
  const wpId = await resolveWpId(projectId, 'G5')
  if (!wpId) {
    return { seeds: [], missing: ['G5'], source: null }
  }

  // 优先 G5-5
  const g55 = await loadChecklistItem(wpId, G5_ITEM_IDS.G5_5_ROWS)
  const raw55 = readCanonicalRaw(g55)
  if (raw55) {
    try {
      const parsed = JSON.parse(raw55)
      const groups = Array.isArray(parsed?.groups)
        ? parsed.groups
        : (Array.isArray(parsed) ? parsed : [])
      const seeds = groups.map(mapG55Group).filter(Boolean) as H1FinanceLeaseG5Seed[]
      if (seeds.length) return { seeds, missing, source: 'G5-5' }
    } catch { /* fall through */ }
  }

  // 回退 G5-2
  const g52 = await loadChecklistItem(wpId, G5_ITEM_IDS.G5_2_ROWS)
  const raw52 = readCanonicalRaw(g52)
  if (raw52) {
    try {
      const parsed = JSON.parse(raw52)
      const rows = Array.isArray(parsed) ? parsed : []
      const seeds = rows.map(mapG52LeaseRow).filter(Boolean) as H1FinanceLeaseG5Seed[]
      if (seeds.length) return { seeds, missing, source: 'G5-2' }
    } catch { /* ignore */ }
  }

  return { seeds: [], missing, source: null }
}

function matchKey(lessee: string, name: string): string {
  return `${String(lessee || '').trim()}|${String(name || '').trim()}`.toLowerCase()
}

/** H1-20 与 G5 种子按承租人+项目名勾稽 */
export function buildH1G5Reconcile(
  h1Rows: Array<{
    rowId: string
    assetName: string
    lessee: string
    presentValue: number
    unrecognizedFinIncome: number
    allocRate: number
    g5ProjectName?: string
  }>,
  seeds: H1FinanceLeaseG5Seed[],
): H1G5ReconcileRow[] {
  const seedByKey = new Map<string, H1FinanceLeaseG5Seed>()
  for (const s of seeds) {
    seedByKey.set(matchKey(s.lessee, s.g5ProjectName), s)
    seedByKey.set(matchKey(s.lessee, s.assetName), s)
  }

  return h1Rows.map((r) => {
    const hit = seedByKey.get(matchKey(r.lessee, r.g5ProjectName || ''))
      || seedByKey.get(matchKey(r.lessee, r.assetName))
      || seeds.find((s) =>
        s.lessee && r.lessee && s.lessee.trim() === r.lessee.trim(),
      )
    if (!hit) {
      return {
        h1RowId: r.rowId,
        h1AssetName: r.assetName,
        h1Lessee: r.lessee,
        g5ProjectName: '',
        h1NetInvestment: r.presentValue,
        g5NetInvestment: 0,
        netVariance: r.presentValue,
        h1Unearned: r.unrecognizedFinIncome,
        g5Unearned: 0,
        unearnedVariance: r.unrecognizedFinIncome,
        h1Rate: r.allocRate,
        g5Rate: 0,
        matched: false,
      }
    }
    return {
      h1RowId: r.rowId,
      h1AssetName: r.assetName,
      h1Lessee: r.lessee,
      g5ProjectName: hit.g5ProjectName,
      h1NetInvestment: r.presentValue,
      g5NetInvestment: hit.g5BookNetInvestment || hit.presentValue,
      netVariance: r.presentValue - (hit.g5BookNetInvestment || hit.presentValue),
      h1Unearned: r.unrecognizedFinIncome,
      g5Unearned: hit.g5BookUnearned || hit.unrecognizedFinIncome,
      unearnedVariance: r.unrecognizedFinIncome - (hit.g5BookUnearned || hit.unrecognizedFinIncome),
      h1Rate: r.allocRate,
      g5Rate: hit.allocRate,
      matched: true,
    }
  })
}
