import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useI6Detail, I6_DETAIL_DEFAULT_CATEGORIES, allocateTbNetToDetailRows } from '../useI6Detail'

describe('useI6Detail', () => {
  it('初始化为 Excel 默认费用类别行', () => {
    const allResponses = ref(new Map<string, any>())
    const onSave = vi.fn()
    const { rows } = useI6Detail({ allResponses, onSave })
    expect(rows.value.length).toBe(I6_DETAIL_DEFAULT_CATEGORIES.length)
    expect(rows.value[0].category).toBe('人工费')
    expect(rows.value[0].unadjTotal).toBe(0)
  })

  it('从旧版 I6-2-rows 迁移到 I6-2-detail-rows', () => {
    const allResponses = ref(new Map<string, any>([
      ['I6-2-rows', {
        remark: JSON.stringify([
          { rowId: 'r1', name: '人工费', code: 'RD-01', months: [100, 200, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], total: 300 },
        ]),
      }],
    ]))
    const onSave = vi.fn()
    const { rows } = useI6Detail({ allResponses, onSave })
    expect(rows.value[0].category).toBe('人工费')
    expect(rows.value[0].unadjTotal).toBe(300)
    expect(onSave).toHaveBeenCalledWith('I6-2-detail-rows', expect.any(String))
  })

  it('计算各月比例与审定合计', () => {
    const allResponses = ref(new Map<string, any>([
      ['I6-2-detail-rows', {
        remark: JSON.stringify([
          { id: 'r1', category: '人工费', months: [100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], aje: 0, rje: 0, priorUnadj: 0, priorAje: 0, priorRje: 0, individualReclass: 0, consolidatedReclass: 0, reconciliation: '', remark: '' },
          { id: 'r2', category: '材料费', months: [0, 0, 200, 0, 0, 0, 0, 0, 0, 0, 0, 0], aje: 0, rje: 0, priorUnadj: 0, priorAje: 0, priorRje: 0, individualReclass: 0, consolidatedReclass: 0, reconciliation: '', remark: '' },
        ]),
      }],
    ]))
    const { totalRow, monthlyRatios } = useI6Detail({ allResponses })
    expect(totalRow.value.auditedAmount).toBe(400)
    expect(monthlyRatios.value[0]).toBeCloseTo(25, 1)
    expect(monthlyRatios.value[1]).toBeCloseTo(25, 1)
    expect(monthlyRatios.value[2]).toBeCloseTo(50, 1)
  })

  it('allocateTbNetToDetailRows 按上期审定占比分配至 12 月', () => {
    const rows = [
      { id: 'r1', category: '人工费', expenseNature: '人工费', months: new Array(12).fill(0), aje: 0, rje: 0, reconciliation: '', priorUnadj: 600, priorAje: 0, priorRje: 0, individualReclass: 0, consolidatedReclass: 0, remark: '' },
      { id: 'r2', category: '材料费', expenseNature: '材料费', months: new Array(12).fill(0), aje: 0, rje: 0, reconciliation: '', priorUnadj: 400, priorAje: 0, priorRje: 0, individualReclass: 0, consolidatedReclass: 0, remark: '' },
    ]
    const { rows: next, allocated } = allocateTbNetToDetailRows(rows, 1000)
    expect(allocated[0]).toBeCloseTo(600, 1)
    expect(allocated[1]).toBeCloseTo(400, 1)
    expect(next[0].months[11]).toBeCloseTo(600, 1)
    expect(next[1].months[11]).toBeCloseTo(400, 1)
  })

  it('applyTbData 从 tbData 写入未审发生额', () => {
    const allResponses = ref(new Map<string, any>())
    const onSave = vi.fn()
    const tbData = ref({ unadjusted6602: 500 })
    const { applyTbData, rows } = useI6Detail({ allResponses, onSave, tbData })
    const r = applyTbData()
    expect(r.ok).toBe(true)
    const total = rows.value.reduce((s, row) => s + row.unadjTotal, 0)
    expect(total).toBeCloseTo(500, 1)
    expect(onSave).toHaveBeenCalled()
  })
})
