/**
 * useH2Detail — H2-2 明细表 composable（50列宽表，3区段Tab）
 *
 * 职责：
 * - H2DetailRow 接口：50列完整定义
 * - 3区段分组配置（基本/增减/竣工结转）
 * - 行内公式（期末=期初+增加-减少-转固；增加合计=材料+人工+机械+利息+其他；完工进度=累计投入/预算×100%）
 * - subtotalRow（computed SUM所有numeric列）
 * - crossValidation（vs H2-1审定表）
 * - addRow(弹窗命名) / removeRow / updateCell
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.4
 * Requirements: 3.1-3.12
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcCipEndBalance,
  calcSubtotal,
  calcCompletionRate,
} from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * H2-2 明细表行（50列）
 * 按3区段逻辑分组：基本信息(~10) / 增减(~20) / 竣工结转(~20)
 */
export interface H2DetailRow {
  /** 行唯一标识 */
  rowId: string

  // ═══════ 区段1: 基本信息 (10列) ═══════
  /** 工程项目名称 */
  name: string
  /** 预算金额 */
  budget: number
  /** 开工日期 */
  startDate: string
  /** 预计竣工日期 */
  plannedEndDate: string
  /** 实际竣工日期 */
  actualEndDate: string
  /** 完工进度(%)（公式列：=累计投入/预算×100） */
  completionRate: number | null
  /** 累计投入 */
  accumulatedInput: number
  /** 资金来源 */
  fundSource: string
  /** 资本化率(%) */
  capRate: number | null
  /** 工程类别 */
  category: string

  // ═══════ 区段2: 增减 (20列) ═══════
  /** 期初余额 */
  cipBegin: number
  /** 本期增加-材料 */
  increaseMaterial: number
  /** 本期增加-人工 */
  increaseLabor: number
  /** 本期增加-机械 */
  increaseMachinery: number
  /** 本期增加-利息（资本化利息） */
  increaseInterest: number
  /** 本期增加-其他 */
  increaseOther: number
  /** 本期增加合计（公式列：=材料+人工+机械+利息+其他） */
  increaseTotal: number
  /** 本期减少 */
  decrease: number
  /** 转出（非转固减少，如报废/损失） */
  transferOut: number
  /** 未调整期末余额 */
  unadjustedEnd: number
  /** 审定期初余额 */
  beginAudited: number
  /** 期初调整 */
  adjustBegin: number
  /** 期末调整 */
  adjustEnd: number
  /** 减少调整 */
  decreaseAdj: number
  /** 转固调整 */
  transferAdj: number
  /** 审定期末余额 */
  endAudited: number
  /** 增加合计调整 */
  increaseAdj: number
  /** AJE调整额 */
  aje: number
  /** RJE重分类额 */
  rje: number

  // ═══════ 区段3: 竣工结转 (20列) ═══════
  /** 转固日期 */
  transferDate: string
  /** 转固金额 */
  transferAmount: number
  /** 转入H1科目 */
  transferToH1: string
  /** 剩余在建金额 */
  remainingCip: number
  /** 期末余额（公式列：=期初+增加合计-减少-转固金额） */
  cipEnd: number
  /** 减值准备-期初 */
  impairmentBegin: number
  /** 减值准备-本期增加 */
  impairmentIncrease: number
  /** 减值准备-本期减少(转回) */
  impairmentDecrease: number
  /** 减值准备-期末 */
  impairmentEnd: number
  /** 账面净值 */
  netValue: number
  /** 合同编号 */
  contractNo: string
  /** 施工单位 */
  contractor: string
  /** 监理单位 */
  supervisor: string
  /** 建筑面积(m²)或工程量 */
  area: number | null
  /** 单位造价 */
  unitCost: number | null
  /** 工程进度说明 */
  progressNote: string
  /** 审计标记（异常标记） */
  auditFlag: string
  /** 索引号 */
  indexRef: string
  /** 备注 */
  remark: string
}

// ─── Segment Column Configs ──────────────────────────────────────────────────

