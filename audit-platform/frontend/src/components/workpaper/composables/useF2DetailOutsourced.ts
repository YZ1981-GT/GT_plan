/**
 * useF2DetailOutsourced — F2-7 委托加工物资明细表
 *
 * 对齐源模板（非收发存结构）：
 * 加工单位 / 合同号 / 发出物资名称 · 数量·单价·金额 · 加工费·运杂费·税金 · 加工物资成本 · 库龄
 * 合计 → 减跌价 → 存货净额
 *
 * 跨表：closingAmt = 加工物资成本，供 F2-2 汇总。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { calcUnitPrice, calcSubtotal, parseNum } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import {
  PRESET_SEGMENTS,
  type AgingPreset,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import { remapAgingData, type AgingData } from '@/composables/useAgingMigration'
import type { F2DetailNotePack } from './useF2DetailSheet'

export type F2OutsourcedView = 'cost' | 'aging' | 'full'

export interface F2OutsourcedRow {
  id: string
  processorName: string
  contractNo: string
  materialName: string
  qty: number
  unitPrice: number | ''
  /** 金额 = 数量 × 单价（可手工覆盖后仍以公式重算优先） */
  amount: number
  processingFee: number
  freight: number
  taxInCost: number
  /** 加工物资成本 = 金额 + 加工费 + 运杂费 + 税金 */
  processingCost: number
  aging: AgingData
  agingTotal: number
  /** 跨表兼容 */
  closingAmt: number
  openingAmt: number
  increaseAmt: number
  decreaseAmt: number
  itemName?: string
  agingLt1?: number
  aging1to2?: number
  aging2to3?: number
  agingGt3?: number
}

const SHEET = 'F2-7'
const DATA_KEY = `${SHEET}-rows`
const NOTE_KEY = `${SHEET}-note-pack`
const IMP_KEY = `${SHEET}-impairment-provision`
const CONCLUSION_KEY = `${SHEET}-audit-conclusion`
const F2_AGING_PRESET_KEY = 'f2-aging-preset'
const F2_AGING_CUSTOM_KEY = 'f2-aging-custom'

const LEGACY_AGING = [
  { flat: 'agingLt1', key: 'within1' },
  { flat: 'aging1to2', key: 'y1to2' },
  { flat: 'aging2to3', key: 'y2to3' },
  { flat: 'agingGt3', key: 'over3' },
] as const

function emptyAging(segments: AgingSegment[]): AgingData {
  const a: AgingData = {}
  for (const s of segments) a[s.key] = 0
  return a
}

function labelsToCustomSegments(labels: string[]): AgingSegment[] {
  return labels.map((label, i) => ({
    key: `custom-${i}`,
    label,
    dayFrom: 0,
    dayTo: null,
  }))
}

function emptyRow(id: string, segments: AgingSegment[]): F2OutsourcedRow {
  return {
    id,
    processorName: '',
    contractNo: '',
    materialName: '',
    qty: 0,
    unitPrice: '',
    amount: 0,
    processingFee: 0,
    freight: 0,
    taxInCost: 0,
    processingCost: 0,
    aging: emptyAging(segments),
    agingTotal: 0,
    closingAmt: 0,
    openingAmt: 0,
    increaseAmt: 0,
    decreaseAmt: 0,
  }
}

function migrateAging(raw: Partial<F2OutsourcedRow>, segments: AgingSegment[]): AgingData {
  let base: AgingData = {}
  if (raw.aging && typeof raw.aging === 'object') base = { ...raw.aging }
  for (const { flat, key } of LEGACY_AGING) {
    const flatVal = Number((raw as any)[flat] ?? 0)
    if (flatVal && !Number(base[key] ?? 0)) base[key] = flatVal
  }
  return remapAgingData(base, segments)
}

function enrichRow(r: F2OutsourcedRow, segments: AgingSegment[]): F2OutsourcedRow {
  const qty = parseNum(r.qty)
  const rawUp = r.unitPrice === '' || r.unitPrice == null ? NaN : Number(r.unitPrice)
  let unitPrice: number | '' = Number.isFinite(rawUp) ? rawUp : ''
  let amount = parseNum(r.amount)
  if (qty && unitPrice !== '') {
    amount = Number((qty * Number(unitPrice)).toFixed(2))
  } else if (qty && amount) {
    unitPrice = calcUnitPrice(amount, qty)
  }
  const processingFee = parseNum(r.processingFee)
  const freight = parseNum(r.freight)
  const taxInCost = parseNum(r.taxInCost)
  const processingCost = Number((amount + processingFee + freight + taxInCost).toFixed(2))
  const aging = remapAgingData(r.aging || {}, segments)
  let agingTotal = 0
  for (const s of segments) agingTotal += Number(aging[s.key] ?? 0)

  return {
    ...r,
    qty,
    unitPrice,
    amount,
    processingFee,
    freight,
    taxInCost,
    processingCost,
    aging,
    agingTotal,
    closingAmt: processingCost,
    openingAmt: parseNum(r.openingAmt),
    increaseAmt: parseNum(r.increaseAmt),
    decreaseAmt: parseNum(r.decreaseAmt),
    itemName: r.materialName,
    agingLt1: Number(aging.within1 ?? 0),
    aging1to2: Number(aging.y1to2 ?? 0),
    aging2to3: Number(aging.y2to3 ?? 0),
    agingGt3: Number(aging.over3 ?? aging.over5 ?? 0),
  }
}

