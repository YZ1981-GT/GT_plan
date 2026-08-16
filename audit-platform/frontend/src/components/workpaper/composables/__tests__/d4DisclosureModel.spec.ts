/**
 * D4 披露数据模型引擎守卫（列引擎 + 列转置稳定 key + 年度列派生 + 合计派生）。
 *
 * PBT (fast-check)：
 * - Property 16: 列转置 key 稳定且不撞（重复 label 也不撞键）
 * - Property 15: 动态年度列由审计年度派生
 * - deriveObligationTotal 与手动求和一致
 * - nextD4CategoryKey 返回唯一 key
 *
 * spec: d4-four-table-extraction-and-disclosure-alignment (Task 5.6)
 * Requirements: 9.1, 9.5, 9.6
 *
 * **Validates: Requirements 9.1, 9.5, 9.6**
 */
import { describe, expect, it } from 'vitest'
import fc from 'fast-check'
import {
  buildD4TwoPeriodColumns,
  buildD4TransposeColumns,
  buildD4ObligationColumns,
  deriveObligationTotal,
  nextD4CategoryKey,
  getObligationYearKeys,
  D4_DEFAULT_CATEGORIES,
  D4_TRANSPOSE_CHECK_ITEMS,
  type D4TransposeCategory,
} from '../d4DisclosureModel'
// Task 31: 行集真源已迁到 d4RevenueSegmentColumns.D4_SEGMENT_ROWS，
// 本文件对 D4_TRANSPOSE_CHECK_ITEMS 的断言只是「退役常量仍可编译」的存在性检查。
import { D4_SEGMENT_ROWS } from '../d4RevenueSegmentColumns'

// ═══════════════════════════════════════════════════════════════════════
// §1 buildD4TwoPeriodColumns — 5 列两级表头
// ═══════════════════════════════════════════════════════════════════════

describe('buildD4TwoPeriodColumns', () => {
  it('零入参返回 5 列（Property 27: builder 零入参可调）', () => {
    const cols = buildD4TwoPeriodColumns()
    expect(cols).toHaveLength(5)
  })

  it('每列声明 group 或 flat（Property 13）', () => {
    const cols = buildD4TwoPeriodColumns()
    for (const col of cols) {
      expect(
        col.group || col.flat,
        `列 ${col.key} 既无 group 又无 flat`,
      ).toBeTruthy()
    }
  })

  it('main 变体叶子列名 = 收入/成本', () => {
    const cols = buildD4TwoPeriodColumns('main')
    expect(cols[1].label).toBe('收入')
    expect(cols[2].label).toBe('成本')
    expect(cols[3].label).toBe('收入')
    expect(cols[4].label).toBe('成本')
  })

  it('region_listed 叶子列名 = 主营业务收入/主营业务成本', () => {
    const cols = buildD4TwoPeriodColumns('region_listed')
    expect(cols[1].label).toBe('主营业务收入')
    expect(cols[2].label).toBe('主营业务成本')
  })

  it('region_soe 叶子列名 = 收入/成本', () => {
    const cols = buildD4TwoPeriodColumns('region_soe')
    expect(cols[1].label).toBe('收入')
    expect(cols[2].label).toBe('成本')
  })

  it('两级 group 结构 = 本期发生额 + 上期发生额', () => {
    const cols = buildD4TwoPeriodColumns()
    expect(cols[1].group).toBe('本期发生额')
    expect(cols[2].group).toBe('本期发生额')
    expect(cols[3].group).toBe('上期发生额')
    expect(cols[4].group).toBe('上期发生额')
  })

  it('标签列为 is_label + flat', () => {
    const cols = buildD4TwoPeriodColumns()
    expect(cols[0].is_label).toBe(true)
    expect(cols[0].flat).toBe(true)
    expect(cols[0].key).toBe('label')
  })
})

// ═══════════════════════════════════════════════════════════════════════
// §2 buildD4TransposeColumns — 列转置 + 稳定 key
// ═══════════════════════════════════════════════════════════════════════

