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

/**
 * 获取方向来源的显示标签。
 *
 * Task 7.5: 历史 fallback 显示 `legacy_inferred` / "推断方向"
 */
export function getDirectionSourceLabel(source: DirectionSource): string {
  const labels: Record<DirectionSource, string> = {
    explicit_direction: '显式方向',
    split_columns: '借贷分列',
    account_category_inferred: '类别推断',
    account_category_inferred_low_confidence: '低置信推断',
    contra_account: '备抵科目',
    user_override: '用户覆盖',
    legacy_inferred: '推断方向',
    unknown: '未知',
  }
  return labels[source] || source
}

/**
 * 判断是否应显示"推断方向"徽标。
 *
 * Task 7.5: direction_source === 'legacy_inferred' 时显示 "(推断方向)" badge
 */
export function shouldShowInferredBadge(result: DirectionResult): boolean {
  return result.source === 'legacy_inferred'
    || result.source === 'account_category_inferred_low_confidence'
}

/**
 * 调用后端 overlay 持久化接口保存方向覆盖。
 *
 * Task 7.4: 本地 directionOverrides 改为调用后端 overlay 持久化接口
 */
export async function saveDirectionOverride(
  projectId: string,
  datasetId: string,
  recordId: string,
  direction: 'debit' | 'credit',
  reason: string,
): Promise<{ id: string; override_at: string }> {
  const url = `/api/projects/${projectId}/datasets/${datasetId}/sign-convention/direction-override`
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      table_name: 'tb_balance',
      record_id: recordId,
      override_direction: direction,
      override_reason: reason,
    }),
  })

  if (!response.ok) {
    throw new Error(`方向覆盖保存失败: ${response.status}`)
  }

  const body = await response.json()
  // 处理 ResponseWrapperMiddleware 信封
  const data = body.data ?? body
  return { id: data.id, override_at: data.override_at }
}

export function useTrialBalanceDirection() {
  return {
    getDirection,
    getDirectionSourceLabel,
    shouldShowInferredBadge,
    saveDirectionOverride,
  }
}
