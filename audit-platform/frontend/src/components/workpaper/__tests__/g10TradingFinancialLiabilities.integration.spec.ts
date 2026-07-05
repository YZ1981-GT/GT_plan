/**
 * G10 交易性金融负债 — 集成测试
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcCreditBalance,
  calcAdjustedAmount,
  calcChangeRate,
  calcL3Reconciliation,
  isDebitCreditBalanced,
  isChangeRateExceeding,
} from '../composables/useG10FormulaEngine'
import {
  G10_ADJUDICATION_ITEMS,
  G10_ACCOUNT_CODE,
  G10_CHANGE_RATE_THRESHOLD,
  G10_DISCLOSURE_LISTED_ROWS,
  G10_DISCLOSURE_SOE_ROWS,
} from '../composables/g10Constants'
import { G10_CLASSIFICATION_SEED } from '../composables/g10ClassificationSeed'
import { G10_DERIVATIVE_SEED } from '../composables/g10DerivativeSeed'
import { G10_IMPORTABLE_SHEETS } from '../composables/useG10ImportExport'
import { enrichG10VoucherRow } from '../composables/useG10VoucherCheck'
import { enrichG10L3Row } from '../composables/useG10L3Reconciliation'
import { validateG10Level3Row } from '../composables/useG10FairValueTest'

function extractSheet(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G10A|G10-\d+)/)
  return m ? m[1] : ''
}

describe('G10 集成 — sheetName 分发', () => {
  it('12 个有效 sheet 正确分发', () => {
    expect(extractSheet('交易性金融负债实质性程序表G10A')).toBe('G10A')
    expect(extractSheet('审定表G10-1')).toBe('G10-1')
    expect(extractSheet('明细表G10-2')).toBe('G10-2')
    expect(extractSheet('调整分录汇总G10-3')).toBe('G10-3')
    expect(extractSheet('分类的适当性检查表G10-4')).toBe('G10-4')
    expect(extractSheet('公允价值测试表G10-5')).toBe('G10-5')
    expect(extractSheet('第三层次公允价值计量的调节表G10-6')).toBe('G10-6')
    expect(extractSheet('凭证检查表G10-7')).toBe('G10-7')
    expect(extractSheet('衍生金融工具核查表G10-8')).toBe('G10-8')
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractSheet('附注披露信息（国企）')).toBe('附注国企')
    expect(extractSheet('底稿目录')).toBe('底稿目录')
  })
})

describe('G10 集成 — 贷方公式', () => {
  it('calcCreditBalance 负债方向', () => {
    expect(calcCreditBalance(100, 50, 20)).toBe(130)
    expect(calcCreditBalance(0, 0, 0)).toBe(0)
  })

  it('审定数 = 未审 + 调整', () => {
    expect(calcAdjustedAmount(100, 10)).toBe(110)
  })

  it('|变动率|>20% 触发', () => {
    const rate = calcChangeRate(100, 130)
    expect(rate).toBeCloseTo(0.3)
    expect(isChangeRateExceeding(rate, G10_CHANGE_RATE_THRESHOLD)).toBe(true)
  })
})

describe('G10 集成 — L3调节表', () => {
  it('负债方向：新增+终止', () => {
    const closing = calcL3Reconciliation(100, 30, 10, 5, 2, 8, 3, 1)
    expect(closing).toBeCloseTo(135)
  })

  it('差异 = 企业期末 - 计算期末', () => {
    const row = enrichG10L3Row({
      rowId: 't1',
      openingBalance: 100,
      currentNew: 20,
      currentTerminated: 5,
      reportedClosing: 120,
    })
    expect(row.variance).toBeCloseTo(row.reportedClosing - row.closingBalance)
  })
})

describe('G10 集成 — G10-7 凭证核对', () => {
  it('check4FairValue ✗ → isAbnormal', () => {
    const row = enrichG10VoucherRow({
      check1OriginalComplete: true,
      check2Authorization: true,
      check3Accounting: true,
      check4FairValueCorrect: false,
    }, 1)
    expect(row.isAbnormal).toBe(true)
  })

  it('借贷平衡', () => {
    expect(isDebitCreditBalanced([100, 50], [150])).toBe(true)
  })
})

describe('G10 集成 — Level3 必填', () => {
  it('Level3 缺估值技术/不可观察输入值', () => {
    const missing = validateG10Level3Row({
      rowId: 'x', seq: 1, liabilityName: '测试', initialDate: '',
      closingUnadjustedQty: 0, closingUnadjustedPrice: 0, closingUnadjustedFV: 0,
      closingAuditedQty: 0, closingAuditedPrice: 0, closingAuditedFV: 0,
      fairValueLevel: 'Level3', valuationMethod: '', methodConsistentWithPrior: '',
      valuationSource: '', inputSourceAndAdjustment: '', valuationTechnique: '',
      unobservableInputDesc: '', unobservableInputValue: '', sensitivityAnalysis: '',
      valuationDocIndex: '',
    })
    expect(missing).toContain('估值技术')
    expect(missing).toContain('不可观察输入值描述')
  })
})

describe('G10 集成 — 种子行数', () => {
  it('G10-4 分类 28 行', () => {
    expect(G10_CLASSIFICATION_SEED.length).toBe(28)
  })

  it('G10-8 衍生 78 行', () => {
    expect(G10_DERIVATIVE_SEED.length).toBe(78)
  })

  it('审定表 24 行', () => {
    expect(G10_ADJUDICATION_ITEMS.length).toBe(24)
  })
})

describe('G10 集成 — 导入导出与附注', () => {
  it('5 张表均可导入导出', () => {
    expect(G10_IMPORTABLE_SHEETS.map((s) => s.code)).toEqual([
      'G10-2', 'G10-3', 'G10-5', 'G10-6', 'G10-7',
    ])
  })

  it('上市附注 46 行（24 审定 + 22 明细）', () => {
    expect(G10_DISCLOSURE_LISTED_ROWS.length).toBe(46)
  })

  it('国企附注 83 行（24 审定 + 59 明细）', () => {
    expect(G10_DISCLOSURE_SOE_ROWS.length).toBe(83)
  })

  it('科目代码 2101', () => {
    expect(G10_ACCOUNT_CODE).toBe('2101')
  })

  it('parseNum 健壮性', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(42)).toBe(42)
  })
})