describe('buildD4TransposeColumns', () => {
  it('零入参返回默认 4 类别的列集（Property 27）', () => {
    const cols = buildD4TransposeColumns()
    // 🔴 Task 31: 源 xlsx 实证该表 **9 列**（label + 4 类别 × 收入/成本），
    //    **没有横向合计列** —— 源模板的合计是**行**（上市 R56 `=B52+B48`）。
    //    改造前这里断言 11 列，镜像的是自造出来的 total_revenue/total_cost。
    expect(cols).toHaveLength(9)
  })

  it('每列声明 group 或 flat（Property 13）', () => {
    const cols = buildD4TransposeColumns()
    for (const col of cols) {
      expect(
        col.group || col.flat,
        `列 ${col.key} 既无 group 又无 flat`,
      ).toBeTruthy()
    }
  })

  it('列 key 使用 {categoryKey}_{revenue|cost} 稳定标识（Property 16）', () => {
    const cols = buildD4TransposeColumns()
    // 非标签/合计列
    const catCols = cols.filter(c => !c.is_label && !c.key.startsWith('total_'))
    for (const c of catCols) {
      expect(c.key).toMatch(/^cat_\d+_(revenue|cost)$/)
    }
  })

  it('默认类别 = 消费品/汽车/能源/其他', () => {
    expect(D4_DEFAULT_CATEGORIES.map(c => c.label)).toEqual(['消费品', '汽车', '能源', '其他'])
    expect(D4_DEFAULT_CATEGORIES.map(c => c.key)).toEqual(['cat_1', 'cat_2', 'cat_3', 'cat_4'])
  })

  it('PBT Property 16: 任意字符串列表（含重复）生成的列 key 不冲突', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 0, maxLength: 20 }), { minLength: 1, maxLength: 20 }),
        (labels) => {
          const categories: D4TransposeCategory[] = labels.map((label, i) => ({
            key: `cat_${i + 1}`,
            label,
          }))
          const cols = buildD4TransposeColumns(categories)
          const keys = cols.map(c => c.key)
          // All keys must be unique
          expect(new Set(keys).size).toBe(keys.length)
        },
      ),
      { numRuns: 50 },
    )
  })

  it('🔴 不得出现横向合计列（Task 31：源模板的合计是行不是列）', () => {
    const cols = buildD4TransposeColumns()
    const keys = cols.map(c => c.key)
    expect(keys).not.toContain('total_revenue')
    expect(keys).not.toContain('total_cost')
    // 也不许换个名字把它加回来：除标签列外，列 key 必须全是 `cat_N_{revenue|cost}`
    for (const c of cols) {
      if (c.is_label) continue
      expect(c.key, `出现了非类别列 ${c.key}`).toMatch(/^cat_\d+_(revenue|cost)$/)
    }
    // 反向自检：类别列本身确实存在（否则上面的断言在空列集上也会通过）
    expect(cols.filter(c => !c.is_label).length).toBe(8)
  })

  it('末列是最后一个类别的成本列（源模板 I 列 = 其他-成本）', () => {
    const cols = buildD4TransposeColumns()
    const last = cols[cols.length - 1]
    const lastCat = D4_DEFAULT_CATEGORIES[D4_DEFAULT_CATEGORIES.length - 1]
    expect(last.key).toBe(`${lastCat.key}_cost`)
    expect(last.group).toBe(lastCat.label)
  })

  it('group 名 = 类别 label', () => {
    const cols = buildD4TransposeColumns()
    const catCols = cols.filter(c => !c.is_label && !c.key.startsWith('total_'))
    expect(catCols[0].group).toBe('消费品')
    expect(catCols[2].group).toBe('汽车')
  })
})

describe('Task 31: 退役常量与新行集的关系', () => {
  it('🔴 D4_TRANSPOSE_CHECK_ITEMS 的每一项都能在新行集里找到对应行', () => {
    const labels = D4_SEGMENT_ROWS.map(r => r.label.trim())
    for (const item of D4_TRANSPOSE_CHECK_ITEMS) {
      expect(
        labels.some(l => l.includes(item)),
        `退役常量项「${item}」在新行集里找不到 ⇒ 行集漂移`,
      ).toBe(true)
    }
  })

  it('🔴 新行集严格多于退役常量（父行 / 可扩行 / 合计行）', () => {
    expect(D4_SEGMENT_ROWS.length).toBeGreaterThan(D4_TRANSPOSE_CHECK_ITEMS.length)
    const kinds = new Set(D4_SEGMENT_ROWS.map(r => r.kind))
    expect(kinds.has('subtotal')).toBe(true)
    expect(kinds.has('expandable')).toBe(true)
    expect(kinds.has('total')).toBe(true)
  })
})

describe('nextD4CategoryKey', () => {
  it('空列表返回 cat_1', () => {
    expect(nextD4CategoryKey([])).toBe('cat_1')
  })

  it('默认 4 类别后返回 cat_5', () => {
    expect(nextD4CategoryKey(D4_DEFAULT_CATEGORIES)).toBe('cat_5')
  })

  it('删中间项后不复用已删除的 seq', () => {
    const cats = [
      { key: 'cat_1', label: 'A' },
      { key: 'cat_3', label: 'C' },
    ]
    // max seq = 3, next = 4
    expect(nextD4CategoryKey(cats)).toBe('cat_4')
  })

  it('PBT: 对任意已有类别集合，返回的 key 不与已有键冲突', () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: 1, max: 100 }), { minLength: 0, maxLength: 20 }),
        (seqs) => {
          const cats: D4TransposeCategory[] = seqs.map(s => ({
            key: `cat_${s}`,
            label: `Category ${s}`,
          }))
          const newKey = nextD4CategoryKey(cats)
          const existingKeys = new Set(cats.map(c => c.key))
          expect(existingKeys.has(newKey)).toBe(false)
        },
      ),
      { numRuns: 50 },
    )
  })
})

