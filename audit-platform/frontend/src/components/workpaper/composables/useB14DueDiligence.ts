/**
 * useB14DueDiligence — B1-4 尽职调查报告 数据管理 + 持久化
 *
 * Spec: .kiro/specs/b1-4-due-diligence-report/
 * Task: 3.1
 *
 * 职责：
 * - hydrate: 从 htmlData 初始化 chapters reactive state
 * - selfLoad: htmlData=null 时调用 render-config?force_component_type=b1-4-due-diligence-report
 * - updateTextarea / updateTableRows / addTableRow / removeTableRow
 * - setVariant (持久化到 b14-meta-variant)
 * - updateSignature (item_id=b14-signature-{field})
 * - 2s debounce 自动保存 + flushPendingSaves
 * - saveStatus 状态管理 (saved/saving/unsaved)
 */
import { ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface B14Section {
  id: string
  title: string
  type: 'textarea' | 'table'
  content?: string | null
  rows?: Record<string, any>[]
  table_id?: string
}

export interface B14ChapterData {
  id: string
  title: string
  type: 'textarea' | 'table' | 'mixed'
  visible: boolean
  content?: string | null         // textarea type
  rows?: Record<string, any>[]    // table type
  table_id?: string               // table type
  sections?: B14Section[]         // mixed type
}

export interface B14Signature {
  partner: string | null
  partner_date: string | null
  manager: string | null
  manager_date: string | null
  report_date: string | null
}

export interface B14ProjectContext {
  client_name: string
  industry: string
  audit_period: string
  firm_name: string
}

export interface B14RenderData {
  source_sheet?: string
  chapters: Record<string, B14ChapterData>
  variant: 'standard' | 'simplified'
  signature: B14Signature
  project_context: B14ProjectContext
  financial_indicators?: Record<string, number>
  related_parties?: { name: string; relation_type: string; detail?: any }[]
}

export interface UseB14Options {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<B14RenderData | null>
  onAfterSave?: () => void
}

export interface UseB14Return {
  chapters: Ref<Record<string, B14ChapterData>>
  variant: Ref<'standard' | 'simplified'>
  signature: Ref<B14Signature>
  projectContext: Ref<B14ProjectContext>
  sourceSheet: Ref<string>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  loading: Ref<boolean>
  // Actions
  updateTextarea: (chapterId: string, field: string, content: string) => void
  updateTableRows: (chapterId: string, tableId: string, rows: Record<string, any>[]) => void
  addTableRow: (chapterId: string, tableId: string) => void
  removeTableRow: (chapterId: string, tableId: string, rowIndex: number) => void
  setVariant: (v: 'standard' | 'simplified') => void
  updateSignature: (field: string, value: string) => void
  flushPendingSaves: () => Promise<void>
  loadData: (id?: string) => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** Chapters visible only in standard variant */
const STANDARD_ONLY_CHAPTERS = new Set(['ch11', 'ch12'])

const SIGNATURE_FIELDS = ['partner', 'partner_date', 'manager', 'manager_date', 'report_date'] as const

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Build item_id for chapter textarea content.
 * Pattern: b14-ch{N}-content
 */
export function buildB14ChapterContentItemId(chapterNum: number): string {
  return `b14-ch${chapterNum}-content`
}

/**
 * Build item_id for chapter section textarea.
 * Pattern: b14-ch{N}-{section_id}
 */
export function buildB14SectionItemId(chapterNum: number, sectionId: string): string {
  return `b14-ch${chapterNum}-${sectionId}`
}

/**
 * Build item_id for chapter table data.
 * Pattern: b14-ch{N}-table-{tableId}
 */
export function buildB14TableItemId(chapterNum: number, tableId: string): string {
  return `b14-ch${chapterNum}-table-${tableId}`
}

/**
 * Build item_id for variant meta.
 * Pattern: b14-meta-variant
 */
export function buildB14VariantItemId(): string {
  return 'b14-meta-variant'
}

/**
 * Build item_id for signature fields.
 * Pattern: b14-signature-{field}
 */
export function buildB14SignatureItemId(field: string): string {
  return `b14-signature-${field}`
}

/** Extract chapter number from chapter id (e.g., "ch3" → 3) */
function chapterIdToNum(chapterId: string): number {
  return parseInt(chapterId.replace('ch', ''), 10)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB14DueDiligence(opts: UseB14Options): UseB14Return {
  const { wpId, htmlData, onAfterSave } = opts

  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const variant = ref<'standard' | 'simplified'>('standard')
  const sourceSheet = ref('')

  const chapters = ref<Record<string, B14ChapterData>>({})

  const signature = ref<B14Signature>({
    partner: null,
    partner_date: null,
    manager: null,
    manager_date: null,
    report_date: null,
  })

  const projectContext = ref<B14ProjectContext>({
    client_name: '',
    industry: '',
    audit_period: '',
    firm_name: '致同会计师事务所（特殊普通合伙）',
  })

  const financialIndicators = ref<Record<string, number>>({})
  const relatedParties = ref<{ name: string; relation_type: string; detail?: any }[]>([])

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Hydrate from render data ───
  function hydrateFromRenderData(data: B14RenderData | null) {
    if (!data) return

    if (data.source_sheet) sourceSheet.value = data.source_sheet

    // Variant
    if (data.variant === 'standard' || data.variant === 'simplified') {
      variant.value = data.variant
    }

    // Chapters
    if (data.chapters && typeof data.chapters === 'object') {
      chapters.value = JSON.parse(JSON.stringify(data.chapters))
    }

    // Signature
    if (data.signature) {
      Object.assign(signature.value, data.signature)
    }

    // Project context
    if (data.project_context) {
      Object.assign(projectContext.value, data.project_context)
    }

    // Financial indicators (ch6 prefill)
    if (data.financial_indicators) {
      financialIndicators.value = { ...data.financial_indicators }
    }

    // Related parties (ch10 prefill)
    if (Array.isArray(data.related_parties)) {
      relatedParties.value = data.related_parties
    }
  }

  // Watch htmlData for initial load
  watch(htmlData, (newData) => {
    hydrateFromRenderData(newData)
  }, { immediate: true })

  // ─── Self Load (for bundle-embedded scenario) ───
  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=b1-4-due-diligence-report`,
        { _silent: true } as any,
      )
      const data = res?.sheets?.[0]?.html_data ?? res
      hydrateFromRenderData(data)
    } catch {
      // 静默失败，显示空章节结构供用户手动填写
    } finally {
      loading.value = false
    }
  }

  // ─── Update Textarea ───
  function updateTextarea(chapterId: string, field: string, content: string) {
    const ch = chapters.value[chapterId]
    if (!ch) return

    const chNum = chapterIdToNum(chapterId)

    if (ch.type === 'textarea' && field === 'content') {
      // Direct chapter textarea: b14-ch{N}-content
      ch.content = content || null
      const itemId = buildB14ChapterContentItemId(chNum)
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: content || null })
    } else if (ch.type === 'mixed' && ch.sections) {
      // Section textarea: b14-ch{N}-{section_id}
      const section = ch.sections.find(s => s.id === field)
      if (section && section.type === 'textarea') {
        section.content = content || null
        const itemId = buildB14SectionItemId(chNum, field)
        pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: content || null })
      }
    }
    scheduleSave()
  }

  // ─── Update Table Rows ───
  function updateTableRows(chapterId: string, tableId: string, rows: Record<string, any>[]) {
    const ch = chapters.value[chapterId]
    if (!ch) return

    const chNum = chapterIdToNum(chapterId)

    if (ch.type === 'table' && ch.table_id === tableId) {
      ch.rows = rows
    } else if (ch.type === 'mixed' && ch.sections) {
      const section = ch.sections.find(s => s.table_id === tableId)
      if (section) {
        section.rows = rows
      }
    }

    const itemId = buildB14TableItemId(chNum, tableId)
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(rows) })
    scheduleSave()
  }

  // ─── Add Table Row ───
  function addTableRow(chapterId: string, tableId: string) {
    const ch = chapters.value[chapterId]
    if (!ch) return

    let targetRows: Record<string, any>[] | undefined

    if (ch.type === 'table' && ch.table_id === tableId) {
      if (!ch.rows) ch.rows = []
      ch.rows.push({})
      targetRows = ch.rows
    } else if (ch.type === 'mixed' && ch.sections) {
      const section = ch.sections.find(s => s.table_id === tableId)
      if (section) {
        if (!section.rows) section.rows = []
        section.rows.push({})
        targetRows = section.rows
      }
    }

    if (targetRows) {
      const chNum = chapterIdToNum(chapterId)
      const itemId = buildB14TableItemId(chNum, tableId)
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(targetRows) })
      scheduleSave()
    }
  }

  // ─── Remove Table Row ───
  function removeTableRow(chapterId: string, tableId: string, rowIndex: number) {
    const ch = chapters.value[chapterId]
    if (!ch) return

    let targetRows: Record<string, any>[] | undefined

    if (ch.type === 'table' && ch.table_id === tableId) {
      if (ch.rows && rowIndex >= 0 && rowIndex < ch.rows.length) {
        ch.rows.splice(rowIndex, 1)
        targetRows = ch.rows
      }
    } else if (ch.type === 'mixed' && ch.sections) {
      const section = ch.sections.find(s => s.table_id === tableId)
      if (section?.rows && rowIndex >= 0 && rowIndex < section.rows.length) {
        section.rows.splice(rowIndex, 1)
        targetRows = section.rows
      }
    }

    if (targetRows) {
      const chNum = chapterIdToNum(chapterId)
      const itemId = buildB14TableItemId(chNum, tableId)
      pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(targetRows) })
      scheduleSave()
    }
  }

  // ─── Set Variant ───
  function setVariant(v: 'standard' | 'simplified') {
    variant.value = v

    // Update visibility on all chapters
    for (const [chId, ch] of Object.entries(chapters.value)) {
      if (STANDARD_ONLY_CHAPTERS.has(chId)) {
        ch.visible = v === 'standard'
      }
    }

    // Persist to b14-meta-variant
    const itemId = buildB14VariantItemId()
    pendingItems.set(itemId, { item_id: itemId, conclusion: v, remark: null })
    scheduleSave()
  }

  // ─── Update Signature ───
  function updateSignature(field: string, value: string) {
    if (!(SIGNATURE_FIELDS as readonly string[]).includes(field)) return
    ;(signature.value as any)[field] = value || null
    const itemId = buildB14SignatureItemId(field)
    pendingItems.set(itemId, { item_id: itemId, conclusion: value || null, remark: null })
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
      try { onAfterSave?.() } catch { /* 版本快照失败不影响保存 */ }
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
    chapters,
    variant,
    signature,
    projectContext,
    sourceSheet,
    saveStatus,
    loading,
    updateTextarea,
    updateTableRows,
    addTableRow,
    removeTableRow,
    setVariant,
    updateSignature,
    flushPendingSaves,
    loadData,
    financialIndicators,
    relatedParties,
  }
}
