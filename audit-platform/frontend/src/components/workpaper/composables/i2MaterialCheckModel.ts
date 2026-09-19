/**
 * I2-8 研发材料投入检查表 — 纯模型
 * 对齐源表：样本选取 → 账簿 vs 领料单双栏核对 → 检查比例（防 #DIV/0!）
 */

export const I2_MATERIAL_DEFAULT_COVERAGE_THRESHOLD = 20

export const I2_MATERIAL_TEST_CONTENT = [
  '检查原始凭证是否齐全（领料单/出库单审批完整）',
  '检查记账凭证与原始凭证是否相符（品名、数量、金额）',
  '检查会计处理是否正确（对方科目、资本化/费用化归集）',
  '检查是否记录于正确的会计期间（截止）',
  '关注领用人员是否为该项目研发人员，领料单项目与账面归集是否一致',
] as const

export const I2_MATERIAL_SAMPLE_METHODS = [
  '随机抽样',
  '系统抽样',
  '货币单元抽样',
  '随意抽样',
  '全部检查',
] as const

export type I2MaterialAbnormal =
  | ''
  | '否'
  | '是'
  | '数量不符'
  | '项目不符'
  | '领用人非研发'
  | '生产混入'
  | '其他'

export interface I2MaterialCheckRow {
  rowId: string
  /** 账面：项目名称 */
  projectName: string
  /** 账面：凭证编号 */
  voucherNo: string
  /** 账面：业务内容 */
  businessDesc: string
  /** 账面：存货名称（品名） */
  inventoryName: string
  /** 账面：单位 */
  unit: string
  /** 账面：数量 */
  quantity: number
  /** 账面：借方金额 */
  debitAmount: number
  /** 账面：对方科目 */
  counterpartAccount: string
  /** 账面：对方明细科目 */
  counterpartDetail: string
  /** 领料单：日期/编号 */
  slipDateNo: string
  /** 领料单：领用人员 */
  recipient: string
  /** 领料单：领用部门 */
  recipientDept: string
  /** 领料单：研发项目 */
  slipProject: string
  /** 领料单：数量 */
  slipQty: number
  /** 索引号 */
  indexRef: string
  /** 是否异常 */
  isAbnormal: I2MaterialAbnormal | string
  /** 审核结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

export interface I2MaterialSampleMeta {
  /** 测试总体说明 */
  populationDesc: string
  /** 本期发生额（总体，优先取 I2-7 材料费合计） */
  populationAmount: number
  /** 是否手工覆盖总体 */
  populationManual: boolean
  /** 特定样本说明（大额/关联方/异常） */
  specificSample: string
  /** 抽样方法 */
  sampleMethod: string
  /** 抽样过程说明 */
  sampleProcess: string
  /** 检查比例告警阈值 % */
  coverageThreshold: number
}

export interface I2MaterialSummary {
  sampleCount: number
  checkedTotal: number
  periodTotal: number
  /** null 表示总体为 0，展示 N/A，避免 #DIV/0! */
  coverageRate: number | null
  anomalyCount: number
  qtyMismatchCount: number
  projectMismatchCount: number
  pendingCount: number
}

