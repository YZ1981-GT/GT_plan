/**
 * useB1RiskAssessment — B1-1/B1-2 A、B类鉴证业务风险评估表 数据管理 + 持久化
 *
 * 源模板是分章节固定问卷表（事项 | 事实或描述 | 说明或附件），后端预置全部固定事项。
 * 职责：
 * - hydrate: 从 htmlData 初始化 sections / header / overall reactive state
 * - selfLoad: htmlData=null 时调用 render-config?force_component_type=b1-risk-assessment
 * - updateAnswer / updateNote / updateHeader / updateOverall
 * - 2s debounce 自动保存 + flushPendingSaves
 * - saveStatus 状态管理 (saved/saving/unsaved)
 *
 * item_id 方案：
 * - 事项答案:   b1risk-a-{si}-{ii}   (remark = 值)
 * - 事项说明:   b1risk-n-{si}-{ii}   (remark = 说明或附件)
 * - 头部信息:   b1risk-hdr-{field}   (remark = 值)
 * - 综合结论:   b1risk-overall-conclusion (conclusion = 枚举值)
 * - 综合说明:   b1risk-overall-explanation (remark = 文本)
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface B1RiskItem {
  key: string          // "{si}-{ii}"
  item: string         // 事项标签（只读）
  kind: 'text' | 'choice'
  answer: string       // 事实或描述 / 是-否-N/A
  note: string         // 说明或附件
}

export interface B1RiskSection {
  title: string
  items: B1RiskItem[]
}

export interface B1HeaderField {
  field: string
  label: string
}

export interface B1ConclusionOption {
  value: string
  label: string
  class: 'success' | 'warning' | 'danger' | 'info'
}

export interface B1PriorYear {
  year: number
  conclusion: string
}

export interface B1KaaHint {
  reached: boolean
  manual: boolean
}

export interface B1RiskRenderData {
  variant: 'acceptance' | 'retention'
  source_sheet: string
  sections: B1RiskSection[]
  header_fields: B1HeaderField[]
  header: Record<string, string>
  overall: { conclusion: string; explanation: string }
  conclusion_options: B1ConclusionOption[]
  project_context: Record<string, string>
  prior_year: B1PriorYear | null
  kaa_hint: B1KaaHint | null
  eval_client_risk: string | null
}

export interface UseB1RiskOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<B1RiskRenderData | null>
  onAfterSave?: () => void
}

// ─── item_id helpers ───────────────────────────────────────────────────────

export function buildAnswerItemId(key: string): string {
  return `b1risk-a-${key}`
}
export function buildNoteItemId(key: string): string {
  return `b1risk-n-${key}`
}
export function buildHeaderItemId(field: string): string {
  return `b1risk-hdr-${field}`
}

// 是/否/N/A 选项（choice 类事项）
export const CHOICE_OPTIONS = ['是', '否', 'N/A'] as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB1RiskAssessment(opts: UseB1RiskOptions) {
  const { wpId, htmlData, onAfterSave } = opts

  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')

  const variant = ref<'acceptance' | 'retention'>('acceptance')
  const sourceSheet = ref('')
  const sections = ref<B1RiskSection[]>([])
  const headerFields = ref<B1HeaderField[]>([])
  const header = ref<Record<string, string>>({})
  const overall = ref<{ conclusion: string; explanation: string }>({ conclusion: '', explanation: '' })
  const conclusionOptions = ref<B1ConclusionOption[]>([])
  const projectContext = ref<Record<string, string>>({})
  const priorYear = ref<B1PriorYear | null>(null)
  const kaaHint = ref<B1KaaHint | null>(null)
  const evalClientRisk = ref<string | null>(null)

  // ─── Pending saves ───
  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Hydrate ───
  function hydrate(data: B1RiskRenderData | null) {
    if (!data) return
    if (data.variant === 'acceptance' || data.variant === 'retention') variant.value = data.variant
    sourceSheet.value = data.source_sheet || ''
    if (Array.isArray(data.sections)) sections.value = JSON.parse(JSON.stringify(data.sections))
    if (Array.isArray(data.header_fields)) headerFields.value = data.header_fields
    if (data.header) header.value = { ...data.header }
    if (data.overall) overall.value = { ...data.overall }
    if (Array.isArray(data.conclusion_options)) conclusionOptions.value = data.conclusion_options
    if (data.project_context) projectContext.value = { ...data.project_context }
    priorYear.value = data.prior_year || null
    kaaHint.value = data.kaa_hint || null
    evalClientRisk.value = data.eval_client_risk || null
  }

  watch(htmlData, (nd) => hydrate(nd), { immediate: true })

  // ─── Self Load (bundle-embedded scenario) ───
  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=b1-risk-assessment`,
        { _silent: true } as any,
      )
      const data = res?.sheets?.[0]?.html_data ?? res
      hydrate(data)
    } catch {
      // 静默失败，显示空结构
    } finally {
      loading.value = false
    }
  }

  // ─── Find item ───
  function findItem(key: string): B1RiskItem | undefined {
    for (const sec of sections.value) {
      const it = sec.items.find((i) => i.key === key)
      if (it) return it
    }
    return undefined
  }

  // ─── Updates ───
  function updateAnswer(key: string, value: string) {
    const it = findItem(key)
    if (!it) return
    it.answer = value
    const itemId = buildAnswerItemId(key)
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || null })
    scheduleSave()
  }

  function updateNote(key: string, value: string) {
    const it = findItem(key)
    if (!it) return
    it.note = value
    const itemId = buildNoteItemId(key)
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || null })
    scheduleSave()
  }

  function updateHeader(field: string, value: string) {
    header.value[field] = value
    const itemId = buildHeaderItemId(field)
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || null })
    scheduleSave()
  }

  // ─── 行级 OCR：📎「说明或附件」上传 → /d4/contract-ocr → 确认后追加到说明 ───
  const ocrLoadingKey = ref<string | null>(null)
  async function ocrRowNote(key: string, file: File): Promise<boolean> {
    const it = findItem(key)
    if (!it) return false
    ocrLoadingKey.value = key
    let text = ''
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = (res as any)?.data?.data ?? (res as any)?.data
      const fields = data?.extracted_fields || {}
      text = String(fields.full_text || fields.fullText || '').trim()
    } catch {
      ocrLoadingKey.value = null
      ElMessage.warning('OCR 识别失败，请稍后重试或手工填写')
      return false
    }
    ocrLoadingKey.value = null
    if (!text) { ElMessage.info('OCR 完成，未识别到文本'); return false }
    try {
      await ElMessageBox.confirm(
        text.slice(0, 1500) + (text.length > 1500 ? '…' : ''),
        'OCR 识别结果 — 确认追加到「说明或附件」？',
        { confirmButtonText: '追加', cancelButtonText: '取消', type: 'info', customClass: 'b1risk-ocr-confirm' },
      )
    } catch {
      return false // 用户取消
    }
    const merged = [(it.note || '').trim(), text].filter(Boolean).join('\n')
    updateNote(key, merged)
    ElMessage.success('已追加 OCR 文本到说明')
    return true
  }

  function updateOverallConclusion(value: string) {
    overall.value.conclusion = value
    pendingItems.set('b1risk-overall-conclusion', {
      item_id: 'b1risk-overall-conclusion', conclusion: value || null, remark: null,
    })
    scheduleSave()
  }

  function updateOverallExplanation(value: string) {
    overall.value.explanation = value
    pendingItems.set('b1risk-overall-explanation', {
      item_id: 'b1risk-overall-explanation', conclusion: null, remark: value || null,
    })
    scheduleSave()
  }

  // ─── Debounce save ───
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

  async function flushPendingSaves(): Promise<void> {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null }
    await doSave()
  }

  // ─── 改进5：风险信号数→综合结论自动建议档位（可覆盖）───
  // 规则：>5项高风险 / 2~5项中风险 / 0~1项低风险（不含N/A和"否"）
  const suggestedConclusion = computed<string | null>(() => {
    let riskCount = 0
    for (const sec of sections.value) {
      for (const it of sec.items) {
        if (it.kind === 'choice' && it.answer === '是') riskCount++
      }
    }
    if (riskCount > 5) return 'high_risk'
    if (riskCount >= 2) return 'medium_risk'
    if (riskCount >= 0 && sections.value.length > 0) return 'low_risk'
    return null
  })

  return {
    loading,
    saveStatus,
    variant,
    sourceSheet,
    sections,
    headerFields,
    header,
    overall,
    conclusionOptions,
    projectContext,
    priorYear,
    kaaHint,
    evalClientRisk,
    updateAnswer,
    updateNote,
    updateHeader,
    updateOverallConclusion,
    updateOverallExplanation,
    flushPendingSaves,
    loadData,
    suggestedConclusion,
    ocrRowNote,
    ocrLoadingKey,
  }
}
