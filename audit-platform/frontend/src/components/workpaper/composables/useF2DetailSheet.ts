/**
 * useF2DetailSheet — F2-3~F2-13 通用存货明细表
 *
 * 对齐源模板：
 * - F2-3 等：编码/名称/规格/单位 · 期初·购进·发出·期末 · 库龄 · 品质
 * - F2-4：供货单位/名称及规格/单位 · 期初·购进·转出·期末 · 期后结转 · 库龄 · 品质
 * 合计 → 减：跌价准备 → 净额；四问审计说明（按 noteProfile）
 *
 * 视图：收发存 | 库龄 | 完整（宽表；默认收发存，避免统一改分段 Tab 后丢失勾稽感）
 * 库龄：与 F2-5 同口径（THREE_YEAR / FIVE_YEAR / CUSTOM + 旧 flat 字段迁移）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calcEndAmount,
  calcEndBalance,
  calcUnitPrice,
  calcSubtotal,
} from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import {
  PRESET_SEGMENTS,
  type AgingPreset,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import { remapAgingData, type AgingData } from '@/composables/useAgingMigration'
import type { F2DetailSheetConfig } from '../f2/detail/f2DetailSheetConfigs'

/** F2 明细表四问审计说明包（字段名沿用；F2-4 第1问=期后入库情况） */
export interface F2DetailNotePack {
  valuationMethod: string
  significantChange: string
  longAgingReason: string
  impairmentReason: string
}

export type F2DetailView = 'movement' | 'aging' | 'full'

export interface F2DetailRow {
  id: string
  /** 存货编码；在途表可空 */
  itemCode: string
  /** 供货单位（F2-4）/ 购货单位（F2-9） */
  supplier: string
  itemName: string
  spec: string
  unit: string
  openingQty: number
  openingAmt: number
  increaseQty: number
  increaseAmt: number
  decreaseQty: number
  decreaseAmt: number
  closingQty: number
  closingAmt: number
  /** F2-4 期后结转 */
  postPeriodQty: number
  postPeriodAmt: number
  postPeriodUnitPrice: number | ''
  openingUnitPrice: number | ''
  increaseUnitPrice: number | ''
  decreaseUnitPrice: number | ''
  unitPrice: number | ''
  aging: AgingData
  agingTotal: number
  qualityStatus: string
  extra?: string
  /** F2-8 在手订单 */
  hasOpenOrder: string
  orderNo: string
  salesUnitPrice: number | ''
  /** 兼容旧持久化 / 跨表测试 */
  agingLt1?: number
  aging1to2?: number
  aging2to3?: number
  agingGt3?: number
}

export interface F2DetailTotals {
  openingQty: number
  openingAmt: number
  increaseQty: number
  increaseAmt: number
  decreaseQty: number
  decreaseAmt: number
  closingQty: number
  closingAmt: number
  postPeriodQty: number
  postPeriodAmt: number
  agingTotal: number
  agingOk: boolean
}

const F2_AGING_PRESET_KEY = 'f2-aging-preset'
const F2_AGING_CUSTOM_KEY = 'f2-aging-custom'

const LEGACY_AGING = [
  { flat: 'agingLt1', key: 'within1' },
  { flat: 'aging1to2', key: 'y1to2' },
  { flat: 'aging2to3', key: 'y2to3' },
  { flat: 'agingGt3', key: 'over3' },
] as const

function dataKey(sheetCode: string): string {
  return `${sheetCode}-rows`
}
function notePackKey(sheetCode: string): string {
  return `${sheetCode}-note-pack`
}
function impairmentKey(sheetCode: string): string {
  return `${sheetCode}-impairment-provision`
}
function conclusionKey(sheetCode: string): string {
  return `${sheetCode}-audit-conclusion`
}
function salesLedgerKey(sheetCode: string): string {
  return `${sheetCode}-sales-ledger-qty`
}

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