export interface SegmentColumn {
  field: keyof H2DetailRow
  label: string
  width?: number
  /** 是否为公式列（不可编辑） */
  formula?: boolean
  /** 是否为金额列（右对齐+格式化） */
  isAmount?: boolean
  /** 是否为日期列 */
  isDate?: boolean
}

/** 3区段分组配置 */
export const SEGMENT_CONFIGS = {
  /** 区段1: 基本信息 (~10列) */
  basic: [
    { field: 'name', label: '工程名称', width: 180 },
    { field: 'budget', label: '预算金额', isAmount: true, width: 130 },
    { field: 'category', label: '工程类别', width: 100 },
    { field: 'startDate', label: '开工日期', isDate: true, width: 110 },
    { field: 'plannedEndDate', label: '预计竣工日期', isDate: true, width: 120 },
    { field: 'actualEndDate', label: '实际竣工日期', isDate: true, width: 120 },
    { field: 'completionRate', label: '完工进度(%)', formula: true, width: 110 },
    { field: 'accumulatedInput', label: '累计投入', isAmount: true, width: 130 },
    { field: 'fundSource', label: '资金来源', width: 100 },
    { field: 'capRate', label: '资本化率(%)', width: 100 },
  ] as SegmentColumn[],

  /** 区段2: 增减 (~20列) */
  movement: [
    { field: 'name', label: '工程名称', width: 180 },
    { field: 'budget', label: '预算金额', isAmount: true, width: 130 },
    { field: 'cipBegin', label: '期初余额', isAmount: true, width: 130 },
    { field: 'increaseMaterial', label: '增加-材料', isAmount: true, width: 110 },
    { field: 'increaseLabor', label: '增加-人工', isAmount: true, width: 110 },
    { field: 'increaseMachinery', label: '增加-机械', isAmount: true, width: 110 },
    { field: 'increaseInterest', label: '增加-利息', isAmount: true, width: 110 },
    { field: 'increaseOther', label: '增加-其他', isAmount: true, width: 110 },
    { field: 'increaseTotal', label: '增加合计', isAmount: true, formula: true, width: 120 },
    { field: 'decrease', label: '本期减少', isAmount: true, width: 110 },
    { field: 'transferOut', label: '转出(非转固)', isAmount: true, width: 120 },
    { field: 'unadjustedEnd', label: '未调整期末', isAmount: true, width: 120 },
    { field: 'beginAudited', label: '审定期初', isAmount: true, width: 120 },
    { field: 'adjustBegin', label: '期初调整', isAmount: true, width: 100 },
    { field: 'adjustEnd', label: '期末调整', isAmount: true, width: 100 },
    { field: 'increaseAdj', label: '增加调整', isAmount: true, width: 100 },
    { field: 'decreaseAdj', label: '减少调整', isAmount: true, width: 100 },
    { field: 'transferAdj', label: '转固调整', isAmount: true, width: 100 },
    { field: 'aje', label: 'AJE', isAmount: true, width: 100 },
    { field: 'rje', label: 'RJE', isAmount: true, width: 100 },
  ] as SegmentColumn[],

  /** 区段3: 竣工结转 (~20列) */
  completion: [
    { field: 'name', label: '工程名称', width: 180 },
    { field: 'budget', label: '预算金额', isAmount: true, width: 130 },
    { field: 'transferDate', label: '转固日期', isDate: true, width: 110 },
    { field: 'transferAmount', label: '转固金额', isAmount: true, width: 130 },
    { field: 'transferToH1', label: '转入H1科目', width: 120 },
    { field: 'remainingCip', label: '剩余在建', isAmount: true, width: 120 },
    { field: 'cipEnd', label: '期末余额', isAmount: true, formula: true, width: 130 },
    { field: 'impairmentBegin', label: '减值-期初', isAmount: true, width: 110 },
    { field: 'impairmentIncrease', label: '减值-增加', isAmount: true, width: 110 },
    { field: 'impairmentDecrease', label: '减值-减少', isAmount: true, width: 110 },
    { field: 'impairmentEnd', label: '减值-期末', isAmount: true, formula: true, width: 110 },
    { field: 'netValue', label: '账面净值', isAmount: true, formula: true, width: 120 },
    { field: 'contractNo', label: '合同编号', width: 120 },
    { field: 'contractor', label: '施工单位', width: 120 },
    { field: 'supervisor', label: '监理单位', width: 120 },
    { field: 'area', label: '建筑面积(m²)', width: 110 },
    { field: 'unitCost', label: '单位造价', isAmount: true, formula: true, width: 110 },
    { field: 'progressNote', label: '进度说明', width: 150 },
    { field: 'auditFlag', label: '审计标记', width: 80 },
    { field: 'indexRef', label: '索引号', width: 80 },
    { field: 'remark', label: '备注', width: 150 },
  ] as SegmentColumn[],
} as const


