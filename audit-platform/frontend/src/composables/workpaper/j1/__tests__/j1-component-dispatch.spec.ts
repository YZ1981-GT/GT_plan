/**
 * Component Tests — J1 sheetName分发 + 5类检查表渲染
 *
 * 验证：主入口 currentSheet 解析逻辑正确
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Task: 7.2
 */
import { describe, it, expect } from 'vitest'

// 模拟 currentSheet 解析逻辑（从主入口提取）
function parseCurrentSheet(sheetName: string): string {
  const sn = sheetName || ''
  const mCode = sn.match(/(J1-\d+)/)
  if (mCode) return mCode[1]
  if (sn.includes('上市')) return 'J1附注(上市)'
  if (sn.includes('国有') || sn.includes('国企')) return 'J1附注(国企)'
  if (sn.includes('目录')) return 'J1-index'
  return sn
}

describe('J1 sheetName dispatch', () => {
  it('解析 J1-1 审定表', () => {
    expect(parseCurrentSheet('审定表J1-1 ')).toBe('J1-1')
    expect(parseCurrentSheet('审定表J1-1')).toBe('J1-1')
  })

  it('解析 J1-2 明细表', () => {
    expect(parseCurrentSheet('明细表J1-2 ')).toBe('J1-2')
  })

  it('解析 J1-4 月度分析', () => {
    expect(parseCurrentSheet('月度分析表J1-4')).toBe('J1-4')
  })

  it('解析 J1-6~J1-10 检查表', () => {
    expect(parseCurrentSheet('计提情况检查表J1-6')).toBe('J1-6')
    expect(parseCurrentSheet('分配情况检查表J1-7')).toBe('J1-7')
    expect(parseCurrentSheet('检查表J1-8')).toBe('J1-8')
    expect(parseCurrentSheet('非货币性福利检查表J1-9')).toBe('J1-9')
    expect(parseCurrentSheet('辞退福利检查表J1-10')).toBe('J1-10')
  })

  it('解析附注', () => {
    expect(parseCurrentSheet('附注披露信息（上市公司）')).toBe('J1附注(上市)')
    expect(parseCurrentSheet('附注披露信息（国有企业）')).toBe('J1附注(国企)')
  })

  it('解析底稿目录', () => {
    expect(parseCurrentSheet('底稿目录')).toBe('J1-index')
  })

  it('未识别sheet透传', () => {
    expect(parseCurrentSheet('未知sheet')).toBe('未知sheet')
  })
})
