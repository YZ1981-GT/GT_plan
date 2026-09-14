/**
 * useG4SppiBusinessModel — G4-5 业务模式分析
 *
 * 对齐 Excel《业务模式分析G4-5》否定筛查问卷：
 * 全「否」→ AC；交易性/公允价值管理 → FVTPL；大额频繁出售 → FVOCI
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  determineBusinessModel,
  detectBusinessModelInconsistencies,
  type BusinessModelAnswers,
  type BusinessModelResult,
} from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'
import {
  G4_CLASSIFICATION_WRITEBACK_EVENT,
  applyG4ClassificationUpdates,
  fetchCanonicalRowsFromWorkpaper,
  resolveG4MainWorkpaperId,
  saveCanonicalRowsToWorkpaper,
  type G4ClassificationUpdate,
} from '@/components/workpaper/composables/g4CrossHelpers'
import { G4_ITEM_IDS } from '@/components/workpaper/composables/g4StorageContract'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface QuestionnaireItem {
  id: string
  seq: number
  /** 展示用题号，如 "2.1" */
  displaySeq: string
  question: string
  answer: boolean | null
  explanation: string
  /** 子题缩进（2.1/2.2/2.3） */
  indent?: boolean
}

export interface SubPortfolio {
  id: string
  name: string
  /** 对齐 Excel「组合依据」 */
  basis: string
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

/** Excel 否定筛查题（是 = 不利 AC） */
const DEFAULT_QUESTIONS: Array<{
  id: string
  seq: number
  displaySeq: string
  question: string
  indent?: boolean
}> = [
  { id: 'q1', seq: 1, displaySeq: '1', question: '被审计单位是否涉及大额且频繁的债权投资出售？' },
  { id: 'q2', seq: 2, displaySeq: '2', question: '被审计单位持有债权投资的目的是交易性的？' },
  {
    id: 'q2_1',
    seq: 3,
    displaySeq: '2.1',
    indent: true,
    question: '取得相关金融资产的目的，主要是为了近期出售或回购？',
  },
  {
    id: 'q2_2',
    seq: 4,
    displaySeq: '2.2',
    indent: true,
    question:
      '相关金融资产在初始确认时属于集中管理的可辨认金融工具组合的一部分，且有客观证据表明近期实际存在短期获利模式？',
  },
  {
    id: 'q2_3',
    seq: 5,
    displaySeq: '2.3',
    indent: true,
    question:
      '相关金融资产属于衍生工具（但符合财务担保合同定义的衍生工具以及被指定为有效套期工具的衍生工具除外）？',
  },
  {
    id: 'q3',
    seq: 6,
    displaySeq: '3',
    question: '被审计单位基于债权投资的公允价值作出决策并对其进行管理？',
  },
  {
    id: 'q4',
    seq: 7,
    displaySeq: '4',
    question: '未来是否预期会进行大额且频繁的债权投资出售？',
  },
  {
    id: 'q5',
    seq: 8,
    displaySeq: '5',
    question:
      '未来是否预期持有债权投资的目的是交易性的或基于债权投资的公允价值作出决策并对其进行管理？',
  },
]

/** 结论 chip — 文案对齐模板业务模式表述 */
export const CONCLUSION_CHIP_MAP: Record<BusinessModelResult, ConclusionChipStyle> = {
  AC: { color: '#67C23A', label: '以收取合同现金流量为目标', type: 'success' },
  FVOCI: {
    color: '#409EFF',
    label: '以收取合同现金流量和出售金融资产为目标',
    type: 'primary',
  },
  FVTPL: { color: '#E6A23C', label: '其他业务模式', type: 'warning' },
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

/** 旧版 5 问问卷 → 迁到新 8 问（答案无法可靠映射，重置为默认未答） */
function normalizeQuestionnaire(parsed: QuestionnaireItem[]): QuestionnaireItem[] {
  const hasNew = parsed.some((i) => i.id === 'q2_1')
  if (!hasNew) return createDefaultQuestionnaire()

  const byId = new Map(parsed.map((i) => [i.id, i]))
  return createDefaultQuestionnaire().map((def) => {
    const prev = byId.get(def.id)
    if (!prev) return def
    return {
      ...def,
      answer: prev.answer ?? null,
      explanation: prev.explanation ?? '',
    }
  })
}

function buildAnswersFromQuestionnaire(items: QuestionnaireItem[]): BusinessModelAnswers {
  const get = (id: string) => items.find((i) => i.id === id)?.answer ?? null
  const q2_1 = get('q2_1')
  const q2_2 = get('q2_2')
  const q2_3 = get('q2_3')
  // 对齐 Excel E16：题2 = OR(2.1,2.2,2.3)；子题齐后覆盖父题
  let q2 = get('q2')
  if (q2_1 !== null && q2_2 !== null && q2_3 !== null) {
    q2 = q2_1 === true || q2_2 === true || q2_3 === true
  }
  return {
    q1: get('q1'),
    q2,
    q2_1,
    q2_2,
    q2_3,
    q3: get('q3'),
    q4: get('q4'),
    q5: get('q5'),
  }
}

/** 将题2同步为子题 OR（与 Excel 一致，父题只读展示） */
function syncDerivedQ2(items: QuestionnaireItem[]): void {
  const q2 = items.find((i) => i.id === 'q2')
  const c1 = items.find((i) => i.id === 'q2_1')?.answer
  const c2 = items.find((i) => i.id === 'q2_2')?.answer
  const c3 = items.find((i) => i.id === 'q2_3')?.answer
  if (!q2) return
  if (c1 === null || c2 === null || c3 === null || c1 === undefined || c2 === undefined || c3 === undefined) {
    return
  }
  q2.answer = c1 === true || c2 === true || c3 === true
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
  wpId?: Ref<string>
  projectId?: Ref<string>
}

export function useG4SppiBusinessModel(opts: UseG4SppiBusinessModelOptions) {
  const { allResponses, debouncedSave, isReadonly } = opts

  const questionnaire = ref<QuestionnaireItem[]>(createDefaultQuestionnaire())
  const auditEvaluation = ref('')
  const conclusion = ref<BusinessModelResult>('INCOMPLETE')

  const hasSubPortfolios = ref(false)
  const subPortfolios = ref<SubPortfolio[]>([])

  const auditConclusion = ref('')

  const conclusionChip = computed<ConclusionChipStyle>(() => {
    return CONCLUSION_CHIP_MAP[conclusion.value]
  })

  /** 跨组校验警告：非AC时提示 */
  const crossCheckWarning = computed<string | null>(() => {
    if (conclusion.value === 'AC' || conclusion.value === 'INCOMPLETE') return null
    return '注：债权投资(G4)科目适用以摊余成本计量(AC)分类。若业务模式判定为FVOCI或FVTPL，该投资应归入G6其他债权投资或G1交易性金融资产，请确认分类是否正确。'
  })

  /** 问卷自洽提示 */
  const inconsistencyHints = computed(() => {
    return detectBusinessModelInconsistencies(buildAnswersFromQuestionnaire(questionnaire.value))
  })

  function loadFromResponses(): void {
    const qResp = allResponses.value.get(STORAGE_KEY_QUESTIONNAIRE)
    const parsed = safeParseJson<QuestionnaireItem[]>(qResp?.conclusion || qResp?.remark)
    if (parsed && Array.isArray(parsed) && parsed.length > 0) {
      questionnaire.value = normalizeQuestionnaire(parsed)
    }

    const evalResp = allResponses.value.get(STORAGE_KEY_AUDIT_EVAL)
    auditEvaluation.value = evalResp?.conclusion || evalResp?.remark || ''

    const hasSubResp = allResponses.value.get(STORAGE_KEY_HAS_SUB)
    hasSubPortfolios.value = (hasSubResp?.conclusion || hasSubResp?.remark) === 'true'

    const subResp = allResponses.value.get(STORAGE_KEY_SUB_PORTFOLIOS)
    const subParsed = safeParseJson<SubPortfolio[]>(subResp?.conclusion || subResp?.remark)
    if (subParsed && Array.isArray(subParsed)) {
      subPortfolios.value = subParsed.map((sp) => ({
        ...sp,
        basis: sp.basis ?? '',
        questionnaire: normalizeQuestionnaire(sp.questionnaire || []),
      }))
    }

    const conclusionResp = allResponses.value.get(STORAGE_KEY_CONCLUSION)
    auditConclusion.value = conclusionResp?.conclusion || conclusionResp?.remark || ''
  }

  watch(
    () => {
      const q = allResponses.value.get(STORAGE_KEY_QUESTIONNAIRE)
      return [q?.conclusion, q?.remark]
    },
    () => loadFromResponses(),
    { immediate: true },
  )

  watch(
    () => questionnaire.value.map((q) => q.answer),
    () => {
      syncDerivedQ2(questionnaire.value)
      const answers = buildAnswersFromQuestionnaire(questionnaire.value)
      conclusion.value = determineBusinessModel(answers)
    },
    { deep: true, immediate: true },
  )

  watch(
    () => subPortfolios.value.map((sp) => sp.questionnaire.map((q) => q.answer)),
    () => {
      for (const sp of subPortfolios.value) {
        syncDerivedQ2(sp.questionnaire)
        const answers = buildAnswersFromQuestionnaire(sp.questionnaire)
        sp.conclusion = determineBusinessModel(answers)
      }
    },
    { deep: true },
  )

  function persistQuestionnaire(): void {
    if (isReadonly.value) return
    const json = JSON.stringify(questionnaire.value)
    debouncedSave(STORAGE_KEY_QUESTIONNAIRE, {
      conclusion: json,
      remark: json,
    })
  }

  function persistAuditEvaluation(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_EVAL, {
      conclusion: null,
      remark: auditEvaluation.value,
    })
  }

  function persistHasSubPortfolios(): void {
    if (isReadonly.value) return
    const value = String(hasSubPortfolios.value)
    debouncedSave(STORAGE_KEY_HAS_SUB, {
      conclusion: value,
      remark: value,
    })
  }

  function persistSubPortfolios(): void {
    if (isReadonly.value) return
    const json = JSON.stringify(subPortfolios.value)
    debouncedSave(STORAGE_KEY_SUB_PORTFOLIOS, {
      conclusion: json,
      remark: json,
    })
  }

  function persistAuditConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_CONCLUSION, {
      conclusion: null,
      remark: auditConclusion.value,
    })
  }

  function setAnswer(questionId: string, value: boolean | null): void {
    if (isReadonly.value) return
    // 题2由 2.1～2.3 自动汇总，禁止手改
    if (questionId === 'q2') return
    const item = questionnaire.value.find((q) => q.id === questionId)
    if (item) {
      item.answer = value
      syncDerivedQ2(questionnaire.value)
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
        basis: '',
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
    if (questionId === 'q2') return
    const sp = subPortfolios.value.find((p) => p.id === portfolioId)
    if (!sp) return
    const item = sp.questionnaire.find((q) => q.id === questionId)
    if (item) {
      item.answer = value
      syncDerivedQ2(sp.questionnaire)
      persistSubPortfolios()
    }
  }

  function setSubBasis(portfolioId: string, basis: string): void {
    if (isReadonly.value) return
    const sp = subPortfolios.value.find((p) => p.id === portfolioId)
    if (!sp) return
    sp.basis = basis
    persistSubPortfolios()
  }

  function renameSubPortfolio(portfolioId: string, name: string): void {
    if (isReadonly.value) return
    const sp = subPortfolios.value.find((p) => p.id === portfolioId)
    if (!sp) return
    sp.name = name.trim() || sp.name
    persistSubPortfolios()
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

  async function writeClassificationToG42(): Promise<void> {
    if (isReadonly.value || conclusion.value === 'INCOMPLETE') return
    const targetWpId = await resolveG4MainWorkpaperId(
      opts.projectId?.value || '',
      opts.wpId?.value,
    )
    if (!targetWpId) {
      ElMessage.error('未找到 G4 主底稿')
      return
    }
    try {
      const existing = await fetchCanonicalRowsFromWorkpaper(targetWpId, G4_ITEM_IDS.G4_2_ROWS)
      const updates: G4ClassificationUpdate[] = hasSubPortfolios.value
        ? subPortfolios.value
            .filter(portfolio => portfolio.conclusion !== 'INCOMPLETE')
            .map(portfolio => ({
              investProject: portfolio.name,
              sourcePortfolioId: portfolio.id,
              businessModelResult: portfolio.conclusion,
              classificationSource: 'G4-5',
            }))
        : existing.map(row => ({
            investProject: String(row.investProject || row.investmentProject || row.name || ''),
            investmentId: String(row.id || ''),
            businessModelResult: conclusion.value,
            classificationSource: 'G4-5',
          }))
      if (!updates.length) {
        ElMessage.warning('无可回写的业务模式结论')
        return
      }
      const warns = updates.some(update =>
        update.businessModelResult === 'FVOCI' || update.businessModelResult === 'FVTPL',
      )
      if (warns) {
        ElMessage.error(
          '检测到 FVOCI/FVTPL 业务模式：债权投资(G4)套件仅适用摊余成本(AC)。请先重分类至 G6/G1 后再回写，当前已阻断。',
        )
        return
      }
      await ElMessageBox.confirm(
        '将业务模式回写至 G4-2（仅 AC）。',
        '回写分类至 G4-2',
        { confirmButtonText: '确认回写', cancelButtonText: '取消', type: 'info' },
      )
      const result = applyG4ClassificationUpdates(existing, updates)
      await saveCanonicalRowsToWorkpaper(
        targetWpId,
        opts.projectId?.value || '',
        G4_ITEM_IDS.G4_2_ROWS,
        result.rows,
      )
      window.dispatchEvent(new CustomEvent(G4_CLASSIFICATION_WRITEBACK_EVENT, {
        detail: { updates, matched: result.matched, unmatched: result.unmatched, source: 'G4-5' },
      }))
      ElMessage.success(`已回写 ${result.matched.length} 条业务模式至 G4-2${
        result.unmatched.length ? `，未匹配 ${result.unmatched.length} 条` : ''
      }`)
    } catch (error: any) {
      if (error === 'cancel' || error === 'close') return
      ElMessage.error('业务模式回写 G4-2 失败')
    }
  }

  return {
    questionnaire,
    auditEvaluation,
    conclusion,
    conclusionChip,
    crossCheckWarning,
    inconsistencyHints,
    hasSubPortfolios,
    subPortfolios,
    auditConclusion,
    setAnswer,
    setExplanation,
    setAuditEvaluation,
    setAuditConclusion,
    setHasSubPortfolios,
    addSubPortfolio,
    removeSubPortfolio,
    setSubAnswer,
    setSubExplanation,
    setSubBasis,
    renameSubPortfolio,
    loadFromResponses,
    persistQuestionnaire,
    persistSubPortfolios,
    writeClassificationToG42,
  }
}

export default useG4SppiBusinessModel
