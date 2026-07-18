/**
 * useF2LossContract — F2-58 亏损合同预计损失测算
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  defaultLossContractSheet,
  enrichLossContractProjects,
  calcLossContractTotals,
  migrateLossContractSheet,
  emptyLossContractProject,
  type LossContractSheet,
  type LossContractProject,
  type LossContractTotals,
} from './useF2LossContractFormulas'

export type {
  LossContractProject,
  EnrichedLossContract,
} from './useF2LossContractFormulas'

/** @deprecated 兼容旧引用 */
export type LossContractRow = LossContractProject

const ROWS_KEY = 'F2-58-rows'
const NOTE_KEY = 'F2-58-note'

export function useF2LossContract(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<LossContractSheet>(defaultLossContractSheet())
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    // persist() 会触发 watcher；内容未变化时跳过，避免刚新增的空行被迁移裁剪。
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateLossContractSheet(parsed)
        if (migrated) {
          const beforeCount = Array.isArray(parsed?.projects)
            ? parsed.projects.length
            : (Array.isArray(parsed) ? parsed.length : 0)
          sheet.value = migrated
          // 清理历史预留空行后立即写回，避免刷新时再次出现。
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

  const enrichedProjects = computed(() => enrichLossContractProjects(sheet.value.projects))
  const enrichedRows = enrichedProjects

  const columnTotals = computed<LossContractTotals>(() =>
    calcLossContractTotals(enrichedProjects.value),
  )

  const lossCount = computed(() =>
    enrichedProjects.value.filter((r) => r.isLoss === '是').length,
  )
  const adjustCount = computed(() =>
    enrichedProjects.value.filter((r) => r.hasDifference).length,
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

  function updateProject(id: string, patch: Partial<LossContractProject>): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      projects: sheet.value.projects.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    }
    persist()
  }

  function updateRow(
    id: string,
    patch: Partial<LossContractProject> & { managementProvision?: number },
  ): void {
    const mapped = { ...patch }
    if (patch.managementProvision != null) {
      mapped.bookRecognizedLoss = patch.managementProvision
    }
    delete (mapped as { managementProvision?: number }).managementProvision
    updateProject(id, mapped)
  }

  function addProject(): void {
    if (readonly.value) return
    sheet.value = {
      ...sheet.value,
      projects: [...sheet.value.projects, emptyLossContractProject()],
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
    enrichedProjects,
    enrichedRows,
    columnTotals,
    lossCount,
    adjustCount,
    auditNote,
    updateProject,
    updateRow,
    addProject,
    addRow,
    removeProject,
    removeRow,
  }
}

export default useF2LossContract