function loadRows(map: Map<string, ChecklistResponse>, segments: AgingSegment[]): F2OutsourcedRow[] {
  const raw = readRowJson(map.get(DATA_KEY))
  if (!raw) return [enrichRow(emptyRow('1', segments), segments)]
  try {
    const parsed = JSON.parse(raw) as Partial<F2OutsourcedRow>[]
    if (!Array.isArray(parsed) || !parsed.length) {
      return [enrichRow(emptyRow('1', segments), segments)]
    }
    return parsed.map((r, i) => {
      const aging = migrateAging(r, segments)
      // 旧收发存结构迁移：itemName → materialName；closingAmt → 作为成本兜底
      const materialName = String(r.materialName || r.itemName || '')
      const processingCostHint = parseNum((r as any).processingCost ?? r.closingAmt)
      const amountHint = parseNum((r as any).amount)
      const fee = parseNum((r as any).processingFee)
      const freight = parseNum((r as any).freight)
      const tax = parseNum((r as any).taxInCost)
      // 旧收发存仅有 closingAmt：作为发出物资金额/成本兜底
      const amount = amountHint || (processingCostHint && !(fee || freight || tax) ? processingCostHint : amountHint)
      return enrichRow(
        {
          ...emptyRow(String(r.id || i + 1), segments),
          ...r,
          processorName: String(r.processorName || ''),
          contractNo: String(r.contractNo || ''),
          materialName,
          qty: parseNum((r as any).qty ?? (r as any).closingQty),
          amount,
          processingFee: fee,
          freight,
          taxInCost: tax,
          aging,
        } as F2OutsourcedRow,
        segments,
      )
    })
  } catch {
    return [enrichRow(emptyRow('1', segments), segments)]
  }
}

function readStoredAgingPreset(): { preset: AgingPreset | null; customLabels: string[] } {
  try {
    const saved = localStorage.getItem(F2_AGING_PRESET_KEY) as AgingPreset | null
    if (saved === 'THREE_YEAR' || saved === 'FIVE_YEAR') return { preset: saved, customLabels: [] }
    if (saved === 'CUSTOM') {
      const raw = localStorage.getItem(F2_AGING_CUSTOM_KEY)
      const labels = raw ? JSON.parse(raw) : []
      if (Array.isArray(labels) && labels.length) {
        return { preset: 'CUSTOM', customLabels: labels.map(String) }
      }
    }
  } catch { /* ignore */ }
  return { preset: null, customLabels: [] }
}

