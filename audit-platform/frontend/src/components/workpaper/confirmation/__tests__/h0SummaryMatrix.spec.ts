/**
 * h0SummaryMatrix.spec.ts — H0-1 品种矩阵纯函数守卫
 *
 * spec: h0-confirmation-source-fidelity-and-linkage
 *   Requirements 2.2~2.5 / 3.8；Property 4 / 5 / 6
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  H0_MATRIX_METRIC_LABELS,
  H0_MATRIX_DEFAULT_CATEGORIES,
  H0_MATRIX_EDITABLE_METRIC_INDEX,
  buildH0SummaryMatrix,
  createDefaultH0Categories,
  detectH0CoverageAlerts,
  h0MatrixOverrideItemId,
  maxH0CategorySeq,
  nextH0CategoryKey,
  parseH0Categories,
  parseH0Seq,
  toH0MatrixTableRows,
  type H0MatrixCategory,
} from '../h0SummaryMatrix'
import type { ConfirmationRow } from '../confirmationTypes'

const CATS: H0MatrixCategory[] = [
  { key: 'cat_1', label: '固定资产' },
  { key: 'cat_2', label: '工程物资' },
]

function row(p: Partial<ConfirmationRow>): ConfirmationRow {
  return { _row_id: Math.random().toString(36).slice(2), ...p } as ConfirmationRow
}

// ─── 指标常量 ────────────────────────────────────────────────────────────────

describe('指标与默认品种（源模板逐字）', () => {
  it('8 个指标标签逐字（源模板 C30:C37）', () => {
    expect(H0_MATRIX_METRIC_LABELS).toEqual([
      '本期（期末）账面金额',
      '抽取样本的发函金额',
      '发函金额占账面金额的比例(%)',
      '回函确认金额',
      '回函可确认金额占发函金额的比例(%)',
      '回函可确认金额占账面金额的比例(%)',
      '替代测试确认金额',
      '回函和替代确认金额占账面金额的比例(%)',
    ])
  })

  it('默认品种 3 个（源模板 E29/F29/G29；H29 是可扩位不 seed）', () => {
    expect(H0_MATRIX_DEFAULT_CATEGORIES).toEqual(['固定资产', '工程物资', '租赁负债'])
    // 🔴 「使用权资产」出现在 sheet 标题但源模板矩阵未列 → 不 seed（宁缺勿造）
    expect(H0_MATRIX_DEFAULT_CATEGORIES).not.toContain('使用权资产')
  })

  it('只有账面金额行可编辑（源模板 R30 手填，R31~R37 是公式）', () => {
    expect(H0_MATRIX_EDITABLE_METRIC_INDEX).toBe(0)
    const m = buildH0SummaryMatrix({ rows: [], categories: CATS })
    for (const catCells of m) {
      expect(catCells[0].editable).toBe(true)
      for (let i = 1; i < 8; i++) expect(catCells[i].editable).toBe(false)
    }
  })
})

// ─── Property 4: 三个聚合行按源模板 SUMIF 口径 ──────────────────────────────

describe('Property 4: SUMIF 口径（E 列分品种，取 F/U/Y 三列）', () => {
  const rows: ConfirmationRow[] = [
    row({ account_type: '固定资产', amount: 100, confirmed_amount: 80, alt_confirmed: 10 }),
    row({ account_type: '固定资产', amount: 200, confirmed_amount: 150, alt_confirmed: 20 }),
    row({ account_type: '工程物资', amount: 50, confirmed_amount: 50, alt_confirmed: 0 }),
    // 品种为空/其它 → 不计入任何品种列
    row({ account_type: '', amount: 999, confirmed_amount: 999, alt_confirmed: 999 }),
    row({ account_type: '应收账款', amount: 888, confirmed_amount: 888, alt_confirmed: 888 }),
  ]

  it('R31 = Σ amount / R33 = Σ confirmed_amount / R36 = Σ alt_confirmed', () => {
    const m = buildH0SummaryMatrix({ rows, categories: CATS })
    expect(m[0][1].value).toBe(300) // 固定资产 100+200
    expect(m[0][3].value).toBe(230) // 80+150
    expect(m[0][6].value).toBe(30) // 10+20
    expect(m[1][1].value).toBe(50)
    expect(m[1][3].value).toBe(50)
    expect(m[1][6].value).toBe(0)
  })

  it('未匹配品种的行不被计入（防「其它」被吞进第一列）', () => {
    const m = buildH0SummaryMatrix({ rows, categories: CATS })
    const total = (m[0][1].value ?? 0) + (m[1][1].value ?? 0)
    expect(total).toBe(350) // 999/888 都不计入
  })

  it('三个聚合行的 sourceHint 写明源模板公式与品种', () => {
    const m = buildH0SummaryMatrix({ rows, categories: CATS })
    expect(m[0][1].sourceHint).toContain('SUMIF(E,固定资产,F)')
    expect(m[0][3].sourceHint).toContain('SUMIF(E,固定资产,U)')
    expect(m[0][6].sourceHint).toContain('SUMIF(E,固定资产,Y)')
  })

  it('比例行按源模板分子分母（R32/R34/R35/R37）', () => {
    const m = buildH0SummaryMatrix({
      rows,
      categories: CATS,
      bookAmounts: { 固定资产: 600, 工程物资: 100 },
    })
    expect(m[0][2].value).toBeCloseTo(300 / 600) // R32 发函/账面
    expect(m[0][4].value!).toBeCloseTo(230 / 300) // R34 回函/发函
    expect(m[0][5].value!).toBeCloseTo(230 / 600) // R35 回函/账面
    expect(m[0][7].value!).toBeCloseTo((230 + 30) / 600) // R37 (回函+替代)/账面
  })
})

// ─── Property 5: 分母缺失返 null 不返 0/NaN ─────────────────────────────────

describe('Property 5: 比例行 null 语义 + 绝不产出 NaN/Infinity', () => {
  it('bookAmounts 缺该品种（键不存在）→ 账面 null、比例 null、origin=empty', () => {
    const m = buildH0SummaryMatrix({ rows: [], categories: CATS, bookAmounts: {} })
    expect(m[0][0].value).toBeNull()
    expect(m[0][0].origin).toBe('empty')
    for (const i of [2, 5, 7]) expect(m[0][i].value).toBeNull()
  })

  it('bookAmounts 该品种为 null（本项目无此科目）→ origin=absent', () => {
    const m = buildH0SummaryMatrix({ rows: [], categories: CATS, bookAmounts: { 固定资产: null } })
    expect(m[0][0].value).toBeNull()
    expect(m[0][0].origin).toBe('absent')
    expect(m[0][0].sourceHint).toContain('无该科目')
  })

  it('账面金额为 0 → 比例返 null（不产出 Infinity）', () => {
    const rows = [row({ account_type: '固定资产', amount: 100, confirmed_amount: 100 })]
    const m = buildH0SummaryMatrix({ rows, categories: CATS, bookAmounts: { 固定资产: 0 } })
    expect(m[0][0].value).toBe(0)
    expect(m[0][2].value).toBeNull()
    expect(m[0][7].value).toBeNull()
  })

  it('发函金额为 0 → R34 返 null（不产出 NaN）', () => {
    const m = buildH0SummaryMatrix({ rows: [], categories: CATS, bookAmounts: { 固定资产: 100 } })
    expect(m[0][1].value).toBe(0)
    expect(m[0][4].value).toBeNull()
  })

  it('PBT：任意金额组合下每格恒为 有限数 或 null', () => {
    const amt = () => fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            account_type: fc.constantFrom('固定资产', '工程物资', '', '其他'),
            amount: amt(),
            confirmed_amount: amt(),
            alt_confirmed: amt(),
          }),
          { maxLength: 12 },
        ),
        fc.option(amt(), { nil: null }),
        (rawRows, book) => {
          const m = buildH0SummaryMatrix({
            rows: rawRows.map((r) => row(r as Partial<ConfirmationRow>)),
            categories: CATS,
            bookAmounts: { 固定资产: book },
          })
          for (const catCells of m) {
            for (const c of catCells) {
              expect(c.value === null || Number.isFinite(c.value)).toBe(true)
            }
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  it('非有限的手工覆盖值被忽略（回落自动取数）', () => {
    const m = buildH0SummaryMatrix({
      rows: [],
      categories: CATS,
      bookAmounts: { 固定资产: 500 },
      manualOverrides: { [h0MatrixOverrideItemId('cat_1', 0)]: Number.POSITIVE_INFINITY },
    })
    expect(m[0][0].value).toBe(500)
    expect(m[0][0].origin).toBe('auto')
  })
})

// ─── 手工覆盖优先 ────────────────────────────────────────────────────────────

describe('账面金额：手工覆盖 > 自动取数', () => {
  it('手工覆盖生效且 origin=manual', () => {
    const m = buildH0SummaryMatrix({
      rows: [],
      categories: CATS,
      bookAmounts: { 固定资产: 500 },
      manualOverrides: { [h0MatrixOverrideItemId('cat_1', 0)]: 777.5 },
    })
    expect(m[0][0].value).toBe(777.5)
    expect(m[0][0].origin).toBe('manual')
  })

  it('覆盖 itemId 形态 `H0-1-matrix-{categoryKey}-{metricIndex}`', () => {
    expect(h0MatrixOverrideItemId('cat_3', 0)).toBe('H0-1-matrix-cat_3-0')
  })
})

// ─── Property 6: 品种列 key 稳定且不用 label ────────────────────────────────

describe('Property 6: 品种列 key 稳定、重名不撞键', () => {
  it('默认列 key 形态 `cat_{n}`', () => {
    for (const c of createDefaultH0Categories()) {
      expect(c.key).toMatch(/^cat_\d+$/)
    }
  })

  it('两个同名品种建列后 key 不相等（反向自检：key 取 label 必撞）', () => {
    let cats = createDefaultH0Categories()
    const dup = { key: nextH0CategoryKey(cats, maxH0CategorySeq(cats)), label: '固定资产' }
    cats = [...cats, dup]
    const keys = cats.map((c) => c.key)
    expect(new Set(keys).size).toBe(keys.length)
    // 反向自检：若 key 取 label，同名即撞键
    const byLabel = cats.map((c) => c.label)
    expect(new Set(byLabel).size).toBeLessThan(byLabel.length)
  })

  it('删列后再增列不复用旧 key（持久化计数器）', () => {
    let cats = createDefaultH0Categories() // cat_1..cat_3
    const seq = maxH0CategorySeq(cats)
    expect(seq).toBe(3)
    cats = cats.filter((c) => c.key !== 'cat_3')
    // 🔴 传入持久化计数器 → 不复用 cat_3
    expect(nextH0CategoryKey(cats, seq)).toBe('cat_4')
  })

  it('反向自检：不传计数器会复用旧 key（正是需要持久化计数器的原因）', () => {
    const cats = createDefaultH0Categories().filter((c) => c.key !== 'cat_3')
    expect(nextH0CategoryKey(cats)).toBe('cat_3')
  })

  it('parseH0Seq：脏数据回退 0', () => {
    expect(parseH0Seq(undefined)).toBe(0)
    expect(parseH0Seq('')).toBe(0)
    expect(parseH0Seq('abc')).toBe(0)
    expect(parseH0Seq('-2')).toBe(0)
    expect(parseH0Seq('7')).toBe(7)
    expect(parseH0Seq('7.9')).toBe(7)
  })

  it('parseH0Categories：脏数据/空值回退默认列', () => {
    expect(parseH0Categories(null)).toEqual(createDefaultH0Categories())
    expect(parseH0Categories([])).toEqual(createDefaultH0Categories())
    expect(parseH0Categories([{ key: 'bad', label: 'x' }])).toEqual(createDefaultH0Categories())
    expect(parseH0Categories([{ key: 'cat_1', label: '' }])).toEqual(createDefaultH0Categories())
  })

  it('parseH0Categories：去重且保留合法项', () => {
    const out = parseH0Categories([
      { key: 'cat_2', label: '使用权资产' },
      { key: 'cat_2', label: '重复key' },
      { key: 'cat_5', label: '租赁负债' },
    ])
    expect(out).toEqual([
      { key: 'cat_2', label: '使用权资产' },
      { key: 'cat_5', label: '租赁负债' },
    ])
  })
})

// ─── 表格投影 ────────────────────────────────────────────────────────────────

describe('toH0MatrixTableRows', () => {
  it('8 行，每行按 categoryKey 索引', () => {
    const m = buildH0SummaryMatrix({ rows: [], categories: CATS })
    const trs = toH0MatrixTableRows(m)
    expect(trs).toHaveLength(8)
    expect(Object.keys(trs[0].cells)).toEqual(['cat_1', 'cat_2'])
    expect(trs[0].editable).toBe(true)
    expect(trs[2].kind).toBe('ratio')
    expect(trs[1].kind).toBe('amount')
  })

  it('零品种列时返回 8 行空 cells（不崩）', () => {
    const trs = toH0MatrixTableRows(buildH0SummaryMatrix({ rows: [], categories: [] }))
    expect(trs).toHaveLength(8)
    expect(trs[0].cells).toEqual({})
  })
})

// ─── 覆盖率红线 ──────────────────────────────────────────────────────────────

describe('detectH0CoverageAlerts', () => {
  it('R37 低于阈值时按 warn/error 分级', () => {
    const rows = [row({ account_type: '固定资产', amount: 100, confirmed_amount: 30, alt_confirmed: 0 })]
    const m = buildH0SummaryMatrix({ rows, categories: CATS, bookAmounts: { 固定资产: 100 } })
    const alerts = detectH0CoverageAlerts(m)
    expect(alerts).toHaveLength(1)
    expect(alerts[0].categoryLabel).toBe('固定资产')
    expect(alerts[0].level).toBe('error') // 0.3 < 0.5
  })

  it('R37 为 null（账面缺失）不产生告警（不拿未知当低覆盖）', () => {
    const m = buildH0SummaryMatrix({ rows: [], categories: CATS, bookAmounts: {} })
    expect(detectH0CoverageAlerts(m)).toEqual([])
  })

  it('达标不告警', () => {
    const rows = [row({ account_type: '固定资产', amount: 100, confirmed_amount: 95, alt_confirmed: 5 })]
    const m = buildH0SummaryMatrix({ rows, categories: CATS, bookAmounts: { 固定资产: 100 } })
    expect(detectH0CoverageAlerts(m)).toEqual([])
  })
})
