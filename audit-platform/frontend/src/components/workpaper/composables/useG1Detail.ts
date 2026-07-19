/**
 * useG1Detail — G1-2 交易性金融资产明细表
 *
 * 对齐 Excel 明细表编制逻辑：
 * - 会计三分类 × 投资品种层级
 * - 成本 / 累计公允变动双桶滚动：期初 → 调整 → 审定 → 本期变动 → 期末 → 调整 → 审定 → 列报
 * - 一年以上重分类、变现限制 / 质押披露标志
 * - 编制闸门（入表条件 + 舞弊风险）与勾稽状态
 *
 * 区段：准入基础 / 期初滚动 / 本期变动 / 期末审定 / 披露损益
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, getCurrentInstance, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcClosingQuantity,
  calcFairValue,
  calcFairValueChange,
  calcRealizedGain,
  calcEndAmount,
  calcAdjustedAmount,
  calcSubtotal,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type G1InvestType = 'stock' | 'fund' | 'bond' | 'derivative' | 'other'

/** 会计分类（对齐 Excel 行层级） */
export type G1AcctClass = 'trading' | 'classified_fvpl' | 'designated_fvpl'

/** G1-2 明细行 */
export interface TradingDetailRow {
  id: string
  seq: number
  // 准入 / 基础
  securityName: string
  securityCode: string
  acctClass: G1AcctClass
  investType: G1InvestType
  market: string
  acquisitionDate: string
  initialCost: number
  originalCurrency: string
  exchangeRate: number
  // 持有数量（证券类辅助）
  openingQuantity: number
  boughtQuantity: number
  soldQuantity: number
  closingQuantity: number
  // 期初双桶
  openingCost: number
  openingCumulativeFv: number
  openingFairValue: number // 公式 = 成本 + 累计 FV
  openingCostAdj: number
  openingFvAdj: number
  auditedOpeningCost: number
  auditedOpeningCumulativeFv: number
  auditedOpeningFvTotal: number
  openingLtDeduction: number
  openingReported: number
  // 本期变动
  addedCost: number
  reducedCost: number
  periodFvChange: number
  dividendIncome: number
  // 公允价值（市价辅助）
  unitFairValue: number
  closingFairValue: number
  fairValueSource: '1' | '2' | '3'
  fairValueChange: number
  cumulativeFVChange: number // 期末累计公允变动（公式）
  quoteDate: string
  // 期末双桶 + 审定
  closingCost: number
  closingCostAdj: number
  closingFvAdj: number
  auditedClosingCost: number
  auditedClosingCumulativeFv: number
  auditedClosingFvTotal: number
  closingLtDeduction: number
  closingReported: number
  // 损益
  disposalProceeds: number
  disposalCost: number
  realizedGain: number
  totalIncome: number
  fvChangeInPL: number
  remark: string
  // 兼容旧审定列 + 勾稽
  unadjusted: number
  aje: number
  rje: number
  adjusted: number
  variance: number
  rollForwardDiff: number // 账面勾稽差：期末账面FV − (期初审定FV + 本期成本净增 + 本期FV变动)
  indexRef: string
  // 披露标志
  realizationRestricted: boolean
  pledged: boolean
}

export interface G1DetailColumn {
  prop: keyof TradingDetailRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'invest' | 'acct' | 'level' | 'flag'
}

export interface G1DetailSegment {
  key: string
  label: string
  hint?: string
  columns: G1DetailColumn[]
}

/** 编制闸门（非打印指引 → 可勾选步骤） */
export interface G1DetailGates {
  inclusionReviewed: boolean
  fxNoted: boolean
  fraudRiskAssessed: boolean
  fraudRiskFlag: boolean
  fraudResponse: string
}

export const G1_INVEST_TYPE_OPTIONS: { value: G1InvestType; label: string }[] = [
  { value: 'stock', label: '股票/权益工具' },
  { value: 'fund', label: '基金' },
  { value: 'bond', label: '债券/债务工具' },
  { value: 'derivative', label: '衍生工具' },
  { value: 'other', label: '其他' },
]

export const G1_ACCT_CLASS_OPTIONS: { value: G1AcctClass; label: string }[] = [
  { value: 'trading', label: '交易性金融资产' },
  { value: 'classified_fvpl', label: '划分为以公允价值计量且其变动计入当期损益' },
  { value: 'designated_fvpl', label: '指定为以公允价值计量且其变动计入当期损益' },
]

