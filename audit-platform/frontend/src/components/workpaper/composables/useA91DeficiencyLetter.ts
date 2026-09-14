/**
 * useA91DeficiencyLetter — A9-1 内控缺陷沟通函 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a9-1-deficiency-letter/
 * Task: 2.1
 *
 * 职责：
 * - reactive section data + deficiency list management
 * - 2s debounce save to checklist-responses batch API (item_id: `a91-{section}-{field_id}`)
 * - deficiency add/remove/update
 * - flush pending saves
 * - B22B refresh via render-config reload
 * - section navigation scrollspy
 */
import { ref, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DeficiencyItem {
  id: string
  description: string
  impact: string
  recommendation: string
  indexRef: string | null
  source: 'b22b' | 'manual'
  severity: 'major' | 'significant' | 'general'
}

export interface A91SectionData {
  addressee: { client_name: string; custom_text: string | null }
  independence: {
    team_independent: 'Y' | 'N' | null
    no_relationships: 'Y' | 'N' | null
    no_relationships_detail: string | null
    safeguards_taken: 'Y' | 'N' | null
    non_audit_services: 'Y' | 'N' | null
    non_audit_services_detail: string | null
  }
  committee: { applicability: 'Y' | 'N' | 'NA' | null; description: string | null }
  signature: { date: string | null }
  response: {
    opinion: string | null
    conclusion: string | null
    representative: string | null
    response_date: string | null
  }
}

export interface A91ProjectContext {
  client_name: string
  firm_name: string
  audit_report_date: string | null
}

export interface A91RenderData {
  section_data?: Partial<A91SectionData>
  deficiency_list?: {
    major?: DeficiencyItem[]
    significant?: DeficiencyItem[]
    general?: DeficiencyItem[]
  }
  project_context?: Partial<A91ProjectContext>
  b22b_warning?: string | null
}

export interface UseA91DeficiencyLetterOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<A91RenderData | null>
  itemIdPrefix?: string  // 'a91' | 'a92', default 'a91'
}

export interface UseA91DeficiencyLetterReturn {
  sectionData: Ref<A91SectionData>
  deficiencyList: Ref<{ major: DeficiencyItem[]; significant: DeficiencyItem[]; general: DeficiencyItem[] }>
  projectContext: Ref<A91ProjectContext>
  b22bWarning: Ref<string | null>
  loading: Ref<boolean>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  activeSection: Ref<string>
  updateField: (section: string, fieldId: string, value: string) => void
  addDeficiency: (severity: string) => void
  removeDeficiency: (severity: string, index: number) => void
  updateDeficiency: (severity: string, index: number, field: string, value: string) => void
  flushPendingSaves: () => Promise<void>
  refreshFromB22B: () => Promise<void>
  scrollToSection: (sectionId: string) => void
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const VALID_SECTIONS = ['addressee', 'independence', 'deficiency', 'committee', 'signature', 'response'] as const
type ValidSection = typeof VALID_SECTIONS[number]

function generateId(): string {
  return crypto.randomUUID ? crypto.randomUUID() : `def-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/** Build item_id for a section+field combination */
export function buildItemId(section: string, fieldId: string, prefix: string = 'a91'): string {
  return `${prefix}-${section}-${fieldId}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA91DeficiencyLetter(opts: UseA91DeficiencyLetterOptions): UseA91DeficiencyLetterReturn {
  const { wpId, projectId, htmlData } = opts
  const prefix = opts.itemIdPrefix ?? 'a91'

  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const activeSection = ref('addressee')

  const sectionData = ref<A91SectionData>({
    addressee: { client_name: '', custom_text: null },
    independence: {
      team_independent: null,
      no_relationships: null,
      no_relationships_detail: null,
      safeguards_taken: null,
      non_audit_services: null,
      non_audit_services_detail: null,
    },
    committee: { applicability: null, description: null },
    signature: { date: null },
    response: {
      opinion: null,
      conclusion: null,
      representative: null,
      response_date: null,
    },
  })

  const deficiencyList = ref<{ major: DeficiencyItem[]; significant: DeficiencyItem[]; general: DeficiencyItem[] }>({
    major: [],
    significant: [],
    general: [],
  })

  const projectContext = ref<A91ProjectContext>({
    client_name: '',
    firm_name: '致同会计师事务所（特殊普通合伙）',
    audit_report_date: null,
  })

  const b22bWarning = ref<string | null>(null)

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Initialize from htmlData ───
  function hydrateFromRenderData(data: A91RenderData | null) {
    if (!data) return
    if (data.section_data) {
      const sd = data.section_data
      if (sd.addressee) Object.assign(sectionData.value.addressee, sd.addressee)
      if (sd.independence) Object.assign(sectionData.value.independence, sd.independence)
      if (sd.committee) Object.assign(sectionData.value.committee, sd.committee)
      if (sd.signature) Object.assign(sectionData.value.signature, sd.signature)
      if (sd.response) Object.assign(sectionData.value.response, sd.response)
    }
    if (data.deficiency_list) {
      const dl = data.deficiency_list
      if (dl.major) deficiencyList.value.major = dl.major
      if (dl.significant) deficiencyList.value.significant = dl.significant
      if (dl.general) deficiencyList.value.general = dl.general
    }
    if (data.project_context) {
      Object.assign(projectContext.value, data.project_context)
    }
    b22bWarning.value = data.b22b_warning ?? null
  }

  // Watch htmlData for changes (initial load + refresh)
  watch(htmlData, (newData) => {
    hydrateFromRenderData(newData)
  }, { immediate: true })

  // ─── Update Field ───
  function updateField(section: string, fieldId: string, value: string) {
    // Update local reactive state
    const sec = sectionData.value[section as keyof A91SectionData]
    if (sec && fieldId in sec) {
      (sec as any)[fieldId] = value
    }

    const itemId = buildItemId(section, fieldId, prefix)
    // For most fields, use conclusion for short values, remark for long text
    if (section === 'response' && ['opinion', 'conclusion'].includes(fieldId)) {
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    } else if (section === 'independence' && fieldId.endsWith('_detail')) {
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    } else if (section === 'committee' && fieldId === 'description') {
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    } else {
      pendingItems.set(itemId, { item_id: itemId, conclusion: value, remark: null })
    }
    scheduleSave()
  }

  // ─── Deficiency List Management ───
  function addDeficiency(severity: string) {
    const sev = severity as keyof typeof deficiencyList.value
    if (!deficiencyList.value[sev]) return

    const newItem: DeficiencyItem = {
      id: generateId(),
      description: '',
      impact: '',
      recommendation: '',
      indexRef: null,
      source: 'manual',
      severity: sev,
    }
    deficiencyList.value[sev].push(newItem)
    _enqueueDeficiencySave(sev)
  }

  function removeDeficiency(severity: string, index: number) {
    const sev = severity as keyof typeof deficiencyList.value
    if (!deficiencyList.value[sev]) return
    if (index >= 0 && index < deficiencyList.value[sev].length) {
      deficiencyList.value[sev].splice(index, 1)
      _enqueueDeficiencySave(sev)
    }
  }

  function updateDeficiency(severity: string, index: number, field: string, value: string) {
    const sev = severity as keyof typeof deficiencyList.value
    if (!deficiencyList.value[sev]) return
    if (index >= 0 && index < deficiencyList.value[sev].length) {
      const item = deficiencyList.value[sev][index]
      if (field in item) {
        (item as any)[field] = value
      }
      _enqueueDeficiencySave(sev)
    }
  }

  function _enqueueDeficiencySave(severity: keyof typeof deficiencyList.value) {
    const itemId = buildItemId('deficiency', severity, prefix)
    const items = deficiencyList.value[severity]
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: String(items.length),
      remark: JSON.stringify(items),
    })
    scheduleSave()
  }

