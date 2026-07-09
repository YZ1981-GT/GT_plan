/**
 * useS12S13ExpertBranch — S12/S13 专家 domain 分支解析
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 本模块覆盖：
 * - resolveExpertSubSheet：根据 (prefix, domain) 确定性解析对应子表 sheetName
 * - EXPERT_DOMAINS：所有合法 domain 枚举
 * - EXPERT_DOMAIN_LABELS：domain 中文显示名
 *
 * 源模板 tab 名（Phase0 已确认）：
 * - S12-3-2 利用专家评价管理层的工作的适当性
 * - S12-3-3 利用专家评价管理层的工作(股份支付)
 * - S12-3-4 利用专家评价管理层的工作(金融工具公允价值）  ← 注意全角右括号
 * - S13-3-2 评价管理层专家工作的适当性
 * - S13-3-3 评价管理层专家工作的适当性(股份支付)
 * - S13-3-4 评价管理层专家工作的适当性(金融工具公允价值)
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/ Task 3.3
 * Requirements: 4.3, 4.4
 */

// ─── types ──────────────────────────────────────────────────

export type ExpertDomain = 'general' | 'share-based-payment' | 'financial-instrument-fair-value'
export type ExpertPrefix = 'S12' | 'S13'

// ─── constants ──────────────────────────────────────────────

/** 所有合法的专家 domain 枚举 */
export const EXPERT_DOMAINS: ExpertDomain[] = [
  'general',
  'share-based-payment',
  'financial-instrument-fair-value',
] as const

/** domain 中文显示名 */
export const EXPERT_DOMAIN_LABELS: Record<ExpertDomain, string> = {
  'general': '通用',
  'share-based-payment': '股份支付',
  'financial-instrument-fair-value': '金融工具公允价值',
}

// ─── 内部映射表（与源模板 tab 名完全一致） ─────────────────

const SHEET_NAME_MAP: Record<ExpertPrefix, Record<ExpertDomain, string>> = {
  S12: {
    'general': 'S12-3-2 利用专家评价管理层的工作的适当性',
    'share-based-payment': 'S12-3-3 利用专家评价管理层的工作(股份支付)',
    'financial-instrument-fair-value': 'S12-3-4 利用专家评价管理层的工作(金融工具公允价值）',
  },
  S13: {
    'general': 'S13-3-2 评价管理层专家工作的适当性',
    'share-based-payment': 'S13-3-3 评价管理层专家工作的适当性(股份支付)',
    'financial-instrument-fair-value': 'S13-3-4 评价管理层专家工作的适当性(金融工具公允价值)',
  },
}

// ─── 主函数 ─────────────────────────────────────────────────

/**
 * 解析专家评价子表的 sheetName
 *
 * 确定性映射：每个 (prefix, domain) 对始终返回相同 sheetName。
 * 若 domain 不在合法范围内，降级为 'general'（参见 design.md Error Handling）。
 *
 * @param prefix - 专家类型前缀 'S12'（注册会计师专家）或 'S13'（管理层专家）
 * @param domain - 专家评估领域
 * @returns 对应子表的完整 sheetName
 */
export function resolveExpertSubSheet(prefix: ExpertPrefix, domain: ExpertDomain): string {
  const prefixMap = SHEET_NAME_MAP[prefix]
  if (!prefixMap) {
    // 前缀非法时降级为 S12 general
    return SHEET_NAME_MAP.S12.general
  }

  const sheetName = prefixMap[domain]
  if (!sheetName) {
    // domain 不可识别，降级为对应 prefix 的 general
    return prefixMap.general
  }

  return sheetName
}
