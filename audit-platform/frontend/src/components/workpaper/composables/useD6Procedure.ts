/**
 * useD6Procedure — D6A 程序表进度
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistResponse } from './useD6FormData'
import { D6_PROCEDURE_STEPS_CONFIG } from './d6Constants'

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

type ChecklistItem = { item_id: string; conclusion: string | null; remark: string | null }
type SaveFn = (items: ChecklistItem[]) => Promise<void>

export function useD6Procedure(
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

  const overallConclusion = ref<string>(getVal('D6-proc-overall').remark || '')

  const procedureSteps: ComputedRef<ProcedureStep[]> = computed(() =>
    D6_PROCEDURE_STEPS_CONFIG.map((cfg, idx) => {
      const n = idx + 1
      return {
        stepOrder: n,
        stepName: cfg.stepName,
        description: cfg.description,
        status: (getVal(`D6-proc-${n}-status`).conclusion as ProcedureStatus) || '未开始',
        executor: getVal(`D6-proc-${n}-executor`).remark || '',
        executeDate: getVal(`D6-proc-${n}-date`).remark || '',
        wpIndexRef: getVal(`D6-proc-${n}-wpindex`).remark || '',
        findings: getVal(`D6-proc-${n}-findings`).remark || '',
        conclusion: getVal(`D6-proc-${n}-conclusion`).remark || '',
        isRequired: cfg.isRequired,
        relatedTab: cfg.relatedTab,
      }
    }),
  )

  type StepField = 'status' | 'executor' | 'executeDate' | 'wpIndexRef' | 'findings' | 'conclusion'

  function updateStepField(stepIndex: number, field: StepField, value: string): void {
    const n = stepIndex + 1
    const keyMap: Record<StepField, string> = {
      status: `D6-proc-${n}-status`,
      executor: `D6-proc-${n}-executor`,
      executeDate: `D6-proc-${n}-date`,
      wpIndexRef: `D6-proc-${n}-wpindex`,
      findings: `D6-proc-${n}-findings`,
      conclusion: `D6-proc-${n}-conclusion`,
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
    saveImmediate([setLocal('D6-proc-overall', null, text)])
  }

  const completedCount = computed(() =>
    procedureSteps.value.filter(s => s.status === '已完成' || s.status === '不适用').length,
  )

  const totalCount = computed(() => procedureSteps.value.length)

  const canInputOverallConclusion: ComputedRef<boolean> = computed(() =>
    procedureSteps.value
      .filter(s => s.isRequired)
      .every(s => s.status === '已完成' || s.status === '不适用'),
  )

  return {
    procedureSteps,
    updateStepField,
    saveOverallConclusion,
    completedCount,
    totalCount,
    canInputOverallConclusion,
    overallConclusion,
  }
}

export default useD6Procedure
