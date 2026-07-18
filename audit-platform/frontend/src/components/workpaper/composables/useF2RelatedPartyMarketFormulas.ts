/** F2-66 关联方采购定价公允性核查（市场价）纯函数层。 */
export const F2_66_OBJECTIVE = '审计目标：获取关联采购产品同期市场（挂牌）价格，逐月比较关联方采购均价是否处于市场价格区间，评价关联方采购定价的公允性。'
export const F2_66_TIP = '提示：该底稿也适用于非关联方之间采购交易的价格公允性测试。'
export const MARKET_MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
export const MARKET_JUDGMENTS = ['是', '否'] as const
export type MarketJudgment = typeof MARKET_JUDGMENTS[number]

let seq = 0
export function newMarketId(): string {
  seq += 1
  return `mkt-${Date.now().toString(36)}-${seq}`
}

export interface MarketMonthRow {
  id: string
  month: number
  purchaseAvgPrice: number
  marketPriceStart: number
  marketPriceEnd: number
  judgment: MarketJudgment | ''
  remark: string
}

export interface EnrichedMarketMonthRow extends MarketMonthRow {
  marketLow: number | null
  marketHigh: number | null
  /** 采购均价相对市场区间中值的偏离率 */
  deviationRate: number | null
  inRange: boolean | null
  isAbnormal: boolean
  suggestedJudgment: MarketJudgment | ''
}

export interface MarketProductGroup {
  id: string
  relatedParty: string
  productName: string
  rows: MarketMonthRow[]
}

export interface EnrichedMarketProductGroup extends Omit<MarketProductGroup, 'rows'> {
  rows: EnrichedMarketMonthRow[]
  abnormalCount: number
  filledMonthCount: number
}

export interface RelatedPartyMarketSheet {
  groups: MarketProductGroup[]
}

export function emptyMarketMonth(month: number): MarketMonthRow {
  return {
    id: newMarketId(),
    month,
    purchaseAvgPrice: 0,
    marketPriceStart: 0,
    marketPriceEnd: 0,
    judgment: '',
    remark: '',
  }
}

export function emptyMarketGroup(): MarketProductGroup {
  return {
    id: newMarketId(),
    relatedParty: '',
    productName: '',
    rows: MARKET_MONTHS.map(emptyMarketMonth),
  }
}

export function defaultRelatedPartyMarketSheet(): RelatedPartyMarketSheet {
  return { groups: [emptyMarketGroup()] }
}

export function enrichMarketMonth(row: MarketMonthRow): EnrichedMarketMonthRow {
  const prices = [row.marketPriceStart, row.marketPriceEnd].filter((price) => price > 0)
  const marketLow = prices.length ? Math.min(...prices) : null
  const marketHigh = prices.length ? Math.max(...prices) : null
  const mid = marketLow !== null && marketHigh !== null ? (marketLow + marketHigh) / 2 : null
  const deviationRate = mid && row.purchaseAvgPrice
    ? (row.purchaseAvgPrice - mid) / mid
    : null
  const inRange = marketLow !== null && marketHigh !== null && row.purchaseAvgPrice > 0
    ? row.purchaseAvgPrice >= marketLow && row.purchaseAvgPrice <= marketHigh
    : null
  const isAbnormal = inRange === false
  const suggestedJudgment: MarketJudgment | '' = inRange === null ? '' : inRange ? '是' : '否'
  return { ...row, marketLow, marketHigh, deviationRate, inRange, isAbnormal, suggestedJudgment }
}

export function enrichMarketGroup(group: MarketProductGroup): EnrichedMarketProductGroup {
  const rows = group.rows.map(enrichMarketMonth)
  return {
    ...group,
    rows,
    abnormalCount: rows.filter((row) => row.isAbnormal || row.judgment === '否').length,
    filledMonthCount: rows.filter((row) =>
      row.purchaseAvgPrice > 0 || row.marketPriceStart > 0 || row.marketPriceEnd > 0,
    ).length,
  }
}

function num(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function normalizeGroup(raw: Record<string, unknown>): MarketProductGroup {
  const sourceRows = Array.isArray(raw.rows) ? raw.rows as Record<string, unknown>[] : []
  return {
    id: text(raw.id) || newMarketId(),
    relatedParty: text(raw.relatedParty),
    productName: text(raw.productName),
    rows: MARKET_MONTHS.map((month) => {
      const row = sourceRows.find((item) => num(item.month) === month)
      if (!row) return emptyMarketMonth(month)
      return {
        id: text(row.id) || newMarketId(),
        month,
        purchaseAvgPrice: num(row.purchaseAvgPrice),
        marketPriceStart: num(row.marketPriceStart),
        marketPriceEnd: num(row.marketPriceEnd),
        judgment: row.judgment === '是' || row.judgment === '否' ? row.judgment : '',
        remark: text(row.remark),
      }
    }),
  }
}

interface LegacyMarketRow {
  id?: string
  relatedParty?: string
  itemName?: string
  relatedPrice?: number
  marketPrice?: number
  conclusion?: string
  remark?: string
}

/** 旧版一行一记录迁为“关联方+产品”分组，按出现顺序放入1~12月。 */
function migrateLegacyRows(rows: LegacyMarketRow[]): RelatedPartyMarketSheet {
  const map = new Map<string, MarketProductGroup>()
  for (const legacy of rows) {
    const party = text(legacy.relatedParty).trim()
    const product = text(legacy.itemName).trim()
    const hasData = party || product || num(legacy.relatedPrice) || num(legacy.marketPrice)
    if (!hasData) continue
    const key = `${party}\u0000${product}`
    if (!map.has(key)) {
      const group = emptyMarketGroup()
      group.relatedParty = party
      group.productName = product
      map.set(key, group)
    }
    const group = map.get(key)!
    const index = Math.min(group.rows.filter((row) =>
      row.purchaseAvgPrice || row.marketPriceStart || row.marketPriceEnd).length, 11)
    group.rows[index] = {
      ...group.rows[index],
      id: text(legacy.id) || newMarketId(),
      purchaseAvgPrice: num(legacy.relatedPrice),
      marketPriceStart: num(legacy.marketPrice),
      marketPriceEnd: num(legacy.marketPrice),
      judgment: legacy.conclusion === '公允' || legacy.conclusion === '基本公允' ? '是'
        : legacy.conclusion === '不公允' ? '否' : '',
      remark: text(legacy.remark),
    }
  }
  return { groups: map.size ? [...map.values()] : [emptyMarketGroup()] }
}

export function migrateRelatedPartyMarketSheet(parsed: unknown): RelatedPartyMarketSheet {
  if (Array.isArray(parsed)) return migrateLegacyRows(parsed as LegacyMarketRow[])
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>
    const groups = Array.isArray(obj.groups)
      ? (obj.groups as Record<string, unknown>[]).map(normalizeGroup)
      : []
    return { groups: groups.length ? groups : [emptyMarketGroup()] }
  }
  return defaultRelatedPartyMarketSheet()
}

