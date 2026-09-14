/**
 * D4（4）分解信息表行集与源模板对齐守卫（Task 31）。
 *
 * 判据真源 = 源 xlsx `backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`
 *   上市 `附注披露信息（上市公司）` R44~R56
 *   国企 `附注披露信息（国企）`     R37~R49
 *
 * 🔴 该 xlsx 由后端守卫 `backend/tests/services/test_note_d_cycle_rest_structure.py`
 * 一类做 openpyxl 直读三向比对；前端这层只能读不到 xlsx（vitest 无 openpyxl），
 * 故把实证结论**冻结为常量**并交叉锁死，任何一侧漂移即打红。
 *
 * spec: d-cycle-four-table-extraction-and-disclosure-completion (Task 31)
 * Requirements: 7.5
 */

import { describe, it, expect } from 'vitest'

import {
  D4_SEGMENT_ROWS,
  D4_SEGMENT_INPUT_ROW_KEYS,
  D4_LEGACY_ROW_INDEX_MAP,
  segmentCellKey,
  deriveSegmentCell,
  segmentRowAcrossCategories,
  migrateSegmentCellKeys,
} from '../d4RevenueSegmentColumns'

// ── 源模板行集实证快照（逐字，含缩进空格）──────────────────────────────────
// 上市 R48~R56 / 国企 R41~R49，两版逐行同构。
const SOURCE_ROW_LABELS = [
  '主营业务',
  '其中：在某一时点确认',
  '      在某一时段确认',
  '', // R51 / R44 空可扩行（在小计 SUM 范围内）
  '其他业务',
  '其中：在某一时点确认',
  '      在某一时段确认',
  '      租赁收入',
  '合  计',
] as const

// 源模板小计公式覆盖范围（上市）：R48=SUM(B49:B51) / R52=SUM(B53:B55) / R56=B52+B48
const SOURCE_SUBTOTAL_SPANS = {
  main: 3, // R49~R51
  other: 3, // R53~R55
} as const

describe('Task 31: 行集与源模板逐行对齐', () => {
  it('行数与标签序列逐字等于源模板', () => {
    expect(D4_SEGMENT_ROWS).toHaveLength(SOURCE_ROW_LABELS.length)
    expect(D4_SEGMENT_ROWS.map((r) => r.label)).toEqual([...SOURCE_ROW_LABELS])
  })

  it('🔴 两个业务父行是派生小计，各辖 3 个可录入行（源模板 SUM 范围）', () => {
    const main = D4_SEGMENT_ROWS.find((r) => r.key === 'main')!
    const other = D4_SEGMENT_ROWS.find((r) => r.key === 'other')!
    expect(main.kind).toBe('subtotal')
    expect(other.kind).toBe('subtotal')
    expect(main.children).toHaveLength(SOURCE_SUBTOTAL_SPANS.main)
    expect(other.children).toHaveLength(SOURCE_SUBTOTAL_SPANS.other)
  })

  it('🔴 空可扩行在主营业务小计范围内（源模板 R51 在 SUM(B49:B51) 内）', () => {
    const main = D4_SEGMENT_ROWS.find((r) => r.key === 'main')!
    expect(main.children).toContain('main_ext')
    const ext = D4_SEGMENT_ROWS.find((r) => r.key === 'main_ext')!
    expect(ext.kind).toBe('expandable')
    expect(ext.label).toBe('')
  })

  it('🔴 租赁收入归其他业务（源模板里它只在其他业务下出现）', () => {
    const other = D4_SEGMENT_ROWS.find((r) => r.key === 'other')!
    expect(other.children).toContain('other_lease')
    const main = D4_SEGMENT_ROWS.find((r) => r.key === 'main')!
    expect(main.children).not.toContain('other_lease')
  })

  it('合计行 = 两个小计之和（源模板 R56 = B52 + B48，不是全部明细行直接求和）', () => {
    const total = D4_SEGMENT_ROWS.find((r) => r.key === 'total')!
    expect(total.kind).toBe('total')
    expect(total.children).toEqual(['main', 'other'])
  })

  it('可录入行恰 6 个，父行与合计行不可录入', () => {
    expect(D4_SEGMENT_INPUT_ROW_KEYS).toEqual([
      'main_point',
      'main_period',
      'main_ext',
      'other_point',
      'other_period',
      'other_lease',
    ])
    expect(D4_SEGMENT_INPUT_ROW_KEYS).not.toContain('main')
    expect(D4_SEGMENT_INPUT_ROW_KEYS).not.toContain('other')
    expect(D4_SEGMENT_INPUT_ROW_KEYS).not.toContain('total')
  })

  it('行键不含中文、不含纯序号（防退回 rowIdx 形态）', () => {
    for (const r of D4_SEGMENT_ROWS) {
      expect(/[\u4e00-\u9fa5]/.test(r.key)).toBe(false)
      expect(/^\d+$/.test(r.key)).toBe(false)
    }
    expect(new Set(D4_SEGMENT_ROWS.map((r) => r.key)).size).toBe(D4_SEGMENT_ROWS.length)
  })

  it('🔴 「时点/时段」在源模板各出现两次 ⇒ 行键必须区分归属', () => {
    const labels = D4_SEGMENT_ROWS.map((r) => r.label)
    expect(labels.filter((l) => l.includes('在某一时点确认'))).toHaveLength(2)
    expect(labels.filter((l) => l.includes('在某一时段确认'))).toHaveLength(2)
    // 同标签不同归属 ⇒ key 必须不同（旧模型只有一份，无法表达）
    const pointKeys = D4_SEGMENT_ROWS.filter((r) => r.label.includes('在某一时点确认')).map(
      (r) => r.key,
    )
    expect(new Set(pointKeys).size).toBe(2)
  })
})

