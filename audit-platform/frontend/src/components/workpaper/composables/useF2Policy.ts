/**
 * useF2Policy — F2-16 会计政策核查
 * Spec: .kiro/specs/f2-inventory-main/ Task 10.1
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import type { ChecklistResponse } from './useF2FormData'

export interface F2PolicySection {
  key: string
  title: string
  policyDesc: string
  isChanged: '是' | '否'
  changeReason: string
  auditEval: string
  indexRef: string
}

const STORAGE_KEY = 'F2-16-policy'
const CONCLUSION_KEY = 'F2-16-conclusion'

export const F2_POLICY_SECTION_DEFS = [
  { key: 'classification', title: '存货分类与确认' },
  { key: 'initial', title: '初始计量方法' },
  { key: 'pricing', title: '发出存货计价方法' },
  { key: 'impairment', title: '存货跌价准备计提政策' },
  { key: 'count', title: '存货盘点制度' },
] as const

function defaultSections(): F2PolicySection[] {
  return F2_POLICY_SECTION_DEFS.map((d) => ({
    key: d.key,
    title: d.title,
    policyDesc: '',
    isChanged: '否' as const,
    changeReason: '',
    auditEval: '',
    indexRef: '',
  }))
}

function safeParse(jsonStr: string | null | undefined): F2PolicySection[] {
  if (!jsonStr) return defaultSections()
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return defaultSections()
    const map = new Map(parsed.map((s: F2PolicySection) => [s.key, s]))
    return F2_POLICY_SECTION_DEFS.map((d) => ({
      ...defaultSections().find((x) => x.key === d.key)!,
      ...(map.get(d.key) || {}),
      key: d.key,
      title: d.title,
    }))
  } catch {
    return defaultSections()
  }
}

export function useF2Policy(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sections = ref<F2PolicySection[]>(defaultSections())
  const policyConclusion = ref('')

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    (v) => { sections.value = safeParse(v) },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(CONCLUSION_KEY)?.remark,
    (v) => { policyConclusion.value = v || '' },
    { immediate: true },
  )

  const changedCount = computed(() => sections.value.filter((s) => s.isChanged === '是').length)

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persistSections(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(sections.value),
    })
    debounceSave()
  }

  function updateSection(key: string, field: keyof Omit<F2PolicySection, 'key' | 'title'>, value: string): void {
    if (readonly.value) return
    const idx = sections.value.findIndex((s) => s.key === key)
    if (idx === -1) return
    const next = { ...sections.value[idx], [field]: value }
    sections.value.splice(idx, 1, next)
    persistSections()
  }

  watch(policyConclusion, (val) => {
    if (readonly.value) return
    allResponses.value.set(CONCLUSION_KEY, {
      item_id: CONCLUSION_KEY,
      conclusion: null,
      remark: val,
    })
    debounceSave()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    sections,
    policyConclusion,
    changedCount,
    updateSection,
  }
}

export default useF2Policy