const INVEST_LABEL: Record<string, string> = Object.fromEntries(
  G1_INVEST_TYPE_OPTIONS.map((o) => [o.value, o.label]),
)
const ACCT_LABEL: Record<string, string> = Object.fromEntries(
  G1_ACCT_CLASS_OPTIONS.map((o) => [o.value, o.label]),
)

/** 区段对齐 Excel：准入 → 期初 → 本期 → 期末 → 披露损益 */
export const G1_DETAIL_SEGMENTS: G1DetailSegment[] = [
  {
    key: 'basic',
    label: '①准入基础',
    hint: '先定会计分类与投资品种，外币填原币与汇率',
    columns: [
      { prop: 'seq', label: '序号', width: 56, formula: true },
      { prop: 'securityName', label: '投资项目', width: 140, type: 'text' },
      { prop: 'securityCode', label: '代码', width: 100, type: 'text' },
      { prop: 'acctClass', label: '会计分类', width: 160, type: 'acct' },
      { prop: 'investType', label: '投资品种', width: 130, type: 'invest' },
      { prop: 'market', label: '交易市场', width: 100, type: 'text' },
      { prop: 'acquisitionDate', label: '取得日期', width: 120, type: 'date' },
      { prop: 'initialCost', label: '初始成本', width: 110, type: 'number' },
      { prop: 'originalCurrency', label: '原币', width: 80, type: 'text' },
      { prop: 'exchangeRate', label: '汇率', width: 90, type: 'number' },
    ],
  },
  {
    key: 'opening',
    label: '②期初滚动',
    hint: '成本与累计公允变动分列；调整后得期初审定，扣一年以上得报表数',
    columns: [
      { prop: 'openingCost', label: '期初成本', width: 110, type: 'number' },
      { prop: 'openingCumulativeFv', label: '期初累计公允变动', width: 130, type: 'number' },
      { prop: 'openingFairValue', label: '期初公允价值', width: 120, type: 'number', formula: true },
      { prop: 'openingCostAdj', label: '期初成本调整', width: 120, type: 'number' },
      { prop: 'openingFvAdj', label: '期初公允调整', width: 120, type: 'number' },
      { prop: 'auditedOpeningCost', label: '期初审定成本', width: 120, type: 'number', formula: true },
      { prop: 'auditedOpeningCumulativeFv', label: '期初审定累计FV', width: 130, type: 'number', formula: true },
      { prop: 'auditedOpeningFvTotal', label: '期初审定公允价值', width: 130, type: 'number', formula: true },
      { prop: 'openingLtDeduction', label: '一年以上扣减', width: 120, type: 'number' },
      { prop: 'openingReported', label: '期初报表数', width: 120, type: 'number', formula: true },
    ],
  },
  {
    key: 'movement',
    label: '③本期变动',
    hint: '成本增减、本期公允变动、利息/股利；数量供证券类验算',
    columns: [
      { prop: 'openingQuantity', label: '期初数量', width: 100, type: 'number' },
      { prop: 'boughtQuantity', label: '本期买入', width: 100, type: 'number' },
      { prop: 'soldQuantity', label: '本期卖出', width: 100, type: 'number' },
      { prop: 'closingQuantity', label: '期末数量', width: 100, type: 'number', formula: true },
      { prop: 'addedCost', label: '本期增加成本', width: 120, type: 'number' },
      { prop: 'reducedCost', label: '本期减少成本', width: 120, type: 'number' },
      { prop: 'periodFvChange', label: '本期公允变动', width: 120, type: 'number' },
      { prop: 'dividendIncome', label: '利息/股利', width: 110, type: 'number' },
      { prop: 'unitFairValue', label: '期末单位公允', width: 120, type: 'number' },
      { prop: 'quoteDate', label: '报价日期', width: 120, type: 'date' },
      { prop: 'fairValueSource', label: '公允层级', width: 100, type: 'level' },
    ],
  },
  {
    key: 'closing',
    label: '④期末审定',
    hint: '期末账面由期初审定+本期变动自动滚动；再调至期末审定与报表数',
    columns: [
      { prop: 'closingCost', label: '期末成本', width: 110, type: 'number', formula: true },
      { prop: 'cumulativeFVChange', label: '期末累计公允变动', width: 130, type: 'number', formula: true },
      { prop: 'closingFairValue', label: '期末公允价值', width: 120, type: 'number', formula: true },
      { prop: 'fairValueChange', label: '公允变动(验算)', width: 120, type: 'number', formula: true },
      { prop: 'closingCostAdj', label: '期末成本调整', width: 120, type: 'number' },
      { prop: 'closingFvAdj', label: '期末公允调整', width: 120, type: 'number' },
      { prop: 'aje', label: 'AJE', width: 90, type: 'number' },
      { prop: 'rje', label: 'RJE', width: 90, type: 'number' },
      { prop: 'auditedClosingCost', label: '期末审定成本', width: 120, type: 'number', formula: true },
      { prop: 'auditedClosingCumulativeFv', label: '期末审定累计FV', width: 130, type: 'number', formula: true },
      { prop: 'auditedClosingFvTotal', label: '期末审定公允价值', width: 130, type: 'number', formula: true },
      { prop: 'closingLtDeduction', label: '一年以上扣减', width: 120, type: 'number' },
      { prop: 'closingReported', label: '期末报表数', width: 120, type: 'number', formula: true },
      { prop: 'rollForwardDiff', label: '滚动勾稽差', width: 110, type: 'number', formula: true },
      { prop: 'variance', label: '审定vs市价差', width: 120, type: 'number', formula: true },
      { prop: 'indexRef', label: '索引', width: 90, type: 'text' },
    ],
  },
  {
    key: 'disclosure',
    label: '⑤披露损益',
    hint: '变现限制/质押；处置与投资收益（已到期应计利息进应收利息，不进本表）',
    columns: [
      { prop: 'realizationRestricted', label: '变现受限', width: 90, type: 'flag' },
      { prop: 'pledged', label: '是否质押', width: 90, type: 'flag' },
      { prop: 'disposalProceeds', label: '处置收入', width: 110, type: 'number' },
      { prop: 'disposalCost', label: '处置成本', width: 110, type: 'number' },
      { prop: 'realizedGain', label: '已实现损益', width: 110, type: 'number', formula: true },
      { prop: 'totalIncome', label: '投资收益合计', width: 120, type: 'number', formula: true },
      { prop: 'fvChangeInPL', label: '公允变动损益', width: 120, type: 'number' },
      { prop: 'adjusted', label: '审定余额(勾稽)', width: 120, type: 'number', formula: true },
      { prop: 'unadjusted', label: '未审余额', width: 110, type: 'number', formula: true },
      { prop: 'remark', label: '备注', width: 140, type: 'text' },
    ],
  },
]

