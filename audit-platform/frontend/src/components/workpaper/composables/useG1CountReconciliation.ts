/**
 * useG1CountReconciliation - G1-12 盘点倒轧表（18列→2区段Tab）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.6
 *
 * Responsibilities:
 * - 18列→2区段Tab（监盘日数据 / 倒轧计算），区段间行同步
 * - 推算余额=calcReconciliation（监盘日余额+增加-减少）；倒轧差异=推算余额-账面余额
 * - 动态行增删 + loadAll/persistAll
 *
 * Requirements: 12.4~12.6
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcReconciliation, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// --- Types ---

/**
 * G1-12 盘点倒轧行（18列，按数量/金额双计量）
 * 区段A（监盘日数据）：证券名称|监盘日余额(数量/金额)|增加(数量/金额)|减少(数量/金额)
 * 区段B（倒轧计算）：证券名称|推算余额(数量/金额,公式)|账面余额(数量/金额)|差异(数量/金额,公式)|结论
 */
export interface G1ReconciliationRow {
  id: string
  seq: number
  securityName: string // 证券名称（两区段共用）
  // --- 监盘日数据区段 ---
  countDayQuantity: number // 监盘日余额-数量
  countDayAmount: number // 监盘日余额-金额
  increaseQuantity: number // 盘点日至报表日增加-数量
  increaseAmount: number // 盘点日至报表日增加-金额
  decreaseQuantity: number // 盘点日至报表日减少-数量
  decreaseAmount: number // 盘点日至报表日减少-金额
  // --- 倒轧计算区段 ---
  derivedQuantity: number // 报表日推算余额-数量(公式)
  derivedAmount: number // 报表日推算余额-金额(公式)
  bookQuantity: number // 账面余额-数量
  bookAmount: number // 账面余额-金额
  diffQuantity: number // 差异-数量(公式)
  diffAmount: number // 差异-金额(公式)
  conclusion: string // 结论
}

export interface G1ReconciliationColumn {
  prop: keyof G1ReconciliationRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number'
}

/** 区段A：监盘日数据 */
export const G1_RECON_COUNTDAY_COLUMNS: G1ReconciliationColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'securityName', label: '证券名称', width: 160, type: 'text' },
  { prop: 'countDayQuantity', label: '监盘日余额·数量', width: 130, type: 'number' },
  { prop: 'countDayAmount', label: '监盘日余额·金额', width: 130, type: 'number' },
  { prop: 'increaseQuantity', label: '增加·数量', width: 110, type: 'number' },
  { prop: 'increaseAmount', label: '增加·金额', width: 120, type: 'number' },
  { prop: 'decreaseQuantity', label: '减少·数量', width: 110, type: 'number' },
  { prop: 'decreaseAmount', label: '减少·金额', width: 120, type: 'number' },
]

/** 区段B：倒轧计算 */
export const G1_RECON_CALC_COLUMNS: G1ReconciliationColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'securityName', label: '证券名称', width: 160, type: 'text' },
  { prop: 'derivedQuantity', label: '推算余额·数量', width: 130, type: 'number', formula: true },
  { prop: 'derivedAmount', label: '推算余额·金额', width: 130, type: 'number', formula: true },
  { prop: 'bookQuantity', label: '账面余额·数量', width: 130, type: 'number' },
  { prop: 'bookAmount', label: '账面余额·金额', width: 130, type: 'number' },
  { prop: 'diffQuantity', label: '差异·数量', width: 110, type: 'number', formula: true },
  { prop: 'diffAmount', label: '差异·金额', width: 120, type: 'number', formula: true },
  { prop: 'conclusion', label: '结论', width: 160, type: 'text' },
]

const DATA_KEY = 'G1-12-rows'
const CONCLUSION_KEY = 'G1-12-conclusion'

// --- Helpers ---

function emptyRow(id: string, seq: number): G1ReconciliationRow {
  return {
    id,
    seq,
    securityName: '',
    countDayQuantity: 0,
    countDayAmount: 0,
    increaseQuantity: 0,
    increaseAmount: 0,
    decreaseQuantity: 0,
    decreaseAmount: 0,
    derivedQuantity: 0,
    derivedAmount: 0,
    bookQuantity: 0,
    bookAmount: 0,
    diffQuantity: 0,
    diffAmount: 0,
    conclusion: '',
  }
}

/**
 * 公式:
 * - 推算余额 = 监盘日余额 + 增加 - 减少（数量与金额各算）
 * - 差异 = 推算余额 - 账面余额
 */
function enrich(r: G1ReconciliationRow): G1ReconciliationRow {
  const derivedQuantity = calcReconciliation(
    parseNum(r.countDayQuantity),
    parseNum(r.increaseQuantity),
    parseNum(r.decreaseQuantity),
  )
  const derivedAmount = calcReconciliation(
    parseNum(r.countDayAmount),
    parseNum(r.increaseAmount),
    parseNum(r.decreaseAmount),
  )
  const diffQuantity = derivedQuantity - parseNum(r.bookQuantity)
  const diffAmount = derivedAmount - parseNum(r.bookAmount)
  return { ...r, derivedQuantity, derivedAmount, diffQuantity, diffAmount }
}

function loadRows(map: Map<string, ChecklistResponse>): G1ReconciliationRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<G1ReconciliationRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

const SUM_FIELDS = [
  'countDayQuantity',
  'countDayAmount',
  'increaseQuantity',
  'increaseAmount',
  'decreaseQuantity',
  'decreaseAmount',
  'derivedQuantity',
  'derivedAmount',
  'bookQuantity',
  'bookAmount',
  'diffQuantity',
  'diffAmount',
] as const

export type G1ReconciliationTotals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: G1ReconciliationRow[]): G1ReconciliationTotals {
  const out = {} as G1ReconciliationTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

// --- Composable ---

export function useG1CountReconciliation(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1ReconciliationRow[]>(loadRows(opts.allResponses.value))
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

  const grandTotal = computed<G1ReconciliationTotals>(() => sumRows(rows.value))

  /** 倒轧差异笔数（数量或金额差异≠0） */
  const diffCount = computed(
    () =>
      rows.value.filter(
        (r) => Math.abs(parseNum(r.diffQuantity)) > 0 || Math.abs(parseNum(r.diffAmount)) > 0.01,
      ).length,
  )

  /** 差异异常判定（供组件橙色标记） */
  function isDiffAbnormal(row: G1ReconciliationRow): boolean {
    return Math.abs(parseNum(row.diffQuantity)) > 0 || Math.abs(parseNum(row.diffAmount)) > 0.01
  }

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1ReconciliationRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增倒轧行', {
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
    countDayColumns: G1_RECON_COUNTDAY_COLUMNS,
    calcColumns: G1_RECON_CALC_COLUMNS,
    rows,
    auditConclusion,
    grandTotal,
    diffCount,
    isDiffAbnormal,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1CountReconciliation
