/** G11 页面级 G11-1 ↔ G11-2 勾稽校验 */
import { computed, type Ref } from 'vue'
import { computeG11DetailCrossCheck, type G11DetailCrossCheck } from './g11CrossHelpers'
import type { ChecklistResponse } from './useF1FormData'

const ADJ_KEY = 'G11-adj-rows'
const DETAIL_KEY = 'G11-detail-rows'

export function useG11CrossValidation(allResponses: Ref<Map<string, ChecklistResponse>>) {
  const crossCheck = computed((): G11DetailCrossCheck => {
    const adj = allResponses.value.get(ADJ_KEY)?.remark
    const detail = allResponses.value.get(DETAIL_KEY)?.remark
    return computeG11DetailCrossCheck(adj, detail)
  })

  const detailCrossValidation = computed(() => crossCheck.value.message)
  const detailMismatch = computed(() => !crossCheck.value.isBalanced && crossCheck.value.hasDetailData)
  const hasDetailData = computed(() => crossCheck.value.hasDetailData)

  return {
    crossCheck,
    detailCrossValidation,
    detailMismatch,
    hasDetailData,
  }
}
