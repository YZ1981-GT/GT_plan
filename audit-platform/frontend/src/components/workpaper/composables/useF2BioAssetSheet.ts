/**
 * useF2BioAssetSheet — F2-13 消耗性生物资产明细
 * 对齐 Excel：（一）原值收发存+库龄 ·（二）跌价准备 ·（三）净值
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcEndAmount,
  calcEndBalance,
  calcUnitPrice,
  calcSubtotal,
} from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import { PRESET_SEGMENTS, type AgingPreset, type AgingSegment } from '@/composables/useAgingConfig'
import { remapAgingData, type AgingData } from '@/composables/useAgingMigration'

export type BioAssetView = 'gross' | 'impairment' | 'net'

export interface BioAssetNotePack {
  auditNote: string
}

export interface BioAssetRow {
  id: string
  itemName: string
  variety: string
  unit: string
  openQty: number
  openAmt: number
  incQty: number
  incAmt: number
  decQty: number
  decAmt: number
  aging: AgingData
  agingTotal: number
  status: string
  /** 跌价未审 */
  impOpen: number
  impInc: number
  impDec: number
  /** 账项/重分类调整 */
  impAdjReclass: number
  impAdjInc: number
  impAdjDec: number
  agingLt1?: number
  aging1to2?: number
  aging2to3?: number
  agingGt3?: number
}

export interface BioAssetEnriched extends BioAssetRow {
  openUnitPrice: number | ''
  incUnitPrice: number | ''
  decUnitPrice: number | ''
  closeQty: number
  closeAmt: number
  closeUnitPrice: number | ''
  agingOk: boolean
  impClose: number
  impAudOpen: number
  impAudInc: number
  impAudDec: number
  impAudClose: number
  netOpenQty: number
  netOpenAmt: number
  netOpenUnit: number | ''
  netCloseQty: number
  netCloseAmt: number
  netCloseUnit: number | ''
}

export const BIO_ASSET_STATUS = ['正常', '停建', '毁损', '报废', '其他'] as const

const ROWS_KEY = 'F2-13-rows'
const NOTE_KEY = 'F2-13-note-pack'
const CONCLUSION_KEY = 'F2-13-audit-conclusion'

const LEGACY_AGING = [
  { flat: 'agingLt1', key: 'within1' },
  { flat: 'aging1to2', key: 'y1to2' },
  { flat: 'aging2to3', key: 'y2to3' },
  { flat: 'agingGt3', key: 'over3' },
] as const

function emptyNotes(): BioAssetNotePack {
  return { auditNote: '' }
}

function emptyAging(segments: AgingSegment[]): AgingData {
  const a: AgingData = {}
  for (const s of segments) a[s.key] = 0
  return a
}

function emptyRow(id: string, segments: AgingSegment[]): BioAssetRow {
  return {
    id,
    itemName: '',
    variety: '',
    unit: '',
    openQty: 0,
    openAmt: 0,
    incQty: 0,
    incAmt: 0,
    decQty: 0,
    decAmt: 0,
    aging: emptyAging(segments),
    agingTotal: 0,
    status: '',
    impOpen: 0,
    impInc: 0,
    impDec: 0,
    impAdjReclass: 0,
    impAdjInc: 0,
    impAdjDec: 0,
  }
}

function migrateAging(raw: Partial<BioAssetRow>, segments: AgingSegment[]): AgingData {
  let base: AgingData = {}
  if (raw.aging && typeof raw.aging === 'object') base = { ...raw.aging }
  for (const { flat, key } of LEGACY_AGING) {
    const flatVal = Number((raw as any)[flat] ?? 0)
    if (flatVal && !Number(base[key] ?? 0)) base[key] = flatVal
  }
  return remapAgingData(base, segments)
}

function migrateLegacy(raw: Record<string, unknown>, segments: AgingSegment[]): Partial<BioAssetRow> {
  if (raw.openAmt != null || raw.variety != null) return raw as Partial<BioAssetRow>
  if (raw.openingAmt == null && raw.itemName == null) return raw as Partial<BioAssetRow>
  return {
    itemName: String(raw.itemName || ''),
    variety: String(raw.spec || ''),
    unit: String(raw.unit || ''),
    openQty: Number(raw.openingQty) || 0,
    openAmt: Number(raw.openingAmt) || 0,
    incQty: Number(raw.increaseQty) || 0,
    incAmt: Number(raw.increaseAmt) || 0,
    decQty: Number(raw.decreaseQty) || 0,
    decAmt: Number(raw.decreaseAmt) || 0,
    aging: migrateAging(raw as Partial<BioAssetRow>, segments),
    status: String(raw.qualityStatus || ''),
  }
}

