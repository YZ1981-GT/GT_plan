import { describe, it, expect } from 'vitest'
import { normalizeSheetName, resolveSheetNameByDeepLink } from '../normalizeSheetName'

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

describe('resolveSheetNameByDeepLink（?sheet= 深链解析）', () => {
  // render-config 下发的 sheet_name **带科目前缀 + 全角括号**（实测 D6）
  const D6_SHEETS = [
    '底稿目录',
    '实质性程序表D6A',
    '合同资产审定表D6-1',
    '合同资产附注披露信息（上市公司）',
    '合同资产附注披露信息（国企）',
  ]

  it('原样精确命中', () => {
    expect(resolveSheetNameByDeepLink(D6_SHEETS, '底稿目录')).toBe('底稿目录')
  })

  it('🔴 附注传源 xlsx tab 名（无科目前缀 + 半角左括号）也要命中', () => {
    // 修复前：第 3 级用未归一原串做 endsWith → 全角「（」vs 半角「(」落空 → 回退底稿目录
    expect(resolveSheetNameByDeepLink(D6_SHEETS, '附注披露信息(上市公司）'))
      .toBe('合同资产附注披露信息（上市公司）')
    expect(resolveSheetNameByDeepLink(D6_SHEETS, '附注披露信息（国企）'))
      .toBe('合同资产附注披露信息（国企）')
  })

  it('上市 / 国企不得互相串台', () => {
    expect(resolveSheetNameByDeepLink(D6_SHEETS, '附注披露信息(上市公司)'))
      .not.toContain('国企')
    expect(resolveSheetNameByDeepLink(D6_SHEETS, '附注披露信息(国企)'))
      .not.toContain('上市')
  })

  it('底稿编码兜底仍可用（来源底稿跳转只知编码）', () => {
    expect(resolveSheetNameByDeepLink(D6_SHEETS, 'D6-1')).toBe('合同资产审定表D6-1')
    expect(resolveSheetNameByDeepLink(D6_SHEETS, 'D6A')).toBe('实质性程序表D6A')
  })

  it('归一优先于后缀：完整名存在时不被前缀名抢走', () => {
    const sheets = ['附注披露信息(上市公司)', '合同资产附注披露信息（上市公司）']
    expect(resolveSheetNameByDeepLink(sheets, '附注披露信息（上市公司）'))
      .toBe('附注披露信息(上市公司)')
  })

  it('未命中返回 null（调用方据此回退首个 sheet）', () => {
    expect(resolveSheetNameByDeepLink(D6_SHEETS, '不存在的表')).toBeNull()
    expect(resolveSheetNameByDeepLink(D6_SHEETS, '')).toBeNull()
    expect(resolveSheetNameByDeepLink(D6_SHEETS, undefined)).toBeNull()
    expect(resolveSheetNameByDeepLink([], 'D6-1')).toBeNull()
  })
})
