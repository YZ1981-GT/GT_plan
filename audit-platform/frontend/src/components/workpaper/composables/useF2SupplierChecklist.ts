/**
 * useF2SupplierChecklist — F2-69 供应商核查清单（49行×19列）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcChecklistCompletion } from './useF2SpecialFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export type CheckItemStatus = '已完成' | '进行中' | '未开始' | '不适用'

export const CHECK_ITEM_LABELS = [
  '工商登记', '实地走访', '交易真实性', '定价公允性', '关联方核查',
  '资金流水', '物流验证', '合同条款', '结算方式', '信用评价',
] as const

export const CHECK_STATUS_OPTIONS: CheckItemStatus[] = [
  '已完成', '进行中', '未开始', '不适用',
]

export type CheckItemKey =
  | 'check1' | 'check2' | 'check3' | 'check4' | 'check5'
  | 'check6' | 'check7' | 'check8' | 'check9' | 'check10'

export interface SupplierChecklistRow {
  id: string
  supplierName: string
  check1: CheckItemStatus
  check2: CheckItemStatus
  check3: CheckItemStatus
  check4: CheckItemStatus
  check5: CheckItemStatus
  check6: CheckItemStatus
  check7: CheckItemStatus
  check8: CheckItemStatus
  check9: CheckItemStatus
  check10: CheckItemStatus
  overallEval: string
  riskCategory: string
  followUp: string
  owner: string
  completeDate: string
  indexNo: string
  remark: string
}

export interface EnrichedChecklistRow extends SupplierChecklistRow {
  completionPct: number
  completedCount: number
  isOverdue: boolean
  highlight: boolean
}

const ROWS_KEY = 'F2-69-rows'
const NOTE_KEY = 'F2-69-note'
const CHECK_KEYS: CheckItemKey[] = [
  'check1', 'check2', 'check3', 'check4', 'check5',
  'check6', 'check7', 'check8', 'check9', 'check10',
]

function emptyRow(id: string): SupplierChecklistRow {
  const base: SupplierChecklistRow = {
    id, supplierName: '', overallEval: '', riskCategory: '',
    followUp: '', owner: '', completeDate: '', indexNo: '', remark: '',
    check1: '未开始', check2: '未开始', check3: '未开始', check4: '未开始', check5: '未开始',
    check6: '未开始', check7: '未开始', check8: '未开始', check9: '未开始', check10: '未开始',
  }
  return base
}

function countStatus(row: SupplierChecklistRow, status: CheckItemStatus): number {
  return CHECK_KEYS.filter((k) => row[k] === status).length
}

export function enrichChecklistRow(r: SupplierChecklistRow): EnrichedChecklistRow {
  const completedCount = countStatus(r, '已完成')
  const naCount = countStatus(r, '不适用')
  const completionPct = calcChecklistCompletion(completedCount, CHECK_KEYS.length, naCount)
  const isOverdue = completionPct < 100
    && !!r.completeDate
    && r.completeDate <= new Date().toISOString().slice(0, 10)
  return {
    ...r,
    completionPct,
    completedCount,
    isOverdue,
    highlight: isOverdue,
  }
}

export function useF2SupplierChecklist(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const searchQuery = ref('')
  const activeCheckCol = ref(0)
  const rows = ref<SupplierChecklistRow[]>([emptyRow('1')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as SupplierChecklistRow[]
        if (parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichChecklistRow))

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      r.supplierName.toLowerCase().includes(q)
      || r.owner.toLowerCase().includes(q),
    )
  })

  const progressSummary = computed(() => {
    let done = 0
    let inProgress = 0
    let notStarted = 0
    let na = 0
    for (const r of enrichedRows.value) {
      done += countStatus(r, '已完成')
      inProgress += countStatus(r, '进行中')
      notStarted += countStatus(r, '未开始')
      na += countStatus(r, '不适用')
    }
    return { done, inProgress, notStarted, na, suppliers: enrichedRows.value.length }
  })

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(id: string, patch: Partial<SupplierChecklistRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  function updateCheck(id: string, key: CheckItemKey, status: CheckItemStatus): void {
    updateRow(id, { [key]: status } as Partial<SupplierChecklistRow>)
  }

  function markAllChecks(id: string, status: CheckItemStatus): void {
    if (readonly.value) return
    const patch = Object.fromEntries(CHECK_KEYS.map((k) => [k, status])) as Partial<SupplierChecklistRow>
    updateRow(id, patch)
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入供应商名称', '新增核查清单', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      rows.value = [...rows.value, { ...emptyRow(String(Date.now())), supplierName: value }]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    searchQuery,
    activeCheckCol,
    filteredRows,
    progressSummary,
    auditNote,
    updateRow,
    updateCheck,
    markAllChecks,
    addRow,
    removeRow,
    CHECK_ITEM_LABELS,
    CHECK_KEYS,
    CHECK_STATUS_OPTIONS,
  }
}

export default useF2SupplierChecklist
