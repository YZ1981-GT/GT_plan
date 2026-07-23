/**
 * i4PolicyPeerRange — I4-4 表A「同业合理」对照表B区间（纯函数）
 * 对齐 H1 范式：同业年限区间 → 偏离须备注 → 可自动建议 Y/N
 */
import { parseBenefitPeriodToMonths } from './i4PolicyAmortCrossCheck'

export interface PeerCellLike {
  benefitPeriod?: string
  amortMethod?: string
}

export interface PeerPolicyRowLike {
  category: string
  cells: Record<string, PeerCellLike>
}

export interface PolicyParamLikeForPeer {
  category: string
  benefitPeriod?: string
  amortMethod?: string
  reasonableVsPeers?: string
  remark?: string
}

export interface PeerRange {
  category: string
  periodMinMonths: number | null
  periodMaxMonths: number | null
  methods: string[]
  sampleCount: number
  label: string
}

export interface PeerDeviation {
  category: string
  field: 'benefitPeriod' | 'amortMethod'
  message: string
  requiresRemark: boolean
}

function normalizeMethod(m: string): string {
  const s = String(m || '').trim()
  if (!s) return ''
  if (/工作量|产量/.test(s)) return '工作量法'
  if (/直线/.test(s)) return '直线法'
  return s
}

function isLeaseLike(text: string): boolean {
  return /租赁|合同期|孰短/.test(String(text || ''))
}

/** 从表B同业格计算各类别受益期区间与方法集合 */
export function computePeerRanges(peerPolicies: PeerPolicyRowLike[]): PeerRange[] {
  return peerPolicies.map((row) => {
    const months: number[] = []
    const methods = new Set<string>()
    let leaseCount = 0
    for (const cell of Object.values(row.cells || {})) {
      const bp = String(cell.benefitPeriod || '').trim()
      const m = normalizeMethod(cell.amortMethod || '')
      if (m) methods.add(m)
      if (!bp) continue
      if (isLeaseLike(bp) && parseBenefitPeriodToMonths(bp) == null) {
        leaseCount++
        continue
      }
      const n = parseBenefitPeriodToMonths(bp)
      if (n != null) months.push(n)
    }
    const periodMinMonths = months.length ? Math.min(...months) : null
    const periodMaxMonths = months.length ? Math.max(...months) : null
    const parts: string[] = []
    if (periodMinMonths != null && periodMaxMonths != null) {
      const a = periodMinMonths % 12 === 0 ? `${periodMinMonths / 12}年` : `${periodMinMonths}月`
      const b = periodMaxMonths % 12 === 0 ? `${periodMaxMonths / 12}年` : `${periodMaxMonths}月`
      parts.push(periodMinMonths === periodMaxMonths ? `期限${a}` : `期限${a}–${b}`)
    } else if (leaseCount > 0) {
      parts.push('期限多为租赁期/孰短')
    }
    if (methods.size) parts.push(`方法:${[...methods].join('/')}`)
    return {
      category: row.category,
      periodMinMonths,
      periodMaxMonths,
      methods: [...methods],
      sampleCount: months.length + leaseCount + methods.size,
      label: parts.join('，'),
    }
  })
}

