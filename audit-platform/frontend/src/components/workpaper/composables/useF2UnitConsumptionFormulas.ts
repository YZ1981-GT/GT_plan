/**
 * F2-64 主要产品生产成本及单耗分析（纯函数层）
 * 源表四部分：成本构成、成本衔接、单位成本、主要原材料耗用。
 */
export const F2_64_OBJECTIVE = '审计目标：按月分析主要产品生产成本构成、成本衔接、单位成本及主要原材料单耗，验证成本归集与结转的准确性，并与上年及同行业水平交叉比较。'
export const MONTH_LABELS = Array.from({ length: 12 }, (_, i) => `${i + 1}月`)
export const CHANGE_THRESHOLD = 0.2

let seq = 0
export function newUnitConsumptionId(): string {
  seq += 1
  return `uc-${Date.now().toString(36)}-${seq}`
}

export interface CostStructureMonth {
  id: string
  period: 'current' | 'prior'
  month: number
  material1: number
  material2: number
  material3: number
  otherMaterial: number
  directLabor: number
  manufacturing: number
}

export interface EnrichedCostStructureMonth extends CostStructureMonth {
  total: number
  rates: {
    material1: number | null
    material2: number | null
    material3: number | null
    otherMaterial: number | null
    directLabor: number | null
    manufacturing: number | null
  }
}

export interface CostFlowMonth {
  id: string
  period: 'current' | 'prior'
  month: number
  openingWip: number
  materialInput: number
  laborInput: number
  manufacturingInput: number
  endingWip: number
  outputQty: number
}

export interface EnrichedCostFlowMonth extends CostFlowMonth {
  productionCost: number
  unitCost: number | null
}

export interface UnitCostMonth {
  id: string
  period: 'current' | 'prior'
  month: number
  openingFinished: number
  directMaterial: number
  directLabor: number
  manufacturing: number
  endingFinished: number
  outputQty: number
}

export interface EnrichedUnitCostMonth extends UnitCostMonth {
  costTotal: number
  unitMaterial: number | null
  unitLabor: number | null
  unitManufacturing: number | null
  unitCost: number | null
}

export interface MaterialInputCell {
  inputQty: number
  unit: string
  inputAmount: number
}

export interface MaterialConsumptionMonth {
  id: string
  period: 'current' | 'prior'
  month: number
  outputQty: number
  material1: MaterialInputCell
  material2: MaterialInputCell
}

export interface EnrichedMaterialInputCell extends MaterialInputCell {
  unitOutput: number | null
  unitCost: number | null
}

export interface EnrichedMaterialConsumptionMonth extends Omit<MaterialConsumptionMonth, 'material1' | 'material2'> {
  material1: EnrichedMaterialInputCell
  material2: EnrichedMaterialInputCell
}

export interface PeerCostRow {
  id: string
  item: '直接材料' | '直接人工' | '制造费用' | '单位成本'
  auditedUnit: number
  peer1Unit: number
  peer2Unit: number
  peer3Unit: number
}

export interface UnitConsumptionSheet {
  productName: string
  currentYear: string
  priorYear: string
  materialNames: [string, string, string]
  consumptionMaterialNames: [string, string]
  peerCompanies: [string, string, string]
  costStructureRows: CostStructureMonth[]
  costFlowRows: CostFlowMonth[]
  unitCostRows: UnitCostMonth[]
  peerRows: PeerCostRow[]
  materialConsumptionRows: MaterialConsumptionMonth[]
}

function periodRows<T>(factory: (period: 'current' | 'prior', month: number) => T): T[] {
  return (['current', 'prior'] as const).flatMap((period) =>
    Array.from({ length: 12 }, (_, i) => factory(period, i + 1)),
  )
}

export function emptyCostStructureMonth(period: 'current' | 'prior', month: number): CostStructureMonth {
  return {
    id: newUnitConsumptionId(), period, month,
    material1: 0, material2: 0, material3: 0, otherMaterial: 0,
    directLabor: 0, manufacturing: 0,
  }
}

export function emptyCostFlowMonth(period: 'current' | 'prior', month: number): CostFlowMonth {
  return {
    id: newUnitConsumptionId(), period, month,
    openingWip: 0, materialInput: 0, laborInput: 0,
    manufacturingInput: 0, endingWip: 0, outputQty: 0,
  }
}

export function emptyUnitCostMonth(period: 'current' | 'prior', month: number): UnitCostMonth {
  return {
    id: newUnitConsumptionId(), period, month,
    openingFinished: 0, directMaterial: 0, directLabor: 0,
    manufacturing: 0, endingFinished: 0, outputQty: 0,
  }
}

function emptyMaterialCell(): MaterialInputCell {
  return { inputQty: 0, unit: '', inputAmount: 0 }
}

