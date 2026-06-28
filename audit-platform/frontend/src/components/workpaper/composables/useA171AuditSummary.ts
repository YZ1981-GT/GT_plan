/**
 * useA171AuditSummary — A17-1 重大事项概要汇总 数据管理 + 持久化
 *
 * Spec: .kiro/specs/a17-1-audit-summary/
 * Task: 2.1
 *
 * 职责：
 * - reactive state: 16 chapters (textarea/table/yn) + signatureTable(10 rows)
 * - textarea/table/yn update methods
 * - table row add/remove
 * - 2s debounce save (item_id: `a171-ch{N}-*`, `a171-signature-*`)
 * - flush pending saves
 */
import { ref, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ChapterType = 'textarea' | 'table' | 'yn'

export interface TextareaChapter {
  type: 'textarea'
  title: string
  content: string | null
}

export interface TableChapter {
  type: 'table'
  title: string
  rows: Record<string, any>[]
}

export interface YnChapter {
  type: 'yn'
  title: string
  answer: 'Y' | 'N' | null
  explanation: string | null
}

export type ChapterData = TextareaChapter | TableChapter | YnChapter

export interface SignatureRow {
  role: string
  name: string | null
  date: string | null
}

export interface A171CrossReferences {
  b50_wp_id: string | null
  a13_wp_id: string | null
  a115_wp_id: string | null
}

export interface A171ProjectContext {
  client_name: string
  audit_period: string
  preparer: string | null
}

export interface A171RenderData {
  chapters?: Record<string, any>
  signature_table?: any[]
  cross_references?: Partial<A171CrossReferences>
  project_context?: Partial<A171ProjectContext>
}

export interface UseA171Options {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<A171RenderData | null>
}

export interface UseA171Return {
  chapters: Ref<Record<string, ChapterData>>
  signatureTable: Ref<SignatureRow[]>
  crossReferences: Ref<A171CrossReferences>
  projectContext: Ref<A171ProjectContext>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  // Actions
  updateTextarea: (chapterNum: number, content: string) => void
  updateTableRows: (chapterNum: number, rows: Record<string, any>[]) => void
  addTableRow: (chapterNum: number) => void
  removeTableRow: (chapterNum: number, rowIndex: number) => void
  updateYn: (chapterNum: number, answer: 'Y' | 'N' | null, explanation: string | null) => void
  updateSignature: (rowIndex: number, col: 'name' | 'date', value: string) => void
  flushPendingSaves: () => Promise<void>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SIGNATURE_ROLES: string[] = [
  '编制人（项目现场负责人）', '复核人（项目合伙人）', '项目质量复核合伙人（如适用）', '质量控制复核人（如适用）',
]

const DEFAULT_CHAPTERS: Record<string, ChapterData> = {
  '1': { type: 'textarea', title: '一、审计工作概况', content: null },
  '2': { type: 'textarea', title: '二、重大会计政策及估计变更', content: null },
  '3': { type: 'textarea', title: '三、关键审计事项', content: null },
  '4': { type: 'textarea', title: '四、持续经营评估', content: null },
  '5': { type: 'textarea', title: '五、审计范围调整', content: null },
  '6': { type: 'table', title: '六、重大错报风险应对', rows: [] },
  '7': { type: 'textarea', title: '七、集团审计事项', content: null },
  '8': { type: 'table', title: '八、已审财务报表分析', rows: [] },
  '9': { type: 'yn', title: '九、舞弊识别', answer: null, explanation: null },
  '10': { type: 'yn', title: '十、违反法规情况', answer: null, explanation: null },
  '11': { type: 'yn', title: '十一、关联方事项', answer: null, explanation: null },
  '12': { type: 'yn', title: '十二、期后事项', answer: null, explanation: null },
  '13': { type: 'textarea', title: '十三、审计意见', content: null },
  '14': { type: 'textarea', title: '十四、错报汇总与处理', content: null },
  '15': { type: 'textarea', title: '十五、与治理层沟通事项', content: null },
  '16': { type: 'textarea', title: '十六、审计总结', content: null },
}

/** Build item_id for A17-1 fields */
export function buildA171ItemId(chapterNum: number, suffix: string): string {
  return `a171-ch${chapterNum}-${suffix}`
}

export function buildA171SignatureItemId(rowIndex: number, col: string): string {
  return `a171-signature-${rowIndex}-${col}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA171AuditSummary(opts: UseA171Options): UseA171Return {
  const { wpId, htmlData } = opts

  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')

  const chapters = ref<Record<string, ChapterData>>(
    JSON.parse(JSON.stringify(DEFAULT_CHAPTERS)),
  )

  const signatureTable = ref<SignatureRow[]>(
    SIGNATURE_ROLES.map(role => ({ role, name: null, date: null })),
  )

  const crossReferences = ref<A171CrossReferences>({
    b50_wp_id: null,
    a13_wp_id: null,
    a115_wp_id: null,
  })

  const projectContext = ref<A171ProjectContext>({
    client_name: '',
    audit_period: '',
    preparer: null,
  })

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Hydrate from render data ───
  function hydrateFromRenderData(data: A171RenderData | null) {
    if (!data) return

    if (data.chapters && typeof data.chapters === 'object') {
      const newChapters: Record<string, ChapterData> = JSON.parse(JSON.stringify(DEFAULT_CHAPTERS))
      for (const [key, val] of Object.entries(data.chapters)) {
        if (!val || !newChapters[key]) continue
        const type = val.type || newChapters[key].type
        if (type === 'textarea') {
          (newChapters[key] as TextareaChapter).content = val.content ?? null
        } else if (type === 'table') {
          (newChapters[key] as TableChapter).rows = Array.isArray(val.rows) ? val.rows : []
        } else if (type === 'yn') {
          (newChapters[key] as YnChapter).answer = val.answer ?? null;
          (newChapters[key] as YnChapter).explanation = val.explanation ?? null
        }
      }
      chapters.value = newChapters
    }

    if (data.signature_table && Array.isArray(data.signature_table)) {
      signatureTable.value = data.signature_table.map((row: any, i: number) => ({
        role: row.role || SIGNATURE_ROLES[i] || '',
        name: row.name ?? null,
        date: row.date ?? null,
      }))
    }

    if (data.cross_references) {
      Object.assign(crossReferences.value, data.cross_references)
    }

    if (data.project_context) {
      Object.assign(projectContext.value, data.project_context)
    }
  }

  watch(htmlData, (newData) => {
    hydrateFromRenderData(newData)
  }, { immediate: true })

  // ─── Update Textarea ───
  function updateTextarea(chapterNum: number, content: string) {
    const key = String(chapterNum)
    const ch = chapters.value[key]
    if (!ch || ch.type !== 'textarea') return
    ;(ch as TextareaChapter).content = content || null
    const itemId = buildA171ItemId(chapterNum, 'content')
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: content || null })
    scheduleSave()
  }

  // ─── Update Table Rows ───
  function updateTableRows(chapterNum: number, rows: Record<string, any>[]) {
    const key = String(chapterNum)
    const ch = chapters.value[key]
    if (!ch || ch.type !== 'table') return
    ;(ch as TableChapter).rows = rows
    const itemId = buildA171ItemId(chapterNum, 'table')
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(rows) })
    scheduleSave()
  }

  function addTableRow(chapterNum: number) {
    const key = String(chapterNum)
    const ch = chapters.value[key]
    if (!ch || ch.type !== 'table') return
    const tableChapter = ch as TableChapter
    if (chapterNum === 6) {
      tableChapter.rows.push({ risk: '', response: '', result: '', conclusion: '' })
    } else if (chapterNum === 8) {
      tableChapter.rows.push({ item: '', amount: null, note: '' })
    }
    const itemId = buildA171ItemId(chapterNum, 'table')
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(tableChapter.rows) })
    scheduleSave()
  }

  function removeTableRow(chapterNum: number, rowIndex: number) {
    const key = String(chapterNum)
    const ch = chapters.value[key]
    if (!ch || ch.type !== 'table') return
    const tableChapter = ch as TableChapter
    if (rowIndex < 0 || rowIndex >= tableChapter.rows.length) return
    tableChapter.rows.splice(rowIndex, 1)
    const itemId = buildA171ItemId(chapterNum, 'table')
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: JSON.stringify(tableChapter.rows) })
    scheduleSave()
  }

  // ─── Update Y/N ───
  function updateYn(chapterNum: number, answer: 'Y' | 'N' | null, explanation: string | null) {
    const key = String(chapterNum)
    const ch = chapters.value[key]
    if (!ch || ch.type !== 'yn') return
    ;(ch as YnChapter).answer = answer;
    (ch as YnChapter).explanation = explanation
    const itemId = buildA171ItemId(chapterNum, 'yn')
    pendingItems.set(itemId, { item_id: itemId, conclusion: answer, remark: explanation })
    scheduleSave()
  }

  // ─── Update Signature ───
  function updateSignature(rowIndex: number, col: 'name' | 'date', value: string) {
    if (rowIndex < 0 || rowIndex >= signatureTable.value.length) return
    signatureTable.value[rowIndex][col] = value || null
    const itemId = buildA171SignatureItemId(rowIndex, col)
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
    signatureTable,
    crossReferences,
    projectContext,
    saveStatus,
    updateTextarea,
    updateTableRows,
    addTableRow,
    removeTableRow,
    updateYn,
    updateSignature,
    flushPendingSaves,
  }
}
