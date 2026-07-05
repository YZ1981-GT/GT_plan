/**
 * useG4MainDetail — G4-2 明细表（44列 → 5区段Tab，行同步 + 公式链 + 分类）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 6.1
 *
 * 职责：
 * - 44列拆为5区段Tab：基础信息(6)/期初余额(10)/本期变动(4)/期末余额+减值(10)/摊余成本+审定(8)
 * - 公式链：期初小计/期初摊余成本/本期变动小计/期末各项/期末小计/摊余成本/一年内到期小计/账面价值
 * - 按到期日与资产负债表日比较进行数据分类（一年内到期 vs 超过一年）
 * - 底部合计行（按投资种类分类小计 + 总计）
 * - 动态行增删（max 500行，ElMessageBox.prompt输入投资项目名称）
 * - 空值/非数字输入视为0参与计算
 * - selectedRowIndex ref 跨Tab同步
 *
 * Requirements: 5.1~5.17
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcBalanceSubtotal,
  calcAmortizedCost,
  calcPeriodEndComponent,
  calcOneYearMaturity,
  calcBookValue,
} from '@/composables/useG4MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type G4InvestCategory = '企业债' | '国债' | '金融债' | '公司债' | '其他'

export type G4StageClassification = 'Stage1' | 'Stage2' | 'Stage3'

/** G4-2 明细行（44列分5区段） */
export interface BondDetailRow {
  id: string
  seq: number
  // ══ 基础信息(6列) ══
  investCategory: string
  investProject: string
  faceValue: number
  couponRate: number
  effectiveRate: number
  maturityDate: string

  // ══ 期初余额(10列) ══
  openingCost: number
  openingInterestAdj: number
  openingAccruedInterest: number
  openingSubtotal: number              // 公式
  openingImpairment: number
  openingAmortizedCost: number         // 公式
  openingOneYearDeduct: number
  openingAdjustment: number
  openingAdjusted: number
  openingRemark: string

  // ══ 本期变动(4列) ══
  periodCostChange: number
  periodInterestAdjChange: number
  periodAccruedInterestChange: number
  periodChangeSubtotal: number         // 公式

  // ══ 期末余额+减值(10列) ══
  closingCost: number                  // 公式
  closingInterestAdj: number           // 公式
  closingAccruedInterest: number       // 公式
  closingSubtotal: number              // 公式
  closingImpairment: number
  stageClassification: G4StageClassification
  creditCombineMethod: string
  creditCombineName: string
  impairmentAdjusted: number
  closingRemark: string

  // ══ 摊余成本+审定(8列) ══
  amortizedCost: number                // 公式
  oneYearBalance: number
  oneYearImpairment: number
  oneYearSubtotal: number              // 公式
  bookValue: number                    // 公式
  correspondenceStatus: string
  auditAdjustment: number
  indexRef: string
}

export interface G4DetailColumn {
  prop: keyof BondDetailRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'select' | 'stage'
}

export interface G4DetailSegment {
  key: string
  label: string
  columns: G4DetailColumn[]
}

/** 数据分类结果 */
export interface G4CategoryGroup {
  category: '一年内到期' | '超过一年'
  label: string
  rows: BondDetailRow[]
}

/** 投资种类小计 */
export interface G4InvestSubtotal {
  investCategory: string
  count: number
  totals: G4DetailTotals
}

export type G4DetailTotals = Record<string, number>

// ─── Constants ───────────────────────────────────────────────────────────────

const DATA_KEY = 'G4-2-rows'
const BALANCE_SHEET_DATE_KEY = 'G4-2-balance-sheet-date'
const MAX_ROWS = 500

export const G4_INVEST_CATEGORY_OPTIONS = [
  '企业债', '国债', '金融债', '公司债', '其他',
]