export function emptyMaterialConsumptionMonth(period: 'current' | 'prior', month: number): MaterialConsumptionMonth {
  return {
    id: newUnitConsumptionId(), period, month, outputQty: 0,
    material1: emptyMaterialCell(), material2: emptyMaterialCell(),
  }
}

export function defaultUnitConsumptionSheet(): UnitConsumptionSheet {
  return {
    productName: '',
    currentYear: '本年',
    priorYear: '上年',
    materialNames: ['主要原材料1', '主要原材料2', '主要原材料3'],
    consumptionMaterialNames: ['主要原材料1', '主要原材料2'],
    peerCompanies: ['同行业公司1', '同行业公司2', '同行业公司3'],
    costStructureRows: periodRows(emptyCostStructureMonth),
    costFlowRows: periodRows(emptyCostFlowMonth),
    unitCostRows: periodRows(emptyUnitCostMonth),
    peerRows: (['直接材料', '直接人工', '制造费用', '单位成本'] as const).map((item) => ({
      id: newUnitConsumptionId(), item,
      auditedUnit: 0, peer1Unit: 0, peer2Unit: 0, peer3Unit: 0,
    })),
    materialConsumptionRows: periodRows(emptyMaterialConsumptionMonth),
  }
}

export function enrichCostStructureRow(row: CostStructureMonth): EnrichedCostStructureMonth {
  const keys = ['material1', 'material2', 'material3', 'otherMaterial', 'directLabor', 'manufacturing'] as const
  const total = keys.reduce((sum, key) => sum + (row[key] || 0), 0)
  return {
    ...row,
    total,
    rates: Object.fromEntries(keys.map((key) => [key, total ? row[key] / total : null])) as EnrichedCostStructureMonth['rates'],
  }
}

export function enrichCostFlowRow(row: CostFlowMonth): EnrichedCostFlowMonth {
  const productionCost = row.openingWip + row.materialInput + row.laborInput
    + row.manufacturingInput - row.endingWip
  return { ...row, productionCost, unitCost: row.outputQty ? productionCost / row.outputQty : null }
}

export function enrichUnitCostRow(row: UnitCostMonth): EnrichedUnitCostMonth {
  const costTotal = row.openingFinished + row.directMaterial + row.directLabor
    + row.manufacturing - row.endingFinished
  const divide = (value: number) => row.outputQty ? value / row.outputQty : null
  return {
    ...row,
    costTotal,
    unitMaterial: divide(row.directMaterial),
    unitLabor: divide(row.directLabor),
    unitManufacturing: divide(row.manufacturing),
    unitCost: divide(costTotal),
  }
}

function enrichMaterialCell(cell: MaterialInputCell, outputQty: number): EnrichedMaterialInputCell {
  return {
    ...cell,
    unitOutput: outputQty ? cell.inputQty / outputQty : null,
    unitCost: outputQty ? cell.inputAmount / outputQty : null,
  }
}

export function enrichMaterialConsumptionRow(row: MaterialConsumptionMonth): EnrichedMaterialConsumptionMonth {
  return {
    ...row,
    material1: enrichMaterialCell(row.material1, row.outputQty),
    material2: enrichMaterialCell(row.material2, row.outputQty),
  }
}

export function sumRows<T extends Record<string, unknown>>(rows: T[], key: keyof T): number {
  return rows.reduce((sum, row) => sum + (Number(row[key]) || 0), 0)
}

export function isUnitConsumptionSheetEmpty(sheet: UnitConsumptionSheet): boolean {
  const structure = sheet.costStructureRows.every((r) =>
    !r.material1 && !r.material2 && !r.material3 && !r.otherMaterial && !r.directLabor && !r.manufacturing)
  const flow = sheet.costFlowRows.every((r) =>
    !r.openingWip && !r.materialInput && !r.laborInput && !r.manufacturingInput && !r.endingWip && !r.outputQty)
  const unit = sheet.unitCostRows.every((r) =>
    !r.openingFinished && !r.directMaterial && !r.directLabor && !r.manufacturing && !r.endingFinished && !r.outputQty)
  const consumption = sheet.materialConsumptionRows.every((r) =>
    !r.outputQty && !r.material1.inputQty && !r.material1.inputAmount && !r.material2.inputQty && !r.material2.inputAmount)
  return !sheet.productName.trim() && structure && flow && unit && consumption
}

