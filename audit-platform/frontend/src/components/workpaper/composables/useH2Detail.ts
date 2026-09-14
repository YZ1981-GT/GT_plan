/**
 * useH2Detail — H2-2 在建工程明细表
 *
 * 对齐致同源模板 + H1-2 编制逻辑：
 * - 基本信息（进度/权属风险标志）
 * - 账面原值未审 roll-forward（期初+增−转固−其他减=期末；利息资本化子列）
 * - 期初调整 / 账项调整 → 审定自动勾稽
 * - 减值准备未审→调整→审定；净值=原值−减值；是否抵押
 *
 * 后向兼容：保留 cipBegin / decrease / transferAmount / cipEnd / endAudited 等字段名，
 * 供 H2-4/H2-5/H2-6 等下游取数。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcCipEndBalance,
  calcSubtotal,
  calcCompletionRate,
} from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H2DetailRow {
  rowId: string

  // ── 基本信息 ──
  name: string
  projectCode: string
  budget: number
  startDate: string
  plannedEndDate: string
  actualEndDate: string
  /** 完工进度(%) = 累计投入/预算×100 */
  completionRate: number | null
  accumulatedInput: number
  fundSource: string
  /** 利息资本化率(%) */
  capRate: number | null
  category: string
  /** 工程状态：在建/停工/缓建/已完工待转固/已转固 */
  projectStatus: string
  approvalDocNo: string
  contractNo: string
  contractor: string
  supervisor: string
  area: number | null
  unitCost: number | null
  progressNote: string
  /** 是否抵押/受限 Y/N */
  isMortgaged: string
  auditFlag: string
  indexRef: string
  remark: string

  // ── 账面原值·未审（对齐致同 J–R）──
  cipBegin: number
  /** 期初累计资本化利息 */
  interestBegin: number
  increaseMaterial: number
  increaseLabor: number
  increaseMachinery: number
  increaseInterest: number
  increaseOther: number
  /** 增加合计（公式） */
  increaseTotal: number
  /** 本期转入固定资产 */
  transferAmount: number
  /** 其他减少（报废/转让等，非转固） */
  decrease: number
  /** @deprecated 并入 decrease；读取时兼容累加 */
  transferOut: number
  /** 转出累计资本化利息 */
  interestDec: number
  /** 未审期末原值（公式） */
  cipEnd: number
  /** 未审期末累计资本化利息（公式） */
  interestEnd: number

  // ── 调整 → 审定原值（对齐致同 S–AH / H1 原值区）──
  adjustBegin: number
  increaseAdj: number
  transferAdj: number
  decreaseAdj: number
  interestOpenAdj: number
  interestIncAdj: number
  interestDecAdj: number
  /** @deprecated 保留兼容；审定公式不再单独使用 */
  adjustEnd: number
  aje: number
  rje: number
  unadjustedEnd: number

  beginAudited: number
  increaseAudited: number
  transferAudited: number
  decreaseAudited: number
  endAudited: number
  interestBeginAud: number
  interestIncAud: number
  interestDecAud: number
  interestEndAud: number

  // ── 竣工结转辅助 ──
  transferDate: string
  transferToH1: string
  /** 兼容旧字段名 */
  transferTo: string
  remainingCip: number

  // ── 减值准备（对齐致同 AI–AS / H1 减值区）──
  impairmentBegin: number
  impairmentIncrease: number
  impairmentDecrease: number
  /** 减值未审期末（公式） */
  impairmentEnd: number
  impairOpenAdj: number
  impairIncAdj: number
  impairDecAdj: number
  impairBeginAud: number
  impairIncAud: number
  impairDecAud: number
  impairEndAud: number

  // ── 净值 ──
  netBeginUnadj: number
  netBeginAud: number
  netEndUnadj: number
  netEndAud: number
  /** @deprecated 等同 netEndAud，下游兼容 */
  netValue: number
}

export interface SegmentColumn {
  field: keyof H2DetailRow
  label: string
  width?: number
  formula?: boolean
  isAmount?: boolean
  isDate?: boolean
}

