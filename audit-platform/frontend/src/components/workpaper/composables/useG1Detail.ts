/**
 * useG1Detail — G1-2 交易性金融资产明细表（35列 → 5区段Tab）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 4.2 / 6.2
 *
 * 职责：
 * - 35列拆为5区段（基础信息/持有明细/公允价值/损益/审定调整），区段间行同步
 * - 公式链：
 *     期末持有数量 = 期初 + 买入 - 卖出                     (calcClosingQuantity)
 *     期末公允价值 = 期末持有数量 × 期末单位公允值           (calcFairValue)
 *     公允价值变动 = 期末公允价值 - 期初公允价值             (calcFairValueChange)
 *     已实现损益   = 处置收入 - 处置成本                     (calcRealizedGain)
 *     投资收益合计 = 已实现损益 + 利息/股利收入
 *     期末成本     = 期初成本 + 本期增加成本 - 本期减少成本   (calcEndAmount)
 *     审定余额     = 未审 + AJE + RJE                        (calcAdjustedAmount)
 *     差异         = 审定余额 - 期末公允价值
 * - 分类小计（按投资类型）+ 总计
 * - 动态行增删（ElMessageBox.prompt 命名）+ loadAll/persistAll
 *
 * Requirements: 5.1~5.11
 */
import { ref, computed, watch, type Ref } from 'vue'
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

/** G1-2 明细行（35列分5区段） */
export interface TradingDetailRow {
  id: string
  seq: number
  // 基础信息(7列)
  securityName: string
  securityCode: string
  investType: G1InvestType
  market: string
  acquisitionDate: string
  initialCost: number
  // 持有明细(7列)
  openingQuantity: number
  boughtQuantity: number
  soldQuantity: number
  closingQuantity: number // 公式 = 期初 + 买入 - 卖出
  openingCost: number
  addedCost: number
  reducedCost: number
  // 公允价值(7列)
  unitFairValue: number
  closingFairValue: number // 公式 = 期末数量 × 单位公允
  fairValueSource: '1' | '2' | '3'
  openingFairValue: number
  fairValueChange: number // 公式 = 期末公允 - 期初公允
  cumulativeFVChange: number
  quoteDate: string
  // 损益(7列)
  disposalProceeds: number
  disposalCost: number
  realizedGain: number // 公式 = 处置收入 - 处置成本
  dividendIncome: number
  totalIncome: number // 公式 = 已实现损益 + 股利
  fvChangeInPL: number
  remark: string
  // 审定调整(7列)
  closingCost: number // 公式 = 期初成本 + 增加 - 减少
  unadjusted: number
  aje: number
  rje: number
  adjusted: number // 公式 = 未审 + AJE + RJE
  variance: number // 公式 = 审定 - 期末公允价值
  indexRef: string
}

export interface G1DetailColumn {
  prop: keyof TradingDetailRow
  label: string
  width: number
  formula?: boolean
  /** 单元格控件类型；缺省为文本输入 */
  type?: 'text' | 'number' | 'date' | 'invest' | 'level'
}

export interface G1DetailSegment {
  key: string
  label: string
  columns: G1DetailColumn[]
}

/** 投资类型下拉 */
export const G1_INVEST_TYPE_OPTIONS: { value: G1InvestType; label: string }[] = [
  { value: 'stock', label: '股票' },
  { value: 'fund', label: '基金' },
  { value: 'bond', label: '债券' },
  { value: 'derivative', label: '衍生工具' },
  { value: 'other', label: '其他' },
]

const INVEST_LABEL: Record<string, string> = Object.fromEntries(
  G1_INVEST_TYPE_OPTIONS.map((o) => [o.value, o.label]),
)

/** 5区段列配置 */
export const G1_DETAIL_SEGMENTS: G1DetailSegment[] = [
  {
    key: 'basic',
    label: '基础信息',
    columns: [
      { prop: 'seq', label: '序号', width: 60, formula: true },
      { prop: 'securityName', label: '证券名称', width: 150, type: 'text' },
      { prop: 'securityCode', label: '证券代码', width: 110, type: 'text' },
      { prop: 'investType', label: '投资类型', width: 120, type: 'invest' },
      { prop: 'market', label: '交易市场', width: 110, type: 'text' },
      { prop: 'acquisitionDate', label: '初始取得日期', width: 140, type: 'date' },
      { prop: 'initialCost', label: '初始取得成本', width: 130, type: 'number' },
    ],
  },
  {
    key: 'holding',
    label: '持有明细',
    columns: [
      { prop: 'openingQuantity', label: '期初持有数量', width: 120, type: 'number' },
      { prop: 'boughtQuantity', label: '本期买入数量', width: 120, type: 'number' },
      { prop: 'soldQuantity', label: '本期卖出数量', width: 120, type: 'number' },
      { prop: 'closingQuantity', label: '期末持有数量', width: 120, type: 'number', formula: true },
      { prop: 'openingCost', label: '期初成本', width: 120, type: 'number' },
      { prop: 'addedCost', label: '本期增加成本', width: 120, type: 'number' },
      { prop: 'reducedCost', label: '本期减少成本', width: 120, type: 'number' },
    ],
  },
  {
    key: 'fairvalue',
    label: '公允价值',
    columns: [
      { prop: 'unitFairValue', label: '期末单位公允值', width: 130, type: 'number' },
      { prop: 'closingFairValue', label: '期末公允价值', width: 130, type: 'number', formula: true },
      { prop: 'fairValueSource', label: '公允价值来源', width: 120, type: 'level' },
      { prop: 'openingFairValue', label: '期初公允价值', width: 130, type: 'number' },
      { prop: 'fairValueChange', label: '公允价值变动', width: 130, type: 'number', formula: true },
      { prop: 'cumulativeFVChange', label: '累计公允变动', width: 130, type: 'number' },
      { prop: 'quoteDate', label: '报价日期', width: 130, type: 'date' },
    ],
  },
  {
    key: 'profit',
    label: '损益',
    columns: [
      { prop: 'disposalProceeds', label: '本期处置收入', width: 120, type: 'number' },
      { prop: 'disposalCost', label: '处置成本', width: 120, type: 'number' },
      { prop: 'realizedGain', label: '已实现损益', width: 120, type: 'number', formula: true },
      { prop: 'dividendIncome', label: '利息/股利收入', width: 130, type: 'number' },
      { prop: 'totalIncome', label: '投资收益合计', width: 130, type: 'number', formula: true },
      { prop: 'fvChangeInPL', label: '公允变动损益', width: 130, type: 'number' },
      { prop: 'remark', label: '备注', width: 140, type: 'text' },
    ],
  },
  {
    key: 'adjust',
    label: '审定调整',
    columns: [
      { prop: 'closingCost', label: '期末成本', width: 120, type: 'number', formula: true },
      { prop: 'unadjusted', label: '未审余额', width: 120, type: 'number' },
      { prop: 'aje', label: 'AJE', width: 110, type: 'number' },
      { prop: 'rje', label: 'RJE', width: 110, type: 'number' },
      { prop: 'adjusted', label: '审定余额', width: 120, type: 'number', formula: true },
      { prop: 'variance', label: '差异', width: 110, type: 'number', formula: true },
      { prop: 'indexRef', label: '索引', width: 100, type: 'text' },
    ],
  },
]

