/**
 * useF2InterviewDetail — F2-72 供应商访谈记录（逐家正式问卷）。
 * 联动：F2-71 访谈汇总、F2-70 工商信息、F2-68 采购额。
 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  emptyInterviewDetailEntity,
  enrichInterviewDetailEntity,
  interviewDetailSummary,
  migrateInterviewDetailEntities,
  nextInterviewAttSlot,
  type InterviewDetailEntity,
  type InterviewQaItem,
} from './useF2InterviewDetailFormulas'

const ENTITIES_KEY = 'F2-72-entities'
const NOTE_KEY = 'F2-72-note'
const F2_71_KEY = 'F2-71-rows'
const F2_70_KEY = 'F2-70-entities'
const F2_68_KEY = 'F2-68-rows'

export interface InterviewDetailLinkage {
  knownSuppliers: string[]
  summaryOf: (name: string) => {
    interviewDate: string
    interviewee: string
    reason: string
    method: string
    recordIndex: string
  } | null
  profileOf: (name: string) => {
    registeredAddress: string
    staffScale: string
    registeredCapital: string
    businessScope: string
    legalRepresentative: string
  } | null
  purchaseAmountOf: (name: string) => number | null
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

export function useF2InterviewDetail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const entities = ref<InterviewDetailEntity[]>([emptyInterviewDetailEntity()])
  const currentId = ref(entities.value[0]?.id || '')
  const searchQuery = ref('')
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

  function scheduleFlush(delay: number): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, delay)
  }

  function ensureCurrent(): void {
    if (!entities.value.some((entity) => entity.id === currentId.value)) {
      currentId.value = entities.value[0]?.id || ''
    }
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ENTITIES_KEY))
    if (raw && raw === JSON.stringify(entities.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migrateInterviewDetailEntities(parsed)
        entities.value = migrated
        ensureCurrent()
        if (!readonly.value && JSON.stringify(parsed) !== JSON.stringify(migrated)) {
          opts.allResponses.value.set(ENTITIES_KEY, {
            item_id: ENTITIES_KEY,
            conclusion: null,
            remark: JSON.stringify(migrated),
          })
          scheduleFlush(300)
        }
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ENTITIES_KEY)?.remark, load, { immediate: true })

  const enrichedEntities = computed(() => entities.value.map(enrichInterviewDetailEntity))
  const filteredEntities = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedEntities.value
    return enrichedEntities.value.filter((entity) =>
      entity.supplierName.toLowerCase().includes(q)
      || entity.interviewee.toLowerCase().includes(q),
    )
  })
  const current = computed(() =>
    enrichedEntities.value.find((entity) => entity.id === currentId.value) || null,
  )
  const summary = computed(() => interviewDetailSummary(entities.value))

  const linkage = computed<InterviewDetailLinkage>(() => {
    const f271 = parseJson(opts.allResponses.value.get(F2_71_KEY))
    const summaryMap = new Map<string, {
      interviewDate: string
      interviewee: string
      reason: string
      method: string
      recordIndex: string
    }>()
    if (Array.isArray(f271)) {
      for (const item of f271) {
        const row = item as Record<string, unknown>
        const name = String(row.supplierName ?? '').trim()
        if (!name || summaryMap.has(name)) continue
        summaryMap.set(name, {
          interviewDate: String(row.interviewDate ?? ''),
          interviewee: String(row.interviewee ?? ''),
          reason: String(row.reason ?? ''),
          method: String(row.method ?? ''),
          recordIndex: String(row.recordIndex ?? ''),
        })
      }
    }

    const f270 = parseJson(opts.allResponses.value.get(F2_70_KEY))
    const profileMap = new Map<string, {
      registeredAddress: string
      staffScale: string
      registeredCapital: string
      businessScope: string
      legalRepresentative: string
    }>()
    if (Array.isArray(f270)) {
      for (const item of f270) {
        const row = item as Record<string, unknown>
        const name = String(row.supplierName ?? '').trim()
        if (!name || profileMap.has(name)) continue
        profileMap.set(name, {
          registeredAddress: String(row.registeredAddress ?? ''),
          staffScale: String(row.staffScale ?? ''),
          registeredCapital: String(row.registeredCapital ?? ''),
          businessScope: String(row.businessScope ?? ''),
          legalRepresentative: String(row.legalRepresentative ?? ''),
        })
      }
    }

    const f268 = parseJson(opts.allResponses.value.get(F2_68_KEY)) as
      | { currentRows?: Array<Record<string, unknown>> }
      | null
    const amountMap = new Map<string, number>()
    for (const row of f268?.currentRows ?? []) {
      const name = String(row?.supplierName ?? '').trim()
      const amount = Number(row?.purchaseAmount ?? 0)
      if (name && Number.isFinite(amount) && amount !== 0 && !amountMap.has(name)) {
        amountMap.set(name, amount)
      }
    }

    return {
      knownSuppliers: [...new Set([
        ...summaryMap.keys(),
        ...profileMap.keys(),
        ...amountMap.keys(),
      ])],
      summaryOf: (name: string) => summaryMap.get(name.trim()) ?? null,
      profileOf: (name: string) => profileMap.get(name.trim()) ?? null,
      purchaseAmountOf: (name: string) => amountMap.get(name.trim()) ?? null,
    }
  })

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ENTITIES_KEY, {
      item_id: ENTITIES_KEY,
      conclusion: null,
      remark: JSON.stringify(entities.value),
    })
    scheduleFlush(2000)
  }

  function selectEntity(id: string): void {
    currentId.value = id
  }

  function addEntity(): void {
    if (readonly.value) return
    const entity = emptyInterviewDetailEntity(nextInterviewAttSlot(entities.value))
    entities.value = [...entities.value, entity]
    currentId.value = entity.id
    persist()
  }

  function addEntityFrom(patch: Partial<InterviewDetailEntity>): string {
    const entity: InterviewDetailEntity = {
      ...emptyInterviewDetailEntity(nextInterviewAttSlot(entities.value)),
      ...patch,
      qaItems: patch.qaItems?.length
        ? patch.qaItems
        : emptyInterviewDetailEntity().qaItems,
    }
    if (readonly.value) return entity.id
    entities.value = [...entities.value, entity]
    currentId.value = entity.id
    persist()
    return entity.id
  }

  function removeEntity(id: string): void {
    if (readonly.value || entities.value.length <= 1) return
    entities.value = entities.value.filter((entity) => entity.id !== id)
    ensureCurrent()
    persist()
  }

  function updateEntity(id: string, patch: Partial<InterviewDetailEntity>): void {
    if (readonly.value) return
    entities.value = entities.value.map((entity) =>
      entity.id === id ? { ...entity, ...patch } : entity,
    )
    persist()
  }

  function updateQa(id: string, key: string, patch: Partial<InterviewQaItem>): void {
    if (readonly.value) return
    entities.value = entities.value.map((entity) => {
      if (entity.id !== id) return entity
      return {
        ...entity,
        qaItems: entity.qaItems.map((item) =>
          item.key === key ? { ...item, ...patch } : item,
        ),
      }
    })
    persist()
  }

  /** 从 F2-71/70 回填访谈对象、日期、公司概况等。 */
  function applyLinkage(id: string): void {
    const entity = entities.value.find((item) => item.id === id)
    if (!entity?.supplierName.trim()) return
    const name = entity.supplierName
    const from71 = linkage.value.summaryOf(name)
    const from70 = linkage.value.profileOf(name)
    const patch: Partial<InterviewDetailEntity> = {}
    if (from71) {
      if (!entity.interviewDate && from71.interviewDate) patch.interviewDate = from71.interviewDate
      if (!entity.interviewee && from71.interviewee) patch.interviewee = from71.interviewee
      if (!entity.interviewTimePlace && from71.interviewDate) {
        patch.interviewTimePlace = from71.interviewDate
      }
      if (!entity.remark && from71.reason) patch.remark = `访谈原因：${from71.reason}`
    }
    if (from70) {
      const q2 = entity.qaItems.find((item) => item.key === 'q2')
      if (q2 && !q2.answer.trim()) {
        const draft = [
          from70.legalRepresentative && `法定代表人：${from70.legalRepresentative}`,
          from70.registeredCapital && `注册资本：${from70.registeredCapital}`,
          from70.staffScale && `人员规模：${from70.staffScale}`,
          from70.registeredAddress && `注册地址：${from70.registeredAddress}`,
          from70.businessScope && `经营范围：${from70.businessScope}`,
        ].filter(Boolean).join('；')
        if (draft) {
          updateQa(id, 'q2', { answer: `（自 F2-70 带入）${draft}` })
        }
      }
    }
    const amount = linkage.value.purchaseAmountOf(name)
    if (amount !== null) {
      const q5 = entity.qaItems.find((item) => item.key === 'q5')
      if (q5 && !q5.answer.trim()) {
        updateQa(id, 'q5', {
          answer: `（自 F2-68 带入）被审计单位本年采购额约 ${amount.toLocaleString('zh-CN')} 元，请与供应商访谈确认销售额及占比。`,
        })
      }
    }
    if (Object.keys(patch).length) updateEntity(id, patch)
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
    filteredEntities,
    current,
    currentId,
    searchQuery,
    summary,
    linkage,
    auditNote,
    selectEntity,
    addEntity,
    addEntityFrom,
    removeEntity,
    updateEntity,
    updateQa,
    applyLinkage,
  }
}

export default useF2InterviewDetail
