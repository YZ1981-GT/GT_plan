/**
 * nCycleLane3RowIdentity.spec.ts — N2 / N5 整表 JSON 行身份（BP-8 收口）
 *
 * spec: n2-n5-json-table-identity-and-cross-entry-readonly · Task 4 / 9
 *
 * 每张表都验同一条 Property 23 判据：**删中间行 / 改某行后，其它行的数据不串到别的行上**，
 * 以及「旧数据无身份字段」时派生出确定性身份（computed 重算不漂移）。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, effectScope } from 'vue'

import { useN5TaxAdjustment } from '../useN5TaxAdjustment'
import { useN5DeferredReconcile } from '../useN5DeferredReconcile'
import { useN5RdSuperDeduction } from '../useN5RdSuperDeduction'
import { useN2OtherTaxCalc } from '../useN2OtherTaxCalc'
import { assignStableRowKeys, duplicateRowKeys } from '../shared/stableRowIdentity'

vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))

function n5Options(itemId: string, rows: any[] | null, column: 'conclusion' | 'remark' = 'conclusion') {
  const all = ref(new Map<string, any>())
  if (rows) all.value.set(itemId, { item_id: itemId, [column]: JSON.stringify(rows) })
  return {
    all,
    opts: {
      allResponses: all as any,
      wpId: ref('wp'),
      projectId: ref('p'),
      saveField: vi.fn(async () => {}),
      getField: () => null,
    },
  }
}

describe('assignStableRowKeys', () => {
  it('确定性：同一输入两次派生结果相同（computed 重算不漂移）', () => {
    const raw = [{ code: 'A1' }, { code: 'A2' }, {}]
    expect(assignStableRowKeys(raw, (r: any) => r.code)).toEqual(
      assignStableRowKeys(raw, (r: any) => r.code))
  })
  it('已落库身份优先；重复语义键按出现顺序追加 #n', () => {
    const keys = assignStableRowKeys(
      [{ rowKey: 'k1', label: 'x' }, { label: '同名' }, { label: '同名' }],
      (r: any) => r.label)
    expect(keys).toEqual(['k1', 'row-同名', 'row-同名#2'])
  })
})

describe('N5-5 纳税调整（useN5TaxAdjustment）', () => {
  const rows = [
    { code: 'A010000', label: '视同销售收入', category: '收入类', basis: '甲', isFixed: false },
    { code: 'A080000', label: '业务招待费', category: '扣除类', basis: '乙', isFixed: false },
    { code: 'A120000', label: '罚款', category: '扣除类', basis: '丙', isFixed: false },
  ]

  it('旧数据无身份 ⇒ 以申报表编码派生语义键', () => {
    const { opts } = n5Options('N5-5-adjustment-rows', rows)
    const adj = useN5TaxAdjustment(opts)
    expect(adj.rows.value.map(r => r.rowKey)).toEqual(['row-A010000', 'row-A080000', 'row-A120000'])
  })

  it('删中间行后，第三行 basis 不左移串到第二行', async () => {
    const { opts, all } = n5Options('N5-5-adjustment-rows', rows)
    const adj = useN5TaxAdjustment(opts)
    await adj.removeRow('row-A080000')
    const after = useN5TaxAdjustment({ ...opts, allResponses: all as any })
    expect(after.rows.value.map(r => [r.rowKey, r.basis])).toEqual([
      ['row-A010000', '甲'], ['row-A120000', '丙'],
    ])
  })

  it('按身份改行：改的就是那一行', async () => {
    const { opts } = n5Options('N5-5-adjustment-rows', rows)
    const adj = useN5TaxAdjustment(opts)
    await adj.updateRow('row-A120000', 'basis', '改')
    expect(adj.rows.value.find(r => r.rowKey === 'row-A120000')?.basis).toBe('改')
    expect(adj.rows.value.find(r => r.rowKey === 'row-A010000')?.basis).toBe('甲')
  })

  it('固定行不可删', async () => {
    const { opts } = n5Options('N5-5-adjustment-rows', null)
    const adj = useN5TaxAdjustment(opts)
    const first = adj.rows.value[0].rowKey
    await adj.removeRow(first)
    expect(adj.rows.value[0].rowKey).toBe(first)
  })

  it('载荷落在 remark 列也能读到（双列取列）', () => {
    const { opts } = n5Options('N5-5-adjustment-rows', rows, 'remark')
    expect(useN5TaxAdjustment(opts).rows.value).toHaveLength(3)
  })
})

describe('N5-8 递延核对（useN5DeferredReconcile）', () => {
  it('删中间行不串行', async () => {
    const data = ['坏账准备', '存货跌价准备', '预计负债'].map((label, i) => ({ label, remark: `r${i}` }))
    const { opts, all } = n5Options('N5-8-reconcile-rows', data)
    const scope = effectScope()
    try {
      const rec = scope.run(() => useN5DeferredReconcile(opts))!
      await rec.removeRow('row-存货跌价准备')
      const after = scope.run(() => useN5DeferredReconcile({ ...opts, allResponses: all as any }))!
      expect(after.rows.value.map(r => [r.label, r.remark])).toEqual([['坏账准备', 'r0'], ['预计负债', 'r2']])
    } finally {
      scope.stop()
    }
  })
})

describe('N5-6-1 研发加计（useN5RdSuperDeduction）', () => {
  it('资本化子表里改「第 1 行」不会改到费用化第 1 行', async () => {
    const data = [
      { projectName: '项目甲', personnelCost: 1, isExpensed: true },
      { projectName: '项目乙', personnelCost: 2, isExpensed: false },
    ]
    const { opts } = n5Options('N5-6-1-rd-projects', data)
    const rd = useN5RdSuperDeduction(opts)
    const capFirst = rd.rows.value.filter(r => !r.isExpensed)[0]
    await rd.updateRow(capFirst.rowKey, 'personnelCost', 99)
    expect(rd.rows.value.find(r => r.projectName === '项目甲')?.personnelCost).toBe(1)
    expect(rd.rows.value.find(r => r.projectName === '项目乙')?.personnelCost).toBe(99)
  })

  it('重名项目身份不重复', () => {
    const { opts } = n5Options('N5-6-1-rd-projects', [{ projectName: 'X' }, { projectName: 'X' }])
    expect(duplicateRowKeys(useN5RdSuperDeduction(opts).rows.value)).toEqual([])
  })
})

describe('N2-8 手工税种（useN2OtherTaxCalc）', () => {
  function make(stored: any[] | null) {
    const all = ref(new Map<string, any>())
    if (stored) all.value.set('N2-8-manual-rows', { item_id: 'N2-8-manual-rows', conclusion: JSON.stringify(stored) })
    const saveField = vi.fn(async (itemId: string, v: any) => {
      all.value.set(itemId, { item_id: itemId, ...v })
      all.value = new Map(all.value)
    })
    const calc = useN2OtherTaxCalc({ allResponses: all as any, saveField, getField: () => null })
    return { calc, all }
  }

  it('默认 4 税种用税种语义键；渲染 key 与持久化身份同源（不再是 manual-${idx}）', () => {
    const { calc } = make(null)
    expect(calc.manualRows.value.map(r => r.rowKey)).toEqual(
      ['row-消费税', 'row-资源税', 'row-城镇土地使用税', 'row-车船税'])
    expect(calc.manualCalcRows.value.map(r => r.key)).toEqual(calc.manualRows.value.map(r => r.rowKey))
  })

  it('旧数据（无身份、按位置存）按税种名对上骨架，不按位置错配', () => {
    // 旧存储里顺序被打乱：车船税在第 0 位
    const { calc } = make([{ taxType: '车船税', remark: '车' }, { taxType: '消费税', remark: '消' }])
    expect(calc.manualRows.value.find(r => r.taxType === '车船税')?.remark).toBe('车')
    expect(calc.manualRows.value.find(r => r.taxType === '消费税')?.remark).toBe('消')
  })

  it('按身份改追加行，不影响默认行；删除后回到原集合', async () => {
    const { calc } = make(null)
    await calc.addManualRow('印花税')
    const extra = calc.manualRows.value[4]
    await calc.updateManualRow(extra.rowKey, 'remark', '追加')
    expect(calc.manualRows.value[4].remark).toBe('追加')
    expect(calc.manualRows.value.slice(0, 4).every(r => r.remark === '')).toBe(true)
    expect(duplicateRowKeys(calc.manualRows.value)).toEqual([])
    await calc.removeManualRow(extra.rowKey)
    expect(calc.manualRows.value).toHaveLength(4)
    // 默认 4 税种不可删
    await calc.removeManualRow('row-消费税')
    expect(calc.manualRows.value).toHaveLength(4)
  })
})