/** 表A 相对表B 的偏离 */
export function computePeerDeviations(
  policyRows: PolicyParamLikeForPeer[],
  ranges: PeerRange[],
): PeerDeviation[] {
  const out: PeerDeviation[] = []
  const byCat = new Map(ranges.map((r) => [r.category, r]))
  for (const row of policyRows) {
    const range = byCat.get(row.category)
    if (!range || range.sampleCount < 1) continue

    const clientMonths = parseBenefitPeriodToMonths(row.benefitPeriod || '')
    const clientLease = isLeaseLike(row.benefitPeriod || '')

    if (range.periodMinMonths != null && range.periodMaxMonths != null && clientMonths != null) {
      // 允许 5% 或 1 月容差
      const tol = Math.max(1, Math.round(range.periodMaxMonths * 0.05))
      if (clientMonths < range.periodMinMonths - tol || clientMonths > range.periodMaxMonths + tol) {
        const a = range.periodMinMonths % 12 === 0 ? `${range.periodMinMonths / 12}年` : `${range.periodMinMonths}月`
        const b = range.periodMaxMonths % 12 === 0 ? `${range.periodMaxMonths / 12}年` : `${range.periodMaxMonths}月`
        out.push({
          category: row.category,
          field: 'benefitPeriod',
          message: `${row.category}受益期「${row.benefitPeriod}」超出同业${a}–${b}`,
          requiresRemark: true,
        })
      }
    } else if (
      clientMonths != null
      && range.periodMinMonths == null
      && range.label.includes('租赁')
      && !clientLease
    ) {
      // 同业多为租赁期，客户给固定年数 — 提示关注（非强制阻断）
      out.push({
        category: row.category,
        field: 'benefitPeriod',
        message: `${row.category}同业多为租赁期/孰短，客户为固定期限「${row.benefitPeriod}」，请说明依据`,
        requiresRemark: true,
      })
    }

    const clientMethod = normalizeMethod(row.amortMethod || '')
    if (clientMethod && range.methods.length && !range.methods.includes(clientMethod)) {
      out.push({
        category: row.category,
        field: 'amortMethod',
        message: `${row.category}摊销方法「${clientMethod}」不在同业常见方法（${range.methods.join('/')}）`,
        requiresRemark: true,
      })
    }
  }
  return out
}

/** 空「同业合理」按偏离自动建议；返回变更行数 */
export function suggestReasonableVsPeers(
  policyRows: Array<PolicyParamLikeForPeer & { reasonableVsPeers?: string; remark?: string }>,
  deviations: PeerDeviation[],
): number {
  const devByCat = new Map<string, PeerDeviation[]>()
  for (const d of deviations) {
    const list = devByCat.get(d.category) || []
    list.push(d)
    devByCat.set(d.category, list)
  }
  let n = 0
  for (const row of policyRows) {
    if (row.reasonableVsPeers) continue
    const devs = devByCat.get(row.category)
    if (!devs?.length) continue
    row.reasonableVsPeers = 'N'
    const msg = `同业偏离：${devs.map((d) => d.message).join('；')}`
    if (!row.remark?.trim()) row.remark = msg
    else if (!row.remark.includes('同业偏离')) row.remark = `${row.remark}；${msg}`
    n++
  }
  return n
}

/**
 * 对有同业样本且无偏离的类别，空字段填 Y
 * （与 suggestReasonableVsPeers 分开，调用方先算 ranges）
 */
export function suggestReasonableYForInRange(
  policyRows: Array<PolicyParamLikeForPeer & { reasonableVsPeers?: string }>,
  ranges: PeerRange[],
  deviations: PeerDeviation[],
): number {
  const devCats = new Set(deviations.map((d) => d.category))
  const ranged = new Set(ranges.filter((r) => r.sampleCount > 0).map((r) => r.category))
  let n = 0
  for (const row of policyRows) {
    if (row.reasonableVsPeers) continue
    if (!ranged.has(row.category)) continue
    if (devCats.has(row.category)) continue
    row.reasonableVsPeers = 'Y'
    n++
  }
  return n
}

export function categoriesNeedingPeerRemark(
  policyRows: PolicyParamLikeForPeer[],
  deviations: PeerDeviation[],
): string[] {
  const need = new Set<string>()
  for (const d of deviations.filter((x) => x.requiresRemark)) {
    const row = policyRows.find((r) => r.category === d.category)
    if (!row) continue
    if (row.reasonableVsPeers === 'N' && !String(row.remark || '').trim()) {
      need.add(d.category)
    }
    // 判 Y 但仍偏离 — 也须备注
    if (row.reasonableVsPeers === 'Y') need.add(d.category)
  }
  return [...need]
}

export default computePeerRanges
