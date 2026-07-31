/**
 * H7 生产性生物资产披露模型守卫（派生公式 + 类别 key 稳定性）。
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 9 — Property 3/4/5)
 */
import { describe, expect, it } from 'vitest'
import fc from 'fast-check'
import {
  H7_COST_MOVEMENT_ROWS,
  H7_FAIR_MOVEMENT_ROWS,
  H7_INDUSTRIES,
  createDefaultH7Categories,
  emptyMovement,
  h7CellValue,
  h7TotalCellValue,
  isH7EditableRow,
  nextH7CategoryKey,
  orderH7Categories,
  setCell,
  type H7ListedCategory,
  type MovementCellMap,
} from '../h7ListedDisclosureModel'
import {
  H7_SOE_INDUSTRIES,
  assertIndustryParity,
  buildSoeDisplayRows,
  createDefaultSoeBlocks,
  grandTotal,
  industryTotals,
  isIndustryEditable,
  nextSoeCategoryId,
  soeEnd,
  type H7SoeIndustryBlock,
} from '../h7SoeDisclosureModel'

const rowOf = (rows: readonly { key: string }[], key: string) =>
  rows.find((r) => r.key === key)!

function costWith(values: Record<string, number>, col = 'crop_1'): MovementCellMap {
  let map = emptyMovement()
  for (const [k, v] of Object.entries(values)) map = setCell(map, k, col, v)
  return map
}

const cost = (map: MovementCellMap, key: string, col = 'crop_1') =>
  h7CellValue(map, rowOf(H7_COST_MOVEMENT_ROWS, key), col, H7_COST_MOVEMENT_ROWS)

const fair = (map: MovementCellMap, key: string, col = 'crop_1') =>
  h7CellValue(map, rowOf(H7_FAIR_MOVEMENT_ROWS, key), col, H7_FAIR_MOVEMENT_ROWS)

// ─────────────────────────────────────────────────────────────────────

describe('P3 类别列 key 稳定性', () => {
  it('默认每产业 1 个类别列，key 唯一且不等于 label', () => {
    const cats = createDefaultH7Categories()
    expect(cats).toHaveLength(4)
    expect(new Set(cats.map((c) => c.key)).size).toBe(4)
    // 四个产业默认叶子名都是源模板字面「类别」→ 用 label 作 key 会撞键
    expect(new Set(cats.map((c) => c.label))).toEqual(new Set(['类别']))
    expect(cats.map((c) => c.key)).toEqual([
      'crop_1', 'livestock_1', 'forestry_1', 'aquatic_1',
    ])
  })

  it('新增 key 取该产业最大 seq + 1，删中间项后剩余 key 不变、新 key 不复用', () => {
    let cats = createDefaultH7Categories()
    const k2 = nextH7CategoryKey(cats, 'crop')
    expect(k2).toBe('crop_2')
    cats = [...cats, { key: k2, label: '苹果树', industry: 'crop' }]
    const k3 = nextH7CategoryKey(cats, 'crop')
    expect(k3).toBe('crop_3')
    cats = [...cats, { key: k3, label: '梨树', industry: 'crop' }]

    // 删中间的 crop_2
    const after = cats.filter((c) => c.key !== 'crop_2')
    expect(after.map((c) => c.key)).toEqual([
      'crop_1', 'livestock_1', 'forestry_1', 'aquatic_1', 'crop_3',
    ])
    // 新增不得复用已删除的 crop_2
    expect(nextH7CategoryKey(after, 'crop')).toBe('crop_4')
  })

  it('orderH7Categories 按源模板列序（产业顺序 → 产业内原序）', () => {
    const cats: H7ListedCategory[] = [
      { key: 'aquatic_1', label: '鱼', industry: 'aquatic' },
      { key: 'crop_2', label: '梨树', industry: 'crop' },
      { key: 'crop_1', label: '苹果树', industry: 'crop' },
    ]
    expect(orderH7Categories(cats).map((c) => c.key)).toEqual([
      'crop_2', 'crop_1', 'aquatic_1',
    ])
  })

  it('产业口径两侧一致（上市 4 产业 ≡ 国企 4 产业）', () => {
    expect(assertIndustryParity()).toBe(true)
    expect(H7_INDUSTRIES.map((i) => i.key)).toEqual(H7_SOE_INDUSTRIES.map((i) => i.key))
  })
})

