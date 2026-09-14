/**
 * useI6Cutoff — 研发费用截止性测试（I6-5 / I6-6）
 * 基于 useCycleCutoff 通用引擎
 */
import type { Ref } from 'vue'
import {
  useCycleCutoff,
  type CutoffRow,
  type CutoffSampleCriteria,
  type CutoffDirection,
} from './useCycleCutoff'

export type { CutoffRow, CutoffSampleCriteria, CutoffDirection }

const I6_CUTOFF_CONFIG = {
  accountCode: '6602',
  forwardRowsKey: 'I6-5-rows',
  backwardRowsKey: 'I6-6-rows',
  forwardCriteriaKey: 'I6-5-sample-criteria',
  backwardCriteriaKey: 'I6-6-sample-criteria',
  sharedCriteriaKey: 'I6-cutoff-shared-criteria',
  forwardSheetCode: 'I6-5',
  backwardSheetCode: 'I6-6',
  adjustmentSheetCode: 'I6-3',
  adjustmentRowsKey: 'I6-3-rows',
  draftDefaults: {
    reportItem: '研发费用',
    accountCode: '6602',
    accountName: '研发费用',
    defaultIndexRef: 'I6',
  },
  defaultThresholdDays: 5,
} as const

export function useI6Cutoff(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  projectId: Ref<string>
  cutoffThresholdDays?: number
  year?: Ref<number | string | undefined> | number | string
  autoSaveMs?: number
}): ReturnType<typeof useCycleCutoff> {
  return useCycleCutoff({
    config: I6_CUTOFF_CONFIG,
    ...params,
  })
}

export default useI6Cutoff
