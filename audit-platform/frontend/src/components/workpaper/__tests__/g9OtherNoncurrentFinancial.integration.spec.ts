/**
 * G9 其他非流动金融资产 — 集成测试
 */
import { describe, it, expect } from 'vitest'
import {
  G9_ACCOUNT_CODE,
  G9_ADJUDICATION_ITEMS,
  G9_DISCLOSURE_LISTED_ROWS,
  G9_DISCLOSURE_SOE_ROWS,
  G9_IMPORTABLE_SHEETS,
  G9_VIRTUAL_SCROLL_THRESHOLD,
} from '../composables/g9Constants'
import { extractG9SheetCode, jumpToG9Sheet } from '../composables/g9SheetLabels'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcEndingBalance,
  calcFairValueDiff,
  calcChangeRate,
  calcL3Reconciliation,
  calcL3Variance,
  isDebitCreditBalanced,
} from '../composables/useG9FormulaEngine'
import { validateG9Level3 } from '../composables/useG9FairValueTest'
import { deriveAbnormal, G9A_VOUCHER_PROGRAM_NOS } from '../composables/useG9VoucherCheck'
import { aggregateG9AdjustmentAjeRje, applyG9AdjustmentWriteback, defaultG9AdjStore } from '../composables/g9AdjStorage'

