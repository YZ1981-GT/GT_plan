/**
 * useF2DevProductSheet — F2-10 开发产品明细
 * 对齐 Excel：（一）原值 ·（二）跌价准备 ·（三）净值 + 审计说明
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcEndAmount, calcSubtotal, calcUnitPrice } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'

export type DevProductView = 'gross' | 'impairment' | 'net'

export interface DevProductNotePack {
  statusNote: string
  significantChange: string
  bookAuditDiff: string
  impairmentReason: string
}

export interface DevProductRow {
  id: string
  projectName: string
  /** 总建筑面积(平方米) */
  totalArea: number
  startDate: string
  completeDate: string
  /** 原值 — 期初结存 */
  openArea: number
  openAmt: number
  openAdjAcct: number
  openAdjReclass: number
  /** 本期增加 / 减少 */
  incArea: number
  incAmt: number
  decArea: number
  decAmt: number
  /** 期末调整 */
  closeAdjAcct: number
  closeAdjReclass: number
  qualityStatus: string
  /** 跌价准备 */
  impOpen: number
  impInc: number
  impDec: number
  impOpenAdjAcct: number
  impOpenAdjReclass: number
  impRemark: string
  impIndex: string
}

export interface DevProductEnriched extends DevProductRow {
  openUnitCost: number | ''
  openAudAmt: number
  openAudUnitCost: number | ''
  incUnitCost: number | ''
  decUnitCost: number | ''
  closeArea: number
  closeAmt: number
  closeUnitCost: number | ''
  closeAudAmt: number
  closeAudUnitCost: number | ''
  impClose: number
  impOpenAud: number
  impCloseAud: number
  netOpenBookArea: number
  netOpenBookAmt: number
  netOpenBookUnit: number | ''
  netCloseBookArea: number
  netCloseBookAmt: number
  netCloseBookUnit: number | ''
  netCloseAudArea: number
  netCloseAudAmt: number
  netCloseAudUnit: number | ''
}

const ROWS_KEY = 'F2-10-rows'
const NOTE_KEY = 'F2-10-note-pack'
const CONCLUSION_KEY = 'F2-10-audit-conclusion'

const QUALITY = ['正常', '滞销', '积压', '毁损', '其他'] as const
export { QUALITY as DEV_PRODUCT_QUALITY }

function emptyNotes(): DevProductNotePack {
  return {
    statusNote: '',
    significantChange: '',
    bookAuditDiff: '',
    impairmentReason: '',
  }
}

function emptyRow(id: string): DevProductRow {
  return {
    id,
    projectName: '',
    totalArea: 0,
    startDate: '',
    completeDate: '',
    openArea: 0,
    openAmt: 0,
    openAdjAcct: 0,
    openAdjReclass: 0,
    incArea: 0,
    incAmt: 0,
    decArea: 0,
    decAmt: 0,
    closeAdjAcct: 0,
    closeAdjReclass: 0,
    qualityStatus: '',
    impOpen: 0,
    impInc: 0,
    impDec: 0,
    impOpenAdjAcct: 0,
    impOpenAdjReclass: 0,
    impRemark: '',
    impIndex: '',
  }
}

/** 旧版土地/建安/利息分区 → 原值收发存 */
function migrateLegacy(raw: Record<string, unknown>): Partial<DevProductRow> {
  if (raw.openAmt != null || (raw.landOpen == null && raw.buildOpen == null)) {
    return raw as Partial<DevProductRow>
  }
  const n = (k: string) => Number(raw[k]) || 0
  const openAmt = n('landOpen') + n('buildOpen') + n('intOpen') + n('otherOpen')
  const incAmt = n('landIn') + n('buildIn') + n('intIn') + n('otherIn')
  const decAmt = n('landOut') + n('buildOut') + n('intOut') + n('otherOut') + n('transferOut')
  return {
    projectName: String(raw.projectName || ''),
    totalArea: n('area'),
    openArea: n('area'),
    openAmt,
    incAmt,
    decAmt,
    qualityStatus: '',
  }
}

