/**
 * useJ2AccrualCheck — J2-4 计提检查 + ISA620精算师工作利用评价
 *
 * 核心内容：
 * 1. 精算假设面板（折现率/薪酬增长率/死亡率/离职率）— 可编辑+范围校验
 * 2. ISA620专家利用评估：精算师资质/独立性/工作范围评价
 * 3. 精算假设合理性对比（本期vs上期 + 同行比较）
 * 4. 计提充分性结论
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 4.4-4.6, 5.2-5.3
 */
import { ref, computed, watch, type Ref } from 'vue'
import {
  validateAssumptions,
  calcSensitivity,
  type ActuarialAssumptions,
  type AssumptionValidation,
  type SensitivityResult,
} from './useJ2ActuarialEngine'

// ─── ISA620 专家利用 ─────────────────────────────────────────────────────────

export interface ISA620Evaluation {
  // 精算师信息
  actuaryName: string                // 精算师姓名
  actuaryFirm: string                // 精算事务所
  actuaryQualification: string       // 资质（如中国精算师/FSA/FIA）
  qualificationVerified: boolean     // 资质已验证

  // 独立性评价
  independenceAssessed: boolean
  independenceConclusion: 'independent' | 'not_independent' | 'pending'
  independenceNote: string

  // 工作范围评价
  scopeAdequacy: 'adequate' | 'inadequate' | 'pending'
  scopeNote: string

  // 方法论评价
  methodologyReasonable: boolean
  methodologyNote: string

  // 总体结论
  overallConclusion: 'rely' | 'partial_rely' | 'not_rely' | 'pending'
  overallNote: string
}

export interface AssumptionComparison {
  field: string
  currentValue: number
  priorValue: number
  industryAvg: number | null
  deviation: number         // 偏离度(%)
  reasonableness: 'reasonable' | 'borderline' | 'unreasonable' | 'pending'
  note: string
}

export function useJ2AccrualCheck() {
  // ── 精算假设面板 ──────────────────────────────────────────────────────────

  const assumptions: Ref<ActuarialAssumptions> = ref({
    discountRate: 0.04,
    salaryGrowthRate: 0.08,
    mortalityRate: 0.005,
    turnoverRate: 0.10,
  })

  const priorAssumptions: Ref<ActuarialAssumptions> = ref({
    discountRate: 0.04,
    salaryGrowthRate: 0.08,
    mortalityRate: 0.005,
    turnoverRate: 0.10,
  })

  const validation = computed((): AssumptionValidation => {
    return validateAssumptions(assumptions.value)
  })

  // ── 假设对比 ──────────────────────────────────────────────────────────────

  const comparisons = computed((): AssumptionComparison[] => {
    const fields: { field: string; key: keyof ActuarialAssumptions }[] = [
      { field: '折现率', key: 'discountRate' },
      { field: '薪酬增长率', key: 'salaryGrowthRate' },
      { field: '死亡率', key: 'mortalityRate' },
      { field: '离职率', key: 'turnoverRate' },
    ]
    return fields.map(({ field, key }) => {
      const curr = assumptions.value[key]
      const prior = priorAssumptions.value[key]
      const deviation = prior === 0 ? 0 : ((curr - prior) / prior) * 100
      return {
        field,
        currentValue: curr,
        priorValue: prior,
        industryAvg: null,
        deviation,
        reasonableness: 'pending' as const,
        note: '',
      }
    })
  })

  // ── 敏感性分析 ──────────────────────────────────────────────────────────

  function runSensitivity(currentDBO: number, duration: number): SensitivityResult {
    return calcSensitivity(currentDBO, duration, 0.005)
  }

  // ── ISA620 评估 ───────────────────────────────────────────────────────────

  const isa620: Ref<ISA620Evaluation> = ref({
    actuaryName: '',
    actuaryFirm: '',
    actuaryQualification: '',
    qualificationVerified: false,
    independenceAssessed: false,
    independenceConclusion: 'pending',
    independenceNote: '',
    scopeAdequacy: 'pending',
    scopeNote: '',
    methodologyReasonable: false,
    methodologyNote: '',
    overallConclusion: 'pending',
    overallNote: '',
  })

  // ISA620完成度
  const isa620Completeness = computed(() => {
    const checks = [
      !!isa620.value.actuaryName,
      !!isa620.value.actuaryFirm,
      isa620.value.qualificationVerified,
      isa620.value.independenceAssessed,
      isa620.value.independenceConclusion !== 'pending',
      isa620.value.scopeAdequacy !== 'pending',
      isa620.value.methodologyReasonable,
      isa620.value.overallConclusion !== 'pending',
    ]
    const done = checks.filter(Boolean).length
    return { done, total: checks.length, percent: Math.round((done / checks.length) * 100) }
  })

  // ── 结论 ──────────────────────────────────────────────────────────────────

  const accrualConclusion: Ref<string> = ref('')
  const isAccrualAdequate: Ref<boolean | null> = ref(null)

  // ── 从htmlData加载 ─────────────────────────────────────────────────────

  function loadFromHtmlData(data: Record<string, unknown>) {
    if (data.assumptions && typeof data.assumptions === 'object') {
      Object.assign(assumptions.value, data.assumptions)
    }
    if (data.priorAssumptions && typeof data.priorAssumptions === 'object') {
      Object.assign(priorAssumptions.value, data.priorAssumptions)
    }
    if (data.isa620 && typeof data.isa620 === 'object') {
      Object.assign(isa620.value, data.isa620)
    }
    if (data.accrualConclusion) {
      accrualConclusion.value = data.accrualConclusion as string
    }
    if (data.isAccrualAdequate !== undefined) {
      isAccrualAdequate.value = data.isAccrualAdequate as boolean
    }
  }

  return {
    assumptions,
    priorAssumptions,
    validation,
    comparisons,
    runSensitivity,
    isa620,
    isa620Completeness,
    accrualConclusion,
    isAccrualAdequate,
    loadFromHtmlData,
  }
}
