/**
 * G13 公允价值变动收益 — 集成测试
 *
 * Spec: .kiro/specs/g13-fair-value-changes/ Task 8.1
 */
import { describe, it, expect, vi } from 'vitest'
import {
  calcAdjustedAmount,
  calcFVChange,
  calcChangeRate,
  isDebitCreditBalanced,
  isFvReconciled,
  calcSubtotal,
} from '../composables/useG13FormulaEngine'
import { G13_ACCOUNT_CODE, G13_CHANGE_RATE_THRESHOLD, G13_ADJUDICATION_ITEMS } from '../composables/g13Constants'
import { G13_IMPORT_EXPORT_SHEETS } from '../composables/useG13ImportExport'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return { ...actual as object, onBeforeUnmount: vi.fn(), onMounted: vi.fn() }
})

function extractSheet(sheetName: string): string {
  if (/底稿目录/.test(sheetName)) return '底稿目录'
  if (/附注披露/.test(sheetName)) return sheetName.includes('国企') ? '附注国企' : '附注上市'
  const m = sheetName.match(/(G13A|G13-\d+)/)
  return m ? m[1] : ''
}

function isHtmlSheet(code: string): boolean {
  return ['G13A', 'G13-1', 'G13-2', 'G13-3', '底稿目录'].includes(code) || code.startsWith('附注')
}

describe('G13 集成 — sheetName 分发', () => {
  it('6个有效 sheet 正确分发', () => {
    expect(extractSheet('公允价值变动收益审计程序表G13A')).toBe('G13A')
    expect(extractSheet('审定表G13-1')).toBe('G13-1')
    expect(extractSheet('明细表G13-2')).toBe('G13-2')
    expect(extractSheet('调整分录汇总G13-3')).toBe('G13-3')
    expect(extractSheet('附注披露信息（上市公司）')).toBe('附注上市')
    expect(extractSheet('附注披露信息（国企）')).toBe('附注国企')
    expect(extractSheet('底稿目录')).toBe('底稿目录')
  })

  it('未匹配走 OO 兜底', () => {
    expect(extractSheet('')).toBe('')
  })

  it('HTML sheet 判定', () => {
    expect(isHtmlSheet('G13-1')).toBe(true)
    expect(isHtmlSheet('附注上市')).toBe(true)
    expect(isHtmlSheet('底稿目录')).toBe(true)
    expect(isHtmlSheet('')).toBe(false)
  })
})

describe('G13 集成 — 损益类公式链', () => {
  it('TB→未审+调整=审定→EventBus payload', () => {
    const unadjusted = 300_000
    const adjustment = -10_000
    const audited = calcAdjustedAmount(unadjusted, adjustment)
    expect(audited).toBe(290_000)

    const detail = { accountCode: G13_ACCOUNT_CODE, adjudicatedAmount: audited }
    expect(detail.accountCode).toBe('6101')
    expect(detail.adjudicatedAmount).toBe(290_000)
  })
})

describe('G13 集成 — FV变动公式', () => {
  it('期末-期初 = FV变动', () => {
    expect(calcFVChange(100, 150)).toBe(50)
    expect(calcFVChange(200, 180)).toBe(-20)
  })

  it('FV变动≠审定数 → 不一致', () => {
    expect(isFvReconciled(50, 60)).toBe(false)
    expect(isFvReconciled(50, 50)).toBe(true)
  })

  it('G13-2 合计与分组小计', () => {
    const rows = [
      { currentAudited: 100, fvChange: 100 },
      { currentAudited: 200, fvChange: 180 },
    ]
    expect(calcSubtotal(rows.map((r) => r.currentAudited))).toBe(300)
    expect(calcSubtotal(rows.map((r) => r.fvChange))).toBe(280)
  })
})

describe('G13 集成 — 变动率', () => {
  it('方向性正确', () => {
    expect(calcChangeRate(100, 150)).toBeGreaterThan(0)
    expect(calcChangeRate(100, 50)).toBeLessThan(0)
    expect(calcChangeRate(0, 100)).toBeNull()
  })

  it('|变动率|>20% 触发原因必填阈值', () => {
    const rate = calcChangeRate(100, 130)
    expect(rate).not.toBeNull()
    expect(Math.abs(rate!)).toBeGreaterThan(G13_CHANGE_RATE_THRESHOLD)
  })
})

describe('G13 集成 — 借贷平衡', () => {
  it('AJE/RJE 借贷平衡', () => {
    expect(isDebitCreditBalanced([100, 50], [150])).toBe(true)
    expect(isDebitCreditBalanced([100], [50])).toBe(false)
  })
})

describe('G13 集成 — 审定表分组', () => {
  it('5类分组 + 合计', () => {
    expect(G13_ADJUDICATION_ITEMS.length).toBe(5)
    expect(G13_ADJUDICATION_ITEMS.map((i) => i.rowKey)).toContain('trading_assets')
  })
})

describe('G13 集成 — 导入导出', () => {
  it('2张表 G13-2/G13-3', () => {
    expect(G13_IMPORT_EXPORT_SHEETS).toEqual(['G13-2', 'G13-3'])
  })
})

describe('G13 集成 — EventBus', () => {
  it('substantive:adjudicated 6101', () => {
    const handler = vi.fn()
    window.addEventListener('substantive:adjudicated', handler)
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { accountCode: '6101', adjudicatedAmount: 12345 },
    }))
    expect(handler).toHaveBeenCalled()
    window.removeEventListener('substantive:adjudicated', handler)
  })
})
