/**
 * useH4Impairment / H4-7 减值测算公式与跨表逻辑单测
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, computed } from 'vue'
import {
  calcRecoverableAmount,
  calcRequiredProvision,
  calcPeriodImpairmentAdjustment,
} from '../composables/useH4FormulaEngine'
import {
  recalcH4ImpairmentCalcRow,
  buildH47ImpairmentAjePair,
  buildH47ConclusionDraft,
  useH4Impairment,
  H47_AJE_MARKER,
  type H4ImpairmentCalcRow,
} from '../composables/useH4Impairment'

function emptyRow(partial: Partial<H4ImpairmentCalcRow> = {}): H4ImpairmentCalcRow {
  return {
    rowId: 'r1',
    category: '',
    name: '',
    hasSign: '',
    signDesc: '',
    bookValue: 0,
    fairValueNet: 0,
    pvCashFlows: 0,
    recoverableAmount: 0,
    requiredProvision: 0,
    bookedProvision: 0,
    periodAdjustment: 0,
    wpIndex: '',
    remark: '',
    ...partial,
  }
}

describe('H4-7 impairment formulas', () => {
  it('⑤ = MAX(③,④)', () => {
    expect(calcRecoverableAmount(100, 80)).toBe(100)
    expect(calcRecoverableAmount(50, 90)).toBe(90)
    expect(calcRecoverableAmount(0, 0)).toBe(0)
  })

  it('⑥ = MAX(②−⑤, 0) — 修正表头⑤−②笔误', () => {
    expect(calcRequiredProvision(100, 80)).toBe(20)
    expect(calcRequiredProvision(80, 100)).toBe(0)
    expect(calcRequiredProvision(100, 100)).toBe(0)
  })

  it('⑧ = ⑥ − ⑦', () => {
    expect(calcPeriodImpairmentAdjustment(20, 5)).toBe(15)
    expect(calcPeriodImpairmentAdjustment(10, 15)).toBe(-5)
  })

  it('无迹象时⑧=0（维持已提）', () => {
    const row = emptyRow({
      hasSign: '否',
      bookValue: 100,
      fairValueNet: 40,
      pvCashFlows: 30,
      bookedProvision: 12,
    })
    recalcH4ImpairmentCalcRow(row)
    expect(row.recoverableAmount).toBe(100)
    expect(row.requiredProvision).toBe(12)
    expect(row.periodAdjustment).toBe(0)
  })

  it('有迹象时按 Excel 公式链计算', () => {
    const row = emptyRow({
      hasSign: '是',
      bookValue: 200,
      fairValueNet: 120,
      pvCashFlows: 150,
      bookedProvision: 10,
    })
    recalcH4ImpairmentCalcRow(row)
    expect(row.recoverableAmount).toBe(150)
    expect(row.requiredProvision).toBe(50)
    expect(row.periodAdjustment).toBe(40)
  })
})

describe('buildH47ImpairmentAjePair', () => {
  it('生成借6701/贷1605减值准备，并带自动草稿标记', () => {
    const pair = buildH47ImpairmentAjePair({ materialName: '螺纹钢', amount: 1234.5, seqStart: 3 })
    expect(pair).toHaveLength(2)
    expect(pair[0].accountCode).toBe('6701')
    expect(pair[0].debitAmount).toBe(1234.5)
    expect(pair[1].accountCode).toBe('1605')
    expect(pair[1].creditAmount).toBe(1234.5)
    expect(pair[0].remark).toBe(H47_AJE_MARKER)
    expect(pair[0].refIndex).toBe('H4-7')
  })
})

describe('buildH47ConclusionDraft', () => {
  it('无迹象时输出无需测算结论', () => {
    const text = buildH47ConclusionDraft({
      signYesCount: 0,
      calcCount: 0,
      totalRequired: 0,
      totalBooked: 0,
      totalAdjustment: 0,
      reversalCount: 0,
    })
    expect(text).toContain('未发现工程物资减值迹象')
  })

  it('有测算时包含补提与CAS8不得转回提示', () => {
    const text = buildH47ConclusionDraft({
      signYesCount: 2,
      calcCount: 3,
      totalRequired: 100,
      totalBooked: 40,
      totalAdjustment: 60,
      reversalCount: 1,
    })
    expect(text).toContain('识别减值迹象 2 项')
    expect(text).toContain('不得转回')
  })
})

describe('useH4Impairment composable', () => {
  function setup(mapInit?: Map<string, any>) {
    const allResponses = ref(mapInit ?? new Map())
    const saved: Array<{ id: string; value: any }> = []
    const api = useH4Impairment({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: computed(() => allResponses.value),
      isReadonly: ref(false),
      onSave: (id, value) => {
        saved.push({ id, value })
        const remark = typeof value === 'string' || typeof value === 'number'
          ? String(value)
          : JSON.stringify(value)
        allResponses.value.set(id, { item_id: id, remark, conclusion: null })
      },
    })
    return { api, saved, allResponses }
  }

  it('从 H4-2 带入账面价值', () => {
    const map = new Map()
    map.set('H4-2-rows', {
      remark: JSON.stringify([
        { rowId: 'd1', category: '专用材料', name: '水泥', endAmount: 5000 },
        { rowId: 'd2', category: '设备', name: '塔吊配件', endAmount: 8000 },
      ]),
    })
    const { api } = setup(map)
    const res = api.importFromH42()
    expect(res.ok).toBe(true)
    expect(res.added).toBe(2)
    expect(api.calcRows.value).toHaveLength(2)
    expect(api.calcRows.value[0].bookValue).toBe(5000)
    expect(api.calcRows.value[1].name).toBe('塔吊配件')
  })

  it('自 H4-6 减值关注一键落成测算行', () => {
    const map = new Map()
    map.set('H4-7-stocktake-concerns', {
      remark: JSON.stringify({
        updatedAt: '2026-07-21T00:00:00.000Z',
        items: [
          {
            sourceRowId: 'r1',
            name: '闲置管材',
            assetNo: 'A1',
            bookAmount: 12000,
            reasons: ['闲置'],
            qualityStatus: '闲置',
            result: '账实相符',
            remark: '',
          },
          {
            sourceRowId: 'r2',
            name: '盘亏螺栓',
            bookAmount: 800,
            reasons: ['盘亏'],
            qualityStatus: '',
            result: '盘亏',
            remark: '',
          },
        ],
      }),
    })
    const { api } = setup(map)
    expect(api.stocktakeConcernCount()).toBe(2)
    const res = api.importFromStocktakeConcerns()
    expect(res.added).toBe(2)
    expect(api.calcRows.value).toHaveLength(2)
    expect(api.calcRows.value.every(r => r.hasSign === '是')).toBe(true)
    expect(api.calcRows.value[0].wpIndex).toBe('H4-6')
    // 再次引入应刷新而非重复新增
    const res2 = api.importFromStocktakeConcerns()
    expect(res2.added).toBe(0)
    expect(res2.refreshed).toBe(2)
    expect(api.calcRows.value).toHaveLength(2)
  })

  it('推送补提AJE至 H4-3，并跳过CAS8拟冲回', () => {
    const { api, allResponses } = setup()
    api.addCalcRow('积压电缆')
    api.updateCalcCell(api.calcRows.value[0].rowId, 'hasSign', '是')
    api.updateCalcCell(api.calcRows.value[0].rowId, 'bookValue', 1000)
    api.updateCalcCell(api.calcRows.value[0].rowId, 'fairValueNet', 600)
    api.updateCalcCell(api.calcRows.value[0].rowId, 'bookedProvision', 50)
    // 第二行拟冲回
    api.addCalcRow('过提项')
    api.updateCalcCell(api.calcRows.value[1].rowId, 'hasSign', '是')
    api.updateCalcCell(api.calcRows.value[1].rowId, 'bookValue', 100)
    api.updateCalcCell(api.calcRows.value[1].rowId, 'fairValueNet', 100)
    api.updateCalcCell(api.calcRows.value[1].rowId, 'bookedProvision', 30)

    expect(api.calcRows.value[0].periodAdjustment).toBe(350) // 400-50
    expect(api.calcRows.value[1].periodAdjustment).toBe(-30)

    const res = api.pushAjeDraftToH43()
    expect(res.ok).toBe(true)
    expect(res.added).toBe(2)
    expect(res.skippedReversal).toBe(1)
    const h43 = JSON.parse(allResponses.value.get('H4-3-rows').remark)
    expect(h43).toHaveLength(2)
    expect(h43[0].debitAmount).toBe(350)
    expect(h43[0].category).toBe('账项调整')
    expect(h43[0].indexRef).toBe('H4-7')
    expect(h43.every((r: any) => r.remark === H47_AJE_MARKER)).toBe(true)
  })

  it('同步摘要键供附注消费', () => {
    const { api, allResponses } = setup()
    api.addCalcRow('A')
    api.updateCalcCell(api.calcRows.value[0].rowId, 'hasSign', '是')
    api.updateCalcCell(api.calcRows.value[0].rowId, 'bookValue', 200)
    api.updateCalcCell(api.calcRows.value[0].rowId, 'fairValueNet', 150)
    api.updateCalcCell(api.calcRows.value[0].rowId, 'bookedProvision', 10)
    expect(Number(allResponses.value.get('H4-7-book-value')?.remark)).toBe(200)
    // 本期计提⑧=40；期末应提⑥=50
    expect(Number(allResponses.value.get('H4-7-impairment-loss')?.remark)).toBe(40)
    expect(Number(allResponses.value.get('H4-7-provision-balance')?.remark)).toBe(50)
  })

  it('编制闭环：H4-2带入 → 填③/④ → 推送H4-3 → 核对/回写H4-1 → 附注键', () => {
    const map = new Map()
    map.set('H4-2-rows', {
      remark: JSON.stringify([
        { rowId: 'd1', category: '专用材料', name: '积压水泥', endAmount: 10000 },
      ]),
    })
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        {
          rowId: 'i1', name: '专用材料', section: 'impairment',
          beginUnadjusted: 0, beginAdjustment: 0,
          endUnadjusted: 0, endAdjustment: 0,
        },
      ]),
    })
    const { api, allResponses } = setup(map)

    // ① 从 H4-2 带入
    expect(api.importFromH42().ok).toBe(true)
    expect(api.calcRows.value[0].bookValue).toBe(10000)

    // ② 填③/④
    const id = api.calcRows.value[0].rowId
    api.updateCalcRow(id, {
      hasSign: '是',
      fairValueNet: 6000,
      pvCashFlows: 5500,
      bookedProvision: 0,
    })
    expect(api.calcRows.value[0].recoverableAmount).toBe(6000)
    expect(api.calcRows.value[0].requiredProvision).toBe(4000)
    expect(api.calcRows.value[0].periodAdjustment).toBe(4000)

    // ③ 推送 H4-3
    const aje = api.pushAjeDraftToH43()
    expect(aje.ok).toBe(true)
    expect(aje.amount).toBe(4000)
    const h43 = JSON.parse(allResponses.value.get('H4-3-rows').remark)
    expect(h43).toHaveLength(2)

    // ④ 核对：初始 H4-1 期末0，应有差额
    const before = api.reconcileWithH41()
    expect(before.isMatch).toBe(false)
    expect(before.totalDiff).toBe(4000)

    // 回写 H4-1
    const applied = api.applyRequiredToH41()
    expect(applied.ok).toBe(true)
    const after = api.reconcileWithH41()
    expect(after.isMatch).toBe(true)

    // 附注键
    expect(Number(allResponses.value.get('H4-7-provision-balance')?.remark)).toBe(4000)
    expect(Number(allResponses.value.get('H4-7-impairment-loss')?.remark)).toBe(4000)
  })
})
