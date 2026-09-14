/**
 * useF2InterviewSummary — F2-71 供应商访谈记录汇总（访谈项目×供应商转置矩阵）。
 * 联动：F2-70 注册地址、F2-68 采购额、F2-72 访谈明细索引。
 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  emptyInterviewSummaryEntity,
  enrichInterviewSummaryEntity,
  interviewSummarySummary,
  migrateInterviewSummaryEntities,
  nextAttSlot,
  type InterviewSummaryEntity,
} from './useF2InterviewSummaryFormulas'

const ROWS_KEY = 'F2-71-rows'
const NOTE_KEY = 'F2-71-note'
const F2_70_KEY = 'F2-70-entities'
const F2_68_KEY = 'F2-68-rows'
const F2_72_KEY = 'F2-72-entities'

export interface SupplierLinkage {
  /** F2-70 供应商名 → 注册地址 */
  registeredAddressOf: (name: string) => string
  /** F2-68 本年供应商名 → 采购额 */
  purchaseAmountOf: (name: string) => number | null
  /** 三张底稿去重后的供应商名单（弹窗录入联想用） */
  knownSuppliers: string[]
  /** F2-72 访谈明细中已建档的供应商名单 */
  interviewDetailSuppliers: string[]
}

function parseJson(response: ChecklistResponse | undefined): unknown {
  const raw = readSpeRowJson(response)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function useF2InterviewSummary(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const entities = ref<InterviewSummaryEntity[]>([emptyInterviewSummaryEntity()])
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

  function scheduleFlush(delay: number): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, delay)
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw && raw === JSON.stringify(entities.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateInterviewSummaryEntities(parsed)
        entities.value = migrated
        if (!readonly.value && JSON.stringify(parsed) !== JSON.stringify(migrated)) {
          opts.allResponses.value.set(ROWS_KEY, {
            item_id: ROWS_KEY,
            conclusion: null,
            remark: JSON.stringify(migrated),
          })
          scheduleFlush(300)
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedEntities = computed(() => entities.value.map(enrichInterviewSummaryEntity))
  const summary = computed(() => interviewSummarySummary(entities.value))

  // ─── 跨底稿联动 ─────────────────────────────────────────────────────────────
  const linkage = computed<SupplierLinkage>(() => {
    const infoEntities = parseJson(opts.allResponses.value.get(F2_70_KEY))
    const addressMap = new Map<string, string>()
    if (Array.isArray(infoEntities)) {
      for (const item of infoEntities) {
        const name = String((item as Record<string, unknown>)?.supplierName ?? '').trim()
        const address = String((item as Record<string, unknown>)?.registeredAddress ?? '').trim()
        if (name && address && !addressMap.has(name)) addressMap.set(name, address)
      }
    }

    const structureSheet = parseJson(opts.allResponses.value.get(F2_68_KEY)) as
      | { currentRows?: Array<Record<string, unknown>> }
      | null
    const amountMap = new Map<string, number>()
    for (const row of structureSheet?.currentRows ?? []) {
      const name = String(row?.supplierName ?? '').trim()
      const amount = Number(row?.purchaseAmount ?? 0)
      if (name && Number.isFinite(amount) && amount !== 0 && !amountMap.has(name)) {
        amountMap.set(name, amount)
      }
    }

    const detailEntities = parseJson(opts.allResponses.value.get(F2_72_KEY))
    const detailNames = Array.isArray(detailEntities)
      ? [...new Set(
          detailEntities
            .map((item) => String((item as Record<string, unknown>)?.supplierName ?? '').trim())
            .filter(Boolean),
        )]
      : []

    const known = [...new Set([
      ...addressMap.keys(),
      ...amountMap.keys(),
      ...detailNames,
    ])]

    return {
      registeredAddressOf: (name: string) => addressMap.get(name.trim()) ?? '',
      purchaseAmountOf: (name: string) => amountMap.get(name.trim()) ?? null,
      knownSuppliers: known,
      interviewDetailSuppliers: detailNames,
    }
  })

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(entities.value),
    })
    scheduleFlush(2000)
  }

  function addEntity(): void {
    if (readonly.value) return
    entities.value = [...entities.value, emptyInterviewSummaryEntity(nextAttSlot(entities.value))]
    persist()
  }

  /** 弹窗录入：以完整草稿新增，自动补 F2-70 注册地址，返回新实体 id。 */
  function addEntityFrom(patch: Partial<InterviewSummaryEntity>): string {
    const entity = {
      ...emptyInterviewSummaryEntity(nextAttSlot(entities.value)),
      ...patch,
    }
    if (!entity.registeredAddress && entity.supplierName) {
      entity.registeredAddress = linkage.value.registeredAddressOf(entity.supplierName)
    }
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

  function updateEntity(id: string, patch: Partial<InterviewSummaryEntity>): void {
    if (readonly.value) return
    entities.value = entities.value.map((entity) =>
      entity.id === id ? { ...entity, ...patch } : entity,
    )
    persist()
  }

  /** 从 F2-70 回填注册地址（联动按钮）。 */
  function fillRegisteredAddress(id: string): void {
    const entity = entities.value.find((item) => item.id === id)
    if (!entity || !entity.supplierName.trim()) return
    const address = linkage.value.registeredAddressOf(entity.supplierName)
    if (address) updateEntity(id, { registeredAddress: address })
  }

  watch(auditNote, (value) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, {
      item_id: NOTE_KEY,
      conclusion: null,
      remark: value,
    })
    scheduleFlush(2000)
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
    linkage,
    auditNote,
    addEntity,
    addEntityFrom,
    removeEntity,
    updateEntity,
    fillRegisteredAddress,
  }
}

export default useF2InterviewSummary
