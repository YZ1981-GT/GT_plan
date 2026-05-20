/**
 * resolveProcedureSheetKey vitest — J 循环路由
 *
 * spec workpaper-j-payroll-cycle J-F9（Task 2.8）
 * 路由：J1→j1a / J2→j2a / J3→j3a
 */
import { describe, it, expect } from 'vitest'
import { resolveProcedureSheetKey } from '../resolveProcedureSheetKey'

describe('resolveProcedureSheetKey - J 循环路由 (J-F9 Task 2.8)', () => {
  it('J1 → j1a', () => {
    expect(resolveProcedureSheetKey('J1')).toBe('j1a')
  })

  it('J1-2 → j1a（子表路由到 J1）', () => {
    expect(resolveProcedureSheetKey('J1-2')).toBe('j1a')
  })

  it('J1-6 → j1a（计提情况检查表）', () => {
    expect(resolveProcedureSheetKey('J1-6')).toBe('j1a')
  })

  it('J1-7 → j1a（分配情况检查表）', () => {
    expect(resolveProcedureSheetKey('J1-7')).toBe('j1a')
  })

  it('J1-10 → j1a（辞退福利）', () => {
    expect(resolveProcedureSheetKey('J1-10')).toBe('j1a')
  })

  it('J2 → j2a', () => {
    expect(resolveProcedureSheetKey('J2')).toBe('j2a')
  })

  it('J2-2 → j2a（长期应付职工薪酬明细）', () => {
    expect(resolveProcedureSheetKey('J2-2')).toBe('j2a')
  })

  it('J3 → j3a', () => {
    expect(resolveProcedureSheetKey('J3')).toBe('j3a')
  })

  it('J3-2 → j3a（股份支付检查表）', () => {
    expect(resolveProcedureSheetKey('J3-2')).toBe('j3a')
  })

  it('大小写不敏感：j1 → j1a', () => {
    expect(resolveProcedureSheetKey('j1')).toBe('j1a')
  })

  it('大小写不敏感：j3-2 → j3a', () => {
    expect(resolveProcedureSheetKey('j3-2')).toBe('j3a')
  })
})

describe('resolveProcedureSheetKey - J 循环不影响其他循环回归', () => {
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

  it('I1 → i1a（I 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('I1')).toBe('i1a')
  })

  it('E1 → e1a（默认 fallback）', () => {
    expect(resolveProcedureSheetKey('E1')).toBe('e1a')
  })
})