export function normalizeDevProductRow(
  partial: Partial<DevProductRow> & { id?: string },
): DevProductRow {
  const migrated = migrateLegacy(partial as Record<string, unknown>)
  return { ...emptyRow(partial.id || '1'), ...migrated, id: partial.id || '1' }
}

export function enrichRow(r: DevProductRow): DevProductEnriched {
  const openUnitCost = calcUnitPrice(r.openAmt, r.openArea)
  const openAudAmt = r.openAmt + r.openAdjAcct + r.openAdjReclass
  const openAudUnitCost = calcUnitPrice(openAudAmt, r.openArea)
  const incUnitCost = calcUnitPrice(r.incAmt, r.incArea)
  const decUnitCost = calcUnitPrice(r.decAmt, r.decArea)
  const closeArea = calcEndAmount(r.openArea, r.incArea, r.decArea)
  const closeAmt = calcEndAmount(r.openAmt, r.incAmt, r.decAmt)
  const closeUnitCost = calcUnitPrice(closeAmt, closeArea)
  const closeAudAmt = closeAmt + r.closeAdjAcct + r.closeAdjReclass
  const closeAudUnitCost = calcUnitPrice(closeAudAmt, closeArea)

  const impClose = calcEndAmount(r.impOpen, r.impInc, r.impDec)
  const impOpenAud = r.impOpen + r.impOpenAdjAcct + r.impOpenAdjReclass
  const impCloseAud = calcEndAmount(impOpenAud, r.impInc, r.impDec)

  const netOpenBookAmt = r.openAmt - r.impOpen
  const netCloseBookAmt = closeAmt - impClose
  const netCloseAudAmt = closeAudAmt - impCloseAud

  return {
    ...r,
    openUnitCost,
    openAudAmt,
    openAudUnitCost,
    incUnitCost,
    decUnitCost,
    closeArea,
    closeAmt,
    closeUnitCost,
    closeAudAmt,
    closeAudUnitCost,
    impClose,
    impOpenAud,
    impCloseAud,
    netOpenBookArea: r.openArea,
    netOpenBookAmt,
    netOpenBookUnit: calcUnitPrice(netOpenBookAmt, r.openArea),
    netCloseBookArea: closeArea,
    netCloseBookAmt,
    netCloseBookUnit: calcUnitPrice(netCloseBookAmt, closeArea),
    netCloseAudArea: closeArea,
    netCloseAudAmt,
    netCloseAudUnit: calcUnitPrice(netCloseAudAmt, closeArea),
  }
}

/** 跨表：原值未审收发存合计 */
export function sumDevProductMovement(rows: Array<Partial<DevProductRow> & Record<string, unknown>>) {
  const normalized = rows.map((r) => normalizeDevProductRow(r as Partial<DevProductRow>))
  const enriched = normalized.map(enrichRow)
  return {
    opening: calcSubtotal(enriched.map((r) => r.openAmt)),
    increase: calcSubtotal(enriched.map((r) => r.incAmt)),
    decrease: calcSubtotal(enriched.map((r) => r.decAmt)),
    closing: calcSubtotal(enriched.map((r) => r.closeAmt)),
  }
}

function loadRows(map: Map<string, ChecklistResponse>): DevProductRow[] {
  const raw = readRowJson(map.get(ROWS_KEY))
  if (!raw) return [emptyRow('1')]
  try {
    const parsed = JSON.parse(raw) as Partial<DevProductRow>[]
    if (!Array.isArray(parsed) || !parsed.length) return [emptyRow('1')]
    return parsed.map((r, i) => normalizeDevProductRow({ ...r, id: r.id || String(i + 1) }))
  } catch {
    return [emptyRow('1')]
  }
}