export const SEGMENT_CONFIGS = {
  basic: [
    { field: 'name', label: '工程名称', width: 180 },
    { field: 'budget', label: '预算金额', isAmount: true, width: 130 },
    { field: 'category', label: '工程类别', width: 100 },
    { field: 'projectStatus', label: '工程状态', width: 110 },
    { field: 'startDate', label: '开工日期', isDate: true, width: 110 },
    { field: 'plannedEndDate', label: '预计竣工', isDate: true, width: 110 },
    { field: 'actualEndDate', label: '实际竣工', isDate: true, width: 110 },
    { field: 'completionRate', label: '完工进度(%)', formula: true, width: 110 },
    { field: 'accumulatedInput', label: '累计投入', isAmount: true, width: 120 },
    { field: 'fundSource', label: '资金来源', width: 100 },
    { field: 'capRate', label: '资本化率(%)', width: 100 },
    { field: 'isMortgaged', label: '是否抵押', width: 90 },
  ] as SegmentColumn[],
  costUnadj: [
    { field: 'name', label: '工程名称', width: 160 },
    { field: 'cipBegin', label: '期初余额', isAmount: true, width: 120 },
    { field: 'interestBegin', label: '其中:累计资本化', isAmount: true, width: 120 },
    { field: 'increaseTotal', label: '本期增加', isAmount: true, formula: true, width: 110 },
    { field: 'increaseInterest', label: '其中:本期利息资本化', isAmount: true, width: 130 },
    { field: 'transferAmount', label: '转入固定资产', isAmount: true, width: 120 },
    { field: 'decrease', label: '其他减少', isAmount: true, width: 110 },
    { field: 'interestDec', label: '其中:资本化转出', isAmount: true, width: 120 },
    { field: 'cipEnd', label: '期末余额', isAmount: true, formula: true, width: 120 },
    { field: 'interestEnd', label: '其中:累计资本化', isAmount: true, formula: true, width: 120 },
  ] as SegmentColumn[],
  costAud: [
    { field: 'name', label: '工程名称', width: 160 },
    { field: 'adjustBegin', label: '期初调整', isAmount: true, width: 100 },
    { field: 'increaseAdj', label: '增加调整', isAmount: true, width: 100 },
    { field: 'transferAdj', label: '转固调整', isAmount: true, width: 100 },
    { field: 'decreaseAdj', label: '其他减少调整', isAmount: true, width: 110 },
    { field: 'beginAudited', label: '审定期初', isAmount: true, formula: true, width: 110 },
    { field: 'increaseAudited', label: '审定增加', isAmount: true, formula: true, width: 110 },
    { field: 'transferAudited', label: '审定转固', isAmount: true, formula: true, width: 110 },
    { field: 'decreaseAudited', label: '审定其他减少', isAmount: true, formula: true, width: 120 },
    { field: 'endAudited', label: '审定期末', isAmount: true, formula: true, width: 110 },
    { field: 'interestEndAud', label: '审定累计资本化', isAmount: true, formula: true, width: 120 },
  ] as SegmentColumn[],
  impair: [
    { field: 'name', label: '工程名称', width: 160 },
    { field: 'impairmentBegin', label: '减值期初', isAmount: true, width: 100 },
    { field: 'impairmentIncrease', label: '减值增加', isAmount: true, width: 100 },
    { field: 'impairmentDecrease', label: '减值减少', isAmount: true, width: 100 },
    { field: 'impairmentEnd', label: '减值未审期末', isAmount: true, formula: true, width: 110 },
    { field: 'impairEndAud', label: '减值审定期末', isAmount: true, formula: true, width: 110 },
    { field: 'netBeginAud', label: '期初净值(审定)', isAmount: true, formula: true, width: 120 },
    { field: 'netEndAud', label: '期末净值(审定)', isAmount: true, formula: true, width: 120 },
    { field: 'isMortgaged', label: '是否抵押', width: 90 },
  ] as SegmentColumn[],
} as const

export const H2_2_CONCLUSION_TEMPLATES = {
  A: '未见异常。',
  B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
} as const

export const H2_2_PROJECT_STATUS_OPTIONS = [
  '在建', '停工', '缓建', '已完工待转固', '已转固',
] as const

const ROWS_KEY = 'H2-2-rows'
const NOTE_KEY = 'H2-2-audit-note'
const CONCLUSION_KEY = 'H2-2-audit-conclusion'

const FORMULA_FIELDS = new Set<string>([
  'completionRate', 'increaseTotal', 'cipEnd', 'interestEnd',
  'beginAudited', 'increaseAudited', 'transferAudited', 'decreaseAudited', 'endAudited',
  'interestBeginAud', 'interestIncAud', 'interestDecAud', 'interestEndAud',
  'impairmentEnd', 'impairBeginAud', 'impairIncAud', 'impairDecAud', 'impairEndAud',
  'netBeginUnadj', 'netBeginAud', 'netEndUnadj', 'netEndAud', 'netValue', 'unitCost',
  'remainingCip', 'unadjustedEnd',
])

