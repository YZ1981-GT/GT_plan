/**
 * useG4SppiBusinessModel — G4-5 业务模式分析（问卷式决策+结论chip）
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 5.1
 * Requirements: 2.1~2.9, 6.1
 *
 * 职责：
 * - 管理 QuestionnaireItem[] 响应式数据（5道问题）
 * - watch 答案变化 → 调用 determineBusinessModel → 更新 conclusion
 * - chip映射: AC→绿色 / FVOCI→蓝色 / FVTPL→橙色 / INCOMPLETE→灰色
 * - 次级组合逻辑（hasSubPortfolios + SubPortfolio[] + ElMessageBox.prompt新增）
 * - 持久化到 checklist_responses via debouncedSave
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  determineBusinessModel,
  type BusinessModelAnswers,
  type BusinessModelResult,
} from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface QuestionnaireItem {
  id: string
  seq: number
  question: string
  answer: boolean | null
  explanation: string
}

export interface SubPortfolio {
  id: string
  name: string
  questionnaire: QuestionnaireItem[]
  conclusion: BusinessModelResult
}

export interface ConclusionChipStyle {
  color: string
  label: string
  type: 'success' | 'primary' | 'warning' | 'info'
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_QUESTIONNAIRE = 'G4-5-questionnaire'
const STORAGE_KEY_AUDIT_EVAL = 'G4-5-audit-evaluation'
const STORAGE_KEY_HAS_SUB = 'G4-5-has-sub-portfolios'
const STORAGE_KEY_SUB_PORTFOLIOS = 'G4-5-sub-portfolios'
const STORAGE_KEY_CONCLUSION = 'G4-5-audit-conclusion'

/** 5道标准问题 */
const DEFAULT_QUESTIONS: Array<{ id: string; seq: number; question: string }> = [
  { id: 'q1', seq: 1, question: '管理金融资产的目标是否为收取合同现金流量？' },
  { id: 'q2', seq: 2, question: '是否存在出售金融资产的活动？' },
  { id: 'q3', seq: 3, question: '出售是否频繁发生且金额重大？' },
  { id: 'q4', seq: 4, question: '是否同时以收取合同现金流量和出售金融资产为目标管理？' },
  { id: 'q5', seq: 5, question: '是否以获取公允价值变动为主要目标持有该投资？' },
]