function persistItem(map: Map<string, ChecklistResponse>, key: string, remark: string) {
  const item: ChecklistResponse = { item_id: key, conclusion: null, remark }
  map.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

export function useF2DevProductSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const activeView = ref<DevProductView>('gross')
  /** @deprecated 旧区段别名 */
  const activeSegment = activeView as unknown as Ref<'basic' | 'land' | 'construction' | 'interest' | 'other'>
  const searchText = ref('')
  const rows = ref<DevProductRow[]>(loadRows(opts.allResponses.value))
  const notePack = ref<DevProductNotePack>(emptyNotes())
  const auditConclusion = ref('')

  function hydrateMeta() {
    const map = opts.allResponses.value
    auditConclusion.value = map.get(CONCLUSION_KEY)?.remark ?? ''
    try {
      const raw = map.get(NOTE_KEY)?.remark
      if (raw) {
        const p = JSON.parse(raw) as Partial<DevProductNotePack>
        notePack.value = { ...emptyNotes(), ...p }
        return
      }
    } catch { /* ignore */ }
    notePack.value = emptyNotes()
  }
  hydrateMeta()

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, () => {
    rows.value = loadRows(opts.allResponses.value)
    hydrateMeta()
  })

  const enrichedRows = computed(() => rows.value.map(enrichRow))

  const filteredRows = computed(() => {
    const q = searchText.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      [r.projectName, r.startDate, r.completeDate].some((x) => String(x || '').toLowerCase().includes(q)),
    )
  })

  const totals = computed(() => {
    const e = enrichedRows.value
    return {
      openAmt: calcSubtotal(e.map((r) => r.openAmt)),
      openAudAmt: calcSubtotal(e.map((r) => r.openAudAmt)),
      incAmt: calcSubtotal(e.map((r) => r.incAmt)),
      decAmt: calcSubtotal(e.map((r) => r.decAmt)),
      closeAmt: calcSubtotal(e.map((r) => r.closeAmt)),
      closeAudAmt: calcSubtotal(e.map((r) => r.closeAudAmt)),
      openArea: calcSubtotal(e.map((r) => r.openArea)),
      closeArea: calcSubtotal(e.map((r) => r.closeArea)),
      impOpen: calcSubtotal(e.map((r) => r.impOpen)),
      impClose: calcSubtotal(e.map((r) => r.impClose)),
      impOpenAud: calcSubtotal(e.map((r) => r.impOpenAud)),
      impCloseAud: calcSubtotal(e.map((r) => r.impCloseAud)),
      netCloseBookAmt: calcSubtotal(e.map((r) => r.netCloseBookAmt)),
      netCloseAudAmt: calcSubtotal(e.map((r) => r.netCloseAudAmt)),
      // 兼容旧 totals 字段名
      landClose: 0,
      buildClose: 0,
      intClose: 0,
      otherClose: 0,
      totalClose: calcSubtotal(e.map((r) => r.closeAmt)),
      netInventory: calcSubtotal(e.map((r) => r.netCloseBookAmt)),
      agingTotal: 0,
    }
  })

  function persistRows() {
    if (opts.isReadonly.value) return
    persistItem(opts.allResponses.value, ROWS_KEY, JSON.stringify(rows.value))
  }

  function updateRow(id: string, patch: Partial<DevProductRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistRows()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增开发产品', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      const id = String(Date.now())
      rows.value = [...rows.value, { ...emptyRow(id), projectName: value }]
      persistRows()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persistRows()
  }

  function persistNotePack(patch: Partial<DevProductNotePack>) {
    if (opts.isReadonly.value) return
    notePack.value = { ...notePack.value, ...patch }
    persistItem(opts.allResponses.value, NOTE_KEY, JSON.stringify(notePack.value))
  }

  function persistConclusion(val: string) {
    if (opts.isReadonly.value) return
    auditConclusion.value = val
    persistItem(opts.allResponses.value, CONCLUSION_KEY, val)
  }

  return {
    activeView,
    activeSegment,
    searchText,
    enrichedRows,
    filteredRows,
    totals,
    agingMismatchCount: computed(() => 0),
    notePack,
    auditConclusion,
    updateRow,
    addRow,
    removeRow,
    persistNotePack,
    persistConclusion,
  }
}

export default useF2DevProductSheet