const TEXT_FIELDS = new Set<string>([
  'name', 'projectCode', 'startDate', 'plannedEndDate', 'actualEndDate',
  'fundSource', 'category', 'projectStatus', 'approvalDocNo',
  'transferDate', 'transferToH1', 'transferTo',
  'contractNo', 'contractor', 'supervisor', 'progressNote',
  'isMortgaged', 'auditFlag', 'indexRef', 'remark',
])

const NUMERIC_FIELDS: (keyof H2DetailRow)[] = [
  'budget', 'accumulatedInput', 'cipBegin', 'interestBegin',
  'increaseMaterial', 'increaseLabor', 'increaseMachinery',
  'increaseInterest', 'increaseOther', 'increaseTotal',
  'transferAmount', 'decrease', 'transferOut', 'interestDec',
  'cipEnd', 'interestEnd',
  'adjustBegin', 'increaseAdj', 'transferAdj', 'decreaseAdj',
  'interestOpenAdj', 'interestIncAdj', 'interestDecAdj',
  'adjustEnd', 'aje', 'rje', 'unadjustedEnd',
  'beginAudited', 'increaseAudited', 'transferAudited', 'decreaseAudited', 'endAudited',
  'interestBeginAud', 'interestIncAud', 'interestDecAud', 'interestEndAud',
  'remainingCip',
  'impairmentBegin', 'impairmentIncrease', 'impairmentDecrease', 'impairmentEnd',
  'impairOpenAdj', 'impairIncAdj', 'impairDecAdj',
  'impairBeginAud', 'impairIncAud', 'impairDecAud', 'impairEndAud',
  'netBeginUnadj', 'netBeginAud', 'netEndUnadj', 'netEndAud', 'netValue',
]

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _str(val: any): string {
  return val == null ? '' : String(val)
}

/** 其他减少口径：decrease + 旧字段 transferOut */
function _otherDecrease(row: Pick<H2DetailRow, 'decrease' | 'transferOut'>): number {
  return _getNum(row.decrease) + _getNum(row.transferOut)
}

function _createEmptyRow(name: string): H2DetailRow {
  const row: H2DetailRow = {
    rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    name,
    projectCode: '',
    budget: 0,
    startDate: '',
    plannedEndDate: '',
    actualEndDate: '',
    completionRate: null,
    accumulatedInput: 0,
    fundSource: '',
    capRate: null,
    category: '',
    projectStatus: '在建',
    approvalDocNo: '',
    contractNo: '',
    contractor: '',
    supervisor: '',
    area: null,
    unitCost: null,
    progressNote: '',
    isMortgaged: '',
    auditFlag: '',
    indexRef: '',
    remark: '',
    cipBegin: 0,
    interestBegin: 0,
    increaseMaterial: 0,
    increaseLabor: 0,
    increaseMachinery: 0,
    increaseInterest: 0,
    increaseOther: 0,
    increaseTotal: 0,
    transferAmount: 0,
    decrease: 0,
    transferOut: 0,
    interestDec: 0,
    cipEnd: 0,
    interestEnd: 0,
    adjustBegin: 0,
    increaseAdj: 0,
    transferAdj: 0,
    decreaseAdj: 0,
    interestOpenAdj: 0,
    interestIncAdj: 0,
    interestDecAdj: 0,
    adjustEnd: 0,
    aje: 0,
    rje: 0,
    unadjustedEnd: 0,
    beginAudited: 0,
    increaseAudited: 0,
    transferAudited: 0,
    decreaseAudited: 0,
    endAudited: 0,
    interestBeginAud: 0,
    interestIncAud: 0,
    interestDecAud: 0,
    interestEndAud: 0,
    transferDate: '',
    transferToH1: '',
    transferTo: '',
    remainingCip: 0,
    impairmentBegin: 0,
    impairmentIncrease: 0,
    impairmentDecrease: 0,
    impairmentEnd: 0,
    impairOpenAdj: 0,
    impairIncAdj: 0,
    impairDecAdj: 0,
    impairBeginAud: 0,
    impairIncAud: 0,
    impairDecAud: 0,
    impairEndAud: 0,
    netBeginUnadj: 0,
    netBeginAud: 0,
    netEndUnadj: 0,
    netEndAud: 0,
    netValue: 0,
  }
  _recalcFormulas(row)
  return row
}

