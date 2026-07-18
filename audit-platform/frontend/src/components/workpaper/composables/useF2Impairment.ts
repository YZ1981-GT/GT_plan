/**
 * useF2Impairment — F2-57 合同履约成本减值准备测算
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  debouncedPublishF2SpeDisclosureNote,
  publishF2SpeSubstantiveAdjudicated,
} from './useF2SpeEventBus'
import {
  defaultContractCostImpairmentSheet,
  enrichImpairmentProjects,
  calcImpairmentTotals,
  calcImpairmentAmountTotal,
  migrateContractCostImpairmentSheet,
  emptyImpairmentProject,
  type ContractCostImpairmentSheet,
  type ContractCostImpairmentProject,
  type ContractCostImpairmentTotals,
} from './useF2ContractCostImpairmentFormulas'

export type {
  ContractCostImpairmentProject,
  EnrichedContractCostImpairment,
} from './useF2ContractCostImpairmentFormulas'

/** @deprecated 兼容旧引用 */
export type ImpairmentRow = ContractCostImpairmentProject

const ROWS_KEY = 'F2-57-rows'
const NOTE_KEY = 'F2-57-note'

export function useF2Impairment(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let adjudicatedTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<ContractCostImpairmentSheet>(defaultContractCostImpairmentSheet())
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    // 自回声守卫：persist() 写回后 watcher 会再次触发 load，
    // 若内容与内存一致则跳过，避免 migrate 的空行裁剪吃掉刚新增的空行。
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateContractCostImpairmentSheet(parsed)
        if (migrated) {
          const beforeCount = Array.isArray(parsed?.projects)
            ? parsed.projects.length
            : (Array.isArray(parsed) ? parsed.length : 0)
          sheet.value = migrated
          // 裁掉历史预留空行并写回，避免刷新后再次出现。
          if (!readonly.value && beforeCount > migrated.projects.length) {
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
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedProjects = computed(() => enrichImpairmentProjects(sheet.value.projects))
  const enrichedRows = enrichedProjects

  const columnTotals = computed<ContractCostImpairmentTotals>(() =>
    calcImpairmentTotals(enrichedProjects.value),
  )

  const impairmentTotal = computed(() => calcImpairmentAmountTotal(enrichedProjects.value))
  const diffCount = computed(() => enrichedProjects.value.filter((r) => r.hasDifference).length)
  const impairedCount = computed(() =>
    enrichedProjects.value.filter((r) => r.isImpaired === '是').length,
  )

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

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

  function updateProject(id: string, patch: Partial<ContractCostImpairmentProject>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      projects: sheet.value.projects.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function updateRow(id: string, patch: Partial<ContractCostImpairmentProject>): void {
    updateProject(id, patch)
  }

  function addProject(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      projects: [...sheet.value.projects, emptyImpairmentProject()],
    }
    persist()
  }

  function addRow(): void {
    addProject()
  }

  function removeProject(id: string): void {
    if (readonly.value || sheet.value.projects.length <= 1) return
    sheet.value = {
      ...sheet.value,
      projects: sheet.value.projects.filter((p) => p.id !== id),
    }
    persist()
  }

  function removeRow(id: string): void {
    removeProject(id)
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debouncedPublishF2SpeDisclosureNote('impairment', val)
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  })

  watch(
    impairmentTotal,
    (amount) => {
      if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
      adjudicatedTimer = setTimeout(() => {
        adjudicatedTimer = null
        publishF2SpeSubstantiveAdjudicated({
          wpCode: 'F2-special',
          accountCode: '1405',
          impairmentAmount: amount,
        })
      }, 2000)
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
    if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
  })

  return {
    sheet,
    enrichedProjects,
    enrichedRows,
    columnTotals,
    impairmentTotal,
    diffCount,
    impairedCount,
    auditNote,
    updateProject,
    updateRow,
    addProject,
    addRow,
    removeProject,
    removeRow,
  }
}

export default useF2Impairment
