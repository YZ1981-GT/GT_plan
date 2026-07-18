/**
 * useF2CapacityEnergyFormulas — F2-63 存货产量与产能、能耗分析表（纯函数层）
 *
 * 源表结构（致同模板）：
 *   一、实际产量与产能比较分析：存货名称 | 本年产量 | 全年产能 | 产能利用率(自动) | 备注
 *   二、期末库存与库存容量比较：仓库名称 | 存货名称 | 实际库存量 | 库存容量 | 容量利用率(自动)
 *       | 已有订单数量/金额 | 期后销售数量/金额，按仓库分组小计
 *   三、实际产量与能耗比较分析：
 *       (a) 能源采购对比：采购项目(水/电/燃气/蒸汽…) × 本期/上期(采购数量/采购金额/单价自动)
 *       (b) 产品能耗：产品 | 本年产量 | 耗用能耗(水/电/燃气) | 单位能耗(自动)
 *           | 上年单位能耗 | 变动(自动) | 变动率(自动)
 *   四、审计说明（3条）　五、审计结论
 */

export const F2_63_OBJECTIVE
  = '审计目标：通过实际产量与产能、期末库存与库存容量、产量与能耗的匹配性分析，'
  + '倒推验证发行人产量、销量及存货数据的真实性与合理性。'

export const F2_63_TIPS: string[] = [
  '1.底稿中仅列示了实际产量与产能比较、期末库存与库存容量比较的参考格式，请结合公司实际情况和审计程序要求设计和编制相关底稿。',
  '2.识别与存货成本密切相关的联动成本因素（如关键原材料、水电费等），根据标准单耗指标，以及工资表、水费单、电费单、运费单等测算发行人真实的产量和销量，'
  + '并倒推采购量，将其实际采购量情况、存货收发存情况与投入产出结合比较，以分析本期存货产、销、存的合理性，分析说明有无重大异常。',
]

/** 产能/容量利用率超过该值标红 */
export const UTILIZATION_WARN_THRESHOLD = 1
/** 单位能耗、能源单价同比变动超过 ±20% 标红 */
export const ENERGY_CHANGE_THRESHOLD = 0.2

/** 能源采购项目预置行（模板固定列示 水/电/燃气/蒸汽） */
export const ENERGY_ITEM_PRESETS = ['水', '电', '燃气', '蒸汽'] as const

let seq = 0
export function newCapacityEnergyId(): string {
  seq += 1
  return `ce-${Date.now().toString(36)}-${seq}`
}

// ─── 一、实际产量与产能比较 ─────────────────────────────────────────────

export interface CapacityCompareRow {
  id: string
  inventoryName: string
  annualOutput: number
  annualCapacity: number
  remark: string
}

export interface EnrichedCapacityCompareRow extends CapacityCompareRow {
  /** 产能利用率 = 本年产量 / 全年产能；产能为0返回 null */
  utilizationRate: number | null
  isAbnormal: boolean
}

export function emptyCapacityRow(): CapacityCompareRow {
  return { id: newCapacityEnergyId(), inventoryName: '', annualOutput: 0, annualCapacity: 0, remark: '' }
}

export function isBlankCapacityRow(row: CapacityCompareRow): boolean {
  return !(row.inventoryName || '').trim()
    && !row.annualOutput && !row.annualCapacity
    && !(row.remark || '').trim()
}

export function enrichCapacityRow(row: CapacityCompareRow): EnrichedCapacityCompareRow {
  const utilizationRate = row.annualCapacity ? row.annualOutput / row.annualCapacity : null
  return {
    ...row,
    utilizationRate,
    isAbnormal: utilizationRate !== null && utilizationRate > UTILIZATION_WARN_THRESHOLD,
  }
}

// ─── 二、期末库存与库存容量比较 ─────────────────────────────────────────

export interface StorageCompareRow {
  id: string
  warehouseName: string
  inventoryName: string
  actualStock: number
  storageCapacity: number
  orderQty: number
  orderAmount: number
  postSaleQty: number
  postSaleAmount: number
}

export interface EnrichedStorageRow extends StorageCompareRow {
  utilizationRate: number | null
  isAbnormal: boolean
}

export interface StorageWarehouseGroup {
  warehouseName: string
  rows: EnrichedStorageRow[]
  subtotal: {
    actualStock: number
    storageCapacity: number
    utilizationRate: number | null
    orderQty: number
    orderAmount: number
    postSaleQty: number
    postSaleAmount: number
  }
}

