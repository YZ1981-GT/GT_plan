import { describe, it, expect } from 'vitest'
import { resolveD5SheetLabel } from '../d5SheetLabels'

describe('d5SheetLabels', () => {
  it('D5-1 默认名与 registry 一致', () => {
    expect(resolveD5SheetLabel('D5-1')).toBe('应收款项融资审定表D5-1')
  })

  it('D5A 程序表默认名', () => {
    expect(resolveD5SheetLabel('D5A')).toBe('应收款项融资审计程序表D5A')
  })
})
