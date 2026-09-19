/**
 * useA173ConsultationRecord — A17-3 业务咨询记录 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a17-3-consultation-record/
 * Task: 2.1
 *
 * 职责：
 * - loadData(wpId): 自加载 render-config?force_component_type=a17-3-consultation-record
 * - updateMeta(field, value): debounce 2s 保存 meta 字段
 * - updateSection(secNum, field, value): debounce 2s 保存 section 字段
 * - addFileTag(fileName): 添加文件引用 tag
 * - removeFileTag(index): 删除文件引用 tag
 * - flushPendingSaves(): 立即保存所有 pending 变更
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface A173MetaInfo {
  department: string
  client_name: string
  consult_type: string
  period: string
  /** 咨询事项编号：多事项时与 A17-3-1.consultation_id 成对 */
  consultation_id: string
  /** 本项目无业务咨询 → 标不适用 */
  not_applicable: string
}

export interface A173Sections {
  1: { overview: string; background: string; files: string[] }
  2: { opinion: string }
  3: { standards: string; reply: string }
  4: { opinion: string }
}

export interface A173ProjectContext {
  client_name: string
  period: string
  current_user: string
}

export interface UseA173Return {
  loading: Ref<boolean>
  metaInfo: Ref<A173MetaInfo>
  sections: Ref<A173Sections>
  projectContext: Ref<A173ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  loadData: (wpId?: string) => Promise<void>
  updateMeta: (field: keyof A173MetaInfo, value: string) => void
  updateSection: (secNum: number, field: string, value: string) => void
  addFileTag: (fileName: string) => void
  removeFileTag: (index: number) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const CONSULT_TYPE_OPTIONS = [
  '会计处理',
  '审计程序',
  '独立性',
  '职业道德',
  '其他',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA173ConsultationRecord(wpId: Ref<string>): UseA173Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const metaInfo = ref<A173MetaInfo>({
    department: '',
    client_name: '',
    consult_type: '',
    period: '',
    consultation_id: '',
    not_applicable: '',
  })

  const sections = ref<A173Sections>({
    1: { overview: '', background: '', files: [] },
    2: { opinion: '' },
    3: { standards: '', reply: '' },
    4: { opinion: '' },
  })

  const projectContext = ref<A173ProjectContext>({
    client_name: '',
    period: '',
    current_user: '',
  })

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load Data ───
  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=a17-3-consultation-record`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.meta_info) {
        Object.assign(metaInfo.value, htmlData.meta_info)
      }
      if (htmlData?.sections) {
        const s = htmlData.sections
        if (s['1']) {
          sections.value[1] = {
            overview: s['1'].overview || '',
            background: s['1'].background || '',
            files: Array.isArray(s['1'].files) ? s['1'].files : [],
          }
        }
        if (s['2']) {
          sections.value[2] = { opinion: s['2'].opinion || '' }
        }
        if (s['3']) {
          sections.value[3] = {
            standards: s['3'].standards || '',
            reply: s['3'].reply || '',
          }
        }
        if (s['4']) {
          sections.value[4] = { opinion: s['4'].opinion || '' }
        }
      }
      if (htmlData?.project_context) {
        Object.assign(projectContext.value, htmlData.project_context)
      }
    } catch { /* 静态结构无需后端 */ }
    finally { loading.value = false }
  }

  // ─── Update Meta ───
  function updateMeta(field: keyof A173MetaInfo, value: string) {
    metaInfo.value[field] = value
    const itemId = `a173-meta-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: value, remark: null })
    scheduleSave()
  }

  // ─── Update Section ───
  function updateSection(secNum: number, field: string, value: string) {
    const sec = sections.value[secNum as keyof A173Sections]
    if (sec && field in sec) {
      (sec as any)[field] = value
    }
    const itemId = `a173-sec${secNum}-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  // ─── File Tag Management ───
  function addFileTag(fileName: string) {
    const trimmed = fileName.trim()
    if (!trimmed) return
    sections.value[1].files.push(trimmed)
    _enqueueFilesSave()
  }

  function removeFileTag(index: number) {
    const list = sections.value[1].files
    if (index >= 0 && index < list.length) {
      list.splice(index, 1)
      _enqueueFilesSave()
    }
  }

  function _enqueueFilesSave() {
    const list = sections.value[1].files
    const itemId = 'a173-sec1-files'
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: String(list.length),
      remark: JSON.stringify(list),
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
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
    await doSave()
  }

  return {
    loading,
    metaInfo,
    sections,
    projectContext,
    saveStatus,
    lastSavedAt,
    loadData,
    updateMeta,
    updateSection,
    addFileTag,
    removeFileTag,
    flushPendingSaves,
  }
}