export function emptyStorageRow(): StorageCompareRow {
  return {
    id: newCapacityEnergyId(),
    warehouseName: '', inventoryName: '',
    actualStock: 0, storageCapacity: 0,
    orderQty: 0, orderAmount: 0,
    postSaleQty: 0, postSaleAmount: 0,
  }
}

export function isBlankStorageRow(row: StorageCompareRow): boolean {
  return !(row.warehouseName || '').trim()
    && !(row.inventoryName || '').trim()
    && !row.actualStock && !row.storageCapacity
    && !row.orderQty && !row.orderAmount
    && !row.postSaleQty && !row.postSaleAmount
}

export function enrichStorageRow(row: StorageCompareRow): EnrichedStorageRow {
  const utilizationRate = row.storageCapacity ? row.actualStock / row.storageCapacity : null
  return {
    ...row,
    utilizationRate,
    isAbnormal: utilizationRate !== null && utilizationRate > UTILIZATION_WARN_THRESHOLD,
  }
}

/** 按仓库名称分组（保持首次出现顺序），并计算各仓库小计 */
export function groupStorageRows(rows: StorageCompareRow[]): StorageWarehouseGroup[] {
  const order: string[] = []
  const byName = new Map<string, EnrichedStorageRow[]>()
  for (const row of rows) {
    const key = (row.warehouseName || '').trim() || '（未填写仓库）'
    if (!byName.has(key)) {
      byName.set(key, [])
      order.push(key)
    }
    byName.get(key)!.push(enrichStorageRow(row))
  }
  return order.map((warehouseName) => {
    const groupRows = byName.get(warehouseName)!
    const actualStock = groupRows.reduce((s, r) => s + (r.actualStock || 0), 0)
    const storageCapacity = groupRows.reduce((s, r) => s + (r.storageCapacity || 0), 0)
    return {
      warehouseName,
      rows: groupRows,
      subtotal: {
        actualStock,
        storageCapacity,
        utilizationRate: storageCapacity ? actualStock / storageCapacity : null,
        orderQty: groupRows.reduce((s, r) => s + (r.orderQty || 0), 0),
        orderAmount: groupRows.reduce((s, r) => s + (r.orderAmount || 0), 0),
        postSaleQty: groupRows.reduce((s, r) => s + (r.postSaleQty || 0), 0),
        postSaleAmount: groupRows.reduce((s, r) => s + (r.postSaleAmount || 0), 0),
      },
    }
  })
}

// ─── 三(a)、能源采购对比 ────────────────────────────────────────────────

export interface EnergyPurchaseRow {
  id: string
  itemName: string
  currentQty: number
  currentAmount: number
  priorQty: number
  priorAmount: number
}

export interface EnrichedEnergyPurchaseRow extends EnergyPurchaseRow {
  currentUnitPrice: number | null
  priorUnitPrice: number | null
  /** 本期单价较上期变动率 */
  priceChangeRate: number | null
  isAbnormal: boolean
}

export function emptyEnergyRow(itemName = ''): EnergyPurchaseRow {
  return { id: newCapacityEnergyId(), itemName, currentQty: 0, currentAmount: 0, priorQty: 0, priorAmount: 0 }
}

export function isBlankEnergyRow(row: EnergyPurchaseRow): boolean {
  return !(row.itemName || '').trim()
    && !row.currentQty && !row.currentAmount
    && !row.priorQty && !row.priorAmount
}

/** 预置项目名且无数据的行，导出/统计时视为未填写 */
export function isUnusedEnergyRow(row: EnergyPurchaseRow): boolean {
  return !row.currentQty && !row.currentAmount && !row.priorQty && !row.priorAmount
}

export function enrichEnergyRow(row: EnergyPurchaseRow): EnrichedEnergyPurchaseRow {
  const currentUnitPrice = row.currentQty ? row.currentAmount / row.currentQty : null
  const priorUnitPrice = row.priorQty ? row.priorAmount / row.priorQty : null
  const priceChangeRate = currentUnitPrice !== null && priorUnitPrice
    ? (currentUnitPrice - priorUnitPrice) / priorUnitPrice
    : null
  return {
    ...row,
    currentUnitPrice,
    priorUnitPrice,
    priceChangeRate,
    isAbnormal: priceChangeRate !== null && Math.abs(priceChangeRate) > ENERGY_CHANGE_THRESHOLD,
  }
}