const DATA_KEY = 'G1-2-rows'
const CONCLUSION_KEY = 'G1-2-conclusion'
const GATES_KEY = 'G1-2-gates'

export const DEFAULT_G1_GATES: G1DetailGates = {
  inclusionReviewed: false,
  fxNoted: false,
  fraudRiskAssessed: false,
  fraudRiskFlag: false,
  fraudResponse: '',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function emptyRow(id: string, seq: number): TradingDetailRow {
  return {
    id,
    seq,
    securityName: '',
    securityCode: '',
    acctClass: 'trading',
    investType: 'stock',
    market: '',
    acquisitionDate: '',
    initialCost: 0,
    originalCurrency: '',
    exchangeRate: 0,
    openingQuantity: 0,
    boughtQuantity: 0,
    soldQuantity: 0,
    closingQuantity: 0,
    openingCost: 0,
    openingCumulativeFv: 0,
    openingFairValue: 0,
    openingCostAdj: 0,
    openingFvAdj: 0,
    auditedOpeningCost: 0,
    auditedOpeningCumulativeFv: 0,
    auditedOpeningFvTotal: 0,
    openingLtDeduction: 0,
    openingReported: 0,
    addedCost: 0,
    reducedCost: 0,
    periodFvChange: 0,
    dividendIncome: 0,
    unitFairValue: 0,
    closingFairValue: 0,
    fairValueSource: '1',
    fairValueChange: 0,
    cumulativeFVChange: 0,
    quoteDate: '',
    closingCost: 0,
    closingCostAdj: 0,
    closingFvAdj: 0,
    auditedClosingCost: 0,
    auditedClosingCumulativeFv: 0,
    auditedClosingFvTotal: 0,
    closingLtDeduction: 0,
    closingReported: 0,
    disposalProceeds: 0,
    disposalCost: 0,
    realizedGain: 0,
    totalIncome: 0,
    fvChangeInPL: 0,
    remark: '',
    unadjusted: 0,
    aje: 0,
    rje: 0,
    adjusted: 0,
    variance: 0,
    rollForwardDiff: 0,
    indexRef: '',
    realizationRestricted: false,
    pledged: false,
  }
}

/** 旧数据迁移：补齐会计分类与期初累计 FV */
function migratePartial(p: Partial<TradingDetailRow>): Partial<TradingDetailRow> {
  const next = { ...p }
  if (!next.acctClass) next.acctClass = 'trading'
  const openingCost = parseNum(next.openingCost)
  const openingFv = parseNum(next.openingFairValue)
  if (
    (next.openingCumulativeFv === undefined || next.openingCumulativeFv === null) &&
    openingFv !== 0
  ) {
    next.openingCumulativeFv = openingFv - openingCost
  }
  // 旧版仅有 fairValueChange、无 periodFvChange 时带入
  if (
    (next.periodFvChange === undefined || next.periodFvChange === null) &&
    next.fairValueChange != null
  ) {
    next.periodFvChange = parseNum(next.fairValueChange)
  }
  return next
}

/**
 * 公式链（Excel 双桶滚动）
 * 期末账面成本 = 期初审定成本 + 本期增加 − 本期减少
 * 期末累计 FV = 期初审定累计 FV + 本期公允变动
 * 若填写单位公允，期末公允价值优先用市价验算，否则用账面双桶合计
 */
export function enrichDetailRow(r: TradingDetailRow): TradingDetailRow {
  const openingCost = parseNum(r.openingCost)
  let openingCumulativeFv = parseNum(r.openingCumulativeFv)
  // 仅填了期初公允价值时反推累计 FV
  if (openingCumulativeFv === 0 && parseNum(r.openingFairValue) !== 0 && openingCost !== parseNum(r.openingFairValue)) {
    openingCumulativeFv = parseNum(r.openingFairValue) - openingCost
  }
  const openingFairValue = openingCost + openingCumulativeFv

  const auditedOpeningCost = openingCost + parseNum(r.openingCostAdj)
  const auditedOpeningCumulativeFv = openingCumulativeFv + parseNum(r.openingFvAdj)
  const auditedOpeningFvTotal = auditedOpeningCost + auditedOpeningCumulativeFv
  const openingReported = auditedOpeningFvTotal - parseNum(r.openingLtDeduction)

  const closingQuantity = calcClosingQuantity(
    parseNum(r.openingQuantity),
    parseNum(r.boughtQuantity),
    parseNum(r.soldQuantity),
  )
  const closingCost = calcEndAmount(auditedOpeningCost, parseNum(r.addedCost), parseNum(r.reducedCost))

  const unitFv = parseNum(r.unitFairValue)
  const marketClosingFv = unitFv !== 0 ? calcFairValue(closingQuantity, unitFv) : 0

  // 本期公允变动：优先用户录入；若为 0 且有市价，则用市价变动
  let periodFvChange = parseNum(r.periodFvChange)
  if (periodFvChange === 0 && marketClosingFv !== 0) {
    periodFvChange = calcFairValueChange(marketClosingFv, auditedOpeningFvTotal)
  }

  const cumulativeFVChange = auditedOpeningCumulativeFv + periodFvChange
  const bookClosingFv = closingCost + cumulativeFVChange
  const closingFairValue = marketClosingFv !== 0 ? marketClosingFv : bookClosingFv
  const fairValueChange = calcFairValueChange(closingFairValue, auditedOpeningFvTotal)

  const auditedClosingCost = closingCost + parseNum(r.closingCostAdj)
  const auditedClosingCumulativeFv = cumulativeFVChange + parseNum(r.closingFvAdj)
  // AJE/RJE 落在公允价值合计（兼容旧列）
  const auditedClosingFvTotal = calcAdjustedAmount(
    auditedClosingCost + auditedClosingCumulativeFv,
    parseNum(r.aje),
    parseNum(r.rje),
  )
  const closingReported = auditedClosingFvTotal - parseNum(r.closingLtDeduction)

  const realizedGain = calcRealizedGain(parseNum(r.disposalProceeds), parseNum(r.disposalCost))
  const totalIncome = realizedGain + parseNum(r.dividendIncome)

  // 有市价时：账面双桶合计 vs 市价；无市价时滚动由公式恒等勾平
  const rollForwardDiff = marketClosingFv !== 0 ? bookClosingFv - marketClosingFv : 0

  const unadjusted = closingFairValue
  const adjusted = auditedClosingFvTotal
  // variance = 审定 − 期末公允价值（市价或账面）
  const variance = auditedClosingFvTotal - closingFairValue

  return {
    ...r,
    openingCumulativeFv,
    openingFairValue,
    auditedOpeningCost,
    auditedOpeningCumulativeFv,
    auditedOpeningFvTotal,
    openingReported,
    closingQuantity,
    periodFvChange,
    closingCost,
    cumulativeFVChange,
    closingFairValue,
    fairValueChange,
    auditedClosingCost,
    auditedClosingCumulativeFv,
    auditedClosingFvTotal,
    closingReported,
    realizedGain,
    totalIncome,
    unadjusted,
    adjusted,
    variance,
    rollForwardDiff,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): TradingDetailRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrichDetailRow(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<TradingDetailRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrichDetailRow(emptyRow('1', 1))]
    return parsed.map((p, i) => {
      const migrated = migratePartial(p)
      return enrichDetailRow({
        ...emptyRow(migrated.id ?? String(i + 1), migrated.seq ?? i + 1),
        ...migrated,
      })
    })
  } catch {
    return [enrichDetailRow(emptyRow('1', 1))]
  }
}

