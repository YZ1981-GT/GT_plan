/**
 * useF2ContractPerfSheet — F2-12 合同履约成本明细
 * 对齐 Excel：项目编码/名称 · 开工/预计竣工 · 期初/转入/转出/期末 · 库龄 · 品质
 * 合计 − 跌价准备 = 净额；四问审计说明
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcEndAmount, calcSubtotal } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'
import { PRESET_SEGMENTS, type AgingPreset, type AgingSegment } from '@/composables/useAgingConfig'
import { remapAgingData, type AgingData } from '@/composables/useAgingMigration'

export interface ContractPerfNotePack {
  costMethod: string
  significantChange: string
  suspendedReason: string
  impairmentReason: string
}

export interface ContractPerfRow {
  id: string
  projectCode: string
  projectName: string
  startDate: string
  expectedCompleteDate: string
  openingAmt: number
  increaseAmt: number
  decreaseAmt: number
  aging: AgingData
  agingTotal: number
  qualityStatus: string
  /** 兼容旧通用明细 */
  agingLt1?: number
  aging1to2?: number
  aging2to3?: number
  agingGt3?: number
}

export interface ContractPerfEnriched extends ContractPerfRow {
  closingAmt: number
  agingOk: boolean
}

export const CONTRACT_PERF_QUALITY = ['正常', '停建', '毁损', '报废', '其他'] as const

const ROWS_KEY = 'F2-12-rows'
const NOTE_KEY = 'F2-12-note-pack'
const IMPAIR_KEY = 'F2-12-impairment-provision'
const CONCLUSION_KEY = 'F2-12-audit-conclusion'

const LEGACY_AGING = [
  { flat: 'agingLt1', key: 'within1' },
  { flat: 'aging1to2', key: 'y1to2' },
  { flat: 'aging2to3', key: 'y2to3' },
  { flat: 'agingGt3', key: 'over3' },
] as const

function emptyNotes(): ContractPerfNotePack {
  return { costMethod: '', significantChange: '', suspendedReason: '', impairmentReason: '' }
}

function emptyAging(segments: AgingSegment[]): AgingData {
  const a: AgingData = {}
  for (const s of segments) a[s.key] = 0
  return a
}

function emptyRow(id: string, segments: AgingSegment[]): ContractPerfRow {
  return {
    id,
    projectCode: '',
    projectName: '',
    startDate: '',
    expectedCompleteDate: '',
    openingAmt: 0,
    increaseAmt: 0,
    decreaseAmt: 0,
    aging: emptyAging(segments),
    agingTotal: 0,
    qualityStatus: '',
  }
}

function migrateAging(raw: Partial<ContractPerfRow>, segments: AgingSegment[]): AgingData {
  let base: AgingData = {}
  if (raw.aging && typeof raw.aging === 'object') base = { ...raw.aging }
  for (const { flat, key } of LEGACY_AGING) {
    const flatVal = Number((raw as any)[flat] ?? 0)
    if (flatVal && !Number(base[key] ?? 0)) base[key] = flatVal
  }
  return remapAgingData(base, segments)
}

/** 旧通用明细行 → 合同履约项目行 */
function migrateLegacy(raw: Record<string, unknown>, segments: AgingSegment[]): Partial<ContractPerfRow> {
  if (raw.projectName != null || raw.projectCode != null) {
    return raw as Partial<ContractPerfRow>
  }
  return {
    projectCode: String(raw.itemCode || ''),
    projectName: String(raw.itemName || ''),
    openingAmt: Number(raw.openingAmt) || 0,
    increaseAmt: Number(raw.increaseAmt) || 0,
    decreaseAmt: Number(raw.decreaseAmt) || 0,
    aging: migrateAging(raw as Partial<ContractPerfRow>, segments),
    qualityStatus: String(raw.qualityStatus || ''),
  }
}

export function normalizeContractPerfRow(
  partial: Partial<ContractPerfRow> & { id?: string },
  segments: AgingSegment[] = PRESET_SEGMENTS.THREE_YEAR,
): ContractPerfRow {
  const migrated = migrateLegacy(partial as Record<string, unknown>, segments)
  const base = { ...emptyRow(partial.id || '1', segments), ...migrated, id: partial.id || '1' }
  base.aging = migrateAging(base, segments)
  return base
}

export function enrichRow(r: ContractPerfRow, segments: AgingSegment[]): ContractPerfEnriched {
  const closingAmt = calcEndAmount(r.openingAmt, r.increaseAmt, r.decreaseAmt)
  const aging = remapAgingData(r.aging || {}, segments)
  let agingTotal = 0
  for (const s of segments) agingTotal += Number(aging[s.key] ?? 0)
  return {
    ...r,
    aging,
    agingTotal,
    closingAmt,
    agingOk: Math.abs(agingTotal - closingAmt) <= 0.01,
    agingLt1: Number(aging.within1 ?? 0),
    aging1to2: Number(aging.y1to2 ?? 0),
    aging2to3: Number(aging.y2to3 ?? 0),
    agingGt3: Number(aging.over3 ?? aging.over5 ?? 0),
  }
}

