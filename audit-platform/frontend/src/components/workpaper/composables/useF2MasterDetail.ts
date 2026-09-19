/**
 * useF2MasterDetail — F2-70 供应商信息核查 / F2-72 访谈记录
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export type MasterDetailKind = 'supplier-info' | 'interview'

export interface SupplierInfoEntity {
  id: string
  supplierName: string
  creditCode: string
  legalRepresentative: string
  registeredCapital: string
  establishDate: string
  businessScope: string
  operatingAddress: string
  employeeCount: number
  mainCustomers: string
  financialStatus: string
  cooperationYears: number
  transactionAmount: number
  checkMethod: string
  checkConclusion: string
}

export interface InterviewQa {
  id: string
  question: string
  answer: string
}

export interface InterviewEntity {
  id: string
  supplierName: string
  interviewDate: string
  interviewee: string
  topic: string
  auditFocus: string
  conclusion: string
  qaPairs: InterviewQa[]
}

const SUPPLIER_KEY = 'F2-70-entities'
const SUPPLIER_NOTE = 'F2-70-note'
const INTERVIEW_KEY = 'F2-72-entities'
const INTERVIEW_NOTE = 'F2-72-note'

function genId(): string {
  return `md-${Date.now().toString(36)}`
}

function emptySupplier(id: string): SupplierInfoEntity {
  return {
    id, supplierName: '', creditCode: '', legalRepresentative: '', registeredCapital: '',
    establishDate: '', businessScope: '', operatingAddress: '', employeeCount: 0,
    mainCustomers: '', financialStatus: '', cooperationYears: 0, transactionAmount: 0,
    checkMethod: '', checkConclusion: '',
  }
}

function emptyInterview(id: string): InterviewEntity {
  return {
    id, supplierName: '', interviewDate: '', interviewee: '', topic: '',
    auditFocus: '', conclusion: '', qaPairs: [{ id: genId(), question: '', answer: '' }],
  }
}

export function useF2MasterDetail(opts: {
  kind: Ref<MasterDetailKind>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const entitiesKey = computed(() => (opts.kind.value === 'supplier-info' ? SUPPLIER_KEY : INTERVIEW_KEY))
  const noteKey = computed(() => (opts.kind.value === 'supplier-info' ? SUPPLIER_NOTE : INTERVIEW_NOTE))

  const suppliers = ref<SupplierInfoEntity[]>([emptySupplier(genId())])
  const interviews = ref<InterviewEntity[]>([emptyInterview(genId())])
  const currentId = ref('')
  const searchQuery = ref('')
  const auditNote = ref('')

  function load(): void {
    const key = entitiesKey.value
    const raw = readSpeRowJson(opts.allResponses.value.get(key))
    if (opts.kind.value === 'supplier-info') {
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as SupplierInfoEntity[]
          if (parsed.length) suppliers.value = parsed
        } catch { /* ignore */ }
      }
      if (!suppliers.value.some((s) => s.id === currentId.value) && suppliers.value.length) {
        currentId.value = suppliers.value[0].id
      }
    } else {
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as InterviewEntity[]
          if (parsed.length) interviews.value = parsed
        } catch { /* ignore */ }
      }
      if (!interviews.value.some((i) => i.id === currentId.value) && interviews.value.length) {
        currentId.value = interviews.value[0].id
      }
    }
    auditNote.value = opts.allResponses.value.get(noteKey.value)?.remark || ''
  }

  watch(
    () => [
      entitiesKey.value,
      opts.allResponses.value.get(entitiesKey.value)?.remark,
      opts.allResponses.value.get(noteKey.value)?.remark,
    ] as const,
    load,
    { immediate: true },
  )

  const entityList = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (opts.kind.value === 'supplier-info') {
      return suppliers.value.filter((s) => !q || s.supplierName.toLowerCase().includes(q))
    }
    return interviews.value.filter((i) => !q || i.supplierName.toLowerCase().includes(q))
  })

  const currentSupplier = computed(() =>
    suppliers.value.find((s) => s.id === currentId.value) ?? null,
  )

  const currentInterview = computed(() =>
    interviews.value.find((i) => i.id === currentId.value) ?? null,
  )

  const groupedInterviews = computed(() => {
    const map = new Map<string, InterviewEntity[]>()
    for (const i of entityList.value as InterviewEntity[]) {
      const k = i.supplierName || '未命名'
      if (!map.has(k)) map.set(k, [])
      map.get(k)!.push(i)
    }
    return map
  })

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(entitiesKey.value),
      opts.allResponses.value.get(noteKey.value),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    const payload = opts.kind.value === 'supplier-info'
      ? JSON.stringify(suppliers.value)
      : JSON.stringify(interviews.value)
    opts.allResponses.value.set(entitiesKey.value, {
      item_id: entitiesKey.value, conclusion: null, remark: payload,
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function selectEntity(id: string): void {
    currentId.value = id
  }

  async function addEntity(): Promise<void> {
    if (readonly.value) return
    try {
      const label = opts.kind.value === 'supplier-info' ? '供应商名称' : '供应商（访谈对象）'
      const { value } = await ElMessageBox.prompt(`请输入${label}`, '新增', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      const id = genId()
      if (opts.kind.value === 'supplier-info') {
        suppliers.value = [...suppliers.value, { ...emptySupplier(id), supplierName: value }]
      } else {
        interviews.value = [...interviews.value, { ...emptyInterview(id), supplierName: value }]
      }
      currentId.value = id
      persist()
    } catch { /* cancelled */ }
  }

  function removeEntity(id: string): void {
    if (readonly.value) return
    if (opts.kind.value === 'supplier-info') {
      if (suppliers.value.length <= 1) return
      suppliers.value = suppliers.value.filter((s) => s.id !== id)
    } else {
      if (interviews.value.length <= 1) return
      interviews.value = interviews.value.filter((i) => i.id !== id)
    }
    if (currentId.value === id) {
      currentId.value = opts.kind.value === 'supplier-info'
        ? suppliers.value[0]?.id ?? ''
        : interviews.value[0]?.id ?? ''
    }
    persist()
  }

  function updateSupplier(id: string, patch: Partial<SupplierInfoEntity>): void {
    if (readonly.value) return
    suppliers.value = suppliers.value.map((s) => (s.id === id ? { ...s, ...patch } : s))
    persist()
  }

  function updateInterview(id: string, patch: Partial<InterviewEntity>): void {
    if (readonly.value) return
    interviews.value = interviews.value.map((i) => (i.id === id ? { ...i, ...patch } : i))
    persist()
  }

  function addQa(interviewId: string): void {
    if (readonly.value) return
    interviews.value = interviews.value.map((i) =>
      i.id === interviewId
        ? { ...i, qaPairs: [...i.qaPairs, { id: genId(), question: '', answer: '' }] }
        : i,
    )
    persist()
  }

  function removeQa(interviewId: string, qaId: string): void {
    if (readonly.value) return
    interviews.value = interviews.value.map((i) => {
      if (i.id !== interviewId || i.qaPairs.length <= 1) return i
      return { ...i, qaPairs: i.qaPairs.filter((q) => q.id !== qaId) }
    })
    persist()
  }

  function updateQa(interviewId: string, qaId: string, patch: Partial<InterviewQa>): void {
    if (readonly.value) return
    interviews.value = interviews.value.map((i) =>
      i.id === interviewId
        ? { ...i, qaPairs: i.qaPairs.map((q) => (q.id === qaId ? { ...q, ...patch } : q)) }
        : i,
    )
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(noteKey.value, { item_id: noteKey.value, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    searchQuery,
    entityList,
    currentId,
    currentSupplier,
    currentInterview,
    groupedInterviews,
    auditNote,
    selectEntity,
    addEntity,
    removeEntity,
    updateSupplier,
    updateInterview,
    addQa,
    removeQa,
    updateQa,
  }
}

export default useF2MasterDetail
