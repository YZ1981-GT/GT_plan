/**
 * G7-14 权益法测算 — 多公司净资产调整 + 差异建议分录
 */
import { parseNum } from '../../composables/useG7EquityMethodFormulaEngine'
import type { EquityMethodCalcRow } from '../../composables/useG7EquityMethodFormData'

/** 分位容差：忽略浮点噪声；重要性未设置时亦作默认阈值 */
export const G714_PENNY_THRESHOLD = 0.005

/**
 * 有效重要性水平：已设置(>0)用用户值；未设置(≤0)回退到分位阈值，
 * 使高亮 / 异常汇总 / 建议分录口径一致。
 */
export function effectiveMaterialityThreshold(materialityLevel: number | null | undefined): number {
  const level = parseNum(materialityLevel)
  return level > 0 ? level : G714_PENNY_THRESHOLD
}

/** |amount| 是否超过有效重要性水平（严格大于） */
export function isAmountOverMateriality(
  amount: number | null | undefined,
  materialityLevel: number | null | undefined,
): boolean {
  return Math.abs(parseNum(amount)) > effectiveMaterialityThreshold(materialityLevel)
}

export interface EquityRollforward {
  begin: number
  increase: number
  decrease: number
}

export interface NetAssetAdjustment {
  id: string
  investeeName: string
  /** 稳定被投资单位 ID（可选） */
  investeeId?: string
  /** 账面所有者权益滚存 */
  shareCapital: EquityRollforward
  capitalReserve: EquityRollforward
  treasuryStock: EquityRollforward
  oci: EquityRollforward
  surplusReserve: EquityRollforward
  specialReserve: EquityRollforward
  retainedEarnings: EquityRollforward
  nonControllingInterest: EquityRollforward
  /** 加项调整 */
  fvDiffAtAcquisition: EquityRollforward
  otherProfitAdj: EquityRollforward
  openingFvDiffCumulative: EquityRollforward
  /** 减项：未实现内部交易 */
  unrealizedInternalElim: EquityRollforward
  /** 本公司持股比例（期末） */
  ownershipRatio: number
}

export interface SuggestedAdjustmentLine {
  id: string
  investeeName: string
  description: string
  category: '账项调整'
  reportItem: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  source: 'incomeDifference' | 'unexplainedVariance' | 'bargainPurchase'
  /** 同源草稿标记，用于 G7-3 精确替换 */
  sourceKind: 'g7-14-suggested' | 'g7-13-bargain-suggested'
}

export const G714_SUGGESTED_SOURCE_KIND = 'g7-14-suggested' as const
export const G713_BARGAIN_SOURCE_KIND = 'g7-13-bargain-suggested' as const

function rf(begin = 0, increase = 0, decrease = 0): EquityRollforward {
  return { begin, increase, decrease }
}

export function rollforwardEnd(item: EquityRollforward): number {
  return Math.round(
    (parseNum(item.begin) + parseNum(item.increase) - parseNum(item.decrease)) * 100,
  ) / 100
}

