import { describe, it, expect } from 'vitest'
import {
  G6_REPORT_ROW_CODE,
  G6_GROSS_FALLBACK_STANDARD,
  g6GrossQueryCodes,
  g6AccountCode,
} from '../g6AccountScope'

describe('g6AccountScope', () => {
  // ─── 常量 ───────────────────────────────────────────────────────────
  it('G6_REPORT_ROW_CODE is BS-022', () => {
    expect(G6_REPORT_ROW_CODE).toBe('BS-022')
  })

  it('G6_GROSS_FALLBACK_STANDARD is 1505', () => {
    expect(G6_GROSS_FALLBACK_STANDARD).toBe('1505')
  })

  // ─── g6GrossQueryCodes ──────────────────────────────────────────────
  describe('g6GrossQueryCodes', () => {
    it('运行态优先：取 render 下发的 gross_standard', () => {
      const src = { gross_standard: ['1505'], resolved_from: 'report_config' as const }
      expect(g6GrossQueryCodes(src)).toEqual(['1505'])
    })

    it('多科目码时全量返回', () => {
      const src = { gross_standard: ['1505', '1505.01'], resolved_from: 'report_config' as const }
      expect(g6GrossQueryCodes(src)).toEqual(['1505', '1505.01'])
    })

    it('空数组时回退兜底码', () => {
      const src = { gross_standard: [], resolved_from: 'fallback' as const }
      expect(g6GrossQueryCodes(src)).toEqual(['1505'])
    })

    it('null 时回退兜底码', () => {
      expect(g6GrossQueryCodes(null)).toEqual(['1505'])
    })

    it('undefined 时回退兜底码', () => {
      expect(g6GrossQueryCodes(undefined)).toEqual(['1505'])
    })
  })

  // ─── g6AccountCode ─────────────────────────────────────────────────
  describe('g6AccountCode', () => {
    it('有 render 数据时取首个', () => {
      const src = { gross_standard: ['1505'], resolved_from: 'report_config' as const }
      expect(g6AccountCode(src)).toBe('1505')
    })

    it('空时回退', () => {
      expect(g6AccountCode(null)).toBe('1505')
    })
  })

  // ─── 反向自检：禁止旧科目码 ─────────────────────────────────────────
  it('常量不含已废止科目码 1503/1510/1531', () => {
    const forbidden = ['1503', '1510', '1531']
    for (const code of forbidden) {
      expect(G6_GROSS_FALLBACK_STANDARD).not.toBe(code)
    }
  })
})