describe('P4 上市成本模式派生公式（34 行四层）', () => {
  it('行集 34 行，section/派生行不可录入，`……` 行可录入', () => {
    expect(H7_COST_MOVEMENT_ROWS).toHaveLength(34)
    const editable = H7_COST_MOVEMENT_ROWS.filter(isH7EditableRow).map((r) => r.key)
    expect(editable).toContain('cost_dec_ellipsis')
    expect(editable).not.toContain('cost_inc')
    expect(editable).not.toContain('cost_section')
    expect(editable).not.toContain('book_end')
  })

  it('小计 = 分项之和；期末 = 期初 + 增 − 减', () => {
    const map = costWith({
      cost_begin: 1000,
      cost_inc_purchase: 300, cost_inc_self: 120, cost_inc_other: 30,
      cost_dec_dispose: 200, cost_dec_other: 50, cost_dec_ellipsis: 10,
    })
    expect(cost(map, 'cost_inc')).toBe(450)
    expect(cost(map, 'cost_dec')).toBe(260)
    expect(cost(map, 'cost_end')).toBe(1190)
  })

  it('`……` 行确实参与本期减少小计（可扩明细行不是装饰）', () => {
    const without = costWith({ cost_dec_dispose: 100 })
    expect(cost(without, 'cost_dec')).toBe(100)
    const withEllipsis = costWith({ cost_dec_dispose: 100, cost_dec_ellipsis: 25 })
    expect(cost(withEllipsis, 'cost_dec')).toBe(125)
  })

  it('账面价值 = 原值 − 累计折旧 − 减值准备（期末与期初同口径）', () => {
    const map = costWith({
      cost_begin: 1000, cost_inc_purchase: 200, cost_dec_dispose: 100,
      dep_begin: 300, dep_inc_provision: 60, dep_dec_dispose: 10,
      imp_begin: 50, imp_inc_provision: 20,
    })
    expect(cost(map, 'cost_end')).toBe(1100)
    expect(cost(map, 'dep_end')).toBe(350)
    expect(cost(map, 'imp_end')).toBe(70)
    expect(cost(map, 'book_end')).toBe(1100 - 350 - 70)
    expect(cost(map, 'book_begin')).toBe(1000 - 300 - 50)
  })

  it('section 行恒 0（含合计列）', () => {
    const map = costWith({ cost_begin: 999 })
    expect(cost(map, 'cost_section')).toBe(0)
    const cats = createDefaultH7Categories()
    expect(
      h7TotalCellValue(map, rowOf(H7_COST_MOVEMENT_ROWS, 'cost_section'), cats, H7_COST_MOVEMENT_ROWS),
    ).toBe(0)
  })

  it('合计列 = 各类别列之和', () => {
    const cats = createDefaultH7Categories()
    let map = emptyMovement()
    map = setCell(map, 'cost_begin', 'crop_1', 100)
    map = setCell(map, 'cost_begin', 'livestock_1', 250)
    map = setCell(map, 'cost_begin', 'forestry_1', 30)
    expect(
      h7TotalCellValue(map, rowOf(H7_COST_MOVEMENT_ROWS, 'cost_begin'), cats, H7_COST_MOVEMENT_ROWS),
    ).toBe(380)
  })

  it('PBT：期末 = 期初 + Σ增 − Σ减（金额域内恒成立）', () => {
    const amt = () => fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
    fc.assert(
      fc.property(amt(), amt(), amt(), amt(), amt(), amt(), (b, i1, i2, d1, d2, d3) => {
        const map = costWith({
          cost_begin: b,
          cost_inc_purchase: i1, cost_inc_self: i2,
          cost_dec_dispose: d1, cost_dec_other: d2, cost_dec_ellipsis: d3,
        })
        const expected = b + (i1 + i2) - (d1 + d2 + d3)
        expect(Math.abs(cost(map, 'cost_end') - expected)).toBeLessThan(1e-6)
      }),
      { numRuns: 25 },
    )
  })
})

describe('P4 上市公允价值模式派生公式（11 行）', () => {
  it('行集 11 行且含 2 个可扩明细行', () => {
    expect(H7_FAIR_MOVEMENT_ROWS).toHaveLength(11)
    expect(H7_FAIR_MOVEMENT_ROWS.filter((r) => r.kind === 'ellipsis')).toHaveLength(2)
  })

  it('本期变动 = 加项 − 减项 + 公允价值变动 + 其他变动；期末 = 期初 + 本期变动', () => {
    let map = emptyMovement()
    const put = (k: string, v: number) => { map = setCell(map, k, 'crop_1', v) }
    put('fair_begin', 5000)
    put('fair_add_purchase', 800)
    put('fair_add_self', 200)
    put('fair_add_merge', 100)
    put('fair_add_ellipsis', 50)
    put('fair_less_dispose', 300)
    put('fair_less_other', 100)
    put('fair_fv_change', 400)
    put('fair_fv_ellipsis', 20)

    // 加项：800+200+100+50 + 400 + 20 = 1570；减项：300+100 = 400
    expect(fair(map, 'fair_change')).toBe(1570 - 400)
    expect(fair(map, 'fair_end')).toBe(5000 + 1170)
  })

  it('公允价值变动为负（跌价）时期末相应减少', () => {
    let map = emptyMovement()
    map = setCell(map, 'fair_begin', 'crop_1', 1000)
    map = setCell(map, 'fair_fv_change', 'crop_1', -250)
    expect(fair(map, 'fair_change')).toBe(-250)
    expect(fair(map, 'fair_end')).toBe(750)
  })

  it('空表全 0，不抛错', () => {
    const empty = emptyMovement()
    for (const def of H7_FAIR_MOVEMENT_ROWS) {
      expect(h7CellValue(empty, def, 'crop_1', H7_FAIR_MOVEMENT_ROWS)).toBe(0)
    }
  })
})

