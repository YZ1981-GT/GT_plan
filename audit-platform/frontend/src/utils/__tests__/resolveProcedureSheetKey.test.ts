/**
 * resolveProcedureSheetKey vitest
 *
 * spec workpaper-h-fixed-assets-cycle H-F13（Task 3.6）
 *
 * 验证 H 循环路由 H1→h1a / H2→h2a / H3→h3a / H8→h8a / H9→h9a
 * + 既有 D/F/E1 路由回归
 */
import { describe, it, expect } from 'vitest'
import { resolveProcedureSheetKey } from '../resolveProcedureSheetKey'

describe('resolveProcedureSheetKey — H 循环路由', () => {
  it('H1 → h1a', () => {
    expect(resolveProcedureSheetKey('H1')).toBe('h1a')
  })

  it('H1-12 → h1a（子表也路由到 H1）', () => {
    expect(resolveProcedureSheetKey('H1-12')).toBe('h1a')
  })

  it('H2 → h2a', () => {
    expect(resolveProcedureSheetKey('H2')).toBe('h2a')
  })

  it('H2-5 → h2a', () => {
    expect(resolveProcedureSheetKey('H2-5')).toBe('h2a')
  })

  it('H3 → h3a', () => {
    expect(resolveProcedureSheetKey('H3')).toBe('h3a')
  })

  it('H3-7 → h3a', () => {
    expect(resolveProcedureSheetKey('H3-7')).toBe('h3a')
  })

  it('H8 → h8a', () => {
    expect(resolveProcedureSheetKey('H8')).toBe('h8a')
  })

  it('H8-8 → h8a', () => {
    expect(resolveProcedureSheetKey('H8-8')).toBe('h8a')
  })

  it('H9 → h9a', () => {
    expect(resolveProcedureSheetKey('H9')).toBe('h9a')
  })

  it('H9-2 → h9a', () => {
    expect(resolveProcedureSheetKey('H9-2')).toBe('h9a')
  })
})

describe('resolveProcedureSheetKey — H 循环无专属路由的子循环 fallback', () => {
  // H0/H4/H5/H6/H7/H10 没有专属 procedure sheet，走默认 e1a
  it('H0 → e1a（无专属路由，fallback 默认）', () => {
    expect(resolveProcedureSheetKey('H0')).toBe('e1a')
  })

  it('H4 → e1a', () => {
    expect(resolveProcedureSheetKey('H4')).toBe('e1a')
  })

  it('H5 → e1a', () => {
    expect(resolveProcedureSheetKey('H5')).toBe('e1a')
  })

  it('H6 → e1a', () => {
    expect(resolveProcedureSheetKey('H6')).toBe('e1a')
  })

  it('H7 → e1a', () => {
    expect(resolveProcedureSheetKey('H7')).toBe('e1a')
  })

  it('H10 → e1a', () => {
    expect(resolveProcedureSheetKey('H10')).toBe('e1a')
  })
})

describe('resolveProcedureSheetKey — D/F/E1 回归', () => {
  it('F2 → f2a', () => {
    expect(resolveProcedureSheetKey('F2')).toBe('f2a')
  })

  it('F2-1 → f2a', () => {
    expect(resolveProcedureSheetKey('F2-1')).toBe('f2a')
  })

  it('F1 → f1a', () => {
    expect(resolveProcedureSheetKey('F1')).toBe('f1a')
  })

  it('F3 → f3a', () => {
    expect(resolveProcedureSheetKey('F3')).toBe('f3a')
  })

  it('F4 → f4a', () => {
    expect(resolveProcedureSheetKey('F4')).toBe('f4a')
  })

  it('F5 → f5a', () => {
    expect(resolveProcedureSheetKey('F5')).toBe('f5a')
  })

  it('D4 → d4a', () => {
    expect(resolveProcedureSheetKey('D4')).toBe('d4a')
  })

  it('D2 → d2a', () => {
    expect(resolveProcedureSheetKey('D2')).toBe('d2a')
  })

  it('E1 → e1a（默认）', () => {
    expect(resolveProcedureSheetKey('E1')).toBe('e1a')
  })

  it('空字符串 → e1a', () => {
    expect(resolveProcedureSheetKey('')).toBe('e1a')
  })

  it('大小写不敏感：h1 → h1a', () => {
    expect(resolveProcedureSheetKey('h1')).toBe('h1a')
  })

  it('大小写不敏感：h8-6 → h8a', () => {
    expect(resolveProcedureSheetKey('h8-6')).toBe('h8a')
  })
})
