/**
 * useF2CapacityEnergy — F2-63 产量与产能/能耗分析（51行×16列）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcChangeRate } from './useF2InvMaiFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export interface CapacityEnergyRow {
  id: string
  productName: string
  productLine: string
  designCapacity: number
  actualOutput: number
  elecTotal: number
  waterTotal: number
  gasTotal: number
  priorOutput: number
  priorElecTotal: number
  changeNote: string
  auditFocus: string
}

export interface EnrichedCapacityEnergyRow extends CapacityEnergyRow {
  utilizationPct: number | 'N/A'
  unitElec: number | '-'
  unitWater: number | '-'
  unitGas: number | '-'
  priorUtilizationPct: number | 'N/A'
  priorUnitElec: number | '-'
  unitElecChangeRate: number | '' | 'N/A'
  isOverCapacity: boolean
  isEnergyAbnormal: boolean
  highlight: boolean
}

const ROWS_KEY = 'F2-63-rows'
const NOTE_KEY = 'F2-63-note'
const ENERGY_CHANGE_THRESHOLD = 0.2

function emptyRow(id: string): CapacityEnergyRow {
  return {
    id, productName: '', productLine: '',
    designCapacity: 0, actualOutput: 0,
    elecTotal: 0, waterTotal: 0, gasTotal: 0,
    priorOutput: 0, priorElecTotal: 0, changeNote: '', auditFocus: '',
  }
}

function calcUtilization(actual: number, design: number): number | 'N/A' {
  if (!design) return 'N/A'
  return (actual / design) * 100
}

function calcUnitConsumption(total: number, output: number): number | '-' {
  if (!output) return '-'
  return total / output
}

export function enrichCapacityEnergyRow(r: CapacityEnergyRow): EnrichedCapacityEnergyRow {
  const utilizationPct = calcUtilization(r.actualOutput, r.designCapacity)
  const unitElec = calcUnitConsumption(r.elecTotal, r.actualOutput)
  const unitWater = calcUnitConsumption(r.waterTotal, r.actualOutput)
  const unitGas = calcUnitConsumption(r.gasTotal, r.actualOutput)
  const priorUtilizationPct = calcUtilization(r.priorOutput, r.designCapacity)
  const priorUnitElec = calcUnitConsumption(r.priorElecTotal, r.priorOutput)
  const unitElecChangeRate = typeof unitElec === 'number' && typeof priorUnitElec === 'number'
    ? calcChangeRate(priorUnitElec, unitElec)
    : ''
  const isOverCapacity = typeof utilizationPct === 'number' && utilizationPct > 100
  const isEnergyAbnormal = typeof unitElecChangeRate === 'number'
    && Math.abs(unitElecChangeRate) > ENERGY_CHANGE_THRESHOLD
  return {
    ...r,
    utilizationPct,
    unitElec,
    unitWater,
    unitGas,
    priorUtilizationPct,
    priorUnitElec,
    unitElecChangeRate,
    isOverCapacity,
    isEnergyAbnormal,
    highlight: isOverCapacity || isEnergyAbnormal,
  }
}

export function useF2CapacityEnergy(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<CapacityEnergyRow[]>([emptyRow('1')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as CapacityEnergyRow[]
        if (parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichCapacityEnergyRow))

  const abnormalCount = computed(() =>
    enrichedRows.value.filter((r) => r.highlight).length,
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

  function updateRow(id: string, patch: Partial<CapacityEnergyRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入产品名称', '新增产品线', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      rows.value = [...rows.value, { ...emptyRow(String(Date.now())), productName: value }]
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
    abnormalCount,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2CapacityEnergy
