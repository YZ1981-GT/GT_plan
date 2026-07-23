/**
 * useI4Detail — I4-2 长期待摊费用明细表（对齐致同 Excel 滚动勾稽）
 *
 * Excel 结构：
 *   项目信息 + 初始入账金额
 *   未审数：期初 → 本期增加 → 本期减少(摊销/其他) → 期末
 *   期初调整 + 账项调整(增/摊销/其他减)
 *   审定数：同上结构（公式）
 *   合同协议索引 / 备注
 *
 * HTML 区段：
 *   0 未审滚动 | 1 调整与审定 | 2 摊销信息 | 3 基础信息
 *
 * 兼容旧 25 列三区段字段（beginBalance/currentIncrease/…），由滚动公式回写，
 * 供 I4-1 / I4-4 / I4-5 / CrossSheet 继续读取。
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/ Task 3.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcAssetEndBalance, calcSubtotal } from './useI4FormulaEngine'
import {
  calcStraightLineAmort,
  calcRemainingMonths,
  calcAmortizationRate,
} from './useI4AmortizationEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface I4DetailRow {
  rowId: string

  // ── 项目识别 ──
  projectName: string
  /** Excel「类别」A/B/C */
  category: string
  /** Excel「资产类型」 */
  assetType: string
  projectCode: string
  /** 费用类型（摊销政策/附注用） */
  expenseType: string

  /** 初始入账金额 */
  originalAmount: number

  // ── 未审数 ──
  unadjOpening: number
  unadjIncrease: number
  unadjAmortization: number
  unadjOtherDecrease: number
  /** 公式：期初+增加−摊销−其他 */
  unadjEnding: number

  // ── 期初调整 + 账项调整 ──
  openingAdj: number
  ajeIncrease: number
  ajeAmortization: number
  ajeOtherDecrease: number

  // ── 审定数（公式）──
  auditedOpening: number
  auditedIncrease: number
  auditedAmortization: number
  auditedOtherDecrease: number
  auditedEnding: number

  // ── 摊销政策 ──
  amortizationMethod: string
  totalMonths: number
  elapsedMonths: number
  accAmortization: number
  monthlyAmortization: number
  amortizationStartMonth: string
  remainingMonths: number
  amortizationProgress: number

  // ── 基础 / 索引 ──
  occurDate: string
  accountCategory: string
  contractNo: string
  startDate: string
  endDate: string
  indexNo: string
  remark: string
  status: string

  // ── 旧字段别名（回写，供下游）──
  /** @deprecated → auditedOpening */
  beginBalance: number
  /** @deprecated → auditedIncrease */
  currentIncrease: number
  /** @deprecated → auditedAmortization */
  currentAmortization: number
  /** @deprecated → auditedOtherDecrease */
  currentDecrease: number
  /** @deprecated → auditedEnding */
  endBalance: number
  /** @deprecated → unadjOpening（上期审定代理） */
  priorBalance: number
}

export type I4DetailSection = 0 | 1 | 2 | 3

export const I4_DETAIL_SECTION_LABELS = ['未审滚动', '调整与审定', '摊销信息', '基础信息'] as const

export const I4_2_OBJECTIVES = [
  '核对长期待摊费用明细账与总账、财务报表是否相符。',
  '检查期初余额是否与上期审定报告一致。',
  '通过未审→调整→审定滚动，核实本期增减、摊销及其他减少，确认期末余额正确。',
] as const

export const I4_2_PREP_NOTES = [
  '长期待摊费用，是指企业已经支出，但摊销期限在 1 年以上的各项费用，如以经营租赁方式租入的固定资产发生的改良支出等。',
  '企业对其所拥有的固定资产发生的改良支出，可以资本化计入固定资产，也可作为长期待摊费用核算；判断关键在于该支出能否确认为资产（能否带来未来经济利益流入）。',
  '企业在筹建期间发生的开办费（人员工资、办公费、培训费、差旅费等），应于发生时计入「管理费用—开办费」，不得作为长期待摊费用。',
  '首次执行企业会计准则时，原长期待摊费用中的开办费余额，应在首次执行日全部转入管理费用。',
] as const

