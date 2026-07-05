import { describe, it, expect } from 'vitest'
import { resolveD7SheetLabel } from '../d7SheetLabels'

describe('d7SheetLabels', () => {
  it('D7-1 默认名与 registry 一致', () => {
    expect(resolveD7SheetLabel('D7-1')).toBe('合同负债审定表D7-1')
  })

  it('D7A 程序表默认名', () => {
    expect(resolveD7SheetLabel('D7A')).toBe('合同负债审计程序表D7A')
  })

  it('D7_INDEX_ROWS 共 11 行', async () => {
    const { D7_INDEX_ROWS } = await import('../d7SheetLabels')
    expect(D7_INDEX_ROWS).toHaveLength(11)
  })
})
