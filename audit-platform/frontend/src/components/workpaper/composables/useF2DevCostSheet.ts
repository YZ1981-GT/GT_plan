/**
 * useF2DevCostSheet — F2-11 开发成本明细
 * 对齐 Excel：（一）原值 ·（二）跌价准备 ·（三）净值 + 审计说明
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcEndAmount, calcSubtotal } from './useF2InvMaiFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF2FormData'

export type DevCostView = 'gross' | 'impairment' | 'net'

export interface DevCostNotePack {
  costMethod: string
  significantChange: string
  longTermReason: string
  capitalizedInterest: string
}

export interface DevCostRow {
  id: string
  projectName: string
  /** 总建筑面积/万平米 */
  totalArea: number
  startDate: string
  expectedCompleteDate: string
  estimatedInvestment: number
  /** 原值未审 */
  unaudOpen: number
  unaudInc: number
  unaudDec: number
  adjAcctInc: number
  adjAcctDec: number
  adjReclassInc: number
  adjReclassDec: number
  /** 库龄（年） */
  agingYears: number | ''
  qualityStatus: string
  /** 跌价 */
  impUnaudOpen: number
  impUnaudInc: number
  impUnaudDec: number
  impAdjAcctInc: number
  impAdjAcctDec: number
  impAdjReclassInc: number
  impAdjReclassDec: number
  impRemark: string
  impIndex: string
}

export interface DevCostEnriched extends DevCostRow {
  unaudClose: number
  audOpen: number
  audInc: number
  audDec: number
  audClose: number
  impUnaudClose: number
  impAudOpen: number
  impAudInc: number
  impAudDec: number
  impAudClose: number
  netUnaudOpen: number
  netUnaudClose: number
  netAudOpen: number
  netAudClose: number
}

const ROWS_KEY = 'F2-11-rows'
const NOTE_KEY = 'F2-11-note-pack'
const CONCLUSION_KEY = 'F2-11-audit-conclusion'

export const DEV_COST_QUALITY = ['正常', '滞建', '毁损', '报废', '其他'] as const

function emptyNotes(): DevCostNotePack {
  return {
    costMethod: '',
    significantChange: '',
    longTermReason: '',
    capitalizedInterest: '',
  }
}

function emptyRow(id: string): DevCostRow {
  return {
    id,
    projectName: '',
    totalArea: 0,
    startDate: '',
    expectedCompleteDate: '',
    estimatedInvestment: 0,
    unaudOpen: 0,
    unaudInc: 0,
    unaudDec: 0,
    adjAcctInc: 0,
    adjAcctDec: 0,
    adjReclassInc: 0,
    adjReclassDec: 0,
    agingYears: '',
    qualityStatus: '',
    impUnaudOpen: 0,
    impUnaudInc: 0,
    impUnaudDec: 0,
    impAdjAcctInc: 0,
    impAdjAcctDec: 0,
    impAdjReclassInc: 0,
    impAdjReclassDec: 0,
    impRemark: '',
    impIndex: '',
  }
}

export function normalizeDevCostRow(
  partial: Partial<DevCostRow> & { id?: string },
): DevCostRow {
  return { ...emptyRow(partial.id || '1'), ...partial, id: partial.id || '1' }
}

export function enrichRow(r: DevCostRow): DevCostEnriched {
  const unaudClose = calcEndAmount(r.unaudOpen, r.unaudInc, r.unaudDec)
  const audOpen = r.unaudOpen
  const audInc = r.unaudInc + r.adjAcctInc + r.adjReclassInc
  const audDec = r.unaudDec + r.adjAcctDec + r.adjReclassDec
  const audClose = calcEndAmount(audOpen, audInc, audDec)

  const impUnaudClose = calcEndAmount(r.impUnaudOpen, r.impUnaudInc, r.impUnaudDec)
  const impAudOpen = r.impUnaudOpen
  const impAudInc = r.impUnaudInc + r.impAdjAcctInc + r.impAdjReclassInc
  const impAudDec = r.impUnaudDec + r.impAdjAcctDec + r.impAdjReclassDec
  const impAudClose = calcEndAmount(impAudOpen, impAudInc, impAudDec)

  return {
    ...r,
    unaudClose,
    audOpen,
    audInc,
    audDec,
    audClose,
    impUnaudClose,
    impAudOpen,
    impAudInc,
    impAudDec,
    impAudClose,
    netUnaudOpen: r.unaudOpen - r.impUnaudOpen,
    netUnaudClose: unaudClose - impUnaudClose,
    netAudOpen: audOpen - impAudOpen,
    netAudClose: audClose - impAudClose,
  }
}

