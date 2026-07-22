/**
 * H10 资产处置损益 — 集成测试
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcIncomeStatementNet,
  calcChangeRate,
  isChangeRateExceeding,
  calcSubtotal,
} from '../composables/useH10FormulaEngine'
import {
  calcDisposalGainLoss,
  calcNetBookValue,
} from '../composables/useH10DisposalCalcEngine'
import { H10_ADJUDICATION_ITEMS, H10_CHANGE_RATE_THRESHOLD, H10_DISCLOSURE_LISTED_ROWS, H10_DISCLOSURE_SOE_ROWS } from '../composables/h10Constants'
import { extractH10SheetCode, getH10SourceTraceStatus } from '../composables/h10SheetLabels'
import { H10_SOURCE_WP_TO_ROW_KEY } from '../composables/useH10CrossSheet'
import { H10_IMPORTABLE_SHEETS } from '../composables/useH10ImportExport'
import { calcH10AdjustmentNet, aggregateH10AdjustmentAjeRje } from '../composables/h10AdjStorage'

describe('H10 集成 — sheetName 分发', () => {
  it('8 个有效 sheet 正确分发', () => {
    expect(extractH10SheetCode('资产处置损益实质性程序表H10A')).toBe('H10A')
    expect(extractH10SheetCode('审定表H10-1')).toBe('H10-1')
    expect(extractH10SheetCode('明细表H10-2')).toBe('H10-2')
    expect(extractH10SheetCode('调整分录汇总H10-3')).toBe('H10-3')
    expect(extractH10SheetCode('检查表H10-4')).toBe('H10-4')
    expect(extractH10SheetCode('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractH10SheetCode('附注披露信息（国有企业）')).toBe('附注国企')
    expect(extractH10SheetCode('底稿目录')).toBe('底稿目录')
  })
})

describe('H10 集成 — 审定表行数与公式', () => {
  it('H10-1 审定表 10 数据行（含使用权/油气/试运行）', () => {
    expect(H10_ADJUDICATION_ITEMS.length).toBe(10)
    expect(H10_ADJUDICATION_ITEMS[0].rowKey).toBe('hfs_disposal')
    expect(H10_ADJUDICATION_ITEMS[6].rowKey).toBe('non_monetary_exchange')
    expect(H10_ADJUDICATION_ITEMS[7].rowKey).toBe('rou_disposal')
    expect(H10_ADJUDICATION_ITEMS[8].rowKey).toBe('oil_gas_disposal')
    expect(H10_ADJUDICATION_ITEMS[9].rowKey).toBe('trial_operation_sales')
  })

  it('审定数 = 未审 + AJE + RJE', () => {
    expect(calcAuditedAmount(100, 10, 5)).toBe(115)
    expect(calcAuditedAmount(80, -5, 2)).toBe(77)
  })

  it('损益类净发生额 贷−借', () => {
    expect(calcIncomeStatementNet(500, 200)).toBe(300)
    expect(calcIncomeStatementNet(100, 150)).toBe(-50)
  })

  it('变动率>20% 触发高亮', () => {
    const rate = calcChangeRate(100, 130)
    expect(rate).toBeCloseTo(0.3)
    expect(isChangeRateExceeding(rate, H10_CHANGE_RATE_THRESHOLD)).toBe(true)
  })
})

describe('H10 集成 — 处置计算', () => {
  it('净值 = 原值 − 累计折旧 − 减值', () => {
    expect(calcNetBookValue(1000, 400)).toBe(600)
    expect(calcNetBookValue(1000, 400, 100)).toBe(500)
  })

  it('处置净损益 = 收入 − 净值 − 费用 − 税费', () => {
    expect(calcDisposalGainLoss(800, 600, 50, 30)).toBe(120)
    expect(calcDisposalGainLoss(400, 600, 20, 10)).toBe(-230)
  })
})

describe('H10 集成 — 附注披露行数', () => {
  it('上市附注与审定同分项（含试运行）', () => {
    expect(H10_DISCLOSURE_LISTED_ROWS.length).toBe(10)
    expect(H10_DISCLOSURE_LISTED_ROWS.map((r) => r.rowKey)).toContain('trial_operation_sales')
    expect(H10_DISCLOSURE_LISTED_ROWS.map((r) => r.rowKey)).toContain('rou_disposal')
    expect(H10_DISCLOSURE_LISTED_ROWS.map((r) => r.rowKey)).not.toContain('listed_sub_dr')
  })

  it('国企附注与审定同分项（含试运行）', () => {
    expect(H10_DISCLOSURE_SOE_ROWS.length).toBe(10)
    expect(H10_DISCLOSURE_SOE_ROWS.map((r) => r.rowKey)).toContain('oil_gas_disposal')
    expect(H10_DISCLOSURE_SOE_ROWS.map((r) => r.rowKey)).toContain('trial_operation_sales')
    expect(H10_DISCLOSURE_SOE_ROWS.map((r) => r.rowKey)).not.toContain('soe_sub_dr')
  })
})

describe('H10 集成 — 导入导出', () => {
  it('H10-2 / H10-3 可导入导出', () => {
    expect(H10_IMPORTABLE_SHEETS.map((s) => s.code)).toEqual(['H10-2', 'H10-3'])
  })
})

describe('H10 集成 — H10-3 调整回写', () => {
  it('6115 贷方净额 = 贷 − 借', () => {
    const net = calcH10AdjustmentNet([
      { accountCode: '6115', debitAmount: 0, creditAmount: 100 },
      { accountCode: '6115', debitAmount: 30, creditAmount: 0 },
    ])
    expect(net).toBe(70)
  })

  it('AJE/RJE 分别汇总', () => {
    const wb = aggregateH10AdjustmentAjeRje([
      { entryType: 'AJE', accountCode: '6115', debitAmount: 0, creditAmount: 50 },
      { entryType: 'RJE', accountCode: '6115', debitAmount: 10, creditAmount: 0 },
    ])
    expect(wb.currentAje).toBe(50)
    expect(wb.currentRje).toBe(-10)
    expect(wb.rowKey).toBe('fixed_asset_disposal')
  })

  it('非 6115 行不计入净额', () => {
    const net = calcH10AdjustmentNet([
      { accountCode: '6115', debitAmount: 0, creditAmount: 50 },
      { accountCode: '1001', debitAmount: 50, creditAmount: 0 },
    ])
    expect(net).toBe(50)
  })
})

describe('H10 集成 — 底稿目录追溯链', () => {
  it('getH10SourceTraceStatus 含 H6 与来源底稿', () => {
    const m = new Map<string, any>([
      ['H10-detail-rows', { remark: JSON.stringify([{ sourceWp: 'H1', linkageId: 'h1-1', disposalGainLoss: 100 }]) }],
    ])
    const trace = getH10SourceTraceStatus(m)
    expect(trace.some((t) => t.wpCode === 'H6')).toBe(true)
    expect(trace.find((t) => t.wpCode === 'H1')?.status).toBe('done')
  })
})

describe('H10 集成 — 跨底稿映射', () => {
  it('SOURCE_WP_TO_ROW_KEY：H8=使用权、I1=无形资产', () => {
    expect(H10_SOURCE_WP_TO_ROW_KEY.H1).toBe('fixed_asset_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.H2).toBe('construction_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.H5).toBe('oil_gas_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.H6).toBe('fixed_asset_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.H7).toBe('productive_bio_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.H8).toBe('rou_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.I1).toBe('intangible_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.DR).toBe('debt_restructuring_disposal')
    expect(H10_SOURCE_WP_TO_ROW_KEY.NM).toBe('non_monetary_exchange')
  })
})

describe('H10 集成 — parseNum', () => {
  it('健壮性', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(42.5)).toBe(42.5)
  })

  it('合计行恒等', () => {
    expect(calcSubtotal([10, 20, 30])).toBe(60)
  })
})