function numberValue(value: unknown): number {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function normalizePeriod(value: unknown): 'current' | 'prior' {
  return value === 'prior' ? 'prior' : 'current'
}

function normalize24<T>(
  rows: unknown,
  factory: (period: 'current' | 'prior', month: number) => T,
  normalize: (raw: Record<string, unknown>, period: 'current' | 'prior', month: number) => T,
): T[] {
  const list = Array.isArray(rows) ? rows as Record<string, unknown>[] : []
  return periodRows((period, month) => {
    const raw = list.find((r) => normalizePeriod(r.period) === period && numberValue(r.month) === month)
    return raw ? normalize(raw, period, month) : factory(period, month)
  })
}

/** 兼容旧版按产品/材料的扁平行；尽可能迁入第4部分主要材料耗用。 */
export function migrateUnitConsumptionSheet(parsed: unknown): UnitConsumptionSheet {
  const fallback = defaultUnitConsumptionSheet()
  if (Array.isArray(parsed)) {
    const old = parsed as Record<string, unknown>[]
    const first = old[0]
    if (!first) return fallback
    fallback.productName = String(first.productName || '')
    fallback.consumptionMaterialNames = [
      String(first.materialName || '主要原材料1'),
      String(old[1]?.materialName || '主要原材料2'),
    ]
    const outputQty = numberValue(first.outputQty)
    fallback.materialConsumptionRows[0] = {
      ...fallback.materialConsumptionRows[0],
      outputQty,
      material1: {
        inputQty: numberValue(first.inputQty),
        unit: String(first.unit || ''),
        inputAmount: numberValue(first.inputQty) * numberValue(first.materialUnitPrice),
      },
      material2: {
        inputQty: numberValue(old[1]?.inputQty),
        unit: String(old[1]?.unit || ''),
        inputAmount: numberValue(old[1]?.inputQty) * numberValue(old[1]?.materialUnitPrice),
      },
    }
    return fallback
  }
  if (!parsed || typeof parsed !== 'object') return fallback
  const obj = parsed as Record<string, unknown>
  const textTuple = (value: unknown, defaults: string[], size: number): string[] => {
    const arr = Array.isArray(value) ? value.map(String) : []
    return Array.from({ length: size }, (_, i) => arr[i] || defaults[i])
  }
  const normalizeId = (raw: Record<string, unknown>) => String(raw.id || newUnitConsumptionId())
  return {
    productName: String(obj.productName || ''),
    currentYear: String(obj.currentYear || '本年'),
    priorYear: String(obj.priorYear || '上年'),
    materialNames: textTuple(obj.materialNames, fallback.materialNames, 3) as [string, string, string],
    consumptionMaterialNames: textTuple(obj.consumptionMaterialNames, fallback.consumptionMaterialNames, 2) as [string, string],
    peerCompanies: textTuple(obj.peerCompanies, fallback.peerCompanies, 3) as [string, string, string],
    costStructureRows: normalize24(obj.costStructureRows, emptyCostStructureMonth, (r, period, month) => ({
      id: normalizeId(r), period, month,
      material1: numberValue(r.material1), material2: numberValue(r.material2),
      material3: numberValue(r.material3), otherMaterial: numberValue(r.otherMaterial),
      directLabor: numberValue(r.directLabor), manufacturing: numberValue(r.manufacturing),
    })),
    costFlowRows: normalize24(obj.costFlowRows, emptyCostFlowMonth, (r, period, month) => ({
      id: normalizeId(r), period, month,
      openingWip: numberValue(r.openingWip), materialInput: numberValue(r.materialInput),
      laborInput: numberValue(r.laborInput), manufacturingInput: numberValue(r.manufacturingInput),
      endingWip: numberValue(r.endingWip), outputQty: numberValue(r.outputQty),
    })),
    unitCostRows: normalize24(obj.unitCostRows, emptyUnitCostMonth, (r, period, month) => ({
      id: normalizeId(r), period, month,
      openingFinished: numberValue(r.openingFinished), directMaterial: numberValue(r.directMaterial),
      directLabor: numberValue(r.directLabor), manufacturing: numberValue(r.manufacturing),
      endingFinished: numberValue(r.endingFinished), outputQty: numberValue(r.outputQty),
    })),
    peerRows: Array.isArray(obj.peerRows) && obj.peerRows.length
      ? (obj.peerRows as Record<string, unknown>[]).map((r, i) => ({
          id: normalizeId(r),
          item: (['直接材料', '直接人工', '制造费用', '单位成本'][i] || String(r.item)) as PeerCostRow['item'],
          auditedUnit: numberValue(r.auditedUnit), peer1Unit: numberValue(r.peer1Unit),
          peer2Unit: numberValue(r.peer2Unit), peer3Unit: numberValue(r.peer3Unit),
        }))
      : fallback.peerRows,
    materialConsumptionRows: normalize24(
      obj.materialConsumptionRows,
      emptyMaterialConsumptionMonth,
      (r, period, month) => {
        const cell = (value: unknown): MaterialInputCell => {
          const raw = value && typeof value === 'object' ? value as Record<string, unknown> : {}
          return { inputQty: numberValue(raw.inputQty), unit: String(raw.unit || ''), inputAmount: numberValue(raw.inputAmount) }
        }
        return {
          id: normalizeId(r), period, month, outputQty: numberValue(r.outputQty),
          material1: cell(r.material1), material2: cell(r.material2),
        }
      },
    ),
  }
}