export function calcEnergyTotals(rows: EnergyPurchaseRow[]): {
  currentAmount: number
  priorAmount: number
} {
  return {
    currentAmount: rows.reduce((s, r) => s + (r.currentAmount || 0), 0),
    priorAmount: rows.reduce((s, r) => s + (r.priorAmount || 0), 0),
  }
}

// ─── 三(b)、产品能耗 ────────────────────────────────────────────────────

export interface ProductEnergyRow {
  id: string
  productName: string
  annualOutput: number
  waterUsage: number
  elecUsage: number
  gasUsage: number
  priorUnitEnergy: number
}

export interface EnrichedProductEnergyRow extends ProductEnergyRow {
  totalEnergy: number
  /** 单位能耗 = (水+电+燃气) / 本年产量 */
  unitEnergy: number | null
  /** 变动 = 单位能耗 - 上年单位能耗 */
  change: number | null
  /** 变动率 = 变动 / 上年单位能耗 */
  changeRate: number | null
  isAbnormal: boolean
}

export function emptyProductEnergyRow(): ProductEnergyRow {
  return {
    id: newCapacityEnergyId(),
    productName: '', annualOutput: 0,
    waterUsage: 0, elecUsage: 0, gasUsage: 0,
    priorUnitEnergy: 0,
  }
}

export function isBlankProductEnergyRow(row: ProductEnergyRow): boolean {
  return !(row.productName || '').trim()
    && !row.annualOutput
    && !row.waterUsage && !row.elecUsage && !row.gasUsage
    && !row.priorUnitEnergy
}

export function enrichProductEnergyRow(row: ProductEnergyRow): EnrichedProductEnergyRow {
  const totalEnergy = (row.waterUsage || 0) + (row.elecUsage || 0) + (row.gasUsage || 0)
  const unitEnergy = row.annualOutput ? totalEnergy / row.annualOutput : null
  const change = unitEnergy !== null && row.priorUnitEnergy ? unitEnergy - row.priorUnitEnergy : null
  const changeRate = change !== null && row.priorUnitEnergy ? change / row.priorUnitEnergy : null
  return {
    ...row,
    totalEnergy,
    unitEnergy,
    change,
    changeRate,
    isAbnormal: changeRate !== null && Math.abs(changeRate) > ENERGY_CHANGE_THRESHOLD,
  }
}

// ─── 整表模型 ──────────────────────────────────────────────────────────

export interface CapacityEnergySheet {
  capacityRows: CapacityCompareRow[]
  storageRows: StorageCompareRow[]
  energyRows: EnergyPurchaseRow[]
  productEnergyRows: ProductEnergyRow[]
}

export function defaultCapacityEnergySheet(): CapacityEnergySheet {
  return {
    capacityRows: [emptyCapacityRow()],
    storageRows: [emptyStorageRow()],
    energyRows: ENERGY_ITEM_PRESETS.map((name) => emptyEnergyRow(name)),
    productEnergyRows: [emptyProductEnergyRow()],
  }
}

function pruneRows<T>(rows: T[], isBlank: (row: T) => boolean, fallback: () => T): T[] {
  const filled = rows.filter((row) => !isBlank(row))
  return filled.length ? filled : [fallback()]
}

// ─── 旧数据迁移 ─────────────────────────────────────────────────────────

interface LegacyCapacityEnergyRow {
  id?: string
  productName?: string
  productLine?: string
  designCapacity?: number
  actualOutput?: number
  elecTotal?: number
  waterTotal?: number
  gasTotal?: number
  priorOutput?: number
  priorElecTotal?: number
  changeNote?: string
  auditFocus?: string
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : ''
}

function isBlankLegacyRow(r: LegacyCapacityEnergyRow): boolean {
  return !str(r.productName).trim() && !str(r.productLine).trim()
    && !num(r.designCapacity) && !num(r.actualOutput)
    && !num(r.elecTotal) && !num(r.waterTotal) && !num(r.gasTotal)
    && !num(r.priorOutput) && !num(r.priorElecTotal)
    && !str(r.changeNote).trim() && !str(r.auditFocus).trim()
}

