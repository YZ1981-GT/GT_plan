import { describe, expect, it } from 'vitest'
import { isG9AccountCode, g9AccountLabel, g9DefaultAccountCode } from '../g9AccountMatch'

describe('g9AccountMatch', () => {
  it('isG9AccountCode 识别别名前缀', () => {
    expect(isG9AccountCode('1519')).toBe(true)
    expect(isG9AccountCode('151901')).toBe(true)
    expect(isG9AccountCode('1504')).toBe(true)
    expect(isG9AccountCode('1510')).toBe(true)
    expect(isG9AccountCode('1511')).toBe(false)
  })

  it('g9DefaultAccountCode 为 1519', () => {
    expect(g9DefaultAccountCode()).toBe('1519')
  })

  it('g9AccountLabel 展示解析码', () => {
    expect(g9AccountLabel('1519')).toContain('1519')
    expect(g9AccountLabel(null)).toContain('1519')
  })
})
