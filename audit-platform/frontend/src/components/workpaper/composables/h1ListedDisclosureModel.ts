/**
 * H1 附注披露（上市公司）数据模型
 *
 * 对齐源模板「附注披露信息（上市公司）」A1:F93：
 *  15、固定资产汇总表
 *  （1）固定资产 → ①情况（原值/折旧/减值/账面价值变动）
 *  【提示区】减值测试/抵押担保/高价出售/政府补助/并购净额
 *  ②暂时闲置 ③经营租出 ④未办妥产权证书 ⑤政府补助金额
 *  （2）固定资产清理
 *
 * 铁律：源模板蓝色固定指引 → textarea placeholder（空值时显示），不作 v-model 默认值。
 */

export const H1_LISTED_ITEM = {
  summary: 'H1-listed-summary',
  categories: 'H1-listed-categories',
  movement: 'H1-listed-movement',
  idle: 'H1-listed-idle-rows',
  leaseOut: 'H1-listed-lease-rows',
  /** 仅 hydrate 读取；persist / H1-19 sync 不再写入 */
  leaseOutLegacy: 'H1-disc-listed-operating_lease_out-rows',
  titleCert: 'H1-listed-title-rows',
  clearing: 'H1-listed-clearing-rows',
  mortgageRows: 'H1-listed-mortgage-rows',
  /** 仅 hydrate 读取；persist / H1-16/17 sync 不再写入上市旧键 */
  mortgageLegacy: 'H1-disc-listed-restricted-rows',
  govSubsidy: 'H1-listed-gov-subsidy',
  fullyDepreciated: 'H1-listed-fully-dep-rows',
  noteImpairment: 'H1-listed-note-impairment',
  noteMortgage: 'H1-listed-note-mortgage',
  noteSale: 'H1-listed-note-sale',
  noteClearing: 'H1-listed-note-clearing',
} as const

/** 默认资产分类列（与 H1_FA_CATEGORIES 对齐；源模板前三列 + 可扩） */
export const H1_LISTED_DEFAULT_CATEGORIES = [
  { key: 'buildings', label: '房屋及建筑物' },
  { key: 'machinery', label: '机器设备' },
  { key: 'transport', label: '运输设备' },
  { key: 'office', label: '办公设备' },
  { key: 'other', label: '其他设备' },
] as const

export type H1ListedCategory = { key: string; label: string }

export type MovementCellMap = Record<string, Record<string, number>>

export type MovementRowKind =
  | 'section'
  | 'subtotal'
  | 'detail'
  | 'ellipsis'
  | 'calc'
  | 'book'

export interface MovementRowDef {
  key: string
  label: string
  indent: number
  kind: MovementRowKind
  /** 可编辑叶子格 */
  editable?: boolean
  /** 合计行：汇总哪些 detail keys */
  sumOf?: string[]
  /** 期末=期初+增-减 */
  endOf?: { begin: string; inc: string; dec: string }
  /** 账面价值 = 原值 - 折旧 - 减值 */
  bookOf?: { cost: string; dep: string; impair: string }
}

