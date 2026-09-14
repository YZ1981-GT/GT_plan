/**
 * I4 长期待摊费用 — sheetName 分发逻辑 + 摊销分支选择器 测试
 * 提取 GtI4LongTermPrepaid.vue 的 currentSheet computed 正则逻辑，独立测试
 * Spec: .kiro/specs/i4-long-term-prepaid/ Task 7.2
 * Requirements: 1.2, 6.1-6.3
 */
import { describe, it, expect } from 'vitest'

/**
 * 从 GtI4LongTermPrepaid.vue 提取的 sheetName → currentSheet 分发逻辑
 * 保持与组件内 computed 一致
 */
function resolveCurrentSheet(sheetName: string): string {
  const name = sheetName || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'I4'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 I4A
  if (/I4A/.test(name)) return 'I4A'
  // I4-N 编码（I4-1 到 I4-7）
  const m = name.match(/(I4-\d+)/)
  if (m) return m[1]
  // 底稿目录 I4（无后缀）
  if (/\bI4\b/.test(name) && !/I4-/.test(name) && !/I4A/.test(name)) return 'I4'
  return ''
}

/**
 * 根据 currentSheet 决定摊销方法
 */
function resolveAmortizationMethod(currentSheet: string): 'straight' | 'units' {
  if (currentSheet === 'I4-7') return 'units'
  return 'straight'
}

// ═══════════════════════════════════════════════════════════════════════════════
// sheetName 分发测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('I4 sheetName 分发逻辑 (resolveCurrentSheet)', () => {
  it('"底稿目录" → "I4"', () => {
    expect(resolveCurrentSheet('底稿目录')).toBe('I4')
  })

  it('含 "I4A" → "I4A"', () => {
    expect(resolveCurrentSheet('长期待摊费用实质性程序表I4A')).toBe('I4A')
  })

  it('"I4-1 审定表" → "I4-1"', () => {
    expect(resolveCurrentSheet('审定表I4-1')).toBe('I4-1')
  })

  it('"I4-6 直线法" → "I4-6"', () => {
    expect(resolveCurrentSheet('摊销测算表I4-6直线法')).toBe('I4-6')
  })

  it('"附注上市" → "附注上市"', () => {
    expect(resolveCurrentSheet('附注披露信息（上市公司）')).toBe('附注上市')
  })

  it('"附注国企" → "附注国企"', () => {
    expect(resolveCurrentSheet('附注披露信息（国有企业）')).toBe('附注国企')
  })

  it('"I4-2 明细" → "I4-2"', () => {
    expect(resolveCurrentSheet('明细表I4-2')).toBe('I4-2')
  })

  it('"I4-7 工作量法" → "I4-7"', () => {
    expect(resolveCurrentSheet('摊销测算表I4-7工作量法')).toBe('I4-7')
  })

  it('无匹配 → 空字符串', () => {
    expect(resolveCurrentSheet('随机名称')).toBe('')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 摊销分支选择器测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('I4 摊销分支选择器', () => {
  it('currentSheet "I4-6" → amortizationMethod = "straight"', () => {
    expect(resolveAmortizationMethod('I4-6')).toBe('straight')
  })

  it('currentSheet "I4-7" → amortizationMethod = "units"', () => {
    expect(resolveAmortizationMethod('I4-7')).toBe('units')
  })

  it('其他 sheet 默认 → "straight"', () => {
    expect(resolveAmortizationMethod('I4-1')).toBe('straight')
  })
})
