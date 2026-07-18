/** F2-70 供应商信息核查表状态管理（沿用 F2-70-entities 存储键）。 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  emptySupplierInfoEntity,
  enrichSupplierInfoEntity,
  migrateSupplierInfoEntities,
  supplierInfoSummary,
  type SupplierInfoEntity,
} from './useF2SupplierInfoCheckFormulas'

const ENTITIES_KEY = 'F2-70-entities'
const NOTE_KEY = 'F2-70-note'

export function useF2SupplierInfoCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const entities = ref<SupplierInfoEntity[]>([emptySupplierInfoEntity()])
  const auditNote = ref('')

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ENTITIES_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ENTITIES_KEY))
    if (raw && raw === JSON.stringify(entities.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateSupplierInfoEntities(parsed)
        entities.value = migrated
        if (!readonly.value && JSON.stringify(parsed) !== JSON.stringify(migrated)) {
          opts.allResponses.value.set(ENTITIES_KEY, {
            item_id: ENTITIES_KEY,
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

  watch(() => opts.allResponses.value.get(ENTITIES_KEY)?.remark, load, { immediate: true })

  const enrichedEntities = computed(() => entities.value.map(enrichSupplierInfoEntity))
  const summary = computed(() => supplierInfoSummary(entities.value))

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ENTITIES_KEY, {
      item_id: ENTITIES_KEY,
      conclusion: null,
      remark: JSON.stringify(entities.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function addEntity(): void {
    if (readonly.value) return
    entities.value = [...entities.value, emptySupplierInfoEntity()]
    persist()
  }

  /** 弹窗录入：以完整草稿新增一列，返回新实体 id。 */
  function addEntityFrom(patch: Partial<SupplierInfoEntity>): string {
    const entity = { ...emptySupplierInfoEntity(), ...patch }
    if (readonly.value) return entity.id
    entities.value = [...entities.value, entity]
    persist()
    return entity.id
  }

  function removeEntity(id: string): void {
    if (readonly.value || entities.value.length <= 1) return
    entities.value = entities.value.filter((entity) => entity.id !== id)
    persist()
  }

  function updateEntity(id: string, patch: Partial<SupplierInfoEntity>): void {
    if (readonly.value) return
    entities.value = entities.value.map((entity) =>
      entity.id === id ? { ...entity, ...patch } : entity,
    )
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
    entities,
    enrichedEntities,
    summary,
    auditNote,
    addEntity,
    addEntityFrom,
    removeEntity,
    updateEntity,
  }
}

export default useF2SupplierInfoCheck
