/**
 * resolveProcedureSheetKey vitest — M 循环路由
 *
 * spec workpaper-m-equity-cycle M-F5（Task 2.4）
 * M2→m2a / M4→m4a / M5→m5a / M6→m6a / M9→m9a / M10→m10a
 */
import { describe, it, expect } from 'vitest'
import { resolveProcedureSheetKey } from '../resolveProcedureSheetKey'

describe('resolveProcedureSheetKey - M 循环路由 (M-F5 Task 2.4)', () => {
  it('M2 → m2a', () => {
    expect(resolveProcedureSheetKey('M2')).toBe('m2a')
  })

  it('M2-2 → m2a（子表路由到 M2）', () => {
    expect(resolveProcedureSheetKey('M2-2')).toBe('m2a')
  })

  it('M4 → m4a', () => {
    expect(resolveProcedureSheetKey('M4')).toBe('m4a')
  })

  it('M4-2 → m4a（明细表路由到 M4）', () => {
    expect(resolveProcedureSheetKey('M4-2')).toBe('m4a')
  })

  it('M5 → m5a', () => {
    expect(resolveProcedureSheetKey('M5')).toBe('m5a')
  })

  it('M5-2 → m5a（明细表路由到 M5）', () => {
    expect(resolveProcedureSheetKey('M5-2')).toBe('m5a')
  })

  it('M6 → m6a', () => {
    expect(resolveProcedureSheetKey('M6')).toBe('m6a')
  })

  it('M6-2 → m6a（变动分析表路由到 M6）', () => {
    expect(resolveProcedureSheetKey('M6-2')).toBe('m6a')
  })

  it('M9 → m9a', () => {
    expect(resolveProcedureSheetKey('M9')).toBe('m9a')
  })

  it('M9-2 → m9a（明细表路由到 M9）', () => {
    expect(resolveProcedureSheetKey('M9-2')).toBe('m9a')
  })

  it('M10 → m10a（M10 必须在 M1 之前判断避免误匹配）', () => {
    expect(resolveProcedureSheetKey('M10')).toBe('m10a')
  })

  it('M10-2 → m10a（子表路由到 M10）', () => {
    expect(resolveProcedureSheetKey('M10-2')).toBe('m10a')
  })

  it('大小写不敏感：m2 → m2a', () => {
    expect(resolveProcedureSheetKey('m2')).toBe('m2a')
  })

  it('大小写不敏感：m6-2 → m6a', () => {
    expect(resolveProcedureSheetKey('m6-2')).toBe('m6a')
  })

  it('大小写不敏感：m10 → m10a', () => {
    expect(resolveProcedureSheetKey('m10')).toBe('m10a')
  })

  // M1/M3/M7/M8 无专属程序表，fallback 到 e1a
  it('M1 → e1a（应付股利无专属程序表，fallback）', () => {
    expect(resolveProcedureSheetKey('M1')).toBe('e1a')
  })

  it('M3 → e1a（库存股无专属程序表，fallback）', () => {
    expect(resolveProcedureSheetKey('M3')).toBe('e1a')
  })

  it('M7 → e1a（专项储备无专属程序表，fallback）', () => {
    expect(resolveProcedureSheetKey('M7')).toBe('e1a')
  })

  it('M8 → e1a（一般风险准备无专属程序表，fallback）', () => {
    expect(resolveProcedureSheetKey('M8')).toBe('e1a')
  })
})

describe('resolveProcedureSheetKey - M 循环不影响其他循环回归', () => {
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

  it('L1 → l1a（L 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('L1')).toBe('l1a')
  })

  it('K8 → k8a（K 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('K8')).toBe('k8a')
  })

  it('J1 → j1a（J 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('J1')).toBe('j1a')
  })

  it('I1 → i1a（I 循环不受影响）', () => {
    expect(resolveProcedureSheetKey('I1')).toBe('i1a')
  })
})
