/**
 * transposeGrid.spec.ts — advanced-query-module Task 18.5
 *
 * Property 10: 转置 round-trip
 * Validates: Requirements 6.2, 6.3
 * Feature: advanced-query-module, Property 10
 *
 * fast-check：随机结果网格（含 Unicode 标签、空值），断言
 * `transposeGrid(transposeGrid(R))` 在**单元格值、行标签、列标签、行列顺序**四个
 * 维度上与原网格完全一致（round-trip 属性）。
 *
 * 说明（按用户约定）：本预览态纯函数的 round-trip 属性对少量样本已足以覆盖退化形态
 * （空表 / 有标签无数据 / 单行 / 单列 / 非方阵），故 `numRuns` 收敛为 20 以保证快速回归，
 * 不做数百次迭代。
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  transposeGrid,
  exceedsPreviewLimit,
  PREVIEW_MAX_ROWS,
  PREVIEW_MAX_COLS,
  type Grid,
  type Cell,
} from '../transposeGrid'

const NUM_RUNS = 20

// ─── fast-check 生成器 ─────────────────────────────────────────────────────────

/** Unicode 标签（含中文 / emoji / 拉丁 / 空串），验证标签在转置中被忠实保留。 */
const labelArb = fc.string({ unit: 'grapheme', maxLength: 6 })

/** 单元格值：显式覆盖空值（null / 空串）、数字、Unicode 文本。 */
const valueArb = fc.oneof(
  fc.constant(null),
  fc.constant(''),
  fc.integer(),
  fc.double({ noNaN: true }),
  fc.string({ unit: 'grapheme', maxLength: 8 }),
)

/** addr_id：单一源格携带字符串，多源 / 无源为 null。 */
const addrIdArb = fc.oneof(fc.constant(null), fc.string({ unit: 'grapheme', maxLength: 10 }))

const cellArb: fc.Arbitrary<Cell> = fc.record({ value: valueArb, addrId: addrIdArb })

/**
 * 良构 Grid 生成器：`cells` 为严格 `R × C` 矩阵，维度与标签长度一致。
 * 允许 R / C 为 0（退化形态：空表、有标签无数据）。
 */
const gridArb: fc.Arbitrary<Grid> = fc
  .tuple(fc.array(labelArb, { maxLength: 5 }), fc.array(labelArb, { maxLength: 5 }))
  .chain(([rowLabels, colLabels]) =>
    fc
      .array(
        fc.array(cellArb, {
          minLength: colLabels.length,
          maxLength: colLabels.length,
        }),
        { minLength: rowLabels.length, maxLength: rowLabels.length },
      )
      .map((cells): Grid => ({ rowLabels, colLabels, cells })),
  )

// ─── Property 10 ───────────────────────────────────────────────────────────────

describe('transposeGrid — Property 10 转置 round-trip (fast-check)', () => {
  it('transposeGrid(transposeGrid(R)) 深度等于 R（单元格值 / 行列标签 / 行列顺序）', () => {
    fc.assert(
      fc.property(gridArb, (grid) => {
        const roundTrip = transposeGrid(transposeGrid(grid))
        // toEqual 为顺序敏感的深度结构相等：同时校验值、行/列标签与行列顺序。
        expect(roundTrip).toEqual(grid)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('单次转置后行列标签互换、矩阵为原矩阵的转置（out[c][r] === in[r][c]）', () => {
    fc.assert(
      fc.property(gridArb, (grid) => {
        const t = transposeGrid(grid)
        expect(t.rowLabels).toEqual(grid.colLabels)
        expect(t.colLabels).toEqual(grid.rowLabels)
        for (let r = 0; r < grid.rowLabels.length; r += 1) {
          for (let c = 0; c < grid.colLabels.length; c += 1) {
            expect(t.cells[c][r]).toEqual(grid.cells[r][c])
          }
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })

  it('纯函数：不修改入参（转置结果与入参无共享可变引用）', () => {
    fc.assert(
      fc.property(gridArb, (grid) => {
        const snapshot = JSON.parse(JSON.stringify(grid))
        const t = transposeGrid(grid)
        // 入参未被改动
        expect(grid).toEqual(snapshot)
        // 修改输出不影响输入（无共享 Cell 引用）
        if (t.cells.length && t.cells[0].length) {
          t.cells[0][0].value = '__mutated__'
          expect(grid).toEqual(snapshot)
        }
      }),
      { numRuns: NUM_RUNS },
    )
  })
})

// ─── 具体边界示例（单元测试补充） ────────────────────────────────────────────────

describe('transposeGrid — 边界示例', () => {
  it('空表 round-trip 恒等', () => {
    const empty: Grid = { rowLabels: [], colLabels: [], cells: [] }
    expect(transposeGrid(transposeGrid(empty))).toEqual(empty)
    expect(transposeGrid(empty)).toEqual(empty)
  })

  it('单格网格转置为自身形态并保留 addr_id 与空值', () => {
    const g: Grid = {
      rowLabels: ['行'],
      colLabels: ['列'],
      cells: [[{ value: null, addrId: 'D2/D2-2/E100' }]],
    }
    const t = transposeGrid(g)
    expect(t.rowLabels).toEqual(['列'])
    expect(t.colLabels).toEqual(['行'])
    expect(t.cells[0][0]).toEqual({ value: null, addrId: 'D2/D2-2/E100' })
    expect(transposeGrid(t)).toEqual(g)
  })

  it('2×3 非方阵转置为 3×2 并 round-trip 恒等', () => {
    const g: Grid = {
      rowLabels: ['甲', '乙'],
      colLabels: ['一', '二', '三'],
      cells: [
        [
          { value: 1, addrId: null },
          { value: '', addrId: null },
          { value: 'x', addrId: 'a' },
        ],
        [
          { value: 2, addrId: 'b' },
          { value: null, addrId: null },
          { value: 3, addrId: null },
        ],
      ],
    }
    const t = transposeGrid(g)
    expect(t.rowLabels.length).toBe(3)
    expect(t.colLabels.length).toBe(2)
    expect(t.cells[2][0]).toEqual({ value: 'x', addrId: 'a' })
    expect(transposeGrid(t)).toEqual(g)
  })

  it('exceedsPreviewLimit：超过 200×200 时为 true', () => {
    const within: Grid = {
      rowLabels: Array.from({ length: PREVIEW_MAX_ROWS }, (_, i) => `r${i}`),
      colLabels: Array.from({ length: PREVIEW_MAX_COLS }, (_, i) => `c${i}`),
      cells: [],
    }
    expect(exceedsPreviewLimit(within)).toBe(false)

    const tooManyRows: Grid = {
      rowLabels: Array.from({ length: PREVIEW_MAX_ROWS + 1 }, (_, i) => `r${i}`),
      colLabels: [],
      cells: [],
    }
    expect(exceedsPreviewLimit(tooManyRows)).toBe(true)
  })
})
