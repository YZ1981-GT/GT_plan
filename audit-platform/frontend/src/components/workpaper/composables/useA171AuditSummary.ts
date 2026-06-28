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
  prefillFromTemplate: (chapterNum: number) => boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const SIGNATURE_ROLES: string[] = [
  '编制人（项目现场负责人）', '复核人（项目合伙人）', '质量控制复核合伙人', 'EQCR技术复核人',
]

const DEFAULT_CHAPTERS: Record<string, ChapterData> = {
  '1': { type: 'textarea', title: '一、审计业务约定范围及执行情况', content: null },
  '2': { type: 'textarea', title: '二、独立性', content: null },
  '3': { type: 'textarea', title: '三、对审计计划的更新和修改', content: null },
  '4': { type: 'textarea', title: '四、审计过程中合伙人已关注的事项', content: null },
  '5': { type: 'textarea', title: '五、业务咨询记录及专业意见分歧解决情况', content: null },
  '6': { type: 'table', title: '六、对重大错报风险的应对措施执行情况', rows: [] },
  '7': { type: 'textarea', title: '七、利用专家的工作', content: null },
  '8': { type: 'table', title: '八、已审财务报表分析', rows: [] },
  '9': { type: 'yn', title: '九、对关联方及关联方交易的结论', answer: null, explanation: null },
  '10': { type: 'yn', title: '十、基于持续经营假设的考虑', answer: null, explanation: null },
  '11': { type: 'yn', title: '十一、对期后事项形成的结论', answer: null, explanation: null },
  '12': { type: 'yn', title: '十二、拟在审计报告中沟通的关键审计事项', answer: null, explanation: null },
  '13': { type: 'textarea', title: '十三、其他信息', content: null },
  '14': { type: 'textarea', title: '十四、财务报表审计结论', content: null },
  '15': { type: 'textarea', title: '十五、其他特殊考虑事项', content: null },
  '16': { type: 'textarea', title: '十六、提请下年度审计关注事项', content: null },
}

// ─── Template Prefill Constants ──────────────────────────────────────────────

/**
 * 各章模板预填内容 — 源自源模板固定骨架文本
 * 使用 {{variable}} 占位符，由 renderTemplate() 替换
 */
export const CHAPTER_TEMPLATE: Record<number, string> = {
  1: `1、业务约定范围及报告用途

根据与被审计单位签订的财务报表审计业务约定书内容，本次审计需出具：
A、{{client_name}}合并及公司财务报表审计报告。
B、其他，如根据证券交易所、证监局、国资委等监管部门有关规定而出具：
  a、控股股东及其他关联方占用资金情况的专项说明；
  b、内控制度自我评估报告核实评价意见；
  c、资金风险状况专项报告。

上述报告用途为：

2、按约定审计范围的执行情况

审计范围按约定书执行，审计范围未扩大、未受到限制。`,

  2: `项目组全体成员已签署独立性声明书（参见A17-7），确认在审计期间保持了独立性。

经评估，不存在影响独立性的重大情况。`,

  4: `（一）特别风险

【说明识别的特别风险及应对情况】

（二）已更正或未更正的错报

1、已更正错报汇总及评价
详见A2-2、A2-3

2、未更正错报汇总及评价
详见A13-1

3、披露不足事项汇总

4、与管理层和治理层的沟通
详见A10-1; A10-2

（三）值得关注的缺陷和其他控制缺陷

（四）重大职业判断

（五）导致注册会计师难以实施必要审计程序的情形

（六）可能导致出具非无保留意见审计报告的事项`,

  5: `详见A17-3和A17-4。

本期无需咨询事项，未发生专业意见分歧。`,

  7: `本期审计未利用专家工作。`,

  13: `经审阅{{client_name}}{{audit_period}}年度报告中除财务报表及审计报告以外的其他信息，未发现与已审财务报表存在重大不一致或与审计中了解到的情况存在重大错报的情形。`,

  14: `经实施审计程序，我们已获取充分、适当的审计证据作为形成审计意见的基础。

未更正错报汇总：参见A13错报汇总表，已评价未更正错报单独及汇总对财务报表整体的影响，判断其未导致财务报表整体存在重大错报。

拟出具审计意见类型：标准无保留意见`,

  15: `A. 舞弊相关：本期审计未发现舞弊或舞弊迹象。
B. 违反法律法规情况：未发现被审计单位存在重大违反法律法规的行为。
C. 组成部分审计师的利用：不适用。`,

  16: `提请下年度审计关注的事项：
（1）
（2）
（3）`,
}

/**
 * 模板预填：将占位符替换为实际项目上下文值
 */
export function renderTemplate(template: string, context: A171ProjectContext): string {
  return template
    .replace(/\{\{client_name\}\}/g, context.client_name || '【被审计单位】')
    .replace(/\{\{audit_period\}\}/g, context.audit_period || '【审计期间】')
    .replace(/\{\{preparer\}\}/g, context.preparer || '【编制人】')
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

  // ─── Prefill from Template ───
  function prefillFromTemplate(chapterNum: number): boolean {
    const template = CHAPTER_TEMPLATE[chapterNum]
    if (!template) return false
    const key = String(chapterNum)
    const ch = chapters.value[key]
    if (!ch || ch.type !== 'textarea') return false
    const rendered = renderTemplate(template, projectContext.value)
    ;(ch as TextareaChapter).content = rendered
    const itemId = buildA171ItemId(chapterNum, 'content')
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: rendered })
    scheduleSave()
    return true
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
    prefillFromTemplate,
  }
}