function persistItem(map: Map<string, ChecklistResponse>, key: string, remark: string) {
  const item: ChecklistResponse = { item_id: key, conclusion: null, remark }
  map.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

export function useF2DetailOutsourced(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const activeView = ref<F2OutsourcedView>('cost')
  const searchText = ref('')

  const storedInit = readStoredAgingPreset()
  const agingPreset = ref<AgingPreset>(storedInit.preset ?? 'THREE_YEAR')
  const customSegments = ref<AgingSegment[]>(
    storedInit.customLabels.length ? labelsToCustomSegments(storedInit.customLabels) : [],
  )

  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    if (agingPreset.value === 'THREE_YEAR' || agingPreset.value === 'FIVE_YEAR') {
      return PRESET_SEGMENTS[agingPreset.value]
    }
    if (agingPreset.value === 'CUSTOM' && customSegments.value.length) return customSegments.value
    return PRESET_SEGMENTS.THREE_YEAR
  })

  const rows = ref<F2OutsourcedRow[]>(loadRows(opts.allResponses.value, segments.value))
  const impairmentProvision = ref(0)
  const notePack = ref<F2DetailNotePack>({
    valuationMethod: '',
    significantChange: '',
    longAgingReason: '',
    impairmentReason: '',
  })
  const auditConclusion = ref('')

  function hydrateMeta() {
    impairmentProvision.value = Number(opts.allResponses.value.get(IMP_KEY)?.remark || 0) || 0
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
    try {
      const raw = opts.allResponses.value.get(NOTE_KEY)?.remark
      if (raw) notePack.value = { ...notePack.value, ...JSON.parse(raw) }
    } catch { /* ignore */ }
  }
  hydrateMeta()

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.remark,
    () => {
      rows.value = loadRows(opts.allResponses.value, segments.value)
      hydrateMeta()
    },
  )

  watch(segments, (segs) => {
    rows.value = rows.value.map((r) => enrichRow({ ...r, aging: migrateAging(r, segs) }, segs))
  })

  const totals = computed(() => {
    const list = rows.value
    const processingCost = calcSubtotal(list.map((r) => r.processingCost))
    const agingTotal = calcSubtotal(list.map((r) => r.agingTotal))
    return {
      qty: calcSubtotal(list.map((r) => r.qty)),
      amount: calcSubtotal(list.map((r) => r.amount)),
      processingFee: calcSubtotal(list.map((r) => r.processingFee)),
      freight: calcSubtotal(list.map((r) => r.freight)),
      taxInCost: calcSubtotal(list.map((r) => r.taxInCost)),
      processingCost,
      agingTotal,
      agingOk: Math.abs(agingTotal - processingCost) <= 0.01,
      closingAmt: processingCost,
    }
  })

  const netAmt = computed(() => totals.value.processingCost - impairmentProvision.value)

  const agingMismatch = computed(() =>
    rows.value.filter((r) => Math.abs(r.agingTotal - r.processingCost) > 0.01),
  )

  const filteredRows = computed(() => {
    const q = searchText.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter((r) =>
      [r.processorName, r.contractNo, r.materialName].some((x) => String(x || '').toLowerCase().includes(q)),
    )
  })

  const useVirtualScroll = computed(() => true)

  function persistRows() {
    if (opts.isReadonly.value) return
    persistItem(opts.allResponses.value, DATA_KEY, JSON.stringify(rows.value))
  }

  function updateRow(id: string, patch: Partial<F2OutsourcedRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      r.id === id ? enrichRow({ ...r, ...patch }, segments.value) : r,
    )
    persistRows()
  }

  function updateAgingCell(id: string, key: string, value: number) {
    const row = rows.value.find((r) => r.id === id)
    if (!row) return
    updateRow(id, { aging: { ...row.aging, [key]: value } })
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入发出加工物资名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const id = String(Date.now())
      rows.value = [
        ...rows.value,
        enrichRow({ ...emptyRow(id, segments.value), materialName: value }, segments.value),
      ]
      persistRows()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persistRows()
  }

  function persistImpairment(val: number) {
    if (opts.isReadonly.value) return
    impairmentProvision.value = Number(val) || 0
    persistItem(opts.allResponses.value, IMP_KEY, String(impairmentProvision.value))
  }

  function persistNotePack(patch: Partial<F2DetailNotePack>) {
    if (opts.isReadonly.value) return
    notePack.value = { ...notePack.value, ...patch }
    persistItem(opts.allResponses.value, NOTE_KEY, JSON.stringify(notePack.value))
  }

  function persistConclusion(val: string) {
    if (opts.isReadonly.value) return
    auditConclusion.value = val
    persistItem(opts.allResponses.value, CONCLUSION_KEY, val)
  }

  function applyAgingPreset(preset: AgingPreset, customLabels?: string[]): boolean {
    if (preset === 'CUSTOM') {
      const labels = (customLabels || []).map((l) => l.trim()).filter(Boolean)
      if (labels.length < 2) {
        ElMessage.warning('自定义库龄至少需要 2 段')
        return false
      }
      customSegments.value = labelsToCustomSegments(labels)
      agingPreset.value = 'CUSTOM'
      try {
        localStorage.setItem(F2_AGING_PRESET_KEY, 'CUSTOM')
        localStorage.setItem(F2_AGING_CUSTOM_KEY, JSON.stringify(labels))
      } catch { /* ignore */ }
      return true
    }
    agingPreset.value = preset
    try {
      localStorage.setItem(F2_AGING_PRESET_KEY, preset)
      localStorage.removeItem(F2_AGING_CUSTOM_KEY)
    } catch { /* ignore */ }
    return true
  }

  return {
    sheetCode: SHEET,
    activeView,
    searchText,
    rows,
    filteredRows,
    totals,
    netAmt,
    agingMismatch,
    useVirtualScroll,
    segments,
    agingPreset,
    customSegments,
    impairmentProvision,
    notePack,
    auditConclusion,
    updateRow,
    updateAgingCell,
    addRow,
    removeRow,
    persistImpairment,
    persistNotePack,
    persistConclusion,
    applyAgingPreset,
  }
}

export default useF2DetailOutsourced