/** 结论chip样式映射 */
export const CONCLUSION_CHIP_MAP: Record<BusinessModelResult, ConclusionChipStyle> = {
  AC: { color: '#67C23A', label: '以收取合同现金流量为目标', type: 'success' },
  FVOCI: { color: '#409EFF', label: '以收取和出售为目标', type: 'primary' },
  FVTPL: { color: '#E6A23C', label: '其他', type: 'warning' },
  INCOMPLETE: { color: '#909399', label: '请完成所有问题', type: 'info' },
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `g4bm-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createDefaultQuestionnaire(): QuestionnaireItem[] {
  return DEFAULT_QUESTIONS.map((q) => ({
    ...q,
    answer: null,
    explanation: '',
  }))
}

function buildAnswersFromQuestionnaire(items: QuestionnaireItem[]): BusinessModelAnswers {
  return {
    q1: items.find((i) => i.id === 'q1')?.answer ?? null,
    q2: items.find((i) => i.id === 'q2')?.answer ?? null,
    q3: items.find((i) => i.id === 'q3')?.answer ?? null,
    q4: items.find((i) => i.id === 'q4')?.answer ?? null,
    q5: items.find((i) => i.id === 'q5')?.answer ?? null,
  }
}

function safeParseJson<T>(jsonStr: string | null | undefined): T | null {
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as T
  } catch {
    return null
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseG4SppiBusinessModelOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

export function useG4SppiBusinessModel(opts: UseG4SppiBusinessModelOptions) {
  const { allResponses, debouncedSave, isReadonly } = opts

  // ─── 主问卷数据 ──────────────────────────────────────────────────────────
  const questionnaire = ref<QuestionnaireItem[]>(createDefaultQuestionnaire())
  const auditEvaluation = ref('')
  const conclusion = ref<BusinessModelResult>('INCOMPLETE')

  // ─── 次级组合 ────────────────────────────────────────────────────────────
  const hasSubPortfolios = ref(false)
  const subPortfolios = ref<SubPortfolio[]>([])

  // ─── 审计结论 ────────────────────────────────────────────────────────────
  const auditConclusion = ref('')

  // ─── 结论chip样式 ────────────────────────────────────────────────────────
  const conclusionChip = computed<ConclusionChipStyle>(() => {
    return CONCLUSION_CHIP_MAP[conclusion.value]
  })

  /** 跨组校验警告：非AC时提示 */
  const crossCheckWarning = computed<string | null>(() => {
    if (conclusion.value === 'AC' || conclusion.value === 'INCOMPLETE') return null
    return '注：债权投资(G4)科目适用以摊余成本计量(AC)分类。若业务模式判定为FVOCI或FVTPL，该投资应归入G6其他债权投资或G1交易性金融资产，请确认分类是否正确。'
  })

  // ─── 从 allResponses 加载 ────────────────────────────────────────────────

  function loadFromResponses(): void {
    const qResp = allResponses.value.get(STORAGE_KEY_QUESTIONNAIRE)
    const parsed = safeParseJson<QuestionnaireItem[]>(qResp?.remark)
    if (parsed && Array.isArray(parsed) && parsed.length > 0) {
      questionnaire.value = parsed
    }

    const evalResp = allResponses.value.get(STORAGE_KEY_AUDIT_EVAL)
    auditEvaluation.value = evalResp?.remark || ''

    const hasSubResp = allResponses.value.get(STORAGE_KEY_HAS_SUB)
    hasSubPortfolios.value = hasSubResp?.remark === 'true'

    const subResp = allResponses.value.get(STORAGE_KEY_SUB_PORTFOLIOS)
    const subParsed = safeParseJson<SubPortfolio[]>(subResp?.remark)
    if (subParsed && Array.isArray(subParsed)) {
      subPortfolios.value = subParsed
    }

    const conclusionResp = allResponses.value.get(STORAGE_KEY_CONCLUSION)
    auditConclusion.value = conclusionResp?.remark || ''
  }

  // allResponses 异步加载完成后回填
  watch(
    () => allResponses.value.get(STORAGE_KEY_QUESTIONNAIRE)?.remark,
    () => loadFromResponses(),
    { immediate: true },
  )

  // ─── watch 答案变化 → 重新计算结论 ────────────────────────────────────────

  watch(
    () => questionnaire.value.map((q) => q.answer),
    () => {
      const answers = buildAnswersFromQuestionnaire(questionnaire.value)
      conclusion.value = determineBusinessModel(answers)
    },
    { deep: true, immediate: true },
  )

  // 次级组合各自的结论也需要更新
  watch(
    () => subPortfolios.value.map((sp) => sp.questionnaire.map((q) => q.answer)),
    () => {
      for (const sp of subPortfolios.value) {
        const answers = buildAnswersFromQuestionnaire(sp.questionnaire)
        sp.conclusion = determineBusinessModel(answers)
      }
    },
    { deep: true },
  )

  // ─── 持久化 ──────────────────────────────────────────────────────────────

  function persistQuestionnaire(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_QUESTIONNAIRE, {
      remark: JSON.stringify(questionnaire.value),
    })
  }

  function persistAuditEvaluation(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_EVAL, { remark: auditEvaluation.value })
  }

  function persistHasSubPortfolios(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_HAS_SUB, { remark: String(hasSubPortfolios.value) })
  }

  function persistSubPortfolios(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_SUB_PORTFOLIOS, {
      remark: JSON.stringify(subPortfolios.value),
    })
  }

  function persistAuditConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_CONCLUSION, { remark: auditConclusion.value })
  }

  // ─── 问卷操作 ────────────────────────────────────────────────────────────

  function setAnswer(questionId: string, value: boolean | null): void {
    if (isReadonly.value) return
    const item = questionnaire.value.find((q) => q.id === questionId)
    if (item) {
      item.answer = value
      persistQuestionnaire()
    }
  }

  function setExplanation(questionId: string, value: string): void {
    if (isReadonly.value) return
    const item = questionnaire.value.find((q) => q.id === questionId)
    if (item) {
      item.explanation = value
      persistQuestionnaire()
    }
  }

  function setAuditEvaluation(value: string): void {
    if (isReadonly.value) return
    auditEvaluation.value = value
    persistAuditEvaluation()
  }

  function setAuditConclusion(value: string): void {
    if (isReadonly.value) return
    auditConclusion.value = value
    persistAuditConclusion()
  }

  // ─── 次级组合操作 ─────────────────────────────────────────────────────────

  function setHasSubPortfolios(value: boolean): void {
    if (isReadonly.value) return
    hasSubPortfolios.value = value
    persistHasSubPortfolios()
  }

  async function addSubPortfolio(): Promise<void> {
    if (isReadonly.value) return
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入次级组合名称',
        '新增次级组合',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '组合名称不能为空',
        },
      )
      const newPortfolio: SubPortfolio = {
        id: generateId(),
        name,
        questionnaire: createDefaultQuestionnaire(),
        conclusion: 'INCOMPLETE',
      }
      subPortfolios.value = [...subPortfolios.value, newPortfolio]
      persistSubPortfolios()
    } catch {
      /* cancelled */
    }
  }

  function removeSubPortfolio(id: string): void {
    if (isReadonly.value) return
    subPortfolios.value = subPortfolios.value.filter((sp) => sp.id !== id)
    persistSubPortfolios()
  }

  function setSubAnswer(portfolioId: string, questionId: string, value: boolean | null): void {
    if (isReadonly.value) return
    const sp = subPortfolios.value.find((p) => p.id === portfolioId)
    if (!sp) return
    const item = sp.questionnaire.find((q) => q.id === questionId)
    if (item) {
      item.answer = value
      persistSubPortfolios()
    }
  }

  function setSubExplanation(portfolioId: string, questionId: string, value: string): void {
    if (isReadonly.value) return
    const sp = subPortfolios.value.find((p) => p.id === portfolioId)
    if (!sp) return
    const item = sp.questionnaire.find((q) => q.id === questionId)
    if (item) {
      item.explanation = value
      persistSubPortfolios()
    }
  }

  return {
    // 主问卷
    questionnaire,
    auditEvaluation,
    conclusion,
    conclusionChip,
    crossCheckWarning,
    // 次级组合
    hasSubPortfolios,
    subPortfolios,
    // 审计结论
    auditConclusion,
    // 操作
    setAnswer,
    setExplanation,
    setAuditEvaluation,
    setAuditConclusion,
    setHasSubPortfolios,
    addSubPortfolio,
    removeSubPortfolio,
    setSubAnswer,
    setSubExplanation,
    // 加载
    loadFromResponses,
    // 持久化
    persistQuestionnaire,
    persistSubPortfolios,
  }
}

export default useG4SppiBusinessModel
