import { describe, it, expect } from 'vitest'
import { newRowId, migrateRowIds, type D4CustomerRow } from './d4CustomerRowIdentity'

describe('d4-9 客户行稳定身份（Task 2 / Requirement 3）', () => {
  it('newRowId 每次返回不同的非空字符串', () => {
    const ids = new Set(Array.from({ length: 200 }, () => newRowId()))
    expect(ids.size).toBe(200)
    for (const id of ids) expect(typeof id).toBe('string')
  })

  it('历史数据（无 rowId）补齐 rowId 且不丢既有手工值', () => {
    const legacy = [
      { name: '客户甲', amount: 1000, quantity: 5, priorRank: '2' },
      { name: '客户乙', amount: 2000, quantity: 8, priorRank: '1' },
    ] as unknown as Partial<D4CustomerRow>[]
    const { rows, changed } = migrateRowIds(legacy)
    expect(changed).toBe(true)
    expect(rows).toHaveLength(2)
    expect(rows[0].rowId).toBeTruthy()
    expect(rows[1].rowId).toBeTruthy()
    expect(rows[0].rowId).not.toBe(rows[1].rowId)
    // 手工值原样保留。
    expect(rows[0].name).toBe('客户甲')
    expect(rows[0].amount).toBe(1000)
    expect(rows[1].priorRank).toBe('1')
  })

  it('已有唯一 rowId 时不改动、不标记 changed', () => {
    const existing = [
      { rowId: 'a', name: '甲', amount: 1, quantity: 1, priorRank: '' },
      { rowId: 'b', name: '乙', amount: 2, quantity: 2, priorRank: '' },
    ]
    const { rows, changed } = migrateRowIds(existing)
    expect(changed).toBe(false)
    expect(rows[0].rowId).toBe('a')
    expect(rows[1].rowId).toBe('b')
  })

  it('重复 rowId 被重新分配（不静默合并、不退回下标）', () => {
    const dup = [
      { rowId: 'x', name: '甲', amount: 1, quantity: 1, priorRank: '' },
      { rowId: 'x', name: '乙', amount: 2, quantity: 2, priorRank: '' },
    ]
    const { rows, changed } = migrateRowIds(dup)
    expect(changed).toBe(true)
    expect(rows[0].rowId).not.toBe(rows[1].rowId)
    // 值不丢。
    expect(rows[1].name).toBe('乙')
  })

  it('空/undefined 输入返回空数组、不报错', () => {
    expect(migrateRowIds(null).rows).toEqual([])
    expect(migrateRowIds(undefined).changed).toBe(false)
    expect(migrateRowIds([]).rows).toEqual([])
  })

  it('区域内 rowId 唯一（对一批含缺失+重复的混合行）', () => {
    const mixed = [
      { rowId: '', name: 'a', amount: 0, quantity: 0, priorRank: '' },
      { rowId: 'k', name: 'b', amount: 0, quantity: 0, priorRank: '' },
      { rowId: 'k', name: 'c', amount: 0, quantity: 0, priorRank: '' },
      { name: 'd', amount: 0, quantity: 0, priorRank: '' },
    ] as unknown as Partial<D4CustomerRow>[]
    const { rows } = migrateRowIds(mixed)
    const ids = rows.map((r) => r.rowId)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
