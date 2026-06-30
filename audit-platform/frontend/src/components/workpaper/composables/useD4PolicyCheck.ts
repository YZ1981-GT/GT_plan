/**
 * useD4PolicyCheck — D4-5 CAS14五步法政策检查逻辑
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 9.1
 *
 * 职责：
 * - CAS14五步法卡片结构（5步）
 * - 每步：政策条款只读details + 实际情况textarea + 审计师评价textarea + AI
 * - Y/N/NA结论 + N时强制说明 + 进度条(5步中已完成N步)
 * - Load/save via allResponses with item_id prefix `D4-5-step{N}-{field}`
 *
 * Requirements: 7.1-7.7, 21.3
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PolicyStep {
  stepNumber: number
  title: string
  policyReference: string
  situation: string
  evaluation: string
  conclusion: 'Y' | 'N' | 'NA' | ''
}

export interface PolicyCheckReturn {
  steps: Ref<PolicyStep[]>
  completedSteps: ComputedRef<number>
  totalSteps: ComputedRef<number>
  progress: ComputedRef<number>
  updateSituation: (stepNum: number, value: string) => void
  updateEvaluation: (stepNum: number, value: string) => void
  updateConclusion: (stepNum: number, value: 'Y' | 'N' | 'NA' | '') => void
  isStepComplete: (stepNum: number) => boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

const POLICY_STEPS: Array<{ stepNumber: number; title: string; policyReference: string }> = [
  {
    stepNumber: 1,
    title: '第一步：识别与客户之间的合同',
    policyReference: '根据CAS14第四条，企业应当在同时满足下列条件时确认与客户之间的合同：(1)合同各方已批准该合同并承诺将履行各自义务；(2)能够识别与所转让商品或服务相关的各方权利；(3)能够识别与所转让商品或服务相关的支付条款；(4)该合同具有商业实质；(5)因向客户转让商品或服务而有权取得的对价很可能收回。',
  },
  {
    stepNumber: 2,
    title: '第二步：识别合同中的单项履约义务',
    policyReference: '根据CAS14第九条，合同开始日，企业应当对合同进行评估，识别该合同所包含的各单项履约义务，并确定各单项履约义务是在某一时段内履行还是在某一时点履行。当企业向客户转让的商品同时满足：(1)可明确区分；(2)具有独立性时，应识别为单项履约义务。',
  },
  {
    stepNumber: 3,
    title: '第三步：确定交易价格',
    policyReference: '根据CAS14第十四条，企业应当根据合同条款，并结合其以往的习惯做法确定交易价格。在确定交易价格时，企业应当考虑可变对价、合同中存在的重大融资成分、非现金对价、应付客户对价等因素的影响。',
  },
  {
    stepNumber: 4,
    title: '第四步：将交易价格分摊至各单项履约义务',
    policyReference: '根据CAS14第二十条，合同中包含两项或多项履约义务的，企业应当在合同开始日按照各单项履约义务所承诺商品的单独售价的相对比例将交易价格分摊至各单项履约义务。企业不得因合同开始日后单独售价的变动而重新分摊交易价格。',
  },
  {
    stepNumber: 5,
    title: '第五步：履行每一单项履约义务时确认收入',
    policyReference: '根据CAS14第二十五条，当企业履行了合同中的履约义务，即在客户取得相关商品或服务控制权时确认收入。满足下列条件之一的属于时段确认：(1)客户在企业履约同时即取得并消耗经济利益；(2)客户能够控制在建商品；(3)产出无替代用途且有权收取款项。不满足上述条件则在时点确认。',
  },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4PolicyCheck(options: UseD4BaseOptions): PolicyCheckReturn {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Steps reactive state ────────────────────────────────────────────

  const steps = ref<PolicyStep[]>(POLICY_STEPS.map(ps => ({
    stepNumber: ps.stepNumber,
    title: ps.title,
    policyReference: ps.policyReference,
    situation: '',
    evaluation: '',
    conclusion: '' as PolicyStep['conclusion'],
  })))

  // ─── Load from allResponses ──────────────────────────────────────────

  function loadFromResponses(): void {
    for (const step of steps.value) {
      const n = step.stepNumber
      const sitResp = allResponses.value.get(`D4-5-step${n}-situation`)
      const evalResp = allResponses.value.get(`D4-5-step${n}-evaluation`)
      const conclResp = allResponses.value.get(`D4-5-step${n}-conclusion`)
      step.situation = sitResp?.remark || ''
      step.evaluation = evalResp?.remark || ''
      step.conclusion = (conclResp?.conclusion as PolicyStep['conclusion']) || ''
    }
  }

  // Watch allResponses for external changes
  watch(
    () => allResponses.value.get('D4-5-step1-situation')?.remark,
    () => loadFromResponses(),
    { immediate: true },
  )

  // ─── Computed: progress ──────────────────────────────────────────────

  const totalSteps = computed(() => POLICY_STEPS.length)

  const completedSteps = computed(() => {
    return steps.value.filter(s => s.conclusion !== '').length
  })

  const progress = computed(() => {
    if (totalSteps.value === 0) return 0
    return Math.round((completedSteps.value / totalSteps.value) * 100)
  })

  // ─── Helpers ─────────────────────────────────────────────────────────

  function isStepComplete(stepNum: number): boolean {
    const step = steps.value.find(s => s.stepNumber === stepNum)
    return step ? step.conclusion !== '' : false
  }

  // ─── Mutations ───────────────────────────────────────────────────────

  function updateSituation(stepNum: number, value: string): void {
    if (readonly.value) return
    const step = steps.value.find(s => s.stepNumber === stepNum)
    if (!step) return
    step.situation = value
    persistField(stepNum, 'situation', value)
  }

  function updateEvaluation(stepNum: number, value: string): void {
    if (readonly.value) return
    const step = steps.value.find(s => s.stepNumber === stepNum)
    if (!step) return
    step.evaluation = value
    persistField(stepNum, 'evaluation', value)
  }

  function updateConclusion(stepNum: number, value: 'Y' | 'N' | 'NA' | ''): void {
    if (readonly.value) return
    const step = steps.value.find(s => s.stepNumber === stepNum)
    if (!step) return
    step.conclusion = value
    const itemId = `D4-5-step${stepNum}-conclusion`
    allResponses.value.set(itemId, { item_id: itemId, conclusion: value, remark: null })
    debounceSave()
  }

  // ─── Persistence ────────────────────────────────────────────────────

  function persistField(stepNum: number, field: string, value: string): void {
    const itemId = `D4-5-step${stepNum}-${field}`
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: value })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const items: any[] = []
      for (const step of steps.value) {
        const n = step.stepNumber
        items.push(allResponses.value.get(`D4-5-step${n}-situation`))
        items.push(allResponses.value.get(`D4-5-step${n}-evaluation`))
        items.push(allResponses.value.get(`D4-5-step${n}-conclusion`))
      }
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: items.filter(Boolean) } }))
    } catch { /* silent */ }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    steps,
    completedSteps,
    totalSteps,
    progress,
    updateSituation,
    updateEvaluation,
    updateConclusion,
    isStepComplete,
  }
}

export default useD4PolicyCheck
