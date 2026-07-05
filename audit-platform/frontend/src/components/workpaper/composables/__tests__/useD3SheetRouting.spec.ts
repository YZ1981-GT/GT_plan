import { describe, it, expect } from 'vitest'
import { resolveD3SheetCode } from '../useD3SheetRouting'

describe('resolveD3SheetCode', () => {
  it('D3 主入口', () => {
    expect(resolveD3SheetCode('D3')).toBe('D3')
    expect(resolveD3SheetCode('预收账款D3')).toBe('D3')
  })

  it('尾部编码优先', () => {
    expect(resolveD3SheetCode('预收账款审定表D3-1')).toBe('D3-1')
    expect(resolveD3SheetCode('预收账款明细表D3-2')).toBe('D3-2')
    expect(resolveD3SheetCode('预收账款审计程序表D3A')).toBe('D3A')
  })

  it('附注披露路由', () => {
    expect(resolveD3SheetCode('附注披露信息（上市公司）')).toBe('附注上市')
    expect(resolveD3SheetCode('附注披露信息（国企）')).toBe('附注国企')
  })

  it('模糊关键字兜底', () => {
    expect(resolveD3SheetCode('账龄1年以上检查表')).toBe('D3-5')
    expect(resolveD3SheetCode('关联关系及交易检查表')).toBe('D3-6')
  })
})
