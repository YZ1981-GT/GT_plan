/**
 * useF2UnitPrice — F2-62 原材料单价分析（58行×18列，多年趋势+偏离度）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcChangeRate } from './useF2InvMaiFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export interface UnitPriceRow {
  id: string
  materialName: string
  spec: string
  unit: string
  priceT: number
  priceT1: number
  priceT2: number
  qtyT: number
  qtyT1: number
  qtyT2: number
  industryAvgPrice: number
  analysisConclusion: string
  remark: string
}

export interface EnrichedUnitPriceRow extends UnitPriceRow {
  amountT: number
  amountT1: number
  amountT2: number
  yoyChangeRate: number | '' | 'N/A'
  momChangeRate: number | '' | 'N/A'
  deviationPct: number
  isHighDeviation: boolean
  highlight: boolean
}

const ROWS_KEY = 'F2-62-rows'
const NOTE_KEY = 'F2-62-note'
const DEVIATION_THRESHOLD = 20

function emptyRow(id: string): UnitPriceRow {
  return {
    id, materialName: '', spec: '', unit: '',
    priceT: 0, priceT1: 0, priceT2: 0,
    qtyT: 0, qtyT1: 0, qtyT2: 0,
    industryAvgPrice: 0,
    analysisConclusion: '', remark: '',
  }
}

function fmtRate(rate: number | '' | 'N/A'): string {
  if (rate === '' || rate === 'N/A') return '—'
  return `${(rate * 100).toFixed(1)}%`
}

export function enrichUnitPriceRow(r: UnitPriceRow): EnrichedUnitPriceRow {
  const amountT = r.priceT * r.qtyT
  const amountT1 = r.priceT1 * r.qtyT1
  const amountT2 = r.priceT2 * r.qtyT2
  const yoyChangeRate = calcChangeRate(r.priceT1, r.priceT)
  const momChangeRate = calcChangeRate(r.priceT2, r.priceT1)
  const deviationPct = r.industryAvgPrice
    ? ((r.priceT - r.industryAvgPrice) / r.industryAvgPrice) * 100
    : 0
  const isHighDeviation = Math.abs(deviationPct) > DEVIATION_THRESHOLD
  return {
    ...r,
    amountT,
    amountT1,
    amountT2,
    yoyChangeRate,
    momChangeRate,
    deviationPct,
    isHighDeviation,
    highlight: isHighDeviation,
  }
}

export function useF2UnitPrice(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const searchQuery = ref('')
  const rows = ref<UnitPriceRow[]>([emptyRow('1')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as UnitPriceRow[]
        if (parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichUnitPriceRow))

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      r.materialName.toLowerCase().includes(q)
      || r.spec.toLowerCase().includes(q),
    )
  })

  const abnormalCount = computed(() =>
    enrichedRows.value.filter((r) => r.isHighDeviation).length,
  )

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

  function updateRow(id: string, patch: Partial<UnitPriceRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入材料名称', '新增材料', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      rows.value = [...rows.value, { ...emptyRow(String(Date.now())), materialName: value }]
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
    filteredRows,
    abnormalCount,
    auditNote,
    updateRow,
    addRow,
    removeRow,
    fmtRate,
  }
}

export default useF2UnitPrice
