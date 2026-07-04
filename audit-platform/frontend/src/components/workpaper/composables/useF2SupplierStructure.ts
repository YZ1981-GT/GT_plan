/**
 * useF2SupplierStructure — F2-68 重要供应商结构（25列：固定5+滚动20）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcChangeRate, calcSubtotal } from './useF2InvMaiFormulaEngine'
import { calcConcentrationRatio } from './useF2SpecialFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export interface SupplierStructureRow {
  id: string
  supplierName: string
  category: string
  coopYear: string
  isRelated: '是' | '否'
  amountT: number
  amountT1: number
  amountT2: number
  concentrationEval: string
  indexNo: string
  remark: string
}

const ROWS_KEY = 'F2-68-rows'
const NOTE_KEY = 'F2-68-note'

function emptyRow(id: string): SupplierStructureRow {
  return {
    id, supplierName: '', category: '', coopYear: '', isRelated: '否',
    amountT: 0, amountT1: 0, amountT2: 0,
    concentrationEval: '', indexNo: '', remark: '',
  }
}

function assignRanks(rows: SupplierStructureRow[]): Map<string, number> {
  const sorted = [...rows].sort((a, b) => b.amountT - a.amountT)
  const map = new Map<string, number>()
  sorted.forEach((r, i) => map.set(r.id, i + 1))
  return map
}

export function enrichSupplierRow(
  r: SupplierStructureRow,
  totalT: number,
  totalT1: number,
  totalT2: number,
  rankT: number,
  rankT1: number,
  rankT2: number,
) {
  const ratioT = calcConcentrationRatio(r.amountT, totalT)
  const ratioT1 = calcConcentrationRatio(r.amountT1, totalT1)
  const ratioT2 = calcConcentrationRatio(r.amountT2, totalT2)
  const changeTvsT1 = calcChangeRate(r.amountT1, r.amountT)
  const changeT1vsT2 = calcChangeRate(r.amountT2, r.amountT1)
  let entryFlag = ''
  if (r.amountT > 0 && !r.amountT1) entryFlag = '新增'
  else if (!r.amountT && r.amountT1 > 0) entryFlag = '退出'
  const isHighConcentration = ratioT > 30
  const isNewTop5 = entryFlag === '新增' && rankT <= 5 && rankT > 0
  return {
    ...r,
    ratioT,
    ratioT1,
    ratioT2,
    rankT,
    rankT1,
    rankT2,
    changeTvsT1,
    changeT1vsT2,
    entryFlag,
    isHighConcentration,
    isNewTop5,
    highlight: isHighConcentration || isNewTop5,
  }
}

export function useF2SupplierStructure(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<SupplierStructureRow[]>([emptyRow('1')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as SupplierStructureRow[]
        if (parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => {
    const raw = rows.value
    const totalT = calcSubtotal(raw.map((r) => r.amountT))
    const totalT1 = calcSubtotal(raw.map((r) => r.amountT1))
    const totalT2 = calcSubtotal(raw.map((r) => r.amountT2))
    const rankMapT = assignRanks(raw)
    const rankMapT1 = assignRanks(raw.map((r) => ({ ...r, amountT: r.amountT1 })))
    const rankMapT2 = assignRanks(raw.map((r) => ({ ...r, amountT: r.amountT2 })))
    return raw.map((r) => enrichSupplierRow(
      r, totalT, totalT1, totalT2,
      rankMapT.get(r.id) ?? 0,
      rankMapT1.get(r.id) ?? 0,
      rankMapT2.get(r.id) ?? 0,
    ))
  })

  const concentrationSummary = computed(() => {
    const sorted = [...enrichedRows.value].sort((a, b) => b.amountT - a.amountT)
    const totalT = calcSubtotal(sorted.map((r) => r.amountT))
    const top5 = calcSubtotal(sorted.slice(0, 5).map((r) => r.amountT))
    const top10 = calcSubtotal(sorted.slice(0, 10).map((r) => r.amountT))
    return {
      totalT,
      top5Ratio: totalT ? (top5 / totalT) * 100 : 0,
      top10Ratio: totalT ? (top10 / totalT) * 100 : 0,
    }
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

  function updateRow(id: string, patch: Partial<SupplierStructureRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入供应商名称', '新增供应商', {
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
    enrichedRows,
    concentrationSummary,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2SupplierStructure
