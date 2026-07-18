/** F2-65 关联方采购定价公允性核查（询价函）纯函数层。 */
export const F2_65_OBJECTIVE = '审计目标：向独立可比供应商询价并按月比较关联方采购价格，评价关联方采购定价是否公允，识别利益输送、虚增成本或采购价格操纵风险。'
export const INQUIRY_MONTHS = Array.from({ length: 12 }, (_, i) => i + 1)
export const PRICE_SPREAD_THRESHOLD = 0.1
export const PRICING_JUDGMENTS = ['合理', '基本合理', '不合理', '待核实'] as const
export type PricingJudgment = typeof PRICING_JUDGMENTS[number]

let seq = 0
export function newInquiryId(): string {
  seq += 1
  return `inq-${Date.now().toString(36)}-${seq}`
}

export interface InquiryMonthRow {
  id: string
  month: number
  productSpec: string
  relatedPrice: number
  comparablePrices: [number, number, number, number]
  judgment: PricingJudgment | ''
  remark: string
}

export interface EnrichedInquiryMonthRow extends InquiryMonthRow {
  comparableAverage: number | null
  spreadRate: number | null
  isAbnormal: boolean
  suggestedJudgment: PricingJudgment | ''
}

export interface RelatedPartyProductGroup {
  id: string
  relatedParty: string
  productName: string
  comparableSuppliers: [string, string, string, string]
  rows: InquiryMonthRow[]
}

export interface EnrichedRelatedPartyProductGroup extends Omit<RelatedPartyProductGroup, 'rows'> {
  rows: EnrichedInquiryMonthRow[]
  abnormalCount: number
  filledMonthCount: number
}

export interface RelatedPartyInquirySheet {
  groups: RelatedPartyProductGroup[]
}

export function emptyInquiryMonth(month: number): InquiryMonthRow {
  return {
    id: newInquiryId(),
    month,
    productSpec: '',
    relatedPrice: 0,
    comparablePrices: [0, 0, 0, 0],
    judgment: '',
    remark: '',
  }
}

export function emptyInquiryGroup(): RelatedPartyProductGroup {
  return {
    id: newInquiryId(),
    relatedParty: '',
    productName: '',
    comparableSuppliers: ['询价单位1', '询价单位2', '询价单位3', '询价单位4'],
    rows: INQUIRY_MONTHS.map(emptyInquiryMonth),
  }
}

export function defaultRelatedPartyInquirySheet(): RelatedPartyInquirySheet {
  return { groups: [emptyInquiryGroup()] }
}

export function enrichInquiryMonth(row: InquiryMonthRow): EnrichedInquiryMonthRow {
  const valid = row.comparablePrices.filter((price) => Number.isFinite(price) && price > 0)
  const comparableAverage = valid.length
    ? valid.reduce((sum, price) => sum + price, 0) / valid.length
    : null
  const spreadRate = comparableAverage && row.relatedPrice
    ? (row.relatedPrice - comparableAverage) / comparableAverage
    : null
  const isAbnormal = spreadRate !== null && Math.abs(spreadRate) > PRICE_SPREAD_THRESHOLD
  const suggestedJudgment: PricingJudgment | '' = spreadRate === null
    ? ''
    : isAbnormal ? '待核实' : '合理'
  return { ...row, comparableAverage, spreadRate, isAbnormal, suggestedJudgment }
}