describe('Task 31: 派生取值（三态，不把未录入当 0）', () => {
  const cat = 'cat_1'

  it('小计 = 其辖明细之和', () => {
    const cells = {
      [segmentCellKey(cat, 'main_point', 'revenue')]: 100,
      [segmentCellKey(cat, 'main_period', 'revenue')]: 200,
    }
    expect(deriveSegmentCell(cells, cat, 'main', 'revenue')).toBe(300)
  })

  it('合计 = 两个小计之和', () => {
    const cells = {
      [segmentCellKey(cat, 'main_point', 'revenue')]: 100,
      [segmentCellKey(cat, 'other_lease', 'revenue')]: 50,
    }
    expect(deriveSegmentCell(cells, cat, 'total', 'revenue')).toBe(150)
  })

  it('🔴 全部被加项未录入 ⇒ 返 null（不是 0）', () => {
    expect(deriveSegmentCell({}, cat, 'main', 'revenue')).toBeNull()
    expect(deriveSegmentCell({}, cat, 'total', 'cost')).toBeNull()
  })

  it('录入 0 与未录入可区分', () => {
    const cells = { [segmentCellKey(cat, 'main_point', 'revenue')]: 0 }
    expect(deriveSegmentCell(cells, cat, 'main', 'revenue')).toBe(0)
    expect(deriveSegmentCell(cells, cat, 'other', 'revenue')).toBeNull()
  })

  it('可扩行参与小计', () => {
    const cells = { [segmentCellKey(cat, 'main_ext', 'cost')]: 7 }
    expect(deriveSegmentCell(cells, cat, 'main', 'cost')).toBe(7)
  })

  it('未知行键返 null 而不抛', () => {
    expect(deriveSegmentCell({}, cat, 'nope', 'revenue')).toBeNull()
  })

  it('横向合计只供底稿内部核对（源模板无该列）', () => {
    const cells = {
      [segmentCellKey('cat_1', 'main_point', 'revenue')]: 10,
      [segmentCellKey('cat_2', 'main_point', 'revenue')]: 20,
    }
    const cats = [
      { key: 'cat_1', label: 'A' },
      { key: 'cat_2', label: 'B' },
    ]
    expect(segmentRowAcrossCategories(cells, cats, 'main_point', 'revenue')).toBe(30)
    expect(segmentRowAcrossCategories({}, cats, 'main_point', 'revenue')).toBeNull()
  })
})

describe('Task 31: 单元格键迁移（rowIdx → rowKey）', () => {
  it('三个旧 rowIdx 逐个映射到确定的新行键', () => {
    expect(D4_LEGACY_ROW_INDEX_MAP['0']).toBe('main_point')
    expect(D4_LEGACY_ROW_INDEX_MAP['1']).toBe('main_period')
    // 租赁收入在源模板里只在其他业务下 ⇒ 这一条是**确定**的
    expect(D4_LEGACY_ROW_INDEX_MAP['2']).toBe('other_lease')
  })

  it('旧键被迁移，值不丢', () => {
    const r = migrateSegmentCellKeys({
      cat_1_0_revenue: 100,
      cat_1_1_cost: 50,
      cat_2_2_revenue: 30,
    })
    expect(r.migrated).toBe(3)
    expect(r.cells[segmentCellKey('cat_1', 'main_point', 'revenue')]).toBe(100)
    expect(r.cells[segmentCellKey('cat_1', 'main_period', 'cost')]).toBe(50)
    expect(r.cells[segmentCellKey('cat_2', 'other_lease', 'revenue')]).toBe(30)
    // 旧键不残留（否则同一笔钱在两行各显示一次）
    expect(r.cells.cat_1_0_revenue).toBeUndefined()
  })

  it('🔴 幂等：已是 rowKey 形态的键原样通过', () => {
    const already = {
      [segmentCellKey('cat_1', 'main_point', 'revenue')]: 100,
      [segmentCellKey('cat_3', 'other_period', 'cost')]: 9,
    }
    const r = migrateSegmentCellKeys(already)
    expect(r.migrated).toBe(0)
    expect(r.changed).toBe(false)
    expect(r.cells).toEqual(already)
  })

  it('🔴 无法识别的键原样保留（数据零丢失）', () => {
    const r = migrateSegmentCellKeys({ weird_key: 1, cat_1_99_revenue: 2 })
    expect(r.cells.weird_key).toBe(1)
    // rowIdx 99 不在迁移表里 ⇒ 保留原键
    expect(r.cells.cat_1_99_revenue).toBe(2)
    expect(r.kept).toContain('weird_key')
    expect(r.kept).toContain('cat_1_99_revenue')
  })

  it('两个旧键映射到同一新键时累加而非覆盖', () => {
    // 构造：旧 0 与已存在的 main_point 同时存在
    const r = migrateSegmentCellKeys({
      cat_1_0_revenue: 100,
      [segmentCellKey('cat_1', 'main_point', 'revenue')]: 5,
    })
    expect(r.cells[segmentCellKey('cat_1', 'main_point', 'revenue')]).toBe(105)
  })

  it('空输入不抛', () => {
    expect(migrateSegmentCellKeys(undefined).cells).toEqual({})
    expect(migrateSegmentCellKeys({}).changed).toBe(false)
  })
})