export function sumContractPerfMovement(rows: Array<Partial<ContractPerfRow>>) {
  const segs = PRESET_SEGMENTS.THREE_YEAR
  const enriched = rows.map((r) => enrichRow(normalizeContractPerfRow(r, segs), segs))
  return {
    opening: calcSubtotal(enriched.map((r) => r.openingAmt)),
    increase: calcSubtotal(enriched.map((r) => r.increaseAmt)),
    decrease: calcSubtotal(enriched.map((r) => r.decreaseAmt)),
    closing: calcSubtotal(enriched.map((r) => r.closingAmt)),
  }
}

function loadRows(map: Map<string, ChecklistResponse>, segments: AgingSegment[]): ContractPerfRow[] {
  const raw = readRowJson(map.get(ROWS_KEY))
  if (!raw) return [emptyRow('1', segments)]
  try {
    const parsed = JSON.parse(raw) as Partial<ContractPerfRow>[]
    if (!Array.isArray(parsed) || !parsed.length) return [emptyRow('1', segments)]
    return parsed.map((r, i) => normalizeContractPerfRow({ ...r, id: r.id || String(i + 1) }, segments))
  } catch {
    return [emptyRow('1', segments)]
  }
}

function persistItem(map: Map<string, ChecklistResponse>, key: string, remark: string) {
  const item: ChecklistResponse = { item_id: key, conclusion: null, remark }
  map.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

export function useF2ContractPerfSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const agingPreset = ref<AgingPreset>('THREE_YEAR')
  const segments: ComputedRef<AgingSegment[]> = computed(() =>
    agingPreset.value === 'FIVE_YEAR' ? PRESET_SEGMENTS.FIVE_YEAR : PRESET_SEGMENTS.THREE_YEAR,
  )

  const activeView = ref<'movement' | 'aging' | 'full'>('full')
  const searchText = ref('')
  const rows = ref<ContractPerfRow[]>(loadRows(opts.allResponses.value, segments.value))
  const impairmentProvision = ref(0)
  const notePack = ref<ContractPerfNotePack>(emptyNotes())
  const auditConclusion = ref('')

  function hydrateMeta() {
    const map = opts.allResponses.value
    impairmentProvision.value = Number(map.get(IMPAIR_KEY)?.remark || 0) || 0
    auditConclusion.value = map.get(CONCLUSION_KEY)?.remark ?? ''
    try {
      const raw = map.get(NOTE_KEY)?.remark
      if (raw) {
        notePack.value = { ...emptyNotes(), ...(JSON.parse(raw) as Partial<ContractPerfNotePack>) }
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
    rows.value = rows.value.map((r) => normalizeContractPerfRow({ ...r, aging: migrateAging(r, segs) }, segs))
  })

  const enrichedRows = computed(() => rows.value.map((r) => enrichRow(r, segments.value)))

  const filteredRows = computed(() => {
    const q = searchText.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      [r.projectCode, r.projectName].some((x) => String(x || '').toLowerCase().includes(q)),
    )
  })

  const totals = computed(() => {
    const e = enrichedRows.value
    const closingAmt = calcSubtotal(e.map((r) => r.closingAmt))
    const agingTotal = calcSubtotal(e.map((r) => r.agingTotal))
    return {
      openingAmt: calcSubtotal(e.map((r) => r.openingAmt)),
      increaseAmt: calcSubtotal(e.map((r) => r.increaseAmt)),
      decreaseAmt: calcSubtotal(e.map((r) => r.decreaseAmt)),
      closingAmt,
      agingTotal,
      agingOk: Math.abs(agingTotal - closingAmt) <= 0.01,
    }
  })

  const netAmt = computed(() => totals.value.closingAmt - impairmentProvision.value)
  const agingMismatch = computed(() => enrichedRows.value.filter((r) => !r.agingOk))

  function persistRows() {
    if (opts.isReadonly.value) return
    persistItem(opts.allResponses.value, ROWS_KEY, JSON.stringify(rows.value))
  }

  function updateRow(id: string, patch: Partial<ContractPerfRow>) {
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
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增合同履约成本', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const id = String(Date.now())
      rows.value = [...rows.value, { ...emptyRow(id, segments.value), projectName: value }]
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
    persistItem(opts.allResponses.value, IMPAIR_KEY, String(impairmentProvision.value))
  }

  function persistNotePack(patch: Partial<ContractPerfNotePack>) {
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
    netAmt,
    agingMismatch,
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

export default useF2ContractPerfSheet
