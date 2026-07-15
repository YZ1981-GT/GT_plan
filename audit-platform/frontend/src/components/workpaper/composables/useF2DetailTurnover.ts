/**
 * useF2DetailTurnover — F2-5 周转材料/低值易耗品/包装物
 *
 * 对齐源模板分组骨架：
 * （一）周转材料 → 明细 → 小计
 * （二）低值易耗品 → 明细 → 小计
 * （三）包装物 → 四用途子类 → 包装物小计
 * 合计 → 减跌价 → 净额
 *
 * 持久化仍走 F2-5-rows（行上带 groupKey + category），供 F2-2 汇总兼容。
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
import type { F2DetailNotePack } from './useF2DetailSheet'

export type F2TurnoverGroupKey =
  | 'revolving'
  | 'lowValue'
  | 'packProd'
  | 'packSoldIncl'
  | 'packSoldSep'
  | 'packRent'

export interface F2TurnoverGroupDef {
  key: F2TurnoverGroupKey
  /** 大类：A/B 独立；P 归包装物 */
  section: 'A' | 'B' | 'P'
  title: string
  /** 写入 category，供汇总/搜索 */
  categoryLabel: string
}

export const F2_TURNOVER_GROUPS: F2TurnoverGroupDef[] = [
  { key: 'revolving', section: 'A', title: '（一）周转材料', categoryLabel: '周转材料' },
  { key: 'lowValue', section: 'B', title: '（二）低值易耗品', categoryLabel: '低值易耗品' },
  {
    key: 'packProd',
    section: 'P',
    title: '1. 生产过程中用于包装产品作为产品组成部分的包装物',
    categoryLabel: '包装物-生产组成',
  },
  {
    key: 'packSoldIncl',
    section: 'P',
    title: '2. 随同商品出售而不单独计价的包装物',
    categoryLabel: '包装物-售出不单独计价',
  },
  {
    key: 'packSoldSep',
    section: 'P',
    title: '3. 随同商品出售而单独计价的包装物',
    categoryLabel: '包装物-售出单独计价',
  },
  {
    key: 'packRent',
    section: 'P',
    title: '4. 出租或出借给购买单位使用的包装物',
    categoryLabel: '包装物-出租出借',
  },
]

export type F2TurnoverView = 'movement' | 'aging' | 'full'

export interface F2TurnoverRow {
  id: string
  groupKey: F2TurnoverGroupKey
  category: string
  itemCode: string
  itemName: string
  unit: string
  openingQty: number
  openingAmt: number
  increaseQty: number
  increaseAmt: number
  decreaseQty: number
  decreaseAmt: number
  closingQty: number
  closingAmt: number
  openingUnitPrice: number | ''
  increaseUnitPrice: number | ''
  decreaseUnitPrice: number | ''
  unitPrice: number | ''
  aging: AgingData
  agingTotal: number
  qualityStatus: string
  agingLt1?: number
  aging1to2?: number
  aging2to3?: number
  agingGt3?: number
}

export interface F2TurnoverAmtBucket {
  openingQty: number
  openingAmt: number
  increaseQty: number
  increaseAmt: number
  decreaseQty: number
  decreaseAmt: number
  closingQty: number
  closingAmt: number
  agingTotal: number
  agingOk: boolean
}

const SHEET = 'F2-5'
const DATA_KEY = `${SHEET}-rows`
const NOTE_KEY = `${SHEET}-note-pack`
const IMP_KEY = `${SHEET}-impairment-provision`
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

function resolveGroupKey(raw: Partial<F2TurnoverRow>): F2TurnoverGroupKey {
  const gk = raw.groupKey
  if (gk && F2_TURNOVER_GROUPS.some((g) => g.key === gk)) return gk
  const cat = String(raw.category || '')
  if (/低值/.test(cat)) return 'lowValue'
  if (/生产|组成部分/.test(cat)) return 'packProd'
  if (/不单独计价/.test(cat)) return 'packSoldIncl'
  if (/单独计价/.test(cat)) return 'packSoldSep'
  if (/出租|出借/.test(cat)) return 'packRent'
  if (/包装/.test(cat)) return 'packProd'
  return 'revolving'
}

function groupDef(key: F2TurnoverGroupKey): F2TurnoverGroupDef {
  return F2_TURNOVER_GROUPS.find((g) => g.key === key)!
}

function emptyRow(id: string, groupKey: F2TurnoverGroupKey, segments: AgingSegment[]): F2TurnoverRow {
  const g = groupDef(groupKey)
  return {
    id,
    groupKey,
    category: g.categoryLabel,
    itemCode: '',
    itemName: '',
    unit: '',
    openingQty: 0,
    openingAmt: 0,
    increaseQty: 0,
    increaseAmt: 0,
    decreaseQty: 0,
    decreaseAmt: 0,
    closingQty: 0,
    closingAmt: 0,
    openingUnitPrice: '',
    increaseUnitPrice: '',
    decreaseUnitPrice: '',
    unitPrice: '',
    aging: emptyAging(segments),
    agingTotal: 0,
    qualityStatus: '',
  }
}

