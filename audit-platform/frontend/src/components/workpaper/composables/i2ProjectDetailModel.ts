/**
 * I2-7 研发项目构成明细表 — 纯模型
 * 对齐源表 73 列：期初→本期增加→本期减少→期末→审计调整→审定
 * 每段费用性质：直接材料/直接人工/折旧摊销/能耗/委外/其他 + 资本化/费用化
 * 勾稽：期末=期初+增加-减少；审定=期末+调整；费用性质合计≈资本化+费用化
 */

export const I2_PROJECT_COST_NATURE_KEYS = [
  'material',
  'labor',
  'depreciation',
  'energy',
  'outsource',
  'other',
] as const

export const I2_PROJECT_TREATMENT_KEYS = ['capitalized', 'expensed'] as const

export const I2_PROJECT_COST_KEYS = [
  ...I2_PROJECT_COST_NATURE_KEYS,
  ...I2_PROJECT_TREATMENT_KEYS,
] as const

export type I2ProjectCostKey = (typeof I2_PROJECT_COST_KEYS)[number]

export const I2_PROJECT_COST_LABELS: Record<I2ProjectCostKey, string> = {
  material: '直接材料',
  labor: '直接人工',
  depreciation: '折旧与摊销',
  energy: '能耗',
  outsource: '委外研发费',
  other: '其他费用',
  capitalized: '资本化金额',
  expensed: '费用化金额',
}

export const I2_PROJECT_STAGE_KEYS = [
  'begin',
  'increase',
  'decrease',
  'ending',
  'adjustment',
  'audited',
] as const

export type I2ProjectStageKey = (typeof I2_PROJECT_STAGE_KEYS)[number]

export const I2_PROJECT_STAGE_LABELS: Record<I2ProjectStageKey, string> = {
  begin: '账面期初余额',
  increase: '账面本期增加',
  decrease: '账面本期减少',
  ending: '账面期末余额',
  adjustment: '审计调整',
  audited: '期末审定金额',
}

/** 可手工录入的阶段（期末/审定为公式） */
export const I2_PROJECT_EDITABLE_STAGES: I2ProjectStageKey[] = [
  'begin',
  'increase',
  'decrease',
  'adjustment',
]

export type I2ProjectCostBlock = Record<I2ProjectCostKey, number>

export interface I2ProjectDetailRow {
  rowId: string
  projectCode: string
  projectName: string
  /** 研发周期起 */
  periodStart: string
  /** 研发周期止 */
  periodEnd: string
  stage: string
  begin: I2ProjectCostBlock
  increase: I2ProjectCostBlock
  decrease: I2ProjectCostBlock
  /** 公式：期初+增加-减少 */
  ending: I2ProjectCostBlock
  adjustment: I2ProjectCostBlock
  /** 公式：期末+调整 */
  audited: I2ProjectCostBlock
  remark: string
  // ── 兼容旧版扁平字段（只读派生，持久化时不依赖）──
  materialSubtotal?: number
  laborSubtotal?: number
  depSubtotal?: number
  otherSubtotal?: number
  totalAmount?: number
}