export function normalizeBioAssetRow(
  partial: Partial<BioAssetRow> & { id?: string },
  segments: AgingSegment[] = PRESET_SEGMENTS.THREE_YEAR,
): BioAssetRow {
  const migrated = migrateLegacy(partial as Record<string, unknown>, segments)
  const base = { ...emptyRow(partial.id || '1', segments), ...migrated, id: partial.id || '1' }
  base.aging = migrateAging(base, segments)
  return base
}

export function enrichRow(r: BioAssetRow, segments: AgingSegment[]): BioAssetEnriched {
  const closeQty = calcEndBalance(r.openQty, r.incQty, r.decQty)
  const closeAmt = calcEndAmount(r.openAmt, r.incAmt, r.decAmt)
  const aging = remapAgingData(r.aging || {}, segments)
  let agingTotal = 0
  for (const s of segments) agingTotal += Number(aging[s.key] ?? 0)

  const impClose = calcEndAmount(r.impOpen, r.impInc, r.impDec)
  const impAudOpen = r.impOpen + r.impAdjReclass
  const impAudInc = r.impInc + r.impAdjInc
  const impAudDec = r.impDec + r.impAdjDec
  const impAudClose = calcEndAmount(impAudOpen, impAudInc, impAudDec)

  const netOpenAmt = r.openAmt - r.impOpen
  const netCloseAmt = closeAmt - impClose

  return {
    ...r,
    aging,
    agingTotal,
    openUnitPrice: calcUnitPrice(r.openAmt, r.openQty),
    incUnitPrice: calcUnitPrice(r.incAmt, r.incQty),
    decUnitPrice: calcUnitPrice(r.decAmt, r.decQty),
    closeQty,
    closeAmt,
    closeUnitPrice: calcUnitPrice(closeAmt, closeQty),
    agingOk: Math.abs(agingTotal - closeAmt) <= 0.01,
    agingLt1: Number(aging.within1 ?? 0),
    aging1to2: Number(aging.y1to2 ?? 0),
    aging2to3: Number(aging.y2to3 ?? 0),
    agingGt3: Number(aging.over3 ?? aging.over5 ?? 0),
    impClose,
    impAudOpen,
    impAudInc,
    impAudDec,
    impAudClose,
    netOpenQty: r.openQty,
    netOpenAmt,
    netOpenUnit: calcUnitPrice(netOpenAmt, r.openQty),
    netCloseQty: closeQty,
    netCloseAmt,
    netCloseUnit: calcUnitPrice(netCloseAmt, closeQty),
  }
}

export function sumBioAssetMovement(rows: Array<Partial<BioAssetRow>>) {
  const segs = PRESET_SEGMENTS.THREE_YEAR
  const enriched = rows.map((r) => enrichRow(normalizeBioAssetRow(r, segs), segs))
  return {
    opening: calcSubtotal(enriched.map((r) => r.openAmt)),
    increase: calcSubtotal(enriched.map((r) => r.incAmt)),
    decrease: calcSubtotal(enriched.map((r) => r.decAmt)),
    closing: calcSubtotal(enriched.map((r) => r.closeAmt)),
  }
}

function loadRows(map: Map<string, ChecklistResponse>, segments: AgingSegment[]): BioAssetRow[] {
  const raw = readRowJson(map.get(ROWS_KEY))
  if (!raw) return [emptyRow('1', segments)]
  try {
    const parsed = JSON.parse(raw) as Partial<BioAssetRow>[]
    if (!Array.isArray(parsed) || !parsed.length) return [emptyRow('1', segments)]
    return parsed.map((r, i) => normalizeBioAssetRow({ ...r, id: r.id || String(i + 1) }, segments))
  } catch {
    return [emptyRow('1', segments)]
  }
}

