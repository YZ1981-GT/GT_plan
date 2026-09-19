/**
 * f2DataResourceInventory — 「确认为存货的数据资源」表纯函数模型
 *
 * 覆盖 design Property 3~5 + 空态 + 子项超额告警
 * Spec: .kiro/specs/f2-inventory-disclosure-template-alignment/ R3
 */
import { describe, it, expect } from 'vitest'
import {
  buildDataResourceRows,
  buildDataResourceSyncRows,
  buildDataResourceTieChecks,
  calcDrEnding,
  calcDrTotals,
  checkDrSubExcess,
  isDataResourceEmpty,
  setDrCell,
  DR_COL_LABELS,
  F2_DR_ROW_COUNT,
  type DrValueMap,
} from '../composables/f2DataResourceInventory'

function rowOf(rows: ReturnType<typeof buildDataResourceRows>, key: string) {
  const r = rows.find((x) => x.rowKey === key)
  if (!r) throw new Error(`row ${key} not found`)
  return r
}

describe('f2DataResourceInventory 结构', () => {
  it('21 行，段标题/录入/其中/公式四类齐备', () => {
    expect(F2_DR_ROW_COUNT).toBe(21)
    const rows = buildDataResourceRows({}, 'listed')
    expect(rows).toHaveLength(21)
    expect(rows.filter((r) => r.kind === 'section').map((r) => r.label)).toEqual([
      '一、账面原值', '二、存货跌价准备', '三、账面价值',
    ])
    expect(rows.filter((r) => r.kind === 'derived').map((r) => r.label)).toEqual([
      '4.期末余额', '4.期末余额', '1.期末账面价值', '2.期初账面价值',
    ])
    // 「其中」子项缩进
    expect(rowOf(rows, 'gross-inc-purchase').indent).toBe(1)
    expect(rowOf(rows, 'gross-open').indent).toBe(0)
  })

  it('国企版第二段标题为「二、跌价准备」（上市为「二、存货跌价准备」）', () => {
    expect(rowOf(buildDataResourceRows({}, 'soe'), 'imp-section').label).toBe('二、跌价准备')
    expect(rowOf(buildDataResourceRows({}, 'listed'), 'imp-section').label).toBe('二、存货跌价准备')
  })

  it('列头逐字取自附注模版', () => {
    expect(DR_COL_LABELS.purchased).toBe('外购的数据资源存货')
    expect(DR_COL_LABELS.selfProcessed).toBe('自行加工的数据资源存货')
    expect(DR_COL_LABELS.other).toBe('其他方式取得的数据资源存货')
    expect(DR_COL_LABELS.total).toBe('合计')
  })
})

describe('Property 3 合计列 = 外购 + 自行加工 + 其他方式（F9-11）', () => {
  it('calcDrTotals 逐行求和', () => {
    expect(calcDrTotals({ purchased: 100, selfProcessed: 250, other: 50 })).toBe(400)
    expect(calcDrTotals({ purchased: 0, selfProcessed: 0, other: 0 })).toBe(0)
  })

  it('每行 total 等于三列之和', () => {
    const values: DrValueMap = {
      'gross-open': { purchased: 100, selfProcessed: 250, other: 50 },
      'gross-inc': { purchased: 30, selfProcessed: 10, other: 5 },
    }
    const rows = buildDataResourceRows(values, 'listed')
    for (const r of rows) {
      if (r.kind === 'section') continue
      expect(r.total).toBeCloseTo(r.purchased + r.selfProcessed + r.other, 10)
    }
    expect(rowOf(rows, 'gross-open').total).toBe(400)
  })
})

describe('Property 4 期末递推（F9-7 / F9-8）', () => {
  it('calcDrEnding = 期初 + 增加 − 减少', () => {
    expect(calcDrEnding(100, 30, 10)).toBe(120)
    expect(calcDrEnding(0, 0, 0)).toBe(0)
  })

  it('账面原值段与跌价准备段逐列独立递推', () => {
    const values: DrValueMap = {
      'gross-open': { purchased: 100, selfProcessed: 200, other: 0 },
      'gross-inc': { purchased: 40, selfProcessed: 10, other: 7 },
      'gross-dec': { purchased: 15, selfProcessed: 0, other: 2 },
      'imp-open': { purchased: 10, selfProcessed: 20, other: 0 },
      'imp-inc': { purchased: 6, selfProcessed: 1, other: 0 },
      'imp-dec': { purchased: 4, selfProcessed: 0, other: 0 },
    }
    const rows = buildDataResourceRows(values, 'listed')
    const grossEnd = rowOf(rows, 'gross-end')
    expect(grossEnd.purchased).toBe(125)   // 100 + 40 - 15
    expect(grossEnd.selfProcessed).toBe(210)
    expect(grossEnd.other).toBe(5)
    expect(grossEnd.total).toBe(340)

    const impEnd = rowOf(rows, 'imp-end')
    expect(impEnd.purchased).toBe(12)      // 10 + 6 - 4
    expect(impEnd.selfProcessed).toBe(21)
    expect(impEnd.other).toBe(0)
  })
})