const DATA_KEY = 'G1-2-rows'
const CONCLUSION_KEY = 'G1-2-conclusion'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function emptyRow(id: string, seq: number): TradingDetailRow {
  return {
    id,
    seq,
    securityName: '',
    securityCode: '',
    investType: 'stock',
    market: '',
    acquisitionDate: '',
    initialCost: 0,
    openingQuantity: 0,
    boughtQuantity: 0,
    soldQuantity: 0,
    closingQuantity: 0,
    openingCost: 0,
    addedCost: 0,
    reducedCost: 0,
    unitFairValue: 0,
    closingFairValue: 0,
    fairValueSource: '1',
    openingFairValue: 0,
    fairValueChange: 0,
    cumulativeFVChange: 0,
    quoteDate: '',
    disposalProceeds: 0,
    disposalCost: 0,
    realizedGain: 0,
    dividendIncome: 0,
    totalIncome: 0,
    fvChangeInPL: 0,
    remark: '',
    closingCost: 0,
    unadjusted: 0,
    aje: 0,
    rje: 0,
    adjusted: 0,
    variance: 0,
    indexRef: '',
  }
}

/** 公式链求解（区段间行同步的核心：所有派生列都在这里重算） */
function enrich(r: TradingDetailRow): TradingDetailRow {
  const closingQuantity = calcClosingQuantity(
    parseNum(r.openingQuantity),
    parseNum(r.boughtQuantity),
    parseNum(r.soldQuantity),
  )
  const closingFairValue = calcFairValue(closingQuantity, parseNum(r.unitFairValue))
  const fairValueChange = calcFairValueChange(closingFairValue, parseNum(r.openingFairValue))
  const realizedGain = calcRealizedGain(parseNum(r.disposalProceeds), parseNum(r.disposalCost))
  const totalIncome = realizedGain + parseNum(r.dividendIncome)
  const closingCost = calcEndAmount(parseNum(r.openingCost), parseNum(r.addedCost), parseNum(r.reducedCost))
  const adjusted = calcAdjustedAmount(parseNum(r.unadjusted), parseNum(r.aje), parseNum(r.rje))
  const variance = adjusted - closingFairValue
  return {
    ...r,
    closingQuantity,
    closingFairValue,
    fairValueChange,
    realizedGain,
    totalIncome,
    closingCost,
    adjusted,
    variance,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): TradingDetailRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<TradingDetailRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [enrich(emptyRow('1', 1))]
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
  'addedCost',
  'reducedCost',
  'closingFairValue',
  'openingFairValue',
  'fairValueChange',
  'cumulativeFVChange',
  'disposalProceeds',
  'disposalCost',
  'realizedGain',
  'dividendIncome',
  'totalIncome',
  'fvChangeInPL',
  'closingCost',
  'unadjusted',
  'aje',
  'rje',
  'adjusted',
  'variance',
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
  investType: string
  investLabel: string
  count: number
  totals: G1DetailTotals
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG1Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<TradingDetailRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')
  /** 当前区段 */
  const segment = ref<string>(G1_DETAIL_SEGMENTS[0].key)

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  // allResponses 异步加载完成后回填
  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  /** 分类小计（按投资类型分组） */
  const subtotalsByType = computed<G1DetailSubtotal[]>(() => {
    const byType = new Map<string, TradingDetailRow[]>()
    for (const r of rows.value) {
      const key = r.investType || 'other'
      if (!byType.has(key)) byType.set(key, [])
      byType.get(key)!.push(r)
    }
    return Array.from(byType.entries()).map(([investType, list]) => ({
      investType,
      investLabel: INVEST_LABEL[investType] ?? '其他',
      count: list.length,
      totals: sumRows(list),
    }))
  })

  /** 总计 */
  const grandTotal = computed<G1DetailTotals>(() => sumRows(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<TradingDetailRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '证券名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [...rows.value, enrich({ ...emptyRow(`row-${Date.now()}`, seq), securityName: value })]
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
    subtotalsByType,
    grandTotal,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1Detail
