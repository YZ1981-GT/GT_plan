/**
 * G8 其他权益工具投资 — 集成测试
 */
import { describe, it, expect } from 'vitest'
import {
  G8_ACCOUNT_CODE,
  G8_ADJUDICATION_ITEMS,
  G8_DISCLOSURE_LISTED_ROWS,
  G8_DISCLOSURE_SOE_ROWS,
  G8_ADJ_WRITEBACK_ROW_KEY,
  G8_CHANGE_RATE_THRESHOLD,
  G8_IMPORTABLE_SHEETS,
  G8_VIRTUAL_SCROLL_THRESHOLD,
} from '../composables/g8Constants'
import { extractG8SheetCode } from '../composables/g8SheetLabels'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcEndingBalance,
  calcFairValueDiff,
  calcChangeRate,
  isDebitCreditBalanced,
} from '../composables/useG8FormulaEngine'
import { validateG8Level3 } from '../composables/useG8FairValueTest'
import { deriveG8Abnormal } from '../composables/useG8VoucherCheck'
import { G8_DESIGNATION_SEED } from '../composables/g8DesignationSeed'
import {
  aggregateG8AdjustmentWriteback,
  applyG8AdjustmentWriteback,
  defaultG8AdjStore,
} from '../composables/g8AdjStorage'

describe('G8 集成 — sheetName 分发', () => {
  it('10 个 HTML sheet 编码', () => {
    expect(extractG8SheetCode('审定表G8-1')).toBe('G8-1')
    expect(extractG8SheetCode('其他权益工具投资实质性程序表G8A')).toBe('G8A')
    expect(extractG8SheetCode('明细表G8-2')).toBe('G8-2')
    expect(extractG8SheetCode('调整分录汇总G8-3')).toBe('G8-3')
    expect(extractG8SheetCode('公允价值测试表G8-4')).toBe('G8-4')
    expect(extractG8SheetCode('指定的适当性检查表G8-5')).toBe('G8-5')
    expect(extractG8SheetCode('凭证检查表G8-6')).toBe('G8-6')
    expect(extractG8SheetCode('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractG8SheetCode('附注披露信息（国企）')).toBe('附注国企')
    expect(extractG8SheetCode('底稿目录')).toBe('底稿目录')
  })
})

describe('G8 集成 — 借方公式', () => {
  it('calcDebitBalance 资产方向', () => {
    expect(calcDebitBalance(100, 50, 20)).toBe(130)
  })

  it('审定数 未审+调整', () => {
    expect(calcAdjustedAmount(1000, 150)).toBe(1150)
  })

  it('期末余额 4 因子', () => {
    expect(calcEndingBalance(100, 30, 10, 5)).toBe(125)
  })
})

describe('G8 集成 — 种子行数', () => {
  it('审定表 10 行（xlsx schema）', () => {
    expect(G8_ADJUDICATION_ITEMS.length).toBe(10)
    expect(G8_ADJUDICATION_ITEMS[0].label).toBe('权益工具投资（FVOCI）')
  })

  it('上市附注 18 行', () => {
    expect(G8_DISCLOSURE_LISTED_ROWS.length).toBe(18)
  })

  it('国企附注 20 行', () => {
    expect(G8_DISCLOSURE_SOE_ROWS.length).toBe(20)
  })

  it('科目代码 1503', () => {
    expect(G8_ACCOUNT_CODE).toBe('1503')
  })

  it('回写目标行 fv_1', () => {
    expect(G8_ADJ_WRITEBACK_ROW_KEY).toBe('fv_1')
  })

  it('4 张表可导入导出', () => {
    expect(G8_IMPORTABLE_SHEETS.map((s) => s.code)).toEqual([
      'G8-2', 'G8-3', 'G8-4', 'G8-6',
    ])
  })

  it('适当性检查种子 36 行', () => {
    expect(G8_DESIGNATION_SEED.length).toBe(36)
  })
})

describe('G8 集成 — Level3 + 异常检测', () => {
  it('Level3 缺估值技术', () => {
    const errs = validateG8Level3({
      rowId: '1', seq: 1, investeeName: 'x', initialInvestDate: '',
      closingUnadjustedQty: 0, closingUnadjustedPrice: 0, closingUnadjustedFV: 0,
      closingAuditedQty: 0, closingAuditedPrice: 0, closingAuditedFV: 0,
      fairValueLevel: 'Level3', valuationMethod: '', methodConsistentWithPrior: 'yes',
      valuationSource: '', inputSourceAndAdjustment: '', valuationTechnique: '',
      unobservableInputDesc: '', unobservableInputValue: '', valuationDocIndex: '',
    })
    expect(errs.length).toBeGreaterThan(0)
  })

  it('Level1/Level2 非必填', () => {
    const errs = validateG8Level3({
      rowId: '1', seq: 1, investeeName: 'x', initialInvestDate: '',
      closingUnadjustedQty: 0, closingUnadjustedPrice: 0, closingUnadjustedFV: 0,
      closingAuditedQty: 0, closingAuditedPrice: 0, closingAuditedFV: 0,
      fairValueLevel: 'Level2', valuationMethod: '', methodConsistentWithPrior: 'yes',
      valuationSource: '', inputSourceAndAdjustment: '', valuationTechnique: '',
      unobservableInputDesc: '', unobservableInputValue: '', valuationDocIndex: '',
    })
    expect(errs.length).toBe(0)
  })

  it('check5 OCI false → 异常', () => {
    const abnormal = deriveG8Abnormal({
      rowId: '1', seq: 1, voucherDate: '', voucherNo: '1', businessContent: '',
      counterAccount: '', debitAmount: 0, creditAmount: 0, attachment: '',
      supportingDocDesc: '', check1OriginalComplete: true, check2Authorization: true,
      check3Accounting: true, check4FairValueCorrect: true, check5OCICorrect: false,
      indexNo: '', isAbnormal: false, abnormalDesc: '', riskLevel: 'low', remark: '',
    })
    expect(abnormal).toBe(true)
  })
})

describe('G8 集成 — reasonRequired + 虚拟滚动阈值', () => {
  it('变动率超阈值需填原因', () => {
    const rate = calcChangeRate(100, 150)
    expect(rate).toBe(0.5)
    const reasonRequired = rate != null && Math.abs(rate) > G8_CHANGE_RATE_THRESHOLD
    expect(reasonRequired).toBe(true)
  })

  it('G8-6 虚拟滚动阈值 50', () => {
    expect(G8_VIRTUAL_SCROLL_THRESHOLD).toBe(50)
  })
})

describe('G8 集成 — parseNum + 公允价值差异', () => {
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

describe('G8 集成 — G8-3 调整回写', () => {
  it('aggregateG8AdjustmentWriteback 净额汇总', () => {
    const wb = aggregateG8AdjustmentWriteback([
      { entryType: 'AJE', accountCode: '1503', debitAmount: 100, creditAmount: 0 },
      { entryType: 'RJE', accountCode: '1503', debitAmount: 0, creditAmount: 30 },
    ])
    expect(wb.closingAdjustment).toBe(70)
    expect(wb.rowKey).toBe('fv_1')
  })

  it('applyG8AdjustmentWriteback 写入审定行', () => {
    const store = defaultG8AdjStore()
    const next = applyG8AdjustmentWriteback(store, { rowKey: 'fv_1', closingAdjustment: 200 })
    expect(next.fv_1?.closingAdjustment).toBe(200)
  })
})
