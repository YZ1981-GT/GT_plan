/**
 * alternativeH05Types.ts — H0-5 固定资产循环替代程序 类型定义
 *
 * 核心设计：
 * - 多公司 master-detail：每公司一组 4 区块检查宽表
 * - 4 区块各自列结构不同，由 blockColumnConfigsH05 驱动
 * - 从 H0-1 带入未回函公司（importFromSummary）
 * - 复用 AlternativeCompany / CheckRow（alternativeD05Types）
 */
import type { AlternativeCompany } from '../alternativeD05/alternativeD05Types'

// ─── H0-5 payload ─────────────────────────────────────────────────────────────

export interface AlternativeH05Payload {
  _format: 'alternative-h05-v1'
  companies: AlternativeCompany[]
}

// ─── 余额汇总区 ───────────────────────────────────────────────────────────────

export interface AlternativeH05Summary {
  /** 函证项目（固定资产/在建工程） */
  investmentType: string
  /** 年初余额 */
  openingBalance: number
  /** 借方发生额 */
  debitAmount: number
  /** 贷方发生额 */
  creditAmount: number
  /** 期末余额 */
  closingBalance: number
  /** 本期新增金额 */
  currentAddition: number
  /** 权属证据检查比例 */
  ownershipCheckRatio: number
  /** 期后验收检查比例 */
  postAcceptanceRatio: number
}

// ─── H0-5 四区块 key ──────────────────────────────────────────────────────────

export type H05BlockKey = 'acceptance_ownership' | 'balance_evidence' | 'new_asset_check' | 'mortgage_lease'

/** H05 区块 key → D05 通用 blockType 映射 */
export const H05_BLOCK_MAP: Record<H05BlockKey, string> = {
  acceptance_ownership: 'block1',
  balance_evidence: 'block2',
  new_asset_check: 'block3',
  mortgage_lease: 'block4',
}

// ─── H0-1 未回函公司（importFromSummary 输入） ─────────────────────────────────

export interface H01UnrepliedEntity {
  /** 被询证单位名称 */
  entity_name: string
  /** 函证索引号 */
  confirm_index?: string
  /** 函证金额 */
  confirm_amount?: number
  /** 未回函原因 */
  unreplied_reason?: string
}