/**
 * 致同公式对齐：
 * Q = J+L−N−O；R = K+M−P
 * Z = J+S … AG = Z+AB−AD−AE；AH = AA+AC−AF
 * AL = AI+AJ−AK；AS = AP+AQ−AR
 * AT/AU/AV/AW 净值
 */
function _recalcFormulas(row: H2DetailRow): void {
  row.increaseTotal =
    _getNum(row.increaseMaterial) +
    _getNum(row.increaseLabor) +
    _getNum(row.increaseMachinery) +
    _getNum(row.increaseInterest) +
    _getNum(row.increaseOther)

  const otherDec = _otherDecrease(row)

  // 未审期末原值 = 期初 + 增加 − 转固 − 其他减少
  row.cipEnd = calcCipEndBalance(
    _getNum(row.cipBegin),
    row.increaseTotal,
    otherDec,
    _getNum(row.transferAmount),
  )
  row.unadjustedEnd = row.cipEnd
  row.remainingCip = row.cipEnd

  row.interestEnd =
    _getNum(row.interestBegin) +
    _getNum(row.increaseInterest) -
    _getNum(row.interestDec)

  // 审定原值
  row.beginAudited = _getNum(row.cipBegin) + _getNum(row.adjustBegin)
  row.increaseAudited = row.increaseTotal + _getNum(row.increaseAdj)
  row.transferAudited = _getNum(row.transferAmount) + _getNum(row.transferAdj)
  row.decreaseAudited = otherDec + _getNum(row.decreaseAdj)
  row.endAudited = calcCipEndBalance(
    row.beginAudited,
    row.increaseAudited,
    row.decreaseAudited,
    row.transferAudited,
  )

  row.interestBeginAud = _getNum(row.interestBegin) + _getNum(row.interestOpenAdj)
  row.interestIncAud = _getNum(row.increaseInterest) + _getNum(row.interestIncAdj)
  row.interestDecAud = _getNum(row.interestDec) + _getNum(row.interestDecAdj)
  row.interestEndAud = row.interestBeginAud + row.interestIncAud - row.interestDecAud

  // 减值
  row.impairmentEnd =
    _getNum(row.impairmentBegin) +
    _getNum(row.impairmentIncrease) -
    _getNum(row.impairmentDecrease)
  row.impairBeginAud = _getNum(row.impairmentBegin) + _getNum(row.impairOpenAdj)
  row.impairIncAud = _getNum(row.impairmentIncrease) + _getNum(row.impairIncAdj)
  row.impairDecAud = _getNum(row.impairmentDecrease) + _getNum(row.impairDecAdj)
  row.impairEndAud = row.impairBeginAud + row.impairIncAud - row.impairDecAud

  // 净值
  row.netBeginUnadj = _getNum(row.cipBegin) - _getNum(row.impairmentBegin)
  row.netBeginAud = row.beginAudited - row.impairBeginAud
  row.netEndUnadj = row.cipEnd - row.impairmentEnd
  row.netEndAud = row.endAudited - row.impairEndAud
  row.netValue = row.netEndAud

  row.completionRate = calcCompletionRate(
    _getNum(row.accumulatedInput),
    _getNum(row.budget),
  )

  const area = _getNum(row.area)
  row.unitCost = area > 0 ? _getNum(row.accumulatedInput) / area : null

  // 同步旧字段 transferTo
  if (row.transferToH1 && !row.transferTo) row.transferTo = row.transferToH1
  if (row.transferTo && !row.transferToH1) row.transferToH1 = row.transferTo
}

