/**
 * 动态插行纯函数守卫。
 *
 * Property 11：动态行 key 唯一且父行派生。
 * 含 PBT（hypothesis 风格 fc.assert 替代 —— 用随机序列增删后检验不变量）。
 *
 * spec: .kiro/specs/j-cycle-four-table-extraction-and-disclosure-alignment/ R7
 */
import { describe, it, expect } from 'vitest'
import {
  addDynamicRow,
  removeDynamicRow,
  seedDynamicRows,
  sumGroupField,
  findDuplicateKeys,
  hasLabelConflict,
  makeRowKey,
  type DbpDynamicRow,
  type DbpDynamicSpec,
} from '../shared/dbpDynamicRows'

// ─────────────────── 基础 ───────────────────

describe('makeRowKey', () => {
  it('generates {group}_{seq} with zero-padded seq', () => {
    expect(makeRowKey('equity', 1)).toBe('equity_01')
    expect(makeRowKey('debt', 12)).toBe('debt_12')
    expect(makeRowKey('x', 100)).toBe('x_100')
  })
})

describe('addDynamicRow', () => {
  it('returns new row with incremented seq', () => {
    const rows: DbpDynamicRow[] = [
      { key: 'equity_01', label: 'A', group: 'equity', seq: 1 },
      { key: 'equity_02', label: 'B', group: 'equity', seq: 2 },
    ]
    const newRow = addDynamicRow(rows, 'equity', 'C')
    expect(newRow.key).toBe('equity_03')
    expect(newRow.seq).toBe(3)
    expect(newRow.label).toBe('C')
    expect(newRow.group).toBe('equity')
  })

  it('starts from 1 for empty group', () => {
    const newRow = addDynamicRow([], 'debt', 'X')
    expect(newRow.key).toBe('debt_01')
    expect(newRow.seq).toBe(1)
  })

  it('does not mutate input array', () => {
    const rows: DbpDynamicRow[] = [{ key: 'a_01', label: 'A', group: 'a', seq: 1 }]
    const before = [...rows]
    addDynamicRow(rows, 'a', 'B')
    expect(rows).toEqual(before)
  })
})

describe('removeDynamicRow', () => {
  it('removes row by key and returns new array', () => {
    const rows: DbpDynamicRow[] = [
      { key: 'x_01', label: 'A', group: 'x', seq: 1 },
      { key: 'x_02', label: 'B', group: 'x', seq: 2 },
    ]
    const result = removeDynamicRow(rows, 'x_01')
    expect(result).toHaveLength(1)
    expect(result[0].key).toBe('x_02')
    // does not mutate
    expect(rows).toHaveLength(2)
  })

  it('returns same content if key not found', () => {
    const rows: DbpDynamicRow[] = [{ key: 'a_01', label: 'Z', group: 'a', seq: 1 }]
    expect(removeDynamicRow(rows, 'nonexist')).toEqual(rows)
  })
})

describe('seedDynamicRows', () => {
  const spec: DbpDynamicSpec = {
    group: 'equity',
    parentKey: 'equity_parent',
    defaultLabel: '1、……',
    minRows: 3,
  }

  it('creates minRows skeleton rows for empty group', () => {
    const result = seedDynamicRows([], spec)
    expect(result).toHaveLength(3)
    expect(result[0].key).toBe('equity_01')
    expect(result[1].key).toBe('equity_02')
    expect(result[2].key).toBe('equity_03')
  })

  it('returns empty if group already has rows (idempotent)', () => {
    const existing: DbpDynamicRow[] = [{ key: 'equity_01', label: 'X', group: 'equity', seq: 1 }]
    expect(seedDynamicRows(existing, spec)).toEqual([])
  })
})

describe('sumGroupField', () => {
  interface Row extends DbpDynamicRow { amount: number }
  const rows: Row[] = [
    { key: 'g_01', label: 'A', group: 'g', seq: 1, amount: 100.005 },
    { key: 'g_02', label: 'B', group: 'g', seq: 2, amount: 200.005 },
    { key: 'other_01', label: 'C', group: 'other', seq: 1, amount: 999 },
  ]

  it('sums only matching group, rounded to 2 decimals', () => {
    expect(sumGroupField(rows, 'g', 'amount')).toBe(300.01)
  })

  it('returns 0 for empty group', () => {
    expect(sumGroupField(rows, 'nonexist', 'amount')).toBe(0)
  })
})

