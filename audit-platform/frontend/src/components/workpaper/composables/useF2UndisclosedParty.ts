/**
 * useF2UndisclosedParty — F2-67 识别未披露的关联方（45行×20列）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export type UndisclosedSegment = 'basic' | 'relation' | 'audit'

export const RELATION_TYPES = [
  '控股股东', '共同控制', '重大影响', '近亲属', '其他关联', '疑似关联',
] as const

export const CHECK_SOURCE_OPTIONS = [
  '天眼查', '企查查', '工商登记', '裁判文书', '企业年报', '实地走访',
] as const

export const RISK_LEVELS = ['高', '中', '低'] as const

export interface UndisclosedPartyRow {
  id: string
  supplierName: string
  creditCode: string
  legalRep: string
  shareholderInfo: string
  registeredAddress: string
  regDate: string
  registeredCapital: string
  actualController: string
  relationToClient: string
  relationType: string
  isDisclosed: '是' | '否' | ''
  checkSources: string[]
  checkDate: string
  checker: string
  checkConclusion: string
  riskLevel: string
  followUp: string
  indexNo: string
  remark: string
}

export interface EnrichedUndisclosedRow extends UndisclosedPartyRow {
  isHighRisk: boolean
  isUndisclosedConfirmed: boolean
  highlight: boolean
  highlightLevel: 'none' | 'orange' | 'red'
}

const ROWS_KEY = 'F2-67-rows'
const NOTE_KEY = 'F2-67-note'

function emptyRow(id: string): UndisclosedPartyRow {
  return {
    id, supplierName: '', creditCode: '', legalRep: '', shareholderInfo: '',
    registeredAddress: '', regDate: '', registeredCapital: '',
    actualController: '', relationToClient: '', relationType: '',
    isDisclosed: '', checkSources: [], checkDate: '', checker: '',
    checkConclusion: '', riskLevel: '', followUp: '', indexNo: '', remark: '',
  }
}

export function enrichUndisclosedRow(r: UndisclosedPartyRow): EnrichedUndisclosedRow {
  const isHighRisk = r.riskLevel === '高'
  const isUndisclosedConfirmed = r.isDisclosed === '否' && r.relationType !== '疑似关联' && !!r.relationType
  let highlightLevel: EnrichedUndisclosedRow['highlightLevel'] = 'none'
  if (isHighRisk) highlightLevel = 'red'
  else if (isUndisclosedConfirmed) highlightLevel = 'orange'
  return {
    ...r,
    isHighRisk,
    isUndisclosedConfirmed,
    highlight: isHighRisk || isUndisclosedConfirmed,
    highlightLevel,
  }
}

export function useF2UndisclosedParty(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const activeSegment = ref<UndisclosedSegment>('basic')
  const searchQuery = ref('')
  const rows = ref<UndisclosedPartyRow[]>([emptyRow('1')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as UndisclosedPartyRow[]
        if (parsed.length) {
          rows.value = parsed.map((r) => ({
            ...r,
            checkSources: Array.isArray(r.checkSources) ? r.checkSources : [],
          }))
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichUndisclosedRow))

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      r.supplierName.toLowerCase().includes(q)
      || r.creditCode.toLowerCase().includes(q)
      || r.relationToClient.toLowerCase().includes(q),
    )
  })

  const riskSummary = computed(() => ({
    high: enrichedRows.value.filter((r) => r.riskLevel === '高').length,
    undisclosed: enrichedRows.value.filter((r) => r.isUndisclosedConfirmed).length,
    total: enrichedRows.value.length,
  }))

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

  function updateRow(id: string, patch: Partial<UndisclosedPartyRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入供应商/实体名称', '新增核查对象', {
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
    activeSegment,
    searchQuery,
    filteredRows,
    riskSummary,
    auditNote,
    updateRow,
    addRow,
    removeRow,
    RELATION_TYPES,
    CHECK_SOURCE_OPTIONS,
    RISK_LEVELS,
  }
}

export default useF2UndisclosedParty
