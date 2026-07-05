/**
 * useG1IncomeCalc - G1-5 收益测算表（2区段Tab）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.5
 *
 * Responsibilities:
 * - 2区段Tab（投资收益测算9列 / 处置损益测算9列），区段间行同步
 * - 应收金额=持有×每股股利；处置损益=calcRealizedGain（成交-成本）；净损益=calcNetGain（处置-手续费）
 * - 合计 + 动态行增删 + loadAll/persistAll
 *
 * Requirements: 8.1~8.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcRealizedGain,
  calcNetGain,
  calcSubtotal,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// --- Types ---

/**
 * G1-5 收益测算行（18列 = 投资收益测算9列 + 处置损益测算9列，共用证券名称）
 * 投资收益测算(9列): 证券名称|持有数量|每股股利/利率|应收金额(公式)|实收金额|差异|确认日期|来源|备注
 * 处置损益测算(9列): 证券名称|卖出数量|成交价|成交金额|原始成本|处置损益(公式)|手续费|净损益(公式)|备注
 */
export interface G1IncomeCalcRow {
  id: string
  seq: number
  securityName: string // 证券名称（两区段共用）
  // --- 投资收益测算区段 ---
  holdingQuantity: number // 持有数量
  dividendPerShare: number // 每股股利/利率
  receivableAmount: number // 应收金额(公式) = 持有 × 每股股利
  receivedAmount: number // 实收金额
  incomeDiff: number // 差异(公式) = 应收 - 实收
  confirmDate: string // 确认日期
  incomeSource: string // 来源
  incomeRemark: string // 备注
  // --- 处置损益测算区段 ---
  soldQuantity: number // 卖出数量
  dealPrice: number // 成交价
  dealAmount: number // 成交金额
  originalCost: number // 原始成本
  realizedGain: number // 处置损益(公式) = 成交金额 - 原始成本
  fee: number // 手续费
  netGain: number // 净损益(公式) = 处置损益 - 手续费
  disposalRemark: string // 备注
}

export interface G1IncomeCalcColumn {
  prop: keyof G1IncomeCalcRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number'
}

/** 投资收益测算区段（9列含证券名称） */
export const G1_INCOME_COLUMNS: G1IncomeCalcColumn[] = [
  { prop: 'securityName', label: '证券名称', width: 160, type: 'text' },
  { prop: 'holdingQuantity', label: '持有数量', width: 110, type: 'number' },
  { prop: 'dividendPerShare', label: '每股股利/利率', width: 130, type: 'number' },
  { prop: 'receivableAmount', label: '应收金额', width: 120, type: 'number', formula: true },
  { prop: 'receivedAmount', label: '实收金额', width: 120, type: 'number' },
  { prop: 'incomeDiff', label: '差异', width: 110, type: 'number', formula: true },
  { prop: 'confirmDate', label: '确认日期', width: 130, type: 'text' },
  { prop: 'incomeSource', label: '来源', width: 130, type: 'text' },
  { prop: 'incomeRemark', label: '备注', width: 140, type: 'text' },
]

/** 处置损益测算区段（9列含证券名称） */
export const G1_DISPOSAL_COLUMNS: G1IncomeCalcColumn[] = [
  { prop: 'securityName', label: '证券名称', width: 160, type: 'text' },
  { prop: 'soldQuantity', label: '卖出数量', width: 110, type: 'number' },
  { prop: 'dealPrice', label: '成交价', width: 110, type: 'number' },
  { prop: 'dealAmount', label: '成交金额', width: 120, type: 'number' },
  { prop: 'originalCost', label: '原始成本', width: 120, type: 'number' },
  { prop: 'realizedGain', label: '处置损益', width: 120, type: 'number', formula: true },
  { prop: 'fee', label: '手续费', width: 110, type: 'number' },
  { prop: 'netGain', label: '净损益', width: 120, type: 'number', formula: true },
  { prop: 'disposalRemark', label: '备注', width: 140, type: 'text' },
]

const DATA_KEY = 'G1-5-rows'
const CONCLUSION_KEY = 'G1-5-conclusion'

// --- Helpers ---

function emptyRow(id: string, seq: number): G1IncomeCalcRow {
  return {
    id,
    seq,
    securityName: '',
    holdingQuantity: 0,
    dividendPerShare: 0,
    receivableAmount: 0,
    receivedAmount: 0,
    incomeDiff: 0,
    confirmDate: '',
    incomeSource: '',
    incomeRemark: '',
    soldQuantity: 0,
    dealPrice: 0,
    dealAmount: 0,
    originalCost: 0,
    realizedGain: 0,
    fee: 0,
    netGain: 0,
    disposalRemark: '',
  }
}

/**
 * 公式:
 * - 应收金额 = 持有数量 × 每股股利
 * - 差异 = 应收金额 - 实收金额
 * - 处置损益 = 成交金额 - 原始成本
 * - 净损益 = 处置损益 - 手续费
 */
function enrich(r: G1IncomeCalcRow): G1IncomeCalcRow {
  const receivableAmount = parseNum(r.holdingQuantity) * parseNum(r.dividendPerShare)
  const incomeDiff = receivableAmount - parseNum(r.receivedAmount)
  const realizedGain = calcRealizedGain(parseNum(r.dealAmount), parseNum(r.originalCost))
  const netGain = calcNetGain(realizedGain, parseNum(r.fee))
  return { ...r, receivableAmount, incomeDiff, realizedGain, netGain }
}

function loadRows(map: Map<string, ChecklistResponse>): G1IncomeCalcRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<G1IncomeCalcRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

const SUM_FIELDS = [
  'holdingQuantity',
  'receivableAmount',
  'receivedAmount',
  'incomeDiff',
  'soldQuantity',
  'dealAmount',
  'originalCost',
  'realizedGain',
  'fee',
  'netGain',
] as const

export type G1IncomeCalcTotals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: G1IncomeCalcRow[]): G1IncomeCalcTotals {
  const out = {} as G1IncomeCalcTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

// --- Composable ---

export function useG1IncomeCalc(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1IncomeCalcRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const grandTotal = computed<G1IncomeCalcTotals>(() => sumRows(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1IncomeCalcRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增测算行', {
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
    incomeColumns: G1_INCOME_COLUMNS,
    disposalColumns: G1_DISPOSAL_COLUMNS,
    rows,
    auditConclusion,
    grandTotal,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1IncomeCalc
