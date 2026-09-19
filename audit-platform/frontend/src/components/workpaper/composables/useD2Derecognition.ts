/**
 * useD2Derecognition — D2-12 保理终止确认判断向导 composable
 *
 * 9 步终止确认判断闭环：附件上传+OCR → 知识库引用 → AI 辅助判断 → 用户确认 → 回填底稿。
 * 步骤来源：致同保理合同分析参考示例（见 d2ReferenceExamples.FACTORING 9 步流程）。
 * 存储：checklist_responses item_id `D2-derecognition`（JSON：steps + conclusion）。
 * 立场：AI 仅建议，最终以审计师确认为准（人工判断优先）。
 */
import { ref, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export type StepJudgment = '符合' | '不符合' | '不适用' | ''

export interface KnowledgeRef {
  id?: string
  name: string
  excerpt: string
}

export interface DerecognitionStep {
  stepId: string
  title: string
  note: string
  judgment: StepJudgment
  userNote: string
  evidenceText: string
  attachmentId: string
  attachmentName: string
  knowledgeRefs: KnowledgeRef[]
  aiSuggestion: StepJudgment
  aiReasoning: string
}

const STORAGE_KEY = 'D2-derecognition'

/** 单份保理合同的终止确认判断（9步 + 结论） */
export interface ContractJudgment {
  steps: DerecognitionStep[]
  conclusion: string
  overallNote?: string
  updatedAt?: string
}

/** 9 步终止确认判断流程（标题+要点，与参考示例一致） */
export const STEP_DEFS: { stepId: string; title: string; note: string }[] = [
  { stepId: 's1', title: '步骤1 报告主体层面', note: '合并报表须先合并所有子公司（含结构化主体如信托/专项计划），再对合并报表应用转移准则。' },
  { stepId: 's2', title: '步骤2 部分 vs 整体', note: '除非特定可辨认或完全成比例，终止确认适用于金融资产整体；优先档/折后部分通常不能按部分处理。' },
  { stepId: 's3', title: '步骤3 合同权利是否终止', note: '保理/证券化通常收取现金流量的合同权利并未终止（未终止=继续下一步）。' },
  { stepId: 's4', title: '步骤4 是否转移收款权利', note: '表现为合法出售或现金流量权利合法转移（如办理转让登记）。' },
  { stepId: 's5', title: '步骤5 过手安排测试', note: '保留收款权利但承担转付义务时，须同时满足不垫付/不控制/不延误，否则继续确认。' },
  { stepId: 's6', title: '步骤6 是否转移几乎所有风险报酬', note: '短期应收款主要风险=信用风险+延迟支付风险；历史无违约不能证明无风险。符合=已转移几乎所有风险报酬。' },
  { stepId: 's7', title: '步骤7 是否保留几乎所有风险报酬', note: '回购限于商业纠纷（明确由商业风险导致）一般不影响转移；自留份额增信/宽泛回购/承担迟付=保留风险。符合=保留了几乎所有风险报酬。' },
  { stepId: 's8', title: '步骤8 是否保留控制', note: '关注转入方能否单独向无关第三方整体出售（实际能力），而非仅合同权利。符合=保留了控制。' },
  { stepId: 's9', title: '步骤9 继续涉入', note: '未丧失控制的按继续涉入程度继续确认；未终止确认的应作为质押借款处理。' },
]

function createSteps(): DerecognitionStep[] {
  return STEP_DEFS.map(d => ({
    ...d,
    judgment: '' as StepJudgment,
    userNote: '',
    evidenceText: '',
    attachmentId: '',
    attachmentName: '',
    knowledgeRefs: [],
    aiSuggestion: '' as StepJudgment,
    aiReasoning: '',
  }))
}

/** 规范化步骤数组（补齐缺失步骤，保序） */
function normalizeSteps(rawSteps: any[]): DerecognitionStep[] {
  const saved = new Map<string, any>((rawSteps || []).map((s: any) => [s.stepId, s]))
  return createSteps().map(s => ({ ...s, ...(saved.get(s.stepId) || {}) }))
}

/**
 * 解析 D2-derecognition 存储，返回 { [contractId]: ContractJudgment }。
 * 兼容旧「单份判断」格式（顶层 steps/conclusion）→ 归入 `__legacy__` 键。
 */
export function parseJudgmentStore(remark: string | null | undefined): Record<string, ContractJudgment> {
  if (!remark) return {}
  try {
    const data = JSON.parse(remark)
    if (data && typeof data === 'object') {
      if (data.byContract && typeof data.byContract === 'object') {
        const out: Record<string, ContractJudgment> = {}
        for (const [id, j] of Object.entries<any>(data.byContract)) {
          out[id] = {
            steps: normalizeSteps(j?.steps || []),
            conclusion: j?.conclusion || '',
            overallNote: j?.overallNote || '',
            updatedAt: j?.updatedAt || '',
          }
        }
        return out
      }
      // 旧单份格式
      if (Array.isArray(data.steps)) {
        return {
          __legacy__: {
            steps: normalizeSteps(data.steps),
            conclusion: data.conclusion || '',
            overallNote: data.overallNote || '',
            updatedAt: data.updatedAt || '',
          },
        }
      }
    }
  } catch { /* ignore */ }
  return {}
}

export interface ContractSummary {
  answered: number
  total: number
  conclusion: string
  stepJudgments: StepJudgment[]
}

/** 汇总单份合同判断状态（供卡片/矩阵展示） */
export function summarizeContract(j?: ContractJudgment): ContractSummary {
  const total = STEP_DEFS.length
  if (!j || !Array.isArray(j.steps)) {
    return { answered: 0, total, conclusion: j?.conclusion || '', stepJudgments: STEP_DEFS.map(() => '' as StepJudgment) }
  }
  const byId = new Map(j.steps.map(s => [s.stepId, s]))
  const stepJudgments = STEP_DEFS.map(d => (byId.get(d.stepId)?.judgment || '') as StepJudgment)
  const answered = stepJudgments.filter(Boolean).length
  return { answered, total, conclusion: j.conclusion || '', stepJudgments }
}

export interface UseD2DerecognitionOptions {
  wpId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** 当前判断的保理合同 ID（rowId）；空串表示旧单份模式 */
  contractId?: Ref<string>
}

export function useD2Derecognition(options: UseD2DerecognitionOptions) {
  const { wpId, allResponses, isReadonly } = options
  const contractId = options.contractId ?? ref('')

  const steps = ref<DerecognitionStep[]>(createSteps())
  const conclusion = ref('')          // 终止确认 / 不终止确认（继续确认，作质押融资） / 按继续涉入确认
  const overallNote = ref('')
  const activeStep = ref(0)
  const loading = ref(false)

  function loadStore(): Record<string, ContractJudgment> {
    return parseJudgmentStore(allResponses.value.get(STORAGE_KEY)?.remark)
  }

  // ─── Load（按当前合同加载判断） ─────────────────────────────────────────────
  function load(): void {
    const store = loadStore()
    const key = contractId.value || '__legacy__'
    const j = store[key] || (contractId.value ? undefined : store.__legacy__)
    if (j && Array.isArray(j.steps)) {
      steps.value = normalizeSteps(j.steps)
      conclusion.value = j.conclusion || ''
      overallNote.value = j.overallNote || ''
    } else {
      steps.value = createSteps()
      conclusion.value = ''
      overallNote.value = ''
    }
    activeStep.value = 0
  }

  // ─── AI 建议结论（决策树，供审计师参考，可手改） ──────────────────────────
  const suggestedConclusion = computed<string>(() => {
    const j = (id: string) => steps.value.find(s => s.stepId === id)?.judgment || ''
    if (j('s6') === '符合') return '终止确认'
    if (j('s7') === '符合') return '不终止确认（继续确认，作质押融资处理）'
    if (j('s8') === '符合') return '按继续涉入程度确认'
    if (j('s6') || j('s7') || j('s8')) return '终止确认'
    return ''
  })

  const answeredCount = computed(() => steps.value.filter(s => s.judgment).length)
  const progressPct = computed(() => Math.round((answeredCount.value / steps.value.length) * 100))

  // ─── 附件 OCR ──────────────────────────────────────────────────────────────
  async function uploadOcr(stepIdx: number, file: File): Promise<void> {
    if (isReadonly.value) return
    loading.value = true
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await http.post(`/api/workpapers/${wpId.value}/d2/derecognition-ocr`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const data = res.data?.data ?? res.data
      const step = steps.value[stepIdx]
      if (step && data) {
        step.evidenceText = data.ocr_text || ''
        step.attachmentId = data.attachment_id || ''
        step.attachmentName = file.name
        ElMessage.success(`OCR 识别完成（${(data.ocr_text || '').length} 字），可用于 AI 判断`)
      }
    } catch {
      ElMessage.warning('OCR 识别失败，可手动粘贴证据文本')
    } finally {
      loading.value = false
    }
  }

  // ─── 知识库检索 ────────────────────────────────────────────────────────────
  async function searchKnowledge(query: string): Promise<KnowledgeRef[]> {
    if (!query.trim()) return []
    try {
      const res = await http.get('/api/knowledge-library/search', {
        params: { q: query, context: '应收账款 保理 终止确认' },
        _silent: true,
      } as any)
      const rows: any[] = res.data?.data ?? res.data ?? []
      return rows.slice(0, 20).map(r => ({
        id: String(r.id),
        name: r.name || '未命名文档',
        excerpt: r.folder_name ? `[${r.folder_name}]` : '',
      }))
    } catch {
      return []
    }
  }

  function addKnowledgeRef(stepIdx: number, ref: KnowledgeRef): void {
    const step = steps.value[stepIdx]
    if (step && !step.knowledgeRefs.some(r => r.id === ref.id)) {
      step.knowledgeRefs.push(ref)
    }
  }
  function removeKnowledgeRef(stepIdx: number, refId?: string): void {
    const step = steps.value[stepIdx]
    if (step) step.knowledgeRefs = step.knowledgeRefs.filter(r => r.id !== refId)
  }

  // ─── AI 辅助判断 ──────────────────────────────────────────────────────────
  async function aiJudge(stepIdx: number, context: Record<string, unknown> = {}): Promise<void> {
    if (isReadonly.value) return
    const step = steps.value[stepIdx]
    if (!step) return
    loading.value = true
    try {
      const res = await http.post(`/api/workpapers/${wpId.value}/d2/derecognition-judge`, {
        step_id: step.stepId,
        step_title: step.title,
        step_note: step.note,
        evidence_text: step.evidenceText,
        knowledge_refs: step.knowledgeRefs.map(r => ({ id: r.id, name: r.name, excerpt: r.excerpt })),
        context,
      })
      const data = res.data?.data ?? res.data
      if (data) {
        step.aiSuggestion = (data.suggestion || '') as StepJudgment
        step.aiReasoning = data.reasoning || ''
        if (data.ai_available === false) ElMessage.warning('AI 服务暂不可用，请人工判断')
      }
    } catch {
      ElMessage.warning('AI 判断失败，请人工判断')
    } finally {
      loading.value = false
    }
  }

  /** 采纳 AI 建议为用户判断 */
  function adoptAi(stepIdx: number): void {
    const step = steps.value[stepIdx]
    if (step && step.aiSuggestion) {
      step.judgment = step.aiSuggestion
      if (!step.userNote && step.aiReasoning) step.userNote = step.aiReasoning
    }
  }

  // ─── 保存 + 回填（写入当前合同，合并到多合同 store） ────────────────────────
  function save(): void {
    if (isReadonly.value) return
    if (!conclusion.value) conclusion.value = suggestedConclusion.value
    const store = loadStore()
    const key = contractId.value || '__legacy__'
    store[key] = {
      steps: steps.value,
      conclusion: conclusion.value || suggestedConclusion.value,
      overallNote: overallNote.value,
      updatedAt: new Date().toISOString(),
    }
    const remark = JSON.stringify({ byContract: store, updatedAt: new Date().toISOString() })
    const item = { item_id: STORAGE_KEY, conclusion: null, remark }
    allResponses.value.set(STORAGE_KEY, item)
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
    } catch { /* silent */ }
    ElMessage.success('终止确认判断已保存')
  }

  /** 生成回填/摘要文字（可带合同标签） */
  function buildSummaryText(label = ''): string {
    const lines = steps.value
      .filter(s => s.judgment)
      .map(s => `${s.title}：${s.judgment}${s.userNote ? '（' + s.userNote + '）' : ''}`)
    const concl = conclusion.value || suggestedConclusion.value
    const head = label ? `保理终止确认判断（${label}·9步）：` : '保理终止确认判断（9步）：'
    return `${head}\n${lines.join('\n')}\n结论：${concl || '待定'}`
  }

  return {
    steps,
    conclusion,
    overallNote,
    activeStep,
    loading,
    suggestedConclusion,
    answeredCount,
    progressPct,
    load,
    uploadOcr,
    searchKnowledge,
    addKnowledgeRef,
    removeKnowledgeRef,
    aiJudge,
    adoptAi,
    save,
    buildSummaryText,
  }
}

export default useD2Derecognition
