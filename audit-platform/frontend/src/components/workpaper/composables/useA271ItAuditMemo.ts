/**
 * useA271ItAuditMemo — A27-1 IT审计总结备忘录 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a27-1-it-audit-memo/
 * Task: 2.1
 *
 * 职责：
 * - reactive header(4), it_team_table CRUD, 7 chapters state
 * - computed showChapter4/showCh3Deficiency/showCh6Deficiency
 * - 2s debounce save (item_id: `a271-*`)
 * - flush pending saves
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface MemoHeader {
  date: string | null
  to: string | null
  from_user: string | null
  subject: string | null
}

export interface TeamRow {
  index: number
  name: string | null
  title: string | null
}

export interface ChapterData {
  number: number
  title: string
  content: string | null
  conclusion: string | null
  deficiency: string | null
  cross_ref: string | null
}

export interface A271CrossReferences {
  b22a_4_3_wp_id: string | null
  c22_wp_id: string | null
  c21_1_wp_id: string | null
  b23_15_wp_id: string | null
}

export interface A271ProjectContext {
  client_name: string
  audit_period: string
  partner: string | null
  current_user: string | null
}

export interface A271MetaInfo {
  client_name: string
  audit_period: string
  index_no: string
}

export interface A271RenderData {
  meta_info?: Partial<A271MetaInfo>
  header?: Partial<MemoHeader>
  purpose_text?: string
  it_team_table?: TeamRow[]
  chapters?: ChapterData[]
  cross_references?: Partial<A271CrossReferences>
  project_context?: Partial<A271ProjectContext>
}

export interface UseA271ItAuditMemoOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<A271RenderData | null>
}

export interface UseA271ItAuditMemoReturn {
  header: Ref<MemoHeader>
  itTeamTable: Ref<TeamRow[]>
  chapters: Ref<ChapterData[]>
  crossReferences: Ref<A271CrossReferences>
  projectContext: Ref<A271ProjectContext>
  purposeText: Ref<string>
  loading: Ref<boolean>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  // Computed conditionals
  showChapter4: ComputedRef<boolean>
  showCh3Deficiency: ComputedRef<boolean>
  showCh6Deficiency: ComputedRef<boolean>
  // Actions
  updateHeader: (field: string, value: string) => void
  updateChapter: (chapterNumber: number, field: string, value: string) => void
  addTeamMember: () => void
  removeTeamMember: (index: number) => void
  updateTeamMember: (index: number, field: string, value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const DEFAULT_CHAPTERS: ChapterData[] = [
  { number: 1, title: '了解信息系统环境', content: null, conclusion: null, deficiency: null, cross_ref: 'B22A-4-3' },
  { number: 2, title: 'IT风险和一般控制', content: null, conclusion: null, deficiency: null, cross_ref: 'C22' },
  { number: 3, title: 'IT一般控制结论', content: null, conclusion: null, deficiency: null, cross_ref: null },
  { number: 4, title: 'IT一般控制缺陷', content: null, conclusion: null, deficiency: null, cross_ref: 'C21-1' },
  { number: 5, title: '信息处理控制', content: null, conclusion: null, deficiency: null, cross_ref: 'B23-15' },
  { number: 6, title: '信息处理控制结论', content: null, conclusion: null, deficiency: null, cross_ref: null },
  { number: 7, title: '缺陷评估', content: null, conclusion: null, deficiency: null, cross_ref: null },
]

/** Build item_id for A27-1 fields */
export function buildA271ItemId(section: string, field: string): string {
  return `a271-${section}-${field}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA271ItAuditMemo(opts: UseA271ItAuditMemoOptions): UseA271ItAuditMemoReturn {
  const { wpId, htmlData } = opts

  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')

  const header = ref<MemoHeader>({
    date: null,
    to: null,
    from_user: null,
    subject: null,
  })

  const itTeamTable = ref<TeamRow[]>([])

  const chapters = ref<ChapterData[]>(DEFAULT_CHAPTERS.map(ch => ({ ...ch })))

  const crossReferences = ref<A271CrossReferences>({
    b22a_4_3_wp_id: null,
    c22_wp_id: null,
    c21_1_wp_id: null,
    b23_15_wp_id: null,
  })

  const projectContext = ref<A271ProjectContext>({
    client_name: '',
    audit_period: '',
    partner: null,
    current_user: null,
  })

  const purposeText = ref('')

  // ─── Computed: conditional logic ───
  const showChapter4 = computed(() => {
    const ch3 = chapters.value[2] // index 2 = chapter 3
    return ch3.conclusion !== '已有效'
  })

  const showCh3Deficiency = computed(() => {
    const ch3 = chapters.value[2]
    return ch3.conclusion !== '已有效'
  })

  const showCh6Deficiency = computed(() => {
    const ch6 = chapters.value[5] // index 5 = chapter 6
    return ch6.conclusion !== '已有效'
  })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Hydrate from render data ───
  function hydrateFromRenderData(data: A271RenderData | null) {
    if (!data) return
    if (data.header) {
      Object.assign(header.value, data.header)
    }
    if (data.it_team_table && Array.isArray(data.it_team_table)) {
      itTeamTable.value = data.it_team_table.map((row, i) => ({
        index: row.index ?? i + 1,
        name: row.name ?? null,
        title: row.title ?? null,
      }))
    }
    if (data.chapters && Array.isArray(data.chapters) && data.chapters.length === 7) {
      chapters.value = data.chapters.map(ch => ({ ...ch }))
    }
    if (data.cross_references) {
      Object.assign(crossReferences.value, data.cross_references)
    }
    if (data.project_context) {
      Object.assign(projectContext.value, data.project_context)
    }
    if (data.purpose_text) {
      purposeText.value = data.purpose_text
    }
  }

  watch(htmlData, (newData) => {
    hydrateFromRenderData(newData)
  }, { immediate: true })

  // ─── Update Header ───
  function updateHeader(field: string, value: string) {
    if (field in header.value) {
      (header.value as any)[field] = value || null
    }
    const itemId = buildA271ItemId('header', field === 'from_user' ? 'from' : field)
    pendingItems.set(itemId, { item_id: itemId, conclusion: value || null, remark: null })
    scheduleSave()
  }

  // ─── Update Chapter ───
  function updateChapter(chapterNumber: number, field: string, value: string) {
    const idx = chapterNumber - 1
    if (idx < 0 || idx >= 7) return
    const ch = chapters.value[idx]
    if (field in ch) {
      (ch as any)[field] = value || null
    }
    const itemId = buildA271ItemId(`ch${chapterNumber}`, field)
    // Long text → remark; conclusion → conclusion field
    if (field === 'conclusion') {
      pendingItems.set(itemId, { item_id: itemId, conclusion: value || null, remark: null })
    } else {
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || null })
    }
    scheduleSave()
  }

  // ─── Team CRUD ───
  function addTeamMember() {
    const newRow: TeamRow = {
      index: itTeamTable.value.length + 1,
      name: null,
      title: null,
    }
    itTeamTable.value.push(newRow)
    _enqueueTeamSave()
  }

  function removeTeamMember(index: number) {
    if (index < 0 || index >= itTeamTable.value.length) return
    itTeamTable.value.splice(index, 1)
    // Re-index
    itTeamTable.value.forEach((row, i) => { row.index = i + 1 })
    _enqueueTeamSave()
  }

  function updateTeamMember(index: number, field: string, value: string) {
    if (index < 0 || index >= itTeamTable.value.length) return
    const row = itTeamTable.value[index]
    if (field === 'name' || field === 'title') {
      row[field] = value || null
    }
    _enqueueTeamSave()
  }

  function _enqueueTeamSave() {
    const itemId = 'a271-team'
    const rows = itTeamTable.value.map(r => ({ name: r.name, title: r.title }))
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: String(rows.length),
      remark: JSON.stringify(rows),
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

  return {
    header,
    itTeamTable,
    chapters,
    crossReferences,
    projectContext,
    purposeText,
    loading,
    saveStatus,
    showChapter4,
    showCh3Deficiency,
    showCh6Deficiency,
    updateHeader,
    updateChapter,
    addTeamMember,
    removeTeamMember,
    updateTeamMember,
    flushPendingSaves,
  }
}