/** 固定列（跨区段Tab始终显示，用于行辨识） */
export const FIXED_COLUMNS: SegmentColumn[] = [
  { field: 'name', label: '工程名称', width: 180 },
  { field: 'budget', label: '预算金额', isAmount: true, width: 130 },
]

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'H2-2-rows'
const NOTE_KEY = 'H2-2-audit-note'
const CONCLUSION_KEY = 'H2-2-audit-conclusion'

/** 金额列字段列表（用于合计行SUM） */
const NUMERIC_FIELDS: (keyof H2DetailRow)[] = [
  'budget', 'accumulatedInput', 'cipBegin',
  'increaseMaterial', 'increaseLabor', 'increaseMachinery',
  'increaseInterest', 'increaseOther', 'increaseTotal',
  'decrease', 'transferOut', 'unadjustedEnd',
  'beginAudited', 'adjustBegin', 'adjustEnd',
  'increaseAdj', 'decreaseAdj', 'transferAdj',
  'aje', 'rje', 'endAudited',
  'transferAmount', 'remainingCip', 'cipEnd',
  'impairmentBegin', 'impairmentIncrease', 'impairmentDecrease',
  'impairmentEnd', 'netValue',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/** 创建一个空白行（全部默认值） */
function _createEmptyRow(name: string): H2DetailRow {
  return {
    rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    // 基本信息
    name,
    budget: 0,
    startDate: '',
    plannedEndDate: '',
    actualEndDate: '',
    completionRate: null,
    accumulatedInput: 0,
    fundSource: '',
    capRate: null,
    category: '',
    // 增减
    cipBegin: 0,
    increaseMaterial: 0,
    increaseLabor: 0,
    increaseMachinery: 0,
    increaseInterest: 0,
    increaseOther: 0,
    increaseTotal: 0,
    decrease: 0,
    transferOut: 0,
    unadjustedEnd: 0,
    beginAudited: 0,
    adjustBegin: 0,
    adjustEnd: 0,
    decreaseAdj: 0,
    transferAdj: 0,
    endAudited: 0,
    increaseAdj: 0,
    aje: 0,
    rje: 0,
    // 竣工结转
    transferDate: '',
    transferAmount: 0,
    transferToH1: '',
    remainingCip: 0,
    cipEnd: 0,
    impairmentBegin: 0,
    impairmentIncrease: 0,
    impairmentDecrease: 0,
    impairmentEnd: 0,
    netValue: 0,
    contractNo: '',
    contractor: '',
    supervisor: '',
    area: null,
    unitCost: null,
    progressNote: '',
    auditFlag: '',
    indexRef: '',
    remark: '',
  }
}

/**
 * 重算行内公式列：
 * - increaseTotal = 材料+人工+机械+利息+其他
 * - cipEnd = 期初+增加合计-减少-转固金额
 * - completionRate = 累计投入/预算×100
 * - impairmentEnd = 减值期初+减值增加-减值减少
 * - netValue = cipEnd - impairmentEnd
 * - unitCost = 累计投入/面积 (area>0时)
 */
function _recalcFormulas(row: H2DetailRow): void {
  // 增加合计
  row.increaseTotal =
    _getNum(row.increaseMaterial) +
    _getNum(row.increaseLabor) +
    _getNum(row.increaseMachinery) +
    _getNum(row.increaseInterest) +
    _getNum(row.increaseOther)

  // 期末余额 = 期初 + 增加合计 - 减少 - 转固金额
  row.cipEnd = calcCipEndBalance(
    _getNum(row.cipBegin),
    row.increaseTotal,
    _getNum(row.decrease),
    _getNum(row.transferAmount),
  )

  // 完工进度
  row.completionRate = calcCompletionRate(
    _getNum(row.accumulatedInput),
    _getNum(row.budget),
  )

  // 减值期末
  row.impairmentEnd =
    _getNum(row.impairmentBegin) +
    _getNum(row.impairmentIncrease) -
    _getNum(row.impairmentDecrease)

  // 账面净值
  row.netValue = row.cipEnd - row.impairmentEnd

  // 单位造价
  const area = _getNum(row.area)
  row.unitCost = area > 0
    ? _getNum(row.accumulatedInput) / area
    : null
}

/** 从持久化JSON规范化行（补全缺失字段+重算公式） */
function _normalizeRow(raw: any): H2DetailRow {
  const row: H2DetailRow = {
    rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
    // 基本信息
    name: raw.name ?? '',
    budget: _getNum(raw.budget),
    startDate: raw.startDate ?? '',
    plannedEndDate: raw.plannedEndDate ?? '',
    actualEndDate: raw.actualEndDate ?? '',
    completionRate: null,
    accumulatedInput: _getNum(raw.accumulatedInput),
    fundSource: raw.fundSource ?? '',
    capRate: raw.capRate != null ? Number(raw.capRate) : null,
    category: raw.category ?? '',
    // 增减
    cipBegin: _getNum(raw.cipBegin),
    increaseMaterial: _getNum(raw.increaseMaterial),
    increaseLabor: _getNum(raw.increaseLabor),
    increaseMachinery: _getNum(raw.increaseMachinery),
    increaseInterest: _getNum(raw.increaseInterest),
    increaseOther: _getNum(raw.increaseOther),
    increaseTotal: 0,
    decrease: _getNum(raw.decrease),
    transferOut: _getNum(raw.transferOut),
    unadjustedEnd: _getNum(raw.unadjustedEnd),
    beginAudited: _getNum(raw.beginAudited),
    adjustBegin: _getNum(raw.adjustBegin),
    adjustEnd: _getNum(raw.adjustEnd),
    decreaseAdj: _getNum(raw.decreaseAdj),
    transferAdj: _getNum(raw.transferAdj),
    endAudited: _getNum(raw.endAudited),
    increaseAdj: _getNum(raw.increaseAdj),
    aje: _getNum(raw.aje),
    rje: _getNum(raw.rje),
    // 竣工结转
    transferDate: raw.transferDate ?? '',
    transferAmount: _getNum(raw.transferAmount),
    transferToH1: raw.transferToH1 ?? '',
    remainingCip: _getNum(raw.remainingCip),
    cipEnd: 0,
    impairmentBegin: _getNum(raw.impairmentBegin),
    impairmentIncrease: _getNum(raw.impairmentIncrease),
    impairmentDecrease: _getNum(raw.impairmentDecrease),
    impairmentEnd: 0,
    netValue: 0,
    contractNo: raw.contractNo ?? '',
    contractor: raw.contractor ?? '',
    supervisor: raw.supervisor ?? '',
    area: raw.area != null ? Number(raw.area) || null : null,
    unitCost: null,
    progressNote: raw.progressNote ?? '',
    auditFlag: raw.auditFlag ?? '',
    indexRef: raw.indexRef ?? '',
    remark: raw.remark ?? '',
  }
  _recalcFormulas(row)
  return row
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Detail(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 保存回调（调用useH2FormData.setValue） */
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2DetailRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  /** 当前选中行的rowId（跨区段Tab同步高亮） */
  const selectedRowId = ref<string | null>(null)

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  // ─── Init / Load ───────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  // Watch allResponses for reloads (selfLoad完成后触发)
  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: subtotalRow (SUM所有numeric列，不可编辑) ─────────────────

  /**
   * Req 3.4: 合计行 = SUM所有工程项目行各金额列
   * 合计行不可编辑，仅用于展示。
   */
  const subtotalRow: ComputedRef<H2DetailRow> = computed(() => {
    const sums: Record<string, number> = {}
    for (const field of NUMERIC_FIELDS) {
      sums[field] = calcSubtotal(rows.value.map(r => _getNum(r[field])))
    }

    const subtotal: H2DetailRow = {
      rowId: 'row-subtotal',
      name: '合计',
      budget: sums['budget'] ?? 0,
      startDate: '',
      plannedEndDate: '',
      actualEndDate: '',
      completionRate: null,
      accumulatedInput: sums['accumulatedInput'] ?? 0,
      fundSource: '',
      capRate: null,
      category: '',
      cipBegin: sums['cipBegin'] ?? 0,
      increaseMaterial: sums['increaseMaterial'] ?? 0,
      increaseLabor: sums['increaseLabor'] ?? 0,
      increaseMachinery: sums['increaseMachinery'] ?? 0,
      increaseInterest: sums['increaseInterest'] ?? 0,
      increaseOther: sums['increaseOther'] ?? 0,
      increaseTotal: sums['increaseTotal'] ?? 0,
      decrease: sums['decrease'] ?? 0,
      transferOut: sums['transferOut'] ?? 0,
      unadjustedEnd: sums['unadjustedEnd'] ?? 0,
      beginAudited: sums['beginAudited'] ?? 0,
      adjustBegin: sums['adjustBegin'] ?? 0,
      adjustEnd: sums['adjustEnd'] ?? 0,
      decreaseAdj: sums['decreaseAdj'] ?? 0,
      transferAdj: sums['transferAdj'] ?? 0,
      endAudited: sums['endAudited'] ?? 0,
      increaseAdj: sums['increaseAdj'] ?? 0,
      aje: sums['aje'] ?? 0,
      rje: sums['rje'] ?? 0,
      transferDate: '',
      transferAmount: sums['transferAmount'] ?? 0,
      transferToH1: '',
      remainingCip: sums['remainingCip'] ?? 0,
      cipEnd: sums['cipEnd'] ?? 0,
      impairmentBegin: sums['impairmentBegin'] ?? 0,
      impairmentIncrease: sums['impairmentIncrease'] ?? 0,
      impairmentDecrease: sums['impairmentDecrease'] ?? 0,
      impairmentEnd: sums['impairmentEnd'] ?? 0,
      netValue: sums['netValue'] ?? 0,
      contractNo: '',
      contractor: '',
      supervisor: '',
      area: null,
      unitCost: null,
      progressNote: '',
      auditFlag: '',
      indexRef: '',
      remark: '',
    }
    return subtotal
  })

  // ─── Computed: crossValidation vs H2-1 ────────────────────────────────────

  /**
   * Req 3.5: 合计行与H2-1审定表交叉验证
   * 期末余额合计 = H2-1审定数合计
   * diff > 0.01 时 isMatch=false
   */
  const crossValidationH1: ComputedRef<{ diff: number; isMatch: boolean }> = computed(() => {
    // 读取H2-1审定表行数据中的期末审定数合计
    const resp = options.allResponses.value.get('H2-1-rows')
    const raw = resp?.remark ?? resp?.conclusion
    let h1AuditedTotal = 0

    if (raw) {
      try {
        const h1Rows = JSON.parse(raw)
        if (Array.isArray(h1Rows)) {
          for (const r of h1Rows) {
            h1AuditedTotal += _getNum(r.endAudited)
          }
        }
      } catch { /* 静默处理 */ }
    }

    const detailCipEnd = subtotalRow.value.cipEnd
    const diff = detailCipEnd - h1AuditedTotal
    return {
      diff,
      isMatch: Math.abs(diff) < 0.01,
    }
  })

  // ─── Computed: 超预算行标记 ────────────────────────────────────────────────

  /**
   * Req 3.9: 完工进度>100%时红色高亮该行"超预算"
   */
  const overBudgetRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of rows.value) {
      if (row.completionRate != null && row.completionRate > 100) {
        ids.add(row.rowId)
      }
    }
    return ids
  })

  // ─── Actions: addRow ───────────────────────────────────────────────────────

  /**
   * Req 3.6: 添加工程项目行
   * 交互层调用 ElMessageBox.prompt 获取名称后回调此方法
   */
  function addRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name || !name.trim()) return

    const newRow = _createEmptyRow(name.trim())
    rows.value.push(newRow)
    _persist()
  }

  // ─── Actions: removeRow ────────────────────────────────────────────────────

  /**
   * 删除指定行（按rowId）
   */
  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return

    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)

    // 清除选中状态
    if (selectedRowId.value === rowId) {
      selectedRowId.value = null
    }
    _persist()
  }

  // ─── Actions: updateCell ───────────────────────────────────────────────────

  /**
   * Req 3.3: 编辑单元格后自动重算公式列
   * 公式列（increaseTotal/cipEnd/completionRate/impairmentEnd/netValue/unitCost）不可直接修改
   */
  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return

    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    // 公式列拒绝直接修改
    const formulaFields = ['increaseTotal', 'cipEnd', 'completionRate', 'impairmentEnd', 'netValue', 'unitCost']
    if (formulaFields.includes(field)) return

    // 日期/文本字段直接赋值
    const textFields = [
      'name', 'startDate', 'plannedEndDate', 'actualEndDate', 'fundSource',
      'category', 'transferDate', 'transferToH1', 'contractNo', 'contractor',
      'supervisor', 'progressNote', 'auditFlag', 'indexRef', 'remark',
    ]
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
    } else {
      // 数值字段
      ;(row as any)[field] = _getNum(value)
    }

    // 重算公式列
    _recalcFormulas(row)
    _persist()
  }

  // ─── Actions: selectRow (跨Tab行同步高亮) ──────────────────────────────────

  /**
   * Req 3.2: 3个区段Tab切换时保持行同步（选中行高亮跨Tab一致）
   */
  function selectRow(rowId: string | null): void {
    selectedRowId.value = rowId
  }

  // ─── Actions: saveNote / saveConclusion ────────────────────────────────────

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Persist (rows → allResponses) ─────────────────────────────────────────

  /**
   * 持久化行数据到 allResponses（去掉公式列，运行时重算）
   */
  function _persist(): void {
    if (!options.onSave) return

    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      // 基本信息
      name: r.name,
      budget: r.budget,
      startDate: r.startDate,
      plannedEndDate: r.plannedEndDate,
      actualEndDate: r.actualEndDate,
      accumulatedInput: r.accumulatedInput,
      fundSource: r.fundSource,
      capRate: r.capRate,
      category: r.category,
      // 增减
      cipBegin: r.cipBegin,
      increaseMaterial: r.increaseMaterial,
      increaseLabor: r.increaseLabor,
      increaseMachinery: r.increaseMachinery,
      increaseInterest: r.increaseInterest,
      increaseOther: r.increaseOther,
      decrease: r.decrease,
      transferOut: r.transferOut,
      unadjustedEnd: r.unadjustedEnd,
      beginAudited: r.beginAudited,
      adjustBegin: r.adjustBegin,
      adjustEnd: r.adjustEnd,
      decreaseAdj: r.decreaseAdj,
      transferAdj: r.transferAdj,
      endAudited: r.endAudited,
      increaseAdj: r.increaseAdj,
      aje: r.aje,
      rje: r.rje,
      // 竣工结转
      transferDate: r.transferDate,
      transferAmount: r.transferAmount,
      transferToH1: r.transferToH1,
      remainingCip: r.remainingCip,
      impairmentBegin: r.impairmentBegin,
      impairmentIncrease: r.impairmentIncrease,
      impairmentDecrease: r.impairmentDecrease,
      contractNo: r.contractNo,
      contractor: r.contractor,
      supervisor: r.supervisor,
      area: r.area,
      progressNote: r.progressNote,
      auditFlag: r.auditFlag,
      indexRef: r.indexRef,
      remark: r.remark,
    }))

    options.onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    auditNote,
    auditConclusion,
    selectedRowId,

    // Computed
    subtotalRow,
    crossValidationH1,
    overBudgetRowIds,

    // Actions
    addRow,
    removeRow,
    updateCell,
    selectRow,
    saveNote,
    saveConclusion,

    // Init (外部可显式调用)
    initFromAllResponses,
  }
}

export default useH2Detail