describe('G9 集成 — sheetName 分发', () => {
  it('10 个有效 sheet 编码', () => {
    expect(extractG9SheetCode('审定表G9-1')).toBe('G9-1')
    expect(extractG9SheetCode('其他非流动金融资产实质性程序表G9A')).toBe('G9A')
    expect(extractG9SheetCode('明细表G9-2')).toBe('G9-2')
    expect(extractG9SheetCode('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractG9SheetCode('附注披露信息（国企）')).toBe('附注国企')
    expect(extractG9SheetCode('底稿目录')).toBe('底稿目录')
  })

  it('jumpToG9Sheet 调用 jumpFn', () => {
    expect(jumpToG9Sheet('G9A', null)).toBe(false)
    const calls: string[] = []
    expect(jumpToG9Sheet('G9-6', (n) => { calls.push(n) })).toBe(true)
    expect(calls[0]).toContain('凭证检查')
  })

  it('G9A 凭证程序含 6/7/12', () => {
    expect([...G9A_VOUCHER_PROGRAM_NOS]).toEqual([6, 7, 12])
  })
})

describe('G9 集成 — 借方公式', () => {
  it('calcDebitBalance 资产方向', () => {
    expect(calcDebitBalance(100, 50, 20)).toBe(130)
  })

  it('审定数 AJE+RJE', () => {
    expect(calcAdjustedAmount(1000, 200, -50)).toBe(1150)
  })

  it('期末余额 6 因子（OCI=0）', () => {
    expect(calcEndingBalance(100, 30, 10, 5, 2, 3)).toBe(124)
  })

  it('期末余额含 OCI', () => {
    expect(calcEndingBalance(100, 30, 10, 5, 2, 3, 4)).toBe(128)
  })

  it('L3 调节 10 因子', () => {
    expect(calcL3Reconciliation(100, 20, 5, 3, 2, 4, 1, 2, 1, 0)).toBe(122)
  })

  it('L3 差异为零', () => {
    const closing = calcL3Reconciliation(100, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    expect(calcL3Variance(closing, closing)).toBe(0)
  })
})

describe('G9 集成 — 种子行数', () => {
  it('审定表按 Excel 分类口径（FVTPL8+FVOCI4+摊余3）', () => {
    expect(G9_ADJUDICATION_ITEMS.length).toBe(15)
    expect(G9_ADJUDICATION_ITEMS.filter((r) => r.category === 'FVTPL').length).toBe(8)
    expect(G9_ADJUDICATION_ITEMS.some((r) => r.isGroupTotal && r.rowKey === 'fvtpl_1')).toBe(true)
    expect(G9_ADJUDICATION_ITEMS.some((r) => r.label.includes('指定为以公允价值计量'))).toBe(true)
  })

  it('上市附注 4 行（xlsx schema）', () => {
    expect(G9_DISCLOSURE_LISTED_ROWS.length).toBe(4)
    expect(G9_DISCLOSURE_LISTED_ROWS[0].label).toBe('债务工具投资')
  })

  it('国企附注 4 行', () => {
    expect(G9_DISCLOSURE_SOE_ROWS.length).toBe(4)
  })

  it('7 张表可导入导出（含附注上市/国企）', () => {
    expect(G9_IMPORTABLE_SHEETS.map((s) => s.code)).toEqual([
      'G9-2', 'G9-3', 'G9-4', 'G9-5', 'G9-6', '附注上市', '附注国企',
    ])
  })

  it('科目代码 1519', () => {
    expect(G9_ACCOUNT_CODE).toBe('1519')
  })
})

describe('G9 集成 — Level3 + 异常检测', () => {
  it('Level3 缺估值技术', () => {
    const errs = validateG9Level3({
      rowId: '1', seq: 1, assetName: 'x', initialInvestDate: '',
      closingUnadjustedQty: 0, closingUnadjustedPrice: 0, closingUnadjustedFV: 0,
      closingAuditedQty: 0, closingAuditedPrice: 0, closingAuditedFV: 0,
      fairValueLevel: 'Level3', valuationMethod: '', methodConsistentWithPrior: 'yes',
      valuationSource: '', inputSourceAndAdjustment: '', valuationTechnique: '',
      unobservableInputDesc: '', unobservableInputValue: '', nonLiquidityDiscount: 0,
      valuationDocIndex: '',
    })
    expect(errs.length).toBeGreaterThan(0)
  })

  it('核对项 false → 异常', () => {
    const abnormal = deriveAbnormal({
      rowId: '1', seq: 1, voucherDate: '', voucherNo: '1', businessContent: '',
      counterAccount: '', debitAmount: 0, creditAmount: 0, attachmentRef: '',
      supportDoc: '', checkOriginal: true, checkAuthorized: true, checkAccounting: true,
      checkClassification: true, checkFairValue: false, checkImpairment: true,
      indexRef: '', isAbnormal: false, forceAbnormal: false, abnormalType: 'none',
      abnormalDesc: '', riskLevel: 'low', suggestion: '', remark: '',
      detailRowId: '', assetName: '',
    })
    expect(abnormal).toBe(true)
  })

  it('未测不计入异常', () => {
    const abnormal = deriveAbnormal({
      rowId: '2', seq: 1, voucherDate: '', voucherNo: '2', businessContent: '',
      counterAccount: '', debitAmount: 0, creditAmount: 0, attachmentRef: '',
      supportDoc: '', checkOriginal: null, checkAuthorized: null, checkAccounting: null,
      checkClassification: null, checkFairValue: null, checkImpairment: null,
      indexRef: '', isAbnormal: false, forceAbnormal: false, abnormalType: 'none',
      abnormalDesc: '', riskLevel: 'low', suggestion: '', remark: '',
      detailRowId: '', assetName: '',
    })
    expect(abnormal).toBe(false)
  })
})

describe('G9 集成 — reasonRequired + 虚拟滚动阈值', () => {
  it('变动率超阈值需填原因', () => {
    const rate = calcChangeRate(100, 150)
    expect(rate).toBe(0.5)
    const reasonRequired = rate != null && Math.abs(rate) > 0.2
    expect(reasonRequired).toBe(true)
  })

  it('G9-6 虚拟滚动阈值 50', () => {
    expect(G9_VIRTUAL_SCROLL_THRESHOLD).toBe(50)
  })
})

describe('G9 集成 — parseNum + 变动率', () => {
  it('parseNum 健壮性', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(42)).toBe(42)
  })

  it('calcChangeRate 除零保护', () => {
    expect(calcChangeRate(0, 100)).toBeNull()
  })

  it('借贷平衡', () => {
    expect(isDebitCreditBalanced([100, 50], [150])).toBe(true)
    expect(isDebitCreditBalanced([100], [90])).toBe(false)
  })

  it('calcFairValueDiff', () => {
    expect(calcFairValueDiff(110, 100)).toBe(10)
  })
})

describe('G9 集成 — G9-3 AJE/RJE 回写', () => {
  it('aggregateG9AdjustmentAjeRje 分项汇总', () => {
    const wb = aggregateG9AdjustmentAjeRje([
      { entryType: 'AJE', accountCode: '1504', debitAmount: 100, creditAmount: 0 },
      { entryType: 'RJE', accountCode: '1504', debitAmount: 0, creditAmount: 30 },
    ])
    expect(wb.closingAje).toBe(100)
    expect(wb.closingRje).toBe(-30)
    expect(wb.rowKey).toBe('fvtpl_1')
  })

  it('applyG9AdjustmentWriteback 写入审定行', () => {
    const store = defaultG9AdjStore()
    const next = applyG9AdjustmentWriteback(store, { rowKey: 'fvtpl_1', closingAje: 200, closingRje: -50 })
    expect(next.fvtpl_1?.closingAJE).toBe(200)
    expect(next.fvtpl_1?.closingRJE).toBe(-50)
  })
})