export function emptyI2MaterialRow(partial?: Partial<I2MaterialCheckRow>): I2MaterialCheckRow {
  return {
    rowId: partial?.rowId || `i28-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: '',
    voucherNo: '',
    businessDesc: '',
    inventoryName: '',
    unit: '',
    quantity: 0,
    debitAmount: 0,
    counterpartAccount: '',
    counterpartDetail: '',
    slipDateNo: '',
    recipient: '',
    recipientDept: '',
    slipProject: '',
    slipQty: 0,
    indexRef: '',
    isAbnormal: '',
    conclusion: '',
    remark: '',
    ...partial,
  }
}

export function emptyI2MaterialSampleMeta(partial?: Partial<I2MaterialSampleMeta>): I2MaterialSampleMeta {
  return {
    populationDesc: '账面记录的研发材料领用借方发生额（凭证总体）',
    populationAmount: 0,
    populationManual: false,
    specificSample: '选取大额、关联方及异常领用作为特定样本；其余从剩余总体中抽样',
    sampleMethod: '系统抽样',
    sampleProcess: '',
    coverageThreshold: I2_MATERIAL_DEFAULT_COVERAGE_THRESHOLD,
    ...partial,
  }
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

/**
 * 兼容旧版精简字段：materialName/unitPrice/amount/requisitionNo
 */
export function normalizeI2MaterialRow(raw: any): I2MaterialCheckRow {
  const inventoryName = _str(raw?.inventoryName || raw?.materialName)
  const quantity = _num(raw?.quantity)
  const unitPrice = _num(raw?.unitPrice)
  const legacyAmount = _num(raw?.amount)
  const debitAmount = raw?.debitAmount != null
    ? _num(raw.debitAmount)
    : (legacyAmount || Math.round(quantity * unitPrice * 100) / 100)

  const row = emptyI2MaterialRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName),
    voucherNo: _str(raw?.voucherNo),
    businessDesc: _str(raw?.businessDesc),
    inventoryName,
    unit: _str(raw?.unit),
    quantity,
    debitAmount,
    counterpartAccount: _str(raw?.counterpartAccount),
    counterpartDetail: _str(raw?.counterpartDetail),
    slipDateNo: _str(raw?.slipDateNo || raw?.requisitionNo),
    recipient: _str(raw?.recipient),
    recipientDept: _str(raw?.recipientDept),
    slipProject: _str(raw?.slipProject),
    slipQty: raw?.slipQty != null ? _num(raw.slipQty) : quantity,
    indexRef: _str(raw?.indexRef),
    isAbnormal: _str(raw?.isAbnormal),
    conclusion: _str(raw?.conclusion),
    remark: _str(raw?.remark),
  })
  return row
}

export function normalizeI2MaterialSampleMeta(raw: any): I2MaterialSampleMeta {
  if (!raw || typeof raw !== 'object') return emptyI2MaterialSampleMeta()
  return emptyI2MaterialSampleMeta({
    populationDesc: _str(raw.populationDesc) || emptyI2MaterialSampleMeta().populationDesc,
    populationAmount: _num(raw.populationAmount),
    populationManual: !!raw.populationManual,
    specificSample: _str(raw.specificSample) || emptyI2MaterialSampleMeta().specificSample,
    sampleMethod: _str(raw.sampleMethod) || '系统抽样',
    sampleProcess: _str(raw.sampleProcess),
    coverageThreshold: Math.min(100, Math.max(1, _num(raw.coverageThreshold) || I2_MATERIAL_DEFAULT_COVERAGE_THRESHOLD)),
  })
}

/** 账面数量 vs 领料单数量是否不符（两侧均有值时才判） */
export function hasQtyMismatch(row: I2MaterialCheckRow): boolean {
  if (!row.quantity && !row.slipQty) return false
  if (row.quantity === 0 || row.slipQty === 0) {
    // 一侧有值另一侧为 0 视为可疑
    return row.quantity !== row.slipQty
  }
  return Math.abs(row.quantity - row.slipQty) > 1e-6
}

/** 账面项目 vs 领料单项目是否不符（两侧均非空时才判） */
export function hasProjectMismatch(row: I2MaterialCheckRow): boolean {
  const a = row.projectName.trim()
  const b = row.slipProject.trim()
  if (!a || !b) return false
  return a !== b
}

/** 根据勾稽差异建议异常标记（不覆盖已有「是/具体类型」以外的空值） */
export function suggestAbnormal(row: I2MaterialCheckRow): I2MaterialAbnormal | '' {
  if (hasQtyMismatch(row)) return '数量不符'
  if (hasProjectMismatch(row)) return '项目不符'
  return ''
}

export function summarizeI2Material(
  rows: I2MaterialCheckRow[],
  periodTotal: number,
): I2MaterialSummary {
  const sampleCount = rows.length
  const checkedTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => {
    const v = (r.isAbnormal || '').trim()
    return v !== '' && v !== '否'
  }).length
  const qtyMismatchCount = rows.filter(hasQtyMismatch).length
  const projectMismatchCount = rows.filter(hasProjectMismatch).length
  const pendingCount = rows.filter((r) => !r.conclusion || r.conclusion === '待查').length

  let coverageRate: number | null = null
  if (periodTotal > 0) {
    coverageRate = Math.round((checkedTotal / periodTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedTotal,
    periodTotal,
    coverageRate,
    anomalyCount,
    qtyMismatchCount,
    projectMismatchCount,
    pendingCount,
  }
}

/** 从 I2-7 项目构成明细提取材料费合计（优先本期增加.直接材料，兼容旧扁平字段） */
export function extractI27MaterialTotal(raw: unknown): number {
  let rows: any[] = []
  if (Array.isArray(raw)) rows = raw
  else if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      rows = Array.isArray(p) ? p : []
    } catch { return 0 }
  } else if (raw && typeof raw === 'object') {
    const obj = raw as any
    const remark = obj.remark ?? obj.conclusion
    if (typeof remark === 'string' && remark) {
      try {
        const p = JSON.parse(remark)
        rows = Array.isArray(p) ? p : []
      } catch { return 0 }
    } else if (Array.isArray(remark)) {
      rows = remark
    }
  }
  const sum = rows.reduce((s, r) => {
    if (r?.increase && typeof r.increase === 'object' && r.increase.material != null) {
      return s + _num(r.increase.material)
    }
    if (r?.materialSubtotal != null) return s + _num(r.materialSubtotal)
    const direct = _num(r?.materialDirect)
    const aux = _num(r?.materialAux)
    const fuel = _num(r?.materialFuel)
    if (direct || aux || fuel) return s + direct + aux + fuel
    return s
  }, 0)
  return Math.round(sum * 100) / 100
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 'N/A'
  return `${rate.toFixed(2)}%`
}