function emptyRow(id: string, segments: AgingSegment[]): F2DetailRow {
  return {
    id,
    itemCode: '',
    supplier: '',
    itemName: '',
    spec: '',
    unit: '',
    openingQty: 0,
    openingAmt: 0,
    increaseQty: 0,
    increaseAmt: 0,
    decreaseQty: 0,
    decreaseAmt: 0,
    closingQty: 0,
    closingAmt: 0,
    postPeriodQty: 0,
    postPeriodAmt: 0,
    postPeriodUnitPrice: '',
    openingUnitPrice: '',
    increaseUnitPrice: '',
    decreaseUnitPrice: '',
    unitPrice: '',
    aging: emptyAging(segments),
    agingTotal: 0,
    qualityStatus: '',
    hasOpenOrder: '',
    orderNo: '',
    salesUnitPrice: '',
  }
}

function migrateAging(raw: Partial<F2DetailRow>, segments: AgingSegment[]): AgingData {
  let base: AgingData = {}
  if (raw.aging && typeof raw.aging === 'object') {
    base = { ...raw.aging }
  }
  // 旧版 flat 字段：若 aging 对象缺段或全 0，用 flat 补齐
  for (const { flat, key } of LEGACY_AGING) {
    const flatVal = Number((raw as any)[flat] ?? 0)
    if (flatVal && !Number(base[key] ?? 0)) {
      base[key] = flatVal
    }
  }
  return remapAgingData(base, segments)
}

function enrichRow(r: F2DetailRow, hasQuantity: boolean, segments: AgingSegment[]): F2DetailRow {
  const closingQty = hasQuantity
    ? calcEndBalance(r.openingQty, r.increaseQty, r.decreaseQty)
    : 0
  const closingAmt = calcEndAmount(r.openingAmt, r.increaseAmt, r.decreaseAmt)
  const aging = remapAgingData(r.aging || {}, segments)
  let agingTotal = 0
  for (const s of segments) agingTotal += Number(aging[s.key] ?? 0)
  const postPeriodQty = Number(r.postPeriodQty) || 0
  const postPeriodAmt = Number(r.postPeriodAmt) || 0
  return {
    ...r,
    supplier: String(r.supplier || ''),
    closingQty,
    closingAmt,
    postPeriodQty,
    postPeriodAmt,
    postPeriodUnitPrice: hasQuantity ? calcUnitPrice(postPeriodAmt, postPeriodQty) : '',
    openingUnitPrice: hasQuantity ? calcUnitPrice(r.openingAmt, r.openingQty) : '',
    increaseUnitPrice: hasQuantity ? calcUnitPrice(r.increaseAmt, r.increaseQty) : '',
    decreaseUnitPrice: hasQuantity ? calcUnitPrice(r.decreaseAmt, r.decreaseQty) : '',
    unitPrice: hasQuantity ? calcUnitPrice(closingAmt, closingQty) : calcUnitPrice(closingAmt, 1),
    aging,
    agingTotal,
    agingLt1: Number(aging.within1 ?? 0),
    aging1to2: Number(aging.y1to2 ?? 0),
    aging2to3: Number(aging.y2to3 ?? 0),
    agingGt3: Number(aging.over3 ?? aging.over5 ?? 0),
  }
}

function loadRows(
  map: Map<string, ChecklistResponse>,
  sheetCode: string,
  hasQuantity: boolean,
  segments: AgingSegment[],
): F2DetailRow[] {
  const raw = readRowJson(map.get(dataKey(sheetCode)))
  if (!raw) return [enrichRow(emptyRow('1', segments), hasQuantity, segments)]
  try {
    const parsed = JSON.parse(raw) as Partial<F2DetailRow>[]
    if (!Array.isArray(parsed) || !parsed.length) {
      return [enrichRow(emptyRow('1', segments), hasQuantity, segments)]
    }
    return parsed.map((r, i) => {
      const aging = migrateAging(r, segments)
      return enrichRow(
        {
          ...emptyRow(String(r.id || i + 1), segments),
          ...r,
          itemCode: String(r.itemCode || ''),
          supplier: String(r.supplier || r.itemCode || ''),
          itemName: String(r.itemName || ''),
          spec: String(r.spec || ''),
          unit: String(r.unit || ''),
          qualityStatus: String(r.qualityStatus || ''),
          hasOpenOrder: String(r.hasOpenOrder || ''),
          orderNo: String(r.orderNo || ''),
          salesUnitPrice: r.salesUnitPrice === '' || r.salesUnitPrice == null
            ? ''
            : Number(r.salesUnitPrice),
          postPeriodQty: Number(r.postPeriodQty) || 0,
          postPeriodAmt: Number(r.postPeriodAmt) || 0,
          aging,
        } as F2DetailRow,
        hasQuantity,
        segments,
      )
    })
  } catch {
    return [enrichRow(emptyRow('1', segments), hasQuantity, segments)]
  }
}

