/**
 * useF2StocktakeQuestionnaire — F2-21 v2 问卷持久化
 */
import { ref, watch, onBeforeUnmount, type Ref } from 'vue'
import type { ChecklistResponse } from './useF2StocktakeFormData'
import {
  emptyQuestionnaire,
  normalizeQuestionnaire,
  migrateLegacyToQuestionnaire,
  isQuestionnaireFilled,
  type F21QuestionnaireData,
  type F21LocationRow,
  type F21PersonnelRow,
  emptyLocationRow,
  emptyPersonnelRow,
} from '../f2/stocktake/f2StocktakeQuestionnaire'

const FIELDS_KEY = 'F2-21-fields'
const NOTE_KEY = 'F2-21-note'
const ROWS_KEY = 'F2-21-rows'

export function useF2StocktakeQuestionnaire(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const data = ref<F21QuestionnaireData>(emptyQuestionnaire())
  const auditNote = ref('')
  const dirty = ref(false)

  function load(): void {
    const raw = opts.allResponses.value.get(FIELDS_KEY)?.remark
    let parsed: Record<string, unknown> | null = null
    if (raw) {
      try {
        parsed = JSON.parse(raw) as Record<string, unknown>
      } catch { /* ignore */ }
    }
    const legacyRows = opts.allResponses.value.get(ROWS_KEY)?.remark
    const hasV2 = parsed && (parsed.version === 2 || Array.isArray(parsed.locations))
    const hasLegacyFlat = !!(parsed && !hasV2 && (
      ['countSchedule', 'warehouses', 'auditors', 'remoteWarehouse', 'expertNeeded'].some(
        (k) => String((parsed as Record<string, unknown>)[k] || '').trim(),
      )
      || Object.values(parsed).some((v) => typeof v === 'string' && String(v).trim())
    ))
    if (hasV2) {
      data.value = normalizeQuestionnaire(parsed)
    } else if (hasLegacyFlat || legacyRows) {
      data.value = migrateLegacyToQuestionnaire(parsed, legacyRows)
    } else {
      data.value = emptyQuestionnaire()
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    dirty.value = false
  }

  watch(() => opts.allResponses.value.get(FIELDS_KEY)?.remark, load, { immediate: true })
  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load)
  watch(() => opts.allResponses.value.get(NOTE_KEY)?.remark, (v) => {
    if (v != null) auditNote.value = v
  })

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(FIELDS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail: { items } }))
    }
    dirty.value = false
  }

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(FIELDS_KEY, {
      item_id: FIELDS_KEY,
      conclusion: null,
      remark: JSON.stringify(data.value),
    })
    dirty.value = true
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 800)
  }

  function saveNow(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    if (readonly.value) return
    opts.allResponses.value.set(FIELDS_KEY, {
      item_id: FIELDS_KEY,
      conclusion: null,
      remark: JSON.stringify(data.value),
    })
    opts.allResponses.value.set(NOTE_KEY, {
      item_id: NOTE_KEY,
      conclusion: null,
      remark: auditNote.value,
    })
    flushSave()
  }

  function replaceData(next: F21QuestionnaireData): void {
    data.value = normalizeQuestionnaire(next)
    persist()
  }

  function updateAnswer(id: string, val: string): void {
    if (readonly.value) return
    data.value = {
      ...data.value,
      answers: { ...data.value.answers, [id]: val },
    }
    persist()
  }

  function updateLocation(id: string, patch: Partial<F21LocationRow>): void {
    if (readonly.value) return
    data.value = {
      ...data.value,
      locations: data.value.locations.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    }
    persist()
  }

  function addLocation(): void {
    if (readonly.value) return
    data.value = { ...data.value, locations: [...data.value.locations, emptyLocationRow()] }
    persist()
  }

  function removeLocation(id: string): void {
    if (readonly.value || data.value.locations.length <= 1) return
    data.value = { ...data.value, locations: data.value.locations.filter((r) => r.id !== id) }
    persist()
  }

  function updatePersonnel(id: string, patch: Partial<F21PersonnelRow>): void {
    if (readonly.value) return
    data.value = {
      ...data.value,
      personnel: data.value.personnel.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    }
    persist()
  }

  function addPersonnel(): void {
    if (readonly.value) return
    data.value = { ...data.value, personnel: [...data.value.personnel, emptyPersonnelRow()] }
    persist()
  }

  function removePersonnel(id: string): void {
    if (readonly.value || data.value.personnel.length <= 1) return
    data.value = { ...data.value, personnel: data.value.personnel.filter((r) => r.id !== id) }
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 800)
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      saveNow()
    }
  })

  const progress = () => isQuestionnaireFilled(data.value)

  return {
    data,
    auditNote,
    dirty,
    load,
    saveNow,
    replaceData,
    updateAnswer,
    updateLocation,
    addLocation,
    removeLocation,
    updatePersonnel,
    addPersonnel,
    removePersonnel,
    progress,
  }
}

export default useF2StocktakeQuestionnaire
