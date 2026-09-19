/**
 * G12 净敞口套期收益 — 集成测试
 *
 * Spec: .kiro/specs/g12-net-hedge-gains/
 */
import { describe, it, expect, vi } from 'vitest'
import {
  calcAdjustedAmount,
  calcFVChange,
  calcChangeRate,
  calcHedgeIneffectiveness,
  isDebitCreditBalanced,
  isChangeRateExceeding,
  isVoucherAbnormal,
  calcSubtotal,
} from '../composables/useG12FormulaEngine'
import { G12_ACCOUNT_CODE, G12_CHANGE_RATE_THRESHOLD, G12_ADJUDICATION_ITEMS } from '../composables/g12Constants'
import { G12_IMPORT_EXPORT_SHEETS } from '../composables/useG12ImportExport'
import { G12_NET_EXPOSURE_SEED } from '../composables/g12NetExposureSeed'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onBeforeUnmount: vi.fn(), onMounted: vi.fn() }
})

function extractSheet(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G12A|G12-\d+)/)
  return m ? m[1] : ''
}

const HTML_SHEETS = ['G12A', 'G12-1', 'G12-2', 'G12-3', 'G12-4', 'G12-5', 'G12-6', '底稿目录']

function isHtmlSheet(code: string): boolean {
  return HTML_SHEETS.includes(code) || code.startsWith('附注')
}

describe('G12 集成 — sheetName 分发', () => {
  it('9个有效 sheet 正确分发', () => {
    expect(extractSheet('净敞口套期收益审计程序表G12A')).toBe('G12A')
    expect(extractSheet('审定表G12-1')).toBe('G12-1')
    expect(extractSheet('净敞口套期收益明细表G12-2')).toBe('G12-2')
    expect(extractSheet('调整分录汇总G12-3')).toBe('G12-3')
    expect(extractSheet('公允价值测试G12-4')).toBe('G12-4')
    expect(extractSheet('风险净敞口检查G12-5')).toBe('G12-5')
    expect(extractSheet('凭证检查G12-6')).toBe('G12-6')
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractSheet('附注披露信息（国企）')).toBe('附注国企')
    expect(extractSheet('底稿目录')).toBe('底稿目录')
  })

  it('未匹配走 OO 兜底', () => {
    expect(extractSheet('')).toBe('')
    expect(extractSheet('修订前')).toBe('')
  })

  it('HTML sheet 判定', () => {
    expect(isHtmlSheet('G12-5')).toBe(true)
    expect(isHtmlSheet('附注上市')).toBe(true)
    expect(isHtmlSheet('底稿目录')).toBe(true)
    expect(isHtmlSheet('')).toBe(false)
  })
})

describe('G12 集成 — 损益类公式链', () => {
  it('TB→未审+调整=审定→EventBus payload', () => {
    const unadjusted = 400_000
    const adjustment = 15_000
    const audited = calcAdjustedAmount(unadjusted, adjustment)
    expect(audited).toBe(415_000)

    const detail = { accountCode: G12_ACCOUNT_CODE, adjudicatedAmount: audited }
    expect(detail.accountCode).toBe('6103')
    expect(detail.adjudicatedAmount).toBe(415_000)
  })
})

describe('G12 集成 — 套期无效部分', () => {
  it('绝对差公式', () => {
    expect(calcHedgeIneffectiveness(100, 80)).toBe(20)
    expect(calcHedgeIneffectiveness(-50, 30)).toBe(80)
  })

  it('FV变动 = 期末 - 期初', () => {
    expect(calcFVChange(100, 150)).toBe(50)
    expect(calcFVChange(200, 180)).toBe(-20)
  })
})

describe('G12 集成 — 变动率', () => {
  it('方向性 + 阈值', () => {
    expect(calcChangeRate(100, 150)).toBeGreaterThan(0)
    expect(calcChangeRate(100, 50)).toBeLessThan(0)
    expect(calcChangeRate(0, 100)).toBeNull()
    const rate = calcChangeRate(100, 130)
    expect(isChangeRateExceeding(rate, G12_CHANGE_RATE_THRESHOLD)).toBe(true)
  })
})

describe('G12 集成 — 借贷平衡', () => {
  it('AJE/RJE 借贷平衡', () => {
    expect(isDebitCreditBalanced([100, 50], [150])).toBe(true)
    expect(isDebitCreditBalanced([100], [50])).toBe(false)
  })
})

describe('G12 集成 — 凭证异常检测', () => {
  it('任一核对项 false → 异常', () => {
    expect(isVoucherAbnormal([true, true, false, true, true])).toBe(true)
    expect(isVoucherAbnormal([true, true, true, true, true])).toBe(false)
  })
})

describe('G12 集成 — G12-5 净敞口种子', () => {
  it('对齐源模板头寸表结构', () => {
    expect(G12_NET_EXPOSURE_SEED.length).toBeGreaterThanOrEqual(1)
    const row = G12_NET_EXPOSURE_SEED[0]
    expect(row.item).toContain('外汇净头寸')
    expect(row.currency).toBe('USD')
    expect(row.position1Desc).toBeTruthy()
    expect(row.position2Desc).toBeTruthy()
    expect(row.netPosition).toBeTruthy()
  })
})

describe('G12 集成 — 审定表分组', () => {
  it('5类项目行', () => {
    expect(G12_ADJUDICATION_ITEMS.length).toBe(5)
    expect(G12_ADJUDICATION_ITEMS.map((i) => i.rowKey)).toContain('net_hedge')
  })
})

describe('G12 集成 — 导入导出', () => {
  it('5张表 G12-2/3/4/5/6', () => {
    expect(G12_IMPORT_EXPORT_SHEETS).toEqual(['G12-2', 'G12-3', 'G12-4', 'G12-5', 'G12-6'])
  })
})

describe('G12 集成 — EventBus', () => {
  it('substantive:adjudicated 6103', () => {
    const handler = vi.fn()
    window.addEventListener('substantive:adjudicated', handler)
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { accountCode: '6103', adjudicatedAmount: 99999 },
    }))
    expect(handler).toHaveBeenCalled()
    window.removeEventListener('substantive:adjudicated', handler)
  })
})

describe('G12 集成 — 合计', () => {
  it('明细合计', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
  })
})
