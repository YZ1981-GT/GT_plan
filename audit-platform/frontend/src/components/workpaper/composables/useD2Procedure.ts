/**
 * useD2Procedure — 程序表D2A核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 18.1
 *
 * 职责：
 * - ProcedureStep 类型定义（stepId, seq, description, category, objective, status, executor, date, finding, conclusion, indexRef, riskLevel, controlConclusion）
 * - steps reactive（7个审计步骤）
 * - completedCount / totalCount / allNecessaryDone computed
 * - overallConclusion ref（仅 allNecessaryDone 时可编辑）
 * - EventBus listeners for 'risk:assessed' and 'control:test-concluded'
 * - updateStep + debounce save
 *
 * Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 21.3, 21.4, 21.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ProcedureStatus = 'not_started' | 'in_progress' | 'completed' | 'not_applicable'
export type RiskLevel = 'H' | 'M' | 'L' | ''

export interface ProcedureStep {
  stepId: string
  seq: number                  // 序号
  description: string          // 程序描述
  category: string             // 程序类别（实质性/控制测试/分析程序）
  objective: string            // 审计目标
  status: ProcedureStatus      // 执行状态
  executor: string             // 执行人
  date: string                 // 执行日期
  finding: string              // 发现
  conclusion: string           // 结论
  indexRef: string             // 索引号
  riskLevel: RiskLevel         // 风险等级
  controlConclusion: string    // 控制结论
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D2-procedure-steps'
const CONCLUSION_KEY = 'D2-procedure-overall-conclusion'

/** 默认7个审计程序步骤 */
const DEFAULT_STEPS: ProcedureStep[] = [
  {
    stepId: 's1', seq: 1,
    description: '获取应收账款明细表，复核加计正确，与总账、报表核对一致',
    category: '实质性', objective: '完整性/准确性',
    status: 'not_started', executor: '', date: '', finding: '', conclusion: '', indexRef: 'D2-1',
    riskLevel: '', controlConclusion: '',
  },
  {
    stepId: 's2', seq: 2,
    description: '实施函证程序，对重要客户发函确认余额',
    category: '实质性', objective: '存在/权利和义务',
    status: 'not_started', executor: '', date: '', finding: '', conclusion: '', indexRef: 'D0-6',
    riskLevel: '', controlConclusion: '',
  },
  {
    stepId: 's3', seq: 3,
    description: '检查坏账准备的计提是否充分和合理',
    category: '实质性', objective: '计价和分摊',
    status: 'not_started', executor: '', date: '', finding: '', conclusion: '', indexRef: 'D2-3',
    riskLevel: '', controlConclusion: '',
  },
  {
    stepId: 's4', seq: 4,
    description: '对应收账款实施分析程序（周转率、账龄分析）',
    category: '分析程序', objective: '计价和分摊',
    status: 'not_started', executor: '', date: '', finding: '', conclusion: '', indexRef: 'D2-5',
    riskLevel: '', controlConclusion: '',
  },
  {
    stepId: 's5', seq: 5,
    description: '检查期后回款情况，验证期末余额的可收回性',
    category: '实质性', objective: '计价和分摊',
    status: 'not_started', executor: '', date: '', finding: '', conclusion: '', indexRef: '',
    riskLevel: '', controlConclusion: '',
  },
  {
    stepId: 's6', seq: 6,
    description: '抽查记账凭证，验证应收账款的入账是否正确',
    category: '实质性', objective: '发生/准确性',
    status: 'not_started', executor: '', date: '', finding: '', conclusion: '', indexRef: 'D2-7',
    riskLevel: '', controlConclusion: '',
  },
  {
    stepId: 's7', seq: 7,
    description: '检查应收账款的列报与披露是否符合企业会计准则',
    category: '实质性', objective: '列报',
    status: 'not_started', executor: '', date: '', finding: '', conclusion: '', indexRef: 'D2-8',
    riskLevel: '', controlConclusion: '',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseSteps(jsonStr: string | null | undefined): ProcedureStep[] {
  if (!jsonStr) return DEFAULT_STEPS.map(s => ({ ...s }))
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_STEPS.map(s => ({ ...s }))
    }
    return parsed.map((raw: any) => ({
      stepId: raw.stepId || '',
      seq: raw.seq ?? 0,
      description: raw.description || '',
      category: raw.category || '',
      objective: raw.objective || '',
      status: (['not_started', 'in_progress', 'completed', 'not_applicable'].includes(raw.status) ? raw.status : 'not_started') as ProcedureStatus,
      executor: raw.executor || '',
      date: raw.date || '',
      finding: raw.finding || '',
      conclusion: raw.conclusion || '',
      indexRef: raw.indexRef || '',
      riskLevel: (['H', 'M', 'L'].includes(raw.riskLevel) ? raw.riskLevel : '') as RiskLevel,
      controlConclusion: raw.controlConclusion || '',
    }))
  } catch {
    return DEFAULT_STEPS.map(s => ({ ...s }))
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Procedure(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const steps = ref<ProcedureStep[]>(DEFAULT_STEPS.map(s => ({ ...s })))
  const overallConclusion = ref<string>('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const stepsResp = allResponses.value.get(STORAGE_KEY)
    steps.value = parseSteps(stepsResp?.remark)

    const conclusionResp = allResponses.value.get(CONCLUSION_KEY)
    overallConclusion.value = conclusionResp?.remark || ''
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      const isInitial = steps.value.every(s => s.status === 'not_started' && !s.executor)
      if (isInitial) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Computed ──────────────────────────────────────────────────────────

  const totalCount: ComputedRef<number> = computed(() => {
    return steps.value.length
  })

  const completedCount: ComputedRef<number> = computed(() => {
    return steps.value.filter(s => s.status === 'completed' || s.status === 'not_applicable').length
  })

  /**
   * 所有必要步骤是否完成
   * （status=not_applicable 也视为"已处理"）
   */
  const allNecessaryDone: ComputedRef<boolean> = computed(() => {
    return steps.value.every(
      s => s.status === 'completed' || s.status === 'not_applicable'
    )
  })

  // ─── Update Step ───────────────────────────────────────────────────────

  function updateStep(stepId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const step = steps.value.find(s => s.stepId === stepId)
    if (!step) return

    const key = field as keyof ProcedureStep
    if (key === 'stepId' || key === 'seq') return

    if (key === 'status') {
      step.status = (['not_started', 'in_progress', 'completed', 'not_applicable'].includes(value) ? value : 'not_started') as ProcedureStatus
    } else if (key === 'riskLevel') {
      step.riskLevel = (['H', 'M', 'L'].includes(value) ? value : '') as RiskLevel
    } else {
      ;(step as any)[key] = String(value)
    }

    debounceSave()
  }

  /**
   * 更新总体结论（仅 allNecessaryDone 时允许）
   */
  function updateOverallConclusion(value: string): void {
    if (isReadonly.value) return
    if (!allNecessaryDone.value) return
    overallConclusion.value = value
    debounceSave()
  }

  // ─── EventBus Listeners ────────────────────────────────────────────────

  /**
   * 监听 'risk:assessed' → 更新步骤风险等级
   */
  function onRiskAssessed(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'D2') return

    // Update risk level for all steps
    for (const step of steps.value) {
      if (detail.riskLevel) {
        step.riskLevel = detail.riskLevel as RiskLevel
      }
    }
    debounceSave()
  }

  /**
   * 监听 'control:test-concluded' → 更新控制结论
   */
  function onControlTestConcluded(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.cycleCode !== 'D2') return

    // Update control conclusion for relevant steps
    for (const step of steps.value) {
      if (step.category === '控制测试' || detail.affectsAll) {
        step.controlConclusion = detail.conclusion || ''
      }
    }
    debounceSave()
  }

  function registerEventListeners(): void {
    const riskHandler = (e: Event) => onRiskAssessed(e)
    const controlHandler = (e: Event) => onControlTestConcluded(e)

    window.addEventListener('risk:assessed', riskHandler)
    window.addEventListener('control:test-concluded', controlHandler)

    eventListeners.push(
      { event: 'risk:assessed', handler: riskHandler },
      { event: 'control:test-concluded', handler: controlHandler },
    )
  }

  function unregisterEventListeners(): void {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
    eventListeners.length = 0
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items = [
      { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(steps.value) },
      { item_id: CONCLUSION_KEY, conclusion: null, remark: overallConclusion.value },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    dispatchSaveEvent(items)
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Initialize & Lifecycle ────────────────────────────────────────────

  registerEventListeners()

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    unregisterEventListeners()
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    steps,
    overallConclusion,
    completedCount,
    totalCount,
    allNecessaryDone,
    updateStep,
    updateOverallConclusion,
  }
}

export default useD2Procedure