describe('Property 5 账面价值（F9-9 / F9-9a）', () => {
  it('期末账面价值 = 原值期末 − 跌价期末；期初同理', () => {
    const values: DrValueMap = {
      'gross-open': { purchased: 100, selfProcessed: 200, other: 0 },
      'gross-inc': { purchased: 40, selfProcessed: 10, other: 7 },
      'gross-dec': { purchased: 15, selfProcessed: 0, other: 2 },
      'imp-open': { purchased: 10, selfProcessed: 20, other: 0 },
      'imp-inc': { purchased: 6, selfProcessed: 1, other: 0 },
      'imp-dec': { purchased: 4, selfProcessed: 0, other: 0 },
    }
    const rows = buildDataResourceRows(values, 'listed')
    const nvEnd = rowOf(rows, 'nv-end')
    expect(nvEnd.purchased).toBe(113)      // 125 - 12
    expect(nvEnd.selfProcessed).toBe(189)  // 210 - 21
    expect(nvEnd.other).toBe(5)

    const nvOpen = rowOf(rows, 'nv-open')
    expect(nvOpen.purchased).toBe(90)      // 100 - 10
    expect(nvOpen.selfProcessed).toBe(180) // 200 - 20
    expect(nvOpen.other).toBe(0)
  })
})

describe('「其中」子项与父项（F9-10 为校验非公式）', () => {
  it('子项不自动汇总到父项：父项保持独立录入值', () => {
    const values: DrValueMap = {
      'gross-inc': { purchased: 100 },
      'gross-inc-purchase': { purchased: 30 },
      'gross-inc-collect': { purchased: 20 },
    }
    const rows = buildDataResourceRows(values, 'listed')
    expect(rowOf(rows, 'gross-inc').purchased).toBe(100)
    expect(rowOf(rows, 'gross-inc').subExcess).toBe(false)
  })

  it('checkDrSubExcess：子项之和 > 父项 → true（0.01 容差）', () => {
    expect(checkDrSubExcess(100, [30, 20])).toBe(false)
    expect(checkDrSubExcess(100, [60, 40])).toBe(false)  // 相等不算超额
    expect(checkDrSubExcess(100, [60, 41])).toBe(true)
    expect(checkDrSubExcess(100, [60, 40.005])).toBe(false) // 容差内
  })

  it('父项行标记 subExcess，不阻断其它行', () => {
    const values: DrValueMap = {
      'gross-dec': { purchased: 10 },
      'gross-dec-sale': { purchased: 8 },
      'gross-dec-invalid': { purchased: 9 },
    }
    const rows = buildDataResourceRows(values, 'listed')
    expect(rowOf(rows, 'gross-dec').subExcess).toBe(true)
    expect(rowOf(rows, 'gross-inc').subExcess).toBe(false)
  })
})

describe('空态与写入', () => {
  it('isDataResourceEmpty：全 0 / null / 仅派生行有值 → true', () => {
    expect(isDataResourceEmpty(null)).toBe(true)
    expect(isDataResourceEmpty({})).toBe(true)
    expect(isDataResourceEmpty({ 'gross-open': { purchased: 0, selfProcessed: 0, other: 0 } })).toBe(true)
  })

  it('isDataResourceEmpty：任一录入行非 0 → false', () => {
    expect(isDataResourceEmpty({ 'imp-dec-writeoff': { other: 1 } })).toBe(false)
  })

  it('setDrCell 只写可录入行，派生/段标题行静默忽略', () => {
    const v0: DrValueMap = {}
    const v1 = setDrCell(v0, 'gross-open', 'purchased', 500)
    expect(v1['gross-open']?.purchased).toBe(500)

    expect(setDrCell(v1, 'gross-end', 'purchased', 999)).toBe(v1)
    expect(setDrCell(v1, 'gross-section', 'purchased', 999)).toBe(v1)
    // 原对象不被就地修改
    expect(v0['gross-open']).toBeUndefined()
  })

  it('setDrCell 归一非数字输入为 0', () => {
    const v = setDrCell({}, 'imp-inc', 'other', '' as unknown as number)
    expect(v['imp-inc']?.other).toBe(0)
  })
})

