import { describe, it, expect } from 'vitest'
import { normalizeSheetName } from '../normalizeSheetName'

describe('normalizeSheetName', () => {
  it('全角括号→半角：上市公司', () => {
    expect(normalizeSheetName('附注披露信息（上市公司）'))
      .toBe(normalizeSheetName('附注披露信息(上市公司)'))
  })

  it('D6 混合括号：半角左+全角右', () => {
    expect(normalizeSheetName('附注披露信息(上市公司）'))
      .toBe(normalizeSheetName('附注披露信息(上市公司)'))
  })

  it('不误伤不同字的内容', () => {
    expect(normalizeSheetName('附注披露信息(上市公司)'))
      .not.toBe(normalizeSheetName('附注披露信息(国企)'))
  })

  it('不改数字/中文/汉字/顿号', () => {
    const input = '五、1 审定表K3-1'
    const result = normalizeSheetName(input)
    expect(result).toContain('五、1')
    expect(result).toContain('审定表K3-1')
  })

  it('幂等：normalize(normalize(x)) === normalize(x)', () => {
    const input = '附注披露信息（上市公司）  备注'
    expect(normalizeSheetName(normalizeSheetName(input)))
      .toBe(normalizeSheetName(input))
  })

  it('全角逗号/冒号/分号折叠', () => {
    expect(normalizeSheetName('测试，数据：项目；结果'))
      .toBe('测试,数据:项目;结果')
  })

  it('多空白合并+全角空格', () => {
    expect(normalizeSheetName('审定表\u3000K3-1  审计'))
      .toBe('审定表 K3-1 审计')
  })

  it('空字符串返回空', () => {
    expect(normalizeSheetName('')).toBe('')
  })

  it('trim 首尾空白', () => {
    expect(normalizeSheetName('  审定表K3-1  ')).toBe('审定表K3-1')
  })
})
