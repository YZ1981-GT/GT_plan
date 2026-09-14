import { describe, it, expect } from 'vitest'
import { resolveD4SheetLabel } from '../d4SheetLabels'

describe('d4SheetLabels', () => {
  it('D4-1 默认名与模板一致', () => {
    expect(resolveD4SheetLabel('D4-1')).toBe('营业收入审定表D4-1')
  })

  it('访谈模板编码解析', () => {
    expect(resolveD4SheetLabel('D4-访谈模板')).toBe('访谈记录与核对示例')
  })
})
