/**
 * useB1Evaluation — B1-3 业务评价表 数据管理 + 持久化
 *
 * item_id 前缀 b1eval-：
 * - 基本信息 b1eval-basic-{field}(remark)
 * - 客户评价 b1eval-client-{rowId}(textarea→remark / risk→conclusion 高中低)
 * - 前提条件 b1eval-pre-{itemId}(conclusion 是/否/N/A) + -note(remark)
 * - 独立性   b1eval-indep-{itemId}(conclusion) + -note(remark)
 * - 费用     b1eval-fee(remark)
 * - 结论要素 b1eval-elem-{elemId}(remark)
 * - 承接意见 b1eval-opinion(conclusion accept/retain/reject) + -note(remark)
 * - 签名     b1eval-sign-{partner|date}(remark)
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export interface EvalField { field: string; label: string; type: string; options?: string[] }
export interface EvalRow { id: string; label: string; type: string }
export interface EvalItem { id: string; label: string }
export interface EvalOption { value: string; label: string; class: string }
export interface EvalSection {
  key: string
  title: string
  fields?: EvalField[]
  rows?: EvalRow[]
  items?: EvalItem[]
  key_elements?: EvalItem[]
  methodology?: string
  note?: string
  type?: string
}
export interface EvalRenderData {
  source_sheet?: string
  sections: EvalSection[]
  opinion_options: EvalOption[]
  risk_options: EvalOption[]
  values: Record<string, { value?: string; note?: string }>
  opinion: string
  opinion_note: string
  sign_partner: string
  sign_date: string
  risk_alert: string
  project_context: Record<string, string>
  risk_assessment_conclusion: string | null
}

export const EVAL_JUDGE_OPTIONS = ['是', '否', 'N/A'] as const

export interface UseB1EvalOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  htmlData: Ref<EvalRenderData | null>
  onAfterSave?: () => void
}

export function useB1Evaluation(opts: UseB1EvalOptions) {
  const { wpId, htmlData, onAfterSave } = opts

  const loading = ref(false)
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const sections = ref<EvalSection[]>([])
  const opinionOptions = ref<EvalOption[]>([])
  const riskOptions = ref<EvalOption[]>([])
  const values = ref<Record<string, { value?: string; note?: string }>>({})
  const opinion = ref('')
  const opinionNote = ref('')
  const signPartner = ref('')
  const signDate = ref('')
  const riskAlert = ref('')
  const projectContext = ref<Record<string, string>>({})
  const riskAssessmentConclusion = ref<string | null>(null)
  const sourceSheet = ref('')

  const pendingItems = new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>()
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function hydrate(data: EvalRenderData | null) {
    if (!data) return
    if (data.source_sheet) sourceSheet.value = data.source_sheet
    if (Array.isArray(data.sections)) sections.value = data.sections
    if (Array.isArray(data.opinion_options)) opinionOptions.value = data.opinion_options
    if (Array.isArray(data.risk_options)) riskOptions.value = data.risk_options
    if (data.values) values.value = JSON.parse(JSON.stringify(data.values))
    opinion.value = data.opinion || ''
    opinionNote.value = data.opinion_note || ''
    signPartner.value = data.sign_partner || ''
    signDate.value = data.sign_date || ''
    riskAlert.value = data.risk_alert || ''
    if (data.project_context) projectContext.value = { ...data.project_context }
    riskAssessmentConclusion.value = data.risk_assessment_conclusion || null
  }
  watch(htmlData, (nd) => hydrate(nd), { immediate: true })

  async function loadData(id?: string) {
    const targetId = id || wpId.value
    if (!targetId) return
    loading.value = true
    try {
      const res = await api.get<any>(
        `/api/workpapers/${targetId}/render-config?force_component_type=b1-3-business-evaluation`,
        { _silent: true } as any,
      )
      hydrate(res?.sheets?.[0]?.html_data ?? res)
    } catch {
      /* 静默 */
    } finally {
      loading.value = false
    }
  }

  function getVal(key: string): string {
    return values.value[key]?.value || ''
  }
  function getNote(key: string): string {
    return values.value[key]?.note || ''
  }

  function setValue(key: string, itemId: string, value: string, asConclusion: boolean) {
    if (!values.value[key]) values.value[key] = {}
    values.value[key].value = value
    pendingItems.set(itemId, {
      item_id: itemId,
      conclusion: asConclusion ? (value || null) : null,
      remark: asConclusion ? null : (value || null),
    })
    scheduleSave()
  }
  function setNote(key: string, itemId: string, value: string) {
    if (!values.value[key]) values.value[key] = {}
    values.value[key].note = value
    pendingItems.set(itemId, { item_id: itemId, conclusion: null, remark: value || null })
    scheduleSave()
  }

  // 各区块更新入口
  function updateBasic(field: string, value: string) {
    setValue(`basic-${field}`, `b1eval-basic-${field}`, value, false)
  }
  function updateClientText(rowId: string, value: string) {
    setValue(`client-${rowId}`, `b1eval-client-${rowId}`, value, false)
  }
  function updateClientRisk(rowId: string, value: string) {
    setValue(`client-${rowId}`, `b1eval-client-${rowId}`, value, true)
  }
  function updatePre(itemId: string, value: string) {
    setValue(`pre-${itemId}`, `b1eval-pre-${itemId}`, value, true)
  }
  function updatePreNote(itemId: string, value: string) {
    setNote(`pre-${itemId}`, `b1eval-pre-${itemId}-note`, value)
  }
  function updateIndep(itemId: string, value: string) {
    setValue(`indep-${itemId}`, `b1eval-indep-${itemId}`, value, true)
  }
  function updateIndepNote(itemId: string, value: string) {
    setNote(`indep-${itemId}`, `b1eval-indep-${itemId}-note`, value)
  }
  function updateFee(value: string) {
    setValue('fee', 'b1eval-fee', value, false)
  }
  function updateElem(elemId: string, value: string) {
    setValue(`elem-${elemId}`, `b1eval-elem-${elemId}`, value, false)
  }
  function updateOpinion(value: string) {
    opinion.value = value
    pendingItems.set('b1eval-opinion', { item_id: 'b1eval-opinion', conclusion: value || null, remark: null })
    scheduleSave()
  }
  function updateOpinionNote(value: string) {
    opinionNote.value = value
    pendingItems.set('b1eval-opinion-note', { item_id: 'b1eval-opinion-note', conclusion: null, remark: value || null })
    scheduleSave()
  }
  function updateSign(field: 'partner' | 'date', value: string) {
    if (field === 'partner') signPartner.value = value
    else signDate.value = value
    const id = `b1eval-sign-${field}`
    pendingItems.set(id, { item_id: id, conclusion: null, remark: value || null })
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

  // ─── 改进1：综合客户风险按诚信/经营/财务三项取最高档自动建议（可覆盖）───
  const RISK_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 }
  const RANK_TO_RISK: Record<number, string> = { 3: 'high', 2: 'medium', 1: 'low' }
  const suggestedOverallRisk = computed(() => {
    const integrity = getVal('client-integrity_risk')
    const operation = getVal('client-operation_risk')
    const financial = getVal('client-financial_risk')
    const levels = [integrity, operation, financial].filter(Boolean)
    if (levels.length === 0) return null
    const maxRank = Math.max(...levels.map((l) => RISK_RANK[l] || 0))
    return RANK_TO_RISK[maxRank] || null
  })

  // ─── 改进2：独立性存在问题 → 承接意见联动预警 ───
  const independenceWarning = computed<string | null>(() => {
    const hasIssue = getVal('indep-has_independence_issue')
    if (hasIssue !== '是') return null
    const curOpinion = opinion.value
    if (!curOpinion || curOpinion === 'accept' || curOpinion === 'retain') {
      return '独立性存在威胁（判定"是"），请确认已评估防范措施且防范措施有效，否则不应承接/保持该业务'
    }
    return null
  })

  // ─── 改进3：费用结构化字段（预计收费/成本/可收回比率%）───
  const feeStructured = computed(() => ({
    estimatedFee: getVal('fee-estimated_fee'),
    estimatedCost: getVal('fee-estimated_cost'),
    recoverRate: getVal('fee-recover_rate'),
  }))
  function updateFeeField(field: 'estimated_fee' | 'estimated_cost' | 'recover_rate', value: string) {
    setValue(`fee-${field}`, `b1eval-fee-${field}`, value, false)
  }

  return {
    loading, saveStatus, sections, opinionOptions, riskOptions, values,
    opinion, opinionNote, signPartner, signDate, riskAlert, projectContext,
    riskAssessmentConclusion, sourceSheet, getVal, getNote,
    updateBasic, updateClientText, updateClientRisk, updatePre, updatePreNote,
    updateIndep, updateIndepNote, updateFee, updateElem, updateOpinion,
    updateOpinionNote, updateSign, flushPendingSaves, loadData,
    // ─── 改进1：综合客户风险自动建议档位 ───
    suggestedOverallRisk,
    // ─── 改进2：独立性存在问题 → 承接意见预警 ───
    independenceWarning,
    // ─── 改进3：费用结构化字段 ───
    feeStructured, updateFeeField,
  }
}