/** 源模板 R14–R50 行结构 */
export const H1_LISTED_MOVEMENT_ROWS: MovementRowDef[] = [
  { key: 'cost_section', label: '一、账面原值：', indent: 0, kind: 'section' },
  { key: 'cost_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'cost_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['cost_inc_purchase', 'cost_inc_cip', 'cost_inc_merge', 'cost_inc_other'] },
  { key: 'cost_inc_purchase', label: '（1）购置', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_cip', label: '（2）在建工程转入', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_merge', label: '（3）企业合并增加', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_inc_other', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'cost_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['cost_dec_dispose', 'cost_dec_other', 'cost_dec_ellipsis'] },
  { key: 'cost_dec_dispose', label: '（1）处置或报废', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_other', label: '（2）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'cost_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'cost_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'cost_begin', inc: 'cost_inc', dec: 'cost_dec' } },

  { key: 'dep_section', label: '二、累计折旧', indent: 0, kind: 'section' },
  { key: 'dep_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'dep_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['dep_inc_provision', 'dep_inc_other', 'dep_inc_ellipsis'] },
  { key: 'dep_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'dep_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['dep_dec_dispose', 'dep_dec_other', 'dep_dec_ellipsis'] },
  { key: 'dep_dec_dispose', label: '（1）处置或报废', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_dec_other', label: '（2）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'dep_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'dep_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'dep_begin', inc: 'dep_inc', dec: 'dep_dec' } },

  { key: 'imp_section', label: '三、减值准备', indent: 0, kind: 'section' },
  { key: 'imp_begin', label: '1.期初余额', indent: 1, kind: 'detail', editable: true },
  { key: 'imp_inc', label: '2.本期增加金额', indent: 1, kind: 'subtotal', sumOf: ['imp_inc_provision', 'imp_inc_other', 'imp_inc_ellipsis'] },
  { key: 'imp_inc_provision', label: '（1）计提', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_inc_other', label: '（2）其他增加', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_inc_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'imp_dec', label: '3.本期减少金额', indent: 1, kind: 'subtotal', sumOf: ['imp_dec_dispose', 'imp_dec_other', 'imp_dec_ellipsis'] },
  { key: 'imp_dec_dispose', label: '（1）处置或报废', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_other', label: '（2）其他减少', indent: 2, kind: 'detail', editable: true },
  { key: 'imp_dec_ellipsis', label: '……', indent: 2, kind: 'ellipsis', editable: true },
  { key: 'imp_end', label: '4.期末余额', indent: 1, kind: 'calc', endOf: { begin: 'imp_begin', inc: 'imp_inc', dec: 'imp_dec' } },

  { key: 'book_section', label: '四、账面价值', indent: 0, kind: 'section' },
  { key: 'book_end', label: '1.期末账面价值', indent: 1, kind: 'book', bookOf: { cost: 'cost_end', dep: 'dep_end', impair: 'imp_end' } },
  { key: 'book_begin', label: '2.期初账面价值', indent: 1, kind: 'book', bookOf: { cost: 'cost_begin', dep: 'dep_begin', impair: 'imp_begin' } },
]

/** 源模板 R52–R58 蓝色提示（编制指引，作 placeholder） */
export const H1_LISTED_GUIDANCE = {
  impairment: '【1、长期资产本期进行减值测试的，应披露可收回金额的具体确定方法。可收回金额按公允价值减去处置费用后的净额确定的，应披露公允价值和处置费用的确定方式、关键参数及其确定依据。可收回金额按预计未来现金流量的现值确定的，应披露预测期的年限、预测期及稳定期的关键参数及其确定依据。前述信息与以前年度减值测试采用的信息或外部信息明显不一致的，或公司以前年度减值测试采用信息与当年实际情况明显不一致的，应披露差异原因。（15号文第十九条（十九））】',
  impairmentNote: '注意：1、本年执行减值测试的，即使未计提减值，也要参照上述要求披露。2、估计可收回金额时通常不应使用重置成本法。',
  mortgage: '2、说明抵押、担保的固定资产情况。',
  sale: '3、本期发生以明显高于账面价值的价格出售固定资产交易的，应详细说明交易作价的基础和依据，如：估值模型、重要参数的选取依据和估值过程，以及必要的敏感性分析。',
  govSubsidyOtherDec: '【提示：在“其他减少”中列示本期收到的政府补助冲减固定资产账面价值的金额。对于冲减无形资产或其他资产账面价值的政府补助，比照披露。】',
  mergeNet: '【提示：非同一控制下企业合并中取得被购买方的资产、负债等应按购买日公允价值计量，因此新并购固定资产的增加应以净额列示。新并购无形资产或其他资产的增加，相关科目附注比照上述要求进行列示。】',
  idleAlert: '（提示：《关于严格执行企业会计准则 切实做好企业2025年年报工作的通知》：企业对于停工项目、闲置资产等的减值情况应予以特别关注，并对是否发生减值作出恰当判断和相应会计处理。）',
  titleCert: '（披露期末未办妥产权证书的固定资产账面价值及原因。）',
  fullyDepreciated: '（披露已提足折旧仍继续使用的固定资产账面原值。可点「从 H1-2 带入候选」按净值≈残值自动识别，再由审计师确认。已提足折旧仍在使用，可能表明原估计使用年限偏短，需复核折旧政策合理性。）',
  govSubsidyLine: '本期冲减固定资产账面价值的政府补助金额为XXX元，具体情况见附注八、政府补助。',
  govSubsidyHint: '（提示：对于冲减无形资产或其他资产账面价值的政府补助，在无形资产或其他资产的科目附注中比照上述要求进行披露。）',
  clearingProgress: '（说明转入固定资产清理起始时间已超过1年的固定资产清理进展情况）',
} as const

export interface SummaryRow {
  key: 'fixed_assets' | 'clearing'
  label: string
  endBalance: number
  priorBalance: number
}

export function createDefaultSummary(): SummaryRow[] {
  return [
    { key: 'fixed_assets', label: '固定资产', endBalance: 0, priorBalance: 0 },
    { key: 'clearing', label: '固定资产清理', endBalance: 0, priorBalance: 0 },
  ]
}

export interface IdleRow {
  rowId: string
  name: string
  cost: number
  dep: number
  impairment: number
  bookValue: number
  remark: string
  isPreset?: boolean
}

export const H1_LISTED_IDLE_PRESETS = ['房屋及建筑物', '机器设备', '电子设备', '运输设备'] as const

export function createDefaultIdleRows(): IdleRow[] {
  return H1_LISTED_IDLE_PRESETS.map((name, i) => ({
    rowId: `idle-preset-${i}`,
    name,
    cost: 0,
    dep: 0,
    impairment: 0,
    bookValue: 0,
    remark: '',
    isPreset: true,
  }))
}

export interface LeaseOutRow {
  rowId: string
  name: string
  bookValue: number
  isPreset?: boolean
}

export const H1_LISTED_LEASE_PRESETS = ['房屋及建筑物', '机器设备', '电子设备', '运输设备'] as const

export function createDefaultLeaseRows(): LeaseOutRow[] {
  return H1_LISTED_LEASE_PRESETS.map((name, i) => ({
    rowId: `lease-preset-${i}`,
    name,
    bookValue: 0,
    isPreset: true,
  }))
}

export interface TitleCertRow {
  rowId: string
  name: string
  bookValue: number
  reason: string
}

export interface ClearingRow {
  rowId: string
  name: string
  endBalance: number
  priorBalance: number
  reason: string
}

export interface MortgageRow {
  rowId: string
  name: string
  amount: number
  description: string
  remark: string
}

/** ⑥已提足折旧仍继续使用的固定资产（披露账面原值，按类别） */
export interface FullyDepRow {
  rowId: string
  /** 类别 / 项目 */
  name: string
  /** 账面原值 */
  cost: number
  remark: string
}

export function sumFullyDep(rows: FullyDepRow[]): number {
  return rows.reduce((s, r) => s + num(r.cost), 0)
}

/**
 * 从 H1-2 明细识别「已提足折旧仍在使用」候选：
 * 净值 ≤ 原值 × 残值率(默认5%) 且 累计折旧>0 的资产，按类别汇总账面原值。
 * 结果为候选，需审计师确认（无逐笔预计净残值时的近似判定）。
 */
export function deriveFullyDepreciatedFromDetail(
  detailRows: Array<{
    category?: string
    name?: string
    originalCostEnd?: number
    accDepEnd?: number
    impairmentEnd?: number
    netValue?: number
  }>,
  opts?: { residualRate?: number },
): FullyDepRow[] {
  const residualRate = opts?.residualRate ?? 0.05
  const byCat = new Map<string, number>()
  for (const r of detailRows) {
    const cost = num(r.originalCostEnd)
    if (cost <= 0) continue
    const accDep = num(r.accDepEnd)
    if (accDep <= 0) continue
    const net = r.netValue != null && r.netValue !== undefined
      ? num(r.netValue)
      : cost - accDep - num(r.impairmentEnd)
    if (net > cost * residualRate + 0.005) continue // 尚未提足
    const cat = String(r.category || r.name || '未分类').trim() || '未分类'
    byCat.set(cat, (byCat.get(cat) || 0) + cost)
  }
  return [...byCat.entries()].map(([name, cost], i) => ({
    rowId: `fdep-${i}-${name}`,
    name,
    cost,
    remark: '已提足折旧仍继续使用',
  }))
}

export interface GovSubsidyState {
  amount: number
  /** 用户改写后的整句；空则用模板+金额 */
  text: string
}

export function createDefaultGovSubsidy(): GovSubsidyState {
  return { amount: 0, text: '' }
}

export function formatGovSubsidyLine(amount: number, customText?: string): string {
  if (customText?.trim()) return customText.trim()
  const amt = Number.isFinite(amount) ? amount : 0
  const amtStr = amt.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return `本期冲减固定资产账面价值的政府补助金额为${amtStr}元，具体情况见附注八、政府补助。`
}

export function num(v: unknown): number {
  const x = typeof v === 'number' ? v : parseFloat(String(v ?? '').replace(/,/g, ''))
  return Number.isFinite(x) ? x : 0
}

export function emptyMovement(): MovementCellMap {
  return {}
}

/** 取单格原始录入值（仅 detail/ellipsis） */
export function rawCell(map: MovementCellMap, rowKey: string, catKey: string): number {
  return num(map[rowKey]?.[catKey])
}

/**
 * 计算某分类下列值：subtotal/calc/book 自动推导；section 返回 0。
 * 递归解析 sumOf / endOf / bookOf。
 */
export function cellValue(
  map: MovementCellMap,
  def: MovementRowDef,
  catKey: string,
  defs: readonly MovementRowDef[] = H1_LISTED_MOVEMENT_ROWS,
): number {
  if (def.kind === 'section') return 0
  if (def.kind === 'detail' || def.kind === 'ellipsis') return rawCell(map, def.key, catKey)
  if (def.kind === 'subtotal' && def.sumOf) {
    return def.sumOf.reduce((s, k) => {
      const child = defs.find((d) => d.key === k)
      return s + (child ? cellValue(map, child, catKey, defs) : rawCell(map, k, catKey))
    }, 0)
  }
  if (def.kind === 'calc' && def.endOf) {
    const begin = defs.find((d) => d.key === def.endOf!.begin)
    const inc = defs.find((d) => d.key === def.endOf!.inc)
    const dec = defs.find((d) => d.key === def.endOf!.dec)
    return (
      (begin ? cellValue(map, begin, catKey, defs) : 0)
      + (inc ? cellValue(map, inc, catKey, defs) : 0)
      - (dec ? cellValue(map, dec, catKey, defs) : 0)
    )
  }
  if (def.kind === 'book' && def.bookOf) {
    const cost = defs.find((d) => d.key === def.bookOf!.cost)
    const dep = defs.find((d) => d.key === def.bookOf!.dep)
    const impair = defs.find((d) => d.key === def.bookOf!.impair)
    return (
      (cost ? cellValue(map, cost, catKey, defs) : 0)
      - (dep ? cellValue(map, dep, catKey, defs) : 0)
      - (impair ? cellValue(map, impair, catKey, defs) : 0)
    )
  }
  return 0
}

/** 合计列 = 各类之和 */
export function totalCellValue(
  map: MovementCellMap,
  def: MovementRowDef,
  categories: readonly H1ListedCategory[],
): number {
  if (def.kind === 'section') return 0
  return categories.reduce((s, c) => s + cellValue(map, def, c.key), 0)
}

export function setCell(map: MovementCellMap, rowKey: string, catKey: string, value: number): MovementCellMap {
  const next = { ...map, [rowKey]: { ...(map[rowKey] || {}), [catKey]: num(value) } }
  return next
}

export function idleBookValue(row: Pick<IdleRow, 'cost' | 'dep' | 'impairment'>): number {
  return num(row.cost) - num(row.dep) - num(row.impairment)
}

export function sumIdle(rows: IdleRow[]): { cost: number; dep: number; impairment: number; bookValue: number } {
  return rows.reduce(
    (a, r) => ({
      cost: a.cost + num(r.cost),
      dep: a.dep + num(r.dep),
      impairment: a.impairment + num(r.impairment),
      bookValue: a.bookValue + idleBookValue(r),
    }),
    { cost: 0, dep: 0, impairment: 0, bookValue: 0 },
  )
}

export function sumLease(rows: LeaseOutRow[]): number {
  return rows.reduce((s, r) => s + num(r.bookValue), 0)
}

export function sumClearing(rows: ClearingRow[]): { endBalance: number; priorBalance: number } {
  return rows.reduce(
    (a, r) => ({
      endBalance: a.endBalance + num(r.endBalance),
      priorBalance: a.priorBalance + num(r.priorBalance),
    }),
    { endBalance: 0, priorBalance: 0 },
  )
}

export function summaryTotal(rows: SummaryRow[]): { endBalance: number; priorBalance: number } {
  return rows.reduce(
    (a, r) => ({
      endBalance: a.endBalance + num(r.endBalance),
      priorBalance: a.priorBalance + num(r.priorBalance),
    }),
    { endBalance: 0, priorBalance: 0 },
  )
}

/** 分类名 → 默认列 key（对齐 h1CategoryClassify / H1-1 五类） */
export function categoryKeyFromLabel(label: string): string {
  const map: Record<string, string> = {
    房屋及建筑物: 'buildings',
    '房屋、建筑物': 'buildings',
    机器设备: 'machinery',
    运输设备: 'transport',
    运输工具: 'transport',
    电子设备: 'office',
    办公设备: 'office',
    其他设备: 'other',
    其他: 'other',
  }
  if (map[label]) return map[label]
  return `cat_${label.replace(/\s+/g, '_')}`
}

/**
 * 从 H1-1 审定表原值/折旧行 seed 变动表（仅在变动表全 0 时调用）。
 * 映射：期初/本期借方→购置(粗)/本期贷方→处置/期末。
 */
export function seedMovementFromAdjudication(
  costRows: Array<{ category?: string; beginBalance?: number; debit?: number; credit?: number; endBalance?: number }>,
  depRows: Array<{ category?: string; beginBalance?: number; debit?: number; credit?: number; endBalance?: number }>,
  categories: H1ListedCategory[],
): { categories: H1ListedCategory[]; movement: MovementCellMap } {
  const catMap = new Map(categories.map((c) => [c.label, c.key]))
  const nextCats = [...categories]
  let movement: MovementCellMap = {}

  const ensureCat = (label: string) => {
    const name = String(label || '').trim()
    if (!name || name.includes('小计') || name.includes('合计')) return null
    let key = catMap.get(name)
    if (!key) {
      key = categoryKeyFromLabel(name)
      if (!catMap.has(name)) {
        nextCats.push({ key, label: name })
        catMap.set(name, key)
      }
    }
    return key
  }

  for (const r of costRows) {
    const key = ensureCat(String(r.category || ''))
    if (!key) continue
    movement = setCell(movement, 'cost_begin', key, num(r.beginBalance))
    movement = setCell(movement, 'cost_inc_purchase', key, num(r.debit))
    movement = setCell(movement, 'cost_dec_dispose', key, num(r.credit))
  }
  for (const r of depRows) {
    const key = ensureCat(String(r.category || ''))
    if (!key) continue
    movement = setCell(movement, 'dep_begin', key, num(r.beginBalance))
    // 折旧：贷方=计提增加，借方=处置转销
    movement = setCell(movement, 'dep_inc_provision', key, num(r.credit))
    movement = setCell(movement, 'dep_dec_dispose', key, num(r.debit))
  }

  return { categories: nextCats, movement }
}

/** 变动表是否全空（用于判断是否可从审定表 seed） */
export function isMovementEmpty(map: MovementCellMap): boolean {
  for (const row of Object.values(map)) {
    for (const v of Object.values(row || {})) {
      if (num(v) !== 0) return false
    }
  }
  return true
}

export function newRowId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}
