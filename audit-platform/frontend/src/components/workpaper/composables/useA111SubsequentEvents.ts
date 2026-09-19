/**
 * useA111SubsequentEvents — A11-1 期后事项问询函 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a11-1-subsequent-events-inquiry/
 * Task: 2.1
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A111QAItem {
  number: number
  title: string
  text: string
  hasGuidance: boolean
  guidanceText: string | null
  answer: string
}

export interface A111MetaData {
  inquiryDate: string | null
  interviewee: string | null
  location: string | null
  teamSignature: string | null
}

export interface A111ProjectContext {
  clientName: string
  balanceSheetDate: string | null
}

export interface UseA111SubsequentEventsReturn {
  loading: Ref<boolean>
  metaData: Ref<A111MetaData>
  qaList: Ref<A111QAItem[]>
  evidence: Ref<string>
  projectContext: Ref<A111ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  activeNavItem: Ref<string>
  loadData: (wpId?: string) => Promise<void>
  updateMeta: (fieldId: string, value: string) => void
  updateAnswer: (questionNumber: number, value: string) => void
  updateEvidence: (value: string) => void
  flushPendingSaves: () => Promise<void>
  scrollToItem: (itemId: string) => void
}

// ─── Navigation items (12 fixed) ─────────────────────────────────────────────

export const NAV_ITEMS = [
  { id: 'nav-meta', label: '元信息' },
  { id: 'nav-q1', label: 'Q1' },
  { id: 'nav-q2', label: 'Q2' },
  { id: 'nav-q3', label: 'Q3' },
  { id: 'nav-q4', label: 'Q4' },
  { id: 'nav-q5', label: 'Q5' },
  { id: 'nav-q6', label: 'Q6' },
  { id: 'nav-q7', label: 'Q7' },
  { id: 'nav-q8', label: 'Q8' },
  { id: 'nav-q9', label: 'Q9' },
  { id: 'nav-q10', label: 'Q10' },
  { id: 'nav-evidence', label: '证据' },
] as const

// ─── Default QA list (10 items, empty answers) ───────────────────────────────

function createDefaultQaList(): A111QAItem[] {
  return Array.from({ length: 10 }, (_, i) => ({
    number: i + 1,
    title: '',
    text: '',
    hasGuidance: false,
    guidanceText: null,
    answer: '',
  }))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA111SubsequentEvents(wpId: Ref<string>): UseA111SubsequentEventsReturn {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)
  const activeNavItem = ref('nav-meta')

  const metaData = ref<A111MetaData>({
    inquiryDate: null,
    interviewee: null,
    location: null,
    teamSignature: null,
  })

  const qaList = ref<A111QAItem[]>(createDefaultQaList())
  const evidence = ref('')
  const projectContext = ref<A111ProjectContext>({ clientName: '', balanceSheetDate: null })

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a11-1-subsequent-events-inquiry`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res

      // Meta data
      if (htmlData?.meta_data) {
        const m = htmlData.meta_data
        metaData.value = {
          inquiryDate: m.inquiry_date ?? null,
          interviewee: m.interviewee ?? null,
          location: m.location ?? null,
          teamSignature: m.team_signature ?? null,
        }
      }

      // QA list (merge config + answers)
      if (htmlData?.questions_config && Array.isArray(htmlData.questions_config)) {
        const answers = htmlData.qa_list || []
        qaList.value = htmlData.questions_config.map((q: any, i: number) => ({
          number: q.number ?? i + 1,
          title: q.title ?? '',
          text: q.text ?? '',
          hasGuidance: q.has_guidance ?? false,
          guidanceText: q.guidance_text ?? null,
          answer: answers[i]?.answer ?? '',
        }))
      }

      // Evidence
      if (htmlData?.evidence != null) {
        evidence.value = htmlData.evidence || ''
      }

      // Project context
      if (htmlData?.project_context) {
        projectContext.value = {
          clientName: htmlData.project_context.client_name || '',
          balanceSheetDate: htmlData.project_context.balance_sheet_date ?? null,
        }
      }
    } catch { /* 静态结构无需后端 */ }
    finally { loading.value = false }
  }

  function updateMeta(fieldId: string, value: string) {
    const key = fieldId as keyof A111MetaData
    if (key in metaData.value) {
      (metaData.value as any)[key] = value || null
    }
    const itemId = `a111-meta-${_toSnakeCase(fieldId)}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  function updateAnswer(questionNumber: number, value: string) {
    const qa = qaList.value.find(q => q.number === questionNumber)
    if (qa) qa.answer = value
    const itemId = `a111-qa-${questionNumber}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  function updateEvidence(value: string) {
    evidence.value = value
    const itemId = 'a111-evidence-description'
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

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
      lastSavedAt.value = new Date()
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

  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
    await doSave()
  }

  function scrollToItem(itemId: string) {
    activeNavItem.value = itemId
    const el = document.getElementById(itemId)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return {
    loading, metaData, qaList, evidence, projectContext,
    saveStatus, lastSavedAt, activeNavItem,
    loadData, updateMeta, updateAnswer, updateEvidence, flushPendingSaves, scrollToItem,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _toSnakeCase(str: string): string {
  return str.replace(/([A-Z])/g, '_$1').toLowerCase().replace(/^_/, '')
}
