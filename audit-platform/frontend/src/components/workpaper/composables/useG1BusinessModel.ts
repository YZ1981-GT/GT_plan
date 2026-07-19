/**
 * useG1BusinessModel — G1-8 业务模式分析（对齐 Excel 问卷 + CAS22）
 *
 * (一) 单一业务模式：是/否问卷 → 自动结论（持有收取 / 兼有 / 其他）
 * (二) 次级组合：组合名称 / 依据 / 业务模式 / 列报项目
 * 结论写入 G1-8-model-result，并派发 g1:business-model-updated 供 G1-9 勾稽
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { ChecklistResponse } from './useF1FormData'

export type G1BizModelResult = 'HOLD_COLLECT' | 'HOLD_AND_SELL' | 'OTHER' | 'INCOMPLETE'

export interface G1BizQuestion {
  id: string
  seq: string
  question: string
  /** 子问缩进展示 */
  indent?: boolean
  answer: boolean | null
  explanation: string
}

export interface G1SubPortfolioRow {
  id: string
  name: string
  basis: string
  businessModel: string
  reportItem: string
}

export interface G1BizModelChip {
  color: string
  label: string
  type: 'success' | 'primary' | 'warning' | 'info'
}

export const G1_BIZ_MODEL_CHIP: Record<G1BizModelResult, G1BizModelChip> = {
  HOLD_COLLECT: { color: '#67C23A', label: '以收取合同现金流量为目标', type: 'success' },
  HOLD_AND_SELL: { color: '#409EFF', label: '既收取合同现金流量又出售', type: 'primary' },
  OTHER: { color: '#E6A23C', label: '属于其他业务模式', type: 'warning' },
  INCOMPLETE: { color: '#909399', label: '请完成问卷全部问题', type: 'info' },
}

/** Excel G1-8（一）问卷题干 */
export const G1_BIZ_DEFAULT_QUESTIONS: Array<{
  id: string
  seq: string
  question: string
  indent?: boolean
}> = [
  {
    id: 'q1',
    seq: '1',
    question: '是否存在频繁且金额重大的出售？',
  },
  {
    id: 'q2',
    seq: '2',
    question: '持有目的是否为交易？',
  },
  {
    id: 'q2_1',
    seq: '2.1',
    question: '是否近期内出售或回购以获取短期收益？',
    indent: true,
  },
  {
    id: 'q2_2',
    seq: '2.2',
    question: '是否属于集中管理的可辨认金融工具组合的一部分，且有短期获利的证据？',
    indent: true,
  },
  {
    id: 'q2_3',
    seq: '2.3',
    question: '是否属于衍生工具（套期会计指定除外）？',
    indent: true,
  },
  {
    id: 'q3',
    seq: '3',
    question: '是否以公允价值为基础进行管理和业绩评价？',
  },
  {
    id: 'q4',
    seq: '4',
    question: '未来是否预期频繁且金额重大地出售债务工具投资？',
  },
  {
    id: 'q5',
    seq: '5',
    question: '未来持有目的是否为交易或以公允价值管理？',
  },
]

const KEY_Q = 'G1-8-questionnaire'
const KEY_EVAL = 'G1-8-audit-evaluation'
const KEY_HAS_SUB = 'G1-8-has-sub-portfolios'
const KEY_SUB = 'G1-8-sub-portfolios'
const KEY_RESULT = 'G1-8-model-result'
const KEY_CONCLUSION = 'G1-8-conclusion'

export function createDefaultG1BizQuestionnaire(): G1BizQuestion[] {
  return G1_BIZ_DEFAULT_QUESTIONS.map((q) => ({
    ...q,
    answer: null,
    explanation: '',
  }))
}

/**
 * G1-8 结论推导（对齐 Excel「属于其他业务模式」样例逻辑）
 *
 * - 交易目的 / FV 管理 / 频繁重大出售 → 其他业务模式（通常对应 FVTPL）
 * - 无上述迹象且不预期未来交易 → 持有收取
 * - 无交易迹象但存在「既收取又有限度出售」特征时 → 兼有（q1=否且 q4=否，但审计说明可手工调）
 */