export interface I2ProjectDetailSummary {
  rowCount: number
  increaseTotal: number
  increaseCapitalized: number
  increaseExpensed: number
  endingTotal: number
  auditedTotal: number
  auditedCapitalized: number
  auditedExpensed: number
  materialIncreaseTotal: number
  treatmentMismatchCount: number
  rollforwardMismatchCount: number
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

export function emptyCostBlock(partial?: Partial<I2ProjectCostBlock>): I2ProjectCostBlock {
  const b: I2ProjectCostBlock = {
    material: 0,
    labor: 0,
    depreciation: 0,
    energy: 0,
    outsource: 0,
    other: 0,
    capitalized: 0,
    expensed: 0,
  }
  if (partial) {
    for (const k of I2_PROJECT_COST_KEYS) {
      if (partial[k] != null) b[k] = _num(partial[k])
    }
  }
  return b
}

export function costNatureSum(block: I2ProjectCostBlock): number {
  return _round2(
    I2_PROJECT_COST_NATURE_KEYS.reduce((s, k) => s + _num(block[k]), 0),
  )
}

export function costTreatmentSum(block: I2ProjectCostBlock): number {
  return _round2(_num(block.capitalized) + _num(block.expensed))
}

/** 费用性质合计与资本化+费用化是否勾稽（容差 0.01） */
export function hasTreatmentMismatch(block: I2ProjectCostBlock): boolean {
  const nature = costNatureSum(block)
  const treatment = costTreatmentSum(block)
  if (nature === 0 && treatment === 0) return false
  return Math.abs(nature - treatment) > 0.01
}

export function calcEndingBlock(
  begin: I2ProjectCostBlock,
  increase: I2ProjectCostBlock,
  decrease: I2ProjectCostBlock,
): I2ProjectCostBlock {
  const out = emptyCostBlock()
  for (const k of I2_PROJECT_COST_KEYS) {
    out[k] = _round2(_num(begin[k]) + _num(increase[k]) - _num(decrease[k]))
  }
  return out
}

export function calcAuditedBlock(
  ending: I2ProjectCostBlock,
  adjustment: I2ProjectCostBlock,
): I2ProjectCostBlock {
  const out = emptyCostBlock()
  for (const k of I2_PROJECT_COST_KEYS) {
    out[k] = _round2(_num(ending[k]) + _num(adjustment[k]))
  }
  return out
}

export function normalizeCostBlock(raw: any): I2ProjectCostBlock {
  if (!raw || typeof raw !== 'object') return emptyCostBlock()
  return emptyCostBlock({
    material: raw.material,
    labor: raw.labor,
    depreciation: raw.depreciation,
    energy: raw.energy,
    outsource: raw.outsource,
    other: raw.other,
    capitalized: raw.capitalized,
    expensed: raw.expensed,
  })
}

/** 旧版扁平费用 → 本期增加块 */
function legacyToIncrease(raw: any): I2ProjectCostBlock {
  const material = _round2(
    _num(raw.materialSubtotal)
    || (_num(raw.materialDirect) + _num(raw.materialAux) + _num(raw.materialFuel)),
  )
  const labor = _round2(
    _num(raw.laborSubtotal)
    || (_num(raw.laborSalary) + _num(raw.laborBonus) + _num(raw.laborInsurance)),
  )
  const depreciation = _round2(
    _num(raw.depSubtotal)
    || (_num(raw.depEquipment) + _num(raw.depBuilding) + _num(raw.depIntangible)),
  )
  const outsource = _num(raw.outsource) || _num(raw.otherOutsource) || 0
  const other = _round2(
    _num(raw.otherSubtotal)
    || (_num(raw.otherDesign) + _num(raw.otherTest) + _num(raw.otherTravel) + _num(raw.otherMisc)),
  )
  // 若旧数据只有费用合计、无资本化拆分，默认全部记入资本化（开发支出底稿语境）
  const nature = _round2(material + labor + depreciation + outsource + other)
  return emptyCostBlock({
    material,
    labor,
    depreciation,
    energy: _num(raw.energy) || _num(raw.materialFuel) || 0,
    outsource,
    other,
    capitalized: _num(raw.capitalized) || nature,
    expensed: _num(raw.expensed) || 0,
  })
}

export function emptyI2ProjectDetailRow(
  partial?: Partial<I2ProjectDetailRow>,
): I2ProjectDetailRow {
  const row: I2ProjectDetailRow = {
    rowId: partial?.rowId || `i27-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectCode: '',
    projectName: '',
    periodStart: '',
    periodEnd: '',
    stage: '',
    begin: emptyCostBlock(),
    increase: emptyCostBlock(),
    decrease: emptyCostBlock(),
    ending: emptyCostBlock(),
    adjustment: emptyCostBlock(),
    audited: emptyCostBlock(),
    remark: '',
    ...partial,
  }
  recalcI2ProjectDetailRow(row)
  return row
}

export function recalcI2ProjectDetailRow(row: I2ProjectDetailRow): void {
  row.ending = calcEndingBlock(row.begin, row.increase, row.decrease)
  row.audited = calcAuditedBlock(row.ending, row.adjustment)
  // 兼容派生字段（供 I2-8 / 旧消费者）
  row.materialSubtotal = row.increase.material
  row.laborSubtotal = row.increase.labor
  row.depSubtotal = row.increase.depreciation
  row.otherSubtotal = _round2(row.increase.energy + row.increase.outsource + row.increase.other)
  row.totalAmount = costTreatmentSum(row.increase) || costNatureSum(row.increase)
}

export function normalizeI2ProjectDetailRow(raw: any): I2ProjectDetailRow {
  const hasNewShape = raw?.begin || raw?.increase || raw?.decrease || raw?.adjustment
  const increase = hasNewShape
    ? normalizeCostBlock(raw.increase)
    : legacyToIncrease(raw)

  const row = emptyI2ProjectDetailRow({
    rowId: _str(raw?.rowId) || undefined,
    projectCode: _str(raw?.projectCode),
    projectName: _str(raw?.projectName),
    periodStart: _str(raw?.periodStart || raw?.startDate),
    periodEnd: _str(raw?.periodEnd || raw?.expectedEnd || raw?.endDate),
    stage: _str(raw?.stage),
    begin: hasNewShape ? normalizeCostBlock(raw.begin) : emptyCostBlock(),
    increase,
    decrease: hasNewShape ? normalizeCostBlock(raw.decrease) : emptyCostBlock(),
    adjustment: hasNewShape ? normalizeCostBlock(raw.adjustment) : emptyCostBlock(),
    remark: _str(raw?.remark),
  })
  return row
}

/** 序列化（只存可编辑字段 + 身份；公式段不存或存亦可被 recalc 覆盖） */
export function serializeI2ProjectDetailRow(row: I2ProjectDetailRow): Record<string, unknown> {
  return {
    rowId: row.rowId,
    projectCode: row.projectCode,
    projectName: row.projectName,
    periodStart: row.periodStart,
    periodEnd: row.periodEnd,
    stage: row.stage,
    begin: { ...row.begin },
    increase: { ...row.increase },
    decrease: { ...row.decrease },
    adjustment: { ...row.adjustment },
    remark: row.remark,
    // 兼容旧消费者 / I2-8 材料总体
    materialSubtotal: row.increase.material,
    materialDirect: row.increase.material,
  }
}

export function summarizeI2ProjectDetail(rows: I2ProjectDetailRow[]): I2ProjectDetailSummary {
  let increaseTotal = 0
  let increaseCapitalized = 0
  let increaseExpensed = 0
  let endingTotal = 0
  let auditedTotal = 0
  let auditedCapitalized = 0
  let auditedExpensed = 0
  let materialIncreaseTotal = 0
  let treatmentMismatchCount = 0
  let rollforwardMismatchCount = 0

  for (const r of rows) {
    const incNature = costNatureSum(r.increase)
    const incTreat = costTreatmentSum(r.increase)
    increaseTotal += incTreat || incNature
    increaseCapitalized += r.increase.capitalized
    increaseExpensed += r.increase.expensed
    endingTotal += costTreatmentSum(r.ending) || costNatureSum(r.ending)
    auditedTotal += costTreatmentSum(r.audited) || costNatureSum(r.audited)
    auditedCapitalized += r.audited.capitalized
    auditedExpensed += r.audited.expensed
    materialIncreaseTotal += r.increase.material

    for (const stage of I2_PROJECT_EDITABLE_STAGES) {
      if (hasTreatmentMismatch(r[stage])) treatmentMismatchCount++
    }
    // 滚动勾稽抽查：期末资本化是否等于期初+增加-减少
    const expectedCap = _round2(r.begin.capitalized + r.increase.capitalized - r.decrease.capitalized)
    if (Math.abs(expectedCap - r.ending.capitalized) > 0.01) rollforwardMismatchCount++
  }

  return {
    rowCount: rows.length,
    increaseTotal: _round2(increaseTotal),
    increaseCapitalized: _round2(increaseCapitalized),
    increaseExpensed: _round2(increaseExpensed),
    endingTotal: _round2(endingTotal),
    auditedTotal: _round2(auditedTotal),
    auditedCapitalized: _round2(auditedCapitalized),
    auditedExpensed: _round2(auditedExpensed),
    materialIncreaseTotal: _round2(materialIncreaseTotal),
    treatmentMismatchCount,
    rollforwardMismatchCount,
  }
}

/** 供 I2-8 提取本期材料增加总体：支持新结构 + 旧扁平字段 */
export function extractMaterialIncreaseTotal(rows: any[]): number {
  const sum = rows.reduce((s, r) => {
    if (r?.increase && typeof r.increase === 'object') {
      return s + _num(r.increase.material)
    }
    if (r?.materialSubtotal != null) return s + _num(r.materialSubtotal)
    return s + _num(r?.materialDirect) + _num(r?.materialAux) + _num(r?.materialFuel)
  }, 0)
  return _round2(sum)
}
