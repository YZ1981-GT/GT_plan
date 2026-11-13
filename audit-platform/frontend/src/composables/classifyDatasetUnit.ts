/**
 * 前端数据集单位分类器。
 *
 * 与后端 dataset_unit_contract.classify_dataset_unit 保持同一口径：
 * - normalized_v1: source_summary.unit_normalization.contract 含有效 64 位小写十六进制 digest
 * - legacy_declared: 有 amount_unit 声明但没有 unit_normalization
 * - legacy_unknown: 其余（含 unit_normalization 无效的 fail-closed）
 */

import type { DatasetUnitClass } from './useDatasetUnitPresentation'

const DIGEST_RE = /^[0-9a-f]{64}$/

/**
 * 将 source_summary 归一为三类数据集单位状态。
 *
 * 与后端 classify_dataset_unit 保持一致的判定逻辑。
 */
export function classifyDatasetUnit(sourceSummary: Record<string, unknown> | null | undefined): DatasetUnitClass {
  if (!sourceSummary || typeof sourceSummary !== 'object') {
    return 'legacy_unknown'
  }

  const normalization = sourceSummary.unit_normalization
  if (normalization != null) {
    if (typeof normalization === 'object' && !Array.isArray(normalization)) {
      const contract = (normalization as Record<string, unknown>).contract
      if (contract && typeof contract === 'object' && !Array.isArray(contract)) {
        const digest = (contract as Record<string, unknown>).contract_digest
        if (typeof digest === 'string' && DIGEST_RE.test(digest)) {
          return 'normalized_v1'
        }
      }
    }
    // unit_normalization 存在但合同无效 → fail-closed
    return 'legacy_unknown'
  }

  // 没有 unit_normalization —— 检查旧的 amount_unit 声明
  const amountUnit = sourceSummary.amount_unit
  if (typeof amountUnit === 'string' && amountUnit.trim()) {
    return 'legacy_declared'
  }

  return 'legacy_unknown'
}