  // ─── Debounce Save ───
  function scheduleSave() {
    saveStatus.value = 'unsaved'
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; doSave() }, 2000)
  }

  async function doSave(retryCount = 0) {
    if (pendingItems.size === 0) return
    const items = [...pendingItems.values()]
    pendingItems.clear()
    saveStatus.value = 'saving'

    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      saveStatus.value = 'saved'
    } catch {
      if (retryCount < 3) {
        for (const item of items) pendingItems.set(item.item_id, item)
        setTimeout(() => doSave(retryCount + 1), 1000 * (retryCount + 1))
        return
      }
      saveStatus.value = 'unsaved'
      ElMessage.warning('保存失败，请检查网络后重试')
    }
  }

  // ─── Flush ───
  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSave()
  }

  // ─── Refresh from B22B ───
  async function refreshFromB22B(): Promise<void> {
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${wpId.value}/render-config?force_component_type=a9-1-deficiency-letter`,
        { _silent: true } as any,
      )
      const data = res?.sheets?.[0]?.html_data ?? res
      if (data?.deficiency_list) {
        const dl = data.deficiency_list
        if (dl.major) deficiencyList.value.major = dl.major
        if (dl.significant) deficiencyList.value.significant = dl.significant
        if (dl.general) deficiencyList.value.general = dl.general
      }
      b22bWarning.value = data?.b22b_warning ?? null
    } catch {
      // 静默失败，保留当前缺陷列表
    } finally {
      loading.value = false
    }
  }

  // ─── Section Navigation ───
  function scrollToSection(sectionId: string) {
    activeSection.value = sectionId
    const el = document.getElementById(`section-${sectionId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  // ─── EventBus: DEFICIENCY_EVALUATED 监听 ───
  function _onDeficiencyEvaluated() {
    refreshFromB22B()
  }

  onMounted(() => {
    eventBus.on('deficiency:severity-evaluated' as any, _onDeficiencyEvaluated)
  })

  onBeforeUnmount(() => {
    eventBus.off('deficiency:severity-evaluated' as any, _onDeficiencyEvaluated)
  })

  return {
    sectionData,
    deficiencyList,
    projectContext,
    b22bWarning,
    loading,
    saveStatus,
    activeSection,
    updateField,
    addDeficiency,
    removeDeficiency,
    updateDeficiency,
    flushPendingSaves,
    refreshFromB22B,
    scrollToSection,
  }
}
