/**
 * 数据集单位展示层 composable。
 *
 * 将后端三类分类（normalized_v1 / legacy_declared / legacy_unknown）
 * 映射为面向 UI 的标签、存储单位和换算因子。
 *
 * LedgerPenetration 与 TrialBalance 共用此 composable，
 * 数据集状态与用户显示单位彼此独立。
 */

import { computed, type ComputedRef, type Ref } from 'vue'

/** 后端 classify_dataset_unit 返回的三类字面量 */
export type DatasetUnitClass = 'normalized_v1' | 'legacy_declared' | 'legacy_unknown'

export interface DatasetUnitPresentation {
  /** 展示给用户的中文标签 */
  label: ComputedRef<string>
  /** 存储单位标识（仅 normalized_v1 为 'yuan'，其余为 null） */
  storageUnit: ComputedRef<string | null>
  /** 换算因子（仅 normalized_v1 从 contract.factor 取，其余为 null） */
  factor: ComputedRef<number | null>
}

/**
 * 根据数据集分类和来源摘要，计算面向 UI 的展示信息。
 *
 * @param classification - 由后端 classify_dataset_unit 返回的分类
 * @param sourceSummary  - 数据集的 source_summary 原始对象
 */
export function useDatasetUnitPresentation(
  classification: Ref<DatasetUnitClass>,
  sourceSummary: Ref<Record<string, unknown> | null>,
): DatasetUnitPresentation {
  const label = computed<string>(() => {
    switch (classification.value) {
      case 'normalized_v1':
        return '存储单位：元'
      case 'legacy_declared': {
        const amountUnit = _extractAmountUnit(sourceSummary.value)
        return amountUnit ? `历史声明：${amountUnit}` : '单位未确认'
      }
      case 'legacy_unknown':
      default:
        return '单位未确认'
    }
  })

  const storageUnit = computed<string | null>(() => {
    return classification.value === 'normalized_v1' ? 'yuan' : null
  })

  const factor = computed<number | null>(() => {
    if (classification.value !== 'normalized_v1') return null
    return _extractFactor(sourceSummary.value)
  })

  return { label, storageUnit, factor }
}

/** 从 source_summary.amount_unit 提取声明单位 */
function _extractAmountUnit(summary: Record<string, unknown> | null): string | null {
  if (!summary) return null
  const val = summary.amount_unit
  if (typeof val === 'string' && val.trim()) return val.trim()
  return null
}

/** 从 source_summary.unit_normalization.contract.factor 提取换算因子 */
function _extractFactor(summary: Record<string, unknown> | null): number | null {
  if (!summary) return null
  const norm = summary.unit_normalization
  if (!norm || typeof norm !== 'object') return null
  const contract = (norm as Record<string, unknown>).contract
  if (!contract || typeof contract !== 'object') return null
  const factor = (contract as Record<string, unknown>).factor
  if (typeof factor === 'number') return factor
  // JSON 里 factor 可能是字符串形式的数字
  if (typeof factor === 'string') {
    const parsed = Number(factor)
    if (!Number.isNaN(parsed) && Number.isFinite(parsed)) return parsed
  }
  return null
}
