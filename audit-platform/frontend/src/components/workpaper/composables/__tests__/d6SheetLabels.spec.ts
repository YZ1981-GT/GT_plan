import { describe, it, expect } from 'vitest'
import { resolveD6SheetLabel } from '../d6SheetLabels'

describe('d6SheetLabels', () => {
  it('D6-1 默认名与 registry 一致', () => {
    expect(resolveD6SheetLabel('D6-1')).toBe('合同资产审定表D6-1')
  })

  it('D6A 程序表默认名', () => {
    expect(resolveD6SheetLabel('D6A')).toBe('实质性程序表D6A')
  })

  it('D6_INDEX_ROWS 共 13 行', async () => {
    const { D6_INDEX_ROWS } = await import('../d6SheetLabels')
    expect(D6_INDEX_ROWS).toHaveLength(13)
  })
})
