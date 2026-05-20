/**
 * test_l_audit_nav.spec.ts — L 循环审计导航图 sheetKey 路由验证
 *
 * spec workpaper-l-debt-cycle L-F9（Task 2.8）
 *
 * **Validates: Requirements L-F9**
 *
 * 测试覆盖：
 * 1. L1 系列底稿 → l1a（短期借款）
 * 2. L3 系列底稿 → l3a（长期借款）
 * 3. L5 系列底稿 → l5a（长期应付款）
 * 4. L8 系列底稿 → l8a（财务费用）
 * 5. L0/L2/L4/L6/L7 → e1a（无专属路由 fallback）
 * 6. 小写 wp_code 也能正确路由
 * 7. 既有循环回归无影响
 */
import { describe, it, expect } from 'vitest'
import { resolveProcedureSheetKey } from '../resolveProcedureSheetKey'

describe('resolveProcedureSheetKey - L 循环路由 (L-F9 Task 2.8)', () => {
  it('L1 系列底稿（L1 / L1-2 / L1-5 等）→ l1a', () => {
    expect(resolveProcedureSheetKey('L1')).toBe('l1a')
    expect(resolveProcedureSheetKey('L1-1')).toBe('l1a')
    expect(resolveProcedureSheetKey('L1-2')).toBe('l1a')
    expect(resolveProcedureSheetKey('L1-5')).toBe('l1a')
  })

  it('L3 系列底稿（L3 / L3-1 / L3-5 等）→ l3a', () => {
    expect(resolveProcedureSheetKey('L3')).toBe('l3a')
    expect(resolveProcedureSheetKey('L3-1')).toBe('l3a')
    expect(resolveProcedureSheetKey('L3-2')).toBe('l3a')
    expect(resolveProcedureSheetKey('L3-5')).toBe('l3a')
  })

  it('L5 系列底稿（L5 / L5-1 / L5-2 等）→ l5a', () => {
    expect(resolveProcedureSheetKey('L5')).toBe('l5a')
    expect(resolveProcedureSheetKey('L5-1')).toBe('l5a')
    expect(resolveProcedureSheetKey('L5-2')).toBe('l5a')
  })

  it('L8 系列底稿（L8 / L8-1 / L8-2 等）→ l8a', () => {
    expect(resolveProcedureSheetKey('L8')).toBe('l8a')
    expect(resolveProcedureSheetKey('L8-1')).toBe('l8a')
    expect(resolveProcedureSheetKey('L8-2')).toBe('l8a')
  })

  it('L0/L2/L4/L6/L7 → e1a（无专属路由 fallback）', () => {
    expect(resolveProcedureSheetKey('L0')).toBe('e1a')
    expect(resolveProcedureSheetKey('L2')).toBe('e1a')
    expect(resolveProcedureSheetKey('L4')).toBe('e1a')
    expect(resolveProcedureSheetKey('L6')).toBe('e1a')
    expect(resolveProcedureSheetKey('L7')).toBe('e1a')
  })

  it('小写 wp_code 也能正确路由（uppercase 标准化）', () => {
    expect(resolveProcedureSheetKey('l1')).toBe('l1a')
    expect(resolveProcedureSheetKey('l3')).toBe('l3a')
    expect(resolveProcedureSheetKey('l5')).toBe('l5a')
    expect(resolveProcedureSheetKey('l8')).toBe('l8a')
    expect(resolveProcedureSheetKey('l8-2')).toBe('l8a')
  })
})

describe('resolveProcedureSheetKey - L 循环不影响既有路由（回归）', () => {
  it('J 循环路由保留', () => {
    expect(resolveProcedureSheetKey('J1')).toBe('j1a')
    expect(resolveProcedureSheetKey('J2')).toBe('j2a')
    expect(resolveProcedureSheetKey('J3')).toBe('j3a')
  })

  it('K 循环路由保留', () => {
    expect(resolveProcedureSheetKey('K1')).toBe('k1a')
    expect(resolveProcedureSheetKey('K8')).toBe('k8a')
    expect(resolveProcedureSheetKey('K11')).toBe('k11a')
  })

  it('H 循环路由保留', () => {
    expect(resolveProcedureSheetKey('H1')).toBe('h1a')
    expect(resolveProcedureSheetKey('H8')).toBe('h8a')
  })

  it('默认 fallback 保留', () => {
    expect(resolveProcedureSheetKey('E1')).toBe('e1a')
    expect(resolveProcedureSheetKey('')).toBe('e1a')
  })
})
