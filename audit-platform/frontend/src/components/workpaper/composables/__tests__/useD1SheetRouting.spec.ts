import { describe, it, expect } from 'vitest'
import { resolveD1SheetCode } from '../useD1SheetRouting'

describe('resolveD1SheetCode', () => {
  it('附注披露（上市公司）→ 附注上市', () => {
    expect(resolveD1SheetCode('附注披露信息（上市公司）')).toBe('附注上市')
  })

  it('附注披露（国企）→ 附注国企', () => {
    expect(resolveD1SheetCode('附注披露信息（国企）')).toBe('附注国企')
  })

  it('尾部编码优先于模糊关键字', () => {
    expect(resolveD1SheetCode('审定表D1-1')).toBe('D1-1')
    expect(resolveD1SheetCode('应收票据坏账准备测试表D1-15')).toBe('D1-15')
  })

  it('业务模式分析提示路由到 analysis-hint（OnlyOffice）', () => {
    expect(resolveD1SheetCode('应收票据业务模式分析提示')).toBe('analysis-hint')
  })

  it('D1-6 业务模式分析表正常路由', () => {
    expect(resolveD1SheetCode('应收票据业务模式分析D1-6')).toBe('D1-6')
  })
})
