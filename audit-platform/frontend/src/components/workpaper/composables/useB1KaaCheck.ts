/**
 * useB1KaaCheck — B1-5 KAA检查程序表 数据管理 + 持久化
 *
 * 一节任一"是"→达到KAA标准（需二节审批/报备）。自动结论可被手工覆盖。
 * item_id 前缀 b1kaa-：
 * - 判定 b1kaa-{sk}-{seq}(conclusion) + 说明 -note(remark)
 * - 子项 b1kaa-{sk}-{seq}-{subSeq}(conclusion)
 * - 头部 b1kaa-hdr-{field}(remark)
 * - 结论 b1kaa-overall-conclusion(conclusion reached/not_reached)
 */
import { ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface KaaSubItem { seq: string; text: string; answer: string }
export interface KaaItem {
  seq: string
  text: string
  kind: 'judge' | 'group'
  answer: string
  note: string
  sub_items: KaaSubItem[]
}
export interface KaaSection { key: string; title: string; items: KaaItem[] }
export interface KaaHeaderField { field: string; label: string }
export interface KaaRenderData {
  source_sheet: string
  sections: KaaSection[]
  header_fields: KaaHeaderField[]
  header: Record<string, string>
  auto_conclusion: string
  conclusion: string
  conclusion_note: string
  reached: boolean
  project_context: Record<string, string>
}

export const KAA_CHOICE_OPTIONS = ['是', '否', 'N/A'] as const

export interface UseB1KaaOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<KaaRenderData | null>
  onAfterSave?: () => void
}

export function useB1KaaCheck(opts: UseB1KaaOptions) {
  const { wpId, htmlData, onAfterSave } = opts

  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const sourceSheet = ref('')
  const sections = ref<KaaSection[]>([])
  const headerFields = ref<KaaHeaderField[]>([])
  const header = ref<Record<string, string>>({})
  const autoConclusion = ref('not_reached')
  const manualConclusion = ref('')
  const conclusionNote = ref('')
  const projectContext = ref<Record<string, string>>({})

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function hydrate(data: KaaRenderData | null) {
    if (!data) return
    sourceSheet.value = data.source_sheet || ''
    if (Array.isArray(data.sections)) sections.value = JSON.parse(JSON.stringify(data.sections))
    if (Array.isArray(data.header_fields)) headerFields.value = data.header_fields
    if (data.header) header.value = { ...data.header }
    autoConclusion.value = data.auto_conclusion || 'not_reached'
    // conclusion 若与 auto 不同说明是手工覆盖
    manualConclusion.value = data.conclusion && data.conclusion !== data.auto_conclusion ? data.conclusion : ''
    conclusionNote.value = data.conclusion_note || ''
    if (data.project_context) projectContext.value = { ...data.project_context }
  }
  watch(htmlData, (nd) => hydrate(nd), { immediate: true })

  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=b1-5-kaa-check`,
        { _silent: true } as any,
      )
      hydrate(res?.sheets?.[0]?.html_data ?? res)
    } catch {
      /* 静默 */
    } finally {
      loading.value = false
    }
  }

  // ─── 自动结论（一节任一"是"）───
  function computeReached(): boolean {
    const std = sections.value.find((s) => s.key === 'standard')
    if (!std) return false
    for (const it of std.items) {
      if (it.answer === '是') return true
      for (const sub of it.sub_items) if (sub.answer === '是') return true
    }
    return false
  }

  function findItem(sk: string, seq: string): KaaItem | undefined {
    return sections.value.find((s) => s.key === sk)?.items.find((i) => i.seq === seq)
  }

  function updateAnswer(sk: string, seq: string, value: string) {
    const it = findItem(sk, seq)
    if (!it) return
    it.answer = value
    const id = `b1kaa-${sk}-${seq}`
    pendingItems.set(id, { item_id: id, conclusion: value || null, remark: null })
    scheduleSave()
  }
  function updateNote(sk: string, seq: string, value: string) {
    const it = findItem(sk, seq)
    if (!it) return
    it.note = value
    const id = `b1kaa-${sk}-${seq}-note`
    pendingItems.set(id, { item_id: id, conclusion: null, remark: value || null })
    scheduleSave()
  }
  function updateSubAnswer(sk: string, seq: string, subSeq: string, value: string) {
    const it = findItem(sk, seq)
    const sub = it?.sub_items.find((s) => s.seq === subSeq)
    if (!sub) return
    sub.answer = value
    const id = `b1kaa-${sk}-${seq}-${subSeq}`
    pendingItems.set(id, { item_id: id, conclusion: value || null, remark: null })
    scheduleSave()
  }
  function updateHeader(field: string, value: string) {
    header.value[field] = value
    const id = `b1kaa-hdr-${field}`
    pendingItems.set(id, { item_id: id, conclusion: null, remark: value || null })
    scheduleSave()
  }
  function updateManualConclusion(value: string) {
    manualConclusion.value = value
    pendingItems.set('b1kaa-overall-conclusion', {
      item_id: 'b1kaa-overall-conclusion', conclusion: value || null, remark: null,
    })
    scheduleSave()
  }
  function updateConclusionNote(value: string) {
    conclusionNote.value = value
    pendingItems.set('b1kaa-conclusion-note', {
      item_id: 'b1kaa-conclusion-note', conclusion: null, remark: value || null,
    })
    scheduleSave()
  }

  function scheduleSave() {
    saveStatus.value = 'unsaved'
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; doSave() }, 2000)
  }
  async function doSave(retry = 0) {
    if (pendingItems.size === 0) return
    const items = [...pendingItems.values()]
    pendingItems.clear()
    saveStatus.value = 'saving'
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      saveStatus.value = 'saved'
      try { onAfterSave?.() } catch { /* 版本快照失败不影响保存 */ }
    } catch {
      if (retry < 3) {
        for (const it of items) pendingItems.set(it.item_id, it)
        setTimeout(() => doSave(retry + 1), 1000 * (retry + 1))
        return
      }
      saveStatus.value = 'unsaved'
      ElMessage.warning('保存失败，请检查网络后重试')
    }
  }
  async function flushPendingSaves() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
    await doSave()
  }

  return {
    loading, saveStatus, sourceSheet, sections, headerFields, header,
    autoConclusion, manualConclusion, conclusionNote, projectContext,
    computeReached, updateAnswer, updateNote, updateSubAnswer, updateHeader,
    updateManualConclusion, updateConclusionNote, flushPendingSaves, loadData,
  }
}
