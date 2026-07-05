/**
 * useG1Inventory - G1-4 结存表（21列→2区段Tab）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.4
 *
 * Responsibilities:
 * - 21列→2区段Tab（基础+期初增减 / 期末+损益），区段间行同步
 * - 期末数量=calcClosingQuantity；期末成本=calcEndAmount；未实现损益=calcUnrealizedGain
 * - 品种分组小计+总计 + 动态行增删 + loadAll/persistAll
 *
 * Requirements: 7.1~7.7
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcClosingQuantity,
  calcEndAmount,
  calcUnrealizedGain,
  calcSubtotal,
} from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// --- Types ---

/**
 * G1-4 结存行（21列）
 * 区段A（基础+期初增减）：证券名称|代码|类型 + 期初(数量/成本/公允) + 增加(数量/成本) + 减少(数量/成本/处置收入)
 * 区段B（期末+损益）：证券名称 + 期末(数量/成本/公允/未实现损益)
 */
export interface G1InventoryRow {
  id: string
  seq: number
  securityName: string // 证券名称（两区段共用）
  securityCode: string // 代码
  securityType: string // 类型（品种分组用）
  // 期初
  openingQuantity: number // 期初数量
  openingCost: number // 期初成本
  openingFairValue: number // 期初公允
  // 增加
  addQuantity: number // 增加数量
  addCost: number // 增加成本
  // 减少
  reduceQuantity: number // 减少数量
  reduceCost: number // 减少成本
  disposalProceeds: number // 处置收入
  // 期末（公式）
  closingQuantity: number // 期末数量 = 期初 + 增加 - 减少
  closingCost: number // 期末成本 = 期初成本 + 增加 - 减少
  closingFairValue: number // 期末公允
  unrealizedGain: number // 未实现损益 = 期末公允 - 期末成本
}

export interface G1InventoryColumn {
  prop: keyof G1InventoryRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number'
}

/** 区段A：基础+期初增减（13列含证券信息） */
export const G1_INVENTORY_BASIC_COLUMNS: G1InventoryColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'securityName', label: '证券名称', width: 160, type: 'text' },
  { prop: 'securityCode', label: '代码', width: 110, type: 'text' },
  { prop: 'securityType', label: '类型', width: 110, type: 'text' },
  { prop: 'openingQuantity', label: '期初数量', width: 110, type: 'number' },
  { prop: 'openingCost', label: '期初成本', width: 120, type: 'number' },
  { prop: 'openingFairValue', label: '期初公允', width: 120, type: 'number' },
  { prop: 'addQuantity', label: '增加数量', width: 110, type: 'number' },
  { prop: 'addCost', label: '增加成本', width: 120, type: 'number' },
  { prop: 'reduceQuantity', label: '减少数量', width: 110, type: 'number' },
  { prop: 'reduceCost', label: '减少成本', width: 120, type: 'number' },
  { prop: 'disposalProceeds', label: '处置收入', width: 120, type: 'number' },
]

/** 区段B：期末+损益（6列含证券名称） */
export const G1_INVENTORY_CLOSING_COLUMNS: G1InventoryColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'securityName', label: '证券名称', width: 160, type: 'text' },
  { prop: 'closingQuantity', label: '期末数量', width: 120, type: 'number', formula: true },
  { prop: 'closingCost', label: '期末成本', width: 120, type: 'number', formula: true },
  { prop: 'closingFairValue', label: '期末公允', width: 120, type: 'number' },
  { prop: 'unrealizedGain', label: '未实现损益', width: 130, type: 'number', formula: true },
]

const DATA_KEY = 'G1-4-rows'
const CONCLUSION_KEY = 'G1-4-conclusion'

// --- Helpers ---

function emptyRow(id: string, seq: number): G1InventoryRow {
  return {
    id,
    seq,
    securityName: '',
    securityCode: '',
    securityType: '',
    openingQuantity: 0,
    openingCost: 0,
    openingFairValue: 0,
    addQuantity: 0,
    addCost: 0,
    reduceQuantity: 0,
    reduceCost: 0,
    disposalProceeds: 0,
    closingQuantity: 0,
    closingCost: 0,
    closingFairValue: 0,
    unrealizedGain: 0,
  }
}

/**
 * 公式:
 * - 期末数量 = 期初 + 增加 - 减少
 * - 期末成本 = 期初成本 + 增加成本 - 减少成本
 * - 未实现损益 = 期末公允 - 期末成本
 */
function enrich(r: G1InventoryRow): G1InventoryRow {
  const closingQuantity = calcClosingQuantity(
    parseNum(r.openingQuantity),
    parseNum(r.addQuantity),
    parseNum(r.reduceQuantity),
  )
  const closingCost = calcEndAmount(parseNum(r.openingCost), parseNum(r.addCost), parseNum(r.reduceCost))
  const unrealizedGain = calcUnrealizedGain(parseNum(r.closingFairValue), closingCost)
  return { ...r, closingQuantity, closingCost, unrealizedGain }
}

function loadRows(map: Map<string, ChecklistResponse>): G1InventoryRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow('1', 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<G1InventoryRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [enrich(emptyRow('1', 1))]
    return parsed.map((p, i) => enrich({ ...emptyRow(p.id ?? String(i + 1), p.seq ?? i + 1), ...p }))
  } catch {
    return [enrich(emptyRow('1', 1))]
  }
}

const SUM_FIELDS = [
  'openingQuantity',
  'openingCost',
  'openingFairValue',
  'addQuantity',
  'addCost',
  'reduceQuantity',
  'reduceCost',
  'disposalProceeds',
  'closingQuantity',
  'closingCost',
  'closingFairValue',
  'unrealizedGain',
] as const

export type G1InventoryTotals = Record<(typeof SUM_FIELDS)[number], number>

function sumRows(list: G1InventoryRow[]): G1InventoryTotals {
  const out = {} as G1InventoryTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

export interface G1InventoryGroup {
  securityType: string
  rows: G1InventoryRow[]
  subtotal: G1InventoryTotals
}

// --- Composable ---

export function useG1Inventory(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1InventoryRow[]>(loadRows(opts.allResponses.value))
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

  /** 品种分组小计 */
  const groups = computed<G1InventoryGroup[]>(() => {
    const byType = new Map<string, G1InventoryRow[]>()
    for (const r of rows.value) {
      const key = r.securityType || '未分类'
      if (!byType.has(key)) byType.set(key, [])
      byType.get(key)!.push(r)
    }
    return Array.from(byType.entries()).map(([securityType, list]) => ({
      securityType,
      rows: list,
      subtotal: sumRows(list),
    }))
  })

  const grandTotal = computed<G1InventoryTotals>(() => sumRows(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1InventoryRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入证券名称', '新增结存行', {
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
    basicColumns: G1_INVENTORY_BASIC_COLUMNS,
    closingColumns: G1_INVENTORY_CLOSING_COLUMNS,
    rows,
    auditConclusion,
    groups,
    grandTotal,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useG1Inventory
