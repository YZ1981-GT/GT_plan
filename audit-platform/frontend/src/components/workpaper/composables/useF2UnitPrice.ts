/**
 * useF2UnitPrice — F2-62 三层采购单价交叉分析
 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  defaultUnitPriceSheet,
  emptyMonthlyGroup,
  emptyMonthlyItem,
  emptySpecGroup,
  emptySpecItem,
  enrichMonthlyGroups,
  enrichSpecGroups,
  isBlankMonthlyGroup,
  isBlankSpecGroup,
  migrateUnitPriceSheet,
  type MonthlyComparisonGroup,
  type MonthlyComparisonItem,
  type AnnualPeriodCell,
  type SpecComparisonGroup,
  type SpecComparisonItem,
  type UnitPriceCell,
  type UnitPriceSheet,
} from './useF2UnitPriceFormulas'

export type MonthlySection = 'supplierGroups' | 'materialGroups'

const ROWS_KEY = 'F2-62-rows'
const NOTE_KEY = 'F2-62-note'

export function useF2UnitPrice(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<UnitPriceSheet>(defaultUnitPriceSheet())
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
    // 自回声守卫：新增空组/空项写回后，避免迁移裁剪立即吃掉。
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateUnitPriceSheet(parsed)
        sheet.value = migrated
        const upgraded = Array.isArray(parsed)
        const beforeCount = upgraded
          ? parsed.length
          : (
              (parsed?.supplierGroups?.length || 0)
              + (parsed?.materialGroups?.length || 0)
              + (parsed?.specGroups?.length || 0)
            )
        const afterCount = migrated.supplierGroups.length
          + migrated.materialGroups.length
          + migrated.specGroups.length
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

  const supplierGroups = computed(() => enrichMonthlyGroups(sheet.value.supplierGroups))
  const materialGroups = computed(() => enrichMonthlyGroups(sheet.value.materialGroups))
  const specGroups = computed(() => enrichSpecGroups(sheet.value.specGroups))

  const filledGroupCount = computed(() =>
    sheet.value.supplierGroups.filter((g) => !isBlankMonthlyGroup(g)).length
    + sheet.value.materialGroups.filter((g) => !isBlankMonthlyGroup(g)).length
    + sheet.value.specGroups.filter((g) => !isBlankSpecGroup(g)).length,
  )
  const abnormalCount = computed(() =>
    supplierGroups.value.reduce((sum, group) => sum + group.abnormalCount, 0)
    + materialGroups.value.reduce((sum, group) => sum + group.abnormalCount, 0)
    + specGroups.value.reduce((sum, group) => sum + group.abnormalCount, 0),
  )
  const totalPurchaseAmount = computed(() =>
    supplierGroups.value.reduce((sum, group) => sum + group.totalAmount, 0),
  )

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

  function updateMonthlyGroup(
    section: MonthlySection,
    groupId: string,
    patch: Partial<MonthlyComparisonGroup>,
  ): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      [section]: sheet.value[section].map((group) =>
        group.id === groupId ? { ...group, ...patch } : group,
      ),
    }
    persist()
  }

  function addMonthlyGroup(section: MonthlySection): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      [section]: [...sheet.value[section], emptyMonthlyGroup()],
    }
    persist()
  }

  function removeMonthlyGroup(section: MonthlySection, groupId: string): void {
    if (readonly.value || sheet.value[section].length <= 1) return
    sheet.value = {
      ...sheet.value,
      [section]: sheet.value[section].filter((group) => group.id !== groupId),
    }
    persist()
  }

  function addMonthlyItem(section: MonthlySection, groupId: string): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      [section]: sheet.value[section].map((group) =>
        group.id === groupId
          ? { ...group, items: [...group.items, emptyMonthlyItem()] }
          : group,
      ),
    }
    persist()
  }

  function removeMonthlyItem(section: MonthlySection, groupId: string, itemId: string): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      [section]: sheet.value[section].map((group) =>
        group.id === groupId && group.items.length > 1
          ? { ...group, items: group.items.filter((item) => item.id !== itemId) }
          : group,
      ),
    }
    persist()
  }

  function updateMonthlyItem(
    section: MonthlySection,
    groupId: string,
    itemId: string,
    patch: Partial<MonthlyComparisonItem>,
  ): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      [section]: sheet.value[section].map((group) =>
        group.id === groupId
          ? {
              ...group,
              items: group.items.map((item) =>
                item.id === itemId ? { ...item, ...patch } : item,
              ),
            }
          : group,
      ),
    }
    persist()
  }

  function updateMonth(
    section: MonthlySection,
    groupId: string,
    itemId: string,
    monthIndex: number,
    patch: Partial<UnitPriceCell>,
  ): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      [section]: sheet.value[section].map((group) =>
        group.id === groupId
          ? {
              ...group,
              items: group.items.map((item) =>
                item.id === itemId
                  ? {
                      ...item,
                      months: item.months.map((month, i) =>
                        i === monthIndex ? { ...month, ...patch } : month,
                      ),
                    }
                  : item,
              ),
            }
          : group,
      ),
    }
    persist()
  }

  function updateSpecGroup(groupId: string, patch: Partial<SpecComparisonGroup>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      specGroups: sheet.value.specGroups.map((group) =>
        group.id === groupId ? { ...group, ...patch } : group,
      ),
    }
    persist()
  }

  function addSpecGroup(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      specGroups: [...sheet.value.specGroups, emptySpecGroup()],
    }
    persist()
  }

  function removeSpecGroup(groupId: string): void {
    if (readonly.value || sheet.value.specGroups.length <= 1) return
    sheet.value = {
      ...sheet.value,
      specGroups: sheet.value.specGroups.filter((group) => group.id !== groupId),
    }
    persist()
  }

  function addSpecItem(groupId: string): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      specGroups: sheet.value.specGroups.map((group) =>
        group.id === groupId
          ? { ...group, items: [...group.items, emptySpecItem()] }
          : group,
      ),
    }
    persist()
  }

  function removeSpecItem(groupId: string, itemId: string): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      specGroups: sheet.value.specGroups.map((group) =>
        group.id === groupId && group.items.length > 1
          ? { ...group, items: group.items.filter((item) => item.id !== itemId) }
          : group,
      ),
    }
    persist()
  }

  function updateSpecItem(
    groupId: string,
    itemId: string,
    patch: Partial<SpecComparisonItem>,
  ): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      specGroups: sheet.value.specGroups.map((group) =>
        group.id === groupId
          ? {
              ...group,
              items: group.items.map((item) =>
                item.id === itemId ? { ...item, ...patch } : item,
              ),
            }
          : group,
      ),
    }
    persist()
  }

  function updateSpecPeriod(
    groupId: string,
    itemId: string,
    periodIndex: number,
    patch: Partial<AnnualPeriodCell>,
  ): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      specGroups: sheet.value.specGroups.map((group) =>
        group.id === groupId
          ? {
              ...group,
              items: group.items.map((item) =>
                item.id === itemId
                  ? {
                      ...item,
                      periods: item.periods.map((period, i) =>
                        i === periodIndex ? { ...period, ...patch } : period,
                      ),
                    }
                  : item,
              ),
            }
          : group,
      ),
    }
    persist()
  }

  watch(auditNote, (value) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, {
      item_id: NOTE_KEY,
      conclusion: null,
      remark: value,
    })
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
    supplierGroups,
    materialGroups,
    specGroups,
    filledGroupCount,
    abnormalCount,
    totalPurchaseAmount,
    auditNote,
    updateMonthlyGroup,
    addMonthlyGroup,
    removeMonthlyGroup,
    addMonthlyItem,
    removeMonthlyItem,
    updateMonthlyItem,
    updateMonth,
    updateSpecGroup,
    addSpecGroup,
    removeSpecGroup,
    addSpecItem,
    removeSpecItem,
    updateSpecItem,
    updateSpecPeriod,
  }
}

export default useF2UnitPrice