/** 5区段列配置（44列） */
export const G4_DETAIL_SEGMENTS: G4DetailSegment[] = [
  {
    key: 'basic',
    label: '基础信息',
    columns: [
      { prop: 'seq', label: '序号', width: 55, formula: true },
      { prop: 'investCategory', label: '投资种类', width: 110, type: 'select' },
      { prop: 'investProject', label: '投资项目', width: 160, type: 'text' },
      { prop: 'faceValue', label: '面值', width: 120, type: 'number' },
      { prop: 'couponRate', label: '票面利率', width: 110, type: 'number' },
      { prop: 'effectiveRate', label: '实际利率', width: 110, type: 'number' },
      { prop: 'maturityDate', label: '到期日', width: 130, type: 'date' },
    ],
  },
  {
    key: 'opening',
    label: '期初余额',
    columns: [
      { prop: 'openingCost', label: '期初成本', width: 120, type: 'number' },
      { prop: 'openingInterestAdj', label: '期初利息调整', width: 120, type: 'number' },
      { prop: 'openingAccruedInterest', label: '期初应计利息', width: 120, type: 'number' },
      { prop: 'openingSubtotal', label: '期初小计', width: 120, formula: true },
      { prop: 'openingImpairment', label: '期初减值准备', width: 120, type: 'number' },
      { prop: 'openingAmortizedCost', label: '期初摊余成本', width: 130, formula: true },
      { prop: 'openingOneYearDeduct', label: '减:一年内到期', width: 120, type: 'number' },
      { prop: 'openingAdjustment', label: '期初调整数', width: 110, type: 'number' },
      { prop: 'openingAdjusted', label: '期初审定数', width: 110, type: 'number' },
      { prop: 'openingRemark', label: '备注', width: 120, type: 'text' },
    ],
  },
  {
    key: 'period',
    label: '本期变动',
    columns: [
      { prop: 'periodCostChange', label: '本期成本变动', width: 120, type: 'number' },
      { prop: 'periodInterestAdjChange', label: '本期利息调整变动', width: 140, type: 'number' },
      { prop: 'periodAccruedInterestChange', label: '本期应计利息变动', width: 140, type: 'number' },
      { prop: 'periodChangeSubtotal', label: '本期变动小计', width: 120, formula: true },
    ],
  },
  {
    key: 'closing',
    label: '期末余额+减值',
    columns: [
      { prop: 'closingCost', label: '期末成本', width: 120, formula: true },
      { prop: 'closingInterestAdj', label: '期末利息调整', width: 120, formula: true },
      { prop: 'closingAccruedInterest', label: '期末应计利息', width: 120, formula: true },
      { prop: 'closingSubtotal', label: '期末小计', width: 120, formula: true },
      { prop: 'closingImpairment', label: '减值准备期末数', width: 130, type: 'number' },
      { prop: 'stageClassification', label: '阶段划分', width: 100, type: 'stage' },
      { prop: 'creditCombineMethod', label: '信用组合方式', width: 120, type: 'text' },
      { prop: 'creditCombineName', label: '信用组合名称', width: 120, type: 'text' },
      { prop: 'impairmentAdjusted', label: '减值准备审定', width: 120, type: 'number' },
      { prop: 'closingRemark', label: '备注', width: 120, type: 'text' },
    ],
  },
  {
    key: 'amortized',
    label: '摊余成本+审定',
    columns: [
      { prop: 'amortizedCost', label: '摊余成本', width: 120, formula: true },
      { prop: 'oneYearBalance', label: '一年内到期余额', width: 130, type: 'number' },
      { prop: 'oneYearImpairment', label: '一年内到期减值', width: 130, type: 'number' },
      { prop: 'oneYearSubtotal', label: '一年内到期小计', width: 130, formula: true },
      { prop: 'bookValue', label: '期末账面价值', width: 120, formula: true },
      { prop: 'correspondenceStatus', label: '发函情况', width: 110, type: 'text' },
      { prop: 'auditAdjustment', label: '审定调整', width: 110, type: 'number' },
      { prop: 'indexRef', label: '索引', width: 100, type: 'text' },
    ],
  },
]