export const I4_2_TAX_NOTES = [
  '《企业所得税法》第十三条：已足额提取折旧的固定资产的改建支出、租入固定资产的改建支出、固定资产的大修理支出及其他规定支出，可作为长期待摊费用按规定摊销扣除。',
  '《实施条例》第六十八条：固定资产大修理支出须同时满足——修理支出达到取得时计税基础 50% 以上，且修理后使用年限延长 2 年以上；按尚可使用年限分期摊销。其他支出摊销年限不得低于 3 年，自支出发生月份的次月起。',
] as const

export interface I4DetailSubtotals {
  originalAmount: number
  unadjOpening: number
  unadjIncrease: number
  unadjAmortization: number
  unadjOtherDecrease: number
  unadjEnding: number
  openingAdj: number
  ajeIncrease: number
  ajeAmortization: number
  ajeOtherDecrease: number
  auditedOpening: number
  auditedIncrease: number
  auditedAmortization: number
  auditedOtherDecrease: number
  auditedEnding: number
  // legacy aliases
  beginBalance: number
  currentIncrease: number
  currentAmortization: number
  currentDecrease: number
  endBalance: number
  accAmortization: number
}

export interface I4DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'date' | 'month' | 'select' | 'formula'
  options?: string[]
  tooltip?: string
  group?: string
}

export interface I4RollWarning {
  rowId: string
  projectName: string
  kind: 'unadj' | 'audited' | 'startup' | 'negative'
  expected: number
  actual: number
  diff: number
  message?: string
}

