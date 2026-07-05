/**
 * useD6PolicyCheck — D6-7 减值政策检查（段落式4项评价）
 *
 * Item IDs:
 *   D6-7-eval-{1-4}  — 4项审计评价 textarea
 *   D6-7-objective   — 审计目标
 *   D6-7-note-explanation / D6-7-note-conclusion
 */
import { ref, watch, type Ref } from 'vue'
import type { ChecklistResponse } from './useD6FormData'

export interface PolicyEvalItem {
  id: number
  itemId: string
  aiSection: string
  title: string
}

export const POLICY_EVAL_ITEMS: PolicyEvalItem[] = [
  {
    id: 1,
    itemId: 'D6-7-eval-1',
    aiSection: 'policy-eval-1',
    title: '(一) 合同资产减值计提会计政策合规性评价',
  },
  {
    id: 2,
    itemId: 'D6-7-eval-2',
    aiSection: 'policy-eval-2',
    title: '(二) 历史坏账损失情况及ECL模型预测准确性',
  },
  {
    id: 3,
    itemId: 'D6-7-eval-3',
    aiSection: 'policy-eval-3',
    title: '(三) 前瞻性信息来源及影响评价',
  },
  {
    id: 4,
    itemId: 'D6-7-eval-4',
    aiSection: 'policy-eval-4',
    title: '(四) 同行业公司会计政策对比分析',
  },
]

export interface UseD6PolicyCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}

export function useD6PolicyCheck(options: UseD6PolicyCheckOptions) {
  const { allResponses, debouncedSave } = options

  const evaluations = ref<Record<number, string>>({ 1: '', 2: '', 3: '', 4: '' })
  const auditObjective = ref('')
  const auditNotes = ref({ explanation: '', conclusion: '' })

  for (const item of POLICY_EVAL_ITEMS) {
    watch(
      () => allResponses.value.get(item.itemId)?.remark,
      (v) => { evaluations.value[item.id] = v || '' },
      { immediate: true },
    )
    watch(
      () => evaluations.value[item.id],
      (v) => debouncedSave(item.itemId, { remark: v }),
    )
  }

  watch(
    () => allResponses.value.get('D6-7-objective')?.remark,
    (v) => { auditObjective.value = v || '' },
    { immediate: true },
  )
  watch(
    () => auditObjective.value,
    (v) => debouncedSave('D6-7-objective', { remark: v }),
  )

  watch(
    () => allResponses.value.get('D6-7-note-explanation')?.remark,
    (v) => { auditNotes.value.explanation = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('D6-7-note-conclusion')?.remark,
    (v) => { auditNotes.value.conclusion = v || '' },
    { immediate: true },
  )
  watch(
    () => auditNotes.value.explanation,
    (v) => debouncedSave('D6-7-note-explanation', { remark: v }),
  )
  watch(
    () => auditNotes.value.conclusion,
    (v) => debouncedSave('D6-7-note-conclusion', { remark: v }),
  )

  function updateEvaluation(id: number, value: string): void {
    evaluations.value = { ...evaluations.value, [id]: value }
  }

  return {
    evaluations,
    updateEvaluation,
    auditObjective,
    auditNotes,
    policyEvalItems: POLICY_EVAL_ITEMS,
  }
}

export default useD6PolicyCheck