function _normalizeRow(raw: any): H2DetailRow {
  const row = _createEmptyRow(_str(raw.name))
  row.rowId = raw.rowId ?? row.rowId
  row.projectCode = _str(raw.projectCode)
  row.budget = _getNum(raw.budget)
  row.startDate = _str(raw.startDate)
  row.plannedEndDate = _str(raw.plannedEndDate)
  row.actualEndDate = _str(raw.actualEndDate)
  row.accumulatedInput = _getNum(raw.accumulatedInput)
  row.fundSource = _str(raw.fundSource)
  row.capRate = raw.capRate != null && raw.capRate !== '' ? Number(raw.capRate) : null
  row.category = _str(raw.category)
  row.projectStatus = _str(raw.projectStatus) || '在建'
  row.approvalDocNo = _str(raw.approvalDocNo)
  row.contractNo = _str(raw.contractNo)
  row.contractor = _str(raw.contractor)
  row.supervisor = _str(raw.supervisor)
  row.area = raw.area != null && raw.area !== '' ? Number(raw.area) || null : null
  row.progressNote = _str(raw.progressNote)
  row.isMortgaged = _str(raw.isMortgaged)
  row.auditFlag = _str(raw.auditFlag)
  row.indexRef = _str(raw.indexRef)
  row.remark = _str(raw.remark)

  row.cipBegin = _getNum(raw.cipBegin)
  row.interestBegin = _getNum(raw.interestBegin)
  row.increaseMaterial = _getNum(raw.increaseMaterial)
  row.increaseLabor = _getNum(raw.increaseLabor)
  row.increaseMachinery = _getNum(raw.increaseMachinery ?? raw.increaseExpense)
  row.increaseInterest = _getNum(raw.increaseInterest)
  row.increaseOther = _getNum(raw.increaseOther)
  row.transferAmount = _getNum(raw.transferAmount ?? raw.decreaseTransfer)
  row.decrease = _getNum(raw.decrease ?? raw.decreaseOther ?? raw.decreaseDisposal)
  row.transferOut = _getNum(raw.transferOut)
  row.interestDec = _getNum(raw.interestDec)

  row.adjustBegin = _getNum(raw.adjustBegin)
  row.increaseAdj = _getNum(raw.increaseAdj)
  row.transferAdj = _getNum(raw.transferAdj)
  row.decreaseAdj = _getNum(raw.decreaseAdj)
  row.interestOpenAdj = _getNum(raw.interestOpenAdj)
  row.interestIncAdj = _getNum(raw.interestIncAdj)
  row.interestDecAdj = _getNum(raw.interestDecAdj)
  row.adjustEnd = _getNum(raw.adjustEnd)
  row.aje = _getNum(raw.aje)
  row.rje = _getNum(raw.rje)

  row.transferDate = _str(raw.transferDate)
  row.transferToH1 = _str(raw.transferToH1 || raw.transferTo)
  row.transferTo = _str(raw.transferTo || raw.transferToH1)

  row.impairmentBegin = _getNum(raw.impairmentBegin)
  row.impairmentIncrease = _getNum(raw.impairmentIncrease)
  row.impairmentDecrease = _getNum(raw.impairmentDecrease)
  row.impairOpenAdj = _getNum(raw.impairOpenAdj)
  row.impairIncAdj = _getNum(raw.impairIncAdj)
  row.impairDecAdj = _getNum(raw.impairDecAdj)

  // 旧数据若只存了 beginAudited/endAudited，尽量反推调整额（仅当调整为空）
  if (!_getNum(raw.adjustBegin) && raw.beginAudited != null) {
    const implied = _getNum(raw.beginAudited) - row.cipBegin
    if (Math.abs(implied) > 0.005) row.adjustBegin = implied
  }

  _recalcFormulas(row)
  return row
}