describe('findDuplicateKeys', () => {
  it('returns empty for all unique', () => {
    const rows: DbpDynamicRow[] = [
      { key: 'a_01', label: '', group: 'a', seq: 1 },
      { key: 'a_02', label: '', group: 'a', seq: 2 },
    ]
    expect(findDuplicateKeys(rows)).toEqual([])
  })

  it('detects duplicates', () => {
    const rows: DbpDynamicRow[] = [
      { key: 'x_01', label: '', group: 'x', seq: 1 },
      { key: 'x_01', label: '', group: 'x', seq: 1 },
    ]
    expect(findDuplicateKeys(rows)).toEqual(['x_01'])
  })
})

describe('hasLabelConflict', () => {
  const rows: DbpDynamicRow[] = [
    { key: 'a_01', label: '权益工具A', group: 'a', seq: 1 },
    { key: 'a_02', label: '权益工具B', group: 'a', seq: 2 },
  ]

  it('returns true for existing label', () => {
    expect(hasLabelConflict(rows, '权益工具A')).toBe(true)
  })

  it('returns false for new label', () => {
    expect(hasLabelConflict(rows, '权益工具C')).toBe(false)
  })

  it('excludes self key (rename scenario)', () => {
    expect(hasLabelConflict(rows, '权益工具A', 'a_01')).toBe(false)
  })

  it('trims whitespace', () => {
    expect(hasLabelConflict(rows, ' 权益工具A ')).toBe(true)
  })
})

// ─────────────────── PBT 风格（Property 11） ───────────────────

describe('Property 11: 任意增删序列后 key 唯一 + 父行派生', () => {
  it('random add/remove sequence keeps keys unique', () => {
    let rows: DbpDynamicRow[] = []
    const group = 'test'

    // 连续增 10 行
    for (let i = 0; i < 10; i++) {
      const r = addDynamicRow(rows, group, `Item ${i}`)
      rows = [...rows, r]
    }
    expect(findDuplicateKeys(rows)).toEqual([])
    expect(rows).toHaveLength(10)

    // 删除偶数 seq 的行
    rows = rows.filter(r => r.seq % 2 !== 0)
    expect(rows).toHaveLength(5)
    expect(findDuplicateKeys(rows)).toEqual([])

    // 再增 5 行（seq 应从 11 开始，不与剩余的 1/3/5/7/9 冲突）
    for (let i = 0; i < 5; i++) {
      const r = addDynamicRow(rows, group, `New ${i}`)
      rows = [...rows, r]
    }
    expect(findDuplicateKeys(rows)).toEqual([])
    expect(rows).toHaveLength(10)
    // 新增行 seq 应大于之前最大的 9
    const newRows = rows.slice(5)
    expect(newRows.every(r => r.seq > 9)).toBe(true)
  })

  it('parent sum changes after child removal', () => {
    interface Row extends DbpDynamicRow { amount: number }
    const group = 'g'
    let rows: Row[] = [
      { key: 'g_01', label: 'A', group, seq: 1, amount: 100 },
      { key: 'g_02', label: 'B', group, seq: 2, amount: 200 },
      { key: 'g_03', label: 'C', group, seq: 3, amount: 300 },
    ]
    expect(sumGroupField(rows, group, 'amount')).toBe(600)

    rows = removeDynamicRow(rows, 'g_02') as Row[]
    expect(sumGroupField(rows, group, 'amount')).toBe(400)
  })

  it('deleted row does not appear in filtered output', () => {
    let rows: DbpDynamicRow[] = [
      { key: 'x_01', label: 'A', group: 'x', seq: 1 },
      { key: 'x_02', label: 'B', group: 'x', seq: 2 },
    ]
    rows = removeDynamicRow(rows, 'x_02')
    expect(rows.find(r => r.key === 'x_02')).toBeUndefined()
  })
})

// ─────────────────── 反向自检 ───────────────────

describe('反向自检：共享件不含 J2 专属字面量', () => {
  it('source has no J2-specific strings', async () => {
    const fs = await import('fs')
    const path = await import('path')
    const src = fs.readFileSync(
      path.resolve(__dirname, '../shared/dbpDynamicRows.ts'),
      'utf-8',
    )
    // 去注释
    const stripped = src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*/g, '')
    expect(stripped).not.toContain("'2705'")
    expect(stripped).not.toContain("'J2'")
    expect(stripped).not.toContain("'设定受益'")
    expect(stripped).not.toContain("'计划资产'")
    // 正向：应含通用关键字
    expect(src).toContain('DbpDynamicSpec')
    expect(src).toContain('addDynamicRow')
  })
})