function enrichRow(r: F2TurnoverRow, segments: AgingSegment[]): F2TurnoverRow {
  const groupKey = resolveGroupKey(r)
  const closingQty = calcEndBalance(r.openingQty, r.increaseQty, r.decreaseQty)
  const closingAmt = calcEndAmount(r.openingAmt, r.increaseAmt, r.decreaseAmt)
  const aging = remapAgingData(r.aging || {}, segments)
  let agingTotal = 0
  for (const s of segments) agingTotal += Number(aging[s.key] ?? 0)
  return {
    ...r,
    groupKey,
    category: groupDef(groupKey).categoryLabel,
    closingQty,
    closingAmt,
    openingUnitPrice: calcUnitPrice(r.openingAmt, r.openingQty),
    increaseUnitPrice: calcUnitPrice(r.increaseAmt, r.increaseQty),
    decreaseUnitPrice: calcUnitPrice(r.decreaseAmt, r.decreaseQty),
    unitPrice: calcUnitPrice(closingAmt, closingQty),
    aging,
    agingTotal,
    agingLt1: Number(aging.within1 ?? 0),
    aging1to2: Number(aging.y1to2 ?? 0),
    aging2to3: Number(aging.y2to3 ?? 0),
    agingGt3: Number(aging.over3 ?? aging.over5 ?? 0),
  }
}

function migrateAging(raw: Partial<F2TurnoverRow>, segments: AgingSegment[]): AgingData {
  let base: AgingData = {}
  if (raw.aging && typeof raw.aging === 'object') {
    base = { ...raw.aging }
  } else {
    for (const { flat, key } of LEGACY_AGING) {
      const v = Number((raw as any)[flat] ?? 0)
      if (v) base[key] = v
    }
  }
  return remapAgingData(base, segments)
}

function sumRows(list: F2TurnoverRow[]): F2TurnoverAmtBucket {
  const closingAmt = calcSubtotal(list.map((r) => r.closingAmt))
  const agingTotal = calcSubtotal(list.map((r) => r.agingTotal))
  return {
    openingQty: calcSubtotal(list.map((r) => r.openingQty)),
    openingAmt: calcSubtotal(list.map((r) => r.openingAmt)),
    increaseQty: calcSubtotal(list.map((r) => r.increaseQty)),
    increaseAmt: calcSubtotal(list.map((r) => r.increaseAmt)),
    decreaseQty: calcSubtotal(list.map((r) => r.decreaseQty)),
    decreaseAmt: calcSubtotal(list.map((r) => r.decreaseAmt)),
    closingQty: calcSubtotal(list.map((r) => r.closingQty)),
    closingAmt,
    agingTotal,
    agingOk: Math.abs(agingTotal - closingAmt) <= 0.01,
  }
}

