/**
 * useH4Detail — H4-2 明细表公式与分类小计单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  recomputeH4DetailRow,
  buildCategorySubtotals,
  useH4Detail,
  type H4DetailRow,
} from '../useH4Detail'
import { calcUnitPrice, calcNetBookValue } from '../useH4FormulaEngine'

function baseRow(partial: Partial<H4DetailRow> = {}): H4DetailRow {
  return recomputeH4DetailRow({
    rowId: 'r1',
    category: '专用材料',
    name: '水泥',
    spec: '',
    unit: '吨',
    supplier: '',
    beginQty: 10,
    increaseQty: 5,
    decreaseQty: 3,
    endQty: 0,
    beginAmount: 10000,
    purchaseAmount: 4000,
    otherIncrease: 1000,
    increaseSubtotal: 0,
    usageAmount: 2000,
    returnAmount: 0,
    scrapAmount: 500,
    otherDecrease: 0,
    decreaseTotal: 0,
    endAmount: 0,
    beginUnitPrice: null,
    increaseUnitPrice: null,
    decreaseUnitPrice: null,
    endUnitPrice: null,
    ajeBegin: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
    auditedBegin: 0,
    auditedIncrease: 0,
    auditedDecrease: 0,
    auditedEnd: 0,
    impairBegin: 200,
    impairIncrease: 100,
    impairDecrease: 0,
    impairEnd: 0,
    ajeImpair: 50,
    auditedImpairEnd: 0,
    bookValueBegin: 0,
    bookValueEnd: 0,
    auditedBookValue: 0,
    bookValueDiff: 0,
    aging: '',
    quality: '',
    ...partial,
  })
}

describe('calcUnitPrice / calcNetBookValue', () => {
  it('数量为0时单价返回 null（防 #DIV/0!）', () => {
    expect(calcUnitPrice(100, 0)).toBeNull()
    expect(calcUnitPrice(100, 10)).toBe(10)
  })

  it('净值 = 原值 - 跌价', () => {
    expect(calcNetBookValue(1000, 200)).toBe(800)
  })
})

describe('recomputeH4DetailRow', () => {
  it('原值/数量 rollforward + 审定 + 减值净值闭环', () => {
    const r = baseRow()
    // 增加 5000，减少 2500 → 期末 12500；数量 10+5-3=12
    expect(r.increaseSubtotal).toBe(5000)
    expect(r.decreaseTotal).toBe(2500)
    expect(r.endAmount).toBe(12500)
    expect(r.endQty).toBe(12)
    expect(r.beginUnitPrice).toBe(1000)
    expect(r.endUnitPrice).toBeCloseTo(12500 / 12, 5)

    expect(r.auditedBegin).toBe(10000)
    expect(r.auditedIncrease).toBe(5000)
    expect(r.auditedDecrease).toBe(2500)
    expect(r.auditedEnd).toBe(12500)

    expect(r.impairEnd).toBe(300)
    expect(r.auditedImpairEnd).toBe(350)
    expect(r.bookValueEnd).toBe(12200)
    expect(r.auditedBookValue).toBe(12150)
    expect(r.bookValueDiff).toBe(50)
  })

  it('AJE 改变审定三角勾稽', () => {
    const r = baseRow({ ajeIncrease: 200, ajeDecrease: -50 })
    expect(r.auditedIncrease).toBe(5200)
    expect(r.auditedDecrease).toBe(2450)
    expect(r.auditedEnd).toBe(10000 + 5200 - 2450)
  })

  it('数量为0时单价为 null', () => {
    const r = baseRow({ beginQty: 0, beginAmount: 100 })
    expect(r.beginUnitPrice).toBeNull()
  })
})

describe('buildCategorySubtotals', () => {
  it('按分类汇总（对齐 SUMPRODUCT）', () => {
    const a = baseRow({ rowId: 'a', category: '专用材料', endAmount: 0 })
    const b = baseRow({
      rowId: 'b',
      category: '专用材料',
      beginAmount: 5000,
      purchaseAmount: 0,
      otherIncrease: 0,
      usageAmount: 0,
      scrapAmount: 0,
      impairBegin: 0,
      impairIncrease: 0,
      ajeImpair: 0,
    })
    const c = baseRow({ rowId: 'c', category: '设备', beginAmount: 2000, purchaseAmount: 0, otherIncrease: 0, usageAmount: 0, scrapAmount: 0, impairBegin: 0, impairIncrease: 0, ajeImpair: 0 })
    const subs = buildCategorySubtotals([a, b, c])
    expect(subs).toHaveLength(2)
    const mat = subs.find(s => s.category === '专用材料')!
    expect(mat.rowCount).toBe(2)
    expect(mat.beginAmount).toBe(15000)
    const eq = subs.find(s => s.category === '设备')!
    expect(eq.rowCount).toBe(1)
    expect(eq.beginAmount).toBe(2000)
  })
})

describe('useH4Detail composable', () => {
  it('加载旧字段并重算；updateCell 持久化含 endAmount', () => {
    const map = ref(new Map<string, any>())
    map.value.set('H4-2-rows', {
      item_id: 'H4-2-rows',
      remark: JSON.stringify([{
        rowId: 'old1',
        name: '旧物资',
        category: '材料',
        quantity: 8,
        beginAmount: 8000,
        purchaseAmount: 2000,
        usageAmount: 1000,
      }]),
    })
    const saved: Record<string, any> = {}
    const { rows, updateCell, subtotalRow } = useH4Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
      onSave: (id, val) => { saved[id] = val },
    })

    expect(rows.value).toHaveLength(1)
    expect(rows.value[0].endAmount).toBe(9000)
    expect(rows.value[0].endQty).toBe(8)

    updateCell(rows.value[0].rowId, 'ajeBegin', 100)
    expect(rows.value[0].auditedBegin).toBe(8100)
    expect(Array.isArray(saved['H4-2-rows'])).toBe(true)
    expect(saved['H4-2-rows'][0].endAmount).toBe(9000)
    expect(saved['H4-2-detail-total']).toBe(9000)
    expect(subtotalRow.value.auditedBegin).toBe(8100)
  })

  it('pushAjeToH43 / pullAjeFromH43 双向闭环', () => {
    const map = ref(new Map<string, any>())
    map.value.set('H4-2-rows', {
      item_id: 'H4-2-rows',
      remark: JSON.stringify([{
        rowId: 'd1',
        name: '电缆',
        beginAmount: 1000,
        ajeBegin: 100,
        ajeImpair: 20,
      }]),
    })
    const saved: Record<string, any> = {}
    const api = useH4Detail({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
      onSave: (id, val) => {
        saved[id] = val
        map.value.set(id, { item_id: id, remark: JSON.stringify(val), conclusion: null })
      },
    })

    const pushed = api.pushAjeToH43()
    expect(pushed.ok).toBe(true)
    expect(pushed.added).toBe(4) // begin pair + impair pair
    expect(Array.isArray(saved['H4-3-rows'])).toBe(true)

    // 改 H4-3 后回写
    const h43 = saved['H4-3-rows'].map((r: any) => {
      if (String(r.remark).includes('kind=begin') && String(r.accountCode).startsWith('1605')) {
        return { ...r, debitAmount: 150, creditAmount: 0 }
      }
      if (String(r.remark).includes('kind=begin') && r.accountCode === '4104') {
        return { ...r, debitAmount: 0, creditAmount: 150 }
      }
      return r
    })
    map.value.set('H4-3-rows', { item_id: 'H4-3-rows', remark: JSON.stringify(h43), conclusion: null })

    const pulled = api.pullAjeFromH43()
    expect(pulled.ok).toBe(true)
    expect(api.rows.value[0].ajeBegin).toBe(150)
  })
})
