/**
 * 符号约定类型前后端一致性 fixture 测试
 *
 * 验证前端枚举值与后端 golden fixture 完全一致。
 * 若后端改枚举，此测试将断言失败。
 *
 * @see backend/tests/ledger_import/test_sign_convention_types.py
 */
import { describe, it, expect } from 'vitest'
import {
  DIRECTION_SOURCE_VALUES,
  SIGN_CONVENTION_VERSION_VALUES,
  CURRENT_SIGN_CONVENTION,
  MIGRATION_SAFETY_LEVEL_VALUES,
} from '@/types/sign-convention'
import type { DirectionSource, SignConventionVersion, MigrationSafetyLevel, SignAnomaly } from '@/types/sign-convention'

// Golden fixtures — 与后端 test_sign_convention_types.py 对齐
const GOLDEN_DIRECTION_SOURCE_VALUES = [
  'explicit_direction',
  'split_columns',
  'account_category_inferred',
  'account_category_inferred_low_confidence',
  'user_override',
  'legacy_inferred',
  'unknown',
]

const GOLDEN_SIGN_CONVENTION_VERSION_VALUES = ['v1_net_debit_positive']

const GOLDEN_MIGRATION_SAFETY_LEVEL_VALUES = [
  'safe_auto_fix',
  'manual_review_required',
  'no_change',
]

describe('sign-convention types contract', () => {
  it('DirectionSource values match backend golden fixture', () => {
    expect(DIRECTION_SOURCE_VALUES).toEqual(GOLDEN_DIRECTION_SOURCE_VALUES)
  })

  it('DirectionSource has no duplicates', () => {
    const unique = new Set(DIRECTION_SOURCE_VALUES)
    expect(unique.size).toBe(DIRECTION_SOURCE_VALUES.length)
  })

  it('DirectionSource count is 7', () => {
    expect(DIRECTION_SOURCE_VALUES).toHaveLength(7)
  })

  it('SignConventionVersion values match backend golden fixture', () => {
    expect(SIGN_CONVENTION_VERSION_VALUES).toEqual(GOLDEN_SIGN_CONVENTION_VERSION_VALUES)
  })

  it('CURRENT_SIGN_CONVENTION is v1_net_debit_positive', () => {
    expect(CURRENT_SIGN_CONVENTION).toBe('v1_net_debit_positive')
  })

  it('MigrationSafetyLevel values match backend golden fixture', () => {
    expect(MIGRATION_SAFETY_LEVEL_VALUES).toEqual(GOLDEN_MIGRATION_SAFETY_LEVEL_VALUES)
  })

  it('MigrationSafetyLevel has no duplicates', () => {
    const unique = new Set(MIGRATION_SAFETY_LEVEL_VALUES)
    expect(unique.size).toBe(MIGRATION_SAFETY_LEVEL_VALUES.length)
  })

  it('SignAnomaly interface has expected shape', () => {
    const anomaly: SignAnomaly = {
      account_code: '2221',
      account_name: '应交税费',
      expected_direction: 'credit',
      actual_direction: 'debit',
      balance_amount: 14203492.0,
      category: 'liability',
      reason: 'liability_normal_credit',
    }
    expect(anomaly.account_code).toBe('2221')
    expect(anomaly.expected_direction).toBe('credit')
    expect(anomaly.actual_direction).toBe('debit')
  })

  it('type assignability — all DirectionSource values are assignable', () => {
    const sources: DirectionSource[] = [...DIRECTION_SOURCE_VALUES]
    expect(sources).toHaveLength(7)
  })

  it('type assignability — all MigrationSafetyLevel values are assignable', () => {
    const levels: MigrationSafetyLevel[] = [...MIGRATION_SAFETY_LEVEL_VALUES]
    expect(levels).toHaveLength(3)
  })

  it('type assignability — SignConventionVersion', () => {
    const versions: SignConventionVersion[] = [...SIGN_CONVENTION_VERSION_VALUES]
    expect(versions).toHaveLength(1)
  })
})
