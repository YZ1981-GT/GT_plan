/**
 * useA174DisagreementRecord — A17-4 重大专业分歧事项记录 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a17-4-disagreement-record/
 * Task: 2.1
 *
 * 职责：
 * - loadData(wpId): 自加载 render-config?force_component_type=a17-4-disagreement-record
 * - addPersonnel(): 添加人员行
 * - removePersonnel(index): 删除人员行
 * - updatePersonnel(index, field, value): 更新人员字段
 * - updateSection(secNum, value): 更新章节内容
 * - updateSignature(field, value): 更新签字字段
 * - flushPendingSaves(): 立即保存所有 pending 变更
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PersonnelRow {
  name: string
  position: string
  role: string
}

export interface A174Sections {
  1: { parties: string }
  2: { cause: string }
  3: { procedures: string }
  4: { opinions: string }
  5: { considerations: string }
  6: { conclusion: string }
}

export interface A174SignatureData {
  preparer: string
  reviewer: string
  date: string
}

export interface A174ProjectContext {
  client_name: string
  current_user: string
}

export interface UseA174Return {
  loading: Ref<boolean>
  personnel: Ref<PersonnelRow[]>
  sections: Ref<A174Sections>
  signatureData: Ref<A174SignatureData>
  projectContext: Ref<A174ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  lastSavedAt: Ref<Date | null>
  notApplicable: Ref<boolean>
  loadData: (wpId?: string) => Promise<void>
  addPersonnel: () => void
  removePersonnel: (index: number) => void
  updatePersonnel: (index: number, field: keyof PersonnelRow, value: string) => void
  updateSection: (secNum: number, value: string) => void
  updateSignature: (field: keyof A174SignatureData, value: string) => void
  setNotApplicable: (v: boolean) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Section field map ───────────────────────────────────────────────────────

const SECTION_FIELD_MAP: Record<number, string> = {
  1: 'parties',
  2: 'cause',
  3: 'procedures',
  4: 'opinions',
  5: 'considerations',
  6: 'conclusion',
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA174DisagreementRecord(wpId: Ref<string>): UseA174Return {
  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const lastSavedAt = ref<Date | null>(null)

  const personnel = ref<PersonnelRow[]>([])

  const sections = ref<A174Sections>({
    1: { parties: '' },
    2: { cause: '' },
    3: { procedures: '' },
    4: { opinions: '' },
    5: { considerations: '' },
    6: { conclusion: '' },
  })

  const signatureData = ref<A174SignatureData>({
    preparer: '',
    reviewer: '',
    date: '',
  })

  const projectContext = ref<A174ProjectContext>({
    client_name: '',
    current_user: '',
  })

  const notApplicable = ref(false)

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
        `/api/workpapers/${targetId}/render-config?force_component_type=a17-4-disagreement-record`,
        { _silent: true } as any,
      )
      const htmlData = res?.sheets?.[0]?.html_data ?? res
      if (htmlData?.personnel && Array.isArray(htmlData.personnel)) {
        personnel.value = htmlData.personnel.map((p: any) => ({
          name: p.name || '',
          position: p.position || '',
          role: p.role || '',
        }))
      }
      if (htmlData?.sections) {
        const s = htmlData.sections
        for (const num of [1, 2, 3, 4, 5, 6] as const) {
          const field = SECTION_FIELD_MAP[num]
          if (s[String(num)] && field in s[String(num)]) {
            (sections.value[num] as any)[field] = s[String(num)][field] || ''
          }
        }
      }
      if (htmlData?.signature_data) {
        Object.assign(signatureData.value, htmlData.signature_data)
      }
      if (htmlData?.project_context) {
        Object.assign(projectContext.value, htmlData.project_context)
      }
      if (htmlData?.not_applicable) {
        notApplicable.value = ['是', '1', 'true', 'yes'].includes(String(htmlData.not_applicable).toLowerCase())
      }
      // Auto-fill preparer from current user if not set
      if (!signatureData.value.preparer && projectContext.value.current_user) {
        signatureData.value.preparer = projectContext.value.current_user
      }
    } catch {
      // 静态结构无需后端
    } finally {
      loading.value = false
    }
  }

  // ─── Personnel CRUD ───
  function addPersonnel() {
    personnel.value.push({ name: '', position: '', role: '' })
    _enqueuePersonnelSave()
  }

  function removePersonnel(index: number) {
    if (index >= 0 && index < personnel.value.length) {
      personnel.value.splice(index, 1)
      _enqueuePersonnelSave()
    }
  }

  function updatePersonnel(index: number, field: keyof PersonnelRow, value: string) {
    if (index >= 0 && index < personnel.value.length) {
      personnel.value[index][field] = value
      _enqueuePersonnelSave()
    }
  }

  function _enqueuePersonnelSave() {
    const itemId = 'a174-personnel'
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: String(personnel.value.length),
      remark: JSON.stringify(personnel.value),
    })
    scheduleSave()
  }

  // ─── Update Section ───
  function updateSection(secNum: number, value: string) {
    const field = SECTION_FIELD_MAP[secNum]
    if (!field) return
    const sec = sections.value[secNum as keyof A174Sections]
    if (sec) {
      (sec as any)[field] = value
    }
    const itemId = `a174-sec${secNum}-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    scheduleSave()
  }

  // ─── Update Signature ───
  function updateSignature(field: keyof A174SignatureData, value: string) {
    signatureData.value[field] = value
    const itemId = `a174-signature-${field}`
    pendingItems.set(itemId, { item_id: itemId, conclusion: value, remark: null })
    scheduleSave()
  }

  function setNotApplicable(v: boolean) {
    notApplicable.value = v
    pendingItems.set('a174-meta-not_applicable', {
      item_id: 'a174-meta-not_applicable',
      conclusion: v ? '是' : '',
      remark: null,
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
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
    await doSave()
  }

  return {
    loading,
    personnel,
    sections,
    signatureData,
    projectContext,
    saveStatus,
    lastSavedAt,
    notApplicable,
    loadData,
    addPersonnel,
    removePersonnel,
    updatePersonnel,
    updateSection,
    updateSignature,
    setNotApplicable,
    flushPendingSaves,
  }
}