function persistItem(map: Map<string, ChecklistResponse>, key: string, remark: string) {
  const item: ChecklistResponse = { item_id: key, conclusion: null, remark }
  map.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

export function useF2BioAssetSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const agingPreset = ref<AgingPreset>('THREE_YEAR')
  const segments: ComputedRef<AgingSegment[]> = computed(() =>
    agingPreset.value === 'FIVE_YEAR' ? PRESET_SEGMENTS.FIVE_YEAR : PRESET_SEGMENTS.THREE_YEAR,
  )

  const activeView = ref<BioAssetView>('gross')
  const searchText = ref('')
  const rows = ref<BioAssetRow[]>(loadRows(opts.allResponses.value, segments.value))
  const notePack = ref<BioAssetNotePack>(emptyNotes())
  const auditConclusion = ref('')

  function hydrateMeta() {
    const map = opts.allResponses.value
    auditConclusion.value = map.get(CONCLUSION_KEY)?.remark ?? ''
    try {
      const raw = map.get(NOTE_KEY)?.remark
      if (raw) {
        const p = JSON.parse(raw) as Partial<BioAssetNotePack> & { valuationMethod?: string }
        notePack.value = { auditNote: p.auditNote || p.valuationMethod || '' }
        return
      }
    } catch { /* ignore */ }
    notePack.value = emptyNotes()
  }
  hydrateMeta()

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, () => {
    rows.value = loadRows(opts.allResponses.value, segments.value)
    hydrateMeta()
  })

  watch(segments, (segs) => {
    rows.value = rows.value.map((r) => normalizeBioAssetRow({ ...r, aging: migrateAging(r, segs) }, segs))
  })

  const enrichedRows = computed(() => rows.value.map((r) => enrichRow(r, segments.value)))

  const filteredRows = computed(() => {
    const q = searchText.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      [r.itemName, r.variety].some((x) => String(x || '').toLowerCase().includes(q)),
    )
  })

  const totals = computed(() => {
    const e = enrichedRows.value
    const closeAmt = calcSubtotal(e.map((r) => r.closeAmt))
    const agingTotal = calcSubtotal(e.map((r) => r.agingTotal))
    return {
      openAmt: calcSubtotal(e.map((r) => r.openAmt)),
      incAmt: calcSubtotal(e.map((r) => r.incAmt)),
      decAmt: calcSubtotal(e.map((r) => r.decAmt)),
      closeAmt,
      agingTotal,
      agingOk: Math.abs(agingTotal - closeAmt) <= 0.01,
      impClose: calcSubtotal(e.map((r) => r.impClose)),
      impAudClose: calcSubtotal(e.map((r) => r.impAudClose)),
      netCloseAmt: calcSubtotal(e.map((r) => r.netCloseAmt)),
    }
  })

  const agingMismatch = computed(() => enrichedRows.value.filter((r) => !r.agingOk))

  function persistRows() {
    if (opts.isReadonly.value) return
    persistItem(opts.allResponses.value, ROWS_KEY, JSON.stringify(rows.value))
  }

  function updateRow(id: string, patch: Partial<BioAssetRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistRows()
  }

  function updateAgingCell(id: string, key: string, val: number) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      return { ...r, aging: { ...r.aging, [key]: val } }
    })
    persistRows()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入存货名称', '新增消耗性生物资产', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const id = String(Date.now())
      rows.value = [...rows.value, { ...emptyRow(id, segments.value), itemName: value }]
      persistRows()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persistRows()
  }

  function persistNotePack(patch: Partial<BioAssetNotePack>) {
    if (opts.isReadonly.value) return
    notePack.value = { ...notePack.value, ...patch }
    persistItem(opts.allResponses.value, NOTE_KEY, JSON.stringify(notePack.value))
  }

  function persistConclusion(val: string) {
    if (opts.isReadonly.value) return
    auditConclusion.value = val
    persistItem(opts.allResponses.value, CONCLUSION_KEY, val)
  }

  function applyAgingPreset(preset: AgingPreset) {
    agingPreset.value = preset
  }

  return {
    activeView,
    searchText,
    segments,
    agingPreset,
    enrichedRows,
    filteredRows,
    totals,
    agingMismatch,
    notePack,
    auditConclusion,
    updateRow,
    updateAgingCell,
    addRow,
    removeRow,
    persistNotePack,
    persistConclusion,
    applyAgingPreset,
  }
}

export default useF2BioAssetSheet
