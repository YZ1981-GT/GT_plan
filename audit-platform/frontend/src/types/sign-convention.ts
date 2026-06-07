/**
 * 符号约定与方向来源类型定义
 *
 * 与后端 `sign_convention_types.py` 保持一致。
 * 枚举值列表用于一致性 fixture 测试。
 *
 * @see requirements 1.1, 1.3, 2.2
 */

/** 方向来源枚举 */
export type DirectionSource =
  | 'explicit_direction'
  | 'split_columns'
  | 'account_category_inferred'
  | 'account_category_inferred_low_confidence'
  | 'user_override'
  | 'legacy_inferred'
  | 'unknown'

/** 方向来源枚举值列表 */
export const DIRECTION_SOURCE_VALUES: DirectionSource[] = [
  'explicit_direction',
  'split_columns',
  'account_category_inferred',
  'account_category_inferred_low_confidence',
  'user_override',
  'legacy_inferred',
  'unknown',
]

/** 符号约定版本 */
export type SignConventionVersion = 'v1_net_debit_positive'

/** 符号约定版本值列表 */
export const SIGN_CONVENTION_VERSION_VALUES: SignConventionVersion[] = [
  'v1_net_debit_positive',
]

/** 当前生效的符号约定 */
export const CURRENT_SIGN_CONVENTION: SignConventionVersion = 'v1_net_debit_positive'

/** 迁移安全等级 */
export type MigrationSafetyLevel =
  | 'safe_auto_fix'
  | 'manual_review_required'
  | 'no_change'

/** 迁移安全等级值列表 */
export const MIGRATION_SAFETY_LEVEL_VALUES: MigrationSafetyLevel[] = [
  'safe_auto_fix',
  'manual_review_required',
  'no_change',
]

/** 符号异常记录 */
export interface SignAnomaly {
  account_code: string
  account_name: string | null
  expected_direction: 'debit' | 'credit'
  actual_direction: string
  balance_amount: number
  category: string
  reason: string
}
