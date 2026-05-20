/**
 * test_n_audit_nav.spec.ts — N-F5 Task 2.5
 *
 * 验证 resolveProcedureSheetKey N 循环路由：
 * - N1→n1a / N2→n2a / N3→n3a / N4→n4a / N5→n5a
 * - 子表路由到对应主表（N2-1 → n2a）
 * - 大小写不敏感
 * - 其他循环路由不受影响
 */
import { describe, it, expect } from 'vitest'
import { resolveProcedureSheetKey } from '../resolveProcedureSheetKey'

describe('resolveProcedureSheetKey - N 循环路由 (N-F5 Task 2.5)', () => {
  it('N1 → n1a（递延所得税资产）', () => {
    expect(resolveProcedureSheetKey('N1')).toBe('n1a')
  })

  it('N1-2 → n1a（子表路由到 N1）', () => {
    expect(resolveProcedureSheetKey('N1-2')).toBe('n1a')
  })

  it('N2 → n2a（应交税费）', () => {
    expect(resolveProcedureSheetKey('N2')).toBe('n2a')
  })

  it('N2-1 → n2a（子表路由到 N2）', () => {
    expect(resolveProcedureSheetKey('N2-1')).toBe('n2a')
  })

  it('N3 → n3a（递延所得税负债）', () => {
    expect(resolveProcedureSheetKey('N3')).toBe('n3a')
  })

  it('N3-2 → n3a（子表路由到 N3）', () => {
    expect(resolveProcedureSheetKey('N3-2')).toBe('n3a')
  })

  it('N4 → n4a（税金及附加）', () => {
    expect(resolveProcedureSheetKey('N4')).toBe('n4a')
  })

  it('N4-1 → n4a（子表路由到 N4）', () => {
    expect(resolveProcedureSheetKey('N4-1')).toBe('n4a')
  })

  it('N5 → n5a（所得税费用）', () => {
    expect(resolveProcedureSheetKey('N5')).toBe('n5a')
  })

  it('N5-1 → n5a（子表路由到 N5）', () => {
    expect(resolveProcedureSheetKey('N5-1')).toBe('n5a')
  })

  it('大小写不敏感：n2 → n2a', () => {
    expect(resolveProcedureSheetKey('n2')).toBe('n2a')
  })

  it('大小写不敏感：n5-1 → n5a', () => {
    expect(resolveProcedureSheetKey('n5-1')).toBe('n5a')
  })
})

describe('resolveProcedureSheetKey - N 循环不影响既有路由（回归）', () => {
  it('M2 → m2a（M 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('M2')).toBe('m2a')
  })

  it('L1 → l1a（L 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('L1')).toBe('l1a')
  })

  it('K8 → k8a（K 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('K8')).toBe('k8a')
  })

  it('J1 → j1a（J 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('J1')).toBe('j1a')
  })

  it('H1 → h1a（H 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('H1')).toBe('h1a')
  })

  it('G7 → g7a（G 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('G7')).toBe('g7a')
  })

  it('F2 → f2a（F 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('F2')).toBe('f2a')
  })

  it('D4 → d4a（D 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('D4')).toBe('d4a')
  })

  it('E1 → e1a（默认 fallback）', () => {
    expect(resolveProcedureSheetKey('E1')).toBe('e1a')
  })
})
