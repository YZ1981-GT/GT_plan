/**
 * useG3Detail — G3-2 应收股利明细表（33列 → 4区段Tab）
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 5.1
 *
 * 职责：
 * - 33列拆为4区段（被投资方信息/持股明细/分红方案/应收核算），区段间行同步
 * - 公式链：
 *     权益份额     = 净资产 × 持股比例/100              (calcEquityShare)
 *     分红总额     = 持股数量 × 每股股利                (calcDividend)
 *     实际分红率   = 分红总额 / 净利润 × 100%          (calcPayoutRatio, 净利润≤0→0)
 *     应收股利     = 持股数量 × 每股股利                (calcDividend)
 *     期末应收     = 应收股利 - 已收金额                (calcNetReceivable)
 *     逾期天数     = MAX(0, 当前日期 - 股权登记日)      (calcOverdueDays)
 * - 动态行增删（ElMessageBox.prompt 输入被投资方名称）
 * - 底部合计（投资成本/分红总额/应收/已收/期末应收）
 * - 逾期行橙色高亮（overdueDays > 0）
 * - 存储到 allResponses 'G3-2-detail-rows' key
 *
 * Requirements: 5.1~5.11
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcEquityShare,
  calcDividend,
  calcPayoutRatio,
  calcNetReceivable,
  calcOverdueDays,
  calcSubtotal,
} from './useG3DivRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type G3InvestType = 'long-term-equity' | 'other-equity'
export type G3AccountingMethod = 'cost' | 'equity'

/** G3-2 明细行（33列分4区段） */
export interface DividendDetailRow {
  id: string
  seq: number
  // 被投资方信息(8列)
  investeeName: string
  socialCreditCode: string
  registeredCapital: number
  industry: string
  investType: G3InvestType
  initialCost: number
  investDate: string
  // 持股明细(9列)
  sharesHeld: number              // 持股数量(股)
  shareholdingRatio: number       // 持股比例(%)
  investeeNetProfit: number       // 被投资方净利润
  investeeNetAssets: number       // 被投资方净资产
  equityShare: number             // 权益份额(公式)
  bookValue: number               // 账面值
  accountingMethod: G3AccountingMethod
  isListed: string
  listingCode: string
  // 分红方案(8列)
  resolutionDate: string          // 股东大会决议日
  dividendPlan: string            // 分红方案描述
  dps: number                     // 每股股利(元)
  declarationDate: string         // 宣告日
  recordDate: string              // 股权登记日
  exDividendDate: string          // 除权日
  totalDividend: number           // 分红总额(公式)
  payoutRatio: number             // 实际分红率(公式)
  // 应收核算(8列)
  dividendReceivable: number      // 应收股利(公式)
  receivedAmount: number          // 已收金额
  netReceivable: number           // 期末应收(公式)
  receiptDate: string             // 收款日期
  receiptMethod: string           // 收款方式
  isOverdue: string               // 是否逾期
  overdueDays: number             // 逾期天数(公式)
  remark: string
}

export interface G3DetailColumn {
  prop: keyof DividendDetailRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'invest-type' | 'method'
}

export interface G3DetailSegment {
  key: string
  label: string
  columns: G3DetailColumn[]
}

// ─── Column Constants ────────────────────────────────────────────────────────

export const G3_INVEST_TYPE_OPTIONS: { value: G3InvestType; label: string }[] = [
  { value: 'long-term-equity', label: '长期股权投资' },
  { value: 'other-equity', label: '其他权益工具投资' },
]

export const G3_ACCOUNTING_METHOD_OPTIONS: { value: G3AccountingMethod; label: string }[] = [
  { value: 'cost', label: '成本法' },
  { value: 'equity', label: '权益法' },
]