function loadGates(map: Map<string, ChecklistResponse>): G1DetailGates {
  const raw = map.get(GATES_KEY)?.conclusion
  if (!raw) return { ...DEFAULT_G1_GATES }
  try {
    return { ...DEFAULT_G1_GATES, ...(JSON.parse(raw) as Partial<G1DetailGates>) }
  } catch {
    return { ...DEFAULT_G1_GATES }
  }
}

// ─── 汇总 ────────────────────────────────────────────────────────────────────

const SUM_FIELDS = [
  'initialCost',
  'openingQuantity',
  'boughtQuantity',
  'soldQuantity',
  'closingQuantity',
  'openingCost',
  'openingCumulativeFv',
  'openingFairValue',
  'openingCostAdj',
  'openingFvAdj',
  'auditedOpeningCost',
  'auditedOpeningCumulativeFv',
  'auditedOpeningFvTotal',
  'openingLtDeduction',
  'openingReported',
  'addedCost',
  'reducedCost',
  'periodFvChange',
  'closingFairValue',
  'fairValueChange',
  'cumulativeFVChange',
  'disposalProceeds',
  'disposalCost',
  'realizedGain',
  'dividendIncome',
  'totalIncome',
  'fvChangeInPL',
  'closingCost',
  'closingCostAdj',
  'closingFvAdj',
  'auditedClosingCost',
  'auditedClosingCumulativeFv',
  'auditedClosingFvTotal',
  'closingLtDeduction',
  'closingReported',
  'unadjusted',
  'aje',
  'rje',
  'adjusted',
  'variance',
  'rollForwardDiff',
] as const