export function sumDevCostMovement(rows: Array<Partial<DevCostRow>>) {
  const enriched = rows.map((r) => enrichRow(normalizeDevCostRow(r)))
  return {
    opening: calcSubtotal(enriched.map((r) => r.unaudOpen)),
    increase: calcSubtotal(enriched.map((r) => r.unaudInc)),
    decrease: calcSubtotal(enriched.map((r) => r.unaudDec)),
    closing: calcSubtotal(enriched.map((r) => r.unaudClose)),
  }
}

function loadRows(map: Map<string, ChecklistResponse>): DevCostRow[] {
  const raw = readRowJson(map.get(ROWS_KEY))
  if (!raw) return [emptyRow('1')]
  try {
    const parsed = JSON.parse(raw) as Partial<DevCostRow>[]
    if (!Array.isArray(parsed) || !parsed.length) return [emptyRow('1')]
    return parsed.map((r, i) => normalizeDevCostRow({ ...r, id: r.id || String(i + 1) }))
  } catch {
    return [emptyRow('1')]
  }
}

function persistItem(map: Map<string, ChecklistResponse>, key: string, remark: string) {
  const item: ChecklistResponse = { item_id: key, conclusion: null, remark }
  map.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}

export function useF2DevCostSheet(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
}) {
  const activeView = ref<DevCostView>('gross')
  const searchText = ref('')
  const rows = ref<DevCostRow[]>(loadRows(opts.allResponses.value))
  const notePack = ref<DevCostNotePack>(emptyNotes())
  const auditConclusion = ref('')

  function hydrateMeta() {
    const map = opts.allResponses.value
    auditConclusion.value = map.get(CONCLUSION_KEY)?.remark ?? ''
    try {
      const raw = map.get(NOTE_KEY)?.remark
      if (raw) {
        notePack.value = { ...emptyNotes(), ...(JSON.parse(raw) as Partial<DevCostNotePack>) }
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
      [r.projectName, r.startDate, r.expectedCompleteDate].some((x) =>
        String(x || '').toLowerCase().includes(q),
      ),
    )
  })

  const totals = computed(() => {
    const e = enrichedRows.value
    return {
      unaudOpen: calcSubtotal(e.map((r) => r.unaudOpen)),
      unaudInc: calcSubtotal(e.map((r) => r.unaudInc)),
      unaudDec: calcSubtotal(e.map((r) => r.unaudDec)),
      unaudClose: calcSubtotal(e.map((r) => r.unaudClose)),
      audOpen: calcSubtotal(e.map((r) => r.audOpen)),
      audInc: calcSubtotal(e.map((r) => r.audInc)),
      audDec: calcSubtotal(e.map((r) => r.audDec)),
      audClose: calcSubtotal(e.map((r) => r.audClose)),
      impUnaudClose: calcSubtotal(e.map((r) => r.impUnaudClose)),
      impAudClose: calcSubtotal(e.map((r) => r.impAudClose)),
      netUnaudClose: calcSubtotal(e.map((r) => r.netUnaudClose)),
      netAudClose: calcSubtotal(e.map((r) => r.netAudClose)),
    }
  })

  function persistRows() {
    if (opts.isReadonly.value) return
    persistItem(opts.allResponses.value, ROWS_KEY, JSON.stringify(rows.value))
  }

  function updateRow(id: string, patch: Partial<DevCostRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistRows()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增开发成本', {
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

  function persistNotePack(patch: Partial<DevCostNotePack>) {
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
    searchText,
    enrichedRows,
    filteredRows,
    totals,
    notePack,
    auditConclusion,
    updateRow,
    addRow,
    removeRow,
    persistNotePack,
    persistConclusion,
  }
}

export default useF2DevCostSheet