/** 4区段列配置 */
export const G3_DETAIL_SEGMENTS: G3DetailSegment[] = [
  {
    key: 'investee',
    label: '被投资方信息',
    columns: [
      { prop: 'seq', label: '序号', width: 60, formula: true },
      { prop: 'investeeName', label: '被投资方名称', width: 160, type: 'text' },
      { prop: 'socialCreditCode', label: '统一社会信用代码', width: 180, type: 'text' },
      { prop: 'registeredCapital', label: '注册资本', width: 130, type: 'number' },
      { prop: 'industry', label: '行业', width: 120, type: 'text' },
      { prop: 'investType', label: '投资类型', width: 140, type: 'invest-type' },
      { prop: 'initialCost', label: '初始投资成本', width: 130, type: 'number' },
      { prop: 'investDate', label: '投资日期', width: 130, type: 'date' },
    ],
  },
  {
    key: 'shareholding',
    label: '持股明细',
    columns: [
      { prop: 'sharesHeld', label: '持股数量(股)', width: 130, type: 'number' },
      { prop: 'shareholdingRatio', label: '持股比例(%)', width: 120, type: 'number' },
      { prop: 'investeeNetProfit', label: '被投资方净利润', width: 140, type: 'number' },
      { prop: 'investeeNetAssets', label: '被投资方净资产', width: 140, type: 'number' },
      { prop: 'equityShare', label: '权益份额', width: 130, type: 'number', formula: true },
      { prop: 'bookValue', label: '账面值', width: 120, type: 'number' },
      { prop: 'accountingMethod', label: '核算方法', width: 110, type: 'method' },
      { prop: 'isListed', label: '是否上市', width: 100, type: 'text' },
      { prop: 'listingCode', label: '上市代码', width: 120, type: 'text' },
    ],
  },
  {
    key: 'dividend',
    label: '分红方案',
    columns: [
      { prop: 'resolutionDate', label: '决议日期', width: 130, type: 'date' },
      { prop: 'dividendPlan', label: '分红方案描述', width: 160, type: 'text' },
      { prop: 'dps', label: '每股股利(元)', width: 120, type: 'number' },
      { prop: 'declarationDate', label: '宣告日', width: 130, type: 'date' },
      { prop: 'recordDate', label: '股权登记日', width: 130, type: 'date' },
      { prop: 'exDividendDate', label: '除权日', width: 130, type: 'date' },
      { prop: 'totalDividend', label: '分红总额', width: 130, type: 'number', formula: true },
      { prop: 'payoutRatio', label: '实际分红率(%)', width: 130, type: 'number', formula: true },
    ],
  },
  {
    key: 'receivable',
    label: '应收核算',
    columns: [
      { prop: 'dividendReceivable', label: '应收股利', width: 130, type: 'number', formula: true },
      { prop: 'receivedAmount', label: '已收金额', width: 120, type: 'number' },
      { prop: 'netReceivable', label: '期末应收', width: 120, type: 'number', formula: true },
      { prop: 'receiptDate', label: '收款日期', width: 130, type: 'date' },
      { prop: 'receiptMethod', label: '收款方式', width: 120, type: 'text' },
      { prop: 'isOverdue', label: '是否逾期', width: 100, type: 'text' },
      { prop: 'overdueDays', label: '逾期天数', width: 110, type: 'number', formula: true },
      { prop: 'remark', label: '备注', width: 140, type: 'text' },
    ],
  },
]

// Convenience exports (alias by segment)
export const SEGMENT_INVESTEE_COLS = G3_DETAIL_SEGMENTS[0].columns
export const SEGMENT_SHAREHOLDING_COLS = G3_DETAIL_SEGMENTS[1].columns
export const SEGMENT_DIVIDEND_COLS = G3_DETAIL_SEGMENTS[2].columns
export const SEGMENT_RECEIVABLE_COLS = G3_DETAIL_SEGMENTS[3].columns

// ─── Storage Key ─────────────────────────────────────────────────────────────

const DATA_KEY = 'G3-2-detail-rows'

// ─── Subtotal Fields ─────────────────────────────────────────────────────────

const SUM_FIELDS = [
  'initialCost',
  'totalDividend',
  'dividendReceivable',
  'receivedAmount',
  'netReceivable',
] as const