export type G1DetailTotals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: TradingDetailRow[]): G1DetailTotals {
  const out = {} as G1DetailTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

export interface G1DetailSubtotal {
  key: string
  label: string
  count: number
  totals: G1DetailTotals
}

export interface G1BalanceStatus {
  ok: boolean
  rollForwardAbs: number
  pledgedCount: number
  restrictedCount: number
  message: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG1Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<TradingDetailRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')
  const gates = ref<G1DetailGates>(loadGates(opts.allResponses.value))
  const segment = ref<string>(G1_DETAIL_SEGMENTS[0].key)

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
    gates.value = loadGates(opts.allResponses.value)
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )
  watch(
    () => opts.allResponses.value.get(GATES_KEY)?.conclusion,
    (raw) => {
      if (raw) gates.value = loadGates(opts.allResponses.value)
    },
  )

  const subtotalsByAcct = computed<G1DetailSubtotal[]>(() => {
    const by = new Map<string, TradingDetailRow[]>()
    for (const r of rows.value) {
      const key = r.acctClass || 'trading'
      if (!by.has(key)) by.set(key, [])
      by.get(key)!.push(r)
    }
    return Array.from(by.entries()).map(([key, list]) => ({
      key,
      label: ACCT_LABEL[key] ?? key,
      count: list.length,
      totals: sumRows(list),
    }))
  })

  const subtotalsByType = computed<G1DetailSubtotal[]>(() => {
    const byType = new Map<string, TradingDetailRow[]>()
    for (const r of rows.value) {
      const key = r.investType || 'other'
      if (!byType.has(key)) byType.set(key, [])
      byType.get(key)!.push(r)
    }
    return Array.from(byType.entries()).map(([investType, list]) => ({
      key: investType,
      label: INVEST_LABEL[investType] ?? '其他',
      count: list.length,
      totals: sumRows(list),
    }))
  })

  const grandTotal = computed<G1DetailTotals>(() => sumRows(rows.value))

  const balanceStatus = computed<G1BalanceStatus>(() => {
    const rollForwardAbs = Math.abs(grandTotal.value.rollForwardDiff)
    const pledgedCount = rows.value.filter((r) => r.pledged).length
    const restrictedCount = rows.value.filter((r) => r.realizationRestricted).length
    const hasMarket = rows.value.some((r) => parseNum(r.unitFairValue) !== 0)
    const ok = rollForwardAbs < 0.01
    return {
      ok,
      rollForwardAbs,
      pledgedCount,
      restrictedCount,
      message: ok
        ? hasMarket
          ? '双桶账面与市价一致；期末由期初审定 + 本期变动自动滚动'
          : '期末账面 = 期初审定 + 本期变动（双桶自动滚动）'
        : `账面双桶与市价差 ${rollForwardAbs.toLocaleString()}，请核对单位公允或本期公允变动`,
    }
  })

  const gatesReady = computed(
    () =>
      gates.value.inclusionReviewed &&
      gates.value.fraudRiskAssessed &&
      (!gates.value.fraudRiskFlag || !!gates.value.fraudResponse.trim()),
  )

  /** 与 G1-9 分类结论软核对：明细为 FVTPL 类但分类表结论非 FVTPL 时告警 */
  const classificationWarnings = computed(() => {
    const raw = opts.allResponses.value.get('G1-9-rows')?.conclusion
      || opts.allResponses.value.get('G1-9-rows')?.remark
    if (!raw) return [] as string[]
    let classRows: Array<{ securityName?: string; finalClassification?: string }> = []
    try {
      const parsed = JSON.parse(raw)
      classRows = Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
    const byName = new Map(
      classRows
        .filter((r) => r.securityName)
        .map((r) => [(r.securityName || '').trim().toLowerCase(), r.finalClassification || '']),
    )
    const warnings: string[] = []
    for (const r of rows.value) {
      if (!r.securityName) continue
      const fc = byName.get(r.securityName.trim().toLowerCase())
      if (!fc) continue
      const isFvplDetail = true // G1-2 本表均为 FVTPL 口径
      if (isFvplDetail && fc && fc !== 'FVTPL' && fc !== 'fvtpl') {
        warnings.push(`${r.securityName}：G1-9 结论为 ${fc}，与明细 FVTPL 口径不一致`)
      }
    }
    return warnings
  })

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  function persistGates() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(GATES_KEY, { conclusion: JSON.stringify(gates.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function onDetailUpdated() {
    loadAll()
  }

  if (getCurrentInstance()) {
    onMounted(() => {
      window.addEventListener('g1:detail-updated', onDetailUpdated)
    })
    onBeforeUnmount(() => {
      window.removeEventListener('g1:detail-updated', onDetailUpdated)
    })
  }

  function updateGates(patch: Partial<G1DetailGates>) {
    if (opts.isReadonly.value) return
    gates.value = { ...gates.value, ...patch }
    persistGates()
  }

  function updateRow(id: string, patch: Partial<TradingDetailRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichDetailRow({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrichDetailRow({ ...emptyRow(`row-${Date.now()}`, seq), securityName: value }),
      ]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  return {
    segments: G1_DETAIL_SEGMENTS,
    segment,
    rows,
    auditConclusion,
    gates,
    gatesReady,
    classificationWarnings,
    subtotalsByType,
    subtotalsByAcct,
    grandTotal,
    balanceStatus,
    loadAll,
    persistAll,
    updateGates,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1Detail
