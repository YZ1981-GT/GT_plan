import { computed, type Ref } from 'vue'
import type { ChecklistResponse } from './useF1FormData'
import {
  evaluateG12CoreWorkflowReadiness,
  resolveG12WorkflowActiveIndex,
  type G12WorkflowReadiness,
} from './g12CoreWorkflowReadiness'

export function useG12CoreWorkflow(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  pageCode: string
}) {
  const readiness = computed(() => evaluateG12CoreWorkflowReadiness(opts.allResponses.value))
  const activeIndex = computed(() => resolveG12WorkflowActiveIndex(opts.pageCode, readiness.value))
  const completedIndices = computed(() => readiness.value.completedStepIndices)

  return { readiness, activeIndex, completedIndices }
}

export type { G12WorkflowReadiness }
