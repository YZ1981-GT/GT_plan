/**
 * useF2DetailSheet — F2-3~F2-13 通用明细表逻辑
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcEndAmount,
  calcEndBalance,
  calcUnitPrice,
  calcSubtotal,
} from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import type { F2DetailSheetConfig } from '../f2/detail/f2DetailSheetConfigs'

export interface F2DetailRow {
  id: string
  itemName: string
  openingQty: number
  openingAmt: number
  increaseQty: number
  increaseAmt: number
  decreaseQty: number
  decreaseAmt: number
  closingQty: number
  closingAmt: number
  unitPrice: number | ''
  agingLt1: number
  aging1to2: number
  aging2to3: number
  agingGt3: number
  agingTotal: number
  extra?: string
}

function dataKey(sheetCode: string): string {
  return `${sheetCode}-rows`
}

function emptyRow(id: string, hasQuantity: boolean): F2DetailRow {
  return {
    id,
    itemName: '',
    openingQty: 0,
    openingAmt: 0,
    increaseQty: 0,
    increaseAmt: 0,
    decreaseQty: 0,
    decreaseAmt: 0,
    closingQty: 0,
    closingAmt: 0,
    unitPrice: '',
    agingLt1: 0,
    aging1to2: 0,
    aging2to3: 0,
    agingGt3: 0,
    agingTotal: 0,
  }
}

function enrichRow(r: F2DetailRow, hasQuantity: boolean): F2DetailRow {
  const closingQty = hasQuantity
    ? calcEndBalance(r.openingQty, r.increaseQty, r.decreaseQty)
    : 0
  const closingAmt = calcEndAmount(r.openingAmt, r.increaseAmt, r.decreaseAmt)
  const unitPrice = hasQuantity ? calcUnitPrice(closingAmt, closingQty) : calcUnitPrice(closingAmt, 1)
  const agingTotal = r.agingLt1 + r.aging1to2 + r.aging2to3 + r.agingGt3
  return { ...r, closingQty, closingAmt, unitPrice, agingTotal }
}

function loadRows(
  map: Map<string, ChecklistResponse>,
  sheetCode: string,
  hasQuantity: boolean,
): F2DetailRow[] {
  const raw = readRowJson(map.get(dataKey(sheetCode)))
  if (!raw) return [enrichRow(emptyRow('1', hasQuantity), hasQuantity)]
  try {
    const parsed = JSON.parse(raw) as F2DetailRow[]
    return parsed.length ? parsed.map((r) => enrichRow(r, hasQuantity)) : [enrichRow(emptyRow('1', hasQuantity), hasQuantity)]
  } catch {
    return [enrichRow(emptyRow('1', hasQuantity), hasQuantity)]
  }
}

export function useF2DetailSheet(opts: {
  config: Ref<F2DetailSheetConfig>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const activeSegment = ref<'opening' | 'movement' | 'closing' | 'aging'>('opening')
  const searchText = ref('')

  const rows = ref<F2DetailRow[]>(
    loadRows(opts.allResponses.value, opts.config.value.sheetCode, opts.config.value.hasQuantity),
  )

  watch(
    () => opts.config.value.sheetCode,
    (code) => {
      rows.value = loadRows(opts.allResponses.value, code, opts.config.value.hasQuantity)
    },
  )

  const totals = computed(() => {
    const r = rows.value
    return {
      openingQty: calcSubtotal(r.map((x) => x.openingQty)),
      openingAmt: calcSubtotal(r.map((x) => x.openingAmt)),
      increaseQty: calcSubtotal(r.map((x) => x.increaseQty)),
      increaseAmt: calcSubtotal(r.map((x) => x.increaseAmt)),
      decreaseQty: calcSubtotal(r.map((x) => x.decreaseQty)),
      decreaseAmt: calcSubtotal(r.map((x) => x.decreaseAmt)),
      closingQty: calcSubtotal(r.map((x) => x.closingQty)),
      closingAmt: calcSubtotal(r.map((x) => x.closingAmt)),
      agingTotal: calcSubtotal(r.map((x) => x.agingTotal)),
    }
  })

  const agingMismatch = computed(() =>
    rows.value.filter((r) => Math.abs(r.agingTotal - r.closingAmt) > 0.01),
  )

  /** 品名模糊搜索筛选（Req 5.10） */
  const filteredRows = computed(() => {
    const q = searchText.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter((r) => r.itemName.toLowerCase().includes(q))
  })

  const useVirtualScroll = computed(
    () => rows.value.length > 100 || opts.config.value.sheetCode === 'F2-7',
  )

  function isLongTermRow(r: F2DetailRow): boolean {
    return (r.agingGt3 ?? 0) > 0
  }

  function persist() {
    if (opts.isReadonly.value) return
    const key = dataKey(opts.config.value.sheetCode)
    const item: ChecklistResponse = {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(rows.value),
    }
    opts.allResponses.value.set(key, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function updateRow(id: string, patch: Partial<F2DetailRow>) {
    if (opts.isReadonly.value) return
    const hq = opts.config.value.hasQuantity
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }, hq) : r))
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入品名', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const id = String(Date.now())
      const hq = opts.config.value.hasQuantity
      rows.value = [...rows.value, enrichRow({ ...emptyRow(id, hq), itemName: value }, hq)]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  return {
    activeSegment,
    searchText,
    rows,
    filteredRows,
    totals,
    agingMismatch,
    useVirtualScroll,
    isLongTermRow,
    updateRow,
    addRow,
    removeRow,
  }
}
