/**
 * useG1SecuritiesCount - G1-11 有价证券监盘表
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.6
 *
 * Responsibilities:
 * - 10列监盘表：序号|证券名称|代码|类型|账面数量|盘点数量|差异(公式)|差异原因|保管机构|监盘日期
 * - 盘点差异=calcCountDiff（盘点-账面），差异>0橙色标记
 * - 动态行增删 + loadAll/persistAll
 *
 * Requirements: 12.1~12.3
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum, calcCountDiff } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// --- Types ---

/** G1-11 监盘行（10列） */
export interface G1SecuritiesCountRow {
  id: string
  seq: number
  securityName: string // 证券名称
  securityCode: string // 代码
  securityType: string // 类型
  bookedQuantity: number // 账面数量
  countedQuantity: number // 盘点数量
  countDiff: number // 差异(公式) = 盘点 - 账面
  diffReason: string // 差异原因
  custodian: string // 保管机构
  countDate: string // 监盘日期
}

export interface G1SecuritiesCountColumn {
  prop: keyof G1SecuritiesCountRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number'
}

export const G1_SECURITIES_COUNT_COLUMNS: G1SecuritiesCountColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'securityName', label: '证券名称', width: 160, type: 'text' },
  { prop: 'securityCode', label: '代码', width: 110, type: 'text' },
  { prop: 'securityType', label: '类型', width: 110, type: 'text' },
  { prop: 'bookedQuantity', label: '账面数量', width: 120, type: 'number' },
  { prop: 'countedQuantity', label: '盘点数量', width: 120, type: 'number' },
  { prop: 'countDiff', label: '差异', width: 110, type: 'number', formula: true },
  { prop: 'diffReason', label: '差异原因', width: 160, type: 'text' },
  { prop: 'custodian', label: '保管机构', width: 140, type: 'text' },
  { prop: 'countDate', label: '监盘日期', width: 130, type: 'text' },
]

const DATA_KEY = 'G1-11-rows'
const CONCLUSION_KEY = 'G1-11-conclusion'

// --- Helpers ---

function emptyRow(id: string, seq: number): G1SecuritiesCountRow {
  return {
    id,
    seq,
    securityName: '',
    securityCode: '',
    securityType: '',
    bookedQuantity: 0,
    countedQuantity: 0,
    countDiff: 0,
    diffReason: '',
    custodian: '',
    countDate: '',
  }
}

/** 公式: 差异 = 盘点数量 - 账面数量 */
function enrich(r: G1SecuritiesCountRow): G1SecuritiesCountRow {
  const countDiff = calcCountDiff(parseNum(r.countedQuantity), parseNum(r.bookedQuantity))
  return { ...r, countDiff }
}

function loadRows(map: Map<string, ChecklistResponse>): G1SecuritiesCountRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<G1SecuritiesCountRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

// --- Composable ---

export function useG1SecuritiesCount(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1SecuritiesCountRow[]>(loadRows(opts.allResponses.value))
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

  /** 差异笔数（|差异|>0） */
  const diffCount = computed(() => rows.value.filter((r) => Math.abs(parseNum(r.countDiff)) > 0).length)

  /** 差异>0 判定（供组件橙色标记） */
  function isDiffAbnormal(row: G1SecuritiesCountRow): boolean {
    return Math.abs(parseNum(row.countDiff)) > 0
  }

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1SecuritiesCountRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增监盘行', {
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
    columns: G1_SECURITIES_COUNT_COLUMNS,
    rows,
    auditConclusion,
    diffCount,
    isDiffAbnormal,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1SecuritiesCount
