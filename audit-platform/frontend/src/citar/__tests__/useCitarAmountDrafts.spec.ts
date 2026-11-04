/**
 * 报表金额格草稿（spec citar-table-manual-edit R6 / R7）：改、清空、恢复已保存的手工值、恢复后再改。
 */
import { describe, expect, it } from 'vitest'
import { useCitarAmountDrafts } from '../useCitarAmountDrafts'

describe('useCitarAmountDrafts', () => {
  it('草稿与恢复计数、恢复后再改去掉恢复标记', () => {
    const d = useCitarAmountDrafts()
    d.edit('a', 10)
    d.edit('b', null)
    expect(d.draftOf('a')).toBe(10)
    expect(d.draftOf('b')).toBeNull()
    expect(d.draftOf('c')).toBeUndefined()
    d.restore('c', true)
    expect(d.isRestored('c')).toBe(true)
    expect(d.count.value).toBe(3)
    d.edit('c', 5)
    expect(d.isRestored('c')).toBe(false)
    expect(d.count.value).toBe(3)
  })

  it('没保存过的格恢复 = 只去掉草稿', () => {
    const d = useCitarAmountDrafts()
    d.edit('a', 1)
    d.restore('a', false)
    expect(d.dirty.value).toBe(false)
    d.restore('x', true)
    d.clear()
    expect(d.dirty.value).toBe(false)
  })
})