function loadRows(map: Map<string, ChecklistResponse>, segments: AgingSegment[]): F2TurnoverRow[] {
  const raw = readRowJson(map.get(DATA_KEY))
  if (!raw) {
    return F2_TURNOVER_GROUPS.map((g, i) => enrichRow(emptyRow(String(i + 1), g.key, segments), segments))
  }
  try {
    const parsed = JSON.parse(raw) as Partial<F2TurnoverRow>[]
    if (!Array.isArray(parsed) || !parsed.length) {
      return F2_TURNOVER_GROUPS.map((g, i) => enrichRow(emptyRow(String(i + 1), g.key, segments), segments))
    }
    return parsed.map((r, i) => {
      const groupKey = resolveGroupKey(r)
      const aging = migrateAging(r, segments)
      return enrichRow(
        {
          ...emptyRow(String(r.id || i + 1), groupKey, segments),
          ...r,
          groupKey,
          itemCode: String(r.itemCode || ''),
          itemName: String(r.itemName || r.spec || ''),
          unit: String(r.unit || ''),
          qualityStatus: String(r.qualityStatus || ''),
          aging,
        } as F2TurnoverRow,
        segments,
      )
    })
  } catch {
    return F2_TURNOVER_GROUPS.map((g, i) => enrichRow(emptyRow(String(i + 1), g.key, segments), segments))
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

export function useF2DetailTurnover(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const activeView = ref<F2TurnoverView>('movement')
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

  const rows = ref<F2TurnoverRow[]>(loadRows(opts.allResponses.value, segments.value))

  const impairmentProvision = ref(0)
  const notePack = ref<F2DetailNotePack>({
    valuationMethod: '',
    significantChange: '',
    longAgingReason: '',
    impairmentReason: '',
  })

  function hydrateMeta(): void {
    const imp = opts.allResponses.value.get(IMP_KEY)?.remark
    impairmentProvision.value = Number(imp || 0) || 0
    const raw = opts.allResponses.value.get(NOTE_KEY)?.remark
    if (raw) {
      try {
        notePack.value = { ...notePack.value, ...JSON.parse(raw) }
      } catch { /* keep */ }
    } else {
      notePack.value = {
        valuationMethod: '',
        significantChange: '',
        longAgingReason: '',
        impairmentReason: '',
      }
    }
  }
  hydrateMeta()

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.remark,
    () => {
      rows.value = loadRows(opts.allResponses.value, segments.value)
      hydrateMeta()
    },
  )

  function persistItem(itemId: string, remark: string): void {
    const item: ChecklistResponse = { item_id: itemId, conclusion: null, remark }
    opts.allResponses.value.set(itemId, item)
    window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function persist(): void {
    if (opts.isReadonly.value) return
    persistItem(DATA_KEY, JSON.stringify(rows.value))
  }

  function persistImpairment(val: number): void {
    if (opts.isReadonly.value) return
    impairmentProvision.value = Number(val) || 0
    persistItem(IMP_KEY, String(impairmentProvision.value))
  }

  function persistNotePack(patch: Partial<F2DetailNotePack>): void {
    if (opts.isReadonly.value) return
    notePack.value = { ...notePack.value, ...patch }
    persistItem(NOTE_KEY, JSON.stringify(notePack.value))
  }

  function applyAgingPreset(val: AgingPreset, customLabels?: string[]): boolean {
    if (val === 'CUSTOM') {
      const labels = (customLabels ?? []).map((l) => l.trim()).filter(Boolean)
      if (!labels.length) {
        ElMessage.warning('至少需要1个库龄段')
        return false
      }
      customSegments.value = labelsToCustomSegments(labels)
      agingPreset.value = 'CUSTOM'
      try {
        localStorage.setItem(F2_AGING_PRESET_KEY, 'CUSTOM')
        localStorage.setItem(F2_AGING_CUSTOM_KEY, JSON.stringify(labels))
      } catch { /* ignore */ }
    } else {
      agingPreset.value = val
      try {
        localStorage.setItem(F2_AGING_PRESET_KEY, val)
        localStorage.removeItem(F2_AGING_CUSTOM_KEY)
      } catch { /* ignore */ }
    }
    const segs = segments.value
    rows.value = rows.value.map((r) => enrichRow({
      ...r,
      aging: remapAgingData(r.aging || {}, segs),
    }, segs))
    persist()
    return true
  }

  function rowsOf(key: F2TurnoverGroupKey): F2TurnoverRow[] {
    const q = searchText.value.trim().toLowerCase()
    return rows.value.filter((r) => {
      if (r.groupKey !== key) return false
      if (!q) return true
      return r.itemName.toLowerCase().includes(q)
        || r.itemCode.toLowerCase().includes(q)
        || r.category.toLowerCase().includes(q)
    })
  }

  const groupTotals = computed(() => {
    const map = {} as Record<F2TurnoverGroupKey, F2TurnoverAmtBucket>
    for (const g of F2_TURNOVER_GROUPS) {
      map[g.key] = sumRows(rows.value.filter((r) => r.groupKey === g.key))
    }
    return map
  })

  const packagingTotal = computed(() =>
    sumRows(rows.value.filter((r) => groupDef(r.groupKey).section === 'P')),
  )

  const sectionATotal = computed(() => groupTotals.value.revolving)
  const sectionBTotal = computed(() => groupTotals.value.lowValue)

  const grandTotal = computed(() => sumRows(rows.value))

  const netAmt = computed(() => grandTotal.value.closingAmt - impairmentProvision.value)

  const agingMismatchCount = computed(() =>
    rows.value.filter((r) => Math.abs(r.agingTotal - r.closingAmt) > 0.01).length,
  )

  function updateRow(id: string, patch: Partial<F2TurnoverRow>): void {
    if (opts.isReadonly.value) return
    const segs = segments.value
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, ...patch }
      if (patch.aging) next.aging = remapAgingData({ ...r.aging, ...patch.aging }, segs)
      if (patch.groupKey) next.category = groupDef(patch.groupKey).categoryLabel
      return enrichRow(next, segs)
    })
    persist()
  }

  function updateAgingCell(id: string, segKey: string, value: number): void {
    const row = rows.value.find((r) => r.id === id)
    if (!row) return
    updateRow(id, { aging: { ...row.aging, [segKey]: Number(value) || 0 } })
  }

  async function addRow(groupKey: F2TurnoverGroupKey): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入名称及规格', '新增明细', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const id = String(Date.now())
      const segs = segments.value
      rows.value = [
        ...rows.value,
        enrichRow({ ...emptyRow(id, groupKey, segs), itemName: value }, segs),
      ]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    const row = rows.value.find((r) => r.id === id)
    if (!row) return
    const peers = rows.value.filter((r) => r.groupKey === row.groupKey)
    if (peers.length <= 1) {
      ElMessage.warning('每个分组至少保留一行')
      return
    }
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  return {
    sheetCode: SHEET,
    groups: F2_TURNOVER_GROUPS,
    activeView,
    searchText,
    rows,
    rowsOf,
    segments,
    agingPreset,
    customSegments,
    applyAgingPreset,
    groupTotals,
    packagingTotal,
    sectionATotal,
    sectionBTotal,
    grandTotal,
    netAmt,
    impairmentProvision,
    persistImpairment,
    notePack,
    persistNotePack,
    agingMismatchCount,
    updateRow,
    updateAgingCell,
    addRow,
    removeRow,
  }
}