/** 需要汇总的金额字段 */
const SUM_FIELDS = [
  'faceValue',
  'openingCost', 'openingInterestAdj', 'openingAccruedInterest', 'openingSubtotal',
  'openingImpairment', 'openingAmortizedCost', 'openingOneYearDeduct',
  'openingAdjustment', 'openingAdjusted',
  'periodCostChange', 'periodInterestAdjChange', 'periodAccruedInterestChange', 'periodChangeSubtotal',
  'closingCost', 'closingInterestAdj', 'closingAccruedInterest', 'closingSubtotal',
  'closingImpairment', 'impairmentAdjusted',
  'amortizedCost', 'oneYearBalance', 'oneYearImpairment', 'oneYearSubtotal',
  'bookValue', 'auditAdjustment',
] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `g4d-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyRow(id: string, seq: number): BondDetailRow {
  return {
    id,
    seq,
    investCategory: '',
    investProject: '',
    faceValue: 0,
    couponRate: 0,
    effectiveRate: 0,
    maturityDate: '',
    openingCost: 0,
    openingInterestAdj: 0,
    openingAccruedInterest: 0,
    openingSubtotal: 0,
    openingImpairment: 0,
    openingAmortizedCost: 0,
    openingOneYearDeduct: 0,
    openingAdjustment: 0,
    openingAdjusted: 0,
    openingRemark: '',
    periodCostChange: 0,
    periodInterestAdjChange: 0,
    periodAccruedInterestChange: 0,
    periodChangeSubtotal: 0,
    closingCost: 0,
    closingInterestAdj: 0,
    closingAccruedInterest: 0,
    closingSubtotal: 0,
    closingImpairment: 0,
    stageClassification: 'Stage1',
    creditCombineMethod: '',
    creditCombineName: '',
    impairmentAdjusted: 0,
    closingRemark: '',
    amortizedCost: 0,
    oneYearBalance: 0,
    oneYearImpairment: 0,
    oneYearSubtotal: 0,
    bookValue: 0,
    correspondenceStatus: '',
    auditAdjustment: 0,
    indexRef: '',
  }
}

/**
 * 公式链求解 — 区段间行同步核心，所有派生列在这里重算。
 * 空值/非数字输入通过 parseNum 视为0参与计算。
 */
function enrich(r: BondDetailRow): BondDetailRow {
  // 期初小计 = 成本 + 利息调整 + 应计利息
  const openingSubtotal = calcBalanceSubtotal(
    parseNum(r.openingCost),
    parseNum(r.openingInterestAdj),
    parseNum(r.openingAccruedInterest),
  )
  // 期初摊余成本 = 期初小计 - 期初减值准备
  const openingAmortizedCost = calcAmortizedCost(openingSubtotal, parseNum(r.openingImpairment))

  // 本期变动小计 = 三项变动之和
  const periodChangeSubtotal = calcBalanceSubtotal(
    parseNum(r.periodCostChange),
    parseNum(r.periodInterestAdjChange),
    parseNum(r.periodAccruedInterestChange),
  )

  // 期末分项 = 期初 + 变动
  const closingCost = calcPeriodEndComponent(parseNum(r.openingCost), parseNum(r.periodCostChange))
  const closingInterestAdj = calcPeriodEndComponent(parseNum(r.openingInterestAdj), parseNum(r.periodInterestAdjChange))
  const closingAccruedInterest = calcPeriodEndComponent(parseNum(r.openingAccruedInterest), parseNum(r.periodAccruedInterestChange))

  // 期末小计 = 期末成本 + 期末利息调整 + 期末应计利息
  const closingSubtotal = calcBalanceSubtotal(closingCost, closingInterestAdj, closingAccruedInterest)

  // 摊余成本 = 期末小计 - 减值准备期末数
  const amortizedCost = calcAmortizedCost(closingSubtotal, parseNum(r.closingImpairment))

  // 一年内到期小计 = 一年内到期余额 - 一年内到期减值
  const oneYearSubtotal = calcOneYearMaturity(parseNum(r.oneYearBalance), parseNum(r.oneYearImpairment))

  // 账面价值 = 摊余成本 - 一年内到期小计
  const bookValue = calcBookValue(amortizedCost, oneYearSubtotal)

  return {
    ...r,
    openingSubtotal,
    openingAmortizedCost,
    periodChangeSubtotal,
    closingCost,
    closingInterestAdj,
    closingAccruedInterest,
    closingSubtotal,
    amortizedCost,
    oneYearSubtotal,
    bookValue,
  }
}

/**
 * 按到期日与资产负债表日比较进行数据分类
 * - 到期日 ≤ 资产负债表日 + 1年 → "一年内到期"
 * - 到期日 > 资产负债表日 + 1年 → "超过一年"
 */
function classifyByMaturity(row: BondDetailRow, balanceSheetDate: string): '一年内到期' | '超过一年' {
  if (!row.maturityDate || !balanceSheetDate) return '超过一年'
  const maturity = new Date(row.maturityDate)
  const bsDate = new Date(balanceSheetDate)
  if (isNaN(maturity.getTime()) || isNaN(bsDate.getTime())) return '超过一年'
  // 资产负债表日 + 1年
  const oneYearLater = new Date(bsDate)
  oneYearLater.setFullYear(oneYearLater.getFullYear() + 1)
  return maturity <= oneYearLater ? '一年内到期' : '超过一年'
}

// ─── 到期日预警+逾期检测 ───────────────────────────────────────────────────

export type MaturityAlertLevel = 'overdue' | 'expiring_soon' | 'normal'

export interface MaturityAlert {
  rowId: string
  investProject: string
  maturityDate: string
  alertLevel: MaturityAlertLevel
  overdueDays: number       // >0 表示已逾期天数
  message: string
}

/**
 * 检测投资到期状态：
 * - 已逾期(maturityDate < balanceSheetDate且closingBalance>0) → 'overdue' 红色
 * - 即将到期(距资产负债表日30天内到期) → 'expiring_soon' 橙色
 * - 正常 → 'normal'
 */
function detectMaturityAlert(row: BondDetailRow, balanceSheetDate: string): MaturityAlert | null {
  if (!row.maturityDate || !balanceSheetDate) return null
  const maturity = new Date(row.maturityDate)
  const bsDate = new Date(balanceSheetDate)
  if (isNaN(maturity.getTime()) || isNaN(bsDate.getTime())) return null

  const diffMs = maturity.getTime() - bsDate.getTime()
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24))

  // 已逾期：到期日已过且仍有余额（closingBalance或amortizedCost>0）
  if (diffDays < 0 && parseNum((row as any).amortizedCost ?? (row as any).closingSubtotal) > 0) {
    return {
      rowId: row.id,
      investProject: row.investProject,
      maturityDate: row.maturityDate,
      alertLevel: 'overdue',
      overdueDays: Math.abs(diffDays),
      message: `"${row.investProject}"已逾期${Math.abs(diffDays)}天（到期日${row.maturityDate}），需评估减值及Stage升级`,
    }
  }

  // 即将到期：30天内到期
  if (diffDays >= 0 && diffDays <= 30) {
    return {
      rowId: row.id,
      investProject: row.investProject,
      maturityDate: row.maturityDate,
      alertLevel: 'expiring_soon',
      overdueDays: 0,
      message: `"${row.investProject}"将在${diffDays}天后到期（${row.maturityDate}），关注到期收回情况`,
    }
  }

  return null
}

function loadRows(map: Map<string, ChecklistResponse>): BondDetailRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow(generateId(), 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<BondDetailRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow(generateId(), 1))]
    return parsed.map((p, i) => enrich({
      ...emptyRow(p.id ?? generateId(), p.seq ?? i + 1),
      ...p,
    }))
  } catch {
    return [enrich(emptyRow(generateId(), 1))]
  }
}

function sumRowsBy(list: BondDetailRow[]): G4DetailTotals {
  const out: G4DetailTotals = {}
  for (const f of SUM_FIELDS) {
    out[f] = list.reduce((sum, r) => sum + parseNum((r as any)[f]), 0)
  }
  return out
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseG4MainDetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

export function useG4MainDetail(opts: UseG4MainDetailOptions) {
  const rows = ref<BondDetailRow[]>(loadRows(opts.allResponses.value))
  const balanceSheetDate = ref<string>(
    opts.allResponses.value.get(BALANCE_SHEET_DATE_KEY)?.conclusion ?? '',
  )

  /** 当前选中的区段Tab索引 */
  const segment = ref<string>(G4_DETAIL_SEGMENTS[0].key)

  /** 跨Tab同步的选中行索引 */
  const selectedRowIndex = ref<number>(-1)

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    balanceSheetDate.value = opts.allResponses.value.get(BALANCE_SHEET_DATE_KEY)?.conclusion ?? ''
  }

  // allResponses 异步加载完成后回填
  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  watch(
    () => opts.allResponses.value.get(BALANCE_SHEET_DATE_KEY)?.conclusion,
    (v) => {
      if (v) balanceSheetDate.value = v
    },
  )

  // ─── 数据分类（一年内到期 vs 超过一年） ─────────────────────────────────

  const categoryGroups = computed<G4CategoryGroup[]>(() => {
    const withinYear: BondDetailRow[] = []
    const overYear: BondDetailRow[] = []
    for (const r of rows.value) {
      if (classifyByMaturity(r, balanceSheetDate.value) === '一年内到期') {
        withinYear.push(r)
      } else {
        overYear.push(r)
      }
    }
    return [
      { category: '一年内到期', label: '一、购入的以摊余成本计量的一年内到期的债权投资', rows: withinYear },
      { category: '超过一年', label: '二、购入的以摊余成本计量的到期期限超过一年的债权投资', rows: overYear },
    ]
  })

  // ─── 分类小计（按投资种类） ──────────────────────────────────────────────

  const subtotalsByCategory = computed<G4InvestSubtotal[]>(() => {
    const byCategory = new Map<string, BondDetailRow[]>()
    for (const r of rows.value) {
      const key = r.investCategory || '其他'
      if (!byCategory.has(key)) byCategory.set(key, [])
      byCategory.get(key)!.push(r)
    }
    return Array.from(byCategory.entries()).map(([investCategory, list]) => ({
      investCategory,
      count: list.length,
      totals: sumRowsBy(list),
    }))
  })

  /** 总计 */
  const grandTotal = computed<G4DetailTotals>(() => sumRowsBy(rows.value))

  // ─── 持久化 ──────────────────────────────────────────────────────────────

  function persistAll() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
  }

  // ─── 单行更新（触发公式重算+持久化） ─────────────────────────────────────

  function updateRow(id: string, patch: Partial<BondDetailRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  // ─── 动态行增删 ──────────────────────────────────────────────────────────

  async function addRow() {
    if (opts.isReadonly.value) return
    if (rows.value.length >= MAX_ROWS) {
      ElMessageBox.alert(`明细行已达上限（${MAX_ROWS}行），无法继续新增。`, '提示')
      return
    }
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '投资项目名称不能为空',
      })
      const seq = rows.value.length + 1
      const newRow = enrich({ ...emptyRow(generateId(), seq), investProject: value })
      rows.value = [...rows.value, newRow]
      selectedRowIndex.value = rows.value.length - 1
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    const idx = rows.value.findIndex((r) => r.id === id)
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    // 调整选中行索引
    if (selectedRowIndex.value >= rows.value.length) {
      selectedRowIndex.value = rows.value.length - 1
    } else if (idx <= selectedRowIndex.value && selectedRowIndex.value > 0) {
      selectedRowIndex.value--
    }
    persistAll()
  }

  // ─── 资产负债表日设置 ─────────────────────────────────────────────────────

  function setBalanceSheetDate(date: string) {
    if (opts.isReadonly.value) return
    balanceSheetDate.value = date
    opts.debouncedSave(BALANCE_SHEET_DATE_KEY, { conclusion: date })
  }

  // ─── 当前区段的列定义（computed based on active tab） ────────────────────

  const activeColumns = computed<G4DetailColumn[]>(() => {
    const seg = G4_DETAIL_SEGMENTS.find((s) => s.key === segment.value)
    return seg?.columns ?? G4_DETAIL_SEGMENTS[0].columns
  })

  // ─── 到期日预警（computed） ─────────────────────────────────────────────

  const maturityAlerts = computed<MaturityAlert[]>(() => {
    if (!balanceSheetDate.value) return []
    const alerts: MaturityAlert[] = []
    for (const row of rows.value) {
      const alert = detectMaturityAlert(row, balanceSheetDate.value)
      if (alert) alerts.push(alert)
    }
    return alerts
  })

  /** 是否存在逾期投资 */
  const hasOverdueItems = computed<boolean>(() =>
    maturityAlerts.value.some((a) => a.alertLevel === 'overdue'),
  )

  /** 是否存在即将到期投资 */
  const hasExpiringSoonItems = computed<boolean>(() =>
    maturityAlerts.value.some((a) => a.alertLevel === 'expiring_soon'),
  )

  return {
    // 区段定义
    segments: G4_DETAIL_SEGMENTS,
    segment,
    activeColumns,
    // 数据
    rows,
    balanceSheetDate,
    // 行同步
    selectedRowIndex,
    // 分类
    categoryGroups,
    // 到期日预警
    maturityAlerts,
    hasOverdueItems,
    hasExpiringSoonItems,
    // 汇总
    subtotalsByCategory,
    grandTotal,
    // 操作
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    setBalanceSheetDate,
  }
}

export default useG4MainDetail
