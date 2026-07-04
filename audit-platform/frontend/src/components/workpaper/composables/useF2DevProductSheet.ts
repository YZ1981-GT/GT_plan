/**
 * useF2DevProductSheet — F2-10 开发产品明细（35列→5区段）
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcEndAmount, calcSubtotal } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'

export type DevProductSegment = 'basic' | 'land' | 'construction' | 'interest' | 'other'

export interface DevProductRow {
  id: string
  projectName: string
  buildingNo: string
  productType: string
  area: number
  soldArea: number
  units: number
  landOpen: number
  landIn: number
  landOut: number
  buildOpen: number
  buildIn: number
  buildOut: number
  intOpen: number
  intIn: number
  intOut: number
  otherOpen: number
  otherIn: number
  otherOut: number
  transferOut: number
  agingLt1: number
  aging1to2: number
  aging2to3: number
  agingGt3: number
  remark: string
}

const ROWS_KEY = 'F2-10-rows'

function emptyRow(id: string): DevProductRow {
  return {
    id, projectName: '', buildingNo: '', productType: '', area: 0, soldArea: 0, units: 0,
    landOpen: 0, landIn: 0, landOut: 0,
    buildOpen: 0, buildIn: 0, buildOut: 0,
    intOpen: 0, intIn: 0, intOut: 0,
    otherOpen: 0, otherIn: 0, otherOut: 0,
    transferOut: 0,
    agingLt1: 0, aging1to2: 0, aging2to3: 0, agingGt3: 0,
    remark: '',
  }
}

function enrichRow(r: DevProductRow) {
  const landClose = calcEndAmount(r.landOpen, r.landIn, r.landOut)
  const buildClose = calcEndAmount(r.buildOpen, r.buildIn, r.buildOut)
  const intClose = calcEndAmount(r.intOpen, r.intIn, r.intOut)
  const otherClose = calcEndAmount(r.otherOpen, r.otherIn, r.otherOut)
  const totalClose = landClose + buildClose + intClose + otherClose
  const netInventory = totalClose - r.transferOut
  const agingTotal = r.agingLt1 + r.aging1to2 + r.aging2to3 + r.agingGt3
  const agingMismatch = Math.abs(agingTotal - netInventory) > 0.01
  const isLongTerm = r.agingGt3 > 0
  return {
    ...r, landClose, buildClose, intClose, otherClose, totalClose, netInventory,
    agingTotal, agingMismatch, isLongTerm,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): DevProductRow[] {
  const raw = readRowJson(map.get(ROWS_KEY))
  if (!raw) return [enrichRow(emptyRow('1'))]
  try {
    const parsed = JSON.parse(raw) as DevProductRow[]
    return parsed.length ? parsed.map(enrichRow) : [enrichRow(emptyRow('1'))]
  } catch {
    return [enrichRow(emptyRow('1'))]
  }
}

export function useF2DevProductSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const activeSegment = ref<DevProductSegment>('basic')
  const rows = ref<DevProductRow[]>(loadRows(opts.allResponses.value))

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, () => {
    rows.value = loadRows(opts.allResponses.value)
  })

  const enrichedRows = computed(() => rows.value.map(enrichRow))

  const totals = computed(() => {
    const e = enrichedRows.value
    return {
      landClose: calcSubtotal(e.map((r) => r.landClose)),
      buildClose: calcSubtotal(e.map((r) => r.buildClose)),
      intClose: calcSubtotal(e.map((r) => r.intClose)),
      otherClose: calcSubtotal(e.map((r) => r.otherClose)),
      totalClose: calcSubtotal(e.map((r) => r.totalClose)),
      netInventory: calcSubtotal(e.map((r) => r.netInventory)),
      agingTotal: calcSubtotal(e.map((r) => r.agingTotal)),
    }
  })

  const agingMismatchCount = computed(() =>
    enrichedRows.value.filter((r) => r.agingMismatch).length,
  )

  function persist(): void {
    if (opts.isReadonly.value) return
    const item: ChecklistResponse = {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(rows.value),
    }
    opts.allResponses.value.set(ROWS_KEY, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function updateRow(id: string, patch: Partial<DevProductRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增开发产品', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const id = String(Date.now())
      rows.value = [...rows.value, enrichRow({ ...emptyRow(id), projectName: value })]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  return {
    activeSegment,
    enrichedRows,
    totals,
    agingMismatchCount,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2DevProductSheet