describe('与 (1) 分类表交叉勾稽（F9-12/12a/13/13a）', () => {
  const filled: DrValueMap = {
    'gross-open': { purchased: 100, selfProcessed: 250, other: 0 },  // 合计 350
    'gross-inc': { purchased: 40, selfProcessed: 0, other: 0 },
    'gross-dec': { purchased: 15, selfProcessed: 0, other: 0 },      // 期末 375
    'imp-open': { purchased: 10, selfProcessed: 0, other: 0 },       // 合计 10
    'imp-inc': { purchased: 2, selfProcessed: 0, other: 0 },         // 期末 12
  }

  it('四条勾稽全对时 ok 均为 true', () => {
    const checks = buildDataResourceTieChecks(
      filled,
      { endGross: 375, endImpairment: 12, priorGross: 350, priorImpairment: 10 },
      'listed',
    )
    expect(checks.map((c) => c.preset)).toEqual(['F9-12', 'F9-12a', 'F9-13', 'F9-13a'])
    expect(checks.every((c) => c.ok)).toBe(true)
    expect(checks.every((c) => c.diff === 0)).toBe(true)
  })

  it('分类表与明细不一致时给出差额与失败标记', () => {
    const checks = buildDataResourceTieChecks(
      filled,
      { endGross: 300, endImpairment: 12, priorGross: 350, priorImpairment: 10 },
      'listed',
    )
    const grossEnd = checks.find((c) => c.key === 'gross-end')!
    expect(grossEnd.ok).toBe(false)
    expect(grossEnd.detail).toBe(375)
    expect(grossEnd.classified).toBe(300)
    expect(grossEnd.diff).toBe(75)
    // 其余三条仍勾稽
    expect(checks.filter((c) => !c.ok)).toHaveLength(1)
  })

  it('差异 < 0.01 视为勾稽通过（分位舍入容差）', () => {
    const checks = buildDataResourceTieChecks(
      filled,
      { endGross: 375.005, endImpairment: 12, priorGross: 350, priorImpairment: 10 },
      'listed',
    )
    expect(checks.find((c) => c.key === 'gross-end')!.ok).toBe(true)
  })

  it('本表全空时返回空数组（未编制不报错）', () => {
    expect(
      buildDataResourceTieChecks({}, { endGross: 999, endImpairment: 9, priorGross: 9, priorImpairment: 9 }, 'listed'),
    ).toEqual([])
    expect(buildDataResourceTieChecks(null, null, 'soe')).toEqual([])
  })

  it('分类表行缺失时按 0 比对，不抛错', () => {
    const checks = buildDataResourceTieChecks(filled, null, 'listed')
    expect(checks).toHaveLength(4)
    expect(checks.find((c) => c.key === 'gross-end')!.classified).toBe(0)
    expect(checks.find((c) => c.key === 'gross-end')!.ok).toBe(false)
  })

  it('期初口径文案随版本切换（上市「上年年末」/ 国企「期初」）', () => {
    const listed = buildDataResourceTieChecks(filled, null, 'listed')
    expect(listed.find((c) => c.key === 'gross-open')!.label).toBe('账面原值上年年末余额')
    const soe = buildDataResourceTieChecks(filled, null, 'soe')
    expect(soe.find((c) => c.key === 'gross-open')!.label).toBe('账面原值期初余额')
  })
})

describe('同步载荷行', () => {
  it('键名与 columns 的 key 对齐，行序即模板行序', () => {
    const rows = buildDataResourceRows({ 'gross-open': { purchased: 100 } }, 'listed')
    const sync = buildDataResourceSyncRows(rows)
    expect(sync).toHaveLength(21)
    expect(sync[0].label).toBe('一、账面原值')
    expect(Object.keys(sync[1])).toEqual(['label', 'purchased', 'self_processed', 'other', 'total'])
    expect(sync[1].purchased).toBe(100)
    expect(sync[1].total).toBe(100)
  })
})
