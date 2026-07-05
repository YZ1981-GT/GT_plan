/**
 * useG1Level3 - G1-7 di san ceng ci tiao jie biao (Level 3 fair value reconciliation)
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.2
 *
 * Responsibilities:
 * - Define Level3ReconRow (13 columns, single table)
 * - Closing balance formula = opening + increase - decrease + current FV change
 * - Total row + audit conclusion
 * - Dynamic add/remove + loadAll/persistAll
 *
 * Requirements: 10.1-10.4
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcEndAmount, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// --- Types ---

/** G1-7 Level3 reconciliation row (13 columns) */
export interface Level3ReconRow {
  id: string
  seq: number
  itemName: string // 项目名称
  openingBalance: number // 期初余额
  addNewRecognition: number // 本期增加-新确认
  addTransferIn: number // 本期增加-转入
  reduceDerecognition: number // 本期减少-终止确认
  reduceTransferOut: number // 本期减少-转出
  fairValueChange: number // 本期公允变动
  closingBalance: number // 期末余额(公式)
  cumulativeChange: number // 累计变动
  valuationMethod: string // 估值方法
  keyAssumption: string // 关键假设
  sensitivity: string // 敏感性分析
  auditEval: string // 审计评价
  remark: string // 备注
}

export interface Level3Column {
  prop: keyof Level3ReconRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number'
}

export const G1_LEVEL3_COLUMNS: Level3Column[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'itemName', label: '项目名称', width: 160, type: 'text' },
  { prop: 'openingBalance', label: '期初余额', width: 120, type: 'number' },
  { prop: 'addNewRecognition', label: '本期增加·新确认', width: 130, type: 'number' },
  { prop: 'addTransferIn', label: '本期增加·转入', width: 130, type: 'number' },
  { prop: 'reduceDerecognition', label: '本期减少·终止确认', width: 140, type: 'number' },
  { prop: 'reduceTransferOut', label: '本期减少·转出', width: 130, type: 'number' },
  { prop: 'fairValueChange', label: '本期公允变动', width: 130, type: 'number' },
  { prop: 'closingBalance', label: '期末余额', width: 120, type: 'number', formula: true },
  { prop: 'cumulativeChange', label: '累计变动', width: 120, type: 'number' },
  { prop: 'valuationMethod', label: '估值方法', width: 140, type: 'text' },
  { prop: 'keyAssumption', label: '关键假设', width: 160, type: 'text' },
  { prop: 'sensitivity', label: '敏感性分析', width: 160, type: 'text' },
  { prop: 'auditEval', label: '审计评价', width: 160, type: 'text' },
  { prop: 'remark', label: '备注', width: 140, type: 'text' },
]

const DATA_KEY = 'G1-7-rows'
const CONCLUSION_KEY = 'G1-7-conclusion'

// --- Helpers ---

function emptyRow(id: string, seq: number): Level3ReconRow {
  return {
    id,
    seq,
    itemName: '',
    openingBalance: 0,
    addNewRecognition: 0,
    addTransferIn: 0,
    reduceDerecognition: 0,
    reduceTransferOut: 0,
    fairValueChange: 0,
    closingBalance: 0,
    cumulativeChange: 0,
    valuationMethod: '',
    keyAssumption: '',
    sensitivity: '',
    auditEval: '',
    remark: '',
  }
}

/** Formula: closing = opening + increase - decrease + FV change */
function enrich(r: Level3ReconRow): Level3ReconRow {
  const increase = parseNum(r.addNewRecognition) + parseNum(r.addTransferIn)
  const decrease = parseNum(r.reduceDerecognition) + parseNum(r.reduceTransferOut)
  const closingBalance = calcEndAmount(parseNum(r.openingBalance), increase, decrease) + parseNum(r.fairValueChange)
  return { ...r, closingBalance }
}

function loadRows(map: Map<string, ChecklistResponse>): Level3ReconRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<Level3ReconRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

const SUM_FIELDS = [
  'openingBalance',
  'addNewRecognition',
  'addTransferIn',
  'reduceDerecognition',
  'reduceTransferOut',
  'fairValueChange',
  'closingBalance',
  'cumulativeChange',
] as const

export type G1Level3Totals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: Level3ReconRow[]): G1Level3Totals {
  const out = {} as G1Level3Totals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

// --- Composable ---

export function useG1Level3(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<Level3ReconRow[]>(loadRows(opts.allResponses.value))
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

  const grandTotal = computed<G1Level3Totals>(() => sumRows(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<Level3ReconRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增调节行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '项目名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [...rows.value, enrich({ ...emptyRow(`row-${Date.now()}`, seq), itemName: value })]
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
    columns: G1_LEVEL3_COLUMNS,
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

export default useG1Level3
