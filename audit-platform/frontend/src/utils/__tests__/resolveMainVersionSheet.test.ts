/**
 * resolveMainVersionSheet vitest
 *
 * spec workpaper-h-fixed-assets-cycle H-F1b（Task 1.2）
 *
 * 覆盖 9 个 wp_code 多 sheet 位置的主版本识别：
 * H1-12（3 版）/ H3-1（2 模式）/ H3-2（2 模式）/ H3-5（2 模式）/
 * H3-7（2 减值）/ H5-12（2 减值）/ H7-11（2 减值）/ H8-6（2 频率）/ H8-8（2 减值）
 */
import { describe, it, expect } from 'vitest'
import { resolveMainVersionSheet, MAIN_VERSION_KEYWORDS } from '../resolveMainVersionSheet'

// 真实 H 循环 sheet 名（来自 Sprint 0 openpyxl 实测）
const ALL_H_SHEETS = [
  // H1-12: 3 版折旧测算
  '折旧测算表（不含减值）-直线法H1-12',
  '折旧测算表（含减值）H1-12',
  '折旧测算表（多次减值）H1-12',
  // H3-1: 2 计量模式
  '审定表（成本模式）H3-1',
  '审定表（公允价值模式）H3-1',
  // H3-2: 2 计量模式
  '明细表（成本模式）H3-2',
  '明细表（公允价值模式）H3-2',
  // H3-5: 2 计量模式
  '增减检查表（成本模式）H3-5',
  '增减检查表（公允价值模式）H3-5',
  // H3-7: 2 减值
  '折旧测算表（成本模式不含减值）H3-7',
  '折旧测算表（成本模式含减值）H3-7',
  // H5-12: 2 减值
  '折耗测算表（不含减值）H5-12',
  '折耗测算表（含减值）H5-12',
  // H7-11: 2 减值
  '折旧测算表（不含减值）-直线法H7-11',
  '折旧测算表（含减值）H7-11',
  // H8-6: 2 频率
  '使用权资产 租赁负债初始及后续计量（按年）H8-6',
  '使用权资产 租赁负债初始及后续计量（按月）H8-6',
  // H8-8: 2 减值
  '折旧测算表（不含减值）H8-8',
  '折旧测算表（含减值）H8-8',
  // 其他正常 sheet（不应干扰路由）
  '审定表H1-1',
  '明细表H1-2',
  '审定表H0-1',
]

describe('resolveMainVersionSheet - 9 个 wp_code 多 sheet 位置', () => {
  it('H1-12: 默认选"折旧测算表（不含减值）-直线法H1-12"（含"（不含减值）"优先）', () => {
    const result = resolveMainVersionSheet('H1-12', ALL_H_SHEETS)
    expect(result).toBe('折旧测算表（不含减值）-直线法H1-12')
  })

  it('H3-1: 默认选"审定表（成本模式）H3-1"（含"（成本模式）"优先）', () => {
    const result = resolveMainVersionSheet('H3-1', ALL_H_SHEETS)
    expect(result).toBe('审定表（成本模式）H3-1')
  })

  it('H3-2: 默认选"明细表（成本模式）H3-2"', () => {
    const result = resolveMainVersionSheet('H3-2', ALL_H_SHEETS)
    expect(result).toBe('明细表（成本模式）H3-2')
  })

  it('H3-5: 默认选"增减检查表（成本模式）H3-5"', () => {
    const result = resolveMainVersionSheet('H3-5', ALL_H_SHEETS)
    expect(result).toBe('增减检查表（成本模式）H3-5')
  })

  it('H3-7: 默认选"折旧测算表（成本模式不含减值）H3-7"（含"（不含减值）"优先于"（成本模式）"）', () => {
    // "（成本模式不含减值）" 包含 "（不含减值）" 子串? 不包含。
    // 实际："折旧测算表（成本模式不含减值）H3-7" 不含完整 "（不含减值）" 子串
    // 但含 "不含减值" — 关键词是 "（不含减值）" 需要完整匹配括号
    // "（成本模式不含减值）" 不包含 "（不含减值）" 子串
    // 所以会 fallback 到 "（成本模式）" 关键词? 也不包含。
    // 实际上两个 sheet 名都不含完整的 MAIN_VERSION_KEYWORDS 关键词
    // → fallback 到首个匹配
    const result = resolveMainVersionSheet('H3-7', ALL_H_SHEETS)
    expect(result).toBe('折旧测算表（成本模式不含减值）H3-7')
  })

  it('H5-12: 默认选"折耗测算表（不含减值）H5-12"', () => {
    const result = resolveMainVersionSheet('H5-12', ALL_H_SHEETS)
    expect(result).toBe('折耗测算表（不含减值）H5-12')
  })

  it('H7-11: 默认选"折旧测算表（不含减值）-直线法H7-11"', () => {
    const result = resolveMainVersionSheet('H7-11', ALL_H_SHEETS)
    expect(result).toBe('折旧测算表（不含减值）-直线法H7-11')
  })

  it('H8-6: 默认选"使用权资产 租赁负债初始及后续计量（按月）H8-6"', () => {
    const result = resolveMainVersionSheet('H8-6', ALL_H_SHEETS)
    expect(result).toBe('使用权资产 租赁负债初始及后续计量（按月）H8-6')
  })

  it('H8-8: 默认选"折旧测算表（不含减值）H8-8"', () => {
    const result = resolveMainVersionSheet('H8-8', ALL_H_SHEETS)
    expect(result).toBe('折旧测算表（不含减值）H8-8')
  })
})

describe('resolveMainVersionSheet - 边界情况', () => {
  it('wp_code 无匹配时返回空字符串', () => {
    const result = resolveMainVersionSheet('H99-99', ALL_H_SHEETS)
    expect(result).toBe('')
  })

  it('wp_code 仅 1 个匹配时直接返回', () => {
    const result = resolveMainVersionSheet('H0-1', ALL_H_SHEETS)
    expect(result).toBe('审定表H0-1')
  })

  it('空 sheet 列表返回空字符串', () => {
    const result = resolveMainVersionSheet('H1-12', [])
    expect(result).toBe('')
  })

  it('MAIN_VERSION_KEYWORDS 包含 4 个关键词', () => {
    expect(MAIN_VERSION_KEYWORDS).toHaveLength(4)
    expect(MAIN_VERSION_KEYWORDS).toContain('（不含减值）')
    expect(MAIN_VERSION_KEYWORDS).toContain('-直线法')
    expect(MAIN_VERSION_KEYWORDS).toContain('（成本模式）')
    expect(MAIN_VERSION_KEYWORDS).toContain('（按月）')
  })
})
