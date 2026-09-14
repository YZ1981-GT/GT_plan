/**
 * useA1731ConsultationExecution — A17-3-1 业务咨询结果执行情况记录 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a17-3-1-consultation-execution/
 * Task: 2.1
 *
 * 职责：
 * - loadData(wpId): 自加载 render-config?force_component_type=a17-3-1-consultation-execution
 * - updateMeta(field, value): debounce 2s 保存 meta 字段
 * - updateSection(secNum, field, value): debounce 2s 保存 section 字段
 * - flushPendingSaves(): 立即保存所有 pending 变更
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A1731MetaInfo {
  executor: string
  execution_date: string
  review_date: string
  reviewer: string
  /** 勾选「无需执行」时关闭 A17-3↔3-1 成对要求 */
  not_required: string
  /** 关联的 A17-3 咨询事项编号 */
  consultation_id: string
}

export interface A1731Sections {
  1: { supplementary: string }
  2: { execution_details: string }
  3: { results: string }
  4: { follow_up: string }
}

export interface A1731A173Reference {
  overview: string
  background: string
  reply: string
}

export interface A1731ProjectContext {
  client_name: string
  period: string
}

export interface UseA1731Return {
  loading: Ref<boolean>
  metaInfo: Ref<A1731MetaInfo>
  sections: Ref<A1731Sections>
  a173Reference: Ref<A1731A173Reference>
  projectContext: Ref<A1731ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  loadData: (wpId?: string) => Promise<void>
  updateMeta: (field: keyof A1731MetaInfo, value: string) => void
  updateSection: (secNum: number, field: string, value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA1731ConsultationExecution(wpId: Ref<string>): UseA1731Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const metaInfo = ref<A1731MetaInfo>({
    executor: '',
    execution_date: '',
    review_date: '',
    reviewer: '',
    not_required: '',
    consultation_id: '',
  })

  const sections = ref<A1731Sections>({
    1: { supplementary: '' },
    2: { execution_details: '' },
    3: { results: '' },
    4: { follow_up: '' },
  })

  const a173Reference = ref<A1731A173Reference>({
    overview: '',
    background: '',
    reply: '',
  })

  const projectContext = ref<A1731ProjectContext>({
    client_name: '',
    period: '',
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
        `/api/workpapers/${targetId}/render-config?force_component_type=a17-3-1-consultation-execution`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.meta_info) {
        Object.assign(metaInfo.value, htmlData.meta_info)
      }
      if (htmlData?.sections) {
        const s = htmlData.sections
        if (s['1']) sections.value[1] = { supplementary: s['1'].supplementary || '' }
        if (s['2']) sections.value[2] = { execution_details: s['2'].execution_details || '' }
        if (s['3']) sections.value[3] = { results: s['3'].results || '' }
        if (s['4']) sections.value[4] = { follow_up: s['4'].follow_up || '' }
      }
      if (htmlData?.a173_reference) {
        a173Reference.value = {
          overview: htmlData.a173_reference.overview || '',
          background: htmlData.a173_reference.background || '',
          reply: htmlData.a173_reference.reply || '',
        }
      }
      if (htmlData?.project_context) {
        Object.assign(projectContext.value, htmlData.project_context)
      }
      // Auto-fill meta from project context if empty
      if (!metaInfo.value.executor && projectContext.value.client_name) {
        // client_name auto-fill not applicable for executor - skip
      }
    } catch {
      // 静态结构无需后端，加载失败不阻塞
    } finally {
      loading.value = false
    }
  }

  // ─── Update Meta ───
  function updateMeta(field: keyof A1731MetaInfo, value: string) {
    metaInfo.value[field] = value
    const itemId = `a1731-meta-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: value, remark: null })
    scheduleSave()
  }

  // ─── Update Section ───
  function updateSection(secNum: number, field: string, value: string) {
    const sec = sections.value[secNum as keyof A1731Sections]
    if (sec && field in sec) {
      (sec as any)[field] = value
    }
    const itemId = `a1731-sec${secNum}-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
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
    sections,
    a173Reference,
    projectContext,
    saveStatus,
    lastSavedAt,
    loadData,
    updateMeta,
    updateSection,
    flushPendingSaves,
  }
}
