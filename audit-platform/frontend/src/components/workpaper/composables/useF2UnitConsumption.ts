/** F2-64 四区块月度矩阵状态管理。 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  CHANGE_THRESHOLD,
  defaultUnitConsumptionSheet,
  enrichCostFlowRow,
  enrichCostStructureRow,
  enrichMaterialConsumptionRow,
  enrichUnitCostRow,
  isUnitConsumptionSheetEmpty,
  migrateUnitConsumptionSheet,
  type CostFlowMonth,
  type CostStructureMonth,
  type MaterialConsumptionMonth,
  type MaterialInputCell,
  type PeerCostRow,
  type UnitConsumptionSheet,
  type UnitCostMonth,
} from './useF2UnitConsumptionFormulas'

const ROWS_KEY = 'F2-64-rows'
const NOTE_KEY = 'F2-64-note'

export function useF2UnitConsumption(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<UnitConsumptionSheet>(defaultUnitConsumptionSheet())
  const auditNote = ref('')

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateUnitConsumptionSheet(parsed)
        sheet.value = migrated
        if (!readonly.value && (Array.isArray(parsed) || JSON.stringify(parsed) !== JSON.stringify(migrated))) {
          opts.allResponses.value.set(ROWS_KEY, {
            item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(migrated),
          })
          if (debounceTimer) clearTimeout(debounceTimer)
          debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 300)
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const costStructureRows = computed(() => sheet.value.costStructureRows.map(enrichCostStructureRow))
  const costFlowRows = computed(() => sheet.value.costFlowRows.map(enrichCostFlowRow))
  const unitCostRows = computed(() => sheet.value.unitCostRows.map(enrichUnitCostRow))
  const materialConsumptionRows = computed(() =>
    sheet.value.materialConsumptionRows.map(enrichMaterialConsumptionRow))
  const abnormalCount = computed(() => {
    const structure = costStructureRows.value.filter((r) =>
      Object.values(r.rates).some((rate) => rate !== null && rate > 0.9)).length
    const material = materialConsumptionRows.value.filter((row, index, rows) => {
      if (row.period !== 'current') return false
      const prior = rows.find((r) => r.period === 'prior' && r.month === row.month)
      if (!prior) return false
      return (['material1', 'material2'] as const).some((key) => {
        const current = row[key].unitOutput
        const previous = prior[key].unitOutput
        return current !== null && previous && Math.abs((current - previous) / previous) > CHANGE_THRESHOLD
      })
    }).length
    return structure + material
  })
  const filledCount = computed(() => isUnitConsumptionSheetEmpty(sheet.value) ? 0 : 1)

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(sheet.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateMeta(patch: Partial<Pick<UnitConsumptionSheet,
    'productName' | 'currentYear' | 'priorYear' | 'materialNames' | 'consumptionMaterialNames' | 'peerCompanies'>>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, ...patch }
    persist()
  }

  function updateCostStructure(id: string, patch: Partial<CostStructureMonth>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, costStructureRows: sheet.value.costStructureRows.map((r) => r.id === id ? { ...r, ...patch } : r) }
    persist()
  }

  function updateCostFlow(id: string, patch: Partial<CostFlowMonth>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, costFlowRows: sheet.value.costFlowRows.map((r) => r.id === id ? { ...r, ...patch } : r) }
    persist()
  }

  function updateUnitCost(id: string, patch: Partial<UnitCostMonth>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, unitCostRows: sheet.value.unitCostRows.map((r) => r.id === id ? { ...r, ...patch } : r) }
    persist()
  }

  function updatePeer(id: string, patch: Partial<PeerCostRow>): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, peerRows: sheet.value.peerRows.map((r) => r.id === id ? { ...r, ...patch } : r) }
    persist()
  }

  function updateMaterialConsumption(id: string, patch: Partial<MaterialConsumptionMonth>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      materialConsumptionRows: sheet.value.materialConsumptionRows.map((r) => r.id === id ? { ...r, ...patch } : r),
    }
    persist()
  }

  function updateMaterialCell(
    id: string,
    key: 'material1' | 'material2',
    patch: Partial<MaterialInputCell>,
  ): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      materialConsumptionRows: sheet.value.materialConsumptionRows.map((r) =>
        r.id === id ? { ...r, [key]: { ...r[key], ...patch } } : r),
    }
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
    sheet,
    auditNote,
    costStructureRows,
    costFlowRows,
    unitCostRows,
    materialConsumptionRows,
    abnormalCount,
    filledCount,
    updateMeta,
    updateCostStructure,
    updateCostFlow,
    updateUnitCost,
    updatePeer,
    updateMaterialConsumption,
    updateMaterialCell,
  }
}

export default useF2UnitConsumption