export type G3DetailTotals = Record<(typeof SUM_FIELDS)[number], number>

// ─── Helpers ─────────────────────────────────────────────────────────────────

function emptyRow(id: string, seq: number): DividendDetailRow {
  return {
    id,
    seq,
    // 被投资方信息
    investeeName: '',
    socialCreditCode: '',
    registeredCapital: 0,
    industry: '',
    investType: 'long-term-equity',
    initialCost: 0,
    investDate: '',
    // 持股明细
    sharesHeld: 0,
    shareholdingRatio: 0,
    investeeNetProfit: 0,
    investeeNetAssets: 0,
    equityShare: 0,
    bookValue: 0,
    accountingMethod: 'cost',
    isListed: '',
    listingCode: '',
    // 分红方案
    resolutionDate: '',
    dividendPlan: '',
    dps: 0,
    declarationDate: '',
    recordDate: '',
    exDividendDate: '',
    totalDividend: 0,
    payoutRatio: 0,
    // 应收核算
    dividendReceivable: 0,
    receivedAmount: 0,
    netReceivable: 0,
    receiptDate: '',
    receiptMethod: '',
    isOverdue: '',
    overdueDays: 0,
    remark: '',
  }
}

/** 公式链求解 — 区段间行同步核心：所有派生列在此重算 */
function enrich(r: DividendDetailRow): DividendDetailRow {
  const sharesHeld = parseNum(r.sharesHeld)
  const shareholdingRatio = parseNum(r.shareholdingRatio)
  const investeeNetAssets = parseNum(r.investeeNetAssets)
  const investeeNetProfit = parseNum(r.investeeNetProfit)
  const dps = parseNum(r.dps)
  const receivedAmount = parseNum(r.receivedAmount)

  // 权益份额 = 净资产 × 持股比例 / 100
  const equityShare = calcEquityShare(investeeNetAssets, shareholdingRatio)

  // 分红总额 = 持股数量 × 每股股利
  const totalDividend = calcDividend(sharesHeld, dps)

  // 实际分红率 = 分红总额 / 净利润 × 100%（净利润≤0→0）
  const payoutRatio = calcPayoutRatio(totalDividend, investeeNetProfit)

  // 应收股利 = 持股数量 × 每股股利（与分红总额相同）
  const dividendReceivable = calcDividend(sharesHeld, dps)

  // 期末应收 = 应收股利 - 已收金额
  const netReceivable = calcNetReceivable(dividendReceivable, receivedAmount)

  // 逾期天数 = MAX(0, 当前日期 - 股权登记日)
  const overdueDays = r.recordDate
    ? calcOverdueDays(new Date(), new Date(r.recordDate))
    : 0

  // 是否逾期自动标记
  const isOverdue = overdueDays > 0 ? '是' : '否'

  return {
    ...r,
    equityShare,
    totalDividend,
    payoutRatio,
    dividendReceivable,
    netReceivable,
    overdueDays,
    isOverdue,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): DividendDetailRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<DividendDetailRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) =>
      enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }),
    )
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

function sumRows(list: DividendDetailRow[]): G3DetailTotals {
  const out = {} as G3DetailTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

/** 判断行是否逾期（用于橙色高亮） */
export function isRowOverdue(row: DividendDetailRow): boolean {
  return row.overdueDays > 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG3Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<DividendDetailRow[]>(loadRows(opts.allResponses.value))
  /** 当前区段 */
  const segment = ref<string>(G3_DETAIL_SEGMENTS[0].key)

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
  }

  // allResponses 异步加载完成后回填
  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  /** 总计行 */
  const totals = computed<G3DetailTotals>(() => sumRows(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  function updateRow(id: string, patch: Partial<DividendDetailRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '被投资方名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrich({ ...emptyRow(`row-${Date.now()}`, seq), investeeName: value }),
      ]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  return {
    segments: G3_DETAIL_SEGMENTS,
    segment,
    rows,
    totals,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    isRowOverdue,
  }
}

export default useG3Detail
