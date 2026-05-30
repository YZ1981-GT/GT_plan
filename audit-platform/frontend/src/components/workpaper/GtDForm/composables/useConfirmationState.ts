/**
 * useConfirmationState — 函证工作流阶段导航 composable
 *
 * 职责：
 * - 阶段定义解析（stages）
 * - 当前激活阶段（activeStageNo / activeStageIdx）
 * - 阶段切换（goToStage）
 * - 步骤状态计算（stepStatus）
 *
 * Validates: Requirements 5.2
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

type FieldType = 'text' | 'textarea' | 'number' | 'percent' | 'date' | 'enum'
type RenderHint = 'amount' | 'tag' | 'index_chip' | 'attachment_chip' | string

export interface FieldDef {
  name: string
  label: string
  type?: FieldType
  cell?: string
  enum?: string[]
  render?: RenderHint
  readonly?: boolean
  required?: boolean
  hint?: string
  max_length?: number
  min?: number
  max?: number
  format?: string
  formula?: string
  source?: string
  default?: any
  default_from?: string
}

export interface ActionDef {
  name: string
  label: string
  emit?: string
  api?: string
  payload?: Record<string, any>
}

export interface StageDef {
  stage: string
  id?: string
  title?: string
  description?: string
  start_row?: number
  end_row?: number | string
  fields?: FieldDef[]
  actions?: ActionDef[]
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseConfirmationStateParams {
  /** confirmation_workflow.stages from schema */
  stages: ComputedRef<StageDef[]>
  /** htmlData.active_stage initial value */
  initialActiveStage: string | undefined
}

export interface UseConfirmationStateReturn {
  activeStageNo: Ref<string>
  activeStageIdx: ComputedRef<number>
  currentStage: ComputedRef<StageDef | null>
  goToStage: (idx: number) => void
  stepStatus: (idx: number) => 'wait' | 'process' | 'finish' | 'success' | 'error'
}

export function useConfirmationState(params: UseConfirmationStateParams): UseConfirmationStateReturn {
  const { stages, initialActiveStage } = params

  // Determine initial active stage
  const resolvedInitial = (() => {
    if (typeof initialActiveStage === 'string' && stages.value.some(s => s.stage === initialActiveStage)) {
      return initialActiveStage
    }
    return stages.value[0]?.stage ?? ''
  })()

  const activeStageNo = ref<string>(resolvedInitial)

  const activeStageIdx = computed(() => {
    if (!stages.value.length) return 0
    const idx = stages.value.findIndex(s => s.stage === activeStageNo.value)
    return idx >= 0 ? idx : 0
  })

  const currentStage = computed<StageDef | null>(
    () => stages.value[activeStageIdx.value] ?? null
  )

  function goToStage(idx: number) {
    if (idx < 0 || idx >= stages.value.length) return
    const target = stages.value[idx]
    if (target) {
      activeStageNo.value = target.stage
    }
  }

  function stepStatus(idx: number): 'wait' | 'process' | 'finish' | 'success' | 'error' {
    if (idx < activeStageIdx.value) return 'finish'
    if (idx === activeStageIdx.value) return 'process'
    return 'wait'
  }

  return {
    activeStageNo,
    activeStageIdx,
    currentStage,
    goToStage,
    stepStatus,
  }
}
