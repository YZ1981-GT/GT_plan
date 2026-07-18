/**
 * useF2CapacityEnergy — F2-63 存货产量与产能、能耗分析（四区块状态管理）
 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  calcEnergyTotals,
  defaultCapacityEnergySheet,
  emptyCapacityRow,
  emptyEnergyRow,
  emptyProductEnergyRow,
  emptyStorageRow,
  enrichCapacityRow,
  enrichEnergyRow,
  enrichProductEnergyRow,
  groupStorageRows,
  isBlankCapacityRow,
  isBlankProductEnergyRow,
  isBlankStorageRow,
  isUnusedEnergyRow,
  migrateCapacityEnergySheet,
  type CapacityCompareRow,
  type CapacityEnergySheet,
  type EnergyPurchaseRow,
  type ProductEnergyRow,
  type StorageCompareRow,
} from './useF2CapacityEnergyFormulas'

const ROWS_KEY = 'F2-63-rows'
const NOTE_KEY = 'F2-63-note'

type SectionKey = keyof CapacityEnergySheet

export function useF2CapacityEnergy(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<CapacityEnergySheet>(defaultCapacityEnergySheet())
  const auditNote = ref('')

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    // 自回声守卫：新增空行写回后，避免迁移裁剪立即吃掉。
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateCapacityEnergySheet(parsed)
        sheet.value = migrated
        const upgraded = Array.isArray(parsed)
        const beforeCount = upgraded
          ? parsed.length
          : (
              (parsed?.capacityRows?.length || 0)
              + (parsed?.storageRows?.length || 0)
              + (parsed?.energyRows?.length || 0)
              + (parsed?.productEnergyRows?.length || 0)
            )
        const afterCount = migrated.capacityRows.length
          + migrated.storageRows.length
          + migrated.energyRows.length
          + migrated.productEnergyRows.length
        if (!readonly.value && (upgraded || beforeCount > afterCount)) {
          opts.allResponses.value.set(ROWS_KEY, {
            item_id: ROWS_KEY,
            conclusion: null,
            remark: JSON.stringify(migrated),
          })
          if (debounceTimer) clearTimeout(debounceTimer)
          debounceTimer = setTimeout(() => {
            debounceTimer = null
            flushSave()
          }, 300)
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  // ─── 派生数据 ─────────────────────────────────────────────────────────
  const capacityRows = computed(() => sheet.value.capacityRows.map(enrichCapacityRow))
  const storageGroups = computed(() => groupStorageRows(sheet.value.storageRows))
  const energyRows = computed(() => sheet.value.energyRows.map(enrichEnergyRow))
  const energyTotals = computed(() => calcEnergyTotals(sheet.value.energyRows))
  const productEnergyRows = computed(() => sheet.value.productEnergyRows.map(enrichProductEnergyRow))

  const filledCount = computed(() =>
    sheet.value.capacityRows.filter((r) => !isBlankCapacityRow(r)).length
    + sheet.value.storageRows.filter((r) => !isBlankStorageRow(r)).length
    + sheet.value.energyRows.filter((r) => !isUnusedEnergyRow(r)).length
    + sheet.value.productEnergyRows.filter((r) => !isBlankProductEnergyRow(r)).length,
  )

  const abnormalCount = computed(() =>
    capacityRows.value.filter((r) => r.isAbnormal).length
    + storageGroups.value.reduce((s, g) => s + g.rows.filter((r) => r.isAbnormal).length, 0)
    + energyRows.value.filter((r) => r.isAbnormal).length
    + productEnergyRows.value.filter((r) => r.isAbnormal).length,
  )

  // ─── 持久化与编辑 ─────────────────────────────────────────────────────
  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function mutateSection<K extends SectionKey>(
    section: K,
    mutate: (rows: CapacityEnergySheet[K]) => CapacityEnergySheet[K],
  ): void {
    if (readonly.value) return
    sheet.value = { ...sheet.value, [section]: mutate(sheet.value[section]) }
    persist()
  }

  function updateCapacityRow(id: string, patch: Partial<CapacityCompareRow>): void {
    mutateSection('capacityRows', (rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }
  function addCapacityRow(): void {
    mutateSection('capacityRows', (rows) => [...rows, emptyCapacityRow()])
  }
  function removeCapacityRow(id: string): void {
    if (sheet.value.capacityRows.length <= 1) return
    mutateSection('capacityRows', (rows) => rows.filter((r) => r.id !== id))
  }

  function updateStorageRow(id: string, patch: Partial<StorageCompareRow>): void {
    mutateSection('storageRows', (rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }
  function addStorageRow(warehouseName = ''): void {
    mutateSection('storageRows', (rows) => [...rows, { ...emptyStorageRow(), warehouseName }])
  }
  function removeStorageRow(id: string): void {
    if (sheet.value.storageRows.length <= 1) return
    mutateSection('storageRows', (rows) => rows.filter((r) => r.id !== id))
  }

  function updateEnergyRow(id: string, patch: Partial<EnergyPurchaseRow>): void {
    mutateSection('energyRows', (rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }
  function addEnergyRow(): void {
    mutateSection('energyRows', (rows) => [...rows, emptyEnergyRow()])
  }
  function removeEnergyRow(id: string): void {
    if (sheet.value.energyRows.length <= 1) return
    mutateSection('energyRows', (rows) => rows.filter((r) => r.id !== id))
  }

  function updateProductEnergyRow(id: string, patch: Partial<ProductEnergyRow>): void {
    mutateSection('productEnergyRows', (rows) => rows.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }
  function addProductEnergyRow(): void {
    mutateSection('productEnergyRows', (rows) => [...rows, emptyProductEnergyRow()])
  }
  function removeProductEnergyRow(id: string): void {
    if (sheet.value.productEnergyRows.length <= 1) return
    mutateSection('productEnergyRows', (rows) => rows.filter((r) => r.id !== id))
  }

  watch(auditNote, (value) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: value })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheet,
    capacityRows,
    storageGroups,
    energyRows,
    energyTotals,
    productEnergyRows,
    filledCount,
    abnormalCount,
    auditNote,
    updateCapacityRow,
    addCapacityRow,
    removeCapacityRow,
    updateStorageRow,
    addStorageRow,
    removeStorageRow,
    updateEnergyRow,
    addEnergyRow,
    removeEnergyRow,
    updateProductEnergyRow,
    addProductEnergyRow,
    removeProductEnergyRow,
  }
}

export default useF2CapacityEnergy
