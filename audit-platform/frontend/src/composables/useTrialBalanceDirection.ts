/**
 * 试算表方向推导 composable — 去补救化。
 *
 * getDirection() 优先级：
 *   1. 后端权威方向字段 (backend_direction)
 *   2. 用户持久化覆盖 (user_override)
 *   3. 历史推断 fallback (legacy_inferred)
 *
 * 移除普通科目按金额正负作为第一方向来源的逻辑。
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */

import type { DirectionSource } from '@/types/sign-convention'

export interface TrialBalanceRow {
  account_code: string
  account_name?: string
  closing_balance?: number
  opening_balance?: number
  /** 后端返回的权威方向 */
  direction?: 'debit' | 'credit' | 'unknown'
  /** 方向来源 */
  direction_source?: DirectionSource
  /** 用户覆盖 */
  user_override_direction?: 'debit' | 'credit'
}

export interface DirectionResult {
  direction: 'debit' | 'credit' | 'unknown'
  source: DirectionSource
}

/** 科目类别正常方向映射 */
const NORMAL_DIRECTION_BY_CATEGORY: Record<string, 'debit' | 'credit'> = {
  asset: 'debit',
  liability: 'credit',
  equity: 'credit',
  revenue: 'credit',
  income: 'credit',
  cost: 'debit',
  expense: 'debit',
}

/** 资产备抵名称匹配 */
const CONTRA_ASSET_PATTERN = /(累计折旧|累计摊销|坏账准备|减值准备|跌价准备|折耗)/

/**
 * 获取试算表行的方向。
 *
 * 优先级：backend field > user_override > legacy_inferred
 * 移除"金额正负作为第一来源"的逻辑。
 */
export function getDirection(
  row: TrialBalanceRow,
  accountCategory?: string,
): DirectionResult {
  // 1. 后端权威方向
  if (row.direction && row.direction !== 'unknown') {
    return {
      direction: row.direction,
      source: row.direction_source || 'explicit_direction',
    }
  }

  // 2. 用户覆盖
  if (row.user_override_direction) {
    return {
      direction: row.user_override_direction,
      source: 'user_override',
    }
  }

  // 3. 历史 fallback: 按类别推断（不按金额正负）
  const inferred = inferDirectionByCategory(row, accountCategory)
  if (inferred) {
    return {
      direction: inferred,
      source: 'legacy_inferred',
    }
  }

  return { direction: 'unknown', source: 'unknown' }
}

/**
 * 按科目类别推断方向（历史 fallback）。
 * 不再按金额正负推断普通科目方向。
 */
function inferDirectionByCategory(
  row: TrialBalanceRow,
  accountCategory?: string,
): 'debit' | 'credit' | null {
  // 资产备抵特殊处理
  const name = row.account_name || ''
  if (CONTRA_ASSET_PATTERN.test(name)) {
    return 'credit'
  }

  // 按类别映射
  if (accountCategory && accountCategory in NORMAL_DIRECTION_BY_CATEGORY) {
    return NORMAL_DIRECTION_BY_CATEGORY[accountCategory]
  }

  // 科目编码前缀推断
  const code = row.account_code || ''
  if (code.startsWith('1')) return 'debit'
  if (code.startsWith('2')) return 'credit'
  if (code.startsWith('3')) return 'credit'
  if (code.startsWith('5')) return 'debit'
  if (code.startsWith('6')) return 'debit'

  // 不按金额正负猜方向
  return null
}

export function useTrialBalanceDirection() {
  return { getDirection }
}