function readStoredAgingPreset(): { preset: AgingPreset | null; customLabels: string[] } {
  try {
    const saved = localStorage.getItem(F2_AGING_PRESET_KEY) as AgingPreset | null
    if (saved === 'THREE_YEAR' || saved === 'FIVE_YEAR') {
      return { preset: saved, customLabels: [] }
    }
    if (saved === 'CUSTOM') {
      const raw = localStorage.getItem(F2_AGING_CUSTOM_KEY)
      const labels = raw ? JSON.parse(raw) : []
      if (Array.isArray(labels) && labels.length > 0) {
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

export function useF2DetailSheet(opts: {
  config: Ref<F2DetailSheetConfig>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const activeView = ref<F2DetailView>('movement')
  /** @deprecated 旧分段 Tab；保留别名以免外部引用断裂 */
  const activeSegment = activeView as unknown as Ref<'opening' | 'movement' | 'closing' | 'aging'>
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
    if (agingPreset.value === 'CUSTOM' && customSegments.value.length) {
      return customSegments.value
    }
    return PRESET_SEGMENTS.THREE_YEAR
  })

  const rows = ref<F2DetailRow[]>(
    loadRows(
      opts.allResponses.value,
      opts.config.value.sheetCode,
      opts.config.value.hasQuantity,
      segments.value,
    ),
  )

  const impairmentProvision = ref(0)
  const salesLedgerQty = ref(0)
  const notePack = ref<F2DetailNotePack>({
    valuationMethod: '',
    significantChange: '',
    longAgingReason: '',
    impairmentReason: '',
  })
  const auditConclusion = ref('')

  function hydrateMeta(sheetCode: string) {
    const map = opts.allResponses.value
    impairmentProvision.value = Number(map.get(impairmentKey(sheetCode))?.remark || 0) || 0
    salesLedgerQty.value = Number(map.get(salesLedgerKey(sheetCode))?.remark || 0) || 0
    auditConclusion.value = map.get(conclusionKey(sheetCode))?.remark ?? ''
    try {
      const raw = map.get(notePackKey(sheetCode))?.remark
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<F2DetailNotePack>
        notePack.value = {
          valuationMethod: parsed.valuationMethod || '',
          significantChange: parsed.significantChange || '',
          longAgingReason: parsed.longAgingReason || '',
          impairmentReason: parsed.impairmentReason || '',
        }
        return
      }
    } catch { /* ignore */ }
    // 兼容旧单文本审计说明
    const legacy = map.get(`${sheetCode}-audit-note`)?.remark || ''
    notePack.value = {
      valuationMethod: legacy,
      significantChange: '',
      longAgingReason: '',
      impairmentReason: '',
    }
  }

  hydrateMeta(opts.config.value.sheetCode)

  watch(
    () => opts.config.value.sheetCode,
    (code) => {
      rows.value = loadRows(
        opts.allResponses.value,
        code,
        opts.config.value.hasQuantity,
        segments.value,
      )
      hydrateMeta(code)
    },
  )

  watch(segments, (segs) => {
    const hq = opts.config.value.hasQuantity
    rows.value = rows.value.map((r) =>
      enrichRow({ ...r, aging: migrateAging(r, segs) }, hq, segs),
    )
  })

  const totals: ComputedRef<F2DetailTotals> = computed(() => {
    const r = rows.value
    const closingAmt = calcSubtotal(r.map((x) => x.closingAmt))
    const agingTotal = calcSubtotal(r.map((x) => x.agingTotal))
    return {
      openingQty: calcSubtotal(r.map((x) => x.openingQty)),
      openingAmt: calcSubtotal(r.map((x) => x.openingAmt)),
      increaseQty: calcSubtotal(r.map((x) => x.increaseQty)),
      increaseAmt: calcSubtotal(r.map((x) => x.increaseAmt)),
      decreaseQty: calcSubtotal(r.map((x) => x.decreaseQty)),
      decreaseAmt: calcSubtotal(r.map((x) => x.decreaseAmt)),
      closingQty: calcSubtotal(r.map((x) => x.closingQty)),
      closingAmt,
      postPeriodQty: calcSubtotal(r.map((x) => x.postPeriodQty)),
      postPeriodAmt: calcSubtotal(r.map((x) => x.postPeriodAmt)),
      agingTotal,
      agingOk: Math.abs(agingTotal - closingAmt) <= 0.01,
    }
  })

  const netAmt = computed(() => totals.value.closingAmt - impairmentProvision.value)

  /** 发出数量合计 − 销售台账出库数量 */
  const salesLedgerDiff = computed(() => totals.value.decreaseQty - salesLedgerQty.value)

  const agingMismatch = computed(() =>
    rows.value.filter((r) => Math.abs(r.agingTotal - r.closingAmt) > 0.01),
  )

  const filteredRows = computed(() => {
    const q = searchText.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter((r) =>
      [r.itemCode, r.supplier, r.itemName, r.spec].some((x) => String(x || '').toLowerCase().includes(q)),
    )
  })

  const useVirtualScroll = computed(
    () => rows.value.length > 100 || opts.config.value.sheetCode === 'F2-7',
  )

  function isLongTermRow(r: F2DetailRow): boolean {
    return Number(r.agingGt3 ?? r.aging?.over3 ?? r.aging?.over5 ?? 0) > 0
  }

  function persistRows() {
    if (opts.isReadonly.value) return
    const key = dataKey(opts.config.value.sheetCode)
    persistItem(opts.allResponses.value, key, JSON.stringify(rows.value))
  }

  function updateRow(id: string, patch: Partial<F2DetailRow>) {
    if (opts.isReadonly.value) return
    const hq = opts.config.value.hasQuantity
    const segs = segments.value
    rows.value = rows.value.map((r) =>
      r.id === id ? enrichRow({ ...r, ...patch }, hq, segs) : r,
    )
    persistRows()
  }

  function updateAgingCell(id: string, key: string, value: number) {
    if (opts.isReadonly.value) return
    const row = rows.value.find((r) => r.id === id)
    if (!row) return
    updateRow(id, { aging: { ...row.aging, [key]: value } })
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    const inTransit = opts.config.value.identityMode === 'inTransit'
    try {
      const { value } = await ElMessageBox.prompt(
        inTransit ? '请输入采购物资名称及规格' : '请输入存货名称',
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
        },
      )
      const id = String(Date.now())
      const hq = opts.config.value.hasQuantity
      rows.value = [
        ...rows.value,
        enrichRow({ ...emptyRow(id, segments.value), itemName: value }, hq, segments.value),
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
    persistItem(
      opts.allResponses.value,
      impairmentKey(opts.config.value.sheetCode),
      String(impairmentProvision.value),
    )
  }

  function persistSalesLedgerQty(val: number) {
    if (opts.isReadonly.value) return
    salesLedgerQty.value = Number(val) || 0
    persistItem(
      opts.allResponses.value,
      salesLedgerKey(opts.config.value.sheetCode),
      String(salesLedgerQty.value),
    )
  }

  function persistNotePack(patch: Partial<F2DetailNotePack>) {
    if (opts.isReadonly.value) return
    notePack.value = { ...notePack.value, ...patch }
    persistItem(
      opts.allResponses.value,
      notePackKey(opts.config.value.sheetCode),
      JSON.stringify(notePack.value),
    )
  }

  function persistConclusion(val: string) {
    if (opts.isReadonly.value) return
    auditConclusion.value = val
    persistItem(
      opts.allResponses.value,
      conclusionKey(opts.config.value.sheetCode),
      val,
    )
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
    activeView,
    activeSegment,
    searchText,
    rows,
    filteredRows,
    totals,
    netAmt,
    salesLedgerQty,
    salesLedgerDiff,
    agingMismatch,
    useVirtualScroll,
    segments,
    agingPreset,
    customSegments,
    impairmentProvision,
    notePack,
    auditConclusion,
    isLongTermRow,
    updateRow,
    updateAgingCell,
    addRow,
    removeRow,
    persistImpairment,
    persistSalesLedgerQty,
    persistNotePack,
    persistConclusion,
    applyAgingPreset,
  }
}