export function enrichInquiryGroup(group: RelatedPartyProductGroup): EnrichedRelatedPartyProductGroup {
  const rows = group.rows.map(enrichInquiryMonth)
  return {
    ...group,
    rows,
    abnormalCount: rows.filter((row) => row.isAbnormal || row.judgment === '不合理' || row.judgment === '待核实').length,
    filledMonthCount: rows.filter((row) =>
      Boolean(row.productSpec.trim()) || row.relatedPrice > 0 || row.comparablePrices.some((price) => price > 0),
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

function normalizePrices(value: unknown): [number, number, number, number] {
  const values = Array.isArray(value) ? value.map(num) : []
  return [values[0] || 0, values[1] || 0, values[2] || 0, values[3] || 0]
}

function normalizeGroup(raw: Record<string, unknown>): RelatedPartyProductGroup {
  const sourceRows = Array.isArray(raw.rows) ? raw.rows as Record<string, unknown>[] : []
  return {
    id: text(raw.id) || newInquiryId(),
    relatedParty: text(raw.relatedParty),
    productName: text(raw.productName),
    comparableSuppliers: (() => {
      const source = Array.isArray(raw.comparableSuppliers) ? raw.comparableSuppliers.map(String) : []
      return [
        source[0] || '询价单位1', source[1] || '询价单位2',
        source[2] || '询价单位3', source[3] || '询价单位4',
      ]
    })(),
    rows: INQUIRY_MONTHS.map((month) => {
      const row = sourceRows.find((item) => num(item.month) === month)
      if (!row) return emptyInquiryMonth(month)
      return {
        id: text(row.id) || newInquiryId(),
        month,
        productSpec: text(row.productSpec),
        relatedPrice: num(row.relatedPrice),
        comparablePrices: normalizePrices(row.comparablePrices),
        judgment: PRICING_JUDGMENTS.includes(row.judgment as PricingJudgment)
          ? row.judgment as PricingJudgment : '',
        remark: text(row.remark),
      }
    }),
  }
}

interface LegacyInquiryRow {
  id?: string
  relatedParty?: string
  itemName?: string
  relatedPrice?: number
  thirdPartyName?: string
  inquiryPrice?: number
  conclusion?: string
  remark?: string
}

/** 旧版一行一询价记录迁为“关联方+产品”分组，按出现顺序放入1~12月。 */
function migrateLegacyRows(rows: LegacyInquiryRow[]): RelatedPartyInquirySheet {
  const map = new Map<string, RelatedPartyProductGroup>()
  for (const legacy of rows) {
    const party = text(legacy.relatedParty).trim()
    const product = text(legacy.itemName).trim()
    const hasData = party || product || num(legacy.relatedPrice) || num(legacy.inquiryPrice)
    if (!hasData) continue
    const key = `${party}\u0000${product}`
    if (!map.has(key)) {
      const group = emptyInquiryGroup()
      group.relatedParty = party
      group.productName = product
      if (text(legacy.thirdPartyName).trim()) group.comparableSuppliers[0] = text(legacy.thirdPartyName).trim()
      map.set(key, group)
    }
    const group = map.get(key)!
    const index = Math.min(group.rows.filter((row) =>
      row.relatedPrice || row.comparablePrices.some((price) => price > 0)).length, 11)
    group.rows[index] = {
      ...group.rows[index],
      id: text(legacy.id) || newInquiryId(),
      relatedPrice: num(legacy.relatedPrice),
      comparablePrices: [num(legacy.inquiryPrice), 0, 0, 0],
      judgment: legacy.conclusion === '公允' ? '合理'
        : legacy.conclusion === '基本公允' ? '基本合理'
          : legacy.conclusion === '不公允' ? '不合理'
            : legacy.conclusion === '待核实' ? '待核实' : '',
      remark: text(legacy.remark),
    }
  }
  return { groups: map.size ? [...map.values()] : [emptyInquiryGroup()] }
}

export function migrateRelatedPartyInquirySheet(parsed: unknown): RelatedPartyInquirySheet {
  if (Array.isArray(parsed)) return migrateLegacyRows(parsed as LegacyInquiryRow[])
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>
    const groups = Array.isArray(obj.groups)
      ? (obj.groups as Record<string, unknown>[]).map(normalizeGroup)
      : []
    return { groups: groups.length ? groups : [emptyInquiryGroup()] }
  }
  return defaultRelatedPartyInquirySheet()
}

/** OCR 询价函字段（与后端 inquiry-letter schema 对齐）。 */
export interface InquiryLetterOcrFields {
  relatedParty?: string
  productName?: string
  month?: number | string
  productSpec?: string
  relatedPrice?: number | string
  supplier1?: string
  price1?: number | string
  supplier2?: string
  price2?: number | string
  supplier3?: string
  price3?: number | string
  supplier4?: string
  price4?: number | string
  judgment?: string
  remark?: string
}

export const INQUIRY_OCR_FIELD_LABELS: Record<keyof InquiryLetterOcrFields, string> = {
  relatedParty: '关联方名称',
  productName: '采购产品名称',
  month: '所属月份',
  productSpec: '产品规格',
  relatedPrice: '关联方采购价格',
  supplier1: '询价单位1',
  price1: '询价单位1报价',
  supplier2: '询价单位2',
  price2: '询价单位2报价',
  supplier3: '询价单位3',
  price3: '询价单位3报价',
  supplier4: '询价单位4',
  price4: '询价单位4报价',
  judgment: '是否合理',
  remark: '备注',
}

function isBlank(value: unknown): boolean {
  return value == null || value === '' || value === 0
}

function parseMonth(value: unknown): number | null {
  const n = Math.round(num(value))
  return n >= 1 && n <= 12 ? n : null
}

function normalizeJudgment(value: unknown): PricingJudgment | '' {
  const raw = text(value).trim()
  if (PRICING_JUDGMENTS.includes(raw as PricingJudgment)) return raw as PricingJudgment
  if (raw === '公允') return '合理'
  if (raw === '基本公允') return '基本合理'
  if (raw === '不公允') return '不合理'
  return ''
}

const DEFAULT_SUPPLIER_LABELS = ['询价单位1', '询价单位2', '询价单位3', '询价单位4'] as const

function isBlankSupplier(value: string): boolean {
  const trimmed = value.trim()
  return !trimmed || (DEFAULT_SUPPLIER_LABELS as readonly string[]).includes(trimmed)
}

function pickSupplier(current: string, next: unknown, overwrite: boolean): string {
  const candidate = text(next).trim()
  if (!candidate) return current
  if (!overwrite && !isBlankSupplier(current)) return current
  return candidate
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

/**
 * 将 OCR 询价函字段回写到 sheet。
 * - 按关联方+产品匹配已有组，找不到则新建
 * - 默认写入指定月份；未指定则取首个空月（或第1月）
 * - overwrite=false 时仅填空字段，便于二次编辑前保留手工值
 */
export function applyInquiryOcrToSheet(
  sheet: RelatedPartyInquirySheet,
  fields: InquiryLetterOcrFields,
  opts?: { overwrite?: boolean; targetGroupId?: string },
): RelatedPartyInquirySheet {
  const overwrite = opts?.overwrite === true
  const party = text(fields.relatedParty).trim()
  const product = text(fields.productName).trim()
  let groups = sheet.groups.map((group) => ({
    ...group,
    comparableSuppliers: [...group.comparableSuppliers] as RelatedPartyProductGroup['comparableSuppliers'],
    rows: group.rows.map((row) => ({
      ...row,
      comparablePrices: [...row.comparablePrices] as InquiryMonthRow['comparablePrices'],
    })),
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
        row.productSpec.trim() || row.relatedPrice || row.comparablePrices.some((price) => price > 0)),
    )
    if (blankIndex >= 0) groupIndex = blankIndex
  }
  if (groupIndex < 0) {
    groups = [...groups, emptyInquiryGroup()]
    groupIndex = groups.length - 1
  }

  const group = groups[groupIndex]
  group.relatedParty = pickText(group.relatedParty, party, overwrite)
  group.productName = pickText(group.productName, product, overwrite)
  const suppliers: [string, string, string, string] = [
    pickSupplier(group.comparableSuppliers[0], fields.supplier1, overwrite),
    pickSupplier(group.comparableSuppliers[1], fields.supplier2, overwrite),
    pickSupplier(group.comparableSuppliers[2], fields.supplier3, overwrite),
    pickSupplier(group.comparableSuppliers[3], fields.supplier4, overwrite),
  ]
  group.comparableSuppliers = suppliers

  const month = parseMonth(fields.month)
    ?? group.rows.find((row) =>
      !row.productSpec.trim() && !row.relatedPrice && !row.comparablePrices.some((price) => price > 0),
    )?.month
    ?? 1
  const rowIndex = group.rows.findIndex((row) => row.month === month)
  if (rowIndex < 0) return { groups }

  const row = group.rows[rowIndex]
  row.productSpec = pickText(row.productSpec, fields.productSpec, overwrite)
  row.relatedPrice = pickNum(row.relatedPrice, fields.relatedPrice, overwrite)
  row.comparablePrices = [
    pickNum(row.comparablePrices[0], fields.price1, overwrite),
    pickNum(row.comparablePrices[1], fields.price2, overwrite),
    pickNum(row.comparablePrices[2], fields.price3, overwrite),
    pickNum(row.comparablePrices[3], fields.price4, overwrite),
  ]
  const judgment = normalizeJudgment(fields.judgment)
  if (judgment && (overwrite || !row.judgment)) row.judgment = judgment
  row.remark = pickText(row.remark, fields.remark, overwrite)

  return { groups }
}

export function emptyInquiryOcrDraft(): {
  relatedParty: string
  productName: string
  month: number | undefined
  productSpec: string
  relatedPrice: number | undefined
  supplier1: string
  price1: number | undefined
  supplier2: string
  price2: number | undefined
  supplier3: string
  price3: number | undefined
  supplier4: string
  price4: number | undefined
  judgment: string
  remark: string
} {
  return {
    relatedParty: '',
    productName: '',
    month: undefined,
    productSpec: '',
    relatedPrice: undefined,
    supplier1: '',
    price1: undefined,
    supplier2: '',
    price2: undefined,
    supplier3: '',
    price3: undefined,
    supplier4: '',
    price4: undefined,
    judgment: '',
    remark: '',
  }
}

export function isInquiryOcrFieldFilled(fields: InquiryLetterOcrFields): boolean {
  return Object.values(fields).some((value) => !isBlank(value))
}