export interface I4CategorySubtotal {
  category: string
  count: number
  auditedEnding: number
  unadjEnding: number
  auditedAmortization: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I4-2-rows'
const TOL = 0.05

const EXPENSE_TYPE_OPTIONS = ['装修费', '开办费', '租赁改良', '大修理', '低值易耗品', '其他']
const CATEGORY_OPTIONS = [
  '使用权资产改良及维护支出',
  '租入固定资产改良支出',
  '固定资产大修理支出',
  '开办费',
  '其他',
  '',
]
const ASSET_TYPE_OPTIONS = ['租入固定资产改良', '自有固定资产改建', '大修理支出', '其他', '']
const AMORTIZATION_METHOD_OPTIONS = ['直线法', '工作量法']
const STATUS_OPTIONS = ['正常', '已到期', '提前终止']

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

function generateRowId(): string {
  return `i42-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

export function emptyI4DetailRow(partial?: Partial<I4DetailRow>): I4DetailRow {
  const row: I4DetailRow = {
    rowId: generateRowId(),
    projectName: '',
    category: '',
    assetType: '',
    projectCode: '',
    expenseType: '',
    originalAmount: 0,
    unadjOpening: 0,
    unadjIncrease: 0,
    unadjAmortization: 0,
    unadjOtherDecrease: 0,
    unadjEnding: 0,
    openingAdj: 0,
    ajeIncrease: 0,
    ajeAmortization: 0,
    ajeOtherDecrease: 0,
    auditedOpening: 0,
    auditedIncrease: 0,
    auditedAmortization: 0,
    auditedOtherDecrease: 0,
    auditedEnding: 0,
    amortizationMethod: '直线法',
    totalMonths: 0,
    elapsedMonths: 0,
    accAmortization: 0,
    monthlyAmortization: 0,
    amortizationStartMonth: '',
    remainingMonths: 0,
    amortizationProgress: 0,
    occurDate: '',
    accountCategory: '',
    contractNo: '',
    startDate: '',
    endDate: '',
    indexNo: '',
    remark: '',
    status: '正常',
    beginBalance: 0,
    currentIncrease: 0,
    currentAmortization: 0,
    currentDecrease: 0,
    endBalance: 0,
    priorBalance: 0,
  }
  Object.assign(row, partial)
  return row
}

/** 回写旧字段别名（I4-1/I4-5/CrossSheet） */
export function syncI4DetailLegacyAliases(row: I4DetailRow): void {
  row.beginBalance = row.auditedOpening
  row.currentIncrease = row.auditedIncrease
  row.currentAmortization = row.auditedAmortization
  row.currentDecrease = row.auditedOtherDecrease
  row.endBalance = row.auditedEnding
  row.priorBalance = row.unadjOpening
}

/**
 * 滚动公式：
 *   未审期末 = 期初+增−摊销−其他
 *   审定* = 未审* + 调整*
 *   审定期末 = 审定期初+增−摊销−其他
 */
export function recalcI4DetailRow(row: I4DetailRow): void {
  // 旧数据仅有 beginBalance 等时，灌入未审列
  if (!row.unadjOpening && row.beginBalance) row.unadjOpening = row.beginBalance
  if (!row.unadjIncrease && row.currentIncrease) row.unadjIncrease = row.currentIncrease
  if (!row.unadjAmortization && row.currentAmortization) row.unadjAmortization = row.currentAmortization
  if (!row.unadjOtherDecrease && row.currentDecrease) row.unadjOtherDecrease = row.currentDecrease
  if (!row.originalAmount && row.unadjIncrease) row.originalAmount = row.unadjIncrease

  row.unadjEnding = _round2(calcAssetEndBalance(
    row.unadjOpening,
    row.unadjIncrease,
    row.unadjAmortization,
    row.unadjOtherDecrease,
  ))

  row.auditedOpening = _round2(row.unadjOpening + row.openingAdj)
  row.auditedIncrease = _round2(row.unadjIncrease + row.ajeIncrease)
  row.auditedAmortization = _round2(row.unadjAmortization + row.ajeAmortization)
  row.auditedOtherDecrease = _round2(row.unadjOtherDecrease + row.ajeOtherDecrease)
  row.auditedEnding = _round2(calcAssetEndBalance(
    row.auditedOpening,
    row.auditedIncrease,
    row.auditedAmortization,
    row.auditedOtherDecrease,
  ))

  row.monthlyAmortization = calcStraightLineAmort(row.originalAmount, row.totalMonths)
  row.remainingMonths = calcRemainingMonths(row.totalMonths, row.elapsedMonths)
  row.amortizationProgress = calcAmortizationRate(row.elapsedMonths, row.totalMonths)

  // 若累计摊销为空且有已摊月数，可提示性回填（不强制覆盖手工累计）
  if (!row.accAmortization && row.monthlyAmortization > 0 && row.elapsedMonths > 0) {
    row.accAmortization = _round2(row.monthlyAmortization * row.elapsedMonths)
  }

  syncI4DetailLegacyAliases(row)
}

export function normalizeI4DetailRow(raw: any): I4DetailRow {
  const row = emptyI4DetailRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName || raw?.name),
    category: _str(raw?.category || raw?.类别),
    assetType: _str(raw?.assetType || raw?.资产类型),
    projectCode: _str(raw?.projectCode || raw?.项目编码),
    expenseType: _str(raw?.expenseType || raw?.accountCategory),
    originalAmount: _num(raw?.originalAmount),
    unadjOpening: _num(raw?.unadjOpening ?? raw?.beginBalance ?? raw?.期初),
    unadjIncrease: _num(raw?.unadjIncrease ?? raw?.currentIncrease ?? raw?.increase),
    unadjAmortization: _num(raw?.unadjAmortization ?? raw?.currentAmortization ?? raw?.amortization),
    unadjOtherDecrease: _num(raw?.unadjOtherDecrease ?? raw?.currentDecrease ?? raw?.decrease),
    unadjEnding: _num(raw?.unadjEnding ?? raw?.endBalance),
    openingAdj: _num(raw?.openingAdj),
    ajeIncrease: _num(raw?.ajeIncrease),
    ajeAmortization: _num(raw?.ajeAmortization),
    ajeOtherDecrease: _num(raw?.ajeOtherDecrease),
    auditedOpening: _num(raw?.auditedOpening),
    auditedIncrease: _num(raw?.auditedIncrease),
    auditedAmortization: _num(raw?.auditedAmortization),
    auditedOtherDecrease: _num(raw?.auditedOtherDecrease),
    auditedEnding: _num(raw?.auditedEnding),
    amortizationMethod: _str(raw?.amortizationMethod) || '直线法',
    totalMonths: _num(raw?.totalMonths),
    elapsedMonths: _num(raw?.elapsedMonths),
    accAmortization: _num(raw?.accAmortization),
    monthlyAmortization: _num(raw?.monthlyAmortization),
    amortizationStartMonth: _str(raw?.amortizationStartMonth),
    remainingMonths: _num(raw?.remainingMonths),
    amortizationProgress: _num(raw?.amortizationProgress),
    occurDate: _str(raw?.occurDate || raw?.startDate),
    accountCategory: _str(raw?.accountCategory),
    contractNo: _str(raw?.contractNo),
    startDate: _str(raw?.startDate),
    endDate: _str(raw?.endDate),
    indexNo: _str(raw?.indexNo || raw?.indexRef),
    remark: _str(raw?.remark),
    status: _str(raw?.status) || '正常',
    beginBalance: _num(raw?.beginBalance),
    currentIncrease: _num(raw?.currentIncrease),
    currentAmortization: _num(raw?.currentAmortization),
    currentDecrease: _num(raw?.currentDecrease),
    endBalance: _num(raw?.endBalance),
    priorBalance: _num(raw?.priorBalance),
  })
  recalcI4DetailRow(row)
  return row
}

export function collectI4RollWarnings(rows: I4DetailRow[]): I4RollWarning[] {
  const out: I4RollWarning[] = []
  for (const row of rows) {
    if (!row.projectName || row.projectName === '合计') continue

    const unadjExpected = _round2(calcAssetEndBalance(
      row.unadjOpening, row.unadjIncrease, row.unadjAmortization, row.unadjOtherDecrease,
    ))
    if (Math.abs(row.unadjEnding - unadjExpected) > TOL) {
      out.push({
        rowId: row.rowId,
        projectName: row.projectName,
        kind: 'unadj',
        expected: unadjExpected,
        actual: row.unadjEnding,
        diff: _round2(row.unadjEnding - unadjExpected),
        message: '未审期末勾稽不平',
      })
    }

    const audExpected = _round2(calcAssetEndBalance(
      row.auditedOpening, row.auditedIncrease, row.auditedAmortization, row.auditedOtherDecrease,
    ))
    if (Math.abs(row.auditedEnding - audExpected) > TOL) {
      out.push({
        rowId: row.rowId,
        projectName: row.projectName,
        kind: 'audited',
        expected: audExpected,
        actual: row.auditedEnding,
        diff: _round2(row.auditedEnding - audExpected),
        message: '审定期末勾稽不平',
      })
    }

    if (row.expenseType === '开办费' && (row.auditedEnding > TOL || row.unadjEnding > TOL || row.originalAmount > TOL)) {
      out.push({
        rowId: row.rowId,
        projectName: row.projectName,
        kind: 'startup',
        expected: 0,
        actual: row.auditedEnding,
        diff: row.auditedEnding,
        message: '开办费应费用化，不得作为长期待摊费用',
      })
    }

    if (row.auditedEnding < -TOL) {
      out.push({
        rowId: row.rowId,
        projectName: row.projectName,
        kind: 'negative',
        expected: 0,
        actual: row.auditedEnding,
        diff: row.auditedEnding,
        message: '审定期末为负，请复核摊销/其他减少',
      })
    }
  }
  return out
}

export function summarizeI4ByCategory(rows: I4DetailRow[]): I4CategorySubtotal[] {
  const map = new Map<string, I4CategorySubtotal>()
  for (const row of rows) {
    if (!row.projectName || row.projectName === '合计') continue
    const cat = row.category || '未分类'
    const cur = map.get(cat) || {
      category: cat,
      count: 0,
      auditedEnding: 0,
      unadjEnding: 0,
      auditedAmortization: 0,
    }
    cur.count += 1
    cur.auditedEnding = _round2(cur.auditedEnding + row.auditedEnding)
    cur.unadjEnding = _round2(cur.unadjEnding + row.unadjEnding)
    cur.auditedAmortization = _round2(cur.auditedAmortization + row.auditedAmortization)
    map.set(cat, cur)
  }
  return [...map.values()].sort((a, b) => a.category.localeCompare(b.category, 'zh'))
}

export function buildI4DetailConclusionDraft(opts: {
  rowCount: number
  auditedEnding: number
  unadjEnding: number
  warningCount: number
  categoryCount: number
}): string {
  const parts = [
    `已编制长期待摊费用明细 ${opts.rowCount} 项，覆盖 ${opts.categoryCount || 1} 个类别。`,
    `未审期末合计 ${opts.unadjEnding.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，审定期末合计 ${opts.auditedEnding.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}。`,
  ]
  if (opts.warningCount > 0) {
    parts.push(`发现 ${opts.warningCount} 处滚动勾稽差异，已在表内标注，请复核后再下结论。`)
  } else {
    parts.push('未审/审定滚动勾稽平衡；期初与上期审定、明细与总账勾稽请结合 I4-1 进一步确认。')
  }
  parts.push('开办费不得资本化；租入固定资产改良及大修理支出摊销期限请对照编制说明与税法规定。')
  parts.push('长期待摊费用明细在重大方面列报适当（请结合 I4-1 审定表、I4-4 摊销政策综合判断）。')
  return parts.join('')
}

// ─── Column Definitions ──────────────────────────────────────────────────────

const UNAUDITED_COLUMNS: I4DetailColumn[] = [
  { key: 'projectName', label: '项目名称', width: 160, editable: true, type: 'text', group: '项目' },
  { key: 'category', label: '类别', width: 90, editable: true, type: 'select', options: CATEGORY_OPTIONS.filter(Boolean), group: '项目' },
  { key: 'assetType', label: '资产类型', width: 130, editable: true, type: 'select', options: ASSET_TYPE_OPTIONS.filter(Boolean), group: '项目' },
  { key: 'projectCode', label: '项目编码', width: 100, editable: true, type: 'text', group: '项目' },
  { key: 'originalAmount', label: '初始入账金额', width: 120, editable: true, type: 'number', group: '项目' },
  { key: 'unadjOpening', label: '期初数', width: 110, editable: true, type: 'number', group: '未审数' },
  { key: 'unadjIncrease', label: '本期增加', width: 110, editable: true, type: 'number', group: '未审数' },
  { key: 'unadjAmortization', label: '本期摊销', width: 110, editable: true, type: 'number', group: '未审减少' },
  { key: 'unadjOtherDecrease', label: '其他减少', width: 110, editable: true, type: 'number', group: '未审减少' },
  {
    key: 'unadjEnding', label: '期末数', width: 110, editable: false, type: 'formula', group: '未审数',
    tooltip: '未审期末=期初+本期增加−本期摊销−其他减少',
  },
]

const AUDITED_COLUMNS: I4DetailColumn[] = [
  { key: 'projectName', label: '项目名称', width: 160, editable: false, type: 'text' },
  { key: 'openingAdj', label: '期初调整', width: 100, editable: true, type: 'number', group: '调整' },
  { key: 'ajeIncrease', label: '调整-增加', width: 100, editable: true, type: 'number', group: '账项调整' },
  { key: 'ajeAmortization', label: '调整-摊销', width: 100, editable: true, type: 'number', group: '账项调整' },
  { key: 'ajeOtherDecrease', label: '调整-其他减少', width: 110, editable: true, type: 'number', group: '账项调整' },
  {
    key: 'auditedOpening', label: '审定期初', width: 110, editable: false, type: 'formula', group: '审定数',
    tooltip: '审定期初=未审期初+期初调整',
  },
  {
    key: 'auditedIncrease', label: '审定增加', width: 110, editable: false, type: 'formula', group: '审定数',
    tooltip: '审定增加=未审增加+账项调整增加',
  },
  {
    key: 'auditedAmortization', label: '审定摊销', width: 110, editable: false, type: 'formula', group: '审定数',
    tooltip: '审定摊销=未审摊销+账项调整摊销',
  },
  {
    key: 'auditedOtherDecrease', label: '审定其他减少', width: 120, editable: false, type: 'formula', group: '审定数',
    tooltip: '审定其他减少=未审其他减少+账项调整其他减少',
  },
  {
    key: 'auditedEnding', label: '审定期末', width: 110, editable: false, type: 'formula', group: '审定数',
    tooltip: '审定期末=审定期初+增加−摊销−其他减少',
  },
  { key: 'indexNo', label: '合同协议索引', width: 120, editable: true, type: 'text' },
  { key: 'remark', label: '备注', width: 140, editable: true, type: 'text' },
]

const AMORT_COLUMNS: I4DetailColumn[] = [
  { key: 'projectName', label: '项目名称', width: 160, editable: false, type: 'text' },
  { key: 'expenseType', label: '费用类型', width: 110, editable: true, type: 'select', options: EXPENSE_TYPE_OPTIONS },
  { key: 'amortizationMethod', label: '摊销方法', width: 100, editable: true, type: 'select', options: AMORTIZATION_METHOD_OPTIONS },
  { key: 'totalMonths', label: '期限(月)', width: 90, editable: true, type: 'number' },
  { key: 'elapsedMonths', label: '已摊月数', width: 90, editable: true, type: 'number' },
  { key: 'accAmortization', label: '累计摊销', width: 110, editable: true, type: 'number' },
  {
    key: 'monthlyAmortization', label: '月摊销额', width: 110, editable: false, type: 'formula',
    tooltip: '月摊销额=初始入账金额÷摊销期限(月)',
  },
  { key: 'amortizationStartMonth', label: '摊销起始月', width: 120, editable: true, type: 'month' },
  {
    key: 'remainingMonths', label: '剩余月数', width: 90, editable: false, type: 'formula',
    tooltip: '剩余月数=期限−已摊月数',
  },
  {
    key: 'amortizationProgress', label: '摊销进度%', width: 100, editable: false, type: 'formula',
    tooltip: '摊销进度=已摊月数÷期限',
  },
  { key: 'status', label: '状态', width: 100, editable: true, type: 'select', options: STATUS_OPTIONS },
]

const BASIC_COLUMNS: I4DetailColumn[] = [
  { key: 'projectName', label: '项目名称', width: 160, editable: true, type: 'text' },
  { key: 'occurDate', label: '发生日期', width: 120, editable: true, type: 'date' },
  { key: 'accountCategory', label: '科目分类', width: 110, editable: true, type: 'text' },
  { key: 'contractNo', label: '合同编号', width: 120, editable: true, type: 'text' },
  { key: 'startDate', label: '受益起始日', width: 120, editable: true, type: 'date' },
  { key: 'endDate', label: '受益结束日', width: 120, editable: true, type: 'date' },
  { key: 'indexNo', label: '索引号', width: 100, editable: true, type: 'text' },
  { key: 'remark', label: '备注', width: 150, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI4Detail(
  allResponses: Ref<Map<string, any>>,
  options?: {
    adjBeginSubtotal?: Ref<number>
    adjEndSubtotal?: Ref<number>
    adjAmortizationSubtotal?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const rows = ref<I4DetailRow[]>([])
  const activeSection = ref<I4DetailSection>(0)
  const activeRowIndex = ref<number>(-1)

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map(normalizeI4DetailRow)
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, JSON.stringify(rows.value))
  }

  function recalcAll(): void {
    for (const row of rows.value) recalcI4DetailRow(row)
  }

  const subtotals: ComputedRef<I4DetailSubtotals> = computed(() => {
    const r = rows.value
    const auditedOpening = calcSubtotal(r.map((x) => x.auditedOpening))
    const auditedIncrease = calcSubtotal(r.map((x) => x.auditedIncrease))
    const auditedAmortization = calcSubtotal(r.map((x) => x.auditedAmortization))
    const auditedOtherDecrease = calcSubtotal(r.map((x) => x.auditedOtherDecrease))
    const auditedEnding = calcSubtotal(r.map((x) => x.auditedEnding))
    return {
      originalAmount: calcSubtotal(r.map((x) => x.originalAmount)),
      unadjOpening: calcSubtotal(r.map((x) => x.unadjOpening)),
      unadjIncrease: calcSubtotal(r.map((x) => x.unadjIncrease)),
      unadjAmortization: calcSubtotal(r.map((x) => x.unadjAmortization)),
      unadjOtherDecrease: calcSubtotal(r.map((x) => x.unadjOtherDecrease)),
      unadjEnding: calcSubtotal(r.map((x) => x.unadjEnding)),
      openingAdj: calcSubtotal(r.map((x) => x.openingAdj)),
      ajeIncrease: calcSubtotal(r.map((x) => x.ajeIncrease)),
      ajeAmortization: calcSubtotal(r.map((x) => x.ajeAmortization)),
      ajeOtherDecrease: calcSubtotal(r.map((x) => x.ajeOtherDecrease)),
      auditedOpening,
      auditedIncrease,
      auditedAmortization,
      auditedOtherDecrease,
      auditedEnding,
      beginBalance: auditedOpening,
      currentIncrease: auditedIncrease,
      currentAmortization: auditedAmortization,
      currentDecrease: auditedOtherDecrease,
      endBalance: auditedEnding,
      accAmortization: calcSubtotal(r.map((x) => x.accAmortization)),
    }
  })

  const rollWarnings = computed(() => collectI4RollWarnings(rows.value))
  const categorySubtotals = computed(() => summarizeI4ByCategory(rows.value))

  function switchSection(section: I4DetailSection): void {
    activeSection.value = section
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    recalcI4DetailRow(row)
    _persist()
  }

  async function addRow(): Promise<void> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入待摊费用项目名称',
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：办公室装修摊销',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )
      if (!name?.trim()) return
      const newRow = emptyI4DetailRow({ projectName: name.trim() })
      recalcI4DetailRow(newRow)
      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
    } catch {
      /* cancel */
    }
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

  function importRows(importedData: any[]): void {
    rows.value = importedData.map(normalizeI4DetailRow)
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  function exportRows(): I4DetailRow[] {
    return [...rows.value]
  }

  const sections = [
    { key: 0 as I4DetailSection, label: '未审滚动', columns: UNAUDITED_COLUMNS },
    { key: 1 as I4DetailSection, label: '调整与审定', columns: AUDITED_COLUMNS },
    { key: 2 as I4DetailSection, label: '摊销信息', columns: AMORT_COLUMNS },
    { key: 3 as I4DetailSection, label: '基础信息', columns: BASIC_COLUMNS },
  ]

  const segments = {
    unaudited: UNAUDITED_COLUMNS,
    audited: AUDITED_COLUMNS,
    amortization: AMORT_COLUMNS,
    basic: BASIC_COLUMNS,
  }

  const activeColumns = computed(() =>
    sections.find((s) => s.key === activeSection.value)?.columns ?? UNAUDITED_COLUMNS,
  )

  watch(allResponses, () => _loadRows(), { immediate: true })

  return {
    rows,
    activeSection,
    activeRowIndex,
    subtotals,
    rollWarnings,
    categorySubtotals,
    activeColumns,
    segments,
    sections,
    switchSection,
    setActiveRow,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    exportRows,
  }
}

export default useI4Detail