/** OCR 市场价/挂牌价字段（与后端 market-quote schema 对齐）。 */
export interface MarketQuoteOcrFields {
  relatedParty?: string
  productName?: string
  month?: number | string
  purchaseAvgPrice?: number | string
  marketPriceStart?: number | string
  marketPriceEnd?: number | string
  judgment?: string
  remark?: string
}

export function emptyMarketOcrDraft(): {
  relatedParty: string
  productName: string
  month: number | undefined
  purchaseAvgPrice: number | undefined
  marketPriceStart: number | undefined
  marketPriceEnd: number | undefined
  judgment: string
  remark: string
} {
  return {
    relatedParty: '',
    productName: '',
    month: undefined,
    purchaseAvgPrice: undefined,
    marketPriceStart: undefined,
    marketPriceEnd: undefined,
    judgment: '',
    remark: '',
  }
}

function pickText(current: string, next: unknown, overwrite: boolean): string {
  const candidate = text(next).trim()
  if (!candidate) return current
  if (!overwrite && current.trim()) return current
  return candidate
}

function pickNum(current: number, next: unknown, overwrite: boolean): number {
  const candidate = num(next)
  if (!candidate) return current
  if (!overwrite && current) return current
  return candidate
}

function parseMonth(value: unknown): number | null {
  const n = Math.round(num(value))
  return n >= 1 && n <= 12 ? n : null
}

function normalizeMarketJudgment(value: unknown): MarketJudgment | '' {
  const raw = text(value).trim()
  if (raw === '是' || raw === '否') return raw
  if (raw === '公允' || raw === '基本公允' || raw === '合理') return '是'
  if (raw === '不公允' || raw === '不合理') return '否'
  return ''
}

/** OCR 市场行情回写：匹配/新建组，默认仅填空字段。 */
export function applyMarketOcrToSheet(
  sheet: RelatedPartyMarketSheet,
  fields: MarketQuoteOcrFields,
  opts?: { overwrite?: boolean; targetGroupId?: string },
): RelatedPartyMarketSheet {
  const overwrite = opts?.overwrite === true
  const party = text(fields.relatedParty).trim()
  const product = text(fields.productName).trim()
  let groups = sheet.groups.map((group) => ({
    ...group,
    rows: group.rows.map((row) => ({ ...row })),
  }))

  let groupIndex = -1
  if (opts?.targetGroupId) {
    groupIndex = groups.findIndex((group) => group.id === opts.targetGroupId)
  }
  if (groupIndex < 0 && (party || product)) {
    groupIndex = groups.findIndex((group) =>
      group.relatedParty.trim() === party && group.productName.trim() === product,
    )
  }
  if (groupIndex < 0) {
    const blankIndex = groups.findIndex((group) =>
      !group.relatedParty.trim()
      && !group.productName.trim()
      && !group.rows.some((row) =>
        row.purchaseAvgPrice || row.marketPriceStart || row.marketPriceEnd),
    )
    if (blankIndex >= 0) groupIndex = blankIndex
  }
  if (groupIndex < 0) {
    groups = [...groups, emptyMarketGroup()]
    groupIndex = groups.length - 1
  }

  const group = groups[groupIndex]
  group.relatedParty = pickText(group.relatedParty, party, overwrite)
  group.productName = pickText(group.productName, product, overwrite)

  const month = parseMonth(fields.month)
    ?? group.rows.find((row) =>
      !row.purchaseAvgPrice && !row.marketPriceStart && !row.marketPriceEnd,
    )?.month
    ?? 1
  const rowIndex = group.rows.findIndex((row) => row.month === month)
  if (rowIndex < 0) return { groups }

  const row = group.rows[rowIndex]
  row.purchaseAvgPrice = pickNum(row.purchaseAvgPrice, fields.purchaseAvgPrice, overwrite)
  row.marketPriceStart = pickNum(row.marketPriceStart, fields.marketPriceStart, overwrite)
  row.marketPriceEnd = pickNum(row.marketPriceEnd, fields.marketPriceEnd, overwrite)
  const judgment = normalizeMarketJudgment(fields.judgment)
  if (judgment && (overwrite || !row.judgment)) row.judgment = judgment
  row.remark = pickText(row.remark, fields.remark, overwrite)
  return { groups }
}
