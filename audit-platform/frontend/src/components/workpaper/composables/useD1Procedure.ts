/**
 * useD1Procedure — D1A 程序表进度（供 useD1Review / GtD1 使用）
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { PROCEDURE_STEPS_CONFIG, type TabStatus } from './d1Constants'

export type ProcedureStatus = '未开始' | '执行中' | '已完成' | '不适用'

export interface ProcedureStep {
  stepOrder: number
  stepName: string
  description: string
  status: ProcedureStatus
  executor: string
  executeDate: string
  wpIndexRef: string
  findings: string
  conclusion: string
  isRequired: boolean
  relatedTab: string | null
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

/** Tab 完成状态判定 */
export function getTabStatusFromResponses(tabResponses: ChecklistResponse[]): TabStatus {
  if (tabResponses.length === 0) return 'not-started'
  const hasValue = tabResponses.some(r => r.conclusion || r.remark)
  if (!hasValue) return 'not-started'
  const allComplete = tabResponses.every(r => r.conclusion || r.remark)
  return allComplete ? 'completed' : 'in-progress'
}

export function useD1Procedure(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  saveImmediate: SaveFn,
) {
  function getVal(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  }

  function setLocal(itemId: string, conclusion: string | null, remark: string | null = null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark }
    allResponses.value.set(itemId, item)
    return item
  }

  const overallConclusion = ref<string>(getVal('D1-proc-overall').remark || '')

  const procedureSteps: ComputedRef<ProcedureStep[]> = computed(() =>
    PROCEDURE_STEPS_CONFIG.map((cfg, idx) => {
      const n = idx + 1
      return {
        stepOrder: n,
        stepName: cfg.stepName,
        description: cfg.description,
        status: (getVal(`D1-proc-${n}-status`).conclusion as ProcedureStatus) || '未开始',
        executor: getVal(`D1-proc-${n}-executor`).remark || '',
        executeDate: getVal(`D1-proc-${n}-date`).remark || '',
        wpIndexRef: getVal(`D1-proc-${n}-wpindex`).remark || '',
        findings: getVal(`D1-proc-${n}-findings`).remark || '',
        conclusion: getVal(`D1-proc-${n}-conclusion`).remark || '',
        isRequired: cfg.isRequired,
        relatedTab: cfg.relatedTab,
      }
    }),
  )

  function setProcedureStatus(stepIndex: number, status: ProcedureStatus): void {
    const n = stepIndex + 1
    saveImmediate([setLocal(`D1-proc-${n}-status`, status)])
  }

  function setProcedureConclusion(stepIndex: number, conclusion: string): void {
    const n = stepIndex + 1
    saveImmediate([setLocal(`D1-proc-${n}-conclusion`, null, conclusion)])
  }

  type StepField = 'status' | 'executor' | 'executeDate' | 'wpIndexRef' | 'findings' | 'conclusion'

  function updateStepField(stepIndex: number, field: StepField, value: string): void {
    const n = stepIndex + 1
    const keyMap: Record<StepField, string> = {
      status: `D1-proc-${n}-status`,
      executor: `D1-proc-${n}-executor`,
      executeDate: `D1-proc-${n}-date`,
      wpIndexRef: `D1-proc-${n}-wpindex`,
      findings: `D1-proc-${n}-findings`,
      conclusion: `D1-proc-${n}-conclusion`,
    }
    const itemId = keyMap[field]
    if (field === 'status') {
      saveImmediate([setLocal(itemId, value as ProcedureStatus)])
    } else {
      saveImmediate([setLocal(itemId, null, value)])
    }
  }

  function saveOverallConclusion(text: string): void {
    overallConclusion.value = text
    saveImmediate([setLocal('D1-proc-overall', null, text)])
  }

  const completedCount = computed(() =>
    procedureSteps.value.filter(s => s.status === '已完成' || s.status === '不适用').length,
  )

  const totalCount = computed(() => procedureSteps.value.length)

  const procedureProgress: ComputedRef<{ completed: number; total: number }> = computed(() => {
    const steps = procedureSteps.value
    return {
      completed: steps.filter(s => s.status === '已完成' || s.status === '不适用').length,
      total: steps.length,
    }
  })

  const canInputOverallConclusion: ComputedRef<boolean> = computed(() =>
    procedureSteps.value
      .filter(s => s.isRequired)
      .every(s => s.status === '已完成' || s.status === '不适用'),
  )

  return {
    procedureSteps,
    setProcedureStatus,
    setProcedureConclusion,
    updateStepField,
    saveOverallConclusion,
    completedCount,
    totalCount,
    procedureProgress,
    canInputOverallConclusion,
    overallConclusion,
  }
}

export default useD1Procedure
