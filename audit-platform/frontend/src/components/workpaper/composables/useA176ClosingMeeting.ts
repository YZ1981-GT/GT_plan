/**
 * useA176ClosingMeeting — A17-6 总结会会议纪要 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a17-6-closing-meeting/
 * Task: 2.1
 *
 * 职责：
 * - loadData(wpId): 自加载 render-config?force_component_type=a17-6-closing-meeting
 * - updateMeta(field, value): debounce 2s 批量保存 meta 字段
 * - updateField(field, value): debounce 2s 批量保存主字段
 * - flushPendingSaves(): 立即保存所有 pending 变更
 * - saving/lastSavedAt/saveError 状态指示
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A176MetaInfo {
  client_name: string
  period: string
  preparer: string
  reviewer: string
  date: string
  index_no: string
}

export interface A176Fields {
  meeting_time: string
  attendees: string
  minutes: string
  conclusion: string
  attachments: string
}

export interface A176ProjectContext {
  client_name: string
  period: string
  current_user: string
}

export interface UseA176Return {
  loading: Ref<boolean>
  metaInfo: Ref<A176MetaInfo>
  fields: Ref<A176Fields>
  projectContext: Ref<A176ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  saveError: Ref<boolean>
  loadData: (wpId: string) => Promise<void>
  updateMeta: (field: keyof A176MetaInfo, value: string) => void
  updateField: (field: keyof A176Fields, value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA176ClosingMeeting(wpId: Ref<string>): UseA176Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)
  const saveError = ref(false)

  const metaInfo = ref<A176MetaInfo>({
    client_name: '',
    period: '',
    preparer: '',
    reviewer: '',
    date: '',
    index_no: 'A17-6',
  })

  const fields = ref<A176Fields>({
    meeting_time: '',
    attendees: '',
    minutes: '',
    conclusion: '',
    attachments: '',
  })

  const projectContext = ref<A176ProjectContext>({
    client_name: '',
    period: '',
    current_user: '',
  })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load Data ───
  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a17-6-closing-meeting`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.meta_info) {
        Object.assign(metaInfo.value, htmlData.meta_info)
      }
      if (htmlData?.fields) {
        Object.assign(fields.value, htmlData.fields)
      }
      if (htmlData?.project_context) {
        Object.assign(projectContext.value, htmlData.project_context)
      }
    } catch {
      // 静态结构无需后端，加载失败不阻塞
    } finally {
      loading.value = false
    }
  }

  // ─── Update Meta ───
  function updateMeta(field: keyof A176MetaInfo, value: string) {
    metaInfo.value[field] = value
    const itemId = `a176-meta-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: value, remark: null })
    scheduleSave()
  }

  // ─── Update Field ───
  function updateField(field: keyof A176Fields, value: string) {
    fields.value[field] = value
    const itemId = `a176-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  // ─── Debounce Save ───
  function scheduleSave() {
    saveStatus.value = 'unsaved'
    saveError.value = false
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
      saveError.value = false
    } catch {
      if (retryCount < 3) {
        // 重试：把 items 放回 pending
        for (const item of items) pendingItems.set(item.item_id, item)
        setTimeout(() => doSave(retryCount + 1), 1000 * (retryCount + 1))
        return
      }
      saveStatus.value = 'unsaved'
      saveError.value = true
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

  return {
    loading,
    metaInfo,
    fields,
    projectContext,
    saveStatus,
    lastSavedAt,
    saveError,
    loadData,
    updateMeta,
    updateField,
    flushPendingSaves,
  }
}
