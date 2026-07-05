/**
 * useG1DerivativeCheck - G1-14 衍生金融工具核查表
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.6
 *
 * Responsibilities:
 * - 10列：序号|工具名称|类型(期权/期货/互换/远期)|名义金额|期限|对手方|保证金|是否套期|会计处理适当性(下拉)|合规结论
 * - 衍生工具类型下拉 + 会计处理适当性下拉 + 合规结论
 * - 动态行增删 + loadAll/persistAll
 *
 * Requirements: 12.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// --- Types ---

/** 衍生工具类型 */
export type DerivativeType = 'option' | 'futures' | 'swap' | 'forward' | ''

/** 会计处理适当性 */
export type AccountingAppropriateness = 'appropriate' | 'inappropriate' | 'needs-review' | ''

export const G1_DERIVATIVE_TYPE_OPTIONS = [
  { value: 'option', label: '期权' },
  { value: 'futures', label: '期货' },
  { value: 'swap', label: '互换' },
  { value: 'forward', label: '远期' },
] as const

export const G1_ACCOUNTING_OPTIONS = [
  { value: 'appropriate', label: '适当' },
  { value: 'inappropriate', label: '不适当' },
  { value: 'needs-review', label: '需复核' },
] as const

/** G1-14 衍生工具核查行（10列） */
export interface G1DerivativeCheckRow {
  id: string
  seq: number
  instrumentName: string // 工具名称
  instrumentType: DerivativeType // 类型（下拉）
  notionalAmount: number // 名义金额
  term: string // 期限
  counterparty: string // 对手方
  margin: number // 保证金
  isHedging: string // 是否套期
  accountingAppropriateness: AccountingAppropriateness // 会计处理适当性（下拉）
  complianceConclusion: string // 合规结论
}

export interface G1DerivativeCheckColumn {
  prop: keyof G1DerivativeCheckRow
  label: string
  width: number
  type: 'text' | 'number' | 'type-select' | 'accounting-select'
}

export const G1_DERIVATIVE_CHECK_COLUMNS: G1DerivativeCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'instrumentName', label: '工具名称', width: 160, type: 'text' },
  { prop: 'instrumentType', label: '类型', width: 120, type: 'type-select' },
  { prop: 'notionalAmount', label: '名义金额', width: 130, type: 'number' },
  { prop: 'term', label: '期限', width: 120, type: 'text' },
  { prop: 'counterparty', label: '对手方', width: 150, type: 'text' },
  { prop: 'margin', label: '保证金', width: 120, type: 'number' },
  { prop: 'isHedging', label: '是否套期', width: 110, type: 'text' },
  { prop: 'accountingAppropriateness', label: '会计处理适当性', width: 140, type: 'accounting-select' },
  { prop: 'complianceConclusion', label: '合规结论', width: 180, type: 'text' },
]

const DATA_KEY = 'G1-14-rows'
const CONCLUSION_KEY = 'G1-14-conclusion'

// --- Helpers ---

function emptyRow(id: string, seq: number): G1DerivativeCheckRow {
  return {
    id,
    seq,
    instrumentName: '',
    instrumentType: '',
    notionalAmount: 0,
    term: '',
    counterparty: '',
    margin: 0,
    isHedging: '',
    accountingAppropriateness: '',
    complianceConclusion: '',
  }
}

function loadRows(map: Map<string, ChecklistResponse>): G1DerivativeCheckRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [emptyRow('1', 1)]
  try {
    const parsed = JSON.parse(raw) as Partial<G1DerivativeCheckRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyRow('1', 1)]
    return parsed.map((p, i) => ({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [emptyRow('1', 1)]
  }
}

// --- Composable ---

export function useG1DerivativeCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1DerivativeCheckRow[]>(loadRows(opts.allResponses.value))
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

  const notionalTotal = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.notionalAmount))))
  const marginTotal = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.margin))))
  const inappropriateCount = computed(
    () => rows.value.filter((r) => r.accountingAppropriateness === 'inappropriate').length,
  )

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1DerivativeCheckRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入衍生工具名称', '新增衍生工具行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '工具名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [...rows.value, { ...emptyRow(`row-${Date.now()}`, seq), instrumentName: value }]
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
    columns: G1_DERIVATIVE_CHECK_COLUMNS,
    typeOptions: G1_DERIVATIVE_TYPE_OPTIONS,
    accountingOptions: G1_ACCOUNTING_OPTIONS,
    rows,
    auditConclusion,
    notionalTotal,
    marginTotal,
    inappropriateCount,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1DerivativeCheck
