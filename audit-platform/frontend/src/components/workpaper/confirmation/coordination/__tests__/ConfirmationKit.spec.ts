/**
 * ConfirmationKit.spec.ts — 共享 UI 工具单元测试
 *
 * 覆盖：
 * - 金额格式化（千分位/小数/零值/负数）
 * - 数据来源标识
 */
import { describe, it, expect } from 'vitest'
import {
  formatAmount,
  getSourceIndicator,
  GRID_PALETTE,
} from '../ConfirmationKit'

describe('ConfirmationKit — 共享 UI 工具', () => {
  // ─── 金额格式化 ────────────────────────────────────────────────────────────

  describe('formatAmount()', () => {
    it('正常金额千分位', () => {
      expect(formatAmount(1234567.89)).toBe('1,234,567.89')
    })

    it('小金额保留 2 位小数', () => {
      expect(formatAmount(42.1)).toBe('42.10')
    })

    it('负数带负号', () => {
      expect(formatAmount(-1500.5)).toBe('-1,500.50')
    })

    it('零值默认显示 0.00', () => {
      expect(formatAmount(0)).toBe('0.00')
    })

    it('零值 dash 模式', () => {
      expect(formatAmount(0, { zeroDisplay: 'dash' })).toBe('—')
    })

    it('零值 empty 模式', () => {
      expect(formatAmount(0, { zeroDisplay: 'empty' })).toBe('')
    })

    it('null 值默认 0.00', () => {
      expect(formatAmount(null)).toBe('0.00')
    })

    it('null 值 dash 模式', () => {
      expect(formatAmount(null, { zeroDisplay: 'dash' })).toBe('—')
    })

    it('undefined 值 empty 模式', () => {
      expect(formatAmount(undefined, { zeroDisplay: 'empty' })).toBe('')
    })

    it('自定义小数位', () => {
      expect(formatAmount(1234.5678, { decimals: 4 })).toBe('1,234.5678')
    })

    it('单位后缀', () => {
      expect(formatAmount(100, { unit: '元' })).toBe('100.00元')
    })

    it('无分隔符', () => {
      expect(formatAmount(1234567, { separator: false })).toBe('1234567.00')
    })
  })

  // ─── 数据来源标识 ──────────────────────────────────────────────────────────

  describe('getSourceIndicator()', () => {
    it('auto 为蓝色', () => {
      const ind = getSourceIndicator('auto')
      expect(ind.color).toBe('#409EFF')
      expect(ind.label).toBe('自动')
    })

    it('manual 为灰色', () => {
      const ind = getSourceIndicator('manual')
      expect(ind.color).toBe('#909399')
    })

    it('import 为绿色', () => {
      const ind = getSourceIndicator('import')
      expect(ind.color).toBe('#67C23A')
    })

    it('undefined 默认 manual', () => {
      const ind = getSourceIndicator(undefined)
      expect(ind.label).toBe('手工')
    })
  })

  // ─── 网格调色板 ────────────────────────────────────────────────────────────

  describe('GRID_PALETTE', () => {
    it('5 色表头轮转', () => {
      expect(GRID_PALETTE.headerColors).toHaveLength(5)
    })

    it('所有色值为合法 hex', () => {
      const allColors = [
        ...GRID_PALETTE.headerColors,
        GRID_PALETTE.zebraOdd,
        GRID_PALETTE.zebraEven,
        GRID_PALETTE.frozenCol,
        GRID_PALETTE.selectedRow,
        GRID_PALETTE.dangerRow,
      ]
      for (const c of allColors) {
        expect(c).toMatch(/^#[0-9A-Fa-f]{6}$/)
      }
    })
  })
})
