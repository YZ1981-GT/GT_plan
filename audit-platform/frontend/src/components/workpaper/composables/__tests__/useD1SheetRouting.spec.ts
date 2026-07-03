import { describe, it, expect } from 'vitest'
import { resolveD1SheetCode } from '../useD1SheetRouting'

describe('resolveD1SheetCode', () => {
  it('附注披露（上市公司）→ disclosure-listed', () => {
    expect(resolveD1SheetCode('附注披露信息（上市公司）')).toBe('disclosure-listed')
  })

  it('附注披露（国企）→ disclosure-soe', () => {
    expect(resolveD1SheetCode('附注披露信息（国企）')).toBe('disclosure-soe')
  })

  it('尾部编码优先于模糊关键字', () => {
    expect(resolveD1SheetCode('审定表D1-1')).toBe('D1-1')
    expect(resolveD1SheetCode('应收票据坏账准备测试表D1-15')).toBe('D1-15')
  })

  it('业务模式分析提示不误路由到 D1-6', () => {
    expect(resolveD1SheetCode('应收票据业务模式分析提示')).toBe('')
  })

  it('D1-6 业务模式分析表正常路由', () => {
    expect(resolveD1SheetCode('应收票据业务模式分析D1-6')).toBe('D1-6')
  })
})