export function createNetAssetAdjustment(
  investeeName: string,
  ownershipRatio = 0,
  investeeId = '',
): NetAssetAdjustment {
  return {
    id: `g7-14-na-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    investeeName,
    investeeId: investeeId || undefined,
    shareCapital: rf(),
    capitalReserve: rf(),
    treasuryStock: rf(),
    oci: rf(),
    surplusReserve: rf(),
    specialReserve: rf(),
    retainedEarnings: rf(),
    nonControllingInterest: rf(),
    fvDiffAtAcquisition: rf(),
    otherProfitAdj: rf(),
    openingFvDiffCumulative: rf(),
    unrealizedInternalElim: rf(),
    ownershipRatio,
  }
}

/** 归属于母公司所有者权益合计（扣库存股） */
export function calcParentEquityTotal(adj: NetAssetAdjustment, phase: 'begin' | 'end'): number {
  const pick = (item: EquityRollforward) =>
    phase === 'begin' ? parseNum(item.begin) : rollforwardEnd(item)
  return Math.round(
    (
      pick(adj.shareCapital)
      + pick(adj.capitalReserve)
      - pick(adj.treasuryStock)
      + pick(adj.oci)
      + pick(adj.surplusReserve)
      + pick(adj.specialReserve)
      + pick(adj.retainedEarnings)
    ) * 100,
  ) / 100
}

/** 调整后所有者权益合计（FV/其他调整 − 内部交易；不含少数股东权益，权益法默认归母口径） */
export function calcAdjustedEquityTotal(adj: NetAssetAdjustment, phase: 'begin' | 'end'): number {
  const pick = (item: EquityRollforward) =>
    phase === 'begin' ? parseNum(item.begin) : rollforwardEnd(item)
  const parent = calcParentEquityTotal(adj, phase)
  return Math.round(
    (
      parent
      + pick(adj.fvDiffAtAcquisition)
      + pick(adj.otherProfitAdj)
      + pick(adj.openingFvDiffCumulative)
      - pick(adj.unrealizedInternalElim)
    ) * 100,
  ) / 100
}

/** 本公司应享有的调整后所有者权益（→ 回写经审计净资产×比例前的净资产基数） */
export function calcShareOfAdjustedEquity(adj: NetAssetAdjustment): number {
  const equity = calcAdjustedEquityTotal(adj, 'end')
  return Math.round(equity * parseNum(adj.ownershipRatio) * 100) / 100
}

/** 将第3部分期末调整后净资产回写到测算行的经审计净资产 */
export function syncAuditedNetAssetsFromAdjustment(
  row: EquityMethodCalcRow,
  adj: NetAssetAdjustment,
): void {
  row.auditedNetAssets = calcAdjustedEquityTotal(adj, 'end')
  if (!row.investmentRatio && adj.ownershipRatio) {
    row.investmentRatio = adj.ownershipRatio
  }
}

export function ensureNetAssetAdjustments(
  rows: EquityMethodCalcRow[],
  existing: NetAssetAdjustment[],
): NetAssetAdjustment[] {
  const byId = new Map(
    existing
      .filter((item) => String(item.investeeId || '').trim())
      .map((item) => [String(item.investeeId).trim(), item]),
  )
  const byName = new Map(existing.map((item) => [item.investeeName, item]))
  const next: NetAssetAdjustment[] = []
  const seen = new Set<string>()
  for (const row of rows) {
    const name = (row.investeeName || '').trim()
    const id = String(row.investeeId || '').trim()
    const seenKey = id ? `id:${id}` : `name:${name}`
    if ((!name && !id) || seen.has(seenKey)) continue
    seen.add(seenKey)
    const found = (id && byId.get(id)) || (name ? byName.get(name) : undefined)
    if (found) {
      if (!found.ownershipRatio && row.investmentRatio) found.ownershipRatio = row.investmentRatio
      if (id && !found.investeeId) found.investeeId = id
      if (name && !found.investeeName) found.investeeName = name
      next.push(found)
    } else {
      next.push(createNetAssetAdjustment(name || id, row.investmentRatio || 0, id))
    }
  }
  return next
}

function lineId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

/** 持股比例归一：>1 视为百分数（30→0.3）；已是小数则保持 */
export function normalizeOwnershipRatio(raw: unknown): number {
  const n = parseNum(raw)
  if (!Number.isFinite(n) || n === 0) return 0
  if (Math.abs(n) > 1.0000001) {
    return Math.round((n / 100) * 1e8) / 1e8
  }
  return n
}

/** 导出用：小数比例 → 百分数展示值 */
export function ownershipRatioToPercent(ratio: unknown): number {
  return Math.round(normalizeOwnershipRatio(ratio) * 10000) / 100
}

export type UnexplainedNature = EquityMethodCalcRow['unexplainedNature']

export const UNEXPLAINED_NATURE_OPTIONS: Array<{
  value: UnexplainedNature
  label: string
  postsAje: boolean
}> = [
  { value: 'pending', label: '待拆解（不成账）', postsAje: false },
  { value: 'skip', label: '已解释/无需调整', postsAje: false },
  { value: 'investmentIncome', label: '投资收益错报', postsAje: true },
  { value: 'impairment', label: '减值准备', postsAje: true },
  { value: 'oci', label: '其他综合收益', postsAje: true },
  { value: 'capitalReserve', label: '资本公积/其他权益', postsAje: true },
  { value: 'priorPeriod', label: '前期差错/期初', postsAje: true },
  { value: 'goodwill', label: '应归入商誉（不成账，请改填商誉列）', postsAje: false },
  { value: 'fvAdj', label: '应归入累计FV（不成账，请改填FV列）', postsAje: false },
]

/** ⑮性质 → 对方科目（与 1511 对转） */
export function resolveUnexplainedCounterAccount(nature: UnexplainedNature): {
  code: string
  name: string
} | null {
  switch (nature) {
    case 'investmentIncome':
      return { code: '6111', name: '投资收益' }
    case 'impairment':
      return { code: '1512', name: '长期股权投资减值准备' }
    case 'oci':
      return { code: '4003', name: '其他综合收益' }
    case 'capitalReserve':
      return { code: '4002', name: '资本公积' }
    case 'priorPeriod':
      return { code: '4104', name: '利润分配—未分配利润' }
    default:
      return null
  }
}

function pushBalancedPair(
  out: SuggestedAdjustmentLine[],
  opts: {
    investeeName: string
    description: string
    amount: number
    bookTooHigh: boolean
    counterCode: string
    counterName: string
    remark: string
    source: SuggestedAdjustmentLine['source']
  },
): void {
  const amt = Math.abs(opts.amount)
  if (amt < G714_PENNY_THRESHOLD) return
  // bookTooHigh：长投账面偏高 → 贷 1511 / 借 对方
  const debitCode = opts.bookTooHigh ? opts.counterCode : '1511'
  const debitName = opts.bookTooHigh ? opts.counterName : '长期股权投资'
  const creditCode = opts.bookTooHigh ? '1511' : opts.counterCode
  const creditName = opts.bookTooHigh ? '长期股权投资' : opts.counterName
  out.push({
    id: lineId(`${opts.source}-dr`),
    investeeName: opts.investeeName,
    description: opts.description,
    category: '账项调整',
    reportItem: '长期股权投资',
    accountCode: debitCode,
    accountName: debitName,
    debitAmount: amt,
    creditAmount: 0,
    indexRef: 'G7-14',
    remark: opts.remark,
    source: opts.source,
    sourceKind: G714_SUGGESTED_SOURCE_KIND,
  })
  out.push({
    id: lineId(`${opts.source}-cr`),
    investeeName: opts.investeeName,
    description: opts.description,
    category: '账项调整',
    reportItem: '长期股权投资',
    accountCode: creditCode,
    accountName: creditName,
    debitAmount: 0,
    creditAmount: amt,
    indexRef: 'G7-14',
    remark: opts.remark,
    source: opts.source,
    sourceKind: G714_SUGGESTED_SOURCE_KIND,
  })
}

/**
 * 由投资收益差异⑩ +（已选性质的）未解释差额⑮生成借贷平衡建议分录。
 * ⑮仅在 unexplainedNature 映射到可入账科目时生成，避免与⑩/商誉/FV列重复。
 */
export function buildSuggestedAdjustments(
  rows: EquityMethodCalcRow[],
  materialityLevel = 0,
  opts: { includeUnexplainedVariance?: boolean } = {},
): SuggestedAdjustmentLine[] {
  // 默认：按行上已选性质自动纳入可入账⑮；显式 false 则仅⑩
  const includeUnexplained = opts.includeUnexplainedVariance !== false
  const out: SuggestedAdjustmentLine[] = []

  for (const row of rows) {
    const name = row.investeeName || `第${row.seq}行`
    const incomeDiff = parseNum(row.incomeDifference)
    if (isAmountOverMateriality(incomeDiff, materialityLevel)) {
      pushBalancedPair(out, {
        investeeName: name,
        description: `【G7-14】${name} 权益法投资收益差异调整（⑩=${incomeDiff.toFixed(2)}）`,
        amount: incomeDiff,
        bookTooHigh: incomeDiff > 0,
        counterCode: '6111',
        counterName: '投资收益',
        remark: `来源：投资收益差异⑩=⑨-⑤+⑧;sourceKind=${G714_SUGGESTED_SOURCE_KIND}`,
        source: 'incomeDifference',
      })
    }

    if (!includeUnexplained) continue
    const unexplained = parseNum(row.unexplainedVariance)
    if (!isAmountOverMateriality(unexplained, materialityLevel)) continue
    const nature = (row.unexplainedNature || 'pending') as UnexplainedNature
    const counter = resolveUnexplainedCounterAccount(nature)
    if (!counter) continue
    pushBalancedPair(out, {
      investeeName: name,
      description: `【G7-14】${name} 未解释差额⑮调整（${nature}=${unexplained.toFixed(2)}）`,
      amount: unexplained,
      bookTooHigh: unexplained > 0,
      counterCode: counter.code,
      counterName: counter.name,
      remark: `来源：未解释差额⑮性质=${nature};sourceKind=${G714_SUGGESTED_SOURCE_KIND}`,
      source: 'unexplainedVariance',
    })
  }
  return out
}

/** 净资产调整 → Excel 扁平行 */
export const NA_LINE_ITEM_KEYS: Array<{ key: keyof NetAssetAdjustment; label: string }> = [
  { key: 'shareCapital', label: '实收资本（或股本）' },
  { key: 'capitalReserve', label: '资本公积' },
  { key: 'treasuryStock', label: '减：库存股' },
  { key: 'oci', label: '其他综合收益' },
  { key: 'surplusReserve', label: '盈余公积' },
  { key: 'specialReserve', label: '专项储备' },
  { key: 'retainedEarnings', label: '未分配利润' },
  { key: 'nonControllingInterest', label: '少数股东权益（展示）' },
  { key: 'fvDiffAtAcquisition', label: '加：取得投资时公允价值差额' },
  { key: 'otherProfitAdj', label: '加：其他需调整损益的项目' },
  { key: 'openingFvDiffCumulative', label: '加：期初累计公允价值调整' },
  { key: 'unrealizedInternalElim', label: '减：未实现内部交易损益' },
]

export function flattenNetAssetAdjustmentsForExport(
  list: NetAssetAdjustment[],
): Array<Record<string, any>> {
  const out: Array<Record<string, any>> = []
  for (const adj of list) {
    for (const def of NA_LINE_ITEM_KEYS) {
      const rfItem = adj[def.key] as EquityRollforward
      if (!rfItem || typeof rfItem !== 'object') continue
      out.push({
        investeeName: adj.investeeName,
        lineItem: def.label,
        lineItemKey: def.key,
        begin: parseNum(rfItem.begin),
        increase: parseNum(rfItem.increase),
        decrease: parseNum(rfItem.decrease),
        end: rollforwardEnd(rfItem),
        ownershipRatio: ownershipRatioToPercent(adj.ownershipRatio),
      })
    }
  }
  return out
}

export function hydrateNetAssetAdjustmentsFromFlatRows(
  flatRows: Array<Record<string, any>>,
): NetAssetAdjustment[] {
  const byName = new Map<string, NetAssetAdjustment>()
  const labelToKey = new Map(NA_LINE_ITEM_KEYS.map((d) => [d.label, d.key]))
  for (const raw of flatRows) {
    const name = String(raw.investeeName ?? raw.investee_name ?? '').trim()
    if (!name) continue
    let adj = byName.get(name)
    if (!adj) {
      adj = createNetAssetAdjustment(name, normalizeOwnershipRatio(raw.ownershipRatio ?? raw.ownership_ratio))
      byName.set(name, adj)
    } else if (!adj.ownershipRatio) {
      adj.ownershipRatio = normalizeOwnershipRatio(raw.ownershipRatio ?? raw.ownership_ratio)
    }
    const keyName = String(raw.lineItemKey ?? raw.line_item_key ?? '')
    const label = String(raw.lineItem ?? raw.line_item ?? '')
    const field = (keyName && (adj as any)[keyName] ? keyName : labelToKey.get(label)) as
      | keyof NetAssetAdjustment
      | undefined
    if (!field || field === 'id' || field === 'investeeName' || field === 'ownershipRatio') continue
    const item = (adj as any)[field]
    if (!item || typeof item !== 'object') continue
    item.begin = parseNum(raw.begin)
    item.increase = parseNum(raw.increase)
    item.decrease = parseNum(raw.decrease)
  }
  return [...byName.values()]
}

/** 将建议分录转为 G7-3 行结构 */
export function toG73Entries(lines: SuggestedAdjustmentLine[]): Record<string, any>[] {
  return lines.map((line, index) => ({
    id: line.id,
    seq: index + 1,
    description: line.description,
    category: line.category,
    reportItem: line.reportItem,
    noteItem: '',
    indexRef: line.indexRef,
    entryType: 'AJE',
    date: '',
    summary: line.description,
    accountCode: line.accountCode,
    accountName: line.accountName,
    debitAmount: line.debitAmount,
    creditAmount: line.creditAmount,
    preparedBy: '',
    remark: line.remark,
    sourceKind: line.sourceKind || G714_SUGGESTED_SOURCE_KIND,
    investeeName: line.investeeName || '',
  }))
}

/** 合并进既有 G7-3 rows：仅替换与本次推送相同 sourceKind 的建议草稿，保留手工及其他来源 */
export function mergeSuggestedIntoG73(
  existing: Record<string, any>[],
  suggested: Record<string, any>[],
): Record<string, any>[] {
  const kinds = new Set(
    suggested
      .map((row) => String(row.sourceKind || '').trim())
      .filter(Boolean),
  )
  if (!kinds.size) kinds.add(G714_SUGGESTED_SOURCE_KIND)

  const isReplacedDraft = (row: Record<string, any>) => {
    const sk = String(row.sourceKind || '')
    if (kinds.has(sk)) return true
    const remark = String(row.remark || '')
    for (const k of kinds) {
      if (remark.includes(`sourceKind=${k}`)) return true
    }
    return false
  }

  const kept = existing.filter((row) => !isReplacedDraft(row))
  const merged = [...kept, ...suggested]
  return merged.map((row, index) => ({ ...row, seq: index + 1 }))
}

function hydrateRf(raw: any): EquityRollforward {
  if (!raw || typeof raw !== 'object') return rf()
  return rf(parseNum(raw.begin), parseNum(raw.increase), parseNum(raw.decrease))
}

/** 从 checklist / 导出 JSON 恢复净资产调整行 */
export function hydrateNetAssetAdjustment(raw: any, fallbackName = ''): NetAssetAdjustment {
  const base = createNetAssetAdjustment(
    String(raw?.investeeName ?? raw?.investee_name ?? fallbackName ?? ''),
    parseNum(raw?.ownershipRatio ?? raw?.ownership_ratio),
  )
  if (!raw || typeof raw !== 'object') return base
  return {
    ...base,
    id: String(raw.id || base.id),
    investeeId: String(raw.investeeId ?? raw.investee_id ?? base.investeeId ?? '') || undefined,
    shareCapital: hydrateRf(raw.shareCapital ?? raw.share_capital),
    capitalReserve: hydrateRf(raw.capitalReserve ?? raw.capital_reserve),
    treasuryStock: hydrateRf(raw.treasuryStock ?? raw.treasury_stock),
    oci: hydrateRf(raw.oci),
    surplusReserve: hydrateRf(raw.surplusReserve ?? raw.surplus_reserve),
    specialReserve: hydrateRf(raw.specialReserve ?? raw.special_reserve),
    retainedEarnings: hydrateRf(raw.retainedEarnings ?? raw.retained_earnings),
    nonControllingInterest: hydrateRf(raw.nonControllingInterest ?? raw.non_controlling_interest),
    fvDiffAtAcquisition: hydrateRf(raw.fvDiffAtAcquisition ?? raw.fv_diff_at_acquisition),
    otherProfitAdj: hydrateRf(raw.otherProfitAdj ?? raw.other_profit_adj),
    openingFvDiffCumulative: hydrateRf(raw.openingFvDiffCumulative ?? raw.opening_fv_diff_cumulative),
    unrealizedInternalElim: hydrateRf(raw.unrealizedInternalElim ?? raw.unrealized_internal_elim),
  }
}

/** 判断工作底稿是否为 G7 主表（含 G7-3） */
export function isG7MainWorkpaper(wp: Record<string, any> | null | undefined): boolean {
  if (!wp) return false
  const code = String(wp.wp_code ?? wp.code ?? '').toUpperCase()
  const name = String(wp.wp_name ?? wp.name ?? wp.title ?? wp.template_name ?? '')
  const ctype = String(
    wp.component_type ?? wp.componentType ?? wp.force_component_type ?? wp.parsed_data?.component_type ?? '',
  ).toLowerCase()
  if (ctype.includes('g7-long-term-equity-main')) return true
  if (ctype.includes('equity-method') || ctype.includes('subsidiary')) return false
  if (name.includes('权益法') || name.includes('子公司')) return false
  if (code === 'G7') return true
  if (name.includes('长期股权投资') && (name.includes('审定') || name.includes('主表') || name.includes('实质性'))) {
    return true
  }
  return false
}