describe('P5 国企派生与可扩类别行', () => {
  function blocksWith(cost: Partial<Record<string, unknown>> = {}): H7SoeIndustryBlock[] {
    const b = createDefaultSoeBlocks()
    Object.assign(b[0], cost)
    return b
  }

  it('默认 4 产业无类别 → 产业行可直接录入', () => {
    const b = createDefaultSoeBlocks()
    expect(b).toHaveLength(4)
    expect(b.every(isIndustryEditable)).toBe(true)
    expect(buildSoeDisplayRows(b)).toHaveLength(5) // 4 产业 + 合计
  })

  it('产业行有类别时 = 类别之和且转为只读', () => {
    const b = blocksWith({
      categories: [
        { id: 'crop-1', name: '苹果树', begin: 100, increase: 30, decrease: 10 },
        { id: 'crop-2', name: '梨树', begin: 200, increase: 0, decrease: 50 },
      ],
      selfAmounts: { begin: 9999, increase: 9999, decrease: 9999 },
    })
    const t = industryTotals(b[0])
    expect(t).toEqual({ begin: 300, increase: 30, decrease: 60 })
    expect(isIndustryEditable(b[0])).toBe(false)
    // selfAmounts 在有类别时被忽略（不参与派生）
    expect(t.begin).not.toBe(9999)
  })

  it('无类别时取 selfAmounts', () => {
    const b = blocksWith({ selfAmounts: { begin: 500, increase: 20, decrease: 5 } })
    expect(industryTotals(b[0])).toEqual({ begin: 500, increase: 20, decrease: 5 })
  })

  it('期末账面价值 = 期初 + 增 − 减（读时派生）', () => {
    expect(soeEnd({ begin: 500, increase: 20, decrease: 5 })).toBe(515)
    const b = blocksWith({ selfAmounts: { begin: 500, increase: 20, decrease: 5 } })
    const rows = buildSoeDisplayRows(b)
    expect(rows[0].end).toBe(515)
  })

  it('合计 = 4 产业行之和', () => {
    const b = createDefaultSoeBlocks()
    b[0].selfAmounts = { begin: 100, increase: 10, decrease: 1 }
    b[1].categories = [{ id: 'livestock-1', name: '奶牛', begin: 200, increase: 20, decrease: 2 }]
    b[2].selfAmounts = { begin: 300, increase: 30, decrease: 3 }
    expect(grandTotal(b)).toEqual({ begin: 600, increase: 60, decrease: 6 })
    const rows = buildSoeDisplayRows(b)
    const total = rows[rows.length - 1]
    expect(total.kind).toBe('total')
    expect(total.begin).toBe(600)
    expect(total.end).toBe(654)
  })

  it('行序 = 4 产业（各自后跟类别行）+ 合计，与源模板 R9–R21 同构', () => {
    const b = createDefaultSoeBlocks()
    b[0].categories = [{ id: 'crop-1', name: '苹果树', begin: 1, increase: 0, decrease: 0 }]
    b[3].categories = [{ id: 'aquatic-1', name: '鱼', begin: 2, increase: 0, decrease: 0 }]
    expect(buildSoeDisplayRows(b).map((r) => r.label)).toEqual([
      '一、种植业', '苹果树',
      '二、畜牧养殖业',
      '三、林业',
      '四、水产业', '鱼',
      '合计',
    ])
  })

  it('类别 id 取最大 seq + 1，删中间不复用', () => {
    const b = createDefaultSoeBlocks()
    expect(nextSoeCategoryId(b[0], 'crop')).toBe('crop-1')
    b[0].categories = [
      { id: 'crop-1', name: 'a', begin: 0, increase: 0, decrease: 0 },
      { id: 'crop-2', name: 'b', begin: 0, increase: 0, decrease: 0 },
    ]
    expect(nextSoeCategoryId(b[0], 'crop')).toBe('crop-3')
    b[0].categories = b[0].categories.filter((c) => c.id !== 'crop-1')
    expect(nextSoeCategoryId(b[0], 'crop')).toBe('crop-3')
  })

  it('删除最后一个类别行后产业行转为可录入且不清零 selfAmounts', () => {
    const b = blocksWith({
      selfAmounts: { begin: 77, increase: 0, decrease: 0 },
      categories: [{ id: 'crop-1', name: 'a', begin: 5, increase: 0, decrease: 0 }],
    })
    expect(isIndustryEditable(b[0])).toBe(false)
    b[0].categories = []
    expect(isIndustryEditable(b[0])).toBe(true)
    expect(industryTotals(b[0]).begin).toBe(77)
  })
})
