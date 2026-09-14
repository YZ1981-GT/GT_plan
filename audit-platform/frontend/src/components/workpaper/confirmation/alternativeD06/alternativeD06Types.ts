/**
 * alternativeD06Types.ts — D0-6 应收及销售替代程序 类型定义
 *
 * D0-6 与 D0-5 姊妹同构，类型完全复用 D0-5，仅 payload _format 不同。
 */

// 复用 D0-5 全部核心类型
export type {
  CheckRow,
  BlockType,
  AlternativeCompany,
  SamplingConfig,
  BalanceSummary,
  AuditConclusion,
  AlternativeD05Metrics,
} from '../alternativeD05/alternativeD05Types'

export { BLOCK_LABELS } from '../alternativeD05/alternativeD05Types'

// ─── D0-6 专属 payload 格式 ─────────────────────────────────────────────────

import type { AlternativeCompany } from '../alternativeD05/alternativeD05Types'

export interface AlternativeD06Payload {
  /** 格式版本标识 */
  _format: 'alternative-d06-v1'
  /** 公司列表 */
  companies: AlternativeCompany[]
}