export function determineG1BusinessModel(
  answers: Record<string, boolean | null>,
): G1BizModelResult {
  const ids = G1_BIZ_DEFAULT_QUESTIONS.map((q) => q.id)
  for (const id of ids) {
    if (answers[id] === null || answers[id] === undefined) return 'INCOMPLETE'
  }

  const trading =
    answers.q2 === true
    || answers.q2_1 === true
    || answers.q2_2 === true
    || answers.q2_3 === true
  const fvManaged = answers.q3 === true || answers.q5 === true
  const frequentSales = answers.q1 === true || answers.q4 === true

  if (trading || fvManaged || frequentSales) return 'OTHER'

  // 全部为否：更接近持有收取（对 G1 科目通常应警示）
  return 'HOLD_COLLECT'
}

function answersFromQuestionnaire(items: G1BizQuestion[]): Record<string, boolean | null> {
  const out: Record<string, boolean | null> = {}
  for (const q of items) out[q.id] = q.answer
  return out
}

function generateId(): string {
  return `g18-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function safeParse<T>(raw: string | null | undefined): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function mergeQuestionnaire(stored: G1BizQuestion[] | null): G1BizQuestion[] {
  const base = createDefaultG1BizQuestionnaire()
  if (!stored?.length) return base
  const byId = new Map(stored.map((q) => [q.id, q]))
  return base.map((q) => {
    const hit = byId.get(q.id)
    if (!hit) return q
    return {
      ...q,
      answer: hit.answer ?? null,
      explanation: hit.explanation || '',
    }
  })
}

export function useG1BusinessModel(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const questionnaire = ref<G1BizQuestion[]>(createDefaultG1BizQuestionnaire())
  const auditEvaluation = ref('')
  const hasSubPortfolios = ref(false)
  const subPortfolios = ref<G1SubPortfolioRow[]>([])
  const auditConclusion = ref('')

  const result = computed<G1BizModelResult>(() =>
    determineG1BusinessModel(answersFromQuestionnaire(questionnaire.value)),
  )

  const conclusionChip = computed(() => G1_BIZ_MODEL_CHIP[result.value])

  /** G1 科目预期多为「其他」；若判为持有收取/兼有则提示分类复核 */
  const crossCheckWarning = computed<string | null>(() => {
    if (result.value === 'INCOMPLETE' || result.value === 'OTHER') return null
    return '提示：G1 交易性金融资产通常对应「其他业务模式」（FVTPL）。当前结论为持有收取，请复核是否应归入债权投资等其他科目，或是否需调整分类。'
  })

  function loadAll() {
    const q = safeParse<G1BizQuestion[]>(opts.allResponses.value.get(KEY_Q)?.remark)
    questionnaire.value = mergeQuestionnaire(q)
    auditEvaluation.value = opts.allResponses.value.get(KEY_EVAL)?.remark || ''
    hasSubPortfolios.value = opts.allResponses.value.get(KEY_HAS_SUB)?.remark === 'true'
    const subs = safeParse<G1SubPortfolioRow[]>(opts.allResponses.value.get(KEY_SUB)?.remark)
    subPortfolios.value = Array.isArray(subs) ? subs : []
    auditConclusion.value =
      opts.allResponses.value.get(KEY_CONCLUSION)?.conclusion
      || opts.allResponses.value.get(KEY_CONCLUSION)?.remark
      || ''
  }

  watch(
    () => opts.allResponses.value.get(KEY_Q)?.remark,
    () => loadAll(),
    { immediate: true },
  )

  function persistResult() {
    if (opts.isReadonly.value) return
    const chip = G1_BIZ_MODEL_CHIP[result.value]
    // 未完成时不把提示文案写入 conclusion（避免被后端 Y/N 白名单误伤；且提示仅用于 UI）
    opts.debouncedSave(KEY_RESULT, {
      remark: result.value,
      conclusion: result.value === 'INCOMPLETE' ? null : chip.label,
    })
    try {
      window.dispatchEvent(
        new CustomEvent('g1:business-model-updated', {
          detail: {
            result: result.value,
            label: chip.label,
            timestamp: Date.now(),
          },
        }),
      )
    } catch {
      /* silent */
    }
  }

  // 结论变化时落库（答题/示例路径会同步触发；勿 immediate，避免未完成时误写）
  watch(result, (next, prev) => {
    if (next === prev) return
    persistResult()
  })

  function persistQ() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(KEY_Q, { remark: JSON.stringify(questionnaire.value) })
  }

  function setAnswer(id: string, value: boolean | null) {
    if (opts.isReadonly.value) return
    questionnaire.value = questionnaire.value.map((q) =>
      q.id === id ? { ...q, answer: value } : q,
    )
    persistQ()
    persistResult()
  }

  function setExplanation(id: string, value: string) {
    if (opts.isReadonly.value) return
    questionnaire.value = questionnaire.value.map((q) =>
      q.id === id ? { ...q, explanation: value } : q,
    )
    persistQ()
  }

  function setAuditEvaluation(value: string) {
    if (opts.isReadonly.value) return
    auditEvaluation.value = value
    opts.debouncedSave(KEY_EVAL, { remark: value })
  }

  function setAuditConclusion(value: string) {
    if (opts.isReadonly.value) return
    auditConclusion.value = value
    opts.debouncedSave(KEY_CONCLUSION, { conclusion: value, remark: value })
  }

  function setHasSubPortfolios(value: boolean) {
    if (opts.isReadonly.value) return
    hasSubPortfolios.value = value
    opts.debouncedSave(KEY_HAS_SUB, { remark: String(value) })
  }

  function persistSubs() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(KEY_SUB, { remark: JSON.stringify(subPortfolios.value) })
  }

  async function addSubPortfolio() {
    if (opts.isReadonly.value) return
    try {
      const { value: name } = await ElMessageBox.prompt('请输入次级组合名称', '新增次级组合', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '组合名称不能为空',
      })
      subPortfolios.value = [
        ...subPortfolios.value,
        {
          id: generateId(),
          name,
          basis: '',
          businessModel: conclusionChip.value.label,
          reportItem: '交易性金融资产',
        },
      ]
      persistSubs()
    } catch {
      /* cancelled */
    }
  }

  function updateSubPortfolio(id: string, patch: Partial<G1SubPortfolioRow>) {
    if (opts.isReadonly.value) return
    subPortfolios.value = subPortfolios.value.map((r) =>
      r.id === id ? { ...r, ...patch } : r,
    )
    persistSubs()
  }

  function removeSubPortfolio(id: string) {
    if (opts.isReadonly.value) return
    subPortfolios.value = subPortfolios.value.filter((r) => r.id !== id)
    persistSubs()
  }

  /** 一键填入与 Excel 样例一致的「其他业务模式」路径（便于演示/自检） */
  function applyTradingPathHints() {
    if (opts.isReadonly.value) return
    const hints: Record<string, boolean> = {
      q1: true,
      q2: true,
      q2_1: true,
      q2_2: false,
      q2_3: false,
      q3: false,
      q4: false,
      q5: false,
    }
    questionnaire.value = questionnaire.value.map((q) => ({
      ...q,
      answer: hints[q.id] ?? q.answer,
    }))
    persistQ()
    persistResult()
  }

  return {
    questionnaire,
    auditEvaluation,
    hasSubPortfolios,
    subPortfolios,
    auditConclusion,
    result,
    conclusionChip,
    crossCheckWarning,
    setAnswer,
    setExplanation,
    setAuditEvaluation,
    setAuditConclusion,
    setHasSubPortfolios,
    addSubPortfolio,
    updateSubPortfolio,
    removeSubPortfolio,
    applyTradingPathHints,
    loadAll,
  }
}

export default useG1BusinessModel
