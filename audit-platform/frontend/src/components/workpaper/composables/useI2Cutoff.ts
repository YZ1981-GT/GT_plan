/**
 * useI2Cutoff — 开发支出截止性测试（I2-13 / I2-14）
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

const I2_CUTOFF_CONFIG = {
  accountCode: '1717',
  forwardRowsKey: 'I2-13-rows',
  backwardRowsKey: 'I2-14-rows',
  forwardCriteriaKey: 'I2-13-sample-criteria',
  backwardCriteriaKey: 'I2-14-sample-criteria',
  sharedCriteriaKey: 'I2-cutoff-shared-criteria',
  forwardSheetCode: 'I2-13',
  backwardSheetCode: 'I2-14',
  adjustmentSheetCode: 'I2-3',
  adjustmentRowsKey: 'I2-3-rows',
  draftDefaults: {
    reportItem: '开发支出',
    accountCode: '1717',
    accountName: '开发支出',
    defaultIndexRef: 'I2',
  },
  defaultThresholdDays: 5,
} as const

export function useI2Cutoff(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  projectId: Ref<string>
  cutoffThresholdDays?: number
  year?: Ref<number | string | undefined> | number | string
  autoSaveMs?: number
}): ReturnType<typeof useCycleCutoff> {
  return useCycleCutoff({
    config: I2_CUTOFF_CONFIG,
    ...params,
  })
}

export default useI2Cutoff