describe('D4_TRANSPOSE_CHECK_ITEMS', () => {
  it('固定检查项行 = 3 项', () => {
    expect(D4_TRANSPOSE_CHECK_ITEMS).toEqual([
      '在某一时点确认',
      '在某一时段确认',
      '租赁收入',
    ])
  })
})

// ═══════════════════════════════════════════════════════════════════════
// §3 buildD4ObligationColumns — 动态年度列 + 合计派生
// ═══════════════════════════════════════════════════════════════════════

describe('buildD4ObligationColumns', () => {
  it('零入参返回 4 列（Property 27）', () => {
    const cols = buildD4ObligationColumns()
    expect(cols).toHaveLength(4)
  })

  it('每列声明 flat（Property 13: 单级表头）', () => {
    const cols = buildD4ObligationColumns()
    for (const col of cols) {
      expect(col.flat, `列 ${col.key} 未标 flat`).toBe(true)
    }
    // 不得有 group
    expect(cols.some(c => c.group)).toBe(false)
  })

  it('默认审计年度 2025 → 年度列 2026年/2027年（Property 15）', () => {
    const cols = buildD4ObligationColumns()
    expect(cols[1].label).toBe('2026年')
    expect(cols[2].label).toBe('2027年')
    expect(cols[1].key).toBe('year_2026')
    expect(cols[2].key).toBe('year_2027')
  })

  it('PBT Property 15: 任意审计年度 → 年度列为 year+1 和 year+2', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 2000, max: 2100 }),
        (auditYear) => {
          const cols = buildD4ObligationColumns(auditYear)
          expect(cols[1].label).toBe(`${auditYear + 1}年`)
          expect(cols[2].label).toBe(`${auditYear + 2}年`)
          expect(cols[1].key).toBe(`year_${auditYear + 1}`)
          expect(cols[2].key).toBe(`year_${auditYear + 2}`)
          // 🔴 「不含硬编码年份」只能**带条件**断言 —— auditYear=2025 时
          //    label 本就是 `2026年`。改造前这里先无条件断言 not.toContain('2026')
          //    再补一个带条件的同款断言，前者在 seed 命中 2025 时必失败
          //    （随机种子脆弱：多数 seed 抽不到 2025 就一直是绿的）。
          if (auditYear !== 2025) {
            expect(cols[1].label).not.toContain('2026')
          }
          if (auditYear !== 2025) {
            expect(cols[2].label).not.toContain('2027')
          }
        },
      ),
      { numRuns: 30 },
    )
  })

  it('审计年度 2025 边界（PBT 曾因随机 seed 漏过）', () => {
    const cols = buildD4ObligationColumns(2025)
    expect(cols[1].label).toBe('2026年')
    expect(cols[2].label).toBe('2027年')
  })

  it('合计列 key 固定 total', () => {
    const cols = buildD4ObligationColumns(2024)
    expect(cols[3].key).toBe('total')
    expect(cols[3].label).toBe('合计')
  })
})

describe('getObligationYearKeys', () => {
  it('返回两个年度 key', () => {
    expect(getObligationYearKeys(2025)).toEqual(['year_2026', 'year_2027'])
    expect(getObligationYearKeys(2030)).toEqual(['year_2031', 'year_2032'])
  })
})

describe('deriveObligationTotal', () => {
  it('两年度列之和', () => {
    expect(deriveObligationTotal({ year_2026: 500, year_2027: 300 }, 2025)).toBe(800)
  })

  it('一列 null 时只取非 null 列', () => {
    expect(deriveObligationTotal({ year_2026: 500, year_2027: null }, 2025)).toBe(500)
    expect(deriveObligationTotal({ year_2026: null, year_2027: 300 }, 2025)).toBe(300)
  })

  it('两列都 null 返回 null', () => {
    expect(deriveObligationTotal({ year_2026: null, year_2027: null }, 2025)).toBeNull()
    expect(deriveObligationTotal({}, 2025)).toBeNull()
  })

  it('PBT: deriveObligationTotal 与手动求和一致', () => {
    const amt = () => fc.oneof(
      fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
      fc.constant(null as number | null),
    )
    fc.assert(
      fc.property(
        fc.integer({ min: 2000, max: 2100 }),
        amt(),
        amt(),
        (auditYear, v1, v2) => {
          const row: Record<string, unknown> = {}
          if (v1 !== null) row[`year_${auditYear + 1}`] = v1
          if (v2 !== null) row[`year_${auditYear + 2}`] = v2

          const result = deriveObligationTotal(row, auditYear)

          if (v1 === null && v2 === null) {
            expect(result).toBeNull()
          } else {
            const expected = (v1 ?? 0) + (v2 ?? 0)
            expect(Math.abs((result as number) - expected)).toBeLessThan(0.011)
          }
        },
      ),
      { numRuns: 50 },
    )
  })
})