/** 旧版扁平行 → 拆到「产能比较」和「产品能耗」两个区块 */
function migrateLegacyRows(rows: LegacyCapacityEnergyRow[]): CapacityEnergySheet {
  const sheet = defaultCapacityEnergySheet()
  const filled = rows.filter((r) => !isBlankLegacyRow(r))
  if (!filled.length) return sheet
  sheet.capacityRows = filled.map((r) => ({
    id: newCapacityEnergyId(),
    inventoryName: [str(r.productName).trim(), str(r.productLine).trim()].filter(Boolean).join(' / '),
    annualOutput: num(r.actualOutput),
    annualCapacity: num(r.designCapacity),
    remark: [str(r.changeNote).trim(), str(r.auditFocus).trim()].filter(Boolean).join('；'),
  }))
  sheet.productEnergyRows = filled.map((r) => ({
    id: newCapacityEnergyId(),
    productName: str(r.productName).trim(),
    annualOutput: num(r.actualOutput),
    waterUsage: num(r.waterTotal),
    elecUsage: num(r.elecTotal),
    gasUsage: num(r.gasTotal),
    priorUnitEnergy: num(r.priorOutput) ? num(r.priorElecTotal) / num(r.priorOutput) : 0,
  }))
  return sheet
}

function normalizeCapacityRow(raw: Record<string, unknown>): CapacityCompareRow {
  return {
    id: str(raw.id) || newCapacityEnergyId(),
    inventoryName: str(raw.inventoryName),
    annualOutput: num(raw.annualOutput),
    annualCapacity: num(raw.annualCapacity),
    remark: str(raw.remark),
  }
}

function normalizeStorageRow(raw: Record<string, unknown>): StorageCompareRow {
  return {
    id: str(raw.id) || newCapacityEnergyId(),
    warehouseName: str(raw.warehouseName),
    inventoryName: str(raw.inventoryName),
    actualStock: num(raw.actualStock),
    storageCapacity: num(raw.storageCapacity),
    orderQty: num(raw.orderQty),
    orderAmount: num(raw.orderAmount),
    postSaleQty: num(raw.postSaleQty),
    postSaleAmount: num(raw.postSaleAmount),
  }
}

function normalizeEnergyRow(raw: Record<string, unknown>): EnergyPurchaseRow {
  return {
    id: str(raw.id) || newCapacityEnergyId(),
    itemName: str(raw.itemName),
    currentQty: num(raw.currentQty),
    currentAmount: num(raw.currentAmount),
    priorQty: num(raw.priorQty),
    priorAmount: num(raw.priorAmount),
  }
}

function normalizeProductEnergyRow(raw: Record<string, unknown>): ProductEnergyRow {
  return {
    id: str(raw.id) || newCapacityEnergyId(),
    productName: str(raw.productName),
    annualOutput: num(raw.annualOutput),
    waterUsage: num(raw.waterUsage),
    elecUsage: num(raw.elecUsage),
    gasUsage: num(raw.gasUsage),
    priorUnitEnergy: num(raw.priorUnitEnergy),
  }
}

/**
 * 兼容两种历史结构：
 *  - 旧版：扁平 CapacityEnergyRow[]（productName/designCapacity/elecTotal…）
 *  - 新版：{ capacityRows, storageRows, energyRows, productEnergyRows }
 */
export function migrateCapacityEnergySheet(parsed: unknown): CapacityEnergySheet {
  if (Array.isArray(parsed)) {
    return migrateLegacyRows(parsed as LegacyCapacityEnergyRow[])
  }
  if (parsed && typeof parsed === 'object') {
    const obj = parsed as Record<string, unknown>
    const capacityRows = Array.isArray(obj.capacityRows)
      ? (obj.capacityRows as Record<string, unknown>[]).map(normalizeCapacityRow)
      : []
    const storageRows = Array.isArray(obj.storageRows)
      ? (obj.storageRows as Record<string, unknown>[]).map(normalizeStorageRow)
      : []
    const energyRows = Array.isArray(obj.energyRows)
      ? (obj.energyRows as Record<string, unknown>[]).map(normalizeEnergyRow)
      : []
    const productEnergyRows = Array.isArray(obj.productEnergyRows)
      ? (obj.productEnergyRows as Record<string, unknown>[]).map(normalizeProductEnergyRow)
      : []
    return {
      capacityRows: pruneRows(capacityRows, isBlankCapacityRow, emptyCapacityRow),
      storageRows: pruneRows(storageRows, isBlankStorageRow, emptyStorageRow),
      energyRows: energyRows.filter((r) => !isBlankEnergyRow(r)).length
        ? energyRows.filter((r) => !isBlankEnergyRow(r))
        : ENERGY_ITEM_PRESETS.map((name) => emptyEnergyRow(name)),
      productEnergyRows: pruneRows(productEnergyRows, isBlankProductEnergyRow, emptyProductEnergyRow),
    }
  }
  return defaultCapacityEnergySheet()
}
