/**
 * 底稿语义契约前端类型测试
 *
 * 验证:
 * - 枚举值完整性
 * - type guard 正确性
 * - 前后端 fixture 一致性（读取共享 fixture JSON）
 */

import { describe, it, expect } from 'vitest'
import {
  SHEET_CONTENT_TYPES,
  FIELD_SOURCE_TYPES,
  STALE_POLICIES,
  PROGRAM_STATUSES,
  REVIEW_STATUSES,
  isSheetContentType,
  isFieldSourceType,
  isStalePolicy,
  isProgramStatus,
  isReviewStatus,
} from '@/types/workpaperSemanticContract'

// fixture 读取通过 @fixtures alias
import fixture from '@fixtures/workpaper_semantic_contract_fixture.json'

// ---------------------------------------------------------------------------
// SheetContentType 测试
// ---------------------------------------------------------------------------

describe('SheetContentType', () => {
  it('包含 13 个枚举值', () => {
    expect(SHEET_CONTENT_TYPES).toHaveLength(13)
  })

  it('type guard 接受合法值', () => {
    for (const value of SHEET_CONTENT_TYPES) {
      expect(isSheetContentType(value)).toBe(true)
    }
  })

  it('type guard 拒绝非法值', () => {
    expect(isSheetContentType('invalid_type')).toBe(false)
    expect(isSheetContentType('')).toBe(false)
    expect(isSheetContentType(123)).toBe(false)
    expect(isSheetContentType(null)).toBe(false)
    expect(isSheetContentType(undefined)).toBe(false)
  })

  it('type guard 拒绝大写形式', () => {
    expect(isSheetContentType('CONTROL_PANEL')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// FieldSourceType 测试
// ---------------------------------------------------------------------------

describe('FieldSourceType', () => {
  it('包含 5 个枚举值', () => {
    expect(FIELD_SOURCE_TYPES).toHaveLength(5)
  })

  it('type guard 接受合法值', () => {
    for (const value of FIELD_SOURCE_TYPES) {
      expect(isFieldSourceType(value)).toBe(true)
    }
  })

  it('type guard 拒绝非法值', () => {
    expect(isFieldSourceType('database')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// StalePolicy 测试
// ---------------------------------------------------------------------------

describe('StalePolicy', () => {
  it('包含 4 个枚举值', () => {
    expect(STALE_POLICIES).toHaveLength(4)
  })

  it('type guard 接受合法值', () => {
    for (const value of STALE_POLICIES) {
      expect(isStalePolicy(value)).toBe(true)
    }
  })

  it('type guard 拒绝非法值', () => {
    expect(isStalePolicy('auto_refresh')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// ProgramStatus 测试
// ---------------------------------------------------------------------------

describe('ProgramStatus', () => {
  it('包含 5 个枚举值', () => {
    expect(PROGRAM_STATUSES).toHaveLength(5)
  })

  it('type guard 接受合法值', () => {
    for (const value of PROGRAM_STATUSES) {
      expect(isProgramStatus(value)).toBe(true)
    }
  })

  it('type guard 拒绝非法值', () => {
    expect(isProgramStatus('done')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// ReviewStatus 测试
// ---------------------------------------------------------------------------

describe('ReviewStatus', () => {
  it('包含 3 个枚举值', () => {
    expect(REVIEW_STATUSES).toHaveLength(3)
  })

  it('type guard 接受合法值', () => {
    for (const value of REVIEW_STATUSES) {
      expect(isReviewStatus(value)).toBe(true)
    }
  })

  it('type guard 拒绝非法值', () => {
    expect(isReviewStatus('waiting')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// 前后端 fixture 一致性
// ---------------------------------------------------------------------------

describe('前后端 fixture 一致性', () => {
  it('SheetContentType 与后端 fixture 一致', () => {
    expect(SHEET_CONTENT_TYPES).toEqual(fixture.SheetContentType)
  })

  it('FieldSourceType 与后端 fixture 一致', () => {
    expect(FIELD_SOURCE_TYPES).toEqual(fixture.FieldSourceType)
  })

  it('StalePolicy 与后端 fixture 一致', () => {
    expect(STALE_POLICIES).toEqual(fixture.StalePolicy)
  })

  it('ProgramStatus 与后端 fixture 一致', () => {
    expect(PROGRAM_STATUSES).toEqual(fixture.ProgramStatus)
  })

  it('ReviewStatus 与后端 fixture 一致', () => {
    expect(REVIEW_STATUSES).toEqual(fixture.ReviewStatus)
  })
})