function _emptySubtotal(): H2DetailRow {
  const row = _createEmptyRow('合计')
  row.rowId = 'row-subtotal'
  row.projectStatus = ''
  return row
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Detail(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  const rows = ref<H2DetailRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const selectedRowId = ref<string | null>(null)

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

  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  const subtotalRow: ComputedRef<H2DetailRow> = computed(() => {
    const subtotal = _emptySubtotal()
    for (const field of NUMERIC_FIELDS) {
      ;(subtotal as any)[field] = calcSubtotal(rows.value.map(r => _getNum(r[field])))
    }
    subtotal.name = '合计'
    // 进度/单位造价不按 SUM 展示
    subtotal.completionRate = null
    subtotal.unitCost = null
    subtotal.capRate = null
    return subtotal
  })

  /** 与 H2-1 交叉验证：优先用审定期末 */
  const crossValidationH1: ComputedRef<{
    diff: number
    isMatch: boolean
    detailTotal: number
    h1Total: number
  }> = computed(() => {
    const resp = options.allResponses.value.get('H2-1-rows')
    const raw = resp?.remark ?? resp?.conclusion
    let h1AuditedTotal = 0
    if (raw) {
      try {
        const h1Rows = JSON.parse(raw)
        if (Array.isArray(h1Rows)) {
          for (const r of h1Rows) {
            h1AuditedTotal += _getNum(r.endAudited) || (_getNum(r.endUnadjusted) + _getNum(r.endAdjustment))
          }
        }
      } catch { /* ignore */ }
    }
    const detailTotal = subtotalRow.value.endAudited
    const diff = detailTotal - h1AuditedTotal
    return {
      diff,
      isMatch: Math.abs(diff) < 0.01,
      detailTotal,
      h1Total: h1AuditedTotal,
    }
  })

  const overBudgetRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of rows.value) {
      if (row.completionRate != null && row.completionRate > 100) ids.add(row.rowId)
    }
    return ids
  })

  function addRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name || !name.trim()) return
    rows.value.push(_createEmptyRow(name.trim()))
    _persist()
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    if (selectedRowId.value === rowId) selectedRowId.value = null
    _persist()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    if (FORMULA_FIELDS.has(field)) return

    if (TEXT_FIELDS.has(field)) {
      ;(row as any)[field] = String(value ?? '')
      if (field === 'transferTo') row.transferToH1 = row.transferTo
      if (field === 'transferToH1') row.transferTo = row.transferToH1
    } else {
      ;(row as any)[field] = _getNum(value)
    }
    _recalcFormulas(row)
    _persist()
  }

  function selectRow(rowId: string | null): void {
    selectedRowId.value = rowId
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  function applyConclusionTemplate(key: 'A' | 'B' | 'C'): void {
    if (options.isReadonly.value) return
    saveConclusion(H2_2_CONCLUSION_TEMPLATES[key])
  }

  function _persist(): void {
    if (!options.onSave) return
    const toPersist = rows.value.map(r => ({
      rowId: r.rowId,
      name: r.name,
      projectCode: r.projectCode,
      budget: r.budget,
      startDate: r.startDate,
      plannedEndDate: r.plannedEndDate,
      actualEndDate: r.actualEndDate,
      accumulatedInput: r.accumulatedInput,
      fundSource: r.fundSource,
      capRate: r.capRate,
      category: r.category,
      projectStatus: r.projectStatus,
      approvalDocNo: r.approvalDocNo,
      contractNo: r.contractNo,
      contractor: r.contractor,
      supervisor: r.supervisor,
      area: r.area,
      progressNote: r.progressNote,
      isMortgaged: r.isMortgaged,
      auditFlag: r.auditFlag,
      indexRef: r.indexRef,
      remark: r.remark,
      cipBegin: r.cipBegin,
      interestBegin: r.interestBegin,
      increaseMaterial: r.increaseMaterial,
      increaseLabor: r.increaseLabor,
      increaseMachinery: r.increaseMachinery,
      increaseInterest: r.increaseInterest,
      increaseOther: r.increaseOther,
      transferAmount: r.transferAmount,
      decrease: r.decrease,
      transferOut: r.transferOut,
      interestDec: r.interestDec,
      adjustBegin: r.adjustBegin,
      increaseAdj: r.increaseAdj,
      transferAdj: r.transferAdj,
      decreaseAdj: r.decreaseAdj,
      interestOpenAdj: r.interestOpenAdj,
      interestIncAdj: r.interestIncAdj,
      interestDecAdj: r.interestDecAdj,
      adjustEnd: r.adjustEnd,
      aje: r.aje,
      rje: r.rje,
      // 持久化审定结果，便于下游直接读取
      beginAudited: r.beginAudited,
      endAudited: r.endAudited,
      transferDate: r.transferDate,
      transferToH1: r.transferToH1,
      transferTo: r.transferTo || r.transferToH1,
      impairmentBegin: r.impairmentBegin,
      impairmentIncrease: r.impairmentIncrease,
      impairmentDecrease: r.impairmentDecrease,
      impairOpenAdj: r.impairOpenAdj,
      impairIncAdj: r.impairIncAdj,
      impairDecAdj: r.impairDecAdj,
      impairEndAud: r.impairEndAud,
      netEndAud: r.netEndAud,
    }))
    options.onSave(ROWS_KEY, toPersist)
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    selectedRowId,
    subtotalRow,
    crossValidationH1,
    overBudgetRowIds,
    addRow,
    removeRow,
    updateCell,
    selectRow,
    saveNote,
    saveConclusion,
    applyConclusionTemplate,
    initFromAllResponses,
  }
}

export default useH2Detail
